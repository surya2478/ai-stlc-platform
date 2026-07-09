"""Phase 4.1: grounded generation — the generator selects locators from the
locator_map (Phase 3 discovery output) rather than guessing, and flags any
element it couldn't ground."""
import json

import anyio

from app.agents.automation import automation_agent as mod
from app.agents.automation.automation_agent import AutomationScriptAgent, _check_grounding
from app.agents.automation.generation_contract import AutomationGenerationContract

CATALOG = [
    {
        "element_name": "textbox_username",
        "role": "role",
        "business_meaning": "enters the username",
        "recommended_locator": "page.getByRole('textbox', { name: 'Username' })",
        "confidence_score": 90,
    },
    {
        "element_name": "button_sign_in",
        "role": "role",
        "business_meaning": "submits the login form",
        "recommended_locator": "page.getByRole('button', { name: 'Sign in' })",
        "confidence_score": 90,
    },
]


def _contract(**overrides):
    data = {
        "testCaseId": "TC-1",
        "scriptType": "playwright-typescript",
        "businessFlow": "login",
        "pageObjects": [{
            "name": "LoginPage",
            "elements": [
                {"name": "textbox_username", "locatorStrategy": "role", "locatorValue": "Username", "roleHint": "textbox"},
                {"name": "button_sign_in", "locatorStrategy": "role", "locatorValue": "Sign in", "roleHint": "button"},
            ],
        }],
    }
    data.update(overrides)
    return AutomationGenerationContract.model_validate(data)


def test_check_grounding_matches_elements_rendered_the_same_way():
    contract = _contract()
    grounded_count, ungrounded = _check_grounding(contract, CATALOG)
    assert grounded_count == 2
    assert ungrounded == []


def test_check_grounding_flags_element_not_in_catalog():
    contract = _contract(pageObjects=[{
        "name": "LoginPage",
        "elements": [
            {"name": "textbox_username", "locatorStrategy": "role", "locatorValue": "Username", "roleHint": "textbox"},
            {"name": "linkForgotPassword", "locatorStrategy": "text", "locatorValue": "Forgot password?"},
        ],
    }])
    grounded_count, ungrounded = _check_grounding(contract, CATALOG)
    assert grounded_count == 1
    assert ungrounded == ["LoginPage.linkForgotPassword"]


def test_check_grounding_returns_zero_for_empty_catalog():
    contract = _contract()
    grounded_count, ungrounded = _check_grounding(contract, None)
    assert grounded_count == 0
    assert ungrounded == []


class _FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.last_system_prompt: str | None = None

    async def achat(self, *, messages):
        self.last_system_prompt = messages[0]["content"]
        return self.response


VALID_CONTRACT_JSON = json.dumps({
    "contractVersion": "1.0",
    "testCaseId": "TC-0001",
    "scriptType": "playwright-typescript",
    "businessFlow": "Valid login succeeds",
    "pageObjects": [{
        "name": "LoginPage",
        "elements": [{"name": "textbox_username", "locatorStrategy": "role", "locatorValue": "Username", "roleHint": "textbox"}],
    }],
    "assertions": [{"type": "url", "target": "page", "expected": "dashboard"}],
})


def test_prompt_includes_locator_catalog_when_available(monkeypatch):
    fake_llm = _FakeLLM(VALID_CONTRACT_JSON)
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: fake_llm)

    async def run():
        return await AutomationScriptAgent().run(
            test_cases=[{"test_case_id": "TC-0001", "title": "Valid login", "application_id": 7}],
            framework="playwright",
            locator_map={"7": CATALOG},
        )

    result = anyio.run(run)

    assert result.success is True
    assert "GROUNDED LOCATORS AVAILABLE" in fake_llm.last_system_prompt
    assert "textbox_username" in fake_llm.last_system_prompt
    script = result.data["scripts"][0]
    assert script["grounded"] is True
    assert script["grounded_element_count"] == 1
    assert script["ungrounded_elements"] == []


def test_prompt_omits_catalog_when_no_discovery_has_run(monkeypatch):
    fake_llm = _FakeLLM(VALID_CONTRACT_JSON)
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: fake_llm)

    async def run():
        return await AutomationScriptAgent().run(
            test_cases=[{"test_case_id": "TC-0001", "title": "Valid login", "application_id": 99}],
            framework="playwright",
            locator_map={"7": CATALOG},  # no entry for application_id=99
        )

    result = anyio.run(run)

    assert "GROUNDED LOCATORS AVAILABLE" not in fake_llm.last_system_prompt
    script = result.data["scripts"][0]
    assert script["grounded"] is False


def test_generation_still_works_without_any_locator_map(monkeypatch):
    """Phase 2 behaviour is preserved when discovery has never run."""
    fake_llm = _FakeLLM(VALID_CONTRACT_JSON)
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: fake_llm)

    async def run():
        return await AutomationScriptAgent().run(
            test_cases=[{"test_case_id": "TC-0001", "title": "Valid login"}],
            framework="playwright",
        )

    result = anyio.run(run)
    assert result.success is True
    assert result.data["scripts"][0]["grounded"] is False
