"""Tests for the AI Execution completion + review lifecycle (Phase 3).

Covers the pure-policy logic in `ai_execution_service.evaluate_completion_rule`
(no DB) and exercises `finalize_ai_run` + `submit_review_decision` against a
tiny in-memory fake AsyncSession.

These tests live independently of the broader execution test fixtures so they
can run without a real database — they only need the model classes (for shape)
and the service module under test.
"""
from __future__ import annotations

import anyio
import pytest

from app.models.execution import ExecutionResult, ExecutionRun
from app.services import ai_execution_service


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _run(**overrides) -> ExecutionRun:
    """Build a bare ExecutionRun in-memory (no DB persistence)."""
    run = ExecutionRun(
        project_id=1,
        created_by=1,
        execution_id="AI-TEST",
        execution_type="ai",
        environment="SIT",
        status="running",
        confidence_score=95.0,
        total_tests=1,
        passed=1, failed=0, skipped=0,
    )
    for k, v in overrides.items():
        setattr(run, k, v)
    return run


def _result(status: str, *, with_evidence: bool = False) -> ExecutionResult:
    r = ExecutionResult(
        execution_run_id=1,
        project_id=1,
        test_name="t",
        status=status,
    )
    if with_evidence:
        r.screenshot_url = "https://example.com/s.png"
    return r


class _FakeDB:
    """Minimal AsyncSession stand-in — only implements what the services touch."""
    def __init__(self) -> None:
        self.flushed = 0
        self.refresh_called_on: list[object] = []

    async def flush(self) -> None:
        self.flushed += 1

    async def execute(self, _stmt):
        # finalize_ai_run only calls execute when results are not passed in;
        # all of our tests pass results explicitly so this is unreachable.
        raise NotImplementedError

    async def refresh(self, obj):
        self.refresh_called_on.append(obj)


# ──────────────────────────────────────────────────────────────────────────────
# evaluate_completion_rule — pure decision logic
# ──────────────────────────────────────────────────────────────────────────────


def test_failed_step_forces_review_regardless_of_confidence():
    run = _run(confidence_score=99.0, environment="SIT")
    results = [_result("passed"), _result("failed")]
    decision = ai_execution_service.evaluate_completion_rule(run, results)
    assert decision.decision == "review_required"
    assert decision.rule == "failure_triggers_review"


def test_blocked_run_requires_review():
    run = _run(confidence_score=99.0)
    results = [_result("blocked")]
    decision = ai_execution_service.evaluate_completion_rule(run, results)
    assert decision.decision == "review_required"
    assert decision.rule == "blocked_triggers_review"


def test_inconclusive_result_requires_review():
    run = _run()
    results: list[ExecutionResult] = []  # no results at all
    decision = ai_execution_service.evaluate_completion_rule(run, results)
    assert decision.decision == "review_required"
    assert decision.rule == "inconclusive_triggers_review"


def test_low_confidence_passing_run_requires_review():
    run = _run(confidence_score=60.0, environment="SIT")
    results = [_result("passed", with_evidence=True)]
    decision = ai_execution_service.evaluate_completion_rule(
        run, results, confidence_threshold=90,
    )
    assert decision.decision == "review_required"
    assert decision.rule == "low_confidence"


def test_environment_outside_allowed_set_requires_review():
    run = _run(confidence_score=99.0, environment="PROD")
    results = [_result("passed", with_evidence=True)]
    decision = ai_execution_service.evaluate_completion_rule(
        run, results, autonomous_environments=["SIT", "UAT"],
    )
    assert decision.decision == "review_required"
    assert decision.rule == "env_not_autonomous"


def test_passing_run_without_evidence_requires_review_when_policy_demands():
    run = _run(confidence_score=99.0, environment="SIT")
    results = [_result("passed", with_evidence=False)]
    decision = ai_execution_service.evaluate_completion_rule(
        run, results,
        autonomous_environments=["SIT"],
        require_evidence_for_pass=True,
    )
    assert decision.decision == "review_required"
    assert decision.rule == "missing_evidence"


def test_evidence_policy_can_be_disabled():
    run = _run(confidence_score=99.0, environment="SIT")
    results = [_result("passed", with_evidence=False)]
    decision = ai_execution_service.evaluate_completion_rule(
        run, results,
        autonomous_environments=["SIT"],
        require_evidence_for_pass=False,
    )
    assert decision.decision == "auto_completed"


def test_happy_path_publishes_autonomously():
    run = _run(confidence_score=99.0, environment="SIT")
    results = [_result("passed", with_evidence=True)]
    decision = ai_execution_service.evaluate_completion_rule(
        run, results,
        confidence_threshold=90,
        autonomous_environments=["SIT", "UAT"],
        require_evidence_for_pass=True,
    )
    assert decision.decision == "auto_completed"
    assert decision.rule == "autonomous_policy_satisfied"
    assert decision.overall_status == "passed"


def test_none_confidence_blocks_autonomous_publish():
    run = _run(confidence_score=None, environment="SIT")
    results = [_result("passed", with_evidence=True)]
    decision = ai_execution_service.evaluate_completion_rule(
        run, results, confidence_threshold=90,
    )
    assert decision.decision == "review_required"
    assert decision.rule == "low_confidence"


# ──────────────────────────────────────────────────────────────────────────────
# finalize_ai_run — state mutation
# ──────────────────────────────────────────────────────────────────────────────


def test_finalize_sets_auto_completed_when_policy_passes():
    async def go() -> None:
        run = _run(confidence_score=99.0, environment="SIT")
        results = [_result("passed", with_evidence=True)]
        db = _FakeDB()
        # Override settings via service kwargs not exposed — but the defaults
        # include SIT as allowed and threshold 90, which our run satisfies.
        evaluation = await ai_execution_service.finalize_ai_run(
            db, run=run, results=results,
        )
        assert evaluation.decision == "auto_completed"
        assert run.status == "auto_completed"
        assert run.completed_at is not None
        assert db.flushed >= 1

    anyio.run(go)


def test_finalize_sets_review_required_when_failed():
    async def go() -> None:
        run = _run(confidence_score=99.0)
        results = [_result("failed"), _result("passed")]
        db = _FakeDB()
        evaluation = await ai_execution_service.finalize_ai_run(
            db, run=run, results=results,
        )
        assert evaluation.decision == "review_required"
        assert run.status == "review_required"
        # Reviewer will close the run, so completed_at stays None for now.
        assert run.completed_at is None

    anyio.run(go)


def test_finalize_is_idempotent_on_already_terminal_runs():
    async def go() -> None:
        run = _run(status="auto_completed", confidence_score=99.0)
        results = [_result("passed", with_evidence=True)]
        db = _FakeDB()
        before_status = run.status
        evaluation = await ai_execution_service.finalize_ai_run(
            db, run=run, results=results,
        )
        # Evaluation still returns a decision, but run state must not flip.
        assert run.status == before_status
        # No flush should be issued for a no-op.
        assert db.flushed == 0
        # Decision still surfaces the would-be outcome.
        assert evaluation.decision in ("auto_completed", "review_required")

    anyio.run(go)


# ──────────────────────────────────────────────────────────────────────────────
# submit_review_decision — reviewer flows
# ──────────────────────────────────────────────────────────────────────────────


def test_review_decision_requires_reason():
    async def go() -> None:
        run = _run(status="review_required")
        db = _FakeDB()
        with pytest.raises(ValueError, match="reason"):
            await ai_execution_service.submit_review_decision(
                db, run=run, user_id=42, decision="approve", reason="",
            )

    anyio.run(go)


def test_review_approve_publishes_run_as_completed():
    async def go() -> None:
        run = _run(status="review_required")
        db = _FakeDB()
        await ai_execution_service.submit_review_decision(
            db, run=run, user_id=42, decision="approve",
            reason="Manually inspected, all good",
        )
        assert run.status == "completed"
        assert run.completed_at is not None
        review_log = (run.metadata_ or {}).get("review_log")
        assert review_log and review_log[-1]["decision"] == "approve"
        assert review_log[-1]["by_user_id"] == 42

    anyio.run(go)


def test_review_override_requires_valid_target_status():
    async def go() -> None:
        run = _run(status="review_required")
        db = _FakeDB()
        with pytest.raises(ValueError):
            await ai_execution_service.submit_review_decision(
                db, run=run, user_id=42, decision="override",
                reason="x", override_status="bogus_state",
            )

    anyio.run(go)


def test_review_override_applies_target_status():
    async def go() -> None:
        run = _run(status="review_required")
        db = _FakeDB()
        await ai_execution_service.submit_review_decision(
            db, run=run, user_id=42, decision="override",
            reason="Reviewer override — partial pass",
            override_status="completed",
        )
        assert run.status == "completed"
        assert run.completed_at is not None

    anyio.run(go)


def test_review_request_rerun_sets_cancelled_with_flag():
    async def go() -> None:
        run = _run(status="review_required")
        db = _FakeDB()
        await ai_execution_service.submit_review_decision(
            db, run=run, user_id=42, decision="request_rerun",
            reason="Flaky setup — please retry",
        )
        assert run.status == "cancelled"
        assert (run.metadata_ or {}).get("rerun_requested") is True

    anyio.run(go)


def test_review_log_caps_at_25_entries():
    async def go() -> None:
        run = _run(status="review_required")
        existing_log = [{"ts": "x", "decision": "approve", "reason": "r"} for _ in range(30)]
        run.metadata_ = {"review_log": existing_log}
        db = _FakeDB()
        await ai_execution_service.submit_review_decision(
            db, run=run, user_id=42, decision="approve", reason="latest",
        )
        log = (run.metadata_ or {}).get("review_log")
        assert log is not None
        assert len(log) == 25
        assert log[-1]["reason"] == "latest"

    anyio.run(go)


# ──────────────────────────────────────────────────────────────────────────────
# governance_snapshot
# ──────────────────────────────────────────────────────────────────────────────


def test_governance_snapshot_returns_settings_shape():
    snapshot = ai_execution_service.governance_snapshot()
    assert "ai_confidence_threshold" in snapshot
    assert "ai_autonomous_environments" in snapshot
    assert "ai_require_evidence_for_pass" in snapshot
    assert isinstance(snapshot["ai_autonomous_environments"], list)
    assert isinstance(snapshot["ai_confidence_threshold"], int)
