"""Pydantic schemas for requirements."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


TELECOM_DOMAINS = [
    "Mobile", "Fixed", "Digital", "Billing", "Charging", "CRM",
    "OSS", "BSS", "Middleware", "Integration", "Network", "Data",
]
# "Test Environment" — governs both filtering and the style/depth of AI-generated
# scenarios & test cases (see scenario_agent.py / test_case_agent.py ENVIRONMENT_GUIDANCE).
TEST_PHASES = ["SIT", "QA", "UAT", "Regression", "Production Smoke Test"]
RISK_LEVELS = ["Critical", "High", "Medium", "Low"]


class RequirementCreate(BaseModel):
    project_id: int
    title: str
    summary: str | None = None
    source: Literal[
        "manual",
        "doc_upload",
        "jira",
        "pasted_text",
        "api_specification",
    ] = "manual"
    source_document_id: int | None = None
    telecom_domain: str | None = None
    qa_domain: str | None = None
    risk_level: str | None = None
    test_phase: str | None = None
    release_version: str | None = None
    release_train: str | None = None

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
    impacted_interfaces: list | None = None
    impacted_products: list | None = None
    impacted_channels: list | None = None
    ui_pages: list | None = None
    apis: list | None = None
    dependencies: list | None = None
    risks: list | None = None
    missing_information: list | None = None
    upstream_systems: list | None = None
    downstream_systems: list | None = None
    api_interface_refs: list | None = None
    dependency_systems: list | None = None
    # Telecom domain
    telecom_domain: str | None = None
    qa_domain: str | None = None
    product_group: str | None = None
    product: str | None = None
    sub_request_type: str | None = None
    risk_level: str | None = None
    test_phase: str | None = None
    release_version: str | None = None
    release_train: str | None = None
    customer_segment: str | None = None
    business_process: str | None = None
    regulatory_impact: bool | None = None
    revenue_impact: bool | None = None
    customer_impact: bool | None = None
    environment_needs: str | None = None
    test_data_needs: str | None = None
    nfr_requirements: str | None = None
    generation_notes: str | None = None
    # Status
    status: Literal["draft", "pending_review", "approved", "rejected"] | None = None
    readiness_status: str | None = None
    review_notes: str | None = Field(default=None, max_length=5000)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Requirement title must not be blank")
        return v


RequirementTransitionAction = Literal[
    "send_to_analysis",
    "send_to_traceability",
    "send_to_review",
    "send_back_to_analysis",
    "send_back_to_traceability",
    "request_clarification",
    "resolve_clarification",
]


class RequirementTransitionRequest(BaseModel):
    """An explicit, auditable hand-off between requirement workspaces."""

    action: RequirementTransitionAction
    notes: str | None = Field(default=None, max_length=2000)


class RequirementOut(BaseModel):
    id: int
    project_id: int
    requirement_id: str
    source: str
    title: str
    summary: str | None = None
    # Intake fields
    acceptance_criteria: list | None = None
    business_rules: list | None = None
    user_roles: list | None = None
    systems_impacted: list | None = None
    impacted_interfaces: list | None = None
    impacted_products: list | None = None
    impacted_channels: list | None = None
    ui_pages: list | None = None
    apis: list | None = None
    dependencies: list | None = None
    risks: list | None = None
    missing_information: list | None = None
    upstream_systems: list | None = None
    downstream_systems: list | None = None
    api_interface_refs: list | None = None
    dependency_systems: list | None = None
    # Telecom domain fields
    telecom_domain: str | None = None
    qa_domain: str | None = None          # legacy column name
    product_group: str | None = None
    product: str | None = None
    sub_request_type: str | None = None
    risk_level: str | None = None
    test_phase: str | None = None
    release_version: str | None = None
    release_train: str | None = None
    customer_segment: str | None = None
    business_process: str | None = None
    regulatory_impact: bool | None = None
    revenue_impact: bool | None = None
    customer_impact: bool | None = None
    environment_needs: str | None = None
    test_data_needs: str | None = None
    nfr_requirements: str | None = None
    generation_notes: str | None = None
    # Quality (denormalised)
    quality_score: float | None = None
    quality_feedback: str | None = None
    quality_verdict: str | None = None
    # Readiness + approval
    readiness_status: str | None = None
    status: str
    review_notes: str | None = None
    is_deleted: bool = False
    # Jira basic
    jira_issue_key: str | None = None
    jira_issue_type: str | None = None
    jira_priority: str | None = None
    jira_deleted: bool = False
    jira_updated_at: datetime | None = None
    jira_last_synced_at: datetime | None = None
    # Jira extended
    jira_issue_id: str | None = None
    jira_status: str | None = None
    jira_assignee: str | None = None
    jira_reporter: str | None = None
    jira_labels: list | None = None
    jira_components: list | None = None
    jira_fix_versions: list | None = None
    jira_sprint: str | None = None
    jira_epic_key: str | None = None
    sync_status: str | None = None
    sync_error: str | None = None
    # Links
    source_document_id: int | None = None
    created_by: int
    updated_by: int | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


RequirementListOut = RequirementOut


class ApprovalRequest(BaseModel):
    action: Literal["approve", "reject"]
    notes: str | None = None
    # Phase 1: when the project's review_mode is "gating", approving an
    # artifact whose latest senior-reviewer verdict is "fail" is blocked
    # unless this is set — the override itself is still recorded via the
    # existing ApprovalAction audit trail (notes/action), never silent.
    override_review_gate: bool = False


class AgentTriggerRequest(BaseModel):
    project_id: int
    document_id: int | None = None
    requirement_ids: list[int] | None = None
    # GAP-1: optional tester-provided context for UI screenshot analysis
    context_note: str | None = None


class URLAnalysisRequest(BaseModel):
    """GAP-2: trigger portal URL analysis."""
    project_id: int
    url: str
    # 0 = single page only; up to 2 levels of same-origin crawling
    crawl_depth: int = Field(default=0, ge=0, le=2)
    context_note: str | None = None


class CodeAnalysisRequest(BaseModel):
    """GAP-3: trigger GitHub / local repository code analysis."""
    project_id: int
    source: Literal["github", "local"]
    # GitHub branch
    github_url: str | None = None
    github_branch: str = "main"
    github_token: str | None = None          # PAT for private repos
    # Local filesystem path
    local_path: str | None = None
    # Languages to scan — e.g. ["python", "javascript", "typescript"]
    languages: list[str] = Field(default_factory=lambda: ["python", "javascript", "typescript"])

    @field_validator("github_url")
    @classmethod
    def validate_github_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v.startswith("https://github.com/"):
            raise ValueError("github_url must start with https://github.com/")
        return v


class RequirementStatsOut(BaseModel):
    total: int = 0
    approved: int = 0
    pending_review: int = 0
    draft: int = 0
    rejected: int = 0
    needs_clarification: int = 0
    ready_for_test_planning: int = 0
    quality_issues: int = 0
    high_risk: int = 0
    missing_ac: int = 0
    jira_synced: int = 0
    jira_conflict: int = 0
