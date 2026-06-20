from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class ApprovalAction(TimestampMixin, Base):
    """
    Human approval/rejection events — every approval gate is stored here.
    Provides a complete audit log of human-in-the-loop decisions.
    """
    __tablename__ = "approval_actions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    action_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # approve_requirement | approve_test_plan | approve_test_cases |
    # approve_automation_scripts | approve_execution | approve_jira_defect |
    # approve_report_export | reject_*

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # requirement | test_plan | test_case | automation_script | defect_draft | report
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)

    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    # approved | rejected | requested_changes

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    changes_requested: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="platform")
    actor_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    jira_issue_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True, index=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="approval_actions")
