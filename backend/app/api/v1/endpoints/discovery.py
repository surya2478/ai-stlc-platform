"""UI-015 Live Discovery Session endpoints — /api/v1/discovery/*.

Deliberately isolated namespace, same 404-when-disabled pattern as
grounded_poc.py / automation_classification.py: every route 404s when
DISCOVERY_SESSIONS_ENABLED is off. Phase 1+2 (Guided User Recording, Free
User-Action Recording) — Agent-Driven-only commands are accepted by the
generic /commands endpoint but refused with an explicit reason by
session_service.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, require_entity_permission, require_permission
from app.config import get_settings
from app.models.discovery_session import (
    DiscoveryAction,
    DiscoveryCapture,
    DiscoveryCheckpoint,
    DiscoverySession,
    DiscoverySessionEvent,
)
from app.schemas.discovery_session import (
    CurrentStepOut,
    DiscoveryActionCorrectionRequest,
    DiscoveryActionOut,
    DiscoveryCaptureOut,
    DiscoveryCheckpointOut,
    DiscoverySessionCommandRequest,
    DiscoverySessionCreateRequest,
    DiscoverySessionEventOut,
    DiscoverySessionOut,
    EligibleTestCaseOut,
    ReadinessResultOut,
    RecordFreeActionRequest,
    ResumeValidationOut,
)
from app.services.discovery import capture_service, readiness_check, resume_validation_service, session_service
from app.services.rbac_service import (
    DISCOVERY_COMPLETE_SESSION,
    DISCOVERY_CONTROL_SESSION,
    DISCOVERY_CORRECT_ACTION,
    DISCOVERY_EMERGENCY_STOP,
    DISCOVERY_START_SESSION,
    DISCOVERY_VIEW,
)

router = APIRouter()

_COMMAND_PERMISSION = {
    "start": DISCOVERY_START_SESSION,
    "pause": DISCOVERY_CONTROL_SESSION,
    "resume": DISCOVERY_CONTROL_SESSION,
    "stop": DISCOVERY_CONTROL_SESSION,
    "checkpoint": DISCOVERY_CONTROL_SESSION,
    "complete": DISCOVERY_COMPLETE_SESSION,
    "cancel": DISCOVERY_CONTROL_SESSION,
    "emergency_stop": DISCOVERY_EMERGENCY_STOP,
    "approve_next_action": DISCOVERY_CONTROL_SESSION,
    "modify_next_action": DISCOVERY_CONTROL_SESSION,
    "take_manual_control": DISCOVERY_CONTROL_SESSION,
    "return_control_to_agent": DISCOVERY_CONTROL_SESSION,
    "skip_action": DISCOVERY_CONTROL_SESSION,
    "rollback": DISCOVERY_CONTROL_SESSION,
}


def _require_enabled() -> None:
    if not get_settings().discovery_sessions_enabled:
        raise HTTPException(status_code=404, detail="Live Discovery Session is disabled (DISCOVERY_SESSIONS_ENABLED=false)")


def _dispatch_worker_task(discovery_session_id: int) -> None:
    from app.worker.tasks.discovery_tasks import run_capture_session

    run_capture_session.delay(discovery_session_id)


@router.get("/projects/{project_id}/eligible-test-cases", response_model=list[EligibleTestCaseOut])
async def get_eligible_test_cases(
    project_id: int, application_id: int, mode: str, db: DBSession, current_user: CurrentUser,
):
    _require_enabled()
    await require_permission(DISCOVERY_VIEW, project_id, current_user, db)
    rows = await session_service.list_eligible_test_cases(db, project_id=project_id, application_id=application_id, mode=mode)
    return [EligibleTestCaseOut(**vars(r)) for r in rows]


@router.post("/projects/{project_id}/sessions", response_model=DiscoverySessionOut)
async def create_session(
    project_id: int, payload: DiscoverySessionCreateRequest, db: DBSession, current_user: CurrentUser,
):
    _require_enabled()
    await require_permission(DISCOVERY_START_SESSION, project_id, current_user, db)
    session = await session_service.create_session(
        db, project_id=project_id, user_id=current_user.id, **payload.model_dump(),
    )
    return session


@router.get("/projects/{project_id}/sessions", response_model=list[DiscoverySessionOut])
async def list_sessions(
    project_id: int, db: DBSession, current_user: CurrentUser,
    application_id: int | None = None, status: str | None = None,
):
    _require_enabled()
    await require_permission(DISCOVERY_VIEW, project_id, current_user, db)
    return await session_service.list_sessions(db, project_id=project_id, application_id=application_id, status_filter=status)


@router.get("/sessions/{session_id}", response_model=DiscoverySessionOut)
async def get_session(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await session_service.get_session_or_404(db, session_id)
    await require_entity_permission(session, DISCOVERY_VIEW, current_user, db)
    return session


@router.get("/sessions/{session_id}/current-step", response_model=CurrentStepOut)
async def get_current_step(session_id: int, db: DBSession, current_user: CurrentUser):
    """Agent-Driven mode's proposed-next-step (Section 11.1) — what the
    supervision loop is about to act on, without executing anything."""
    _require_enabled()
    session = await session_service.get_session_or_404(db, session_id)
    await require_entity_permission(session, DISCOVERY_VIEW, current_user, db)
    step = await capture_service.get_current_step(db, session)
    return CurrentStepOut(**step) if step else CurrentStepOut(text=None, step_ref=None)


@router.post("/sessions/{session_id}/readiness", response_model=ReadinessResultOut)
async def evaluate_readiness(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await session_service.get_session_or_404(db, session_id)
    await require_entity_permission(session, DISCOVERY_VIEW, current_user, db)
    result = await readiness_check.evaluate_session_readiness(db, session)
    return ReadinessResultOut(**result.as_dict())


@router.post("/sessions/{session_id}/commands", response_model=DiscoverySessionOut)
async def issue_command(
    session_id: int, payload: DiscoverySessionCommandRequest, db: DBSession, current_user: CurrentUser,
):
    _require_enabled()
    session = await session_service.get_session_or_404(db, session_id)
    permission = _COMMAND_PERMISSION.get(payload.command, DISCOVERY_CONTROL_SESSION)
    await require_entity_permission(session, permission, current_user, db)

    if payload.command in ("start", "resume"):
        readiness = await readiness_check.evaluate_session_readiness(db, session)
        if not readiness.ready:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "READINESS_BLOCKED",
                    "message": "Cannot start/resume — one or more mandatory readiness checks failed.",
                    "blockers": [c.as_dict() for c in readiness.blockers],
                },
            )

    if payload.command == "resume":
        checkpoint = None
        if session.latest_checkpoint_id:
            checkpoint = await db.get(DiscoveryCheckpoint, session.latest_checkpoint_id)
        validation = resume_validation_service.classify_resume_state(session, checkpoint)
        session.resume_state_classification = validation.classification
        recovery_option = (payload.params or {}).get("recovery_option")
        if recovery_option not in validation.allowed_recovery_options:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "RESUME_RECOVERY_OPTION_REQUIRED",
                    "message": f"Session state classified as '{validation.classification}' — "
                               f"choose one of {validation.allowed_recovery_options}.",
                    "classification": validation.classification,
                    "allowed_recovery_options": list(validation.allowed_recovery_options),
                },
            )

    session = await session_service.issue_command(
        db, session, command=payload.command, user_id=current_user.id, idempotency_key=payload.idempotency_key,
        reason=payload.reason, params=payload.params,
    )

    if payload.command in ("start", "resume"):
        _dispatch_worker_task(session.id)

    return session


@router.get("/sessions/{session_id}/actions", response_model=list[DiscoveryActionOut])
async def list_actions(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await session_service.get_session_or_404(db, session_id)
    await require_entity_permission(session, DISCOVERY_VIEW, current_user, db)
    result = await db.execute(
        select(DiscoveryAction).where(DiscoveryAction.session_id == session_id).order_by(DiscoveryAction.sequence)
    )
    return list(result.scalars().all())


@router.post("/sessions/{session_id}/actions", response_model=DiscoverySessionOut)
async def record_action(
    session_id: int, payload: RecordFreeActionRequest, db: DBSession, current_user: CurrentUser,
):
    """Queue one Free User-Action Recording action (Section 5.2) for the
    live capture task's next poll tick. Returns the session, not the
    resulting DiscoveryAction — the action is created asynchronously once
    the task actually performs it; poll GET .../actions to see it appear."""
    _require_enabled()
    session = await session_service.get_session_or_404(db, session_id)
    await require_entity_permission(session, DISCOVERY_CONTROL_SESSION, current_user, db)
    return await session_service.record_free_action(
        db, session, user_id=current_user.id, idempotency_key=payload.idempotency_key,
        action_family=payload.action_family, target_ref=payload.target_ref,
        target_semantic=payload.target_semantic, input_text=payload.input_text, url=payload.url,
    )


@router.post("/sessions/{session_id}/actions/{action_id}/correct", response_model=DiscoveryActionOut)
async def correct_action(
    session_id: int, action_id: int, payload: DiscoveryActionCorrectionRequest, db: DBSession, current_user: CurrentUser,
):
    _require_enabled()
    session = await session_service.get_session_or_404(db, session_id)
    await require_entity_permission(session, DISCOVERY_CORRECT_ACTION, current_user, db)
    action = await db.get(DiscoveryAction, action_id)
    if action is None or action.session_id != session_id:
        raise HTTPException(status_code=404, detail="Action not found in this session")
    if payload.inclusion_state not in ("included", "excluded", "corrected", "skipped", "rolled_back"):
        raise HTTPException(status_code=400, detail="Invalid inclusion_state")

    history_entry = {
        "previous_inclusion_state": action.inclusion_state,
        "new_inclusion_state": payload.inclusion_state,
        "reviewer_note": payload.reviewer_note,
        "reason": payload.reason,
        "mapped_test_step_ref": payload.mapped_test_step_ref,
        "changed_by": current_user.id,
    }
    action.correction_history = [*(action.correction_history or []), history_entry]
    action.inclusion_state = payload.inclusion_state
    if payload.reviewer_note:
        action.reviewer_note = payload.reviewer_note
    if payload.mapped_test_step_ref is not None:
        # Mapping only (Section 5.2) — no publish/automation-generation
        # workflow reads this yet, it just records reviewer intent.
        action.test_step_ref = payload.mapped_test_step_ref
    await db.commit()
    await db.refresh(action)
    return action


@router.post("/sessions/{session_id}/complete", response_model=DiscoverySessionOut)
async def complete_session(session_id: int, payload: DiscoverySessionCommandRequest, db: DBSession, current_user: CurrentUser):
    """Thin alias over POST /commands with command="complete" — kept as its
    own route per the plan's endpoint list (Section 18 allows either shape)."""
    payload.command = "complete"
    return await issue_command(session_id, payload, db, current_user)


@router.post("/sessions/{session_id}/cancel", response_model=DiscoverySessionOut)
async def cancel_session(session_id: int, payload: DiscoverySessionCommandRequest, db: DBSession, current_user: CurrentUser):
    payload.command = "cancel"
    return await issue_command(session_id, payload, db, current_user)


@router.get("/sessions/{session_id}/checkpoints", response_model=list[DiscoveryCheckpointOut])
async def list_checkpoints(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await session_service.get_session_or_404(db, session_id)
    await require_entity_permission(session, DISCOVERY_VIEW, current_user, db)
    result = await db.execute(
        select(DiscoveryCheckpoint).where(DiscoveryCheckpoint.session_id == session_id).order_by(DiscoveryCheckpoint.sequence)
    )
    return list(result.scalars().all())


@router.get("/sessions/{session_id}/captures/{capture_id}", response_model=DiscoveryCaptureOut)
async def get_capture(session_id: int, capture_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await session_service.get_session_or_404(db, session_id)
    await require_entity_permission(session, DISCOVERY_VIEW, current_user, db)
    capture = await db.get(DiscoveryCapture, capture_id)
    if capture is None or capture.session_id != session_id:
        raise HTTPException(status_code=404, detail="Capture not found in this session")
    return capture


@router.get("/sessions/{session_id}/activity", response_model=list[DiscoverySessionEventOut])
async def get_activity(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await session_service.get_session_or_404(db, session_id)
    await require_entity_permission(session, DISCOVERY_VIEW, current_user, db)
    result = await db.execute(
        select(DiscoverySessionEvent).where(DiscoverySessionEvent.session_id == session_id).order_by(DiscoverySessionEvent.occurred_at)
    )
    return list(result.scalars().all())
