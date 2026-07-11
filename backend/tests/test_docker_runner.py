"""M2 (Playwright AI Studio): DockerPlaywrightRunner, runner-mode dispatch,
and the parallel batch-execution path. Docker/subprocess side effects are
stubbed — the real container flow is exercised live against the compose
deployment (see plan M5)."""
import asyncio
import json
from types import SimpleNamespace

import anyio

import app.services.automation_runner.docker_playwright as docker_mod
import app.worker.tasks.automation_tasks as automation_tasks_module
from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult, ExecutionRun
from app.services.automation_runner.base import PerTestResult, RunnerResult
from app.services.automation_runner.dispatcher import get_runner_for_framework
from app.services.automation_runner.docker_playwright import DockerPlaywrightRunner
from app.services.automation_runner.local_playwright import LocalPlaywrightRunner
from app.services.automation_runner.local_pytest import LocalPytestRunner
from app.worker.tasks.automation_tasks import _execute_batch


# ── Dispatcher: runner-mode selection ────────────────────────────────────────

def test_dispatcher_selects_docker_runner_for_playwright():
    runner = get_runner_for_framework("playwright", "docker")
    assert isinstance(runner, DockerPlaywrightRunner)


def test_dispatcher_defaults_to_local_runner():
    assert isinstance(get_runner_for_framework("playwright"), LocalPlaywrightRunner)
    assert not isinstance(get_runner_for_framework("playwright", "local"), DockerPlaywrightRunner)


def test_dispatcher_docker_pytest_falls_back_to_local():
    assert isinstance(get_runner_for_framework("pytest", "docker"), LocalPytestRunner)


# ── DockerPlaywrightRunner ───────────────────────────────────────────────────

def _playwright_json(status="passed", title="order flow"):
    return json.dumps({
        "suites": [{
            "specs": [{
                "title": title,
                "tests": [{"results": [{"status": status, "duration": 1200, "attachments": []}]}],
            }],
        }],
    }).encode()


class _FakeStream:
    def __init__(self, payload: bytes):
        self._chunks = [payload] if payload else []

    async def read(self, _n):
        return self._chunks.pop(0) if self._chunks else b""


class _FakeProc:
    def __init__(self, stdout_payload=b"", returncode=0, hang=False):
        self.stdout = _FakeStream(stdout_payload)
        self.returncode = returncode
        self._hang = hang

    async def wait(self):
        while self._hang:
            await asyncio.sleep(0.05)
        return self.returncode

    def kill(self):
        self._hang = False


def _run_docker(runner, workspace, timeout_seconds=600):
    async def _go():
        return await runner.run(
            workspace_dir=workspace, script_file_name="specs/x.spec.ts",
            execution_command=None, environment="SIT", timeout_seconds=timeout_seconds,
        )

    return anyio.run(_go)


def test_docker_runner_fails_cleanly_when_docker_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(docker_mod, "docker_available", lambda: (False, "docker CLI not found"))
    result = _run_docker(DockerPlaywrightRunner(), tmp_path)
    assert result.run_status == "failed"
    assert "docker CLI not found" in result.error_message


def test_docker_runner_rejects_workspace_outside_shared_mount(monkeypatch, tmp_path):
    monkeypatch.setattr(docker_mod, "docker_available", lambda: (True, "ok"))
    monkeypatch.setattr(
        docker_mod.settings, "automation_docker_storage_mount", str(tmp_path / "elsewhere")
    )
    result = _run_docker(DockerPlaywrightRunner(), tmp_path / "workspace")
    assert result.run_status == "failed"
    assert "shared storage mount" in result.error_message


def test_docker_runner_builds_container_command_and_parses_results(monkeypatch, tmp_path):
    workspace = tmp_path / "automation_workspace" / "99-1"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(docker_mod, "docker_available", lambda: (True, "ok"))
    monkeypatch.setattr(docker_mod.settings, "automation_docker_storage_mount", str(tmp_path))
    monkeypatch.setattr(docker_mod.settings, "automation_docker_volume", "stlc-platform_stlc_storage")
    monkeypatch.setattr(docker_mod.settings, "automation_docker_image", "stlc-platform-worker")
    monkeypatch.setattr(docker_mod.settings, "automation_docker_network", "stlc-net")

    captured = {}

    async def fake_exec(*cmd, **kwargs):
        captured["cmd"] = list(cmd)
        return _FakeProc(stdout_payload=_playwright_json(), returncode=0)

    monkeypatch.setattr(docker_mod.asyncio, "create_subprocess_exec", fake_exec)

    result = _run_docker(DockerPlaywrightRunner(), workspace)

    cmd = captured["cmd"]
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert "--user" in cmd and cmd[cmd.index("--user") + 1] == "root"
    assert "stlc-platform_stlc_storage:" + str(tmp_path) in " ".join(cmd)
    assert "--network" in cmd and cmd[cmd.index("--network") + 1] == "stlc-net"
    assert "stlc-platform-worker" in cmd
    assert cmd[-1] == "--reporter=json"

    assert result.run_status == "completed"
    assert len(result.results) == 1
    assert result.results[0].status == "pass"
    assert result.results[0].name == "order flow"
    assert result.metadata["runner"] == "docker_playwright"
    assert result.metadata["container"].startswith("stlc-pw-")
    # Raw JSON persisted for download parity with the local runner.
    assert (workspace / "results.json").exists()


def test_docker_runner_kills_container_on_timeout(monkeypatch, tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setattr(docker_mod, "docker_available", lambda: (True, "ok"))
    monkeypatch.setattr(docker_mod.settings, "automation_docker_storage_mount", str(tmp_path))

    hanging = _FakeProc(hang=True)

    async def fake_exec(*cmd, **kwargs):
        return hanging

    killed = []

    async def fake_kill(name):
        killed.append(name)
        hanging.kill()

    monkeypatch.setattr(docker_mod.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(DockerPlaywrightRunner, "_kill_container", staticmethod(fake_kill))

    result = _run_docker(DockerPlaywrightRunner(), workspace, timeout_seconds=1)

    assert result.run_status == "failed"
    assert "timed out" in result.error_message
    assert len(killed) == 1 and killed[0].startswith("stlc-pw-")


def test_docker_runner_nonzero_docker_exit_is_runner_failure(monkeypatch, tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setattr(docker_mod, "docker_available", lambda: (True, "ok"))
    monkeypatch.setattr(docker_mod.settings, "automation_docker_storage_mount", str(tmp_path))

    async def fake_exec(*cmd, **kwargs):
        return _FakeProc(stdout_payload=b"", returncode=125)  # docker daemon error

    monkeypatch.setattr(docker_mod.asyncio, "create_subprocess_exec", fake_exec)

    result = _run_docker(DockerPlaywrightRunner(), workspace)
    assert result.run_status == "failed"
    assert "code 125" in result.error_message


# ── Parallel batch path (shared fakes shaped like test_automation_batch_task) ─

class _ExecResultStub:
    def __init__(self, many):
        self._many = many

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._many))


class _TaskDB:
    def __init__(self, run, scripts_by_id, placeholders):
        self.run = run
        self.scripts_by_id = scripts_by_id
        self.placeholders = list(placeholders)
        self.commits = 0

    def add(self, obj):
        pass

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def get(self, model, object_id):
        if model is ExecutionRun:
            return self.run if object_id == self.run.id else None
        if model is AutomationScript:
            return self.scripts_by_id.get(object_id)
        return None

    async def execute(self, _stmt):
        return _ExecResultStub(self.placeholders)


class _AsyncSessionFactory:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


def _script(script_id):
    return AutomationScript(
        id=script_id, project_id=1, test_case_id=None, created_by=1,
        script_id=f"AS-{script_id:04d}", framework="pytest",
        file_path="tests/test_example.py", code="def test_example(): assert True",
        status="approved",
    )


def _placeholder(pk, script_id):
    return ExecutionResult(
        id=pk, execution_run_id=99, project_id=1, test_name=f"AS-{script_id:04d}",
        status="pending", metadata_={"automation_script_id": script_id},
    )


def test_execute_batch_parallel_mode_passes_runner_mode_and_runs_all(monkeypatch, tmp_path):
    monkeypatch.setattr(automation_tasks_module, "reset_workspace", lambda key: tmp_path / str(key))
    monkeypatch.setattr(automation_tasks_module, "write_pytest_config", lambda workspace: None)
    monkeypatch.setattr(
        automation_tasks_module, "materialize_script",
        lambda *, workspace, framework, code, suggested_file_path: "test_example.py",
    )

    seen_modes = []
    in_flight = {"now": 0, "max": 0}

    async def fake_runner(**kwargs):
        seen_modes.append(kwargs.get("runner_mode"))
        in_flight["now"] += 1
        in_flight["max"] = max(in_flight["max"], in_flight["now"])
        await asyncio.sleep(0.05)
        in_flight["now"] -= 1
        return RunnerResult(
            run_status="completed",
            results=[PerTestResult(name="test_example", status="pass", duration_ms=10)],
            duration_seconds=0.05, log_path=None,
        )

    monkeypatch.setattr(automation_tasks_module, "run_script_for_execution", fake_runner)

    run = ExecutionRun(
        id=99, project_id=1, execution_id="ER-0099", suite_name="Studio batch",
        environment="SIT", status="queued", execution_type="automation",
        source_type="automation_local_batch", total_tests=3, passed=0, failed=0,
        skipped=0, execution_logs=[],
        metadata_={
            "source_type": "automation_local_batch",
            "automation_script_ids": [1, 2, 3],
            "runner_mode": "docker",
            "parallelism": 2,
        },
    )
    scripts = {1: _script(1), 2: _script(2), 3: _script(3)}
    placeholders = [_placeholder(1, 1), _placeholder(2, 2), _placeholder(3, 3)]
    db = _TaskDB(run, scripts, placeholders)
    monkeypatch.setattr(automation_tasks_module, "AsyncSessionLocal", lambda: _AsyncSessionFactory(db))

    async def _go():
        return await _execute_batch(99, 600)

    result = anyio.run(_go)

    assert result["status"] == "completed"
    assert result["passed"] == 3
    assert seen_modes == ["docker", "docker", "docker"]
    assert in_flight["max"] == 2  # semaphore honoured: never more than `parallelism`
    assert all(p.status == "pass" for p in placeholders)
    # Progress still committed per completed script (live movement for pollers).
    assert db.commits >= 4
