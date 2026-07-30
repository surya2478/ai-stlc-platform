"""UI-020/021/023 Automation Asset Workspace — the immutable autonomy decision record.

Every autonomy verdict and every human approval writes one row here and never
updates it. The row stores the score, the dimension breakdown, the rubric id and
the threshold **by value** rather than by reference to whatever config holds
today, because thresholds and rubrics change: a pointer to current config cannot
answer "why was this approved" six months later, and a decision that silently
re-reads a changed threshold is not an audit record at all.

`decided_by IS NULL` means the machine decided. A human decision always carries
an actor, which is what makes the separation-of-duty rule checkable after the
fact as well as at the moment of approval.

The two state axes this record explains live on `AutomationSuiteTestCase`:
`autonomy_state` (machine-owned) and `approval_state` (human-owned). They are
deliberately separate columns — see `app/services/automation_asset/autonomy.py`.
"""
from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# What kind of decision this row records.
#   AI_APPROVED / AI_HELD  — machine verdicts from the autonomy policy
#   FINAL_APPROVED / REJECTED — the governed human gate
#   OVERRIDE — an authorised manual stage advancement, always with a reason
DECISION_TYPES = ("AI_APPROVED", "AI_HELD", "FINAL_APPROVED", "REJECTED", "OVERRIDE")

# Decisions a human takes. Used to enforce "reason required" and to identify
# rows that must carry an actor.
HUMAN_DECISIONS = ("FINAL_APPROVED", "REJECTED", "OVERRIDE")

# Decisions that require a stated reason.
REASON_REQUIRED_DECISIONS = ("REJECTED", "OVERRIDE")


class AutomationAssetDecision(Base):
    """One insert-only decision about one automation asset.

    Deliberately does NOT use TimestampMixin: an `updated_at` column would imply
    these rows can be edited. They cannot.
    """

    __tablename__ = "automation_asset_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('" + "','".join(DECISION_TYPES) + "')",
            name="ck_automation_asset_decisions_decision",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suite_test_case_id: Mapped[int] = mapped_column(
        ForeignKey("automation_suite_test_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The artifact versions the decision was taken against. Nullable because a
    # decision can precede either artifact existing (an asset held for having no
    # IR at all still deserves a recorded verdict).
    ir_draft_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_ir_drafts.id", ondelete="SET NULL"), nullable=True
    )
    script_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_scripts.id", ondelete="SET NULL"), nullable=True
    )

    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    # NULL => machine decision.
    decided_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    rubric_id: Mapped[str] = mapped_column(String(50), nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nullable: an asset can be held before a score is computable at all.
    score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    dimensions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    preconditions: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    model_versions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    member: Mapped["AutomationSuiteTestCase"] = relationship(
        "AutomationSuiteTestCase", foreign_keys=[suite_test_case_id]
    )
