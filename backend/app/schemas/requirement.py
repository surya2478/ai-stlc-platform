"""Pydantic schemas for requirements."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, field_validator


class RequirementCreate(BaseModel):
    project_id: int
    title: str
    summary: str | None = None
    source: Literal["manual", "doc_upload", "jira"] = "manual"
    source_document_id: int | None = None

    @field_validator("project_id")
    @classmethod
    def project_id_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("project_id must be a positive integer")
        return v

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Requirement title must not be blank")
        if len(v) > 500:
            raise ValueError("Title must be 500 characters or fewer")
        return v


class RequirementUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    acceptance_criteria: list | None = None
    business_rules: list | None = None
    user_roles: list | None = None
    systems_impacted: list | None = None
    ui_pages: list | None = None
    apis: list | None = None
    dependencies: list | None = None
    risks: list | None = None
    missing_information: list | None = None
    status: Literal["draft", "pending_review", "approved", "rejected"] | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Requirement title must not be blank")
        return v


class RequirementOut(BaseModel):
    id: int
    project_id: int
    requirement_id: str
    source: str
    title: str
    summary: str | None = None
    acceptance_criteria: list | None = None
    business_rules: list | None = None
    user_roles: list | None = None
    systems_impacted: list | None = None
    ui_pages: list | None = None
    apis: list | None = None
    dependencies: list | None = None
    risks: list | None = None
    missing_information: list | None = None
    quality_score: float | None = None
    quality_feedback: str | None = None
    status: str
    jira_issue_key: str | None = None
    source_document_id: int | None = None
    metadata_: dict[str, Any] | None = None
    review_notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# Lightweight version used in list views (kept for backwards compat)
RequirementListOut = RequirementOut


class ApprovalRequest(BaseModel):
    action: Literal["approve", "reject"]
    notes: str | None = None


class AgentTriggerRequest(BaseModel):
    project_id: int
    document_id: int | None = None
    requirement_ids: list[int] | None = None
