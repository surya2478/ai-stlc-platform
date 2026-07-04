"""Playwright TypeScript runner — runs a single spec via `npx playwright test`.

Requires Node.js + @playwright/test on the host. If either is missing, returns
a clean run_status="failed" with a remediation hint rather than crashing.

We always force `--reporter=json` and parse the resulting structure for
per-test outcomes. Trace.zip / screenshot / video files end up under
`test-results/` inside the workspace; we lift the relevant ones into the
PerTestResult so the API can serve them.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import time
from pathlib import Path

from app.services.automation_runner.base import AutomationRunner, PerTestResult, RunnerResult
from app.services.automation_runner.preflight import is_available


# Strip ANSI colour / style escape sequences from Playwright's error messages
# so they display cleanly in the UI instead of as "[31m...[39m" garbage.
_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _strip_ansi(value):
    if not isinstance(value, str):
        return value
    return _ANSI_ESCAPE_RE.sub("", value).strip()


PLAYWRIGHT_STATUS_TO_DB = {
    "passed": "pass",
    "failed": "fail",
    "timedout": "fail",
    "skipped": "skip",
    "interrupted": "error",
    "flaky": "fail",
}


class LocalPlaywrightRunner(AutomationRunner):
    name = "local_playwright"

    async def run(
        self,
        *,
        workspace_dir: Path,
        script_file_name: str,
        execution_command: str | None,
        environment: str | None,
        timeout_seconds: int = 600,
    ) -> RunnerResult:
        available, detail = is_available("playwright")
        if not available:
            return RunnerResult(
                run_status="failed",
                results=[],
                duration_seconds=0.0,
                log_path=None,
                error_message=detail,
                metadata={"runner": self.name},
            )

        log_path = workspace_dir / "run.log"
        # Force json reporter — overrides anything LLM put in the config.
        cmd = [
            "npx", "--yes", "playwright", "test",
            script_file_name,
            "--reporter=json",
        ]
        env = {**os.environ, "AUTOMATION_ENV": environment or "", "CI": "1"}

        start = time.monotonic()
        json_stdout = bytearray()
        try:
            with log_path.open("wb") as log_fh:
                # Playwright writes JSON to stdout, human logs to stderr (with our
                # config). We pipe stdout to a buffer for parsing and stderr to
                # the log file.
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(workspace_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=log_fh,
                    env=env,
                )

                async def drain_stdout() -> None:
                    assert proc.stdout is not None
                    while True:
                        chunk = await proc.stdout.read(64 * 1024)
                        if not chunk:
                            break
                        json_stdout.extend(chunk)

                drain_task = asyncio.create_task(drain_stdout())
                try:
                    await asyncio.wait_for(proc.wait(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    drain_task.cancel()
                    duration = time.monotonic() - start
                    return RunnerResult(
                        run_status="failed",
                        results=[],
                        duration_seconds=duration,
                        log_path=str(log_path),
                        error_message=f"playwright run timed out after {timeout_seconds}s",
                        metadata={"runner": self.name, "command": " ".join(shlex.quote(a) for a in cmd)},
                    )
                await drain_task
        except FileNotFoundError as exc:
            return RunnerResult(
                run_status="failed",
                results=[],
                duration_seconds=time.monotonic() - start,
                log_path=None,
                error_message=f"Could not start playwright: {exc}",
                metadata={"runner": self.name},
            )

        duration = time.monotonic() - start
        exit_code = proc.returncode if proc.returncode is not None else -1

        # Persist the raw JSON alongside the log so it's downloadable.
        results_json_path = workspace_dir / "results.json"
        if json_stdout:
            results_json_path.write_bytes(bytes(json_stdout))

        results = self._parse_results(json_stdout, workspace_dir, script_file_name, exit_code)
        # Playwright exit codes: 0=ok, 1=test failed, 2=interrupted/timeout, others=runner failure
        if exit_code == 0:
            run_status = "completed"
        elif exit_code == 1:
            run_status = "completed"  # tests ran, some failed
        else:
            run_status = "failed"
        return RunnerResult(
            run_status=run_status,
            results=results,
            duration_seconds=duration,
            log_path=str(log_path),
            error_message=None if exit_code in (0, 1) else f"playwright exited with code {exit_code}",
            metadata={
                "runner": self.name,
                "command": " ".join(shlex.quote(a) for a in cmd),
                "exit_code": exit_code,
            },
        )

    def _parse_results(
        self,
        raw_json: bytes,
        workspace_dir: Path,
        script_file_name: str,
        exit_code: int,
    ) -> list[PerTestResult]:
        if not raw_json:
            return [self._fallback_row(script_file_name, exit_code)]
        try:
            report = json.loads(raw_json.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return [self._fallback_row(script_file_name, exit_code)]

        rows: list[PerTestResult] = []
        for suite in report.get("suites", []):
            self._collect_specs(suite, workspace_dir, rows)
        if rows:
            return rows
        return [self._fallback_row(script_file_name, exit_code)]

    def _collect_specs(self, suite: dict, workspace_dir: Path, sink: list[PerTestResult]) -> None:
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                for result in test.get("results", []):
                    status = PLAYWRIGHT_STATUS_TO_DB.get((result.get("status") or "").lower(), "error")
                    duration_ms = result.get("duration")
                    if isinstance(duration_ms, (int, float)):
                        duration_ms = int(duration_ms)
                    error_message = None
                    stack_trace = None
                    error = result.get("error")
                    if isinstance(error, dict):
                        error_message = _strip_ansi(error.get("message"))
                        stack_trace = _strip_ansi(error.get("stack"))
                    elif result.get("errors"):
                        first = (result.get("errors") or [{}])[0]
                        if isinstance(first, dict):
                            error_message = _strip_ansi(first.get("message"))
                            stack_trace = _strip_ansi(first.get("stack"))

                    screenshot_path, video_path, trace_path = self._lift_attachments(
                        result.get("attachments") or [],
                        workspace_dir,
                    )
                    sink.append(PerTestResult(
                        name=spec.get("title") or test.get("title") or "unknown",
                        status=status,
                        duration_ms=duration_ms,
                        error_message=error_message,
                        stack_trace=stack_trace,
                        screenshot_path=screenshot_path,
                        video_path=video_path,
                        trace_path=trace_path,
                        raw={"playwright_status": result.get("status")},
                    ))
        for child in suite.get("suites", []):
            self._collect_specs(child, workspace_dir, sink)

    def _lift_attachments(
        self,
        attachments: list[dict],
        workspace_dir: Path,
    ) -> tuple[str | None, str | None, str | None]:
        screenshot = video = trace = None
        for att in attachments:
            name = (att.get("name") or "").lower()
            path = att.get("path")
            if not path:
                continue
            # Playwright reports paths relative to the workspace.
            abs_path = (workspace_dir / path).resolve()
            try:
                # Keep only paths under the workspace — defence in depth.
                abs_path.relative_to(workspace_dir.resolve())
            except ValueError:
                continue
            if "screenshot" in name and not screenshot:
                screenshot = str(abs_path)
            elif "video" in name and not video:
                video = str(abs_path)
            elif "trace" in name and not trace:
                trace = str(abs_path)
        return screenshot, video, trace

    def _fallback_row(self, script_file_name: str, exit_code: int) -> PerTestResult:
        if exit_code == 0:
            return PerTestResult(name=script_file_name, status="pass")
        return PerTestResult(
            name=script_file_name,
            status="fail",
            error_message=f"playwright exit code {exit_code}; see run.log",
        )
