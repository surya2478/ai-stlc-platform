from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class ExecutionRun(TimestampMixin, Base):
    """A test execution run from Test Execution Agent (Agent 8)."""
    __tablename__ = "execution_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    execution_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    suite_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(100), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="pending")
    # status: pending | in_progress | completed | failed | cancelled

    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)

    execution_logs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    artifacts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    allure_report_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    simulated: Mapped[bool] = mapped_column(default=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)


    project: Mapped["Project"] = relationship("Project", back_populates="execution_runs")
    results: Mapped[list["ExecutionResult"]] = relationship("ExecutionResult", back_populates="execution_run", cascade="all, delete-orphan")


class ExecutionResult(TimestampMixin, Base):
    """Individual test result within an ExecutionRun."""
    __tablename__ = "execution_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    execution_run_id: Mapped[int] = mapped_column(ForeignKey("execution_runs.id"), nullable=False, index=True)
    test_case_id: Mapped[int | None] = mapped_column(ForeignKey("test_cases.id"), nullable=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)

    test_name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    # status: passed | failed | skipped | error
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    execution_run: Mapped["ExecutionRun"] = relationship("ExecutionRun", back_populates="results")
    test_case: Mapped["TestCase | None"] = relationship("TestCase", back_populates="execution_results")
