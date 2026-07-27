"""048 - UI-019 Live Recorder

Additive only. Extends `discovery_sessions` with the Automation Test Suite
linkage and recording metadata UI-019 needs (every new column is either
nullable or carries a server_default, so existing UI-015 rows are valid
without a data migration), and adds the six tables that hold what UI-019 adds
on top of the shared capture engine: step state, action-to-step mapping,
validation checkpoints, multi-application segments, data bindings, notes, and
the emitted Automation IR draft.

No existing column changes type or nullability. `discovery_actions`,
`discovery_captures` and `discovery_session_events` are reused untouched —
see app.models.recording_session for why.

Revision ID: 048
Revises: 047
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None

STEP_STATES = (
    "PENDING", "ACTIVE", "RECORDED", "PARTIALLY_RECORDED",
    "SKIPPED", "MISMATCH", "NEEDS_REVIEW", "COMPLETED",
)
MAPPING_SOURCES = ("active_step", "user", "unmapped")
MAPPING_REVIEW_STATES = ("accepted", "needs_review", "rejected")
CHECKPOINT_TYPES = (
    "element_visible", "element_hidden", "text_equals", "text_contains",
    "value_equals", "attribute_equals", "url_matches", "title_matches",
    "download_complete", "file_exists", "api_status", "api_response_field",
    "network_request_occurred", "no_severe_console_errors",
    "mobile_element_state", "application_transition_complete",
    "async_process_status", "custom_adapter_validation",
)
CHECKPOINT_SOURCES = ("user", "recommended")
CHECKPOINT_REVIEW_STATES = ("accepted", "needs_review", "rejected")
DATA_BINDING_CLASSIFICATIONS = (
    "static_value", "test_data_parameter", "generated_value", "secret_reference",
    "previous_step_output", "environment_value", "runtime_value",
)
NOTE_SCOPES = ("session", "step", "action", "checkpoint", "segment")
IR_DRAFT_STATUSES = ("DRAFT", "SUPERSEDED")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return column + " IN ('" + "','".join(values) + "')"


def upgrade() -> None:
    # ── discovery_sessions: UI-019 columns ──
    op.add_column(
        "discovery_sessions",
        sa.Column("recording_origin", sa.String(length=30), nullable=False, server_default="discovery"),
    )
    op.create_index(
        "ix_discovery_sessions_recording_origin", "discovery_sessions", ["recording_origin"]
    )
    op.add_column("discovery_sessions", sa.Column("suite_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_discovery_sessions_suite_id", "discovery_sessions", "automation_suites",
        ["suite_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_discovery_sessions_suite_id", "discovery_sessions", ["suite_id"])
    op.add_column("discovery_sessions", sa.Column("suite_member_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_discovery_sessions_suite_member_id", "discovery_sessions", "automation_suite_test_cases",
        ["suite_member_id"], ["id"], ondelete="SET NULL",
    )
    op.add_column("discovery_sessions", sa.Column("recording_mode", sa.String(length=30), nullable=True))
    op.add_column(
        "discovery_sessions",
        sa.Column("ir_status", sa.String(length=30), nullable=False, server_default="NOT_GENERATED"),
    )
    op.add_column(
        "discovery_sessions",
        sa.Column("recording_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("discovery_sessions", sa.Column("parent_recording_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_discovery_sessions_parent_recording_id", "discovery_sessions", "discovery_sessions",
        ["parent_recording_id"], ["id"], ondelete="SET NULL",
    )

    # ── recording_step_states ──
    op.create_table(
        "recording_step_states",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_key", sa.String(length=50), nullable=False),
        sa.Column("source_step_index", sa.Integer(), nullable=True),
        sa.Column("parent_step_key", sa.String(length=50), nullable=True),
        sa.Column("discovered_label", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(_in_list("status", STEP_STATES), name="ck_recording_step_states_status"),
        sa.UniqueConstraint("session_id", "step_key", name="uq_recording_step_states_session_step"),
    )
    op.create_index("ix_recording_step_states_session_id", "recording_step_states", ["session_id"])
    op.create_index("ix_recording_step_states_project_id", "recording_step_states", ["project_id"])

    # ── recording_step_mappings ──
    op.create_table(
        "recording_step_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "action_id", sa.Integer(), sa.ForeignKey("discovery_actions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("step_key", sa.String(length=50), nullable=False),
        sa.Column("mapping_source", sa.String(length=20), nullable=False, server_default="active_step"),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("review_state", sa.String(length=20), nullable=False, server_default="accepted"),
        sa.Column("lifecycle_phase", sa.String(length=20), nullable=True),
        sa.Column("excluded_from_ir", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("exclusion_reason", sa.Text(), nullable=True),
        sa.Column("mapped_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(_in_list("mapping_source", MAPPING_SOURCES), name="ck_recording_step_mappings_source"),
        sa.CheckConstraint(
            _in_list("review_state", MAPPING_REVIEW_STATES), name="ck_recording_step_mappings_review_state"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_recording_step_mappings_confidence_range",
        ),
        sa.UniqueConstraint("action_id", name="uq_recording_step_mappings_action"),
    )
    op.create_index("ix_recording_step_mappings_session_id", "recording_step_mappings", ["session_id"])
    op.create_index("ix_recording_step_mappings_project_id", "recording_step_mappings", ["project_id"])
    op.create_index("ix_recording_step_mappings_action_id", "recording_step_mappings", ["action_id"])
    op.create_index("ix_recording_step_mappings_step_key", "recording_step_mappings", ["step_key"])

    # ── recording_checkpoints ──
    op.create_table(
        "recording_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "action_id", sa.Integer(), sa.ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("step_key", sa.String(length=50), nullable=True),
        sa.Column("checkpoint_type", sa.String(length=40), nullable=False),
        sa.Column("target", sa.String(length=1000), nullable=True),
        sa.Column("expected_value", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="user"),
        sa.Column("review_state", sa.String(length=20), nullable=False, server_default="accepted"),
        sa.Column("recommendation_reason", sa.Text(), nullable=True),
        sa.Column("expected_result_ref", sa.Text(), nullable=True),
        sa.Column(
            "evidence_capture_id", sa.Integer(),
            sa.ForeignKey("discovery_captures.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(_in_list("checkpoint_type", CHECKPOINT_TYPES), name="ck_recording_checkpoints_type"),
        sa.CheckConstraint(_in_list("source", CHECKPOINT_SOURCES), name="ck_recording_checkpoints_source"),
        sa.CheckConstraint(
            _in_list("review_state", CHECKPOINT_REVIEW_STATES), name="ck_recording_checkpoints_review_state"
        ),
    )
    op.create_index("ix_recording_checkpoints_session_id", "recording_checkpoints", ["session_id"])
    op.create_index("ix_recording_checkpoints_project_id", "recording_checkpoints", ["project_id"])
    op.create_index("ix_recording_checkpoints_action_id", "recording_checkpoints", ["action_id"])
    op.create_index("ix_recording_checkpoints_step_key", "recording_checkpoints", ["step_key"])

    # ── recording_segments ──
    op.create_table(
        "recording_segments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "application_id", sa.Integer(),
            sa.ForeignKey("project_applications.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("environment", sa.String(length=100), nullable=False),
        sa.Column("framework", sa.String(length=50), nullable=True),
        sa.Column("adapter", sa.String(length=50), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_action_sequence", sa.Integer(), nullable=True),
        sa.Column("end_action_sequence", sa.Integer(), nullable=True),
        sa.Column("transition_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("session_id", "sequence", name="uq_recording_segments_session_sequence"),
    )
    op.create_index("ix_recording_segments_session_id", "recording_segments", ["session_id"])
    op.create_index("ix_recording_segments_project_id", "recording_segments", ["project_id"])

    # ── recording_data_bindings ──
    op.create_table(
        "recording_data_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "action_id", sa.Integer(), sa.ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("placeholder", sa.String(length=200), nullable=False),
        sa.Column("classification", sa.String(length=30), nullable=False),
        sa.Column("test_data_id", sa.Integer(), sa.ForeignKey("test_data.id", ondelete="SET NULL"), nullable=True),
        sa.Column("secret_reference", sa.String(length=200), nullable=True),
        sa.Column(
            "source_action_id", sa.Integer(),
            sa.ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("environment_key", sa.String(length=200), nullable=True),
        sa.Column("sample_value", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            _in_list("classification", DATA_BINDING_CLASSIFICATIONS),
            name="ck_recording_data_bindings_classification",
        ),
        sa.CheckConstraint(
            "classification <> 'secret_reference' OR sample_value IS NULL",
            name="ck_recording_data_bindings_secret_has_no_value",
        ),
        sa.UniqueConstraint("session_id", "name", name="uq_recording_data_bindings_session_name"),
    )
    op.create_index("ix_recording_data_bindings_session_id", "recording_data_bindings", ["session_id"])
    op.create_index("ix_recording_data_bindings_project_id", "recording_data_bindings", ["project_id"])
    op.create_index("ix_recording_data_bindings_action_id", "recording_data_bindings", ["action_id"])

    # ── recording_notes ──
    op.create_table(
        "recording_notes",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="session"),
        sa.Column("step_key", sa.String(length=50), nullable=True),
        sa.Column(
            "action_id", sa.Integer(), sa.ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "checkpoint_id", sa.Integer(),
            sa.ForeignKey("recording_checkpoints.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "segment_id", sa.Integer(), sa.ForeignKey("recording_segments.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(_in_list("scope", NOTE_SCOPES), name="ck_recording_notes_scope"),
    )
    op.create_index("ix_recording_notes_session_id", "recording_notes", ["session_id"])
    op.create_index("ix_recording_notes_project_id", "recording_notes", ["project_id"])

    # ── automation_ir_drafts ──
    op.create_table(
        "automation_ir_drafts",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("suite_id", sa.Integer(), sa.ForeignKey("automation_suites.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "test_case_id", sa.Integer(), sa.ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("contract", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("contract_version", sa.String(length=10), nullable=False, server_default="1.0"),
        sa.Column(
            "source_action_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
        ),
        sa.Column("readiness", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("generated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(_in_list("status", IR_DRAFT_STATUSES), name="ck_automation_ir_drafts_status"),
    )
    op.create_index("ix_automation_ir_drafts_project_id", "automation_ir_drafts", ["project_id"])
    op.create_index("ix_automation_ir_drafts_session_id", "automation_ir_drafts", ["session_id"])
    op.create_index("ix_automation_ir_drafts_suite_id", "automation_ir_drafts", ["suite_id"])
    op.create_index("ix_automation_ir_drafts_test_case_id", "automation_ir_drafts", ["test_case_id"])
    op.create_index("ix_automation_ir_drafts_is_current", "automation_ir_drafts", ["is_current"])


def downgrade() -> None:
    op.drop_table("automation_ir_drafts")
    op.drop_table("recording_notes")
    op.drop_table("recording_data_bindings")
    op.drop_table("recording_segments")
    op.drop_table("recording_checkpoints")
    op.drop_table("recording_step_mappings")
    op.drop_table("recording_step_states")

    op.drop_constraint("fk_discovery_sessions_parent_recording_id", "discovery_sessions", type_="foreignkey")
    op.drop_column("discovery_sessions", "parent_recording_id")
    op.drop_column("discovery_sessions", "recording_version")
    op.drop_column("discovery_sessions", "ir_status")
    op.drop_column("discovery_sessions", "recording_mode")
    op.drop_constraint("fk_discovery_sessions_suite_member_id", "discovery_sessions", type_="foreignkey")
    op.drop_column("discovery_sessions", "suite_member_id")
    op.drop_index("ix_discovery_sessions_suite_id", table_name="discovery_sessions")
    op.drop_constraint("fk_discovery_sessions_suite_id", "discovery_sessions", type_="foreignkey")
    op.drop_column("discovery_sessions", "suite_id")
    op.drop_index("ix_discovery_sessions_recording_origin", table_name="discovery_sessions")
    op.drop_column("discovery_sessions", "recording_origin")
