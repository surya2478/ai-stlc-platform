"""030 - test suite as a direct field on test cases

Simplifies the Test Suite model from a many-to-many junction (test_suite_cases)
to a single `test_suite_id` FK directly on `test_cases` — a test case belongs to
at most one suite, edited the same way as other flat metadata (Test Environment,
Telecom Domain, Product Group). Matches the existing UX pattern for this app
better than a dedicated suite-membership screen.

Revision ID: 030
Revises: 029
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_test_suite_case", table_name="test_suite_cases")
    op.drop_index("ix_test_suite_cases_test_case_id", table_name="test_suite_cases")
    op.drop_index("ix_test_suite_cases_test_suite_id", table_name="test_suite_cases")
    op.drop_table("test_suite_cases")

    op.add_column("test_cases", sa.Column("test_suite_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_test_cases_test_suite_id",
        "test_cases",
        "test_suites",
        ["test_suite_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_test_cases_test_suite_id", "test_cases", ["test_suite_id"])


def downgrade() -> None:
    op.drop_index("ix_test_cases_test_suite_id", table_name="test_cases")
    op.drop_constraint("fk_test_cases_test_suite_id", "test_cases", type_="foreignkey")
    op.drop_column("test_cases", "test_suite_id")

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
