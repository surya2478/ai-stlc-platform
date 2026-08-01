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
from app.services.automation_runner.docker_pytest import DockerPytestRunner
from app.services.automation_runner.local_playwright import LocalPlaywrightRunner
from app.services.automation_runner.local_pytest import LocalPytestRunner
from app.services.automation_runner.policy import resolve_runner_mode
from app.services.automation_runner.remote_executor import RemoteExecutorRunner


_RUNNER_BY_FRAMEWORK: dict[str, AutomationRunner] = {
    "playwright": LocalPlaywrightRunner(),
    "pytest": LocalPytestRunner(),
}

_DOCKER_RUNNER_BY_FRAMEWORK: dict[str, AutomationRunner] = {
    "playwright": DockerPlaywrightRunner(),
    "pytest": DockerPytestRunner(),
}

# Executor mode brokers the same containers through a service that owns the
# Docker socket, so the worker does not have to (AUT-002). One client covers
# both frameworks; the executor picks the runner from the requested framework.
_EXECUTOR_RUNNER_BY_FRAMEWORK: dict[str, AutomationRunner] = {
    "playwright": RemoteExecutorRunner("playwright"),
    "pytest": RemoteExecutorRunner("pytest"),
}

_RUNNERS_BY_MODE: dict[str, dict[str, AutomationRunner]] = {
    "docker": _DOCKER_RUNNER_BY_FRAMEWORK,
    "executor": _EXECUTOR_RUNNER_BY_FRAMEWORK,
}


def get_runner_for_framework(framework: str, runner_mode: str | None = None) -> AutomationRunner | None:
    """Resolve the runner, never downgrading the isolation that was asked for.

    An isolated mode with no runner for this framework returns None so the
    caller reports a blocked framework. Falling back to the local subprocess
    would run untrusted code inside the worker precisely when the operator had
    asked for it to be contained — the same silent-downgrade defect as AUT-018,
    one level down.
    """
    key = (framework or "").lower()
    mode = (runner_mode or "").lower()
    mode_runners = _RUNNERS_BY_MODE.get(mode)
    if mode_runners is not None:
        return mode_runners.get(key)
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
                f"No '{decision.mode}' runner is registered for framework "
                f"'{framework}'. Running it locally instead would put untrusted "
                "code back inside the worker, so it is blocked rather than "
                "downgraded."
                if decision.mode in _RUNNERS_BY_MODE
                else (
                    f"No runner registered for framework '{framework}'. "
                    "Supported frameworks: playwright, pytest."
                )
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
