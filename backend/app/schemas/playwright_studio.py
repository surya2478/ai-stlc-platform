"""Pydantic schemas for the Playwright AI Studio endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

ALLOWED_COVERAGE_TYPES = {"positive", "negative", "boundary", "e2e"}


class StudioRunCreate(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=255)
    application_id: int
    environment: str = Field(min_length=1, max_length=80)
    objective: str = Field(default="", max_length=500)
    coverage_types: list[str] = Field(default_factory=lambda: ["positive", "negative"])
    excluded_paths: list[str] = Field(default_factory=list, max_length=50)
    browser: str = Field(default="chromium", max_length=30)
    max_pages: int = Field(default=10, ge=1, le=25)
    max_minutes: int = Field(default=20, ge=1, le=60)
    # Optional hard cap on total proposed test cases across ALL explored
    # pages. Each page proposes independently (2-8 per page, see
    # planner_agent.MAX_PROPOSALS_PER_PAGE) with no built-in awareness of a
    # global target, so this is enforced deterministically after collection
    # (studio_service._apply_test_case_cap / planner_agent), never left to
    # the LLM to self-limit across calls it can't coordinate.
    target_test_case_count: int | None = Field(default=None, ge=1, le=200)
    framework: str = Field(default="playwright", pattern="^(playwright|pytest)$")
    # None means "let the server decide" — the runner policy owns this
    # (AUT-018). Defaulting to "local" here pinned every Studio batch to the
    # least isolated runner regardless of how the deployment was configured,
    # and would now simply be refused wherever local mode is not permitted.
    runner_mode: str | None = Field(default=None, pattern="^(local|docker|executor)$")
    parallelism: int = Field(default=4, ge=1, le=16)
    timeout_seconds: int = Field(default=600, ge=30, le=3600)

    def model_post_init(self, __context) -> None:
        self.coverage_types = [c for c in self.coverage_types if c in ALLOWED_COVERAGE_TYPES] or ["positive"]
        self.excluded_paths = [p.strip() for p in self.excluded_paths if p and p.strip()]


class StudioRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_by: int
    name: str
    status: str
    config: dict
    error: str | None = None
    # Optional: server-default timestamps are only populated after a real
    # DB round-trip (they're always present in production responses).
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentRunSummary(BaseModel):
    id: int
    status: str
    progress_percent: int = 0
    progress_message: str | None = None
    error_message: str | None = None
    # Carried so the UI can show elapsed time and distinguish "working slowly"
    # from "stuck" without polling a second endpoint.
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StudioAgentRunsOut(BaseModel):
    planner: AgentRunSummary | None = None
    generation: list[AgentRunSummary] = Field(default_factory=list)


class StudioScriptSummary(BaseModel):
    id: int
    script_id: str
    test_case_id: int | None = None
    status: str
    version: int
    framework: str | None = None
    grounding: dict | None = None
    static_gate_passed: bool | None = None
    last_dry_run: dict | None = None


class StudioExecutionSummary(BaseModel):
    id: int
    execution_id: str
    status: str
    total_tests: int
    passed: int
    failed: int
    skipped: int
    # Auto-heal outcome for Studio batches: attempted / repaired /
    # not_repairable / errors / new_script_ids / capped.
    auto_heal: dict | None = None


class StudioFailureInsight(BaseModel):
    """Actionable, non-functional diagnostic derived from a run's failures
    (environment unreachable, runner infrastructure, auth/route problems,
    test data) so the user knows what to fix — distinct from per-test
    functional verdicts."""
    kind: str
    severity: str  # error | warning | info
    message: str
    action: str
    count: int
    examples: list[str] = Field(default_factory=list)


class StudioRunDetailOut(StudioRunOut):
    plan: dict | None = None
    test_case_ids: list[int] | None = None
    agent_runs: StudioAgentRunsOut = Field(default_factory=StudioAgentRunsOut)
    scripts: list[StudioScriptSummary] = Field(default_factory=list)
    script_counts: dict[str, int] = Field(default_factory=dict)
    executions: list[StudioExecutionSummary] = Field(default_factory=list)
    failure_insights: list[StudioFailureInsight] = Field(default_factory=list)
    # Whether a retry is available, and from which stage — see studio_service.can_retry.
    can_retry: bool = False
    # Test cases in this run whose latest script failed — what "regenerate only
    # the failed ones" would act on.
    failed_test_case_ids: list[int] = Field(default_factory=list)


class StudioStartResponse(BaseModel):
    studio_run_id: int
    agent_run_id: int
    task_id: str | None = None
    status: str
    message: str


class ApprovePlanRequest(BaseModel):
    # None = every proposal the planner didn't flag as blocked. Explicit
    # keys can include blocked proposals — a deliberate, audited choice.
    included_keys: list[str] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ApprovePlanResponse(BaseModel):
    studio_run_id: int
    status: str
    test_case_count: int
    wave_count: int
    message: str


class ApproveScriptsRequest(BaseModel):
    # Required only when any script has a known quality issue
    # (approval_override_reason) — enforced by studio_service.
    notes: str | None = Field(default=None, max_length=2000)


class ApproveScriptsResponse(BaseModel):
    studio_run_id: int
    status: str
    approved_script_count: int
    execution_run_ids: list[int]
    message: str


class StudioCancelResponse(BaseModel):
    studio_run_id: int
    status: str
    message: str


class StudioRetryRequest(BaseModel):
    # Optional because most retries want the same configuration. Present when
    # the previous attempt failed *because* of the mode it ran in.
    runner_mode: str | None = None
    # Regenerate only the test cases whose scripts failed, leaving the ones
    # that work untouched.
    only_failed: bool = False


class StudioRetryResponse(BaseModel):
    studio_run_id: int
    status: str
    # Which stage was resumed — "generation" reuses the approved test cases,
    # "exploration" starts the crawl again because nothing approvable existed.
    stage: str
    agent_run_ids: list[int]
    execution_run_ids: list[int] = Field(default_factory=list)
    test_case_count: int
    message: str
