from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from agents.execution_agent import ExecutionResult
from agents.rca_agent import RCAAgent, RootCauseAnalysis


def execution(status="failed", stdout="", artifacts=None):
    return ExecutionResult(
        test_file="tests/generated/test_example.py", status=status, exit_code=1,
        duration_seconds=1.0, stdout=stdout, failed_test_names=["test_example"],
        artifacts=artifacts or [],
    )


def model_result(classification):
    return RootCauseAnalysis(
        classification=classification, summary="Grounded summary", probable_root_cause="Grounded cause",
        confidence=.8, evidence=["stdout contains the failure"], missing_evidence=[],
        affected_layer="test", recommended_action="Review the observed failure", retry_recommended=False,
        likely_test_defect=False, likely_application_defect=False, likely_infrastructure_defect=False,
    )


def mock_client(classification):
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(parsed=model_result(classification))
    return client


def test_browser_launch_infrastructure_error_is_deterministic(tmp_path):
    output = "ERROR at setup\nBrowserType.launch: Target closed\nsandbox_host_linux.cc Operation not permitted SIGTRAP"
    client = mock_client("unknown")
    result = RCAAgent(tmp_path, client).analyze(execution(status="error", stdout=output), "browser-run")

    assert result.classification == "browser_launch_error"
    assert result.likely_infrastructure_defect is True
    assert result.likely_application_defect is False
    assert result.likely_test_defect is False
    client.models.generate_content.assert_not_called()
    assert (tmp_path / "reports/executions/browser-run/rca_result.json").is_file()


def test_assertion_failure_is_preclassified_before_gemini(tmp_path):
    client = mock_client("unknown")
    result = RCAAgent(tmp_path, client).analyze(execution(stdout="AssertionError: expected 2, got 1"), "assert-run")
    assert result.classification == "assertion_failure"
    assert "'assertion_failure'" in client.models.generate_content.call_args.kwargs["contents"]


def test_locator_failure(tmp_path):
    result = RCAAgent(tmp_path, mock_client("unknown")).analyze(
        execution(stdout="playwright: waiting for locator('#checkout')"), "locator-run"
    )
    assert result.classification == "locator_failure"


def test_timeout(tmp_path):
    result = RCAAgent(tmp_path, mock_client("unknown")).analyze(
        execution(stdout="TimeoutError: timeout exceeded"), "timeout-run"
    )
    assert result.classification == "timeout"


def test_missing_artifacts_are_explicit(tmp_path):
    result = RCAAgent(tmp_path, mock_client("assertion_failure")).analyze(
        execution(stdout="AssertionError", artifacts=[str(tmp_path / "absent.png")]), "missing-run"
    )
    assert "screenshots unavailable" in result.missing_evidence
    assert "traces unavailable" in result.missing_evidence


def test_passed_test_does_not_require_or_persist_rca(tmp_path):
    client = mock_client("unknown")
    passed = execution(status="passed")
    passed.exit_code = 0
    assert RCAAgent(tmp_path, client).analyze(passed, "pass-run") is None
    client.models.generate_content.assert_not_called()
    assert not Path(tmp_path / "reports/executions/pass-run/rca_result.json").exists()


def test_unauthenticated_inventory_failure_is_authentication_error(tmp_path):
    output = """page = <Page url='https://www.saucedemo.com/'>
Aria snapshot:
- textbox \"Username\"
- textbox \"Password\"
- button \"Login\"
Epic sadface: You can only access '/inventory.html' when you are logged in.
waiting for locator(\"[data-test='inventory-item-name']\")
"""
    result = RCAAgent(tmp_path).analyze(execution(stdout=output), "auth-run")

    assert result.classification == "authentication_error"
    assert result.likely_application_defect is False
    assert result.likely_infrastructure_defect is False
    assert all("locator" not in value.lower() for value in [result.summary, result.probable_root_cause])


def test_missing_storage_state_is_authentication_error(tmp_path):
    result = RCAAgent(tmp_path).analyze(
        execution(status="error", stdout="Authentication setup error: storage state is missing"),
        "missing-auth-run",
    )
    assert result.classification == "authentication_error"
