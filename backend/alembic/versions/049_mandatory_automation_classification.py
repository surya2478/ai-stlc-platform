"""049 - mandatory automation classification with a global default policy

Revision ID: 049
Revises: 048
Create Date: 2026-07-28
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.services.test_classification.policy_defaults import default_policy_rules

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None

DEFAULT_CODE = "PLATFORM_DEFAULT_AUTOMATION"


def upgrade() -> None:
    policy = sa.table(
        "automation_classification_policies",
        sa.column("project_id", sa.Integer),
        sa.column("application_id", sa.Integer),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("version", sa.Integer),
        sa.column("parent_policy_id", sa.Integer),
        sa.column("status", sa.String),
        sa.column("rules", postgresql.JSONB),
        sa.column("created_by", sa.Integer),
        sa.column("published_by", sa.Integer),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        policy,
        [{
            "project_id": None,
            "application_id": None,
            "code": DEFAULT_CODE,
            "name": "Platform Default Automation Classification",
            "version": 1,
            "parent_policy_id": None,
            "status": "published",
            "rules": default_policy_rules(),
            "created_by": None,
            "published_by": None,
            "published_at": now,
            "created_at": now,
            "updated_at": now,
        }],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM automation_classification_policies WHERE code = :code")
        .bindparams(code=DEFAULT_CODE)
    )
