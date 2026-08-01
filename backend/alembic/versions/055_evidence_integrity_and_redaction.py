"""055 - Evidence integrity and redaction state

Additive only. Every column is nullable or defaulted, so existing rows stay
valid without a data migration.

`execution_run_evidence` stored a path, an optional size and a `sanitized`
boolean that no code ever set to true. Three things were missing to make an
evidence row an audit record rather than a pointer:

  checksum_sha256  the bytes as captured. A stored path proves a file existed
                   once, not that the file served later is the one the run
                   produced.
  content_type     what the artifact is, so the download endpoint does not have
                   to guess a media type from the evidence type.
  redaction_state  why `sanitized` holds the value it does. A screenshot cannot
                   be masked by any text pass, so "not sanitized" meant two
                   unrelated things — not-yet-processed and not-processable —
                   and that ambiguity is why the flag could not be used as a
                   serving gate.

The pairing constraint makes `sanitized` a view of `redaction_state` rather than
an independent claim: only content the masking pass actually rewrote may assert
it. Existing rows are all `pending`/`sanitized=false`, which satisfies it.

This is the storage half of P0-06. The download endpoint, the masking pass and
the serving policy land with it in `evidence_service.py`.
"""
from alembic import op
import sqlalchemy as sa

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None

_REDACTION_STATES = "('pending','masked','not_maskable')"


def upgrade() -> None:
    op.add_column(
        "execution_run_evidence",
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "execution_run_evidence",
        sa.Column("content_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "execution_run_evidence",
        sa.Column(
            "redaction_state",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.create_check_constraint(
        "ck_execution_run_evidence_redaction_state",
        "execution_run_evidence",
        f"redaction_state IN {_REDACTION_STATES}",
    )
    op.create_check_constraint(
        "ck_execution_run_evidence_sanitized_pairing",
        "execution_run_evidence",
        "sanitized = false OR redaction_state = 'masked'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_execution_run_evidence_sanitized_pairing",
        "execution_run_evidence",
        type_="check",
    )
    op.drop_constraint(
        "ck_execution_run_evidence_redaction_state",
        "execution_run_evidence",
        type_="check",
    )
    op.drop_column("execution_run_evidence", "redaction_state")
    op.drop_column("execution_run_evidence", "content_type")
    op.drop_column("execution_run_evidence", "checksum_sha256")
