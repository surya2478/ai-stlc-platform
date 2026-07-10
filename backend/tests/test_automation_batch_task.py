"""Edge cases and negative cases for the `run_automation_batch` Celery task
(app.worker.tasks.automation_tasks._execute_batch) added for "Run All
Eligible". Filesystem/subprocess side effects (workspace, script runner) are
stubbed out — these tests exercise the orchestration logic only: sequential
processing, per-script isolation, missing-script handling, and the run-level
status roll-up rules.
"""
from types import SimpleNamespace

import anyio

from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult, ExecutionRun
from app.services.automation_runner import PerTestResult, RunnerResult
import app.worker.tasks.automation_tasks as automation_tasks_module
from app.worker.tasks.automation_tasks import _execute_batch, _execute_run


class _ScalarsResult:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return self._items


class _ExecResult:
    def __init__(self, *, single=None, many=None):
        self._single = single
        self._many = many if many is not None else []

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return _ScalarsResult(self._many)


class _TaskDB:
    """Fake AsyncSession for the whole lifetime of one `_execute_batch` call."""

    def __init__(self, run, scripts_by_id, placeholders, test_cases_by_id=None):
        self.run = run
        self.scripts_by_id = scripts_by_id
        self.placeholders = list(placeholders)
        self.test_cases_by_id = test_cases_by_id or {}
        self.added = []
        self.next_id = 5000
        self.commits = 0

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self.next_id
            self.next_id += 1
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def get(self, model, object_id):
        if model is ExecutionRun:
            return self.run if object_id == self.run.id else None
        if model is AutomationScript:
            return self.scripts_by_id.get(object_id)
        # TestCase (or anything else) — used for the last_automation_status rollup.
        return self.test_cases_by_id.get(object_id)

    async def execute(self, _stmt):
        return _ExecResult(many=self.placeholders)


class _AsyncSessionFactory:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _script(script_id, **overrides):
    defaults = dict(
        id=script_id,
        project_id=1,
        test_case_id=None,
        created_by=1,
        script_id=f"AS-{script_id:04d}",
        framework="pytest",  # sidesteps Playwright base-URL resolution entirely
        file_path="tests/test_example.py",
        code="def test_example(): assert True",
        status="approved",
    )
    defaults.update(overrides)
    return AutomationScript(**defaults)


def _placeholder(pk, script_id, **overrides):
    defaults = dict(
        id=pk,
        execution_run_id=99,
        project_id=1,
        test_name=f"AS-{script_id:04d}",
        status="pending",
        metadata_={"automation_script_id": script_id},
    )
    defaults.update(overrides)
    return ExecutionResult(**defaults)


def _batch_run(script_ids, run_id=99):
    return ExecutionRun(
        id=run_id,
        project_id=1,
        execution_id=f"ER-{run_id:04d}",
        suite_name="Test Batch",
        environment="staging",
        status="queued",
        execution_type="automation",
        source_type="automation_local_batch",
        total_tests=len(script_ids),
        passed=0,
        failed=0,
        skipped=0,
        execution_logs=[],
        metadata_={
            "source_type": "automation_local_batch",
            "automation_script_ids": script_ids,
            "timeout_seconds": 600,
        },
    )


def _passing_result(name="test_example"):
    return RunnerResult(
        run_status="completed",
        results=[PerTestResult(name=name, status="pass", duration_ms=120)],
        duration_seconds=0.5,
        log_path=None,
    )


def _failing_result(name="test_example", message="AssertionError"):
    return RunnerResult(
        run_status="completed",  # runner itself worked fine — the *test* failed
        results=[PerTestResult(name=name, status="fail", duration_ms=80, error_message=message)],
        duration_seconds=0.4,
        log_path=None,
    )


def _crashed_result(message="npx: command not found"):
    return RunnerResult(
        run_status="failed",
        results=[],
        duration_seconds=0.1,
        log_path=None,
        error_message=message,
    )


def _stub_filesystem_layer(monkeypatch, tmp_path):
    monkeypatch.setattr(automation_tasks_module, "reset_workspace", lambda key: tmp_path / str(key))
    monkeypatch.setattr(automation_tasks_module, "write_pytest_config", lambda workspace: None)
    monkeypatch.setattr(automation_tasks_module, "write_playwright_config", lambda workspace, base_url=None: None)
    monkeypatch.setattr(
        automation_tasks_module, "materialize_script",
        lambda *, workspace, framework, code, suggested_file_path: "test_example.py",
    )


def _run_batch(db, execution_run_id, timeout_seconds=600):
    async def _go():
        return await _execute_batch(execution_run_id, timeout_seconds)

    return anyio.run(_go)


# ── Negative / boundary cases needing no filesystem stubs ───────────────────

def test_execute_batch_returns_skipped_when_run_missing(monkeypatch):
    db = _TaskDB(run=None, scripts_by_id={}, placeholders=[])
    db.run = None  # simulate ExecutionRun row deleted/never existed

    class _NoRunDB(_TaskDB):
        async def get(self, model, object_id):
            return None

    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(_NoRunDB(None, {}, [])))
    result = _run_batch(None, execution_run_id=999)
    assert result == {"status": "skipped", "reason": "execution_run not found"}


def test_execute_batch_fails_fast_when_script_ids_missing(monkeypatch):
    run = _batch_run(script_ids=[])
    run.metadata_ = {"source_type": "automation_local_batch"}  # no automation_script_ids key at all
    db = _TaskDB(run=run, scripts_by_id={}, placeholders=[])
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    result = _run_batch(db, execution_run_id=99)

    assert result == {"status": "failed", "reason": "missing automation_script_ids"}
    assert run.status == "failed"
    assert "error" in run.metadata_
    assert db.commits == 1


# ── Orchestration happy paths ────────────────────────────────────────────────

def test_execute_batch_all_scripts_pass(monkeypatch, tmp_path):
    _stub_filesystem_layer(monkeypatch, tmp_path)
    results_queue = [_passing_result(), _passing_result()]
    monkeypatch.setattr(
        automation_tasks_module, "run_script_for_execution",
        _queue_runner(results_queue),
    )

    run = _batch_run(script_ids=[1, 2])
    scripts = {1: _script(1), 2: _script(2)}
    placeholders = [_placeholder(1, 1), _placeholder(2, 2)]
    db = _TaskDB(run=run, scripts_by_id=scripts, placeholders=placeholders)
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    result = _run_batch(db, execution_run_id=99)

    assert result["status"] == "completed"
    assert result["passed"] == 2
    assert result["failed"] == 0
    assert run.status == "completed"
    assert run.total_tests == 2
    assert all(p.status == "pass" for p in placeholders)


def test_execute_batch_mixed_pass_fail_still_completed(monkeypatch, tmp_path):
    """A failing *test* is not a runner crash — the batch should still report
    'completed' so the frontend derives pass/fail from the counts, matching
    the same convention as the single-script runner."""
    _stub_filesystem_layer(monkeypatch, tmp_path)
    monkeypatch.setattr(
        automation_tasks_module, "run_script_for_execution",
        _queue_runner([_passing_result(), _failing_result(message="assert 1 == 2")]),
    )

    run = _batch_run(script_ids=[1, 2])
    scripts = {1: _script(1), 2: _script(2)}
    placeholders = [_placeholder(1, 1), _placeholder(2, 2)]
    db = _TaskDB(run=run, scripts_by_id=scripts, placeholders=placeholders)
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    result = _run_batch(db, execution_run_id=99)

    assert result["status"] == "completed"
    assert result["passed"] == 1
    assert result["failed"] == 1
    assert placeholders[0].status == "pass"
    assert placeholders[1].status == "fail"
    assert placeholders[1].error_message == "assert 1 == 2"


def test_execute_batch_missing_script_continues_to_next(monkeypatch, tmp_path):
    """A script deleted between being queued and the worker picking it up
    must not abort the whole batch — later scripts still run."""
    _stub_filesystem_layer(monkeypatch, tmp_path)
    monkeypatch.setattr(
        automation_tasks_module, "run_script_for_execution",
        _queue_runner([_passing_result()]),  # only script 2 ever reaches the runner
    )

    run = _batch_run(script_ids=[1, 2])
    scripts = {2: _script(2)}  # script 1 is "gone"
    placeholders = [_placeholder(10, 1), _placeholder(11, 2)]
    db = _TaskDB(run=run, scripts_by_id=scripts, placeholders=placeholders)
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    result = _run_batch(db, execution_run_id=99)

    assert result["status"] == "completed"  # script 2 still succeeded
    assert placeholders[0].status == "fail"
    assert "deleted" in placeholders[0].error_message.lower()
    assert placeholders[1].status == "pass"
    assert result["passed"] == 1
    assert result["failed"] == 1


def test_execute_batch_all_runners_crash_marks_run_failed(monkeypatch, tmp_path):
    """If every script's subprocess runner itself fails to start (not just a
    failing test), the batch run should be marked 'failed', not 'completed'."""
    _stub_filesystem_layer(monkeypatch, tmp_path)
    monkeypatch.setattr(
        automation_tasks_module, "run_script_for_execution",
        _queue_runner([_crashed_result(), _crashed_result()]),
    )

    run = _batch_run(script_ids=[1, 2])
    scripts = {1: _script(1), 2: _script(2)}
    placeholders = [_placeholder(1, 1), _placeholder(2, 2)]
    db = _TaskDB(run=run, scripts_by_id=scripts, placeholders=placeholders)
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    result = _run_batch(db, execution_run_id=99)

    assert result["status"] == "failed"
    assert run.status == "failed"
    # Both placeholders should carry the crash message rather than being
    # silently marked "skip", since a crash is not a pass/fail verdict.
    assert all(p.status == "fail" for p in placeholders)
    assert all("npx" in (p.error_message or "") for p in placeholders)


def test_execute_batch_one_crash_one_success_marks_run_completed(monkeypatch, tmp_path):
    _stub_filesystem_layer(monkeypatch, tmp_path)
    monkeypatch.setattr(
        automation_tasks_module, "run_script_for_execution",
        _queue_runner([_crashed_result(), _passing_result()]),
    )

    run = _batch_run(script_ids=[1, 2])
    scripts = {1: _script(1), 2: _script(2)}
    placeholders = [_placeholder(1, 1), _placeholder(2, 2)]
    db = _TaskDB(run=run, scripts_by_id=scripts, placeholders=placeholders)
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    result = _run_batch(db, execution_run_id=99)

    assert result["status"] == "completed"  # at least one script actually ran
    assert placeholders[0].status == "fail"  # the crashed one
    assert placeholders[1].status == "pass"


def test_execute_batch_commits_progress_after_each_script(monkeypatch, tmp_path):
    """Verifies the "live progress" claim: the run row is committed after
    every script, not only once at the very end."""
    _stub_filesystem_layer(monkeypatch, tmp_path)
    monkeypatch.setattr(
        automation_tasks_module, "run_script_for_execution",
        _queue_runner([_passing_result(), _passing_result(), _passing_result()]),
    )

    run = _batch_run(script_ids=[1, 2, 3])
    scripts = {1: _script(1), 2: _script(2), 3: _script(3)}
    placeholders = [_placeholder(1, 1), _placeholder(2, 2), _placeholder(3, 3)]
    db = _TaskDB(run=run, scripts_by_id=scripts, placeholders=placeholders)
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    _run_batch(db, execution_run_id=99)

    # 1 commit to flip to "running" + 3 per-script commits + 1 final commit.
    assert db.commits == 5


def test_execute_batch_rolls_up_last_automation_status_onto_linked_test_case(monkeypatch, tmp_path):
    _stub_filesystem_layer(monkeypatch, tmp_path)
    monkeypatch.setattr(
        automation_tasks_module, "run_script_for_execution",
        _queue_runner([_failing_result(message="boom")]),
    )

    class _FakeTestCase:
        id = 77
        last_execution_run_id = None
        last_automation_status = None
        last_automation_run_at = None
        latest_evidence_available = None

    tc = _FakeTestCase()
    run = _batch_run(script_ids=[1])
    scripts = {1: _script(1, test_case_id=77)}
    placeholders = [_placeholder(1, 1, test_case_id=77)]
    db = _TaskDB(run=run, scripts_by_id=scripts, placeholders=placeholders, test_cases_by_id={77: tc})
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    _run_batch(db, execution_run_id=99)

    assert tc.last_automation_status == "fail"
    assert tc.last_execution_run_id == 99
    assert tc.latest_evidence_available is True  # error_message was set


def test_execute_batch_records_real_lifecycle_stages(monkeypatch, tmp_path):
    """Locks in the Execution Monitor stepper's data contract: a real
    preflight runtime check (not fabricated pass/fail), then running,
    finalizing, and a terminal stage — each with an actual timestamp, in
    chronological order."""
    _stub_filesystem_layer(monkeypatch, tmp_path)
    monkeypatch.setattr(automation_tasks_module, "run_script_for_execution", _queue_runner([_passing_result()]))
    monkeypatch.setattr(
        automation_tasks_module, "runtime_status",
        lambda: {
            "playwright": SimpleNamespace(available=False, detail="npx not found"),
            "pytest": SimpleNamespace(available=True, detail="pytest 8.0"),
        },
    )

    run = _batch_run(script_ids=[1])
    scripts = {1: _script(1)}
    placeholders = [_placeholder(1, 1)]
    db = _TaskDB(run=run, scripts_by_id=scripts, placeholders=placeholders)
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    _run_batch(db, execution_run_id=99)

    stages = run.metadata_["stages"]
    assert [s["stage"] for s in stages] == ["preflight", "running", "finalizing", "completed"]
    assert stages[0]["runner_availability"] == {"playwright": False, "pytest": True}
    timestamps = [s["at"] for s in stages]
    assert timestamps == sorted(timestamps)  # strictly non-decreasing, real clock time


def test_execute_run_records_real_lifecycle_stages(monkeypatch, tmp_path):
    """Same stage contract for the single-script task, so the frontend
    stepper renders identically for both entry points."""
    _stub_filesystem_layer(monkeypatch, tmp_path)
    monkeypatch.setattr(automation_tasks_module, "run_script_for_execution", _queue_runner([_failing_result()]))
    monkeypatch.setattr(
        automation_tasks_module, "runtime_status",
        lambda: {"pytest": SimpleNamespace(available=True, detail="pytest 8.0")},
    )

    run = ExecutionRun(
        id=200, project_id=1, execution_id="ER-0200", environment="staging",
        status="queued", execution_type="automation", source_type="automation_local",
        total_tests=1, passed=0, failed=0, skipped=0, execution_logs=[],
        metadata_={"source_type": "automation_local", "automation_script_id": 1},
    )
    script = _script(1)
    placeholder = _placeholder(1, 1)
    db = _TaskDB(run=run, scripts_by_id={1: script}, placeholders=[placeholder])
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    async def _go():
        return await _execute_run(200, 600)

    result = anyio.run(_go)

    assert result["status"] == "completed"
    stages = run.metadata_["stages"]
    assert [s["stage"] for s in stages] == ["preflight", "running", "finalizing", "completed"]
    assert stages[0]["runner_availability"] == {"pytest": True}


def _queue_runner(results):
    queue = list(results)

    async def _fake_run_script_for_execution(**_kwargs):
        return queue.pop(0)

    return _fake_run_script_for_execution


# ── failure classification wiring: real executions never went through the
# dry-run chain's failure_classification agent — confirm both task entry
# points now call it whenever there's an actual failure, and skip the call
# entirely when everything passed. ────────────────────────────────────────

def test_execute_batch_classifies_failures_when_present(monkeypatch, tmp_path):
    _stub_filesystem_layer(monkeypatch, tmp_path)
    monkeypatch.setattr(
        automation_tasks_module, "run_script_for_execution",
        _queue_runner([_passing_result(), _failing_result(message="assert 1 == 2")]),
    )
    calls = []

    async def _fake_classify(_db, *, execution_run_id):
        calls.append(execution_run_id)
        return 1
    monkeypatch.setattr(automation_tasks_module.automation_service, "classify_failed_results", _fake_classify)

    run = _batch_run(script_ids=[1, 2])
    scripts = {1: _script(1), 2: _script(2)}
    placeholders = [_placeholder(1, 1), _placeholder(2, 2)]
    db = _TaskDB(run=run, scripts_by_id=scripts, placeholders=placeholders)
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    _run_batch(db, execution_run_id=99)

    assert calls == [99]


def test_execute_batch_skips_classification_when_everything_passed(monkeypatch, tmp_path):
    _stub_filesystem_layer(monkeypatch, tmp_path)
    monkeypatch.setattr(
        automation_tasks_module, "run_script_for_execution",
        _queue_runner([_passing_result(), _passing_result()]),
    )
    calls = []

    async def _fake_classify(_db, *, execution_run_id):
        calls.append(execution_run_id)
        return 0
    monkeypatch.setattr(automation_tasks_module.automation_service, "classify_failed_results", _fake_classify)

    run = _batch_run(script_ids=[1, 2])
    scripts = {1: _script(1), 2: _script(2)}
    placeholders = [_placeholder(1, 1), _placeholder(2, 2)]
    db = _TaskDB(run=run, scripts_by_id=scripts, placeholders=placeholders)
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    _run_batch(db, execution_run_id=99)

    assert calls == []


def test_execute_run_classifies_failures_when_present(monkeypatch, tmp_path):
    _stub_filesystem_layer(monkeypatch, tmp_path)
    monkeypatch.setattr(automation_tasks_module, "run_script_for_execution", _queue_runner([_failing_result()]))
    monkeypatch.setattr(
        automation_tasks_module, "runtime_status",
        lambda: {"pytest": SimpleNamespace(available=True, detail="pytest 8.0")},
    )
    calls = []

    async def _fake_classify(_db, *, execution_run_id):
        calls.append(execution_run_id)
        return 1
    monkeypatch.setattr(automation_tasks_module.automation_service, "classify_failed_results", _fake_classify)

    run = ExecutionRun(
        id=200, project_id=1, execution_id="ER-0200", environment="staging",
        status="queued", execution_type="automation", source_type="automation_local",
        total_tests=1, passed=0, failed=0, skipped=0, execution_logs=[],
        metadata_={"source_type": "automation_local", "automation_script_id": 1},
    )
    script = _script(1)
    placeholder = _placeholder(1, 1)
    db = _TaskDB(run=run, scripts_by_id={1: script}, placeholders=[placeholder])
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    async def _go():
        return await _execute_run(200, 600)

    anyio.run(_go)

    assert calls == [200]
