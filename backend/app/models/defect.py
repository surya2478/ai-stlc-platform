from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class DefectDraft(TimestampMixin, Base):
    """AI-generated defect draft from Defect Analysis Agent (Agent 9). Requires human approval before Jira push."""
    __tablename__ = "defect_drafts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    test_case_id: Mapped[int | None] = mapped_column(ForeignKey("test_cases.id"), nullable=True, index=True)
    execution_result_id: Mapped[int | None] = mapped_column(ForeignKey("execution_results.id"), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    defect_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps_to_reproduce: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_result: Mapped[str | None] = mapped_column(Text, nullable=True)

    severity: Mapped[str] = mapped_column(String(20), default="Medium")
    priority: Mapped[str] = mapped_column(String(20), default="Medium")
    root_cause_hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification: Mapped[str] = mapped_column(String(100), default="product_defect")
    # product_defect | automation_issue | environment_issue | test_data_issue

    attachments: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    jira_ready: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[str] = mapped_column(String(50), default="draft")
    # draft | pending_approval | approved | rejected | pushed_to_jira

    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="defect_drafts")
    test_case: Mapped["TestCase | None"] = relationship("TestCase", back_populates="defect_drafts")
    jira_defect: Mapped["JiraDefect | None"] = relationship("JiraDefect", back_populates="defect_draft", uselist=False)


class JiraDefect(TimestampMixin, Base):
    """Created Jira defect — only exists after human approval + successful Jira API call."""
    __tablename__ = "jira_defects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    defect_draft_id: Mapped[int] = mapped_column(ForeignKey("defect_drafts.id"), nullable=False, unique=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    jira_issue_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    jira_url: Mapped[str] = mapped_column(Text, nullable=False)
    jira_status: Mapped[str | None] = mapped_column(String(100), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="created")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    defect_draft: Mapped["DefectDraft"] = relationship("DefectDraft", back_populates="jira_defect")
