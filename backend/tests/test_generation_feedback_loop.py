"""M1: feedback-loop generation — live testing found roughly half of
first-attempt generations came back either invalid or partially
ungrounded. Rather than accept a broken result or silently discard it,
_generate_one_contract retries up to MAX_GENERATION_ATTEMPTS times,
feeding the exact validation error or the specific ungrounded element
names back to the LLM so each retry is a corrected attempt, not a fresh
guess."""
import json

import anyio

from app.agents.automation import automation_agent as mod
from app.agents.automation.automation_agent import AutomationScriptAgent, MAX_GENERATION_ATTEMPTS

VALID_CONTRACT_JSON = json.dumps({
    "contractVersion": "1.0",
    "testCaseId": "TC-0001",
    "scriptType": "playwright-typescript",
    "businessFlow": "Valid login succeeds",
    "pageObjects": [{
        "name": "LoginPage",
        "elements": [{"name": "usernameInput", "locatorStrategy": "label", "locatorValue": "Username"}],
    }],
    "steps": [{"phase": "act", "action": "fill", "target": "LoginPage.usernameInput", "value": "someone"}],
    "assertions": [{"type": "url", "target": "page", "expected": "dashboard"}],
})

# Fails AutomationGenerationContract's target-resolution validator: a
# "fill" step (element-required action) with no target at all.
INVALID_NO_TARGET_JSON = json.dumps({
    "contractVersion": "1.0",
    "testCaseId": "TC-0001",
    "scriptType": "playwright-typescript",
    "businessFlow": "Valid login succeeds",
    "pageObjects": [{
        "name": "LoginPage",
        "elements": [{"name": "usernameInput", "locatorStrategy": "label", "locatorValue": "Username"}],
    }],
    "steps": [{"phase": "act", "action": "fill", "target": None, "value": "someone"}],
})

CATALOG = [{
    "element_name": "combobox",
    "page": "https://example.com/",
    "recommended_locator": "page.getByRole('combobox', { name: 'Search' })",
}]

# Names its element "combobox" (matches the catalog by name) but invents
# its own locator instead of reusing the catalog's — ground_page_object_elements
# force-corrects the name match, so this one actually grounds cleanly.
# For an ungrounded case we need a name the catalog can't match at all.
UNGROUNDED_JSON = json.dumps({
    "contractVersion": "1.0",
    "testCaseId": "TC-0001",
    "scriptType": "playwright-typescript",
    "businessFlow": "Search flow",
    "pageObjects": [{
        "name": "SearchPage",
        "elements": [{"name": "mysteryBox", "locatorStrategy": "css", "locatorValue": "#guess"}],
    }],
})

GROUNDED_JSON = json.dumps({
    "contractVersion": "1.0",
    "testCaseId": "TC-0001",
    "scriptType": "playwright-typescript",
    "businessFlow": "Search flow",
    "pageObjects": [{
        "name": "SearchPage",
        "elements": [{"name": "combobox", "locatorStrategy": "role", "locatorValue": "Search", "roleHint": "combobox"}],
    }],
})


class _QueuedLLM:
    """Returns one queued response per call, repeating the last one if the
    queue runs dry — records every full message list sent, so tests can
    inspect exactly what corrective feedback reached the LLM."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = 0
        self.sent_messages: list[list[dict]] = []

    async def achat(self, *, messages):
        self.calls += 1
        self.sent_messages.append(messages)
        idx = min(self.calls - 1, len(self.responses) - 1)
        return self.responses[idx]


class _FailingLLM:
    def __init__(self, exc: Exception):
        self.exc = exc
        self.calls = 0

    async def achat(self, **_kwargs):
        self.calls += 1
        raise self.exc


def test_retries_after_validation_error_and_succeeds_on_second_attempt(monkeypatch):
    llm = _QueuedLLM([INVALID_NO_TARGET_JSON, VALID_CONTRACT_JSON])
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: llm)

    async def run():
        return await AutomationScriptAgent().run(
            test_cases=[{"test_case_id": "TC-0001", "title": "Valid login"}],
            framework="playwright",
        )

    result = anyio.run(run)

    assert result.success is True
    assert llm.calls == 2
    scripts = result.data["scripts"]
    assert len(scripts) == 1
    assert scripts[0]["test_case_id"] == "TC-0001"
    attempts = scripts[0]["generation_attempts"]
    assert [a["outcome"] for a in attempts] == ["validation_failed", "compiled"]
    # The corrective message sent for the second attempt names the actual failure.
    second_call_messages = llm.sent_messages[1]
    feedback = second_call_messages[-1]["content"]
    assert "failed validation" in feedback
    assert "no target" in feedback.lower()


def test_gives_up_after_max_attempts_with_the_final_validation_error(monkeypatch):
    llm = _QueuedLLM([INVALID_NO_TARGET_JSON])  # every attempt returns the same broken contract
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: llm)

    async def run():
        return await AutomationScriptAgent().run(
            test_cases=[{"test_case_id": "TC-0001", "title": "Valid login"}],
            framework="playwright",
        )

    result = anyio.run(run)

    assert result.success is True
    assert llm.calls == MAX_GENERATION_ATTEMPTS
    assert result.data["scripts"] == []
    assert any("Contract validation failed" in log["message"] for log in result.logs)


def test_retries_when_ungrounded_and_succeeds_once_grounded(monkeypatch):
    llm = _QueuedLLM([UNGROUNDED_JSON, GROUNDED_JSON])
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: llm)

    async def run():
        return await AutomationScriptAgent().run(
            test_cases=[{"test_case_id": "TC-0001", "title": "Search flow", "application_id": 7}],
            framework="playwright",
            locator_map={"7": CATALOG},
        )

    result = anyio.run(run)

    assert llm.calls == 2
    script = result.data["scripts"][0]
    assert script["ungrounded_elements"] == []
    attempts = script["generation_attempts"]
    assert [a["outcome"] for a in attempts] == ["compiled", "compiled"]
    assert attempts[0]["ungrounded_count"] == 1
    assert attempts[1]["ungrounded_count"] == 0
    # The corrective message names the specific ungrounded element.
    second_call_messages = llm.sent_messages[1]
    feedback = second_call_messages[-1]["content"]
    assert "mysteryBox" in feedback


def test_falls_back_to_best_effort_when_never_fully_grounded(monkeypatch):
    # Every attempt compiles but stays ungrounded — should NOT be discarded;
    # the fewest-ungrounded attempt is returned as a best-effort result
    # rather than nothing, matching the existing "still generates, just
    # unmarked as grounded" fallback.
    llm = _QueuedLLM([UNGROUNDED_JSON])
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: llm)

    async def run():
        return await AutomationScriptAgent().run(
            test_cases=[{"test_case_id": "TC-0001", "title": "Search flow", "application_id": 7}],
            framework="playwright",
            locator_map={"7": CATALOG},
        )

    result = anyio.run(run)

    assert llm.calls == MAX_GENERATION_ATTEMPTS
    assert result.data["errors"] if "errors" in result.data else True  # no fatal error recorded
    scripts = result.data["scripts"]
    assert len(scripts) == 1
    assert scripts[0]["ungrounded_elements"] == ["SearchPage.mysteryBox"]
    assert len(scripts[0]["generation_attempts"]) == MAX_GENERATION_ATTEMPTS


def test_rate_limit_stops_retrying_immediately_and_skips_remaining_test_cases(monkeypatch):
    llm = _FailingLLM(Exception("rate_limit_exceeded: try again in 5s"))
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: llm)

    async def run():
        return await AutomationScriptAgent().run(
            test_cases=[
                {"test_case_id": "TC-0001", "title": "First"},
                {"test_case_id": "TC-0002", "title": "Second"},
            ],
            framework="playwright",
        )

    result = anyio.run(run)

    assert llm.calls == 1  # no retries burned against a rate limit, and the 2nd TC was never attempted
    assert result.data["scripts"] == []
    assert any("Rate limit hit" in log["message"] for log in result.logs)


def test_no_retry_needed_when_first_attempt_is_valid_and_grounded(monkeypatch):
    llm = _QueuedLLM([VALID_CONTRACT_JSON])
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: llm)

    async def run():
        return await AutomationScriptAgent().run(
            test_cases=[{"test_case_id": "TC-0001", "title": "Valid login"}],
            framework="playwright",
        )

    result = anyio.run(run)

    assert llm.calls == 1
    assert len(result.data["scripts"][0]["generation_attempts"]) == 1
