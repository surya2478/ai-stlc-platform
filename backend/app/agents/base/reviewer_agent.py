"""
Shared base for "senior reviewer" agents (Phase 1 of the agentic automation
initiative — see AGENTIC_AUTOMATION_IMPLEMENTATION_PLAN.md at the repo root).

A reviewer agent receives a generated artifact *and* its upstream source
artifact (e.g. test scenarios + the requirement they were generated from)
and produces a structured verdict per item: dimension scores, findings, a
coverage-gap list, and a pass/needs_revision/fail verdict. This generalizes
the pattern already proven in `requirement/quality_agent.py` so every stage
(scenario, test case, ...) gets the same review contract, persistence shape,
and UI surface.

Concrete reviewer agents follow the same convention as every other concrete
agent in this codebase: they expose their own `run(...)` with review-specific
keyword arguments (mirroring `TestScenarioAgent.run(requirements=...)` etc.)
rather than being invoked through `BaseAgent.run()`'s generic timeout/logging
wrapper — that wrapper is unused by any agent in `AGENT_REGISTRY` today; the
Celery task calls each agent's own `run()` directly (see agent_tasks.py).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.base.base_agent import AgentRunResult, BaseAgent

Verdict = Literal["pass", "needs_revision", "fail"]


class CoverageGap(BaseModel):
    """A specific piece of upstream intent the reviewed artifact does not cover.

    `source_ref` names the missed upstream item (an acceptance criterion, a
    business rule, a scenario step) in whatever form the reviewer agent used
    to identify it — free text, since upstream artifacts don't have stable
    per-line IDs.
    """
    source_ref: str
    description: str
    severity: Literal["high", "medium", "low"] = "medium"


class ReviewFinding(BaseModel):
    dimension: str
    issue: str
    suggestion: str | None = None


class ReviewVerdict(BaseModel):
    """Structured output every reviewer agent produces, one per reviewed item."""
    target_ref: str  # the business ID of the item being reviewed (e.g. "TS-001")
    scores: dict[str, float] = Field(default_factory=dict)
    overall_score: float | None = None
    verdict: Verdict = "needs_revision"
    findings: list[ReviewFinding] = Field(default_factory=list)
    coverage_gaps: list[CoverageGap] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class BaseReviewerAgent(BaseAgent):
    """Common plumbing for reviewer agents — see module docstring."""

    async def _run(self, input_data: dict) -> dict:  # pragma: no cover - unused bridge
        raise NotImplementedError(
            f"{self.name} exposes its own `run(...)` with review-specific "
            "kwargs; it is not invoked through the generic BaseAgent._run bridge."
        )

    def _build_result(self, verdicts: list[ReviewVerdict], target_kind: str) -> AgentRunResult:
        passes = sum(1 for v in verdicts if v.verdict == "pass")
        needs_revision = sum(1 for v in verdicts if v.verdict == "needs_revision")
        fails = sum(1 for v in verdicts if v.verdict == "fail")
        return AgentRunResult(
            success=True,
            data={
                "target_kind": target_kind,
                "reviews": [v.as_dict() for v in verdicts],
                "summary": {"pass": passes, "needs_revision": needs_revision, "fail": fails},
            },
            logs=self._logs,
        )
