from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.requirement_service import (
    approve_requirement,
    requirement_workflow_stage,
    transition_requirement,
)


class FakeDB:
    async def flush(self):
        return None

    async def refresh(self, _value):
        return None


def requirement(**overrides):
    values = {
        "id": 1,
        "project_id": 4,
        "requirement_id": "REQ-0001",
        "title": "Cancel order before payment",
        "source": "jira",
        "status": "draft",
        "readiness_status": "intake_ready",
        "quality_verdict": None,
        "missing_information": [],
        "telecom_domain": "Digital",
        "qa_domain": None,
        "business_process": "Order Management",
        "product": "OMS",
        "product_group": None,
        "sub_request_type": "Functional",
        "systems_impacted": ["OMS"],
        "impacted_systems": None,
        "impacted_interfaces": [],
        "upstream_systems": [],
        "downstream_systems": [],
        "metadata_": {"workflow_stage": "intake"},
        "review_notes": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_legacy_stage_mapping_does_not_treat_ai_review_as_final_review():
    req = requirement(metadata_={}, status="pending_review", readiness_status="ai_review_pending")
    assert requirement_workflow_stage(req) == "analysis"


@pytest.mark.asyncio
async def test_requirement_moves_through_each_stage_only_in_order():
    req = requirement()
    db = FakeDB()

    await transition_requirement(db, req, "send_to_analysis", user_id=7)
    assert requirement_workflow_stage(req) == "analysis"
    assert req.status == "draft"

    with pytest.raises(HTTPException) as exc:
        await transition_requirement(db, req, "send_to_traceability", user_id=7)
    assert exc.value.status_code == 409

    req.quality_verdict = "pass"
    await transition_requirement(db, req, "send_to_traceability", user_id=7)
    assert requirement_workflow_stage(req) == "traceability"

    await transition_requirement(db, req, "send_to_review", user_id=7)
    assert requirement_workflow_stage(req) == "review"
    assert req.status == "pending_review"
    assert req.metadata_["traceability_validated"] is True

    await approve_requirement(db, req, "approve", "Validated by reviewer")
    assert req.status == "approved"


@pytest.mark.asyncio
async def test_approval_is_rejected_outside_final_review():
    req = requirement()
    with pytest.raises(HTTPException) as exc:
        await approve_requirement(FakeDB(), req, "approve", None)
    assert exc.value.status_code == 409
    assert "Review & Approval" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_final_review_cannot_approve_without_traceability_validation():
    req = requirement(
        status="pending_review",
        readiness_status="pending_review",
        quality_verdict="pass",
        metadata_={"workflow_stage": "review"},
    )
    with pytest.raises(HTTPException) as exc:
        await approve_requirement(FakeDB(), req, "approve", None)
    assert exc.value.status_code == 409
    assert "Traceability" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_review_can_return_to_traceability_or_analysis():
    db = FakeDB()
    req = requirement(
        status="pending_review",
        readiness_status="pending_review",
        quality_verdict="pass",
        metadata_={"workflow_stage": "review", "traceability_validated": True},
    )
    await transition_requirement(db, req, "send_back_to_traceability", user_id=9)
    assert requirement_workflow_stage(req) == "traceability"
    await transition_requirement(db, req, "send_back_to_analysis", user_id=9)
    assert requirement_workflow_stage(req) == "analysis"


@pytest.mark.asyncio
async def test_clarification_request_requires_details_and_stays_in_analysis():
    db = FakeDB()
    req = requirement(
        readiness_status="analysis_pending",
        metadata_={"workflow_stage": "analysis"},
    )
    with pytest.raises(HTTPException) as exc:
        await transition_requirement(db, req, "request_clarification", notes="", user_id=11)
    assert exc.value.status_code == 422

    await transition_requirement(
        db,
        req,
        "request_clarification",
        notes="Confirm the source and allowed cancellation window.",
        user_id=11,
    )
    assert requirement_workflow_stage(req) == "analysis"
    assert req.readiness_status == "needs_clarification"
    assert req.review_notes == "Confirm the source and allowed cancellation window."
    assert req.metadata_["workflow_history"][-1]["action"] == "request_clarification"


@pytest.mark.asyncio
async def test_clarification_resolution_clears_blocker_and_requeues_analysis():
    db = FakeDB()
    req = requirement(
        readiness_status="needs_clarification",
        missing_information=["Cancellation window"],
        review_notes="Confirm the source and allowed cancellation window.",
        metadata_={"workflow_stage": "analysis"},
    )
    await transition_requirement(
        db,
        req,
        "resolve_clarification",
        notes="Owner confirmed a 30-day cancellation window in the signed process document.",
        user_id=11,
    )
    assert requirement_workflow_stage(req) == "analysis"
    assert req.readiness_status == "analysis_pending"
    assert req.missing_information == []
    assert req.metadata_["clarification_resolved"] is True
