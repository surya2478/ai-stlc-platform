"""043 - Test case import previews

Revision ID: 043
Revises: 042
Create Date: 2026-07-24

Adds test_case_import_previews — the same preview-token/expiry/single-use
pattern as test_data_import_previews (migration behind models/test_data.py),
applied to CSV/XLSX import of the UAT template's 22-column test case format.

Idempotent — safe to re-run after partial failure.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    r = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=:t"
        ),
        {"t": table},
    )
    return r.fetchone() is not None


def _index_exists(index_name: str) -> bool:
    conn = op.get_bind()
    r = conn.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"),
        {"n": index_name},
    )
    return r.fetchone() is not None


def upgrade() -> None:
    if not _table_exists("test_case_import_previews"):
        op.create_table(
            "test_case_import_previews",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("preview_token", sa.String(length=100), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("file_type", sa.String(length=50), nullable=False),
            sa.Column("detected_columns_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("parsed_rows_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("resolved_rows_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("validation_errors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("validation_warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("can_import", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    for col in ("preview_token", "project_id", "user_id"):
        idx = f"ix_test_case_import_previews_{col}"
        if not _index_exists(idx):
            op.create_index(idx, "test_case_import_previews", [col])


def downgrade() -> None:
    if _table_exists("test_case_import_previews"):
        op.drop_table("test_case_import_previews")
