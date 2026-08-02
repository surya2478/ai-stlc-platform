"""Read the current state of every stage on the path, once.

Deliberately separate from `execution_path`: the decision logic there is pure
and fully tested, and this is the I/O. Each read is independently guarded — a
subsystem that cannot be reached leaves its field None, which the path reports
as UNKNOWN rather than assuming DONE.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_model import ApplicationModel, ApplicationModelNode
from app.models.automation_classification import TestCaseAutomationClassification
from app.models.automation_script import AutomationScript
from app.models.automation_suite import AutomationSuite, AutomationSuiteTestCase
from app.models.discovery_session import DiscoverySession
from app.models.execution_command_center import ExecutionRunItem
from app.models.project_application import ProjectApplication
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.services.execution_path import PathFacts
from app.services.project_application_service import resolve_environment_url

logger = logging.getLogger(__name__)


async def gather(db: AsyncSession, *, project_id: int, test_case_id: int) -> PathFacts:
    facts = PathFacts(project_id=project_id, test_case_id=test_case_id)

    tc = await db.get(TestCase, test_case_id)
    if tc is None or tc.project_id != project_id:
        facts.errors.append("Test case not found in this project.")
        return facts
    facts.test_case_key = tc.test_case_id
    facts.test_case_status = tc.status

    if tc.requirement_id:
        req = await db.get(Requirement, tc.requirement_id)
        if req is not None:
            facts.requirement_key = req.requirement_id
            facts.requirement_status = req.status

    # Application + the URL for *this* test's environment. Resolving rather than
    # checking presence is the point: an app can be registered and still have no
    # URL for the phase this test runs in.
    application = None
    if tc.application_id:
        application = await db.get(ProjectApplication, tc.application_id)
    if application is None:
        application = (
            await db.execute(
                select(ProjectApplication).where(
                    ProjectApplication.project_id == project_id,
                    ProjectApplication.is_active.is_(True),
                ).order_by(ProjectApplication.is_default.desc(), ProjectApplication.id)
            )
        ).scalars().first()
    if application is not None:
        facts.application_id = application.id
        facts.application_name = application.name
        facts.environment = tc.test_phase or next(iter(application.environment_urls or {}), None)
        try:
            facts.environment_url = resolve_environment_url(application, facts.environment)
        except Exception:
            logger.warning("execution_path: could not resolve environment URL", exc_info=True)

        session = (
            await db.execute(
                select(DiscoverySession).where(
                    DiscoverySession.project_id == project_id,
                    DiscoverySession.application_id == application.id,
                    DiscoverySession.status == "COMPLETED",
                ).order_by(DiscoverySession.id.desc())
            )
        ).scalars().first()
        facts.discovery_session_id = session.id if session else None

        model = (
            await db.execute(
                select(ApplicationModel).where(
                    ApplicationModel.project_id == project_id,
                    ApplicationModel.application_id == application.id,
                    ApplicationModel.is_current.is_(True),
                )
            )
        ).scalars().first()
        if model is not None:
            facts.model_id = model.id
            facts.model_version = model.version
            facts.model_status = model.status
            facts.model_screens = (
                await db.execute(
                    select(ApplicationModelNode).where(
                        ApplicationModelNode.model_id == model.id,
                        ApplicationModelNode.node_type == "screen",
                    )
                )
            ).scalars().all().__len__()

    classification = (
        await db.execute(
            select(TestCaseAutomationClassification).where(
                TestCaseAutomationClassification.project_id == project_id,
                TestCaseAutomationClassification.test_case_id == test_case_id,
            ).order_by(TestCaseAutomationClassification.id.desc())
        )
    ).scalars().first()
    if classification is not None:
        facts.classification_review_status = classification.review_status
        facts.classification_candidate_status = classification.candidate_status

    script = (
        await db.execute(
            select(AutomationScript).where(
                AutomationScript.project_id == project_id,
                AutomationScript.test_case_id == test_case_id,
            ).order_by(AutomationScript.id.desc())
        )
    ).scalars().first()
    if script is not None:
        facts.script_key = script.script_id
        gate = script.static_gate_result or None
        facts.script_gate_passed = bool(gate.get("passed")) if gate else None

    # The most recently updated suite containing this test case. A test case may
    # sit in several; the one being worked on is the useful one to report.
    member = (
        await db.execute(
            select(AutomationSuiteTestCase).where(
                AutomationSuiteTestCase.test_case_id == test_case_id,
            ).order_by(AutomationSuiteTestCase.id.desc())
        )
    ).scalars().first()
    if member is not None:
        suite = await db.get(AutomationSuite, member.suite_id)
        if suite is not None:
            facts.suite_id = suite.id
            facts.suite_name = suite.name
            facts.suite_status = suite.status
            members = (
                await db.execute(
                    select(AutomationSuiteTestCase).where(
                        AutomationSuiteTestCase.suite_id == suite.id,
                        AutomationSuiteTestCase.inclusion_status == "included",
                    )
                )
            ).scalars().all()
            facts.members_awaiting_final_approval = sum(
                1 for m in members
                if getattr(m, "approval_state", "PENDING_FINAL") != "FINAL_APPROVED"
            )

    # The most recent governed run for this test case. Without this the path
    # reported "No governed run yet" on a test case that had already passed —
    # a blocker where there is none, which costs trust as fast as a false green.
    item = (
        await db.execute(
            select(ExecutionRunItem).where(
                ExecutionRunItem.project_id == project_id,
                ExecutionRunItem.test_case_id == test_case_id,
            ).order_by(ExecutionRunItem.id.desc())
        )
    ).scalars().first()
    if item is not None:
        facts.last_run_id = item.execution_run_id
        facts.last_run_state = item.lifecycle_state
        facts.last_run_result = item.result

    return facts
