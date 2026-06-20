"""Expand test data into a governed management module.

Revision ID: 009_test_data_management
Revises: 008_test_case_metadata_history
Create Date: 2026-06-11 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009_test_data_management"
down_revision: Union[str, None] = "008_test_case_metadata_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_data_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("template_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("telecom_domain", sa.String(length=100), nullable=True),
        sa.Column("test_phase", sa.String(length=100), nullable=True),
        sa.Column("data_type", sa.String(length=100), nullable=False, server_default="Generic"),
        sa.Column("schema_json", postgresql.JSONB(), nullable=True),
        sa.Column("default_generation_rules_json", postgresql.JSONB(), nullable=True),
        sa.Column("validation_rules_json", postgresql.JSONB(), nullable=True),
        sa.Column("masking_rules_json", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    new_columns = [
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("requirements.id"), nullable=True),
        sa.Column("execution_run_id", sa.Integer(), sa.ForeignKey("execution_runs.id"), nullable=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("test_data_templates.id"), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reserved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False, server_default="Test Data"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data_type", sa.String(length=100), nullable=False, server_default="Generic"),
        sa.Column("source_type", sa.String(length=100), nullable=False, server_default="manual"),
        sa.Column("data_payload_json", postgresql.JSONB(), nullable=True),
        sa.Column("schema_json", postgresql.JSONB(), nullable=True),
        sa.Column("sample_preview_json", postgresql.JSONB(), nullable=True),
        sa.Column("sensitive_fields_json", postgresql.JSONB(), nullable=True),
        sa.Column("masking_rules_json", postgresql.JSONB(), nullable=True),
        sa.Column("validation_rules_json", postgresql.JSONB(), nullable=True),
        sa.Column("approval_status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("telecom_domain", sa.String(length=100), nullable=True),
        sa.Column("test_phase", sa.String(length=100), nullable=True),
        sa.Column("environment", sa.String(length=100), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("linked_requirement_key", sa.String(length=100), nullable=True),
        sa.Column("linked_jira_issue_key", sa.String(length=100), nullable=True),
        sa.Column("linked_jira_url", sa.Text(), nullable=True),
        sa.Column("linked_defect_id", sa.Integer(), nullable=True),
        sa.Column("privacy_level", sa.String(length=50), nullable=False, server_default="internal"),
        sa.Column("contains_pii", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("masking_status", sa.String(length=50), nullable=False, server_default="not_required"),
        sa.Column("synthetic_generation_status", sa.String(length=50), nullable=False, server_default="not_required"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reservation_status", sa.String(length=50), nullable=False, server_default="available"),
        sa.Column("reserved_for_execution_id", sa.Integer(), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reservation_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("quality_status", sa.String(length=50), nullable=False, server_default="not_checked"),
        sa.Column("quality_issues_json", postgresql.JSONB(), nullable=True),
        sa.Column("jira_sync_status", sa.String(length=50), nullable=False, server_default="not_synced"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_error", sa.Text(), nullable=True),
    ]

    for column in new_columns:
        op.add_column("test_data", column)

    op.alter_column("test_data", "status", existing_type=sa.String(length=50), server_default="draft")

    indexes = [
        ("ix_test_data_data_type", ["data_type"]),
        ("ix_test_data_source_type", ["source_type"]),
        ("ix_test_data_approval_status", ["approval_status"]),
        ("ix_test_data_masking_status", ["masking_status"]),
        ("ix_test_data_quality_status", ["quality_status"]),
        ("ix_test_data_reservation_status", ["reservation_status"]),
        ("ix_test_data_jira_sync_status", ["jira_sync_status"]),
        ("ix_test_data_linked_jira_issue_key", ["linked_jira_issue_key"]),
        ("ix_test_data_environment", ["environment"]),
        ("ix_test_data_telecom_domain", ["telecom_domain"]),
        ("ix_test_data_test_phase", ["test_phase"]),
    ]
    for index_name, columns in indexes:
        op.create_index(index_name, "test_data", columns, unique=False)


def downgrade() -> None:
    for index_name in [
        "ix_test_data_test_phase",
        "ix_test_data_telecom_domain",
        "ix_test_data_environment",
        "ix_test_data_linked_jira_issue_key",
        "ix_test_data_jira_sync_status",
        "ix_test_data_reservation_status",
        "ix_test_data_quality_status",
        "ix_test_data_masking_status",
        "ix_test_data_approval_status",
        "ix_test_data_source_type",
        "ix_test_data_data_type",
    ]:
        op.drop_index(index_name, table_name="test_data")

    for column_name in [
        "sync_error",
        "last_synced_at",
        "jira_sync_status",
        "quality_issues_json",
        "quality_status",
        "quality_score",
        "usage_count",
        "last_used_at",
        "released_at",
        "consumed_at",
        "reservation_expires_at",
        "reserved_at",
        "reserved_for_execution_id",
        "reservation_status",
        "approved_at",
        "rejection_reason",
        "synthetic_generation_status",
        "masking_status",
        "contains_pii",
        "privacy_level",
        "linked_defect_id",
        "linked_jira_url",
        "linked_jira_issue_key",
        "linked_requirement_key",
        "tags",
        "version",
        "environment",
        "test_phase",
        "telecom_domain",
        "approval_status",
        "validation_rules_json",
        "masking_rules_json",
        "sensitive_fields_json",
        "sample_preview_json",
        "schema_json",
        "data_payload_json",
        "source_type",
        "data_type",
        "description",
        "name",
        "reserved_by",
        "approved_by",
        "updated_by",
        "template_id",
        "execution_run_id",
        "requirement_id",
    ]:
        op.drop_column("test_data", column_name)

    op.drop_table("test_data_templates")
