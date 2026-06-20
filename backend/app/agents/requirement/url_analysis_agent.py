"""
Portal URL Analysis Agent (GAP-2)
Renders portal pages with Playwright, then combines:
  1. A deterministic DOM inventory (forms, fields, validation attributes,
     buttons, links) — cheap and exact, no LLM needed.
  2. A best-effort vision pass over the page screenshot for flows, validation
     behaviour, negative scenarios, and edge cases (falls back to a text-only
     pass over the DOM summary if the vision model is unavailable).
  3. The same requirement-derivation step as the UI analysis agent, so the
     output feeds the existing quality/scenario/test-case pipeline unchanged.

Screenshots are written to file storage; the worker persistence handler turns
them into UploadedDocument records and links requirements to them.
"""
import base64
import json
import uuid
from pathlib import Path

from app.agents.base.base_agent import BaseAgent
from app.agents.requirement.ui_analysis_agent import (
    DERIVE_SYSTEM,
    VISION_SYSTEM,
    _parse_json_block,
)
from app.agents.structured_schemas import RequirementLLMOutput
from app.llm.provider import get_llm, get_vision_llm
from app.llm.structured import validate_structured_output
from app.config import get_settings
from app.services.url_capture_service import capture_pages

settings = get_settings()

DOM_FALLBACK_SYSTEM = """You are a senior QA engineer. You receive a DOM inventory of a web page
(title, headings, forms, fields with validation attributes, buttons, links).

Produce a JSON object with these keys:
- screen_name: short name for the page
- screen_purpose: 1-2 sentences on what the page does
- user_flows: list of user journeys the page supports
- validation_rules: list of validation behaviours implied by field attributes (required, pattern, min/max length, types)
- negative_scenarios: list of negative/error cases to test
- edge_cases: list of edge cases (boundary lengths, special characters, navigation interruptions)
- accessibility_notes: list of likely accessibility considerations

Output ONLY a valid JSON object. No extra text."""


class URLAnalysisAgent(BaseAgent):
    """Generates structured requirements from a live portal URL (GAP-2)."""

    async def run(
        self,
        url: str,
        crawl_depth: int = 0,
        context_note: str = "",
        project_id: int = 0,
    ) -> "URLAnalysisAgentResult":
        self._logs.clear()
        self.log("info", "start", f"Analysing portal URL {url} (depth {crawl_depth}) for project {project_id}")

        if not url or not url.strip():
            return URLAnalysisAgentResult(success=False, error="No URL provided", data={}, logs=self._logs)

        # 1. Capture pages (Playwright render + DOM summary + screenshot)
        try:
            pages = await capture_pages(url, crawl_depth=crawl_depth)
        except Exception as exc:
            return URLAnalysisAgentResult(
                success=False,
                error=f"Page capture failed: {exc}",
                data={},
                logs=self._logs,
            )
        self.log("info", "capture", f"Captured {len(pages)} page(s)")

        screenshot_dir = Path(settings.file_storage_path) / "uploads" / str(project_id)
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        llm = get_llm(settings.default_llm_provider, settings.default_llm_model)
        page_results: list[dict] = []
        errors: list[str] = []

        for page in pages:
            # 2. Persist the screenshot to file storage (DB record is created
            #    later by the worker persistence handler).
            stored_name = f"{uuid.uuid4().hex}_url_capture.png"
            screenshot_path = screenshot_dir / stored_name
            screenshot_path.write_bytes(page.screenshot_png)

            # 3. Behavioural analysis: vision pass first, DOM-text fallback.
            analysis = await self._analyze_page(llm, page, context_note, errors)

            # Merge the deterministic DOM inventory (exact) over LLM guesses.
            analysis["fields"] = page.dom_summary.get("fields", [])
            analysis["buttons"] = page.dom_summary.get("buttons", [])
            analysis["links"] = [l.get("label") or l.get("href") for l in page.dom_summary.get("links", [])][:30]
            analysis.setdefault("screen_name", page.title)

            # 4. Derive structured requirements.
            requirements = await self._derive_requirements(llm, page, analysis, errors)

            page_results.append({
                "url": page.url,
                "title": page.title,
                "screenshot_path": str(screenshot_path),
                "screenshot_name": stored_name,
                "screenshot_size": len(page.screenshot_png),
                "ui_analysis": analysis,
                "requirements": requirements,
            })
            self.log(
                "info", "page",
                f"{page.url}: {len(page.dom_summary.get('fields', []))} fields, "
                f"{len(requirements)} requirements derived",
            )

        for e in errors:
            self.log("warning", "warning", e)

        total_reqs = sum(len(p["requirements"]) for p in page_results)
        if total_reqs == 0:
            return URLAnalysisAgentResult(
                success=False,
                error="URL analysis produced no requirements. " + "; ".join(errors[:3]),
                data={"pages": page_results, "count": 0},
                logs=self._logs,
            )

        self.log("info", "complete", f"Derived {total_reqs} requirements from {len(page_results)} page(s)")
        return URLAnalysisAgentResult(
            success=True,
            data={"pages": page_results, "count": total_reqs, "source_url": url},
            logs=self._logs,
        )

    async def _analyze_page(self, llm, page, context_note: str, errors: list[str]) -> dict:
        """Vision pass with DOM-text fallback. Always returns a dict."""
        user_prompt = (
            f"Analyse this web page screenshot (page title: '{page.title}', URL: {page.url}) "
            "and return the JSON object."
        )
        if context_note:
            user_prompt += f"\n\nAdditional context from the tester: {context_note}"

        # Vision pass (best-effort)
        try:
            vision_llm = get_vision_llm()
            image_b64 = base64.b64encode(page.screenshot_png).decode("ascii")
            response = await vision_llm.generate_vision(
                system=VISION_SYSTEM,
                user=user_prompt,
                images_b64=[image_b64],
                temperature=0.1,
                max_tokens=4000,
            )
            parsed = _parse_json_block(response)
            if isinstance(parsed, dict):
                return parsed
            errors.append(f"{page.url}: vision pass returned no valid JSON — using DOM fallback")
        except Exception as exc:
            errors.append(f"{page.url}: vision pass failed ({exc}) — using DOM fallback")

        # DOM-text fallback
        try:
            response = await llm.generate(
                system=DOM_FALLBACK_SYSTEM,
                user=(
                    f"DOM inventory of page '{page.title}' ({page.url}):\n\n"
                    f"{json.dumps(page.dom_summary, indent=2)}\n\nReturn the JSON object."
                ),
                temperature=0.1,
                max_tokens=3000,
            )
            parsed = _parse_json_block(response)
            if isinstance(parsed, dict):
                return parsed
            errors.append(f"{page.url}: DOM fallback returned no valid JSON")
        except Exception as exc:
            errors.append(f"{page.url}: DOM fallback failed: {exc}")
        return {}

    async def _derive_requirements(self, llm, page, analysis: dict, errors: list[str]) -> list[dict]:
        """Convert the merged analysis into validated requirement dicts."""
        if not analysis:
            return []
        prompt = (
            f"UI analysis for live page '{page.title}' (URL: {page.url}):\n\n"
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
                    errors.append(f"{page.url}: requirement schema validation failed: {exc}")
        except Exception as exc:
            errors.append(f"{page.url}: requirement derivation error: {exc}")
        return requirements

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(
            url=input_data.get("url", ""),
            crawl_depth=input_data.get("crawl_depth", 0),
            context_note=input_data.get("context_note", ""),
            project_id=input_data.get("project_id", 0),
        )
        return result.data


class URLAnalysisAgentResult:
    def __init__(self, success: bool, data: dict, logs: list, error: str | None = None):
        self.success = success
        self.data = data
        self.logs = logs
        self.error = error
