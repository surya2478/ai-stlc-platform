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

import asyncio
from pathlib import Path

from app.services.automation_runner.base import AutomationRunner, RunnerResult
from app.services.automation_runner.docker_playwright import DockerPlaywrightRunner
from app.services.automation_runner.local_playwright import LocalPlaywrightRunner
from app.services.automation_runner.local_pytest import LocalPytestRunner
from app.services.automation_runner.policy import resolve_runner_mode


_RUNNER_BY_FRAMEWORK: dict[str, AutomationRunner] = {
    "playwright": LocalPlaywrightRunner(),
    "pytest": LocalPytestRunner(),
}

_DOCKER_RUNNER_BY_FRAMEWORK: dict[str, AutomationRunner] = {
    # Pytest scripts have no docker runner yet — they fall back to the local
    # subprocess (get_runner_for_framework below), which stays correct, just
    # not containerized.
    "playwright": DockerPlaywrightRunner(),
}


def get_runner_for_framework(framework: str, runner_mode: str | None = None) -> AutomationRunner | None:
    key = (framework or "").lower()
    if (runner_mode or "").lower() == "docker":
        docker_runner = _DOCKER_RUNNER_BY_FRAMEWORK.get(key)
        if docker_runner is not None:
            return docker_runner
    return _RUNNER_BY_FRAMEWORK.get(key)


async def run_script_for_execution(
    *,
    framework: str,
    workspace: Path,
    script_file_name: str,
    execution_command: str | None,
    environment: str | None,
    timeout_seconds: int = 600,
    runner_mode: str | None = None,
    cancellation: asyncio.Event | None = None,
) -> RunnerResult:
    # `runner_mode` is a *preference*. The server decides what actually runs, so
    # a caller that passes nothing gets the configured default rather than
    # silently falling through to the least isolated runner (P0-01).
    decision = resolve_runner_mode(runner_mode)
    if not decision.permitted:
        return RunnerResult(
            run_status="failed",
            results=[],
            duration_seconds=0.0,
            log_path=None,
            error_message=decision.reason,
            metadata={"runner": "none", "runner_policy": "refused", **decision.as_metadata()},
        )

    runner = get_runner_for_framework(framework, decision.mode)
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
            metadata={"runner": "none", **decision.as_metadata()},
        )

    result = await runner.run(
        workspace_dir=workspace,
        script_file_name=script_file_name,
        execution_command=execution_command,
        environment=environment,
        timeout_seconds=timeout_seconds,
        cancellation=cancellation,
    )
    # Record what policy chose alongside what the runner reported, so evidence
    # shows the isolation level a result was produced under.
    result.metadata = {**decision.as_metadata(), **result.metadata}
    return result
