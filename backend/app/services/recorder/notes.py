"""Recording notes (Contract Section 12.6).

A note attaches to the session, a step, an action, a checkpoint or a segment.
Notes are additive observations by a person — they never change the recording
or the IR, which is exactly why they are safe to write at any point in the
session lifecycle, including after it has finalized.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_session import DiscoveryAction, DiscoverySession
from app.models.recording_session import NOTE_SCOPES, RecordingCheckpoint, RecordingNote, RecordingSegment
from app.services.recorder.errors import RecorderError


async def list_notes(db: AsyncSession, session: DiscoverySession) -> list[RecordingNote]:
    result = await db.execute(
        select(RecordingNote).where(RecordingNote.session_id == session.id).order_by(RecordingNote.id)
    )
    return list(result.scalars().all())


async def create_note(
    db: AsyncSession,
    session: DiscoverySession,
    *,
    user_id: int,
    body: str,
    scope: str = "session",
    step_key: str | None = None,
    action_id: int | None = None,
    checkpoint_id: int | None = None,
    segment_id: int | None = None,
) -> RecordingNote:
    if scope not in NOTE_SCOPES:
        raise RecorderError(400, "INVALID_NOTE_SCOPE", f"scope must be one of {list(NOTE_SCOPES)}.")
    if not (body or "").strip():
        raise RecorderError(400, "NOTE_BODY_REQUIRED", "A note needs a body.")

    # A scoped note whose target does not exist would be orphaned the moment
    # it was written, so the target is verified rather than assumed.
    if scope == "step" and not step_key:
        raise RecorderError(400, "STEP_KEY_REQUIRED", "A step-scoped note must name the step.")
    if scope == "action":
        action = await db.get(DiscoveryAction, action_id) if action_id else None
        if action is None or action.session_id != session.id:
            raise RecorderError(404, "ACTION_NOT_FOUND", "Action not found in this recording session.")
    if scope == "checkpoint":
        checkpoint = await db.get(RecordingCheckpoint, checkpoint_id) if checkpoint_id else None
        if checkpoint is None or checkpoint.session_id != session.id:
            raise RecorderError(404, "CHECKPOINT_NOT_FOUND", "Checkpoint not found in this recording session.")
    if scope == "segment":
        segment = await db.get(RecordingSegment, segment_id) if segment_id else None
        if segment is None or segment.session_id != session.id:
            raise RecorderError(404, "SEGMENT_NOT_FOUND", "Segment not found in this recording session.")

    note = RecordingNote(
        session_id=session.id,
        project_id=session.project_id,
        scope=scope,
        step_key=step_key,
        action_id=action_id,
        checkpoint_id=checkpoint_id,
        segment_id=segment_id,
        body=body.strip(),
        created_by=user_id,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def delete_note(db: AsyncSession, session: DiscoverySession, *, note_id: int) -> None:
    note = await db.get(RecordingNote, note_id)
    if note is None or note.session_id != session.id:
        raise RecorderError(404, "NOTE_NOT_FOUND", "Note not found in this recording session.")
    await db.delete(note)
    await db.commit()
