"""023 - Manual Step Result metadata column

Adds a JSONB `metadata` column to manual_step_results so the AI-assist feature
can record a rolling history of suggestions (audit trail of what the AI
recommended versus what the tester chose).

Revision ID: 023
Revises: 022
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "manual_step_results",
        sa.Column("metadata", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("manual_step_results", "metadata")
