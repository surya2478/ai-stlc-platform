"""Containerized pytest runner.

pytest previously had no container runner, so an isolated mode had to block it
rather than downgrade it into the worker. This is the runner that makes the
block unnecessary — and it has to be confined identically to the Playwright one,
because a sandbox control applied to one framework and not the other is a gap
nobody would see.
"""
from __future__ import annotations

import asyncio
import json

import anyio

import app.services.automation_runner.docker_pytest as pytest_mod
from app.services.automation_runner.docker_pytest import DockerPytestRunner


class _FakeProc:
    def __init__(self, returncode=0, hang=False):
        self.returncode = returncode
        self._hang = hang

    async def wait(self):
        while self._hang:
            await asyncio.sleep(0.05)
        return self.returncode

    def kill(self):
        self._hang = False


def _run(runner, workspace, timeout_seconds=600):
    async def _go():
        return await runner.run(
            workspace_dir=workspace, script_file_name="test_x.py",
            execution_command=None, environment="SIT", timeout_seconds=timeout_seconds,
        )

    return anyio.run(_go)


def _write_report(workspace, outcome="passed"):
    (workspace / "pytest-report.json").write_text(
        json.dumps({
            "tests": [{"nodeid": "test_x.py::test_order", "outcome": outcome,
                       "call": {"duration": 0.5}}]
        }),
        encoding="utf-8",
    )


def _prepare(monkeypatch, tmp_path):
    workspace = tmp_path / "automation_workspace" / "42"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(pytest_mod, "docker_available", lambda: (True, "ok"))
    monkeypatch.setattr(
        pytest_mod.settings, "automation_docker_storage_mount", str(tmp_path)
    )
    return workspace


def test_it_fails_cleanly_when_docker_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        pytest_mod, "docker_available", lambda: (False, "docker CLI not found")
    )
    result = _run(DockerPytestRunner(), tmp_path)
    assert result.run_status == "failed"
    assert "docker CLI not found" in result.error_message


def test_it_rejects_a_workspace_outside_the_shared_mount(monkeypatch, tmp_path):
    monkeypatch.setattr(pytest_mod, "docker_available", lambda: (True, "ok"))
    monkeypatch.setattr(
        pytest_mod.settings, "automation_docker_storage_mount", str(tmp_path / "other")
    )
    result = _run(DockerPytestRunner(), tmp_path / "ws")
    assert result.run_status == "failed"
    assert "shared storage mount" in result.error_message


def test_it_forces_the_json_reporter_and_carries_the_sandbox(monkeypatch, tmp_path):
    """The reporter is forced for the same reason as the local runner: without
    structured rows there is no result to score. The sandbox flags matter just
    as much here as for Playwright."""
    workspace = _prepare(monkeypatch, tmp_path)
    captured = {}

    async def fake_exec(*cmd, **_kwargs):
        captured["cmd"] = list(cmd)
        _write_report(workspace)
        return _FakeProc(returncode=0)

    monkeypatch.setattr(pytest_mod.asyncio, "create_subprocess_exec", fake_exec)
    result = _run(DockerPytestRunner(), workspace)

    cmd = captured["cmd"]
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert "--json-report" in cmd
    assert any(a.startswith("--json-report-file=") for a in cmd)
    # Identical confinement to the Playwright runner — one shared implementation.
    assert cmd[cmd.index("--user") + 1] == "10001:10001"
    assert "--cap-drop" in cmd and "--read-only" in cmd and "no-new-privileges" in cmd
    assert "--pids-limit" in cmd

    assert result.run_status == "completed"
    assert result.results[0].status == "pass"
    assert result.metadata["runner"] == "docker_pytest"
    assert result.metadata["container"].startswith("stlc-pt-")


def test_a_read_only_root_gets_a_writable_home_and_no_bytecode(monkeypatch, tmp_path):
    """Without these pytest fails on an unwritable HOME or tries to write .pyc
    beside the image's own modules."""
    workspace = _prepare(monkeypatch, tmp_path)

    async def fake_exec(*cmd, **_kwargs):
        _write_report(workspace)
        fake_exec.cmd = list(cmd)
        return _FakeProc(returncode=0)

    monkeypatch.setattr(pytest_mod.asyncio, "create_subprocess_exec", fake_exec)
    _run(DockerPytestRunner(), workspace)

    joined = " ".join(fake_exec.cmd)
    assert "PYTHONDONTWRITEBYTECODE=1" in joined
    assert "HOME=/tmp" in joined


def test_failing_tests_are_a_completed_run_not_a_harness_failure(monkeypatch, tmp_path):
    """Exit 1 means tests ran and some failed — an application verdict, not a
    broken runner."""
    workspace = _prepare(monkeypatch, tmp_path)

    async def fake_exec(*_cmd, **_kwargs):
        _write_report(workspace, outcome="failed")
        return _FakeProc(returncode=1)

    monkeypatch.setattr(pytest_mod.asyncio, "create_subprocess_exec", fake_exec)
    result = _run(DockerPytestRunner(), workspace)

    assert result.run_status == "completed"
    assert result.error_message is None
    assert result.results[0].status == "fail"


def test_a_docker_level_failure_is_a_runner_failure(monkeypatch, tmp_path):
    """125-127 are docker's own daemon/image errors, not test outcomes."""
    workspace = _prepare(monkeypatch, tmp_path)

    async def fake_exec(*_cmd, **_kwargs):
        return _FakeProc(returncode=125)

    monkeypatch.setattr(pytest_mod.asyncio, "create_subprocess_exec", fake_exec)
    result = _run(DockerPytestRunner(), workspace)

    assert result.run_status == "failed"
    assert "125" in result.error_message


def test_zero_collected_tests_is_an_error_not_a_skip(monkeypatch, tmp_path):
    """Inherited from the local runner: exit 5 means nothing ran, and calling
    that a skip hides a harness failure (AUT-006)."""
    workspace = _prepare(monkeypatch, tmp_path)

    async def fake_exec(*_cmd, **_kwargs):
        return _FakeProc(returncode=5)

    monkeypatch.setattr(pytest_mod.asyncio, "create_subprocess_exec", fake_exec)
    result = _run(DockerPytestRunner(), workspace)

    assert result.results[0].status == "error"
    assert "collected 0 tests" in result.results[0].error_message


def test_the_container_is_killed_on_timeout(monkeypatch, tmp_path):
    """Killing the `docker run` client alone would leave the container running."""
    workspace = _prepare(monkeypatch, tmp_path)
    hanging = _FakeProc(hang=True)
    killed = []

    async def fake_exec(*_cmd, **_kwargs):
        return hanging

    async def fake_kill(name):
        killed.append(name)
        hanging.kill()

    monkeypatch.setattr(pytest_mod.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(pytest_mod, "kill_container", fake_kill)

    result = _run(DockerPytestRunner(), workspace, timeout_seconds=1)

    assert result.run_status == "failed"
    assert "timed out" in result.error_message
    assert len(killed) == 1 and killed[0].startswith("stlc-pt-")


def test_cancellation_terminates_the_container(monkeypatch, tmp_path):
    """Wave 2's control has to reach the container here too, not just for
    Playwright."""
    workspace = _prepare(monkeypatch, tmp_path)
    hanging = _FakeProc(hang=True)
    killed = []

    async def fake_exec(*_cmd, **_kwargs):
        return hanging

    async def fake_kill(name):
        killed.append(name)
        hanging.kill()

    monkeypatch.setattr(pytest_mod.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(pytest_mod, "kill_container", fake_kill)

    async def _go():
        cancellation = asyncio.Event()
        task = asyncio.create_task(
            DockerPytestRunner().run(
                workspace_dir=workspace, script_file_name="test_x.py",
                execution_command=None, environment="SIT", timeout_seconds=60,
                cancellation=cancellation,
            )
        )
        await asyncio.sleep(0.05)
        cancellation.set()
        return await task

    result = asyncio.run(_go())

    assert result.run_status == "cancelled"
    assert result.metadata["cancelled"] is True
    assert killed
