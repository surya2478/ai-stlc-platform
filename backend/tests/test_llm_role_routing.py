import pytest

from app.llm import provider
from app.llm.roles import ROLES, role_default_route, role_for_scope
from app.worker.tasks import agent_tasks


def test_role_default_route_legacy_matrix(monkeypatch):
    monkeypatch.setattr(provider.settings, "ai_gateway_enabled", False)
    monkeypatch.setattr(provider.settings, "default_llm_provider", "ollama")
    monkeypatch.setattr(provider.settings, "default_llm_model", "llama3.1")
    monkeypatch.setattr(provider.settings, "default_vision_model", "llava")

    assert role_default_route("coding") == ("ollama", "llama3.1")
    assert role_default_route("vision") == ("ollama", "llava")
    assert role_default_route("reasoning") == ("ollama", "llama3.1")


def test_role_default_route_gateway_matrix(monkeypatch):
    monkeypatch.setattr(provider.settings, "ai_gateway_enabled", True)
    monkeypatch.setattr(provider.settings, "llm_coding_model", "qwen3-coder-next")
    monkeypatch.setattr(provider.settings, "llm_vision_model", "qwen3-vl-8b")
    monkeypatch.setattr(provider.settings, "llm_reasoning_model", "gpt-oss-20b")

    assert role_default_route("coding") == ("ai_gateway", "qwen3-coder-next")
    assert role_default_route("vision") == ("ai_gateway", "qwen3-vl-8b")
    assert role_default_route("reasoning") == ("ai_gateway", "gpt-oss-20b")


def test_role_for_scope_defaults_to_reasoning():
    assert role_for_scope("automation") == "coding"
    assert role_for_scope("automation_repair_loop") == "coding"
    assert role_for_scope("automation_script_review") == "coding"
    assert role_for_scope("test_planning") == "coding"
    assert role_for_scope("defect") == "reasoning"
    assert role_for_scope("reporting") == "reasoning"
    assert role_for_scope("some_unknown_scope") == "reasoning"
    assert role_for_scope(None) == "reasoning"


def test_agent_role_explicit_pin_wins_over_scope_map():
    # test_planning's own AgentSpec pins llm_role="reasoning" even though its
    # module_scope ("test_planning") maps to "coding" via SCOPE_ROLE_MAP —
    # the pin exists specifically to override that for this one agent.
    assert agent_tasks.agent_role("test_planning") == "reasoning"


def test_agent_role_inherits_from_scope_map():
    # test_case shares module_scope="test_planning" with the planning agent
    # but has no explicit pin, so it correctly inherits "coding".
    assert agent_tasks.agent_role("test_case") == "coding"
    assert agent_tasks.agent_role("automation_script") == "coding"


def test_agent_role_unknown_agent_defaults_to_reasoning():
    assert agent_tasks.agent_role("some_agent_not_in_registry") == "reasoning"


def test_vision_pinning_ignores_generic_route_override():
    route = provider.LLMRouteOverride(provider="groq", model="llama-3.3-70b-versatile")
    token = provider.set_llm_route_override(route)
    try:
        vision_llm = provider.get_vision_llm()
        assert vision_llm.model != route.model
    finally:
        provider.reset_llm_route_override(token)


def test_role_keyed_vision_override_is_honored():
    overrides = {
        "vision": provider.LLMRouteOverride(provider="groq", model="pinned-vision-model", role="vision"),
    }
    token = provider.set_llm_role_route_overrides(overrides)
    try:
        vision_llm = provider.get_vision_llm()
        assert vision_llm.model == "pinned-vision-model"
    finally:
        provider.reset_llm_role_route_overrides(token)


def test_role_context_var_resets_cleanly():
    assert provider._role_route_overrides.get() is None

    overrides = {"coding": provider.LLMRouteOverride(provider="ollama", model="x", role="coding")}
    token = provider.set_llm_role_route_overrides(overrides)
    assert provider._role_route_overrides.get() == overrides

    provider.reset_llm_role_route_overrides(token)
    assert provider._role_route_overrides.get() is None


@pytest.mark.parametrize("role", ROLES)
def test_get_llm_for_role_falls_through_to_system_default(monkeypatch, role):
    monkeypatch.setattr(provider.settings, "ai_gateway_enabled", False)
    monkeypatch.setattr(provider.settings, "default_llm_provider", "ollama")
    monkeypatch.setattr(provider.settings, "default_llm_model", "llama3.1")
    monkeypatch.setattr(provider.settings, "default_vision_model", "llava")

    llm = provider.get_llm_for_role(role)

    expected_model = "llava" if role == "vision" else "llama3.1"
    assert llm.model == expected_model
