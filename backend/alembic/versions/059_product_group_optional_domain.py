"""Let a Product Group stand on its own, without a QA Domain above it.

`product_groups.parent_id` was NOT NULL, which made QA Domain the mandatory
root of the classification chain: Domain → Product Group → Product. That is not
how the UAT template is actually filled in. Domain is an independent label
alongside Channel, while the dependency that matters to a tester runs

    Product Group → Product → Sub Request Type

with the last hop already modelled as a `subrequest_for_product` edge in
`taxonomy_relationships`. Requiring a Domain first forced every deployment to
invent a domain row purely to unlock the level below it.

Nullable rather than dropped: the column still expresses a real relationship
for anyone who wants to group product families under a domain, and
`/taxonomy/tree` keeps nesting the ones that set it. It is simply no longer a
precondition for creating a Product Group.

Safe on existing data — the FK, its ON DELETE CASCADE and every index are
untouched, and rows that already carry a parent keep it. Only the NOT NULL
constraint is relaxed, so no value changes and no backfill is required.

Revision ID: 059
Revises: 058
"""
from alembic import op
import sqlalchemy as sa

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "product_groups",
        "parent_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # Re-imposing NOT NULL would fail against any parentless row created while
    # the column was nullable. Those rows cannot be given a correct parent
    # automatically — there is no rule that says which domain they belong to —
    # so they are detached from the hierarchy instead of silently misfiled.
    conn = op.get_bind()
    orphans = conn.execute(
        sa.text("SELECT count(*) FROM product_groups WHERE parent_id IS NULL")
    ).scalar_one()
    if orphans:
        conn.execute(sa.text("DELETE FROM product_groups WHERE parent_id IS NULL"))

    op.alter_column(
        "product_groups",
        "parent_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
