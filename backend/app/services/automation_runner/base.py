"""Runner abstraction.

A runner takes a materialized workspace (script on disk + framework config) and
returns a structured RunnerResult — totals, per-test outcomes, captured artifact
file paths. The dispatcher decides which concrete runner to use based on the
script's framework.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class PerTestResult:
    """A single test inside the script's results."""
    name: str
    # Uses the DB vocabulary (matches ck_execution_results_status):
    #   pass | fail | skip | error | blocked
    status: str
    duration_ms: int | None = None
    error_message: str | None = None
    stack_trace: str | None = None
    # File paths on disk (relative to the workspace) for artifacts captured for THIS test.
    screenshot_path: str | None = None
    video_path: str | None = None
    trace_path: str | None = None
    # Parsed inline (small, structured JSON) rather than left as a file path —
    # captured via page.on('console'/'response') listeners the compiler
    # always renders and attaches with testInfo.attach() (Phase 4.2). Using
    # Playwright's public attachment API instead of parsing trace.zip's
    # internal format, which isn't a supported external parsing target.
    console_logs: list[dict] | None = None
    network_logs: list[dict] | None = None
    raw: dict = field(default_factory=dict)


@dataclass(slots=True)
class RunnerResult:
    """End-to-end runner outcome for one script execution."""
    # ExecutionRun.status:  pending | queued | running | completed | failed | cancelled
    run_status: str
    # Per-test rows the caller should persist to ExecutionResult.
    results: list[PerTestResult]
    duration_seconds: float
    # Full stdout/stderr file path; the API streams this through the artifacts endpoint.
    log_path: str | None
    # If the runner could not start at all (e.g. missing Node), set error_message
    # and an empty results list. run_status should be "failed".
    error_message: str | None = None
    # Free-form metadata (workspace dir, command, env, framework).
    metadata: dict = field(default_factory=dict)


class AutomationRunner(ABC):
    """Common contract every runner implements."""

    name: str = "base"

    @abstractmethod
    async def run(
        self,
        *,
        workspace_dir: Path,
        script_file_name: str,
        execution_command: str | None,
        environment: str | None,
        timeout_seconds: int = 600,
    ) -> RunnerResult:
        """Execute the script under workspace_dir and return a normalized result.

        - workspace_dir: pre-created, contains the script file and any framework
          configuration the dispatcher wrote (package.json, playwright.config.ts, etc.)
        - script_file_name: file inside workspace_dir to point the runner at
        - execution_command: the command suggested by the LLM (may be None — runners
          may ignore it and use their own canonical command)
        - environment: free-form environment label ("staging", "SIT", ...), surfaced
          to the script via the AUTOMATION_ENV env var so tests can branch on it.
        - timeout_seconds: hard cap. Runner kills the subprocess on timeout and
          reports run_status="failed", error_message="Timed out after Ns".
        """
        raise NotImplementedError
