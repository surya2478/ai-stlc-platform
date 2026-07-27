"""Action-to-step mapping and step state transitions (Contract Sections 7.1, 15).

Writes only. Everything these functions produce is read back through
`steps.build_step_list`, which recomputes derived status rather than trusting
anything stored here beyond the explicit user decisions listed in
`steps.USER_OWNED_STATES`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_session import DiscoveryAction, DiscoverySession, DiscoverySessionEvent
from app.models.recording_session import RecordingStepMapping, RecordingStepState
from app.services.recorder import context as recorder_context
from app.services.recorder import steps as recorder_steps
from app.services.recorder.errors import RecorderError

# Section 10.3's step actions map onto these. "ACTIVE" is handled separately by
# `set_active_step` because it is exclusive within a session.
SETTABLE_STEP_STATUSES = ("PENDING", "COMPLETED", "SKIPPED", "MISMATCH", "NEEDS_REVIEW")


async def _get_or_create_state(
    db: AsyncSession,
    session: DiscoverySession,
    step_key: str,
    *,
    source_step_index: int | None = None,
    parent_step_key: str | None = None,
    discovered_label: str | None = None,
) -> RecordingStepState:
    result = await db.execute(
        select(RecordingStepState).where(
            RecordingStepState.session_id == session.id, RecordingStepState.step_key == step_key
        )
    )
    state = result.scalar_one_or_none()
    if state is not None:
        return state
    state = RecordingStepState(
        session_id=session.id,
        project_id=session.project_id,
        step_key=step_key,
        source_step_index=source_step_index,
        parent_step_key=parent_step_key,
        discovered_label=discovered_label,
        status="PENDING",
    )
    db.add(state)
    await db.flush()
    return state


async def _known_step_keys(db: AsyncSession, session: DiscoverySession) -> tuple[set[str], dict[str, int]]:
    """Every addressable step key for this session, and the source index of
    each real test case step."""
    ctx = await recorder_context.load(db, session)
    keys: set[str] = set()
    index_by_key: dict[str, int] = {}
    for index, _ in enumerate(ctx.source_steps):
        key = recorder_steps.step_key_for_index(index)
        keys.add(key)
        index_by_key[key] = index
    for state in ctx.step_states:
        keys.add(state.step_key)
    return keys, index_by_key


async def _require_step_key(db: AsyncSession, session: DiscoverySession, step_key: str) -> int | None:
    keys, index_by_key = await _known_step_keys(db, session)
    if step_key not in keys:
        raise RecorderError(
            404,
            "STEP_NOT_FOUND",
            f"Step '{step_key}' does not exist in this recording's test case or discovered sub-steps.",
        )
    return index_by_key.get(step_key)


async def _audit(
    db: AsyncSession,
    session: DiscoverySession,
    *,
    command: str,
    user_id: int,
    reason: str | None = None,
) -> None:
    """Section 25 — mapping changes and checkpoints are audited on the same
    immutable event log the session lifecycle already writes to."""
    db.add(
        DiscoverySessionEvent(
            session_id=session.id,
            project_id=session.project_id,
            actor_id=user_id,
            actor_type="user",
            previous_state=session.status,
            new_state=session.status,
            command=command,
            reason=reason,
            correlation_id=session.correlation_id,
            occurred_at=datetime.now(timezone.utc),
        )
    )


async def set_active_step(db: AsyncSession, session: DiscoverySession, *, step_key: str, user_id: int) -> None:
    """Section 10.3 "Set Active Step". Exactly one step is ACTIVE at a time —
    the previous one drops back to PENDING so its status resumes being derived
    from what was actually recorded against it."""
    source_index = await _require_step_key(db, session, step_key)

    result = await db.execute(
        select(RecordingStepState).where(
            RecordingStepState.session_id == session.id, RecordingStepState.status == "ACTIVE"
        )
    )
    for previous in result.scalars().all():
        if previous.step_key == step_key:
            continue
        previous.status = "PENDING"
        previous.updated_by = user_id

    state = await _get_or_create_state(db, session, step_key, source_step_index=source_index)
    state.status = "ACTIVE"
    state.updated_by = user_id
    await _audit(db, session, command="set_active_step", user_id=user_id, reason=f"Step {step_key}")
    await db.commit()


async def set_step_status(
    db: AsyncSession,
    session: DiscoverySession,
    *,
    step_key: str,
    status: str,
    reason: str | None,
    user_id: int,
) -> None:
    """Section 10.3 Complete Step / Skip with Reason / flag for review."""
    if status not in SETTABLE_STEP_STATUSES:
        raise RecorderError(
            400,
            "INVALID_STEP_STATUS",
            f"'{status}' is not a settable step status. Use one of {list(SETTABLE_STEP_STATUSES)}, "
            "or the set-active-step action for ACTIVE.",
        )
    if status == "SKIPPED" and not (reason or "").strip():
        raise RecorderError(
            400, "SKIP_REASON_REQUIRED", f"Skipping step {step_key} requires a reason (Section 7.1)."
        )

    source_index = await _require_step_key(db, session, step_key)
    state = await _get_or_create_state(db, session, step_key, source_step_index=source_index)
    state.status = status
    state.skip_reason = reason if status == "SKIPPED" else None
    state.updated_by = user_id
    await _audit(db, session, command="set_step_status", user_id=user_id, reason=f"Step {step_key} -> {status}")
    await db.commit()


async def add_discovered_substep(
    db: AsyncSession, session: DiscoverySession, *, parent_step_key: str, label: str, user_id: int
) -> RecordingStepState:
    """Section 7.1 "Add discovered sub-step" — a real interaction the test case
    does not describe. It is recorded under its parent rather than silently
    folded into it, so review can see what the test case is missing."""
    if not (label or "").strip():
        raise RecorderError(400, "SUBSTEP_LABEL_REQUIRED", "A discovered sub-step needs a description.")
    await _require_step_key(db, session, parent_step_key)

    keys, _ = await _known_step_keys(db, session)
    step_key = recorder_steps.next_substep_key(parent_step_key, keys)
    state = await _get_or_create_state(
        db,
        session,
        step_key,
        parent_step_key=parent_step_key,
        discovered_label=label.strip(),
    )
    state.updated_by = user_id
    await _audit(
        db, session, command="add_discovered_substep", user_id=user_id, reason=f"{step_key} under {parent_step_key}"
    )
    await db.commit()
    await db.refresh(state)
    return state


async def auto_map_action(
    db: AsyncSession, session: DiscoverySession, action: DiscoveryAction, *, step_key: str | None
) -> RecordingStepMapping | None:
    """Attaches a just-recorded action to the step that was active when the
    user asked for it (Section 15's "active step" automatic mapping).

    Called from the capture worker, not the API, because that is the only
    place that knows the action was actually performed. Returns None when no
    step was active — an unmapped action is a legitimate, reportable state
    (Section 21), not an error, and never a guess.
    """
    if not step_key:
        return None

    existing = await db.execute(
        select(RecordingStepMapping).where(RecordingStepMapping.action_id == action.id)
    )
    if existing.scalar_one_or_none() is not None:
        return None

    mapping = RecordingStepMapping(
        session_id=session.id,
        project_id=session.project_id,
        action_id=action.id,
        step_key=step_key,
        mapping_source="active_step",
        # Deliberately null: the user chose the active step, so this is a
        # recorded fact, not a scored inference. See the model's comment.
        confidence=None,
        review_state="accepted",
    )
    db.add(mapping)
    action.test_step_ref = step_key
    await db.flush()
    return mapping


async def map_action(
    db: AsyncSession, session: DiscoverySession, *, action_id: int, step_key: str | None, user_id: int
) -> RecordingStepMapping | None:
    """Section 15 — map, re-map or unmap one action by hand. `step_key=None`
    removes the mapping, which is how an action is returned to the unmapped
    list rather than deleted."""
    action = await db.get(DiscoveryAction, action_id)
    if action is None or action.session_id != session.id:
        raise RecorderError(404, "ACTION_NOT_FOUND", "Action not found in this recording session.")

    result = await db.execute(select(RecordingStepMapping).where(RecordingStepMapping.action_id == action_id))
    mapping = result.scalar_one_or_none()

    if step_key is None:
        if mapping is not None:
            await db.delete(mapping)
        action.test_step_ref = None
        await _audit(db, session, command="unmap_action", user_id=user_id, reason=f"Action {action_id}")
        await db.commit()
        return None

    await _require_step_key(db, session, step_key)

    if mapping is None:
        mapping = RecordingStepMapping(
            session_id=session.id,
            project_id=session.project_id,
            action_id=action_id,
            step_key=step_key,
            mapping_source="user",
            review_state="accepted",
        )
        db.add(mapping)
    else:
        mapping.step_key = step_key
        mapping.mapping_source = "user"
        mapping.review_state = "accepted"
    mapping.mapped_by = user_id
    action.test_step_ref = step_key
    await _audit(
        db, session, command="map_action", user_id=user_id, reason=f"Action {action_id} -> step {step_key}"
    )
    await db.commit()
    await db.refresh(mapping)
    return mapping


async def update_mapping(
    db: AsyncSession,
    session: DiscoverySession,
    *,
    action_id: int,
    user_id: int,
    lifecycle_phase: str | None = ...,
    excluded_from_ir: bool | None = None,
    exclusion_reason: str | None = None,
    review_state: str | None = None,
) -> RecordingStepMapping:
    """Section 15 — mark setup/teardown, or hold an action out of the IR.

    `lifecycle_phase` uses an Ellipsis sentinel so that explicitly clearing it
    to None is distinguishable from not passing it at all.
    """
    result = await db.execute(select(RecordingStepMapping).where(RecordingStepMapping.action_id == action_id))
    mapping = result.scalar_one_or_none()
    if mapping is None or mapping.session_id != session.id:
        raise RecorderError(
            404,
            "MAPPING_NOT_FOUND",
            "This action is not mapped to a step yet — map it to a step before marking it setup, "
            "teardown or excluded.",
        )

    if lifecycle_phase is not ...:
        if lifecycle_phase not in (None, "setup", "teardown"):
            raise RecorderError(
                400, "INVALID_LIFECYCLE_PHASE", "lifecycle_phase must be 'setup', 'teardown' or null."
            )
        mapping.lifecycle_phase = lifecycle_phase

    if excluded_from_ir is not None:
        if excluded_from_ir and not (exclusion_reason or "").strip():
            raise RecorderError(
                400,
                "EXCLUSION_REASON_REQUIRED",
                "Excluding a recorded action from the Automation IR requires a reason.",
            )
        mapping.excluded_from_ir = excluded_from_ir
        mapping.exclusion_reason = exclusion_reason if excluded_from_ir else None

    if review_state is not None:
        if review_state not in ("accepted", "needs_review", "rejected"):
            raise RecorderError(400, "INVALID_REVIEW_STATE", "review_state must be accepted/needs_review/rejected.")
        mapping.review_state = review_state

    mapping.mapped_by = user_id
    await _audit(db, session, command="update_mapping", user_id=user_id, reason=f"Action {action_id}")
    await db.commit()
    await db.refresh(mapping)
    return mapping
