"""Pydantic schemas for Test Execution."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ManualStepStatus = Literal["not_run", "in_progress", "passed", "failed", "blocked", "skipped"]


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
    execution_type: str = "manual"
    test_cycle_id: str | None = None
    source_type: str | None = None
    external_tool_name: str | None = None
    external_run_id: str | None = None
    suite_name: str | None = None
    environment: str | None = None
    status: str
    triggered_by: int | None = None
    triggered_by_name: str | None = None
    # Resolved live from the Test Cases module: test_suite_name via
    # TestCase.test_suite_id -> TestSuite.name, test_environment via
    # TestCase.test_phase (the field the Test Cases screen itself labels
    # "Test Environment"). Distinct from `suite_name` above, which is just
    # the free-text title given to this run at creation time.
    test_suite_name: str | None = None
    test_environment: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    total_tests: int
    passed: int
    failed: int
    skipped: int
    confidence_score: float | None = None
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


# ── Manual Execution ──────────────────────────────────────────────────────────


class ManualEvidenceOut(BaseModel):
    id: str
    filename: str
    size: int
    content_type: str | None = None
    uploaded_at: datetime
    download_url: str


class ManualStepResultOut(BaseModel):
    id: int
    execution_result_id: int
    step_number: int
    action_text: str | None = None
    expected_text: str | None = None
    status: ManualStepStatus
    actual_result: str | None = None
    comments: str | None = None
    evidence: list[ManualEvidenceOut] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_by: int | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class ManualStepUpdate(BaseModel):
    status: ManualStepStatus | None = None
    actual_result: str | None = None
    comments: str | None = None


class ManualResultDetail(BaseModel):
    result: ExecutionResultOut
    steps: list[ManualStepResultOut]


class ManualRunDetail(BaseModel):
    run: ExecutionRunOut
    results: list[ManualResultDetail]


class ManualRunStart(BaseModel):
    project_id: int
    test_case_ids: list[int] = Field(..., min_length=1)
    # Free-form so real enterprise environments (SIT, UAT, INT, dev1, …)
    # work without an allowlist. Stored in execution_runs.environment (varchar 100).
    environment: str | None = Field(default="staging", max_length=100)
    suite_name: str | None = None
    # Optional: bind one TestDataRecord per test case. Step text containing
    # ${field} placeholders is substituted at run-start and snapshotted onto
    # the ManualStepResult rows. Map: test_case_id -> test_data_record_id.
    bound_data_records: dict[int, int] = Field(default_factory=dict)


# ── Execution Dashboard ───────────────────────────────────────────────────────


class DashboardKpis(BaseModel):
    total_executions: int
    total_test_cases: int
    passed: int
    failed: int
    skipped: int
    blocked: int
    in_progress: int
    review_required: int
    avg_execution_seconds: float
    total_execution_seconds: float
    overall_pass_rate: float


class DashboardByType(BaseModel):
    execution_type: str
    run_count: int
    total_tests: int
    passed: int
    failed: int
    skipped: int
    blocked: int
    in_progress: int
    pass_rate: float


class DashboardByEnvironment(BaseModel):
    environment: str
    run_count: int


class DashboardByModule(BaseModel):
    module: str
    executions: int
    failures: int


class DashboardTrendPoint(BaseModel):
    date: str
    manual: int = 0
    automation: int = 0
    ai: int = 0
    hybrid: int = 0


class DashboardRecentRun(BaseModel):
    id: int
    execution_id: str
    execution_type: str
    status: str
    environment: str | None = None
    suite_name: str | None = None
    total_tests: int
    passed: int
    failed: int
    started_at: str | None = None
    duration_seconds: float | None = None
    triggered_by_name: str | None = None
    confidence_score: float | None = None


class DashboardDefects(BaseModel):
    total: int
    by_type: dict[str, int] = Field(default_factory=dict)


class DashboardInsight(BaseModel):
    kind: str
    title: str
    body: str


class DashboardFilters(BaseModel):
    project_id: int
    environment: str | None = None
    execution_type: str | None = None
    date_from: str | None = None
    date_to: str | None = None


class ExecutionDashboardResponse(BaseModel):
    kpis: DashboardKpis
    by_type: list[DashboardByType]
    by_environment: list[DashboardByEnvironment]
    by_module: list[DashboardByModule]
    trend: list[DashboardTrendPoint]
    recent_runs: list[DashboardRecentRun]
    defects: DashboardDefects
    insights: list[DashboardInsight]
    filters_applied: DashboardFilters


# ── AI Execution Lifecycle ────────────────────────────────────────────────────


class AiRunStart(BaseModel):
    project_id: int
    test_case_ids: list[int] = Field(..., min_length=1)
    environment: str | None = Field(default="staging", max_length=100)
    agent_name: str = Field(default="nxtQA AI Agent v2.1", max_length=200)
    model: str | None = Field(default=None, max_length=200)
    suite_name: str | None = None
    # Override per-run confidence threshold; falls back to platform default.
    confidence_threshold: int | None = Field(default=None, ge=0, le=100)
    # "autonomous" lets the run auto-publish if the policy passes;
    # "supervised" always parks the run in review_required for a human.
    mode: Literal["autonomous", "supervised"] = "autonomous"


class AiRunGovernance(BaseModel):
    ai_confidence_threshold: int
    ai_autonomous_environments: list[str]
    ai_require_evidence_for_pass: bool
    ai_run_max_seconds: int


class AiRunReviewDecision(BaseModel):
    decision: Literal["approve", "override", "request_rerun", "reject"]
    reason: str = Field(..., min_length=1, max_length=1000)
    override_status: Literal["completed", "failed", "auto_completed", "cancelled"] | None = None


class AiRunStepOut(BaseModel):
    """Per-step view of an AI execution. Reads from ExecutionResult + metadata."""
    step_number: int
    step_description: str
    expected_result: str | None = None
    actual_result: str | None = None
    status: str
    confidence: int | None = None
    evidence_urls: list[str] = Field(default_factory=list)
    reasoning_summary: str | None = None


class AiRunDetail(BaseModel):
    run: ExecutionRunOut
    results: list[ExecutionResultOut]
    governance: AiRunGovernance
    review_log: list[dict[str, Any]] = Field(default_factory=list)


class AiAssistResponse(BaseModel):
    """Returned by POST /execution/manual/steps/{id}/ai-assist.

    `suggested_status` is the LLM's recommendation; the frontend only applies it
    if the tester clicks "Use suggestion". `confidence` is 0-100 and `reasoning`
    is human-friendly. The suggestion is also persisted on the step's metadata
    so the audit trail records what the AI advised, separate from what the
    tester chose.
    """
    suggested_status: Literal["pass", "fail", "blocked"]
    confidence: int = Field(..., ge=0, le=100)
    reasoning: str
    observations: list[str] = Field(default_factory=list)
    inputs_used: dict[str, Any] = Field(default_factory=dict)
    raw_response: str | None = None

