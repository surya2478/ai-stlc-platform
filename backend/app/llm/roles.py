"""Role-based LLM routing: maps agent scopes to one of five model roles.

Five roles sit behind either the AI Gateway (one OpenAI-compatible endpoint,
model selected per-request) or legacy per-provider routing:
  - coding:    test case generation, automation script generation/repair
  - vision:    screenshots, OCR, PDFs, UI analysis (never scope-derived —
               only reached via get_llm_for_role("vision"))
  - review:    the gates that judge another agent's output — requirement
               quality, scenario/test-case review, automation script review.
               Split out from "reasoning" so review can run a *different*
               model from the one that produced the artifact; a reviewer
               sharing the generator's model shares its blind spots, and
               these gates feed the autonomy thresholds that decide what
               publishes without a human.
  - rag:       assistant / knowledge-base answer generation. Covers only the
               generation step: retrieval is pure pgvector + keyword hybrid
               with no LLM call, and embeddings have their own provider
               config (EMBEDDING_PROVIDER), since OpenRouter and most chat
               gateways serve no /embeddings endpoint.
  - reasoning: planning, intake, triage, reporting (default)
"""
from typing import Literal

from app.config import get_settings

LLMRole = Literal["coding", "vision", "review", "rag", "reasoning"]
ROLES: tuple[LLMRole, ...] = ("coding", "vision", "review", "rag", "reasoning")

# Agent module_scope -> role. Anything not listed here defaults to "reasoning".
SCOPE_ROLE_MAP: dict[str, LLMRole] = {
    "automation": "coding",
    "automation_repair_loop": "coding",
    "test_planning": "coding",
    # The four gates that judge another agent's output. Note
    # automation_script_review moved here from "coding": it reviews generated
    # Playwright scripts, but reviewing is the job, and leaving it on the
    # coding role would have kept it on the same model that wrote the script.
    "requirement_review": "review",
    "scenario_review": "review",
    "test_case_review": "review",
    "automation_script_review": "review",
    # Deliberately NOT review: these classify/triage rather than judge quality
    # (failure_classification buckets a dry-run failure, automation_eligibility
    # decides whether a test case can be automated at all). Both are
    # high-volume and cheap, so they stay on the default reasoning route.
    "assistant": "rag",
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
            "review": settings.llm_review_model or settings.llm_reasoning_model,
            "rag": settings.llm_rag_model or settings.llm_reasoning_model,
            "reasoning": settings.llm_reasoning_model,
        }[role]
        return "ai_gateway", model

    provider = settings.default_llm_provider
    # Blank falls back to DEFAULT_LLM_MODEL, so a deployment that never sets
    # the new vars behaves exactly as it did before these roles existed.
    model = {
        "vision": settings.default_vision_model,
        "review": settings.default_review_model or settings.default_llm_model,
        "rag": settings.default_rag_model or settings.default_llm_model,
    }.get(role, settings.default_llm_model)
    return provider, model
