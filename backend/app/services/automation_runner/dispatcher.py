"""Pick the right runner for a given script and orchestrate the per-run setup.

Caller flow (used by the Celery task):

    workspace = reset_workspace(run_id)
    script_file = materialize_script(...)
    result = await run_script_for_execution(
        framework=script.framework,
        workspace=workspace,
        script_file_name=script_file,
        execution_command=script.execution_command,
        environment=run.environment,
    )
    # caller persists `result` to ExecutionRun / ExecutionResult rows.
"""
from __future__ import annotations

from pathlib import Path

from app.services.automation_runner.base import AutomationRunner, RunnerResult
from app.services.automation_runner.local_playwright import LocalPlaywrightRunner
from app.services.automation_runner.local_pytest import LocalPytestRunner


_RUNNER_BY_FRAMEWORK: dict[str, AutomationRunner] = {
    "playwright": LocalPlaywrightRunner(),
    "pytest": LocalPytestRunner(),
}


def get_runner_for_framework(framework: str) -> AutomationRunner | None:
    return _RUNNER_BY_FRAMEWORK.get((framework or "").lower())


async def run_script_for_execution(
    *,
    framework: str,
    workspace: Path,
    script_file_name: str,
    execution_command: str | None,
    environment: str | None,
    timeout_seconds: int = 600,
) -> RunnerResult:
    runner = get_runner_for_framework(framework)
    if runner is None:
        return RunnerResult(
            run_status="failed",
            results=[],
            duration_seconds=0.0,
            log_path=None,
            error_message=(
                f"No runner registered for framework '{framework}'. "
                "Supported frameworks: playwright, pytest."
            ),
            metadata={"runner": "none"},
        )
    return await runner.run(
        workspace_dir=workspace,
        script_file_name=script_file_name,
        execution_command=execution_command,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )
