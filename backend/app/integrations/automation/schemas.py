from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AutomationExecutionResult:
    external_run_id: str
    external_test_case_id: str
    status: str
    duration_seconds: float
    logs: list[str] = field(default_factory=list)
    screenshot_url: str | None = None
    video_url: str | None = None
    log_url: str | None = None
    external_result_url: str | None = None
    error_message: str | None = None
    stack_trace: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AutomationExecutionSummary:
    external_run_id: str
    status: str
    results: list[AutomationExecutionResult]
