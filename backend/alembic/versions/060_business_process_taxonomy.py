"""060 - Business Process master table

Requirements already carry a `business_process` ("Journey / Business Process"
on the Requirement Analysis screen), but it was the only classification field
with no governed master table behind it — every screen offered a free-text box,
so the same journey could be spelled four ways and nothing could group by it.

Adds `business_processes` with the same shape as the other flat taxonomy
lookups (systems/sub_request_types from 019, test_case_types/environments from
042), and mounts it under /taxonomy/business-processes.

Seeded from the distinct values already present in `requirements.business_process`
rather than from an invented vocabulary: those are the only values known to be
real for this deployment, and seeding them means no existing requirement is
left holding a value the new dropdown cannot offer. A deployment with no
requirements yet gets an empty table for an admin to fill in — an empty master
table is honest, a fabricated one is not.

Also carries a partial unique index on `code` for organization-less rows. The
shared `UniqueConstraint(organization_id, code)` cannot constrain those, since
Postgres treats NULLs as distinct — see the comment at the index for detail.

Idempotent — safe to re-run after partial failure (mirrors the 042 pattern).

Revision ID: 060
Revises: 059
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None

TABLE = "business_processes"


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


def _common_taxonomy_columns() -> list[sa.Column]:
    """Same shared columns as every other taxonomy master table."""
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def _code_for(name: str) -> str:
    """Machine-friendly code, matching the shape the schema validator enforces."""
    code = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return (code or "BUSINESS_PROCESS")[:60]


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(TABLE):
        op.create_table(
            TABLE,
            *_common_taxonomy_columns(),
            sa.UniqueConstraint("organization_id", "code", name=f"uq_{TABLE}_org_code"),
        )
    for col in ("organization_id", "name", "code"):
        idx = f"ix_{TABLE}_{col}"
        if not _index_exists(idx):
            op.create_index(idx, TABLE, [col])

    # UniqueConstraint(organization_id, code) does not constrain global rows:
    # Postgres treats NULLs as distinct, so (NULL, 'SALES') can be inserted
    # repeatedly and the service's 409 never fires. Every taxonomy table shares
    # this gap — qa_domains already carries a duplicate because of it — so the
    # new table gets the partial index that makes the promise true for the
    # organization-less rows the seeder and the admin UI actually create.
    if not _index_exists(f"uq_{TABLE}_global_code"):
        op.create_index(
            f"uq_{TABLE}_global_code",
            TABLE,
            ["code"],
            unique=True,
            postgresql_where=sa.text("organization_id IS NULL"),
        )

    # Adopt what requirements already use. Ordered by how often each value
    # appears so the most-used journeys sort to the top of the dropdown.
    existing = conn.execute(
        sa.text(
            "SELECT btrim(business_process) AS name, count(*) AS uses "
            "FROM requirements "
            "WHERE business_process IS NOT NULL AND btrim(business_process) <> '' "
            "GROUP BY btrim(business_process) "
            "ORDER BY count(*) DESC, btrim(business_process)"
        )
    ).fetchall()

    seen: set[str] = set()
    sort_order = 0
    for row in existing:
        code = _code_for(row.name)
        # Two spellings can collapse to one code ("Order to Cash" /
        # "order-to-cash"); the first (most used) wins the row.
        if code in seen:
            continue
        already = conn.execute(
            sa.text(f'SELECT 1 FROM "{TABLE}" WHERE organization_id IS NULL AND code = :code'),
            {"code": code},
        ).fetchone()
        if already:
            seen.add(code)
            continue
        conn.execute(
            sa.text(
                f'INSERT INTO "{TABLE}" '
                "(code, name, description, status, is_active, sort_order, created_at, updated_at) "
                "VALUES (:code, :name, :description, 'active', true, :sort_order, now(), now())"
            ),
            {
                "code": code,
                "name": row.name,
                "description": "Adopted from requirements already classified with this journey.",
                "sort_order": sort_order,
            },
        )
        seen.add(code)
        sort_order += 1


def downgrade() -> None:
    # requirements.business_process is free text and is not FK'd to this table,
    # so dropping it loses the governed list but no requirement's own value.
    if _table_exists(TABLE):
        op.drop_table(TABLE)
