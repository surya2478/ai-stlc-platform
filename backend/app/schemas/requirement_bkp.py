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

    # Telecom / QA domain fields
    qa_domain: str | None = None
    product_group: str | None = None
    product: str | None = None
    sub_request_type: str | None = None
    test_phase: str | None = None
    impacted_systems: list[str] | None = None
    impacted_interfaces: list[str] | None = None
    impacted_products: list[str] | None = None
    impacted_channels: list[str] | None = None
    customer_segment: str | None = None
    business_process: str | None = None
    release_train: str | None = None
    release_version: str | None = None
    risk_level: str | None = None
    regulatory_impact: bool | None = False
    revenue_impact: bool | None = False
    customer_impact: bool | None = False
    dependency_systems: list[str] | None = None
    upstream_systems: list[str] | None = None
    downstream_systems: list[str] | None = None
    api_interface_refs: list[str] | None = None
    environment_needs: str | None = None
    test_data_needs: str | None = None
    nfr_requirements: str | None = None
    readiness_status: str | None = None

    # Jira fields
    jira_issue_key: str | None = None
    jira_issue_type: str | None = None
    jira_priority: str | None = None
    jira_deleted: bool | None = False
    jira_issue_id: str | None = None
    jira_status: str | None = None
    jira_assignee: str | None = None
    jira_reporter: str | None = None
    jira_labels: list[str] | None = None
    jira_components: list[str] | None = None
    jira_fix_versions: list[str] | None = None
    jira_sprint: str | None = None
    jira_epic_key: str | None = None
    sync_status: str | None = None
    sync_error: str | None = None

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

    # Telecom / QA domain fields
    qa_domain: str | None = None
    product_group: str | None = None
    product: str | None = None
    sub_request_type: str | None = None
    test_phase: str | None = None
    impacted_systems: list[str] | None = None
    impacted_interfaces: list[str] | None = None
    impacted_products: list[str] | None = None
    impacted_channels: list[str] | None = None
    customer_segment: str | None = None
    business_process: str | None = None
    release_train: str | None = None
    release_version: str | None = None
    risk_level: str | None = None
    regulatory_impact: bool | None = None
    revenue_impact: bool | None = None
    customer_impact: bool | None = None
    dependency_systems: list[str] | None = None
    upstream_systems: list[str] | None = None
    downstream_systems: list[str] | None = None
    api_interface_refs: list[str] | None = None
    environment_needs: str | None = None
    test_data_needs: str | None = None
    nfr_requirements: str | None = None
    readiness_status: str | None = None

    # Jira fields
    jira_issue_key: str | None = None
    jira_issue_type: str | None = None
    jira_priority: str | None = None
    jira_deleted: bool | None = None
    jira_issue_id: str | None = None
    jira_status: str | None = None
    jira_assignee: str | None = None
    jira_reporter: str | None = None
    jira_labels: list[str] | None = None
    jira_components: list[str] | None = None
    jira_fix_versions: list[str] | None = None
    jira_sprint: str | None = None
    jira_epic_key: str | None = None
    sync_status: str | None = None
    sync_error: str | None = None

    # Quality denormalization
    quality_score: float | None = None
    quality_feedback: str | None = None
    quality_verdict: str | None = None

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

    # Telecom / QA domain fields
    qa_domain: str | None = None
    product_group: str | None = None
    product: str | None = None
    sub_request_type: str | None = None
    test_phase: str | None = None
    impacted_systems: list[str] | None = None
    impacted_interfaces: list[str] | None = None
    impacted_products: list[str] | None = None
    impacted_channels: list[str] | None = None
    customer_segment: str | None = None
    business_process: str | None = None
    release_train: str | None = None
    release_version: str | None = None
    risk_level: str | None = None
    regulatory_impact: bool | None = None
    revenue_impact: bool | None = None
    customer_impact: bool | None = None
    dependency_systems: list[str] | None = None
    upstream_systems: list[str] | None = None
    downstream_systems: list[str] | None = None
    api_interface_refs: list[str] | None = None
    environment_needs: str | None = None
    test_data_needs: str | None = None
    nfr_requirements: str | None = None
    readiness_status: str | None = None

    # Quality denormalization
    quality_score: float | None = None
    quality_feedback: str | None = None
    quality_verdict: str | None = None

    status: str
    jira_issue_key: str | None = None
    jira_issue_type: str | None = None
    jira_priority: str | None = None
    jira_deleted: bool | None = None
    jira_updated_at: datetime | None = None
    jira_last_synced_at: datetime | None = None

    jira_issue_id: str | None = None
    jira_status: str | None = None
    jira_assignee: str | None = None
    jira_reporter: str | None = None
    jira_labels: list[str] | None = None
    jira_components: list[str] | None = None
    jira_fix_versions: list[str] | None = None
    jira_sprint: str | None = None
    jira_epic_key: str | None = None
    sync_status: str | None = None
    sync_error: str | None = None

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
