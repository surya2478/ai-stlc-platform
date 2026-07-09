from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class CoverageMatrixEntry(TimestampMixin, Base):
    """Requirement -> Scenario -> Test Case -> Script -> Execution -> Defect
    rollup (Phase 1). One row per test case — the natural join grain, since
    every other link (script, execution result, defect) hangs off a test
    case in this schema already. Acceptance-criteria/business-rule level
    detail is intentionally NOT tracked here as separate rows (the
    Requirement model stores those as plain string lists with no stable
    per-item ID); gaps at that granularity live in `ArtifactReview.
    coverage_gaps` as free-text findings instead.
    """
    __tablename__ = "coverage_matrix"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), nullable=True, index=True
    )
    scenario_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_scenarios.id", ondelete="CASCADE"), nullable=True, index=True
    )
    test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=True, index=True, unique=True
    )
    script_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_scripts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    execution_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("execution_results.id", ondelete="SET NULL"), nullable=True, index=True
    )
    defect_id: Mapped[int | None] = mapped_column(
        ForeignKey("defect_drafts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    test_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    case_class: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # case_class: positive | negative | boundary | exception
    automation_eligible: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # yes | no | unknown — mirrors TestCase.automation_eligible's convention
    automation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    defect_linked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    project: Mapped["Project"] = relationship("Project")
