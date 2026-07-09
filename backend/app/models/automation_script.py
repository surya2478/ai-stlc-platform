from sqlalchemy import ForeignKey, Integer, String, Text
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

    # Phase 2 (ADR-001): every repair/healing change is a NEW row, never an
    # in-place code mutation — "rollback guaranteed". parent_script_id links
    # to the version this one supersedes; version increments per chain.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    parent_script_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_scripts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Full multi-file bundle the Script Compiler produced (specs/pages/
    # fixtures/utils) — `code`/`file_path` above hold the entry spec for the
    # existing script editor UI.
    compiled_files: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # The Automation Generation Contract that produced this version — audit
    # trail + regeneration source; no free-form code, per ADR-001.
    contract: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Persisted Static Quality Gate verdict (see app/services/static_quality_gate.py).
    static_gate_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="draft")
    # status: ai_draft | draft | in_review | pending_approval | approved | rejected
    #       | executed | deprecated | blocked | generated | static_passed
    #       | mcp_discovered | dry_run_passed | reviewer_approved | lead_approved
    #       | ci_ready | production_regression_candidate
    # ai_draft   = first output of AI generation, must be reviewed before promotion
    # draft      = author is iterating on the script
    # in_review  = submitted for peer review (also referred to as pending_approval)
    # approved   = ready for execution
    # rejected   = explicitly rejected during review
    # executed   = legacy marker; superseded by ExecutionRun + ExecutionResult
    # deprecated = script kept for history but not executable
    # blocked    = generation/review blocked on an upstream issue
    # generated  = Script Compiler rendered code from a validated contract (Phase 2)
    # static_passed = Static Quality Gate found zero blocking violations (Phase 2)
    # mcp_discovered / dry_run_passed / reviewer_approved / lead_approved / ci_ready /
    #   production_regression_candidate = later-phase lifecycle stages (Phase 3-5)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="automation_scripts")
    test_case: Mapped["TestCase | None"] = relationship(
        "TestCase",
        back_populates="automation_scripts",
        foreign_keys=[test_case_id],
    )
    parent_script: Mapped["AutomationScript | None"] = relationship(
        "AutomationScript", remote_side=[id], foreign_keys=[parent_script_id]
    )
