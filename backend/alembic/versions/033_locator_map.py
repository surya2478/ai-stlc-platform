"""033 - locator_map (Phase 3: Playwright MCP Discovery Agent)

Durable, per-element locator knowledge base built from live browser
evidence — see app/models/locator_map.py and
app/agents/automation/mcp_discovery_agent.py. Upserted by
(application_id, page, element_name) so re-discovery refreshes confidence
and last_validated_at instead of accumulating duplicate rows.

Revision ID: 033
Revises: 032
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "locator_map",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("page", sa.String(length=500), nullable=False),
        sa.Column("element_name", sa.String(length=200), nullable=False),
        sa.Column("business_meaning", sa.Text(), nullable=True),
        sa.Column("recommended_locator", sa.Text(), nullable=False),
        sa.Column("recommended_strategy", sa.String(length=20), nullable=False),
        sa.Column("fallback_locator", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by_scripts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["project_applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "recommended_strategy IN ('role','label','placeholder','text','testid','css','xpath')",
            name="ck_locator_map_recommended_strategy",
        ),
        sa.UniqueConstraint(
            "application_id", "page", "element_name", name="uq_locator_map_application_page_element"
        ),
    )
    op.create_index("ix_locator_map_project_id", "locator_map", ["project_id"])
    op.create_index("ix_locator_map_application_id", "locator_map", ["application_id"])
    op.create_index("ix_locator_map_page", "locator_map", ["page"])


def downgrade() -> None:
    op.drop_index("ix_locator_map_page", table_name="locator_map")
    op.drop_index("ix_locator_map_application_id", table_name="locator_map")
    op.drop_index("ix_locator_map_project_id", table_name="locator_map")
    op.drop_table("locator_map")
