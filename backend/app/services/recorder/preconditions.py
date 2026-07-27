"""Live Recorder preconditions (Contract Section 6).

Wraps UI-015's `readiness_check` — which already covers the environment,
evidence storage, host policy and runner preflight — and adds the checks that
only exist because a Live Recorder run belongs to an Automation Test Suite
member rather than to a bare application.

Two kinds of result, deliberately separated. A *blocking* precondition stops
recording, because proceeding would produce automation from something the
platform cannot stand behind. An *advisory* is stated and shown but does not
stop anything — for instance a project that has never built an Application
Model can still record; it just will not get model-backed locator governance,
and saying so is more useful than refusing to start.

Every check reads a real row or makes a real call. Nothing is assumed to pass.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_model import ApplicationModel
from app.models.automation_suite import AutomationSuite, AutomationSuiteTestCase
from app.models.discovery_session import DiscoverySession
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.models.test_data import TestData
from app.services.discovery import readiness_check

# The only recorder adapter that exists. Mobile (Appium) and desktop adapters
# are named in the contract's Section 11 but have no implementation, so a
# member resolving to one of those is blocked with that stated plainly rather
# than silently recorded through a web adapter that cannot drive it.
SUPPORTED_RECORDER_FRAMEWORKS = ("playwright",)

# A session in one of these states holds the test case — a second recorder
# run against it would interleave two users' actions into one action stream.
_LIVE_SESSION_STATES = ("INITIALISING", "RECORDING", "PAUSE_REQUESTED", "RESUMING", "STOP_REQUESTED")


@dataclass(frozen=True)
class Precondition:
    name: str
    passed: bool
    blocking: bool
    detail: str
    # Where to go to fix it (Section 6: "route the user to the source entity"),
    # as an app-relative path. Null when the check is not fixable by navigation.
    remediation_href: str | None = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "blocking": self.blocking,
            "detail": self.detail,
            "remediation_href": self.remediation_href,
        }


@dataclass(frozen=True)
class PreconditionResult:
    checks: list[Precondition]

    @property
    def ready(self) -> bool:
        return all(c.passed for c in self.checks if c.blocking)

    @property
    def blockers(self) -> list[Precondition]:
        return [c for c in self.checks if c.blocking and not c.passed]

    @property
    def advisories(self) -> list[Precondition]:
        return [c for c in self.checks if not c.blocking and not c.passed]

    def as_dict(self) -> dict:
        return {
            "ready": self.ready,
            "checks": [c.as_dict() for c in self.checks],
            "blockers": [c.as_dict() for c in self.blockers],
            "advisories": [c.as_dict() for c in self.advisories],
        }


async def _suite_checks(
    db: AsyncSession, session: DiscoverySession, project_id: int
) -> tuple[list[Precondition], AutomationSuiteTestCase | None]:
    checks: list[Precondition] = []

    if session.suite_id is None:
        checks.append(
            Precondition(
                "suite_selected",
                False,
                True,
                "This recording is not attached to an Automation Test Suite.",
                "/automation?view=workspace",
            )
        )
        return checks, None

    suite = await db.get(AutomationSuite, session.suite_id)
    if suite is None or suite.project_id != project_id:
        checks.append(
            Precondition(
                "suite_selected", False, True, "The Automation Test Suite no longer exists in this project.",
                "/automation?view=workspace",
            )
        )
        return checks, None
    checks.append(
        Precondition("suite_selected", True, True, f"Suite '{suite.name}' (v{suite.version}).", None)
    )

    result = await db.execute(
        select(AutomationSuiteTestCase).where(
            AutomationSuiteTestCase.suite_id == suite.id,
            AutomationSuiteTestCase.test_case_id == session.test_case_id,
        )
    )
    member = result.scalar_one_or_none()
    suite_href = f"/automation?view=workspace&suite={suite.id}"

    if member is None:
        checks.append(
            Precondition(
                "test_case_in_suite", False, True,
                "The selected test case is not a member of this suite.", suite_href,
            )
        )
        return checks, None
    checks.append(Precondition("test_case_in_suite", True, True, "Test case is a member of the suite.", None))

    if member.inclusion_status == "included":
        checks.append(Precondition("member_included", True, True, "Member is included in the suite scope.", None))
    else:
        checks.append(
            Precondition(
                "member_included", False, True,
                f"Member is '{member.inclusion_status}' in this suite, not 'included'"
                + (f" — {member.exclusion_reason}" if member.exclusion_reason else "")
                + ".",
                suite_href,
            )
        )

    # Deliberately advisory, not blocking. A member is BLOCKED when the suite
    # evaluation found a critical gap, and in practice the two most common are
    # "no automation classification" and "no approved Application Model" —
    # neither of which stops a browser from being driven. Blocking on it would
    # also be circular: recording is one of the ways those gaps get closed, so
    # a suite could never leave BLOCKED. What genuinely stops a recording is
    # checked separately and blocks properly (application mapping, environment
    # URL, adapter support, an exclusive lock).
    if member.member_status == "BLOCKED":
        checks.append(
            Precondition(
                "suite_member_ready", False, False,
                f"The suite's last evaluation left this member BLOCKED "
                f"({member.readiness_checks_passed}/{member.readiness_checks_total} readiness checks passed). "
                "Recording is still allowed — it is often how these gaps get closed — but the suite "
                "cannot be published until they are resolved.",
                suite_href,
            )
        )
    else:
        checks.append(
            Precondition(
                "suite_member_ready", True, False,
                f"Member status is {member.member_status}.", None,
            )
        )

    return checks, member


async def _application_checks(
    db: AsyncSession, session: DiscoverySession, member: AutomationSuiteTestCase | None
) -> list[Precondition]:
    checks: list[Precondition] = []
    application = await db.get(ProjectApplication, session.application_id)

    if application is None:
        checks.append(
            Precondition(
                "application_mapping", False, True,
                "The mapped application no longer exists in the Application Registry.", "/applications",
            )
        )
        return checks
    checks.append(
        Precondition("application_mapping", True, True, f"Application '{application.name}'.", None)
    )

    environment_urls = application.environment_urls or {}
    if session.environment in environment_urls:
        checks.append(
            Precondition(
                "environment_resolved", True, True,
                f"Environment '{session.environment}' has a configured URL.", None,
            )
        )
    else:
        checks.append(
            Precondition(
                "environment_resolved", False, True,
                f"Environment '{session.environment}' has no URL configured for '{application.name}'.",
                "/applications",
            )
        )

    framework = (member.resolved_framework if member else None) or session.framework
    if framework in SUPPORTED_RECORDER_FRAMEWORKS:
        checks.append(
            Precondition("recorder_adapter_supported", True, True, f"Recorder adapter available for '{framework}'.", None)
        )
    else:
        checks.append(
            Precondition(
                "recorder_adapter_supported", False, True,
                f"No Live Recorder adapter exists for framework '{framework}'. "
                f"Supported today: {', '.join(SUPPORTED_RECORDER_FRAMEWORKS)}.",
                None,
            )
        )

    result = await db.execute(
        select(ApplicationModel)
        .where(ApplicationModel.application_id == application.id, ApplicationModel.is_current.is_(True))
        .limit(1)
    )
    model = result.scalar_one_or_none()
    checks.append(
        Precondition(
            "application_model_available",
            model is not None,
            False,
            f"Application Model v{model.version} is current."
            if model is not None
            else "No current Application Model for this application. Recording still works; "
                 "locator candidates will not be reconciled against a model.",
            "/applications?view=model",
        )
    )
    return checks


async def _test_data_check(db: AsyncSession, session: DiscoverySession) -> Precondition:
    if session.test_case_id is None:
        return Precondition("linked_test_data", True, False, "No test case selected.", None)
    result = await db.execute(select(TestData).where(TestData.test_case_id == session.test_case_id))
    rows = list(result.scalars().all())
    if rows:
        return Precondition(
            "linked_test_data", True, False, f"{len(rows)} linked test data record(s).", None
        )
    return Precondition(
        "linked_test_data", False, False,
        "No test data is linked to this test case. Typed values will be captured as static literals "
        "unless you classify them as parameters during recording.",
        "/test-data",
    )


async def _exclusive_lock_check(db: AsyncSession, session: DiscoverySession) -> Precondition:
    """Section 6's "test case is not locked by an incompatible operation"."""
    if session.test_case_id is None:
        return Precondition("test_case_not_locked", True, True, "No test case selected.", None)
    result = await db.execute(
        select(DiscoverySession).where(
            DiscoverySession.test_case_id == session.test_case_id,
            DiscoverySession.id != session.id,
            DiscoverySession.status.in_(_LIVE_SESSION_STATES),
        )
    )
    conflicting = result.scalars().first()
    if conflicting is None:
        return Precondition("test_case_not_locked", True, True, "No other live session holds this test case.", None)
    return Precondition(
        "test_case_not_locked", False, True,
        f"Session #{conflicting.id} is already live against this test case (status {conflicting.status}). "
        "Stop it before starting another recording.",
        None,
    )


async def evaluate(db: AsyncSession, session: DiscoverySession) -> PreconditionResult:
    """Section 6 in full. Base readiness (environment reachability, runner
    preflight, evidence storage, host allowlist) is delegated to UI-015's
    existing gate rather than reimplemented."""
    checks: list[Precondition] = []

    suite_checks, member = await _suite_checks(db, session, session.project_id)
    checks.extend(suite_checks)

    if session.test_case_id is None:
        checks.append(
            Precondition(
                "test_case_selected", False, True,
                "A Live Recorder session must have a test case selected (Section 5).", None,
            )
        )
    else:
        test_case = await db.get(TestCase, session.test_case_id)
        if test_case is None:
            checks.append(
                Precondition("test_case_selected", False, True, "The selected test case no longer exists.", None)
            )
        else:
            checks.append(
                Precondition("test_case_selected", True, True, f"{test_case.test_case_id} — {test_case.title}", None)
            )
            steps = [s for s in (test_case.steps or []) if isinstance(s, dict)]
            checks.append(
                Precondition(
                    "test_case_has_steps",
                    bool(steps),
                    session.recording_mode == "GUIDED_TEST_CASE",
                    f"{len(steps)} step(s) to record against."
                    if steps
                    else "The test case has no steps. Guided Test Case Recording has nothing to walk — "
                         "use Exploratory recording, or add steps to the test case first.",
                    f"/test-cases?view=editor",
                )
            )

    checks.extend(await _application_checks(db, session, member))
    checks.append(await _test_data_check(db, session))
    checks.append(await _exclusive_lock_check(db, session))

    # UI-015's gate: environment reachable, runner/browser preflight, evidence
    # storage writable, allowed-host policy, mandatory validators.
    base = await readiness_check.evaluate_session_readiness(db, session)
    for check in base.checks:
        checks.append(
            Precondition(
                check.name,
                check.passed,
                # Credentials and test-data checks from the generic runner
                # gate are informational for a recorder run — a user can log
                # in by hand during the recording, which is the normal case.
                check.name not in ("credentials_configured", "test_data_present"),
                check.detail,
                None,
            )
        )

    return PreconditionResult(checks=checks)
