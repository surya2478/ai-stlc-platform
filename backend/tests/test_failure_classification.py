import anyio

from app.agents.execution import failure_classification_agent as mod
from app.agents.execution.failure_classification_agent import (
    FailureClassificationAgent,
    classify_by_rules,
)


def test_classifies_timeout():
    result = {"error_message": "TimeoutError: locator.click: Timeout 5000ms exceeded."}
    assert classify_by_rules(result) == "timeout"


def test_classifies_locator_issue():
    result = {"error_message": "Error: locator.click: waiting for locator('button:has-text(\"Submit\")')"}
    assert classify_by_rules(result) == "locator_issue"


def test_classifies_strict_mode_violation_as_locator_issue():
    result = {"error_message": "Error: strict mode violation: locator resolved to 3 elements"}
    assert classify_by_rules(result) == "locator_issue"


def test_classifies_environment_issue_from_connection_error():
    result = {"error_message": "page.goto: net::ERR_CONNECTION_REFUSED at http://app.example.com/"}
    assert classify_by_rules(result) == "environment_issue"


def test_classifies_environment_issue_from_5xx_network_log():
    result = {"error_message": "expected page to show dashboard", "network_logs": [
        {"url": "http://app.example.com/api/session", "status": 503, "method": "GET"},
    ]}
    assert classify_by_rules(result) == "environment_issue"


def test_classifies_data_issue_from_duplicate_message():
    result = {"error_message": "Error: customer with this email already exists"}
    assert classify_by_rules(result) == "data_issue"


def test_classifies_api_issue_from_4xx_network_log():
    result = {"error_message": "order creation failed", "network_logs": [
        {"url": "http://app.example.com/api/orders", "status": 422, "method": "POST"},
    ]}
    assert classify_by_rules(result) == "api_issue"


def test_returns_none_when_rules_are_inconclusive():
    result = {"error_message": "expect(received).toBe(expected) // dashboard title mismatch"}
    assert classify_by_rules(result) is None


def test_agent_uses_rules_for_clear_cases_without_calling_llm(monkeypatch):
    def explode(*_a, **_k):
        raise AssertionError("LLM should not be called when rules are conclusive")
    monkeypatch.setattr(mod, "get_llm", explode)

    agent = FailureClassificationAgent()

    async def run():
        return await agent.run(results=[
            {"result_id": 1, "status": "fail", "error_message": "TimeoutError: Timeout 5000ms exceeded."},
        ])

    result = anyio.run(run)
    assert result.success is True
    classification = result.data["classifications"][0]
    assert classification["classification"] == "timeout"
    assert classification["source"] == "rules"
    assert classification["repairable"] is True


def test_agent_skips_passing_results():
    agent = FailureClassificationAgent()

    async def run():
        return await agent.run(results=[{"result_id": 1, "status": "pass"}])

    result = anyio.run(run)
    assert result.data["classifications"] == []


def test_agent_falls_back_to_llm_when_rules_inconclusive(monkeypatch):
    class _FakeLLM:
        async def achat(self, *, messages):
            return '{"classification": "app_defect", "reason": "dashboard title text was wrong"}'
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: _FakeLLM())

    agent = FailureClassificationAgent()

    async def run():
        return await agent.run(results=[
            {"result_id": 2, "status": "fail", "error_message": "expected 'Dashboard' but got 'Home'"},
        ])

    result = anyio.run(run)
    classification = result.data["classifications"][0]
    assert classification["classification"] == "app_defect"
    assert classification["source"] == "llm"
    assert classification["repairable"] is False


def test_llm_failure_defaults_to_app_defect_not_a_crash(monkeypatch):
    class _BrokenLLM:
        async def achat(self, *, messages):
            raise RuntimeError("provider down")
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: _BrokenLLM())

    agent = FailureClassificationAgent()

    async def run():
        return await agent.run(results=[
            {"result_id": 3, "status": "fail", "error_message": "something ambiguous happened"},
        ])

    result = anyio.run(run)
    assert result.success is True
    assert result.data["classifications"][0]["classification"] == "app_defect"


def test_agent_fails_cleanly_with_no_results():
    agent = FailureClassificationAgent()

    async def run():
        return await agent.run(results=[])

    result = anyio.run(run)
    assert result.success is False
