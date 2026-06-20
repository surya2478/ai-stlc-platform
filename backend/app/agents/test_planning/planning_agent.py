"""
Agent 3 — Test Planning Agent
Generates a structured test plan from approved requirements.
"""
import json
import re
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from app.agents.base.base_agent import BaseAgent
from app.agents.structured_schemas import TestPlanLLMOutput
from app.llm.provider import get_llm
from app.llm.structured import validate_structured_output, parse_and_validate_llm_output
from app.config import get_settings

settings = get_settings()


# ── State ──────────────────────────────────────────────────────────────────────

class PlanningState(TypedDict):
    requirements: list[dict]
    project_name: str
    test_plan: dict
    errors: list[str]


# ── LLM Prompt ────────────────────────────────────────────────────────────────

PLANNING_SYSTEM = """You are a QA Manager with 15 years of experience creating test plans for enterprise software.

Based on the provided requirements, create a comprehensive test plan with these sections:
- title: Title of the test plan
- scope: list of features/modules IN scope for testing
- out_of_scope: list of items explicitly OUT of scope
- test_types: list of testing types needed (e.g. functional, regression, performance, security, UAT)
- entry_criteria: list of conditions that must be met before testing begins
- exit_criteria: list of conditions that define when testing is complete
- risks: list of testing risks identified
- mitigations: list of risk mitigation strategies (corresponding to risks)
- automation_candidates: list of test areas best suited for automation
- estimated_effort: estimation of testing effort (e.g., "3 sprints, 2 QA engineers")
- resource_recommendation: recommended team composition and tools

Output ONLY a valid JSON object. No extra text.
"""


# ── Nodes ──────────────────────────────────────────────────────────────────────

async def _generate_plan(state: PlanningState) -> PlanningState:
    llm = get_llm(settings.default_llm_provider, settings.default_llm_model)
    errors = []

    req_summary = []
    for r in state["requirements"]:
        req_summary.append({
            "id": r.get("requirement_id", r.get("id")),
            "title": r.get("title"),
            "summary": r.get("summary"),
            "acceptance_criteria": r.get("acceptance_criteria", []),
            "risks": r.get("risks", []),
        })

    prompt = f"""Project: {state['project_name']}

Requirements ({len(req_summary)} total):
{json.dumps(req_summary, indent=2)}

Create a comprehensive test plan for this project."""

    try:
        response = await llm.generate(
            system=PLANNING_SYSTEM,
            user=prompt,
            temperature=0.2,
            max_tokens=4000,
        )
        test_plan = parse_and_validate_llm_output(response, TestPlanLLMOutput).model_dump(mode="json")
    except Exception as exc:
        test_plan = {}
        errors.append(f"Planning agent error: {str(exc)}")

    return {**state, "test_plan": test_plan, "errors": errors}


def _validate_plan(state: PlanningState) -> PlanningState:
    """Ensure all required keys are present in the plan."""
    errors = list(state["errors"])
    plan = state["test_plan"]
    required_keys = ["title", "scope", "test_types", "entry_criteria", "exit_criteria"]
    for key in required_keys:
        if key not in plan:
            plan[key] = []
    if "title" not in plan or not plan["title"]:
        plan["title"] = f"Test Plan — {state['project_name']}"
    return {**state, "test_plan": plan, "errors": errors}


# ── Graph ──────────────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    graph = StateGraph(PlanningState)
    graph.add_node("generate", _generate_plan)
    graph.add_node("validate", _validate_plan)
    graph.set_entry_point("generate")
    graph.add_edge("generate", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


_graph = _build_graph()


# ── Agent Class ────────────────────────────────────────────────────────────────

class TestPlanningAgent(BaseAgent):
    """Generates a structured test plan from approved requirements."""

    async def run(self, requirements: list[dict], project_name: str = "Project") -> "TestPlanAgentResult":
        self._logs.clear()
        self.log("info", "start", f"Creating test plan for '{project_name}' from {len(requirements)} requirements")

        if not requirements:
            return TestPlanAgentResult(
                success=False,
                error="No requirements provided for test planning",
                data={},
                logs=self._logs,
            )

        initial_state: PlanningState = {
            "requirements": requirements,
            "project_name": project_name,
            "test_plan": {},
            "errors": [],
        }

        final_state = await _graph.ainvoke(initial_state)

        plan = final_state["test_plan"]
        errors = final_state["errors"]

        for e in errors:
            self.log("warning", "warning", e)

        self.log("info", "complete", f"Test plan generated: '{plan.get('title', 'N/A')}'")

        return TestPlanAgentResult(
            success=True,
            data={"test_plan": plan},
            logs=self._logs,
        )

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(
            requirements=input_data.get("requirements", []),
            project_name=input_data.get("project_name", "Project"),
        )
        return result.data


class TestPlanAgentResult:
    def __init__(self, success: bool, data: dict, logs: list, error: str | None = None):
        self.success = success
        self.data = data
        self.logs = logs
        self.error = error
