"""Autonomy policy — pure, so no DB fake is needed.

The centrepiece is `test_never_approves_without_execution_evidence`, which pins
acceptance criterion 15 of the UI-020/021/023 contract: an asset with no
dry-run history can never reach AI_APPROVED, no matter how high its score. That
is the regression test for the defect documented in Section 14.3 — the
confidence service returns neutral 0.5/0.7 defaults when evidence is *absent*,
so a score-only gate would auto-approve the least-evidenced assets.
"""
import pytest

from app.services.automation_asset.autonomy import (
    DRY_RUNS_PASSED,
    LOCATORS_GROUNDED,
    NO_CRITICAL_GAPS,
    NO_UNRESOLVED_STEPS,
    PRECONDITION_ORDER,
    STATIC_GATE_CLEAN,
    AssetEvidence,
    AutonomyPolicy,
    evaluate,
    evaluate_preconditions,
    next_autonomy_state,
)

POLICY = AutonomyPolicy(rubric_id="automation.v1", threshold=80, min_passing_dry_runs=1, enabled=True)
POLICY_OFF = AutonomyPolicy(rubric_id="automation.v1", threshold=80, min_passing_dry_runs=1, enabled=False)


def qualified(**overrides) -> AssetEvidence:
    """An asset that meets every precondition and scores above threshold."""
    base = dict(
        static_gate_ran=True,
        static_gate_passed=True,
        blocking_violation_count=0,
        has_ir=True,
        custom_step_count=0,
        ir_unresolved_count=0,
        element_step_count=3,
        referenced_locator_count=3,
        grounded_locator_count=3,
        passing_dry_runs=1,
        total_dry_runs=1,
        unwaived_critical_gaps=0,
        score=88.0,
        dimensions={"locator_confidence": 0.94, "dry_run_stability": 1.0},
    )
    base.update(overrides)
    return AssetEvidence(**base)


def outcome(verdict, code):
    return next(p for p in verdict.preconditions if p.code == code)


# ── The regression test for Section 14.3 ─────────────────────────────────────


def test_never_approves_without_execution_evidence():
    """Acceptance criterion 15. A never-executed asset scoring 95 is still held."""
    verdict = evaluate(qualified(passing_dry_runs=0, total_dry_runs=0, score=95.0), POLICY)
    assert verdict.state == "AI_HELD"
    assert outcome(verdict, DRY_RUNS_PASSED).met is False
    assert "never been executed" in outcome(verdict, DRY_RUNS_PASSED).detail


def test_score_alone_cannot_approve_an_ungrounded_asset():
    """The other half of 14.3: a high score with ungrounded locators is held."""
    verdict = evaluate(qualified(grounded_locator_count=1, score=99.0), POLICY)
    assert verdict.state == "AI_HELD"
    assert outcome(verdict, LOCATORS_GROUNDED).met is False
    assert "2 of 3 locators" in outcome(verdict, LOCATORS_GROUNDED).detail


# ── Preconditions ────────────────────────────────────────────────────────────


def test_all_five_preconditions_always_evaluated_in_order():
    """Acceptance criterion 14 relies on the full checklist being present even
    after the first failure — a reviewer needs the whole picture."""
    verdict = evaluate(
        qualified(static_gate_passed=False, blocking_violation_count=2, passing_dry_runs=0),
        POLICY,
    )
    assert tuple(p.code for p in verdict.preconditions) == PRECONDITION_ORDER
    assert len(verdict.unmet) == 2


def test_gate_not_run_is_unmet_not_satisfied():
    """Absent evidence must never read as good evidence."""
    verdict = evaluate(qualified(static_gate_ran=False, static_gate_passed=None), POLICY)
    assert verdict.state == "AI_HELD"
    assert outcome(verdict, STATIC_GATE_CLEAN).met is False
    assert "has not run" in outcome(verdict, STATIC_GATE_CLEAN).detail


def test_missing_ir_is_unmet():
    verdict = evaluate(qualified(has_ir=False, custom_step_count=None), POLICY)
    assert outcome(verdict, NO_UNRESOLVED_STEPS).met is False


def test_custom_steps_and_unresolved_items_are_independent():
    """The emitter's readiness map keeps these separate; a draft can have zero
    custom steps and still be unready."""
    only_unresolved = evaluate(qualified(custom_step_count=0, ir_unresolved_count=2), POLICY)
    assert only_unresolved.state == "AI_HELD"
    assert "2 readiness items unresolved" in outcome(only_unresolved, NO_UNRESOLVED_STEPS).detail

    only_custom = evaluate(qualified(custom_step_count=3, ir_unresolved_count=0), POLICY)
    assert "3 steps still need a locator" in outcome(only_custom, NO_UNRESOLVED_STEPS).detail


def test_no_element_steps_makes_grounding_not_applicable():
    """A pure API/DB asset has nothing to ground — but only when there genuinely
    are no element-driven steps."""
    verdict = evaluate(
        qualified(element_step_count=0, referenced_locator_count=0, grounded_locator_count=0),
        POLICY,
    )
    assert outcome(verdict, LOCATORS_GROUNDED).met is True
    assert verdict.state == "AI_APPROVED"


def test_element_steps_with_no_declared_locators_is_unmet():
    verdict = evaluate(
        qualified(element_step_count=2, referenced_locator_count=0, grounded_locator_count=0),
        POLICY,
    )
    assert outcome(verdict, LOCATORS_GROUNDED).met is False


def test_unwaived_critical_gap_holds_the_asset():
    verdict = evaluate(qualified(unwaived_critical_gaps=1), POLICY)
    assert verdict.state == "AI_HELD"
    assert outcome(verdict, NO_CRITICAL_GAPS).met is False


@pytest.mark.parametrize("required,passing,expected", [(1, 1, True), (2, 1, False), (3, 3, True)])
def test_min_dry_runs_is_configurable(required, passing, expected):
    policy = AutonomyPolicy(threshold=80, min_passing_dry_runs=required, enabled=True)
    verdict = evaluate(qualified(passing_dry_runs=passing, total_dry_runs=passing), policy)
    assert outcome(verdict, DRY_RUNS_PASSED).met is expected


# ── Threshold ────────────────────────────────────────────────────────────────


def test_approves_at_exactly_the_threshold():
    assert evaluate(qualified(score=80.0), POLICY).state == "AI_APPROVED"


def test_holds_just_below_the_threshold():
    verdict = evaluate(qualified(score=79.9), POLICY)
    assert verdict.state == "AI_HELD"
    assert "below the 80 threshold" in verdict.held_reason


def test_held_reason_names_the_weakest_dimension():
    verdict = evaluate(
        qualified(score=70.0, dimensions={"locator_confidence": 0.9, "dry_run_stability": 0.2}),
        POLICY,
    )
    assert "dry run stability at 0.2" in verdict.held_reason


def test_uncomputable_score_holds_rather_than_defaults_to_pass():
    verdict = evaluate(qualified(score=None), POLICY)
    assert verdict.state == "AI_HELD"
    assert "could not be computed" in verdict.held_reason


def test_threshold_is_carried_on_the_verdict_by_value():
    """Acceptance criterion 20 — decisions store the threshold, not a pointer."""
    verdict = evaluate(qualified(), AutonomyPolicy(threshold=95, min_passing_dry_runs=1, enabled=True))
    assert verdict.threshold == 95
    assert verdict.as_dict()["threshold"] == 95


def test_dimensions_travel_with_the_verdict():
    verdict = evaluate(qualified(), POLICY)
    assert verdict.dimensions["locator_confidence"] == 0.94
    assert verdict.as_dict()["dimensions"]["dry_run_stability"] == 1.0


# ── Feature flag ─────────────────────────────────────────────────────────────


def test_disabled_policy_reports_qualification_without_approving():
    verdict = evaluate(qualified(), POLICY_OFF)
    assert verdict.state == "AI_PENDING"
    assert verdict.would_approve is True
    assert "disabled" in verdict.held_reason


def test_disabled_policy_still_holds_an_unqualified_asset():
    verdict = evaluate(qualified(passing_dry_runs=0, total_dry_runs=0), POLICY_OFF)
    assert verdict.state == "AI_HELD"
    assert verdict.would_approve is False


# ── The approval-owned guard (Section 14.6) ──────────────────────────────────


@pytest.mark.parametrize("approval_state", ["FINAL_APPROVED", "REJECTED"])
def test_human_decision_is_never_overwritten_by_re_evaluation(approval_state):
    """Acceptance criterion 19. UI-018 Phase B hit this exact bug at suite level:
    an evaluation pass that recomputes status silently undoes an approval."""
    verdict = evaluate(qualified(passing_dry_runs=0, total_dry_runs=0), POLICY)
    assert verdict.state == "AI_HELD"
    resolved = next_autonomy_state(
        current_autonomy_state="AI_APPROVED",
        current_approval_state=approval_state,
        verdict=verdict,
    )
    assert resolved == "AI_APPROVED"


def test_pending_final_still_follows_the_verdict():
    verdict = evaluate(qualified(), POLICY)
    resolved = next_autonomy_state(
        current_autonomy_state="AI_HELD",
        current_approval_state="PENDING_FINAL",
        verdict=verdict,
    )
    assert resolved == "AI_APPROVED"


def test_verdict_is_serialisable_for_the_decision_record():
    payload = evaluate(qualified(), POLICY).as_dict()
    assert payload["state"] == "AI_APPROVED"
    assert len(payload["preconditions"]) == 5
    assert all({"code", "label", "met", "detail"} <= set(p) for p in payload["preconditions"])


def test_preconditions_helper_matches_evaluate():
    ev = qualified(passing_dry_runs=0)
    assert evaluate_preconditions(ev, POLICY) == evaluate(ev, POLICY).preconditions
