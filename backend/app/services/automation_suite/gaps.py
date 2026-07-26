"""Gap detection payloads and the evaluation-to-persistence sync plan.

Re-evaluation **upserts by fingerprint and auto-closes what it no longer
detects — it never deletes.** The retired per-test-case engine wiped and
rebuilt its blockers on every pass, which was harmless only because a blocker
carried no human decision. A suite gap does: `exception_approved`,
`resolution_action`, `reviewer_notes` and `first_detected_at` are all
governance state, and deleting the row would silently discard an approved
waiver along with its audit trail.

A fingerprint must therefore be built from *stable* parts only. Counts and id
lists that churn on unrelated rebuilds are deliberately excluded — see
`_stable_key`.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_suite import AutomationSuite, AutomationSuiteGap


@dataclass(frozen=True)
class DetectedGap:
    """One finding from a single evaluation pass, not yet persisted."""

    gap_type: str
    scope: str  # member | suite
    category: str  # gap | conflict
    severity: str  # critical | warning
    stage: str
    reason: str
    remediation: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    # None for suite-scope findings.
    member_id: int | None = None
    test_case_id: int | None = None
    # Optional extra discriminator when one member can raise the same
    # gap_type more than once for genuinely different subjects.
    subject: str | None = None


def _stable_key(gap: DetectedGap) -> str:
    """The identity-bearing part of a fingerprint.

    Deliberately excludes churny evidence. `LOCATOR_MISSING`, for example,
    carries the list of Application Model gap ids in its evidence; that list
    changes every time the model is rebuilt, so keying on it would mint a new
    row per rebuild and orphan any approved exception. The gap's *subject*
    (this member's grounding is incomplete) is what persists, not the
    particular gap ids behind it.
    """
    return gap.subject or ""


def fingerprint(gap: DetectedGap) -> str:
    raw = f"{gap.gap_type}|{gap.scope}|{gap.member_id or ''}|{_stable_key(gap)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


@dataclass
class GapSyncPlan:
    to_insert: list[DetectedGap] = field(default_factory=list)
    # (existing row, freshly detected version of it)
    to_update: list[tuple[AutomationSuiteGap, DetectedGap]] = field(default_factory=list)
    to_reopen: list[tuple[AutomationSuiteGap, DetectedGap]] = field(default_factory=list)
    to_leave_adjudicated: list[tuple[AutomationSuiteGap, DetectedGap]] = field(default_factory=list)
    to_auto_close: list[AutomationSuiteGap] = field(default_factory=list)

    @property
    def blocking_fingerprints(self) -> set[str]:
        """Fingerprints that still count against readiness.

        A row a human resolved, waived or excluded does not block, which is
        what makes "approve exception" and "exclude test case" genuinely
        advance the suite's status.
        """
        blocking: set[str] = set()
        for gap in self.to_insert:
            blocking.add(fingerprint(gap))
        for row, _ in self.to_update + self.to_reopen:
            blocking.add(row.fingerprint)
        return blocking


# Human decisions. Re-detection must not silently overturn these.
_ADJUDICATED_STATUSES = ("exception_approved", "excluded")


def plan_gap_sync(existing: list[AutomationSuiteGap], detected: list[DetectedGap]) -> GapSyncPlan:
    plan = GapSyncPlan()
    by_fingerprint = {row.fingerprint: row for row in existing}
    detected_fingerprints: set[str] = set()

    for gap in detected:
        fp = fingerprint(gap)
        detected_fingerprints.add(fp)
        row = by_fingerprint.get(fp)
        if row is None:
            plan.to_insert.append(gap)
        elif row.status in _ADJUDICATED_STATUSES:
            plan.to_leave_adjudicated.append((row, gap))
        elif row.status == "resolved":
            # Auto-closed earlier and detected again, or a human marked it
            # resolved at source and it did not actually go away.
            plan.to_reopen.append((row, gap))
        else:
            plan.to_update.append((row, gap))

    for row in existing:
        if row.fingerprint not in detected_fingerprints and row.status == "open":
            plan.to_auto_close.append(row)

    return plan


async def apply_gap_sync(
    db: AsyncSession, *, suite: AutomationSuite, plan: GapSyncPlan, now: datetime | None = None
) -> None:
    stamp = now or datetime.now(timezone.utc)

    for gap in plan.to_insert:
        db.add(
            AutomationSuiteGap(
                suite_id=suite.id,
                suite_test_case_id=gap.member_id,
                test_case_id=gap.test_case_id,
                gap_type=gap.gap_type,
                scope=gap.scope,
                category=gap.category,
                severity=gap.severity,
                stage=gap.stage,
                reason=gap.reason,
                remediation=gap.remediation,
                evidence=gap.evidence,
                status="open",
                auto_closed=False,
                fingerprint=fingerprint(gap),
                first_detected_at=stamp,
                last_detected_at=stamp,
            )
        )

    for row, gap in plan.to_update:
        # Refresh the human-readable detail (counts, names) but never the
        # identity or the adjudication.
        row.reason = gap.reason
        row.remediation = gap.remediation
        row.evidence = gap.evidence
        row.severity = gap.severity
        row.last_detected_at = stamp

    for row, gap in plan.to_reopen:
        row.status = "open"
        row.auto_closed = False
        row.resolved_by = None
        row.resolved_at = None
        row.reason = gap.reason
        row.remediation = gap.remediation
        row.evidence = gap.evidence
        row.severity = gap.severity
        row.last_detected_at = stamp

    for row, _gap in plan.to_leave_adjudicated:
        row.last_detected_at = stamp

    for row in plan.to_auto_close:
        row.status = "resolved"
        row.auto_closed = True
        row.resolved_by = None
        row.resolved_at = stamp

    await db.flush()
