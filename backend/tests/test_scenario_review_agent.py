import json

import pytest

from app.agents.test_planning import scenario_review_agent
from app.agents.test_planning.scenario_review_agent import ScenarioReviewAgent


class _FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    async def generate(self, **_kwargs):
        self.calls += 1
        return self.response


REQ = {
    "id": 1,
    "requirement_id": "REQ-0001",
    "title": "Login",
    "summary": "User can log in",
    "acceptance_criteria": ["Valid credentials succeed", "Invalid credentials show an error"],
    "business_rules": [],
}

SCENARIO = {
    "id": 10,
    "scenario_id": "TS-0001",
    "title": "Successful login",
    "description": "User logs in with valid credentials",
    "scenario_type": "positive",
    "priority": "High",
    "coverage_mapping": [],
    "_source_requirement_id": 1,
}


@pytest.mark.anyio
async def test_scenario_review_maps_llm_output_to_verdict(monkeypatch):
    llm_output = json.dumps({
        "coverage_score": 4.0,
        "business_alignment_score": 4.0,
        "clarity_score": 4.0,
        "prioritization_score": 4.0,
        "overall_score": 4.0,
        "verdict": "pass",
        "coverage_gaps": [],
        "issues": [],
        "suggestions": ["Add a negative-path scenario"],
    })
    monkeypatch.setattr(scenario_review_agent, "get_llm", lambda *_a, **_k: _FakeLLM(llm_output))

    result = await ScenarioReviewAgent().run(requirements=[REQ], scenarios=[SCENARIO])

    assert result.success is True
    assert result.data["target_kind"] == "test_scenario_set"
    reviews = result.data["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["target_ref"] == "REQ-0001"
    assert reviews[0]["verdict"] == "pass"
    assert reviews[0]["scores"]["coverage"] == 4.0
    assert result.data["summary"] == {"pass": 1, "needs_revision": 0, "fail": 0}


@pytest.mark.anyio
async def test_scenario_review_flags_requirement_with_no_scenarios(monkeypatch):
    monkeypatch.setattr(scenario_review_agent, "get_llm", lambda *_a, **_k: _FakeLLM("{}"))

    result = await ScenarioReviewAgent().run(requirements=[REQ], scenarios=[])

    assert result.success is True
    reviews = result.data["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["verdict"] == "fail"
    assert reviews[0]["coverage_gaps"][0]["severity"] == "high"
    assert "No test scenarios were generated" in reviews[0]["coverage_gaps"][0]["description"]


@pytest.mark.anyio
async def test_scenario_review_fails_when_no_requirements_provided():
    result = await ScenarioReviewAgent().run(requirements=[], scenarios=[SCENARIO])
    assert result.success is False
    assert "No requirements provided" in result.error


@pytest.mark.anyio
async def test_scenario_review_invalid_verdict_defaults_to_needs_revision(monkeypatch):
    llm_output = json.dumps({
        "coverage_score": 3.0,
        "business_alignment_score": 3.0,
        "clarity_score": 3.0,
        "prioritization_score": 3.0,
        "overall_score": 3.0,
        "verdict": "not_a_real_verdict",
        "coverage_gaps": [],
        "issues": [],
        "suggestions": [],
    })
    monkeypatch.setattr(scenario_review_agent, "get_llm", lambda *_a, **_k: _FakeLLM(llm_output))

    result = await ScenarioReviewAgent().run(requirements=[REQ], scenarios=[SCENARIO])

    assert result.data["reviews"][0]["verdict"] == "needs_revision"
