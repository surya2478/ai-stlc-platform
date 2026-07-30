"""051 - UI-020/021/023 Automation Asset Workspace: autonomy and decision records

Additive only. Adds the two independent state axes required by the approved
UI-020/021/023 contract (Section 14.1) and the immutable decision record that
makes an autonomy verdict auditable (Section 14.5).

`autonomy_state` is machine-owned and `approval_state` is human-owned; they are
deliberately separate columns. Collapsing them into one field would let the
generating agent write the same field a reviewer writes, which is the
separation-of-duty violation `automation_suite/lifecycle.py` already refuses for
human actors (SEPARATION_OF_DUTY_VIOLATION).

Both columns carry a server_default, so every existing member row is valid
without a data migration: an already-approved suite's members land on
AI_PENDING / PENDING_FINAL and are simply re-evaluated on the next pass.

`automation_asset_decisions` is insert-only. It stores the threshold, score and
dimension breakdown **by value** rather than by reference to current config,
because thresholds and rubrics change and a pointer cannot answer "why was this
approved" after they do.

No existing column changes type or nullability. VALIDATION_PENDING and
VALIDATION_FAILED already exist in ck_automation_suites_status (reserved by
migration 046 for UI-023), so no constraint is rewritten here.

Revision ID: 051
Revises: 050
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None

AUTONOMY_STATES = ("AI_PENDING", "AI_HELD", "AI_APPROVED")
APPROVAL_STATES = ("PENDING_FINAL", "FINAL_APPROVED", "REJECTED")
DECISION_TYPES = ("AI_APPROVED", "AI_HELD", "FINAL_APPROVED", "REJECTED", "OVERRIDE")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ('" + "','".join(values) + "')"


def upgrade() -> None:
    # ── The two state axes on the suite member ───────────────────────────────
    op.add_column(
        "automation_suite_test_cases",
        sa.Column(
            "autonomy_state",
            sa.String(length=20),
            nullable=False,
            server_default="AI_PENDING",
        ),
    )
    op.add_column(
        "automation_suite_test_cases",
        sa.Column(
            "approval_state",
            sa.String(length=20),
            nullable=False,
            server_default="PENDING_FINAL",
        ),
    )
    op.create_check_constraint(
        "ck_automation_suite_test_cases_autonomy_state",
        "automation_suite_test_cases",
        _in_list("autonomy_state", AUTONOMY_STATES),
    )
    op.create_check_constraint(
        "ck_automation_suite_test_cases_approval_state",
        "automation_suite_test_cases",
        _in_list("approval_state", APPROVAL_STATES),
    )
    # The "pending final approval" aging queue (contract Section 16) filters on
    # both axes together.
    op.create_index(
        "ix_automation_suite_test_cases_autonomy",
        "automation_suite_test_cases",
        ["autonomy_state", "approval_state"],
    )

    # ── The immutable decision record ────────────────────────────────────────
    op.create_table(
        "automation_asset_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "suite_test_case_id",
            sa.Integer(),
            sa.ForeignKey("automation_suite_test_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Which artifact versions the decision was taken against. Nullable
        # because a decision can precede either artifact existing.
        sa.Column(
            "ir_draft_id",
            sa.Integer(),
            sa.ForeignKey("automation_ir_drafts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "script_id",
            sa.Integer(),
            sa.ForeignKey("automation_scripts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decision", sa.String(length=20), nullable=False),
        # NULL actor => the machine decided. A human decision always carries an
        # actor, which is what makes SEPARATION_OF_DUTY checkable after the fact.
        sa.Column(
            "decided_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rubric_id", sa.String(length=50), nullable=False),
        # Stored by value, not by reference to current config — see the module
        # docstring.
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "dimensions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "preconditions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "model_versions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _in_list("decision", DECISION_TYPES),
            name="ck_automation_asset_decisions_decision",
        ),
    )
    op.create_index(
        "ix_automation_asset_decisions_project_id",
        "automation_asset_decisions",
        ["project_id"],
    )
    op.create_index(
        "ix_automation_asset_decisions_member",
        "automation_asset_decisions",
        ["suite_test_case_id"],
    )
    # Decision history for one member, newest first.
    op.create_index(
        "ix_automation_asset_decisions_member_created",
        "automation_asset_decisions",
        ["suite_test_case_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_automation_asset_decisions_member_created",
        table_name="automation_asset_decisions",
    )
    op.drop_index(
        "ix_automation_asset_decisions_member", table_name="automation_asset_decisions"
    )
    op.drop_index(
        "ix_automation_asset_decisions_project_id",
        table_name="automation_asset_decisions",
    )
    op.drop_table("automation_asset_decisions")

    op.drop_index(
        "ix_automation_suite_test_cases_autonomy",
        table_name="automation_suite_test_cases",
    )
    op.drop_constraint(
        "ck_automation_suite_test_cases_approval_state",
        "automation_suite_test_cases",
        type_="check",
    )
    op.drop_constraint(
        "ck_automation_suite_test_cases_autonomy_state",
        "automation_suite_test_cases",
        type_="check",
    )
    op.drop_column("automation_suite_test_cases", "approval_state")
    op.drop_column("automation_suite_test_cases", "autonomy_state")
