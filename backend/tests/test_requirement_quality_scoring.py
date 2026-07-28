from datetime import datetime, timezone
from types import SimpleNamespace

from app.agents.requirement.quality_agent import (
    QUALITY_PASS_SCORE,
    calculate_quality_outcome,
    _validate_and_merge,
)
from app.services.agent_run_service import derive_idempotency_key
from app.services.requirement_service import build_quality_agent_input


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


def quality_requirement(**overrides):
    values = {
        "id": 139,
        "requirement_id": "REQ-0139",
        "title": "Provision subscriber",
        "summary": "Provision and activate the subscriber.",
        "acceptance_criteria": ["Subscriber is active"],
        "business_rules": [],
        "user_roles": [],
        "systems_impacted": ["Provisioning"],
        "impacted_systems": ["Charging"],
        "impacted_interfaces": ["REST"],
        "upstream_systems": [],
        "downstream_systems": [],
        "ui_pages": [],
        "apis": ["/subscribers"],
        "dependencies": [],
        "risks": [],
        "missing_information": [],
        "telecom_domain": "Network",
        "qa_domain": None,
        "business_process": "Sales",
        "product": "Postpaid",
        "product_group": "Mobile",
        "sub_request_type": "New",
        "test_phase": "SIT",
        "risk_level": "Critical",
        "release_version": "1.0",
        "review_notes": None,
        "metadata_": {},
        "version": 1,
        "updated_at": datetime(2026, 7, 28, 7, 6, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_quality_agent_input_includes_classification_and_revision():
    payload = build_quality_agent_input(quality_requirement())

    assert payload["business_process"] == "Sales"
    assert payload["product"] == "Postpaid"
    assert payload["sub_request_type"] == "New"
    assert payload["quality_revision"] == "2026-07-28T07:06:00+00:00"


def test_requirement_edit_changes_quality_run_idempotency_key():
    before = build_quality_agent_input(quality_requirement())
    after = build_quality_agent_input(
        quality_requirement(
            product="Postpaid Plus",
            updated_at=datetime(2026, 7, 28, 7, 12, tzinfo=timezone.utc),
        )
    )

    before_key, _ = derive_idempotency_key(
        project_id=7,
        user_id=1,
        agent_name="requirement_quality",
        input_data={"requirements": [before], "project_id": 7},
    )
    after_key, _ = derive_idempotency_key(
        project_id=7,
        user_id=1,
        agent_name="requirement_quality",
        input_data={"requirements": [after], "project_id": 7},
    )

    assert before_key != after_key
