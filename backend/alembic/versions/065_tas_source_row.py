"""065 - TAS: keep every column the uploaded test case sheet carried

The studio refines a test case's objective, steps and expected result. It has
nothing to say about Domain, Channel, Product, Area of Test, Environment, Sub
Request Type or the execution columns — but a download that dropped them is not
the format the team uploaded, which is the format they have to hand back.

Only four fields survived extraction (`tc_display_id`, `title`, `summary`,
`steps`), so the rest had nowhere to live. This adds the whole row, keyed by
the canonical field names in `app/services/test_case_template.py` so import,
the platform export and this module all speak one vocabulary.

Revision ID: 065
Revises: 064
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tas_source_test_cases",
        sa.Column(
            "source_row",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("tas_source_test_cases", "source_row")
