"""Playwright AI Studio endpoints — application-first bulk automation.

A deliberately separate surface from /automation (which stays per-script):
create a run against a registered application, let the planner explore it
and propose test cases, then advance through two bulk approval gates
(plan → scripts) into batch execution. See studio_service for the stage
machine and ADR-001 notes.
"""
from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DBSession, require_permission, require_project_access
from app.schemas.playwright_studio import (
    ApprovePlanRequest,
    ApprovePlanResponse,
    ApproveScriptsRequest,
    ApproveScriptsResponse,
    StudioCancelResponse,
    StudioRunCreate,
    StudioRunDetailOut,
    StudioRunOut,
    StudioStartResponse,
)
from app.services import studio_service
from app.services.rbac_service import EXECUTE_TESTS, GENERATE_AUTOMATION
from app.services.studio_service import StudioStateError, StudioValidationError

router = APIRouter()


async def _get_run_or_404(db, run_id: int):
    run = await studio_service.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Studio run not found")
    return run


@router.post("/runs", response_model=StudioRunOut, status_code=201)
async def create_studio_run(body: StudioRunCreate, db: DBSession, current_user: CurrentUser):
    await require_permission(GENERATE_AUTOMATION, body.project_id, current_user, db)
    try:
        run = await studio_service.create_run(
            db, project_id=body.project_id, user_id=current_user.id, data=body
        )
    except StudioValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(run)
    return run


@router.get("/runs", response_model=list[StudioRunOut])
async def list_studio_runs(
    db: DBSession,
    current_user: CurrentUser,
    project_id: int = Query(...),
):
    await require_project_access(project_id, current_user, db)
    return await studio_service.list_runs(db, project_id)


@router.get("/runs/{run_id}", response_model=StudioRunDetailOut)
async def get_studio_run(run_id: int, db: DBSession, current_user: CurrentUser):
    run = await _get_run_or_404(db, run_id)
    await require_project_access(run.project_id, current_user, db)
    detail = await studio_service.get_run_detail(db, run)
    await db.commit()  # read-time reconciliation may have advanced the status
    return StudioRunDetailOut(
        **StudioRunOut.model_validate(run).model_dump(),
        plan=run.plan,
        test_case_ids=run.test_case_ids,
        **detail,
    )


@router.post("/runs/{run_id}/start", response_model=StudioStartResponse, status_code=202)
async def start_studio_run(run_id: int, db: DBSession, current_user: CurrentUser):
    """Kick off the planner agent (Step 1 → Step 2): explore the application
    and propose a test plan."""
    run = await _get_run_or_404(db, run_id)
    await require_permission(GENERATE_AUTOMATION, run.project_id, current_user, db)
    try:
        agent_run, task_id = await studio_service.start_exploration(db, run, current_user.id)
    except StudioStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return StudioStartResponse(
        studio_run_id=run.id,
        agent_run_id=agent_run.id,
        task_id=task_id,
        status=run.status,
        message="Exploration started — the planner agent is mapping the application.",
    )


@router.post("/runs/{run_id}/approve-plan", response_model=ApprovePlanResponse)
async def approve_studio_plan(
    run_id: int, body: ApprovePlanRequest, db: DBSession, current_user: CurrentUser
):
    """Bulk gate 1 (Step 2 → Step 3): materialize the selected proposals as
    approved test cases and start script generation waves."""
    run = await _get_run_or_404(db, run_id)
    await require_permission(GENERATE_AUTOMATION, run.project_id, current_user, db)
    try:
        outcome = await studio_service.approve_plan(
            db, run, current_user.id, included_keys=body.included_keys, notes=body.notes
        )
    except StudioStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StudioValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return ApprovePlanResponse(
        studio_run_id=run.id,
        status=run.status,
        test_case_count=len(outcome["test_case_ids"]),
        wave_count=outcome["wave_count"],
        message=(
            f"{len(outcome['test_case_ids'])} test case(s) approved; "
            f"script generation queued in {outcome['wave_count']} wave(s)."
        ),
    )


@router.post("/runs/{run_id}/approve-scripts", response_model=ApproveScriptsResponse)
async def approve_studio_scripts(
    run_id: int, body: ApproveScriptsRequest, db: DBSession, current_user: CurrentUser
):
    """Bulk gate 2 (Step 3 → Step 4): approve every generated script and
    launch batch execution."""
    run = await _get_run_or_404(db, run_id)
    await require_permission(GENERATE_AUTOMATION, run.project_id, current_user, db)
    await require_permission(EXECUTE_TESTS, run.project_id, current_user, db)
    from app.services.automation_execution_service import BatchValidationError

    try:
        outcome = await studio_service.approve_scripts(db, run, current_user.id, notes=body.notes)
    except StudioStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (StudioValidationError, BatchValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return ApproveScriptsResponse(
        studio_run_id=run.id,
        status=run.status,
        approved_script_count=len(outcome["approved_script_ids"]),
        execution_run_ids=outcome["execution_run_ids"],
        message=(
            f"{len(outcome['approved_script_ids'])} script(s) approved and queued across "
            f"{len(outcome['execution_run_ids'])} execution batch(es)."
        ),
    )


@router.post("/runs/{run_id}/cancel", response_model=StudioCancelResponse)
async def cancel_studio_run(run_id: int, db: DBSession, current_user: CurrentUser):
    run = await _get_run_or_404(db, run_id)
    await require_permission(GENERATE_AUTOMATION, run.project_id, current_user, db)
    try:
        await studio_service.cancel_run(db, run, current_user.id)
    except StudioStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return StudioCancelResponse(
        studio_run_id=run.id,
        status=run.status,
        message="Studio run cancelled; in-flight agent and execution tasks were revoked best-effort.",
    )
