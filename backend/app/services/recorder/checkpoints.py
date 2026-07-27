"""Validation checkpoints (Contract Section 16).

A checkpoint is what the generated script will assert. Two ways one comes into
existence, and the difference matters:

- A user creates it. It enters `accepted` and goes straight into the IR.
- The recorder recommends it. It enters `recommended` + `needs_review` and is
  held out of the IR until a person accepts it — Section 16's "recorder
  recommendations must not silently become final assertions".

Recommendations are only ever derived from something the recorder actually
observed: the URL a real navigation landed on, and whether console capture was
on. A step's expected result is *not* turned into an assertion, because
converting "Search results are displayed" into a selector requires guessing at
behaviour nobody performed. That case is reported as a gap instead (see
`steps.expected_results_without_checkpoints`), which tells the truth: the test
case wants something checked and the recording does not yet check it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_session import DiscoveryAction, DiscoverySession
from app.models.recording_session import CHECKPOINT_TYPES, RecordingCheckpoint
from app.services.recorder import context as recorder_context
from app.services.recorder.errors import RecorderError

# Which checkpoint types actually render into an assertion lives in
# `ir_emitter.CHECKPOINT_ASSERTIONS` — one source of truth, since the answer
# is a property of the IR contract rather than of this module.


async def list_checkpoints(db: AsyncSession, session: DiscoverySession) -> list[RecordingCheckpoint]:
    result = await db.execute(
        select(RecordingCheckpoint)
        .where(RecordingCheckpoint.session_id == session.id)
        .order_by(RecordingCheckpoint.id)
    )
    return list(result.scalars().all())


async def create_checkpoint(
    db: AsyncSession,
    session: DiscoverySession,
    *,
    user_id: int,
    checkpoint_type: str,
    step_key: str | None = None,
    action_id: int | None = None,
    target: str | None = None,
    expected_value: str | None = None,
    expected_result_ref: str | None = None,
) -> RecordingCheckpoint:
    if checkpoint_type not in CHECKPOINT_TYPES:
        raise RecorderError(
            400, "INVALID_CHECKPOINT_TYPE", f"'{checkpoint_type}' is not a supported checkpoint type."
        )
    if action_id is not None:
        action = await db.get(DiscoveryAction, action_id)
        if action is None or action.session_id != session.id:
            raise RecorderError(404, "ACTION_NOT_FOUND", "Action not found in this recording session.")

    checkpoint = RecordingCheckpoint(
        session_id=session.id,
        project_id=session.project_id,
        action_id=action_id,
        step_key=step_key,
        checkpoint_type=checkpoint_type,
        target=target,
        expected_value=expected_value,
        expected_result_ref=expected_result_ref,
        source="user",
        review_state="accepted",
        created_by=user_id,
    )
    db.add(checkpoint)
    await db.commit()
    await db.refresh(checkpoint)
    return checkpoint


async def review_checkpoint(
    db: AsyncSession,
    session: DiscoverySession,
    *,
    checkpoint_id: int,
    review_state: str,
    user_id: int,
    expected_value: str | None = None,
) -> RecordingCheckpoint:
    """Accept, reject or re-flag a checkpoint. Accepting a recommendation is
    the explicit act Section 16 requires before it can become an assertion."""
    if review_state not in ("accepted", "needs_review", "rejected"):
        raise RecorderError(400, "INVALID_REVIEW_STATE", "review_state must be accepted/needs_review/rejected.")

    checkpoint = await db.get(RecordingCheckpoint, checkpoint_id)
    if checkpoint is None or checkpoint.session_id != session.id:
        raise RecorderError(404, "CHECKPOINT_NOT_FOUND", "Checkpoint not found in this recording session.")

    checkpoint.review_state = review_state
    if expected_value is not None:
        checkpoint.expected_value = expected_value
    checkpoint.reviewed_by = user_id
    checkpoint.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(checkpoint)
    return checkpoint


async def delete_checkpoint(db: AsyncSession, session: DiscoverySession, *, checkpoint_id: int) -> None:
    checkpoint = await db.get(RecordingCheckpoint, checkpoint_id)
    if checkpoint is None or checkpoint.session_id != session.id:
        raise RecorderError(404, "CHECKPOINT_NOT_FOUND", "Checkpoint not found in this recording session.")
    await db.delete(checkpoint)
    await db.commit()


def _observed_url(action: DiscoveryAction) -> str | None:
    if action.action_family == "navigate":
        return (action.input_binding or {}).get("url")
    evidence = action.locator_evidence or {}
    return evidence.get("page_url")


async def generate_recommendations(
    db: AsyncSession, session: DiscoverySession, *, user_id: int
) -> list[RecordingCheckpoint]:
    """Called on Stop (Section 13). Proposes only grounded checkpoints, each
    with the reason shown to the reviewer. Idempotent: a recommendation whose
    (type, step, target) already exists is not duplicated, so re-stopping a
    resumed recording never piles up copies.
    """
    ctx = await recorder_context.load(db, session)
    existing = {(c.checkpoint_type, c.step_key, c.target) for c in ctx.checkpoints}
    mapping_by_action = ctx.mapping_by_action_id

    created: list[RecordingCheckpoint] = []

    for action in ctx.actions:
        if action.inclusion_state != "included" or action.action_family != "navigate":
            continue
        url = _observed_url(action)
        if not url:
            continue
        mapping = mapping_by_action.get(action.id)
        step_key = mapping.step_key if mapping else None
        key = ("url_matches", step_key, url)
        if key in existing:
            continue
        existing.add(key)
        checkpoint = RecordingCheckpoint(
            session_id=session.id,
            project_id=session.project_id,
            action_id=action.id,
            step_key=step_key,
            checkpoint_type="url_matches",
            target=url,
            expected_value=url,
            source="recommended",
            review_state="needs_review",
            recommendation_reason=(
                f"Action #{action.sequence} navigated to this URL and the page loaded. "
                "Accept to assert the destination; reject if the URL is not stable across runs."
            ),
            created_by=user_id,
        )
        db.add(checkpoint)
        created.append(checkpoint)

    console_capture_on = (session.capture_options or {}).get("console_capture", True)
    if console_capture_on and ("no_severe_console_errors", None, None) not in existing:
        checkpoint = RecordingCheckpoint(
            session_id=session.id,
            project_id=session.project_id,
            checkpoint_type="no_severe_console_errors",
            source="recommended",
            review_state="needs_review",
            recommendation_reason=(
                "Console output was captured for this recording, so the generated script can assert "
                "that no severe console errors occur. Accept to enforce it."
            ),
            created_by=user_id,
        )
        db.add(checkpoint)
        created.append(checkpoint)

    if created:
        await db.commit()
        for checkpoint in created:
            await db.refresh(checkpoint)
    return created
