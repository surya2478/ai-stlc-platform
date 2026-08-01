"""054 - Item lease and liveness for suite execution recovery

Additive only, both columns nullable with no default, so every existing row
stays valid and no backfill is required.

`execution_run_items` records which item is running but nothing about *who* is
running it or *when it was last seen*. When a worker died mid-item — a crash, a
container restart, a lost connection — `_mark_run_faulted` closed the run and
left its items in STARTING/RUNNING permanently. The command center polls those
rows, so an operator saw a test spinning forever against a run that had already
finished, with no way to tell it apart from a genuinely slow test.

  worker_id     the Celery task that claimed the item
  heartbeat_at  refreshed on the control-poll cadence while the item executes,
                and cleared when the item reaches a terminal state

The partial index covers the reconciler's only query — items still in flight —
rather than the whole table, which is overwhelmingly terminal rows.

This is the storage half of P2-06 (recovery and reconciliation). This migration
plus `orchestrator.reconcile_stranded_items` handles the in-process cases: a
faulted run and a resumed run that finds leftovers from a previous attempt. A
periodic cross-run sweeper for workers that vanish without running any Python
at all is still outstanding.
"""
from alembic import op
import sqlalchemy as sa

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "execution_run_items",
        sa.Column("worker_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "execution_run_items",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_execution_run_items_in_flight",
        "execution_run_items",
        ["execution_run_id", "heartbeat_at"],
        postgresql_where=sa.text("lifecycle_state IN ('STARTING','RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index("ix_execution_run_items_in_flight", table_name="execution_run_items")
    op.drop_column("execution_run_items", "heartbeat_at")
    op.drop_column("execution_run_items", "worker_id")
