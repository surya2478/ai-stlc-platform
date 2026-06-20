from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.user import User
from app.services.rbac_service import MANAGE_PROJECT, VIEW_PROJECT, permissions_for_role


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


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


class _FakeMembershipDB:
    def __init__(self, membership: ProjectMembership | None):
        self.membership = membership
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        if self.calls == 1:
            return _ExecuteResult(Project(id=1, owner_id=99, name="Shared project"))
        return _ExecuteResult(self.membership)


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


def test_project_role_permissions_are_derived_from_membership_role():
    permissions = permissions_for_role("Tester")

    assert VIEW_PROJECT in permissions
    assert MANAGE_PROJECT not in permissions


def test_member_with_view_permission_can_access_project():
    membership = ProjectMembership(project_id=1, user_id=2, role="Tester", is_active=True)

    async def fake_db() -> AsyncIterator[_FakeMembershipDB]:
        yield _FakeMembershipDB(membership)

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).get("/api/v1/requirements/project/1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code != 403


def test_member_without_manage_permission_cannot_list_project_memberships():
    membership = ProjectMembership(project_id=1, user_id=2, role="Tester", is_active=True)

    async def fake_db() -> AsyncIterator[_FakeMembershipDB]:
        yield _FakeMembershipDB(membership)

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).get("/api/v1/projects/1/memberships")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
