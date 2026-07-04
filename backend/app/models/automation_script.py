from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class AutomationScript(TimestampMixin, Base):
    """Playwright / Pytest scripts from Automation Script Agent (Agent 7)."""
    __tablename__ = "automation_scripts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    test_case_id: Mapped[int | None] = mapped_column(ForeignKey("test_cases.id"), nullable=True, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    script_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    framework: Mapped[str] = mapped_column(String(50), nullable=False)
    # framework: playwright | pytest | httpx
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    setup_required: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    execution_command: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="draft")
    # status: ai_draft | draft | in_review | pending_approval | approved | rejected
    #       | executed | deprecated | blocked
    # ai_draft   = first output of AI generation, must be reviewed before promotion
    # draft      = author is iterating on the script
    # in_review  = submitted for peer review (also referred to as pending_approval)
    # approved   = ready for execution
    # rejected   = explicitly rejected during review
    # executed   = legacy marker; superseded by ExecutionRun + ExecutionResult
    # deprecated = script kept for history but not executable
    # blocked    = generation/review blocked on an upstream issue
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="automation_scripts")
    test_case: Mapped["TestCase | None"] = relationship(
        "TestCase",
        back_populates="automation_scripts",
        foreign_keys=[test_case_id],
    )
