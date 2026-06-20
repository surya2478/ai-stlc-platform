"""Add Jira two-way sync tables.

Revision ID: 004_jira_two_way_sync
Revises: 003_project_memberships_rbac
Create Date: 2026-06-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "004_jira_two_way_sync"
down_revision: Union[str, None] = "003_project_memberships_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("requirements", sa.Column("jira_deleted", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("requirements", sa.Column("jira_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("requirements", sa.Column("jira_last_synced_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "jira_sync_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("jira_connections.id"), nullable=False),
        sa.Column("triggered_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_jira_sync_history_project_id", "jira_sync_history", ["project_id"])
    op.create_index("ix_jira_sync_history_connection_id", "jira_sync_history", ["connection_id"])
    op.create_index("ix_jira_sync_history_direction", "jira_sync_history", ["direction"])
    op.create_index("ix_jira_sync_history_status", "jira_sync_history", ["status"])

    op.create_table(
        "conflict_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("jira_connections.id"), nullable=False),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("requirements.id"), nullable=True),
        sa.Column("sync_history_id", sa.Integer(), sa.ForeignKey("jira_sync_history.id"), nullable=True),
        sa.Column("jira_issue_key", sa.String(100), nullable=False),
        sa.Column("conflict_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("local_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("remote_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("resolution", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("connection_id", "jira_issue_key", "status", name="uq_open_jira_conflict"),
    )
    op.create_index("ix_conflict_records_project_id", "conflict_records", ["project_id"])
    op.create_index("ix_conflict_records_connection_id", "conflict_records", ["connection_id"])
    op.create_index("ix_conflict_records_requirement_id", "conflict_records", ["requirement_id"])
    op.create_index("ix_conflict_records_jira_issue_key", "conflict_records", ["jira_issue_key"])
    op.create_index("ix_conflict_records_status", "conflict_records", ["status"])

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("jira_connections.id"), nullable=False),
        sa.Column("event_key", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("event_key", name="uq_webhook_events_event_key"),
    )
    op.create_index("ix_webhook_events_project_id", "webhook_events", ["project_id"])
    op.create_index("ix_webhook_events_connection_id", "webhook_events", ["connection_id"])
    op.create_index("ix_webhook_events_event_key", "webhook_events", ["event_key"])
    op.create_index("ix_webhook_events_status", "webhook_events", ["status"])


def downgrade() -> None:
    op.drop_index("ix_webhook_events_status", table_name="webhook_events")
    op.drop_index("ix_webhook_events_event_key", table_name="webhook_events")
    op.drop_index("ix_webhook_events_connection_id", table_name="webhook_events")
    op.drop_index("ix_webhook_events_project_id", table_name="webhook_events")
    op.drop_table("webhook_events")

    op.drop_index("ix_conflict_records_status", table_name="conflict_records")
    op.drop_index("ix_conflict_records_jira_issue_key", table_name="conflict_records")
    op.drop_index("ix_conflict_records_requirement_id", table_name="conflict_records")
    op.drop_index("ix_conflict_records_connection_id", table_name="conflict_records")
    op.drop_index("ix_conflict_records_project_id", table_name="conflict_records")
    op.drop_table("conflict_records")

    op.drop_index("ix_jira_sync_history_status", table_name="jira_sync_history")
    op.drop_index("ix_jira_sync_history_direction", table_name="jira_sync_history")
    op.drop_index("ix_jira_sync_history_connection_id", table_name="jira_sync_history")
    op.drop_index("ix_jira_sync_history_project_id", table_name="jira_sync_history")
    op.drop_table("jira_sync_history")

    op.drop_column("requirements", "jira_last_synced_at")
    op.drop_column("requirements", "jira_updated_at")
    op.drop_column("requirements", "jira_deleted")
