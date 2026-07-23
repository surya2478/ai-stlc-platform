"""039 - project application governance fields (UI-014 Application Registry)

Adds application_type, aliases, lifecycle_status, business_owner_id,
technical_owner_id, domain, product_group, product and channel to
project_applications. These back the Application Registry screen's Owner,
Lifecycle, and Domain/Product/Channel columns and the Mapping Conflicts KPI
with real persisted data instead of rendering fabricated values.

Health-check, discovery-capability, AVD/device-compatibility and versioned
per-field history are deliberately NOT added here — no backing subsystem
exists for any of them yet, so the UI renders those sections as "Not
configured" rather than inventing schema for data nothing produces.

No backfill required: all new columns are nullable or carry a safe default
(lifecycle_status defaults to "active", aliases defaults to an empty list),
so existing rows keep working untouched.

Revision ID: 039
Revises: 038
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_applications", sa.Column("application_type", sa.String(length=80), nullable=True))
    op.add_column(
        "project_applications",
        sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column(
        "project_applications",
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.add_column("project_applications", sa.Column("business_owner_id", sa.Integer(), nullable=True))
    op.add_column("project_applications", sa.Column("technical_owner_id", sa.Integer(), nullable=True))
    op.add_column("project_applications", sa.Column("domain", sa.String(length=120), nullable=True))
    op.add_column("project_applications", sa.Column("product_group", sa.String(length=120), nullable=True))
    op.add_column("project_applications", sa.Column("product", sa.String(length=120), nullable=True))
    op.add_column("project_applications", sa.Column("channel", sa.String(length=80), nullable=True))

    op.create_foreign_key(
        "fk_project_applications_business_owner_id",
        "project_applications",
        "users",
        ["business_owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_project_applications_technical_owner_id",
        "project_applications",
        "users",
        ["technical_owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_project_applications_business_owner_id", "project_applications", ["business_owner_id"])
    op.create_index("ix_project_applications_technical_owner_id", "project_applications", ["technical_owner_id"])
    op.create_index("ix_project_applications_domain", "project_applications", ["domain"])
    op.create_index("ix_project_applications_product_group", "project_applications", ["product_group"])
    op.create_index("ix_project_applications_product", "project_applications", ["product"])
    op.create_index("ix_project_applications_channel", "project_applications", ["channel"])
    op.create_index("ix_project_applications_lifecycle_status", "project_applications", ["lifecycle_status"])


def downgrade() -> None:
    op.drop_index("ix_project_applications_lifecycle_status", table_name="project_applications")
    op.drop_index("ix_project_applications_channel", table_name="project_applications")
    op.drop_index("ix_project_applications_product", table_name="project_applications")
    op.drop_index("ix_project_applications_product_group", table_name="project_applications")
    op.drop_index("ix_project_applications_domain", table_name="project_applications")
    op.drop_index("ix_project_applications_technical_owner_id", table_name="project_applications")
    op.drop_index("ix_project_applications_business_owner_id", table_name="project_applications")
    op.drop_constraint("fk_project_applications_technical_owner_id", "project_applications", type_="foreignkey")
    op.drop_constraint("fk_project_applications_business_owner_id", "project_applications", type_="foreignkey")

    op.drop_column("project_applications", "channel")
    op.drop_column("project_applications", "product")
    op.drop_column("project_applications", "product_group")
    op.drop_column("project_applications", "domain")
    op.drop_column("project_applications", "technical_owner_id")
    op.drop_column("project_applications", "business_owner_id")
    op.drop_column("project_applications", "lifecycle_status")
    op.drop_column("project_applications", "aliases")
    op.drop_column("project_applications", "application_type")
