"""UI-015 Live Discovery Session — Phase 1 (Guided User Recording only).

Persisted state machine + evidence contract backing the governed live
discovery workspace (see the P1-S4 UI-015 contract, Section 9 for the state
machine and Section 17 for the entity list). Free User-Action and
Supervised Agent-Driven modes reuse this same schema — `mode` gates which
UI/behaviour applies, not a separate table — but only Guided User Recording
is wired end-to-end in Phase 1 (see the implementation plan's phasing).

`DiscoverySession.pending_command` is the single "DB is source of truth"
field the dedicated Celery task polls every step, the same pattern already
used by `agent_tasks.py`'s cancel-check and Grounded Automation PoC's
reconciliation loop — see the plan's "Pause/resume design" section for why
this needs no new pub/sub or WebSocket infrastructure.
"""
from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

DISCOVERY_MODES = ("GUIDED_USER", "FREE_USER_ACTION", "SUPERVISED_AGENT_DRIVEN")

DISCOVERY_SESSION_STATES = (
    "NOT_STARTED", "INITIALISING", "RECORDING", "PAUSE_REQUESTED", "PAUSED",
    "RESUMING", "STOP_REQUESTED", "STOPPED", "COMPLETED", "CANCELLED",
    "FAILED", "EMERGENCY_STOPPED",
)

# Contract Section 9 — the only state transitions a command may request.
# Enforced by session_service; invalid transitions return a structured
# conflict and never mutate state.
DISCOVERY_SESSION_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "NOT_STARTED": ("INITIALISING", "CANCELLED"),
    "INITIALISING": ("RECORDING", "CANCELLED", "EMERGENCY_STOPPED", "FAILED"),
    "RECORDING": ("PAUSE_REQUESTED", "STOP_REQUESTED", "EMERGENCY_STOPPED", "COMPLETED", "FAILED"),
    "PAUSE_REQUESTED": ("PAUSED", "EMERGENCY_STOPPED", "FAILED"),
    "PAUSED": ("RESUMING", "STOP_REQUESTED", "CANCELLED", "EMERGENCY_STOPPED"),
    "RESUMING": ("RECORDING", "STOP_REQUESTED", "EMERGENCY_STOPPED", "FAILED"),
    "STOP_REQUESTED": ("STOPPED", "EMERGENCY_STOPPED", "FAILED"),
    "STOPPED": ("RESUMING", "COMPLETED", "CANCELLED"),
    "COMPLETED": (),
    "CANCELLED": (),
    "FAILED": (),
    "EMERGENCY_STOPPED": (),
}

ACTION_FAMILIES = (
    "navigate", "click", "input", "select", "upload", "download", "wait", "read",
    "api", "database_validation", "context_switch", "mobile_gesture",
)
ACTION_INCLUSION_STATES = ("included", "excluded", "corrected", "skipped", "rolled_back")
ACTOR_TYPES = ("user", "agent", "system")
CAPTURE_TYPES = (
    "screenshot", "dom_snapshot", "accessibility_tree", "network_log",
    "console_log", "trace", "video",
)
REDACTION_STATES = ("not_required", "applied", "failed")
RETENTION_STATES = ("active", "flagged", "purged")


class DiscoverySession(TimestampMixin, Base):
    """One governed live discovery run against one application/environment.

    Exactly one primary test case (Guided/Agent-Driven mandatory, Free
    optional — Section 3.1). `pending_command` + `last_command_idempotency_key`
    are the command-issuance contract every `/commands` POST writes to and
    the capture task reads every step.
    """

    __tablename__ = "discovery_sessions"
    __table_args__ = (
        CheckConstraint("mode IN ('" + "','".join(DISCOVERY_MODES) + "')", name="ck_discovery_sessions_mode"),
        CheckConstraint(
            "status IN ('" + "','".join(DISCOVERY_SESSION_STATES) + "')", name="ck_discovery_sessions_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("project_applications.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    environment: Mapped[str] = mapped_column(String(100), nullable=False)

    mode: Mapped[str] = mapped_column(String(30), nullable=False, default="GUIDED_USER")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="NOT_STARTED", server_default="NOT_STARTED")

    browser_target: Mapped[str | None] = mapped_column(String(100), nullable=True)
    framework: Mapped[str] = mapped_column(String(30), nullable=False, default="playwright", server_default="playwright")
    auth_profile_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Mandatory for Guided/Agent-Driven, optional for Free — enforced in
    # session_service, not the DB (mode determines which rule applies).
    test_case_id: Mapped[int | None] = mapped_column(ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True, index=True)
    test_case_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Resolved server-side from the test case at session creation (Section 17)
    # so the header/left panel never has to re-join test_cases at render time.
    requirement_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ppm_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    journey_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scenario_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)

    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)  # mandatory for Free mode
    evidence_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    capture_options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    allowed_hosts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminal_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Plain reference, not a FK — DiscoveryCheckpoint is created in the same
    # migration/table set and a forward FK would force a two-pass insert.
    # Kept authoritative by session_service on every checkpoint write.
    latest_checkpoint_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # UI-016 doesn't exist yet — plain reference per the plan's Phase 4 note.
    draft_model_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)

    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # {"command": "pause", "idempotency_key": "...", "issued_by": <user_id>,
    #  "issued_at": "...", "reason": "...", "params": {...}} — the capture
    # task's step loop reads this every iteration (see discovery_tasks.py).
    pending_command: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_command_idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    resume_state_classification: Mapped[str | None] = mapped_column(String(40), nullable=True)

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    project: Mapped["Project"] = relationship("Project")
    application: Mapped["ProjectApplication"] = relationship("ProjectApplication")
    test_case: Mapped["TestCase | None"] = relationship("TestCase")

    actions: Mapped[list["DiscoveryAction"]] = relationship(
        "DiscoveryAction", back_populates="session", cascade="all, delete-orphan", order_by="DiscoveryAction.sequence"
    )
    checkpoints: Mapped[list["DiscoveryCheckpoint"]] = relationship(
        "DiscoveryCheckpoint", back_populates="session", cascade="all, delete-orphan", order_by="DiscoveryCheckpoint.sequence"
    )
    captures: Mapped[list["DiscoveryCapture"]] = relationship(
        "DiscoveryCapture", back_populates="session", cascade="all, delete-orphan"
    )
    events: Mapped[list["DiscoverySessionEvent"]] = relationship(
        "DiscoverySessionEvent", back_populates="session", cascade="all, delete-orphan", order_by="DiscoverySessionEvent.occurred_at"
    )


class DiscoveryAction(TimestampMixin, Base):
    """One structured captured action (Section 13's captured-action contract).

    The primary recording source — raw pointer/keyboard events may support
    interpretation but never replace this row.
    """

    __tablename__ = "discovery_actions"
    __table_args__ = (
        CheckConstraint("actor IN ('" + "','".join(ACTOR_TYPES) + "')", name="ck_discovery_actions_actor"),
        CheckConstraint(
            "action_family IN ('" + "','".join(ACTION_FAMILIES) + "')", name="ck_discovery_actions_family"
        ),
        CheckConstraint(
            "inclusion_state IN ('" + "','".join(ACTION_INCLUSION_STATES) + "')",
            name="ck_discovery_actions_inclusion_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    test_step_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action_family: Mapped[str] = mapped_column(String(30), nullable=False)

    target_semantic: Mapped[str | None] = mapped_column(String(300), nullable=True)
    target_screen_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_component_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_element_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)

    input_binding: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # sanitized — never raw secrets
    pre_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    post_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    evidence_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    locator_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    locator_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    inclusion_state: Mapped[str] = mapped_column(String(20), nullable=False, default="included", server_default="included")
    issue_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_history: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # tool-call reference

    session: Mapped["DiscoverySession"] = relationship("DiscoverySession", back_populates="actions")


class DiscoveryCheckpoint(TimestampMixin, Base):
    """A resumable snapshot — persisted BEFORE a pause is ever acknowledged
    (the checkpoint-before-pause invariant, Section 10)."""

    __tablename__ = "discovery_checkpoints"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    state_at_checkpoint: Mapped[str] = mapped_column(String(30), nullable=False)
    action_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sanitized_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    sanitized_screen: Mapped[str | None] = mapped_column(String(300), nullable=True)
    application_state_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    browser_session_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    evidence_snapshot_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)

    resumable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_actor: Mapped[str] = mapped_column(String(20), nullable=False, default="system")

    session: Mapped["DiscoverySession"] = relationship("DiscoverySession", back_populates="checkpoints")


class DiscoveryCapture(TimestampMixin, Base):
    """One stored evidence artifact — screenshot/DOM/network/console/trace."""

    __tablename__ = "discovery_captures"
    __table_args__ = (
        CheckConstraint("capture_type IN ('" + "','".join(CAPTURE_TYPES) + "')", name="ck_discovery_captures_type"),
        CheckConstraint(
            "redaction_state IN ('" + "','".join(REDACTION_STATES) + "')", name="ck_discovery_captures_redaction"
        ),
        CheckConstraint(
            "retention_state IN ('" + "','".join(RETENTION_STATES) + "')", name="ck_discovery_captures_retention"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    action_id: Mapped[int | None] = mapped_column(ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True, index=True)
    checkpoint_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovery_checkpoints.id", ondelete="SET NULL"), nullable=True, index=True
    )

    capture_type: Mapped[str] = mapped_column(String(30), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)  # always under the managed workspace root
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    captured_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    sanitized_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    redaction_state: Mapped[str] = mapped_column(String(20), nullable=False, default="not_required", server_default="not_required")
    retention_state: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")

    session: Mapped["DiscoverySession"] = relationship("DiscoverySession", back_populates="captures")


class DiscoverySessionEvent(TimestampMixin, Base):
    """Immutable session transition/command/audit log entry (Section 17's
    "Session Transition Event" + the Activity/Audit tab's data source)."""

    __tablename__ = "discovery_session_events"
    __table_args__ = (
        CheckConstraint("actor_type IN ('" + "','".join(ACTOR_TYPES) + "')", name="ck_discovery_session_events_actor_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="user")

    previous_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_state: Mapped[str] = mapped_column(String(30), nullable=False)
    command: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_step_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    checkpoint_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovery_checkpoints.id", ondelete="SET NULL"), nullable=True
    )
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)

    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    session: Mapped["DiscoverySession"] = relationship("DiscoverySession", back_populates="events")
