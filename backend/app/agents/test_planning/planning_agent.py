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
    if not _has_meaningful_plan_content(plan):
        plan = _fallback_plan_from_requirements(state["requirements"], state["project_name"])
        errors.append("Planning agent returned an empty plan; generated fallback content from approved requirements.")

    required_keys = ["scope", "out_of_scope", "test_types", "entry_criteria", "exit_criteria", "risks", "mitigations", "automation_candidates"]
    for key in required_keys:
        if key not in plan or plan[key] is None:
            plan[key] = []
    if "title" not in plan or not plan["title"]:
        plan["title"] = f"Test Plan — {state['project_name']}"
    return {**state, "test_plan": plan, "errors": errors}


# ── Graph ──────────────────────────────────────────────────────────────────────

def _has_meaningful_plan_content(plan: dict) -> bool:
    section_keys = ("scope", "test_types", "entry_criteria", "exit_criteria", "risks", "mitigations", "automation_candidates")
    return any(bool(plan.get(key)) for key in section_keys)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _fallback_plan_from_requirements(requirements: list[dict], project_name: str) -> dict:
    scope = []
    entry_criteria = ["Approved requirements are baselined and available for test design."]
    exit_criteria = [
        "All planned functional, regression, and risk-based tests are executed.",
        "Critical and high severity defects are resolved or formally accepted.",
        "Traceability from requirements to test scenarios and test cases is complete.",
    ]
    risks = []
    automation_candidates = []

    for req in requirements:
        req_ref = req.get("requirement_id") or req.get("id") or "REQ"
        title = req.get("title") or "Untitled requirement"
        summary = req.get("summary")
        scope.append(f"{req_ref}: {title}" + (f" - {summary}" if summary else ""))
        for criterion in _as_list(req.get("acceptance_criteria")):
            entry_criteria.append(f"{req_ref}: Acceptance criterion available - {criterion}")
        for risk in _as_list(req.get("risks")):
            risks.append(f"{req_ref}: {risk}")
        automation_candidates.append(f"{req_ref}: Regression coverage for {title}")

    return {
        "title": f"Test Plan - {project_name}",
        "scope": scope,
        "out_of_scope": ["Items not covered by the selected approved requirements."],
        "test_types": ["Functional", "Regression", "Integration", "Security", "User Acceptance"],
        "entry_criteria": entry_criteria,
        "exit_criteria": exit_criteria,
        "risks": risks,
        "mitigations": ["Prioritize high-risk requirements and validate acceptance criteria before execution."],
        "automation_candidates": automation_candidates,
        "estimated_effort": f"Depends on execution depth for {len(requirements)} approved requirement(s).",
        "resource_recommendation": "QA lead, functional QA engineer, automation engineer, and domain/business reviewer.",
    }


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
