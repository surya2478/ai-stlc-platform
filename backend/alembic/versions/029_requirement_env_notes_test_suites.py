"""029 - requirement generation context, test suites

Adds `generation_notes` (free-text tester instructions for AI test-case
generation) to `requirements`. The existing `test_phase` column is repurposed
in the application layer as the "Test Environment" selector (SIT/QA/UAT/
Regression/Production Smoke Test) — no column change needed there, only the
allowed value list in app/schemas/requirement.py.

Also introduces TestSuite (a named, curated collection of test cases per
project, optionally tagged with the same test-environment taxonomy) and
TestSuiteCase (the explicit membership join table).

Revision ID: 029
Revises: 028
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requirements", sa.Column("generation_notes", sa.Text(), nullable=True))

    op.create_table(
        "test_suites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("environment", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_suites_id", "test_suites", ["id"])
    op.create_index("ix_test_suites_project_id", "test_suites", ["project_id"])

    op.create_table(
        "test_suite_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("test_suite_id", sa.Integer(), nullable=False),
        sa.Column("test_case_id", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("added_by", sa.Integer(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["test_suite_id"], ["test_suites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_suite_cases_test_suite_id", "test_suite_cases", ["test_suite_id"])
    op.create_index("ix_test_suite_cases_test_case_id", "test_suite_cases", ["test_case_id"])
    op.create_index(
        "uq_test_suite_case", "test_suite_cases", ["test_suite_id", "test_case_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_test_suite_case", table_name="test_suite_cases")
    op.drop_index("ix_test_suite_cases_test_case_id", table_name="test_suite_cases")
    op.drop_index("ix_test_suite_cases_test_suite_id", table_name="test_suite_cases")
    op.drop_table("test_suite_cases")

    op.drop_index("ix_test_suites_project_id", table_name="test_suites")
    op.drop_index("ix_test_suites_id", table_name="test_suites")
    op.drop_table("test_suites")

    op.drop_column("requirements", "generation_notes")
