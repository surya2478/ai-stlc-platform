"""Pydantic contracts for the Test Automation Studio module."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

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


class BatchAuthConfig(BaseModel):
    """The non-secret shape of the application's login form.

    Field labels rather than selectors: discovery matches these against the
    live accessibility tree, which is the same thing a human reads off the
    screen. Asking for a CSS selector would require the user to already know
    what discovery is supposed to find out.
    """

    login_url: str | None = None
    username_label: str | None = None
    password_label: str | None = None
    submit_label: str | None = None

    @field_validator("login_url")
    @classmethod
    def _validate_login_url(cls, value: str | None) -> str | None:
        return normalize_application_url(value)


class IntakeBatchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    application_id: int | None = None
    application_url: str | None = None
    application_environment: str = "qa"
    # Credentials discovery uses to sign in before crawling. `auth_password`
    # is write-only in every direction: it is accepted here, encrypted at
    # rest, and never appears in any response model.
    auth_mode: Literal["none", "form"] = "none"
    auth_config: BatchAuthConfig | None = None
    auth_username: str | None = None
    auth_password: str | None = None

    @field_validator("application_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return normalize_application_url(value)

    @model_validator(mode="after")
    def _credentials_complete(self) -> "IntakeBatchCreate":
        if self.auth_mode == "form" and bool(self.auth_username) != bool(self.auth_password):
            raise ValueError("Provide both a username and a password, or neither.")
        return self


class IntakeBatchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    application_id: int | None = None
    application_url: str | None = None
    application_environment: str | None = None
    auth_mode: Literal["none", "form"] | None = None
    auth_config: BatchAuthConfig | None = None
    auth_username: str | None = None
    auth_password: str | None = None

    @field_validator("application_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return normalize_application_url(value)

    @model_validator(mode="after")
    def _credentials_complete(self) -> "IntakeBatchUpdate":
        if bool(self.auth_username) != bool(self.auth_password):
            raise ValueError("Provide both a username and a password, or neither.")
        return self


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
    auth_mode: Literal["none", "form"] = "none"
    auth_config: dict = Field(default_factory=dict)
    # Whether credentials are stored — never what they are. This is the only
    # thing any route may say about the encrypted secret.
    has_credentials: bool = False
    created_by: int
    created_at: datetime
    updated_at: datetime
    documents: list[IntakeDocumentOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# ── Screen 1: application discovery ──────────────────────────────────────────

class DiscoveryRunOut(BaseModel):
    id: int
    project_id: int
    batch_id: int
    version: int
    is_current: bool
    status: Literal["running", "completed", "failed"]
    application_url: str | None = None
    application_environment: str | None = None
    auth_mode: Literal["none", "form"]
    auth_status: Literal["not_required", "succeeded", "failed", "skipped"]
    auth_detail: str | None = None
    pages_discovered: int
    elements_discovered: int
    explored_pages: list = Field(default_factory=list)
    blockers: list = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DiscoveredElementOut(BaseModel):
    id: int
    page_url: str
    page_title: str | None = None
    element_name: str
    role: str | None = None
    accessible_name: str | None = None
    business_meaning: str | None = None
    recommended_locator: str
    recommended_strategy: str
    confidence_score: int
    href: str | None = None

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
    total_criteria: int = 0
    covered_criteria: int = 0
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
    total_criteria: int = 0
    covered_criteria: int = 0
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
    # Whether each step resolved to an element discovery actually found.
    # `not_checked` means grounding has never run for this test case, which is
    # a different statement from "ran and found nothing" (`ungrounded`).
    grounding_status: Literal["not_checked", "grounded", "partially_grounded", "ungrounded"] = (
        "not_checked"
    )
    grounding_summary: dict | None = None
    grounded_at: datetime | None = None
    discovery_run_id: int | None = None
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def source_missing(self) -> bool:
        """The row this was refined from has since been deleted.

        Both source links are ON DELETE SET NULL, so deleting an uploaded test
        case (or the platform test case behind it) leaves the refined row
        alive with nothing to point at. Nothing recorded that, so the grid
        showed an ordinary row and the "already refined" check — which reads
        the same nulled column — stopped recognising it, quietly refining the
        same behaviour a second time on the next run.

        Derived rather than stored: `tc_display_id` is copied from the source
        and never regenerated, so the row already carries the identity of what
        it came from. Only the fact that the link is gone was missing.
        """
        return (
            self.origin in ("imported", "existing")
            and self.source_uploaded_test_case_id is None
            and self.source_test_case_id is None
        )


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
    # `compiled` went through the Script Compiler and had its locators
    # substituted from the discovered catalog; `freeform` is LLM-authored code
    # that was merely shown the catalog. The screen reports which, because the
    # two carry very different guarantees.
    generation_mode: Literal["compiled", "freeform"] = "freeform"
    entry_path: str | None = None
    static_gate_result: dict | None = None
    grounding: dict | None = None
    dry_run_status: Literal["not_run", "queued", "running", "passed", "failed", "blocked"] = (
        "not_run"
    )
    dry_run_summary: dict | None = None
    dry_run_at: datetime | None = None
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def contract_present(self) -> bool:
        """Whether a contract backs this script, without shipping the whole
        contract to a grid that only needs to know it exists."""
        return self.generation_mode == "compiled"


class GenerateScriptsRequest(BaseModel):
    test_case_ids: list[int] = Field(min_length=1)
    framework: Framework
    regenerate: bool = False
    # Playwright compiles through the Script Compiler by default (ADR-001).
    # This forces the old free-form path instead — kept as an explicit escape
    # hatch for a test case the contract vocabulary genuinely cannot express,
    # not as a routine option.
    freeform: bool = False
    environment_profile: Literal["DEV", "SIT", "QA", "UAT", "PREPROD", "PROD_SANITY"] = "QA"


class GenerateScriptsResponse(BaseModel):
    generated: list[ScriptAssetOut]
    skipped: list[dict] = Field(default_factory=list)
    agent_run_id: int | None = None


class GroundTestCasesRequest(BaseModel):
    """Match refined test case steps against the discovered element catalog.

    Runs synchronously: it is string matching over rows already in the
    database, with no LLM call and no browser, so the 202-and-poll contract
    the other studio actions use would add latency and a spinner for work
    that finishes in milliseconds.
    """

    test_case_ids: list[int] | None = None
    batch_id: int | None = None

    @model_validator(mode="after")
    def _needs_a_selection(self) -> "GroundTestCasesRequest":
        if not self.test_case_ids and self.batch_id is None:
            raise ValueError("Provide test_case_ids, a batch_id, or both.")
        return self


class GroundTestCasesResponse(BaseModel):
    updated: list[RefinedTestCaseOut] = Field(default_factory=list)
    # Test cases that could not be grounded and why — almost always "no
    # discovery run for this batch yet", which is a fixable state rather than
    # an error.
    skipped: list[dict] = Field(default_factory=list)


class DryRunRequest(BaseModel):
    script_ids: list[int] = Field(min_length=1)


class ScriptAssetUpdate(BaseModel):
    code: str | None = None
    files: dict | None = None
    execution_command: str | None = None
    setup_notes: list | None = None


class ScriptDecision(BaseModel):
    decision: Literal["approve", "reopen"]
    reason: str | None = None


# ── Shared ───────────────────────────────────────────────────────────────────

class BulkDeleteRequest(BaseModel):
    """The ids of the generated artefacts to remove.

    One shape for all four artefact families — derived requirements, uploaded
    test cases, refined test cases and scripts — because the screens all do the
    same thing with it: delete the current selection.
    """

    ids: list[int] = Field(min_length=1)


class DeletionSummary(BaseModel):
    """What a delete actually removed.

    Deleting one of these artefacts is never only the row the user clicked:
    superseded versions go with it, and the database cascades scripts off a
    refined test case. The screens report these numbers rather than a bare
    "deleted", so the user is told what left with it.
    """

    deleted: list[int] = Field(default_factory=list)
    # Requested ids that are not in this project (already deleted, or another
    # project's). Reported rather than raising: a stale grid is the usual
    # cause and the rest of the selection should still go.
    not_found: list[int] = Field(default_factory=list)
    # Superseded versions removed alongside the current ones.
    versions_deleted: int = 0
    # Scripts the database cascaded away with their test case.
    scripts_deleted: int = 0
    # Refined test cases left in place but no longer linked to the artefact
    # that produced them (the FK is ON DELETE SET NULL).
    test_cases_unlinked: int = 0
    # How many of the deleted rows had been approved.
    approved_deleted: int = 0


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
