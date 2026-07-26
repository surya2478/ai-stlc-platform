"""Suite status — table-driven over the reachable set and its precedence."""
import pytest

from app.models.automation_suite import (
    SUITE_REACHABLE_STATUSES,
    SUITE_STATUSES,
    WORKFLOW_OWNED_STATUSES,
)
from app.services.automation_suite.status import SuiteRollup, compute_suite_status

_UNREACHABLE = set(SUITE_STATUSES) - set(SUITE_REACHABLE_STATUSES)


@pytest.mark.parametrize(
    "rollup,expected",
    [
        (SuiteRollup(archived=True, members_included=3, evaluated=True), "ARCHIVED"),
        (SuiteRollup(), "DRAFT"),
        (SuiteRollup(members_total=2, members_included=0), "DRAFT"),
        (SuiteRollup(members_total=1, members_included=1, evaluated=False), "SCOPE_SELECTED"),
        (SuiteRollup(members_included=1, evaluated=True, gaps_critical_open=1), "MAPPING_INCOMPLETE"),
        (
            SuiteRollup(members_included=2, evaluated=True, conflicts_open=1, conflicts_critical_open=1),
            "CONFLICT_REVIEW_REQUIRED",
        ),
        (SuiteRollup(members_included=1, evaluated=True, members_drifted=1), "INHERITANCE_REVIEW_REQUIRED"),
        (SuiteRollup(members_included=1, evaluated=True), "READY_FOR_VALIDATION"),
        # A manual-only member is real scope, so the suite is past DRAFT.
        (SuiteRollup(members_total=1, members_manual_only=1, evaluated=True), "READY_FOR_VALIDATION"),
    ],
)
def test_status_for_rollup(rollup, expected):
    assert compute_suite_status(rollup) == expected


def test_archived_wins_over_everything():
    rollup = SuiteRollup(
        archived=True, members_included=5, evaluated=True, gaps_critical_open=3, conflicts_critical_open=2,
        members_drifted=4,
    )
    assert compute_suite_status(rollup) == "ARCHIVED"


def test_missing_mappings_outrank_conflicts_and_drift():
    rollup = SuiteRollup(
        members_included=3, evaluated=True, gaps_critical_open=1, conflicts_open=1, conflicts_critical_open=1,
        members_drifted=1,
    )
    assert compute_suite_status(rollup) == "MAPPING_INCOMPLETE"


def test_conflicts_outrank_drift():
    rollup = SuiteRollup(
        members_included=3, evaluated=True, conflicts_open=1, conflicts_critical_open=1, members_drifted=1
    )
    assert compute_suite_status(rollup) == "CONFLICT_REVIEW_REQUIRED"


def test_warning_only_gaps_do_not_block_readiness():
    rollup = SuiteRollup(members_included=2, evaluated=True, gaps_warning_open=4)
    assert compute_suite_status(rollup) == "READY_FOR_VALIDATION"


def test_non_critical_conflicts_do_not_gate_the_status():
    rollup = SuiteRollup(members_included=2, evaluated=True, conflicts_open=2, conflicts_critical_open=0)
    assert compute_suite_status(rollup) == "READY_FOR_VALIDATION"


@pytest.mark.parametrize(
    "rollup",
    [
        SuiteRollup(),
        SuiteRollup(members_included=1, evaluated=True),
        SuiteRollup(members_included=1, evaluated=True, gaps_critical_open=2),
        SuiteRollup(members_included=1, evaluated=True, conflicts_critical_open=1, conflicts_open=1),
        SuiteRollup(members_included=1, evaluated=True, members_drifted=1),
        SuiteRollup(archived=True),
    ],
)
def test_never_produces_a_phase_b_status(rollup):
    """VALIDATION_*, READY_FOR_REVIEW, APPROVED, PUBLISHED, DEPRECATED are reserved."""
    assert compute_suite_status(rollup) not in _UNREACHABLE


def test_the_engine_produces_exactly_the_deterministic_statuses():
    """The workflow-owned statuses are decisions, not derivations.

    READY_FOR_REVIEW/APPROVED/PUBLISHED/DEPRECATED are set by the approval
    workflow, so this function must never produce them — otherwise an
    evaluation pass could silently undo an approval.
    """
    produced = {
        compute_suite_status(r)
        for r in [
            SuiteRollup(),
            SuiteRollup(members_included=1),
            SuiteRollup(members_included=1, evaluated=True, gaps_critical_open=1),
            SuiteRollup(members_included=1, evaluated=True, conflicts_critical_open=1),
            SuiteRollup(members_included=1, evaluated=True, members_drifted=1),
            SuiteRollup(members_included=1, evaluated=True),
            SuiteRollup(archived=True),
        ]
    }
    assert produced == {
        "DRAFT",
        "SCOPE_SELECTED",
        "MAPPING_INCOMPLETE",
        "CONFLICT_REVIEW_REQUIRED",
        "INHERITANCE_REVIEW_REQUIRED",
        "READY_FOR_VALIDATION",
        "ARCHIVED",
    }
    assert produced <= set(SUITE_REACHABLE_STATUSES)
    assert produced & set(WORKFLOW_OWNED_STATUSES) == {"ARCHIVED"}
