"""
Pluggable LLM provider factory.

Switch via environment variable:
  DEFAULT_LLM_PROVIDER=ollama   → uses Ollama local server
  DEFAULT_LLM_PROVIDER=openai   → uses OpenAI-compatible endpoint (OpenAI, Groq, OpenRouter, etc.)

Every agent imports `get_llm()` — provider choice is transparent to agents.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMProvider(Protocol):
    """Minimal protocol all LLM wrappers must satisfy."""

    async def acomplete(self, prompt: str, **kwargs) -> str:
        """Single-turn async completion."""
        ...

    async def achat(self, messages: list[dict], **kwargs) -> str:
        """Multi-turn chat async completion."""
        ...

    async def generate(self, system: str, user: str, **kwargs) -> str:
        """Chat-style generation with separate system and user messages.

        Convenience wrapper used by legacy agents. Delegates to achat().
        """
        ...


def _extract_ollama_options(kwargs: dict) -> tuple[dict, dict]:
    """
    Split kwargs into Ollama-style options dict and remaining top-level kwargs.

    Ollama's /api/generate and /api/chat accept generation params inside an
    'options' sub-object rather than at the top level.  Common OpenAI-style
    params are translated here so agents don't need to know about the
    difference.

    Returns:
        (options_dict, remaining_kwargs)
    """
    OPTION_KEYS = {
        "temperature": "temperature",
        "max_tokens": "num_predict",   # Ollama uses num_predict, not max_tokens
        "top_p": "top_p",
        "top_k": "top_k",
        "repeat_penalty": "repeat_penalty",
        "seed": "seed",
        "stop": "stop",
    }
    options: dict = kwargs.pop("options", {})
    remaining: dict = {}
    for key, value in kwargs.items():
        if key in OPTION_KEYS:
            options[OPTION_KEYS[key]] = value
        else:
            remaining[key] = value
    return options, remaining


class OllamaProvider:
    """Wraps Ollama via httpx — no SDK required."""

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def acomplete(self, prompt: str, **kwargs) -> str:
        import httpx
        options, remaining = _extract_ollama_options(kwargs)
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            **remaining,
        }
        if options:
            payload["options"] = options
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json().get("response", "")

    async def achat(self, messages: list[dict], **kwargs) -> str:
        import httpx
        options, remaining = _extract_ollama_options(kwargs)
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            **remaining,
        }
        if options:
            payload["options"] = options
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    async def generate(self, system: str, user: str, **kwargs) -> str:
        """Chat-style generation with separate system and user messages."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return await self.achat(messages, **kwargs)


class OpenAICompatibleProvider:
    """Wraps any OpenAI-compatible endpoint (OpenAI, Groq, OpenRouter, Ollama OpenAI-mode)."""

    def __init__(self, api_key: str, base_url: str, model: str):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key or "ollama", base_url=base_url)
        self.model = model

    async def acomplete(self, prompt: str, **kwargs) -> str:
        messages = [{"role": "user", "content": prompt}]
        return await self.achat(messages, **kwargs)

    async def achat(self, messages: list[dict], **kwargs) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs,
        )
        return resp.choices[0].message.content or ""

    async def generate(self, system: str, user: str, **kwargs) -> str:
        """Chat-style generation with separate system and user messages."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return await self.achat(messages, **kwargs)


@lru_cache
def get_llm(
    provider: str | None = None,
    model: str | None = None,
) -> LLMProvider:
    """
    Return a cached LLM provider instance.

    Args:
        provider: Override DEFAULT_LLM_PROVIDER env. ("ollama" | "openai")
        model:    Override DEFAULT_LLM_MODEL env.
    """
    resolved_provider = (provider or settings.default_llm_provider).lower()
    resolved_model = model or settings.default_llm_model

    logger.info("LLM provider: %s  model: %s", resolved_provider, resolved_model)

    if resolved_provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=resolved_model,
        )
    elif resolved_provider == "openai":
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY is not set — OpenAI calls will fail")
        return OpenAICompatibleProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model or resolved_model,
        )
    else:
        raise ValueError(f"Unknown LLM provider: '{resolved_provider}'. Valid values: ollama, openai")
