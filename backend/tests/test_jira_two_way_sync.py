from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
from typing import Any

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.api.v1.endpoints import jira as jira_endpoint
from app.database import get_db
from app.main import app
from app.models.jira_connection import JiraConnection
from app.models.jira_sync import ConflictRecord, JiraSyncHistory, WebhookEvent
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.requirement import Requirement
from app.models.user import User
from app.schemas.jira import JiraSyncTriggerRequest
from app.services.jira_service import JiraService, encrypt_credential, webhook_event_key


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


class _JiraSyncDB:
    def __init__(self, connection: JiraConnection | None = None):
        self.connection = connection or _connection()
        self.requirements: dict[tuple[int, str], Requirement] = {}
        self.conflicts: dict[tuple[int, str, str], ConflictRecord] = {}
        self.webhook_events: dict[str, WebhookEvent] = {}
        self.histories: dict[int, JiraSyncHistory] = {}
        self.commit_count = 0
        self.rollback_count = 0
        self.next_id = 1

    async def execute(self, stmt):
        text = str(stmt)
        params = stmt.compile().params
        if "jira_connections" in text:
            return _ExecuteResult(self.connection)
        if "requirements" in text:
            project_id = params.get("project_id_1")
            requirement_id = params.get("requirement_id_1")
            if requirement_id is not None:
                return _ExecuteResult(self.requirements.get((project_id, requirement_id)))
            return _ExecuteResult(values=list(self.requirements.values()))
        if "conflict_records" in text:
            connection_id = params.get("connection_id_1")
            jira_issue_key = params.get("jira_issue_key_1")
            status = params.get("status_1")
            return _ExecuteResult(self.conflicts.get((connection_id, jira_issue_key, status)))
        if "webhook_events" in text:
            event_id = params.get("id_1")
            event_key = params.get("event_key_1")
            if event_key is not None:
                return _ExecuteResult(self.webhook_events.get(event_key))
            for event in self.webhook_events.values():
                if event.id == event_id:
                    return _ExecuteResult(event)
            return _ExecuteResult()
        if "jira_sync_history" in text:
            return _ExecuteResult(self.histories.get(params.get("id_1")))
        if "projects" in text:
            return _ExecuteResult(Project(id=1, owner_id=99, name="Project"))
        if "project_memberships" in text:
            return _ExecuteResult(ProjectMembership(project_id=1, user_id=2, role="QA Manager", is_active=True))
        return _ExecuteResult()

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self.next_id
            self.next_id += 1
        if isinstance(obj, Requirement):
            self.requirements[(obj.project_id, obj.requirement_id)] = obj
        elif isinstance(obj, ConflictRecord):
            self.conflicts[(obj.connection_id, obj.jira_issue_key, obj.status)] = obj
        elif isinstance(obj, WebhookEvent):
            self.webhook_events[obj.event_key] = obj
        elif isinstance(obj, JiraSyncHistory):
            self.histories[obj.id] = obj

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None

    async def commit(self):
        self.commit_count += 1
        return None

    async def rollback(self):
        self.rollback_count += 1
        return None


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


def _issue(key: str, summary: str = "Login requirement", updated: str = "2026-06-10T08:00:00.000+0000") -> dict[str, Any]:
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "description": {"content": [{"content": [{"type": "text", "text": "As a user I can log in"}]}]},
            "issuetype": {"name": "Story"},
            "status": {"name": "To Do"},
            "priority": {"name": "High"},
            "labels": ["auth"],
            "updated": updated,
        },
    }


def _search_client(*issues: dict[str, Any]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"total": len(issues), "issues": list(issues)}))
    )


def _inactive_connection() -> JiraConnection:
    connection = _connection()
    connection.is_active = False
    return connection


def test_inbound_creates_new_requirement_with_pending_approval_status():
    async def run():
        db = _JiraSyncDB()
        client = _search_client(_issue("STLC-1"))
        history = await JiraService(db, client).sync_inbound(
            db.connection,
            JiraSyncTriggerRequest(),
            user_id=1,
        )
        await client.aclose()
        return db, history

    db, history = anyio.run(run)
    requirement = db.requirements[(1, "STLC-1")]

    assert requirement.status == "pending_approval"
    assert requirement.jira_deleted is False
    assert history.created_count == 1


def test_inbound_is_idempotent_and_updates_existing_requirement_fields():
    async def run():
        db = _JiraSyncDB()
        first_client = _search_client(_issue("STLC-1", "Initial summary"))
        await JiraService(db, first_client).sync_inbound(db.connection, JiraSyncTriggerRequest(), user_id=1)
        await first_client.aclose()
        second_client = _search_client(_issue("STLC-1", "Updated summary"))
        history = await JiraService(db, second_client).sync_inbound(db.connection, JiraSyncTriggerRequest(), user_id=1)
        await second_client.aclose()
        return db, history

    db, history = anyio.run(run)

    assert len(db.requirements) == 1
    assert db.requirements[(1, "STLC-1")].title == "Updated summary"
    assert history.created_count == 0
    assert history.updated_count == 1


def test_deleted_jira_issue_sets_jira_deleted_without_hard_delete():
    async def run():
        db = _JiraSyncDB()
        requirement = Requirement(
            id=10,
            project_id=1,
            created_by=1,
            requirement_id="STLC-1",
            source="jira",
            title="Requirement",
            status="approved",
            jira_deleted=False,
        )
        db.add(requirement)
        await JiraService(db).mark_issue_deleted(db.connection, "STLC-1")
        return db

    db = anyio.run(run)
    requirement = db.requirements[(1, "STLC-1")]

    assert len(db.requirements) == 1
    assert requirement.jira_deleted is True
    assert requirement.status == "pending_approval"


def test_conflict_detection_triggers_on_concurrent_modification():
    synced_at = datetime.now(timezone.utc) - timedelta(hours=2)
    local_updated = datetime.now(timezone.utc) - timedelta(hours=1)
    remote_updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")

    async def run():
        db = _JiraSyncDB()
        requirement = Requirement(
            id=10,
            project_id=1,
            created_by=1,
            requirement_id="STLC-1",
            source="jira",
            title="Local edit",
            status="approved",
            jira_deleted=False,
            jira_last_synced_at=synced_at,
            updated_at=local_updated,
        )
        db.add(requirement)
        client = _search_client(_issue("STLC-1", "Remote edit", remote_updated))
        history = await JiraService(db, client).sync_inbound(db.connection, JiraSyncTriggerRequest(), user_id=1)
        await client.aclose()
        return db, history

    db, history = anyio.run(run)

    assert history.conflict_count == 1
    assert len(db.conflicts) == 1
    assert db.requirements[(1, "STLC-1")].title == "Local edit"


def test_inbound_failure_persists_failed_history_and_error_status(caplog):
    async def run():
        db = _JiraSyncDB()
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(500, json={"errorMessages": ["boom"]}))
        )
        with pytest.raises(Exception):
            await JiraService(db, client).sync_inbound(db.connection, JiraSyncTriggerRequest(), user_id=1)
        await client.aclose()
        return db

    with caplog.at_level(logging.WARNING):
        db = anyio.run(run)
    history = next(iter(db.histories.values()))

    assert history.status == "failed"
    # SEC-051: raw upstream error detail ("boom") must never be persisted or
    # shown to the client — only a sanitized, generic message. The raw
    # detail is still logged server-side for diagnostics.
    assert "boom" not in history.error_message
    assert "Jira service error" in history.error_message
    assert any("boom" in record.message for record in caplog.records)
    assert db.connection.status == "error"


def test_outbound_sync_accepts_jira_204_no_content_response():
    async def run():
        db = _JiraSyncDB()
        requirement = Requirement(
            id=10,
            project_id=1,
            created_by=1,
            requirement_id="STLC-1",
            source="jira",
            title="Local edit",
            summary="Local summary",
            status="approved",
            jira_issue_key="STLC-1",
            jira_deleted=False,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(requirement)
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(204)))
        history = await JiraService(db, client).sync_outbound(db.connection, user_id=1)
        await client.aclose()
        return requirement, history

    requirement, history = anyio.run(run)

    assert history.status == "completed"
    assert history.updated_count == 1
    assert requirement.jira_last_synced_at is not None


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


def test_webhook_receive_valid_signature_returns_200_and_queued(monkeypatch):
    db = _JiraSyncDB()
    payload = {"webhookEvent": "jira:issue_updated", "timestamp": 1, "issue": _issue("STLC-1")}
    raw = json.dumps(payload).encode("utf-8")
    signature = hmac.new(b"secret", raw, hashlib.sha256).hexdigest()
    queued = {}

    class _Task:
        id = "task-123"

    def fake_delay(event_id):
        queued["event_id"] = event_id
        return _Task()

    monkeypatch.setattr(jira_endpoint.settings, "jira_webhook_secret", "secret")
    monkeypatch.setattr(jira_endpoint.process_jira_webhook, "delay", fake_delay)

    async def fake_db() -> AsyncIterator[_JiraSyncDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    try:
        response = TestClient(app).post(
            "/api/v1/jira/connections/1/webhook",
            content=raw,
            headers={"x-jira-signature": f"sha256={signature}", "content-type": "application/json"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["queued"] is True
    assert queued["event_id"] == response.json()["webhook_event_id"]


def test_webhook_receive_duplicate_event_does_not_enqueue_again(monkeypatch):
    db = _JiraSyncDB()
    payload = {"webhookEventId": "evt-duplicate", "webhookEvent": "jira:issue_updated", "issue": _issue("STLC-1")}
    raw = json.dumps(payload).encode("utf-8")
    signature = hmac.new(b"secret", raw, hashlib.sha256).hexdigest()
    queued: list[int] = []

    class _Task:
        id = "task-123"

    def fake_delay(event_id):
        queued.append(event_id)
        return _Task()

    monkeypatch.setattr(jira_endpoint.settings, "jira_webhook_secret", "secret")
    monkeypatch.setattr(jira_endpoint.process_jira_webhook, "delay", fake_delay)

    async def fake_db() -> AsyncIterator[_JiraSyncDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    try:
        first = TestClient(app).post(
            "/api/v1/jira/connections/1/webhook",
            content=raw,
            headers={"x-jira-signature": f"sha256={signature}", "content-type": "application/json"},
        )
        second = TestClient(app).post(
            "/api/v1/jira/connections/1/webhook",
            content=raw,
            headers={"x-jira-signature": f"sha256={signature}", "content-type": "application/json"},
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["queued"] is True
    assert second.json()["queued"] is False
    assert len(queued) == 1


def test_webhook_receive_invalid_signature_returns_401(monkeypatch):
    db = _JiraSyncDB()
    monkeypatch.setattr(jira_endpoint.settings, "jira_webhook_secret", "secret")

    async def fake_db() -> AsyncIterator[_JiraSyncDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    try:
        response = TestClient(app).post(
            "/api/v1/jira/connections/1/webhook",
            json={"webhookEvent": "jira:issue_updated", "issue": _issue("STLC-1")},
            headers={"x-jira-signature": "sha256=bad"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_webhook_deduplication_same_event_key_processed_once():
    async def run():
        db = _JiraSyncDB()
        service = JiraService(db)
        payload = {"webhookEventId": "evt-1", "webhookEvent": "jira:issue_updated", "issue": _issue("STLC-1")}
        first, first_new = await service.persist_webhook_event(db.connection, payload)
        second, second_new = await service.persist_webhook_event(db.connection, payload)
        return first, first_new, second, second_new, db

    first, first_new, second, second_new, db = anyio.run(run)

    assert first_new is True
    assert second_new is False
    assert first.id == second.id
    assert len(db.webhook_events) == 1
    assert first.event_key == webhook_event_key(first.payload)


def test_celery_task_updates_requirement_from_webhook_payload():
    async def run():
        db = _JiraSyncDB()
        requirement = Requirement(
            id=10,
            project_id=1,
            created_by=1,
            requirement_id="STLC-1",
            source="jira",
            title="Old",
            status="draft",
            jira_deleted=False,
        )
        db.add(requirement)
        event = WebhookEvent(
            id=20,
            project_id=1,
            connection_id=1,
            event_key="event-20",
            event_type="jira:issue_updated",
            status="queued",
            payload={"webhookEvent": "jira:issue_updated", "issue": _issue("STLC-1", "New from webhook")},
        )
        db.add(event)
        processed = await JiraService(db).process_webhook_event(event)
        return db, processed

    db, processed = anyio.run(run)

    assert processed.status == "processed"
    assert db.requirements[(1, "STLC-1")].title == "New from webhook"


def test_webhook_processing_rejects_inactive_connection_without_mutation():
    async def run():
        db = _JiraSyncDB(connection=_inactive_connection())
        requirement = Requirement(
            id=10,
            project_id=1,
            created_by=1,
            requirement_id="STLC-1",
            source="jira",
            title="Old",
            status="draft",
            jira_deleted=False,
        )
        db.add(requirement)
        event = WebhookEvent(
            id=20,
            project_id=1,
            connection_id=1,
            event_key="event-20",
            event_type="jira:issue_updated",
            status="queued",
            payload={"webhookEvent": "jira:issue_updated", "issue": _issue("STLC-1", "New from webhook")},
        )
        db.add(event)
        with pytest.raises(Exception):
            await JiraService(db).process_webhook_event(event)
        return db, event

    db, event = anyio.run(run)

    assert event.status == "failed"
    assert db.requirements[(1, "STLC-1")].title == "Old"
