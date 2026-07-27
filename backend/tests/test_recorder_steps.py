"""UI-019 step derivation — the left panel's status is computed, never stored.

The one behaviour worth pinning hardest: a step's status must follow what was
actually recorded against it. An early version counted an ACTIVE step as
covered, which reported 17% coverage on a recording that had captured nothing.
"""
from types import SimpleNamespace

import pytest

from app.services.recorder import steps as recorder_steps
from app.services.recorder.context import RecordingContext


def _context(*, source_steps=None, step_states=(), mappings=(), checkpoints=()):
    test_case = SimpleNamespace(steps=list(source_steps or []))
    return RecordingContext(
        session=SimpleNamespace(id=1, project_id=1),
        test_case=test_case,
        suite=None,
        member=None,
        application=None,
        application_model=None,
        actions=[],
        mappings=list(mappings),
        step_states=list(step_states),
        checkpoints=list(checkpoints),
    )


def _step(number, action="do a thing", expected=None):
    return {"step_number": number, "action": action, "expected_result": expected}


def _state(step_key, status="PENDING", **kwargs):
    return SimpleNamespace(
        step_key=step_key,
        status=status,
        source_step_index=kwargs.get("source_step_index"),
        parent_step_key=kwargs.get("parent_step_key"),
        discovered_label=kwargs.get("discovered_label"),
        skip_reason=kwargs.get("skip_reason"),
    )


def _mapping(action_id, step_key, *, excluded=False):
    return SimpleNamespace(
        action_id=action_id, step_key=step_key, excluded_from_ir=excluded, mapping_source="active_step"
    )


def _checkpoint(step_key, review_state="accepted"):
    return SimpleNamespace(step_key=step_key, review_state=review_state)


def test_steps_come_from_the_live_test_case():
    context = _context(source_steps=[_step(1, "Log in"), _step(2, "Search")])
    rows = recorder_steps.build_step_list(context)
    assert [r.step_key for r in rows] == ["1", "2"]
    assert [r.action_text for r in rows] == ["Log in", "Search"]
    assert all(r.status == "PENDING" for r in rows)


def test_recorded_when_actions_are_mapped():
    context = _context(source_steps=[_step(1)], mappings=[_mapping(10, "1"), _mapping(11, "1")])
    row = recorder_steps.build_step_list(context)[0]
    assert row.status == "RECORDED"
    assert row.recorded_action_count == 2


def test_expected_result_without_checkpoint_is_only_partially_recorded():
    context = _context(
        source_steps=[_step(1, expected="Results are shown")], mappings=[_mapping(10, "1")]
    )
    row = recorder_steps.build_step_list(context)[0]
    assert row.status == "PARTIALLY_RECORDED"
    assert "expected result" in row.status_reason


def test_accepted_checkpoint_completes_the_step():
    context = _context(
        source_steps=[_step(1, expected="Results are shown")],
        mappings=[_mapping(10, "1")],
        checkpoints=[_checkpoint("1", "accepted")],
    )
    assert recorder_steps.build_step_list(context)[0].status == "RECORDED"


def test_unreviewed_checkpoint_does_not_complete_the_step():
    context = _context(
        source_steps=[_step(1, expected="Results are shown")],
        mappings=[_mapping(10, "1")],
        checkpoints=[_checkpoint("1", "needs_review")],
    )
    assert recorder_steps.build_step_list(context)[0].status == "PARTIALLY_RECORDED"


def test_excluded_mapping_does_not_count_as_recorded():
    context = _context(source_steps=[_step(1)], mappings=[_mapping(10, "1", excluded=True)])
    row = recorder_steps.build_step_list(context)[0]
    assert row.recorded_action_count == 0
    assert row.status == "PENDING"


@pytest.mark.parametrize("stored", recorder_steps.USER_OWNED_STATES)
def test_user_decisions_survive_recomputation(stored):
    """Marking a step Skipped must not be undone by the next mapped action."""
    context = _context(
        source_steps=[_step(1)], step_states=[_state("1", stored)], mappings=[_mapping(10, "1")]
    )
    assert recorder_steps.build_step_list(context)[0].status == stored


def test_active_step_with_nothing_recorded_is_still_a_gap():
    """The regression this pins: an ACTIVE label is not evidence of coverage."""
    context = _context(source_steps=[_step(1), _step(2)], step_states=[_state("2", "ACTIVE")])
    gaps = recorder_steps.steps_without_actions(context)
    assert {row.step_key for row in gaps} == {"1", "2"}
    assert recorder_steps.steps_with_actions(context) == []


def test_skipped_step_is_not_reported_as_a_gap():
    context = _context(
        source_steps=[_step(1), _step(2)],
        step_states=[_state("1", "SKIPPED", skip_reason="Already logged in")],
    )
    assert [row.step_key for row in recorder_steps.steps_without_actions(context)] == ["2"]


def test_completed_step_with_no_actions_is_still_a_gap():
    context = _context(source_steps=[_step(1)], step_states=[_state("1", "COMPLETED")])
    assert [row.step_key for row in recorder_steps.steps_without_actions(context)] == ["1"]


def test_discovered_substeps_sort_under_their_parent():
    context = _context(
        source_steps=[_step(1), _step(2), _step(3)],
        step_states=[
            _state("2.2", parent_step_key="2", discovered_label="second"),
            _state("2.1", parent_step_key="2", discovered_label="first"),
        ],
    )
    assert [r.step_key for r in recorder_steps.build_step_list(context)] == ["1", "2", "2.1", "2.2", "3"]


def test_step_keys_are_positional_not_the_test_cases_own_numbering():
    """A test case numbering its steps 10/20/30 still gets keys 1/2/3 — see
    `step_key_for_index` for why identity cannot come from that field."""
    context = _context(source_steps=[_step(10), _step(20), _step(30)])
    assert [r.step_key for r in recorder_steps.build_step_list(context)] == ["1", "2", "3"]


def test_double_digit_step_keys_sort_numerically():
    context = _context(source_steps=[_step(n) for n in range(1, 12)])
    keys = [r.step_key for r in recorder_steps.build_step_list(context)]
    assert keys[-2:] == ["10", "11"]


def test_substep_key_allocation_skips_taken_keys():
    assert recorder_steps.next_substep_key("3", set()) == "3.1"
    assert recorder_steps.next_substep_key("3", {"3.1", "3.2"}) == "3.3"


def test_step_removed_from_the_test_case_stays_visible():
    """Its recorded actions are still mapped to it — hiding it would hide them."""
    context = _context(
        source_steps=[_step(1)],
        step_states=[_state("9", "RECORDED")],
        mappings=[_mapping(10, "9")],
    )
    assert "9" in {row.step_key for row in recorder_steps.build_step_list(context)}


def test_active_step_prefers_the_explicit_one():
    context = _context(source_steps=[_step(1), _step(2)], step_states=[_state("2", "ACTIVE")])
    assert recorder_steps.active_step_key(context) == "2"


def test_active_step_falls_back_to_the_first_pending_step():
    context = _context(source_steps=[_step(1), _step(2)], mappings=[_mapping(10, "1")])
    assert recorder_steps.active_step_key(context) == "2"


def test_active_step_is_none_when_everything_is_recorded():
    context = _context(source_steps=[_step(1)], mappings=[_mapping(10, "1")])
    assert recorder_steps.active_step_key(context) is None


def test_expected_results_without_checkpoints_ignores_skipped_steps():
    context = _context(
        source_steps=[_step(1, expected="A"), _step(2, expected="B")],
        step_states=[_state("2", "SKIPPED", skip_reason="n/a")],
    )
    rows = recorder_steps.expected_results_without_checkpoints(context)
    assert [row.step_key for row in rows] == ["1"]


def test_unmapped_actions_exclude_observations_and_excluded_actions():
    context = _context(source_steps=[_step(1)])
    context = RecordingContext(
        **{
            **context.__dict__,
            "actions": [
                SimpleNamespace(id=1, action_family="click", inclusion_state="included"),
                SimpleNamespace(id=2, action_family="read", inclusion_state="included"),
                SimpleNamespace(id=3, action_family="click", inclusion_state="excluded"),
            ],
        }
    )
    assert [a.id for a in recorder_steps.unmapped_actions(context)] == [1]
