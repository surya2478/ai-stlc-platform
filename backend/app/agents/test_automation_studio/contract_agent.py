"""Screen 3, Playwright path — emit a contract, never code.

The studio's original script agent asked an LLM to write a `.spec.ts` file
directly. That is the pattern ADR-001 exists to prevent: the model invents
locators, the invention is syntactically perfect, and nothing downstream can
tell a real locator from a plausible one. This agent produces an
`AutomationGenerationContract` instead — a validated JSON structure naming
page objects, elements, steps and assertions — and the deterministic Script
Compiler renders the TypeScript.

Two things become possible only once generation goes through a contract:

  1. `locator_policy.ground_page_object_elements` can overwrite an element's
     locator straight from the discovered catalog. Asking a model to
     transcribe a locator's strategy, value and role hint into three separate
     fields is error-prone in a way that force-substitution simply removes.
  2. `_check_grounding` can count, per element, how much of the script rests
     on real evidence — which is what Screen 3's badge reports.

The prompt itself is imported from the classic automation agent rather than
rewritten. It encodes a long list of failure modes found in live runs (bare
page-object targets, invented URL patterns, `check` used to mean "verify"),
and a studio-local copy would drift away from those fixes the first time one
of them is amended.

Katalon and Appium do not come through here: no compiler backend renders
them, so they keep free-form generation and are grounded only by having the
catalog in the prompt (see `script_agent.py`).
"""
from __future__ import annotations

import json
from typing import Any

from app.agents.automation.automation_agent import (
    CONTRACT_SYSTEM,
    EXPLORED_PAGES_INSTRUCTION,
    GROUNDED_LOCATORS_INSTRUCTION,
    _check_grounding,
    _format_explored_pages,
    _format_locator_catalog,
)
from app.agents.automation.generation_contract import AutomationGenerationContract
from app.agents.base.base_agent import AgentRunResult, BaseAgent
from app.agents.test_automation_studio import call_budget
from app.config import get_settings
from app.llm.provider import get_llm_for_role
from app.llm.structured import parse_and_validate_llm_output
from app.security.prompt_guard import detect_prompt_injection
from app.services.script_compiler import locator_policy
from app.services.script_compiler.compiler import compile_contract

# A contract is denser than a rendered spec but still carries every page
# object, step and assertion; sized above the free-form script budget because
# truncation here discards the whole generation rather than one file.
CONTRACT_MAX_TOKENS = 9000


def _wrap(text: str) -> str:
    return f"<user_content>\n{text}\n</user_content>"


class TasContractAgent(BaseAgent):
    """Produces a compiled Playwright bundle for one refined test case."""

    name = "tas_contract_generation"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.llm = kwargs.get("llm") or get_llm_for_role("coding")

    async def run(
        self,
        *,
        test_case: dict[str, Any],
        catalog: list[dict] | None = None,
        explored_page_paths: list[str] | None = None,
        environment_profile: str = "QA",
        call_timeout: float | None = None,
    ) -> AgentRunResult:
        self._logs.clear()
        display_id = test_case.get("tc_display_id") or test_case.get("id")
        self.log("info", "start", f"Building contract for {display_id}")

        payload = json.dumps(test_case, ensure_ascii=False, default=str)
        if detect_prompt_injection(payload):
            self.log("error", "security_violation", "Prompt injection pattern in test case content")
            return AgentRunResult(
                success=False,
                error="The test case content contains a prompt injection pattern and was rejected.",
                data={},
                logs=self._logs,
            )

        system = CONTRACT_SYSTEM.format(
            script_type="playwright-typescript",
            environment_profile=(environment_profile or "QA").upper(),
        )
        # Only the entries plausibly relevant to THIS test case, capped: a
        # large catalog otherwise crowds the test case out of its own prompt.
        scoped = locator_policy.filter_catalog_by_page(catalog, test_case.get("application_url"))
        scoped = locator_policy.select_relevant_catalog(scoped, payload)
        if scoped:
            system += GROUNDED_LOCATORS_INSTRUCTION.format(
                locator_catalog=_format_locator_catalog(scoped)
            )
        if explored_page_paths:
            system += EXPLORED_PAGES_INSTRUCTION.format(
                explored_pages=_format_explored_pages(explored_page_paths)
            )

        try:
            raw = await call_budget.with_ceiling(
                self.llm.generate(system, _wrap(payload), max_tokens=CONTRACT_MAX_TOKENS),
                call_budget.resolve(call_timeout, get_settings().tas_script_call_timeout_seconds),
                what="this script contract",
                setting="TAS_SCRIPT_CALL_TIMEOUT_SECONDS",
            )
            contract = parse_and_validate_llm_output(raw, AutomationGenerationContract)
        except Exception as exc:
            self.log("error", "contract", f"{display_id}: {exc}")
            return AgentRunResult(success=False, error=str(exc), data={}, logs=self._logs)

        # Force every element the model named after a discovered one back onto
        # the catalog's own locator. This is not a nicety: a model that names
        # the right element and then swaps its role and accessible name
        # produces a locator matching nothing, and does it confidently.
        if scoped:
            locator_policy.ground_page_object_elements(contract, scoped)

        grounded_count, ungrounded = _check_grounding(contract, scoped)
        ungrounded += locator_policy.check_url_targets_grounded(contract, explored_page_paths)

        try:
            bundle = compile_contract(contract)
        except Exception as exc:
            self.log("error", "compile", f"{display_id}: {exc}")
            return AgentRunResult(
                success=False,
                error=f"The contract could not be compiled: {exc}",
                data={},
                logs=self._logs,
            )

        entry_code = bundle.files.get(bundle.entry_path, "")
        extra_files = {path: body for path, body in bundle.files.items() if path != bundle.entry_path}

        setup_notes = list(bundle.setup_required)
        if ungrounded:
            setup_notes.append(
                f"{len(ungrounded)} locator/navigation target(s) are not backed by discovered "
                "evidence and may not match the real page: " + ", ".join(ungrounded[:8])
            )
        if not scoped:
            setup_notes.append(
                "No discovered element catalog was available, so every locator in this script is "
                "the model's best guess. Run Discover Application on the batch and regenerate."
            )

        self.log(
            "info",
            "complete",
            f"{display_id}: {len(bundle.files)} file(s), {grounded_count} grounded element(s)",
        )
        return AgentRunResult(
            success=True,
            data={
                "code": entry_code,
                "files": extra_files,
                "entry_path": bundle.entry_path,
                "execution_command": bundle.execution_command,
                "setup_notes": setup_notes,
                "contract": contract.model_dump(mode="json", by_alias=True),
                "grounding": {
                    "catalog_size": len(scoped or []),
                    "grounded_elements": grounded_count,
                    "ungrounded_elements": ungrounded,
                },
                "framework": "playwright",
            },
            logs=self._logs,
        )

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(
            test_case=input_data.get("test_case", {}),
            catalog=input_data.get("catalog"),
            explored_page_paths=input_data.get("explored_page_paths"),
            environment_profile=input_data.get("environment_profile", "QA"),
        )
        if not result.success:
            raise ValueError(result.error or "Contract generation failed")
        return result.data
