"""028 - project applications, environment URLs, external dependencies

Adds ProjectApplication (named application/channel per project, with a
per-environment base URL map) and ProjectExternalDependency (registry of
third-party services an application calls out to, so generated automation
mocks them instead of hitting them live). Also tags TestCase with an optional
application_id so script generation/execution can resolve a real URL instead
of inventing a placeholder domain.

No backfill: application_id is nullable and resolution falls back to the
project's default application (or the pre-existing metadata_ chain) when
unset, so existing test cases keep working untouched.

Revision ID: 028
Revises: 027
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("environment_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_applications_id", "project_applications", ["id"])
    op.create_index("ix_project_applications_project_id", "project_applications", ["project_id"])
    op.create_index("uq_project_application_key", "project_applications", ["project_id", "key"], unique=True)
    op.create_index(
        "uq_project_application_default",
        "project_applications",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE"),
    )

    op.create_table(
        "project_external_dependencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("service_name", sa.String(length=200), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sandbox_url", sa.Text(), nullable=True),
        sa.Column("mock_strategy", sa.String(length=30), nullable=False, server_default="intercept"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["project_applications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_external_dependencies_id", "project_external_dependencies", ["id"])
    op.create_index("ix_project_external_dependencies_project_id", "project_external_dependencies", ["project_id"])
    op.create_index("ix_project_external_dependencies_application_id", "project_external_dependencies", ["application_id"])

    op.add_column("test_cases", sa.Column("application_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_test_cases_application_id",
        "test_cases",
        "project_applications",
        ["application_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_test_cases_application_id", "test_cases", ["application_id"])


def downgrade() -> None:
    op.drop_index("ix_test_cases_application_id", table_name="test_cases")
    op.drop_constraint("fk_test_cases_application_id", "test_cases", type_="foreignkey")
    op.drop_column("test_cases", "application_id")

    op.drop_index("ix_project_external_dependencies_application_id", table_name="project_external_dependencies")
    op.drop_index("ix_project_external_dependencies_project_id", table_name="project_external_dependencies")
    op.drop_index("ix_project_external_dependencies_id", table_name="project_external_dependencies")
    op.drop_table("project_external_dependencies")

    op.drop_index("uq_project_application_default", table_name="project_applications")
    op.drop_index("uq_project_application_key", table_name="project_applications")
    op.drop_index("ix_project_applications_project_id", table_name="project_applications")
    op.drop_index("ix_project_applications_id", table_name="project_applications")
    op.drop_table("project_applications")
