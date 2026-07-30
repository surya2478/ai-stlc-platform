"""Approval workflow, publication snapshots, versions and impact review (Phase B).

The transition rules and the separation-of-duty rule mirror
`application_model_service` exactly, so governance behaves the same way across
UI-016 and UI-018 rather than inventing a second dialect.

The load-bearing guarantee here is immutability: publishing writes an
`AutomationSuiteSnapshot` that is never updated afterwards. Impact review reads
the snapshot and compares it against live sources, so a test case or script
changing after publication produces a *finding* rather than silently rewriting
what was published.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalAction
from app.models.automation_suite import (
    AutomationSuite,
    AutomationSuiteExecutionGroup,
    AutomationSuiteGap,
    AutomationSuiteSnapshot,
    AutomationSuiteTestCase,
)
from app.services.automation_suite import inheritance as inheritance_engine
from app.services.automation_suite.errors import AutomationSuiteError
from app.services.automation_suite.gaps import DetectedGap

# A suite may only be submitted from a state the deterministic engine produced
# and judged clean enough to review.
SUBMITTABLE_STATUSES = ("READY_FOR_VALIDATION", "INHERITANCE_REVIEW_REQUIRED")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _log(db: AsyncSession, suite: AutomationSuite, event_type: str, actor_id: int, **kwargs: Any) -> None:
    from app.services.automation_suite.suite_service import _log_activity

    await _log_activity(db, suite=suite, event_type=event_type, actor_id=actor_id, **kwargs)


async def _open_critical_gaps(db: AsyncSession, suite: AutomationSuite) -> list[AutomationSuiteGap]:
    """Findings that still block, ignoring anything a human adjudicated."""
    result = await db.execute(
        select(AutomationSuiteGap).where(
            AutomationSuiteGap.suite_id == suite.id,
            AutomationSuiteGap.severity == "critical",
            AutomationSuiteGap.status == "open",
        )
    )
    return list(result.scalars().all())


async def _require_no_blocking_criticals(db: AsyncSession, suite: AutomationSuite, action: str) -> None:
    blocking = await _open_critical_gaps(db, suite)
    if blocking:
        raise AutomationSuiteError(
            409,
            "CRITICAL_GAP_OPEN",
            f"{len(blocking)} unresolved critical finding(s) must be resolved, excluded or waived before {action}.",
        )


# ─── Review workflow ──────────────────────────────────────────────────────────

async def submit_for_review(db: AsyncSession, suite: AutomationSuite, *, actor_id: int) -> AutomationSuite:
    if suite.status not in SUBMITTABLE_STATUSES:
        raise AutomationSuiteError(
            409,
            "INVALID_TRANSITION",
            f"Cannot submit a suite for review from '{suite.status}'. Resolve its findings first.",
        )
    await _require_no_blocking_criticals(db, suite, "submitting for review")

    members = (
        await db.execute(
            select(AutomationSuiteTestCase).where(
                AutomationSuiteTestCase.suite_id == suite.id,
                AutomationSuiteTestCase.inclusion_status != "excluded",
            )
        )
    ).scalars().all()
    if not list(members):
        raise AutomationSuiteError(
            409, "NO_MEMBERS", "A suite needs at least one included test case before review."
        )

    suite.status = "READY_FOR_REVIEW"
    suite.submitted_by = actor_id
    suite.submitted_at = _now()
    await _log(db, suite, "submitted_for_review", actor_id)
    await db.commit()
    await db.refresh(suite)
    return suite


async def request_changes(
    db: AsyncSession, suite: AutomationSuite, *, actor_id: int, reason: str
) -> AutomationSuite:
    if suite.status != "READY_FOR_REVIEW":
        raise AutomationSuiteError(
            409, "INVALID_TRANSITION", "Only a suite awaiting review can have changes requested."
        )
    if not (reason or "").strip():
        raise AutomationSuiteError(422, "REASON_REQUIRED", "Requesting changes requires a reason.")

    # Back to the deterministic engine's judgement, so the next evaluation owns
    # the status again.
    suite.status = "READY_FOR_VALIDATION"
    suite.reviewed_by = actor_id
    suite.reviewed_at = _now()
    suite.decision_reason = reason
    await _log(db, suite, "changes_requested", actor_id, reason=reason)
    await db.commit()
    await db.refresh(suite)
    return suite


async def reject(db: AsyncSession, suite: AutomationSuite, *, actor_id: int, reason: str) -> AutomationSuite:
    if suite.status != "READY_FOR_REVIEW":
        raise AutomationSuiteError(409, "INVALID_TRANSITION", "Only a suite awaiting review can be rejected.")
    if not (reason or "").strip():
        raise AutomationSuiteError(422, "REASON_REQUIRED", "Rejecting a suite requires a reason.")

    suite.status = "READY_FOR_VALIDATION"
    suite.reviewed_by = actor_id
    suite.reviewed_at = _now()
    suite.decision_reason = reason
    db.add(
        ApprovalAction(
            project_id=suite.project_id,
            user_id=actor_id,
            action_type="reject_automation_suite",
            entity_type="automation_suite",
            entity_id=suite.id,
            decision="rejected",
            notes=reason,
            correlation_id=suite.correlation_id,
        )
    )
    await _log(db, suite, "rejected", actor_id, reason=reason)
    await db.commit()
    await db.refresh(suite)
    return suite


async def approve(
    db: AsyncSession, suite: AutomationSuite, *, actor_id: int, reason: str | None = None
) -> AutomationSuite:
    if suite.status != "READY_FOR_REVIEW":
        raise AutomationSuiteError(409, "INVALID_TRANSITION", "Only a suite awaiting review can be approved.")
    # Same rule as UI-016: whoever assembled the scope cannot also clear it.
    if suite.submitted_by == actor_id:
        raise AutomationSuiteError(
            409,
            "SEPARATION_OF_DUTY_VIOLATION",
            "The user who submitted this suite for review cannot also approve it.",
        )
    await _require_no_blocking_criticals(db, suite, "approval")

    suite.status = "APPROVED"
    suite.approved_by = actor_id
    suite.approved_at = _now()
    if reason:
        suite.decision_reason = reason
    db.add(
        ApprovalAction(
            project_id=suite.project_id,
            user_id=actor_id,
            action_type="approve_automation_suite",
            entity_type="automation_suite",
            entity_id=suite.id,
            decision="approved",
            notes=reason,
            correlation_id=suite.correlation_id,
        )
    )
    await _log(db, suite, "approved", actor_id, reason=reason)
    await db.commit()
    await db.refresh(suite)
    return suite


# ─── Publication and snapshots ────────────────────────────────────────────────

def _canonical(members: list[dict[str, Any]]) -> str:
    return json.dumps(members, sort_keys=True, separators=(",", ":"), default=str)


def build_snapshot_payload(suite_inh: inheritance_engine.SuiteInheritance) -> tuple[list[dict[str, Any]], str]:
    """Freeze the resolved scope: source ids and versions, not editable values."""
    members: list[dict[str, Any]] = []
    for m in suite_inh.members:
        if m.member.inclusion_status == "excluded":
            continue
        script = m.primary_script
        members.append(
            {
                "member_id": m.member_id,
                "test_case_id": m.test_case_id,
                "test_case_version": (m.test_case.version if m.test_case else None),
                "inclusion_status": m.member.inclusion_status,
                "planned_sequence": m.member.planned_sequence,
                "execution_group_id": m.member.execution_group_id,
                "application_id": (m.application.id if m.application else None),
                "application_model_id": (m.model.id if m.model else None),
                "application_model_version": (m.model.version if m.model else None),
                "classification_id": (m.classification.id if m.classification else None),
                "script_id": (script.id if script else None),
                "script_version": (script.version if script else None),
                "framework": (script.framework if script else None),
                "environment": m.resolved_environment,
            }
        )
    members.sort(key=lambda r: r["member_id"])
    checksum = hashlib.sha256(_canonical(members).encode("utf-8")).hexdigest()
    return members, checksum


def _require_final_approval(members: list[AutomationSuiteTestCase]) -> None:
    """The hard line (UI-023 contract Section 16).

    An AI-approved asset flows freely through IR -> compile -> dry run ->
    validation. Publication is where that stops: it freezes an immutable
    snapshot, so it cannot be crossed without a human record. Deferred review is
    safe precisely because this line is not.

    Takes the member list `publish` has already loaded rather than issuing a
    second query, and filters in Python. Members that are excluded or
    manual-only are not automation assets and are not held to this.
    """
    lacking = [
        m
        for m in members
        if m.inclusion_status == "included"
        and getattr(m, "approval_state", "PENDING_FINAL") != "FINAL_APPROVED"
    ]
    if not lacking:
        return
    ids = ", ".join(f"#{m.id}" for m in lacking[:10])
    more = "" if len(lacking) <= 10 else f" and {len(lacking) - 10} more"
    raise AutomationSuiteError(
        409,
        "FINAL_APPROVAL_REQUIRED",
        f"{len(lacking)} member(s) have not been finally approved and cannot be "
        f"published: {ids}{more}.",
    )


async def publish(db: AsyncSession, suite: AutomationSuite, *, actor_id: int) -> AutomationSuite:
    if suite.status != "APPROVED":
        raise AutomationSuiteError(409, "INVALID_TRANSITION", "Only an approved suite can be published.")
    await _require_no_blocking_criticals(db, suite, "publication")

    members = list(
        (
            await db.execute(
                select(AutomationSuiteTestCase).where(AutomationSuiteTestCase.suite_id == suite.id)
            )
        )
        .scalars()
        .all()
    )
    # The hard line, checked against the members already loaded above.
    _require_final_approval(members)

    suite_inh = await inheritance_engine.resolve_suite_inheritance(db, suite=suite, members=members)
    payload, checksum = build_snapshot_payload(suite_inh)

    groups = list(
        (
            await db.execute(
                select(AutomationSuiteExecutionGroup)
                .where(AutomationSuiteExecutionGroup.suite_id == suite.id)
                .order_by(AutomationSuiteExecutionGroup.sequence)
            )
        )
        .scalars()
        .all()
    )

    db.add(
        AutomationSuiteSnapshot(
            suite_id=suite.id,
            suite_version=suite.version,
            members=payload,
            execution_groups=[
                {
                    "id": g.id,
                    "name": g.name,
                    "sequence": g.sequence,
                    "framework": g.framework,
                    "environment": g.environment,
                    "application_id": g.application_id,
                }
                for g in groups
            ],
            summary={
                "member_count": len(payload),
                "default_environment": suite.default_environment,
                "approved_by": suite.approved_by,
                "submitted_by": suite.submitted_by,
            },
            checksum=checksum,
            created_by=actor_id,
        )
    )

    # Supersede any previously published version of this suite chain.
    root_id = suite.parent_suite_id or suite.id
    prior = await db.execute(
        select(AutomationSuite).where(
            AutomationSuite.project_id == suite.project_id,
            AutomationSuite.status == "PUBLISHED",
            AutomationSuite.id != suite.id,
        )
    )
    for candidate in prior.scalars().all():
        if (candidate.parent_suite_id or candidate.id) == root_id:
            candidate.status = "DEPRECATED"
            candidate.is_current = False

    suite.status = "PUBLISHED"
    suite.published_by = actor_id
    suite.published_at = _now()
    suite.is_current = True
    await _log(
        db, suite, "published", actor_id, new_value={"suite_version": suite.version, "checksum": checksum}
    )
    db.add(
        ApprovalAction(
            project_id=suite.project_id,
            user_id=actor_id,
            action_type="publish_automation_suite",
            entity_type="automation_suite",
            entity_id=suite.id,
            decision="approved",
            notes=f"Published version {suite.version}",
            new_value={"checksum": checksum},
            correlation_id=suite.correlation_id,
        )
    )
    await db.commit()
    await db.refresh(suite)
    return suite


async def get_snapshot(db: AsyncSession, suite: AutomationSuite) -> AutomationSuiteSnapshot | None:
    result = await db.execute(
        select(AutomationSuiteSnapshot)
        .where(
            AutomationSuiteSnapshot.suite_id == suite.id,
            AutomationSuiteSnapshot.suite_version == suite.version,
        )
    )
    return result.scalars().first()


# ─── Versions ─────────────────────────────────────────────────────────────────

async def create_new_draft(db: AsyncSession, suite: AutomationSuite, *, actor_id: int) -> AutomationSuite:
    """Open a new editable version, leaving the published one frozen."""
    if suite.status not in ("APPROVED", "PUBLISHED", "DEPRECATED"):
        raise AutomationSuiteError(
            409,
            "INVALID_TRANSITION",
            "A new version can only be started from an approved, published or deprecated suite.",
        )

    new_suite = AutomationSuite(
        project_id=suite.project_id,
        name=suite.name,
        description=suite.description,
        tags=list(suite.tags or []),
        status="DRAFT",
        version=suite.version + 1,
        parent_suite_id=suite.parent_suite_id or suite.id,
        is_current=True,
        default_environment=suite.default_environment,
        owner_id=suite.owner_id,
        created_by=actor_id,
        correlation_id=suite.correlation_id,
    )
    # The published version stays queryable but is no longer the current one.
    suite.is_current = False
    db.add(new_suite)
    await db.flush()

    source_members = list(
        (
            await db.execute(
                select(AutomationSuiteTestCase).where(AutomationSuiteTestCase.suite_id == suite.id)
            )
        )
        .scalars()
        .all()
    )
    for member in source_members:
        db.add(
            AutomationSuiteTestCase(
                suite_id=new_suite.id,
                test_case_id=member.test_case_id,
                inclusion_status=member.inclusion_status,
                planned_sequence=member.planned_sequence,
                source_system=member.source_system,
                source_reference=member.source_reference,
                added_by=actor_id,
            )
        )
    await db.flush()

    await _log(
        db,
        new_suite,
        "new_version_created",
        actor_id,
        old_value={"from_suite_id": suite.id, "from_version": suite.version},
        new_value={"version": new_suite.version, "members_copied": len(source_members)},
    )
    await db.commit()
    await db.refresh(new_suite)
    return new_suite


async def list_versions(db: AsyncSession, suite: AutomationSuite) -> list[dict[str, Any]]:
    root_id = suite.parent_suite_id or suite.id
    result = await db.execute(
        select(AutomationSuite).where(AutomationSuite.project_id == suite.project_id)
    )
    chain = [
        s
        for s in result.scalars().all()
        if (s.parent_suite_id or s.id) == root_id
    ]
    chain.sort(key=lambda s: s.version, reverse=True)

    snapshots = {}
    if chain:
        snap_rows = await db.execute(
            select(AutomationSuiteSnapshot).where(
                AutomationSuiteSnapshot.suite_id.in_([s.id for s in chain])
            )
        )
        snapshots = {(s.suite_id, s.suite_version): s for s in snap_rows.scalars().all()}

    return [
        {
            "suite_id": s.id,
            "version": s.version,
            "status": s.status,
            "is_current": s.is_current,
            "submitted_by": s.submitted_by,
            "approved_by": s.approved_by,
            "published_by": s.published_by,
            "published_at": s.published_at,
            "decision_reason": s.decision_reason,
            "members_included": s.members_included,
            "snapshot_checksum": (
                snapshots[(s.id, s.version)].checksum if (s.id, s.version) in snapshots else None
            ),
            "created_at": s.created_at,
        }
        for s in chain
    ]


# ─── Impact review ────────────────────────────────────────────────────────────

async def detect_snapshot_drift(
    db: AsyncSession, suite: AutomationSuite
) -> tuple[list[DetectedGap], dict[str, Any]]:
    """Compare a published suite's frozen snapshot against live sources.

    Returns findings, never mutations: historical evidence and the snapshot
    itself are left exactly as published.
    """
    snapshot = await get_snapshot(db, suite)
    if snapshot is None:
        return [], {"snapshot": None, "reason": "This suite version has no publication snapshot."}

    members = list(
        (
            await db.execute(
                select(AutomationSuiteTestCase).where(AutomationSuiteTestCase.suite_id == suite.id)
            )
        )
        .scalars()
        .all()
    )
    suite_inh = await inheritance_engine.resolve_suite_inheritance(db, suite=suite, members=members)
    live_by_member = {m.member_id: m for m in suite_inh.members}

    findings: list[DetectedGap] = []
    changes: list[dict[str, Any]] = []

    for frozen in snapshot.members:
        member_id = frozen["member_id"]
        live = live_by_member.get(member_id)
        if live is None:
            reasons = ["The test case is no longer a member of this suite."]
        else:
            reasons = []
            live_tc_version = live.test_case.version if live.test_case else None
            if live.test_case is None or getattr(live.test_case, "is_deleted", False):
                reasons.append("The source test case has been deleted.")
            elif live_tc_version != frozen["test_case_version"]:
                reasons.append(
                    f"Test case version changed from {frozen['test_case_version']} to {live_tc_version}."
                )
            live_model_id = live.model.id if live.model else None
            if live_model_id != frozen["application_model_id"]:
                reasons.append("The current Application Model differs from the published one.")
            live_script = live.primary_script
            live_script_version = live_script.version if live_script else None
            if live_script_version != frozen["script_version"]:
                reasons.append(
                    f"Script version changed from {frozen['script_version']} to {live_script_version}."
                )
            if (live_script.framework if live_script else None) != frozen["framework"]:
                reasons.append("The resolved framework differs from the published one.")
            if live.resolved_environment != frozen["environment"]:
                reasons.append("The resolved environment differs from the published one.")

        if reasons:
            changes.append({"member_id": member_id, "test_case_id": frozen["test_case_id"], "reasons": reasons})
            findings.append(
                DetectedGap(
                    gap_type="SNAPSHOT_DRIFT",
                    scope="member",
                    category="gap",
                    severity="warning",
                    stage="approval_publish",
                    reason=" ".join(reasons),
                    remediation=(
                        "Start a new suite version to adopt the change. The published version and its "
                        "historical results stay unchanged."
                    ),
                    evidence={"published_version": snapshot.suite_version},
                    member_id=member_id if live is not None else None,
                    test_case_id=frozen["test_case_id"],
                    subject=f"snapshot:{snapshot.suite_version}",
                )
            )

    return findings, {
        "snapshot": {
            "suite_version": snapshot.suite_version,
            "checksum": snapshot.checksum,
            "member_count": len(snapshot.members),
            "created_at": snapshot.created_at,
        },
        "changed_members": changes,
        "impact_review_required": bool(changes),
    }
