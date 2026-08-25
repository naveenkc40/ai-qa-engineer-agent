import json
from types import SimpleNamespace

import pytest
from google.genai.errors import ServerError

from agents.execution_agent import ExecutionResult
from agents.qa_orchestrator import QAOrchestrator
from agents.rca_agent import RootCauseAnalysis
from agents.requirement_agent import RequirementAnalysis, TestScenario as Scenario
from agents.test_generation_agent import GeneratedTest


def analysis(count=1):
    return RequirementAnalysis(feature="Cart", summary="Test cart", scenarios=[
        Scenario(id=f"S{i}", title=f"Scenario {i}", description="Cart behavior",
                     scenario_type="positive", priority="high", steps=["Use cart"],
                     expected_result="Cart updates") for i in range(1, count + 1)
    ])


def generated(index=1):
    return GeneratedTest(status="generated", filename=f"test_{index}.py",
                         test_name=f"test_{index}", code=f"def test_{index}(): pass\n",
                         grounded=True, evidence_used=["page.url=https://example.test/inventory"])


def cannot_generate():
    return GeneratedTest(status="cannot_generate", missing_evidence=["checkout is not discovered"])


def execution(status):
    return ExecutionResult(test_file="test.py", status=status,
                           exit_code=0 if status == "passed" else 1,
                           duration_seconds=0.1,
                           stdout="1 passed" if status == "passed" else "AssertionError")


def rca(classification="assertion_failure"):
    return RootCauseAnalysis(classification=classification, summary="Failure", probable_root_cause="Observed",
        confidence=.9, evidence=["output"], affected_layer="test", recommended_action="Review",
        retry_recommended=False, likely_test_defect=False, likely_application_defect=True,
        likely_infrastructure_defect=classification == "infrastructure_error")


class SequenceGenerator:
    def __init__(self, values):
        self.values = iter(values)
    def generate(self, scenario):
        return next(self.values)


class SequenceExecutor:
    def __init__(self, statuses):
        self.statuses = iter(statuses)
        self.calls = []
    def execute(self, test, run_id):
        assert test.grounded is True
        self.calls.append(test)
        return execution(next(self.statuses))


class RecordingRCA:
    def __init__(self):
        self.calls = []
    def analyze(self, result, run_id, **kwargs):
        self.calls.append(result)
        return rca("infrastructure_error" if result.status == "error" else "assertion_failure")


def make_orchestrator(tmp_path, generated_values, statuses, scenario_count=None):
    count = scenario_count or len(generated_values)
    context_dir = tmp_path / "application_context"
    context_dir.mkdir()
    context_dir.joinpath("authenticated_application_map.json").write_text(json.dumps({
        "authenticated": True, "base_url": "https://example.test",
        "page": {"url": "https://example.test/inventory"},
    }), encoding="utf-8")
    executor, rca_agent = SequenceExecutor(statuses), RecordingRCA()
    orchestrator = QAOrchestrator(project_root=tmp_path,
        requirement_agent=SimpleNamespace(analyze=lambda value: analysis(count)),
        generation_agent=SequenceGenerator(generated_values), execution_agent=executor,
        rca_agent=rca_agent, progress=lambda value: None)
    return orchestrator, executor, rca_agent


@pytest.mark.asyncio
async def test_full_successful_workflow(tmp_path):
    orchestrator, executor, rca_agent = make_orchestrator(tmp_path, [generated()], ["passed"])
    result = await orchestrator.run("Add a product")
    assert result.overall_status == "PASSED"
    assert len(result.execution_results) == 1
    assert rca_agent.calls == []
    run_dir = tmp_path / "reports/runs" / result.run_id
    assert (run_dir / "workflow_result.json").is_file()
    assert (run_dir / "requirement_analysis.json").is_file()
    assert (run_dir / "generated_tests/test_1.py").is_file()
    assert (run_dir / "final_report.json").is_file()
    assert result.metrics.generated_count == 1
    assert result.metrics.skipped_count == 0
    assert result.metrics.grounding_success_rate == 1.0
    assert result.metrics.generated_to_skipped_ratio is None
    assert result.metrics.passed_count == 1
    assert result.metrics.failed_count == result.metrics.error_count == 0
    assert result.metrics.requirement_analysis_latency_seconds is not None
    assert result.metrics.generation_latency_seconds is not None
    assert result.metrics.execution_duration_seconds == 0.1
    assert result.metrics.rca_latency_seconds is not None


@pytest.mark.asyncio
async def test_cannot_generate_scenario_is_never_executed(tmp_path):
    orchestrator, executor, rca_agent = make_orchestrator(tmp_path, [cannot_generate()], [])
    result = await orchestrator.run("Checkout")
    assert result.overall_status == "BLOCKED"
    assert len(result.skipped_tests) == 1
    assert executor.calls == [] and rca_agent.calls == []
    assert result.metrics.grounding_success_rate == 0.0
    assert result.metrics.generated_to_skipped_ratio == 0.0


@pytest.mark.asyncio
async def test_failed_execution_invokes_rca(tmp_path):
    orchestrator, _, rca_agent = make_orchestrator(tmp_path, [generated()], ["failed"])
    result = await orchestrator.run("Add a product")
    assert result.overall_status == "FAILED"
    assert len(rca_agent.calls) == len(result.rca_results) == 1


@pytest.mark.asyncio
async def test_infrastructure_error_invokes_rca(tmp_path):
    orchestrator, _, rca_agent = make_orchestrator(tmp_path, [generated()], ["error"])
    result = await orchestrator.run("Add a product")
    assert result.overall_status == "FAILED"
    assert result.rca_results[0].classification == "infrastructure_error"
    assert len(rca_agent.calls) == 1


@pytest.mark.asyncio
async def test_discovery_failure_blocks_generation(tmp_path):
    context_dir = tmp_path / "application_context"
    context_dir.mkdir()
    context_dir.joinpath("authenticated_application_map.json").write_text("{}", encoding="utf-8")
    generator = SequenceGenerator([generated()])
    discovery = SimpleNamespace(discover_authenticated=lambda: None)
    orchestrator = QAOrchestrator(project_root=tmp_path, base_url="https://example.test",
        requirement_agent=SimpleNamespace(analyze=lambda value: analysis()),
        authentication_agent=SimpleNamespace(login=lambda: (_ for _ in ()).throw(RuntimeError("login failed"))),
        discovery_agent=discovery, generation_agent=generator, progress=lambda value: None)
    result = await orchestrator.run("Add a product")
    assert result.overall_status == "BLOCKED"
    assert "login failed" in result.application_discovery_status
    assert result.generated_tests == [] and result.execution_results == []


@pytest.mark.asyncio
async def test_requirement_failure_is_reported_without_corrupting_discovery_status(tmp_path):
    error = ServerError(503, {"error": {
        "code": 503, "status": "UNAVAILABLE", "message": "The service is currently unavailable"
    }})
    error.retry_attempts = 4
    orchestrator = QAOrchestrator(
        project_root=tmp_path,
        requirement_agent=SimpleNamespace(analyze=lambda value: (_ for _ in ()).throw(error)),
        progress=lambda value: None,
    )

    result = await orchestrator.run("Add a product")

    assert result.failed_stage == "requirement_analysis"
    assert result.error_type == "service_unavailable"
    assert result.error_message == str(error)
    assert result.retry_attempts == 4
    assert result.overall_status == "BLOCKED"
    assert result.application_discovery_status == "not_started"


@pytest.mark.asyncio
async def test_mixed_pass_fail_continues_and_only_failure_gets_rca(tmp_path):
    orchestrator, executor, rca_agent = make_orchestrator(
        tmp_path, [generated(1), generated(2)], ["failed", "passed"])
    result = await orchestrator.run("Exercise cart")
    assert result.overall_status == "PARTIAL"
    assert len(executor.calls) == 2
    assert [item.status for item in result.execution_results] == ["failed", "passed"]
    assert len(rca_agent.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "error"])
async def test_every_nonpassing_execution_invokes_rca(tmp_path, status):
    orchestrator, _, rca_agent = make_orchestrator(tmp_path, [generated()], [status])
    result = await orchestrator.run("Add a product")
    assert [call.status for call in rca_agent.calls] == [status]
    assert len(result.rca_results) == 1


@pytest.mark.asyncio
async def test_failed_execution_retains_rca_when_rca_service_raises(tmp_path):
    orchestrator, _, _ = make_orchestrator(tmp_path, [generated()], ["failed"])
    orchestrator.rca_agent = SimpleNamespace(
        analyze=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("service unavailable"))
    )

    result = await orchestrator.run("Add a product")

    assert result.overall_status == "FAILED"
    assert len(result.rca_results) == 1
    assert result.rca_results[0].classification == "assertion_failure"
