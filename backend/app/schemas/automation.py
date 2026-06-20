"""Pydantic schemas for Automation Scripts."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, field_validator


AutomationStatus = Literal["not_required", "mapping_required", "ready_for_automation", "automated", "automation_failed", "maintenance_required"]
ExecutionMode = Literal["manual", "automated", "hybrid", "ai"]
ExecutionStatus = Literal["passed", "failed", "blocked", "skipped", "not_run", "in_progress", "deferred", "error", "pending"]


class AutomationScriptOut(BaseModel):
    id: int
    project_id: int
    test_case_id: int | None = None
    script_id: str
    framework: str
    file_path: str | None = None
    code: str
    setup_required: list[str] | None = None
    execution_command: str | None = None
    status: str
    agent_run_id: int | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AutomationScriptUpdate(BaseModel):
    framework: Literal["playwright", "pytest"] | None = None
    file_path: str | None = None
    code: str | None = None
    setup_required: list[str] | None = None
    execution_command: str | None = None
    status: Literal["draft", "approved", "rejected"] | None = None


class AgentAutomationTrigger(BaseModel):
    project_id: int
    test_case_ids: list[int]
    framework: Literal["playwright", "pytest"] = "playwright"

    @field_validator("test_case_ids")
    @classmethod
    def test_case_ids_non_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("test_case_ids must contain at least one ID")
        return v


class AutomationTestMappingBase(BaseModel):
    project_id: int
    test_case_id: int
    external_tool_name: str
    external_project_id: str | None = None
    external_suite_id: str | None = None
    external_test_case_id: str
    external_script_id: str | None = None
    automation_status: AutomationStatus = "ready_for_automation"
    is_active: bool = True


class AutomationTestMappingCreate(AutomationTestMappingBase):
    pass


class AutomationTestMappingUpdate(BaseModel):
    external_tool_name: str | None = None
    external_project_id: str | None = None
    external_suite_id: str | None = None
    external_test_case_id: str | None = None
    external_script_id: str | None = None
    automation_status: AutomationStatus | None = None
    is_active: bool | None = None


class AutomationTestMappingOut(AutomationTestMappingBase):
    id: int
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExternalAutomationRunRequest(BaseModel):
    project_id: int
    test_case_ids: list[int]
    environment: Literal["local", "development", "staging", "production", "ci"] = "staging"

    @field_validator("test_case_ids")
    @classmethod
    def test_case_ids_non_empty_for_run(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("test_case_ids must contain at least one ID")
        return v


class ExternalAutomationRunOut(BaseModel):
    execution_run_id: int
    external_run_id: str
    status: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    message: str


class ExternalAutomationSyncRequest(BaseModel):
    mapping_id: int
    environment: Literal["local", "development", "staging", "production", "ci"] = "staging"


class JiraExecutionStatusSyncRequest(BaseModel):
    test_case_id: int
    jira_execution_status: ExecutionStatus
    jira_issue_key: str | None = None
    jira_test_key: str | None = None


class JiraExecutionStatusOut(BaseModel):
    test_case_id: int
    jira_issue_key: str | None = None
    jira_test_key: str | None = None
    jira_execution_status: str | None = None
    final_qa_status: str
    source: str = "jira"
