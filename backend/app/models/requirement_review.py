from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class RequirementQualityReview(TimestampMixin, Base):
    """Output of Requirement Quality Agent (Agent 2)."""
    __tablename__ = "requirement_quality_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ambiguities: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    missing_details: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    contradictions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    testability_issues: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    clarification_questions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    recommendations: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(default="draft")
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)

    requirement: Mapped["Requirement"] = relationship("Requirement", back_populates="quality_reviews")
