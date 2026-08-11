"""Progress reporting shared by the studio's long-running jobs.

The studio's three heavy operations each run as a Celery task against an
`agent_runs` row, which is what the UI polls. The services do the work but must
not know they are inside a worker, so they take a callback instead of writing to
the run themselves — which also keeps them directly callable from a test or a
script with no callback at all.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.services import agent_run_service

# (percent, message) -> awaitable
ProgressCallback = Callable[[int, str], Awaitable[None]]


async def report(callback: ProgressCallback | None, percent: int, message: str) -> None:
    """Invoke a progress callback if one was supplied.

    Failures are deliberately not swallowed here: a callback that cannot write
    progress is writing to a run row the UI is polling, and a job that silently
    stops reporting looks identical to one that hung.
    """
    if callback is not None:
        await callback(percent, message)


def db_progress_callback(db: AsyncSession, run: AgentRun) -> ProgressCallback:
    """A callback that writes progress onto an agent run and commits.

    Commits on every update on purpose: the point of the write is that a
    *different* process — the API serving the poll — can see it. Batching these
    into the surrounding transaction would leave the client watching a run that
    reports 5% until the whole job finishes.
    """

    async def _update(percent: int, message: str) -> None:
        await agent_run_service.update_progress(db, run, percent=percent, message=message)
        await db.commit()

    return _update
