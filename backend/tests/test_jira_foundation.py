from collections.abc import AsyncIterator
from typing import Any

import anyio
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.jira_connection import JiraConnection
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.requirement import Requirement
from app.models.user import User
from app.schemas.jira import JiraFetchIssuesRequest, JiraImportRequirementsRequest
from app.services.jira_service import (
    JiraService,
    build_jql,
    decrypt_credential,
    encrypt_credential,
)


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


class _JiraImportDB:
    def __init__(self):
        self.requirements: dict[tuple[int, str], Requirement] = {}
        self.next_id = 1

    async def execute(self, stmt):
        where_text = str(stmt.whereclause)
        if "requirements" in where_text:
            params = stmt.compile().params
            project_id = params.get("project_id_1")
            requirement_id = params.get("requirement_id_1")
            return _ExecuteResult(self.requirements.get((project_id, requirement_id)))
        return _ExecuteResult()

    def add(self, obj):
        if isinstance(obj, Requirement):
            obj.id = self.next_id
            self.next_id += 1
            self.requirements[(obj.project_id, obj.requirement_id)] = obj

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None

    async def rollback(self):
        return None


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


def _connection() -> JiraConnection:
    return JiraConnection(
        id=1,
        project_id=1,
        created_by=1,
        jira_base_url="https://example.atlassian.net",
        jira_email="qa@example.com",
        jira_api_token_encrypted=encrypt_credential("jira-token"),
        jira_project_key="STLC",
        is_active=True,
        status="connected",
    )


def _inactive_connection() -> JiraConnection:
    connection = _connection()
    connection.is_active = False
    return connection


def _issue(key: str, summary: str = "Login requirement") -> dict[str, Any]:
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "description": {"content": [{"content": [{"type": "text", "text": "As a user I can log in"}]}]},
            "issuetype": {"name": "Story"},
            "status": {"name": "To Do"},
            "priority": {"name": "High"},
            "labels": ["auth"],
            "updated": "2026-06-10T08:00:00.000+0000",
        },
    }


def test_jira_credential_encryption_round_trip():
    encrypted = encrypt_credential("super-secret-token")

    assert encrypted != "super-secret-token"
    assert decrypt_credential(encrypted) == "super-secret-token"


def test_jira_test_connection_success_and_failure():
    async def run():
        connection = _connection()

        success_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={"accountId": "abc123", "displayName": "QA User"},
                )
            )
        )
        success = await JiraService(_JiraImportDB(), success_client).test_connection(connection)
        await success_client.aclose()

        failure_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    401,
                    json={"errorMessages": ["Unauthorized"]},
                )
            )
        )
        failure = await JiraService(_JiraImportDB(), failure_client).test_connection(connection)
        await failure_client.aclose()
        return success, failure, connection

    success, failure, connection = anyio.run(run)

    assert success.success is True
    assert success.account_id == "abc123"
    assert failure.success is False
    assert "Jira authentication failed" in failure.message
    assert connection.metadata_["last_test_error"] == failure.message


def test_fetch_issues_applies_all_filter_types():
    body = JiraFetchIssuesRequest(
        issue_types=["Story", "Bug"],
        statuses=["To Do"],
        priorities=["High"],
        labels=["auth"],
        assignee="qa@example.com",
        text="login",
        updated_since="2026-06-01",
        jql="component = Web",
    )

    jql = build_jql("STLC", body)

    assert 'project = "STLC"' in jql
    assert 'issuetype in ("Story", "Bug")' in jql
    assert 'status in ("To Do")' in jql
    assert 'priority in ("High")' in jql
    assert 'labels in ("auth")' in jql
    assert 'assignee = "qa@example.com"' in jql
    assert 'text ~ "login"' in jql
    assert 'updated >= "2026-06-01"' in jql
    assert "(component = Web)" in jql


def test_raw_jql_order_by_replaces_default_ordering():
    body = JiraFetchIssuesRequest(jql="component = Web ORDER BY priority DESC")

    jql = build_jql("STLC", body)

    assert jql == 'project = "STLC" AND (component = Web) ORDER BY priority DESC'
    assert jql.lower().count("order by") == 1


def test_fetch_issues_returns_paginated_mocked_results():
    captured = []

    async def run():
        def handler(request: httpx.Request) -> httpx.Response:
            captured.append((request.url.path, dict(request.url.params)))
            if len(captured) == 1:
                return httpx.Response(
                    200,
                    json={"issues": [_issue("STLC-0")], "isLast": False, "nextPageToken": "token-2"},
                )
            return httpx.Response(
                200,
                json={"issues": [_issue("STLC-1")], "isLast": True},
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        result = await JiraService(_JiraImportDB(), client).fetch_issues(
            _connection(),
            JiraFetchIssuesRequest(statuses=["To Do"], page=2, page_size=25),
        )
        await client.aclose()
        return result

    result = anyio.run(run)

    assert captured[0][0] == "/rest/api/3/search/jql"
    assert "startAt" not in captured[0][1]
    assert captured[0][1]["maxResults"] == "25"
    assert 'status in ("To Do")' in captured[0][1]["jql"]
    assert captured[1][1]["nextPageToken"] == "token-2"
    assert result.total == 26
    assert result.items[0].key == "STLC-1"


def test_fetch_issues_rejects_inactive_connection_before_http_call():
    called = False

    async def run():
        nonlocal called

        def handler(_request: httpx.Request) -> httpx.Response:
            called = True
            return httpx.Response(200, json={"total": 0, "issues": []})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            await JiraService(_JiraImportDB(), client).fetch_issues(
                _inactive_connection(),
                JiraFetchIssuesRequest(),
            )
        except HTTPException as exc:
            await client.aclose()
            return exc
        await client.aclose()
        return None

    exc = anyio.run(run)

    assert called is False
    assert exc is not None
    assert exc.status_code == 409


def test_import_requirements_is_idempotent_when_run_twice():
    async def run():
        db = _JiraImportDB()

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"total": 1, "issues": [_issue("STLC-1")]})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = JiraService(db, client)
        first = await service.import_requirements(_connection(), JiraImportRequirementsRequest(), user_id=1)
        second = await service.import_requirements(_connection(), JiraImportRequirementsRequest(), user_id=1)
        await client.aclose()
        return first, second, db

    first, second, db = anyio.run(run)

    assert first.created == 1
    assert second.created == 0
    assert second.updated == 1
    assert len(db.requirements) == 1
    requirement = next(iter(db.requirements.values()))
    # An import enters the governed workflow at intake, not part-way through
    # its review. This asserted "pending_review" from before that workflow
    # existed, and kept asserting it after ae06528 introduced intake — so it
    # described a promotion the service had deliberately stopped doing.
    assert requirement.status == "draft"
    assert requirement.readiness_status == "intake_ready"
    assert (requirement.metadata_ or {}).get("workflow_stage") == "intake"


def test_import_requirements_leaves_an_existing_draft_at_intake():
    """Re-importing refreshes the issue's fields; it does not advance the
    requirement's stage. Promotion is the reviewer's action, and the governed
    transitions are covered in test_requirement_workflow.py."""
    async def run():
        db = _JiraImportDB()
        existing = Requirement(
            id=1,
            project_id=1,
            created_by=1,
            requirement_id="STLC-1",
            source="jira",
            title="Old draft",
            status="draft",
        )
        db.requirements[(1, "STLC-1")] = existing

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"issues": [_issue("STLC-1")]})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        result = await JiraService(db, client).import_requirements(_connection(), JiraImportRequirementsRequest(), user_id=1)
        await client.aclose()
        return result, existing

    result, existing = anyio.run(run)

    assert result.updated == 1
    assert existing.status == "draft"
    assert existing.readiness_status == "intake_ready"


def test_import_requirements_uses_search_jql_next_page_token():
    captured = []

    async def run():
        db = _JiraImportDB()

        def handler(request: httpx.Request) -> httpx.Response:
            params = dict(request.url.params)
            captured.append((request.url.path, params))
            if len(captured) == 1:
                return httpx.Response(
                    200,
                    json={"issues": [_issue("STLC-1")], "isLast": False, "nextPageToken": "token-2"},
                )
            return httpx.Response(
                200,
                json={"issues": [_issue("STLC-2")], "isLast": True},
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        result = await JiraService(db, client).import_requirements(
            _connection(),
            JiraImportRequirementsRequest(batch_size=1, max_issues=5),
            user_id=1,
        )
        await client.aclose()
        return result

    result = anyio.run(run)

    assert result.imported == 2
    assert captured[0][0] == "/rest/api/3/search/jql"
    assert "startAt" not in captured[0][1]
    assert captured[1][1]["nextPageToken"] == "token-2"


def test_import_requirements_deduplicates_repeated_issue_keys_in_same_batch():
    async def run():
        db = _JiraImportDB()

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"total": 2, "issues": [_issue("STLC-1"), _issue("STLC-1", "Updated duplicate")]},
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        result = await JiraService(db, client).import_requirements(
            _connection(),
            JiraImportRequirementsRequest(),
            user_id=1,
        )
        await client.aclose()
        return result, db

    result, db = anyio.run(run)

    assert result.imported == 1
    assert result.created == 1
    assert result.updated == 0
    assert len(db.requirements) == 1


def test_import_requirements_truncates_jira_fields_to_database_limits():
    async def run():
        db = _JiraImportDB()
        long_key = "STLC-" + ("1" * 200)
        long_summary = "S" * 700

        def handler(_request: httpx.Request) -> httpx.Response:
            issue = _issue(long_key, long_summary)
            issue["fields"]["issuetype"]["name"] = "T" * 200
            issue["fields"]["priority"]["name"] = "P" * 200
            return httpx.Response(200, json={"total": 1, "issues": [issue]})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await JiraService(db, client).import_requirements(_connection(), JiraImportRequirementsRequest(), user_id=1)
        await client.aclose()
        return next(iter(db.requirements.values()))

    requirement = anyio.run(run)

    assert len(requirement.requirement_id) == 100
    assert len(requirement.title) == 500
    assert len(requirement.jira_issue_type) == 100
    assert len(requirement.jira_priority) == 50


def test_fetch_issues_non_json_response_marks_connection_error():
    async def run():
        connection = _connection()
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, text="<html>oops</html>"))
        )
        try:
            await JiraService(_JiraImportDB(), client).fetch_issues(connection, JiraFetchIssuesRequest())
        except HTTPException as exc:
            await client.aclose()
            return connection, exc
        await client.aclose()
        return connection, None

    connection, exc = anyio.run(run)

    assert exc is not None
    assert exc.status_code == 502
    assert connection.status == "error"


def test_concurrent_import_of_same_issue_does_not_create_duplicates():
    async def run():
        db = _JiraImportDB()

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"total": 1, "issues": [_issue("STLC-1")]})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = JiraService(db, client)
        async with anyio.create_task_group() as tg:
            tg.start_soon(service.import_requirements, _connection(), JiraImportRequirementsRequest(), 1)
            tg.start_soon(service.import_requirements, _connection(), JiraImportRequirementsRequest(), 1)
        await client.aclose()
        return db

    db = anyio.run(run)

    assert len(db.requirements) == 1


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


def test_jira_endpoint_requires_sync_jira_permission():
    db = _SequencedDB(
        _connection(),
        Project(id=1, owner_id=99, name="RBAC Project"),
        ProjectMembership(project_id=1, user_id=2, role="Tester", is_active=True),
    )

    async def fake_db() -> AsyncIterator[_SequencedDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _member_user
    try:
        response = TestClient(app).post("/api/v1/jira/connections/1/test")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
