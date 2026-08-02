"""Playwright runner that executes each script in an ephemeral Docker
container (Playwright AI Studio's "Docker based execution").

Spawned via the docker CLI against the host's Docker socket (mounted into
the worker — see docker-compose.yml). Each run gets a throwaway sibling
container from the worker's own image, sharing the storage volume so the
already-materialized workspace resolves at the SAME path inside the
container — no path mapping, no per-run npm installs, and exact
Node/@playwright/test/Chromium version parity with the local runner.

Inherits ALL result handling from LocalPlaywrightRunner (JSON reporter
parsing, attachment lifting, console/network evidence) — only process
launch/kill differs. On timeout the container is killed by name (killing
just the `docker run` client process would leave the container running).
"""
from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import subprocess
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
from app.services.automation_runner.local_playwright import LocalPlaywrightRunner

settings = get_settings()

__all__ = ["DockerPlaywrightRunner", "docker_available"]


class DockerPlaywrightRunner(LocalPlaywrightRunner):
    name = "docker_playwright"

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
                    f"{mount_root} — the spawned container could not see it. Docker mode "
                    "requires the compose deployment (file_storage_path on the shared volume)."
                ),
                metadata={"runner": self.name},
            )

        ownership_error = prepare_workspace_ownership(workspace_dir)
        if ownership_error:
            return RunnerResult(
                run_status="failed", results=[], duration_seconds=0.0, log_path=None,
                error_message=ownership_error,
                metadata={"runner": self.name},
            )

        container_name = f"stlc-pw-{uuid.uuid4().hex[:12]}"
        cmd = build_run_command(
            container_name=container_name,
            workspace_dir=workspace_dir,
            environment=environment,
            image_command=[
                "npx", "--yes", "playwright", "test",
                script_file_name,
                "--reporter=json",
            ],
        )

        log_path = workspace_dir / "run.log"
        start = time.monotonic()
        json_stdout = bytearray()
        try:
            with log_path.open("wb") as log_fh:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=log_fh,
                )

                async def drain_stdout() -> None:
                    # Tee: stdout is both the JSON report this parses and the
                    # only record of what the run did. Piping it away for
                    # parsing left run.log holding stderr alone, which is empty
                    # on a clean run — so the log evidence attested to zero
                    # bytes precisely when the test passed, and a reader could
                    # not tell "ran cleanly" from "log capture is broken".
                    assert proc.stdout is not None
                    while True:
                        chunk = await proc.stdout.read(64 * 1024)
                        if not chunk:
                            break
                        json_stdout.extend(chunk)
                        log_fh.write(chunk)

                drain_task = asyncio.create_task(drain_stdout())
                outcome = await await_process(
                    proc, timeout_seconds=timeout_seconds, cancellation=cancellation
                )
                if outcome != "exited":
                    # Killing the `docker run` client alone would leave the
                    # container executing, so the container goes first.
                    await kill_container(container_name)
                    proc.kill()
                    await proc.wait()
                    drain_task.cancel()
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
                            else f"dockerized playwright run timed out after {timeout_seconds}s"
                        ),
                        metadata={
                            "runner": self.name, "container": container_name,
                            "command": " ".join(shlex.quote(a) for a in cmd),
                            "cancelled": cancelled,
                        },
                    )
                await drain_task
        except FileNotFoundError as exc:
            return RunnerResult(
                run_status="failed", results=[],
                duration_seconds=time.monotonic() - start, log_path=None,
                error_message=f"Could not start docker: {exc}",
                metadata={"runner": self.name},
            )

        duration = time.monotonic() - start
        exit_code = proc.returncode if proc.returncode is not None else -1

        results_json_path = workspace_dir / "results.json"
        if json_stdout:
            results_json_path.write_bytes(bytes(json_stdout))

        results, parse_failure = self._parse_results(
            json_stdout, workspace_dir, script_file_name, exit_code
        )
        # Same convention as the local runner: 0=ok, 1=tests ran with failures;
        # docker itself uses 125-127 for daemon/image errors, which land in
        # the else branch as a runner failure.
        if exit_code in (0, 1):
            run_status = "completed"
            error_message = None
        else:
            run_status = "failed"
            error_message = f"docker/playwright exited with code {exit_code}"

        # No parsed result is a harness failure regardless of exit code — see
        # the local runner for the reasoning (AUT-006).
        if parse_failure:
            run_status = "failed"
            error_message = (
                f"{parse_failure} (docker/playwright exit code {exit_code}; see run.log)"
            )
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

