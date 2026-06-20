from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.project import Project
from app.models.user import User


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    async def execute(self, _stmt):
        return _ScalarResult(Project(id=1, owner_id=1, name="Owner project"))


async def _fake_db() -> AsyncIterator[_FakeDB]:
    yield _FakeDB()


def test_business_endpoint_without_token_returns_401():
    app.dependency_overrides[get_db] = _fake_db
    try:
        response = TestClient(app).get("/api/v1/requirements/project/1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_cross_user_project_access_returns_403():
    async def other_user():
        return User(
            id=2,
            email="other@example.com",
            full_name="Other User",
            hashed_password="not-used",
            role="qa_engineer",
            is_active=True,
            is_superuser=False,
        )

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[require_user] = other_user
    try:
        response = TestClient(app).get("/api/v1/requirements/project/1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
