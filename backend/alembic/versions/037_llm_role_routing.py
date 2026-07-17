"""037 - llm_role routing on project_llm_settings

Adds llm_role ('coding' | 'vision' | 'reasoning' | NULL-for-all-roles) so a
project can pin a different provider/model per role behind the AI Gateway's
3-model architecture — see app/llm/roles.py and
app/services/project_llm_settings_service.py. Rebuilds the three uniqueness
indexes role-aware (a NULL llm_role is coalesced to '__all__' so it keeps
acting as a single generic group, same as before this migration).

Revision ID: 037
Revises: 036
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_llm_settings", sa.Column("llm_role", sa.String(length=20), nullable=True))
    op.create_index("ix_project_llm_settings_llm_role", "project_llm_settings", ["llm_role"])
    op.create_check_constraint(
        "ck_project_llm_settings_role",
        "project_llm_settings",
        "llm_role IS NULL OR llm_role IN ('coding','vision','reasoning')",
    )

    op.drop_index("uq_project_llm_provider", table_name="project_llm_settings")
    op.drop_index("uq_project_primary_llm", table_name="project_llm_settings")
    op.drop_index("uq_project_fallback_priority", table_name="project_llm_settings")

    op.create_index(
        "uq_project_llm_provider_role",
        "project_llm_settings",
        ["project_id", "provider_key", sa.text("coalesce(llm_role, '__all__')")],
        unique=True,
    )
    op.create_index(
        "uq_project_primary_llm_role",
        "project_llm_settings",
        ["project_id", sa.text("coalesce(llm_role, '__all__')")],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )
    op.create_index(
        "uq_project_fallback_priority_role",
        "project_llm_settings",
        ["project_id", "fallback_priority", sa.text("coalesce(llm_role, '__all__')")],
        unique=True,
        postgresql_where=sa.text("is_fallback IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_project_fallback_priority_role", table_name="project_llm_settings")
    op.drop_index("uq_project_primary_llm_role", table_name="project_llm_settings")
    op.drop_index("uq_project_llm_provider_role", table_name="project_llm_settings")

    op.create_index(
        "uq_project_llm_provider",
        "project_llm_settings",
        ["project_id", "provider_key"],
        unique=True,
    )
    op.create_index(
        "uq_project_primary_llm",
        "project_llm_settings",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )
    op.create_index(
        "uq_project_fallback_priority",
        "project_llm_settings",
        ["project_id", "fallback_priority"],
        unique=True,
        postgresql_where=sa.text("is_fallback IS TRUE"),
    )

    op.drop_constraint("ck_project_llm_settings_role", "project_llm_settings", type_="check")
    op.drop_index("ix_project_llm_settings_llm_role", table_name="project_llm_settings")
    op.drop_column("project_llm_settings", "llm_role")
