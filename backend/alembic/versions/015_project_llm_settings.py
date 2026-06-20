"""015 - project-level LLM settings and audit logs

Revision ID: 015
Revises: 014
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_llm_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("provider_name", sa.String(length=120), nullable=False),
        sa.Column("provider_key", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fallback_priority", sa.Integer(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.2"),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="4000"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("module_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("config_status", sa.String(length=50), nullable=False, server_default="disabled"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_llm_settings_id", "project_llm_settings", ["id"])
    op.create_index("ix_project_llm_settings_project_id", "project_llm_settings", ["project_id"])
    op.create_index("ix_project_llm_settings_provider_key", "project_llm_settings", ["provider_key"])
    op.create_index("uq_project_llm_provider", "project_llm_settings", ["project_id", "provider_key"], unique=True)
    op.create_index(
        "uq_project_primary_llm",
        "project_llm_settings",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )
    op.create_index(
        "uq_project_fallback_priority",
        "project_llm_settings",
        ["project_id", "fallback_priority"],
        unique=True,
        postgresql_where=sa.text("is_fallback IS TRUE"),
    )

    op.create_table(
        "project_setting_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("setting_type", sa.String(length=80), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("changed_by", sa.Integer(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="ui"),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_setting_audit_logs_id", "project_setting_audit_logs", ["id"])
    op.create_index("ix_project_setting_audit_logs_project_id", "project_setting_audit_logs", ["project_id"])
    op.create_index("ix_project_setting_audit_logs_setting_type", "project_setting_audit_logs", ["setting_type"])


def downgrade() -> None:
    op.drop_index("ix_project_setting_audit_logs_setting_type", table_name="project_setting_audit_logs")
    op.drop_index("ix_project_setting_audit_logs_project_id", table_name="project_setting_audit_logs")
    op.drop_index("ix_project_setting_audit_logs_id", table_name="project_setting_audit_logs")
    op.drop_table("project_setting_audit_logs")

    op.drop_index("uq_project_fallback_priority", table_name="project_llm_settings")
    op.drop_index("uq_project_primary_llm", table_name="project_llm_settings")
    op.drop_index("uq_project_llm_provider", table_name="project_llm_settings")
    op.drop_index("ix_project_llm_settings_provider_key", table_name="project_llm_settings")
    op.drop_index("ix_project_llm_settings_project_id", table_name="project_llm_settings")
    op.drop_index("ix_project_llm_settings_id", table_name="project_llm_settings")
    op.drop_table("project_llm_settings")
