"""UI-019 Live Recorder — the suite/test-case-scoped overlay on a recording run.

The capture engine itself is *not* redefined here. A Live Recorder run IS a
`DiscoverySession` (UI-015): the same state machine, the same
`DiscoveryAction` rows, the same `DiscoveryCapture` evidence and the same
`DiscoverySessionEvent` audit trail. Contract Section 29 is explicit that the
illustrative `recording_*` entity names "must not duplicate existing models",
and duplicating the action/evidence tables would have forked the one place
that actually observes a browser.

What lives here is only what UI-019 adds and UI-015 has no concept of:

- which Automation Test Suite member the run belongs to (columns added to
  `discovery_sessions`, not a second session table)
- per-test-case-step recording state and action-to-step mapping (Section 15)
- validation checkpoints (Section 16) — distinct from `DiscoveryCheckpoint`,
  which is a *resume* checkpoint and answers a different question
- multi-application segments (Section 17)
- data-binding classification (Section 18)
- notes (Section 12.6)
- the emitted Automation IR draft (Section 22)

Step identity uses a `step_key` string rather than a bare index so a
discovered sub-step (Section 10.3) is addressable without renumbering the
source test case: "3" is the test case's third step, "3.1" is a sub-step
discovered underneath it. The step's *text* is never copied here — it is read
from the test case at render time, because the test case is the source of
truth (Section 4) and a copy would silently go stale.
"""
from __future__ import annotations

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

# Section 7 — which recording discipline the run follows. Deliberately not the
# same axis as `DiscoverySession.mode`, which describes who drives the browser
# (user vs agent). A Live Recorder run is always user-driven; this says
# whether it is walking the test case or exploring.
RECORDING_MODES = ("GUIDED_TEST_CASE", "EXPLORATORY")

# Which surface opened the session. Existing UI-015 rows backfill to
# "discovery" so the two surfaces never show each other's sessions.
RECORDING_ORIGINS = ("discovery", "live_recorder")

# Section 10.3.
STEP_STATES = (
    "PENDING", "ACTIVE", "RECORDED", "PARTIALLY_RECORDED",
    "SKIPPED", "MISMATCH", "NEEDS_REVIEW", "COMPLETED",
)

# Section 15 — how an action came to be attached to a step. "active_step" is
# the automatic path (the step that was active when the action was recorded);
# "user" is an explicit mapping or re-mapping; "unmapped" exists so an action
# with no home is a queryable state rather than a missing row.
MAPPING_SOURCES = ("active_step", "user", "unmapped")
MAPPING_REVIEW_STATES = ("accepted", "needs_review", "rejected")

# Section 16.
CHECKPOINT_TYPES = (
    "element_visible", "element_hidden", "text_equals", "text_contains",
    "value_equals", "attribute_equals", "url_matches", "title_matches",
    "download_complete", "file_exists", "api_status", "api_response_field",
    "network_request_occurred", "no_severe_console_errors",
    "mobile_element_state", "application_transition_complete",
    "async_process_status", "custom_adapter_validation",
)
# A recorder-proposed checkpoint enters as "recommended" and must be reviewed
# before it can reach the IR — Section 16's "recommendations must not silently
# become final assertions".
CHECKPOINT_SOURCES = ("user", "recommended")
CHECKPOINT_REVIEW_STATES = ("accepted", "needs_review", "rejected")

# Section 18. `secret_reference` never carries a sample value — see the check
# constraint on RecordingDataBinding.
DATA_BINDING_CLASSIFICATIONS = (
    "static_value", "test_data_parameter", "generated_value", "secret_reference",
    "previous_step_output", "environment_value", "runtime_value",
)

NOTE_SCOPES = ("session", "step", "action", "checkpoint", "segment")

IR_DRAFT_STATUSES = ("DRAFT", "SUPERSEDED")


class RecordingStepState(TimestampMixin, Base):
    """One test case step's (or discovered sub-step's) recording state.

    Rows are created lazily — a step with no row has never been touched and
    reads as PENDING. That keeps a 200-step test case from writing 200 rows
    for a session that recorded three of them.
    """

    __tablename__ = "recording_step_states"
    __table_args__ = (
        CheckConstraint("status IN ('" + "','".join(STEP_STATES) + "')", name="ck_recording_step_states_status"),
        UniqueConstraint("session_id", "step_key", name="uq_recording_step_states_session_step"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # "3" for the test case's third step, "3.1" for a sub-step discovered
    # underneath it. See the module docstring.
    step_key: Mapped[str] = mapped_column(String(50), nullable=False)
    # Index into the live test case's `steps` array. Null for a discovered
    # sub-step, which has no counterpart in the source test case.
    source_step_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_step_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Only ever set for a discovered sub-step — a real step's text is read
    # from the test case, never copied (Section 4).
    discovered_label: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING", server_default="PENDING")
    # Mandatory when status is SKIPPED (Section 7.1) — enforced in the
    # service, where the message can name the step.
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    session: Mapped["DiscoverySession"] = relationship("DiscoverySession")


class RecordingStepMapping(TimestampMixin, Base):
    """One recorded action's attachment to one step (Section 15).

    Unique on `action_id`: an action belongs to at most one step. Many actions
    per step is the normal case and is what "map multiple actions to one step"
    means; the reverse would make the IR's ordering ambiguous.
    """

    __tablename__ = "recording_step_mappings"
    __table_args__ = (
        CheckConstraint(
            "mapping_source IN ('" + "','".join(MAPPING_SOURCES) + "')", name="ck_recording_step_mappings_source"
        ),
        CheckConstraint(
            "review_state IN ('" + "','".join(MAPPING_REVIEW_STATES) + "')",
            name="ck_recording_step_mappings_review_state",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_recording_step_mappings_confidence_range",
        ),
        UniqueConstraint("action_id", name="uq_recording_step_mappings_action"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    action_id: Mapped[int] = mapped_column(
        ForeignKey("discovery_actions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    step_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    mapping_source: Mapped[str] = mapped_column(String(20), nullable=False, default="active_step")
    # Null when the mapping is a direct user decision — a person choosing a
    # step is not a confidence score, and storing 100 would misrepresent it.
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accepted", server_default="accepted"
    )

    # Section 15 — an action can be marked as setup/teardown, or held out of
    # the IR entirely, without being deleted.
    lifecycle_phase: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "setup" | "teardown"
    excluded_from_ir: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    mapped_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    session: Mapped["DiscoverySession"] = relationship("DiscoverySession")


class RecordingCheckpoint(TimestampMixin, Base):
    """A validation checkpoint (Section 16).

    Not to be confused with `DiscoveryCheckpoint`, which is a resume point.
    This is an assertion the generated script will make.
    """

    __tablename__ = "recording_checkpoints"
    __table_args__ = (
        CheckConstraint(
            "checkpoint_type IN ('" + "','".join(CHECKPOINT_TYPES) + "')", name="ck_recording_checkpoints_type"
        ),
        CheckConstraint(
            "source IN ('" + "','".join(CHECKPOINT_SOURCES) + "')", name="ck_recording_checkpoints_source"
        ),
        CheckConstraint(
            "review_state IN ('" + "','".join(CHECKPOINT_REVIEW_STATES) + "')",
            name="ck_recording_checkpoints_review_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    # Null for a checkpoint attached to a step rather than a specific action.
    action_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    step_key: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    checkpoint_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[str] = mapped_column(String(20), nullable=False, default="user", server_default="user")
    review_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accepted", server_default="accepted"
    )
    # Why the recorder proposed this one — shown verbatim to the reviewer so a
    # recommendation is never accepted blind.
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The step's expected result this checkpoint is meant to satisfy, so
    # Section 21's "expected results without checkpoints" gap is answerable.
    expected_result_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_capture_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovery_captures.id", ondelete="SET NULL"), nullable=True
    )

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["DiscoverySession"] = relationship("DiscoverySession")


class RecordingSegment(TimestampMixin, Base):
    """One application's stretch of a multi-application journey (Section 17).

    A new adapter/application/environment combination opens a new segment
    within the same session — it never starts a second session, because the
    runtime values that flow between applications belong to one journey.
    """

    __tablename__ = "recording_segments"
    __table_args__ = (UniqueConstraint("session_id", "sequence", name="uq_recording_segments_session_sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("project_applications.id", ondelete="RESTRICT"), nullable=False
    )
    environment: Mapped[str] = mapped_column(String(100), nullable=False)
    framework: Mapped[str | None] = mapped_column(String(50), nullable=True)
    adapter: Mapped[str | None] = mapped_column(String(50), nullable=True)

    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Action-sequence range this segment covers. `end_action_sequence` stays
    # null while the segment is the open one.
    start_action_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_action_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    transition_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    session: Mapped["DiscoverySession"] = relationship("DiscoverySession")


class RecordingDataBinding(TimestampMixin, Base):
    """How one captured input should be parameterized (Section 18)."""

    __tablename__ = "recording_data_bindings"
    __table_args__ = (
        CheckConstraint(
            "classification IN ('" + "','".join(DATA_BINDING_CLASSIFICATIONS) + "')",
            name="ck_recording_data_bindings_classification",
        ),
        # Section 18's hard rule, enforced by the database rather than only by
        # the service: a secret reference never carries a value.
        CheckConstraint(
            "classification <> 'secret_reference' OR sample_value IS NULL",
            name="ck_recording_data_bindings_secret_has_no_value",
        ),
        UniqueConstraint("session_id", "name", name="uq_recording_data_bindings_session_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    action_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    placeholder: Mapped[str] = mapped_column(String(200), nullable=False)
    classification: Mapped[str] = mapped_column(String(30), nullable=False)

    # Only one of these is meaningful, depending on `classification`.
    test_data_id: Mapped[int | None] = mapped_column(ForeignKey("test_data.id", ondelete="SET NULL"), nullable=True)
    secret_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_action_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True
    )
    environment_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Non-sensitive literals only. Null whenever the classification is
    # secret_reference (see the check constraint above).
    sample_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    session: Mapped["DiscoverySession"] = relationship("DiscoverySession")


class RecordingNote(TimestampMixin, Base):
    """A note attached to the session, a step, an action, a checkpoint or a
    segment (Section 12.6)."""

    __tablename__ = "recording_notes"
    __table_args__ = (
        CheckConstraint("scope IN ('" + "','".join(NOTE_SCOPES) + "')", name="ck_recording_notes_scope"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="session")
    step_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    action_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True
    )
    checkpoint_id: Mapped[int | None] = mapped_column(
        ForeignKey("recording_checkpoints.id", ondelete="CASCADE"), nullable=True
    )
    segment_id: Mapped[int | None] = mapped_column(
        ForeignKey("recording_segments.id", ondelete="CASCADE"), nullable=True
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    session: Mapped["DiscoverySession"] = relationship("DiscoverySession")


class AutomationIrDraft(TimestampMixin, Base):
    """The framework-neutral Automation IR emitted from a recording (Section 22).

    `contract` holds a serialized `AutomationGenerationContract` — the same
    validated structure the script compiler already renders to Playwright and
    pytest. Nothing new was invented for the IR; recording just became a
    second way to produce one, alongside generation.

    `source_action_ids` is what makes Section 22's "IR must retain the source
    recording session and action IDs" true, and is what lets UI-020 show a
    reviewer which observed action produced a given IR step.
    """

    __tablename__ = "automation_ir_drafts"
    __table_args__ = (
        CheckConstraint("status IN ('" + "','".join(IR_DRAFT_STATUSES) + "')", name="ck_automation_ir_drafts_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suite_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_suites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT", server_default="DRAFT")

    contract: Mapped[dict] = mapped_column(JSONB, nullable=False)
    contract_version: Mapped[str] = mapped_column(String(10), nullable=False, default="1.0", server_default="1.0")
    source_action_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # What the emitter could not resolve, stated rather than silently dropped
    # (e.g. an action with no accepted locator, an expected result with no
    # checkpoint). UI-020 shows these as the first thing a reviewer sees.
    readiness: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    session: Mapped["DiscoverySession"] = relationship("DiscoverySession")
