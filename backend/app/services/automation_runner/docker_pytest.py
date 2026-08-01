"""Pytest runner that executes each test module in an ephemeral container.

Until this existed, `pytest` had no containerized runner at all. An isolated
runner mode therefore had two bad options: silently fall back to the worker's
own subprocess — running untrusted code inside the worker precisely when the
operator had asked for it to be contained — or block the framework outright.
Blocking was the honest choice, and this is what makes it unnecessary.

Inherits ALL result handling from LocalPytestRunner (json-report parsing, the
synthesized-row fallback, outcome mapping); only process launch and teardown
differ. Sandbox flags, workspace ownership and container teardown come from
`docker_common`, so pytest and Playwright are confined identically rather than
each carrying its own copy of the controls.

One difference from the Playwright runner is worth knowing: pytest's structured
output goes to a file in the workspace, not to stdout, so stdout and stderr are
both captured to run.log and the report is read from disk afterwards.
"""
from __future__ import annotations

import asyncio
import os
import shlex
import time
import uuid
from pathlib import Path

from app.config import get_settings
from app.services.automation_runner.base import RunnerResult, await_process
from app.services.automation_runner.docker_common import (
    build_run_command,
    docker_available,
    kill_container,
    prepare_workspace_ownership,
)
from app.services.automation_runner.local_pytest import LocalPytestRunner

settings = get_settings()


class DockerPytestRunner(LocalPytestRunner):
    name = "docker_pytest"

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
        available, detail = docker_available()
        if not available:
            return RunnerResult(
                run_status="failed", results=[], duration_seconds=0.0,
                log_path=None, error_message=detail, metadata={"runner": self.name},
            )

        mount_root = Path(settings.automation_docker_storage_mount)
        try:
            workspace_dir.resolve().relative_to(mount_root)
        except ValueError:
            return RunnerResult(
                run_status="failed", results=[], duration_seconds=0.0, log_path=None,
                error_message=(
                    f"Workspace {workspace_dir} is not under the shared storage mount "
                    f"{mount_root} — the spawned container could not see it. Container "
                    "mode requires the compose deployment (file_storage_path on the "
                    "shared volume)."
                ),
                metadata={"runner": self.name},
            )

        ownership_error = prepare_workspace_ownership(workspace_dir)
        if ownership_error:
            return RunnerResult(
                run_status="failed", results=[], duration_seconds=0.0, log_path=None,
                error_message=ownership_error, metadata={"runner": self.name},
            )

        report_path = workspace_dir / "pytest-report.json"
        log_path = workspace_dir / "run.log"
        container_name = f"stlc-pt-{uuid.uuid4().hex[:12]}"

        # The same forced json-report arguments as the local runner: the LLM's
        # suggested command is ignored because it routinely omits the reporter,
        # and without structured rows there is no result to score.
        cmd = build_run_command(
            container_name=container_name,
            workspace_dir=workspace_dir,
            environment=environment,
            image_command=[
                "python", "-m", "pytest",
                script_file_name,
                "-q",
                "--maxfail=0",
                "--disable-warnings",
                f"--json-report-file={report_path.name}",
                "--json-report",
            ],
            # With a read-only root filesystem pytest cannot write bytecode
            # beside the image's own modules, and HOME is not writable either.
            extra_env={"PYTHONDONTWRITEBYTECODE": "1", "HOME": "/tmp"},
        )

        start = time.monotonic()
        try:
            with log_path.open("wb") as log_fh:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=log_fh,
                    stderr=asyncio.subprocess.STDOUT,
                )
                outcome = await await_process(
                    proc, timeout_seconds=timeout_seconds, cancellation=cancellation
                )
                if outcome != "exited":
                    # Killing the `docker run` client alone would leave the
                    # container executing.
                    await kill_container(container_name)
                    proc.kill()
                    await proc.wait()
                    cancelled = outcome == "cancelled"
                    return RunnerResult(
                        run_status="cancelled" if cancelled else "failed",
                        results=[],
                        duration_seconds=time.monotonic() - start,
                        log_path=str(log_path),
                        error_message=(
                            "The run was cancelled while this test was executing; "
                            "the runner container was terminated."
                            if cancelled
                            else f"dockerized pytest run timed out after {timeout_seconds}s"
                        ),
                        metadata={
                            "runner": self.name, "container": container_name,
                            "command": " ".join(shlex.quote(a) for a in cmd),
                            "cancelled": cancelled,
                        },
                    )
        except FileNotFoundError as exc:
            return RunnerResult(
                run_status="failed", results=[], duration_seconds=0.0, log_path=None,
                error_message=f"Could not start docker: {exc}",
                metadata={"runner": self.name},
            )

        duration = time.monotonic() - start
        exit_code = proc.returncode if proc.returncode is not None else -1

        results = self._parse_results(report_path, log_path, script_file_name, exit_code)
        # Pytest exit codes: 0=ok, 1=tests failed, 2=interrupted, 3=internal,
        # 4=usage, 5=no tests. Docker itself uses 125-127 for daemon/image
        # errors, which land in the else branch as a runner failure.
        if exit_code in (0, 1, 2):
            run_status = "completed"
            error_message = None
        else:
            run_status = "failed"
            error_message = f"docker/pytest exited with code {exit_code}"

        return RunnerResult(
            run_status=run_status,
            results=results,
            duration_seconds=duration,
            log_path=str(log_path),
            error_message=error_message,
            metadata={
                "runner": self.name,
                "container": container_name,
                "image": settings.automation_docker_image,
                "command": " ".join(shlex.quote(a) for a in cmd),
                "exit_code": exit_code,
            },
        )
