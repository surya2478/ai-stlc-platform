"""Grounded Automation PoC endpoints — /api/v1/poc/grounded-automation/*.

A deliberately separate namespace (isolation control from the review):
every route 404s when GROUNDED_AUTOMATION_ENABLED is off, so with the flag
disabled the PoC is externally indistinguishable from not being deployed.
Existing Automation Studio endpoints are untouched.
"""
from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DBSession, require_permission, require_project_access
from app.config import get_settings
from app.models.grounded_poc import PocStateEvidence
from app.schemas.grounded_poc import (
    PocActionResponse,
    PocConfirmStepRequest,
    PocEvidenceDetailOut,
    PocRunCreate,
    PocRunDetailOut,
    PocRunOut,
    PocStatusOut,
)
from app.services import grounded_poc_service
from app.services.grounded_poc_service import PocStateError, PocValidationError
from app.services.rbac_service import GENERATE_AUTOMATION

router = APIRouter()


def _require_enabled() -> None:
    if not get_settings().grounded_automation_enabled:
        raise HTTPException(
            status_code=404,
            detail="Grounded Automation PoC is disabled (GROUNDED_AUTOMATION_ENABLED=false)",
        )


async def _get_run_or_404(db, run_id: int):
    run = await grounded_poc_service.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Grounding run not found")
    return run


@router.get("/status", response_model=PocStatusOut)
async def poc_status(current_user: CurrentUser):
    """The only route that answers with the flag off — lets the UI show a
    clear 'feature disabled' state instead of raw 404s."""
    enabled = get_settings().grounded_automation_enabled
    return PocStatusOut(
        enabled=enabled,
        message="Grounded Automation PoC is enabled" if enabled
        else "Set GROUNDED_AUTOMATION_ENABLED=true to activate the PoC",
    )


@router.post("/runs", response_model=PocRunOut, status_code=201)
async def create_run(body: PocRunCreate, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    await require_permission(GENERATE_AUTOMATION, body.project_id, current_user, db)
    try:
        run = await grounded_poc_service.create_run(
            db,
            project_id=body.project_id,
            user_id=current_user.id,
            test_case_id=body.test_case_id,
            environment=body.environment,
            capture_mode=body.capture_mode,
        )
    except PocValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(run)
    return run


@router.get("/runs", response_model=list[PocRunOut])
async def list_runs(db: DBSession, current_user: CurrentUser, project_id: int = Query(...)):
    _require_enabled()
    await require_project_access(project_id, current_user, db)
    return await grounded_poc_service.list_runs(db, project_id)


@router.get("/runs/{run_id}", response_model=PocRunDetailOut)
async def get_run(run_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    run = await _get_run_or_404(db, run_id)
    await require_project_access(run.project_id, current_user, db)
    detail = await grounded_poc_service.get_run_detail(db, run)
    await db.commit()  # read-time reconciliation may have advanced the status
    return PocRunDetailOut(
        **PocRunOut.model_validate(run).model_dump(),
        routing=run.routing,
        coverage=run.coverage,
        pending_confirmation=run.pending_confirmation,
        script_ids=run.script_ids,
        **detail,
    )


@router.get("/runs/{run_id}/evidence/{evidence_id}", response_model=PocEvidenceDetailOut)
async def get_evidence(run_id: int, evidence_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    run = await _get_run_or_404(db, run_id)
    await require_project_access(run.project_id, current_user, db)
    row = await db.get(PocStateEvidence, evidence_id)
    if row is None or row.grounding_run_id != run.id:
        raise HTTPException(status_code=404, detail="Evidence package not found on this run")
    return PocEvidenceDetailOut(
        id=row.id,
        sequence=row.sequence,
        state_fingerprint=row.state_fingerprint,
        url=row.url,
        title=row.title,
        element_count=len(row.elements or []),
        blockers=row.blockers or [],
        produced_by_step=row.produced_by_step,
        has_screenshot=bool(row.screenshot_path),
        environment=row.environment,
        elements=row.elements or [],
        snapshot_text=row.snapshot_text,
        console_evidence=row.console_evidence or [],
        prev_evidence_id=row.prev_evidence_id,
    )


@router.post("/runs/{run_id}/start-capture", response_model=PocActionResponse, status_code=202)
async def start_capture(run_id: int, db: DBSession, current_user: CurrentUser):
    """Launch the target application and walk the test case's journey,
    capturing Application State Evidence Packages."""
    _require_enabled()
    run = await _get_run_or_404(db, run_id)
    await require_permission(GENERATE_AUTOMATION, run.project_id, current_user, db)
    try:
        agent_run, task_id = await grounded_poc_service.start_capture(db, run, current_user.id)
    except PocStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PocValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return PocActionResponse(
        grounding_run_id=run.id,
        status=run.status,
        agent_run_id=agent_run.id,
        task_id=task_id,
        message="Capture started — launching the application and walking the test case's journey.",
    )


@router.post("/runs/{run_id}/confirm-step", response_model=PocActionResponse, status_code=202)
async def confirm_step(
    run_id: int, body: PocConfirmStepRequest, db: DBSession, current_user: CurrentUser
):
    """Assisted mode: resolve the ambiguity the capture agent paused on."""
    _require_enabled()
    run = await _get_run_or_404(db, run_id)
    await require_permission(GENERATE_AUTOMATION, run.project_id, current_user, db)
    try:
        agent_run, task_id = await grounded_poc_service.confirm_step(
            db, run, current_user.id, step_index=body.step_index, element_name=body.element_name
        )
    except PocStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PocValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return PocActionResponse(
        grounding_run_id=run.id,
        status=run.status,
        agent_run_id=agent_run.id,
        task_id=task_id,
        message="Choice recorded — re-walking the journey with your confirmation.",
    )


@router.post("/runs/{run_id}/generate", response_model=PocActionResponse, status_code=202)
async def generate(run_id: int, db: DBSession, current_user: CurrentUser):
    """Evidence-gated generation: only allowed from gate_passed, and the
    generation LLM sees exclusively this run's captured element catalog."""
    _require_enabled()
    run = await _get_run_or_404(db, run_id)
    await require_permission(GENERATE_AUTOMATION, run.project_id, current_user, db)
    try:
        agent_run, task_id = await grounded_poc_service.start_generation(db, run, current_user.id)
    except PocStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PocValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return PocActionResponse(
        grounding_run_id=run.id,
        status=run.status,
        agent_run_id=agent_run.id,
        task_id=task_id,
        message="Generation started — the contract is restricted to captured evidence; "
                "the script will pass the static gate and live dry run before review.",
    )


@router.post("/runs/{run_id}/cancel", response_model=PocActionResponse)
async def cancel(run_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    run = await _get_run_or_404(db, run_id)
    await require_permission(GENERATE_AUTOMATION, run.project_id, current_user, db)
    try:
        await grounded_poc_service.cancel_run(db, run, current_user.id)
    except PocStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return PocActionResponse(
        grounding_run_id=run.id, status=run.status, message="Grounding run cancelled."
    )
