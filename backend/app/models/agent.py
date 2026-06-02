from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class AgentRun(TimestampMixin, Base):
    """Tracks every agent invocation — full audit trail."""
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    triggered_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # requirement_intake | requirement_quality | test_planning | test_scenario |
    # test_case | test_data | automation_script | test_execution |
    # defect_analysis | jira_defect | test_reporting

    status: Mapped[str] = mapped_column(String(50), default="pending")
    # pending | running | completed | failed | cancelled

    input_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="agent_runs")
    logs: Mapped[list["AgentLog"]] = relationship("AgentLog", back_populates="agent_run", cascade="all, delete-orphan")


class AgentLog(TimestampMixin, Base):
    """Structured log entries for each agent run step."""
    __tablename__ = "agent_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)

    level: Mapped[str] = mapped_column(String(20), default="info")
    # debug | info | warning | error | critical
    step: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    agent_run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="logs")
