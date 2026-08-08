"""061 - Allow "review" and "rag" LLM roles on project_llm_settings

`project_llm_settings.llm_role` was constrained to ('coding','vision',
'reasoning') by ck_project_llm_settings_role. Two roles are added:

  - review: the four gates that judge another agent's output (requirement
    quality, scenario review, test case review, automation script review).
    Previously these shared the reasoning route with the agents that PRODUCED
    the artifact — a reviewer running the generator's model shares its blind
    spots, and these gates feed the autonomy thresholds that decide what
    publishes without a human.
  - rag: assistant / knowledge-base answer generation.

Constraint-only change: no column is added, no row is rewritten, and every
existing row keeps a role that stays valid. Purely widening, so the upgrade
cannot fail on existing data.

The downgrade narrows the constraint again, which WOULD fail on rows using a
new role, so it clears llm_role on those rows first — a row reverting to
llm_role IS NULL means "applies to all roles", the pre-061 behaviour, rather
than being deleted. Note that dropping to NULL can collide with the partial
unique indexes on (project_id, coalesce(llm_role,'__all__')): if a project has
both a generic primary and a review primary, the downgrade would produce two
'__all__' primaries. It de-primaries the new-role rows first to avoid that.

Idempotent — safe to re-run after partial failure.

Revision ID: 061
Revises: 060
"""
from alembic import op

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None

TABLE = "project_llm_settings"
CONSTRAINT = "ck_project_llm_settings_role"

OLD_ROLES = ("coding", "vision", "reasoning")
NEW_ROLES = ("coding", "vision", "review", "rag", "reasoning")


def _role_check(roles: tuple[str, ...]) -> str:
    joined = "','".join(roles)
    return f"llm_role IS NULL OR llm_role IN ('{joined}')"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
    op.create_check_constraint(CONSTRAINT, TABLE, _role_check(NEW_ROLES))


def downgrade() -> None:
    # Rows on a role that no longer exists revert to the generic
    # ("applies to all roles") setting rather than being deleted. Primary and
    # fallback flags are cleared first so the reverted rows cannot collide
    # with an existing generic primary on the partial unique indexes.
    op.execute(
        f"""
        UPDATE {TABLE}
           SET is_primary = false,
               is_fallback = false,
               fallback_priority = NULL
         WHERE llm_role IN ('review', 'rag')
        """
    )
    op.execute(f"UPDATE {TABLE} SET llm_role = NULL WHERE llm_role IN ('review', 'rag')")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
    op.create_check_constraint(CONSTRAINT, TABLE, _role_check(OLD_ROLES))
