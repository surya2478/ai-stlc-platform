"""Wave 2: suite execution stability.

Three defects are covered.

1. Cancel and Emergency Stop were read only at dispatch boundaries, so a test
   that had already started kept running for up to the full item timeout after
   an operator asked for it to stop (AUT-013). Runners now race a cancellation
   signal and terminate the process.

2. The worker held a database session open across `dispatch_item`, which can
   occupy ITEM_TIMEOUT_SECONDS. Dispatch is now split so the execution phase
   holds nothing.

3. Items left in STARTING/RUNNING by a worker that died were never closed out,
   so the command center polled a spinning test against a finished run.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import app.worker.tasks.suite_execution_tasks as worker_mod
from app.services.automation_runner.base import await_process
from app.services.automation_runner.local_playwright import LocalPlaywrightRunner
from app.services.automation_runner.local_pytest import LocalPytestRunner
from app.services.execution_command_center.orchestrator import ItemExecutionPlan


class _FakeStream:
    def __init__(self, payload: bytes = b""):
        self._chunks = [payload] if payload else []

    async def read(self, _n):
        return self._chunks.pop(0) if self._chunks else b""


class _FakeProc:
    """A process that runs until killed, like a browser test mid-flight."""

    def __init__(self, returncode=0, hang=True):
        self.stdout = _FakeStream()
        self.returncode = returncode
        self._hang = hang
        self.killed = False

    async def wait(self):
        while self._hang:
            await asyncio.sleep(0.01)
        return self.returncode

    def kill(self):
        self.killed = True
        self._hang = False


# ── await_process ───────────────────────────────────────────────────────────


def test_await_process_reports_a_normal_exit():
    proc = _FakeProc(hang=False)
    assert asyncio.run(await_process(proc, timeout_seconds=5)) == "exited"


def test_await_process_reports_cancellation():
    async def _go():
        proc = _FakeProc()
        cancellation = asyncio.Event()
        waiter = asyncio.create_task(
            await_process(proc, timeout_seconds=30, cancellation=cancellation)
        )
        await asyncio.sleep(0.05)
        cancellation.set()
        return await waiter

    assert asyncio.run(_go()) == "cancelled"


def test_await_process_reports_a_timeout():
    proc = _FakeProc()
    assert asyncio.run(await_process(proc, timeout_seconds=0.05)) == "timeout"


def test_a_process_that_exits_wins_over_a_simultaneous_cancel():
    """A real result is better evidence than an abandoned one."""

    async def _go():
        proc = _FakeProc(hang=False)
        cancellation = asyncio.Event()
        cancellation.set()
        return await await_process(proc, timeout_seconds=5, cancellation=cancellation)

    assert asyncio.run(_go()) == "exited"


# ── Runners honour the signal ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "runner_cls, script",
    [(LocalPlaywrightRunner, "specs/x.spec.ts"), (LocalPytestRunner, "test_x.py")],
)
def test_runner_terminates_the_process_and_reports_cancelled(
    runner_cls, script, monkeypatch, tmp_path
):
    proc = _FakeProc()
    monkeypatch.setattr(
        "app.services.automation_runner.preflight.is_available", lambda _f: (True, "ok")
    )
    for mod in (
        "app.services.automation_runner.local_playwright",
        "app.services.automation_runner.local_pytest",
    ):
        monkeypatch.setattr(f"{mod}.is_available", lambda _f: (True, "ok"))

    async def fake_exec(*_cmd, **_kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    async def _go():
        cancellation = asyncio.Event()
        task = asyncio.create_task(
            runner_cls().run(
                workspace_dir=tmp_path,
                script_file_name=script,
                execution_command=None,
                environment="SIT",
                timeout_seconds=30,
                cancellation=cancellation,
            )
        )
        await asyncio.sleep(0.05)
        cancellation.set()
        return await task

    result = asyncio.run(_go())

    assert result.run_status == "cancelled"
    assert result.results == []
    assert "cancelled" in result.error_message
    assert result.metadata["cancelled"] is True
    # The whole point: the process is gone, not merely abandoned.
    assert proc.killed


# ── Plan gating ─────────────────────────────────────────────────────────────


def test_a_blocked_plan_is_not_runnable():
    plan = ItemExecutionPlan(item_id=1, blocked_reason="no compiled bundle")
    assert not plan.runnable


def test_a_plan_without_a_workspace_is_not_runnable():
    """Guards against a prepare phase that returned early without saying why."""
    assert not ItemExecutionPlan(item_id=1, framework="playwright").runnable


def test_a_resolved_plan_is_runnable(tmp_path):
    plan = ItemExecutionPlan(
        item_id=1,
        framework="playwright",
        workspace=Path(tmp_path),
        script_file="specs/x.spec.ts",
    )
    assert plan.runnable


# ── The in-item control watcher ─────────────────────────────────────────────


class _FakeRun:
    def __init__(self, command=None):
        self.pending_command = command


class _FakeSession:
    """Enough of AsyncSession for the watcher's two statements."""

    def __init__(self, run):
        self._run = run

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def execute(self, _stmt):
        return None

    async def get(self, _model, _pk):
        return self._run

    async def commit(self):
        return None


def _install_fake_session(monkeypatch, run):
    monkeypatch.setattr(worker_mod, "AsyncSessionLocal", lambda: _FakeSession(run))
    monkeypatch.setattr(worker_mod, "CONTROL_POLL_SECONDS", 0.01)


def test_watcher_cancels_a_running_item_when_the_control_arrives(monkeypatch, tmp_path):
    """The behaviour the command center's Cancel button always claimed."""
    run = _FakeRun(command=None)
    _install_fake_session(monkeypatch, run)

    observed = {}

    async def fake_execute_plan(plan, *, cancellation=None):
        observed["had_signal"] = cancellation is not None
        run.pending_command = "CANCEL_NOW"
        await asyncio.wait_for(cancellation.wait(), timeout=2)
        return type(
            "R", (), {"run_status": "cancelled", "metadata": {}, "error_message": "x"}
        )()

    monkeypatch.setattr(worker_mod.orchestrator, "execute_plan", fake_execute_plan)
    monkeypatch.setattr(
        worker_mod.orchestrator, "touch_heartbeat", lambda *_a, **_k: _noop()
    )

    plan = ItemExecutionPlan(item_id=7, workspace=Path(tmp_path), script_file="x")
    result, cancelled = asyncio.run(worker_mod._execute_with_controls(1, 7, plan))

    assert observed["had_signal"]
    assert cancelled
    assert result.run_status == "cancelled"


def test_watcher_leaves_an_uninterrupted_item_alone(monkeypatch, tmp_path):
    run = _FakeRun(command=None)
    _install_fake_session(monkeypatch, run)

    async def fake_execute_plan(plan, *, cancellation=None):
        await asyncio.sleep(0.05)
        assert not cancellation.is_set()
        return type("R", (), {"run_status": "completed", "metadata": {}})()

    monkeypatch.setattr(worker_mod.orchestrator, "execute_plan", fake_execute_plan)
    monkeypatch.setattr(
        worker_mod.orchestrator, "touch_heartbeat", lambda *_a, **_k: _noop()
    )

    plan = ItemExecutionPlan(item_id=7, workspace=Path(tmp_path), script_file="x")
    _result, cancelled = asyncio.run(worker_mod._execute_with_controls(1, 7, plan))
    assert not cancelled


def test_pause_does_not_interrupt_a_running_item(monkeypatch, tmp_path):
    """Pause stays a boundary control by design: stopping mid-test would leave
    the application under test in an unknown state."""
    run = _FakeRun(command="PAUSE_AFTER_CURRENT")
    _install_fake_session(monkeypatch, run)

    async def fake_execute_plan(plan, *, cancellation=None):
        await asyncio.sleep(0.05)
        assert not cancellation.is_set()
        return type("R", (), {"run_status": "completed", "metadata": {}})()

    monkeypatch.setattr(worker_mod.orchestrator, "execute_plan", fake_execute_plan)
    monkeypatch.setattr(
        worker_mod.orchestrator, "touch_heartbeat", lambda *_a, **_k: _noop()
    )

    plan = ItemExecutionPlan(item_id=7, workspace=Path(tmp_path), script_file="x")
    _result, cancelled = asyncio.run(worker_mod._execute_with_controls(1, 7, plan))
    assert not cancelled


async def _noop():
    return None


# ── Stranded item reconciliation ────────────────────────────────────────────


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _ReconcileSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _ExecResult(self._rows)


def test_stranded_items_are_closed_out_with_a_recovery_reason(monkeypatch):
    """A worker that died leaves no verdict. Saying so is the only honest
    option — leaving the row RUNNING made the UI spin forever."""
    from app.models.execution_command_center import ExecutionRunItem
    from app.services.execution_command_center import orchestrator

    running = ExecutionRunItem(lifecycle_state="RUNNING", result="PENDING")
    running.id = 11
    starting = ExecutionRunItem(lifecycle_state="STARTING", result="PENDING")
    starting.id = 12

    monkeypatch.setattr(orchestrator, "_recount_item", lambda *_a, **_k: _noop())
    monkeypatch.setattr(orchestrator, "_recount_evidence", lambda *_a, **_k: _noop())
    monkeypatch.setattr(orchestrator.events, "emit", lambda *_a, **_k: _noop())

    run = type("Run", (), {"id": 1})()
    count = asyncio.run(
        orchestrator.reconcile_stranded_items(
            _ReconcileSession([running, starting]), run, reason="worker died"
        )
    )

    assert count == 2
    for item in (running, starting):
        assert item.lifecycle_state == "COMPLETED"
        assert item.result == "AUTOMATION_FAILURE"
        assert item.attention_reason == "worker died"
        assert item.completed_at is not None
        # The lease is released, so a later sweep cannot re-reconcile it.
        assert item.heartbeat_at is None


def test_reconciliation_is_a_no_op_when_nothing_is_in_flight(monkeypatch):
    from app.services.execution_command_center import orchestrator

    monkeypatch.setattr(orchestrator, "_recount_evidence", lambda *_a, **_k: _noop())
    run = type("Run", (), {"id": 1})()
    assert (
        asyncio.run(
            orchestrator.reconcile_stranded_items(
                _ReconcileSession([]), run, reason="worker died"
            )
        )
        == 0
    )
