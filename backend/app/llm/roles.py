"""Role-based LLM routing: maps agent scopes to one of three model roles.

Three roles sit behind either the AI Gateway (one OpenAI-compatible endpoint,
model selected per-request) or legacy per-provider routing:
  - coding:    test case generation, automation script generation/repair
  - vision:    screenshots, OCR, PDFs, UI analysis (never scope-derived —
               only reached via get_llm_for_role("vision"))
  - reasoning: planning, agents, review, chat, triage, reporting (default)
"""
from typing import Literal

from app.config import get_settings

LLMRole = Literal["coding", "vision", "reasoning"]
ROLES: tuple[LLMRole, ...] = ("coding", "vision", "reasoning")

# Agent module_scope -> role. Anything not listed here defaults to "reasoning".
SCOPE_ROLE_MAP: dict[str, LLMRole] = {
    "automation": "coding",
    "automation_repair_loop": "coding",
    "automation_script_review": "coding",
    "test_planning": "coding",
}


def role_for_scope(scope: str | None) -> LLMRole:
    if scope is None:
        return "reasoning"
    return SCOPE_ROLE_MAP.get(scope, "reasoning")


def role_default_route(role: LLMRole) -> tuple[str, str]:
    """Return (provider, model) for a role's system-default route."""
    settings = get_settings()
    if settings.ai_gateway_enabled:
        model = {
            "coding": settings.llm_coding_model,
            "vision": settings.llm_vision_model,
            "reasoning": settings.llm_reasoning_model,
        }[role]
        return "ai_gateway", model

    provider = settings.default_llm_provider
    model = settings.default_vision_model if role == "vision" else settings.default_llm_model
    return provider, model
