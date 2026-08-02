"""Automation Test Suite — membership, evaluation, adjudication and queries."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.approval import ApprovalAction
from app.models.automation_script import AutomationScript
from app.models.automation_suite import (
    IMMUTABLE_STATUSES,
    WORKFLOW_OWNED_STATUSES,
    AutomationSuite,
    AutomationSuiteActivity,
    AutomationSuiteExecutionGroup,
    AutomationSuiteGap,
    AutomationSuiteTestCase,
)
from app.models.test_case import TestCase
from app.services.automation_suite import conflicts as conflict_engine
from app.services.automation_suite import gaps as gap_engine
from app.services.automation_suite import execution_groups as group_engine
from app.services.automation_suite import inheritance as inheritance_engine
from app.services.automation_suite import lifecycle
from app.services.automation_suite import readiness as readiness_engine
from app.services.automation_suite import status as status_engine
from app.services.automation_suite.errors import AutomationSuiteError


# ─── Lookups ──────────────────────────────────────────────────────────────────

async def get_suite_or_404(db: AsyncSession, suite_id: int) -> AutomationSuite:
    row = await db.get(AutomationSuite, suite_id)
    if row is None:
        raise AutomationSuiteError(404, "SUITE_NOT_FOUND", "Automation test suite not found.")
    return row


async def _load_members(db: AsyncSession, suite_id: int) -> list[AutomationSuiteTestCase]:
    result = await db.execute(
        select(AutomationSuiteTestCase)
        .where(AutomationSuiteTestCase.suite_id == suite_id)
        .order_by(
            AutomationSuiteTestCase.planned_sequence.nulls_last(),
            AutomationSuiteTestCase.id,
        )
    )
    return list(result.scalars().all())


async def _get_member_or_404(db: AsyncSession, suite: AutomationSuite, member_id: int) -> AutomationSuiteTestCase:
    row = await db.get(AutomationSuiteTestCase, member_id)
    if row is None or row.suite_id != suite.id:
        raise AutomationSuiteError(404, "MEMBER_NOT_FOUND", "Test case is not a member of this suite.")
    return row


async def _log_activity(
    db: AsyncSession,
    *,
    suite: AutomationSuite,
    event_type: str,
    actor_id: int | None,
    member_id: int | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    reason: str | None = None,
) -> None:
    db.add(
        AutomationSuiteActivity(
            project_id=suite.project_id,
            suite_id=suite.id,
            suite_test_case_id=member_id,
            event_type=event_type,
            actor_id=actor_id,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            correlation_id=suite.correlation_id,
        )
    )
    await db.flush()


# ─── Creation ─────────────────────────────────────────────────────────────────

async def _find_by_idempotency_key(
    db: AsyncSession, *, project_id: int, idempotency_key: str
) -> AutomationSuite | None:
    result = await db.execute(
        select(AutomationSuite).where(
            AutomationSuite.project_id == project_id,
            AutomationSuite.idempotency_key == idempotency_key,
        )
    )
    return result.scalars().first()


async def _assert_name_available(db: AsyncSession, *, project_id: int, name: str, exclude_id: int | None = None) -> None:
    query = select(AutomationSuite).where(
        AutomationSuite.project_id == project_id,
        func.lower(AutomationSuite.name) == name.strip().lower(),
        AutomationSuite.is_current.is_(True),
        AutomationSuite.status != "ARCHIVED",
    )
    if exclude_id is not None:
        query = query.where(AutomationSuite.id != exclude_id)
    if (await db.execute(query)).scalars().first() is not None:
        raise AutomationSuiteError(409, "SUITE_NAME_EXISTS", f"An active suite named '{name}' already exists.")


async def create_suite(
    db: AsyncSession,
    *,
    project_id: int,
    name: str,
    description: str | None,
    tags: list[str] | None,
    test_case_ids: list[int],
    test_suite_ids: list[int] | None,
    default_environment: str | None,
    idempotency_key: str | None,
    actor_id: int,
) -> tuple[AutomationSuite, bool]:
    """Returns (suite, created). A replayed idempotency key returns created=False."""
    if idempotency_key:
        existing = await _find_by_idempotency_key(db, project_id=project_id, idempotency_key=idempotency_key)
        if existing is not None:
            return existing, False

    clean_name = (name or "").strip()
    if not clean_name:
        raise AutomationSuiteError(422, "SUITE_NAME_REQUIRED", "Suite name is required.")
    await _assert_name_available(db, project_id=project_id, name=clean_name)

    suite = AutomationSuite(
        project_id=project_id,
        name=clean_name,
        description=description,
        tags=list(tags or []),
        status="DRAFT",
        version=1,
        is_current=True,
        default_environment=default_environment,
        owner_id=actor_id,
        created_by=actor_id,
        idempotency_key=idempotency_key,
    )
    db.add(suite)
    try:
        await db.flush()
    except IntegrityError:
        # Two concurrent submits with the same key: the loser re-reads the
        # winner's row instead of creating a duplicate.
        await db.rollback()
        if idempotency_key:
            existing = await _find_by_idempotency_key(db, project_id=project_id, idempotency_key=idempotency_key)
            if existing is not None:
                return existing, False
        raise AutomationSuiteError(409, "SUITE_CREATE_CONFLICT", "This suite has already been created.")

    await _log_activity(
        db,
        suite=suite,
        event_type="suite_created",
        actor_id=actor_id,
        new_value={"name": clean_name, "default_environment": default_environment},
    )
    await add_members(
        db,
        suite,
        test_case_ids=test_case_ids,
        test_suite_ids=test_suite_ids,
        actor_id=actor_id,
        commit=False,
    )
    await evaluate_suite(db, suite, actor_id=actor_id)
    return suite, True


async def update_suite(
    db: AsyncSession,
    suite: AutomationSuite,
    *,
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    actor_id: int,
) -> AutomationSuite:
    _require_mutable(suite)
    old = {"name": suite.name, "description": suite.description, "tags": list(suite.tags or [])}
    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise AutomationSuiteError(422, "SUITE_NAME_REQUIRED", "Suite name is required.")
        await _assert_name_available(db, project_id=suite.project_id, name=clean_name, exclude_id=suite.id)
        suite.name = clean_name
    if description is not None:
        suite.description = description
    if tags is not None:
        suite.tags = list(tags)
    await _log_activity(
        db,
        suite=suite,
        event_type="suite_updated",
        actor_id=actor_id,
        old_value=old,
        new_value={"name": suite.name, "description": suite.description, "tags": list(suite.tags or [])},
    )
    await db.commit()
    await db.refresh(suite)
    return suite


async def set_default_environment(
    db: AsyncSession, suite: AutomationSuite, *, environment: str | None, actor_id: int
) -> AutomationSuite:
    _require_mutable(suite)
    old = suite.default_environment
    suite.default_environment = environment
    await _log_activity(
        db,
        suite=suite,
        event_type="default_environment_set",
        actor_id=actor_id,
        old_value={"default_environment": old},
        new_value={"default_environment": environment},
    )
    # The environment feeds readiness check 8, so the suite must be re-judged.
    return await evaluate_suite(db, suite, actor_id=actor_id)


def _require_mutable(suite: AutomationSuite) -> None:
    """Blocks changes to a suite's *scope*.

    An approved or published suite is frozen by its publication snapshot —
    changing its membership would make the snapshot a lie. Adopting a change
    means starting a new version.
    """
    if suite.status == "ARCHIVED":
        raise AutomationSuiteError(409, "SUITE_ARCHIVED", "This suite is archived and can no longer be changed.")
    if suite.status in IMMUTABLE_STATUSES:
        raise AutomationSuiteError(
            409,
            "SUITE_IMMUTABLE",
            f"A suite that is '{suite.status}' is frozen by its publication snapshot. "
            "Start a new version to change its scope.",
        )


def _require_not_archived(suite: AutomationSuite) -> None:
    """Blocks only what archiving forbids — re-evaluation stays allowed.

    A published suite must remain evaluable so impact review can keep
    comparing it against live sources.
    """
    if suite.status == "ARCHIVED":
        raise AutomationSuiteError(409, "SUITE_ARCHIVED", "This suite is archived and can no longer be changed.")


# ─── Membership ───────────────────────────────────────────────────────────────

async def add_members(
    db: AsyncSession,
    suite: AutomationSuite,
    *,
    test_case_ids: list[int] | None = None,
    test_suite_ids: list[int] | None = None,
    actor_id: int,
    commit: bool = True,
) -> dict[str, Any]:
    _require_mutable(suite)

    requested: dict[int, str | None] = {}
    for test_case_id in test_case_ids or []:
        requested.setdefault(test_case_id, None)

    # A pack expands to individual members carrying their provenance; there
    # is no separate pack table.
    for test_suite_id in test_suite_ids or []:
        result = await db.execute(
            select(TestCase.id).where(
                TestCase.test_suite_id == test_suite_id,
                TestCase.project_id == suite.project_id,
                TestCase.is_deleted.is_(False),
            )
        )
        for test_case_id in result.scalars().all():
            requested.setdefault(test_case_id, f"test_suite:{test_suite_id}")

    if not requested:
        return {"added": 0, "skipped_duplicate": 0, "rejected": []}

    existing_result = await db.execute(
        select(AutomationSuiteTestCase.test_case_id).where(AutomationSuiteTestCase.suite_id == suite.id)
    )
    already = set(existing_result.scalars().all())

    valid_result = await db.execute(
        select(TestCase).where(
            TestCase.id.in_(list(requested)),
            TestCase.project_id == suite.project_id,
            TestCase.is_deleted.is_(False),
        )
    )
    valid = {tc.id: tc for tc in valid_result.scalars().all()}

    rejected = [
        {"test_case_id": tcid, "reason": "Not found in this project, or deleted."}
        for tcid in requested
        if tcid not in valid
    ]
    skipped = [tcid for tcid in requested if tcid in valid and tcid in already]
    to_add = [tcid for tcid in requested if tcid in valid and tcid not in already]

    total_after = len(already) + len(to_add)
    if total_after > get_settings().automation_suite_max_members:
        raise AutomationSuiteError(
            422,
            "SUITE_TOO_LARGE",
            f"A suite is limited to {get_settings().automation_suite_max_members} test cases; this would make {total_after}.",
        )

    for test_case_id in to_add:
        db.add(
            AutomationSuiteTestCase(
                suite_id=suite.id,
                test_case_id=test_case_id,
                inclusion_status="included",
                source_system="platform",
                source_reference=requested[test_case_id],
                added_by=actor_id,
            )
        )
    await db.flush()

    if to_add:
        await _log_activity(
            db,
            suite=suite,
            event_type="members_added",
            actor_id=actor_id,
            new_value={"test_case_ids": to_add, "count": len(to_add)},
        )

    if commit:
        await evaluate_suite(db, suite, actor_id=actor_id)

    return {"added": len(to_add), "skipped_duplicate": len(skipped), "rejected": rejected}


async def remove_member(db: AsyncSession, suite: AutomationSuite, member_id: int, *, actor_id: int) -> None:
    _require_mutable(suite)
    member = await _get_member_or_404(db, suite, member_id)
    test_case_id = member.test_case_id
    await db.delete(member)
    await db.flush()
    await _log_activity(
        db,
        suite=suite,
        event_type="member_removed",
        actor_id=actor_id,
        old_value={"test_case_id": test_case_id},
    )
    await evaluate_suite(db, suite, actor_id=actor_id)


async def update_member(
    db: AsyncSession,
    suite: AutomationSuite,
    member_id: int,
    *,
    inclusion_status: str | None = None,
    planned_sequence: int | None = None,
    exclusion_reason: str | None = None,
    actor_id: int,
) -> AutomationSuiteTestCase:
    _require_mutable(suite)
    member = await _get_member_or_404(db, suite, member_id)
    old = {"inclusion_status": member.inclusion_status, "planned_sequence": member.planned_sequence}

    if inclusion_status is not None and inclusion_status != member.inclusion_status:
        member.inclusion_status = inclusion_status
        if inclusion_status == "excluded":
            member.excluded_by = actor_id
            member.excluded_at = datetime.now(timezone.utc)
            member.exclusion_reason = exclusion_reason
            event = "member_excluded"
        elif inclusion_status == "manual_only":
            event = "member_marked_manual_only"
        else:
            member.excluded_by = None
            member.excluded_at = None
            member.exclusion_reason = None
            event = "member_included"
        await _log_activity(
            db,
            suite=suite,
            event_type=event,
            actor_id=actor_id,
            member_id=member.id,
            old_value=old,
            new_value={"inclusion_status": inclusion_status},
            reason=exclusion_reason,
        )

    if planned_sequence is not None:
        member.planned_sequence = planned_sequence

    await db.flush()
    await evaluate_suite(db, suite, actor_id=actor_id)
    await db.refresh(member)
    return member


async def list_members(
    db: AsyncSession,
    suite: AutomationSuite,
    *,
    inclusion_status: str | None = None,
    member_status: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    filters = [AutomationSuiteTestCase.suite_id == suite.id]
    if inclusion_status:
        filters.append(AutomationSuiteTestCase.inclusion_status == inclusion_status)
    if member_status:
        filters.append(AutomationSuiteTestCase.member_status == member_status)

    total = (
        await db.execute(select(func.count()).select_from(AutomationSuiteTestCase).where(*filters))
    ).scalar() or 0

    result = await db.execute(
        select(AutomationSuiteTestCase)
        .where(*filters)
        .order_by(AutomationSuiteTestCase.planned_sequence.nulls_last(), AutomationSuiteTestCase.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    members = list(result.scalars().all())

    test_cases: dict[int, TestCase] = {}
    if members:
        tc_result = await db.execute(select(TestCase).where(TestCase.id.in_([m.test_case_id for m in members])))
        test_cases = {tc.id: tc for tc in tc_result.scalars().all()}

    items = [_member_payload(m, test_cases.get(m.test_case_id)) for m in members]
    return _paginated(items, total=total, page=page, page_size=page_size)


def _member_payload(member: AutomationSuiteTestCase, test_case: TestCase | None) -> dict[str, Any]:
    return {
        "id": member.id,
        "test_case_id": member.test_case_id,
        "test_case_reference": getattr(test_case, "test_case_id", None) if test_case else None,
        "title": getattr(test_case, "title", None) if test_case else None,
        "test_case_status": getattr(test_case, "status", None) if test_case else None,
        "execution_mode": getattr(test_case, "execution_mode", None) if test_case else None,
        "priority": getattr(test_case, "priority", None) if test_case else None,
        "automation_status": getattr(test_case, "automation_status", None) if test_case else None,
        "inclusion_status": member.inclusion_status,
        "planned_sequence": member.planned_sequence,
        "source_system": member.source_system,
        "source_reference": member.source_reference,
        "member_status": member.member_status,
        "readiness_checks_passed": member.readiness_checks_passed,
        "readiness_checks_total": member.readiness_checks_total,
        "last_evaluated_at": member.last_evaluated_at,
        "resolved_application_id": member.resolved_application_id,
        "resolved_framework": member.resolved_framework,
        "resolved_environment": member.resolved_environment,
        "resolved_script_id": member.resolved_script_id,
        "exclusion_reason": member.exclusion_reason,
    }


def _paginated(items: list[Any], *, total: int, page: int, page_size: int) -> dict[str, Any]:
    pages = (total + page_size - 1) // page_size if page_size else 0
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages}


# ─── Evaluation ───────────────────────────────────────────────────────────────

async def evaluate_suite(db: AsyncSession, suite: AutomationSuite, *, actor_id: int) -> AutomationSuite:
    """Re-resolve inheritance, re-judge every member, sync gaps, recompute status.

    Runs against published suites too, because that is how impact review keeps
    working — but it never recomputes a status the approval workflow owns.
    """
    _require_not_archived(suite)
    members = await _load_members(db, suite.id)
    if len(members) > get_settings().automation_suite_max_members:
        raise AutomationSuiteError(
            422,
            "SUITE_TOO_LARGE",
            f"A suite is limited to {get_settings().automation_suite_max_members} test cases.",
        )

    suite_inh = await inheritance_engine.resolve_suite_inheritance(db, suite=suite, members=members)

    evaluations: dict[int, readiness_engine.MemberEvaluation] = {}
    detected: list[gap_engine.DetectedGap] = []
    for member_inh in suite_inh.evaluable:
        evaluation = readiness_engine.evaluate_member(
            member_inh, capability_status=suite_inh.capability_status
        )
        evaluations[member_inh.member_id] = evaluation
        detected.extend(evaluation.gaps)

    detected.extend(conflict_engine.detect_cross_member_conflicts(suite_inh))

    # A published version is additionally checked against its frozen snapshot,
    # so a source that moved on shows up as an impact finding.
    if suite.status in ("PUBLISHED", "DEPRECATED"):
        drift, _summary = await lifecycle.detect_snapshot_drift(db, suite)
        detected.extend(drift)

    existing_result = await db.execute(select(AutomationSuiteGap).where(AutomationSuiteGap.suite_id == suite.id))
    plan = gap_engine.plan_gap_sync(list(existing_result.scalars().all()), detected)
    now = datetime.now(timezone.utc)
    await gap_engine.apply_gap_sync(db, suite=suite, plan=plan, now=now)

    if plan.to_auto_close:
        await _log_activity(
            db,
            suite=suite,
            event_type="gap_auto_closed",
            actor_id=actor_id,
            new_value={"count": len(plan.to_auto_close)},
        )

    # Only findings that still count against the suite feed the rollup, so a
    # waived or excluded gap genuinely advances the status.
    blocking_fingerprints = plan.blocking_fingerprints
    blocking_gaps = [g for g in detected if gap_engine.fingerprint(g) in blocking_fingerprints]
    member_statuses = {
        member_id: evaluation.effective_status(blocking_fingerprints)
        for member_id, evaluation in evaluations.items()
    }

    for member_inh in suite_inh.members:
        evaluation = evaluations.get(member_inh.member_id)
        member = member_inh.member
        if evaluation is None:
            # Excluded members are not judged; leave their last verdict alone.
            continue
        member.member_status = member_statuses[member_inh.member_id]
        member.readiness_checks_passed = evaluation.checks_passed
        member.readiness_checks_total = evaluation.checks_total
        member.last_evaluated_at = now
        member.source_test_case_version = (
            member_inh.test_case.version or 0 if member_inh.test_case else member.source_test_case_version
        )
        member.resolved_application_id = member_inh.application.id if member_inh.application else None
        member.resolved_classification_id = member_inh.classification.id if member_inh.classification else None
        member.resolved_model_id = member_inh.model.id if member_inh.model else None
        member.resolved_script_id = member_inh.primary_script.id if member_inh.primary_script else None
        member.resolved_framework = member_inh.primary_script.framework if member_inh.primary_script else None
        member.resolved_environment = member_inh.resolved_environment

    # UI-023: a member's validation state is read from the persisted Static
    # Quality Gate verdict on its script — never recomputed here.
    #
    # A *passed* gate previously also mapped to "pending", which made a
    # validated member indistinguishable from an unvalidated one and parked the
    # whole suite in VALIDATION_PENDING — a status this codebase excludes from
    # SUITE_REACHABLE_STATUSES precisely because nothing exists to clear it. A
    # suite with every script passing its gate and zero open findings could not
    # be submitted, and there was no action that would ever unblock it.
    #
    # Passing the gate is the validation completing, so no state is recorded:
    # only "pending" and "failed" are states a member is *in*.
    validation_states: dict[int, str] = {}
    for member_inh in suite_inh.members:
        script = member_inh.primary_script
        if script is None:
            continue
        gate = script.static_gate_result or None
        if gate is None:
            # Never gated — genuinely awaiting validation.
            validation_states[member_inh.member_id] = "pending"
        elif not gate.get("passed"):
            validation_states[member_inh.member_id] = "failed"

    rollup = status_engine.compute_rollup(
        members=suite_inh.members,
        member_statuses=member_statuses,
        blocking_gaps=blocking_gaps,
        evaluated=True,
        validation_states=validation_states,
    )
    _apply_rollup(suite, rollup)
    # Once a suite is in review, approved or published, its status is a human
    # decision — recomputing it here would silently undo that decision.
    if suite.status not in WORKFLOW_OWNED_STATUSES:
        suite.status = status_engine.compute_suite_status(rollup)
    suite.last_evaluated_at = now
    suite.last_inheritance_sync_at = now

    await _log_activity(
        db,
        suite=suite,
        event_type="suite_evaluated",
        actor_id=actor_id,
        new_value={
            "status": suite.status,
            "members_included": rollup.members_included,
            "members_ready": rollup.members_ready,
            "members_blocked": rollup.members_blocked,
            "gaps_critical_open": rollup.gaps_critical_open,
            "conflicts_open": rollup.conflicts_open,
        },
    )
    await db.commit()
    await db.refresh(suite)
    return suite


def _apply_rollup(suite: AutomationSuite, rollup: status_engine.SuiteRollup) -> None:
    suite.members_total = rollup.members_total
    suite.members_included = rollup.members_included
    suite.members_ready = rollup.members_ready
    suite.members_blocked = rollup.members_blocked
    suite.members_manual_only = rollup.members_manual_only
    suite.members_drifted = rollup.members_drifted
    suite.gaps_critical_open = rollup.gaps_critical_open
    suite.gaps_warning_open = rollup.gaps_warning_open
    suite.conflicts_open = rollup.conflicts_open


# ─── Gap adjudication ─────────────────────────────────────────────────────────

# Which conflicts a group split can actually resolve, and the dimension it
# splits on. Any other finding has no grouping interpretation.
_SPLITTABLE_CONFLICTS = {
    "MULTIPLE_FRAMEWORKS": "framework",
    "MULTIPLE_ENVIRONMENTS": "environment",
}


async def _get_gap_or_404(db: AsyncSession, suite: AutomationSuite, gap_id: int) -> AutomationSuiteGap:
    row = await db.get(AutomationSuiteGap, gap_id)
    if row is None or row.suite_id != suite.id:
        raise AutomationSuiteError(404, "GAP_NOT_FOUND", "Gap not found on this suite.")
    return row


async def resolve_gap(
    db: AsyncSession,
    suite: AutomationSuite,
    *,
    gap_id: int,
    resolution_action: str,
    reviewer_notes: str | None,
    actor_id: int,
) -> AutomationSuiteGap:
    _require_mutable(suite)
    gap = await _get_gap_or_404(db, suite, gap_id)
    old_status = gap.status

    if resolution_action == "split_execution_groups":
        dimension = _SPLITTABLE_CONFLICTS.get(gap.gap_type)
        if dimension is None:
            raise AutomationSuiteError(
                422,
                "NOT_SPLITTABLE",
                f"'{gap.gap_type}' cannot be resolved by splitting into execution groups.",
            )
        created = await split_into_execution_groups(db, suite, dimension=dimension, actor_id=actor_id)
        gap.status = "resolved"
        gap.resolution_action = resolution_action
        gap.reviewer_notes = reviewer_notes or f"Split into {created} execution group(s) by {dimension}."
        gap.resolved_by = actor_id
        gap.resolved_at = datetime.now(timezone.utc)
        gap.auto_closed = False
        await _log_activity(
            db,
            suite=suite,
            event_type="gap_resolved",
            actor_id=actor_id,
            old_value={"status": old_status},
            new_value={
                "status": gap.status,
                "resolution_action": resolution_action,
                "gap_type": gap.gap_type,
                "groups_created": created,
            },
            reason=reviewer_notes,
        )
        await db.commit()
        await db.refresh(gap)
        return gap

    if resolution_action == "exclude_test_case":
        if gap.suite_test_case_id is None:
            raise AutomationSuiteError(
                422, "GAP_NOT_MEMBER_SCOPED", "This finding is not tied to a single test case, so it cannot be excluded."
            )
        await update_member(
            db,
            suite,
            gap.suite_test_case_id,
            inclusion_status="excluded",
            exclusion_reason=reviewer_notes or f"Excluded to resolve {gap.gap_type}.",
            actor_id=actor_id,
        )
        gap.status = "excluded"
    else:
        gap.status = "resolved"

    gap.resolution_action = resolution_action
    gap.reviewer_notes = reviewer_notes
    gap.resolved_by = actor_id
    gap.resolved_at = datetime.now(timezone.utc)
    gap.auto_closed = False

    await _log_activity(
        db,
        suite=suite,
        event_type="gap_resolved",
        actor_id=actor_id,
        member_id=gap.suite_test_case_id,
        old_value={"status": old_status},
        new_value={"status": gap.status, "resolution_action": resolution_action, "gap_type": gap.gap_type},
        reason=reviewer_notes,
    )
    await db.commit()
    await db.refresh(gap)
    return gap


async def approve_exception(
    db: AsyncSession, suite: AutomationSuite, *, gap_id: int, reason: str, actor_id: int
) -> AutomationSuiteGap:
    _require_mutable(suite)
    if not (reason or "").strip():
        raise AutomationSuiteError(422, "REASON_REQUIRED", "A reason is required to approve an exception.")
    gap = await _get_gap_or_404(db, suite, gap_id)
    old_status = gap.status

    gap.status = "exception_approved"
    gap.resolution_action = "approve_exception"
    gap.reviewer_notes = reason
    gap.resolved_by = actor_id
    gap.resolved_at = datetime.now(timezone.utc)
    gap.auto_closed = False

    # Waivers are governance decisions, so they also land in the shared
    # approval ledger, not only this module's activity log.
    db.add(
        ApprovalAction(
            project_id=suite.project_id,
            user_id=actor_id,
            action_type="approve_automation_suite_exception",
            entity_type="automation_suite_gap",
            entity_id=gap.id,
            decision="approved",
            notes=reason,
            new_value={"gap_type": gap.gap_type, "suite_id": suite.id},
            correlation_id=suite.correlation_id,
        )
    )
    await _log_activity(
        db,
        suite=suite,
        event_type="exception_approved",
        actor_id=actor_id,
        member_id=gap.suite_test_case_id,
        old_value={"status": old_status},
        new_value={"status": gap.status, "gap_type": gap.gap_type},
        reason=reason,
    )
    await db.commit()
    await db.refresh(gap)
    return gap


async def list_gaps(
    db: AsyncSession,
    suite: AutomationSuite,
    *,
    category: str | None = None,
    severity: str | None = None,
    status_filter: str | None = None,
    member_id: int | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    filters = [AutomationSuiteGap.suite_id == suite.id]
    if category:
        filters.append(AutomationSuiteGap.category == category)
    if severity:
        filters.append(AutomationSuiteGap.severity == severity)
    if status_filter:
        filters.append(AutomationSuiteGap.status == status_filter)
    if member_id is not None:
        filters.append(AutomationSuiteGap.suite_test_case_id == member_id)

    total = (await db.execute(select(func.count()).select_from(AutomationSuiteGap).where(*filters))).scalar() or 0
    result = await db.execute(
        select(AutomationSuiteGap)
        .where(*filters)
        .order_by(
            AutomationSuiteGap.severity.desc(),
            AutomationSuiteGap.status,
            AutomationSuiteGap.id,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return _paginated(list(result.scalars().all()), total=total, page=page, page_size=page_size)


# ─── Execution groups ─────────────────────────────────────────────────────────

async def split_into_execution_groups(
    db: AsyncSession, suite: AutomationSuite, *, dimension: str, actor_id: int
) -> int:
    """Replace the suite's groups with one per distinct value of `dimension`."""
    _require_mutable(suite)
    members = await _load_members(db, suite.id)
    suite_inh = await inheritance_engine.resolve_suite_inheritance(db, suite=suite, members=members)

    planned = group_engine.plan_auto_split(suite_inh.members, dimension=dimension)
    if not planned:
        raise AutomationSuiteError(
            422, "NOTHING_TO_SPLIT", "This suite has no included test cases to group."
        )

    await group_engine.clear_groups(db, suite)
    for plan in planned:
        group = await group_engine.create_group(
            db,
            suite,
            name=plan.name,
            framework=plan.framework,
            environment=plan.environment,
            application_id=plan.application_id,
            sequence=plan.sequence,
            notes=f"Created by splitting the suite on {dimension}.",
            actor_id=actor_id,
        )
        await group_engine.assign_members(db, suite, group_id=group.id, member_ids=list(plan.member_ids))

    await _log_activity(
        db,
        suite=suite,
        event_type="execution_groups_split",
        actor_id=actor_id,
        new_value={"dimension": dimension, "groups": len(planned)},
    )
    await db.flush()
    return len(planned)


async def list_execution_groups(db: AsyncSession, suite: AutomationSuite) -> dict[str, Any]:
    groups = await group_engine.list_groups(db, suite)
    return {
        "items": groups,
        "split_dimensions": list(group_engine.SPLIT_DIMENSIONS),
        # Orchestration policy has no home yet: nothing executes a suite.
        "unavailable": {
            "parallelism": "No suite-to-execution path exists yet, so parallelism cannot be honoured.",
            "retry_policy": "No suite-to-execution path exists yet, so a retry policy cannot be honoured.",
            "timeout_policy": "No suite-to-execution path exists yet, so a timeout policy cannot be honoured.",
            "agent_pool": "No agent-pool entity exists.",
            "schedule": "No scheduler dispatches suite executions yet (P1-S7).",
        },
    }


async def create_execution_group(
    db: AsyncSession,
    suite: AutomationSuite,
    *,
    name: str,
    framework: str | None,
    environment: str | None,
    notes: str | None,
    actor_id: int,
) -> dict[str, Any]:
    _require_mutable(suite)
    group = await group_engine.create_group(
        db, suite, name=name, framework=framework, environment=environment, notes=notes, actor_id=actor_id
    )
    await _log_activity(
        db,
        suite=suite,
        event_type="execution_group_created",
        actor_id=actor_id,
        new_value={"group_id": group.id, "name": group.name},
    )
    await db.commit()
    await db.refresh(group)
    return {"id": group.id, "name": group.name, "sequence": group.sequence, "status": group.status}


async def assign_member_to_group(
    db: AsyncSession, suite: AutomationSuite, *, member_id: int, group_id: int | None, actor_id: int
) -> None:
    _require_mutable(suite)
    await _get_member_or_404(db, suite, member_id)
    if group_id is not None:
        await group_engine.get_group_or_404(db, suite, group_id)
    await group_engine.assign_members(db, suite, group_id=group_id, member_ids=[member_id])
    await _log_activity(
        db,
        suite=suite,
        event_type="execution_group_assigned",
        actor_id=actor_id,
        member_id=member_id,
        new_value={"execution_group_id": group_id},
    )
    await db.commit()


async def delete_execution_group(
    db: AsyncSession, suite: AutomationSuite, *, group_id: int, actor_id: int
) -> None:
    _require_mutable(suite)
    group = await group_engine.get_group_or_404(db, suite, group_id)
    name = group.name
    await group_engine.assign_members(
        db,
        suite,
        group_id=None,
        member_ids=[
            m.id for m in await _load_members(db, suite.id) if m.execution_group_id == group_id
        ],
    )
    await db.delete(group)
    await _log_activity(
        db,
        suite=suite,
        event_type="execution_group_deleted",
        actor_id=actor_id,
        old_value={"group_id": group_id, "name": name},
    )
    await db.commit()


# ─── Archive ──────────────────────────────────────────────────────────────────

async def archive_suite(db: AsyncSession, suite: AutomationSuite, *, actor_id: int) -> AutomationSuite:
    if suite.status == "ARCHIVED":
        raise AutomationSuiteError(409, "ALREADY_ARCHIVED", "This suite is already archived.")
    suite.status = "ARCHIVED"
    suite.is_current = False
    suite.archived_by = actor_id
    suite.archived_at = datetime.now(timezone.utc)
    await _log_activity(db, suite=suite, event_type="suite_archived", actor_id=actor_id)
    await db.commit()
    await db.refresh(suite)
    return suite


# ─── Read models for the detail tabs ──────────────────────────────────────────

async def compute_suite_overview(db: AsyncSession, suite: AutomationSuite) -> dict[str, Any]:
    members = await _load_members(db, suite.id)
    suite_inh = await inheritance_engine.resolve_suite_inheritance(db, suite=suite, members=members)
    included = [m for m in suite_inh.members if m.is_included]

    applications = {m.application.id for m in included if m.application}
    frameworks = sorted({f for m in included for f in m.frameworks})
    scripts = sum(len(m.current_scripts) for m in included)
    automated = len([m for m in included if m.current_scripts])

    return {
        "suite_id": suite.id,
        "name": suite.name,
        "description": suite.description,
        "tags": list(suite.tags or []),
        "status": suite.status,
        "default_environment": suite.default_environment,
        "members_total": suite.members_total,
        "members_included": suite.members_included,
        "members_ready": suite.members_ready,
        "members_blocked": suite.members_blocked,
        "members_manual_only": suite.members_manual_only,
        "members_drifted": suite.members_drifted,
        "gaps_critical_open": suite.gaps_critical_open,
        "gaps_warning_open": suite.gaps_warning_open,
        "conflicts_open": suite.conflicts_open,
        "automated_members": automated,
        "automation_coverage_pct": round(100 * automated / len(included)) if included else 0,
        "inherited_application_count": len(applications),
        "inherited_frameworks": frameworks,
        "linked_script_count": scripts,
        "last_evaluated_at": suite.last_evaluated_at,
        "last_inheritance_sync_at": suite.last_inheritance_sync_at,
        "execution_group_count": (
            await db.execute(
                select(func.count())
                .select_from(AutomationSuiteExecutionGroup)
                .where(AutomationSuiteExecutionGroup.suite_id == suite.id)
            )
        ).scalar()
        or 0,
        # Approval audit — real once the suite enters the review workflow.
        "submitted_by": suite.submitted_by,
        "submitted_at": suite.submitted_at,
        "reviewed_by": suite.reviewed_by,
        "approved_by": suite.approved_by,
        "approved_at": suite.approved_at,
        "published_by": suite.published_by,
        "published_at": suite.published_at,
        "decision_reason": suite.decision_reason,
        # Still no source for this one.
        "validation_summary": None,
        "unavailable": {
            "validation_summary": "No validation subsystem exists yet (UI-023 Validation and Review).",
        },
    }


async def get_inherited_scope(db: AsyncSession, suite: AutomationSuite) -> dict[str, Any]:
    """Read-only inherited sections, each item carrying its source."""
    members = await _load_members(db, suite.id)
    suite_inh = await inheritance_engine.resolve_suite_inheritance(db, suite=suite, members=members)
    included = [m for m in suite_inh.members if m.member.inclusion_status != "excluded"]

    business: list[dict[str, Any]] = []
    applications: dict[int, dict[str, Any]] = {}
    frameworks: dict[str, dict[str, Any]] = {}
    scripts: list[dict[str, Any]] = []
    environments: dict[str, dict[str, Any]] = {}
    test_data: list[dict[str, Any]] = []

    for m in included:
        tc = m.test_case
        if tc is not None:
            business.append(
                {
                    "test_case_id": tc.id,
                    "test_case_reference": tc.test_case_id,
                    "title": tc.title,
                    "requirement_id": tc.requirement_id,
                    "linked_release_version": tc.linked_release_version,
                    "linked_test_plan_id": tc.linked_test_plan_id,
                    "source": f"Inherited from {tc.test_case_id or f'TC-{tc.id}'}",
                    "source_entity": "test_case",
                    "source_id": tc.id,
                }
            )
        if m.application is not None:
            applications.setdefault(
                m.application.id,
                {
                    "application_id": m.application.id,
                    "key": m.application.key,
                    "name": m.application.name,
                    "application_type": m.application.application_type,
                    "lifecycle_status": m.application.lifecycle_status,
                    "model_id": m.model.id if m.model else None,
                    "model_status": m.model.status if m.model else None,
                    "model_version": m.model.version if m.model else None,
                    "model_is_stale": m.model_is_stale,
                    "source": f"Inherited from {m.application.name} Application Model",
                    "source_entity": "project_application",
                    "source_id": m.application.id,
                    "test_case_count": 0,
                },
            )
            applications[m.application.id]["test_case_count"] += 1
        for script in m.current_scripts:
            scripts.append(
                {
                    "script_id": script.id,
                    "script_reference": script.script_id,
                    "framework": script.framework,
                    "file_path": script.file_path,
                    "status": script.status,
                    "version": script.version,
                    "test_case_id": m.test_case_id,
                    "source": f"Inherited from {script.script_id or script.file_path or f'script {script.id}'}",
                    "source_entity": "automation_script",
                    "source_id": script.id,
                }
            )
            if script.framework:
                frameworks.setdefault(
                    script.framework,
                    {
                        # No framework_profile entity exists (UI-022, P2-S3),
                        # so this is the plain string from the script, and the
                        # source names the script rather than a profile.
                        "framework": script.framework,
                        "profile_id": None,
                        "profile_version": None,
                        "script_count": 0,
                        "source": f"Derived from linked script framework '{script.framework}'",
                        "source_entity": "automation_script",
                    },
                )
                frameworks[script.framework]["script_count"] += 1
        if m.resolved_environment:
            environments.setdefault(
                m.resolved_environment,
                {
                    "environment": m.resolved_environment,
                    "source": "Suite default environment",
                    "source_entity": "automation_suite",
                    "source_id": suite.id,
                    "url_configured": bool(
                        m.application and (m.application.environment_urls or {}).get(m.resolved_environment)
                    ),
                    "test_case_count": 0,
                },
            )
            environments[m.resolved_environment]["test_case_count"] += 1
        for td in m.test_data:
            test_data.append(
                {
                    "test_data_id": td.id,
                    "reference": td.data_id,
                    "name": td.name,
                    "environment": td.environment,
                    "approval_status": td.approval_status,
                    "test_case_id": m.test_case_id,
                    "source": f"Inherited from {td.data_id or f'test data {td.id}'}",
                    "source_entity": "test_data",
                    "source_id": td.id,
                }
            )

    return {
        "business_traceability": business,
        "applications": list(applications.values()),
        "frameworks": list(frameworks.values()),
        "scripts": scripts,
        "environments": list(environments.values()),
        "test_data": test_data,
        "owners": [
            {
                "role": "Suite owner",
                "user_id": suite.owner_id,
                "source": "Derived from the suite creator",
                "source_entity": "user",
                "source_id": suite.owner_id,
            }
        ],
        "last_synchronized_at": suite.last_inheritance_sync_at,
        # Sections the contract asks for whose source entity does not exist.
        "unavailable": {
            "automation_ir": "No Automation IR entity exists yet (UI-020 Automation IR Editor).",
            "framework_profiles": "No Framework Profile entity exists yet (UI-022 Framework Configuration, P2-S3).",
            "change_requests": "This platform has no change-request entity.",
            "releases": "Releases are a free-text field on the test case, not a linked entity.",
            "page_objects": "No page-object entity exists yet.",
            "api_collections": "No API-collection entity exists yet.",
            "agents_and_device_matrices": "No agent-pool or device-matrix entity exists yet.",
        },
    }


async def member_grounding(db: AsyncSession, suite: AutomationSuite, member_id: int) -> list[dict[str, Any]]:
    from app.services.automation_suite import grounding as grounding_engine

    member = await _get_member_or_404(db, suite, member_id)
    suite_inh = await inheritance_engine.resolve_suite_inheritance(db, suite=suite, members=[member])
    if not suite_inh.members:
        return []
    member_inh = suite_inh.members[0]
    return await grounding_engine.build_grounding_matrix(
        db, test_case=member_inh.test_case, model=member_inh.model
    )


async def list_activity(
    db: AsyncSession, suite: AutomationSuite, *, page: int = 1, page_size: int = 50
) -> dict[str, Any]:
    total = (
        await db.execute(
            select(func.count()).select_from(AutomationSuiteActivity).where(AutomationSuiteActivity.suite_id == suite.id)
        )
    ).scalar() or 0
    result = await db.execute(
        select(AutomationSuiteActivity)
        .where(AutomationSuiteActivity.suite_id == suite.id)
        .order_by(AutomationSuiteActivity.created_at.desc(), AutomationSuiteActivity.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return _paginated(list(result.scalars().all()), total=total, page=page, page_size=page_size)


# ─── Suite list ───────────────────────────────────────────────────────────────

async def list_suites(
    db: AsyncSession,
    *,
    project_id: int,
    search: str | None = None,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "updated_desc",
) -> dict[str, Any]:
    filters = [AutomationSuite.project_id == project_id]
    if status_filter:
        filters.append(AutomationSuite.status == status_filter)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(or_(AutomationSuite.name.ilike(pattern), AutomationSuite.description.ilike(pattern)))

    total = (await db.execute(select(func.count()).select_from(AutomationSuite).where(*filters))).scalar() or 0

    order = {
        "updated_desc": AutomationSuite.updated_at.desc(),
        "updated_asc": AutomationSuite.updated_at.asc(),
        "name_asc": AutomationSuite.name.asc(),
        "name_desc": AutomationSuite.name.desc(),
    }.get(sort, AutomationSuite.updated_at.desc())

    result = await db.execute(
        select(AutomationSuite).where(*filters).order_by(order).offset((page - 1) * page_size).limit(page_size)
    )
    suites = list(result.scalars().all())

    # One extra query for the whole page's inherited badges rather than one
    # per row.
    frameworks_by_suite: dict[int, list[str]] = {}
    applications_by_suite: dict[int, int] = {}
    if suites:
        suite_ids = [s.id for s in suites]
        rows = await db.execute(
            select(
                AutomationSuiteTestCase.suite_id,
                AutomationSuiteTestCase.resolved_framework,
                AutomationSuiteTestCase.resolved_application_id,
            ).where(
                AutomationSuiteTestCase.suite_id.in_(suite_ids),
                AutomationSuiteTestCase.inclusion_status == "included",
            )
        )
        seen_apps: dict[int, set[int]] = {}
        seen_frameworks: dict[int, set[str]] = {}
        for suite_id, framework, application_id in rows.all():
            if framework:
                seen_frameworks.setdefault(suite_id, set()).add(framework)
            if application_id:
                seen_apps.setdefault(suite_id, set()).add(application_id)
        frameworks_by_suite = {k: sorted(v) for k, v in seen_frameworks.items()}
        applications_by_suite = {k: len(v) for k, v in seen_apps.items()}

    items = [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "tags": list(s.tags or []),
            "status": s.status,
            # A version chain reuses the name, so the list has to show which
            # version each row is or the rows are indistinguishable.
            "version": s.version,
            "is_current": s.is_current,
            "default_environment": s.default_environment,
            "members_total": s.members_total,
            "members_included": s.members_included,
            "members_ready": s.members_ready,
            "members_blocked": s.members_blocked,
            "members_manual_only": s.members_manual_only,
            "members_drifted": s.members_drifted,
            "gaps_critical_open": s.gaps_critical_open,
            "gaps_warning_open": s.gaps_warning_open,
            "conflicts_open": s.conflicts_open,
            "frameworks": frameworks_by_suite.get(s.id, []),
            "application_count": applications_by_suite.get(s.id, 0),
            "owner_id": s.owner_id,
            "last_evaluated_at": s.last_evaluated_at,
            "updated_at": s.updated_at,
            "created_at": s.created_at,
        }
        for s in suites
    ]
    return _paginated(items, total=total, page=page, page_size=page_size)


# ─── Wizard step 1: selectable test cases ─────────────────────────────────────

async def list_selectable_test_cases(
    db: AsyncSession,
    *,
    project_id: int,
    search: str | None = None,
    status_filter: str | None = None,
    automation_status: str | None = None,
    execution_mode: str | None = None,
    automation_candidate: bool | None = None,
    test_type: str | None = None,
    priority: str | None = None,
    is_critical: bool | None = None,
    application_id: int | None = None,
    requirement_id: int | None = None,
    test_suite_id: int | None = None,
    framework: str | None = None,
    has_script: bool | None = None,
    exclude_suite_id: int | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    """Server-side paginated. Never loads the whole project's test cases.

    Every filter maps to a real column. There is deliberately no environment
    filter (test cases carry no environment) and no change-request filter
    (this platform has no change-request entity) — offering either would be a
    control that cannot mean what it says.
    """
    filters = [TestCase.project_id == project_id, TestCase.is_deleted.is_(False)]
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                TestCase.test_case_id.ilike(pattern),
                TestCase.title.ilike(pattern),
                TestCase.test_case_objective.ilike(pattern),
            )
        )
    if status_filter:
        filters.append(TestCase.status == status_filter)
    if automation_status:
        filters.append(TestCase.automation_status == automation_status)
    if execution_mode:
        filters.append(TestCase.execution_mode == execution_mode)
    if automation_candidate is not None:
        filters.append(TestCase.automation_candidate.is_(automation_candidate))
    if test_type:
        filters.append(TestCase.test_type == test_type)
    if priority:
        filters.append(TestCase.priority == priority)
    if is_critical is not None:
        filters.append(TestCase.is_critical.is_(is_critical))
    if application_id is not None:
        filters.append(TestCase.application_id == application_id)
    if requirement_id is not None:
        filters.append(TestCase.requirement_id == requirement_id)
    if test_suite_id is not None:
        filters.append(TestCase.test_suite_id == test_suite_id)

    if framework or has_script is not None:
        script_exists = select(AutomationScript.id).where(AutomationScript.test_case_id == TestCase.id)
        if framework:
            script_exists = script_exists.where(AutomationScript.framework == framework)
        if has_script is False:
            filters.append(~script_exists.exists())
        else:
            filters.append(script_exists.exists())

    if exclude_suite_id is not None:
        member_exists = select(AutomationSuiteTestCase.id).where(
            AutomationSuiteTestCase.suite_id == exclude_suite_id,
            AutomationSuiteTestCase.test_case_id == TestCase.id,
        )
        filters.append(~member_exists.exists())

    total = (await db.execute(select(func.count()).select_from(TestCase).where(*filters))).scalar() or 0
    result = await db.execute(
        select(TestCase)
        .where(*filters)
        .order_by(TestCase.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    test_cases = list(result.scalars().all())

    # Linked-asset counts for this page only.
    scripts_by_tc: dict[int, list[AutomationScript]] = {}
    if test_cases:
        script_rows = await db.execute(
            select(AutomationScript).where(AutomationScript.test_case_id.in_([tc.id for tc in test_cases]))
        )
        for script in script_rows.scalars().all():
            scripts_by_tc.setdefault(script.test_case_id, []).append(script)

    items = []
    for tc in test_cases:
        scripts = scripts_by_tc.get(tc.id, [])
        items.append(
            {
                "id": tc.id,
                "test_case_reference": tc.test_case_id,
                "title": tc.title,
                "objective": tc.test_case_objective,
                "status": tc.status,
                "test_type": tc.test_type,
                "priority": tc.priority,
                "is_critical": tc.is_critical,
                "execution_mode": tc.execution_mode,
                "automation_status": tc.automation_status,
                "automation_candidate": tc.automation_candidate,
                "application_id": tc.application_id,
                "requirement_id": tc.requirement_id,
                "test_suite_id": tc.test_suite_id,
                "linked_release_version": tc.linked_release_version,
                "linked_script_count": len(scripts),
                "frameworks": sorted({s.framework for s in scripts if s.framework}),
                "mapping_status": "MAPPED" if tc.application_id else "APPLICATION_UNMAPPED",
            }
        )
    return _paginated(items, total=total, page=page, page_size=page_size)


async def preview_inheritance(
    db: AsyncSession, *, project_id: int, test_case_ids: list[int], default_environment: str | None
) -> dict[str, Any]:
    """Wizard summary panel. Reads only; writes nothing."""
    if len(test_case_ids) > get_settings().automation_suite_max_members:
        raise AutomationSuiteError(
            422,
            "SUITE_TOO_LARGE",
            f"A suite is limited to {get_settings().automation_suite_max_members} test cases.",
        )
    suite_inh = await inheritance_engine.resolve_preview_inheritance(
        db, project_id=project_id, test_case_ids=test_case_ids, default_environment=default_environment
    )

    detected: list[gap_engine.DetectedGap] = []
    for member_inh in suite_inh.evaluable:
        detected.extend(
            readiness_engine.evaluate_member(member_inh, capability_status=suite_inh.capability_status).gaps
        )
    detected.extend(conflict_engine.detect_cross_member_conflicts(suite_inh))

    members = suite_inh.members
    applications = {m.application.id for m in members if m.application}
    frameworks = sorted({f for m in members for f in m.frameworks})
    environments = sorted({m.resolved_environment for m in members if m.resolved_environment})
    requirements = {m.test_case.requirement_id for m in members if m.test_case and m.test_case.requirement_id}
    scripts = sum(len(m.current_scripts) for m in members)
    test_data = sum(len(m.test_data) for m in members)
    recordings = sum(len(m.recordings) for m in members)

    return {
        "selected_test_cases": len(members),
        "applications": len(applications),
        "frameworks": frameworks,
        "existing_scripts": scripts,
        "recordings": recordings,
        "environments": environments,
        "test_data_sources": test_data,
        "requirements": len(requirements),
        "missing_mappings": len([g for g in detected if g.category == "gap" and g.severity == "critical"]),
        "warnings": len([g for g in detected if g.category == "gap" and g.severity == "warning"]),
        "conflicts": len([g for g in detected if g.category == "conflict"]),
        "blocking_conflicts": len([g for g in detected if g.category == "conflict" and g.severity == "critical"]),
        "findings": [
            {
                "gap_type": g.gap_type,
                "scope": g.scope,
                "category": g.category,
                "severity": g.severity,
                "stage": g.stage,
                "reason": g.reason,
                "remediation": g.remediation,
                "test_case_id": g.test_case_id,
            }
            for g in detected
        ],
        # Counts the contract's summary panel lists that have no source here.
        "automation_ir_definitions": None,
        "defects": None,
        "change_requests": None,
        "execution_groups": None,
        "business_projects": 1,
        "unavailable": {
            "automation_ir_definitions": "No Automation IR entity exists yet (UI-020).",
            "defects": "Defects link to executions, not to test cases selected for a suite.",
            "change_requests": "This platform has no change-request entity.",
            "execution_groups": "Execution groups arrive with Phase B.",
            "business_projects": "A suite is scoped to one project, so this is the project itself, not a count.",
        },
    }
