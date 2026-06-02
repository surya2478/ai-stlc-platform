"""
Agent 1 — Requirement Intake Agent
Parses raw document text into structured requirements using LangGraph.
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

class IntakeState(TypedDict):
    document_text: str
    project_id: int
    chunks: list[str]
    requirements: list[dict]
    errors: list[str]


# ── LLM Prompt ────────────────────────────────────────────────────────────────

INTAKE_SYSTEM = """You are a senior QA engineer and business analyst.
Your task is to extract and structure requirements from the provided document text.

For each distinct requirement you identify, output a JSON object with these keys:
- title: concise requirement title (max 120 chars)
- summary: 2-3 sentence description of what is required
- acceptance_criteria: list of testable acceptance criteria (strings)
- business_rules: list of business rules mentioned
- user_roles: list of user roles / personas involved
- systems_impacted: list of systems, modules, or components affected
- ui_pages: list of UI screens or pages mentioned
- apis: list of API endpoints or integrations mentioned
- dependencies: list of dependencies on other requirements or systems
- risks: list of identified risks
- missing_information: list of unclear or missing details that need clarification

Output ONLY a valid JSON array of requirement objects. No extra text.
"""


# ── Nodes ──────────────────────────────────────────────────────────────────────

def _chunk_text(state: IntakeState) -> IntakeState:
    """Split large documents into overlapping chunks of ~3000 chars."""
    text = state["document_text"]
    chunk_size = 3000
    overlap = 300
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return {**state, "chunks": chunks}


async def _extract_requirements(state: IntakeState) -> IntakeState:
    """Run LLM over each chunk to extract requirements."""
    llm = get_llm(settings.default_llm_provider, settings.default_llm_model)
    all_requirements = []
    errors = []

    for i, chunk in enumerate(state["chunks"]):
        prompt = f"""Document excerpt (chunk {i+1}/{len(state['chunks'])}):\n\n{chunk}

Extract all requirements from this excerpt. Return a JSON array."""
        try:
            response = await llm.generate(
                system=INTAKE_SYSTEM,
                user=prompt,
                temperature=0.1,
                max_tokens=4000,
            )
            # Extract JSON from response
            text = response.strip()
            # Find JSON array in response
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                reqs = json.loads(match.group(0))
                all_requirements.extend(reqs)
        except Exception as exc:
            errors.append(f"Chunk {i+1} extraction error: {str(exc)}")

    return {**state, "requirements": all_requirements, "errors": errors}


def _deduplicate(state: IntakeState) -> IntakeState:
    """Remove obvious duplicates by title similarity."""
    seen_titles = set()
    unique = []
    for req in state["requirements"]:
        title = req.get("title", "").strip().lower()
        if title and title not in seen_titles:
            seen_titles.add(title)
            unique.append(req)
    return {**state, "requirements": unique}


# ── Graph ──────────────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    graph = StateGraph(IntakeState)
    graph.add_node("chunk", _chunk_text)
    graph.add_node("extract", _extract_requirements)
    graph.add_node("deduplicate", _deduplicate)
    graph.set_entry_point("chunk")
    graph.add_edge("chunk", "extract")
    graph.add_edge("extract", "deduplicate")
    graph.add_edge("deduplicate", END)
    return graph.compile()


_graph = _build_graph()


# ── Agent Class ────────────────────────────────────────────────────────────────

class RequirementIntakeAgent(BaseAgent):
    """Extracts structured requirements from uploaded document text."""

    async def run(self, document_text: str, project_id: int) -> "RequirementAgentResult":
        self._logs.clear()
        self.log("info", "start", f"Starting requirement intake for project {project_id}")
        self.log("info", "info", f"Document length: {len(document_text)} chars")

        if not document_text.strip():
            return RequirementAgentResult(
                success=False,
                error="Document text is empty",
                data={},
                logs=self._logs,
            )

        initial_state: IntakeState = {
            "document_text": document_text,
            "project_id": project_id,
            "chunks": [],
            "requirements": [],
            "errors": [],
        }

        final_state = await _graph.ainvoke(initial_state)

        reqs = final_state["requirements"]
        errors = final_state["errors"]

        self.log("info", "complete", f"Extracted {len(reqs)} requirements")
        if errors:
            for e in errors:
                self.log("warning", "warning", e)

        return RequirementAgentResult(
            success=True,
            data={"requirements": reqs, "count": len(reqs)},
            logs=self._logs,
        )

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(
            document_text=input_data.get("document_text", ""),
            project_id=input_data.get("project_id", 0),
        )
        return result.data


class RequirementAgentResult:
    def __init__(self, success: bool, data: dict, logs: list, error: str | None = None):
        self.success = success
        self.data = data
        self.logs = logs
        self.error = error
