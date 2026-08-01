"""053 - Record how an execution assertion verdict was reached

Additive only. `execution_run_assertions.passed` records *what* the verdict was
but nothing about *how* it was established, and the suite orchestrator sets
every assertion on an item to passed=true when the runner reports a green test
(`_mark_assertions_passed`).

That inference is sound — Playwright fails the test if any web-first assertion
fails, so a green test does mean every declared assertion held — but the stored
row is indistinguishable from one an adapter evaluated individually. An auditor
reading the evidence sees a per-assertion evaluation the run never performed.

`evaluation_source` makes the distinction explicit:

  runner_verdict  inferred from the test-level pass/fail
  reported        the adapter reported this assertion individually
  manual          a human recorded the verdict

Two constraints hold the invariant. The vocabulary check permits NULL, because
an unevaluated assertion has no method. The pairing check ties the two columns
together in both directions: a verdict must state its method, and a row with no
verdict must not claim one.

Backfill: existing evaluated rows are set to 'runner_verdict'. That is the only
path that has ever written `passed`, so the backfill is a statement of fact
rather than an assumption — and it is required, since the pairing constraint
would otherwise reject every historical row.
"""
from alembic import op
import sqlalchemy as sa

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


_VOCABULARY = "('runner_verdict','reported','manual')"


def upgrade() -> None:
    op.add_column(
        "execution_run_assertions",
        sa.Column("evaluation_source", sa.String(length=20), nullable=True),
    )

    # Backfill before the constraints land, or the pairing check fails on every
    # already-evaluated row.
    op.execute(
        """
        UPDATE execution_run_assertions
        SET evaluation_source = 'runner_verdict'
        WHERE passed IS NOT NULL AND evaluation_source IS NULL
        """
    )

    op.create_check_constraint(
        "ck_execution_run_assertions_evaluation_source",
        "execution_run_assertions",
        f"evaluation_source IN {_VOCABULARY} OR evaluation_source IS NULL",
    )
    op.create_check_constraint(
        "ck_execution_run_assertions_evaluation_pairing",
        "execution_run_assertions",
        "(passed IS NULL) = (evaluation_source IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_execution_run_assertions_evaluation_pairing",
        "execution_run_assertions",
        type_="check",
    )
    op.drop_constraint(
        "ck_execution_run_assertions_evaluation_source",
        "execution_run_assertions",
        type_="check",
    )
    op.drop_column("execution_run_assertions", "evaluation_source")
