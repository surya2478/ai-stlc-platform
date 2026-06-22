"""
Agent 2 — Requirement Quality Review Agent
Scores each requirement for completeness, clarity, testability and flags issues.
"""
import json
import re
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from app.agents.base.base_agent import BaseAgent
from app.agents.structured_schemas import RequirementQualityLLMOutput
from app.llm.provider import get_llm
from app.llm.structured import validate_structured_output, parse_and_validate_llm_list
from app.config import get_settings

settings = get_settings()


# ── State ──────────────────────────────────────────────────────────────────────

class QualityState(TypedDict):
    requirements: list[dict]
    reviews: list[dict]
    errors: list[str]


# ── LLM Prompt ────────────────────────────────────────────────────────────────

QUALITY_SYSTEM = """You are a QA Lead performing a quality review of software requirements.

Evaluate each requirement against these quality dimensions:
1. COMPLETENESS — All needed information is present (who, what, when, why)
2. CLARITY — The requirement is unambiguous and uses precise language
3. TESTABILITY — Can a test case be directly written from this requirement?
4. CONSISTENCY — No contradictions with other requirements
5. TRACEABILITY — Business justification is clear

For each requirement, output a JSON object with:
- requirement_title: the title of the requirement being reviewed
- completeness_score: 1-5 integer
- clarity_score: 1-5 integer
- testability_score: 1-5 integer
- overall_score: average of the three scores (float)
- issues: list of specific problems found (strings)
- suggestions: list of specific improvement suggestions (strings)
- verdict: "pass" | "needs_revision" | "fail"
  - pass: all scores >= 3
  - needs_revision: any score 2-3
  - fail: any score <= 1

Output ONLY a valid JSON array. No extra text.
"""


# ── Nodes ──────────────────────────────────────────────────────────────────────

async def _review_batch(state: QualityState) -> QualityState:
    """Review requirements in batches of 5."""
    llm = get_llm(settings.default_llm_provider, settings.default_llm_model)
    reviews = []
    errors = []
    batch_size = 5
    reqs = state["requirements"]

    for i in range(0, len(reqs), batch_size):
        batch = reqs[i:i + batch_size]
        req_text = json.dumps(batch, indent=2)
        prompt = f"""Review these {len(batch)} requirements:\n\n{req_text}

Return a JSON array of review objects."""
        try:
            response = await llm.generate(
                system=QUALITY_SYSTEM,
                user=prompt,
                temperature=0.1,
                max_tokens=4000,
            )
            batch_reviews = parse_and_validate_llm_list(response, RequirementQualityLLMOutput)
            reviews.extend(batch_reviews)
        except Exception as exc:
            errors.append(f"Batch {i//batch_size + 1} review error: {str(exc)}")

    return {**state, "reviews": reviews, "errors": errors}


def _merge_scores(state: QualityState) -> QualityState:
    """Merge reviews back into requirement objects."""
    errors = list(state["errors"])
    validated_reviews = state["reviews"]
    review_map = {r.get("requirement_title", "").lower(): r for r in validated_reviews}
    merged = []
    for req in state["requirements"]:
        review = review_map.get(req.get("title", "").lower(), {})
        merged.append({**req, "_quality_review": review})
    return {**state, "requirements": merged, "reviews": validated_reviews, "errors": errors}


# ── Graph ──────────────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    graph = StateGraph(QualityState)
    graph.add_node("review", _review_batch)
    graph.add_node("merge", _merge_scores)
    graph.set_entry_point("review")
    graph.add_edge("review", "merge")
    graph.add_edge("merge", END)
    return graph.compile()


_graph = _build_graph()


# ── Agent Class ────────────────────────────────────────────────────────────────

class RequirementQualityAgent(BaseAgent):
    """Quality-reviews extracted requirements and scores them."""

    async def run(self, requirements: list[dict]) -> "RequirementAgentResult":
        self._logs.clear()
        self.log("info", "start", f"Quality-reviewing {len(requirements)} requirements")

        if not requirements:
            return RequirementAgentResult(
                success=False,
                error="No requirements to review",
                data={},
                logs=self._logs,
            )

        initial_state: QualityState = {
            "requirements": requirements,
            "reviews": [],
            "errors": [],
        }

        final_state = await _graph.ainvoke(initial_state)

        reviewed = final_state["requirements"]
        errors = final_state["errors"]

        passes = sum(1 for r in reviewed if r.get("_quality_review", {}).get("verdict") == "pass")
        needs_rev = sum(1 for r in reviewed if r.get("_quality_review", {}).get("verdict") == "needs_revision")
        fails = sum(1 for r in reviewed if r.get("_quality_review", {}).get("verdict") == "fail")

        self.log("info", "complete", f"Pass: {passes}, Needs Revision: {needs_rev}, Fail: {fails}")
        for e in errors:
            self.log("warning", "warning", e)

        return RequirementAgentResult(
            success=True,
            data={
                "requirements": reviewed,
                "summary": {"pass": passes, "needs_revision": needs_rev, "fail": fails},
            },
            logs=self._logs,
        )

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(requirements=input_data.get("requirements", []))
        return result.data


class RequirementAgentResult:
    def __init__(self, success: bool, data: dict, logs: list, error: str | None = None):
        self.success = success
        self.data = data
        self.logs = logs
        self.error = error
