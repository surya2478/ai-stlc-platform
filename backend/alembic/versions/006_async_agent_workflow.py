"""Harden async agent workflow metadata.

Revision ID: 006_async_agent_workflow
Revises: 005_traceability_governance
Create Date: 2026-06-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "006_async_agent_workflow"
down_revision: Union[str, None] = "005_traceability_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("input_hash", sa.String(64), nullable=True))
    op.add_column("agent_runs", sa.Column("idempotency_key", sa.String(255), nullable=True))
    op.add_column("agent_runs", sa.Column("prompt_version", sa.String(100), nullable=True))
    op.add_column("agent_runs", sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("agent_runs", sa.Column("progress_message", sa.String(500), nullable=True))
    op.create_index("ix_agent_runs_input_hash", "agent_runs", ["input_hash"])
    op.create_index("ix_agent_runs_idempotency_key", "agent_runs", ["idempotency_key"])
    op.create_unique_constraint("uq_agent_runs_project_idempotency_key", "agent_runs", ["project_id", "idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_agent_runs_project_idempotency_key", "agent_runs", type_="unique")
    op.drop_index("ix_agent_runs_idempotency_key", table_name="agent_runs")
    op.drop_index("ix_agent_runs_input_hash", table_name="agent_runs")
    op.drop_column("agent_runs", "progress_message")
    op.drop_column("agent_runs", "progress_percent")
    op.drop_column("agent_runs", "prompt_version")
    op.drop_column("agent_runs", "idempotency_key")
    op.drop_column("agent_runs", "input_hash")
