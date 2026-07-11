"""036 - mcp_connections (Playwright AI Studio MCP registry)

External MCP server registry with encrypted credentials and health-check
status — see app/models/mcp_connection.py and
app/services/mcp_connection_service.py. v1 scope: registry + Test
Connection only; agents do not call these servers during runs yet.

Revision ID: 036
Revises: 035
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("connection_type", sa.String(length=30), nullable=False, server_default="custom"),
        sa.Column("transport", sa.String(length=10), nullable=False, server_default="stdio"),
        sa.Column("target", sa.String(length=500), nullable=True),
        sa.Column("command", sa.String(length=200), nullable=True),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("env_encrypted", sa.Text(), nullable=True),
        sa.Column("access_mode", sa.String(length=20), nullable=False, server_default="read_only"),
        sa.Column("available_to", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="not_configured"),
        sa.Column("tool_count", sa.Integer(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "connection_type IN ('browser','api','db','kafka','application','custom')",
            name="ck_mcp_connections_type",
        ),
        sa.CheckConstraint("transport IN ('stdio','http')", name="ck_mcp_connections_transport"),
        sa.CheckConstraint(
            "access_mode IN ('read_only','read_write')", name="ck_mcp_connections_access_mode"
        ),
        sa.CheckConstraint(
            "status IN ('connected','not_configured','error')", name="ck_mcp_connections_status"
        ),
    )
    op.create_index("ix_mcp_connections_project_id", "mcp_connections", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_mcp_connections_project_id", table_name="mcp_connections")
    op.drop_table("mcp_connections")
