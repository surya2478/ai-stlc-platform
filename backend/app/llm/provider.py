"""
Pluggable LLM provider factory.

Switch via environment variable:
  DEFAULT_LLM_PROVIDER=ollama   → uses Ollama local server
  DEFAULT_LLM_PROVIDER=openai   → uses OpenAI-compatible endpoint (OpenAI, Groq, OpenRouter, etc.)

Every agent imports `get_llm()` — provider choice is transparent to agents.
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Awaitable, Callable, Protocol, TypeVar

from app.config import get_settings
from app.llm.roles import role_default_route

logger = logging.getLogger(__name__)
settings = get_settings()
T = TypeVar("T")


class LLMCircuitOpenError(RuntimeError):
    """Raised when an LLM provider circuit is temporarily open."""


@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float | None = None
    last_error: str | None = None


@dataclass
class _RateLimitSnapshot:
    provider: str
    base_url: str
    model: str
    observed_at: str
    retry_after_seconds: str | None = None
    limit_requests: str | None = None
    remaining_requests: str | None = None
    reset_requests: str | None = None
    limit_tokens: str | None = None
    remaining_tokens: str | None = None
    reset_tokens: str | None = None
    source_status_code: int | None = None


@dataclass(frozen=True)
class LLMRouteOverride:
    provider: str
    model: str
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: int | None = None
    role: str | None = None


_circuits: dict[str, _CircuitState] = {}
_latest_rate_limits: dict[str, _RateLimitSnapshot] = {}
_route_override: ContextVar[LLMRouteOverride | None] = ContextVar("llm_route_override", default=None)
_role_route_overrides: ContextVar[dict[str, LLMRouteOverride] | None] = ContextVar(
    "llm_role_route_overrides", default=None
)


def set_llm_route_override(route: LLMRouteOverride | None) -> Token:
    return _route_override.set(route)


def reset_llm_route_override(token: Token) -> None:
    _route_override.reset(token)


def set_llm_role_route_overrides(overrides: dict[str, LLMRouteOverride] | None) -> Token:
    return _role_route_overrides.set(overrides)


def reset_llm_role_route_overrides(token: Token) -> None:
    _role_route_overrides.reset(token)


def _get_circuit(key: str) -> _CircuitState:
    return _circuits.setdefault(key, _CircuitState())


def _reset_expired_circuit(state: _CircuitState) -> None:
    if state.opened_at is None:
        return
    reset_seconds = max(1, settings.llm_circuit_breaker_reset_seconds)
    if time.monotonic() - state.opened_at >= reset_seconds:
        state.failures = 0
        state.opened_at = None
        state.last_error = None


def _normalize_header_mapping(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    try:
        items = headers.items()
    except Exception:
        return {}
    normalized: dict[str, str] = {}
    for key, value in items:
        normalized[str(key).lower()] = str(value)
    return normalized


def _record_rate_limit_snapshot(
    *,
    provider: str,
    base_url: str,
    model: str,
    headers: Any,
    status_code: int | None = None,
) -> None:
    header_map = _normalize_header_mapping(headers)
    interesting_headers = (
        "retry-after",
        "x-ratelimit-limit-requests",
        "x-ratelimit-remaining-requests",
        "x-ratelimit-reset-requests",
        "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-tokens",
        "x-ratelimit-reset-tokens",
    )
    if not any(header_map.get(name) for name in interesting_headers):
        return

    snapshot = _RateLimitSnapshot(
        provider=provider,
        base_url=base_url,
        model=model,
        observed_at=datetime.now(timezone.utc).isoformat(),
        retry_after_seconds=header_map.get("retry-after"),
        limit_requests=header_map.get("x-ratelimit-limit-requests"),
        remaining_requests=header_map.get("x-ratelimit-remaining-requests"),
        reset_requests=header_map.get("x-ratelimit-reset-requests"),
        limit_tokens=header_map.get("x-ratelimit-limit-tokens"),
        remaining_tokens=header_map.get("x-ratelimit-remaining-tokens"),
        reset_tokens=header_map.get("x-ratelimit-reset-tokens"),
        source_status_code=status_code,
    )
    _latest_rate_limits[f"{provider}:{base_url}:{model}"] = snapshot


def get_latest_rate_limit_snapshot(provider: str, base_url: str, model: str) -> dict[str, Any] | None:
    snapshot = _latest_rate_limits.get(f"{provider}:{base_url}:{model}")
    if snapshot is None:
        return None
    return {
        "provider": snapshot.provider,
        "base_url": snapshot.base_url,
        "model": snapshot.model,
        "observed_at": snapshot.observed_at,
        "retry_after_seconds": snapshot.retry_after_seconds,
        "limit_requests": snapshot.limit_requests,
        "remaining_requests": snapshot.remaining_requests,
        "reset_requests": snapshot.reset_requests,
        "limit_tokens": snapshot.limit_tokens,
        "remaining_tokens": snapshot.remaining_tokens,
        "reset_tokens": snapshot.reset_tokens,
        "source_status_code": snapshot.source_status_code,
    }


def validate_vision_configuration(provider: str | None = None, model: str | None = None) -> str | None:
    """Return a user-facing validation error when UI vision analysis is not runnable."""
    if provider is None and model is None:
        resolved_provider, resolved_model = role_default_route("vision")
        resolved_provider = resolved_provider.lower()
        resolved_model = resolved_model.strip()
    else:
        resolved_provider = (provider or settings.default_llm_provider).lower()
        resolved_model = (model or settings.default_vision_model).strip()

    if not resolved_model:
        return (
            "UI image analysis is not configured because no vision model is set. "
            "Configure DEFAULT_VISION_MODEL to a multimodal model such as llava, qwen2.5vl, gpt-4o-mini, or gemini-2.0-flash."
        )

    if resolved_provider == "ollama":
        return None

    if resolved_provider == "ai_gateway":
        if not (settings.ai_gateway_base_url and settings.ai_gateway_api_key):
            return (
                "UI image analysis is not configured because the AI Gateway is missing a base URL or API key. "
                "Set AI_GATEWAY_BASE_URL and AI_GATEWAY_API_KEY, or set AI_GATEWAY_ENABLED=false to use legacy providers."
            )
        return None

    if resolved_provider == "openai":
        if not settings.openai_api_key:
            return (
                "UI image analysis is not configured because OPENAI_API_KEY is missing. "
                "Add an API key for a vision-capable OpenAI model or switch to Ollama with llava/qwen2.5vl."
            )
        return None

    if resolved_provider == "openrouter":
        if not settings.openrouter_api_key:
            return (
                "UI image analysis is not configured because OPENROUTER_API_KEY is missing. "
                "Add an API key and set DEFAULT_VISION_MODEL to a vision-capable OpenRouter "
                "model such as qwen/qwen2.5-vl-72b-instruct or openai/gpt-4o-mini, "
                "or switch to Ollama with llava/qwen2.5vl."
            )
        return None

    if resolved_provider == "google_gemini":
        if not (settings.google_gemini_api_key or settings.gemini_api_key or settings.google_api_key):
            return (
                "UI image analysis is not configured because no Google Gemini API key is set. "
                "Add GOOGLE_GEMINI_API_KEY or switch to Ollama with llava/qwen2.5vl."
            )
        return None

    if resolved_provider == "huggingface":
        return (
            "UI image analysis is not supported for the Hugging Face provider in this deployment. "
            "Use Ollama with llava/qwen2.5vl, OpenAI with a vision-capable model, or Google Gemini."
        )

    return (
        f"UI image analysis is not enabled for the current provider '{resolved_provider}'. "
        "This deployment currently validates vision analysis only for ollama, openai, openrouter, and google_gemini. "
        "Use a vision-capable model such as llava, qwen2.5vl, gpt-4o-mini, or gemini-2.0-flash."
    )


def _exception_status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _exception_headers(exc: Exception) -> Any:
    response = getattr(exc, "response", None)
    return getattr(response, "headers", None)


def _is_retriable_llm_error(exc: Exception) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError, RuntimeError)):
        return True

    try:
        import httpx
    except Exception:  # pragma: no cover - httpx is installed in runtime
        httpx = None

    if httpx is not None and isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
        ),
    ):
        return True

    # The openai SDK wraps transport failures in its own classes, which are NOT
    # httpx subclasses — so the check above never matched them and every
    # OpenAI-compatible provider (which is all of them here, the AI gateway
    # included) had its connection failures classified as permanent. Observed
    # live: a momentary blip on the local gateway raised APIConnectionError,
    # `_with_retries` logged "non-retriable error" and gave up instantly, and
    # the backoff and circuit breaker never engaged for the one failure mode
    # they exist for.
    try:
        import openai
    except Exception:  # pragma: no cover - openai is installed in runtime
        openai = None

    if openai is not None and isinstance(
        exc,
        (
            openai.APIConnectionError,  # covers APITimeoutError, its subclass
            openai.InternalServerError,
            openai.RateLimitError,
        ),
    ):
        return True

    status_code = _exception_status_code(exc)
    if status_code is not None:
        return status_code == 429 or status_code >= 500

    return False


async def _with_retries(circuit_key: str, operation: Callable[[], Awaitable[T]]) -> T:
    """Run an LLM call with retry/backoff and a simple in-process circuit breaker."""
    state = _get_circuit(circuit_key)
    _reset_expired_circuit(state)
    if state.opened_at is not None:
        detail = f" Last error: {state.last_error}" if state.last_error else ""
        raise LLMCircuitOpenError(f"LLM circuit is open for {circuit_key}.{detail}")

    attempts = max(1, settings.llm_max_retries + 1)
    for attempt in range(attempts):
        try:
            result = await operation()
            state.failures = 0
            state.opened_at = None
            state.last_error = None
            return result
        except Exception as exc:
            if not _is_retriable_llm_error(exc):
                logger.exception("LLM call failed with non-retriable error: %s", circuit_key)
                raise

            state.failures += 1
            state.last_error = f"{type(exc).__name__}: {exc}"
            should_open = state.failures >= max(1, settings.llm_circuit_breaker_failures)
            if should_open:
                state.opened_at = time.monotonic()
                logger.exception("LLM circuit opened for %s", circuit_key)
                raise
            if attempt >= attempts - 1:
                logger.exception("LLM call failed after %s attempt(s): %s", attempts, circuit_key)
                raise
            delay = max(0.0, settings.llm_retry_backoff_seconds) * (2**attempt)
            logger.warning("LLM call failed for %s; retrying in %.2fs", circuit_key, delay)
            if delay:
                await asyncio.sleep(delay)

    raise RuntimeError(f"LLM call failed unexpectedly for {circuit_key}")


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

    async def generate_vision(self, system: str, user: str, images_b64: list[str], **kwargs) -> str:
        """Vision generation: text prompt + one or more base64-encoded images.

        GAP-1: used by the UI screenshot analysis agent. Each provider maps the
        images to its own multimodal message format.
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

    def __init__(self, base_url: str, model: str, default_options: dict[str, Any] | None = None, timeout_seconds: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._circuit_key = f"ollama:{self.base_url}:{self.model}"
        self.default_options = default_options or {}
        self.timeout_seconds = timeout_seconds

    async def acomplete(self, prompt: str, **kwargs) -> str:
        import httpx
        kwargs = {**self.default_options, **kwargs}
        options, remaining = _extract_ollama_options(kwargs)
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            **remaining,
        }
        if options:
            payload["options"] = options

        async def _call() -> str:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(f"{self.base_url}/api/generate", json=payload)
                resp.raise_for_status()
                return resp.json().get("response", "")

        return await _with_retries(self._circuit_key, _call)

    async def achat(self, messages: list[dict], **kwargs) -> str:
        import httpx
        kwargs = {**self.default_options, **kwargs}
        options, remaining = _extract_ollama_options(kwargs)
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            **remaining,
        }
        if options:
            payload["options"] = options

        async def _call() -> str:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                return resp.json()["message"]["content"]

        return await _with_retries(self._circuit_key, _call)

    async def generate(self, system: str, user: str, **kwargs) -> str:
        """Chat-style generation with separate system and user messages."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return await self.achat(messages, **kwargs)

    async def generate_vision(self, system: str, user: str, images_b64: list[str], **kwargs) -> str:
        """Vision generation via Ollama multimodal chat (e.g. llava, qwen2.5vl).

        Ollama accepts raw base64 strings in the message-level "images" field.
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user, "images": images_b64},
        ]
        return await self.achat(messages, **kwargs)


class OpenAICompatibleProvider:
    """Wraps any OpenAI-compatible endpoint (OpenAI, Groq, OpenRouter, Ollama OpenAI-mode)."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        default_options: dict[str, Any] | None = None,
        timeout_seconds: int = 120,
        default_headers: dict[str, str] | None = None,
    ):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(
            api_key=api_key or "ollama",
            base_url=base_url,
            timeout=timeout_seconds,
            default_headers=default_headers or None,
        )
        self.base_url = base_url
        self.model = model
        self._circuit_key = f"openai:{base_url}:{self.model}"
        self.default_options = default_options or {}

    async def acomplete(self, prompt: str, **kwargs) -> str:
        messages = [{"role": "user", "content": prompt}]
        return await self.achat(messages, **kwargs)

    async def achat(self, messages: list[dict], **kwargs) -> str:
        kwargs = {**self.default_options, **kwargs}

        async def _call() -> str:
            try:
                raw_resp = await self._client.with_raw_response.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    **kwargs,
                )
            except Exception as exc:
                _record_rate_limit_snapshot(
                    provider="openai",
                    base_url=self.base_url,
                    model=self.model,
                    headers=_exception_headers(exc),
                    status_code=_exception_status_code(exc),
                )
                raise

            _record_rate_limit_snapshot(
                provider="openai",
                base_url=self.base_url,
                model=self.model,
                headers=getattr(raw_resp, "headers", None),
                status_code=getattr(raw_resp, "status_code", None),
            )
            resp = raw_resp.parse()
            return resp.choices[0].message.content or ""

        return await _with_retries(self._circuit_key, _call)

    async def generate(self, system: str, user: str, **kwargs) -> str:
        """Chat-style generation with separate system and user messages."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return await self.achat(messages, **kwargs)

    async def generate_vision(self, system: str, user: str, images_b64: list[str], **kwargs) -> str:
        """Vision generation via OpenAI-compatible multimodal content parts.

        Images are sent as data-URI image_url parts (vision-capable model required).
        """
        content: list[dict] = [{"type": "text", "text": user}]
        for img in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img}"},
            })
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]
        return await self.achat(messages, **kwargs)


class GoogleGeminiProvider:
    """Minimal Gemini REST wrapper for project-level routing."""

    def __init__(self, api_key: str, model: str, default_options: dict[str, Any] | None = None, timeout_seconds: int = 120):
        self.api_key = api_key
        self.model = model
        self.default_options = default_options or {}
        self.timeout_seconds = timeout_seconds
        self._circuit_key = f"google_gemini:{self.model}"

    @staticmethod
    def _message_to_text(message: dict) -> str:
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "\n".join(parts)
        return str(content)

    async def acomplete(self, prompt: str, **kwargs) -> str:
        return await self.achat([{"role": "user", "content": prompt}], **kwargs)

    async def achat(self, messages: list[dict], **kwargs) -> str:
        import httpx
        opts = {**self.default_options, **kwargs}
        contents = []
        for message in messages:
            role = "model" if message.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": self._message_to_text(message)}]})
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": opts.get("temperature"),
                "maxOutputTokens": opts.get("max_tokens"),
            },
        }
        payload["generationConfig"] = {k: v for k, v in payload["generationConfig"].items() if v is not None}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

        async def _call() -> str:
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    resp = await client.post(url, headers={"x-goog-api-key": self.api_key}, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    candidates = data.get("candidates") or []
                    if not candidates:
                        return ""
                    parts = candidates[0].get("content", {}).get("parts", [])
                    return "\n".join(str(part.get("text", "")) for part in parts)
            except Exception as exc:
                msg = str(exc)
                if self.api_key and self.api_key in msg:
                    msg = msg.replace(self.api_key, "***REDACTED***")
                raise type(exc)(msg) from exc

        return await _with_retries(self._circuit_key, _call)

    async def generate(self, system: str, user: str, **kwargs) -> str:
        return await self.achat(
            [{"role": "user", "content": f"{system}\n\n{user}"}],
            **kwargs,
        )

    async def generate_vision(self, system: str, user: str, images_b64: list[str], **kwargs) -> str:
        import httpx
        opts = {**self.default_options, **kwargs}
        parts: list[dict[str, Any]] = [{"text": f"{system}\n\n{user}"}]
        for image in images_b64:
            parts.append({"inline_data": {"mime_type": "image/png", "data": image}})
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": opts.get("temperature"),
                "maxOutputTokens": opts.get("max_tokens"),
            },
        }
        payload["generationConfig"] = {k: v for k, v in payload["generationConfig"].items() if v is not None}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

        async def _call() -> str:
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    resp = await client.post(url, headers={"x-goog-api-key": self.api_key}, json=payload)
                    resp.raise_for_status()
                    candidates = resp.json().get("candidates") or []
                    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
                    return "\n".join(str(part.get("text", "")) for part in parts)
            except Exception as exc:
                msg = str(exc)
                if self.api_key and self.api_key in msg:
                    msg = msg.replace(self.api_key, "***REDACTED***")
                raise type(exc)(msg) from exc

        return await _with_retries(self._circuit_key, _call)


class HuggingFaceInferenceProvider:
    """Minimal Hugging Face Inference API wrapper for text generation."""

    def __init__(self, api_key: str, model: str, default_options: dict[str, Any] | None = None, timeout_seconds: int = 120):
        self.api_key = api_key
        self.model = model
        self.default_options = default_options or {}
        self.timeout_seconds = timeout_seconds
        self._circuit_key = f"huggingface:{self.model}"

    async def acomplete(self, prompt: str, **kwargs) -> str:
        import httpx
        opts = {**self.default_options, **kwargs}
        parameters = {
            "temperature": opts.get("temperature"),
            "max_new_tokens": opts.get("max_tokens"),
            "return_full_text": False,
        }
        parameters = {k: v for k, v in parameters.items() if v is not None}
        payload = {"inputs": prompt, "parameters": parameters}
        url = f"https://api-inference.huggingface.co/models/{self.model}"

        async def _call() -> str:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(url, headers={"Authorization": f"Bearer {self.api_key}"}, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list) and data:
                    return str(data[0].get("generated_text", ""))
                if isinstance(data, dict):
                    return str(data.get("generated_text", ""))
                return ""

        return await _with_retries(self._circuit_key, _call)

    async def achat(self, messages: list[dict], **kwargs) -> str:
        prompt = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)
        return await self.acomplete(prompt, **kwargs)

    async def generate(self, system: str, user: str, **kwargs) -> str:
        return await self.acomplete(f"{system}\n\n{user}", **kwargs)

    async def generate_vision(self, system: str, user: str, images_b64: list[str], **kwargs) -> str:
        raise NotImplementedError("Hugging Face vision routing is not enabled for this project provider.")


def openrouter_attribution_headers() -> dict[str, str]:
    """Optional HTTP-Referer / X-Title headers for OpenRouter requests.

    OpenRouter uses these to attribute traffic to this deployment on the
    account activity page and its public leaderboards. Unset values are
    omitted rather than sent blank, since an empty HTTP-Referer is worse than
    no header at all.
    """
    headers: dict[str, str] = {}
    site_url = settings.openrouter_site_url.strip()
    app_name = settings.openrouter_app_name.strip()
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name
    return headers


# OpenRouter rejects a "models" array longer than this with a 400:
# "'models' array must have 3 items or fewer." Observed live 2026-08-08 with a
# primary plus three fallbacks. The cap counts the primary, so only two
# fallbacks actually fit.
OPENROUTER_MAX_MODEL_CHAIN = 3


def openrouter_model_chain(primary: str) -> list[str]:
    """Primary model followed by OPENROUTER_FALLBACK_MODELS, de-duplicated.

    Returns [] when no fallbacks are configured, so the request keeps its
    plain single-model shape rather than carrying a one-element array.
    Truncated to OPENROUTER_MAX_MODEL_CHAIN, because over-length arrays fail
    the whole request rather than being trimmed server-side.
    """
    extras = [item.strip() for item in settings.openrouter_fallback_models.split(",") if item.strip()]
    if not extras:
        return []
    chain = [primary.strip()] + extras
    seen: set[str] = set()
    chain = [m for m in chain if m and not (m in seen or seen.add(m))]
    if len(chain) > OPENROUTER_MAX_MODEL_CHAIN:
        logger.warning(
            "OpenRouter model chain has %d entries; only the first %d are sent. Dropped: %s",
            len(chain),
            OPENROUTER_MAX_MODEL_CHAIN,
            ", ".join(chain[OPENROUTER_MAX_MODEL_CHAIN:]),
        )
        chain = chain[:OPENROUTER_MAX_MODEL_CHAIN]
    return chain


def _default_options_from_route(route: LLMRouteOverride | None) -> dict[str, Any]:
    if route is None:
        return {}
    options: dict[str, Any] = {}
    if route.temperature is not None:
        options["temperature"] = route.temperature
    if route.max_tokens is not None:
        options["max_tokens"] = route.max_tokens
    return options


def _build_llm(
    provider: str,
    model: str,
    *,
    default_options: dict[str, Any] | None = None,
    timeout_seconds: int = 120,
) -> LLMProvider:
    logger.info("LLM provider: %s  model: %s", provider, model)

    if provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=model,
            default_options=default_options,
            timeout_seconds=timeout_seconds,
        )
    if provider == "openai":
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY is not set - OpenAI calls will fail")
        return OpenAICompatibleProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model or model,
            default_options=default_options,
            timeout_seconds=timeout_seconds,
        )
    if provider == "groq":
        if not settings.groq_api_key:
            logger.warning("GROQ_API_KEY is not set - Groq calls will fail")
        return OpenAICompatibleProvider(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            model=model or settings.groq_model,
            default_options=default_options,
            timeout_seconds=timeout_seconds,
        )
    if provider == "openrouter":
        if not settings.openrouter_api_key:
            logger.warning("OPENROUTER_API_KEY is not set - OpenRouter calls will fail")
        resolved_model = model or settings.openrouter_model
        options = dict(default_options or {})
        chain = openrouter_model_chain(resolved_model)
        if chain:
            extra_body = dict(options.get("extra_body") or {})
            extra_body["models"] = chain
            options["extra_body"] = extra_body
        return OpenAICompatibleProvider(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=resolved_model,
            default_options=options,
            timeout_seconds=timeout_seconds,
            default_headers=openrouter_attribution_headers(),
        )
    if provider == "google_gemini":
        api_key = settings.google_gemini_api_key or settings.gemini_api_key or settings.google_api_key
        if not api_key:
            logger.warning("GOOGLE_GEMINI_API_KEY is not set - Gemini calls will fail")
        return GoogleGeminiProvider(
            api_key=api_key,
            model=model or settings.google_gemini_model,
            default_options=default_options,
            timeout_seconds=timeout_seconds,
        )
    if provider == "huggingface":
        api_key = settings.huggingface_api_key or settings.huggingfacehub_api_token
        if not api_key:
            logger.warning("HUGGINGFACE_API_KEY is not set - Hugging Face calls will fail")
        return HuggingFaceInferenceProvider(
            api_key=api_key,
            model=model or settings.huggingface_model,
            default_options=default_options,
            timeout_seconds=timeout_seconds,
        )
    if provider == "together":
        if not settings.together_api_key:
            logger.warning("TOGETHER_API_KEY is not set - Together AI calls will fail")
        return OpenAICompatibleProvider(
            api_key=settings.together_api_key,
            base_url=settings.together_base_url,
            model=model or settings.together_model,
            default_options=default_options,
            timeout_seconds=timeout_seconds,
        )
    if provider == "cerebras":
        if not settings.cerebras_api_key:
            logger.warning("CEREBRAS_API_KEY is not set - Cerebras calls will fail")
        return OpenAICompatibleProvider(
            api_key=settings.cerebras_api_key,
            base_url=settings.cerebras_base_url,
            model=model or settings.cerebras_model,
            default_options=default_options,
            timeout_seconds=timeout_seconds,
        )
    if provider == "mistral":
        if not settings.mistral_api_key:
            logger.warning("MISTRAL_API_KEY is not set - Mistral AI calls will fail")
        return OpenAICompatibleProvider(
            api_key=settings.mistral_api_key,
            base_url=settings.mistral_base_url,
            model=model or settings.mistral_model,
            default_options=default_options,
            timeout_seconds=timeout_seconds,
        )
    if provider == "ai_gateway":
        if not settings.ai_gateway_api_key:
            logger.warning("AI_GATEWAY_API_KEY is not set - AI Gateway calls will fail")
        # Caller's model always wins — unlike the openai branch above, the
        # gateway routes purely on the model field of each request.
        return OpenAICompatibleProvider(
            api_key=settings.ai_gateway_api_key,
            base_url=settings.ai_gateway_base_url,
            model=model,
            default_options=default_options,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError("Unknown LLM provider: '%s'. Valid values: ollama, openai, groq, google_gemini, openrouter, huggingface, together, cerebras, mistral, ai_gateway" % provider)


@lru_cache
def _get_cached_llm(provider: str, model: str) -> LLMProvider:
    return _build_llm(provider, model)


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
    route = _route_override.get()
    if route is not None and (
        provider is None
        or provider == settings.default_llm_provider
        or provider == route.provider
    ):
        return _build_llm(
            route.provider.lower(),
            route.model,
            default_options=_default_options_from_route(route),
            timeout_seconds=route.timeout_seconds or 120,
        )

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
    elif resolved_provider in ("together", "cerebras", "mistral"):
        return _build_llm(resolved_provider, resolved_model)
    else:
        return _get_cached_llm(resolved_provider, resolved_model)


def get_llm_for_role(role: str) -> LLMProvider:
    """Resolve an LLM provider for a role (see app.llm.roles.ROLES:
    "coding" | "vision" | "review" | "rag" | "reasoning").

    Precedence:
      1. Role-keyed override (worker pins one route per role for a run).
      2. Legacy generic route override — non-vision roles only, so a plain
         project/agent override never silently swallows the vision route.
      3. The role's system default (AI Gateway model, or legacy
         DEFAULT_LLM_MODEL / DEFAULT_VISION_MODEL when the gateway is off).

    Not cached: overrides are ContextVar-scoped per request/task, so caching
    across calls would leak one caller's route into another's context.
    """
    role_overrides = _role_route_overrides.get()
    if role_overrides and role in role_overrides:
        route = role_overrides[role]
        return _build_llm(
            route.provider.lower(),
            route.model,
            default_options=_default_options_from_route(route),
            timeout_seconds=route.timeout_seconds or 120,
        )

    if role != "vision":
        route = _route_override.get()
        if route is not None:
            return _build_llm(
                route.provider.lower(),
                route.model,
                default_options=_default_options_from_route(route),
                timeout_seconds=route.timeout_seconds or 120,
            )

    provider, model = role_default_route(role)
    logger.info("LLM role: %s  provider: %s  model: %s", role, provider, model)
    return _get_cached_llm(provider, model)


def get_vision_llm(provider: str | None = None, model: str | None = None) -> LLMProvider:
    """Return an LLM provider configured with a vision-capable model (GAP-1).

    Called with no arguments (the normal case), this delegates to
    get_llm_for_role("vision") so vision correctly resolves the vision role
    default/override instead of collapsing onto a generic text override.
    Explicit provider/model args (used by tests and any caller pinning a
    specific vision model) keep the original direct-build behavior.
    """
    if provider is None and model is None:
        return get_llm_for_role("vision")

    route = _route_override.get()
    if route is not None and (
        provider is None
        or provider == settings.default_llm_provider
        or provider == route.provider
    ):
        return _build_llm(
            route.provider.lower(),
            route.model,
            default_options=_default_options_from_route(route),
            timeout_seconds=route.timeout_seconds or 120,
        )

    resolved_provider = (provider or settings.default_llm_provider).lower()
    resolved_model = model or settings.default_vision_model
    logger.info("Vision LLM provider: %s  model: %s", resolved_provider, resolved_model)

    if resolved_provider == "ollama":
        return OllamaProvider(base_url=settings.ollama_base_url, model=resolved_model)
    if resolved_provider == "openai":
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY is not set — OpenAI vision calls will fail")
        return OpenAICompatibleProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=resolved_model,
        )
    return _get_cached_llm(resolved_provider, resolved_model)
