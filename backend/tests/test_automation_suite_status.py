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


# ── Validation states are derived from the gate verdict ─────────────────────
#
# A passed Static Quality Gate used to map to "pending" alongside a missing
# one, so a fully validated member counted as still-in-validation and the suite
# sat in VALIDATION_PENDING — a status this module's own SUITE_REACHABLE_STATUSES
# excludes, because nothing exists to clear it. Observed on a real suite: every
# script passing its gate, zero open findings, and submission permanently
# refused with "Resolve its findings first" when there were none left.

from types import SimpleNamespace

from app.services.automation_suite.status import compute_rollup


def _member(member_id: int):
    return SimpleNamespace(
        member_id=member_id, is_included=True, is_manual_only=False, drift_reasons=[],
    )


def _rollup_for(states: dict[int, str], count: int = 2):
    members = [_member(i) for i in range(1, count + 1)]
    return compute_rollup(
        members=members,
        member_statuses={m.member_id: "READY" for m in members},
        blocking_gaps=[],
        evaluated=True,
        validation_states=states,
    )


def test_a_passed_gate_does_not_leave_a_member_in_validation():
    """The deadlock: nothing records a state for a member whose gate passed."""
    rollup = _rollup_for({})
    assert rollup.members_in_validation == 0
    assert compute_suite_status(rollup) == "READY_FOR_VALIDATION"


def test_a_member_never_gated_is_still_pending():
    rollup = _rollup_for({1: "pending"})
    assert rollup.members_in_validation == 1
    assert compute_suite_status(rollup) == "VALIDATION_PENDING"


def test_a_failed_gate_outranks_a_pending_one():
    """"Something is broken" is more actionable than "something is running"."""
    rollup = _rollup_for({1: "pending", 2: "failed"})
    assert compute_suite_status(rollup) == "VALIDATION_FAILED"


def test_a_suite_whose_scripts_all_passed_is_submittable():
    """End state of the bug — the status must be one submit_for_review accepts."""
    from app.services.automation_suite.lifecycle import SUBMITTABLE_STATUSES

    assert compute_suite_status(_rollup_for({})) in SUBMITTABLE_STATUSES


# ── Separation of duty is one deployment-wide policy ────────────────────────
#
# Relaxing it for Application Models left the identical gate on suite approval
# still enforcing, so a single-operator deployment cleared one blocker only to
# meet the next. One flag covers both.


def test_suite_and_model_approval_share_one_policy_flag():
    """A flag per gate leaves an operator hunting for the next one."""
    import inspect

    from app.config import Settings
    from app.services.application_model_service import approve as approve_model
    from app.services.automation_suite.lifecycle import approve as approve_suite

    assert Settings.model_fields["require_separate_approver"].default is True
    for fn in (approve_model, approve_suite):
        assert "require_separate_approver" in inspect.getsource(fn), (
            f"{fn.__module__}.{fn.__name__} does not honour the shared policy"
        )


def test_the_suite_refusal_names_the_flag():
    import inspect

    from app.services.automation_suite.lifecycle import approve as approve_suite

    assert "REQUIRE_SEPARATE_APPROVER=false" in inspect.getsource(approve_suite)
