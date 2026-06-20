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

    async def execute(self, _stmt):
        if not self.responses:
            return _ExecuteResult()
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _ExecuteResult(values=value)
        return _ExecuteResult(value=value)


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


def test_generate_cases_rejects_draft_scenario():
    # If the explicit scenario is in draft status, the API should reject it with 400 Bad Request
    scenario = _scenario(status="draft")
    db = _FakeDB(
        _project(),
        _membership("Test Lead"),
        _membership("Test Lead"),
        scenario
    )

    async def fake_db() -> AsyncIterator[_FakeDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).post(
            "/api/v1/test-plans/agent/generate-cases",
            json={
                "project_id": 1,
                "scenario_ids": [5],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "is not approved" in response.json()["detail"]
