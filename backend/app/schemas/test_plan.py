"""Pydantic schemas for test plans, scenarios, and test cases."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


# Phase 5: per-TC AI assistance state. Mirrors the model default of "disabled"
# so existing consumers that don't pass the field get the safe value.
AiAssistanceStatus = Literal[
    "disabled",
    "enabled",
    "recommendation_pending",
    "approved",
    "rejected",
]


# ── Test Plan ─────────────────────────────────────────────────────────────────

class TestPlanOut(BaseModel):
    id: int
    project_id: int
    test_plan_id: str
    title: str
    scope: list | None = None
    out_of_scope: list | None = None
    test_types: list | None = None
    entry_criteria: list | None = None
    exit_criteria: list | None = None
    risks: list | None = None
    mitigations: list | None = None
    automation_candidates: list | None = None
    estimated_effort: str | None = None
    resource_recommendation: str | None = None
    status: str
    agent_run_id: int | None = None
    created_by: int
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestPlanUpdate(BaseModel):
    title: str | None = None
    scope: list | None = None
    out_of_scope: list | None = None
    test_types: list | None = None
    entry_criteria: list | None = None
    exit_criteria: list | None = None
    risks: list | None = None
    mitigations: list | None = None
    automation_candidates: list | None = None
    estimated_effort: str | None = None
    resource_recommendation: str | None = None
    status: str | None = None


# ── Test Scenario ─────────────────────────────────────────────────────────────

class TestScenarioOut(BaseModel):
    id: int
    project_id: int
    requirement_id: int | None = None
    scenario_id: str
    title: str
    description: str | None = None
    scenario_type: str | None = None
    priority: str
    coverage_mapping: list | None = None
    status: str
    agent_run_id: int | None = None
    created_by: int
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Test Case ─────────────────────────────────────────────────────────────────

class TestCaseOut(BaseModel):
    id: int
    project_id: int
    scenario_id: int | None = None
    requirement_id: int | None = None
    test_case_id: str
    title: str
    preconditions: list | None = None
    test_data: dict | None = None
    steps: list | None = None
    expected_result: str | None = None
    bdd_scenario: str | None = None
    priority: str
    severity: str
    test_type: str | None = None
    automation_candidate: bool
    mode: str
    execution_mode: str
    automation_eligible: str
    automation_status: str
    automation_ready: bool = False
    ai_assistance_status: AiAssistanceStatus = "disabled"
    test_phase: str | None = None
    telecom_domain: str | None = None
    product_group: str | None = None
    product: str | None = None
    sub_request_type: str | None = None
    application_id: int | None = None
    external_tool: str | None = None
    suite_id: str | None = None
    test_suite_id: int | None = None
    test_suite_name: str | None = None
    external_tc_id: str | None = None
    external_tc_url: str | None = None
    automation_script_id: int | None = None
    last_automation_status: str | None = None
    last_automation_run_at: datetime | None = None
    last_execution_run_id: int | None = None
    latest_evidence_available: bool = False
    evidence_url: str | None = None
    jira_issue_key: str | None = None
    jira_issue_id: str | None = None
    jira_url: str | None = None
    jira_final_status: str | None = None
    jira_sync_status: str = "not_synced"
    jira_last_synced_at: datetime | None = None
    jira_sync_error: str | None = None
    jira_test_key: str | None = None
    approval_status: str
    linked_requirement_id: int | None = None
    linked_requirement_key: str | None = None
    linked_scenario_id: int | None = None
    linked_application_id: int | None = None
    linked_project_id: int | None = None
    linked_release_version: str | None = None
    linked_test_plan_id: int | None = None
    created_by: int
    updated_by: int | None = None
    last_status_updated_by: int | None = None
    last_status_updated_at: datetime | None = None
    status: str
    version: int = 1
    agent_run_id: int | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestCaseUpdate(BaseModel):
    requirement_id: int | None = None
    scenario_id: int | None = None
    title: str | None = None
    preconditions: list | None = None
    test_data: dict | None = None
    steps: list | None = None
    expected_result: str | None = None
    bdd_scenario: str | None = None
    priority: str | None = None
    severity: str | None = None
    test_type: str | None = None
    automation_candidate: bool | None = None
    mode: str | None = None
    execution_mode: str | None = None
    automation_eligible: str | None = None
    automation_status: str | None = None
    automation_ready: bool | None = None
    ai_assistance_status: AiAssistanceStatus | None = None
    test_phase: str | None = None
    telecom_domain: str | None = None
    product_group: str | None = None
    product: str | None = None
    sub_request_type: str | None = None
    application_id: int | None = None
    external_tool: str | None = None
    suite_id: str | None = None
    test_suite_id: int | None = None
    external_tc_id: str | None = None
    external_tc_url: HttpUrl | None = None
    automation_script_id: int | None = None
    last_automation_status: str | None = None
    jira_issue_id: str | None = None
    jira_url: HttpUrl | None = None
    jira_final_status: str | None = None
    jira_sync_status: str | None = None
    jira_sync_error: str | None = None
    jira_issue_key: str | None = None
    jira_test_key: str | None = None
    status: str | None = None
    approval_status: str | None = None
    metadata_: dict[str, Any] | None = None
    comment: str | None = None


# ── Bulk update ───────────────────────────────────────────────────────────────


class TestCaseBulkPatch(BaseModel):
    """Per-bulk-call patch — every field is optional. Only non-None fields
    are applied to each selected test case. Empty string means "clear" for the
    free-text fields (external_tool, suite_id, external_tc_id)."""
    execution_mode: str | None = None
    automation_status: str | None = None
    automation_ready: bool | None = None
    external_tool: str | None = None
    suite_id: str | None = None
    test_suite_id: int | None = None
    external_tc_id: str | None = None


class TestCaseBulkUpdateRequest(BaseModel):
    test_case_ids: list[int] = Field(..., min_length=1, max_length=500)
    patch: TestCaseBulkPatch
    reason: str = Field(..., min_length=1, max_length=500,
                        description="Required audit comment shown to reviewers")
    dry_run: bool = Field(default=False,
                          description="When true, returns the per-row analysis without persisting anything")

    @field_validator("reason")
    @classmethod
    def _reason_must_have_content(cls, v: str) -> str:
        # Pydantic's min_length=1 only checks raw length, so "   " (whitespace) slips
        # through. Strip first so the audit trail can't be filled with blank reasons.
        stripped = v.strip()
        if not stripped:
            raise ValueError("reason cannot be empty or whitespace-only")
        return stripped


class TestCaseBulkRowOutcome(BaseModel):
    test_case_id: int
    test_case_key: str | None = None
    title: str | None = None
    # "updated" (changes applied) | "skipped" (nothing to change for this row) |
    # "conflict" (would silently corrupt state — see `conflict_reason`) |
    # "not_found" | "forbidden" (different project)
    outcome: str
    changes: dict[str, dict[str, Any]] = Field(default_factory=dict,
        description="Per-field {old, new} diff applied (or that would be applied in dry-run)")
    conflict_reason: str | None = None


class TestCaseBulkUpdateResult(BaseModel):
    requested: int
    updated: int
    skipped: int
    conflicts: int
    not_found: int
    forbidden: int
    dry_run: bool
    rows: list[TestCaseBulkRowOutcome]


class TestCaseHistoryOut(BaseModel):
    id: int
    project_id: int
    test_case_id: int
    changed_by: int | None = None
    field_name: str
    old_value: str | None = None
    new_value: str | None = None
    source: str
    comment: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TestCaseSummaryOut(BaseModel):
    total: int
    by_status: dict[str, int]
    by_approval_status: dict[str, int]
    by_automation_status: dict[str, int]
    by_mode: dict[str, int]
    by_jira_sync_status: dict[str, int]
    by_priority: dict[str, int]
    by_telecom_domain: dict[str, int]


class TestCaseJiraSyncOut(BaseModel):
    test_case_id: int
    status: str
    sync_job_id: int | None = None
    task_id: str | None = None


class AgentPlanTrigger(BaseModel):
    project_id: int
    requirement_ids: list[int]
    # GAP-4c: set true to generate despite failed/low-quality requirements
    override_quality_gate: bool = False


class AgentCaseTrigger(BaseModel):
    project_id: int
    scenario_ids: list[int] | None = None
    requirement_ids: list[int] | None = None
    # GAP-4c: set true to generate despite failed/low-quality requirements
    override_quality_gate: bool = False
