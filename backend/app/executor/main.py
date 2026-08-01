"""Runner executor — the only process that talks to the Docker daemon (AUT-002).

The worker used to mount `/var/run/docker.sock` itself. Docker daemon access is
effectively host-level authority: anything that can reach the socket can create
a privileged container, bind-mount `/`, and own the host. The worker is the
large attack surface in this platform — it runs LLM-generated code paths,
handles user input, and holds database, Redis and LLM provider credentials — so
that is precisely the process that should not hold it.

This service inverts that. It owns the socket and exposes one typed operation:
*run this already-materialized workspace as a test*. The caller cannot express
`--privileged`, cannot choose an image, cannot pick a mount, and cannot pass
arbitrary flags — the sandbox is decided here, from server configuration. A
compromised worker gains "run a test bundle in a hardened container", not
"control the host".

It is deliberately tiny and deliberately credential-free: no database, no
Redis, no LLM keys. The only secret it holds is the shared token that proves a
request came from inside the deployment.

If this platform later moves to Kubernetes, this service is what a Job-based
runner replaces; the worker-side interface (`remote_executor.py`) stays the
same.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.automation_runner.base import RunnerResult
from app.services.automation_runner.docker_playwright import (
    DockerPlaywrightRunner,
    docker_available,
)

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title="STLC Runner Executor",
    description="Spawns sandboxed automation runner containers. Not a public API.",
    docs_url=None,
    redoc_url=None,
)

# job_id -> cancellation event, so a caller can stop a run that is already in
# flight rather than waiting out its timeout.
_JOBS: dict[str, asyncio.Event] = {}


class RunJobRequest(BaseModel):
    """Everything the caller may influence. Nothing here reaches docker as a
    flag: the workspace is validated against the storage root and the rest of
    the command is built from server configuration."""

    job_id: str = Field(min_length=1, max_length=100)
    workspace_path: str
    script_file_name: str = Field(min_length=1, max_length=500)
    environment: str | None = None
    timeout_seconds: int = Field(default=600, ge=1, le=7200)


async def require_token(x_executor_token: str = Header(default="")) -> None:
    """Shared-secret gate. The executor is not exposed outside the compose
    network, but an unauthenticated container-spawning endpoint on any network
    is an unacceptable default."""
    expected = settings.automation_executor_token
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=(
                "The executor has no AUTOMATION_EXECUTOR_TOKEN configured and "
                "refuses to accept jobs without one."
            ),
        )
    # Constant-time compare so a wrong token cannot be recovered by timing.
    if not _constant_time_equals(x_executor_token, expected):
        raise HTTPException(status_code=401, detail="Invalid executor token")


def _constant_time_equals(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _validated_workspace(raw: str) -> Path:
    """Confine the caller to workspaces under the shared storage root.

    Without this the one thing the caller *can* choose becomes a way to point
    the runner at any path the executor can see.
    """
    root = Path(os.path.realpath(settings.file_storage_path))
    candidate = Path(os.path.realpath(raw))
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Workspace {raw} is outside the executor's storage root.",
        )
    if not candidate.is_dir():
        raise HTTPException(
            status_code=404, detail=f"Workspace {raw} does not exist on the executor."
        )
    return candidate


@app.get("/health")
async def health() -> dict:
    available, detail = docker_available()
    return {
        "status": "ok" if available else "degraded",
        "docker": detail,
        "active_jobs": len(_JOBS),
    }


@app.post("/jobs", dependencies=[Depends(require_token)])
async def run_job(request: RunJobRequest) -> dict:
    """Run one test bundle and return the normalized runner result."""
    workspace = _validated_workspace(request.workspace_path)

    cancellation = asyncio.Event()
    _JOBS[request.job_id] = cancellation
    try:
        result: RunnerResult = await DockerPlaywrightRunner().run(
            workspace_dir=workspace,
            script_file_name=request.script_file_name,
            execution_command=None,
            environment=request.environment,
            timeout_seconds=request.timeout_seconds,
            cancellation=cancellation,
        )
    except Exception as exc:  # noqa: BLE001 - reported, never leaked as a 500 body
        logger.exception("Executor job %s failed", request.job_id)
        return asdict(
            RunnerResult(
                run_status="failed",
                results=[],
                duration_seconds=0.0,
                log_path=None,
                error_message=f"The executor failed to run this job: {exc}",
                metadata={"runner": "executor", "job_id": request.job_id},
            )
        )
    finally:
        _JOBS.pop(request.job_id, None)

    return asdict(result)


@app.post("/jobs/{job_id}/cancel", dependencies=[Depends(require_token)])
async def cancel_job(job_id: str) -> dict:
    """Ask a running job to stop. Idempotent, and truthful about whether it
    found anything: a caller must be able to tell "stopped it" from "there was
    nothing to stop"."""
    event = _JOBS.get(job_id)
    if event is None:
        return {"job_id": job_id, "cancelled": False, "reason": "No such active job."}
    event.set()
    return {"job_id": job_id, "cancelled": True}
