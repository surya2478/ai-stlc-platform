from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings

settings = get_settings()


@dataclass(frozen=True)
class LLMProviderMetadata:
    provider_name: str
    provider_key: str
    description: str
    logo_icon: str
    available_models: tuple[str, ...]
    api_key_required: bool
    supports_local_execution: bool
    supports_fallback_usage: bool
    enabled_for_selection: bool
    default_model: str


# Deliberately narrow. OpenRouter already fronts 400+ models — Llama, Qwen,
# Mistral, Gemini, GPT and the rest — so Groq / Together AI / Cerebras /
# Mistral AI / Google Gemini / Hugging Face / OpenAI were removed as separate
# selectable providers on 2026-08-08 (migration 062 deleted their saved rows).
#
# Their branches in app.llm.provider._build_llm and their config fields are
# INTENTIONALLY kept: they cost nothing without a UI surface, and restoring a
# provider is then a ten-line edit here rather than a re-implementation.
#
# Anything listed here must also resolve in _build_llm — the registry is the
# menu, that function is the kitchen.
PROVIDERS: tuple[LLMProviderMetadata, ...] = (
    LLMProviderMetadata(
        provider_name="Ollama Local",
        provider_key="ollama",
        description="Run local open-source LLMs without any external API dependency. Always available.",
        logo_icon="server",
        available_models=("llama3.2", "llama3.1", "phi4", "qwen2.5-coder:7b", "deepseek-r1:7b", "mistral", "codellama", "gemma2"),
        api_key_required=False,
        supports_local_execution=True,
        supports_fallback_usage=True,
        enabled_for_selection=True,
        default_model="llama3.2",
    ),
    LLMProviderMetadata(
        provider_name="OpenRouter",
        provider_key="openrouter",
        description="Access 100+ hosted LLM providers through one routing layer. Many free models available.",
        logo_icon="route",
        available_models=("configurable",),
        api_key_required=True,
        supports_local_execution=False,
        supports_fallback_usage=True,
        enabled_for_selection=True,
        default_model="configurable",
    ),
    LLMProviderMetadata(
        provider_name="AI Gateway",
        provider_key="ai_gateway",
        description="Single OpenAI-compatible gateway routing to role-specific models (coding, vision, reasoning).",
        logo_icon="route",
        available_models=("configurable",),
        api_key_required=True,
        supports_local_execution=False,
        supports_fallback_usage=True,
        enabled_for_selection=True,
        default_model=settings.llm_reasoning_model,
    ),
)


def list_provider_metadata() -> list[LLMProviderMetadata]:
    return list(PROVIDERS)


def get_provider_metadata(provider_key: str) -> LLMProviderMetadata | None:
    normalized = provider_key.strip().lower()
    return next((provider for provider in PROVIDERS if provider.provider_key == normalized), None)


def provider_api_key(provider_key: str) -> str:
    normalized = provider_key.strip().lower()
    if normalized == "openai":
        return settings.openai_api_key
    if normalized == "groq":
        return settings.groq_api_key
    if normalized == "google_gemini":
        return settings.google_gemini_api_key or settings.gemini_api_key or settings.google_api_key
    if normalized == "openrouter":
        return settings.openrouter_api_key
    if normalized == "huggingface":
        return settings.huggingface_api_key or settings.huggingfacehub_api_token
    if normalized == "together":
        return settings.together_api_key
    if normalized == "cerebras":
        return settings.cerebras_api_key
    if normalized == "mistral":
        return settings.mistral_api_key
    if normalized == "ai_gateway":
        return settings.ai_gateway_api_key
    return ""


def is_provider_key_configured(provider_key: str) -> bool:
    metadata = get_provider_metadata(provider_key)
    if metadata is None:
        return False
    if not metadata.api_key_required:
        return True
    return bool(provider_api_key(provider_key))


def provider_to_response(provider: LLMProviderMetadata) -> dict:
    return {
        "provider_name": provider.provider_name,
        "provider_key": provider.provider_key,
        "description": provider.description,
        "logo_icon": provider.logo_icon,
        "available_models": list(provider.available_models),
        "api_key_required": provider.api_key_required,
        "api_key_configured": is_provider_key_configured(provider.provider_key),
        "supports_local_execution": provider.supports_local_execution,
        "supports_fallback_usage": provider.supports_fallback_usage,
        "enabled_for_selection": provider.enabled_for_selection,
        "default_model": provider.default_model,
    }


def model_is_supported(provider_key: str, model_name: str) -> bool:
    metadata = get_provider_metadata(provider_key)
    if metadata is None:
        return False
    if "configurable" in metadata.available_models:
        return bool(model_name.strip())
    return model_name in metadata.available_models
