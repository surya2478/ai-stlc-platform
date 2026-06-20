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
    suite_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    # status: draft | pending_approval | approved | rejected | automated

    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    deleted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="test_cases")
    scenario: Mapped["TestScenario | None"] = relationship("TestScenario", back_populates="test_cases")
    requirement: Mapped["Requirement | None"] = relationship("Requirement", back_populates="test_cases")
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
