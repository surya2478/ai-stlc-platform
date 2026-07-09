"""
Requirement Enrichment Agent (GAP-4b)
Runs the Requirement Intake extraction over already-persisted requirements
(typically raw Jira imports) so that structured fields — acceptance criteria,
business rules, systems impacted, telecom domain, etc. — are populated.

It deliberately reuses the RequirementIntakeAgent so the extraction prompt and
validation stay in one place. Persistence happens in the Celery worker
(`requirement_enrichment` handler), which only fills empty fields and never
overwrites user edits or Jira sync data.
"""
import logging

from app.agents.base.base_agent import AgentRunResult, BaseAgent
from app.agents.requirement.intake_agent import RequirementIntakeAgent

logger = logging.getLogger(__name__)


class RequirementEnrichmentAgent(BaseAgent):
    """Enriches existing requirements (e.g. Jira imports) with structured fields."""

    async def run(self, requirements: list[dict], project_id: int = 0) -> AgentRunResult:
        self._logs.clear()
        self.log("info", "start", f"Enriching {len(requirements)} requirements")

        if not requirements:
            return AgentRunResult(
                success=False,
                error="No requirements to enrich",
                data={},
                logs=self._logs,
            )

        intake = RequirementIntakeAgent()
        enriched: list[dict] = []
        errors: list[str] = []

        for req in requirements:
            req_id = req.get("id")
            title = (req.get("title") or "").strip()
            summary = (req.get("summary") or "").strip()
            if not req_id or not (title or summary):
                continue

            text = f"Requirement / User Story: {title}\n\nDescription:\n{summary or '(no description provided)'}"
            try:
                result = await intake.run(document_text=text, project_id=project_id)
                extracted = (result.data or {}).get("requirements") or []
                if not extracted:
                    errors.append(f"Requirement {req_id}: intake extracted nothing")
                    continue
                # A single story may be split into several extracted items —
                # merge list fields, take scalars from the first item.
                merged: dict = dict(extracted[0])
                for extra in extracted[1:]:
                    for key, value in extra.items():
                        if isinstance(value, list) and value:
                            existing = merged.get(key) or []
                            merged[key] = existing + [v for v in value if v not in existing]
                enriched.append({"id": req_id, "fields": merged})
            except Exception as exc:
                errors.append(f"Requirement {req_id}: enrichment error: {exc}")

        self.log("info", "complete", f"Enriched {len(enriched)} of {len(requirements)} requirements")
        for e in errors:
            self.log("warning", "warning", e)

        if not enriched and errors:
            return AgentRunResult(
                success=False,
                error="Enrichment failed for all requirements. " + "; ".join(errors[:3]),
                data={"enriched_requirements": [], "count": 0},
                logs=self._logs,
            )

        return AgentRunResult(
            success=True,
            data={"enriched_requirements": enriched, "count": len(enriched)},
            logs=self._logs,
        )

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(
            requirements=input_data.get("requirements", []),
            project_id=input_data.get("project_id", 0),
        )
        return result.data
