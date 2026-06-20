"""Add test data generation/import persistence.

Revision ID: 010_test_data_generation_import
Revises: 009_test_data_management
Create Date: 2026-06-11 00:30:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_test_data_generation_import"
down_revision: Union[str, None] = "009_test_data_management"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    new_columns = [
        sa.Column("generation_status", sa.String(length=50), nullable=False, server_default="not_requested"),
        sa.Column("generation_mode", sa.String(length=50), nullable=True),
        sa.Column("requested_record_count", sa.Integer(), nullable=True),
        sa.Column("actual_record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("external_tool", sa.String(length=100), nullable=True),
        sa.Column("external_suite_id", sa.String(length=255), nullable=True),
        sa.Column("external_dataset_id", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("request_notes", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(length=50), nullable=True),
        sa.Column("expected_by_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validation_status", sa.String(length=50), nullable=False, server_default="not_validated"),
        sa.Column("validation_summary_json", postgresql.JSONB(), nullable=True),
        sa.Column("import_filename", sa.String(length=255), nullable=True),
    ]
    for column in new_columns:
        op.add_column("test_data", column)

    op.create_index("ix_test_data_generation_status", "test_data", ["generation_status"], unique=False)
    op.create_index("ix_test_data_external_tool", "test_data", ["external_tool"], unique=False)
    op.create_index("ix_test_data_priority", "test_data", ["priority"], unique=False)
    op.create_index("ix_test_data_validation_status", "test_data", ["validation_status"], unique=False)

    op.create_table(
        "test_data_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("data_set_id", sa.Integer(), sa.ForeignKey("test_data.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("record_key", sa.String(length=255), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column("masked_payload_json", postgresql.JSONB(), nullable=True),
        sa.Column("validation_status", sa.String(length=50), nullable=False, server_default="valid"),
        sa.Column("validation_errors_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_test_data_records_data_set_id", "test_data_records", ["data_set_id"], unique=False)
    op.create_index("ix_test_data_records_project_id", "test_data_records", ["project_id"], unique=False)
    op.create_index("ix_test_data_records_record_key", "test_data_records", ["record_key"], unique=False)
    op.create_index("ix_test_data_records_validation_status", "test_data_records", ["validation_status"], unique=False)

    op.create_table(
        "test_data_import_previews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("preview_token", sa.String(length=100), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("detected_columns_json", postgresql.JSONB(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column("parsed_rows_json", postgresql.JSONB(), nullable=False),
        sa.Column("validation_errors_json", postgresql.JSONB(), nullable=False),
        sa.Column("validation_warnings_json", postgresql.JSONB(), nullable=False),
        sa.Column("can_import", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("preview_token"),
    )
    op.create_index("ix_test_data_import_previews_preview_token", "test_data_import_previews", ["preview_token"], unique=True)
    op.create_index("ix_test_data_import_previews_project_id", "test_data_import_previews", ["project_id"], unique=False)
    op.create_index("ix_test_data_import_previews_user_id", "test_data_import_previews", ["user_id"], unique=False)
    op.create_index("ix_test_data_import_previews_expires_at", "test_data_import_previews", ["expires_at"], unique=False)


def downgrade() -> None:
    for index_name in [
        "ix_test_data_import_previews_expires_at",
        "ix_test_data_import_previews_user_id",
        "ix_test_data_import_previews_project_id",
        "ix_test_data_import_previews_preview_token",
    ]:
        op.drop_index(index_name, table_name="test_data_import_previews")
    op.drop_table("test_data_import_previews")

    for index_name in [
        "ix_test_data_records_validation_status",
        "ix_test_data_records_record_key",
        "ix_test_data_records_project_id",
        "ix_test_data_records_data_set_id",
    ]:
        op.drop_index(index_name, table_name="test_data_records")
    op.drop_table("test_data_records")

    for index_name in [
        "ix_test_data_validation_status",
        "ix_test_data_priority",
        "ix_test_data_external_tool",
        "ix_test_data_generation_status",
    ]:
        op.drop_index(index_name, table_name="test_data")

    for column_name in [
        "import_filename",
        "validation_summary_json",
        "validation_status",
        "expected_by_date",
        "priority",
        "request_notes",
        "external_url",
        "external_dataset_id",
        "external_suite_id",
        "external_tool",
        "actual_record_count",
        "requested_record_count",
        "generation_mode",
        "generation_status",
    ]:
        op.drop_column("test_data", column_name)
