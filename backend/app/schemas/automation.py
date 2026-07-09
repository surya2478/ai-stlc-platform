"""Pydantic schemas for Automation Scripts."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


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


AutomationScriptStatus = Literal[
    "ai_draft",
    "draft",
    "in_review",
    "pending_approval",
    "approved",
    "rejected",
    "executed",
    "deprecated",
    "blocked",
]


class AutomationScriptUpdate(BaseModel):
    framework: Literal["playwright", "pytest"] | None = None
    file_path: str | None = None
    code: str | None = None
    setup_required: list[str] | None = None
    execution_command: str | None = None
    status: AutomationScriptStatus | None = None


class AgentAutomationTrigger(BaseModel):
    project_id: int
    test_case_ids: list[int]
    framework: Literal["playwright", "pytest"] = "playwright"
    source: Literal["approved_test_case", "manual_conversion"] = "approved_test_case"

    @field_validator("test_case_ids")
    @classmethod
    def test_case_ids_non_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("test_case_ids must contain at least one ID")
        return v


class AgentMCPDiscoveryTrigger(BaseModel):
    """Phase 3 — triggers the Playwright MCP Discovery Agent for a batch of
    test cases against a specific environment."""
    project_id: int
    test_case_ids: list[int]
    environment: str = "QA"

    @field_validator("test_case_ids")
    @classmethod
    def test_case_ids_non_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("test_case_ids must contain at least one ID")
        return v


ScriptTransitionAction = Literal["submit_for_review", "request_changes", "restore_draft"]


class ScriptTransitionRequest(BaseModel):
    action: ScriptTransitionAction
    notes: str | None = None


class RecommendationDecisionRequest(BaseModel):
    action: Literal["apply", "dismiss"]
    notes: str | None = None


class BulkScriptApprovalRequest(BaseModel):
    script_ids: list[int]
    action: Literal["approve", "reject"]
    notes: str | None = None


LifecycleApprovalAction = Literal[
    "reviewer_approve", "reviewer_reject",
    "lead_approve", "lead_reject",
    "environment_approve",
    "mark_ci_ready",
]


class LifecycleApprovalRequest(BaseModel):
    """Phase 4.6: one step of the staged post-generation approval chain —
    dry_run_passed -> reviewer_approved -> lead_approved
    -> [environment_approve, required for PROD_SANITY] -> ci_ready."""
    action: LifecycleApprovalAction
    notes: str | None = None


class AutomationConfidenceScoreOut(BaseModel):
    overall: float
    locator_confidence: float
    assertion_confidence: float
    data_readiness: float
    environment_readiness: float
    dry_run_stability: float


class BulkScriptApprovalResult(BaseModel):
    script_id: int
    ok: bool
    error: str | None = None


class BulkScriptApprovalResponse(BaseModel):
    results: list[BulkScriptApprovalResult]
    approved_count: int
    failed_count: int


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


class AutomationFrameworkOption(BaseModel):
    key: Literal["playwright", "pytest"]
    label: str
    language: str
    runner_family: str
    primary_use_cases: list[str]


class AutomationPlanningCandidateOut(BaseModel):
    test_case_id: int
    test_case_key: str
    title: str
    test_type: str | None = None
    automation_status: str
    automation_ready: bool
    mapping_status: str
    execution_handoff: Literal["draft_generation", "human_review", "repository_ready", "ready_for_execution"]
    recommended_framework: Literal["playwright", "pytest"]
    secondary_framework: Literal["playwright", "pytest"]
    hybrid_ready: bool = False
    recommended_language: str
    assessment_score: int
    assessment_band: Literal["high", "medium", "low"]
    assessment_reasons: list[str] = Field(default_factory=list)
    framework_reasons: list[str] = Field(default_factory=list)
    framework_scores: dict[str, int] = Field(default_factory=dict)
    script_id: int | None = None
    linked_script_ids: list[int] = Field(default_factory=list)
    script_status: str | None = None
    repository: str | None = None
    branch: str | None = None
    script_path: str | None = None
    last_execution_status: str | None = None
    last_execution_at: datetime | None = None
    inferred_suite: str | None = None
    coverage_hint: str | None = None
    updated_at: datetime | None = None
    framework_options: list[AutomationFrameworkOption] = Field(default_factory=list)
    # The real Test Suite tag (TestCase.test_suite_id) — distinct from
    # `inferred_suite`, which is a free-form label the LLM wrote into script
    # metadata. Used to group candidates into "Run by Suite" batch runs.
    test_suite_id: int | None = None
    test_suite_name: str | None = None


class AutomationPlanningSummaryOut(BaseModel):
    total_candidates: int
    ready_for_generation: int
    pending_review: int
    repository_ready: int
    ready_for_execution: int
    by_framework: dict[str, int]
    by_handoff: dict[str, int]
    supported_frameworks: list[AutomationFrameworkOption]
    available_environments: list[str]
    available_browsers: list[str]


class AutomationPlanningOut(BaseModel):
    project_id: int
    summary: AutomationPlanningSummaryOut
    candidates: list[AutomationPlanningCandidateOut]


# ── Local runner ─────────────────────────────────────────────────────────────


class AutomationScriptExecuteRequest(BaseModel):
    """Request to run an approved script via the local subprocess runner."""
    environment: str | None = Field(default="staging", max_length=100)
    timeout_seconds: int = Field(default=600, ge=30, le=3600)


class AutomationScriptExecuteResponse(BaseModel):
    execution_run_id: int
    task_id: str | None = None
    status: str  # "queued"
    message: str


class AutomationBatchExecuteRequest(BaseModel):
    """Request to run several approved scripts as one batch ("Run All Eligible")."""
    script_ids: list[int] = Field(min_length=1, max_length=200)
    environment: str | None = Field(default="staging", max_length=100)
    timeout_seconds: int = Field(default=600, ge=30, le=3600)
    run_name: str | None = Field(default=None, max_length=255)
    # Set when this batch is a "Retry Failed" of an earlier run — recorded in
    # metadata_ for lineage; not enforced server-side beyond that.
    parent_run_id: int | None = None


class AutomationBatchExecuteResponse(BaseModel):
    execution_run_id: int
    task_id: str | None = None
    status: str  # "queued"
    script_count: int
    message: str


class RunnerFrameworkStatus(BaseModel):
    framework: str
    available: bool
    detail: str


class RunnerStatusOut(BaseModel):
    frameworks: list[RunnerFrameworkStatus]


class AutomationRunCancelResponse(BaseModel):
    execution_run_id: int
    status: str
    message: str
