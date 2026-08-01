"""Wave 4 / AUT-002: the executor boundary.

The worker used to mount `/var/run/docker.sock`. Daemon access is host-level
authority, and the worker is the worst process in the deployment to hold it: it
runs LLM-generated code paths and carries database, Redis and LLM credentials.

The executor inverts that. What matters is the *narrowness* of the interface —
a caller can ask for a bundle to be run and nothing else — so these test the
refusals as much as the happy path.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.executor.main as executor_mod
from app.config import Settings
from app.services.automation_runner.base import PerTestResult, RunnerResult
from app.services.automation_runner.policy import resolve_runner_mode
from app.services.automation_runner.remote_executor import RemoteExecutorRunner

TOKEN = "executor-shared-secret"


def _settings(**overrides) -> Settings:
    overrides.setdefault("app_secret_key", "test-secret-key-with-sufficient-length-1234")
    return Settings(**overrides)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        executor_mod,
        "settings",
        _settings(automation_executor_token=TOKEN, file_storage_path=str(tmp_path)),
    )
    return TestClient(executor_mod.app)


# ── Authentication ──────────────────────────────────────────────────────────


def test_job_without_a_token_is_rejected(client, tmp_path):
    response = client.post("/jobs", json={
        "job_id": "j1", "workspace_path": str(tmp_path), "script_file_name": "x.spec.ts",
    })
    assert response.status_code == 401


def test_job_with_a_wrong_token_is_rejected(client, tmp_path):
    response = client.post(
        "/jobs",
        json={"job_id": "j1", "workspace_path": str(tmp_path), "script_file_name": "x.spec.ts"},
        headers={"X-Executor-Token": "guessed"},
    )
    assert response.status_code == 401


def test_executor_refuses_to_serve_when_no_token_is_configured(monkeypatch, tmp_path):
    """An unauthenticated container-spawning endpoint is not an acceptable
    default, even on an internal network."""
    monkeypatch.setattr(
        executor_mod, "settings",
        _settings(automation_executor_token="", file_storage_path=str(tmp_path)),
    )
    response = TestClient(executor_mod.app).post(
        "/jobs",
        json={"job_id": "j1", "workspace_path": str(tmp_path), "script_file_name": "x"},
        headers={"X-Executor-Token": "anything"},
    )
    assert response.status_code == 503


# ── The narrow interface ────────────────────────────────────────────────────


def test_workspace_outside_the_storage_root_is_refused(client, tmp_path):
    """The one path the caller chooses must not become a way to point the
    runner at anything the executor can see."""
    outside = tmp_path.parent / "elsewhere"
    outside.mkdir(exist_ok=True)
    response = client.post(
        "/jobs",
        json={"job_id": "j1", "workspace_path": str(outside), "script_file_name": "x.spec.ts"},
        headers={"X-Executor-Token": TOKEN},
    )
    assert response.status_code == 400
    assert "storage root" in response.json()["detail"]


def test_missing_workspace_is_reported_not_created(client, tmp_path):
    response = client.post(
        "/jobs",
        json={
            "job_id": "j1",
            "workspace_path": str(tmp_path / "never-materialized"),
            "script_file_name": "x.spec.ts",
        },
        headers={"X-Executor-Token": TOKEN},
    )
    assert response.status_code == 404


def test_request_schema_offers_no_way_to_influence_the_container():
    """The security property is what the caller *cannot* say. If this list ever
    grows an image, mount, user or flag field, the boundary is gone."""
    allowed = set(executor_mod.RunJobRequest.model_fields)
    assert allowed == {
        "job_id", "workspace_path", "script_file_name", "environment", "timeout_seconds",
    }


def test_a_job_runs_the_sandboxed_runner_and_returns_its_result(client, monkeypatch, tmp_path):
    workspace = tmp_path / "automation_workspace" / "run-1"
    workspace.mkdir(parents=True)

    async def fake_run(**kwargs):
        assert kwargs["workspace_dir"] == workspace.resolve()
        # Cancellation must be plumbed through or Wave 2's control stops at the
        # executor boundary.
        assert kwargs["cancellation"] is not None
        return RunnerResult(
            run_status="completed",
            results=[PerTestResult(name="order flow", status="pass", duration_ms=1200)],
            duration_seconds=1.2,
            log_path=str(workspace / "run.log"),
            metadata={"runner": "docker_playwright"},
        )

    monkeypatch.setattr(
        executor_mod.DockerPlaywrightRunner, "run", staticmethod(fake_run)
    )

    response = client.post(
        "/jobs",
        json={
            "job_id": "j1",
            "workspace_path": str(workspace),
            "script_file_name": "specs/x.spec.ts",
            "timeout_seconds": 60,
        },
        headers={"X-Executor-Token": TOKEN},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_status"] == "completed"
    assert body["results"][0]["name"] == "order flow"


def test_cancelling_an_unknown_job_says_so_rather_than_claiming_success(client):
    response = client.post(
        "/jobs/nope/cancel", headers={"X-Executor-Token": TOKEN}
    )
    assert response.status_code == 200
    assert response.json()["cancelled"] is False


# ── Policy ──────────────────────────────────────────────────────────────────


def test_executor_mode_requires_a_url_and_a_token():
    """Falling back to a lesser mode would silently undo the isolation the
    operator asked for."""
    decision = resolve_runner_mode(
        "executor", settings=_settings(automation_executor_url="", automation_executor_token="")
    )
    assert not decision.permitted
    assert "AUTOMATION_EXECUTOR_URL" in decision.reason


def test_executor_mode_is_permitted_when_configured():
    decision = resolve_runner_mode(
        "executor",
        settings=_settings(
            app_env="production",
            automation_executor_url="http://runner-executor:8100",
            automation_executor_token=TOKEN,
        ),
    )
    assert decision.permitted and decision.mode == "executor"


# ── Worker-side client ──────────────────────────────────────────────────────


def test_client_reports_an_unreachable_executor_as_a_harness_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.automation_runner.remote_executor.settings",
        _settings(
            automation_executor_url="http://127.0.0.1:9",  # discard port
            automation_executor_token=TOKEN,
        ),
    )
    result = asyncio.run(
        RemoteExecutorRunner().run(
            workspace_dir=Path(tmp_path),
            script_file_name="x.spec.ts",
            execution_command=None,
            environment="SIT",
            timeout_seconds=1,
        )
    )
    assert result.run_status == "failed"
    assert result.results == []
    assert "could not be reached" in result.error_message


def test_client_refuses_when_the_executor_url_is_unset(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.automation_runner.remote_executor.settings",
        _settings(automation_executor_url="", automation_executor_token=""),
    )
    result = asyncio.run(
        RemoteExecutorRunner().run(
            workspace_dir=Path(tmp_path),
            script_file_name="x.spec.ts",
            execution_command=None,
            environment=None,
        )
    )
    assert result.run_status == "failed"
    assert "AUTOMATION_EXECUTOR_URL" in result.error_message


def test_client_deserializes_a_result_and_records_who_executed_it():
    body = {
        "run_status": "completed",
        "results": [{"name": "t1", "status": "pass", "duration_ms": 10}],
        "duration_seconds": 1.0,
        "log_path": "/app/storage/x/run.log",
        "error_message": None,
        "metadata": {"runner": "docker_playwright", "container": "stlc-pw-abc"},
    }
    result = RemoteExecutorRunner._deserialize(body, "job-1")

    assert result.results[0].name == "t1"
    assert result.metadata["job_id"] == "job-1"
    # Provenance: the worker brokered this, the executor ran it.
    assert result.metadata["executed_by"] == "executor"
    assert result.metadata["container"] == "stlc-pw-abc"
