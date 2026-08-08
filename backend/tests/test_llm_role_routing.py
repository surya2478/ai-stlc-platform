import pytest

from app.llm import provider
from app.llm.roles import ROLES, role_default_route, role_for_scope
from app.worker.tasks import agent_tasks


def _legacy_settings(monkeypatch, review="", rag=""):
    monkeypatch.setattr(provider.settings, "ai_gateway_enabled", False)
    monkeypatch.setattr(provider.settings, "default_llm_provider", "ollama")
    monkeypatch.setattr(provider.settings, "default_llm_model", "llama3.1")
    monkeypatch.setattr(provider.settings, "default_vision_model", "llava")
    monkeypatch.setattr(provider.settings, "default_review_model", review)
    monkeypatch.setattr(provider.settings, "default_rag_model", rag)


def test_role_default_route_legacy_matrix(monkeypatch):
    _legacy_settings(monkeypatch)

    assert role_default_route("coding") == ("ollama", "llama3.1")
    assert role_default_route("vision") == ("ollama", "llava")
    assert role_default_route("reasoning") == ("ollama", "llama3.1")
    # Unset review/rag inherit DEFAULT_LLM_MODEL, so a deployment that never
    # sets them behaves exactly as it did before these roles existed.
    assert role_default_route("review") == ("ollama", "llama3.1")
    assert role_default_route("rag") == ("ollama", "llama3.1")


def test_role_default_route_legacy_honors_review_and_rag_models(monkeypatch):
    _legacy_settings(monkeypatch, review="z-ai/glm-5.2", rag="some/rag-model")

    assert role_default_route("review") == ("ollama", "z-ai/glm-5.2")
    assert role_default_route("rag") == ("ollama", "some/rag-model")
    # The other roles must not drift onto the review model.
    assert role_default_route("coding") == ("ollama", "llama3.1")
    assert role_default_route("reasoning") == ("ollama", "llama3.1")


def test_role_default_route_gateway_matrix(monkeypatch):
    monkeypatch.setattr(provider.settings, "ai_gateway_enabled", True)
    monkeypatch.setattr(provider.settings, "llm_coding_model", "qwen3-coder-next")
    monkeypatch.setattr(provider.settings, "llm_vision_model", "qwen3-vl-8b")
    monkeypatch.setattr(provider.settings, "llm_reasoning_model", "gpt-oss-20b")
    monkeypatch.setattr(provider.settings, "llm_review_model", "")
    monkeypatch.setattr(provider.settings, "llm_rag_model", "")

    assert role_default_route("coding") == ("ai_gateway", "qwen3-coder-next")
    assert role_default_route("vision") == ("ai_gateway", "qwen3-vl-8b")
    assert role_default_route("reasoning") == ("ai_gateway", "gpt-oss-20b")
    assert role_default_route("review") == ("ai_gateway", "gpt-oss-20b")
    assert role_default_route("rag") == ("ai_gateway", "gpt-oss-20b")

    monkeypatch.setattr(provider.settings, "llm_review_model", "review-model")
    monkeypatch.setattr(provider.settings, "llm_rag_model", "rag-model")
    assert role_default_route("review") == ("ai_gateway", "review-model")
    assert role_default_route("rag") == ("ai_gateway", "rag-model")


def test_role_for_scope_defaults_to_reasoning():
    assert role_for_scope("automation") == "coding"
    assert role_for_scope("automation_repair_loop") == "coding"
    assert role_for_scope("test_planning") == "coding"
    assert role_for_scope("defect") == "reasoning"
    assert role_for_scope("reporting") == "reasoning"
    assert role_for_scope("some_unknown_scope") == "reasoning"
    assert role_for_scope(None) == "reasoning"


def test_review_scopes_map_to_review_role():
    # automation_script_review moved off "coding" deliberately: it reviews
    # generated scripts, and leaving it on the coding role kept it on the
    # same model that wrote them.
    for scope in ("requirement_review", "scenario_review", "test_case_review", "automation_script_review"):
        assert role_for_scope(scope) == "review", scope


def test_triage_scopes_stay_on_reasoning():
    # Classification/triage, not quality judgement — high-volume and cheap,
    # so they stay on the default route rather than the review model.
    assert role_for_scope("failure_classification") == "reasoning"
    assert role_for_scope("automation_eligibility") == "reasoning"


def test_reviewer_agents_resolve_to_review_role():
    for agent in ("requirement_quality", "scenario_review", "test_case_review", "automation_script_review"):
        assert agent_tasks.agent_role(agent) == "review", agent


def test_generator_agents_stay_off_the_review_role():
    for agent in ("requirement_intake", "test_planning", "test_scenario", "test_case", "automation_script"):
        assert agent_tasks.agent_role(agent) != "review", agent


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
    _legacy_settings(monkeypatch)

    llm = provider.get_llm_for_role(role)

    expected_model = "llava" if role == "vision" else "llama3.1"
    assert llm.model == expected_model


def test_review_role_is_not_swallowed_by_generic_route_override(monkeypatch):
    # The legacy generic override exists for project/agent text routing. It
    # already excludes "vision"; review must NOT be excluded the same way —
    # a project that pins one text model still expects reviews to follow it
    # unless it pins the review role explicitly.
    _legacy_settings(monkeypatch, review="z-ai/glm-5.2")
    route = provider.LLMRouteOverride(provider="ollama", model="pinned-text-model")
    token = provider.set_llm_route_override(route)
    try:
        assert provider.get_llm_for_role("review").model == "pinned-text-model"
    finally:
        provider.reset_llm_route_override(token)

    overrides = {"review": provider.LLMRouteOverride(provider="ollama", model="pinned-review", role="review")}
    token = provider.set_llm_role_route_overrides(overrides)
    try:
        assert provider.get_llm_for_role("review").model == "pinned-review"
    finally:
        provider.reset_llm_role_route_overrides(token)
