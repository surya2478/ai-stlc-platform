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


PROVIDERS: tuple[LLMProviderMetadata, ...] = (
    LLMProviderMetadata(
        provider_name="Groq",
        provider_key="groq",
        description="Fast free inference for open-source LLMs via Groq's custom LPU hardware.",
        logo_icon="zap",
        available_models=(
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
            "deepseek-r1-distill-llama-70b",
            "gemma2-9b-it",
            "compound-beta",
        ),
        api_key_required=True,
        supports_local_execution=False,
        supports_fallback_usage=True,
        enabled_for_selection=True,
        default_model="llama-3.3-70b-versatile",
    ),
    LLMProviderMetadata(
        provider_name="Together AI",
        provider_key="together",
        description="Free-tier open-source LLMs (LLaMA 3.3 70B, Qwen, Mixtral). OpenAI-compatible. $25 free credit.",
        logo_icon="zap",
        available_models=(
            "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
            "meta-llama/Llama-3.1-8B-Instruct-Turbo",
            "mistralai/Mixtral-8x7B-Instruct-v0.1",
            "Qwen/Qwen2.5-72B-Instruct-Turbo",
        ),
        api_key_required=True,
        supports_local_execution=False,
        supports_fallback_usage=True,
        enabled_for_selection=True,
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
    ),
    LLMProviderMetadata(
        provider_name="Cerebras",
        provider_key="cerebras",
        description="Ultra-fast LLaMA inference at 2000+ tokens/sec. Free tier available. OpenAI-compatible API.",
        logo_icon="zap",
        available_models=(
            "gpt-oss-120b",
            "llama-3.3-70b",
            "llama-3.1-70b",
            "llama-3.1-8b",
        ),
        api_key_required=True,
        supports_local_execution=False,
        supports_fallback_usage=True,
        enabled_for_selection=True,
        default_model="gpt-oss-120b",
    ),
    LLMProviderMetadata(
        provider_name="Mistral AI",
        provider_key="mistral",
        description="Codestral (free for code tasks), Mistral Large. European-hosted — GDPR-friendly.",
        logo_icon="braces",
        available_models=(
            "codestral-latest",
            "mistral-large-latest",
            "open-mistral-nemo",
            "mistral-small-latest",
        ),
        api_key_required=True,
        supports_local_execution=False,
        supports_fallback_usage=True,
        enabled_for_selection=True,
        default_model="codestral-latest",
    ),
    LLMProviderMetadata(
        provider_name="Google Gemini",
        provider_key="google_gemini",
        description="Google’s multimodal AI models for reasoning and generation.",
        logo_icon="sparkles",
        available_models=("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"),
        api_key_required=True,
        supports_local_execution=False,
        supports_fallback_usage=True,
        enabled_for_selection=True,
        default_model="gemini-2.0-flash",
    ),
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
        provider_name="Hugging Face Inference",
        provider_key="huggingface",
        description="Hosted open-source models from Hugging Face Inference API. Large model catalogue.",
        logo_icon="braces",
        available_models=("configurable",),
        api_key_required=True,
        supports_local_execution=False,
        supports_fallback_usage=True,
        enabled_for_selection=True,
        default_model="configurable",
    ),
    LLMProviderMetadata(
        provider_name="OpenAI",
        provider_key="openai",
        description="Hosted OpenAI-compatible models for advanced reasoning and generation.",
        logo_icon="bot",
        available_models=("gpt-4o", "gpt-4o-mini", "o3-mini", "o1-mini"),
        api_key_required=True,
        supports_local_execution=False,
        supports_fallback_usage=True,
        enabled_for_selection=True,
        default_model="gpt-4o-mini",
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
