from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.project_membership import ProjectMembership
from app.models.user import User


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


class _CreateUserDB:
    def __init__(self):
        self.created_user = None

    async def execute(self, _stmt):
        return _ScalarResult(None)

    def add(self, obj):
        self.created_user = obj
        obj.id = 101
        if obj.is_active is None:
            obj.is_active = True

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None


class _ListUsersDB:
    def __init__(self, membership: ProjectMembership | None, users: list[User]):
        self.membership = membership
        self.users = users
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        if self.calls == 1:
            return _ExecuteResult(value=self.membership)
        return _ExecuteResult(values=self.users)


class _UpdateUserDB:
    def __init__(self, target: User, users: list[User]):
        self.target = target
        self.users = users
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        if self.calls == 1:
            return _ExecuteResult(value=self.target)
        return _ExecuteResult(values=self.users)

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None


async def _admin_user():
    return User(
        id=1,
        email="admin@example.com",
        full_name="Platform Admin",
        hashed_password="not-used",
        role="admin",
        is_active=True,
        is_superuser=True,
    )


async def _qa_user():
    return User(
        id=2,
        email="qa@example.com",
        full_name="QA User",
        hashed_password="not-used",
        role="qa_engineer",
        is_active=True,
        is_superuser=False,
    )


def test_public_registration_cannot_create_admin_or_superuser():
    db = _CreateUserDB()

    async def fake_db() -> AsyncIterator[_CreateUserDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    try:
        response = TestClient(app).post(
            "/api/v1/users/register",
            json={
                "email": "new@example.com",
                "full_name": "New User",
                "password": "Strongpass123!",
                "role": "admin",
                "is_superuser": True,
            },
        )

    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["role"] == "qa_engineer"
    assert response.json()["is_superuser"] is False
    assert db.created_user.role == "qa_engineer"
    assert db.created_user.is_superuser is False


def test_non_admin_cannot_list_users():
    app.dependency_overrides[require_user] = _qa_user
    try:
        response = TestClient(app).get("/api/v1/users/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_project_manager_can_list_users_for_managed_project():
    membership = ProjectMembership(project_id=9, user_id=2, role="Project Admin", is_active=True)
    visible_user = User(
        id=11,
        email="visible@example.com",
        full_name="Visible User",
        hashed_password="not-used",
        role="qa_engineer",
        is_active=True,
        is_superuser=False,
    )
    db = _ListUsersDB(membership=membership, users=[visible_user])

    async def fake_db() -> AsyncIterator[_ListUsersDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _qa_user
    try:
        response = TestClient(app).get("/api/v1/users/?project_id=9")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 11,
            "email": "visible@example.com",
            "full_name": "Visible User",
            "role": "qa_engineer",
            "is_active": True,
            "is_superuser": False,
        }
    ]


# Satisfies validate_password_strength: 12+ chars, upper, lower, digit, symbol.
_COMPLIANT_PASSWORD = "Str0ng!Passw0rd"


def _create_user(payload: dict):
    db = _CreateUserDB()

    async def fake_db() -> AsyncIterator[_CreateUserDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _admin_user
    try:
        response = TestClient(app).post("/api/v1/users/", json=payload)
    finally:
        app.dependency_overrides.clear()
    return response, db


def test_admin_can_create_user_with_valid_role():
    response, _ = _create_user(
        {
            "email": "lead@example.com",
            "full_name": "QA Lead",
            "password": _COMPLIANT_PASSWORD,
            "role": "qa_lead",
            "is_superuser": False,
        }
    )

    assert response.status_code == 201
    assert response.json()["role"] == "qa_lead"
    assert response.json()["is_active"] is True


def test_admin_created_email_is_lowercased_like_login():
    """Login lowercases before looking up, so an address stored with the
    capitalisation the admin typed produced an account that could never
    authenticate.

    EmailStr already lowercases the domain but preserves the local part, so
    the local part is where the bug actually bit. Surrounding whitespace is
    unreachable here (EmailStr 422s first), but the endpoint strips anyway to
    stay identical to /register.
    """
    response, db = _create_user(
        {
            "email": "Admin@Local.com",
            "full_name": "Admin",
            "password": _COMPLIANT_PASSWORD,
            "role": "qa_lead",
            "is_superuser": False,
        }
    )

    assert response.status_code == 201
    assert db.created_user.email == "admin@local.com"


def test_admin_created_user_must_meet_the_same_password_policy_as_register():
    """Otherwise an admin can mint an account weaker than any user could
    create for themselves."""
    response, db = _create_user(
        {
            "email": "weak@example.com",
            "full_name": "Weak",
            "password": "strongpass123",  # no uppercase, no special character
            "role": "qa_lead",
            "is_superuser": False,
        }
    )

    assert response.status_code == 400
    assert "uppercase" in response.json()["detail"].lower()
    assert db.created_user is None


def test_last_active_admin_cannot_be_deactivated():
    admin = User(
        id=1,
        email="admin@example.com",
        full_name="Platform Admin",
        hashed_password="not-used",
        role="admin",
        is_active=True,
        is_superuser=True,
    )
    db = _UpdateUserDB(target=admin, users=[admin])

    async def fake_db() -> AsyncIterator[_UpdateUserDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _admin_user
    try:
        response = TestClient(app).patch("/api/v1/users/1", json={"is_active": False})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "At least one active platform admin must remain"
