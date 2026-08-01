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
import shlex
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from app.config import get_settings
from app.services.automation_runner.base import RunnerResult, await_process
from app.services.automation_runner.local_playwright import LocalPlaywrightRunner

settings = get_settings()


def docker_available() -> tuple[bool, str]:
    """Real check: CLI present AND the daemon reachable through the socket."""
    if shutil.which("docker") is None:
        return False, (
            "docker CLI not found in the worker image — rebuild the backend image "
            "(the Dockerfile installs docker-ce-cli) or set AUTOMATION_RUNNER_MODE=local."
        )
    try:
        proc = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"docker daemon not reachable: {exc}"
    if proc.returncode != 0:
        return False, (
            "docker daemon not reachable — is /var/run/docker.sock mounted into the "
            f"worker container? ({proc.stderr.strip() or 'no error output'})"
        )
    return True, f"docker server {proc.stdout.strip()}"


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

        container_name = f"stlc-pw-{uuid.uuid4().hex[:12]}"
        cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            # Compose runs the worker as root (browsers were provisioned under
            # /root/.cache at build time); spawned containers must match or
            # Chromium won't resolve.
            "--user", "root",
            "-v", f"{settings.automation_docker_volume}:{settings.automation_docker_storage_mount}",
            "-w", workspace_dir.resolve().as_posix(),
            "-e", f"AUTOMATION_ENV={environment or ''}",
            "-e", "CI=1",
        ]
        if settings.automation_docker_network:
            cmd += ["--network", settings.automation_docker_network]
        cmd += [
            settings.automation_docker_image,
            "npx", "--yes", "playwright", "test",
            script_file_name,
            "--reporter=json",
        ]

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
                    # Killing the `docker run` client alone would leave the
                    # container executing, so the container goes first.
                    await self._kill_container(container_name)
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

    @staticmethod
    async def _kill_container(container_name: str) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "kill", container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=15)
        except (OSError, asyncio.TimeoutError):
            # --rm cleans the container up once the daemon reaps it; a failed
            # kill here must not mask the timeout result we're about to return.
            pass
