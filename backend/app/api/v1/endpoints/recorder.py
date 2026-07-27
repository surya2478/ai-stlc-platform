"""UI-019 Live Recorder endpoints — /api/v1/lab/recorder/*.

Gated on the same `DISCOVERY_SESSIONS_ENABLED` flag as UI-015, because the
Live Recorder drives the same capture engine: with that engine disabled there
is no browser to record through, and a recorder surface that cannot record
would be worse than an honest 404.

Lifecycle commands are delegated to UI-015's `session_service.issue_command`
rather than reimplemented — the state machine, idempotency contract and
pause/resume checkpointing are all already correct there, and a second
implementation would be a second thing to keep correct.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, require_entity_permission, require_permission
from app.config import get_settings
from app.models.discovery_session import DiscoveryAction, DiscoveryCapture, DiscoveryCheckpoint, DiscoverySessionEvent
from app.schemas.discovery_session import DiscoverySessionEventOut
from app.schemas.recorder import (
    CheckpointCreateRequest,
    CheckpointOut,
    CheckpointReviewRequest,
    DataBindingOut,
    DataBindingRequest,
    DiscoveredSubstepRequest,
    IrDraftOut,
    MapActionRequest,
    NoteCreateRequest,
    NoteOut,
    PreconditionResultOut,
    RecordActionRequest,
    RecordedActionOut,
    RecordingCommandRequest,
    RecordingCreateRequest,
    RecordingOut,
    RecordingReasonRequest,
    RecorderStepOut,
    SegmentOut,
    SegmentTransitionRequest,
    StepMappingOut,
    StepStatusRequest,
    UpdateMappingRequest,
)
from app.services.discovery import readiness_check, resume_validation_service
from app.services.discovery import session_service as discovery_session_service
from app.services.rbac_service import (
    RECORDER_CONTROL_RECORDING,
    RECORDER_CREATE_VERSION,
    RECORDER_DISCARD,
    RECORDER_GENERATE_IR,
    RECORDER_MAP_ACTIONS,
    RECORDER_START_RECORDING,
    RECORDER_VIEW,
)
from app.services.recorder import bindings as recorder_bindings
from app.services.recorder import checkpoints as recorder_checkpoints
from app.services.recorder import context as recorder_context
from app.services.recorder import lifecycle as recorder_lifecycle
from app.services.recorder import mapping as recorder_mapping
from app.services.recorder import notes as recorder_notes
from app.services.recorder import preconditions as recorder_preconditions
from app.services.recorder import segments as recorder_segments
from app.services.recorder import session_service as recorder_session_service
from app.services.recorder import steps as recorder_steps

router = APIRouter()

_COMMAND_PERMISSION = {
    "start": RECORDER_START_RECORDING,
    "pause": RECORDER_CONTROL_RECORDING,
    "resume": RECORDER_CONTROL_RECORDING,
    "stop": RECORDER_CONTROL_RECORDING,
    "checkpoint": RECORDER_CONTROL_RECORDING,
    "complete": RECORDER_CONTROL_RECORDING,
    "cancel": RECORDER_DISCARD,
}


def _require_enabled() -> None:
    if not get_settings().discovery_sessions_enabled:
        raise HTTPException(
            status_code=404,
            detail="Live Recorder is disabled (DISCOVERY_SESSIONS_ENABLED=false) — it drives the same "
                   "capture engine as Live Discovery.",
        )


def _dispatch_worker_task(session_id: int) -> None:
    from app.worker.tasks.discovery_tasks import run_capture_session

    run_capture_session.delay(session_id)


async def _load(db, session_id: int, permission: str, current_user):
    session = await recorder_session_service.get_recording_or_404(db, session_id)
    await require_entity_permission(session, permission, current_user, db)
    return session


# ── Sessions ─────────────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/recordings", response_model=RecordingOut)
async def create_recording(
    project_id: int, payload: RecordingCreateRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    await require_permission(RECORDER_START_RECORDING, project_id, current_user, db)
    return await recorder_session_service.create_session(
        db, project_id=project_id, user_id=current_user.id, **payload.model_dump()
    )


@router.get("/projects/{project_id}/recordings", response_model=list[RecordingOut])
async def list_recordings(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    suite_id: int | None = None,
    test_case_id: int | None = None,
    status: str | None = None,
):
    _require_enabled()
    await require_permission(RECORDER_VIEW, project_id, current_user, db)
    return await recorder_session_service.list_recordings(
        db, project_id=project_id, suite_id=suite_id, test_case_id=test_case_id, status=status
    )


@router.get("/recordings/{session_id}", response_model=RecordingOut)
async def get_recording(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    return await _load(db, session_id, RECORDER_VIEW, current_user)


@router.get("/recordings/{session_id}/inherited-context")
async def get_inherited_context(session_id: int, db: DBSession, current_user: CurrentUser):
    """Sections 9 and 10.1 — the read-only header and test case panel. Every
    value is resolved live from its owning entity on each call."""
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    return await recorder_session_service.build_inherited_context(db, session)


@router.get("/recordings/{session_id}/preconditions", response_model=PreconditionResultOut)
async def get_preconditions(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    result = await recorder_preconditions.evaluate(db, session)
    return PreconditionResultOut(**result.as_dict())


@router.post("/recordings/{session_id}/commands", response_model=RecordingOut)
async def issue_command(
    session_id: int, payload: RecordingCommandRequest, db: DBSession, current_user: CurrentUser
):
    """Start/pause/resume/stop/checkpoint/complete. Delegates the state
    machine to UI-015 and adds the recorder's own gates around it."""
    _require_enabled()
    permission = _COMMAND_PERMISSION.get(payload.command, RECORDER_CONTROL_RECORDING)
    session = await _load(db, session_id, permission, current_user)

    if payload.command in ("start", "resume"):
        preconditions = await recorder_preconditions.evaluate(db, session)
        if not preconditions.ready:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PRECONDITIONS_BLOCKED",
                    "message": "One or more blocking preconditions failed (Section 6).",
                    "blockers": [c.as_dict() for c in preconditions.blockers],
                },
            )

    if payload.command == "resume":
        checkpoint = (
            await db.get(DiscoveryCheckpoint, session.latest_checkpoint_id)
            if session.latest_checkpoint_id
            else None
        )
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

    session = await discovery_session_service.issue_command(
        db,
        session,
        command=payload.command,
        user_id=current_user.id,
        idempotency_key=payload.idempotency_key,
        reason=payload.reason,
        params=payload.params,
    )

    if payload.command in ("start", "resume"):
        await recorder_segments.ensure_initial_segment(db, session, user_id=current_user.id)
        _dispatch_worker_task(session.id)

    return session


@router.get("/recordings/{session_id}/readiness")
async def get_engine_readiness(session_id: int, db: DBSession, current_user: CurrentUser):
    """UI-015's engine-level readiness, exposed separately from Section 6's
    preconditions so a browser/runner problem is distinguishable from a
    governance one."""
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    result = await readiness_check.evaluate_session_readiness(db, session)
    return result.as_dict()


@router.post("/recordings/{session_id}/discard", response_model=RecordingOut)
async def discard_recording(
    session_id: int, payload: RecordingReasonRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_DISCARD, current_user)
    return await recorder_lifecycle.discard(db, session, user_id=current_user.id, reason=payload.reason)


@router.post("/recordings/{session_id}/new-version", response_model=RecordingOut)
async def create_new_version(
    session_id: int, payload: RecordingReasonRequest, db: DBSession, current_user: CurrentUser
):
    """Section 23/25 — never overwrite a finalized recording."""
    _require_enabled()
    session = await _load(db, session_id, RECORDER_CREATE_VERSION, current_user)
    return await recorder_session_service.create_version(
        db, session, user_id=current_user.id, reason=payload.reason
    )


# ── Steps ────────────────────────────────────────────────────────────────────


@router.get("/recordings/{session_id}/steps", response_model=list[RecorderStepOut])
async def list_steps(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    ctx = await recorder_context.load(db, session)
    return [RecorderStepOut(**vars(step)) for step in recorder_steps.build_step_list(ctx)]


@router.get("/recordings/{session_id}/active-step")
async def get_active_step(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    ctx = await recorder_context.load(db, session)
    return {"step_key": recorder_steps.active_step_key(ctx)}


@router.post("/recordings/{session_id}/steps/{step_key}/activate", response_model=list[RecorderStepOut])
async def activate_step(session_id: int, step_key: str, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_MAP_ACTIONS, current_user)
    await recorder_mapping.set_active_step(db, session, step_key=step_key, user_id=current_user.id)
    ctx = await recorder_context.load(db, session)
    return [RecorderStepOut(**vars(step)) for step in recorder_steps.build_step_list(ctx)]


@router.post("/recordings/{session_id}/steps/{step_key}/status", response_model=list[RecorderStepOut])
async def set_step_status(
    session_id: int, step_key: str, payload: StepStatusRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_MAP_ACTIONS, current_user)
    await recorder_mapping.set_step_status(
        db, session, step_key=step_key, status=payload.status, reason=payload.reason, user_id=current_user.id
    )
    ctx = await recorder_context.load(db, session)
    return [RecorderStepOut(**vars(step)) for step in recorder_steps.build_step_list(ctx)]


@router.post("/recordings/{session_id}/steps/discovered", response_model=list[RecorderStepOut])
async def add_discovered_substep(
    session_id: int, payload: DiscoveredSubstepRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_MAP_ACTIONS, current_user)
    await recorder_mapping.add_discovered_substep(
        db, session, parent_step_key=payload.parent_step_key, label=payload.label, user_id=current_user.id
    )
    ctx = await recorder_context.load(db, session)
    return [RecorderStepOut(**vars(step)) for step in recorder_steps.build_step_list(ctx)]


# ── Actions and mapping ──────────────────────────────────────────────────────


@router.get("/recordings/{session_id}/actions", response_model=list[RecordedActionOut])
async def list_actions(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    result = await db.execute(
        select(DiscoveryAction)
        .where(DiscoveryAction.session_id == session.id)
        .order_by(DiscoveryAction.sequence)
    )
    return list(result.scalars().all())


@router.post("/recordings/{session_id}/actions", response_model=RecordingOut)
async def record_action(
    session_id: int, payload: RecordActionRequest, db: DBSession, current_user: CurrentUser
):
    """Queues one user-directed action for the live capture worker. Returns
    the session, not the action — the action row only exists once the worker
    has actually performed it against the real application. Poll
    GET .../actions to see it appear."""
    _require_enabled()
    session = await _load(db, session_id, RECORDER_CONTROL_RECORDING, current_user)

    step_key = payload.active_step_key
    if step_key is None:
        ctx = await recorder_context.load(db, session)
        step_key = recorder_steps.active_step_key(ctx)

    return await discovery_session_service.record_free_action(
        db,
        session,
        user_id=current_user.id,
        idempotency_key=payload.idempotency_key,
        action_family=payload.action_family,
        target_ref=payload.target_ref,
        target_semantic=payload.target_semantic,
        input_text=payload.input_text,
        url=payload.url,
        active_step_key=step_key,
    )


@router.get("/recordings/{session_id}/mappings", response_model=list[StepMappingOut])
async def list_mappings(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    ctx = await recorder_context.load(db, session)
    return ctx.mappings


@router.post("/recordings/{session_id}/actions/{action_id}/map")
async def map_action(
    session_id: int, action_id: int, payload: MapActionRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_MAP_ACTIONS, current_user)
    mapping = await recorder_mapping.map_action(
        db, session, action_id=action_id, step_key=payload.step_key, user_id=current_user.id
    )
    return StepMappingOut.model_validate(mapping) if mapping is not None else None


@router.patch("/recordings/{session_id}/actions/{action_id}/mapping", response_model=StepMappingOut)
async def update_mapping(
    session_id: int, action_id: int, payload: UpdateMappingRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_MAP_ACTIONS, current_user)
    fields = payload.model_dump(exclude_unset=True)
    return await recorder_mapping.update_mapping(
        db,
        session,
        action_id=action_id,
        user_id=current_user.id,
        lifecycle_phase=fields.get("lifecycle_phase", ...),
        excluded_from_ir=fields.get("excluded_from_ir"),
        exclusion_reason=fields.get("exclusion_reason"),
        review_state=fields.get("review_state"),
    )


# ── Checkpoints ──────────────────────────────────────────────────────────────


@router.get("/recordings/{session_id}/checkpoints", response_model=list[CheckpointOut])
async def list_checkpoints(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    return await recorder_checkpoints.list_checkpoints(db, session)


@router.post("/recordings/{session_id}/checkpoints", response_model=CheckpointOut)
async def create_checkpoint(
    session_id: int, payload: CheckpointCreateRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_MAP_ACTIONS, current_user)
    return await recorder_checkpoints.create_checkpoint(
        db, session, user_id=current_user.id, **payload.model_dump()
    )


@router.post("/recordings/{session_id}/checkpoints/{checkpoint_id}/review", response_model=CheckpointOut)
async def review_checkpoint(
    session_id: int,
    checkpoint_id: int,
    payload: CheckpointReviewRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_MAP_ACTIONS, current_user)
    return await recorder_checkpoints.review_checkpoint(
        db,
        session,
        checkpoint_id=checkpoint_id,
        review_state=payload.review_state,
        expected_value=payload.expected_value,
        user_id=current_user.id,
    )


@router.delete("/recordings/{session_id}/checkpoints/{checkpoint_id}", status_code=204)
async def delete_checkpoint(session_id: int, checkpoint_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_MAP_ACTIONS, current_user)
    await recorder_checkpoints.delete_checkpoint(db, session, checkpoint_id=checkpoint_id)


# ── Segments ─────────────────────────────────────────────────────────────────


@router.get("/recordings/{session_id}/segments", response_model=list[SegmentOut])
async def list_segments(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    return await recorder_segments.list_segments(db, session)


@router.post("/recordings/{session_id}/segments/transition", response_model=SegmentOut)
async def transition_segment(
    session_id: int, payload: SegmentTransitionRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_CONTROL_RECORDING, current_user)
    return await recorder_segments.transition(
        db,
        session,
        application_id=payload.application_id,
        environment=payload.environment,
        transition_reason=payload.transition_reason,
        user_id=current_user.id,
    )


# ── Data bindings ────────────────────────────────────────────────────────────


@router.get("/recordings/{session_id}/data-bindings", response_model=list[DataBindingOut])
async def list_data_bindings(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    return await recorder_bindings.list_bindings(db, session)


@router.put("/recordings/{session_id}/data-bindings", response_model=DataBindingOut)
async def upsert_data_binding(
    session_id: int, payload: DataBindingRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_MAP_ACTIONS, current_user)
    return await recorder_bindings.upsert_binding(
        db, session, user_id=current_user.id, **payload.model_dump()
    )


@router.delete("/recordings/{session_id}/data-bindings/{binding_id}", status_code=204)
async def delete_data_binding(session_id: int, binding_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_MAP_ACTIONS, current_user)
    await recorder_bindings.delete_binding(db, session, binding_id=binding_id)


# ── Notes ────────────────────────────────────────────────────────────────────


@router.get("/recordings/{session_id}/notes", response_model=list[NoteOut])
async def list_notes(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    return await recorder_notes.list_notes(db, session)


@router.post("/recordings/{session_id}/notes", response_model=NoteOut)
async def create_note(
    session_id: int, payload: NoteCreateRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_MAP_ACTIONS, current_user)
    return await recorder_notes.create_note(db, session, user_id=current_user.id, **payload.model_dump())


@router.delete("/recordings/{session_id}/notes/{note_id}", status_code=204)
async def delete_note(session_id: int, note_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_MAP_ACTIONS, current_user)
    await recorder_notes.delete_note(db, session, note_id=note_id)


# ── Evidence ─────────────────────────────────────────────────────────────────


@router.get("/recordings/{session_id}/captures")
async def list_captures(
    session_id: int, db: DBSession, current_user: CurrentUser, action_id: int | None = None
):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    query = select(DiscoveryCapture).where(DiscoveryCapture.session_id == session.id)
    if action_id is not None:
        query = query.where(DiscoveryCapture.action_id == action_id)
    result = await db.execute(query.order_by(DiscoveryCapture.id))
    return [
        {
            "id": capture.id,
            "action_id": capture.action_id,
            "capture_type": capture.capture_type,
            "captured_at": capture.captured_at,
            "source": capture.source,
            "redaction_state": capture.redaction_state,
            "retention_state": capture.retention_state,
        }
        for capture in result.scalars().all()
    ]


@router.get("/recordings/{session_id}/captures/{capture_id}/image")
async def get_capture_image(session_id: int, capture_id: int, db: DBSession, current_user: CurrentUser):
    """Serves a screenshot capture as an image.

    This is what makes the centre viewport show the real application rather
    than a text snapshot. Screenshots were already being captured to the
    managed workspace by UI-015; nothing served them. The same
    realpath-containment check every other capture reader uses applies here —
    a capture row whose path escapes the workspace root is refused, not read.
    """
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    capture = await db.get(DiscoveryCapture, capture_id)
    if capture is None or capture.session_id != session.id:
        raise HTTPException(status_code=404, detail="Capture not found in this recording session.")
    if capture.capture_type != "screenshot":
        raise HTTPException(
            status_code=400,
            detail=f"Capture type '{capture.capture_type}' is not an image — use the text content endpoint.",
        )

    from app.services.discovery.capture_service import discovery_workspace_root

    storage_root = os.path.realpath(discovery_workspace_root())
    real_path = os.path.realpath(capture.storage_path)
    if not (real_path.startswith(storage_root + os.sep) or real_path == storage_root):
        raise HTTPException(status_code=403, detail="Capture path is outside the managed workspace root.")
    if not os.path.exists(real_path):
        raise HTTPException(status_code=410, detail="Capture file is no longer available.")

    return FileResponse(real_path, media_type="image/png")


@router.get("/recordings/{session_id}/latest-view")
async def get_latest_view(session_id: int, db: DBSession, current_user: CurrentUser):
    """The centre panel's current picture of the application: the newest
    screenshot capture and the accessibility snapshot taken alongside it.

    The snapshot is what the user picks element refs from, so the two must
    come from the same action — returning a newer snapshot with an older
    screenshot would have them clicking refs that no longer exist.
    """
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)

    result = await db.execute(
        select(DiscoveryAction)
        .where(DiscoveryAction.session_id == session.id)
        .order_by(DiscoveryAction.sequence.desc())
        .limit(1)
    )
    action = result.scalar_one_or_none()
    if action is None:
        return {
            "action_id": None,
            "sequence": None,
            "screenshot_capture_id": None,
            "accessibility_snapshot": None,
            "page_url": None,
            "captured_at": None,
        }

    capture_result = await db.execute(
        select(DiscoveryCapture)
        .where(
            DiscoveryCapture.session_id == session.id,
            DiscoveryCapture.action_id == action.id,
            DiscoveryCapture.capture_type == "screenshot",
        )
        .limit(1)
    )
    screenshot = capture_result.scalar_one_or_none()

    return {
        "action_id": action.id,
        "sequence": action.sequence,
        "screenshot_capture_id": screenshot.id if screenshot else None,
        "accessibility_snapshot": (action.post_state or {}).get("accessibility_snapshot_excerpt"),
        "page_url": (action.locator_evidence or {}).get("page_url")
        or (action.input_binding or {}).get("url"),
        "captured_at": action.occurred_at,
    }


# ── Summary, IR and audit ────────────────────────────────────────────────────


@router.get("/recordings/{session_id}/summary")
async def get_summary(session_id: int, db: DBSession, current_user: CurrentUser):
    """Section 21's recording summary."""
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    return await recorder_lifecycle.build_summary(db, session)


@router.post("/recordings/{session_id}/finalize")
async def finalize_recording(session_id: int, db: DBSession, current_user: CurrentUser):
    """Section 13's Stop post-processing: close the open segment, parse network
    activity, propose grounded checkpoints, and return the summary."""
    _require_enabled()
    session = await _load(db, session_id, RECORDER_CONTROL_RECORDING, current_user)
    return await recorder_lifecycle.finalize_stop(db, session, user_id=current_user.id)


@router.get("/recordings/{session_id}/ir-draft", response_model=IrDraftOut | None)
async def get_ir_draft(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    return await recorder_lifecycle.get_current_ir_draft(db, session)


@router.post("/recordings/{session_id}/ir-draft", response_model=IrDraftOut)
async def emit_ir_draft(session_id: int, db: DBSession, current_user: CurrentUser):
    """Section 22 — Save and Continue to Automation IR."""
    _require_enabled()
    session = await _load(db, session_id, RECORDER_GENERATE_IR, current_user)
    return await recorder_lifecycle.emit_ir_draft(db, session, user_id=current_user.id)


@router.get("/recordings/{session_id}/activity", response_model=list[DiscoverySessionEventOut])
async def get_activity(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await _load(db, session_id, RECORDER_VIEW, current_user)
    result = await db.execute(
        select(DiscoverySessionEvent)
        .where(DiscoverySessionEvent.session_id == session.id)
        .order_by(DiscoverySessionEvent.occurred_at)
    )
    return list(result.scalars().all())
