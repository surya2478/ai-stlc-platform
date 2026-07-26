"""Suite rollup and deterministic status — pure functions.

The suite's `status` column is a cache of `compute_suite_status`; it is never
set by hand. Precedence answers "what does this suite need next": fix what is
missing, then reconcile members against each other, then re-sync against
sources.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.automation_suite.gaps import DetectedGap
from app.services.automation_suite.inheritance import MemberInheritance


@dataclass(frozen=True)
class SuiteRollup:
    members_total: int = 0
    members_included: int = 0
    members_ready: int = 0
    members_blocked: int = 0
    members_manual_only: int = 0
    members_drifted: int = 0
    gaps_critical_open: int = 0
    gaps_warning_open: int = 0
    conflicts_open: int = 0
    # Only criticals gate the status; the total is what the UI badges.
    conflicts_critical_open: int = 0
    evaluated: bool = False
    archived: bool = False


def compute_rollup(
    *,
    members: list[MemberInheritance],
    member_statuses: dict[int, str],
    blocking_gaps: list[DetectedGap],
    evaluated: bool,
    archived: bool = False,
) -> SuiteRollup:
    included = [m for m in members if m.is_included]
    manual_only = [m for m in members if m.is_manual_only]
    ready = [m for m in included if member_statuses.get(m.member_id) == "READY"]
    blocked = [m for m in included if member_statuses.get(m.member_id) == "BLOCKED"]
    drifted = [m for m in members if m.drift_reasons]

    return SuiteRollup(
        members_total=len(members),
        members_included=len(included),
        members_ready=len(ready),
        members_blocked=len(blocked),
        members_manual_only=len(manual_only),
        members_drifted=len(drifted),
        gaps_critical_open=len([g for g in blocking_gaps if g.severity == "critical" and g.category == "gap"]),
        gaps_warning_open=len([g for g in blocking_gaps if g.severity == "warning" and g.category == "gap"]),
        conflicts_open=len([g for g in blocking_gaps if g.category == "conflict"]),
        conflicts_critical_open=len(
            [g for g in blocking_gaps if g.category == "conflict" and g.severity == "critical"]
        ),
        evaluated=evaluated,
        archived=archived,
    )


def compute_suite_status(rollup: SuiteRollup) -> str:
    if rollup.archived:
        return "ARCHIVED"
    # manual_only members are real scope, so they count as selected even
    # though they are not "included" for automation purposes.
    if rollup.members_included == 0 and rollup.members_manual_only == 0:
        return "DRAFT"
    if not rollup.evaluated:
        return "SCOPE_SELECTED"
    if rollup.gaps_critical_open > 0:
        return "MAPPING_INCOMPLETE"
    if rollup.conflicts_critical_open > 0:
        return "CONFLICT_REVIEW_REQUIRED"
    if rollup.members_drifted > 0:
        return "INHERITANCE_REVIEW_REQUIRED"
    return "READY_FOR_VALIDATION"
