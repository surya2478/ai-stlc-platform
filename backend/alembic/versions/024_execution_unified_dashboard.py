"""024 - Unified Execution Dashboard fields

Adds first-class `execution_type` and `confidence_score` columns to
`execution_runs` so the Execution Dashboard can aggregate runs by Manual /
Automation / AI without unpacking JSON metadata on every query.

The check constraint `ck_execution_runs_status` is extended to allow two new
lifecycle states required by the AI Execution module:
    - auto_completed: AI run met confidence + evidence policy, published itself.
    - review_required: AI run finished but flagged for human review.

Backfill rules for execution_type:
    * source_type = 'ai'                              -> 'ai'
    * source_type LIKE '%automation%'                 -> 'automation'
    * metadata->>'execution_type' present             -> use it verbatim
    * everything else                                 -> 'manual'

Revision ID: 024
Revises: 023
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa


revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


# Keep in sync with backend/app/models/execution.py ExecutionRun.status
_NEW_STATUS_VALUES = (
    "pending",
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "auto_completed",
    "review_required",
)
_EXECUTION_TYPE_VALUES = ("manual", "automation", "ai", "hybrid")


def upgrade() -> None:
    # 1. Add execution_type column (nullable initially so we can backfill)
    op.add_column(
        "execution_runs",
        sa.Column("execution_type", sa.String(length=20), nullable=True),
    )

    # 2. Add confidence_score column (nullable; only meaningful for AI runs)
    op.add_column(
        "execution_runs",
        sa.Column("confidence_score", sa.Float(), nullable=True),
    )

    # 3. Backfill execution_type from source_type / metadata.
    op.execute(
        """
        UPDATE execution_runs
        SET execution_type = CASE
            WHEN (metadata->>'execution_type') IS NOT NULL
                THEN metadata->>'execution_type'
            WHEN source_type = 'ai' THEN 'ai'
            WHEN source_type ILIKE '%%automation%%' THEN 'automation'
            WHEN source_type = 'jira_sync' THEN 'automation'
            ELSE 'manual'
        END
        WHERE execution_type IS NULL
        """
    )

    # 4. Enforce NOT NULL + default + check constraint.
    op.alter_column(
        "execution_runs",
        "execution_type",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="manual",
    )
    op.create_check_constraint(
        "ck_execution_runs_execution_type",
        "execution_runs",
        "execution_type IN ({})".format(", ".join(f"'{v}'" for v in _EXECUTION_TYPE_VALUES)),
    )
    op.create_index(
        "ix_execution_runs_execution_type",
        "execution_runs",
        ["execution_type"],
    )

    # 5. Extend status check constraint to allow auto_completed + review_required.
    op.drop_constraint("ck_execution_runs_status", "execution_runs", type_="check")
    op.create_check_constraint(
        "ck_execution_runs_status",
        "execution_runs",
        "status IN ({})".format(", ".join(f"'{v}'" for v in _NEW_STATUS_VALUES)),
    )

    # 6. Backfill confidence_score from metadata.confidence_score when present.
    op.execute(
        """
        UPDATE execution_runs
        SET confidence_score = (metadata->>'confidence_score')::float
        WHERE confidence_score IS NULL
          AND metadata ? 'confidence_score'
          AND metadata->>'confidence_score' ~ '^[0-9]+(\\.[0-9]+)?$'
        """
    )


def downgrade() -> None:
    # Revert status check constraint to original 6-value set.
    op.drop_constraint("ck_execution_runs_status", "execution_runs", type_="check")
    op.create_check_constraint(
        "ck_execution_runs_status",
        "execution_runs",
        "status IN ('pending', 'queued', 'running', 'completed', 'failed', 'cancelled')",
    )

    op.drop_index("ix_execution_runs_execution_type", table_name="execution_runs")
    op.drop_constraint("ck_execution_runs_execution_type", "execution_runs", type_="check")
    op.drop_column("execution_runs", "confidence_score")
    op.drop_column("execution_runs", "execution_type")
