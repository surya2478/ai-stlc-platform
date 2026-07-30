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
    # UI-023. Default 0 so every existing caller is unaffected: a suite whose
    # members have never been compiled has nothing to validate and keeps its
    # previous status exactly.
    #   in_validation  — member has a compiled script, so validation applies
    #   validation_failed — that script has blocking Static Quality Gate findings
    members_in_validation: int = 0
    members_validation_failed: int = 0


def compute_rollup(
    *,
    members: list[MemberInheritance],
    member_statuses: dict[int, str],
    blocking_gaps: list[DetectedGap],
    evaluated: bool,
    archived: bool = False,
    validation_states: dict[int, str] | None = None,
) -> SuiteRollup:
    """`validation_states` maps member_id -> "none" | "pending" | "failed".

    Optional and defaulting to empty so every pre-UI-023 caller behaves exactly
    as before: with no validation data the two new counts stay zero and the
    status precedence is unchanged.
    """
    included = [m for m in members if m.is_included]
    manual_only = [m for m in members if m.is_manual_only]
    ready = [m for m in included if member_statuses.get(m.member_id) == "READY"]
    blocked = [m for m in included if member_statuses.get(m.member_id) == "BLOCKED"]
    drifted = [m for m in members if m.drift_reasons]

    states = validation_states or {}
    in_validation = [m for m in included if states.get(m.member_id) == "pending"]
    validation_failed = [m for m in included if states.get(m.member_id) == "failed"]

    return SuiteRollup(
        members_total=len(members),
        members_included=len(included),
        members_ready=len(ready),
        members_blocked=len(blocked),
        members_manual_only=len(manual_only),
        members_drifted=len(drifted),
        members_in_validation=len(in_validation),
        members_validation_failed=len(validation_failed),
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
    # UI-023 (contract Section 17). Both values were reserved in the CHECK
    # constraint by migration 046 precisely for this, so no migration is needed
    # to reach them. A failure outranks pending: "something is broken" is more
    # actionable than "something is in progress".
    if rollup.members_validation_failed > 0:
        return "VALIDATION_FAILED"
    if rollup.members_in_validation > 0:
        return "VALIDATION_PENDING"
    return "READY_FOR_VALIDATION"
