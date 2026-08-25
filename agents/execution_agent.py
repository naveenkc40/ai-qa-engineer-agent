"""Execute grounded generated Playwright tests and retain failure evidence."""

from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from agents.test_generation_agent import GeneratedTest


class ExecutionResult(BaseModel):
    test_file: str
    status: Literal["passed", "failed", "error"]
    exit_code: int | None
    duration_seconds: float
    stdout: str = ""
    stderr: str = ""
    failed_test_names: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class ExecutionAgent:
    """Run one already-generated, grounded test in an isolated pytest process."""

    def __init__(
        self,
        project_root: str | Path | None = None,
        executions_dir: str | Path | None = None,
    ):
        self.project_root = Path(project_root or Path(__file__).resolve().parents[1]).resolve()
        self.generated_tests_dir = self.project_root / "tests" / "generated"
        self.executions_dir = Path(
            executions_dir or self.project_root / "reports" / "executions"
        ).resolve()
        self.python = self.project_root / ".venv" / "bin" / "python"

    def execute(self, generated: GeneratedTest, run_id: str | None = None) -> ExecutionResult:
        if generated.status != "generated" or generated.grounded is not True:
            raise ValueError("ExecutionAgent accepts only grounded GeneratedTest results")

        test_file = self._resolve_test_file(generated.filename)
        safe_run_id = run_id or f"run-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", safe_run_id):
            raise ValueError("run_id may contain only letters, numbers, dot, underscore, and hyphen")
        artifact_dir = self.executions_dir / safe_run_id
        artifact_dir.mkdir(parents=True, exist_ok=False)

        if not test_file.is_file():
            result = ExecutionResult(
                test_file=str(test_file), status="error", exit_code=None,
                duration_seconds=0.0,
                stderr=f"Generated test file not found: {test_file}",
            )
            return self._persist_result(result, artifact_dir)
        if not self.python.is_file():
            result = ExecutionResult(
                test_file=str(test_file), status="error", exit_code=None,
                duration_seconds=0.0,
                stderr=f"Project virtual environment Python not found: {self.python}",
            )
            return self._persist_result(result, artifact_dir)

        environment = os.environ.copy()
        environment["EXECUTION_ARTIFACT_DIR"] = str(artifact_dir)
        command = [
            # pytest.ini excludes generated/external tests from normal quality
            # gates. This is the explicit, grounded execution path, so override
            # that default selection for the single accepted test file.
            str(self.python), "-m", "pytest", str(test_file), "-q", "-m", "generated",
        ]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command, cwd=self.project_root, env=environment,
                capture_output=True, text=True, check=False,
            )
            duration = time.monotonic() - started
            status = self._status(completed.returncode, completed.stdout)
            result = ExecutionResult(
                test_file=str(test_file), status=status,
                exit_code=completed.returncode, duration_seconds=duration,
                stdout=completed.stdout, stderr=completed.stderr,
                failed_test_names=self._failed_test_names(completed.stdout),
            )
        except OSError as error:
            result = ExecutionResult(
                test_file=str(test_file), status="error", exit_code=None,
                duration_seconds=time.monotonic() - started, stderr=str(error),
            )
        return self._persist_result(result, artifact_dir)

    def _resolve_test_file(self, filename: str) -> Path:
        if not filename or Path(filename).name != filename or not filename.endswith(".py"):
            raise ValueError("Generated test filename must be a Python basename")
        return (self.generated_tests_dir / filename).resolve()

    @staticmethod
    def _failed_test_names(stdout: str) -> list[str]:
        names = re.findall(
            r"^(?:FAILED|ERROR)\s+\S+::([^\s]+)", stdout, flags=re.MULTILINE
        )
        return list(dict.fromkeys(names))

    @staticmethod
    def _status(exit_code: int, stdout: str) -> Literal["passed", "failed", "error"]:
        if exit_code == pytest.ExitCode.OK:
            return "passed"
        # Pytest uses exit code 1 for both assertion failures and fixture/setup
        # errors. Keep that distinction for downstream RCA.
        if exit_code == pytest.ExitCode.TESTS_FAILED and not re.search(
            r"^(?:ERROR|ERRORS)\b", stdout, flags=re.MULTILINE
        ):
            return "failed"
        return "error"

    def _persist_result(self, result: ExecutionResult, artifact_dir: Path) -> ExecutionResult:
        (artifact_dir / "stdout.txt").write_text(result.stdout, encoding="utf-8")
        (artifact_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")
        result.artifacts = sorted(
            str(path) for path in artifact_dir.iterdir() if path.is_file()
        )
        result_path = artifact_dir / "execution_result.json"
        result.artifacts.append(str(result_path))
        result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result
