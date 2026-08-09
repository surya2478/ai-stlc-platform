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


def test_route_configured_max_tokens_beats_agent_call_site_value():
    # Agents pass their own max_tokens on every call, which used to win over a
    # per-role configured limit because the merge was `{**defaults, **kwargs}`.
    merged = provider._merge_call_options({"max_tokens": 8000, "temperature": 0.7}, {"max_tokens": 3000, "temperature": 0.2})

    assert merged["max_tokens"] == 8000
    # Temperature is not route-authoritative: agents tune it per task.
    assert merged["temperature"] == 0.2


def test_agent_max_tokens_applies_when_route_configures_none():
    merged = provider._merge_call_options({}, {"max_tokens": 6000})

    assert merged["max_tokens"] == 6000


def test_truncated_output_is_not_retriable():
    # Re-issuing the identical request hits the identical cap, so the retry
    # helper must treat truncation as permanent rather than transient.
    exc = provider._truncation_error("qwen3-coder-next", {"max_tokens": 6000})

    assert not provider._is_retriable_llm_error(exc)
    assert "6000-token" in str(exc)


@pytest.mark.anyio
async def test_openai_provider_raises_on_length_finish_reason(monkeypatch):
    pytest.importorskip("openai")
    provider._circuits.clear()
    monkeypatch.setattr(provider.settings, "llm_max_retries", 0)

    llm = provider.OpenAICompatibleProvider(api_key="k", base_url="http://gw/v1", model="m")

    class _Raw:
        headers: dict = {}
        status_code = 200

        def parse(self):
            message = type("_M", (), {"content": '[{"test_case_id": "TC-001", "title": "half a te'})()
            choice = type("_C", (), {"finish_reason": "length", "message": message})()
            return type("_P", (), {"choices": [choice]})()

    async def fake_create(**kwargs):
        return _Raw()

    completions = type("_Completions", (), {"create": staticmethod(fake_create)})()
    raw_response = type("_Raw2", (), {"chat": type("_Chat", (), {"completions": completions})()})()
    monkeypatch.setattr(llm._client, "with_raw_response", raw_response, raising=False)

    with pytest.raises(provider.LLMOutputTruncatedError) as excinfo:
        await llm.achat([{"role": "user", "content": "generate"}], max_tokens=6000)

    assert "truncated" in str(excinfo.value).lower()


@pytest.mark.anyio
async def test_ollama_provider_raises_on_length_done_reason(monkeypatch):
    provider._circuits.clear()
    monkeypatch.setattr(provider.settings, "llm_max_retries", 0)
    llm = provider.OllamaProvider(base_url="http://ollama:11434", model="qwen3")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"done_reason": "length", "message": {"content": '[{"title": "half a te'}}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return _Resp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    with pytest.raises(provider.LLMOutputTruncatedError):
        await llm.achat([{"role": "user", "content": "generate"}], max_tokens=6000)


def test_truncated_json_reports_a_length_problem_not_a_syntax_problem():
    from app.llm.structured import parse_and_validate_llm_list

    truncated = '[{"test_case_id": "TC-001", "title": "Verify sign-up URLs include'

    with pytest.raises(ValueError) as excinfo:
        parse_and_validate_llm_list(truncated, AutomationScriptLLMOutput)

    assert "truncated" in str(excinfo.value)
    assert "max_tokens" in str(excinfo.value)
