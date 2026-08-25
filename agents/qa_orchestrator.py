"""End-to-end orchestration for the AI QA Engineer workflow."""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field

from agents.application_discovery_agent import ApplicationDiscoveryAgent
from agents.authentication_agent import AuthenticationAgent
from agents.execution_agent import ExecutionAgent, ExecutionResult
from agents.gemini_retry import error_type as workflow_error_type, retry_attempts
from agents.rca_agent import RCAAgent, RootCauseAnalysis
from agents.requirement_agent import RequirementAgent, RequirementAnalysis
from agents.test_generation_agent import GeneratedTest, TestGenerationAgent
from tools.test_file_writer import TestFileWriter

OverallStatus = Literal["PASSED", "FAILED", "BLOCKED", "PARTIAL"]


class WorkflowMetrics(BaseModel):
    """Measurements derived from the current run; no benchmark values are assumed."""

    requirement_analysis_latency_seconds: float | None = None
    generation_latency_seconds: float | None = None
    execution_duration_seconds: float = 0.0
    rca_latency_seconds: float | None = None
    grounding_success_rate: float | None = None
    generated_to_skipped_ratio: float | None = None
    generated_count: int = 0
    skipped_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    error_count: int = 0


class WorkflowResult(BaseModel):
    run_id: str
    requirement: str
    requirement_analysis: RequirementAnalysis | None = None
    application_discovery_status: str
    generated_tests: list[GeneratedTest] = Field(default_factory=list)
    skipped_tests: list[GeneratedTest] = Field(default_factory=list)
    execution_results: list[ExecutionResult] = Field(default_factory=list)
    rca_results: list[RootCauseAnalysis] = Field(default_factory=list)
    overall_status: OverallStatus
    failed_stage: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    retry_attempts: int = 0
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    metrics: WorkflowMetrics = Field(default_factory=WorkflowMetrics)


class QAOrchestrator:
    """Coordinate existing agents without taking over their responsibilities."""

    def __init__(
        self, *, project_root: str | Path | None = None, base_url: str | None = None,
        requirement_agent=None, authentication_agent=None, discovery_agent=None,
        generation_agent=None, file_writer=None, execution_agent=None, rca_agent=None,
        progress: Callable[[str], None] | None = None,
    ):
        self.project_root = Path(project_root or Path(__file__).resolve().parents[1]).resolve()
        self.context_path = self.project_root / "application_context/authenticated_application_map.json"
        self.storage_state_path = self.project_root / "application_context/storage_state.json"
        self.base_url = base_url or os.getenv("QA_BASE_URL") or self._mapped_base_url()
        self.requirement_agent = requirement_agent
        self.authentication_agent = authentication_agent
        self.discovery_agent = discovery_agent
        self.generation_agent = generation_agent
        self.file_writer = file_writer
        self.execution_agent = execution_agent
        self.rca_agent = rca_agent
        self.progress = progress or print

    def _mapped_base_url(self) -> str:
        try:
            value = json.loads(self.context_path.read_text(encoding="utf-8"))
            return str(value.get("base_url") or "")
        except (OSError, json.JSONDecodeError):
            return ""

    @staticmethod
    def _valid_context(context: object) -> bool:
        return (isinstance(context, dict) and context.get("authenticated") is True
                and bool(context.get("base_url")) and isinstance(context.get("page"), dict)
                and bool(context["page"].get("url")))

    async def _application_context(self) -> tuple[dict, str]:
        try:
            context = json.loads(self.context_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            context = None
        if self._valid_context(context):
            return context, "authenticated_context_valid"
        if not self.base_url:
            raise RuntimeError("No valid authenticated application context or QA_BASE_URL")
        authentication = self.authentication_agent or AuthenticationAgent(self.base_url)
        discovery = self.discovery_agent or ApplicationDiscoveryAgent(self.base_url, str(self.storage_state_path))
        await authentication.login()
        context = await discovery.discover_authenticated()
        if not self._valid_context(context):
            raise RuntimeError("Discovery did not return authenticated application evidence")
        discovery.save_authenticated(context)
        self.context_path.parent.mkdir(parents=True, exist_ok=True)
        self.context_path.write_text(json.dumps(context, indent=2), encoding="utf-8")
        return context, "authenticated_context_refreshed"

    async def run(self, requirement: str) -> WorkflowResult:
        requirement = requirement.strip()
        if not requirement:
            raise ValueError("requirement must not be empty")
        run_id = f"run-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
        run_dir = self.project_root / "reports/runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        started_at, started_clock = datetime.now(timezone.utc), time.monotonic()
        analysis = None
        generated, skipped, executions, rcas = [], [], [], []
        metrics = WorkflowMetrics()
        discovery_status = "not_started"
        try:
            self.progress("[1/5] Analyzing requirement...")
            phase_clock = time.monotonic()
            analysis = (self.requirement_agent or RequirementAgent()).analyze(requirement)
            metrics.requirement_analysis_latency_seconds = round(
                time.monotonic() - phase_clock, 6
            )
            self._write_json(run_dir / "requirement_analysis.json", analysis.model_dump(mode="json"))
        except Exception as error:
            return self._finish(run_id, run_dir, requirement, analysis, discovery_status,
                                generated, skipped, executions, rcas, "BLOCKED", started_at,
                                started_clock, metrics, failed_stage="requirement_analysis",
                                error=error)

        try:
            self.progress("[2/5] Loading application evidence...")
            application_map, discovery_status = await self._application_context()
        except Exception as error:
            discovery_status = f"failed: {type(error).__name__}: {error}"
            return self._finish(run_id, run_dir, requirement, analysis, discovery_status,
                                generated, skipped, executions, rcas, "BLOCKED", started_at,
                                started_clock, metrics, failed_stage="application_discovery",
                                error=error)

        self.progress("[3/5] Generating grounded tests...")
        generation_agent = self.generation_agent or TestGenerationAgent(self.context_path)
        writer = self.file_writer or TestFileWriter(self.project_root / "tests/generated")
        generated_archive = run_dir / "generated_tests"
        generated_archive.mkdir(exist_ok=True)
        phase_clock = time.monotonic()
        for scenario in analysis.scenarios:
            try:
                candidate = generation_agent.generate(scenario)
            except Exception as error:
                skipped.append(GeneratedTest(status="cannot_generate", test_name=scenario.id,
                    missing_evidence=[f"generation error: {type(error).__name__}: {error}"]))
                continue
            if candidate.status != "generated" or candidate.grounded is not True:
                skipped.append(candidate)
                continue
            saved_path = writer.save(candidate.filename, candidate.code)
            shutil.copy2(saved_path, generated_archive / candidate.filename)
            generated.append(candidate)
        metrics.generation_latency_seconds = round(time.monotonic() - phase_clock, 6)

        self.progress("[4/5] Executing tests...")
        execution_agent = self.execution_agent or ExecutionAgent(self.project_root, run_dir / "executions")
        rca_agent = self.rca_agent or RCAAgent(
            self.project_root, executions_dir=run_dir / "executions"
        )
        for index, test in enumerate(generated, start=1):
            execution_id = f"test-{index:03d}"
            try:
                result = execution_agent.execute(test, run_id=execution_id)
            except Exception as error:
                result = ExecutionResult(test_file=test.filename, status="error", exit_code=None,
                    duration_seconds=0.0, stderr=f"ExecutionAgent raised {type(error).__name__}: {error}")
            executions.append(result)
            execution_dir = run_dir / "executions" / execution_id
            self._write_json(execution_dir / "execution_result.json", result.model_dump(mode="json"))
        metrics.execution_duration_seconds = round(
            sum(item.duration_seconds for item in executions), 6
        )

        self.progress("[5/5] Performing RCA...")
        phase_clock = time.monotonic()
        for index, (test, result) in enumerate(zip(generated, executions), start=1):
            execution_id = f"test-{index:03d}"
            execution_dir = run_dir / "executions" / execution_id
            if result.status in {"failed", "error"}:
                try:
                    rca = rca_agent.analyze(result, execution_id, application_map=application_map,
                                            grounding_evidence=test.evidence_used)
                except Exception as error:
                    (execution_dir / "rca_error.txt").write_text(
                        f"{type(error).__name__}: {error}", encoding="utf-8"
                    )
                    classification = RCAAgent.pre_classify(result)
                    rca = RCAAgent._fallback_rca(
                        classification,
                        {"execution_result": result.model_dump(exclude={"artifacts"})},
                        ["model-assisted RCA unavailable"],
                        error,
                    )
                if rca is not None:
                    rcas.append(rca)
                    self._write_json(execution_dir / "rca_result.json", rca.model_dump(mode="json"))
        metrics.rca_latency_seconds = round(time.monotonic() - phase_clock, 6)
        self._complete_metrics(metrics, generated, skipped, executions)

        status = self._overall_status(generated, skipped, executions)
        return self._finish(run_id, run_dir, requirement, analysis, discovery_status,
                            generated, skipped, executions, rcas, status, started_at,
                            started_clock, metrics)

    @staticmethod
    def _complete_metrics(metrics, generated, skipped, executions) -> None:
        metrics.generated_count = len(generated)
        metrics.skipped_count = len(skipped)
        evaluated = metrics.generated_count + metrics.skipped_count
        metrics.grounding_success_rate = (
            round(metrics.generated_count / evaluated, 6) if evaluated else None
        )
        metrics.generated_to_skipped_ratio = (
            round(metrics.generated_count / metrics.skipped_count, 6)
            if metrics.skipped_count else None
        )
        metrics.passed_count = sum(item.status == "passed" for item in executions)
        metrics.failed_count = sum(item.status == "failed" for item in executions)
        metrics.error_count = sum(item.status == "error" for item in executions)

    @staticmethod
    def _overall_status(generated, skipped, executions) -> OverallStatus:
        if not generated:
            return "BLOCKED"
        has_problem = any(item.status != "passed" for item in executions)
        if has_problem and (any(item.status == "passed" for item in executions) or skipped):
            return "PARTIAL"
        if has_problem:
            return "FAILED"
        return "PARTIAL" if skipped else "PASSED"

    def _finish(self, run_id, run_dir, requirement, analysis, discovery_status,
                generated, skipped, executions, rcas, status, started_at, started_clock,
                metrics, failed_stage=None, error=None) -> WorkflowResult:
        self._complete_metrics(metrics, generated, skipped, executions)
        result = WorkflowResult(run_id=run_id, requirement=requirement,
            requirement_analysis=analysis, application_discovery_status=discovery_status,
            generated_tests=generated, skipped_tests=skipped, execution_results=executions,
            rca_results=rcas, overall_status=status, started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            duration_seconds=round(time.monotonic() - started_clock, 6), metrics=metrics,
            failed_stage=failed_stage,
            error_type=workflow_error_type(error) if error else None,
            error_message=str(error) if error else None,
            retry_attempts=retry_attempts(error) if error else 0)
        payload = result.model_dump(mode="json")
        self._write_json(run_dir / "workflow_result.json", payload)
        self._write_json(run_dir / "final_report.json", payload)
        return result

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")
