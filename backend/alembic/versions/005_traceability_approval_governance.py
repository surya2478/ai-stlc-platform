"""Add traceability lineage and approval governance fields.

Revision ID: 005_traceability_governance
Revises: 004_jira_two_way_sync
Create Date: 2026-06-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "005_traceability_governance"
down_revision: Union[str, None] = "004_jira_two_way_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "artifact_lineage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("parent_type", sa.String(100), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("child_type", sa.String(100), nullable=False),
        sa.Column("child_id", sa.Integer(), nullable=False),
        sa.Column("relationship_type", sa.String(100), nullable=False, server_default="generated_from"),
        sa.Column("source", sa.String(50), nullable=False, server_default="agent"),
        sa.Column("correlation_id", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_artifact_lineage_project_id", "artifact_lineage", ["project_id"])
    op.create_index("ix_artifact_lineage_agent_run_id", "artifact_lineage", ["agent_run_id"])
    op.create_index("ix_artifact_lineage_parent_type", "artifact_lineage", ["parent_type"])
    op.create_index("ix_artifact_lineage_parent_id", "artifact_lineage", ["parent_id"])
    op.create_index("ix_artifact_lineage_child_type", "artifact_lineage", ["child_type"])
    op.create_index("ix_artifact_lineage_child_id", "artifact_lineage", ["child_id"])
    op.create_index("ix_artifact_lineage_correlation_id", "artifact_lineage", ["correlation_id"])

    op.add_column("approval_actions", sa.Column("source", sa.String(50), nullable=False, server_default="platform"))
    op.add_column("approval_actions", sa.Column("actor_role", sa.String(100), nullable=True))
    op.add_column("approval_actions", sa.Column("old_value", postgresql.JSONB(), nullable=True))
    op.add_column("approval_actions", sa.Column("new_value", postgresql.JSONB(), nullable=True))
    op.add_column("approval_actions", sa.Column("jira_issue_key", sa.String(100), nullable=True))
    op.add_column("approval_actions", sa.Column("correlation_id", sa.String(255), nullable=True))
    op.add_column("approval_actions", sa.Column("request_id", sa.String(255), nullable=True))
    op.add_column("approval_actions", sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=True))
    op.create_index("ix_approval_actions_jira_issue_key", "approval_actions", ["jira_issue_key"])
    op.create_index("ix_approval_actions_correlation_id", "approval_actions", ["correlation_id"])
    op.create_index("ix_approval_actions_request_id", "approval_actions", ["request_id"])
    op.create_index("ix_approval_actions_agent_run_id", "approval_actions", ["agent_run_id"])


def downgrade() -> None:
    op.drop_index("ix_approval_actions_agent_run_id", table_name="approval_actions")
    op.drop_index("ix_approval_actions_request_id", table_name="approval_actions")
    op.drop_index("ix_approval_actions_correlation_id", table_name="approval_actions")
    op.drop_index("ix_approval_actions_jira_issue_key", table_name="approval_actions")
    op.drop_column("approval_actions", "agent_run_id")
    op.drop_column("approval_actions", "request_id")
    op.drop_column("approval_actions", "correlation_id")
    op.drop_column("approval_actions", "jira_issue_key")
    op.drop_column("approval_actions", "new_value")
    op.drop_column("approval_actions", "old_value")
    op.drop_column("approval_actions", "actor_role")
    op.drop_column("approval_actions", "source")

    op.drop_index("ix_artifact_lineage_correlation_id", table_name="artifact_lineage")
    op.drop_index("ix_artifact_lineage_child_id", table_name="artifact_lineage")
    op.drop_index("ix_artifact_lineage_child_type", table_name="artifact_lineage")
    op.drop_index("ix_artifact_lineage_parent_id", table_name="artifact_lineage")
    op.drop_index("ix_artifact_lineage_parent_type", table_name="artifact_lineage")
    op.drop_index("ix_artifact_lineage_agent_run_id", table_name="artifact_lineage")
    op.drop_index("ix_artifact_lineage_project_id", table_name="artifact_lineage")
    op.drop_table("artifact_lineage")
