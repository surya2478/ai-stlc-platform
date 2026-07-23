"""UI-015 Live Discovery Session — session CRUD, eligibility and command
issuance (Phase 1, Guided User Recording).

Every lifecycle-changing command is written here as one atomic transaction:
validate the transition (Section 9), append a `DiscoverySessionEvent`, and
either mutate `status` directly or leave a `pending_command` for the
dedicated Celery task to act on next step boundary (see discovery_tasks.py
and the plan's "Pause/resume design"). Idempotency is enforced by
`idempotency_key` scoped to the session: a repeated key with the same
command replays the already-recorded event instead of re-mutating state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.discovery_session import (
    DISCOVERY_SESSION_TRANSITIONS,
    DiscoverySession,
    DiscoverySessionEvent,
)
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase

# Commands only meaningful for Supervised Agent-Driven mode — accepted by the
# endpoint but explicitly refused in Phase 1 (Guided User Recording only),
# per CLAUDE.md rule 7: disabled with an explanation, never silently ignored.
_AGENT_DRIVEN_ONLY_COMMANDS = {"approve_next_action", "take_manual_control", "skip_action", "rollback"}

# Commands that request a state transition (validated against
# DISCOVERY_SESSION_TRANSITIONS). "checkpoint" is deliberately absent — it
# does not change session status, only appends a checkpoint at the next step
# boundary (or immediately, if the session isn't actively recording).
_COMMAND_TARGET_STATE = {
    "start": "INITIALISING",
    "pause": "PAUSE_REQUESTED",
    "resume": "RESUMING",
    "stop": "STOP_REQUESTED",
    "complete": "COMPLETED",
    "cancel": "CANCELLED",
    "emergency_stop": "EMERGENCY_STOPPED",
}


@dataclass
class EligibleTestCase:
    test_case_id: int
    display_id: str
    title: str
    requirement_ref: str | None
    scenario_ref: str | None
    approval_status: str
    eligible: bool
    blocking_reason: str | None


async def list_eligible_test_cases(
    db: AsyncSession, *, project_id: int, application_id: int, mode: str
) -> list[EligibleTestCase]:
    """Section 3.1 eligibility — every test case in the project, each marked
    eligible/blocked with the exact reason, never silently filtered out."""
    result = await db.execute(
        select(TestCase)
        .options(selectinload(TestCase.requirement), selectinload(TestCase.scenario))
        .where(TestCase.project_id == project_id, TestCase.is_deleted.is_(False))
    )
    rows: list[EligibleTestCase] = []
    for tc in result.scalars().all():
        blocking_reason = _eligibility_blocker(tc, application_id=application_id, mode=mode)
        rows.append(
            EligibleTestCase(
                test_case_id=tc.id,
                display_id=tc.test_case_id,
                title=tc.title,
                requirement_ref=tc.requirement.requirement_id if tc.requirement else None,
                scenario_ref=tc.scenario.scenario_id if tc.scenario else None,
                approval_status=tc.status,
                eligible=blocking_reason is None,
                blocking_reason=blocking_reason,
            )
        )
    return rows


def _eligibility_blocker(tc: TestCase, *, application_id: int, mode: str) -> str | None:
    if mode == "FREE_USER_ACTION":
        return None  # Free mode's test case is optional (Section 5.2) — nothing to block.
    if tc.status != "approved":
        return f"Test case is '{tc.status}', not approved through Test Case Approval."
    if tc.application_id is not None and tc.application_id != application_id:
        return "Test case is mapped to a different application than the one selected."
    if tc.application_id is None:
        return "Test case has no Application Registry mapping — map it in Test Case Approval first."
    return None


async def _load_test_case_context(db: AsyncSession, test_case_id: int) -> TestCase | None:
    result = await db.execute(
        select(TestCase)
        .options(selectinload(TestCase.requirement), selectinload(TestCase.scenario))
        .where(TestCase.id == test_case_id)
    )
    return result.scalar_one_or_none()


async def create_session(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    application_id: int,
    environment: str,
    mode: str,
    test_case_id: int | None,
    purpose: str | None,
    browser_target: str | None,
    framework: str,
    auth_profile_reference: str | None,
    capture_options: dict[str, Any] | None,
    evidence_policy: dict[str, Any] | None,
    allowed_hosts: list[str] | None,
    correlation_id: str | None,
) -> DiscoverySession:
    application = await db.get(ProjectApplication, application_id)
    if application is None or application.project_id != project_id:
        raise HTTPException(status_code=404, detail="Application not found in this project")
    if environment not in (application.environment_urls or {}):
        raise HTTPException(
            status_code=400,
            detail=f"Environment '{environment}' is not configured for application '{application.name}'",
        )

    if mode not in ("GUIDED_USER", "FREE_USER_ACTION", "SUPERVISED_AGENT_DRIVEN"):
        raise HTTPException(status_code=400, detail=f"Unknown discovery mode '{mode}'")
    if mode == "FREE_USER_ACTION" and not (purpose or "").strip():
        raise HTTPException(status_code=400, detail="Free User-Action Recording requires a recorded session purpose")

    test_case: TestCase | None = None
    if test_case_id is not None:
        test_case = await _load_test_case_context(db, test_case_id)
        if test_case is None or test_case.project_id != project_id:
            raise HTTPException(status_code=404, detail="Test case not found in this project")
        blocker = _eligibility_blocker(test_case, application_id=application_id, mode=mode)
        if blocker is not None:
            raise HTTPException(status_code=409, detail={"code": "TEST_CASE_NOT_ELIGIBLE", "message": blocker})
    elif mode in ("GUIDED_USER", "SUPERVISED_AGENT_DRIVEN"):
        raise HTTPException(
            status_code=400,
            detail=f"{mode} requires one approved, application-mapped, discovery-eligible test case",
        )

    host = None
    from urllib.parse import urlparse

    host = urlparse(application.environment_urls[environment]).hostname
    resolved_allowed_hosts = list(dict.fromkeys((allowed_hosts or []) + ([host] if host else [])))

    session = DiscoverySession(
        project_id=project_id,
        application_id=application_id,
        environment=environment,
        mode=mode,
        status="NOT_STARTED",
        browser_target=browser_target,
        framework=framework or "playwright",
        auth_profile_reference=auth_profile_reference,
        test_case_id=test_case.id if test_case else None,
        test_case_version=test_case.version if test_case else None,
        requirement_ref=test_case.requirement.requirement_id if (test_case and test_case.requirement) else None,
        journey_ref=None,
        scenario_ref=test_case.scenario.scenario_id if (test_case and test_case.scenario) else None,
        purpose=purpose,
        evidence_policy=evidence_policy or {},
        capture_options=capture_options or {},
        allowed_hosts=resolved_allowed_hosts,
        owner_id=user_id,
        created_by=user_id,
        correlation_id=correlation_id,
    )
    db.add(session)
    await db.flush()
    await _record_event(
        db, session, actor_id=user_id, actor_type="user", previous_state=None, new_state="NOT_STARTED",
        command="create", reason="Session created",
    )
    await db.commit()
    await db.refresh(session)
    return session


async def get_session_or_404(db: AsyncSession, session_id: int) -> DiscoverySession:
    session = await db.get(DiscoverySession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Discovery session not found")
    return session


async def list_sessions(
    db: AsyncSession, *, project_id: int, application_id: int | None = None, status_filter: str | None = None
) -> list[DiscoverySession]:
    query = select(DiscoverySession).where(DiscoverySession.project_id == project_id)
    if application_id is not None:
        query = query.where(DiscoverySession.application_id == application_id)
    if status_filter is not None:
        query = query.where(DiscoverySession.status == status_filter)
    result = await db.execute(query.order_by(DiscoverySession.created_at.desc()))
    return list(result.scalars().all())


async def _record_event(
    db: AsyncSession,
    session: DiscoverySession,
    *,
    actor_id: int | None,
    actor_type: str,
    previous_state: str | None,
    new_state: str,
    command: str | None,
    reason: str | None = None,
    idempotency_key: str | None = None,
    checkpoint_id: int | None = None,
) -> DiscoverySessionEvent:
    event = DiscoverySessionEvent(
        session_id=session.id,
        project_id=session.project_id,
        actor_id=actor_id,
        actor_type=actor_type,
        previous_state=previous_state,
        new_state=new_state,
        command=command,
        reason=reason,
        checkpoint_id=checkpoint_id,
        idempotency_key=idempotency_key,
        correlation_id=session.correlation_id,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)
    await db.flush()
    return event


async def _find_by_idempotency_key(db: AsyncSession, session_id: int, idempotency_key: str) -> DiscoverySessionEvent | None:
    result = await db.execute(
        select(DiscoverySessionEvent).where(
            DiscoverySessionEvent.session_id == session_id,
            DiscoverySessionEvent.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def issue_command(
    db: AsyncSession,
    session: DiscoverySession,
    *,
    command: str,
    user_id: int,
    idempotency_key: str,
    reason: str | None = None,
    params: dict[str, Any] | None = None,
) -> DiscoverySession:
    """Validate + apply one session command. Returns the session unchanged
    (idempotent replay) if `idempotency_key` was already recorded."""
    existing = await _find_by_idempotency_key(db, session.id, idempotency_key)
    if existing is not None:
        return session  # idempotent replay — no re-mutation

    if command in _AGENT_DRIVEN_ONLY_COMMANDS:
        raise HTTPException(
            status_code=400,
            detail=f"'{command}' is only available in Supervised Agent-Driven mode, "
                   "which is not implemented in Phase 1 (Guided User Recording only).",
        )

    # A live task is looping (and will notice `pending_command` on its next
    # iteration) whenever the session is RECORDING, or in one of the states
    # only a live task can produce as an intermediate step on its way there
    # or away from it (INITIALISING/RESUMING just before it flips to
    # RECORDING; PAUSE_REQUESTED/STOP_REQUESTED — with this fix — only ever
    # set by a command issued while RECORDING, so the same task that was
    # looping is still mid-iteration and will see the newest pending_command
    # next). PAUSED is the only state with no task attached — the task
    # closed its MCPSession and exited before setting it (see
    # discovery_tasks.py). Checkpoint/stop issued from PAUSED must finalize
    # synchronously here instead of writing a command nobody will ever read.
    has_live_task = session.status in (
        "RECORDING", "INITIALISING", "RESUMING", "PAUSE_REQUESTED", "STOP_REQUESTED",
    )

    if command == "checkpoint":
        if session.status not in ("RECORDING", "PAUSED"):
            raise HTTPException(status_code=409, detail=f"Cannot checkpoint a session in state '{session.status}'")
        if has_live_task:
            session.pending_command = {
                "command": "checkpoint", "idempotency_key": idempotency_key, "issued_by": user_id,
                "issued_at": datetime.now(timezone.utc).isoformat(), "reason": reason, "params": params or {},
            }
        else:
            from app.services.discovery import capture_service

            await capture_service.create_checkpoint(db, session, state_at_checkpoint=session.status)
        await _record_event(
            db, session, actor_id=user_id, actor_type="user", previous_state=session.status,
            new_state=session.status, command=command, reason=reason, idempotency_key=idempotency_key,
        )
        await db.commit()
        await db.refresh(session)
        return session

    target_state = _COMMAND_TARGET_STATE.get(command)
    if target_state is None:
        raise HTTPException(status_code=400, detail=f"Unknown command '{command}'")

    allowed = DISCOVERY_SESSION_TRANSITIONS.get(session.status, ())
    if target_state not in allowed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INVALID_TRANSITION",
                "message": f"Cannot '{command}' a session in state '{session.status}'",
                "current_state": session.status,
            },
        )

    previous_state = session.status
    session.last_command_idempotency_key = idempotency_key
    if command == "start":
        session.started_at = datetime.now(timezone.utc)

    if command == "stop" and not has_live_task:
        # "stop"'s target_state (STOP_REQUESTED) is an intermediate state
        # only a live task can finalize into STOPPED. With no live task (the
        # only reachable case is PAUSED), there is no browser subprocess to
        # close either (PAUSED already closed it) — finalize straight to
        # STOPPED here instead of stranding STOP_REQUESTED forever.
        from app.services.discovery import capture_service

        await capture_service.create_checkpoint(db, session, state_at_checkpoint="STOPPED", resumable=True)
        session.status = "STOPPED"
        session.pending_command = None
    else:
        # "emergency_stop"'s target_state (EMERGENCY_STOPPED) is already
        # terminal regardless of a live task — set it directly. If a task IS
        # still looping it will independently notice pending_command, best-
        # effort persist its own checkpoint, and reach the same state.
        session.status = target_state
        session.pending_command = {
            "command": command, "idempotency_key": idempotency_key, "issued_by": user_id,
            "issued_at": datetime.now(timezone.utc).isoformat(), "reason": reason, "params": params or {},
        }

    if session.status in ("COMPLETED", "CANCELLED", "FAILED", "EMERGENCY_STOPPED"):
        session.terminal_at = datetime.now(timezone.utc)
        session.terminal_reason = reason

    await _record_event(
        db, session, actor_id=user_id, actor_type="user", previous_state=previous_state, new_state=session.status,
        command=command, reason=reason, idempotency_key=idempotency_key,
    )
    await db.commit()
    await db.refresh(session)
    return session


async def record_free_action(
    db: AsyncSession,
    session: DiscoverySession,
    *,
    user_id: int,
    idempotency_key: str,
    action_family: str,
    target_ref: str | None = None,
    target_semantic: str | None = None,
    input_text: str | None = None,
    url: str | None = None,
) -> DiscoverySession:
    """Queue one Free User-Action Recording action (Section 5.2) for the
    live capture task to perform on its next poll tick. Unlike lifecycle
    commands this never transitions session status — the resulting
    DiscoveryAction, once the task actually performs it, is itself the
    audit record.
    """
    if session.mode != "FREE_USER_ACTION":
        raise HTTPException(
            status_code=400,
            detail="Recording ad-hoc actions is only supported in Free User-Action Recording mode",
        )
    if session.status != "RECORDING":
        raise HTTPException(
            status_code=409,
            detail=f"Session must be RECORDING to record an action (currently '{session.status}') — Start or Resume it first",
        )

    pending = session.pending_command or {}
    if pending.get("command") == "perform_action" and pending.get("idempotency_key") == idempotency_key:
        return session  # already queued — idempotent replay, not a second action

    session.pending_command = {
        "command": "perform_action",
        "idempotency_key": idempotency_key,
        "issued_by": user_id,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "params": {
            "action_family": action_family,
            "target_ref": target_ref,
            "target_semantic": target_semantic,
            "input_text": input_text,
            "url": url,
        },
    }
    await db.commit()
    await db.refresh(session)
    return session
