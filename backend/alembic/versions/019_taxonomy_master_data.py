"""019 - Telecom QA taxonomy master data

Revision ID: 019
Revises: 018
Create Date: 2026-06-25

Creates the 6 master-data tables for the centrally governed telecom QA taxonomy:
    - qa_domains
    - product_groups        (parent_id -> qa_domains)
    - products              (parent_id -> product_groups)
    - systems
    - sub_request_types
    - taxonomy_relationships (polymorphic M:N edges)

Idempotent — safe to re-run after partial failure.
"""
from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


# ── helpers (mirrors the pattern from 017_data_layer_enterprise_hardening) ──

def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    r = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=:t"
        ),
        {"t": table},
    )
    return r.fetchone() is not None


def _index_exists(index_name: str) -> bool:
    conn = op.get_bind()
    r = conn.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"),
        {"n": index_name},
    )
    return r.fetchone() is not None


def _common_columns() -> list[sa.Column]:
    """Audit + lifecycle columns shared by every taxonomy master entity."""
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("owner", sa.String(length=150), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def _create_indexes(table: str, extra: list[str] | None = None) -> None:
    """Standard indexes on common columns; pass extra column names for per-table ones."""
    for col in ("organization_id", "name", "code"):
        idx = f"ix_{table}_{col}"
        if not _index_exists(idx):
            op.create_index(idx, table, [col])
    for col in extra or []:
        idx = f"ix_{table}_{col}"
        if not _index_exists(idx):
            op.create_index(idx, table, [col])


# ── upgrade ──────────────────────────────────────────────────────────────────


def upgrade() -> None:
    # qa_domains
    if not _table_exists("qa_domains"):
        op.create_table(
            "qa_domains",
            *_common_columns(),
            sa.UniqueConstraint("organization_id", "code", name="uq_qa_domains_org_code"),
        )
    _create_indexes("qa_domains")

    # product_groups (parent -> qa_domains)
    if not _table_exists("product_groups"):
        op.create_table(
            "product_groups",
            *_common_columns(),
            sa.Column(
                "parent_id",
                sa.Integer(),
                sa.ForeignKey("qa_domains.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.UniqueConstraint("organization_id", "code", name="uq_product_groups_org_code"),
        )
    _create_indexes("product_groups", extra=["parent_id"])

    # products (parent -> product_groups)
    if not _table_exists("products"):
        op.create_table(
            "products",
            *_common_columns(),
            sa.Column(
                "parent_id",
                sa.Integer(),
                sa.ForeignKey("product_groups.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.UniqueConstraint("organization_id", "code", name="uq_products_org_code"),
        )
    _create_indexes("products", extra=["parent_id"])

    # systems
    if not _table_exists("systems"):
        op.create_table(
            "systems",
            *_common_columns(),
            sa.UniqueConstraint("organization_id", "code", name="uq_systems_org_code"),
        )
    _create_indexes("systems")

    # sub_request_types
    if not _table_exists("sub_request_types"):
        op.create_table(
            "sub_request_types",
            *_common_columns(),
            sa.UniqueConstraint("organization_id", "code", name="uq_sub_request_types_org_code"),
        )
    _create_indexes("sub_request_types")

    # taxonomy_relationships (polymorphic M:N edges)
    if not _table_exists("taxonomy_relationships"):
        op.create_table(
            "taxonomy_relationships",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("relation_type", sa.String(length=60), nullable=False),
            sa.Column("from_entity", sa.String(length=40), nullable=False),
            sa.Column("from_id", sa.Integer(), nullable=False),
            sa.Column("to_entity", sa.String(length=40), nullable=False),
            sa.Column("to_id", sa.Integer(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column(
                "created_by",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint(
                "relation_type",
                "from_entity",
                "from_id",
                "to_entity",
                "to_id",
                name="uq_taxonomy_relationships_edge",
            ),
        )
    for col in ("organization_id", "relation_type", "from_entity", "from_id", "to_entity", "to_id"):
        idx = f"ix_taxonomy_relationships_{col}"
        if not _index_exists(idx):
            op.create_index(idx, "taxonomy_relationships", [col])


# ── downgrade ────────────────────────────────────────────────────────────────


def downgrade() -> None:
    # Drop child-first to honour FKs
    for table in (
        "taxonomy_relationships",
        "sub_request_types",
        "systems",
        "products",
        "product_groups",
        "qa_domains",
    ):
        if _table_exists(table):
            op.drop_table(table)
