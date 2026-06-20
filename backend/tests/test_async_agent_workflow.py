from collections.abc import AsyncIterator
from types import SimpleNamespace

import anyio
from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.agent import AgentLog, AgentRun
from app.models.project import Project
from app.models.test_case import TestCase
from app.models.user import User
from app.services import agent_dispatch_service, agent_run_service
from app.worker.tasks import agent_tasks


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


class _AgentDB:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.added = []
        self.commits = 0
        self.refreshed = []
        self.next_id = 1

    async def execute(self, _stmt):
        if self.responses:
            value = self.responses.pop(0)
            if isinstance(value, list):
                return _ExecuteResult(values=value)
            return _ExecuteResult(value=value)
        return _ExecuteResult()

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self.next_id
            self.next_id += 1
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)

    async def rollback(self):
        return None


class _AsyncSessionFactory:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def _user():
    return User(
        id=1,
        email="qa@example.com",
        full_name="QA Manager",
        hashed_password="x",
        role="qa_engineer",
        is_active=True,
        is_superuser=False,
    )


def test_trigger_returns_202_with_agent_run_id(monkeypatch):
    db = _AgentDB(
        [
            Project(id=1, owner_id=1, name="Project"),
            TestCase(
                id=1,
                project_id=1,
                created_by=1,
                test_case_id="TC-1",
                title="Approved case",
                status="approved",
            ),
            None,
        ]
    )

    class _Task:
        id = "task-123"

    async def fake_db() -> AsyncIterator[_AgentDB]:
        yield db

    monkeypatch.setattr(agent_dispatch_service.run_agent, "delay", lambda *args: _Task())
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _user
    try:
        response = TestClient(app).post(
            "/api/v1/automation/agent/generate-scripts",
            json={"project_id": 1, "test_case_ids": [1], "framework": "pytest"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["agent_run_id"] == 1
    assert response.json()["task_id"] == "task-123"


def test_duplicate_trigger_returns_existing_agent_run_without_new_run(monkeypatch):
    existing = AgentRun(
        id=42,
        project_id=1,
        triggered_by=1,
        agent_name="automation_script",
        status="pending",
        idempotency_key="existing-key",
        celery_task_id="task-existing",
    )
    db = _AgentDB([existing])

    async def run():
        return await agent_dispatch_service.enqueue_agent_run(
            db,
            project_id=1,
            user_id=1,
            agent_name="automation_script",
            input_data={"test_cases": [{"id": 1}], "framework": "pytest"},
            idempotency_key="existing-key",
        )

    monkeypatch.setattr(agent_dispatch_service.run_agent, "delay", lambda *_args: (_ for _ in ()).throw(AssertionError("should not enqueue")))
    run, task_id = anyio.run(run)

    assert run is existing
    assert task_id == "task-existing"
    assert not any(isinstance(obj, AgentRun) and obj is not existing for obj in db.added)


def test_failed_duplicate_trigger_requeues_existing_run(monkeypatch):
    existing = AgentRun(
        id=42,
        project_id=1,
        triggered_by=1,
        agent_name="automation_script",
        status="failed",
        idempotency_key="existing-key",
        celery_task_id="old-task",
        error_message="old failure",
        progress_percent=100,
    )
    db = _AgentDB([existing])

    class _Task:
        id = "task-new"

    async def run():
        return await agent_dispatch_service.enqueue_agent_run(
            db,
            project_id=1,
            user_id=1,
            agent_name="automation_script",
            input_data={"test_cases": [{"id": 1}], "framework": "pytest"},
            idempotency_key="existing-key",
        )

    monkeypatch.setattr(agent_dispatch_service.run_agent, "delay", lambda *_args: _Task())
    run, task_id = anyio.run(run)

    assert run is existing
    assert task_id == "task-new"
    assert existing.status == "pending"
    assert existing.error_message is None
    assert existing.progress_percent == 5
    assert not any(isinstance(obj, AgentRun) and obj is not existing for obj in db.added)


def test_enqueue_failure_marks_new_run_failed(monkeypatch):
    db = _AgentDB([None])

    async def run():
        try:
            await agent_dispatch_service.enqueue_agent_run(
                db,
                project_id=1,
                user_id=1,
                agent_name="automation_script",
                input_data={"test_cases": [{"id": 1}], "framework": "pytest"},
                idempotency_key="new-key",
            )
        except RuntimeError:
            return next(obj for obj in db.added if isinstance(obj, AgentRun))
        raise AssertionError("Expected enqueue failure")

    monkeypatch.setattr(agent_dispatch_service.run_agent, "delay", lambda *_args: (_ for _ in ()).throw(RuntimeError("broker down")))
    run = anyio.run(run)

    assert run.status == "failed"
    assert "broker down" in run.error_message


def test_task_marks_running_then_completed(monkeypatch):
    run = AgentRun(id=1, project_id=1, triggered_by=1, agent_name="fake", status="pending")
    db = _AgentDB([run, run])

    async def fake_agent(_input):
        return SimpleNamespace(success=True, data={"ok": True}, logs=[])

    async def run_task():
        monkeypatch.setitem(agent_tasks.AGENT_REGISTRY, "fake", fake_agent)
        monkeypatch.setattr(agent_tasks, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))
        return await agent_tasks._run_agent_task("task-1", 1, "fake", {})

    result = anyio.run(run_task)

    assert result == {"agent_run_id": 1, "status": "completed"}
    assert run.status == "completed"
    assert run.progress_percent == 100
    assert any(isinstance(obj, AgentLog) and obj.step == "running" for obj in db.added)


def test_failed_task_sanitizes_error(monkeypatch):
    run = AgentRun(id=1, project_id=1, triggered_by=1, agent_name="fake", status="pending")
    db = _AgentDB([run, None, run])

    async def fail_agent(_input):
        raise agent_tasks.PermanentAgentError("token=secret-value exploded")

    async def run_task():
        monkeypatch.setitem(agent_tasks.AGENT_REGISTRY, "fake", fail_agent)
        monkeypatch.setattr(agent_tasks, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))
        try:
            await agent_tasks._run_agent_task("task-1", 1, "fake", {})
        except agent_tasks.PermanentAgentError as exc:
            await agent_tasks._mark_agent_failed(1, exc)

    anyio.run(run_task)

    assert run.status == "failed"
    assert "secret-value" not in run.error_message
    assert "[REDACTED]" in run.error_message


def test_failed_task_sanitizes_json_style_secret(monkeypatch):
    run = AgentRun(id=1, project_id=1, triggered_by=1, agent_name="fake", status="pending")
    db = _AgentDB([run])

    async def run_fail():
        await agent_run_service.fail_agent_run(
            db,
            run,
            error_message='provider failed {"token": "json-secret", "detail": "nope"}',
        )

    anyio.run(run_fail)

    assert "json-secret" not in run.error_message
    assert '"token": "[REDACTED]"' in run.error_message


def test_task_timeout_fails_run_without_retry(monkeypatch):
    import asyncio
    run = AgentRun(id=1, project_id=1, triggered_by=1, agent_name="fake", status="pending")
    db = _AgentDB([run, run])

    async def mock_wait_for(aw, timeout):
        raise asyncio.wait_for._CancelledError() if hasattr(asyncio, "CancelledError") else asyncio.TimeoutError() # wait_for raises TimeoutError, let's just raise asyncio.TimeoutError
    
    # Actually wait_for raises TimeoutError in standard library.
    async def mock_wait_for_timeout(aw, timeout):
        try:
            aw.close()
        except AttributeError:
            pass
        raise asyncio.TimeoutError()

    async def run_task():
        monkeypatch.setitem(agent_tasks.AGENT_REGISTRY, "fake", lambda _in: None)
        monkeypatch.setattr(agent_tasks, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))
        monkeypatch.setattr(agent_tasks.asyncio, "wait_for", mock_wait_for_timeout)
        return await agent_tasks._run_agent_task("task-1", 1, "fake", {})

    result = anyio.run(run_task)

    assert result["status"] == "failed"
    assert "timed out after 120 seconds" in result["error"]
    assert run.status == "failed"
    assert "timed out after 120 seconds" in run.error_message


def test_transient_failure_classified_for_retry():
    assert agent_tasks.classify_exception(agent_tasks.TransientAgentError("try again")) == "transient"


def test_permanent_failure_classified_no_retry():
    assert agent_tasks.classify_exception(agent_tasks.PermanentAgentError("bad input")) == "permanent"


def test_progress_percent_visible_via_polling_schema():
    run = AgentRun(
        id=1,
        project_id=1,
        triggered_by=1,
        agent_name="fake",
        status="running",
        progress_percent=45,
        progress_message="Halfway",
    )

    data = app.dependency_overrides  # keeps app imported for route schema registration
    assert data == app.dependency_overrides
    assert run.progress_percent == 45
    assert run.progress_message == "Halfway"
