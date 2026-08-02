"""One list answering "why won't this run yet?".

Driving a test case to a governed execution meant walking six modules and
hitting nine blockers, every one discovered by being refused and almost none
reported where it is fixed — the suite wizard reports MODEL_NOT_APPROVED, which
is resolved three modules away.

The rules these tests hold:

  * a green step means the owning subsystem said so — never an assumption
  * exactly one step is actionable; the rest are consequences
  * every blocker names where to go
"""
from __future__ import annotations

from app.services.execution_path import (
    PathFacts,
    StepState,
    build_path,
    summarize,
)


def _complete(**overrides) -> PathFacts:
    """Facts for a test case that is ready to run — the end state."""
    base = dict(
        project_id=11, test_case_id=70, test_case_key="TC-0070",
        requirement_status="approved", requirement_key="REQ-0290",
        test_case_status="approved",
        application_name="Web", environment="SIT", environment_url="http://static-test/",
        discovery_session_id=25, application_id=16,
        model_id=6, model_version=1, model_status="approved", model_screens=2,
        classification_review_status="APPROVED", classification_candidate_status="CONDITIONAL",
        script_key="AS-0045", script_gate_passed=True,
        suite_id=10, suite_name="Fixture Home Navigation E2E", suite_status="PUBLISHED",
        members_awaiting_final_approval=0,
        last_run_id=49, last_run_state="COMPLETED", last_run_result="PASS",
    )
    base.update(overrides)
    return PathFacts(**base)


def _by_key(steps):
    return {s.key: s for s in steps}


# ── The end state ────────────────────────────────────────────────────────────

def test_a_fully_ready_test_case_has_no_blockers():
    steps = build_path(_complete())
    assert all(s.state is StepState.DONE for s in steps)
    assert summarize(steps)["ready_to_execute"] is True
    assert summarize(steps)["next_action"] is None


# ── One blocker at a time ────────────────────────────────────────────────────

def test_only_the_first_unmet_step_is_actionable():
    """Five blockers when four follow from the first is how a checklist stops
    being read."""
    steps = build_path(_complete(
        model_status="pending_review",
        classification_review_status=None,
        script_key=None,
        suite_status="DRAFT",
    ))
    states = _by_key(steps)
    assert states["model"].state is StepState.BLOCKED
    assert states["classification"].state is StepState.WAITING
    assert states["script"].state is StepState.WAITING
    assert states["suite"].state is StepState.WAITING


def test_a_waiting_step_offers_no_fix_link():
    """Sending someone to fix a consequence wastes the trip."""
    steps = build_path(_complete(test_case_status="draft", script_key=None))
    waiting = [s for s in steps if s.state is StepState.WAITING]
    assert waiting
    assert all(s.fix_href is None for s in waiting)


def test_the_summary_names_the_one_thing_to_do_next():
    steps = build_path(_complete(model_status="pending_review", script_key=None))
    summary = summarize(steps)
    assert summary["next_action"] == "Application Model approved"
    assert "view=model" in summary["next_action_href"]
    assert summary["ready_to_execute"] is False


# ── Every blocker names where it is fixed ────────────────────────────────────

def test_each_blocker_links_to_the_module_that_owns_it():
    cases = [
        (dict(requirement_status="draft"), "requirement", "/requirements"),
        (dict(test_case_status="draft"), "test_case", "/test-cases"),
        (dict(environment_url=None), "application", "/applications"),
        (dict(discovery_session_id=None), "discovery", "view=discovery"),
        (dict(model_status="pending_review"), "model", "view=model"),
        (dict(classification_review_status="PENDING_REVIEW"), "classification", "/test-cases"),
        (dict(script_key=None), "script", "view=workspace"),
        (dict(suite_status="DRAFT"), "suite", "/automation"),
    ]
    for override, key, expected_href_fragment in cases:
        step = _by_key(build_path(_complete(**override)))[key]
        assert step.state is StepState.BLOCKED, f"{key} should block"
        assert step.fix_href and expected_href_fragment in step.fix_href, key
        assert step.fix_label, key


def test_final_approval_points_at_assets_not_the_workspace():
    """The blocker that cost the most: publish refuses in the workspace, but
    members are finally approved in Automation Assets."""
    step = _by_key(build_path(_complete(
        suite_status="APPROVED", members_awaiting_final_approval=2,
    )))["suite"]
    assert step.state is StepState.BLOCKED
    assert "2 member(s) still need final approval" in step.detail
    assert "view=ir" in step.fix_href


# ── Never invent a verdict ───────────────────────────────────────────────────

def test_an_unreadable_step_is_unknown_not_done():
    """A green path has to mean something."""
    steps = build_path(_complete(requirement_status=None, requirement_key=None))
    assert _by_key(steps)["requirement"].state is StepState.UNKNOWN
    assert summarize(steps)["ready_to_execute"] is False


def test_unknown_stops_the_path_like_a_blocker():
    """If a step cannot be judged, nothing after it can be either."""
    steps = build_path(_complete(requirement_status=None, requirement_key=None,
                                 script_key=None))
    assert _by_key(steps)["script"].state is StepState.WAITING


# ── The specific traps this exists to surface ────────────────────────────────

def test_a_registered_application_with_no_url_for_this_environment_blocks():
    """The silent dead end: generation resolved application_url to None while
    the app looked configured, producing a script with nowhere to navigate."""
    step = _by_key(build_path(_complete(environment_url=None)))["application"]
    assert step.state is StepState.BLOCKED
    assert "has no URL for environment 'SIT'" in step.detail


def test_a_failing_static_gate_is_visible_on_the_script_step():
    """A generated script is not automatically a usable one."""
    step = _by_key(build_path(_complete(script_gate_passed=False)))["script"]
    assert "static gate FAILED" in step.detail


def test_a_rejected_classification_blocks_even_though_one_exists():
    step = _by_key(build_path(_complete(
        classification_review_status="APPROVED",
        classification_candidate_status="NOT_RECOMMENDED",
    )))["classification"]
    assert step.state is StepState.BLOCKED


def test_a_run_that_failed_does_not_count_as_executed():
    steps = build_path(_complete(last_run_result="FAIL"))
    assert _by_key(steps)["execution"].state is StepState.BLOCKED
    assert summarize(steps)["ready_to_execute"] is False


def test_the_path_is_stable_in_order_and_shape():
    """The order is the argument — it must not drift silently."""
    keys = [s.key for s in build_path(_complete())]
    assert keys == [
        "requirement", "test_case", "application", "discovery", "model",
        "classification", "script", "suite", "execution",
    ]
    assert all(s.as_dict()["detail"] for s in build_path(_complete()))


def test_a_satisfied_step_offers_no_fix_link():
    """Every row carrying a link made a finished path look like nine
    outstanding actions."""
    steps = build_path(_complete())
    assert all(s.fix_href is None and s.fix_label is None for s in steps)


def test_a_passed_run_closes_the_path():
    """Found immediately against real data: the path reported "No governed run
    yet" for a test case that had already passed — a blocker where there was
    none, which costs trust as fast as a false green."""
    steps = build_path(_complete(last_run_id=49, last_run_result="PASS"))
    assert _by_key(steps)["execution"].state is StepState.DONE
    assert "Run #49" in _by_key(steps)["execution"].detail
