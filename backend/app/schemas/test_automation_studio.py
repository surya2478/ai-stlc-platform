"""Pydantic contracts for the Test Automation Studio module."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DocRole = Literal["brd", "srd", "test_cases", "other"]
RequirementOrigin = Literal["extracted", "derived"]
CoverageState = Literal["covered", "partially_covered", "uncovered"]
ApprovalStatus = Literal["draft", "pending_approval", "approved", "rejected"]
Classification = Literal["automation", "manual", "undecided"]
TestDataStatus = Literal["not_required", "agent_provided", "needs_user_action", "user_provided"]
Framework = Literal["playwright", "katalon", "appium"]

SUPPORTED_FRAMEWORKS: tuple[str, ...] = ("playwright", "katalon", "appium")

# Which language each framework's generated asset is written in. Fixed per
# framework rather than user-selectable: a Katalon test case is Groovy and an
# Appium test here is Python, and offering a language picker that silently
# does nothing would be worse than not offering one.
FRAMEWORK_LANGUAGES: dict[str, str] = {
    "playwright": "typescript",
    "katalon": "groovy",
    "appium": "python",
}


# ── Screen 1: intake ─────────────────────────────────────────────────────────

def normalize_application_url(value: str | None) -> str | None:
    """Reject anything that is not an http(s) URL.

    The value ends up in a generated script's `page.goto(...)` and is written
    back into the application's environment_urls, so a `javascript:` or
    `file:` scheme here would be a script-injection vector rather than a
    typo.
    """
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if not trimmed.startswith(("http://", "https://")):
        raise ValueError("Application URL must start with http:// or https://")
    return trimmed


class IntakeBatchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    application_id: int | None = None
    application_url: str | None = None
    application_environment: str = "qa"

    @field_validator("application_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return normalize_application_url(value)


class IntakeBatchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    application_id: int | None = None
    application_url: str | None = None
    application_environment: str | None = None

    @field_validator("application_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return normalize_application_url(value)


class IntakeDocumentAttach(BaseModel):
    """Attach an already-uploaded document to a batch.

    Upload goes through the existing POST /documents/upload endpoint — this
    module does not re-implement storage, extraction or file validation.
    """

    document_id: int
    doc_role: DocRole = "other"


class IntakeDocumentBulkAttach(BaseModel):
    documents: list[IntakeDocumentAttach] = Field(min_length=1)


class IntakeDocumentOut(BaseModel):
    id: int
    batch_id: int
    document_id: int
    doc_role: DocRole
    extraction_status: str
    extraction_error: str | None = None
    # The uploaded document's own status and whether its text has landed yet.
    # Extraction is a background job, so a freshly uploaded document is
    # attached but not yet assessable.
    document_status: str = "unknown"
    text_available: bool = False
    ready_for_assessment: bool = False
    extracted_requirement_count: int
    extracted_test_case_count: int
    original_filename: str | None = None
    file_type: str | None = None
    file_size_bytes: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntakeBatchOut(BaseModel):
    id: int
    project_id: int
    name: str
    description: str | None = None
    application_id: int | None = None
    application_url: str | None = None
    application_environment: str
    status: str
    status_error: str | None = None
    created_by: int
    created_at: datetime
    updated_at: datetime
    documents: list[IntakeDocumentOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CoverageAssessmentOut(BaseModel):
    id: int
    project_id: int
    batch_id: int
    version: int
    is_current: bool
    status: str
    error: str | None = None
    total_requirements: int
    covered_requirements: int
    partially_covered_requirements: int
    uncovered_requirements: int
    existing_test_case_count: int
    derived_requirement_count: int
    coverage_percent: int
    coverage_rows: list = Field(default_factory=list)
    extracted_test_cases: list = Field(default_factory=list)
    gap_summary: dict = Field(default_factory=dict)
    agent_run_id: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DerivedRequirementOut(BaseModel):
    id: int
    project_id: int
    batch_id: int
    assessment_id: int | None = None
    requirement_key: str
    title: str
    summary: str | None = None
    acceptance_criteria: list = Field(default_factory=list)
    business_rules: list = Field(default_factory=list)
    ui_pages: list = Field(default_factory=list)
    apis: list = Field(default_factory=list)
    test_data_needs: list = Field(default_factory=list)
    origin: RequirementOrigin
    coverage_state: CoverageState
    gap_reason: str | None = None
    source_refs: list = Field(default_factory=list)
    covering_test_case_refs: list = Field(default_factory=list)
    automation_relevance: str | None = None
    priority: str
    status: ApprovalStatus
    decision_reason: str | None = None
    approved_by: int | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DerivedRequirementUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    summary: str | None = None
    acceptance_criteria: list | None = None
    priority: str | None = None
    automation_relevance: str | None = None


class BulkRequirementDecision(BaseModel):
    requirement_ids: list[int] = Field(min_length=1)
    decision: Literal["approve", "reject"]
    reason: str | None = None


class AssessCoverageRequest(BaseModel):
    """Screen 1's "Assess Coverage for Automation" action."""

    application_id: int | None = None
    application_url: str | None = None
    application_environment: str | None = None
    # When true the assessment also proposes new requirements for behaviours
    # the documents describe but the supplied test cases never exercise. Off
    # would make the screen a pure report; the requirement asks for the
    # derivation, so it defaults on.
    derive_gap_requirements: bool = True

    @field_validator("application_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return normalize_application_url(value)


class AssessCoverageResponse(BaseModel):
    assessment: CoverageAssessmentOut
    requirements: list[DerivedRequirementOut]


class SourceTestCaseOut(BaseModel):
    """A test case read off an uploaded test case document.

    `tc_display_id` and `title` are reproduced exactly as the sheet had them —
    they are what a refined test case inherits, so showing anything normalised
    here would misrepresent what the user is about to get.
    """

    id: int
    project_id: int
    batch_id: int
    assessment_id: int | None = None
    tc_display_id: str
    title: str
    summary: str | None = None
    steps: list = Field(default_factory=list)
    source_document_id: int | None = None
    source_ref: str | None = None
    matched_platform_test_case_id: int | None = None
    # Filled by the endpoint, not stored: the requirements this test case was
    # assessed as covering, and whether Screen 2 has already refined it.
    covers_requirement_ids: list[int] = Field(default_factory=list)
    refined_test_case_id: int | None = None
    refined_status: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Screen 2: refined test cases ─────────────────────────────────────────────

class RefinedStep(BaseModel):
    step_number: int
    action: str
    target: str | None = None
    test_data_ref: str | None = None
    expected_result: str | None = None


class TestDataRequirementOut(BaseModel):
    """One test data need the agent identified for a test case."""

    key: str
    description: str | None = None
    example_value: str | None = None
    sensitive: bool = False
    # resolution: agent_generated | existing_record | user_required
    resolution: str = "user_required"
    test_data_id: int | None = None


class RefinedTestCaseOut(BaseModel):
    id: int
    project_id: int
    batch_id: int | None = None
    derived_requirement_id: int | None = None
    source_test_case_id: int | None = None
    source_uploaded_test_case_id: int | None = None
    origin: Literal["existing", "imported", "derived"]
    tc_display_id: str
    title: str
    objective: str | None = None
    preconditions: list = Field(default_factory=list)
    steps: list = Field(default_factory=list)
    expected_result: str | None = None
    bdd_scenario: str | None = None
    application_id: int | None = None
    application_url: str | None = None
    priority: str
    test_type: str | None = None
    classification: Classification
    classification_source: str | None = None
    classification_reason: str | None = None
    manual_only_reasons: list = Field(default_factory=list)
    test_data_required: bool
    test_data_status: TestDataStatus
    test_data_notes: str | None = None
    test_data_requirements: list = Field(default_factory=list)
    test_data_ids: list = Field(default_factory=list)
    status: ApprovalStatus
    decision_reason: str | None = None
    approved_by: int | None = None
    approved_at: datetime | None = None
    version: int
    is_current: bool
    edited_by_user: bool
    agent_run_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GenerateRefinedTestCasesRequest(BaseModel):
    """Screen 2's generate action, which has two entry points.

    `source_test_case_ids` are uploaded test cases (TasSourceTestCase). Each is
    refined in place: it keeps the ID and name off the sheet and gains
    automation-ready detail, with the requirements it covers passed as context.
    Documents are the context; the test case is the anchor.

    `requirement_ids` are approved TasDerivedRequirement rows and cover the
    other case — a behaviour the documents describe that no uploaded test case
    exercises. There is no ID to preserve, so a new test case is created.
    Any platform `test_cases` row the assessment matched to one of those
    requirements is refined alongside them, keeping its own ID and title.

    At least one of the two lists must be non-empty; requiring both would make
    a project with full coverage unable to refine anything, and a project with
    no test cases at all unable to close its gaps.
    """

    requirement_ids: list[int] = Field(default_factory=list)
    source_test_case_ids: list[int] = Field(default_factory=list)
    application_id: int | None = None
    application_environment: str | None = None
    include_existing_test_cases: bool = True
    regenerate: bool = False

    @model_validator(mode="after")
    def _require_a_source(self) -> "GenerateRefinedTestCasesRequest":
        if not self.requirement_ids and not self.source_test_case_ids:
            raise ValueError(
                "Select at least one uploaded test case or approved requirement to refine."
            )
        return self


class GenerateRefinedTestCasesResponse(BaseModel):
    generated: list[RefinedTestCaseOut]
    skipped: list[dict] = Field(default_factory=list)
    agent_run_id: int | None = None


class RefinedTestCaseUpdate(BaseModel):
    """Editing a refined test case.

    `tc_display_id` is absent by design: an existing test case keeps the ID it
    already has in the platform, and a derived one keeps the ID the studio
    assigned. Letting either be retyped here would break the link back to the
    source test case and to any script already generated from it.
    """

    title: str | None = Field(default=None, min_length=1, max_length=500)
    objective: str | None = None
    preconditions: list | None = None
    steps: list | None = None
    expected_result: str | None = None
    bdd_scenario: str | None = None
    application_id: int | None = None
    application_url: str | None = None
    priority: str | None = None
    test_type: str | None = None
    test_data_required: bool | None = None
    test_data_status: TestDataStatus | None = None
    test_data_notes: str | None = None
    test_data_requirements: list | None = None
    test_data_ids: list | None = None


class BulkClassifyRequest(BaseModel):
    """Bulk Automation/Manual classification.

    With `classification` unset the project's published automation
    classification policy decides each case — that is the "based on
    configuration in the project settings" path. Setting it explicitly is a
    manual override and is recorded as `classification_source='manual'`.
    """

    test_case_ids: list[int] = Field(min_length=1)
    classification: Classification | None = None
    reason: str | None = None


class BulkClassifyResponse(BaseModel):
    updated: list[RefinedTestCaseOut]
    policy_id: int | None = None
    policy_version: int | None = None
    unresolved: list[dict] = Field(default_factory=list)


class BulkTestCaseDecision(BaseModel):
    test_case_ids: list[int] = Field(min_length=1)
    decision: Literal["approve", "reject"]
    reason: str | None = None


class BulkDecisionResponse(BaseModel):
    updated: list[RefinedTestCaseOut]
    blocked: list[dict] = Field(default_factory=list)


# ── Screen 3: script lab ─────────────────────────────────────────────────────

class ScriptAssetOut(BaseModel):
    id: int
    project_id: int
    refined_test_case_id: int
    framework: Framework
    language: str
    script_key: str
    code: str
    files: dict = Field(default_factory=dict)
    execution_command: str | None = None
    setup_notes: list = Field(default_factory=list)
    status: str
    version: int
    is_current: bool
    edited_by_user: bool
    generation_error: str | None = None
    agent_run_id: int | None = None
    created_at: datetime
    updated_at: datetime
    # Denormalised for the grid so the client need not join every row.
    test_case_display_id: str | None = None
    test_case_title: str | None = None

    model_config = ConfigDict(from_attributes=True)


class GenerateScriptsRequest(BaseModel):
    test_case_ids: list[int] = Field(min_length=1)
    framework: Framework
    regenerate: bool = False


class GenerateScriptsResponse(BaseModel):
    generated: list[ScriptAssetOut]
    skipped: list[dict] = Field(default_factory=list)
    agent_run_id: int | None = None


class ScriptAssetUpdate(BaseModel):
    code: str | None = None
    files: dict | None = None
    execution_command: str | None = None
    setup_notes: list | None = None


class ScriptDecision(BaseModel):
    decision: Literal["approve", "reopen"]
    reason: str | None = None


# ── Shared ───────────────────────────────────────────────────────────────────

class StudioJobOut(BaseModel):
    """Acknowledgement for a queued studio job.

    The studio's three heavy operations return this instead of their results:
    each runs one or more LLM calls over minutes, which no HTTP hop will hold
    open. Poll GET /api/v1/agent-runs/{agent_run_id} for `status`,
    `progress_percent` and `progress_message`, then re-read the screen's own
    list endpoint when the run reaches a terminal status.
    """

    agent_run_id: int
    task_id: str | None = None
    status: str = "queued"
    message: str


class StudioJobStatusOut(BaseModel):
    """Progress of a queued studio job.

    Deliberately not the platform's own /agent-runs/{id}: that endpoint is
    gated on VIEW_AUDIT_LOGS, and watching the job you just started is not the
    same authority as reading a project's audit history. This exposes the
    progress fields only, for studio runs only, behind `tas.view`.
    """

    agent_run_id: int
    agent_name: str
    status: str
    progress_percent: int = 0
    progress_message: str | None = None
    error_message: str | None = None
    output_data: dict | None = None
    created_at: datetime
    updated_at: datetime
    # True once the run has stopped, whatever the outcome. The client stops
    # polling on this rather than matching a status list of its own, so a
    # status nobody anticipated ends the poll instead of spinning forever.
    finished: bool = False

class StudioSummaryOut(BaseModel):
    """Header counts for the studio workspace."""

    batches: int
    requirements_pending: int
    requirements_approved: int
    test_cases_total: int
    test_cases_pending: int
    test_cases_approved: int
    test_cases_automation: int
    test_cases_manual: int
    test_cases_needing_test_data: int
    scripts_total: int
    scripts_by_framework: dict[str, int] = Field(default_factory=dict)
