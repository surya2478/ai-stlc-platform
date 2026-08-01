"""Worker-side client for the runner executor (AUT-002).

This is what lets the worker stop mounting the Docker socket. It implements the
same `AutomationRunner` interface as the in-process runners, so the dispatcher
and the orchestrator are unchanged — the difference is that the container is
created by a separate, credential-free service that owns the daemon connection.

The worker can ask for a test bundle to be run. It cannot ask for an image, a
mount, a capability or a flag: those are decided by the executor from its own
configuration. That asymmetry is the entire point, so nothing here should ever
grow a parameter that widens it.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

import httpx

from app.config import get_settings
from app.services.automation_runner.base import (
    AutomationRunner,
    PerTestResult,
    RunnerResult,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class RemoteExecutorRunner(AutomationRunner):
    name = "remote_executor"

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
        base_url = (settings.automation_executor_url or "").rstrip("/")
        if not base_url:
            return RunnerResult(
                run_status="failed", results=[], duration_seconds=0.0, log_path=None,
                error_message=(
                    "Runner mode is 'executor' but AUTOMATION_EXECUTOR_URL is not "
                    "configured, so there is nothing to dispatch to."
                ),
                metadata={"runner": self.name},
            )

        job_id = f"job-{uuid.uuid4().hex[:12]}"
        payload = {
            "job_id": job_id,
            # The executor validates this against its own storage root; both
            # containers mount the same volume at the same path, so the
            # workspace resolves identically on either side.
            "workspace_path": str(workspace_dir.resolve()),
            "script_file_name": script_file_name,
            "environment": environment,
            "timeout_seconds": timeout_seconds,
        }
        headers = {"X-Executor-Token": settings.automation_executor_token}

        # The client budget exceeds the job's own timeout so the executor gets
        # the chance to return its structured timeout result rather than the
        # worker giving up first and losing the reason.
        client_timeout = timeout_seconds + 60

        async with httpx.AsyncClient(timeout=client_timeout) as client:
            request = asyncio.create_task(
                client.post(f"{base_url}/jobs", json=payload, headers=headers)
            )
            watcher = None
            if cancellation is not None:
                watcher = asyncio.create_task(
                    self._forward_cancellation(
                        client, base_url, job_id, headers, cancellation
                    )
                )
            try:
                response = await request
            except httpx.HTTPError as exc:
                return RunnerResult(
                    run_status="failed", results=[], duration_seconds=0.0, log_path=None,
                    error_message=f"The runner executor could not be reached: {exc}",
                    metadata={"runner": self.name, "job_id": job_id},
                )
            finally:
                if watcher is not None:
                    watcher.cancel()

        if response.status_code != 200:
            return RunnerResult(
                run_status="failed", results=[], duration_seconds=0.0, log_path=None,
                error_message=(
                    f"The runner executor refused this job ({response.status_code}): "
                    f"{response.text[:500]}"
                ),
                metadata={"runner": self.name, "job_id": job_id},
            )

        return self._deserialize(response.json(), job_id)

    async def _forward_cancellation(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        job_id: str,
        headers: dict,
        cancellation: asyncio.Event,
    ) -> None:
        """Relay a local cancel to the executor.

        Without this, Wave 2's cancellation would stop at the worker boundary:
        the worker would abandon the request while the container kept running.
        """
        await cancellation.wait()
        try:
            await client.post(
                f"{base_url}/jobs/{job_id}/cancel", headers=headers, timeout=30
            )
        except httpx.HTTPError:
            logger.warning("Could not forward cancellation for job %s", job_id)

    @staticmethod
    def _deserialize(body: dict, job_id: str) -> RunnerResult:
        rows = [PerTestResult(**row) for row in (body.get("results") or [])]
        metadata = dict(body.get("metadata") or {})
        metadata.setdefault("runner", "remote_executor")
        metadata["job_id"] = job_id
        # Preserve what actually ran the test; the worker only brokered it.
        metadata["executed_by"] = "executor"
        return RunnerResult(
            run_status=body.get("run_status") or "failed",
            results=rows,
            duration_seconds=float(body.get("duration_seconds") or 0.0),
            log_path=body.get("log_path"),
            error_message=body.get("error_message"),
            metadata=metadata,
        )
