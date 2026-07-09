import json

import anyio

from app.agents.automation import repair_agent as mod
from app.agents.automation.repair_agent import MAX_REPAIR_ATTEMPTS, RepairLoopAgent
from app.agents.base.base_agent import AgentRunResult

ORIGINAL_CONTRACT = {
    "contractVersion": "1.0",
    "testCaseId": "TC-0001",
    "scriptType": "playwright-typescript",
    "businessFlow": "Valid login succeeds",
    "pageObjects": [{
        "name": "LoginPage",
        "elements": [{"name": "usernameInput", "locatorStrategy": "css", "locatorValue": "#user"}],
    }],
    "steps": [{"phase": "act", "action": "fill", "target": "LoginPage.usernameInput", "value": "someone"}],
    "assertions": [{"type": "url", "target": "page", "expected": "dashboard"}],
}

FIXED_CONTRACT = {
    **ORIGINAL_CONTRACT,
    "pageObjects": [{
        "name": "LoginPage",
        "elements": [{"name": "usernameInput", "locatorStrategy": "label", "locatorValue": "Username"}],
    }],
}


class _FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    async def achat(self, *, messages):
        self.calls += 1
        return self.response


def _script_data(**overrides):
    data = {
        "script_id": 1,
        "contract": ORIGINAL_CONTRACT,
        "framework": "playwright",
        "application_url": "http://app.example.com",
        "environment": "QA",
        "locator_catalog": [],
        "failure": {
            "classification": "locator_issue",
            "error_message": "Error: waiting for locator('#user') — element not found",
            "stack_trace": "",
        },
    }
    data.update(overrides)
    return data


def test_repair_succeeds_on_first_attempt(monkeypatch):
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: _FakeLLM(json.dumps(FIXED_CONTRACT)))

    async def fake_dry_run(self, scripts):
        return AgentRunResult(success=True, data={"dry_runs": [{
            "script_id": scripts[0]["script_id"], "passed": True, "run_status": "completed",
            "results": [{"name": "t1", "status": "pass"}],
        }]}, logs=[])
    monkeypatch.setattr(mod.DryRunAgent, "run", fake_dry_run)

    agent = RepairLoopAgent()

    async def run():
        return await agent.run(scripts=[_script_data()])

    result = anyio.run(run)

    assert result.success is True
    repair = result.data["repairs"][0]
    assert repair["resolved"] is True
    assert len(repair["attempts"]) == 1
    assert repair["attempts"][0]["static_gate_passed"] is True
    assert repair["attempts"][0]["dry_run_passed"] is True


def test_repair_exhausts_after_max_attempts_when_never_passing(monkeypatch):
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: _FakeLLM(json.dumps(FIXED_CONTRACT)))

    async def fake_dry_run(self, scripts):
        return AgentRunResult(success=True, data={"dry_runs": [{
            "script_id": scripts[0]["script_id"], "passed": False, "run_status": "completed",
            "results": [{
                "name": "t1", "status": "fail",
                "error_message": "Error: waiting for locator - still not found",
            }],
        }]}, logs=[])
    monkeypatch.setattr(mod.DryRunAgent, "run", fake_dry_run)

    agent = RepairLoopAgent()

    async def run():
        return await agent.run(scripts=[_script_data()])

    result = anyio.run(run)

    repair = result.data["repairs"][0]
    assert repair["resolved"] is False
    assert len(repair["attempts"]) == MAX_REPAIR_ATTEMPTS
    assert all(a["outcome"] == "failed" for a in repair["attempts"])


def test_repair_exits_early_when_new_failure_is_not_repairable(monkeypatch):
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: _FakeLLM(json.dumps(FIXED_CONTRACT)))

    async def fake_dry_run(self, scripts):
        return AgentRunResult(success=True, data={"dry_runs": [{
            "script_id": scripts[0]["script_id"], "passed": False, "run_status": "completed",
            "results": [{
                "name": "t1", "status": "fail",
                "error_message": "customer with this email already exists",  # data_issue, not repairable
            }],
        }]}, logs=[])
    monkeypatch.setattr(mod.DryRunAgent, "run", fake_dry_run)

    agent = RepairLoopAgent()

    async def run():
        return await agent.run(scripts=[_script_data()])

    result = anyio.run(run)

    repair = result.data["repairs"][0]
    assert repair["resolved"] is False
    assert len(repair["attempts"]) == 1  # stopped after first attempt, not exhausted all 3
    assert repair["attempts"][0]["outcome"] == "exited_not_repairable"
    assert repair["attempts"][0]["new_classification"] == "data_issue"


def test_repair_stops_when_llm_returns_unparseable_response(monkeypatch):
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: _FakeLLM("not json at all"))

    agent = RepairLoopAgent()

    async def run():
        return await agent.run(scripts=[_script_data()])

    result = anyio.run(run)

    repair = result.data["repairs"][0]
    assert repair["resolved"] is False
    assert repair["attempts"][0]["outcome"] == "llm_patch_failed"


def test_repair_stops_when_patched_contract_is_invalid(monkeypatch):
    invalid_contract = {**ORIGINAL_CONTRACT, "steps": [{"phase": "act", "action": "not_a_real_action"}]}
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: _FakeLLM(json.dumps(invalid_contract)))

    agent = RepairLoopAgent()

    async def run():
        return await agent.run(scripts=[_script_data()])

    result = anyio.run(run)

    repair = result.data["repairs"][0]
    assert repair["resolved"] is False
    assert repair["attempts"][0]["outcome"] == "compile_failed"


def test_repair_loop_fails_cleanly_with_no_scripts():
    agent = RepairLoopAgent()

    async def run():
        return await agent.run(scripts=[])

    result = anyio.run(run)
    assert result.success is False


def test_one_script_crashing_does_not_block_others(monkeypatch):
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: _FakeLLM(json.dumps(FIXED_CONTRACT)))

    async def fake_dry_run(self, scripts):
        return AgentRunResult(success=True, data={"dry_runs": [{
            "script_id": scripts[0]["script_id"], "passed": True, "run_status": "completed",
            "results": [{"name": "t1", "status": "pass"}],
        }]}, logs=[])
    monkeypatch.setattr(mod.DryRunAgent, "run", fake_dry_run)

    agent = RepairLoopAgent()

    broken_script = _script_data(script_id=1)
    del broken_script["failure"]  # causes a KeyError inside _repair_one for this script only

    async def run():
        return await agent.run(scripts=[broken_script, _script_data(script_id=2)])

    result = anyio.run(run)
    assert result.success is True
    # script 1 crashed (KeyError) and is excluded entirely; script 2 still resolved.
    assert len(result.data["repairs"]) == 1
    assert result.data["repairs"][0]["script_id"] == 2
    assert result.data["repairs"][0]["resolved"] is True
    assert any("crashed" in log["message"] for log in result.logs)
