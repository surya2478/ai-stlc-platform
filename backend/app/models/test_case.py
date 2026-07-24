from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class TestCase(TimestampMixin, Base):
    """Detailed manual test case from Test Case Development Agent (Agent 5)."""
    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("test_scenarios.id"), nullable=True, index=True)
    requirement_id: Mapped[int | None] = mapped_column(ForeignKey("requirements.id"), nullable=True, index=True)
    # Which application/channel under test this test case targets. Nullable —
    # unset test cases resolve to the project's default ProjectApplication at
    # script-generation/execution time rather than requiring a backfill.
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    test_case_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)

    preconditions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    test_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    bdd_scenario: Mapped[str | None] = mapped_column(Text, nullable=True)

    priority: Mapped[str] = mapped_column(String(20), default="Medium")
    severity: Mapped[str] = mapped_column(String(20), default="Medium")
    test_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    automation_candidate: Mapped[bool] = mapped_column(Boolean, default=False)

    execution_mode: Mapped[str] = mapped_column(String(50), default="manual")
    automation_eligible: Mapped[str] = mapped_column(String(20), default="no")
    automation_status: Mapped[str] = mapped_column(String(50), default="not_required")
    automation_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    test_phase: Mapped[str | None] = mapped_column(String(80), nullable=True)
    telecom_domain: Mapped[str | None] = mapped_column(String(80), nullable=True)
    product_group: Mapped[str | None] = mapped_column(String(200), nullable=True)
    product: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sub_request_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_tool: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Free-text suite/test-set ID from an *external* tool (Xray/Zephyr) — set
    # automatically when an automation mapping syncs. Distinct from
    # `test_suite_id` below, which is this platform's own internal Test Suite.
    suite_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    test_suite_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_suites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_tc_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_tc_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    automation_script_id: Mapped[int | None] = mapped_column(ForeignKey("automation_scripts.id"), nullable=True)
    last_automation_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_automation_run_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_execution_run_id: Mapped[int | None] = mapped_column(ForeignKey("execution_runs.id"), nullable=True)
    latest_evidence_available: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    jira_issue_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jira_test_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jira_issue_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    jira_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    jira_final_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    jira_sync_status: Mapped[str] = mapped_column(String(50), default="not_synced")
    jira_last_synced_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    jira_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    linked_release_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linked_test_plan_id: Mapped[int | None] = mapped_column(ForeignKey("test_plans.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_status_updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_status_updated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="draft")
    # status: draft | pending_approval | approved | rejected
    # Post-migration 026, 'automated' is no longer a lifecycle status — that
    # concept moved to `automation_status`. Any row that previously carried
    # status='automated' was backfilled to status='approved' with
    # automation_status='automated'.

    # ai_assistance_status: disabled | enabled | recommendation_pending | approved | rejected
    # Phase 5 addition. Tracks whether the AI Automation Studio is providing
    # recommendations for this TC and where any outstanding recs sit in the
    # review flow. See the intelligence assistant panel for the surface.
    ai_assistance_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="disabled", server_default="disabled"
    )

    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    deleted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # UAT template fields (migration 042). Additive `*_id` taxonomy FKs —
    # kept alongside the legacy free-text columns above (telecom_domain,
    # product, sub_request_type, test_type) for backward compatibility.
    # When set, the FK-resolved value is the taxonomy-governed source of
    # truth; the free-text column remains as a fallback for older rows.
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("systems.id", ondelete="SET NULL"), nullable=True, index=True)
    domain_id: Mapped[int | None] = mapped_column(ForeignKey("qa_domains.id", ondelete="SET NULL"), nullable=True, index=True)
    area_of_test_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    sub_request_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("sub_request_types.id", ondelete="SET NULL"), nullable=True, index=True
    )
    test_case_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_case_types.id", ondelete="SET NULL"), nullable=True, index=True
    )
    test_case_complexity_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_case_complexities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Fuller UAT description, distinct from the short `title` above.
    test_case_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free-text ATC (automated test case) reference/ID from the template —
    # not consolidated into automation_candidate/automation_status, which
    # track automation eligibility rather than an external ATC identifier.
    atc_test_case: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    ppm_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="test_cases")
    scenario: Mapped["TestScenario | None"] = relationship("TestScenario", back_populates="test_cases")
    requirement: Mapped["Requirement | None"] = relationship("Requirement", back_populates="test_cases")
    application: Mapped["ProjectApplication | None"] = relationship("ProjectApplication")
    test_suite: Mapped["TestSuite | None"] = relationship("TestSuite")
    channel: Mapped["System | None"] = relationship("System")
    domain: Mapped["QADomain | None"] = relationship("QADomain")
    area_of_test: Mapped["ProductGroup | None"] = relationship("ProductGroup")
    taxonomy_product: Mapped["Product | None"] = relationship("Product")
    taxonomy_sub_request_type: Mapped["SubRequestType | None"] = relationship("SubRequestType")
    taxonomy_test_case_type: Mapped["TestCaseType | None"] = relationship("TestCaseType")
    taxonomy_test_case_complexity: Mapped["TestCaseComplexity | None"] = relationship("TestCaseComplexity")
    test_data_sets: Mapped[list["TestData"]] = relationship("TestData", back_populates="test_case")
    automation_scripts: Mapped[list["AutomationScript"]] = relationship(
        "AutomationScript",
        back_populates="test_case",
        foreign_keys="AutomationScript.test_case_id",
    )
    automation_mappings: Mapped[list["AutomationTestMapping"]] = relationship(
        "AutomationTestMapping",
        back_populates="test_case",
    )
    execution_results: Mapped[list["ExecutionResult"]] = relationship("ExecutionResult", back_populates="test_case")
    defect_drafts: Mapped[list["DefectDraft"]] = relationship("DefectDraft", back_populates="test_case")
    history: Mapped[list["TestCaseHistory"]] = relationship("TestCaseHistory", back_populates="test_case")

    @property
    def mode(self) -> str:
        return self.execution_mode

    @property
    def approval_status(self) -> str:
        return self.status

    @property
    def linked_requirement_id(self) -> int | None:
        return self.requirement_id

    @property
    def linked_requirement_key(self) -> str | None:
        return self.requirement.requirement_id if self.requirement else None

    @property
    def linked_scenario_id(self) -> int | None:
        return self.scenario_id

    @property
    def test_suite_name(self) -> str | None:
        return self.test_suite.name if self.test_suite else None

    @property
    def channel_name(self) -> str | None:
        return self.channel.name if self.channel else None

    @property
    def domain_name(self) -> str | None:
        return self.domain.name if self.domain else self.telecom_domain

    @property
    def area_of_test_name(self) -> str | None:
        return self.area_of_test.name if self.area_of_test else None

    @property
    def product_name(self) -> str | None:
        return self.taxonomy_product.name if self.taxonomy_product else self.product

    @property
    def sub_request_type_name(self) -> str | None:
        return self.taxonomy_sub_request_type.name if self.taxonomy_sub_request_type else self.sub_request_type

    @property
    def test_case_type_name(self) -> str | None:
        return self.taxonomy_test_case_type.name if self.taxonomy_test_case_type else self.test_type

    @property
    def test_case_complexity_name(self) -> str | None:
        return self.taxonomy_test_case_complexity.name if self.taxonomy_test_case_complexity else None

    @property
    def linked_application_id(self) -> int | None:
        return self.application_id

    @property
    def linked_project_id(self) -> int:
        return self.project_id


class TestCaseHistory(TimestampMixin, Base):
    """Audit history for user-visible test case field changes."""
    __tablename__ = "test_case_history"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    test_case_id: Mapped[int] = mapped_column(ForeignKey("test_cases.id"), nullable=False, index=True)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="platform")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    test_case: Mapped["TestCase"] = relationship("TestCase", back_populates="history")


class TestCaseImportPreview(TimestampMixin, Base):
    """Temporary parsed test-case import payload awaiting user confirmation.

    Mirrors TestDataImportPreview (models/test_data.py) — same preview-token,
    15-minute-expiry, single-use pattern, applied to the UAT template's
    22-column CSV/XLSX import instead of test data records.
    """
    __tablename__ = "test_case_import_previews"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    preview_token: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    detected_columns_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parsed_rows_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    resolved_rows_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    validation_errors_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    validation_warnings_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    can_import: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consumed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
