"""032 - automation_scripts versioning + Phase 2 generation lifecycle

Phase 2 of the agentic automation initiative (ADR-001 / Phase-2 plan):

- version / parent_script_id: every repair or healing change creates a NEW
  row rather than mutating code in place. The parent row is never deleted or
  overwritten — "rollback guaranteed" per the plan. A version's parent is
  found via parent_script_id; the full chain is queryable without a separate
  script_versions table.
- compiled_files: the full multi-file bundle the Script Compiler produced
  (specs/pages/fixtures/utils) — `code`/`file_path` continue to hold the
  entry spec for backward-compatible display in the existing script editor.
- contract: the Automation Generation Contract that produced this version —
  audit trail + regeneration source (no free-form code, per ADR-001).
- static_gate_result: the persisted Static Quality Gate verdict.
- status CHECK constraint widened to the full target lifecycle named in the
  plan. Not every value is assigned by Phase 2 code yet (mcp_discovered,
  ci_ready, production_regression_candidate arrive in Phase 3/5) — defining
  the full vocabulary now avoids a second migration when those phases land.

Revision ID: 032
Revises: 031
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None

NEW_STATUSES = (
    "'ai_draft','draft','in_review','pending_approval','approved','rejected',"
    "'executed','deprecated','blocked','generated','static_passed',"
    "'mcp_discovered','dry_run_passed','reviewer_approved','lead_approved',"
    "'ci_ready','production_regression_candidate'"
)
OLD_STATUSES = (
    "'ai_draft','draft','in_review','pending_approval','approved',"
    "'rejected','executed','deprecated','blocked'"
)


def upgrade() -> None:
    op.add_column(
        "automation_scripts",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "automation_scripts",
        sa.Column("parent_script_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_automation_scripts_parent_script_id",
        "automation_scripts",
        "automation_scripts",
        ["parent_script_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_automation_scripts_parent_script_id", "automation_scripts", ["parent_script_id"]
    )
    op.add_column(
        "automation_scripts",
        sa.Column("compiled_files", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "automation_scripts",
        sa.Column("contract", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "automation_scripts",
        sa.Column("static_gate_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.execute("ALTER TABLE automation_scripts DROP CONSTRAINT IF EXISTS ck_automation_scripts_status")
    op.execute(
        f"ALTER TABLE automation_scripts ADD CONSTRAINT ck_automation_scripts_status "
        f"CHECK (status IN ({NEW_STATUSES})) NOT VALID"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE automation_scripts DROP CONSTRAINT IF EXISTS ck_automation_scripts_status")
    op.execute(
        f"ALTER TABLE automation_scripts ADD CONSTRAINT ck_automation_scripts_status "
        f"CHECK (status IN ({OLD_STATUSES})) NOT VALID"
    )

    op.drop_column("automation_scripts", "static_gate_result")
    op.drop_column("automation_scripts", "contract")
    op.drop_column("automation_scripts", "compiled_files")
    op.drop_index("ix_automation_scripts_parent_script_id", table_name="automation_scripts")
    op.drop_constraint("fk_automation_scripts_parent_script_id", "automation_scripts", type_="foreignkey")
    op.drop_column("automation_scripts", "parent_script_id")
    op.drop_column("automation_scripts", "version")
