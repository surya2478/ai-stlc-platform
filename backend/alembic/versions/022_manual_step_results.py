"""022 - Manual Step Results

Per-step persistence for manual test execution. Replaces the previous
localStorage-only state with a real backend record so step pass/fail,
actual results, comments, and evidence survive across sessions and
testers.

Revision ID: 022
Revises: 021
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_step_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "execution_result_id",
            sa.Integer(),
            sa.ForeignKey("execution_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("action_text", sa.Text(), nullable=True),
        sa.Column("expected_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="not_run"),
        sa.Column("actual_result", sa.Text(), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("evidence", JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_by",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "execution_result_id",
            "step_number",
            name="uq_manual_step_result_step",
        ),
    )
    op.create_index(
        "ix_manual_step_results_execution_result_id",
        "manual_step_results",
        ["execution_result_id"],
    )
    op.create_index(
        "ix_manual_step_results_project_id",
        "manual_step_results",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_manual_step_results_project_id", table_name="manual_step_results")
    op.drop_index("ix_manual_step_results_execution_result_id", table_name="manual_step_results")
    op.drop_table("manual_step_results")
