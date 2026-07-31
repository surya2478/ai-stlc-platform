"""
UI Analysis Agent (GAP-1)
Analyses an uploaded UI screenshot with a vision-capable LLM and produces:
  1. A UI inventory: screen purpose, fields, buttons, links, implied validations,
     user flows, and edge/negative considerations.
  2. Structured requirements (same schema as the intake agent) so the existing
     quality review, scenario, and test case agents work downstream unchanged.

Two-step design:
  - "analyze" uses the vision model (Ollama llava/qwen2.5vl or any
    OpenAI-compatible vision model) for visual extraction.
  - "derive" uses the standard text model, which is stronger at strict JSON
    schema adherence, to convert the analysis into requirement records.
"""
import base64
import json
import re
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from app.agents.base.base_agent import AgentRunResult, BaseAgent
from app.agents.structured_schemas import RequirementLLMOutput
from app.llm.provider import get_llm, get_vision_llm
from app.llm.structured import validate_structured_output
from app.config import get_settings

settings = get_settings()


# ── State ──────────────────────────────────────────────────────────────────────

class UIAnalysisState(TypedDict):
    image_path: str
    image_name: str
    context_note: str
    project_id: int
    ui_analysis: dict
    requirements: list[dict]
    errors: list[str]


# ── Prompts ────────────────────────────────────────────────────────────────────

VISION_SYSTEM = """You are a senior QA engineer analysing a UI screenshot of a Telecom OSS/BSS or customer portal application.

Examine the screenshot carefully and produce a JSON object with these keys:
- screen_name: short name for this screen/page
- screen_purpose: 1-2 sentences on what this screen does
- fields: list of objects {"name": str, "type": "text|email|phone|password|number|date|dropdown|checkbox|radio|file|toggle|search", "required": true|false|null, "validations": [list of likely validation rules]}
- buttons: list of objects {"label": str, "action": "what it likely does"}
- links: list of visible navigation links or tabs
- user_flows: list of strings describing the user journeys this screen supports (e.g. "User fills the form and submits to register")
- validation_rules: list of validation behaviours implied by the UI (mandatory markers, formats, ranges, masks)
- negative_scenarios: list of negative/error cases to test (invalid input, empty submit, boundary lengths)
- edge_cases: list of edge cases (long values, special characters, concurrent actions, slow network states)
- accessibility_notes: list of visible accessibility considerations or gaps

Be exhaustive about fields and buttons — list every visible interactive element.
Output ONLY a valid JSON object. No extra text."""

DERIVE_SYSTEM = """You are a senior QA business analyst. You receive a structured analysis of a UI screenshot.
Convert it into 1-3 testable requirements for the screen.

For each requirement output a JSON object with these keys:
- title: concise requirement title (max 120 chars)
- summary: 2-3 sentence description of the required behaviour
- acceptance_criteria: list of specific, testable acceptance criteria covering positive, negative, and boundary behaviour of the fields/buttons/validations
- business_rules: list of business rules implied by the UI
- user_roles: list of user roles involved
- systems_impacted: list of systems/modules likely involved
- ui_pages: list containing the screen name and any linked pages
- apis: list of likely backend APIs invoked (e.g. "POST /api/register")
- dependencies: list of dependencies
- risks: list of identified risks
- missing_information: list of objects, each {"item": "<detail not visible in the
  screenshot>", "severity": "blocking" | "advisory"}.
  Severity test: can a tester write and execute a meaningful test case without
  this answer? "blocking" if not (the endpoint behind a button, the validation
  rule, the destination of a navigation); "advisory" if it would only improve
  polish (exact message wording, label text, styling). A screenshot shows
  behaviour, not intent, so expect several genuine unknowns — but only mark as
  blocking the ones that actually prevent testing.
- telecom_domain: best-fit domain from [Mobile, Fixed, Digital, Billing, Charging, CRM, OSS, BSS, Middleware, Integration, Network, Data] or null
- impacted_interfaces: list of interfaces/protocols
- risk_level: "Critical" | "High" | "Medium" | "Low"
- test_phase: "SIT" | "QA" | "UAT" | "Regression" | "Production Smoke Test" | null
- release_version: null
- upstream_systems: []
- downstream_systems: []
- regulatory_impact: true|false
- revenue_impact: true|false

Output ONLY a valid JSON array of requirement objects. No extra text."""


def _parse_json_block(text: str) -> Any:
    """Extract the first JSON object/array from LLM output."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for pattern in (r"\[.*\]", r"\{.*\}"):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    return None


# ── Nodes ──────────────────────────────────────────────────────────────────────

async def _analyze_image(state: UIAnalysisState) -> UIAnalysisState:
    """Run the vision model over the screenshot."""
    errors = list(state["errors"])
    image_path = Path(state["image_path"])
    if not image_path.exists():
        return {**state, "errors": errors + [f"Image file not found: {image_path}"]}

    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    vision_llm = get_vision_llm()

    user_prompt = "Analyse this UI screenshot and return the JSON object."
    if state.get("context_note"):
        user_prompt += f"\n\nAdditional context from the tester: {state['context_note']}"

    try:
        response = await vision_llm.generate_vision(
            system=VISION_SYSTEM,
            user=user_prompt,
            images_b64=[image_b64],
            temperature=0.1,
            max_tokens=4000,
        )
        parsed = _parse_json_block(response)
        if isinstance(parsed, dict):
            return {**state, "ui_analysis": parsed, "errors": errors}
        errors.append("Vision model did not return a valid JSON object")
    except Exception as exc:
        errors.append(f"Vision analysis error: {exc}")
    return {**state, "errors": errors}


async def _derive_requirements(state: UIAnalysisState) -> UIAnalysisState:
    """Convert the UI analysis into structured requirements via the text model."""
    errors = list(state["errors"])
    analysis = state.get("ui_analysis") or {}
    if not analysis:
        return {**state, "requirements": [], "errors": errors}

    llm = get_llm(settings.default_llm_provider, settings.default_llm_model)
    prompt = (
        f"UI screenshot analysis for image '{state['image_name']}':\n\n"
        f"{json.dumps(analysis, indent=2)}\n\n"
        "Convert this into requirement objects. Return a JSON array."
    )
    requirements: list[dict] = []
    try:
        response = await llm.generate(
            system=DERIVE_SYSTEM,
            user=prompt,
            temperature=0.1,
            max_tokens=4000,
        )
        parsed = _parse_json_block(response)
        items = parsed if isinstance(parsed, list) else [parsed] if isinstance(parsed, dict) else []
        for item in items:
            try:
                validated = validate_structured_output(item, RequirementLLMOutput).model_dump(mode="json")
                requirements.append(validated)
            except Exception as exc:
                errors.append(f"Requirement schema validation failed: {exc}")
    except Exception as exc:
        errors.append(f"Requirement derivation error: {exc}")

    return {**state, "requirements": requirements, "errors": errors}


# ── Graph ──────────────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    graph = StateGraph(UIAnalysisState)
    graph.add_node("analyze", _analyze_image)
    graph.add_node("derive", _derive_requirements)
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "derive")
    graph.add_edge("derive", END)
    return graph.compile()


_graph = _build_graph()


# ── Agent Class ────────────────────────────────────────────────────────────────

class UIAnalysisAgent(BaseAgent):
    """Generates structured requirements from a UI screenshot (GAP-1)."""

    async def run(
        self,
        image_path: str,
        image_name: str = "screenshot",
        context_note: str = "",
        project_id: int = 0,
    ) -> AgentRunResult:
        self._logs.clear()
        self.log("info", "start", f"Analysing UI screenshot '{image_name}' for project {project_id}")

        if not image_path:
            return AgentRunResult(
                success=False, error="No image path provided", data={}, logs=self._logs
            )

        initial_state: UIAnalysisState = {
            "image_path": image_path,
            "image_name": image_name,
            "context_note": context_note or "",
            "project_id": project_id,
            "ui_analysis": {},
            "requirements": [],
            "errors": [],
        }

        final_state = await _graph.ainvoke(initial_state)
        reqs = final_state["requirements"]
        analysis = final_state["ui_analysis"]
        errors = final_state["errors"]

        self.log(
            "info", "complete",
            f"Vision analysis found {len(analysis.get('fields', []))} fields, "
            f"{len(analysis.get('buttons', []))} buttons; derived {len(reqs)} requirements",
        )
        for e in errors:
            self.log("warning", "warning", e)

        if not reqs:
            return AgentRunResult(
                success=False,
                error="UI analysis produced no requirements. " + "; ".join(errors[:3]),
                data={"ui_analysis": analysis, "requirements": [], "count": 0},
                logs=self._logs,
            )

        return AgentRunResult(
            success=True,
            data={"ui_analysis": analysis, "requirements": reqs, "count": len(reqs)},
            logs=self._logs,
        )

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(
            image_path=input_data.get("image_path", ""),
            image_name=input_data.get("image_name", "screenshot"),
            context_note=input_data.get("context_note", ""),
            project_id=input_data.get("project_id", 0),
        )
        return result.data
