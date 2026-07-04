"""Pytest runner — runs a single test file via `python -m pytest --json-report`.

Works inside the existing backend Python env. Requires pytest-json-report
(added to requirements.txt by this change). If json-report is missing the
runner still completes — it falls back to parsing pytest's exit code and
stdout, with a single per-test row representing the whole file.
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import time
from pathlib import Path

from app.services.automation_runner.base import AutomationRunner, PerTestResult, RunnerResult
from app.services.automation_runner.preflight import is_available


PYTEST_OUTCOME_TO_STATUS = {
    "passed": "pass",
    "failed": "fail",
    "skipped": "skip",
    "error": "error",
    "xfailed": "pass",
    "xpassed": "pass",
}


class LocalPytestRunner(AutomationRunner):
    name = "local_pytest"

    async def run(
        self,
        *,
        workspace_dir: Path,
        script_file_name: str,
        execution_command: str | None,
        environment: str | None,
        timeout_seconds: int = 600,
    ) -> RunnerResult:
        available, detail = is_available("pytest")
        if not available:
            return RunnerResult(
                run_status="failed",
                results=[],
                duration_seconds=0.0,
                log_path=None,
                error_message=detail,
                metadata={"runner": self.name},
            )

        report_path = workspace_dir / "pytest-report.json"
        log_path = workspace_dir / "run.log"

        # Decide command. We always force json-report via plugin args so we get
        # structured per-test rows. We don't trust the LLM's suggested command
        # because it often omits the json reporter.
        pytest_args = [
            "python", "-m", "pytest",
            script_file_name,
            "-q",
            "--maxfail=0",
            "--disable-warnings",
            f"--json-report-file={report_path.name}",
            "--json-report",
        ]

        env = {**os.environ, "AUTOMATION_ENV": environment or ""}
        # Force unbuffered output so stdout/stderr land in the log file in order.
        env.setdefault("PYTHONUNBUFFERED", "1")

        start = time.monotonic()
        try:
            with log_path.open("wb") as log_fh:
                proc = await asyncio.create_subprocess_exec(
                    *pytest_args,
                    cwd=str(workspace_dir),
                    stdout=log_fh,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )
                try:
                    await asyncio.wait_for(proc.wait(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    duration = time.monotonic() - start
                    return RunnerResult(
                        run_status="failed",
                        results=[],
                        duration_seconds=duration,
                        log_path=str(log_path),
                        error_message=f"pytest run timed out after {timeout_seconds}s",
                        metadata={"runner": self.name, "command": " ".join(shlex.quote(a) for a in pytest_args)},
                    )
        except FileNotFoundError as exc:
            return RunnerResult(
                run_status="failed",
                results=[],
                duration_seconds=time.monotonic() - start,
                log_path=None,
                error_message=f"Could not start pytest: {exc}",
                metadata={"runner": self.name},
            )

        duration = time.monotonic() - start
        exit_code = proc.returncode if proc.returncode is not None else -1

        results = self._parse_results(report_path, log_path, script_file_name, exit_code)
        # Pytest exit codes: 0=ok, 1=tests failed, 2=interrupted, 3=internal, 4=usage, 5=no tests
        if exit_code == 0:
            run_status = "completed"
        elif exit_code in (1, 2):
            run_status = "completed"  # tests ran, some failed — that's still a completed run
        else:
            run_status = "failed"
        return RunnerResult(
            run_status=run_status,
            results=results,
            duration_seconds=duration,
            log_path=str(log_path),
            error_message=None if exit_code in (0, 1, 2) else f"pytest exited with code {exit_code}",
            metadata={
                "runner": self.name,
                "command": " ".join(shlex.quote(a) for a in pytest_args),
                "exit_code": exit_code,
            },
        )

    def _parse_results(
        self,
        report_path: Path,
        log_path: Path,
        script_file_name: str,
        exit_code: int,
    ) -> list[PerTestResult]:
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                tests = report.get("tests") or []
                if tests:
                    return [self._row_from_pytest_test(t) for t in tests]
            except (OSError, json.JSONDecodeError):
                pass

        # Fallback: synthesize a single row from the exit code.
        if exit_code == 0:
            status = "pass"
            error = None
        elif exit_code == 5:
            status = "skip"
            error = "pytest collected 0 tests"
        else:
            status = "fail"
            error = f"pytest exit code {exit_code}; see {log_path.name}"
        return [PerTestResult(name=script_file_name, status=status, error_message=error)]

    def _row_from_pytest_test(self, t: dict) -> PerTestResult:
        outcome = (t.get("outcome") or "").lower()
        status = PYTEST_OUTCOME_TO_STATUS.get(outcome, "error")
        duration_ms: int | None = None
        for phase in ("call", "setup", "teardown"):
            duration = t.get(phase, {}).get("duration")
            if isinstance(duration, (int, float)):
                duration_ms = (duration_ms or 0) + int(duration * 1000)
        error_message = None
        stack_trace = None
        call = t.get("call") or {}
        crash = call.get("crash") or {}
        if crash:
            error_message = crash.get("message")
            stack_trace = crash.get("traceback") if isinstance(crash.get("traceback"), str) else None
        if not error_message and call.get("longrepr"):
            error_message = str(call.get("longrepr"))[:2000]
        return PerTestResult(
            name=t.get("nodeid") or t.get("name") or "unknown",
            status=status,
            duration_ms=duration_ms,
            error_message=error_message,
            stack_trace=stack_trace,
            raw={"outcome": outcome},
        )
