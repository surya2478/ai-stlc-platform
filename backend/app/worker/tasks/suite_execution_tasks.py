"""Celery task driving one suite execution run (UI-046).

The API creates the run, gates it and expands its items synchronously so the
command center can be opened immediately with real scope and a real readiness
verdict. This task then dispatches items one at a time.

**Pause and stop are read from the database, not from a signal.** At every
dispatch boundary the loop re-reads `execution_runs.pending_command` in a fresh
transaction. That is the same pattern `DiscoverySession.pending_command` and the
Grounded PoC reconciliation loop already use, and it is why controls need no
pub/sub: a control request is a committed row, so it survives a worker restart
and cannot be lost in transit.

A pause exits the task rather than sleeping in it. Holding a worker slot open
across an operator's coffee break wastes the fleet; `RESUME` enqueues a fresh
task that continues from the next queued item, which is exactly what contract
Section 9.2 describes.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.database import AsyncSessionLocal
from app.models.execution import ExecutionRun
from app.services.execution_command_center import events, orchestrator
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _execute_suite_run(execution_run_id: int) -> dict:
    dispatched = 0
    stopped = False

    async with AsyncSessionLocal() as db:
        run = await db.get(ExecutionRun, execution_run_id)
        if run is None:
            logger.warning("Suite run %s no longer exists", execution_run_id)
            return {"run_id": execution_run_id, "status": "missing"}
        if run.lifecycle_state not in ("QUEUED", "PAUSED"):
            # Not an error: a second RESUME, or a task retry after the run already
            # reached a terminal state.
            return {"run_id": execution_run_id, "status": f"not_startable:{run.lifecycle_state}"}

        run.lifecycle_state = "RUNNING"
        run.status = "running"
        run.run_version = (run.run_version or 0) + 1
        if run.started_at is None:
            run.started_at = _now()
        await events.emit(
            db,
            run.id,
            event_type="run_started",
            message="Execution started.",
        )
        await db.commit()

    while True:
        async with AsyncSessionLocal() as db:
            run = await db.get(ExecutionRun, execution_run_id)
            if run is None:
                break

            # ── The control boundary ──────────────────────────────────────────
            command = run.pending_command
            if command in ("CANCEL_NOW", "EMERGENCY_STOP"):
                run.lifecycle_state = "CANCELLED"
                run.pending_command = None
                await events.emit(
                    db,
                    run.id,
                    event_type="control_applied",
                    message=(
                        "Cancelled. Queued work was not dispatched; partial evidence "
                        "already captured is retained."
                    ),
                    payload={"action": command},
                )
                await orchestrator.finalize_run(db, run, stopped=True)
                await db.commit()
                stopped = True
                break
            if command == "STOP_GRACEFULLY":
                run.pending_command = None
                await events.emit(
                    db,
                    run.id,
                    event_type="control_applied",
                    message="Stopped gracefully. Available results and evidence finalized.",
                    payload={"action": command},
                )
                await orchestrator.finalize_run(db, run, stopped=True)
                await db.commit()
                stopped = True
                break
            if command == "PAUSE_AFTER_CURRENT":
                run.lifecycle_state = "PAUSED"
                run.status = "pending"
                run.pending_command = None
                run.run_version = (run.run_version or 0) + 1
                await events.emit(
                    db,
                    run.id,
                    event_type="run_paused",
                    message=(
                        "Paused. No further test cases will be dispatched until the run "
                        "is resumed."
                    ),
                )
                await db.commit()
                return {
                    "run_id": execution_run_id,
                    "status": "paused",
                    "dispatched": dispatched,
                }

            item = await orchestrator.next_queued_item(db, run)
            if item is None:
                await orchestrator.finalize_run(db, run)
                await db.commit()
                break

            try:
                await orchestrator.dispatch_item(db, run, item)
            except Exception as exc:
                # One item blowing up must not abandon the rest of the suite. The
                # orchestrator classifies every expected failure itself, so
                # reaching here means an unexpected fault — recorded as an
                # automation failure on this item, with the loop continuing.
                logger.exception(
                    "Unexpected fault dispatching item %s of run %s", item.id, run.id
                )
                await db.rollback()
                async with AsyncSessionLocal() as recovery:
                    recovered = await recovery.get(type(item), item.id)
                    if recovered is not None:
                        recovered.lifecycle_state = "COMPLETED"
                        recovered.result = "AUTOMATION_FAILURE"
                        recovered.attention_reason = (
                            f"The orchestrator faulted while dispatching this test: {exc}"
                        )
                        recovered.completed_at = _now()
                        await events.emit(
                            recovery,
                            execution_run_id,
                            event_type="runner_warning",
                            message=f"Orchestrator fault on item {recovered.order_index}: {exc}",
                            item_id=recovered.id,
                        )
                        await recovery.commit()
                dispatched += 1
                continue

            run.run_version = (run.run_version or 0) + 1
            await db.commit()
            dispatched += 1

    return {
        "run_id": execution_run_id,
        "status": "stopped" if stopped else "completed",
        "dispatched": dispatched,
    }


async def _mark_run_faulted(execution_run_id: int, message: str) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(ExecutionRun, execution_run_id)
        if run is None:
            return
        run.lifecycle_state = "STOPPED"
        run.status = "failed"
        run.outcome = "AUTOMATION_FAILURE"
        run.pending_command = None
        run.completed_at = _now()
        await events.emit(
            db,
            run.id,
            event_type="run_finalized",
            message=f"The orchestrator crashed and the run was stopped: {message}",
            payload={"outcome": "AUTOMATION_FAILURE"},
        )
        await db.commit()


@celery_app.task(
    bind=True, name="suite_execution_tasks.run_suite_execution", max_retries=0
)
def run_suite_execution(self, execution_run_id: int):
    """Entry point invoked by the API after creating and gating the run."""
    try:
        return asyncio.run(_execute_suite_run(execution_run_id))
    except Exception as exc:
        logger.exception("Suite execution crashed for run_id=%s", execution_run_id)
        try:
            asyncio.run(_mark_run_faulted(execution_run_id, str(exc)))
        except Exception:
            logger.exception("Failed to mark run %s as faulted after crash", execution_run_id)
        raise
