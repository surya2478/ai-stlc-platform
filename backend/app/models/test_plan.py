from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class TestPlan(TimestampMixin, Base):
    """Output of Test Planning Agent (Agent 3)."""
    __tablename__ = "test_plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    test_plan_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), default="Test Plan")

    scope: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    out_of_scope: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    test_types: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    entry_criteria: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    exit_criteria: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    risks: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    mitigations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    automation_candidates: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    estimated_effort: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="draft")
    # status: draft | pending_approval | approved | rejected
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="test_plans")
    enrollments: Mapped[list["PlanTestCase"]] = relationship(
        "PlanTestCase", back_populates="test_plan", cascade="all, delete-orphan"
    )


class PlanTestCase(TimestampMixin, Base):
    """Enrollment of a reusable TestCase into a TestPlan's UAT cycle.

    Distinct from `TestCase.linked_test_plan_id` (the single plan a TC was
    authored/generated under). This table lets the same TestCase be enrolled
    into multiple plans/cycles over time, each with its own planned
    environment, tester assignment and execution-day sequence — matching the
    per-cycle UAT tracking template while keeping TestCase itself reusable.
    """
    __tablename__ = "plan_test_cases"
    __table_args__ = (
        UniqueConstraint("test_plan_id", "test_case_id", name="uq_plan_test_cases_plan_case"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    test_plan_id: Mapped[int] = mapped_column(ForeignKey("test_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id: Mapped[int] = mapped_column(ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    environment_id: Mapped[int | None] = mapped_column(
        ForeignKey("environments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tester_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    planned_execution_sequence: Mapped[str | None] = mapped_column(String(50), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    test_plan: Mapped["TestPlan"] = relationship("TestPlan", back_populates="enrollments")
    test_case: Mapped["TestCase"] = relationship("TestCase")
    environment: Mapped["Environment | None"] = relationship("Environment")
