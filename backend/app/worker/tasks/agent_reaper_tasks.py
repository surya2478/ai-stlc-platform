"""Fail agent runs whose worker died holding them.

An agent run is marked `running` by the worker that picked it up, and reaches a
terminal state only because that same worker writes one. Kill the worker — a
restart, an OOM, a crashed container — and the row stays `running` forever.
Nothing ever reconciles it, so `studio_service._reconcile_status` (which waits
for every agent run to be terminal) never advances either, and the UI spins on
a task that stopped existing. Observed live 2026-08-03: Playwright AI Studio
run 6 showed "Generating scripts… 30%" for 26 minutes against agent run 284,
whose worker had been restarted two minutes into it.

The rule is deliberately derived from the timeout each agent already declares,
not from a new invented constant:

    a run older than its own timeout + REAP_GRACE_SECONDS, still not terminal,
    has no live runner

That holds because `_run_agent_task` enforces `AgentSpec.timeout_seconds`
itself with `asyncio.wait_for` and fails the run when it expires. So a live
runner would have already terminated anything past that ceiling — if the row
is still open well beyond it, the process that owned it is gone.

Age is measured from `created_at`, not `updated_at`: a healthy agent can run
for its full budget without writing a single log line (one long LLM call does
exactly that), and reaping on write-silence would kill working runs.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.agent import AgentRun
from app.services import agent_run_service
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# Headroom over the agent's own ceiling before we call it abandoned. Covers
# queue wait, a slow final commit, and clock skew between worker and database.
# Generous on purpose: reaping a run that was about to finish destroys real
# work, while reaping one minute later costs only a minute of a spinner.
REAP_GRACE_SECONDS = 300.0

# Applied to a run whose agent_name is not in AGENT_SPECS — an agent that was
# renamed or removed while its rows survived. Uses the same default the spec
# dataclass does, so an unknown agent is not treated as unlimited.
FALLBACK_TIMEOUT_SECONDS = 120.0

_OPEN_STATUSES = ("pending", "running")


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _attempt_started(run: AgentRun) -> datetime | None:
    """When the CURRENT attempt began.

    There is no started_at column, and `created_at` alone is wrong for a run
    that was requeued: `enqueue_agent_run` reuses a failed run's row in place
    (status back to pending, error cleared) rather than inserting a new one,
    so a retry inherits a creation time from hours ago and would be reaped
    within one sweep while it was legitimately running. Observed while adding
    the Studio retry button.

    `max(created_at, updated_at)` is the fix precisely because it is monotonic:
    updated_at only ever moves forward, so this can only ever postpone a
    reaping, never hasten one. That keeps the guarantee this module was
    written for — a silent long-running agent is never killed early — while
    giving a requeued run a fresh clock.
    """
    created = _as_utc(run.created_at)
    updated = _as_utc(run.updated_at)
    if created is None:
        return updated
    if updated is None:
        return created
    return max(created, updated)


def _reap_deadline(run: AgentRun, started: datetime) -> datetime:
    # Imported here rather than at module scope: agent_tasks imports every
    # agent class, and importing it eagerly would make this module's import
    # cost the entire agent graph even when only the constant is needed.
    from app.worker.tasks.agent_tasks import AGENT_SPECS

    spec = AGENT_SPECS.get(run.agent_name)
    timeout = spec.timeout_seconds if spec is not None else FALLBACK_TIMEOUT_SECONDS
    return started + timedelta(seconds=timeout + REAP_GRACE_SECONDS)


async def _reap_abandoned_agent_runs() -> dict:
    now = datetime.now(timezone.utc)
    reaped: list[int] = []

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentRun).where(AgentRun.status.in_(_OPEN_STATUSES))
        )
        candidates = list(result.scalars().all())

        for run in candidates:
            started = _attempt_started(run)
            if started is None:
                continue
            if now < _reap_deadline(run, started):
                continue

            age = int((now - started).total_seconds())
            # Says what happened and what to do, because this message is the
            # only thing the user sees in place of a result.
            await agent_run_service.fail_agent_run(
                db,
                run,
                error_message=(
                    f"Interrupted: no worker has reported on this run for {age} seconds, "
                    f"past the {run.agent_name} ceiling. The worker that was running it "
                    f"most likely restarted or crashed. Nothing was produced — re-run it to retry."
                ),
                output_data=run.output_data or {},
            )
            reaped.append(run.id)

        if reaped:
            await db.commit()

    if reaped:
        logger.warning("agent_reaper: failed %d abandoned agent run(s): %s", len(reaped), reaped)
    return {"checked": len(candidates), "reaped": reaped}


@celery_app.task(name="agent_reaper_tasks.reap_abandoned_agent_runs", max_retries=0)
def reap_abandoned_agent_runs() -> dict:
    return asyncio.run(_reap_abandoned_agent_runs())
