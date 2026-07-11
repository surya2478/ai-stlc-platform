"""035 - studio_runs (Playwright AI Studio)

Application-first pipeline runs: the planner agent explores a live
application, proposes test cases, and downstream stages (generation,
execution, healing) are approved in bulk. See app/models/studio_run.py and
app/services/studio_service.py.

Revision ID: 035
Revises: 034
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None

STATUSES = (
    "'draft','exploring','plan_ready','generating','scripts_ready',"
    "'executing','healing','completed','failed','cancelled'"
)


def upgrade() -> None:
    op.create_table(
        "studio_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("test_case_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("agent_runs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("execution_run_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_studio_runs_status"),
    )
    op.create_index("ix_studio_runs_project_id", "studio_runs", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_studio_runs_project_id", table_name="studio_runs")
    op.drop_table("studio_runs")
