"""047 - UI-018 Automation Test Suite Phase B

Adds execution groups, immutable publication snapshots, the approval-workflow
audit columns on automation_suites, and the additive execution_group_id link on
automation_suite_test_cases. Additive only — no existing column changes type or
nullability, so this is backward compatible with Phase A rows.

Revision ID: 047
Revises: 046
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None

EXECUTION_GROUP_STATUSES = ("draft", "ready", "blocked")

_APPROVAL_COLUMNS = (
    ("submitted_by", True),
    ("reviewed_by", True),
    ("approved_by", True),
    ("published_by", True),
)


def upgrade() -> None:
    op.create_table(
        "automation_suite_execution_groups",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "suite_id", sa.Integer(), sa.ForeignKey("automation_suites.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("framework", sa.String(length=50), nullable=True),
        sa.Column("environment", sa.String(length=100), nullable=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("project_applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('" + "','".join(EXECUTION_GROUP_STATUSES) + "')",
            name="ck_automation_suite_execution_groups_status",
        ),
        sa.UniqueConstraint("suite_id", "name", name="uq_automation_suite_execution_groups_name"),
    )
    op.create_index(
        "ix_automation_suite_execution_groups_suite_id", "automation_suite_execution_groups", ["suite_id"]
    )

    op.create_table(
        "automation_suite_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "suite_id", sa.Integer(), sa.ForeignKey("automation_suites.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("suite_version", sa.Integer(), nullable=False),
        sa.Column("members", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("execution_groups", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("summary", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("suite_id", "suite_version", name="uq_automation_suite_snapshots_version"),
    )
    op.create_index("ix_automation_suite_snapshots_suite_id", "automation_suite_snapshots", ["suite_id"])

    # Additive membership link to a group.
    op.add_column(
        "automation_suite_test_cases", sa.Column("execution_group_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_automation_suite_test_cases_execution_group",
        "automation_suite_test_cases",
        "automation_suite_execution_groups",
        ["execution_group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_automation_suite_test_cases_execution_group_id",
        "automation_suite_test_cases",
        ["execution_group_id"],
    )

    # Approval workflow audit.
    for column, _nullable in _APPROVAL_COLUMNS:
        op.add_column("automation_suites", sa.Column(column, sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_automation_suites_{column}", "automation_suites", "users", [column], ["id"], ondelete="SET NULL"
        )
    for column in ("submitted_at", "reviewed_at", "approved_at", "published_at"):
        op.add_column("automation_suites", sa.Column(column, sa.DateTime(timezone=True), nullable=True))
    op.add_column("automation_suites", sa.Column("decision_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("automation_suites", "decision_reason")
    for column in ("published_at", "approved_at", "reviewed_at", "submitted_at"):
        op.drop_column("automation_suites", column)
    for column, _nullable in reversed(_APPROVAL_COLUMNS):
        op.drop_constraint(f"fk_automation_suites_{column}", "automation_suites", type_="foreignkey")
        op.drop_column("automation_suites", column)

    op.drop_index("ix_automation_suite_test_cases_execution_group_id", "automation_suite_test_cases")
    op.drop_constraint(
        "fk_automation_suite_test_cases_execution_group", "automation_suite_test_cases", type_="foreignkey"
    )
    op.drop_column("automation_suite_test_cases", "execution_group_id")

    op.drop_table("automation_suite_snapshots")
    op.drop_table("automation_suite_execution_groups")
