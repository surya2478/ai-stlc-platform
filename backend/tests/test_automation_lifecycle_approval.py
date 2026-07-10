"""Phase 4.6: the staged post-generation approval chain
(dry_run_passed -> reviewer_approved -> lead_approved
-> [environment_approve, required for PROD_SANITY] -> ci_ready),
distinct from the legacy draft/in_review approve_script workflow."""
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.automation_script import AutomationScript
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.user import User
from app.services import automation_service


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


class _ExecuteResult:
    def __init__(self, value=None, values=None):
        self._value = value
        self._values = values or []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return _ScalarsResult(self._values)


class _FakeDB:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.added = []

    async def execute(self, _stmt):
        if not self.responses:
            return _ExecuteResult()
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _ExecuteResult(values=value)
        return _ExecuteResult(value=value)

    async def get(self, model, obj_id):
        return None

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None

    async def commit(self):
        return None


def _script(**overrides):
    data = {
        "id": 1,
        "project_id": 1,
        "created_by": 2,
        "script_id": "AS-0001",
        "framework": "playwright",
        "code": "x",
        "status": "dry_run_passed",
        "contract": {"environmentProfile": "QA"},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return AutomationScript(**data)


@pytest.mark.anyio
async def test_reviewer_approve_moves_dry_run_passed_to_reviewer_approved():
    db = _FakeDB()
    script = _script()

    updated = await automation_service.advance_script_lifecycle(db, script, "reviewer_approve", "Looks solid")

    assert updated.status == "reviewer_approved"
    assert updated.metadata_ == {"reviewer_approve_notes": "Looks solid"}


@pytest.mark.anyio
async def test_reviewer_reject_moves_dry_run_passed_to_rejected():
    db = _FakeDB()
    script = _script()

    updated = await automation_service.advance_script_lifecycle(db, script, "reviewer_reject", "Coverage gap")

    assert updated.status == "rejected"


@pytest.mark.anyio
async def test_lead_approve_requires_reviewer_approved_first():
    db = _FakeDB()
    script = _script(status="dry_run_passed")

    with pytest.raises(ValueError, match="Expected status 'reviewer_approved'"):
        await automation_service.advance_script_lifecycle(db, script, "lead_approve", None)


@pytest.mark.anyio
async def test_lead_approve_succeeds_from_reviewer_approved():
    db = _FakeDB()
    script = _script(status="reviewer_approved")

    updated = await automation_service.advance_script_lifecycle(db, script, "lead_approve", None)

    assert updated.status == "lead_approved"


@pytest.mark.anyio
async def test_mark_ci_ready_succeeds_for_non_prod_sanity_without_environment_approve():
    db = _FakeDB([])  # prod_sanity_gate_satisfied's ApprovalAction query — irrelevant since not PROD_SANITY
    script = _script(status="lead_approved", contract={"environmentProfile": "QA"})

    updated = await automation_service.advance_script_lifecycle(db, script, "mark_ci_ready", None)

    assert updated.status == "ci_ready"


@pytest.mark.anyio
async def test_mark_ci_ready_blocked_for_prod_sanity_without_environment_approve():
    db = _FakeDB([])  # no matching ApprovalAction found
    script = _script(status="lead_approved", contract={"environmentProfile": "PROD_SANITY"})

    with pytest.raises(ValueError, match="requires an environment_approve"):
        await automation_service.advance_script_lifecycle(db, script, "mark_ci_ready", None)


@pytest.mark.anyio
async def test_mark_ci_ready_succeeds_for_prod_sanity_after_environment_approve():
    from app.models.approval import ApprovalAction
    existing_approval = ApprovalAction(
        id=1, project_id=1, user_id=3, action_type="environment_approve_automation_script",
        entity_type="automation_script", entity_id=1, decision="approved",
    )
    db = _FakeDB([existing_approval])
    script = _script(status="lead_approved", contract={"environmentProfile": "PROD_SANITY"})

    updated = await automation_service.advance_script_lifecycle(db, script, "mark_ci_ready", None)

    assert updated.status == "ci_ready"


@pytest.mark.anyio
async def test_environment_approve_does_not_change_status():
    db = _FakeDB()
    script = _script(status="lead_approved", contract={"environmentProfile": "PROD_SANITY"})

    updated = await automation_service.advance_script_lifecycle(db, script, "environment_approve", "Env verified")

    assert updated.status == "lead_approved"
    assert updated.metadata_ == {"environment_approve_notes": "Env verified"}


@pytest.mark.anyio
async def test_unknown_action_raises():
    db = _FakeDB()
    script = _script()

    with pytest.raises(ValueError, match="Unknown lifecycle approval action"):
        await automation_service.advance_script_lifecycle(db, script, "not_a_real_action", None)


# ── Endpoint-level permission gating ─────────────────────────────────────────

async def _member_user():
    return User(
        id=2, email="member@example.com", full_name="Member", hashed_password="x",
        role="qa_engineer", is_active=True, is_superuser=False,
    )


def _project():
    return Project(id=1, owner_id=99, name="Test Project")


def _membership(role: str):
    return ProjectMembership(project_id=1, user_id=2, role=role, is_active=True)


def test_lifecycle_approval_endpoint_reviewer_approve_success():
    script = _script(status="dry_run_passed")
    # require_entity_permission consumes: get_script (script), then
    # require_project_access's own VIEW_PROJECT membership check (project +
    # membership), then require_permission's actual-permission membership
    # check (membership again) — two membership lookups per call.
    db = _FakeDB(script, _project(), _membership("Test Lead"), _membership("Test Lead"))

    async def fake_db() -> AsyncIterator[_FakeDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).post(
            "/api/v1/automation/1/lifecycle-approval",
            json={"action": "reviewer_approve", "notes": "Looks good"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "reviewer_approved"
    approval_action = db.added[0]
    assert approval_action.action_type == "reviewer_approve_automation_script"
    assert approval_action.decision == "approved"
    assert approval_action.actor_role == "qa_engineer"


def test_lifecycle_approval_endpoint_rejects_tester_for_lead_approve():
    script = _script(status="reviewer_approved")
    db = _FakeDB(script, _project(), _membership("Tester"))

    async def fake_db() -> AsyncIterator[_FakeDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).post(
            "/api/v1/automation/1/lifecycle-approval",
            json={"action": "lead_approve"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_lifecycle_approval_endpoint_blocks_reviewer_approve_when_ungrounded_without_notes():
    script = _script(status="dry_run_passed", metadata_={"grounding": {"ungrounded_elements": ["Page.searchBar"]}})
    db = _FakeDB(script, _project(), _membership("Test Lead"), _membership("Test Lead"))

    async def fake_db() -> AsyncIterator[_FakeDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).post(
            "/api/v1/automation/1/lifecycle-approval",
            json={"action": "reviewer_approve"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "Page.searchBar" in response.json()["detail"]


def test_lifecycle_approval_endpoint_allows_reviewer_approve_when_ungrounded_with_notes():
    script = _script(status="dry_run_passed", metadata_={"grounding": {"ungrounded_elements": ["Page.searchBar"]}})
    db = _FakeDB(script, _project(), _membership("Test Lead"), _membership("Test Lead"))

    async def fake_db() -> AsyncIterator[_FakeDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).post(
            "/api/v1/automation/1/lifecycle-approval",
            json={"action": "reviewer_approve", "notes": "Known gap, approving for manual follow-up"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "reviewer_approved"


def test_lifecycle_approval_endpoint_returns_409_on_wrong_stage():
    script = _script(status="dry_run_passed")  # not yet reviewer_approved
    db = _FakeDB(script, _project(), _membership("Test Lead"), _membership("Test Lead"))

    async def fake_db() -> AsyncIterator[_FakeDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).post(
            "/api/v1/automation/1/lifecycle-approval",
            json={"action": "lead_approve"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
