import pytest

from app.agents.structured_schemas import AutomationScriptLLMOutput
from app.llm import provider
from app.llm.structured import validate_structured_list, validate_structured_output


@pytest.mark.anyio
async def test_llm_retry_helper_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(provider.settings, "llm_max_retries", 2)
    monkeypatch.setattr(provider.settings, "llm_retry_backoff_seconds", 0)
    monkeypatch.setattr(provider.settings, "llm_circuit_breaker_failures", 10)
    provider._circuits.clear()
    calls = 0

    async def flaky_call():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary outage")
        return "ok"

    result = await provider._with_retries("test-provider", flaky_call)

    assert result == "ok"
    assert calls == 2


@pytest.mark.anyio
async def test_llm_retry_helper_does_not_open_circuit_for_non_retriable_errors(monkeypatch):
    monkeypatch.setattr(provider.settings, "llm_max_retries", 2)
    monkeypatch.setattr(provider.settings, "llm_retry_backoff_seconds", 0)
    monkeypatch.setattr(provider.settings, "llm_circuit_breaker_failures", 1)
    provider._circuits.clear()
    calls = 0

    class BadRequestError(Exception):
        status_code = 400

    async def bad_request():
        nonlocal calls
        calls += 1
        raise BadRequestError("unsupported request")

    with pytest.raises(BadRequestError):
        await provider._with_retries("test-provider", bad_request)

    assert calls == 1
    state = provider._circuits["test-provider"]
    assert state.failures == 0
    assert state.opened_at is None


@pytest.mark.anyio
async def test_llm_retry_helper_circuit_error_preserves_last_failure(monkeypatch):
    monkeypatch.setattr(provider.settings, "llm_max_retries", 0)
    monkeypatch.setattr(provider.settings, "llm_retry_backoff_seconds", 0)
    monkeypatch.setattr(provider.settings, "llm_circuit_breaker_failures", 1)
    provider._circuits.clear()

    class RateLimitError(Exception):
        status_code = 429

    async def rate_limited():
        raise RateLimitError("quota exceeded")

    with pytest.raises(RateLimitError):
        await provider._with_retries("test-provider", rate_limited)

    with pytest.raises(provider.LLMCircuitOpenError, match="quota exceeded"):
        await provider._with_retries("test-provider", rate_limited)


def test_structured_output_validation_normalizes_lists():
    parsed = validate_structured_output(
        {
            "test_case_id": "TC-1",
            "framework": "pytest",
            "file_path": "tests/test_sample.py",
            "code": "def test_sample(): pass",
            "setup_required": "pytest",
            "execution_command": "pytest",
            "unexpected": "ignored",
        },
        AutomationScriptLLMOutput,
    )

    assert parsed.setup_required == ["pytest"]


def test_structured_list_validation_returns_json_safe_dicts():
    parsed = validate_structured_list(
        [{"test_case_id": "TC-1", "framework": "pytest", "setup_required": ["pytest"]}],
        AutomationScriptLLMOutput,
    )

    assert parsed[0]["test_case_id"] == "TC-1"


def test_build_llm_ai_gateway_returns_openai_compatible_provider(monkeypatch):
    monkeypatch.setattr(provider.settings, "ai_gateway_base_url", "http://ai-gateway:4000/v1")
    monkeypatch.setattr(provider.settings, "ai_gateway_api_key", "gw-secret")

    llm = provider._build_llm("ai_gateway", "qwen3-coder-next")

    assert isinstance(llm, provider.OpenAICompatibleProvider)
    assert llm.base_url == "http://ai-gateway:4000/v1"
    assert llm.model == "qwen3-coder-next"


def test_build_llm_ai_gateway_does_not_pin_model_like_openai_branch(monkeypatch):
    # Unlike the "openai" branch (which pins settings.openai_model), the
    # gateway must always honor the caller's model — that's the whole point
    # of a single endpoint routing by model name.
    monkeypatch.setattr(provider.settings, "ai_gateway_base_url", "http://ai-gateway:4000/v1")
    monkeypatch.setattr(provider.settings, "ai_gateway_api_key", "gw-secret")

    coding = provider._build_llm("ai_gateway", "qwen3-coder-next")
    vision = provider._build_llm("ai_gateway", "qwen3-vl-8b")

    assert coding.model == "qwen3-coder-next"
    assert vision.model == "qwen3-vl-8b"
