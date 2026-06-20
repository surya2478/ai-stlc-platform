"""Add simulated field to execution runs.

Revision ID: 012_execution_simulated_field
Revises: 011_telecom_fields
Create Date: 2026-06-12 16:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_execution_simulated_field"
down_revision: Union[str, None] = "011_telecom_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("execution_runs", sa.Column("simulated", sa.Boolean(), nullable=True, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("execution_runs", "simulated")
