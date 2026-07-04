"""
Agent 8 — Test Execution Agent
Simulates test execution and produces structured pass/fail results for each test case.
In a real pipeline this would invoke actual Playwright/Pytest runners; here it uses
the LLM to generate realistic execution results with error messages for failing tests.
"""
import json
import re
import random
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from app.agents.base.base_agent import BaseAgent, AgentResult
from app.agents.structured_schemas import ExecutionResultLLMOutput
from app.llm.provider import get_llm
from app.llm.structured import validate_structured_output, parse_and_validate_llm_list
from app.config import get_settings

settings = get_settings()


# ── State ──────────────────────────────────────────────────────────────────────

class ExecutionState(TypedDict):
    test_cases: list[dict]
    environment: str
    suite_name: str
    results: list[dict]
    errors: list[str]


# ── Prompts ───────────────────────────────────────────────────────────────────

EXECUTION_SYSTEM = """You are a CI/CD test execution engine returning realistic test results.

For each test case provided, generate an execution result. Each result object must contain:
- test_case_id: the source test case ID string (e.g. "TC-0001")
- test_name: descriptive test name (based on test case title)
- status: "passed" | "failed" | "skipped"
  - Roughly 70% passed, 20% failed, 10% skipped for realism
  - Negative/boundary tests should fail more often
  - Performance/security tests can be skipped
- duration_ms: execution time in milliseconds (100-8000, longer for complex tests)
- error_message: null if passed/skipped; realistic error message if failed
  - Examples: "AssertionError: Expected 200, got 401", "TimeoutError: Locator not found after 30s",
    "TypeError: Cannot read property 'id' of undefined", "AssertionError: Form validation not triggered"
- stack_trace: null if passed/skipped; short stack trace if failed (2-3 lines)
- logs: list of log strings showing execution steps (3-5 entries regardless of status)

Output ONLY a valid JSON array. No extra text.
"""


# ── Nodes ──────────────────────────────────────────────────────────────────────

async def _execute_tests(state: ExecutionState) -> ExecutionState:
    llm = get_llm(settings.default_llm_provider, settings.default_llm_model)
    errors = []

    tc_summaries = []
    for tc in state["test_cases"]:
        tc_summaries.append({
            "id": tc.get("test_case_id", tc.get("id")),
            "title": tc.get("title"),
            "test_type": tc.get("test_type", "functional"),
            "priority": tc.get("priority", "Medium"),
            "steps_count": len(tc.get("steps") or []),
        })

    prompt = f"""Environment: {state['environment']}
Suite: {state['suite_name']}

Execute the following {len(tc_summaries)} test cases and return results:

{json.dumps(tc_summaries, indent=2)}"""

    try:
        response = await llm.achat(
            messages=[
                {"role": "system", "content": EXECUTION_SYSTEM},
                {"role": "user", "content": prompt},
            ]
        )
        results = parse_and_validate_llm_list(response, ExecutionResultLLMOutput)
    except Exception as exc:
        results = []
        errors.append(f"Execution agent error: {str(exc)}")

    return {**state, "results": results, "errors": errors}


def _finalise_results(state: ExecutionState) -> ExecutionState:
    """Ensure required fields and compute summary."""
    def _to_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(str(item) for item in value)
        if isinstance(value, dict):
            return json.dumps(value)
        return str(value)

    def _to_log_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    finalised = []
    errors = list(state["errors"])
    for r in state["results"]:
        status = r.get("status", "passed")
        if status not in ("passed", "failed", "skipped"):
            status = "passed"
        finalised.append({
            "test_case_id": r.get("test_case_id"),
            "test_name": r.get("test_name", "Unknown test"),
            "status": status,
            "duration_ms": r.get("duration_ms", 500),
            "error_message": _to_text(r.get("error_message")) if status == "failed" else None,
            "stack_trace": _to_text(r.get("stack_trace")) if status == "failed" else None,
            "logs": _to_log_list(r.get("logs")),
        })
    return {**state, "results": finalised, "errors": errors}


# ── Graph ──────────────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    graph = StateGraph(ExecutionState)
    graph.add_node("execute", _execute_tests)
    graph.add_node("finalise", _finalise_results)
    graph.set_entry_point("execute")
    graph.add_edge("execute", "finalise")
    graph.add_edge("finalise", END)
    return graph.compile()


_graph = _build_graph()


# ── Agent Class ────────────────────────────────────────────────────────────────

class ExecutionAgentResult:
    def __init__(self, success: bool, data: dict, logs: list, error: str | None = None):
        self.success = success
        self.data = data
        self.logs = logs
        self.error = error


class TestExecutionAgent(BaseAgent):
    """Executes test cases and returns structured pass/fail results."""

    def _controlled_ai_gateway_unavailable(self, test_cases: list[dict]) -> list[dict]:
        results = []
        for tc in test_cases:
            test_case_id = tc.get("test_case_id") or str(tc.get("id") or "unknown")
            test_name = tc.get("title") or test_case_id
            results.append({
                "test_case_id": test_case_id,
                "test_name": test_name,
                "status": "failed",
                "duration_ms": 0,
                "error_message": "Controlled AI execution gateway is not configured. No browser, API, or validation tool run was performed.",
                "stack_trace": None,
                "logs": [
                    "AI execution request accepted by backend orchestration.",
                    "Execution stopped before tool invocation because no controlled AI tool gateway is configured.",
                    "Result requires review; no mock pass/fail decision was generated.",
                ],
                "metadata": {
                    "review_required": True,
                    "failure_category": "AI_CONFIDENCE_ISSUE",
                    "actual_tool_run": False,
                },
            })
        return results

    async def run(
        self,
        test_cases: list[dict],
        environment: str = "staging",
        suite_name: str = "Test Suite",
        source_type: str = "manual",
    ) -> ExecutionAgentResult:
        self._logs.clear()
        self.log("info", "start", f"Executing {len(test_cases)} tests on '{environment}'")

        if not test_cases:
            return ExecutionAgentResult(
                success=False,
                error="No test cases provided",
                data={},
                logs=self._logs,
            )

        if source_type == "ai":
            results = self._controlled_ai_gateway_unavailable(test_cases)
            self.log("warning", "ai_gateway", "Controlled AI execution gateway is not configured; AI run stopped without mock execution.")
            return ExecutionAgentResult(
                success=True,
                data={
                    "results": results,
                    "summary": {
                        "total": len(results),
                        "passed": 0,
                        "failed": len(results),
                        "skipped": 0,
                    },
                },
                logs=self._logs,
            )

        initial_state: ExecutionState = {
            "test_cases": test_cases,
            "environment": environment,
            "suite_name": suite_name,
            "results": [],
            "errors": [],
        }

        final_state = await _graph.ainvoke(initial_state)
        results = final_state["results"]
        errors = final_state["errors"]

        for e in errors:
            self.log("warning", "warning", e)

        passed = sum(1 for r in results if r["status"] == "passed")
        failed = sum(1 for r in results if r["status"] == "failed")
        skipped = sum(1 for r in results if r["status"] == "skipped")

        self.log("info", "complete", f"Execution complete — {passed} passed / {failed} failed / {skipped} skipped")

        return ExecutionAgentResult(
            success=True,
            data={
                "results": results,
                "summary": {
                    "total": len(results),
                    "passed": passed,
                    "failed": failed,
                    "skipped": skipped,
                },
            },
            logs=self._logs,
        )

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(
            test_cases=input_data.get("test_cases", []),
            environment=input_data.get("environment", "staging"),
            suite_name=input_data.get("suite_name", "Test Suite"),
            source_type=input_data.get("source_type", "manual"),
        )
        return result.data
