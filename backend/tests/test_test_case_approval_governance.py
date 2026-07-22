"""UI-013 approval-path regression tests.

These tests exercise the two persisted service paths used by Test Case
Approval without mutating a live project database.
"""
from types import SimpleNamespace

import anyio

from app.schemas.traceability import ApprovalDecisionRequest
from app.services import test_plan_service, traceability_service


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None

    async def refresh(self, _value):
        return None


def test_request_changes_records_audited_decision_and_returns_case_to_pending_approval():
    db = FakeDB()
    test_case = SimpleNamespace(
        id=34,
        project_id=3,
        status="approved",
        metadata_={},
        jira_issue_key=None,
        agent_run_id=None,
    )
    user = SimpleNamespace(id=7, role="qa_lead")
    body = ApprovalDecisionRequest(
        action="request_changes",
        notes="Add the missing evidence requirement",
        changes_requested={"evidence_requirements": "required"},
    )

    async def run():
        return await traceability_service.approve_artifact(
            db,
            entity=test_case,
            entity_type="test_case",
            user=user,
            body=body,
            request_id="req-ui-013",
        )

    action = anyio.run(run)

    assert test_case.status == "pending_approval"
    assert action in db.added
    assert action.entity_type == "test_case"
    assert action.entity_id == 34
    assert action.decision == "requested_changes"
    assert action.notes == "Add the missing evidence requirement"
    assert action.changes_requested == {"evidence_requirements": "required"}
    assert action.old_value["status"] == "approved"
    assert action.new_value["status"] == "pending_approval"
    assert action.request_id == "req-ui-013"


def test_test_case_approve_updates_status_and_adds_immutable_field_history():
    db = FakeDB()
    test_case = SimpleNamespace(
        id=34,
        project_id=3,
        status="pending_approval",
        metadata_={},
        updated_by=None,
        last_status_updated_by=None,
        last_status_updated_at=None,
    )

    async def run():
        return await test_plan_service.approve_test_case(
            db,
            test_case,
            "approve",
            "All readiness checks passed",
            user_id=7,
        )

    updated = anyio.run(run)

    assert updated.status == "approved"
    assert updated.updated_by == 7
    assert updated.metadata_["review_notes"] == "All readiness checks passed"
    history = db.added[0]
    assert history.test_case_id == 34
    assert history.field_name == "status"
    assert history.old_value == "pending_approval"
    assert history.new_value == "approved"
    assert history.changed_by == 7
    assert history.comment == "All readiness checks passed"
