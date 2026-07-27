"""Live Recorder session creation, inherited context and lifecycle.

A Live Recorder session *is* a `DiscoverySession` — see the module docstring
of `app.models.recording_session` for why. This module owns the part UI-015
has no concept of: resolving what the session inherits from its Automation
Test Suite member (Section 4), refusing to let a user re-enter any of it
(Section 3), and the Section 25 version chain.

The transport mode is always `FREE_USER_ACTION`, because a Live Recorder run
is user-driven: the person chooses every action and the platform performs and
observes it. UI-015's `GUIDED_USER` mode means something different — an agent
auto-walking an approved step list — and reusing that name here would have
made the recorder do the one thing the contract forbids, which is generate
automation from behaviour nobody performed. Section 7's Guided/Exploratory
distinction is carried by `recording_mode` instead.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.automation_suite import AutomationSuite, AutomationSuiteTestCase
from app.models.automation_script import AutomationScript
from app.models.discovery_session import DiscoverySession, DiscoverySessionEvent
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.services.automation_suite import inheritance
from app.services.recorder.errors import RecorderError

RECORDING_MODES = ("GUIDED_TEST_CASE", "EXPLORATORY")

# A recording in one of these states has produced everything it is going to
# produce; Section 5 forbids editing it further. A new version is the way
# forward (see `create_version`).
FINALIZED_STATES = ("COMPLETED", "CANCELLED", "EMERGENCY_STOPPED")


async def _resolve_member_context(
    db: AsyncSession, *, suite: AutomationSuite, test_case_id: int
) -> tuple[AutomationSuiteTestCase, inheritance.MemberInheritance]:
    """What the member inherits, resolved against the authoritative sources —
    never copied into the session and never asked of the user (Section 4)."""
    result = await db.execute(
        select(AutomationSuiteTestCase).where(
            AutomationSuiteTestCase.suite_id == suite.id,
            AutomationSuiteTestCase.test_case_id == test_case_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise RecorderError(
            404,
            "TEST_CASE_NOT_IN_SUITE",
            "That test case is not a member of this Automation Test Suite. Add it in the Automation "
            "Workspace before recording against it.",
        )

    resolved = await inheritance.resolve_suite_inheritance(db, suite=suite, members=[member])
    if not resolved.members:
        raise RecorderError(
            409, "INHERITANCE_UNRESOLVED", "The suite member's inherited context could not be resolved."
        )
    return member, resolved.members[0]


async def build_inherited_context(db: AsyncSession, session: DiscoverySession) -> dict:
    """The header and left-panel context (Sections 9, 10.1), read-only.

    Every value here is resolved live from its owning entity on each call, so
    a correction made in the Test Case, Application Registry or suite shows up
    without the recording having to be recreated.
    """
    test_case = await db.get(TestCase, session.test_case_id) if session.test_case_id else None
    suite = await db.get(AutomationSuite, session.suite_id) if session.suite_id else None
    application = await db.get(ProjectApplication, session.application_id)

    member_inheritance = None
    if suite is not None and session.test_case_id is not None:
        try:
            _, member_inheritance = await _resolve_member_context(
                db, suite=suite, test_case_id=session.test_case_id
            )
        except RecorderError:
            # The member was removed from the suite after the recording
            # started. The recording remains readable; the precondition gate
            # is what refuses to let it continue.
            member_inheritance = None

    scripts = member_inheritance.current_scripts if member_inheritance else []
    primary_script: AutomationScript | None = scripts[0] if scripts else None

    return {
        "suite": None
        if suite is None
        else {"id": suite.id, "name": suite.name, "version": suite.version, "status": suite.status},
        "test_case": None
        if test_case is None
        else {
            "id": test_case.id,
            "display_id": test_case.test_case_id,
            "title": test_case.title,
            "objective": test_case.test_case_objective,
            "test_type": test_case.test_type,
            "priority": test_case.priority,
            "is_critical": test_case.is_critical,
            "status": test_case.status,
            "version": test_case.version,
            "automation_status": test_case.automation_status,
            "preconditions": test_case.preconditions,
        },
        "application": None
        if application is None
        else {"id": application.id, "name": application.name, "type": application.application_type},
        "environment": session.environment,
        "framework": session.framework,
        "recording_mode": session.recording_mode,
        "requirement_ref": session.requirement_ref,
        "scenario_ref": session.scenario_ref,
        "test_data": [
            {"id": td.id, "name": td.name, "status": td.status}
            for td in (member_inheritance.test_data if member_inheritance else [])
        ],
        # Section 23 — existing automation assets, so a published one is never
        # silently overwritten.
        "existing_script": None
        if primary_script is None
        else {
            "id": primary_script.id,
            "framework": primary_script.framework,
            "status": primary_script.status,
            "version": primary_script.version,
        },
        "application_model": None
        if member_inheritance is None or member_inheritance.model is None
        else {
            "id": member_inheritance.model.id,
            "version": member_inheritance.model.version,
            "is_stale": member_inheritance.model_is_stale,
        },
    }


async def create_session(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    suite_id: int,
    test_case_id: int,
    recording_mode: str,
    environment: str | None = None,
    correlation_id: str | None = None,
    parent_recording_id: int | None = None,
) -> DiscoverySession:
    """Opens a Live Recorder session for one suite member.

    Application, framework, environment and traceability are resolved from the
    member — none of them are parameters a caller can override, which is what
    makes Section 4's "corrections must be made in the authoritative source"
    true rather than merely stated.
    """
    if recording_mode not in RECORDING_MODES:
        raise RecorderError(
            400, "INVALID_RECORDING_MODE", f"recording_mode must be one of {list(RECORDING_MODES)}."
        )

    suite = await db.get(AutomationSuite, suite_id)
    if suite is None or suite.project_id != project_id:
        raise RecorderError(404, "SUITE_NOT_FOUND", "Automation Test Suite not found in this project.")

    # Eager-load the traceability relationships: touching them lazily on an
    # AsyncSession raises MissingGreenlet rather than emitting a query.
    tc_result = await db.execute(
        select(TestCase)
        .options(selectinload(TestCase.requirement), selectinload(TestCase.scenario))
        .where(TestCase.id == test_case_id)
    )
    test_case = tc_result.scalar_one_or_none()
    if test_case is None or test_case.project_id != project_id:
        raise RecorderError(404, "TEST_CASE_NOT_FOUND", "Test case not found in this project.")

    member, resolved = await _resolve_member_context(db, suite=suite, test_case_id=test_case_id)

    application = resolved.application
    if application is None:
        raise RecorderError(
            409,
            "APPLICATION_UNRESOLVED",
            "This test case has no application mapping. Map it in the Application Registry — the Live "
            "Recorder will not ask you to re-enter it here (Section 6).",
        )

    resolved_environment = environment or resolved.resolved_environment
    if not resolved_environment:
        raise RecorderError(
            409,
            "ENVIRONMENT_UNRESOLVED",
            "No environment is inherited for this member and the suite has no default environment. "
            "Set one on the suite in the Automation Workspace.",
        )
    if resolved_environment not in (application.environment_urls or {}):
        raise RecorderError(
            409,
            "ENVIRONMENT_URL_MISSING",
            f"Environment '{resolved_environment}' has no URL configured for application "
            f"'{application.name}'. Configure it in the Application Registry.",
        )

    framework = next(iter(sorted(resolved.frameworks)), None) or "playwright"

    host = urlparse(application.environment_urls[resolved_environment]).hostname
    session = DiscoverySession(
        project_id=project_id,
        application_id=application.id,
        environment=resolved_environment,
        # See the module docstring: user-driven transport, always.
        mode="FREE_USER_ACTION",
        status="NOT_STARTED",
        framework=framework,
        test_case_id=test_case.id,
        test_case_version=test_case.version,
        requirement_ref=test_case.requirement.requirement_id if test_case.requirement else None,
        scenario_ref=test_case.scenario.scenario_id if test_case.scenario else None,
        # Free mode requires a stated purpose. This is a factual description of
        # why the session exists, not invented content.
        purpose=(
            f"Live Recorder — {recording_mode.replace('_', ' ').title()} for "
            f"{test_case.test_case_id} in suite '{suite.name}' v{suite.version}"
        ),
        allowed_hosts=[host] if host else [],
        owner_id=user_id,
        created_by=user_id,
        correlation_id=correlation_id,
        recording_origin="live_recorder",
        suite_id=suite.id,
        suite_member_id=member.id,
        recording_mode=recording_mode,
        ir_status="NOT_GENERATED",
        recording_version=1,
        parent_recording_id=parent_recording_id,
    )

    if parent_recording_id is not None:
        parent = await db.get(DiscoverySession, parent_recording_id)
        if parent is None or parent.project_id != project_id:
            raise RecorderError(404, "PARENT_RECORDING_NOT_FOUND", "The recording to version was not found.")
        session.recording_version = parent.recording_version + 1

    db.add(session)
    await db.flush()
    db.add(
        DiscoverySessionEvent(
            session_id=session.id,
            project_id=project_id,
            actor_id=user_id,
            actor_type="user",
            previous_state=None,
            new_state="NOT_STARTED",
            command="create_recording",
            reason=f"Live Recorder session v{session.recording_version} created",
            correlation_id=correlation_id,
            occurred_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
    await db.refresh(session)
    return session


async def get_recording_or_404(db: AsyncSession, session_id: int) -> DiscoverySession:
    session = await db.get(DiscoverySession, session_id)
    if session is None:
        raise RecorderError(404, "RECORDING_NOT_FOUND", "Recording session not found.")
    if session.recording_origin != "live_recorder":
        raise RecorderError(
            404,
            "NOT_A_RECORDING",
            f"Session #{session_id} is a Live Discovery session, not a Live Recorder recording. "
            "Open it from Live Discovery instead.",
        )
    return session


async def list_recordings(
    db: AsyncSession,
    *,
    project_id: int,
    suite_id: int | None = None,
    test_case_id: int | None = None,
    status: str | None = None,
) -> list[DiscoverySession]:
    query = select(DiscoverySession).where(
        DiscoverySession.project_id == project_id,
        DiscoverySession.recording_origin == "live_recorder",
    )
    if suite_id is not None:
        query = query.where(DiscoverySession.suite_id == suite_id)
    if test_case_id is not None:
        query = query.where(DiscoverySession.test_case_id == test_case_id)
    if status is not None:
        query = query.where(DiscoverySession.status == status)
    result = await db.execute(query.order_by(DiscoverySession.created_at.desc()))
    return list(result.scalars().all())


async def create_version(
    db: AsyncSession, session: DiscoverySession, *, user_id: int, reason: str
) -> DiscoverySession:
    """Section 25 — a finalized recording is never edited; a new version is
    chained off it and starts empty. Section 23's "Create New Recording
    Version" resolves to this."""
    if session.suite_id is None or session.test_case_id is None:
        raise RecorderError(
            409, "RECORDING_NOT_VERSIONABLE", "This recording has no suite/test case to version against."
        )
    if not (reason or "").strip():
        raise RecorderError(400, "VERSION_REASON_REQUIRED", "Creating a new recording version requires a reason.")

    new_session = await create_session(
        db,
        project_id=session.project_id,
        user_id=user_id,
        suite_id=session.suite_id,
        test_case_id=session.test_case_id,
        recording_mode=session.recording_mode or "GUIDED_TEST_CASE",
        environment=session.environment,
        correlation_id=session.correlation_id,
        parent_recording_id=session.id,
    )
    db.add(
        DiscoverySessionEvent(
            session_id=session.id,
            project_id=session.project_id,
            actor_id=user_id,
            actor_type="user",
            previous_state=session.status,
            new_state=session.status,
            command="superseded_by_new_version",
            reason=f"v{new_session.recording_version} created: {reason}",
            correlation_id=session.correlation_id,
            occurred_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
    await db.refresh(new_session)
    return new_session
