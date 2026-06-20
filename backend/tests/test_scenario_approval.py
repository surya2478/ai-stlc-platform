import pytest
from datetime import datetime
from collections.abc import AsyncIterator
from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.test_scenario import TestScenario
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.user import User
from app.services import test_plan_service


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


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

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None

    async def commit(self):
        return None


async def _member_user():
    return User(
        id=2,
        email="member@example.com",
        full_name="Member User",
        hashed_password="not-used",
        role="qa_engineer",
        is_active=True,
        is_superuser=False,
    )


def _project():
    return Project(id=1, owner_id=99, name="Test Project")


def _membership(role: str):
    return ProjectMembership(project_id=1, user_id=2, role=role, is_active=True)


def _scenario(**overrides):
    data = {
        "id": 5,
        "project_id": 1,
        "created_by": 2,
        "scenario_id": "TS-001",
        "title": "Successful eSIM replacement",
        "priority": "Medium",
        "status": "draft",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    data.update(overrides)
    return TestScenario(**data)


@pytest.mark.anyio
async def test_approve_test_scenario_service():
    db = _FakeDB()
    scenario = _scenario()
    
    updated = await test_plan_service.approve_test_scenario(db, scenario, "approve", "Looks good")
    
    assert updated.status == "approved"
    assert updated.metadata_ == {"review_notes": "Looks good"}


@pytest.mark.anyio
async def test_reject_test_scenario_service():
    db = _FakeDB()
    scenario = _scenario()
    
    updated = await test_plan_service.approve_test_scenario(db, scenario, "reject", "Missing edge cases")
    
    assert updated.status == "rejected"
    assert updated.metadata_ == {"review_notes": "Missing edge cases"}


def test_approve_scenario_endpoint_success():
    scenario = _scenario()
    db = _FakeDB(scenario, _project(), _membership("Test Lead"), _membership("Test Lead"))

    async def fake_db() -> AsyncIterator[_FakeDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).post(
            "/api/v1/test-plans/scenarios/5/approve",
            json={"action": "approve", "notes": "Approved by QA Lead"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    # Ensure ApprovalAction is logged and created
    assert len(db.added) == 1
    approval_action = db.added[0]
    assert approval_action.action_type == "approve_test_scenario"
    assert approval_action.entity_type == "test_scenario"
    assert approval_action.decision == "approved"
    assert approval_action.notes == "Approved by QA Lead"


def test_approve_scenario_endpoint_unauthorized():
    scenario = _scenario()
    db = _FakeDB(scenario, _project(), _membership("Tester"), _membership("Tester"))  # Tester does not have APPROVE_TEST_PLANS permission

    async def fake_db() -> AsyncIterator[_FakeDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).post(
            "/api/v1/test-plans/scenarios/5/approve",
            json={"action": "approve", "notes": "I try to approve"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
