"""Evidence-grounded root-cause analysis for test execution failures."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field

from agents.execution_agent import ExecutionResult
from agents.gemini_retry import call_gemini_with_retry

load_dotenv()

Classification = Literal[
    "infrastructure_error", "browser_launch_error", "authentication_error",
    "locator_failure", "assertion_failure", "timeout", "network_error",
    "application_error", "test_code_error", "unknown",
]


class RootCauseAnalysis(BaseModel):
    classification: Classification
    summary: str
    probable_root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    affected_layer: str
    recommended_action: str
    retry_recommended: bool
    likely_test_defect: bool
    likely_application_defect: bool
    likely_infrastructure_defect: bool


class RCAAgent:
    """Classify a failed execution, then ask Gemini only about available evidence."""

    MODEL = "gemini-2.5-flash"
    SCREENSHOT_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
    TRACE_SUFFIXES = {".zip", ".trace"}

    def __init__(
        self,
        project_root: str | Path | None = None,
        client=None,
        executions_dir: str | Path | None = None,
    ):
        self.project_root = Path(project_root or Path(__file__).resolve().parents[1]).resolve()
        self.executions_dir = Path(
            executions_dir or self.project_root / "reports" / "executions"
        ).resolve()
        self.client = client

    def analyze(
        self,
        execution_result: ExecutionResult,
        run_id: str,
        *,
        application_map: dict[str, Any] | None = None,
        grounding_evidence: list[str] | None = None,
        console_errors: list[str] | None = None,
        page_errors: list[str] | None = None,
    ) -> RootCauseAnalysis | None:
        """Create and persist RCA for a failed/error execution; return None for passes."""
        if execution_result.status == "passed":
            return None
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
            raise ValueError("run_id may contain only letters, numbers, dot, underscore, and hyphen")

        classification = self.pre_classify(execution_result)
        available, missing = self._collect_evidence(
            execution_result, application_map, grounding_evidence,
            console_errors, page_errors,
        )

        # No page existed in these classes. A model must not speculate about page,
        # DOM, locator, generated-test, application, or functional behavior.
        if classification == "authentication_error":
            result = self._authentication_failure_rca(execution_result, available, missing)
        elif classification in {"browser_launch_error", "infrastructure_error"} and self._failed_before_page(
            execution_result, classification
        ):
            result = self._setup_failure_rca(classification, execution_result, missing)
        else:
            try:
                result = self._gemini_rca(classification, available, missing)
            except Exception as error:
                result = self._fallback_rca(classification, available, missing, error)
        self._persist(result, run_id)
        return result

    @staticmethod
    def pre_classify(result: ExecutionResult) -> Classification:
        text = f"{result.stdout}\n{result.stderr}".lower()
        rules: list[tuple[Classification, tuple[str, ...]]] = [
            ("browser_launch_error", ("browsertype.launch", "browser has been closed", "failed to launch browser", "executable doesn't exist")),
            ("authentication_error", (
                "401 unauthorized", "403 forbidden", "authentication failed", "login failed",
                "authentication setup error", "when you are logged in",
                "storage state is missing", "storage state is invalid",
            )),
            ("locator_failure", ("waiting for locator", "locator resolved to", "strict mode violation", "no element found", "element not found")),
            ("assertion_failure", ("assertionerror", "expect(", "assert ")),
            ("timeout", ("timeouterror", "timed out", "timeout exceeded")),
            ("network_error", ("err_connection", "connection refused", "name_not_resolved", "networkerror")),
            ("application_error", ("500 internal server error", "502 bad gateway", "503 service unavailable")),
            ("test_code_error", ("syntaxerror", "nameerror", "typeerror", "importerror", "modulenotfounderror")),
            ("infrastructure_error", ("operation not permitted", "permission denied", "no space left on device", "project virtual environment python not found")),
        ]
        for classification, markers in rules:
            if any(marker in text for marker in markers):
                return classification
        if result.status == "error" and ("error at setup" in text or "fixture" in text):
            return "infrastructure_error"
        return "unknown"

    @staticmethod
    def _failed_before_page(result: ExecutionResult, classification: Classification) -> bool:
        text = f"{result.stdout}\n{result.stderr}".lower()
        return classification == "browser_launch_error" or any(
            marker in text for marker in ("error at setup", "browser = await", "page creation", "fixture 'page'")
        )

    def _collect_evidence(
        self,
        result: ExecutionResult,
        application_map: dict[str, Any] | None,
        grounding_evidence: list[str] | None,
        console_errors: list[str] | None,
        page_errors: list[str] | None,
    ) -> tuple[dict[str, Any], list[str]]:
        available: dict[str, Any] = {"execution_result": result.model_dump(exclude={"artifacts"})}
        if result.stdout:
            available["stdout"] = result.stdout
        if result.stderr:
            available["stderr"] = result.stderr
        if result.failed_test_names:
            available["failed_test_names"] = result.failed_test_names

        existing = [Path(item) for item in result.artifacts if Path(item).is_file()]
        screenshots = [str(path) for path in existing if path.suffix.lower() in self.SCREENSHOT_SUFFIXES]
        traces = [str(path) for path in existing if path.suffix.lower() in self.TRACE_SUFFIXES or "trace" in path.name.lower()]
        missing: list[str] = []
        if screenshots:
            available["screenshots"] = screenshots
        else:
            missing.append("screenshots unavailable")
        if traces:
            available["traces"] = traces
        else:
            missing.append("traces unavailable")
        if console_errors:
            available["console_errors"] = console_errors
        else:
            missing.append("console errors unavailable")
        if page_errors:
            available["page_errors"] = page_errors
        else:
            missing.append("page errors unavailable")
        if application_map is None:
            map_path = self.project_root / "application_context" / "authenticated_application_map.json"
            if map_path.is_file():
                try:
                    loaded_map = json.loads(map_path.read_text(encoding="utf-8"))
                    if isinstance(loaded_map, dict):
                        application_map = loaded_map
                except (OSError, json.JSONDecodeError):
                    # An unreadable/invalid file is not usable evidence.
                    pass
        if application_map is not None:
            available["application_map"] = application_map
        else:
            missing.append("application map unavailable")
        if grounding_evidence:
            available["generated_test_grounding_evidence"] = grounding_evidence
        else:
            missing.append("generated-test grounding evidence unavailable")
        return available, missing

    @staticmethod
    def _setup_failure_rca(
        classification: Classification, result: ExecutionResult, missing: list[str]
    ) -> RootCauseAnalysis:
        text = f"{result.stdout}\n{result.stderr}"
        sandbox = "sandbox_host_linux.cc" in text and "Operation not permitted" in text
        if classification == "browser_launch_error":
            cause = (
                "Chromium failed during launch because the host rejected a browser sandbox operation."
                if sandbox else "The browser failed during launch, before page creation succeeded."
            )
            action = "Correct the host/container permissions or browser sandbox configuration, then retry the execution."
        else:
            cause = "Test setup failed before page creation succeeded."
            action = "Correct the execution environment or setup failure, then retry the execution."
        evidence = ["Execution status is error."]
        if "BrowserType.launch" in text:
            evidence.append("The traceback fails in BrowserType.launch from the page fixture.")
        if sandbox:
            evidence.append("Chromium logged sandbox_host_linux.cc: Operation not permitted and exited with SIGTRAP.")
        return RootCauseAnalysis(
            classification=classification,
            summary="Execution stopped during environment/browser setup before any application page was created.",
            probable_root_cause=cause,
            confidence=0.99 if sandbox else 0.9,
            evidence=evidence,
            missing_evidence=missing,
            affected_layer="browser infrastructure" if classification == "browser_launch_error" else "execution infrastructure",
            recommended_action=action,
            retry_recommended=True,
            likely_test_defect=False,
            likely_application_defect=False,
            likely_infrastructure_defect=True,
        )

    @staticmethod
    def _authentication_failure_rca(
        result: ExecutionResult, available: dict[str, Any], missing: list[str]
    ) -> RootCauseAnalysis:
        text = f"{result.stdout}\n{result.stderr}".lower()
        state_problem = "storage state is missing" in text or "storage state is invalid" in text
        protected_route = "when you are logged in" in text
        login_form = all(marker in text for marker in ('"username"', '"password"', '"login"'))
        evidence = ["Execution did not pass."]
        if state_problem:
            evidence.append("The authenticated page fixture reported missing or invalid storage state.")
        if protected_route:
            evidence.append("SauceDemo explicitly rejected protected inventory access because the session was not logged in.")
        if login_form:
            evidence.append("The failure output's ARIA snapshot contains Username, Password, and Login controls.")
        if "page = <page url='https://www.saucedemo.com/'" in text:
            evidence.append("The observed page URL remained the SauceDemo login page.")
        return RootCauseAnalysis(
            classification="authentication_error",
            summary="The test could not establish an authenticated browser context.",
            probable_root_cause=(
                "The generated-test fixture could not load a usable authenticated storage state."
                if state_problem else
                "The protected inventory route redirected to the login page because the browser context was unauthenticated."
            ),
            confidence=0.99 if state_problem or (protected_route and login_form) else 0.9,
            evidence=evidence,
            missing_evidence=missing,
            affected_layer="test authentication setup",
            recommended_action="Create a valid authenticated storage state and restore it when constructing the Playwright context, then rerun.",
            retry_recommended=True,
            likely_test_defect=True,
            likely_application_defect=False,
            likely_infrastructure_defect=False,
        )

    @staticmethod
    def _fallback_rca(
        classification: Classification, available: dict[str, Any], missing: list[str], error: Exception
    ) -> RootCauseAnalysis:
        execution = available.get("execution_result", {})
        return RootCauseAnalysis(
            classification=classification,
            summary="Execution failed; deterministic RCA was retained because model-assisted analysis was unavailable.",
            probable_root_cause=f"The execution evidence matched the deterministic {classification} classification.",
            confidence=0.7 if classification != "unknown" else 0.4,
            evidence=[
                f"Execution status is {execution.get('status', 'unknown')}.",
                f"RCA model assistance was unavailable: {type(error).__name__}.",
            ],
            missing_evidence=missing,
            affected_layer="test execution",
            recommended_action="Review the retained execution artifacts and correct the classified failure before rerunning.",
            retry_recommended=classification in {"timeout", "network_error", "infrastructure_error", "unknown"},
            likely_test_defect=classification in {"locator_failure", "assertion_failure", "test_code_error"},
            likely_application_defect=classification == "application_error",
            likely_infrastructure_defect=classification in {"browser_launch_error", "infrastructure_error", "network_error"},
        )

    def _gemini_rca(
        self, classification: Classification, available: dict[str, Any], missing: list[str]
    ) -> RootCauseAnalysis:
        client = self.client
        if client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY is required for non-setup RCA")
            client = genai.Client(api_key=api_key)
        prompt = f"""Analyze this test failure using ONLY the JSON evidence below.
The deterministic classification is {classification!r}; preserve it.
Never invent observations or claim unavailable artifacts were inspected.
List unavailable evidence exactly as supplied. Calibrate defect flags and confidence to evidence.

AVAILABLE EVIDENCE:
{json.dumps(available, indent=2)}

MISSING EVIDENCE:
{json.dumps(missing, indent=2)}
"""
        response = call_gemini_with_retry(
            lambda: client.models.generate_content(
                model=self.MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json", "response_schema": RootCauseAnalysis},
            )
        )
        result = response.parsed
        if not isinstance(result, RootCauseAnalysis):
            result = RootCauseAnalysis.model_validate_json(response.text)
        result.classification = classification
        result.missing_evidence = list(dict.fromkeys([*missing, *result.missing_evidence]))
        return result

    def _persist(self, result: RootCauseAnalysis, run_id: str) -> None:
        run_dir = self.executions_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "rca_result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
