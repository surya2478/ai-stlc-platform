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

from app.services.automation_runner.base import (
    AutomationRunner,
    PerTestResult,
    RunnerResult,
    await_process,
)
from app.services.automation_runner.env_policy import build_runner_env
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
        cancellation: asyncio.Event | None = None,
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

        # Force unbuffered output so stdout/stderr land in the log file in order.
        env, withheld_env = build_runner_env(
            source=os.environ,
            overrides={"AUTOMATION_ENV": environment or "", "PYTHONUNBUFFERED": "1"},
            runner_name=self.name,
        )

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
                outcome = await await_process(
                    proc, timeout_seconds=timeout_seconds, cancellation=cancellation
                )
                if outcome != "exited":
                    proc.kill()
                    await proc.wait()
                    duration = time.monotonic() - start
                    cancelled = outcome == "cancelled"
                    return RunnerResult(
                        run_status="cancelled" if cancelled else "failed",
                        results=[],
                        duration_seconds=duration,
                        log_path=str(log_path),
                        error_message=(
                            "The run was cancelled while this test was executing; "
                            "the pytest process was terminated."
                            if cancelled
                            else f"pytest run timed out after {timeout_seconds}s"
                        ),
                        metadata={
                            "runner": self.name,
                            "command": " ".join(shlex.quote(a) for a in pytest_args),
                            "cancelled": cancelled,
                        },
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
                "env_withheld_count": len(withheld_env),
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

        # Fallback: synthesize a single row from the exit code. Unlike
        # Playwright — where the JSON reporter is forced and its absence means
        # the harness misbehaved — pytest's exit code is itself meaningful:
        # 0 means it collected and passed tests, 5 means it collected none.
        # The row is flagged as synthesized so nothing downstream mistakes it
        # for parsed per-test detail.
        if exit_code == 0:
            status = "pass"
            error = None
        elif exit_code == 5:
            # Previously "skip", which read as "this test was intentionally
            # skipped". Nothing ran at all — that is a harness failure, and
            # hiding it behind a skip is the pytest sibling of AUT-006.
            status = "error"
            error = (
                "pytest collected 0 tests from this file, so nothing executed "
                "and there is no result to score."
            )
        else:
            status = "fail"
            error = f"pytest exit code {exit_code}; see {log_path.name}"
        return [
            PerTestResult(
                name=script_file_name,
                status=status,
                error_message=error,
                raw={"synthesized": True, "reason": "pytest-json-report produced no rows"},
            )
        ]

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
