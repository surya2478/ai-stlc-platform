"""Multi-application recording segments (Contract Section 17).

One recording session, several applications. A segment records which
application/environment/adapter a stretch of the action timeline ran against,
so a CRM → OMS → Billing journey stays one recording with one runtime data
flow rather than three disconnected ones.

Segment 1 is opened implicitly when recording starts, against the session's
own inherited application. Every later segment is an explicit user transition
with a stated reason — the recorder never infers that an application changed,
because a URL moving to a different host can equally be an SSO redirect.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_session import DiscoveryAction, DiscoverySession, DiscoverySessionEvent
from app.models.project_application import ProjectApplication
from app.models.recording_session import RecordingSegment
from app.services.recorder.errors import RecorderError


async def list_segments(db: AsyncSession, session: DiscoverySession) -> list[RecordingSegment]:
    result = await db.execute(
        select(RecordingSegment)
        .where(RecordingSegment.session_id == session.id)
        .order_by(RecordingSegment.sequence)
    )
    return list(result.scalars().all())


async def open_segment(db: AsyncSession, session: DiscoverySession) -> RecordingSegment | None:
    result = await db.execute(
        select(RecordingSegment)
        .where(RecordingSegment.session_id == session.id, RecordingSegment.ended_at.is_(None))
        .order_by(RecordingSegment.sequence.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _next_action_sequence(db: AsyncSession, session: DiscoverySession) -> int | None:
    result = await db.execute(
        select(DiscoveryAction.sequence)
        .where(DiscoveryAction.session_id == session.id)
        .order_by(DiscoveryAction.sequence.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    return (latest + 1) if latest is not None else 0


async def ensure_initial_segment(
    db: AsyncSession, session: DiscoverySession, *, user_id: int | None = None
) -> RecordingSegment:
    """Opens segment 1 against the session's inherited application if the
    recording has no segment yet. Safe to call repeatedly."""
    existing = await open_segment(db, session)
    if existing is not None:
        return existing

    result = await db.execute(
        select(RecordingSegment)
        .where(RecordingSegment.session_id == session.id)
        .order_by(RecordingSegment.sequence.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if last is not None:
        # Every segment is closed and the caller wants an open one — that only
        # happens on resume, so continue the journey in a new segment against
        # the same application rather than reopening a closed one.
        return await _create(
            db,
            session,
            sequence=last.sequence + 1,
            application_id=last.application_id,
            environment=last.environment,
            framework=last.framework,
            transition_reason="Recording resumed",
            user_id=user_id,
        )

    return await _create(
        db,
        session,
        sequence=1,
        application_id=session.application_id,
        environment=session.environment,
        framework=session.framework,
        transition_reason=None,
        user_id=user_id,
    )


async def _create(
    db: AsyncSession,
    session: DiscoverySession,
    *,
    sequence: int,
    application_id: int,
    environment: str,
    framework: str | None,
    transition_reason: str | None,
    user_id: int | None,
) -> RecordingSegment:
    segment = RecordingSegment(
        session_id=session.id,
        project_id=session.project_id,
        sequence=sequence,
        application_id=application_id,
        environment=environment,
        framework=framework,
        adapter="playwright_mcp",
        started_at=datetime.now(timezone.utc),
        start_action_sequence=await _next_action_sequence(db, session),
        transition_reason=transition_reason,
        created_by=user_id,
    )
    db.add(segment)
    await db.commit()
    await db.refresh(segment)
    return segment


async def transition(
    db: AsyncSession,
    session: DiscoverySession,
    *,
    application_id: int,
    environment: str,
    transition_reason: str,
    user_id: int,
) -> RecordingSegment:
    """Closes the open segment and opens the next one against a different
    application (Section 17). The new application's host is added to the
    session's allowed hosts, because navigation to it would otherwise be
    refused by the same security boundary that protects every other session."""
    if not (transition_reason or "").strip():
        raise RecorderError(
            400,
            "TRANSITION_REASON_REQUIRED",
            "Moving to another application requires a stated reason — it becomes part of the journey record.",
        )

    application = await db.get(ProjectApplication, application_id)
    if application is None or application.project_id != session.project_id:
        raise RecorderError(404, "APPLICATION_NOT_FOUND", "Application not found in this project.")
    environment_urls = application.environment_urls or {}
    if environment not in environment_urls:
        raise RecorderError(
            409,
            "ENVIRONMENT_URL_MISSING",
            f"Environment '{environment}' has no URL configured for application '{application.name}'.",
        )

    current = await open_segment(db, session)
    if current is not None:
        current.ended_at = datetime.now(timezone.utc)
        latest_sequence = await _next_action_sequence(db, session)
        current.end_action_sequence = (latest_sequence - 1) if latest_sequence else None
        await db.flush()

    from urllib.parse import urlparse

    host = urlparse(environment_urls[environment]).hostname
    if host and host not in (session.allowed_hosts or []):
        session.allowed_hosts = [*(session.allowed_hosts or []), host]

    db.add(
        DiscoverySessionEvent(
            session_id=session.id,
            project_id=session.project_id,
            actor_id=user_id,
            actor_type="user",
            previous_state=session.status,
            new_state=session.status,
            command="segment_transition",
            reason=f"To '{application.name}' ({environment}): {transition_reason}",
            correlation_id=session.correlation_id,
            occurred_at=datetime.now(timezone.utc),
        )
    )

    next_sequence = (current.sequence + 1) if current is not None else 1
    return await _create(
        db,
        session,
        sequence=next_sequence,
        application_id=application_id,
        environment=environment,
        framework=session.framework,
        transition_reason=transition_reason,
        user_id=user_id,
    )


async def close_open_segment(db: AsyncSession, session: DiscoverySession) -> None:
    """Called when a recording stops — the last segment gets an end time and
    action boundary so the timeline has no open-ended stretch."""
    current = await open_segment(db, session)
    if current is None:
        return
    current.ended_at = datetime.now(timezone.utc)
    latest_sequence = await _next_action_sequence(db, session)
    current.end_action_sequence = (latest_sequence - 1) if latest_sequence else None
    await db.commit()
