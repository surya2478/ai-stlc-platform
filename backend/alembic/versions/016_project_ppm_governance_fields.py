"""016 - Add HP PPM ID, Project Manager, Business PM, and Domain to projects

Revision ID: 016
Revises: 015
Create Date: 2026-06-14

Adds governance fields required for HP PPM integration:
  - ppm_id            VARCHAR(50)  — numeric HP PPM project identifier
  - project_manager_name  VARCHAR(255) — IT/Delivery Project Manager
  - business_pm_name  VARCHAR(255) — Business-side Project Manager (optional)
  - domain            VARCHAR(50)  — project domain enum (qa_domain | telecom_domain)
"""
from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("ppm_id", sa.String(length=50), nullable=True))
    op.add_column("projects", sa.Column("project_manager_name", sa.String(length=255), nullable=True))
    op.add_column("projects", sa.Column("business_pm_name", sa.String(length=255), nullable=True))
    op.add_column("projects", sa.Column("domain", sa.String(length=50), nullable=True))

    # Index ppm_id for fast lookups (PPM dashboard queries)
    op.create_index("ix_projects_ppm_id", "projects", ["ppm_id"])
    # Index domain for filtering by domain in project lists
    op.create_index("ix_projects_domain", "projects", ["domain"])


def downgrade() -> None:
    op.drop_index("ix_projects_domain", table_name="projects")
    op.drop_index("ix_projects_ppm_id", table_name="projects")
    op.drop_column("projects", "domain")
    op.drop_column("projects", "business_pm_name")
    op.drop_column("projects", "project_manager_name")
    op.drop_column("projects", "ppm_id")
