"""026 - TestCase.status cleanup + ai_assistance_status column.

Phase 5 splits two concerns that used to share the ``status`` column:

    Before                              After
    ------                              -----
    status = 'automated'                status = 'approved'   (the real lifecycle)
                                        automation_status = 'automated'   (moved here)

The lifecycle column now covers only: draft | pending_approval | approved
| rejected. The presence or absence of an automation script is answered by
``automation_status`` (or the new ``automation_ready`` flag added earlier).

Also adds ``ai_assistance_status`` with values
    disabled | enabled | recommendation_pending | approved | rejected
tracking whether AI assistance is on for the TC and whether outstanding AI
recommendations are still pending review.

Backfill safety: no rows should get lost. We convert every
``status='automated'`` row into ``status='approved'`` and populate
``automation_status='automated'`` only where it isn't already set to something
more specific.

Revision ID: 026
Revises: 025
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa


revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Backfill: any TC whose lifecycle status still says 'automated' has
    #    conflated two concepts. Move the automation signal into the right
    #    column, then promote the lifecycle status to 'approved' (the
    #    predecessor state before it was automated).
    op.execute(
        """
        UPDATE test_cases
        SET
            automation_status = CASE
                WHEN automation_status IS NULL OR automation_status = 'not_required'
                    THEN 'automated'
                ELSE automation_status
            END,
            status = 'approved'
        WHERE status = 'automated'
        """
    )

    # 2. Add the new ai_assistance_status column. Nullable=False + default so
    #    existing rows get 'disabled' automatically and new rows keep the
    #    default without every writer having to specify it.
    op.add_column(
        "test_cases",
        sa.Column(
            "ai_assistance_status",
            sa.String(length=50),
            nullable=False,
            server_default="disabled",
        ),
    )

    # 3. Index on ai_assistance_status so filtering by "which TCs have AI on"
    #    stays cheap even at scale. Skipped for now — the column has low
    #    cardinality and TC counts are typically small; add if a slow query
    #    proves it necessary.


def downgrade() -> None:
    # Drop the new column.
    op.drop_column("test_cases", "ai_assistance_status")

    # Reverse the status backfill: any TC that is currently status='approved'
    # AND has automation_status='automated' AND was previously flipped by
    # migration 026 gets moved back to status='automated'. There's no perfect
    # marker for "was flipped by 026" — we make a best-effort call: if the
    # row satisfies the two conditions we consider it a candidate. If your
    # deployment had legitimately-approved automated TCs before 026, this
    # downgrade will also flip them — which is why the downgrade is meant
    # for dev environments, not production rollback.
    op.execute(
        """
        UPDATE test_cases
        SET status = 'automated'
        WHERE status = 'approved'
          AND automation_status = 'automated'
        """
    )
