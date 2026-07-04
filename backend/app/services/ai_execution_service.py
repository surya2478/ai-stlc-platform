"""AI Execution lifecycle.

This module owns the rules that decide whether an AI run is allowed to publish
its result autonomously, or whether a human reviewer must sign off first.

Lifecycle states for an AI ExecutionRun:

    pending ─▶ queued ─▶ running ─┬─▶ auto_completed   (autonomous publish)
                                  ├─▶ review_required  (needs human signoff)
                                  ├─▶ completed        (manual publish, e.g. via review)
                                  └─▶ failed / cancelled

`evaluate_completion_rule` is the single source of truth for that branch. It
runs after the agent finishes producing its step results. The same rule is
re-applied whenever someone tries to mark a run reviewed without an explicit
override.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import audit_logger
from app.models.execution import ExecutionResult, ExecutionRun


CompletionDecision = Literal["auto_completed", "review_required", "failed"]


@dataclass(slots=True)
class CompletionEvaluation:
    decision: CompletionDecision
    reason: str
    rule: str
    overall_status: str  # one of: passed | failed | blocked | inconclusive
    confidence: float | None


def _result_outcome(results: list[ExecutionResult]) -> str:
    """Roll up per-test-case outcomes to a single run-level outcome."""
    if not results:
        return "inconclusive"
    has_fail = any(r.status in ("fail", "failed", "error") for r in results)
    has_blocked = any(r.status == "blocked" for r in results)
    has_pass = any(r.status in ("pass", "passed") for r in results)
    if has_fail:
        return "failed"
    if has_blocked and not has_pass:
        return "blocked"
    if has_pass and not has_fail and not has_blocked:
        return "passed"
    return "inconclusive"


def _has_evidence(results: list[ExecutionResult]) -> bool:
    """True iff at least one result has any evidence artifact (URL, screenshot,
    video, log, raw json, etc.)."""
    for r in results:
        if r.screenshot_url or r.video_url or r.log_url or r.external_result_url:
            return True
        if r.screenshot_path or r.video_path or r.trace_path:
            return True
        if r.raw_result_json or r.logs:
            return True
    return False


def evaluate_completion_rule(
    run: ExecutionRun,
    results: list[ExecutionResult],
    *,
    confidence_threshold: int | None = None,
    autonomous_environments: list[str] | None = None,
    require_evidence_for_pass: bool | None = None,
) -> CompletionEvaluation:
    """Decide whether an AI run can auto-publish, must wait for review, or has failed.

    All thresholds default to platform settings — callers may override for tests.
    """
    settings = get_settings()
    threshold = confidence_threshold if confidence_threshold is not None else settings.ai_confidence_threshold
    allowed_envs = (
        [e.upper() for e in autonomous_environments]
        if autonomous_environments is not None
        else settings.ai_autonomous_environments_list
    )
    require_evidence = (
        require_evidence_for_pass if require_evidence_for_pass is not None else settings.ai_require_evidence_for_pass
    )

    overall = _result_outcome(results)
    confidence = run.confidence_score

    if overall == "failed":
        return CompletionEvaluation(
            decision="review_required",
            reason="One or more steps failed — human triage required",
            rule="failure_triggers_review",
            overall_status="failed",
            confidence=confidence,
        )

    if overall == "blocked":
        return CompletionEvaluation(
            decision="review_required",
            reason="Run hit a blocking condition — human triage required",
            rule="blocked_triggers_review",
            overall_status="blocked",
            confidence=confidence,
        )

    if overall == "inconclusive":
        return CompletionEvaluation(
            decision="review_required",
            reason="Result was inconclusive — no clear pass/fail signal",
            rule="inconclusive_triggers_review",
            overall_status="inconclusive",
            confidence=confidence,
        )

    # overall == "passed"
    env = (run.environment or "").upper()
    if allowed_envs and env not in allowed_envs:
        return CompletionEvaluation(
            decision="review_required",
            reason=f"Environment '{run.environment}' is outside the autonomous-allowed set",
            rule="env_not_autonomous",
            overall_status="passed",
            confidence=confidence,
        )

    if confidence is None or confidence < threshold:
        return CompletionEvaluation(
            decision="review_required",
            reason=f"Confidence {confidence if confidence is not None else 'unknown'} is below threshold {threshold}",
            rule="low_confidence",
            overall_status="passed",
            confidence=confidence,
        )

    if require_evidence and not _has_evidence(results):
        return CompletionEvaluation(
            decision="review_required",
            reason="No evidence captured for a passing run — policy requires evidence",
            rule="missing_evidence",
            overall_status="passed",
            confidence=confidence,
        )

    return CompletionEvaluation(
        decision="auto_completed",
        reason="All steps passed, evidence present, confidence above threshold, environment allowed",
        rule="autonomous_policy_satisfied",
        overall_status="passed",
        confidence=confidence,
    )


async def finalize_ai_run(
    db: AsyncSession,
    *,
    run: ExecutionRun,
    results: list[ExecutionResult] | None = None,
) -> CompletionEvaluation:
    """Apply the completion rule, set run.status accordingly, and emit audit.

    Called by the AI execution worker after the agent produces its results, and
    re-callable by an admin "re-evaluate" action. Safe to call multiple times —
    re-running on an already-published run is a no-op (returns the latest eval
    without mutation if the run is already terminal).
    """
    if results is None:
        results_query = select(ExecutionResult).where(ExecutionResult.execution_run_id == run.id)
        results = list((await db.execute(results_query)).scalars().all())

    evaluation = evaluate_completion_rule(run, results)

    previous_status = run.status

    if previous_status in ("auto_completed", "completed", "failed", "cancelled"):
        # Already terminal — don't reset.
        return evaluation

    now = datetime.now(timezone.utc)

    if evaluation.decision == "auto_completed":
        run.status = "auto_completed"
        run.completed_at = now
        audit_logger.execution_run_auto_completed(
            run_id=run.id,
            project_id=run.project_id,
            confidence_score=run.confidence_score,
            rule=evaluation.rule,
        )
    elif evaluation.decision == "review_required":
        run.status = "review_required"
        # Don't set completed_at — reviewer will close it.
        audit_logger.execution_run_review_required(
            run_id=run.id,
            project_id=run.project_id,
            confidence_score=run.confidence_score,
            reason=evaluation.reason,
        )
    else:  # failed (defensive — current rule never returns this)
        run.status = "failed"
        run.completed_at = now

    audit_logger.execution_run_state_changed(
        by_user_id=None,
        run_id=run.id,
        previous_status=previous_status,
        new_status=run.status,
        reason=evaluation.reason,
    )

    if run.duration_seconds is None and run.started_at and run.completed_at:
        run.duration_seconds = (run.completed_at - run.started_at).total_seconds()

    await db.flush()
    return evaluation


ReviewDecision = Literal["approve", "override", "request_rerun", "reject"]


async def submit_review_decision(
    db: AsyncSession,
    *,
    run: ExecutionRun,
    user_id: int,
    decision: ReviewDecision,
    reason: str,
    override_status: str | None = None,
) -> ExecutionRun:
    """Apply a human reviewer's decision to an AI run.

    `decision`:
        approve         → review_required becomes completed (run treated as passed)
        override        → set the run to override_status (passed/failed/blocked etc.)
        request_rerun   → mark cancelled with a re-run requested note in metadata
        reject          → set failed; reason is mandatory

    Audit-logged with the reviewer's user id, decision, prior status, and reason.
    A comment is always required; the API enforces this.
    """
    if not reason or not reason.strip():
        raise ValueError("A reason / comment is required for a review decision")

    previous_status = run.status
    metadata = dict(run.metadata_ or {})
    review_log = list(metadata.get("review_log") or [])
    review_log.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "by_user_id": user_id,
        "decision": decision,
        "reason": reason,
        "previous_status": previous_status,
        "override_status": override_status,
    })
    # Cap at last 25 entries.
    metadata["review_log"] = review_log[-25:]

    if decision == "approve":
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
    elif decision == "override":
        if not override_status:
            raise ValueError("override_status is required for an override decision")
        if override_status not in ("completed", "failed", "auto_completed", "cancelled"):
            raise ValueError(f"override_status '{override_status}' is not a valid terminal state")
        run.status = override_status
        run.completed_at = datetime.now(timezone.utc)
    elif decision == "request_rerun":
        run.status = "cancelled"
        metadata["rerun_requested"] = True
    elif decision == "reject":
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
    else:
        raise ValueError(f"Unknown review decision: {decision}")

    run.metadata_ = metadata

    audit_logger.execution_run_reviewed(
        by_user_id=user_id,
        run_id=run.id,
        decision=decision,
        override_status=override_status,
        reason=reason,
    )
    audit_logger.execution_run_state_changed(
        by_user_id=user_id,
        run_id=run.id,
        previous_status=previous_status,
        new_status=run.status,
        reason=f"review:{decision} {reason}",
    )

    if run.duration_seconds is None and run.started_at and run.completed_at:
        run.duration_seconds = (run.completed_at - run.started_at).total_seconds()

    await db.flush()
    return run


def governance_snapshot() -> dict[str, object]:
    """Return the current governance config so the UI can render policy badges."""
    settings = get_settings()
    return {
        "ai_confidence_threshold": settings.ai_confidence_threshold,
        "ai_autonomous_environments": settings.ai_autonomous_environments_list,
        "ai_require_evidence_for_pass": settings.ai_require_evidence_for_pass,
        "ai_run_max_seconds": settings.ai_run_max_seconds,
    }
