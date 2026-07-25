"""045 - UI-017 API and Network Explorer (Phase 1)

Adds network_events (structured requests parsed from a discovery session's
masked network_log capture text) and network_event_activity (residual audit
log for review actions). Additive only.

Revision ID: 045
Revises: 044
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "network_events",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capture_id", sa.Integer(), sa.ForeignKey("discovery_captures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_id", sa.Integer(), sa.ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("parse_state", sa.String(length=20), nullable=False, server_default="unparsed"),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("host", sa.String(length=300), nullable=True),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("is_external", sa.Boolean(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("status_text", sa.String(length=200), nullable=True),
        sa.Column("raw_line", sa.Text(), nullable=False),
        sa.Column("review_state", sa.String(length=20), nullable=False, server_default="unreviewed"),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("parse_state IN ('parsed','unparsed')", name="ck_network_events_parse_state"),
        sa.CheckConstraint("review_state IN ('unreviewed','reviewed','ignored')", name="ck_network_events_review_state"),
    )
    op.create_index("ix_network_events_project_id", "network_events", ["project_id"])
    op.create_index("ix_network_events_session_id", "network_events", ["session_id"])
    op.create_index("ix_network_events_capture_id", "network_events", ["capture_id"])
    op.create_index("ix_network_events_action_id", "network_events", ["action_id"])
    op.create_index("ix_network_events_method", "network_events", ["method"])
    op.create_index("ix_network_events_host", "network_events", ["host"])
    op.create_index("ix_network_events_status_code", "network_events", ["status_code"])

    op.create_table(
        "network_event_activity",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("network_events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_network_event_activity_project_id", "network_event_activity", ["project_id"])
    op.create_index("ix_network_event_activity_session_id", "network_event_activity", ["session_id"])
    op.create_index("ix_network_event_activity_event_id", "network_event_activity", ["event_id"])
    op.create_index("ix_network_event_activity_event_type", "network_event_activity", ["event_type"])
    op.create_index("ix_network_event_activity_correlation_id", "network_event_activity", ["correlation_id"])


def downgrade() -> None:
    op.drop_table("network_event_activity")
    op.drop_table("network_events")
