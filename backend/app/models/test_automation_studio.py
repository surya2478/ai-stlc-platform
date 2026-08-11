"""Test Automation Studio (TAS) — own tables for an isolated module.

Nothing here writes to `requirements`, `test_cases` or `automation_scripts`.
The studio references those rows read-only (`source_test_case_id`,
`promoted_requirement_id`) so the classic Requirements / Test Cases /
Automation modules render exactly the same content whether this module is
enabled or not. Promotion back into the shared tables is a separate,
explicit action and is not part of this module's generation flow.

Flow across the three screens:

    tas_intake_batches            Screen 1 — a set of uploaded BRD/SRD/TC docs
      └ tas_intake_documents        the docs, each tagged with its role
      └ tas_coverage_assessments    the assessment run over that batch
      └ tas_derived_requirements    requirements extracted + gap-derived
      └ tas_source_test_cases       the TCs read out of the uploaded TC sheet
    tas_refined_test_cases        Screen 2 — automation-shaped TCs
    tas_script_assets             Screen 3 — generated framework scripts

Screen 2 has two entry points and needs both. An uploaded test case is
refined in place and keeps its ID and name; a coverage gap has no test case
to keep, so it produces a new one from the approved requirement.
"""
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class TasIntakeBatch(TimestampMixin, Base):
    """One Requirement Coverage Assessment intake (Screen 1).

    A batch is the unit a coverage assessment runs over — you upload the BRD,
    the SRD and the existing test case sheet together because the gap only
    exists relative to all three.
    """

    __tablename__ = "tas_intake_batches"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Which application under test these documents describe, and the URL the
    # generated automation should target. `application_id` points at the real
    # ProjectApplication so this complements Project Settings rather than
    # duplicating it; `application_url` is the batch-level value the user typed
    # on Screen 1, which is written back into the application's
    # environment_urls when `application_id` is set.
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    application_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_environment: Mapped[str] = mapped_column(String(50), nullable=False, default="qa")

    # status: draft | assessing | assessed | failed
    # `draft` = documents attached, assessment not run yet.
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    status_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    documents: Mapped[list["TasIntakeDocument"]] = relationship(
        "TasIntakeDocument", back_populates="batch", cascade="all, delete-orphan", lazy="selectin"
    )
    assessments: Mapped[list["TasCoverageAssessment"]] = relationship(
        "TasCoverageAssessment", back_populates="batch", cascade="all, delete-orphan", lazy="select"
    )


class TasIntakeDocument(TimestampMixin, Base):
    """A document attached to a batch, tagged with the role it plays.

    The role matters: a BRD and an SRD are read as sources of requirements,
    while a test case document is read as *existing coverage*. Assessing
    coverage without that distinction would count the test cases as
    requirements and report perfect coverage of itself.
    """

    __tablename__ = "tas_intake_documents"
    __table_args__ = (UniqueConstraint("batch_id", "document_id", name="uq_tas_intake_batch_document"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("tas_intake_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("uploaded_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # doc_role: brd | srd | test_cases | other
    doc_role: Mapped[str] = mapped_column(String(30), nullable=False, default="other", index=True)
    # extraction_status: pending | extracted | failed
    extraction_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_requirement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extracted_test_case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    batch: Mapped["TasIntakeBatch"] = relationship("TasIntakeBatch", back_populates="documents")
    document: Mapped["UploadedDocument"] = relationship("UploadedDocument", lazy="selectin")


class TasCoverageAssessment(TimestampMixin, Base):
    """The result of one "Assess Coverage for Automation" run over a batch."""

    __tablename__ = "tas_coverage_assessments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("tas_intake_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # status: running | completed | failed
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    total_requirements: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    covered_requirements: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    partially_covered_requirements: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uncovered_requirements: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    existing_test_case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    derived_requirement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coverage_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Per-requirement coverage rows and the extracted existing test cases, kept
    # as JSONB rather than as tables: they are evidence for one assessment
    # version, never queried across assessments, and superseded wholesale by
    # the next run.
    coverage_rows: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    extracted_test_cases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    gap_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    batch: Mapped["TasIntakeBatch"] = relationship("TasIntakeBatch", back_populates="assessments")


class TasDerivedRequirement(TimestampMixin, Base):
    """A requirement produced by Screen 1 — extracted from the docs, or
    derived to close a coverage gap.

    `origin` distinguishes the two: `extracted` came straight out of a BRD/SRD,
    `derived` is the studio's own proposal for a behaviour the documents imply
    but the supplied test cases never exercise. Both need approval before they
    reach Screen 2, because both drive test case generation.
    """

    __tablename__ = "tas_derived_requirements"
    __table_args__ = (
        UniqueConstraint("batch_id", "requirement_key", name="uq_tas_derived_requirement_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("tas_intake_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("tas_coverage_assessments.id", ondelete="SET NULL"), nullable=True, index=True
    )

    requirement_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    acceptance_criteria: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    business_rules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    ui_pages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    apis: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    test_data_needs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # origin: extracted | derived
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="extracted", index=True)
    # coverage_state: covered | partially_covered | uncovered
    coverage_state: Mapped[str] = mapped_column(String(30), nullable=False, default="uncovered", index=True)
    gap_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    covering_test_case_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    automation_relevance: Mapped[str | None] = mapped_column(String(20), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="Medium")

    # status: draft | pending_approval | approved | rejected
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_approval", index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Set only if this studio requirement is ever promoted into the shared
    # `requirements` table by an explicit action. Read-only from this module.
    promoted_requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirements.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class TasSourceTestCase(TimestampMixin, Base):
    """A test case read out of an uploaded test case document.

    The coverage agent already extracts these — ID, title and steps, verbatim
    off the sheet. Holding them only inside the assessment's JSONB made them
    unaddressable: refinement could reach an uploaded test case solely by
    matching its ID against the platform `test_cases` table, so a project that
    had never imported its test cases into the platform (the normal case for
    this module) got a freshly minted ID and the requirement's title instead of
    the ones on the sheet. A row gives the uploaded test case an identity a
    refined row can point at.

    Deliberately a studio table rather than rows in `test_cases`: this module
    does not write to the shared tables, and importing unreviewed sheet rows
    there would put them in the classic Test Cases module and entangle the
    platform's own display-ID sequence.
    """

    __tablename__ = "tas_source_test_cases"
    __table_args__ = (
        UniqueConstraint("batch_id", "tc_display_id", name="uq_tas_source_test_case_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("tas_intake_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The assessment that most recently saw this test case. Re-assessment
    # refreshes the row and moves this pointer rather than deleting and
    # recreating it, because refined test cases reference it.
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("tas_coverage_assessments.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Exactly as written in the document — `TC-01`, `LOGIN-3`, whatever the
    # team uses. Never reformatted: preserving it is the entire point.
    tc_display_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("uploaded_documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Every column the uploaded sheet carried, keyed by the canonical field
    # names in `test_case_template`. The studio refines objective, steps and
    # expected result; it has nothing to say about Domain, Channel, Product,
    # Environment or the execution columns, and a download that dropped them
    # would not be the format the team uploaded. Kept whole rather than as
    # columns because it is the source document's shape, not this module's.
    source_row: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Set when the same display ID also exists in the platform's `test_cases`.
    # That row is the better refinement source — it carries structured
    # preconditions, test data and priority the sheet does not — so refinement
    # prefers it and this records that the two are the same test case.
    matched_platform_test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class TasRefinedTestCase(TimestampMixin, Base):
    """An automation-shaped test case (Screen 2).

    When `source_test_case_id` or `source_uploaded_test_case_id` is set this
    row is the automation-ready rewrite of a test case that already existed:
    `tc_display_id` and `title` are copied verbatim from the source and never
    regenerated, every other field is the studio's improvised version. Neither
    the `test_cases` row nor the uploaded sheet is touched.

    With both null the row came from a newly approved gap requirement — there
    was no test case to preserve — and gets a display ID in the platform's own
    `TC-0001` format.
    """

    __tablename__ = "tas_refined_test_cases"
    __table_args__ = (
        UniqueConstraint("project_id", "tc_display_id", "version", name="uq_tas_refined_tc_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("tas_intake_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    derived_requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("tas_derived_requirements.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Read-only reference to the platform test case this refines, if any.
    source_test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The uploaded sheet row this refines, if any. Separate from
    # `source_test_case_id` because they are different kinds of source with
    # different lifetimes: one is a platform row this module must not touch,
    # the other is intake evidence that a re-assessment may refresh.
    source_uploaded_test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("tas_source_test_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # origin: existing | imported | derived
    #   existing — refined from a platform `test_cases` row
    #   imported — refined from an uploaded test case document
    #   derived  — created from an approved gap requirement
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="derived", index=True)
    tc_display_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)

    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    preconditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    bdd_scenario: Mapped[str | None] = mapped_column(Text, nullable=True)

    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    application_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="Medium")
    test_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # classification: automation | manual | undecided
    classification: Mapped[str] = mapped_column(String(20), nullable=False, default="undecided", index=True)
    # classification_source: policy | agent | manual
    classification_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    classification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_only_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Requirement 4. The agent resolves test data into the shared Test Data
    # module and binds it here; when it cannot, `test_data_required` stays true
    # with `test_data_status='needs_user_action'` so the gap is visible on the
    # grid and blocks approval until a human deals with it.
    test_data_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    # test_data_status: not_required | agent_provided | needs_user_action | user_provided
    test_data_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_required", index=True
    )
    test_data_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_data_requirements: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # IDs of rows in the shared `test_data` table this test case binds to.
    test_data_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # status: draft | pending_approval | approved | rejected
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    scripts: Mapped[list["TasScriptAsset"]] = relationship(
        "TasScriptAsset", back_populates="refined_test_case", cascade="all, delete-orphan", lazy="select"
    )


class TasScriptAsset(TimestampMixin, Base):
    """A generated automation script for one refined test case (Screen 3).

    One row per (test case, framework, version) so a team can generate
    Playwright and Appium off the same test case without either overwriting
    the other, and so editing produces a new version rather than losing the
    generated original.
    """

    __tablename__ = "tas_script_assets"
    __table_args__ = (
        UniqueConstraint(
            "refined_test_case_id", "framework", "version", name="uq_tas_script_asset_version"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refined_test_case_id: Mapped[int] = mapped_column(
        ForeignKey("tas_refined_test_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # framework: playwright | katalon | appium
    framework: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(30), nullable=False, default="typescript")
    script_key: Mapped[str] = mapped_column(String(150), nullable=False, index=True)

    # `code` is the primary file; `files` carries the rest of a multi-file
    # artifact (Katalon emits a test case plus an object repository, Appium a
    # test plus a capabilities file) as {relative_path: contents}.
    code: Mapped[str] = mapped_column(Text, nullable=False)
    files: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    execution_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    setup_notes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # status: draft | edited | approved
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    refined_test_case: Mapped["TasRefinedTestCase"] = relationship(
        "TasRefinedTestCase", back_populates="scripts"
    )
