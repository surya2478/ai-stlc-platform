"""
Agent 9 — Defect Analysis Agent
Analyses failed test execution results and generates structured defect draft reports.
"""
import json
import re
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from app.agents.base.base_agent import AgentRunResult, BaseAgent
from app.agents.structured_schemas import DefectLLMOutput
from app.llm.provider import get_llm
from app.llm.structured import validate_structured_output, clean_json_text
from app.config import get_settings

settings = get_settings()


# ── State ──────────────────────────────────────────────────────────────────────

class DefectState(TypedDict):
    failed_results: list[dict]
    project_name: str
    defects: list[dict]
    errors: list[str]


# ── Prompts ───────────────────────────────────────────────────────────────────

DEFECT_SYSTEM = """You are a senior QA engineer writing defect reports from failed automated tests.

For each failed test result, generate a structured defect draft. Each defect object must contain:
- execution_result_ref: the test_case_id or test_name of the failing test
- summary: concise one-line defect summary (max 120 chars, starts with verb e.g. "Login fails when...")
- description: detailed description of the defect (2-3 sentences explaining what is broken)
- steps_to_reproduce: ordered list of steps to reproduce the defect
- expected_result: what should have happened
- actual_result: what actually happened (derived from the error_message)
- severity: "Critical" | "High" | "Medium" | "Low"
  - Critical: system crash, data loss, security breach
  - High: core feature broken, no workaround
  - Medium: feature partially broken, workaround exists
  - Low: cosmetic, minor UX issue
- priority: "Critical" | "High" | "Medium" | "Low" (can differ from severity)
- root_cause_hypothesis: short hypothesis of the root cause (1-2 sentences)
- classification: "product_defect" | "automation_issue" | "environment_issue" | "test_data_issue"
  - TimeoutError → possibly "environment_issue"
  - AssertionError on wrong value → "product_defect"
  - NullPointerException / TypeError → "product_defect"
  - Test setup failures → "automation_issue"

Output ONLY a valid JSON array of defect objects. No extra text.
"""


# ── Nodes ──────────────────────────────────────────────────────────────────────

import logging as _logging
_logger = _logging.getLogger(__name__)


def _repair_json(text: str) -> str:
    """Escape raw control characters inside JSON string values."""
    result = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == '\n': result.append('\\n')
            elif ch == '\r': result.append('\\r')
            elif ch == '\t': result.append('\\t')
            elif ord(ch) < 0x20: result.append(f'\\u{ord(ch):04x}')
            else: result.append(ch)
        else:
            result.append(ch)
    return ''.join(result)


def _parse_defects_json(text: str) -> tuple[list, str | None]:
    """Parse a JSON array of defects from LLM text. Returns (defects, error)."""
    clean = re.sub(r'```(?:json)?\s*', '', text).replace('```', '').strip()

    def _try(s):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json(s))
            except json.JSONDecodeError:
                return None

    # Try full parse
    parsed = _try(clean)
    if isinstance(parsed, list):
        return parsed, None

    # Extract [...] array
    cleaned_obj = clean_json_text(clean)
    if cleaned_obj.startswith("["):
        parsed = _try(cleaned_obj)
        if isinstance(parsed, list):
            return parsed, None
        return [], f"JSON parse error after repair. Snippet: {text[:200]}"

    return [], f"No JSON array found. Snippet: {text[:200]}"


async def _analyse_defects(state: DefectState) -> DefectState:
    llm = get_llm(settings.default_llm_provider, settings.default_llm_model)
    errors = []
    defects = []

    if not state["failed_results"]:
        return {**state, "defects": [], "errors": ["No failed results to analyse"]}

    prompt = f"""Project: {state['project_name']}

Analyse these {len(state['failed_results'])} failed test results and generate defect reports:

{json.dumps(state['failed_results'], indent=2)}"""

    try:
        response = await llm.achat(
            messages=[
                {"role": "system", "content": DEFECT_SYSTEM},
                {"role": "user", "content": prompt},
            ]
        )
        text = response.strip()
        _logger.info("Defect LLM response: %d chars", len(text))
        defects, err = _parse_defects_json(text)
        if err:
            errors.append(err)
            _logger.error("Defect JSON parse failed: %s", err)
        if not defects:
            errors.append("LLM returned 0 parseable defects")
    except Exception as exc:
        exc_str = str(exc)
        if "rate_limit_exceeded" in exc_str or "429" in exc_str:
            wait_match = re.search(r'try again in ([\d.]+[smh])', exc_str)
            hint = f" Try again in {wait_match.group(1)}." if wait_match else " Daily quota may be exhausted."
            errors.append(f"Groq rate limit hit.{hint}")
            _logger.warning("Defect agent rate-limited: %s", exc_str[:200])
        else:
            errors.append(f"Defect agent error: {exc_str}")
            _logger.exception("Defect agent LLM call failed")

    return {**state, "defects": defects, "errors": errors}


def _validate_defects(state: DefectState) -> DefectState:
    """Ensure all required fields are present."""
    validated = []
    errors = list(state["errors"])
    for d in state["defects"]:
        try:
            d = validate_structured_output(d, DefectLLMOutput).model_dump(mode="json")
        except Exception as exc:
            errors.append(f"Defect schema validation failed: {exc}")
            continue
        validated.append({
            "execution_result_ref": d.get("execution_result_ref", "unknown"),
            "summary": d.get("summary", "Defect detected in automated test"),
            "description": d.get("description", ""),
            "steps_to_reproduce": d.get("steps_to_reproduce", []),
            "expected_result": d.get("expected_result", ""),
            "actual_result": d.get("actual_result", ""),
            "severity": d.get("severity", "Medium"),
            "priority": d.get("priority", "Medium"),
            "root_cause_hypothesis": d.get("root_cause_hypothesis", ""),
            "classification": d.get("classification", "product_defect"),
        })
    return {**state, "defects": validated, "errors": errors}


# ── Graph ──────────────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    graph = StateGraph(DefectState)
    graph.add_node("analyse", _analyse_defects)
    graph.add_node("validate", _validate_defects)
    graph.set_entry_point("analyse")
    graph.add_edge("analyse", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


_graph = _build_graph()


# ── Agent Class ────────────────────────────────────────────────────────────────

class DefectAnalysisAgent(BaseAgent):
    """Analyses failed test results and generates structured defect drafts."""

    async def run(
        self,
        failed_results: list[dict],
        project_name: str = "Project",
    ) -> AgentRunResult:
        self._logs.clear()
        self.log("info", "start", f"Analysing {len(failed_results)} failed test results")

        if not failed_results:
            return AgentRunResult(
                success=False,
                error="No failed results to analyse",
                data={"defects": []},
                logs=self._logs,
            )

        initial_state: DefectState = {
            "failed_results": failed_results,
            "project_name": project_name,
            "defects": [],
            "errors": [],
        }

        final_state = await _graph.ainvoke(initial_state)
        defects = final_state["defects"]
        errors = final_state["errors"]

        for e in errors:
            self.log("warning", "warning", e)

        self.log("info", "complete", f"Generated {len(defects)} defect drafts")

        return AgentRunResult(
            success=True,
            data={"defects": defects},
            logs=self._logs,
        )

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(
            failed_results=input_data.get("failed_results", []),
            project_name=input_data.get("project_name", "Project"),
        )
        return result.data
