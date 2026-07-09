import json

import pytest

from app.agents.automation import script_review_agent
from app.agents.automation.script_review_agent import AutomationScriptReviewAgent


class _FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    async def generate(self, **_kwargs):
        self.calls += 1
        return self.response


SCRIPT = {
    "script_id": 1,
    "test_case": {
        "test_case_id": "TC-0001",
        "title": "Valid login succeeds",
        "preconditions": ["User has an active account"],
        "steps": [{"step_number": 1, "action": "enter valid credentials", "expected_result": "redirected to dashboard"}],
        "expected_result": "User lands on the dashboard",
    },
    "code": "test('login', async ({ page }) => { await page.goto('/'); });",
    "static_gate_result": {"passed": True, "violations": []},
    "dry_run_evidence": {"passed": True},
}


@pytest.mark.anyio
async def test_script_review_maps_llm_output_to_verdict(monkeypatch):
    llm_output = json.dumps({
        "business_step_coverage_score": 4.0,
        "assertion_meaningfulness_score": 4.0,
        "code_cleanliness_score": 4.0,
        "cleanup_presence_score": 4.0,
        "overall_score": 4.0,
        "verdict": "pass",
        "coverage_gaps": [],
        "issues": [],
        "suggestions": ["Add an explicit assertion on the dashboard header"],
    })
    monkeypatch.setattr(script_review_agent, "get_llm", lambda *_a, **_k: _FakeLLM(llm_output))

    result = await AutomationScriptReviewAgent().run(scripts=[SCRIPT])

    assert result.success is True
    assert result.data["target_kind"] == "automation_script"
    reviews = result.data["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["target_ref"] == "TC-0001"
    assert reviews[0]["verdict"] == "pass"
    assert reviews[0]["scores"]["business_step_coverage"] == 4.0
    assert result.data["summary"] == {"pass": 1, "needs_revision": 0, "fail": 0}


@pytest.mark.anyio
async def test_script_review_falls_back_to_script_id_when_no_test_case(monkeypatch):
    llm_output = json.dumps({
        "business_step_coverage_score": 3.0,
        "assertion_meaningfulness_score": 3.0,
        "code_cleanliness_score": 3.0,
        "cleanup_presence_score": 3.0,
        "overall_score": 3.0,
        "verdict": "needs_revision",
        "coverage_gaps": [],
        "issues": [],
        "suggestions": [],
    })
    monkeypatch.setattr(script_review_agent, "get_llm", lambda *_a, **_k: _FakeLLM(llm_output))

    script_without_tc = {**SCRIPT, "test_case": {}}
    result = await AutomationScriptReviewAgent().run(scripts=[script_without_tc])

    assert result.data["reviews"][0]["target_ref"] == "1"


@pytest.mark.anyio
async def test_script_review_fails_when_no_scripts_provided():
    result = await AutomationScriptReviewAgent().run(scripts=[])
    assert result.success is False
    assert "No scripts provided" in result.error


@pytest.mark.anyio
async def test_script_review_invalid_verdict_defaults_to_needs_revision(monkeypatch):
    llm_output = json.dumps({
        "business_step_coverage_score": 3.0,
        "assertion_meaningfulness_score": 3.0,
        "code_cleanliness_score": 3.0,
        "cleanup_presence_score": 3.0,
        "overall_score": 3.0,
        "verdict": "not_a_real_verdict",
        "coverage_gaps": [],
        "issues": [],
        "suggestions": [],
    })
    monkeypatch.setattr(script_review_agent, "get_llm", lambda *_a, **_k: _FakeLLM(llm_output))

    result = await AutomationScriptReviewAgent().run(scripts=[SCRIPT])

    assert result.data["reviews"][0]["verdict"] == "needs_revision"


@pytest.mark.anyio
async def test_script_review_reports_coverage_gaps(monkeypatch):
    llm_output = json.dumps({
        "business_step_coverage_score": 2.0,
        "assertion_meaningfulness_score": 2.0,
        "code_cleanliness_score": 3.0,
        "cleanup_presence_score": 3.0,
        "overall_score": 2.5,
        "verdict": "needs_revision",
        "coverage_gaps": ["Script never verifies the redirected-to-dashboard expected result"],
        "issues": ["No assertion on final URL"],
        "suggestions": [],
    })
    monkeypatch.setattr(script_review_agent, "get_llm", lambda *_a, **_k: _FakeLLM(llm_output))

    result = await AutomationScriptReviewAgent().run(scripts=[SCRIPT])

    review = result.data["reviews"][0]
    assert len(review["coverage_gaps"]) == 1
    assert review["coverage_gaps"][0]["description"].startswith("Script never verifies")
    assert any(f["issue"] == "No assertion on final URL" for f in review["findings"])


@pytest.mark.anyio
async def test_script_review_one_script_erroring_does_not_block_others(monkeypatch):
    llm_output = json.dumps({
        "business_step_coverage_score": 4.0,
        "assertion_meaningfulness_score": 4.0,
        "code_cleanliness_score": 4.0,
        "cleanup_presence_score": 4.0,
        "overall_score": 4.0,
        "verdict": "pass",
        "coverage_gaps": [],
        "issues": [],
        "suggestions": [],
    })

    class _FlakyLLM:
        def __init__(self):
            self.calls = 0

        async def generate(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("LLM timeout")
            return llm_output

    monkeypatch.setattr(script_review_agent, "get_llm", lambda *_a, **_k: _FlakyLLM())

    other_script = {**SCRIPT, "script_id": 2, "test_case": {**SCRIPT["test_case"], "test_case_id": "TC-0002"}}
    result = await AutomationScriptReviewAgent().run(scripts=[SCRIPT, other_script])

    assert result.success is True
    assert len(result.data["reviews"]) == 1
    assert result.data["reviews"][0]["target_ref"] == "TC-0002"


@pytest.mark.anyio
async def test_script_review_fails_when_all_scripts_error(monkeypatch):
    class _BrokenLLM:
        async def generate(self, **_kwargs):
            raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(script_review_agent, "get_llm", lambda *_a, **_k: _BrokenLLM())

    result = await AutomationScriptReviewAgent().run(scripts=[SCRIPT])

    assert result.success is False
    assert "Script review failed for all scripts" in result.error
