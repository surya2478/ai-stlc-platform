"""025 - Fold execution_type='ai' into 'automation' with metadata flag.

Phase 3 completes the "AI is a layer, not a runner" refactor. AI runs are no
longer their own execution_type; they're automation runs with
``metadata.ai_assisted = true`` (and any AI-specific telemetry moves to
``metadata`` too).

Backfill:
    * All rows with execution_type='ai' get execution_type='automation' and
      metadata.ai_assisted=true.
    * confidence_score column stays where it is — still populated for
      AI-assisted runs, null for standard runs.

Check constraint:
    * ck_execution_runs_execution_type is tightened to {manual, automation,
      hybrid}. Any leftover 'ai' rows must be backfilled before the constraint
      is re-created, so we do the UPDATE first.

Revision ID: 025
Revises: 024
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa


revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


_NEW_EXECUTION_TYPE_VALUES = ("manual", "automation", "hybrid")
_OLD_EXECUTION_TYPE_VALUES = ("manual", "automation", "ai", "hybrid")


def upgrade() -> None:
    # 1. Backfill any lingering execution_type='ai' rows.
    #    Merge {ai_assisted: true} into the JSONB metadata column.
    op.execute(
        """
        UPDATE execution_runs
        SET
            execution_type = 'automation',
            metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('ai_assisted', true)
        WHERE execution_type = 'ai'
        """
    )

    # 2. Swap the check constraint to the tighter allow-list.
    op.drop_constraint("ck_execution_runs_execution_type", "execution_runs", type_="check")
    op.create_check_constraint(
        "ck_execution_runs_execution_type",
        "execution_runs",
        "execution_type IN ({})".format(
            ", ".join(f"'{v}'" for v in _NEW_EXECUTION_TYPE_VALUES)
        ),
    )


def downgrade() -> None:
    # 1. Widen the check constraint back to the old set that includes 'ai'.
    op.drop_constraint("ck_execution_runs_execution_type", "execution_runs", type_="check")
    op.create_check_constraint(
        "ck_execution_runs_execution_type",
        "execution_runs",
        "execution_type IN ({})".format(
            ", ".join(f"'{v}'" for v in _OLD_EXECUTION_TYPE_VALUES)
        ),
    )

    # 2. Reverse the backfill: rows we tagged as ai_assisted move back to
    #    execution_type='ai'. Drops the ai_assisted flag from metadata.
    op.execute(
        """
        UPDATE execution_runs
        SET
            execution_type = 'ai',
            metadata = (metadata - 'ai_assisted')
        WHERE execution_type = 'automation'
          AND metadata ? 'ai_assisted'
          AND (metadata->>'ai_assisted')::boolean = true
        """
    )
