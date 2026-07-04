"""027 - Widen automation_scripts status CHECK constraint to the full lifecycle.

Migration 017 created ``ck_automation_scripts_status`` allowing only
draft | pending_approval | approved | rejected | executed. Phases 2B/2C
introduced the richer AI-review lifecycle (see
``app.schemas.automation.AutomationScriptStatus``) — ai_draft | draft |
in_review | pending_approval | approved | rejected | executed | deprecated |
blocked — but the DB constraint was never updated to match. Any insert of a
script with status='ai_draft' (i.e. every AI-generated script) has been
failing with a CheckViolationError since Phase 2D shipped.

Revision ID: 027
Revises: 026
Create Date: 2026-07-01
"""
from alembic import op


revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None

OLD_STATUSES = "'draft','pending_approval','approved','rejected','executed'"
NEW_STATUSES = (
    "'ai_draft','draft','in_review','pending_approval','approved',"
    "'rejected','executed','deprecated','blocked'"
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
