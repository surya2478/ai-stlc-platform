"""038 - Grounded Automation PoC (evidence-first generation)

Two isolated PoC tables — poc_grounding_runs (per-TC pipeline state:
routing → capture → coverage gate → generation) and poc_state_evidence
(Application State Evidence Packages captured from the live app). No
existing table is altered; downgrade removes the PoC completely.

See app/models/grounded_poc.py and app/services/grounded_poc_service.py.

Revision ID: 038
Revises: 037
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None

_STATUSES = (
    "draft", "routing_ready", "capturing", "awaiting_confirmation",
    "gate_passed", "gate_blocked", "generating", "generated",
    "failed", "cancelled",
)


def upgrade() -> None:
    op.create_table(
        "poc_grounding_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("test_case_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("capture_mode", sa.String(length=20), nullable=False, server_default="automated"),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("routing", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("coverage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pending_confirmation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("agent_runs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("script_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["project_applications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('" + "','".join(_STATUSES) + "')",
            name="ck_poc_grounding_runs_status",
        ),
        sa.CheckConstraint(
            "capture_mode IN ('automated','assisted','manual_guided')",
            name="ck_poc_grounding_runs_capture_mode",
        ),
    )
    op.create_index("ix_poc_grounding_runs_project_id", "poc_grounding_runs", ["project_id"])
    op.create_index("ix_poc_grounding_runs_test_case_id", "poc_grounding_runs", ["test_case_id"])

    op.create_table(
        "poc_state_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("grounding_run_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("environment", sa.String(length=80), nullable=True),
        sa.Column("viewport", sa.String(length=30), nullable=True),
        sa.Column("elements", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("snapshot_text", sa.Text(), nullable=True),
        sa.Column("screenshot_path", sa.String(length=1000), nullable=True),
        sa.Column("blockers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("console_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("produced_by_step", sa.Integer(), nullable=True),
        sa.Column("prev_evidence_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["grounding_run_id"], ["poc_grounding_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prev_evidence_id"], ["poc_state_evidence.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_poc_state_evidence_project_id", "poc_state_evidence", ["project_id"])
    op.create_index("ix_poc_state_evidence_grounding_run_id", "poc_state_evidence", ["grounding_run_id"])
    op.create_index("ix_poc_state_evidence_state_fingerprint", "poc_state_evidence", ["state_fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_poc_state_evidence_state_fingerprint", table_name="poc_state_evidence")
    op.drop_index("ix_poc_state_evidence_grounding_run_id", table_name="poc_state_evidence")
    op.drop_index("ix_poc_state_evidence_project_id", table_name="poc_state_evidence")
    op.drop_table("poc_state_evidence")
    op.drop_index("ix_poc_grounding_runs_test_case_id", table_name="poc_grounding_runs")
    op.drop_index("ix_poc_grounding_runs_project_id", table_name="poc_grounding_runs")
    op.drop_table("poc_grounding_runs")
