from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.defect import DefectDraft
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.requirement import Requirement
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


class _SequencedDB:
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
    return Project(id=1, owner_id=99, name="RBAC Project")


def _membership(role: str):
    return ProjectMembership(project_id=1, user_id=2, role=role, is_active=True)


def test_tester_cannot_approve_requirement():
    req = Requirement(id=1, project_id=1, title="Requirement", created_by=99)
    db = _SequencedDB(req, _project(), _membership("Tester"))

    async def fake_db() -> AsyncIterator[_SequencedDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).post(
            "/api/v1/requirements/1/approve",
            json={"action": "approve", "notes": "ok"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_viewer_auditor_cannot_generate_automation():
    db = _SequencedDB(_project(), _membership("Viewer/Auditor"))

    async def fake_db() -> AsyncIterator[_SequencedDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).post(
            "/api/v1/automation/agent/generate-scripts",
            json={"project_id": 1, "test_case_ids": [1], "framework": "pytest"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_defect_manager_cannot_view_agent_audit_logs_without_audit_permission():
    db = _SequencedDB(_project(), _membership("Tester"))

    async def fake_db() -> AsyncIterator[_SequencedDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).get("/api/v1/agents/project/1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_tester_cannot_push_defects_to_jira():
    defect = DefectDraft(
        id=1,
        project_id=1,
        defect_id="DF-0001",
        summary="Defect",
        created_by=99,
        status="approved",
    )
    db = _SequencedDB(defect, _project(), _membership("Tester"))

    async def fake_db() -> AsyncIterator[_SequencedDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).post("/api/v1/defects/1/push-to-jira")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
