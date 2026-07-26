"""Resolves everything a suite inherits from authoritative entities.

This module is the *only* place in the package that touches the database for
evaluation purposes. Readiness, conflict detection, gap planning and status
computation are all pure functions over the dataclasses returned here.

That split is not cosmetic: a naive per-member port of the retired engine
issued about ten queries per member, so a 200-member suite would have issued
two thousand. Every read below is a bulk `IN` query or a per-distinct-entity
query, so cost scales with distinct applications and models rather than with
member count.

Nothing here copies an inherited value into suite-owned storage. The
`resolved_*` ids written back to a member row are references, and the two
denormalized strings are recomputed every pass — see the note in
`app.models.automation_suite`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_model import ApplicationModel, ApplicationModelGap
from app.models.automation_classification import TestCaseAutomationClassification
from app.models.automation_script import AutomationScript
from app.models.automation_suite import AutomationSuite, AutomationSuiteTestCase
from app.models.discovery_session import DiscoverySession
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.models.test_data import TestData
from app.services import application_model_service
from app.services.project_application_service import resolve_default_application
from app.services.test_classification import capability_resolver
from app.services.test_classification.capability_resolver import CapabilityStatus

# A script in one of these states is not a usable automation asset.
_DEPRECATED_SCRIPT_STATUSES = ("deprecated", "archived", "superseded")


@dataclass(frozen=True)
class MemberInheritance:
    """Everything one suite member inherits, resolved against live sources."""

    member: AutomationSuiteTestCase
    test_case: TestCase | None
    application: ProjectApplication | None
    classification: TestCaseAutomationClassification | None
    model: ApplicationModel | None
    model_is_stale: bool
    open_model_gaps: list[ApplicationModelGap]
    scripts: list[AutomationScript]
    current_scripts: list[AutomationScript]
    frameworks: frozenset[str]
    test_data: list[TestData]
    recordings: list[DiscoverySession]
    resolved_environment: str | None
    environment_source: str | None  # "suite_default" | None
    mandatory_capability_keys: tuple[str, ...]
    drift_reasons: tuple[str, ...]

    @property
    def member_id(self) -> int:
        return self.member.id

    @property
    def test_case_id(self) -> int:
        return self.member.test_case_id

    @property
    def is_included(self) -> bool:
        return self.member.inclusion_status == "included"

    @property
    def is_manual_only(self) -> bool:
        return self.member.inclusion_status == "manual_only"

    @property
    def primary_script(self) -> AutomationScript | None:
        return self.current_scripts[0] if self.current_scripts else None


@dataclass(frozen=True)
class SuiteInheritance:
    members: list[MemberInheritance] = field(default_factory=list)
    capability_status: dict[str, CapabilityStatus] = field(default_factory=dict)

    @property
    def evaluable(self) -> list[MemberInheritance]:
        """Members an evaluation should consider: everything not excluded."""
        return [m for m in self.members if m.member.inclusion_status != "excluded"]


def _current_scripts(scripts: list[AutomationScript]) -> list[AutomationScript]:
    """Highest surviving version per framework.

    `AutomationScript` has `version`/`parent_script_id` but no `is_current`
    flag (unlike `ApplicationModel`), so "the current script" has to be
    derived. A member left with two frameworks after this is a real conflict,
    not an artefact of picking wrongly.
    """
    live = [s for s in scripts if (s.status or "") not in _DEPRECATED_SCRIPT_STATUSES]
    best: dict[str, AutomationScript] = {}
    for script in live:
        framework = script.framework or ""
        incumbent = best.get(framework)
        if incumbent is None or (script.version or 0) > (incumbent.version or 0):
            best[framework] = script
    return sorted(best.values(), key=lambda s: (s.framework or "", -(s.version or 0)))


def _drift_reasons(member: AutomationSuiteTestCase, test_case: TestCase | None,
                   classification: TestCaseAutomationClassification | None,
                   model: ApplicationModel | None) -> tuple[str, ...]:
    """Live sources having moved past what this member was evaluated against.

    This is the preserved `is_stale` concept from the retired engine, now
    per-member and reported rather than returned as a bare boolean.
    """
    if member.last_evaluated_at is None:
        return ()
    reasons: list[str] = []
    if test_case is not None and (test_case.version or 0) != member.source_test_case_version:
        reasons.append(
            f"Test case is now version {test_case.version}, evaluated against version "
            f"{member.source_test_case_version}."
        )
    current_classification_id = classification.id if classification else None
    if current_classification_id != member.resolved_classification_id:
        reasons.append("The current automation classification differs from the one evaluated.")
    if member.resolved_application_id is not None:
        current_model_id = model.id if model else None
        if current_model_id != member.resolved_model_id:
            reasons.append("The current Application Model differs from the one evaluated.")
    return tuple(reasons)


async def _load_applications(
    db: AsyncSession, *, project_id: int, test_cases: list[TestCase]
) -> dict[int, ProjectApplication | None]:
    """Application per test case: explicit mapping, else the project default."""
    explicit_ids = {tc.application_id for tc in test_cases if tc.application_id is not None}
    by_id: dict[int, ProjectApplication] = {}
    if explicit_ids:
        result = await db.execute(select(ProjectApplication).where(ProjectApplication.id.in_(explicit_ids)))
        by_id = {row.id: row for row in result.scalars().all()}

    default_app: ProjectApplication | None = None
    if any(tc.application_id is None or tc.application_id not in by_id for tc in test_cases):
        default_app = await resolve_default_application(db, project_id)

    resolved: dict[int, ProjectApplication | None] = {}
    for tc in test_cases:
        app = by_id.get(tc.application_id) if tc.application_id is not None else None
        resolved[tc.id] = app or default_app
    return resolved


async def _load_models(
    db: AsyncSession, *, project_id: int, applications: list[ProjectApplication]
) -> tuple[dict[int, ApplicationModel | None], dict[int, bool], dict[int, list[ApplicationModelGap]]]:
    """Current model, staleness and open gaps per distinct application."""
    models: dict[int, ApplicationModel | None] = {}
    stale: dict[int, bool] = {}
    for app in applications:
        model = await application_model_service.get_current_model(
            db, project_id=project_id, application_id=app.id
        )
        models[app.id] = model
        stale[app.id] = await application_model_service.is_stale(db, model) if model else False

    gaps_by_model: dict[int, list[ApplicationModelGap]] = {}
    model_ids = [m.id for m in models.values() if m is not None]
    if model_ids:
        result = await db.execute(
            select(ApplicationModelGap).where(
                ApplicationModelGap.model_id.in_(model_ids),
                ApplicationModelGap.status == "open",
            )
        )
        for gap in result.scalars().all():
            gaps_by_model.setdefault(gap.model_id, []).append(gap)
    return models, stale, gaps_by_model


async def _group_by_test_case(db: AsyncSession, model, column, test_case_ids: list[int]) -> dict[int, list[Any]]:
    if not test_case_ids:
        return {}
    result = await db.execute(select(model).where(column.in_(test_case_ids)))
    grouped: dict[int, list[Any]] = {}
    for row in result.scalars().all():
        grouped.setdefault(getattr(row, column.key), []).append(row)
    return grouped


async def _build(
    db: AsyncSession,
    *,
    project_id: int,
    members: list[AutomationSuiteTestCase],
    default_environment: str | None,
) -> SuiteInheritance:
    test_case_ids = [m.test_case_id for m in members]
    if not test_case_ids:
        return SuiteInheritance()

    result = await db.execute(select(TestCase).where(TestCase.id.in_(test_case_ids)))
    test_cases_by_id = {tc.id: tc for tc in result.scalars().all()}
    test_cases = list(test_cases_by_id.values())

    applications_by_tc = await _load_applications(db, project_id=project_id, test_cases=test_cases)
    distinct_applications = {app.id: app for app in applications_by_tc.values() if app is not None}
    models_by_app, stale_by_app, gaps_by_model = await _load_models(
        db, project_id=project_id, applications=list(distinct_applications.values())
    )

    result = await db.execute(
        select(TestCaseAutomationClassification).where(
            TestCaseAutomationClassification.test_case_id.in_(test_case_ids),
            TestCaseAutomationClassification.is_current.is_(True),
        )
    )
    classifications_by_tc = {c.test_case_id: c for c in result.scalars().all()}

    scripts_by_tc = await _group_by_test_case(db, AutomationScript, AutomationScript.test_case_id, test_case_ids)
    test_data_by_tc = await _group_by_test_case(db, TestData, TestData.test_case_id, test_case_ids)
    recordings_by_tc = await _group_by_test_case(
        db, DiscoverySession, DiscoverySession.test_case_id, test_case_ids
    )

    # One capability lookup for the union of every member's mandatory keys.
    mandatory_by_member: dict[int, tuple[str, ...]] = {}
    all_keys: set[str] = set()
    for member in members:
        classification = classifications_by_tc.get(member.test_case_id)
        keys: list[str] = []
        if classification is not None:
            if classification.primary_adapter:
                keys.append(classification.primary_adapter)
            keys.extend(classification.mandatory_validators or [])
        mandatory_by_member[member.id] = tuple(keys)
        all_keys.update(keys)

    capability_status: dict[str, CapabilityStatus] = {}
    if all_keys:
        capability_status = await capability_resolver.resolve_capabilities(
            db, project_id=project_id, keys=sorted(all_keys)
        )

    resolved_members: list[MemberInheritance] = []
    for member in members:
        test_case = test_cases_by_id.get(member.test_case_id)
        application = applications_by_tc.get(member.test_case_id)
        classification = classifications_by_tc.get(member.test_case_id)
        model = models_by_app.get(application.id) if application else None
        scripts = scripts_by_tc.get(member.test_case_id, [])
        current = _current_scripts(scripts)

        # Environment is suite-owned or unresolved. It is deliberately not
        # inferred from test data: "test data exists for env X" is a
        # different statement from "this test case runs in env X", and
        # treating them as the same would misreport the source.
        environment = default_environment
        environment_source = "suite_default" if environment else None

        resolved_members.append(
            MemberInheritance(
                member=member,
                test_case=test_case,
                application=application,
                classification=classification,
                model=model,
                model_is_stale=stale_by_app.get(application.id, False) if application else False,
                open_model_gaps=gaps_by_model.get(model.id, []) if model else [],
                scripts=scripts,
                current_scripts=current,
                frameworks=frozenset(s.framework for s in current if s.framework),
                test_data=test_data_by_tc.get(member.test_case_id, []),
                recordings=recordings_by_tc.get(member.test_case_id, []),
                resolved_environment=environment,
                environment_source=environment_source,
                mandatory_capability_keys=mandatory_by_member[member.id],
                drift_reasons=_drift_reasons(member, test_case, classification, model),
            )
        )

    return SuiteInheritance(members=resolved_members, capability_status=capability_status)


async def resolve_suite_inheritance(
    db: AsyncSession, *, suite: AutomationSuite, members: list[AutomationSuiteTestCase]
) -> SuiteInheritance:
    return await _build(
        db, project_id=suite.project_id, members=members, default_environment=suite.default_environment
    )


async def resolve_preview_inheritance(
    db: AsyncSession, *, project_id: int, test_case_ids: list[int], default_environment: str | None
) -> SuiteInheritance:
    """Inheritance for a not-yet-created suite, for the wizard's live panel.

    Uses unsaved, in-memory member rows so the preview writes nothing. Ids are
    negative placeholders so a preview gap can never collide with a persisted
    member id.
    """
    members = [
        AutomationSuiteTestCase(
            id=-(index + 1),
            suite_id=0,
            test_case_id=test_case_id,
            inclusion_status="included",
            source_system="platform",
            member_status="NOT_EVALUATED",
            readiness_checks_passed=0,
            readiness_checks_total=0,
            source_test_case_version=0,
        )
        for index, test_case_id in enumerate(dict.fromkeys(test_case_ids))
    ]
    return await _build(
        db, project_id=project_id, members=members, default_environment=default_environment
    )
