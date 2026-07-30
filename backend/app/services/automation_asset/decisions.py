"""UI-020/021/023 — persisting autonomy verdicts and the governed human gate.

Two things live here and nothing else: writing the insert-only decision record,
and moving the two state axes on a suite member. All judgement happens in
`autonomy.py`; all reading happens in `evidence.py`.

The separation-of-duty rule reuses the same error code UI-018 already raises
(`SEPARATION_OF_DUTY_VIOLATION`) so governance reads identically across the
Application Model, the Automation Suite and an individual automation asset.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.automation_asset_decision import (
    REASON_REQUIRED_DECISIONS,
    AutomationAssetDecision,
)
from app.models.automation_suite import (
    APPROVAL_OWNED_STATES,
    AutomationSuite,
    AutomationSuiteTestCase,
)
from app.services.automation_asset import evidence as evidence_engine
from app.services.automation_asset.autonomy import (
    AutonomyPolicy,
    AutonomyVerdict,
    evaluate,
    next_autonomy_state,
)
from app.services.automation_suite.errors import AutomationSuiteError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def policy_from_settings() -> AutonomyPolicy:
    """The rubric currently in force.

    Read once per evaluation and then carried by value, so a decision record can
    be reproduced exactly from its own stored fields even after these settings
    change.
    """
    settings = get_settings()
    return AutonomyPolicy(
        rubric_id=settings.automation_autonomy_rubric_id,
        threshold=settings.automation_ai_approval_threshold,
        min_passing_dry_runs=settings.automation_min_passing_dry_runs,
        enabled=settings.automation_autonomy_enabled,
    )


def _model_versions() -> dict:
    """Model/prompt identity in force at decision time.

    Recorded by value on every decision. Empty rather than guessed when the
    project has no LLM settings resolved — an invented version string in an
    audit record is worse than an absent one.
    """
    settings = get_settings()
    versions: dict[str, str] = {}
    for attr, key in (
        ("default_llm_provider", "llm_provider"),
        ("default_llm_model", "llm_model"),
    ):
        value = getattr(settings, attr, None)
        if value:
            versions[key] = str(value)
    return versions


async def record_decision(
    db: AsyncSession,
    member: AutomationSuiteTestCase,
    *,
    project_id: int,
    decision: str,
    verdict: AutonomyVerdict,
    ir_draft_id: int | None = None,
    script_id: int | None = None,
    decided_by: int | None = None,
    reason: str | None = None,
) -> AutomationAssetDecision:
    """Insert one immutable decision row. Never updates an existing one."""
    if decision in REASON_REQUIRED_DECISIONS and not (reason or "").strip():
        raise AutomationSuiteError(
            422, "REASON_REQUIRED", f"A reason is required to record a {decision} decision."
        )

    row = AutomationAssetDecision(
        project_id=project_id,
        suite_test_case_id=member.id,
        ir_draft_id=ir_draft_id,
        script_id=script_id,
        decision=decision,
        decided_by=decided_by,
        rubric_id=verdict.rubric_id,
        threshold=verdict.threshold,
        score=verdict.score,
        dimensions=dict(verdict.dimensions),
        preconditions=[p.as_dict() for p in verdict.preconditions],
        model_versions=_model_versions(),
        reason=reason,
    )
    db.add(row)
    await db.flush()
    return row


async def evaluate_member(
    db: AsyncSession,
    member: AutomationSuiteTestCase,
    suite: AutomationSuite,
    *,
    record: bool = True,
) -> tuple[AutonomyVerdict, AutomationAssetDecision | None]:
    """Evaluate one member and persist the resulting autonomy state.

    Honours the approval-owned guard: once a human has ruled, the score is
    refreshed for display but `autonomy_state` is left exactly as it was. A
    decision row is written only when the state actually changes, so
    re-evaluation does not fill the audit trail with identical verdicts.
    """
    policy = policy_from_settings()
    asset_evidence, draft, script = await evidence_engine.gather(db, member, suite)
    verdict = evaluate(asset_evidence, policy)

    previous = member.autonomy_state
    resolved = next_autonomy_state(
        current_autonomy_state=member.autonomy_state,
        current_approval_state=member.approval_state,
        verdict=verdict,
    )

    decision_row = None
    if resolved != previous:
        member.autonomy_state = resolved
        if record and resolved in ("AI_APPROVED", "AI_HELD"):
            decision_row = await record_decision(
                db,
                member,
                project_id=suite.project_id,
                decision=resolved,
                verdict=verdict,
                ir_draft_id=draft.id if draft else None,
                script_id=script.id if script else None,
                decided_by=None,  # machine
            )
    return verdict, decision_row


async def _blocked_approver_ids(
    db: AsyncSession, member: AutomationSuiteTestCase, suite: AutomationSuite
) -> set[int]:
    """Identities that may not give final approval on this asset.

    Whoever produced the artifact cannot also sign it off. Covers both the IR
    draft's generator and the script's author, because either is "the person who
    made this thing".
    """
    blocked: set[int] = set()
    _, draft, script = await evidence_engine.gather(db, member, suite)
    if draft is not None and draft.generated_by:
        blocked.add(draft.generated_by)
    if script is not None and script.created_by:
        blocked.add(script.created_by)
    return blocked


async def final_approve(
    db: AsyncSession,
    member: AutomationSuiteTestCase,
    suite: AutomationSuite,
    *,
    actor_id: int,
    approve: bool,
    reason: str | None = None,
) -> AutomationAssetDecision:
    """The one governed human gate (contract Section 13.5).

    Enforces separation of duty and, on approval, that nothing blocking remains.
    Rejection requires a reason and is always permitted, because a reviewer must
    be able to refuse an asset whose findings the machine considered acceptable.
    """
    if member.approval_state in APPROVAL_OWNED_STATES:
        raise AutomationSuiteError(
            409,
            "ALREADY_DECIDED",
            f"This asset is already {member.approval_state}. Open a new version to change it.",
        )

    if approve:
        blocked = await _blocked_approver_ids(db, member, suite)
        if actor_id in blocked:
            raise AutomationSuiteError(
                409,
                "SEPARATION_OF_DUTY_VIOLATION",
                "The user who generated or authored this automation asset cannot "
                "also give it final approval.",
            )

    policy = policy_from_settings()
    asset_evidence, draft, script = await evidence_engine.gather(db, member, suite)
    verdict = evaluate(asset_evidence, policy)

    if approve:
        unmet_blocking = [
            p for p in verdict.preconditions if not p.met and p.code == "STATIC_GATE_CLEAN"
        ]
        if unmet_blocking:
            raise AutomationSuiteError(
                409,
                "BLOCKING_FINDINGS_PRESENT",
                "This asset has blocking validation findings and cannot be approved: "
                + unmet_blocking[0].detail,
            )

    member.approval_state = "FINAL_APPROVED" if approve else "REJECTED"
    return await record_decision(
        db,
        member,
        project_id=suite.project_id,
        decision="FINAL_APPROVED" if approve else "REJECTED",
        verdict=verdict,
        ir_draft_id=draft.id if draft else None,
        script_id=script.id if script else None,
        decided_by=actor_id,
        reason=reason,
    )


async def pending_final_approval(
    db: AsyncSession, suite_id: int
) -> list[AutomationSuiteTestCase]:
    """The aging queue (contract Section 16).

    Deferred human review is only safe if the backlog is visible; without this
    an AI-approved asset can sit unreviewed indefinitely and the audit trail
    proves nothing.
    """
    result = await db.execute(
        select(AutomationSuiteTestCase)
        .where(
            AutomationSuiteTestCase.suite_id == suite_id,
            AutomationSuiteTestCase.autonomy_state == "AI_APPROVED",
            AutomationSuiteTestCase.approval_state == "PENDING_FINAL",
        )
        .order_by(AutomationSuiteTestCase.id)
    )
    return list(result.scalars().all())


async def members_lacking_final_approval(
    db: AsyncSession, suite_id: int
) -> list[AutomationSuiteTestCase]:
    """Publish preflight (contract Section 16).

    Publication is the hard line: an AI-approved asset flows freely up to it,
    and cannot cross it without a human record.
    """
    result = await db.execute(
        select(AutomationSuiteTestCase)
        .where(
            AutomationSuiteTestCase.suite_id == suite_id,
            AutomationSuiteTestCase.inclusion_status == "included",
            AutomationSuiteTestCase.approval_state != "FINAL_APPROVED",
        )
        .order_by(AutomationSuiteTestCase.id)
    )
    return list(result.scalars().all())
