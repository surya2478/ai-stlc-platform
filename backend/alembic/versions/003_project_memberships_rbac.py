"""Add project memberships for RBAC.

Revision ID: 003_project_memberships_rbac
Revises: 002_project_scoped_artifact_ids
Create Date: 2026-06-10
"""
import sqlalchemy as sa
from alembic import op


revision = "003_project_memberships_rbac"
down_revision = "002_project_scoped_artifact_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_memberships_project_user"),
    )
    op.create_index("ix_project_memberships_project_id", "project_memberships", ["project_id"])
    op.create_index("ix_project_memberships_user_id", "project_memberships", ["user_id"])
    op.create_index("ix_project_memberships_role", "project_memberships", ["role"])
    op.create_index("ix_project_memberships_is_active", "project_memberships", ["is_active"])

    op.execute(
        """
        INSERT INTO project_memberships (project_id, user_id, role, is_active, created_at, updated_at)
        SELECT id, owner_id, 'Project Admin', true, now(), now()
        FROM projects
        ON CONFLICT (project_id, user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_project_memberships_is_active", table_name="project_memberships")
    op.drop_index("ix_project_memberships_role", table_name="project_memberships")
    op.drop_index("ix_project_memberships_user_id", table_name="project_memberships")
    op.drop_index("ix_project_memberships_project_id", table_name="project_memberships")
    op.drop_table("project_memberships")
