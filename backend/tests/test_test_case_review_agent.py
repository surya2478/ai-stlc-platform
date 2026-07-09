import json

import pytest

from app.agents.test_planning import test_case_review_agent
from app.agents.test_planning.test_case_review_agent import TestCaseReviewAgent


class _FakeLLM:
    def __init__(self, response: str):
        self.response = response

    async def generate(self, **_kwargs):
        return self.response


SCENARIO = {
    "id": 10,
    "scenario_id": "TS-0001",
    "title": "Successful login",
    "description": "User logs in with valid credentials",
    "scenario_type": "positive",
    "priority": "High",
    "coverage_mapping": [],
    "test_environment": "QA",
}

TEST_CASE = {
    "id": 100,
    "test_case_id": "TC-0001",
    "title": "Valid login succeeds",
    "preconditions": ["User account exists"],
    "steps": [{"step_number": 1, "action": "Enter valid credentials", "expected_result": "Redirected to dashboard"}],
    "expected_result": "User is logged in",
    "priority": "High",
    "test_type": "functional",
    "_source_scenario_id": 10,
}


@pytest.mark.anyio
async def test_test_case_review_maps_llm_output_to_verdict(monkeypatch):
    llm_output = json.dumps({
        "step_quality_score": 4.0,
        "data_readiness_score": 4.0,
        "expected_result_clarity_score": 4.0,
        "phase_fit_score": 4.0,
        "coverage_score": 4.0,
        "overall_score": 4.0,
        "verdict": "pass",
        "coverage_gaps": [],
        "issues": [],
        "suggestions": [],
    })
    monkeypatch.setattr(test_case_review_agent, "get_llm", lambda *_a, **_k: _FakeLLM(llm_output))

    result = await TestCaseReviewAgent().run(scenarios=[SCENARIO], test_cases=[TEST_CASE])

    assert result.success is True
    assert result.data["target_kind"] == "test_case_set"
    reviews = result.data["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["target_ref"] == "TS-0001"
    assert reviews[0]["verdict"] == "pass"
    assert reviews[0]["scores"]["step_quality"] == 4.0


@pytest.mark.anyio
async def test_test_case_review_flags_scenario_with_no_test_cases(monkeypatch):
    monkeypatch.setattr(test_case_review_agent, "get_llm", lambda *_a, **_k: _FakeLLM("{}"))

    result = await TestCaseReviewAgent().run(scenarios=[SCENARIO], test_cases=[])

    assert result.success is True
    reviews = result.data["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["verdict"] == "fail"
    assert "No test cases were generated" in reviews[0]["coverage_gaps"][0]["description"]


@pytest.mark.anyio
async def test_test_case_review_fails_when_no_scenarios_provided():
    result = await TestCaseReviewAgent().run(scenarios=[], test_cases=[TEST_CASE])
    assert result.success is False
    assert "No scenarios provided" in result.error
