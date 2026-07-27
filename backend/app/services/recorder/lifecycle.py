"""Recording lifecycle orchestration — stop finalization, summary assembly,
IR emission and discard (Contract Sections 13, 21, 22).

This is the async layer that stitches the pure modules to the database and to
the two services that already own their domains: UI-015's capture engine and
UI-017's network-event parser. Nothing here re-implements either.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_session import DiscoveryCapture, DiscoverySession, DiscoverySessionEvent
from app.models.network_event import NetworkEvent
from app.models.recording_session import AutomationIrDraft
from app.services import network_event_service
from app.services.recorder import checkpoints as recorder_checkpoints
from app.services.recorder import context as recorder_context
from app.services.recorder import ir_emitter
from app.services.recorder import segments as recorder_segments
from app.services.recorder import summary as recorder_summary
from app.services.recorder.errors import RecorderError

logger = logging.getLogger(__name__)

# Section 14 — a recording has produced its final action set in these states,
# which is what makes a summary and an IR draft meaningful.
CAPTURED_STATES = ("STOPPED", "PAUSED", "COMPLETED")


async def _read_console_text(db: AsyncSession, session: DiscoverySession) -> str | None:
    """Concatenates this recording's console captures. Uses the same
    managed-workspace containment check every other reader uses — a capture
    row pointing outside the workspace root is skipped, never read."""
    from app.services.discovery.capture_service import discovery_workspace_root

    result = await db.execute(
        select(DiscoveryCapture).where(
            DiscoveryCapture.session_id == session.id, DiscoveryCapture.capture_type == "console_log"
        )
    )
    captures = list(result.scalars().all())
    if not captures:
        return None

    storage_root = os.path.realpath(discovery_workspace_root())
    chunks: list[str] = []
    for capture in captures:
        real_path = os.path.realpath(capture.storage_path)
        if not (real_path.startswith(storage_root + os.sep) or real_path == storage_root):
            continue
        if not os.path.exists(real_path):
            continue
        try:
            with open(real_path, "r", encoding="utf-8") as handle:
                chunks.append(handle.read())
        except OSError:
            logger.warning("recorder: could not read console capture %s", capture.id, exc_info=True)
    return "\n".join(chunks) if chunks else None


async def _network_stats(db: AsyncSession, session: DiscoverySession) -> dict | None:
    """Network figures from UI-017's parsed events. Returns None when nothing
    has been parsed, so the summary says "not parsed" rather than "zero"."""
    result = await db.execute(select(NetworkEvent).where(NetworkEvent.session_id == session.id))
    events = list(result.scalars().all())
    if not events:
        return None
    failed = sum(1 for e in events if e.status_code is not None and e.status_code >= 400)
    return {"total": len(events), "failed": failed}


async def build_summary(db: AsyncSession, session: DiscoverySession) -> dict:
    context = await recorder_context.load(db, session)
    console_text = await _read_console_text(db, session)
    return recorder_summary.build(
        context,
        console_stats=recorder_summary.parse_console_text(console_text) if console_text is not None else None,
        network_stats=await _network_stats(db, session),
    )


async def finalize_stop(db: AsyncSession, session: DiscoverySession, *, user_id: int) -> dict:
    """Section 13's Stop post-processing. Runs after the capture worker has
    already closed the browser and moved the session to STOPPED.

    Idempotent: closing an already-closed segment is a no-op, recommendations
    de-duplicate by (type, step, target), and re-parsing network events
    rebuilds them from the same capture files.
    """
    await recorder_segments.close_open_segment(db, session)

    # UI-017 owns network parsing. A failure here must not lose the recording,
    # so it degrades to "not parsed" in the summary rather than raising.
    try:
        await network_event_service.build_or_rebuild(
            db, project_id=session.project_id, session_id=session.id, actor_id=user_id
        )
    except Exception:
        logger.warning("recorder: network event parse failed for session %s", session.id, exc_info=True)

    await recorder_checkpoints.generate_recommendations(db, session, user_id=user_id)

    db.add(
        DiscoverySessionEvent(
            session_id=session.id,
            project_id=session.project_id,
            actor_id=user_id,
            actor_type="system",
            previous_state=session.status,
            new_state=session.status,
            command="recording_finalized",
            reason="Segments closed, network events parsed, checkpoint recommendations generated.",
            correlation_id=session.correlation_id,
            occurred_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
    return await build_summary(db, session)


async def emit_ir_draft(db: AsyncSession, session: DiscoverySession, *, user_id: int) -> AutomationIrDraft:
    """Section 22 — Save and Continue to Automation IR.

    Supersedes rather than overwrites: the previous draft stays readable and
    keeps its own source action ids, so a reviewer can always see what an
    earlier emission produced.
    """
    if session.status not in CAPTURED_STATES:
        raise RecorderError(
            409,
            "RECORDING_NOT_CAPTURED",
            f"An Automation IR draft can only be emitted from a captured recording. This one is "
            f"'{session.status}' — stop or pause it first.",
            current_state=session.status,
        )
    if session.test_case_id is None:
        raise RecorderError(
            409, "NO_TEST_CASE", "This recording has no test case, so there is nothing to emit an IR for."
        )

    context = await recorder_context.load(db, session)
    if not context.actions:
        raise RecorderError(
            409,
            "NOTHING_RECORDED",
            "No actions were recorded in this session, so there is nothing to convert to an Automation IR.",
        )

    result = ir_emitter.build(context)

    previous = await db.execute(
        select(AutomationIrDraft).where(
            AutomationIrDraft.session_id == session.id, AutomationIrDraft.is_current.is_(True)
        )
    )
    next_version = 1
    for draft in previous.scalars().all():
        draft.is_current = False
        draft.status = "SUPERSEDED"
        next_version = max(next_version, draft.version + 1)

    draft = AutomationIrDraft(
        project_id=session.project_id,
        session_id=session.id,
        suite_id=session.suite_id,
        test_case_id=session.test_case_id,
        version=next_version,
        is_current=True,
        status="DRAFT",
        contract=result.contract.model_dump(by_alias=True, mode="json"),
        contract_version=result.contract.contract_version,
        source_action_ids=result.source_action_ids,
        readiness=result.readiness,
        generated_by=user_id,
    )
    db.add(draft)

    session.ir_status = "DRAFT"
    db.add(
        DiscoverySessionEvent(
            session_id=session.id,
            project_id=session.project_id,
            actor_id=user_id,
            actor_type="user",
            previous_state=session.status,
            new_state=session.status,
            command="ir_generated",
            reason=f"Automation IR draft v{next_version} — {result.readiness['step_count']} step(s), "
                   f"{result.readiness['assertion_count']} assertion(s), "
                   f"{result.readiness['unresolved_count']} open item(s).",
            correlation_id=session.correlation_id,
            occurred_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
    await db.refresh(draft)
    return draft


async def get_current_ir_draft(db: AsyncSession, session: DiscoverySession) -> AutomationIrDraft | None:
    result = await db.execute(
        select(AutomationIrDraft)
        .where(AutomationIrDraft.session_id == session.id, AutomationIrDraft.is_current.is_(True))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def discard(db: AsyncSession, session: DiscoverySession, *, user_id: int, reason: str) -> DiscoverySession:
    """Section 13's Discard. Requires a reason once capture has begun, and is
    audited. The captured rows are *not* deleted — the recording is marked
    cancelled so the discard itself remains reviewable, which is what Section
    25's audit requirement means in practice."""
    if not (reason or "").strip():
        raise RecorderError(400, "DISCARD_REASON_REQUIRED", "Discarding a recording requires a reason.")
    if session.status in ("COMPLETED", "CANCELLED", "EMERGENCY_STOPPED"):
        raise RecorderError(
            409,
            "ALREADY_FINAL",
            f"This recording is already '{session.status}' and cannot be discarded again.",
            current_state=session.status,
        )

    previous_state = session.status
    session.status = "CANCELLED"
    session.terminal_at = datetime.now(timezone.utc)
    session.terminal_reason = reason
    session.pending_command = None
    db.add(
        DiscoverySessionEvent(
            session_id=session.id,
            project_id=session.project_id,
            actor_id=user_id,
            actor_type="user",
            previous_state=previous_state,
            new_state="CANCELLED",
            command="discard_recording",
            reason=reason,
            correlation_id=session.correlation_id,
            occurred_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
    await db.refresh(session)
    return session
