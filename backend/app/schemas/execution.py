"""Pydantic schemas for Test Execution."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, model_validator


class ExecutionResultOut(BaseModel):
    id: int
    execution_run_id: int
    test_case_id: int | None = None
    test_name: str
    status: str
    duration_ms: int | None = None
    error_message: str | None = None
    stack_trace: str | None = None
    logs: list | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExecutionRunOut(BaseModel):
    id: int
    project_id: int
    execution_id: str
    suite_name: str | None = None
    environment: str | None = None
    status: str
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
    metadata_: dict[str, Any] | None = None

    @model_validator(mode="after")
    def at_least_one_id_set(self) -> "AgentExecutionTrigger":
        if not self.test_case_ids and not self.automation_script_ids:
            raise ValueError("Provide at least one of: test_case_ids or automation_script_ids")
        return self
