import subprocess

import pytest

from agents.execution_agent import ExecutionAgent
from agents.test_generation_agent import GeneratedTest


def generated(filename="test_example.py", grounded=True):
    return GeneratedTest(
        status="generated", filename=filename, test_name="test_example",
        code="def test_example(): pass", grounded=grounded,
        evidence_used=["page.url=https://example.test"],
    )


def make_project(tmp_path):
    (tmp_path / "tests" / "generated").mkdir(parents=True)
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    test_file = tmp_path / "tests" / "generated" / "test_example.py"
    test_file.write_text("def test_example(): pass\n", encoding="utf-8")
    return ExecutionAgent(tmp_path)


def test_passed_execution(tmp_path, monkeypatch):
    agent = make_project(tmp_path)
    observed = {}

    def run(command, **kwargs):
        observed["command"] = command
        return subprocess.CompletedProcess(
            command, 0, stdout="1 passed in 0.10s\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", run)

    result = agent.execute(generated(), run_id="pass-run")

    assert result.status == "passed"
    assert result.exit_code == 0
    assert result.failed_test_names == []
    assert observed["command"][-2:] == ["-m", "generated"]
    assert any(path.endswith("execution_result.json") for path in result.artifacts)


def test_failed_execution_preserves_failure(tmp_path, monkeypatch):
    agent = make_project(tmp_path)
    output = "FAILED tests/generated/test_example.py::test_example - AssertionError\n"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], 1, stdout=output, stderr="browser error"
    ))

    result = agent.execute(generated(), run_id="fail-run")

    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.failed_test_names == ["test_example"]
    assert result.stdout == output
    assert result.stderr == "browser error"


def test_rejects_ungrounded_test(tmp_path):
    agent = ExecutionAgent(tmp_path)

    with pytest.raises(ValueError, match="only grounded"):
        agent.execute(generated(grounded=False))


def test_missing_test_file_returns_error(tmp_path):
    agent = make_project(tmp_path)

    result = agent.execute(generated("test_missing.py"), run_id="missing-run")

    assert result.status == "error"
    assert result.exit_code is None
    assert "not found" in result.stderr
    assert any(path.endswith("stderr.txt") for path in result.artifacts)


def test_pytest_setup_failure_is_an_error(tmp_path, monkeypatch):
    agent = make_project(tmp_path)
    output = "ERROR tests/generated/test_example.py::test_example\n1 error in 0.10s\n"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], 1, stdout=output, stderr=""
    ))

    result = agent.execute(generated(), run_id="setup-error-run")

    assert result.status == "error"
    assert result.failed_test_names == ["test_example"]
