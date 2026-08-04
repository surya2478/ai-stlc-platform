"""058 — Replace the project domain taxonomy

The qa_domain / telecom_domain pair is replaced by the delivery-track taxonomy
the projects screens now offer (Digital-Consumer, Digital-Business, Non-Digital,
Billing, Sales, Marketing, CCC, Special Track, Production Testing).

projects.domain is a plain VARCHAR with no check constraint — the allowed values
are enforced by app.schemas.project.ProjectDomain. Rows still holding a retired
value would therefore load fine but fail validation the moment someone saved an
edit, so clear them. There is no meaningful mapping from the old two-value
taxonomy onto the new tracks; the domain simply has to be picked again.

Revision ID: 058
Revises: 057
"""
import sqlalchemy as sa
from alembic import op

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None

RETIRED_DOMAINS = ("qa_domain", "telecom_domain")


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE projects SET domain = NULL WHERE domain IN :retired"
        ).bindparams(sa.bindparam("retired", value=RETIRED_DOMAINS, expanding=True))
    )


def downgrade() -> None:
    # The previous values are not recoverable — they were cleared, not mapped.
    pass
