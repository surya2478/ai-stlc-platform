"""034 - automation_scripts: add 'needs_regeneration' status

Data-migration status for scripts generated before the locator grounding
fixes (page-scoping, single-candidate fill-step fallback, contract target
validation) landed on 2026-07-10. execution_blocked_reason() in
automation_service.py gives these a specific, actionable reason instead of
the generic "not approved" — distinct from "rejected" (a human judgement
call) or "deprecated" (superseded), since these were approved in good faith
and are only wrong because the generator that produced them has since been
fixed.

Revision ID: 034
Revises: 033
Create Date: 2026-07-10
"""
from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None

NEW_STATUSES = (
    "'ai_draft','draft','in_review','pending_approval','approved','rejected',"
    "'executed','deprecated','blocked','generated','static_passed',"
    "'mcp_discovered','dry_run_passed','reviewer_approved','lead_approved',"
    "'ci_ready','production_regression_candidate','needs_regeneration'"
)
OLD_STATUSES = (
    "'ai_draft','draft','in_review','pending_approval','approved','rejected',"
    "'executed','deprecated','blocked','generated','static_passed',"
    "'mcp_discovered','dry_run_passed','reviewer_approved','lead_approved',"
    "'ci_ready','production_regression_candidate'"
)


def upgrade() -> None:
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
