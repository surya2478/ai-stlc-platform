"""Automation runner package — executes generated automation scripts locally.

Entry points the rest of the codebase should use:

  from app.services.automation_runner import run_script_for_execution
  from app.services.automation_runner.preflight import runtime_status
"""
from app.services.automation_runner.base import (  # noqa: F401
    AutomationRunner,
    PerTestResult,
    RunnerResult,
)
from app.services.automation_runner.dispatcher import (  # noqa: F401
    get_runner_for_framework,
    run_script_for_execution,
)
from app.services.automation_runner.preflight import runtime_status  # noqa: F401
