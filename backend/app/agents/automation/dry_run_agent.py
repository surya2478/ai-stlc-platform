"""
Dry Run Agent (Phase 4.2).

Executes every script that just passed the Static Quality Gate through the
SAME local runner infrastructure the manual "Run" button uses
(app/services/automation_runner/) — a real subprocess, not a simulation.
Chained automatically after automation_script (see agent_tasks.py:
AGENT_SPECS["automation_script"].chain_on_success). Persistence
(agent_tasks.py) creates ExecutionRun/ExecutionResult rows tagged
source_type="dry_run" and promotes a script to status="dry_run_passed"
only when every test in it passed.
"""
from __future__ import annotations

import logging
import uuid

from app.agents.base.base_agent import AgentRunResult, BaseAgent
from app.services.automation_runner import run_script_for_execution
from app.services.automation_runner.workspace import (
    materialize_bundle,
    materialize_script,
    reset_workspace,
    write_playwright_config,
    write_pytest_config,
)

logger = logging.getLogger(__name__)

DEFAULT_DRY_RUN_TIMEOUT_SECONDS = 180


class DryRunAgent(BaseAgent):
    """Executes newly-generated scripts once, before any human reviews them."""

    name = "automation_dry_run"

    async def run(self, scripts: list[dict]) -> AgentRunResult:
        self._logs.clear()
        self.log("info", "start", f"Dry-running {len(scripts)} script(s)")

        if not scripts:
            return AgentRunResult(success=False, error="No scripts provided", data={}, logs=self._logs)

        dry_runs: list[dict] = []
        errors: list[str] = []

        for script_data in scripts:
            script_id = script_data.get("script_id")
            try:
                dry_runs.append(await self._dry_run_one(script_data))
            except Exception as exc:
                errors.append(f"Dry run crashed for script {script_id}: {exc}")
                logger.exception("Dry run crashed for script %s", script_id)

        for e in errors:
            self.log("warning", "warning", e)

        if not dry_runs and errors:
            return AgentRunResult(
                success=False,
                error="Dry run failed for all scripts: " + "; ".join(errors),
                data={},
                logs=self._logs,
            )

        passed = sum(1 for d in dry_runs if d["passed"])
        self.log("info", "complete", f"Dry run complete: {passed}/{len(dry_runs)} scripts fully passed")
        return AgentRunResult(success=True, data={"dry_runs": dry_runs}, logs=self._logs)

    async def _dry_run_one(self, script_data: dict) -> dict:
        script_id = script_data["script_id"]
        framework = (script_data.get("framework") or "playwright").lower()
        compiled_files = script_data.get("compiled_files")
        workspace_key = f"dryrun-{script_id}-{uuid.uuid4().hex[:8]}"
        workspace = reset_workspace(workspace_key)

        if framework == "playwright":
            write_playwright_config(
                workspace,
                base_url=script_data.get("application_url"),
                test_dir="specs" if compiled_files else ".",
            )
        else:
            write_pytest_config(workspace)

        if compiled_files:
            materialize_bundle(workspace=workspace, compiled_files=compiled_files)
            script_file = script_data.get("file_path") or next(iter(compiled_files))
        else:
            script_file = materialize_script(
                workspace=workspace,
                framework=framework,
                code=script_data.get("code", ""),
                suggested_file_path=script_data.get("file_path"),
            )

        runner_result = await run_script_for_execution(
            framework=framework,
            workspace=workspace,
            script_file_name=script_file,
            execution_command=script_data.get("execution_command"),
            environment=script_data.get("environment"),
            timeout_seconds=script_data.get("timeout_seconds", DEFAULT_DRY_RUN_TIMEOUT_SECONDS),
        )

        per_test = [
            {
                "name": r.name,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "error_message": r.error_message,
                "stack_trace": r.stack_trace,
                "console_logs": r.console_logs,
                "network_logs": r.network_logs,
                "screenshot_path": r.screenshot_path,
                "video_path": r.video_path,
                "trace_path": r.trace_path,
            }
            for r in runner_result.results
        ]
        passed = bool(per_test) and all(r["status"] == "pass" for r in per_test)
        return {
            "script_id": script_id,
            "run_status": runner_result.run_status,
            "passed": passed,
            "results": per_test,
            "log_path": runner_result.log_path,
            "error_message": runner_result.error_message,
        }

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(scripts=input_data.get("scripts", []))
        return result.data
