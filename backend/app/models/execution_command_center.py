"""P1-S7 UI-046 Suite Execution Command Center — the per-run execution graph.

One `ExecutionRun` executing a published suite snapshot fans out into
`ExecutionRunItem` rows (one per snapshot member), each of which owns its steps,
assertions and evidence. `ExecutionRunEvent` is the append-only stream the
command center polls; `ExecutionRunCommand` is the audited record of an operator
control action.

Why this sits beside `ExecutionResult` rather than replacing it: `ExecutionResult`
is the cross-flow result row that the Execution Dashboard, Jira sync and UAT
templates all read, and its status vocabulary is shared with manual and AI runs.
The command center needs a richer per-member record — lifecycle separate from
result, eight outcomes, attempts, step progress, typed evidence — that would
change the meaning of that shared table. Suite runs write both: `ExecutionResult`
stays the portable result, `ExecutionRunItem` carries the governed detail.

Lifecycle and result are deliberately separate columns on the item, the same
two-axis discipline migration 051 applied to autonomy and approval. A single
field cannot express "running, not yet judged" without inventing a fake result,
and contract Section 14.3 requires them presented separately.

See migration 052 for the constraint definitions and the reasoning behind the
event sequence.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

# ── Vocabularies. Kept in the model layer so services and schemas import one
# definition rather than re-declaring string literals. Must stay in step with
# migration 052's check constraints.

RUN_LIFECYCLE_STATES = (
    "READINESS_PENDING",
    "BLOCKED_BEFORE_START",
    "QUEUED",
    "RUNNING",
    "PAUSE_REQUESTED",
    "PAUSED",
    "STOP_REQUESTED",
    "STOPPED",
    "CANCELLED",
    "COMPLETED",
)

# A run in one of these has finished; Section 3.1 switches the primary action to
# "Open execution report" and the poller stops.
TERMINAL_RUN_STATES = ("BLOCKED_BEFORE_START", "STOPPED", "CANCELLED", "COMPLETED")

OUTCOMES = (
    "PASS",
    "FAIL",
    "INCONCLUSIVE",
    "BLOCKED",
    "ENVIRONMENT_FAILURE",
    "DATA_FAILURE",
    "AUTOMATION_FAILURE",
    "POLICY_BLOCKED",
)

# Outcomes that are not a verdict on the application under test. The tracker's
# "a system error must not become an application FAIL" rule (contract Section 10)
# is enforced by classifying into these instead.
INFRASTRUCTURE_OUTCOMES = (
    "ENVIRONMENT_FAILURE",
    "DATA_FAILURE",
    "AUTOMATION_FAILURE",
    "POLICY_BLOCKED",
    "BLOCKED",
)

ITEM_RESULTS = ("PENDING", "SKIPPED") + OUTCOMES
ITEM_LIFECYCLE_STATES = ("QUEUED", "STARTING", "RUNNING", "PAUSED", "COMPLETED")
STEP_STATUSES = ("pending", "running", "passed", "failed", "skipped")

CONTROL_ACTIONS = (
    "PAUSE_AFTER_CURRENT",
    "RESUME",
    "STOP_GRACEFULLY",
    "CANCEL_NOW",
    "EMERGENCY_STOP",
)
COMMAND_STATES = ("REQUESTED", "ACKNOWLEDGED", "APPLIED", "REJECTED", "SUPERSEDED")

EVIDENCE_TYPES = (
    "screenshot",
    "video",
    "trace",
    "log",
    "api",
    "network",
    "console",
    "database",
    "dom",
    "accessibility",
    "event",
)

# What this slice can actually capture, from what the Playwright runner returns
# (see automation_runner/base.py PerTestResult). Everything else in
# EVIDENCE_TYPES is in the vocabulary for a later capture path and is reported
# as unavailable with a reason — never as absent.
CAPTURABLE_EVIDENCE_TYPES = (
    "screenshot",
    "trace",
    "log",
    "api",
    "network",
    "console",
)
DEFERRED_EVIDENCE_TYPES = tuple(
    t for t in EVIDENCE_TYPES if t not in CAPTURABLE_EVIDENCE_TYPES
)

EVIDENCE_STATUSES = ("pending", "captured", "unavailable")
ASSERTION_SOURCES = ("ui", "api", "db", "oms", "billing", "provisioning", "network")

TRIGGER_SOURCES = ("user", "schedule", "ci_cd", "api")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ('" + "','".join(values) + "')"


class ExecutionRunItem(TimestampMixin, Base):
    """One published snapshot member, as dispatched in one run."""

    __tablename__ = "execution_run_items"
    __table_args__ = (
        CheckConstraint(
            _in("lifecycle_state", ITEM_LIFECYCLE_STATES),
            name="ck_execution_run_items_lifecycle_state",
        ),
        CheckConstraint(_in("result", ITEM_RESULTS), name="ck_execution_run_items_result"),
        UniqueConstraint(
            "execution_run_id", "order_index", name="uq_execution_run_items_order"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    execution_run_id: Mapped[int] = mapped_column(
        ForeignKey("execution_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    suite_test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_suite_test_cases.id", ondelete="SET NULL"), nullable=True
    )
    test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True
    )
    execution_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_suite_execution_groups.id", ondelete="SET NULL"), nullable=True
    )
    script_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_scripts.id", ondelete="SET NULL"), nullable=True
    )
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_applications.id", ondelete="SET NULL"), nullable=True
    )

    # Frozen from the snapshot at expansion. The one place copying is correct:
    # the snapshot is already immutable, and the matrix must render what was
    # published even if the live test case is later renamed or deleted.
    test_case_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    journey: Mapped[str | None] = mapped_column(String(200), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(30), nullable=True)
    framework: Mapped[str | None] = mapped_column(String(50), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    test_case_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    runner_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    lifecycle_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="QUEUED", server_default="QUEUED"
    )
    result: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING", server_default="PENDING"
    )

    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    attempts_allowed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    steps_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    steps_completed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    evidence_required: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    evidence_captured: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Every artifact retained, mandatory or not. Kept separate from the mandatory
    # pair above so a test with no declared evidence requirement still reports the
    # trace and screenshot it actually produced.
    evidence_total_captured: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    assertions_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    assertions_passed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Stored, not reconstructed by the frontend from a status code: Section 6.2
    # requires the exact reason in the tooltip and the inspector.
    attention_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    snapshot_member: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    execution_run: Mapped["ExecutionRun"] = relationship(
        "ExecutionRun", back_populates="items"
    )
    steps: Mapped[list["ExecutionRunItemStep"]] = relationship(
        "ExecutionRunItemStep",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ExecutionRunItemStep.step_number",
    )
    assertions: Mapped[list["ExecutionRunAssertion"]] = relationship(
        "ExecutionRunAssertion", back_populates="item", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["ExecutionRunEvidence"]] = relationship(
        "ExecutionRunEvidence",
        back_populates="item",
        cascade="all, delete-orphan",
        foreign_keys="ExecutionRunEvidence.execution_run_item_id",
    )

    @property
    def is_terminal(self) -> bool:
        return self.lifecycle_state == "COMPLETED"


class ExecutionRunItemStep(TimestampMixin, Base):
    """One step of one item — the inspector's "6 of 14"."""

    __tablename__ = "execution_run_item_steps"
    __table_args__ = (
        CheckConstraint(_in("status", STEP_STATUSES), name="ck_execution_run_item_steps_status"),
        UniqueConstraint(
            "execution_run_item_id", "step_number", name="uq_execution_run_item_steps"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    execution_run_item_id: Mapped[int] = mapped_column(
        ForeignKey("execution_run_items.id", ondelete="CASCADE"), nullable=False, index=True
    )

    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    application_context: Mapped[str | None] = mapped_column(String(200), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    item: Mapped["ExecutionRunItem"] = relationship("ExecutionRunItem", back_populates="steps")


class ExecutionRunAssertion(TimestampMixin, Base):
    """A deterministic business assertion evaluated during an item.

    `passed` is nullable on purpose: NULL means not evaluated yet. Section 7.3
    needs a pending count, and defaulting the boolean either way would record an
    assertion the run never actually made.
    """

    __tablename__ = "execution_run_assertions"
    __table_args__ = (
        CheckConstraint(_in("source", ASSERTION_SOURCES), name="ck_execution_run_assertions_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    execution_run_item_id: Mapped[int] = mapped_column(
        ForeignKey("execution_run_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    execution_run_item_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("execution_run_item_steps.id", ondelete="SET NULL"), nullable=True
    )

    source: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    mandatory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    item: Mapped["ExecutionRunItem"] = relationship(
        "ExecutionRunItem", back_populates="assertions"
    )


class ExecutionRunEvidence(TimestampMixin, Base):
    """One evidence artifact, or one explicit record of why it is missing.

    `status='unavailable'` with a reason is the load-bearing case: contract
    Section 14.12 requires missing mandatory evidence to stay visible and be
    able to drive INCONCLUSIVE, which an absent row could not express.
    """

    __tablename__ = "execution_run_evidence"
    __table_args__ = (
        CheckConstraint(_in("evidence_type", EVIDENCE_TYPES), name="ck_execution_run_evidence_type"),
        CheckConstraint(_in("status", EVIDENCE_STATUSES), name="ck_execution_run_evidence_status"),
        CheckConstraint(
            "status <> 'unavailable' OR unavailable_reason IS NOT NULL",
            name="ck_execution_run_evidence_unavailable_reason",
        ),
        CheckConstraint(
            "status <> 'captured' OR file_path IS NOT NULL OR payload IS NOT NULL",
            name="ck_execution_run_evidence_captured_artifact",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    execution_run_id: Mapped[int] = mapped_column(
        ForeignKey("execution_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL for run-scope evidence such as the orchestrator log.
    execution_run_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("execution_run_items.id", ondelete="CASCADE"), nullable=True, index=True
    )
    execution_run_item_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("execution_run_item_steps.id", ondelete="SET NULL"), nullable=True
    )

    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    mandatory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # False means the artifact has not been through the masking pass and must
    # not be served (Section 14.14).
    sanitized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    item: Mapped["ExecutionRunItem | None"] = relationship(
        "ExecutionRunItem",
        back_populates="evidence",
        foreign_keys=[execution_run_item_id],
    )


class ExecutionRunEvent(Base):
    """Append-only run event. `sequence` is the polling cursor.

    No TimestampMixin: this table is written once and never updated, and it
    carries its own `occurred_at` from the emitter so a batched write cannot
    reorder events relative to what actually happened.
    """

    __tablename__ = "execution_run_events"
    __table_args__ = (
        UniqueConstraint("execution_run_id", "sequence", name="uq_execution_run_events_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    execution_run_id: Mapped[int] = mapped_column(
        ForeignKey("execution_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_run_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("execution_run_items.id", ondelete="CASCADE"), nullable=True
    )

    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExecutionRunCommand(Base):
    """An operator control action, its acknowledgement and its outcome.

    Insert-then-resolve, never deleted. A rejected command is kept with its
    reason: "the operator tried to pause and was refused" is audit-relevant.
    """

    __tablename__ = "execution_run_commands"
    __table_args__ = (
        CheckConstraint(_in("action", CONTROL_ACTIONS), name="ck_execution_run_commands_action"),
        CheckConstraint(_in("state", COMMAND_STATES), name="ck_execution_run_commands_state"),
        UniqueConstraint("command_key", name="uq_execution_run_commands_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    execution_run_id: Mapped[int] = mapped_column(
        ForeignKey("execution_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    command_key: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="REQUESTED", server_default="REQUESTED"
    )
    expected_run_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_version_at_request: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resulting_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
