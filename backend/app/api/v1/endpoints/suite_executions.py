"""UI-046 Suite Execution Command Center endpoints — /api/v1/lab/suite-executions/*.

Same isolated-namespace and 404-when-disabled pattern as automation_suites.py and
automation_assets.py: a suite execution only exists inside a suite, so it shares
the suite's feature flag.

Contract Section 11 lists a `WS/SSE /stream` route. It is deliberately **not**
implemented — this platform has no socket transport, and the two existing live
screens poll a database state machine for the same reason. `GET /events` with a
sequence cursor is the transport instead, and it is what makes Section 14.8's
"reconnect without losing or duplicating events" actually true rather than
aspirational. See contract Section 2.1.7.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DBSession, require_permission
from app.config import get_settings
from app.models.automation_suite import AutomationSuite
from app.models.execution import ExecutionRun
from app.models.execution_command_center import ExecutionRunItem
from app.schemas.suite_execution import (
    ControlRequest,
    ControlResponse,
    StartRunRequest,
)
from app.services.execution_command_center import controls, orchestrator, views
from app.models.project import Project
from app.services.rbac_service import (
    EXECUTION_CANCEL_RUN,
    EXECUTION_CONTROL_RUN,
    EXECUTION_EMERGENCY_STOP,
    EXECUTION_RUN_AUTOMATION,
    EXECUTION_VIEW_LIVE_RUNS,
    user_has_permission,
)

router = APIRouter()


def _require_enabled() -> None:
    if not get_settings().automation_suite_enabled:
        raise HTTPException(
            status_code=404,
            detail="Automation Workspace is disabled (AUTOMATION_SUITE_ENABLED=false)",
        )


async def _load_run(db, run_id: int) -> ExecutionRun:
    _require_enabled()
    run = await db.get(ExecutionRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Execution run not found")
    if run.suite_id is None:
        # A manual, AI or single-script run has no command-center lifecycle. 404
        # rather than serving a half-empty command center over it.
        raise HTTPException(
            status_code=404,
            detail="This execution run is not a suite run and has no command center.",
        )
    return run


async def _control_flags(db, run: ExecutionRun, current_user) -> tuple[bool, bool]:
    """What this user may actually do, so the UI disables rather than guesses.

    Mirrors `require_permission`'s project-owner bypass. Without it the owner
    would see controls disabled and then find they work — worse than either
    consistently allowing or consistently refusing.
    """
    project = await db.get(Project, run.project_id)
    if project is not None and project.owner_id == current_user.id:
        return True, True
    can_control = await user_has_permission(
        db, current_user, run.project_id, EXECUTION_CONTROL_RUN
    )
    can_cancel = await user_has_permission(
        db, current_user, run.project_id, EXECUTION_CANCEL_RUN
    )
    return can_control, can_cancel


# ─── Launching a run ─────────────────────────────────────────────────────────


@router.post("/suites/{suite_id}/runs")
async def start_suite_run(
    suite_id: int,
    payload: StartRunRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Create, gate and expand a run for a published suite, then dispatch it.

    The gate runs synchronously so the command center opens on a real readiness
    verdict rather than a spinner. A blocked run is still created and returned —
    the operator needs to see the scope and the blocker.
    """
    _require_enabled()
    suite = await db.get(AutomationSuite, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="Automation suite not found")
    await require_permission(EXECUTION_RUN_AUTOMATION, suite.project_id, current_user, db)

    run = await orchestrator.create_suite_run(
        db,
        suite,
        actor_id=current_user.id,
        environment=payload.environment,
        execution_purpose=payload.execution_purpose,
        trigger_source="user",
    )
    await db.commit()
    await db.refresh(run)

    if run.lifecycle_state == "QUEUED":
        # Imported here rather than at module scope: the API process should not
        # need the worker's task module to serve read requests.
        from app.worker.tasks.suite_execution_tasks import run_suite_execution

        run_suite_execution.delay(run.id)

    can_control, can_cancel = await _control_flags(db, run, current_user)
    return await views.build_identity(
        db, run, can_control=can_control, can_cancel=can_cancel
    )


@router.get("/suites/{suite_id}/runs")
async def list_suite_runs(
    suite_id: int,
    db: DBSession,
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
):
    """This suite's runs, newest first — the Executions tab's landing list.

    Deliberately a thin projection rather than the full identity payload: the tab
    needs enough to pick a run, and building the snapshot join for twenty rows to
    render a list would be wasteful.
    """
    _require_enabled()
    suite = await db.get(AutomationSuite, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="Automation suite not found")
    await require_permission(EXECUTION_VIEW_LIVE_RUNS, suite.project_id, current_user, db)
    return await views.list_suite_runs(db, suite_id, limit=limit)


# ─── Reading a run ───────────────────────────────────────────────────────────


@router.get("/runs/{run_id}")
async def get_run(run_id: int, db: DBSession, current_user: CurrentUser):
    """Run identity, state and the immutable contract summary (Section 11)."""
    run = await _load_run(db, run_id)
    await require_permission(EXECUTION_VIEW_LIVE_RUNS, run.project_id, current_user, db)
    can_control, can_cancel = await _control_flags(db, run, current_user)
    return await views.build_identity(
        db, run, can_control=can_control, can_cancel=can_cancel
    )


@router.get("/runs/{run_id}/summary")
async def get_run_summary(run_id: int, db: DBSession, current_user: CurrentUser):
    """Reconciled status counts and suite progress (Section 4)."""
    run = await _load_run(db, run_id)
    await require_permission(EXECUTION_VIEW_LIVE_RUNS, run.project_id, current_user, db)
    return await views.build_summary(db, run)


@router.get("/runs/{run_id}/tree")
async def get_suite_tree(run_id: int, db: DBSession, current_user: CurrentUser):
    """Journey/framework hierarchy with live progress (Section 5.2)."""
    run = await _load_run(db, run_id)
    await require_permission(EXECUTION_VIEW_LIVE_RUNS, run.project_id, current_user, db)
    return await views.suite_tree(db, run)


@router.get("/runs/{run_id}/items")
async def list_run_items(
    run_id: int,
    db: DBSession,
    current_user: CurrentUser,
    cursor: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    result: list[str] | None = Query(None),
    lifecycle_state: list[str] | None = Query(None),
    search: str | None = Query(None, max_length=200),
    journey: str | None = Query(None),
    framework: str | None = Query(None),
    priority: str | None = Query(None),
):
    """Cursor-paginated execution matrix (Section 6, Section 14.13)."""
    run = await _load_run(db, run_id)
    await require_permission(EXECUTION_VIEW_LIVE_RUNS, run.project_id, current_user, db)
    return await views.list_items(
        db,
        run,
        cursor=cursor,
        limit=limit,
        results=result,
        lifecycle_states=lifecycle_state,
        search=search,
        journey=journey,
        framework=framework,
        priority=priority,
    )


@router.get("/runs/{run_id}/items/{item_id}")
async def get_run_item(
    run_id: int, item_id: int, db: DBSession, current_user: CurrentUser
):
    """Selected test details: steps, assertions and evidence metadata (Section 7)."""
    run = await _load_run(db, run_id)
    await require_permission(EXECUTION_VIEW_LIVE_RUNS, run.project_id, current_user, db)
    item = await db.get(ExecutionRunItem, item_id)
    if item is None or item.execution_run_id != run.id:
        raise HTTPException(status_code=404, detail="Execution item not found in this run")
    return await views.build_item_detail(db, item)


@router.get("/runs/{run_id}/events")
async def get_run_events(
    run_id: int,
    db: DBSession,
    current_user: CurrentUser,
    after: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
):
    """Events strictly after `after`, in sequence order.

    This is the live transport. Dense, ordered sequence numbers are what let a
    reconnecting client replay exactly the gap, once each.
    """
    run = await _load_run(db, run_id)
    await require_permission(EXECUTION_VIEW_LIVE_RUNS, run.project_id, current_user, db)
    return await views.build_event_page(db, run, after=after, limit=limit)


# ─── Controlling a run ───────────────────────────────────────────────────────


@router.post("/runs/{run_id}/controls", response_model=ControlResponse)
async def control_run(
    run_id: int,
    payload: ControlRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Pause, resume, stop, cancel or emergency-stop (Section 9, Section 11).

    Cancel and emergency stop carry their own permissions: whoever may pause a run
    they are watching is not automatically permitted to discard in-progress work
    and release shared runners.
    """
    run = await _load_run(db, run_id)

    if payload.action == "EMERGENCY_STOP":
        permission = EXECUTION_EMERGENCY_STOP
    elif payload.action == "CANCEL_NOW":
        permission = EXECUTION_CANCEL_RUN
    else:
        permission = EXECUTION_CONTROL_RUN
    await require_permission(permission, run.project_id, current_user, db)

    command = await controls.request_control(
        db,
        run,
        action=payload.action,
        actor_id=current_user.id,
        reason=payload.reason,
        expected_run_version=payload.expectedRunVersion,
    )
    await db.commit()
    await db.refresh(run)

    if controls.should_redispatch(payload.action):
        from app.worker.tasks.suite_execution_tasks import run_suite_execution

        run_suite_execution.delay(run.id)

    return ControlResponse(
        commandId=command.command_key,
        accepted=True,
        currentState=run.lifecycle_state or "",
        runVersion=run.run_version or 0,
        message=controls.ACKNOWLEDGEMENT[payload.action],
    )
