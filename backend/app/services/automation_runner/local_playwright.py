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
import base64
import json
import os
import re
import shlex
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
        cancellation: asyncio.Event | None = None,
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
        env, withheld_env = build_runner_env(
            source=os.environ,
            overrides={"AUTOMATION_ENV": environment or "", "CI": "1"},
            runner_name=self.name,
        )

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
                outcome = await await_process(
                    proc, timeout_seconds=timeout_seconds, cancellation=cancellation
                )
                if outcome != "exited":
                    proc.kill()
                    await proc.wait()
                    drain_task.cancel()
                    duration = time.monotonic() - start
                    cancelled = outcome == "cancelled"
                    return RunnerResult(
                        run_status="cancelled" if cancelled else "failed",
                        results=[],
                        duration_seconds=duration,
                        log_path=str(log_path),
                        error_message=(
                            "The run was cancelled while this test was executing; "
                            "the browser process was terminated."
                            if cancelled
                            else f"playwright run timed out after {timeout_seconds}s"
                        ),
                        metadata={
                            "runner": self.name,
                            "command": " ".join(shlex.quote(a) for a in cmd),
                            "cancelled": cancelled,
                        },
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

        results, parse_failure = self._parse_results(
            json_stdout, workspace_dir, script_file_name, exit_code
        )
        # Playwright exit codes: 0=ok, 1=test failed, 2=interrupted/timeout, others=runner failure
        if exit_code in (0, 1):
            run_status = "completed"  # tests ran; some may have failed
            error_message = None
        else:
            run_status = "failed"
            error_message = f"playwright exited with code {exit_code}"

        # No parsed result outranks a clean exit code. Reporting this as a run
        # that merely "completed" would let a harness defect — a broken config,
        # a spec that matched nothing, a reporter that never wrote — reach the
        # caller as a scoreable outcome (AUT-006).
        if parse_failure:
            run_status = "failed"
            error_message = (
                f"{parse_failure} (playwright exit code {exit_code}; see run.log)"
            )

        return RunnerResult(
            run_status=run_status,
            results=results,
            duration_seconds=duration,
            log_path=str(log_path),
            error_message=error_message,
            metadata={
                "runner": self.name,
                "command": " ".join(shlex.quote(a) for a in cmd),
                "exit_code": exit_code,
                "env_withheld_count": len(withheld_env),
            },
        )

    def _parse_results(
        self,
        raw_json: bytes,
        workspace_dir: Path,
        script_file_name: str,
        exit_code: int,
    ) -> tuple[list[PerTestResult], str | None]:
        """Parse the JSON reporter output.

        Returns `(rows, parse_failure_reason)`. An empty row list is never
        substituted with a synthesized outcome: a zero exit code proves the
        process ended cleanly, not that a test ran or an assertion held, so the
        caller reports an automation failure instead (AUT-006).
        """
        if not raw_json:
            return [], (
                "The Playwright JSON reporter produced no output, so no test "
                "result could be read. The run cannot be scored."
            )
        try:
            report = json.loads(raw_json.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return [], (
                "The Playwright JSON reporter output could not be parsed, so no "
                "test result could be read. The run cannot be scored."
            )

        rows: list[PerTestResult] = []
        for suite in report.get("suites", []):
            self._collect_specs(suite, workspace_dir, rows)
        if rows:
            return rows, None
        return [], (
            "The Playwright JSON reporter reported no tests. Nothing executed, "
            "so there is no result to score."
        )

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
                    console_logs, network_logs = self._lift_json_evidence(
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
                        console_logs=console_logs,
                        network_logs=network_logs,
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

    def _lift_json_evidence(
        self,
        attachments: list[dict],
        workspace_dir: Path,
    ) -> tuple[list[dict] | None, list[dict] | None]:
        """Read the console-logs/network-logs JSON attachments the compiled
        spec always emits via testInfo.attach() (see playwright_renderer.py)
        and parse them inline — small, structured, and immediately useful
        for failure_classification, unlike trace.zip's opaque binary format.

        Playwright's JSON reporter embeds SMALL attachments inline as
        base64 in a `body` field rather than writing them to disk — only
        larger ones get a `path` (confirmed by actually running a compiled
        script: console/network attachments came back as `body`, not
        `path`). Both are handled here.
        """
        console_logs = network_logs = None
        for att in attachments:
            name = (att.get("name") or "").lower()
            if "json" not in (att.get("contentType") or "").lower():
                continue
            if "console-logs" not in name and "network-logs" not in name:
                continue
            parsed = self._read_json_attachment(att, workspace_dir)
            if parsed is None:
                continue
            if "console-logs" in name and console_logs is None:
                console_logs = parsed
            elif "network-logs" in name and network_logs is None:
                network_logs = parsed
        return console_logs, network_logs

    @staticmethod
    def _read_json_attachment(att: dict, workspace_dir: Path) -> list[dict] | None:
        body = att.get("body")
        if body:
            try:
                raw = base64.b64decode(body)
                data = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                return None
            return data if isinstance(data, list) else None
        path = att.get("path")
        if not path:
            return None
        abs_path = (workspace_dir / path).resolve()
        try:
            abs_path.relative_to(workspace_dir.resolve())
        except ValueError:
            return None
        try:
            data = json.loads(abs_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, list) else None

