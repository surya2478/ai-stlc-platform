"""
Agent 11 - Test Reporting Agent
Aggregates STLC metrics and generates an AI-written QA status report with
coverage analysis, defect trends, risk assessment, and recommendations.
"""
import json
import re
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from app.agents.base.base_agent import AgentRunResult, BaseAgent
from app.agents.structured_schemas import ReportLLMOutput
from app.llm.provider import get_llm
from app.llm.structured import validate_structured_output, parse_and_validate_llm_output
from app.config import get_settings

settings = get_settings()


class ReportState(TypedDict):
    project_name: str
    report_type: str
    metrics: dict
    report: dict
    errors: list[str]


REPORT_SYSTEM = """You are a QA Lead writing an executive-level test status report.

Given the project metrics, generate a structured report with:
- title: Report title including project name and report type
- summary: 2-3 sentence executive summary of current QA health
- coverage: dict with keys:
    requirements_total, requirements_approved, requirements_coverage_pct,
    test_cases_total, test_cases_approved, scenarios_total,
    automation_candidate_count, automation_coverage_pct
- execution_metrics: dict with keys:
    total_runs, latest_pass_pct, total_passed, total_failed, total_skipped,
    flaky_tests (estimated), avg_duration_note
- defect_metrics: dict with keys:
    total_defects, critical_count, high_count, medium_count, low_count,
    open_defects, pushed_to_jira, product_defect_pct
- risks: list of 3-5 risk strings (current QA risks based on metrics)
- recommendations: list of 3-5 actionable recommendation strings

Output ONLY a valid JSON object. No extra text.
"""


async def _generate_report(state: ReportState) -> ReportState:
    llm = get_llm(settings.default_llm_provider, settings.default_llm_model)
    errors = []

    prompt = f"""Project: {state['project_name']}
Report Type: {state['report_type']}

Current Metrics:
{json.dumps(state['metrics'], indent=2)}

Generate a comprehensive QA status report."""

    try:
        response = await llm.achat(
            messages=[
                {"role": "system", "content": REPORT_SYSTEM},
                {"role": "user", "content": prompt},
            ]
        )
        report = parse_and_validate_llm_output(response, ReportLLMOutput).model_dump(mode="json")
    except Exception as exc:
        report = {}
        errors.append(f"Reporting agent error: {str(exc)}")

    return {**state, "report": report, "errors": errors}


def _validate_report(state: ReportState) -> ReportState:
    errors = list(state["errors"])
    r = state["report"]
    if not r.get("title"):
        r["title"] = f"{state['report_type'].capitalize()} QA Report - {state['project_name']}"
    if not r.get("summary"):
        r["summary"] = "QA report generated."
    for key in ("coverage", "execution_metrics", "defect_metrics"):
        if key not in r:
            r[key] = {}
    for key in ("risks", "recommendations"):
        if key not in r:
            r[key] = []
    return {**state, "report": r, "errors": errors}


def _build_graph() -> Any:
    graph = StateGraph(ReportState)
    graph.add_node("generate", _generate_report)
    graph.add_node("validate", _validate_report)
    graph.set_entry_point("generate")
    graph.add_edge("generate", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


_graph = _build_graph()


class TestReportingAgent(BaseAgent):
    """Aggregates STLC metrics and writes a structured QA status report."""

    async def run(self, metrics: dict, project_name: str, report_type: str = "sprint") -> AgentRunResult:
        self._logs.clear()
        self.log("info", "start", f"Generating {report_type} report for '{project_name}'")

        initial_state: ReportState = {
            "project_name": project_name,
            "report_type": report_type,
            "metrics": metrics,
            "report": {},
            "errors": [],
        }
        final_state = await _graph.ainvoke(initial_state)
        report = final_state["report"]

        for e in final_state["errors"]:
            self.log("warning", "warning", e)

        self.log("info", "complete", f"Report generated: '{report.get('title', '')}'")

        return AgentRunResult(
            success=True,
            data={"report": report},
            logs=self._logs,
        )

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(
            metrics=input_data.get("metrics", {}),
            project_name=input_data.get("project_name", "Project"),
            report_type=input_data.get("report_type", "sprint"),
        )
        return result.data
