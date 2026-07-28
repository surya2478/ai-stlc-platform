"""050 - configurable manual-only automation conditions

Revision ID: 050
Revises: 049
Create Date: 2026-07-28
"""

import json

from alembic import op
import sqlalchemy as sa

from app.services.test_classification.policy_defaults import default_policy_rules

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conditions = default_policy_rules()["manual_only_conditions"]
    op.execute(
        sa.text(
            """
            INSERT INTO automation_classification_policies (
                project_id, application_id, code, name, version,
                parent_policy_id, status, rules, created_by, published_by,
                published_at, created_at, updated_at
            )
            SELECT
                NULL, NULL, current.code, current.name, current.version + 1,
                current.id, 'published',
                jsonb_set(current.rules, '{manual_only_conditions}', CAST(:conditions AS jsonb), true),
                NULL, NULL, now(), now(), now()
            FROM automation_classification_policies AS current
            WHERE current.id = (
                SELECT id
                FROM automation_classification_policies
                WHERE code = 'PLATFORM_DEFAULT_AUTOMATION'
                ORDER BY version DESC
                LIMIT 1
            )
              AND NOT (current.rules ? 'manual_only_conditions')
            """
        ).bindparams(conditions=json.dumps(conditions))
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM automation_classification_policies
            WHERE code = 'PLATFORM_DEFAULT_AUTOMATION'
              AND rules ? 'manual_only_conditions'
              AND version > 1
            """
        )
    )
