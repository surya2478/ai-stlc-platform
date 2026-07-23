"""041 - UI-015 Live Discovery Session (Phase 1 - Guided User Recording)

Adds the persisted discovery-session state machine and evidence contract:
discovery_sessions, discovery_actions, discovery_checkpoints,
discovery_captures, discovery_session_events. Additive only, no backfill
required (new tables carry no rows on upgrade).

Revision ID: 041
Revises: 040
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("project_applications.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("environment", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=30), nullable=False, server_default="GUIDED_USER"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="NOT_STARTED"),
        sa.Column("browser_target", sa.String(length=100), nullable=True),
        sa.Column("framework", sa.String(length=30), nullable=False, server_default="playwright"),
        sa.Column("auth_profile_reference", sa.String(length=200), nullable=True),
        sa.Column("test_case_id", sa.Integer(), sa.ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("test_case_version", sa.Integer(), nullable=True),
        sa.Column("requirement_ref", sa.String(length=100), nullable=True),
        sa.Column("ppm_ref", sa.String(length=100), nullable=True),
        sa.Column("journey_ref", sa.String(length=100), nullable=True),
        sa.Column("scenario_ref", sa.String(length=100), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("evidence_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("capture_options", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("allowed_hosts", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_reason", sa.Text(), nullable=True),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        sa.Column("latest_checkpoint_id", sa.Integer(), nullable=True),
        sa.Column("draft_model_version_id", sa.Integer(), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("current_step_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_command", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_command_idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("resume_state_classification", sa.String(length=40), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "mode IN ('GUIDED_USER','FREE_USER_ACTION','SUPERVISED_AGENT_DRIVEN')", name="ck_discovery_sessions_mode"
        ),
        sa.CheckConstraint(
            "status IN ('NOT_STARTED','INITIALISING','RECORDING','PAUSE_REQUESTED','PAUSED','RESUMING',"
            "'STOP_REQUESTED','STOPPED','COMPLETED','CANCELLED','FAILED','EMERGENCY_STOPPED')",
            name="ck_discovery_sessions_status",
        ),
    )
    op.create_index("ix_discovery_sessions_project_id", "discovery_sessions", ["project_id"])
    op.create_index("ix_discovery_sessions_application_id", "discovery_sessions", ["application_id"])
    op.create_index("ix_discovery_sessions_test_case_id", "discovery_sessions", ["test_case_id"])
    op.create_index("ix_discovery_sessions_correlation_id", "discovery_sessions", ["correlation_id"])
    op.create_index(
        "ix_discovery_sessions_last_command_idempotency_key", "discovery_sessions", ["last_command_idempotency_key"]
    )

    op.create_table(
        "discovery_actions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=20), nullable=False, server_default="user"),
        sa.Column("test_step_ref", sa.String(length=100), nullable=True),
        sa.Column("action_family", sa.String(length=30), nullable=False),
        sa.Column("target_semantic", sa.String(length=300), nullable=True),
        sa.Column("target_screen_ref", sa.String(length=200), nullable=True),
        sa.Column("target_component_ref", sa.String(length=200), nullable=True),
        sa.Column("target_element_ref", sa.String(length=200), nullable=True),
        sa.Column("input_binding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pre_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("post_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("locator_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("locator_confidence", sa.Integer(), nullable=True),
        sa.Column("inclusion_state", sa.String(length=20), nullable=False, server_default="included"),
        sa.Column("issue_note", sa.Text(), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("correction_history", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("actor IN ('user','agent','system')", name="ck_discovery_actions_actor"),
        sa.CheckConstraint(
            "action_family IN ('navigate','click','input','select','upload','download','wait','read',"
            "'api','database_validation','context_switch','mobile_gesture')",
            name="ck_discovery_actions_family",
        ),
        sa.CheckConstraint(
            "inclusion_state IN ('included','excluded','corrected','skipped','rolled_back')",
            name="ck_discovery_actions_inclusion_state",
        ),
    )
    op.create_index("ix_discovery_actions_session_id", "discovery_actions", ["session_id"])
    op.create_index("ix_discovery_actions_project_id", "discovery_actions", ["project_id"])

    op.create_table(
        "discovery_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("state_at_checkpoint", sa.String(length=30), nullable=False),
        sa.Column("action_position", sa.Integer(), nullable=True),
        sa.Column("sanitized_url", sa.String(length=2000), nullable=True),
        sa.Column("sanitized_screen", sa.String(length=300), nullable=True),
        sa.Column("application_state_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("browser_session_ref", sa.String(length=200), nullable=True),
        sa.Column("evidence_snapshot_ref", sa.String(length=500), nullable=True),
        sa.Column("resumable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_actor", sa.String(length=20), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_discovery_checkpoints_session_id", "discovery_checkpoints", ["session_id"])
    op.create_index("ix_discovery_checkpoints_project_id", "discovery_checkpoints", ["project_id"])

    op.create_table(
        "discovery_captures",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_id", sa.Integer(), sa.ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "checkpoint_id", sa.Integer(), sa.ForeignKey("discovery_checkpoints.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("capture_type", sa.String(length=30), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sanitized_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("redaction_state", sa.String(length=20), nullable=False, server_default="not_required"),
        sa.Column("retention_state", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "capture_type IN ('screenshot','dom_snapshot','accessibility_tree','network_log','console_log',"
            "'trace','video')",
            name="ck_discovery_captures_type",
        ),
        sa.CheckConstraint(
            "redaction_state IN ('not_required','applied','failed')", name="ck_discovery_captures_redaction"
        ),
        sa.CheckConstraint(
            "retention_state IN ('active','flagged','purged')", name="ck_discovery_captures_retention"
        ),
    )
    op.create_index("ix_discovery_captures_session_id", "discovery_captures", ["session_id"])
    op.create_index("ix_discovery_captures_project_id", "discovery_captures", ["project_id"])
    op.create_index("ix_discovery_captures_action_id", "discovery_captures", ["action_id"])
    op.create_index("ix_discovery_captures_checkpoint_id", "discovery_captures", ["checkpoint_id"])

    op.create_table(
        "discovery_session_events",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_type", sa.String(length=20), nullable=False, server_default="user"),
        sa.Column("previous_state", sa.String(length=30), nullable=True),
        sa.Column("new_state", sa.String(length=30), nullable=False),
        sa.Column("command", sa.String(length=30), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("current_step_ref", sa.String(length=200), nullable=True),
        sa.Column(
            "checkpoint_id", sa.Integer(), sa.ForeignKey("discovery_checkpoints.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("evidence_ref", sa.String(length=500), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("actor_type IN ('user','agent','system')", name="ck_discovery_session_events_actor_type"),
    )
    op.create_index("ix_discovery_session_events_session_id", "discovery_session_events", ["session_id"])
    op.create_index("ix_discovery_session_events_project_id", "discovery_session_events", ["project_id"])
    op.create_index("ix_discovery_session_events_idempotency_key", "discovery_session_events", ["idempotency_key"])
    op.create_index("ix_discovery_session_events_correlation_id", "discovery_session_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_discovery_session_events_correlation_id", table_name="discovery_session_events")
    op.drop_index("ix_discovery_session_events_idempotency_key", table_name="discovery_session_events")
    op.drop_index("ix_discovery_session_events_project_id", table_name="discovery_session_events")
    op.drop_index("ix_discovery_session_events_session_id", table_name="discovery_session_events")
    op.drop_table("discovery_session_events")

    op.drop_index("ix_discovery_captures_checkpoint_id", table_name="discovery_captures")
    op.drop_index("ix_discovery_captures_action_id", table_name="discovery_captures")
    op.drop_index("ix_discovery_captures_project_id", table_name="discovery_captures")
    op.drop_index("ix_discovery_captures_session_id", table_name="discovery_captures")
    op.drop_table("discovery_captures")

    op.drop_index("ix_discovery_checkpoints_project_id", table_name="discovery_checkpoints")
    op.drop_index("ix_discovery_checkpoints_session_id", table_name="discovery_checkpoints")
    op.drop_table("discovery_checkpoints")

    op.drop_index("ix_discovery_actions_project_id", table_name="discovery_actions")
    op.drop_index("ix_discovery_actions_session_id", table_name="discovery_actions")
    op.drop_table("discovery_actions")

    op.drop_index("ix_discovery_sessions_last_command_idempotency_key", table_name="discovery_sessions")
    op.drop_index("ix_discovery_sessions_correlation_id", table_name="discovery_sessions")
    op.drop_index("ix_discovery_sessions_test_case_id", table_name="discovery_sessions")
    op.drop_index("ix_discovery_sessions_application_id", table_name="discovery_sessions")
    op.drop_index("ix_discovery_sessions_project_id", table_name="discovery_sessions")
    op.drop_table("discovery_sessions")
