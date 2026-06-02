from sqlalchemy import ForeignKey, String, Text
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
