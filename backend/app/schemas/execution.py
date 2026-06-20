"""Pydantic schemas for Test Execution."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, model_validator


class ExecutionResultOut(BaseModel):
    id: int
    execution_run_id: int
    test_case_id: int | None = None
    automation_mapping_id: int | None = None
    test_name: str
    status: str
    duration_ms: int | None = None
    execution_mode: str | None = None
    external_tool_name: str | None = None
    external_test_case_id: str | None = None
    automation_execution_status: str | None = None
    manual_execution_status: str | None = None
    jira_execution_status: str | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    stack_trace: str | None = None
    screenshot_url: str | None = None
    video_url: str | None = None
    log_url: str | None = None
    external_result_url: str | None = None
    jira_issue_key: str | None = None
    jira_test_key: str | None = None
    raw_result_json: dict[str, Any] | None = None
    logs: list | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExecutionRunOut(BaseModel):
    id: int
    project_id: int
    execution_id: str
    test_cycle_id: str | None = None
    source_type: str | None = None
    external_tool_name: str | None = None
    external_run_id: str | None = None
    suite_name: str | None = None
    environment: str | None = None
    status: str
    triggered_by: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    total_tests: int
    passed: int
    failed: int
    skipped: int
    execution_logs: list | None = None
    allure_report_path: str | None = None
    agent_run_id: int | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentExecutionTrigger(BaseModel):
    project_id: int
    test_case_ids: list[int] | None = None
    automation_script_ids: list[int] | None = None
    environment: Literal["local", "staging", "production", "ci"] = "staging"
    suite_name: str | None = None
    source_type: Literal["manual", "automation", "ai"] = "manual"
    metadata_: dict[str, Any] | None = None

    @model_validator(mode="after")
    def at_least_one_id_set(self) -> "AgentExecutionTrigger":
        if not self.test_case_ids and not self.automation_script_ids:
            raise ValueError("Provide at least one of: test_case_ids or automation_script_ids")
        return self
