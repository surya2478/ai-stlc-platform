"""Celery task driving one suite execution run (UI-046).

The API creates the run, gates it and expands its items synchronously so the
command center can be opened immediately with real scope and a real readiness
verdict. This task then dispatches items one at a time.

**Pause and stop are read from the database, not from a signal.** The loop
re-reads `execution_runs.pending_command` in a fresh transaction. That is the
same pattern `DiscoverySession.pending_command` and the Grounded PoC
reconciliation loop already use, and it is why controls need no pub/sub: a
control request is a committed row, so it survives a worker restart and cannot
be lost in transit.

Pause is still a boundary control — it stops the *next* dispatch, by design:
interrupting a test mid-flight would leave the application under test in an
unknown state, which is exactly what an operator pausing to inspect does not
want. Cancel and Emergency Stop are not boundary controls. They are read on a
timer *during* the item by `_execute_with_controls`, which terminates the
running process. Previously they were also boundary-only, so an operator
watching a run misbehave had to wait out the item before anything stopped.

**The database session is not held across execution.** Dispatch runs in three
phases — `prepare_item` (session), `execute_plan` (no session),
`finalize_item` (session). The middle phase can occupy the full item timeout,
and holding a connection open across it pinned one pool slot per in-flight item,
idle in transaction, which capped concurrency below anything `parallel_limit`
could express.

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
from app.models.execution_command_center import ExecutionRunItem
from app.services.execution_command_center import events, orchestrator
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# How often the in-item watcher re-reads the control channel and writes a
# heartbeat. Short enough that Cancel feels immediate, long enough that a
# 10-minute test costs a handful of tiny queries rather than a busy loop.
CONTROL_POLL_SECONDS = 3.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _execute_suite_run(execution_run_id: int, worker_id: str | None = None) -> dict:
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

        # A resumed run may carry items left mid-flight by a previous attempt
        # whose worker died. They cannot be adopted — their process is gone —
        # so they are closed out before new work is dispatched.
        await orchestrator.reconcile_stranded_items(
            db,
            run,
            reason=(
                "The worker executing this test stopped before reporting a result. "
                "No verdict was reached; re-run the test to get one."
            ),
        )

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

            item_id = item.id
            item_order = item.order_index
            try:
                plan = await orchestrator.prepare_item(db, run, item, worker_id=worker_id)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                await _fault_item(execution_run_id, item_id, item_order, exc)
                dispatched += 1
                continue

        # ── Outside the session ───────────────────────────────────────────────
        # The runner can occupy up to ITEM_TIMEOUT_SECONDS. Holding a connection
        # open across it pinned one pool slot per in-flight item, idle in
        # transaction, which is the real ceiling on suite concurrency. Nothing
        # below touches the database until the item is done.
        runner_result = None
        cancelled = False
        try:
            if plan.runnable:
                runner_result, cancelled = await _execute_with_controls(
                    execution_run_id, item_id, plan
                )
            else:
                runner_result = await orchestrator.execute_plan(plan)
        except Exception as exc:
            await _fault_item(execution_run_id, item_id, item_order, exc)
            dispatched += 1
            continue

        async with AsyncSessionLocal() as db:
            run = await db.get(ExecutionRun, execution_run_id)
            item = await db.get(ExecutionRunItem, item_id)
            if run is None or item is None:
                break
            try:
                await orchestrator.finalize_item(db, run, item, plan, runner_result)
                run.run_version = (run.run_version or 0) + 1
                await db.commit()
            except Exception as exc:
                # One item blowing up must not abandon the rest of the suite. The
                # orchestrator classifies every expected failure itself, so
                # reaching here means an unexpected fault — recorded as an
                # automation failure on this item, with the loop continuing.
                await db.rollback()
                await _fault_item(execution_run_id, item_id, item_order, exc)
                dispatched += 1
                continue

        dispatched += 1

        if cancelled:
            # The control that terminated the process still has to be applied to
            # the run itself. Looping back would re-read it at the boundary, but
            # closing out here keeps the cancel atomic with the item it stopped.
            async with AsyncSessionLocal() as db:
                run = await db.get(ExecutionRun, execution_run_id)
                if run is not None:
                    run.lifecycle_state = "CANCELLED"
                    run.pending_command = None
                    await events.emit(
                        db,
                        run.id,
                        event_type="control_applied",
                        message=(
                            "Cancelled. The running test was terminated; partial "
                            "evidence already captured is retained."
                        ),
                        payload={"action": "CANCEL_NOW"},
                    )
                    await orchestrator.finalize_run(db, run, stopped=True)
                    await db.commit()
            stopped = True
            break

    return {
        "run_id": execution_run_id,
        "status": "stopped" if stopped else "completed",
        "dispatched": dispatched,
    }


async def _execute_with_controls(
    execution_run_id: int, item_id: int, plan
) -> tuple[object, bool]:
    """Run one item while watching for a stop request.

    Before this, `pending_command` was only read at dispatch boundaries, so
    Cancel and Emergency Stop could not reach a test that had already started —
    an operator watching a run do something harmful had to wait out the item
    (AUT-013). The watcher polls the same committed-row control channel the
    boundary check uses, on its own short-lived sessions, and sets the event the
    runner races against.

    It doubles as the heartbeat writer: the poll cadence is exactly the liveness
    signal `reconcile_stranded_items` needs, so one loop serves both.
    """
    cancellation = asyncio.Event()
    stop = asyncio.Event()

    async def watch() -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=CONTROL_POLL_SECONDS)
                return
            except asyncio.TimeoutError:
                pass
            try:
                async with AsyncSessionLocal() as db:
                    await orchestrator.touch_heartbeat(db, item_id)
                    run = await db.get(ExecutionRun, execution_run_id)
                    command = run.pending_command if run else None
                    await db.commit()
                if command in ("CANCEL_NOW", "EMERGENCY_STOP"):
                    logger.info(
                        "Control %s observed while item %s was running; terminating",
                        command, item_id,
                    )
                    cancellation.set()
                    return
            except Exception:
                # A watcher fault must never take down the run it is watching.
                # Losing a heartbeat costs a delayed recovery, not a wrong result.
                logger.exception("Control watcher failed for item %s", item_id)

    watcher = asyncio.create_task(watch())
    try:
        runner_result = await orchestrator.execute_plan(plan, cancellation=cancellation)
    finally:
        stop.set()
        watcher.cancel()

    was_cancelled = getattr(runner_result, "run_status", None) == "cancelled"
    return runner_result, was_cancelled


async def _fault_item(
    execution_run_id: int, item_id: int, order_index: int | None, exc: Exception
) -> None:
    """Record an unexpected orchestration fault against one item."""
    logger.exception(
        "Unexpected fault dispatching item %s of run %s", item_id, execution_run_id
    )
    async with AsyncSessionLocal() as recovery:
        recovered = await recovery.get(ExecutionRunItem, item_id)
        if recovered is None:
            return
        recovered.lifecycle_state = "COMPLETED"
        recovered.result = "AUTOMATION_FAILURE"
        recovered.attention_reason = (
            f"The orchestrator faulted while dispatching this test: {exc}"
        )
        recovered.completed_at = _now()
        recovered.heartbeat_at = None
        # The old recovery path left the run's rollup counters untouched, so the
        # summary tiles disagreed with the item list for the rest of the run.
        await orchestrator.recount_after_fault(recovery, execution_run_id, item_id)
        await events.emit(
            recovery,
            execution_run_id,
            event_type="runner_warning",
            message=f"Orchestrator fault on item {order_index}: {exc}",
            item_id=recovered.id,
        )
        await recovery.commit()


async def _mark_run_faulted(execution_run_id: int, message: str) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(ExecutionRun, execution_run_id)
        if run is None:
            return
        # Close out anything left mid-flight first. Marking the run terminal
        # while its items stayed RUNNING is what made the command center spin
        # forever against a finished run.
        await orchestrator.reconcile_stranded_items(
            db,
            run,
            reason=(
                "The orchestrator crashed while this test was running, so no "
                "verdict was reached."
            ),
        )
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
        return asyncio.run(
            _execute_suite_run(execution_run_id, worker_id=getattr(self.request, "id", None))
        )
    except Exception as exc:
        logger.exception("Suite execution crashed for run_id=%s", execution_run_id)
        try:
            asyncio.run(_mark_run_faulted(execution_run_id, str(exc)))
        except Exception:
            logger.exception("Failed to mark run %s as faulted after crash", execution_run_id)
        raise
