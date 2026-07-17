"""Phase 4.2: DryRunAgent — executes generated scripts via the real runner
infrastructure (mocked here to avoid spawning subprocesses in unit tests;
the runner itself is exercised for real in test_evidence_capture.py /
test_script_compiler.py's underlying pipeline, and was smoke-tested live
during development)."""
import asyncio
import time

import anyio

from app.agents.automation import dry_run_agent as mod
from app.agents.automation.dry_run_agent import DryRunAgent
from app.services.automation_runner.base import PerTestResult, RunnerResult


def _fake_runner(run_status="completed", results=None):
    async def run_script_for_execution(**_kwargs):
        return RunnerResult(
            run_status=run_status,
            results=results or [],
            duration_seconds=1.2,
            log_path="/tmp/run.log",
        )
    return run_script_for_execution


def test_dry_run_marks_script_passed_when_all_tests_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "reset_workspace", lambda _key: tmp_path)
    monkeypatch.setattr(mod, "write_playwright_config", lambda *a, **k: None)
    monkeypatch.setattr(mod, "materialize_bundle", lambda **k: None)
    monkeypatch.setattr(
        mod, "run_script_for_execution",
        _fake_runner(results=[PerTestResult(name="t1", status="pass", duration_ms=100)]),
    )

    agent = DryRunAgent()

    async def run():
        return await agent.run(scripts=[{
            "script_id": 42, "framework": "playwright", "file_path": "specs/x.spec.ts",
            "compiled_files": {"specs/x.spec.ts": "..."}, "application_url": "http://app/",
        }])

    result = anyio.run(run)

    assert result.success is True
    dry_run = result.data["dry_runs"][0]
    assert dry_run["script_id"] == 42
    assert dry_run["passed"] is True
    assert dry_run["results"][0]["status"] == "pass"


def test_dry_run_not_passed_when_any_test_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "reset_workspace", lambda _key: tmp_path)
    monkeypatch.setattr(mod, "write_playwright_config", lambda *a, **k: None)
    monkeypatch.setattr(mod, "materialize_bundle", lambda **k: None)
    monkeypatch.setattr(
        mod, "run_script_for_execution",
        _fake_runner(results=[
            PerTestResult(name="t1", status="pass"),
            PerTestResult(name="t2", status="fail", error_message="assertion failed"),
        ]),
    )

    agent = DryRunAgent()

    async def run():
        return await agent.run(scripts=[{
            "script_id": 42, "framework": "playwright", "compiled_files": {"specs/x.spec.ts": "..."},
        }])

    result = anyio.run(run)
    assert result.data["dry_runs"][0]["passed"] is False


def test_dry_run_falls_back_to_single_file_materialization_without_bundle(monkeypatch, tmp_path):
    calls = {}

    def fake_materialize_script(**kwargs):
        calls.update(kwargs)
        return "test_script.py"

    monkeypatch.setattr(mod, "reset_workspace", lambda _key: tmp_path)
    monkeypatch.setattr(mod, "write_pytest_config", lambda *a, **k: None)
    monkeypatch.setattr(mod, "materialize_script", fake_materialize_script)
    monkeypatch.setattr(mod, "run_script_for_execution", _fake_runner(results=[PerTestResult(name="t1", status="pass")]))

    agent = DryRunAgent()

    async def run():
        return await agent.run(scripts=[{
            "script_id": 7, "framework": "pytest", "code": "def test_x(): pass",
        }])

    result = anyio.run(run)
    assert result.success is True
    assert calls["framework"] == "pytest"
    assert calls["code"] == "def test_x(): pass"


def test_dry_run_crash_for_one_script_does_not_block_others(monkeypatch, tmp_path):
    # Keyed on the script id embedded in workspace_key (not call order —
    # scripts now run concurrently, see DRY_RUN_CONCURRENCY, so which task's
    # synchronous prefix happens to execute first is not something a test
    # should depend on).
    def reset_workspace(key):
        if key.startswith("dryrun-1-"):
            raise RuntimeError("disk full")
        return tmp_path

    monkeypatch.setattr(mod, "reset_workspace", reset_workspace)
    monkeypatch.setattr(mod, "write_playwright_config", lambda *a, **k: None)
    monkeypatch.setattr(mod, "materialize_bundle", lambda **k: None)
    monkeypatch.setattr(mod, "run_script_for_execution", _fake_runner(results=[PerTestResult(name="t1", status="pass")]))

    agent = DryRunAgent()

    async def run():
        return await agent.run(scripts=[
            {"script_id": 1, "framework": "playwright", "compiled_files": {"a.spec.ts": "x"}},
            {"script_id": 2, "framework": "playwright", "compiled_files": {"b.spec.ts": "x"}},
        ])

    result = anyio.run(run)
    assert result.success is True
    assert len(result.data["dry_runs"]) == 1
    assert result.data["dry_runs"][0]["script_id"] == 2
    assert any("disk full" in log["message"] for log in result.logs)


def test_dry_run_fails_cleanly_with_no_scripts():
    agent = DryRunAgent()

    async def run():
        return await agent.run(scripts=[])

    result = anyio.run(run)
    assert result.success is False


# ── Concurrent wave dry-run (Playwright AI Studio) ───────────────────────────
# Same rationale as automation_agent's wave-generation concurrency: a Studio
# wave can hand this agent up to 25 scripts in one call, each a real
# subprocess. Sequential execution has the identical failure mode
# (blow through the agent's timeout) one stage later in the chain.

def _slow_runner(delay: float, tracker: dict):
    async def run_script_for_execution(**_kwargs):
        tracker["in_flight"] = tracker.get("in_flight", 0) + 1
        tracker["max_in_flight"] = max(tracker.get("max_in_flight", 0), tracker["in_flight"])
        try:
            await asyncio.sleep(delay)
            return RunnerResult(
                run_status="completed",
                results=[PerTestResult(name="t1", status="pass", duration_ms=10)],
                duration_seconds=delay, log_path=None,
            )
        finally:
            tracker["in_flight"] -= 1
    return run_script_for_execution


def test_dry_run_wave_runs_concurrently_not_serially(monkeypatch, tmp_path):
    tracker: dict = {}
    monkeypatch.setattr(mod, "reset_workspace", lambda _key: tmp_path)
    monkeypatch.setattr(mod, "write_playwright_config", lambda *a, **k: None)
    monkeypatch.setattr(mod, "materialize_bundle", lambda **k: None)
    monkeypatch.setattr(mod, "run_script_for_execution", _slow_runner(0.1, tracker))

    scripts = [
        {"script_id": i, "framework": "playwright", "compiled_files": {"a.spec.ts": "x"}}
        for i in range(1, 6)
    ]
    agent = DryRunAgent()

    async def run():
        return await agent.run(scripts=scripts)

    start = time.monotonic()
    result = anyio.run(run)
    elapsed = time.monotonic() - start

    assert len(result.data["dry_runs"]) == 5
    # 5 sequential 0.1s runs would take >=0.5s; concurrent should be ~0.1s.
    assert elapsed < 0.3
    assert tracker["max_in_flight"] > 1


def test_dry_run_wave_respects_concurrency_cap(monkeypatch, tmp_path):
    tracker: dict = {}
    monkeypatch.setattr(mod, "reset_workspace", lambda _key: tmp_path)
    monkeypatch.setattr(mod, "write_playwright_config", lambda *a, **k: None)
    monkeypatch.setattr(mod, "materialize_bundle", lambda **k: None)
    monkeypatch.setattr(mod, "run_script_for_execution", _slow_runner(0.05, tracker))
    monkeypatch.setattr(mod, "DRY_RUN_CONCURRENCY", 2)

    scripts = [
        {"script_id": i, "framework": "playwright", "compiled_files": {"a.spec.ts": "x"}}
        for i in range(1, 7)
    ]
    agent = DryRunAgent()

    async def run():
        return await agent.run(scripts=scripts)

    result = anyio.run(run)

    assert len(result.data["dry_runs"]) == 6
    assert tracker["max_in_flight"] == 2
