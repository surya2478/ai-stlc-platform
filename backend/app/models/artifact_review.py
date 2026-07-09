from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class ArtifactReview(TimestampMixin, Base):
    """Generic senior-reviewer output, one row per reviewed artifact (Phase 1).

    Generalizes `RequirementQualityReview` across every stage. `artifact_type`
    + `artifact_id` is a polymorphic reference — same convention as
    `ArtifactLineage` — since the thing reviewed is sometimes a single row
    (a requirement) and sometimes a *set* keyed by its parent (all scenarios
    generated from a requirement, all test cases generated from a scenario).
    """
    __tablename__ = "artifact_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # requirement | requirement_scenario_coverage | scenario_test_case_coverage
    # requirement_scenario_coverage reviews the *set* of scenarios generated from a
    # requirement (artifact_id = Requirement.id); scenario_test_case_coverage reviews
    # the *set* of test cases generated from a scenario (artifact_id = TestScenario.id).
    artifact_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    reviewer_agent: Mapped[str] = mapped_column(String(100), nullable=False)
    scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False, default="needs_revision")
    # verdict: pass | needs_revision | fail
    findings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    coverage_gaps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    review_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="advisory")
    # review_mode captured at review time (off | advisory | gating) so historical
    # rows show what governance was in effect when this review ran.

    project: Mapped["Project"] = relationship("Project")
