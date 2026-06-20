import pytest
from datetime import datetime
from collections.abc import AsyncIterator
import httpx
from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.defect import DefectDraft
from app.models.jira_connection import JiraConnection
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.user import User
from app.services.jira_service import encrypt_credential


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
        role="qa_lead",
        is_active=True,
        is_superuser=False,
    )


def _defect_draft():
    return DefectDraft(
        id=5,
        project_id=1,
        created_by=2,
        defect_id="DEF-0005",
        summary="eSIM activation failing",
        description="Fails consistently at step 3",
        status="approved",
    )


def _connection():
    return JiraConnection(
        id=1,
        project_id=1,
        created_by=2,
        jira_base_url="https://example.atlassian.net",
        jira_email="qa@example.com",
        jira_api_token_encrypted=encrypt_credential("jira-token"),
        jira_project_key="STLC",
        is_active=True,
        status="connected",
    )


def test_push_defect_no_jira_connection_fails():
    # Setup DB to return:
    # 1. DefectDraft (defect_service.get_defect)
    # 2. Project (require_project_access)
    # 3. ProjectMembership (require_project_access check)
    # 4. ProjectMembership (user_permissions_for_project check - role must have PUSH_DEFECTS_TO_JIRA permission, like "QA Manager")
    # 5. None (JiraConnection lookup)
    db = _SequencedDB(
        _defect_draft(),
        Project(id=1, owner_id=99, name="Test Project"),
        ProjectMembership(project_id=1, user_id=2, role="QA Manager", is_active=True),
        ProjectMembership(project_id=1, user_id=2, role="QA Manager", is_active=True),
        None,
    )

    async def fake_db() -> AsyncIterator[_SequencedDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).post("/api/v1/defects/5/push-to-jira")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "No active Jira connection configured" in response.json()["detail"]
