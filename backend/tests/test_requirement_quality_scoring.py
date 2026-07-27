from app.agents.requirement.quality_agent import (
    QUALITY_PASS_SCORE,
    calculate_quality_outcome,
    _validate_and_merge,
)


def review(**overrides):
    values = {
        "requirement_id": 7,
        "requirement_title": "Billing change",
        "completeness_score": 4,
        "clarity_score": 4,
        "testability_score": 4,
        "ambiguity_score": 4,
        "acceptance_criteria_score": 4,
        "interface_readiness_score": 4,
        "telecom_domain_completeness": 4,
        "scenario_generation_readiness": 4,
        "overall_score": 1,
        "issues": [],
        "suggestions": [],
        "verdict": "fail",
    }
    values.update(overrides)
    return values


def test_quality_outcome_uses_governed_weights_and_pass_gate():
    overall, verdict = calculate_quality_outcome(review())
    assert overall == 4
    assert overall >= QUALITY_PASS_SCORE
    assert verdict == "pass"


def test_scenario_readiness_gate_prevents_a_high_overall_pass():
    overall, verdict = calculate_quality_outcome(review(scenario_generation_readiness=2))
    assert overall >= QUALITY_PASS_SCORE
    assert verdict == "needs_revision"


def test_validated_review_overwrites_llm_overall_and_verdict():
    state = {
        "requirements": [{"id": 7, "title": "Billing change"}],
        "reviews": [review(overall_score=1, verdict="fail")],
        "errors": [],
        "user_id": 1,
        "project_id": 1,
    }
    result = _validate_and_merge(state)
    persisted = result["requirements"][0]["_quality_review"]
    assert persisted["overall_score"] == 4
    assert persisted["verdict"] == "pass"
