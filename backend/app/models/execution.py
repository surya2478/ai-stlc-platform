from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class ExecutionRun(TimestampMixin, Base):
    """A test execution run.

    Spans Manual, Automation (local Playwright/Pytest + external tools), and AI
    execution flows. The unified `execution_type` column (added in migration 024)
    lets the Execution Dashboard aggregate without unpacking JSON metadata.
    """
    __tablename__ = "execution_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    execution_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    suite_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Lifecycle state. Allowed values enforced by ck_execution_runs_status
    # (see migration 024): pending | queued | running | completed | failed |
    # cancelled | auto_completed | review_required.
    status: Mapped[str] = mapped_column(String(50), default="pending")

    # Unified execution flavour. Allowed values enforced by
    # ck_execution_runs_execution_type (migration 024):
    # manual | automation | ai | hybrid.
    execution_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual", index=True)

    # External tool plumbing (added in migration 007).
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    test_cycle_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)

    # AI run telemetry. Populated when the run is an AI execution; null otherwise.
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

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
    # status: pending | pass | fail | skip | error | blocked | not_run | running
    # (enforced by ck_execution_results_status — see migration 017)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Per-result execution flavour + external/jira plumbing (added in migration 007).
    execution_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    automation_mapping_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_test_mappings.id"), nullable=True, index=True
    )
    external_tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_test_case_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    automation_execution_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    manual_execution_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    jira_execution_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    screenshot_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_result_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    jira_issue_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    jira_test_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    raw_result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    execution_run: Mapped["ExecutionRun"] = relationship("ExecutionRun", back_populates="results")
    test_case: Mapped["TestCase | None"] = relationship("TestCase", back_populates="execution_results")
    manual_steps: Mapped[list["ManualStepResult"]] = relationship(
        "ManualStepResult",
        back_populates="execution_result",
        cascade="all, delete-orphan",
        order_by="ManualStepResult.step_number",
    )


class ManualStepResult(TimestampMixin, Base):
    """Per-step result captured by a human tester during manual execution.

    One row per (execution_result, step_number). Evidence is stored as a JSONB list
    of file descriptors. The actual files live on disk under
    settings.file_storage_path / manual_evidence / <project_id> / <run_id> / and
    are served via an authenticated download endpoint.
    """
    __tablename__ = "manual_step_results"
    __table_args__ = (
        UniqueConstraint("execution_result_id", "step_number", name="uq_manual_step_result_step"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    execution_result_id: Mapped[int] = mapped_column(
        ForeignKey("execution_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)

    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_run")
    # status: not_run | in_progress | passed | failed | blocked | skipped

    actual_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Evidence descriptors: list of dicts. Each evidence item is also assigned a
    # short id (uuid hex) so the frontend can delete a specific attachment.
    evidence: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Free-form audit / supplementary data — currently holds the rolling
    # `ai_assist_history` capped at 10 entries (each: ts, by_user_id,
    # suggested_status, confidence, reasoning, observations, inputs_used).
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    execution_result: Mapped["ExecutionResult"] = relationship("ExecutionResult", back_populates="manual_steps")
