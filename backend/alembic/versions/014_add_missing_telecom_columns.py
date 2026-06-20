"""014 — Add missing columns: telecom_domain alias, is_deleted, review_notes, verdict

Adds only the columns confirmed missing from the live database after inspecting
the actual schema at revision 013_tc_td_telecom_fields.

Missing from requirements:
  - telecom_domain  (live DB uses qa_domain for domain; add telecom_domain as alias column)
  - is_deleted      (soft delete flag)
  - review_notes    (approval notes)

Missing from requirement_quality_reviews:
  - verdict         (pass | needs_revision | fail)

Revision ID: 014
Revises: 013_tc_td_telecom_fields
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013_tc_td_telecom_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── requirements: 3 missing columns ──────────────────────────────────────
    op.add_column(
        "requirements",
        sa.Column("telecom_domain", sa.String(50), nullable=True),
    )
    op.add_column(
        "requirements",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "requirements",
        sa.Column("review_notes", sa.Text(), nullable=True),
    )

    # ── indexes for new filterable columns ────────────────────────────────────
    op.create_index("ix_requirements_telecom_domain", "requirements", ["telecom_domain"])
    op.create_index("ix_requirements_is_deleted", "requirements", ["is_deleted"])

    # ── requirement_quality_reviews: 1 missing column ─────────────────────────
    op.add_column(
        "requirement_quality_reviews",
        sa.Column("verdict", sa.String(30), nullable=True),
    )


def downgrade() -> None:
    op.drop_index("ix_requirements_is_deleted", table_name="requirements")
    op.drop_index("ix_requirements_telecom_domain", table_name="requirements")
    op.drop_column("requirements", "review_notes")
    op.drop_column("requirements", "is_deleted")
    op.drop_column("requirements", "telecom_domain")
    op.drop_column("requirement_quality_reviews", "verdict")
