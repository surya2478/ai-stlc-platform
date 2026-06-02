"""
Agent 4 — Test Scenario Agent
Generates high-level test scenarios from approved requirements.
"""
import json
import re
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from app.agents.base.base_agent import BaseAgent
from app.llm.provider import get_llm
from app.config import get_settings

settings = get_settings()


# ── State ──────────────────────────────────────────────────────────────────────

class ScenarioState(TypedDict):
    requirements: list[dict]
    scenarios: list[dict]
    errors: list[str]


# ── LLM Prompt ────────────────────────────────────────────────────────────────

SCENARIO_SYSTEM = """You are a senior QA engineer generating test scenarios from requirements.

A TEST SCENARIO is a high-level description of what needs to be tested, representing a complete user flow or feature behavior. It is NOT a detailed test case — it is the "what to test" without the specific "how".

For each requirement, generate 2-6 test scenarios. Each scenario must have:
- requirement_title: the title of the source requirement
- scenario_id: a unique identifier like "TS-001", "TS-002", etc. (auto-number globally)
- title: concise scenario title (max 120 chars)
- description: 2-3 sentence description of what this scenario covers
- scenario_type: one of: positive | negative | edge | boundary | integration | security | performance | accessibility
- priority: High | Medium | Low (based on requirement importance and risk)
- coverage_mapping: list of feature areas or tags this scenario covers (strings)

Output ONLY a valid JSON array of scenario objects. No extra text.
"""


# ── Nodes ──────────────────────────────────────────────────────────────────────

async def _generate_scenarios(state: ScenarioState) -> ScenarioState:
    llm = get_llm(settings.default_llm_provider, settings.default_llm_model)
    all_scenarios = []
    errors = []
    scenario_counter = 1

    # Process each requirement individually for better quality
    for req in state["requirements"]:
        req_text = json.dumps({
            "title": req.get("title"),
            "summary": req.get("summary"),
            "acceptance_criteria": req.get("acceptance_criteria", []),
            "business_rules": req.get("business_rules", []),
            "user_roles": req.get("user_roles", []),
            "systems_impacted": req.get("systems_impacted", []),
        }, indent=2)

        prompt = f"""Requirement:
{req_text}

Generate 3-5 test scenarios for this requirement. Start scenario IDs at TS-{scenario_counter:03d}.
Output a JSON array."""

        try:
            response = await llm.generate(
                system=SCENARIO_SYSTEM,
                user=prompt,
                temperature=0.3,
                max_tokens=2000,
            )
            text = response.strip()
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                scenarios = json.loads(match.group(0))
                # Tag with source requirement
                for s in scenarios:
                    s["_source_requirement_title"] = req.get("title")
                    s["_source_requirement_id"] = req.get("id") or req.get("requirement_id")
                all_scenarios.extend(scenarios)
                scenario_counter += len(scenarios)
        except Exception as exc:
            errors.append(f"Scenario gen error for '{req.get('title', 'unknown')}': {str(exc)}")

    return {**state, "scenarios": all_scenarios, "errors": errors}


# ── Graph ──────────────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    graph = StateGraph(ScenarioState)
    graph.add_node("generate", _generate_scenarios)
    graph.set_entry_point("generate")
    graph.add_edge("generate", END)
    return graph.compile()


_graph = _build_graph()


# ── Agent Class ────────────────────────────────────────────────────────────────

class TestScenarioAgent(BaseAgent):
    """Generates test scenarios from approved requirements."""

    async def run(self, requirements: list[dict]) -> "ScenarioAgentResult":
        self._logs.clear()
        self.log("info", "start", f"Generating test scenarios from {len(requirements)} requirements")

        if not requirements:
            return ScenarioAgentResult(
                success=False,
                error="No requirements provided",
                data={},
                logs=self._logs,
            )

        initial_state: ScenarioState = {
            "requirements": requirements,
            "scenarios": [],
            "errors": [],
        }

        final_state = await _graph.ainvoke(initial_state)

        scenarios = final_state["scenarios"]
        errors = final_state["errors"]

        self.log("info", "complete", f"Generated {len(scenarios)} test scenarios")
        for e in errors:
            self.log("warning", "warning", e)

        return ScenarioAgentResult(
            success=True,
            data={"scenarios": scenarios, "count": len(scenarios)},
            logs=self._logs,
        )

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(requirements=input_data.get("requirements", []))
        return result.data


class ScenarioAgentResult:
    def __init__(self, success: bool, data: dict, logs: list, error: str | None = None):
        self.success = success
        self.data = data
        self.logs = logs
        self.error = error
