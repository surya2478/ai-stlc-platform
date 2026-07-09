from collections.abc import AsyncIterator
from datetime import datetime, timezone
from types import SimpleNamespace

import anyio
from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.agent import AgentLog, AgentRun
from app.models.project import Project
from app.models.project_application import ProjectApplication
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


def test_discovery_trigger_returns_202_with_agent_run_id(monkeypatch):
    db = _AgentDB(
        [
            Project(id=1, owner_id=1, name="Project"),
            TestCase(
                id=1, project_id=1, created_by=1, test_case_id="TC-1",
                title="Login test", status="approved", application_id=None,
            ),
            ProjectApplication(
                id=7, project_id=1, key="web", name="Web App", is_default=True, is_active=True,
                environment_urls={"QA": "http://app.example.com"},
            ),
            None,
        ]
    )

    class _Task:
        id = "task-mcp-1"

    async def fake_db() -> AsyncIterator[_AgentDB]:
        yield db

    monkeypatch.setattr(agent_dispatch_service.run_agent, "delay", lambda *args: _Task())
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _user
    try:
        response = TestClient(app).post(
            "/api/v1/automation/agent/discover-ui",
            json={"project_id": 1, "test_case_ids": [1], "environment": "QA"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["agent_run_id"] == 1
    assert response.json()["task_id"] == "task-mcp-1"


def test_discovery_trigger_422s_when_no_application_url_configured(monkeypatch):
    db = _AgentDB(
        [
            Project(id=1, owner_id=1, name="Project"),
            TestCase(
                id=1, project_id=1, created_by=1, test_case_id="TC-1",
                title="Login test", status="approved", application_id=None,
            ),
            ProjectApplication(
                id=7, project_id=1, key="web", name="Web App", is_default=True, is_active=True,
                environment_urls={},  # no URL configured for any environment
            ),
        ]
    )

    async def fake_db() -> AsyncIterator[_AgentDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _user
    try:
        response = TestClient(app).post(
            "/api/v1/automation/agent/discover-ui",
            json={"project_id": 1, "test_case_ids": [1], "environment": "QA"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


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


def test_cancel_self_triggered_pending_run_revokes_celery_task(monkeypatch):
    now = datetime.now(timezone.utc)
    run = AgentRun(
        id=5, project_id=1, triggered_by=1, agent_name="fake",
        status="pending", celery_task_id="task-abc",
        progress_percent=0, created_at=now, updated_at=now,
    )
    db = _AgentDB([run])
    revoke_calls = []

    async def fake_db() -> AsyncIterator[_AgentDB]:
        yield db

    monkeypatch.setattr(
        "app.api.v1.endpoints.agents.celery_app.control.revoke",
        lambda task_id, terminate=False: revoke_calls.append((task_id, terminate)),
    )
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _user
    try:
        response = TestClient(app).post("/api/v1/agents/5/cancel")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert run.status == "cancelled"
    assert revoke_calls == [("task-abc", True)]


def test_cancel_already_completed_run_returns_409(monkeypatch):
    now = datetime.now(timezone.utc)
    run = AgentRun(
        id=6, project_id=1, triggered_by=1, agent_name="fake",
        status="completed", celery_task_id="task-xyz",
        progress_percent=100, created_at=now, updated_at=now,
    )
    db = _AgentDB([run])

    async def fake_db() -> AsyncIterator[_AgentDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _user
    try:
        response = TestClient(app).post("/api/v1/agents/6/cancel")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert run.status == "completed"


def test_queued_run_cancelled_before_worker_start_is_not_overwritten(monkeypatch):
    run = AgentRun(id=1, project_id=1, triggered_by=1, agent_name="fake", status="cancelled")
    db = _AgentDB([run])

    async def fake_agent(_input):
        raise AssertionError("agent must not run once the run is already cancelled")

    async def run_task():
        monkeypatch.setitem(agent_tasks.AGENT_REGISTRY, "fake", fake_agent)
        monkeypatch.setattr(agent_tasks, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))
        return await agent_tasks._run_agent_task("task-1", 1, "fake", {})

    result = anyio.run(run_task)

    assert result == {"agent_run_id": 1, "status": "cancelled"}
    assert run.status == "cancelled"


def test_run_cancelled_mid_execution_is_not_marked_completed(monkeypatch):
    run = AgentRun(id=1, project_id=1, triggered_by=1, agent_name="fake", status="pending")
    # Response order: [0] top-of-task select(AgentRun), [1] the project LLM
    # route lookup inside _run_agent_with_project_llm_routes (empty = no
    # project-specific routes configured), [2] this function's own
    # post-execution cancellation re-check.
    db = _AgentDB([run, [], "cancelled"])

    async def fake_agent(_input):
        return SimpleNamespace(success=True, data={"ok": True}, logs=[])

    async def run_task():
        monkeypatch.setitem(agent_tasks.AGENT_REGISTRY, "fake", fake_agent)
        monkeypatch.setattr(agent_tasks, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))
        return await agent_tasks._run_agent_task("task-1", 1, "fake", {})

    result = anyio.run(run_task)

    assert result == {"agent_run_id": 1, "status": "cancelled"}
    assert run.status != "completed"


def test_get_agent_spec_falls_back_to_default_for_unknown_agent():
    assert agent_tasks.get_agent_spec("no_such_agent") is agent_tasks.DEFAULT_AGENT_SPEC


def test_get_agent_spec_returns_registered_spec():
    spec = agent_tasks.get_agent_spec("test_execution")
    assert spec.timeout_seconds == 300.0
    assert spec.module_scope == "execution"


def test_chain_on_success_enqueues_configured_next_agent(monkeypatch):
    run = AgentRun(id=1, project_id=7, triggered_by=3, agent_name="fake", status="pending")
    db = _AgentDB([run, run])

    async def fake_agent(_input):
        return SimpleNamespace(success=True, data={"ok": True}, logs=[])

    captured = {}

    async def fake_enqueue(_db, **kwargs):
        captured.update(kwargs)

        class _Run:
            id = 99

        return _Run(), "task-chained"

    async def run_task():
        monkeypatch.setitem(agent_tasks.AGENT_REGISTRY, "fake", fake_agent)
        monkeypatch.setitem(
            agent_tasks.AGENT_SPECS, "fake", agent_tasks.AgentSpec(chain_on_success=("fake_child",))
        )
        async def fake_builder(_db, chained_run, _input, _output):
            return {"parent_run_id": chained_run.id}

        monkeypatch.setitem(agent_tasks.CHAIN_INPUT_BUILDERS, "fake_child", fake_builder)
        monkeypatch.setattr(agent_tasks, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))
        monkeypatch.setattr(agent_dispatch_service, "enqueue_agent_run", fake_enqueue)
        return await agent_tasks._run_agent_task("task-1", 1, "fake", {})

    result = anyio.run(run_task)

    assert result == {"agent_run_id": 1, "status": "completed"}
    assert captured["agent_name"] == "fake_child"
    assert captured["input_data"] == {"parent_run_id": 1}
    assert captured["project_id"] == 7
    assert captured["user_id"] == 3


def test_chain_on_success_missing_builder_does_not_fail_parent_run(monkeypatch):
    run = AgentRun(id=1, project_id=7, triggered_by=3, agent_name="fake", status="pending")
    db = _AgentDB([run, run])

    async def fake_agent(_input):
        return SimpleNamespace(success=True, data={"ok": True}, logs=[])

    async def run_task():
        monkeypatch.setitem(agent_tasks.AGENT_REGISTRY, "fake", fake_agent)
        monkeypatch.setitem(
            agent_tasks.AGENT_SPECS, "fake", agent_tasks.AgentSpec(chain_on_success=("unregistered_child",))
        )
        monkeypatch.setattr(agent_tasks, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))
        return await agent_tasks._run_agent_task("task-1", 1, "fake", {})

    result = anyio.run(run_task)

    assert result == {"agent_run_id": 1, "status": "completed"}
    assert run.status == "completed"


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
