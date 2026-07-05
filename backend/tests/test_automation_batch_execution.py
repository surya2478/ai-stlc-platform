"""Edge cases and negative cases for the "Run All Eligible" batch execute
endpoint and the best-effort Cancel Run endpoint added for Phase 1/3.

Follows the fake-DB + dependency_overrides pattern established in
test_execution_flow.py — no real database or Celery broker required.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.project import Project
from app.models.user import User
from app.services.rbac_service import EXECUTE_TESTS
import app.worker.tasks.automation_tasks as automation_tasks_module


# ── Shared fakes ─────────────────────────────────────────────────────────────

class _ScalarsResult:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return self._items


class _ExecResult:
    """Stands in for the SQLAlchemy Result object returned by db.execute()."""

    def __init__(self, *, single=None, many=None):
        self._single = single
        self._many = many if many is not None else []

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return _ScalarsResult(self._many)

    def all(self):
        return self._many


class _FakeDB:
    """Minimal async-session stand-in.

    - `get_map` backs `db.get(Model, id)` lookups (pre-seeded rows).
    - `execute_queue` backs `db.execute(stmt)` calls, popped in the exact
      order the endpoint under test issues them.
    - `db.add()` auto-assigns incrementing ids (mirroring flush-assigned PKs)
      and registers the row into `get_map` so later `db.get()` calls resolve.
    """

    def __init__(self, get_map=None, execute_queue=None):
        self.get_map = dict(get_map or {})
        self.execute_queue = list(execute_queue or [])
        self.added = []
        self.next_id = 1000
        self.commits = 0

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self.next_id
            self.next_id += 1
        self.added.append(obj)
        self.get_map[(type(obj), obj.id)] = obj

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def execute(self, _stmt):
        return self.execute_queue.pop(0)


async def _owner_user():
    return User(
        id=1,
        email="owner@example.com",
        full_name="Owner",
        hashed_password="x",
        role="qa_engineer",
        is_active=True,
        is_superuser=False,
    )


def _override(db):
    async def fake_db():
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _owner_user


def _clear():
    app.dependency_overrides.clear()


def _project():
    return Project(id=1, owner_id=1, name="Project")


def _script(**overrides):
    defaults = dict(
        id=1,
        project_id=1,
        test_case_id=10,
        created_by=1,
        script_id="AS-0001",
        framework="playwright",
        file_path="tests/example.spec.ts",
        code="import { test } from '@playwright/test';",
        status="approved",
    )
    defaults.update(overrides)
    return AutomationScript(**defaults)


def _no_op_delay(monkeypatch, task_id="celery-task-abc"):
    """Prevent the endpoint's `.delay(...)` call from touching a real broker."""
    monkeypatch.setattr(
        automation_tasks_module.run_automation_batch,
        "delay",
        lambda *args, **kwargs: SimpleNamespace(id=task_id),
    )


BATCH_URL = "/api/v1/automation/project/1/execute-batch"


# ── execute-batch: request validation (no DB reached) ───────────────────────

def test_batch_execute_rejects_empty_script_id_list():
    _override(_FakeDB())
    try:
        response = TestClient(app).post(BATCH_URL, json={"script_ids": []})
    finally:
        _clear()
    assert response.status_code == 422


def test_batch_execute_rejects_over_max_script_ids():
    _override(_FakeDB())
    try:
        response = TestClient(app).post(BATCH_URL, json={"script_ids": list(range(1, 202))})
    finally:
        _clear()
    assert response.status_code == 422


def test_batch_execute_rejects_timeout_out_of_bounds():
    _override(_FakeDB())
    try:
        response = TestClient(app).post(BATCH_URL, json={"script_ids": [1], "timeout_seconds": 5})
    finally:
        _clear()
    assert response.status_code == 422


# ── execute-batch: negative cases past validation ───────────────────────────

def test_batch_execute_rejects_missing_scripts():
    db = _FakeDB(execute_queue=[
        _ExecResult(single=_project()),
        _ExecResult(many=[_script(id=1)]),  # id=2 requested but not returned
    ])
    _override(db)
    try:
        response = TestClient(app).post(BATCH_URL, json={"script_ids": [1, 2]})
    finally:
        _clear()
    assert response.status_code == 404
    assert "2" in response.json()["detail"]


def test_batch_execute_rejects_scripts_from_another_project():
    other_project_script = _script(id=1, project_id=99, script_id="AS-9999")
    db = _FakeDB(execute_queue=[
        _ExecResult(single=_project()),
        _ExecResult(many=[other_project_script]),
    ])
    _override(db)
    try:
        response = TestClient(app).post(BATCH_URL, json={"script_ids": [1]})
    finally:
        _clear()
    assert response.status_code == 422
    assert "AS-9999" in response.json()["detail"]


def test_batch_execute_rejects_unapproved_scripts():
    draft_script = _script(id=1, status="draft")
    db = _FakeDB(execute_queue=[
        _ExecResult(single=_project()),
        _ExecResult(many=[draft_script]),
    ])
    _override(db)
    try:
        response = TestClient(app).post(BATCH_URL, json={"script_ids": [1]})
    finally:
        _clear()
    assert response.status_code == 422
    assert "approved" in response.json()["detail"].lower()


def test_batch_execute_rejects_unsupported_framework():
    selenium_script = _script(id=1, framework="selenium")
    db = _FakeDB(execute_queue=[
        _ExecResult(single=_project()),
        _ExecResult(many=[selenium_script]),
    ])
    _override(db)
    try:
        response = TestClient(app).post(BATCH_URL, json={"script_ids": [1]})
    finally:
        _clear()
    assert response.status_code == 422
    assert "not supported" in response.json()["detail"].lower()


def test_batch_execute_mixed_valid_and_invalid_scripts_reports_only_bad_ones():
    good = _script(id=1, status="approved")
    rejected = _script(id=2, status="rejected", script_id="AS-0002")
    db = _FakeDB(execute_queue=[
        _ExecResult(single=_project()),
        _ExecResult(many=[good, rejected]),
    ])
    _override(db)
    try:
        response = TestClient(app).post(BATCH_URL, json={"script_ids": [1, 2]})
    finally:
        _clear()
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "AS-0002" in detail
    assert "AS-0001" not in detail


def test_batch_execute_rejects_when_not_project_owner_or_member():
    async def _other_user():
        return User(
            id=2,
            email="other@example.com",
            full_name="Other",
            hashed_password="x",
            role="qa_engineer",
            is_active=True,
            is_superuser=False,
        )

    db = _FakeDB(execute_queue=[
        _ExecResult(single=_project()),  # owner_id=1, current_user.id=2
        _ExecResult(single=None),  # no active ProjectMembership for user 2 either
    ])

    async def fake_db():
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _other_user
    try:
        response = TestClient(app).post(BATCH_URL, json={"script_ids": [1]})
    finally:
        _clear()
    assert response.status_code == 403


# ── execute-batch: success + edge cases ──────────────────────────────────────

def test_batch_execute_dedupes_repeated_script_ids(monkeypatch):
    _no_op_delay(monkeypatch)
    script = _script(id=1)
    db = _FakeDB(execute_queue=[
        _ExecResult(single=_project()),
        _ExecResult(many=[script]),
    ])
    _override(db)
    try:
        response = TestClient(app).post(BATCH_URL, json={"script_ids": [1, 1, 1]})
    finally:
        _clear()

    assert response.status_code == 202
    body = response.json()
    assert body["script_count"] == 1

    run = next(o for o in db.added if isinstance(o, ExecutionRun))
    placeholders = [o for o in db.added if isinstance(o, ExecutionResult)]
    assert run.total_tests == 1
    assert len(placeholders) == 1  # not 3 — duplicate ids must not fan out placeholders


def test_batch_execute_success_persists_run_and_placeholders(monkeypatch):
    _no_op_delay(monkeypatch, task_id="celery-xyz")
    scripts = [_script(id=1, script_id="AS-0001"), _script(id=2, script_id="AS-0002", framework="pytest")]
    db = _FakeDB(execute_queue=[
        _ExecResult(single=_project()),
        _ExecResult(many=scripts),
    ])
    _override(db)
    try:
        response = TestClient(app).post(
            BATCH_URL,
            json={"script_ids": [1, 2], "environment": "qa", "run_name": "Smoke_Regression_QA"},
        )
    finally:
        _clear()

    assert response.status_code == 202
    body = response.json()
    assert body["script_count"] == 2
    assert body["task_id"] == "celery-xyz"

    run = next(o for o in db.added if isinstance(o, ExecutionRun))
    assert run.suite_name == "Smoke_Regression_QA"
    assert run.total_tests == 2
    assert run.status == "queued"
    assert run.metadata_["automation_script_ids"] == [1, 2]
    assert run.metadata_["parent_run_id"] is None
    # task_id is persisted onto the run for a later Cancel Run to revoke it.
    assert run.metadata_["task_id"] == "celery-xyz"

    placeholders = [o for o in db.added if isinstance(o, ExecutionResult)]
    assert {p.metadata_["automation_script_id"] for p in placeholders} == {1, 2}
    assert all(p.status == "pending" for p in placeholders)
    assert db.commits >= 2  # initial commit + task_id persistence commit


def test_batch_execute_records_parent_run_id_for_retry(monkeypatch):
    _no_op_delay(monkeypatch)
    script = _script(id=1)
    db = _FakeDB(execute_queue=[
        _ExecResult(single=_project()),
        _ExecResult(many=[script]),
    ])
    _override(db)
    try:
        response = TestClient(app).post(BATCH_URL, json={"script_ids": [1], "parent_run_id": 42})
    finally:
        _clear()

    assert response.status_code == 202
    run = next(o for o in db.added if isinstance(o, ExecutionRun))
    assert run.metadata_["parent_run_id"] == 42


def test_batch_execute_accepts_scripts_previously_executed_not_just_approved(monkeypatch):
    _no_op_delay(monkeypatch)
    script = _script(id=1, status="executed")
    db = _FakeDB(execute_queue=[
        _ExecResult(single=_project()),
        _ExecResult(many=[script]),
    ])
    _override(db)
    try:
        response = TestClient(app).post(BATCH_URL, json={"script_ids": [1]})
    finally:
        _clear()
    assert response.status_code == 202


# ── cancel run: negative cases ───────────────────────────────────────────────

def test_cancel_run_rejects_unknown_run():
    db = _FakeDB()
    _override(db)
    try:
        response = TestClient(app).post("/api/v1/automation/runs/999/cancel")
    finally:
        _clear()
    assert response.status_code == 404


def test_cancel_run_rejects_non_local_runner_run():
    run = ExecutionRun(
        id=5, project_id=1, execution_id="ER-0005", status="running",
        execution_type="automation", total_tests=1, passed=0, failed=0, skipped=0,
        metadata_={"source_type": "external"},
    )
    db = _FakeDB(
        get_map={(ExecutionRun, 5): run},
        execute_queue=[_ExecResult(single=_project())],
    )
    _override(db)
    try:
        response = TestClient(app).post("/api/v1/automation/runs/5/cancel")
    finally:
        _clear()
    assert response.status_code == 422
    assert "local-runner" in response.json()["detail"].lower()


def test_cancel_run_rejects_run_missing_source_type_metadata():
    run = ExecutionRun(
        id=6, project_id=1, execution_id="ER-0006", status="running",
        execution_type="automation", total_tests=1, passed=0, failed=0, skipped=0,
        metadata_=None,
    )
    db = _FakeDB(
        get_map={(ExecutionRun, 6): run},
        execute_queue=[_ExecResult(single=_project())],
    )
    _override(db)
    try:
        response = TestClient(app).post("/api/v1/automation/runs/6/cancel")
    finally:
        _clear()
    assert response.status_code == 422


@pytest.mark.parametrize("terminal_status", ["completed", "failed", "cancelled"])
def test_cancel_run_rejects_already_terminal_run(terminal_status):
    run = ExecutionRun(
        id=7, project_id=1, execution_id="ER-0007", status=terminal_status,
        execution_type="automation", total_tests=1, passed=1, failed=0, skipped=0,
        metadata_={"source_type": "automation_local_batch"},
    )
    db = _FakeDB(
        get_map={(ExecutionRun, 7): run},
        execute_queue=[_ExecResult(single=_project())],
    )
    _override(db)
    try:
        response = TestClient(app).post("/api/v1/automation/runs/7/cancel")
    finally:
        _clear()
    assert response.status_code == 422
    assert "already" in response.json()["detail"].lower()


def test_cancel_run_rejects_cross_project_caller():
    async def _other_user():
        return User(
            id=2, email="other@example.com", full_name="Other", hashed_password="x",
            role="qa_engineer", is_active=True, is_superuser=False,
        )

    run = ExecutionRun(
        id=8, project_id=1, execution_id="ER-0008", status="running",
        execution_type="automation", total_tests=1, passed=0, failed=0, skipped=0,
        metadata_={"source_type": "automation_local_batch"},
    )
    db = _FakeDB(
        get_map={(ExecutionRun, 8): run},
        execute_queue=[
            _ExecResult(single=_project()),  # owner_id=1
            _ExecResult(single=None),  # no active ProjectMembership for user 2 either
        ],
    )

    async def fake_db():
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _other_user
    try:
        response = TestClient(app).post("/api/v1/automation/runs/8/cancel")
    finally:
        _clear()
    assert response.status_code == 403


# ── cancel run: success + edge cases ─────────────────────────────────────────

def test_cancel_run_revokes_task_and_skips_pending_results(monkeypatch):
    revoked = {}

    class _FakeControl:
        def revoke(self, task_id, terminate=False):
            revoked["task_id"] = task_id
            revoked["terminate"] = terminate

    monkeypatch.setattr(
        automation_tasks_module.celery_app, "control", _FakeControl(), raising=False,
    )

    run = ExecutionRun(
        id=9, project_id=1, execution_id="ER-0009", status="running",
        execution_type="automation", total_tests=2, passed=0, failed=0, skipped=0,
        metadata_={"source_type": "automation_local_batch", "task_id": "celery-live-task"},
    )
    pending_1 = ExecutionResult(id=100, execution_run_id=9, project_id=1, test_name="AS-0001", status="pending")
    pending_2 = ExecutionResult(id=101, execution_run_id=9, project_id=1, test_name="AS-0002", status="running")
    db = _FakeDB(
        get_map={(ExecutionRun, 9): run},
        execute_queue=[
            _ExecResult(single=_project()),
            _ExecResult(many=[pending_1, pending_2]),
        ],
    )
    _override(db)
    try:
        response = TestClient(app).post("/api/v1/automation/runs/9/cancel")
    finally:
        _clear()

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert run.status == "cancelled"
    assert pending_1.status == "skip"
    assert pending_2.status == "skip"
    assert pending_1.error_message == "Cancelled before this test ran."
    assert revoked == {"task_id": "celery-live-task", "terminate": True}
    assert run.metadata_["cancelled_by"] == 1


def test_cancel_run_succeeds_without_a_persisted_task_id(monkeypatch):
    """Older/legacy runs (or runs cancelled before the worker ever got the
    task id back) shouldn't crash the cancel flow — just skip the revoke."""
    def _should_not_be_called(*_a, **_k):
        raise AssertionError("revoke should not be called when there's no task_id")

    monkeypatch.setattr(
        automation_tasks_module.celery_app.control, "revoke", _should_not_be_called,
    )

    run = ExecutionRun(
        id=10, project_id=1, execution_id="ER-0010", status="queued",
        execution_type="automation", total_tests=1, passed=0, failed=0, skipped=0,
        metadata_={"source_type": "automation_local"},  # no task_id key at all
    )
    db = _FakeDB(
        get_map={(ExecutionRun, 10): run},
        execute_queue=[_ExecResult(single=_project()), _ExecResult(many=[])],
    )
    _override(db)
    try:
        response = TestClient(app).post("/api/v1/automation/runs/10/cancel")
    finally:
        _clear()

    assert response.status_code == 200
    assert run.status == "cancelled"


def test_cancel_run_tolerates_broker_failure_during_revoke(monkeypatch):
    """A broker/network hiccup on revoke must not block marking the run
    cancelled in the DB — cancellation is best-effort."""
    class _FlakyControl:
        def revoke(self, *_a, **_k):
            raise ConnectionError("broker unreachable")

    monkeypatch.setattr(automation_tasks_module.celery_app, "control", _FlakyControl(), raising=False)

    run = ExecutionRun(
        id=11, project_id=1, execution_id="ER-0011", status="running",
        execution_type="automation", total_tests=1, passed=0, failed=0, skipped=0,
        metadata_={"source_type": "automation_local_batch", "task_id": "task-1"},
    )
    db = _FakeDB(
        get_map={(ExecutionRun, 11): run},
        execute_queue=[_ExecResult(single=_project()), _ExecResult(many=[])],
    )
    _override(db)
    try:
        response = TestClient(app).post("/api/v1/automation/runs/11/cancel")
    finally:
        _clear()

    assert response.status_code == 200
    assert run.status == "cancelled"
