"""UI-023 Validation and Review — status precedence and waiver rules.

Acceptance criterion 21 says the suite must be able to reach VALIDATION_PENDING
and VALIDATION_FAILED with no migration. Both were reserved in the CHECK
constraint by migration 046; these tests prove the status engine can actually
produce them and that they sit in the right place in the precedence order.
"""
import pytest

from app.models.automation_suite import SUITE_STATUSES
from app.services.automation_suite.status import SuiteRollup, compute_suite_status


def rollup(**overrides) -> SuiteRollup:
    base = dict(
        members_total=2,
        members_included=2,
        members_ready=2,
        members_blocked=0,
        members_manual_only=0,
        members_drifted=0,
        gaps_critical_open=0,
        gaps_warning_open=0,
        conflicts_open=0,
        conflicts_critical_open=0,
        evaluated=True,
        archived=False,
    )
    base.update(overrides)
    return SuiteRollup(**base)


# ── The two reserved statuses are now reachable ──────────────────────────────


def test_validation_pending_is_reachable():
    assert compute_suite_status(rollup(members_in_validation=1)) == "VALIDATION_PENDING"


def test_validation_failed_is_reachable():
    assert compute_suite_status(rollup(members_validation_failed=1)) == "VALIDATION_FAILED"


def test_both_reserved_statuses_are_in_the_check_constraint():
    """They were reserved by migration 046 precisely so UI-023 needs no migration."""
    assert "VALIDATION_PENDING" in SUITE_STATUSES
    assert "VALIDATION_FAILED" in SUITE_STATUSES


def test_all_thirteen_statuses_are_now_producible_or_workflow_owned():
    """11 of 13 were reachable before UI-023; these two close the gap."""
    from app.models.automation_suite import WORKFLOW_OWNED_STATUSES

    computable = {
        compute_suite_status(rollup(archived=True)),
        compute_suite_status(rollup(members_included=0)),
        compute_suite_status(rollup(evaluated=False)),
        compute_suite_status(rollup(gaps_critical_open=1)),
        compute_suite_status(rollup(conflicts_critical_open=1)),
        compute_suite_status(rollup(members_drifted=1)),
        compute_suite_status(rollup(members_validation_failed=1)),
        compute_suite_status(rollup(members_in_validation=1)),
        compute_suite_status(rollup()),
    }
    assert computable | set(WORKFLOW_OWNED_STATUSES) == set(SUITE_STATUSES)


# ── Precedence ───────────────────────────────────────────────────────────────


def test_failure_outranks_pending():
    """"Something is broken" is more actionable than "something is in progress"."""
    status = compute_suite_status(rollup(members_in_validation=2, members_validation_failed=1))
    assert status == "VALIDATION_FAILED"


@pytest.mark.parametrize(
    "override,expected",
    [
        ({"gaps_critical_open": 1}, "MAPPING_INCOMPLETE"),
        ({"conflicts_critical_open": 1}, "CONFLICT_REVIEW_REQUIRED"),
        ({"members_drifted": 1}, "INHERITANCE_REVIEW_REQUIRED"),
    ],
)
def test_pre_existing_problems_still_outrank_validation(override, expected):
    """Validation states must not mask a mapping gap, a conflict or drift — those
    have to be fixed before validation means anything."""
    assert compute_suite_status(rollup(members_validation_failed=1, **override)) == expected


def test_no_validation_data_leaves_the_old_behaviour_untouched():
    """Every pre-UI-023 caller omits validation_states; the result must not move."""
    assert compute_suite_status(rollup()) == "READY_FOR_VALIDATION"


def test_archived_still_wins_over_everything():
    assert compute_suite_status(rollup(archived=True, members_validation_failed=3)) == "ARCHIVED"


# ── compute_rollup stays backward compatible ─────────────────────────────────


def test_compute_rollup_defaults_validation_counts_to_zero():
    from app.services.automation_suite.status import compute_rollup

    result = compute_rollup(
        members=[], member_statuses={}, blocking_gaps=[], evaluated=True
    )
    assert result.members_in_validation == 0
    assert result.members_validation_failed == 0


# ── Waiver rules ─────────────────────────────────────────────────────────────


def test_only_warnings_are_declared_waivable():
    """Contract Section 13.4: clearing a hard block is a change to the asset, not
    a review decision about it."""
    from app.services.automation_asset.validation_service import WAIVABLE_SEVERITY

    assert WAIVABLE_SEVERITY == "warn"
