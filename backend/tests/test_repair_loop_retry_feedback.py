"""RepairLoopAgent's _repair_one used to break immediately on a
parse/validation failure from _propose_patch, wasting the remaining
MAX_REPAIR_ATTEMPTS budget on nothing. Confirmed live: the LLM sometimes
echoes back the whole _propose_patch payload wrapper (original_contract/
failure_evidence/fresh_locator_catalog) instead of just the corrected
contract, producing a "testCaseId Field required" validation error on the
very first attempt — for a real TC-0110 repair, this used to give up after
exactly one wasted LLM call. Now a parse/validation failure feeds the exact
error back and retries, mirroring automation_agent's generation feedback
loop."""
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

# What the LLM actually returned in the live run: the whole payload
# wrapper echoed back instead of just the contract.
WRAPPER_ECHO = {
    "original_contract": ORIGINAL_CONTRACT,
    "failure_evidence": {"classification": "timeout", "error_message": "Test timeout of 30000ms exceeded."},
    "fresh_locator_catalog": [],
}

FIXED_CONTRACT = {
    **ORIGINAL_CONTRACT,
    "pageObjects": [{
        "name": "LoginPage",
        "elements": [{"name": "usernameInput", "locatorStrategy": "label", "locatorValue": "Username"}],
    }],
}


def _script_data(**overrides):
    data = {
        "script_id": 1,
        "contract": ORIGINAL_CONTRACT,
        "framework": "playwright",
        "application_url": "http://app.example.com",
        "environment": "QA",
        "locator_catalog": [],
        "failure": {
            "classification": "timeout",
            "error_message": "Test timeout of 30000ms exceeded.",
            "stack_trace": "",
        },
    }
    data.update(overrides)
    return data


class _QueuedLLM:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = 0
        self.sent_prompts: list[str] = []

    async def achat(self, *, messages):
        self.calls += 1
        self.sent_prompts.append(messages[-1]["content"])
        idx = min(self.calls - 1, len(self.responses) - 1)
        return self.responses[idx]


def test_retries_after_wrapper_echo_and_succeeds_on_second_attempt(monkeypatch):
    llm = _QueuedLLM([json.dumps(WRAPPER_ECHO), json.dumps(FIXED_CONTRACT)])
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: llm)

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

    assert llm.calls == 2
    repair = result.data["repairs"][0]
    assert repair["resolved"] is True
    assert [a["outcome"] for a in repair["attempts"]] == ["compile_failed", "passed"]
    # The corrective prompt on the second call names the actual failure.
    assert "previous_attempt_error" in llm.sent_prompts[1]
    assert "testCaseId" in llm.sent_prompts[1]


def test_gives_up_after_max_attempts_of_the_same_wrapper_echo(monkeypatch):
    llm = _QueuedLLM([json.dumps(WRAPPER_ECHO)])  # every attempt returns the same broken echo
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: llm)

    agent = RepairLoopAgent()

    async def run():
        return await agent.run(scripts=[_script_data()])

    result = anyio.run(run)

    assert llm.calls == MAX_REPAIR_ATTEMPTS
    repair = result.data["repairs"][0]
    assert repair["resolved"] is False
    assert len(repair["attempts"]) == MAX_REPAIR_ATTEMPTS
    assert all(a["outcome"] == "compile_failed" for a in repair["attempts"])


def test_unparseable_response_also_retries_with_feedback(monkeypatch):
    llm = _QueuedLLM(["not json at all", json.dumps(FIXED_CONTRACT)])
    monkeypatch.setattr(mod, "get_llm", lambda *_a, **_k: llm)

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

    assert llm.calls == 2
    repair = result.data["repairs"][0]
    assert repair["resolved"] is True
    assert [a["outcome"] for a in repair["attempts"]] == ["llm_patch_failed", "passed"]
