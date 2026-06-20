"""Pydantic schemas for Defect Management."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator

PriorityCode = Literal["P1", "P2", "P3", "P4"]
PriorityLabel = Literal["Critical", "High", "Medium", "Low"]
PriorityValue = PriorityCode | PriorityLabel

PRIORITY_NORMALIZATION: dict[str, PriorityLabel] = {
    "p1": "Critical",
    "p2": "High",
    "p3": "Medium",
    "p4": "Low",
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}


def normalize_priority(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = PRIORITY_NORMALIZATION.get(value.strip().lower())
    if not normalized:
        raise ValueError("Priority must be one of: P1, P2, P3, P4, Critical, High, Medium, Low")
    return normalized


class DefectDraftOut(BaseModel):
    id: int
    project_id: int
    test_case_id: int | None = None
    execution_result_id: int | None = None
    defect_id: str
    summary: str
    description: str | None = None
    steps_to_reproduce: list | None = None
    expected_result: str | None = None
    actual_result: str | None = None
    severity: str
    priority: str
    root_cause_hypothesis: str | None = None
    classification: str
    jira_ready: bool
    status: str
    agent_run_id: int | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JiraDefectOut(BaseModel):
    id: int
    defect_draft_id: int
    project_id: int
    jira_issue_key: str
    jira_url: str | None = None
    jira_status: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DefectDraftUpdate(BaseModel):
    summary: str | None = None
    description: str | None = None
    steps_to_reproduce: list | None = None
    expected_result: str | None = None
    actual_result: str | None = None
    severity: Literal["Critical", "High", "Medium", "Low"] | None = None
    priority: PriorityValue | None = None
    root_cause_hypothesis: str | None = None
    classification: Literal["product_defect", "automation_issue", "environment_issue", "test_data_issue"] | None = None
    jira_ready: bool | None = None
    status: Literal["draft", "approved", "rejected", "pushed_to_jira"] | None = None

    @field_validator("summary")
    @classmethod
    def summary_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Summary must not be blank")
        return v

    @field_validator("priority")
    @classmethod
    def normalize_priority_value(cls, v: str | None) -> str | None:
        return normalize_priority(v)


class ApprovalRequest(BaseModel):
    action: Literal["approve", "reject"]
    notes: str | None = None


class AgentDefectTrigger(BaseModel):
    project_id: int
    execution_result_ids: list[int] | None = None
    test_case_ids: list[int] | None = None

    @model_validator(mode="after")
    def at_least_one_source(self) -> "AgentDefectTrigger":
        if not self.execution_result_ids and not self.test_case_ids:
            raise ValueError("Provide at least one of: execution_result_ids or test_case_ids")
        return self


class JiraPushRequest(BaseModel):
    defect_ids: list[int]

    @field_validator("defect_ids")
    @classmethod
    def defect_ids_non_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("defect_ids must contain at least one ID")
        return v


class DefectDraftCreate(BaseModel):
    project_id: int
    test_case_id: int | None = None
    execution_result_id: int | None = None
    summary: str
    description: str | None = None
    steps_to_reproduce: list[str] | None = None
    expected_result: str | None = None
    actual_result: str | None = None
    severity: Literal["Critical", "High", "Medium", "Low"] = "Medium"
    priority: PriorityValue = "P3"
    root_cause_hypothesis: str | None = None
    classification: Literal["product_defect", "automation_issue", "environment_issue", "test_data_issue"] = "product_defect"

    @field_validator("priority")
    @classmethod
    def normalize_priority_value(cls, v: str) -> str:
        normalized = normalize_priority(v)
        if normalized is None:
            raise ValueError("Priority is required")
        return normalized
