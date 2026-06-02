from sqlalchemy import Boolean, ForeignKey, String, Text
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

    status: Mapped[str] = mapped_column(String(50), default="draft")
    # status: draft | pending_approval | approved | rejected | automated

    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="test_cases")
    scenario: Mapped["TestScenario | None"] = relationship("TestScenario", back_populates="test_cases")
    requirement: Mapped["Requirement | None"] = relationship("Requirement", back_populates="test_cases")
    test_data_sets: Mapped[list["TestData"]] = relationship("TestData", back_populates="test_case")
    automation_scripts: Mapped[list["AutomationScript"]] = relationship("AutomationScript", back_populates="test_case")
    execution_results: Mapped[list["ExecutionResult"]] = relationship("ExecutionResult", back_populates="test_case")
    defect_drafts: Mapped[list["DefectDraft"]] = relationship("DefectDraft", back_populates="test_case")
