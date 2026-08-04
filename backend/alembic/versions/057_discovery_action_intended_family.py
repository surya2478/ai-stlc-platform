"""Record what a discovery action was *meant* to do, not only what it did.

`capture_service` degrades an action to `read` whenever it cannot resolve the
element a step named, or when performing it fails. That degradation is correct
behaviour — refusing to click a best guess between two identically-named
controls is the whole point — but it was lossy: the action was persisted as
`read`, indistinguishable from a step that was always meant to be an
observation.

`application_model_service` raises the critical MISSING_ELEMENT gap only for
actions whose family is click/input/select, so a degraded click raised nothing.
`resolve_target_ref` promises the opposite in its own docstring ("the model
build raises MISSING_ELEMENT, and a human is asked"), and that promise silently
did not hold.

Observed live, session 33: four actions, one of them "Click the Register
button" on a page carrying both a `link "Register"` and a `button "Register"`.
The ambiguity was refused, the click became a `read`, the model built with one
screen and zero elements, raised zero gaps, and published clean — grounding
nothing.

Additive and nullable: every existing row keeps meaning exactly what it meant,
and a NULL simply says "this action was never degraded".

Revision ID: 057
Revises: 056
"""
from alembic import op
import sqlalchemy as sa

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discovery_actions",
        sa.Column("intended_action_family", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discovery_actions", "intended_action_family")
