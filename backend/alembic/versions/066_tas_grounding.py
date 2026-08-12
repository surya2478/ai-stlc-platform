"""066 - Test Automation Studio: application discovery, grounding, dry run

Adds the evidence layer the studio was missing. Until now Screen 3 generated
scripts from test case prose alone, so every locator in them was an LLM guess
about a page it had never seen. This migration introduces:

  tas_discovery_runs        one live crawl of the batch's application
  tas_discovered_elements   the ranked, real elements that crawl found

plus the columns that let the three existing screens show what the evidence
changed:

  tas_intake_batches      how to log in before crawling (secret encrypted)
  tas_refined_test_cases  whether each step resolved to a real element
  tas_script_assets       whether the script was compiled, and whether it ran

Purely additive. Downgrade drops the two tables and the added columns, leaving
the studio exactly as it behaved before — free-form generation still works,
it is simply ungrounded.

Revision ID: 066
Revises: 065
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── The crawl ────────────────────────────────────────────────────────────
    op.create_table(
        "tas_discovery_runs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "batch_id", sa.Integer(), sa.ForeignKey("tas_intake_batches.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="running"),
        sa.Column("application_url", sa.Text(), nullable=True),
        sa.Column("application_environment", sa.String(length=50), nullable=True),
        # How the crawl authenticated, and whether it worked. A crawl that
        # never got past the login page produces a catalog of login-form
        # elements and nothing else — that is a very different result from a
        # successful crawl, and the screens have to be able to say which
        # happened rather than reporting "12 elements found" either way.
        sa.Column("auth_mode", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("auth_status", sa.String(length=30), nullable=False, server_default="not_required"),
        sa.Column("auth_detail", sa.Text(), nullable=True),
        sa.Column("pages_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("elements_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("explored_pages", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("blockers", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('running','completed','failed')", name="ck_tas_discovery_run_status"
        ),
        sa.CheckConstraint("auth_mode IN ('none','form')", name="ck_tas_discovery_run_auth_mode"),
        sa.CheckConstraint(
            "auth_status IN ('not_required','succeeded','failed','skipped')",
            name="ck_tas_discovery_run_auth_status",
        ),
    )
    op.create_index("ix_tas_discovery_runs_project_id", "tas_discovery_runs", ["project_id"])
    op.create_index("ix_tas_discovery_runs_batch_id", "tas_discovery_runs", ["batch_id"])
    op.create_index("ix_tas_discovery_runs_is_current", "tas_discovery_runs", ["is_current"])
    op.create_index("ix_tas_discovery_runs_status", "tas_discovery_runs", ["status"])

    op.create_table(
        "tas_discovered_elements",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "batch_id", sa.Integer(), sa.ForeignKey("tas_intake_batches.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "discovery_run_id",
            sa.Integer(),
            sa.ForeignKey("tas_discovery_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_url", sa.String(length=1000), nullable=False),
        sa.Column("page_title", sa.String(length=500), nullable=True),
        # element_name matches locator_map's own bound (ELEMENT_NAME_MAX = 200)
        # because grounding matches a contract element against this name — a
        # shorter column here would silently truncate exactly the names the
        # generator is told to reuse.
        sa.Column("element_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=True),
        sa.Column("accessible_name", sa.Text(), nullable=True),
        sa.Column("business_meaning", sa.Text(), nullable=True),
        sa.Column("recommended_locator", sa.Text(), nullable=False),
        sa.Column("recommended_strategy", sa.String(length=20), nullable=False, server_default="role"),
        sa.Column("confidence_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("href", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "discovery_run_id", "page_url", "element_name", name="uq_tas_discovered_element"
        ),
    )
    op.create_index("ix_tas_discovered_elements_project_id", "tas_discovered_elements", ["project_id"])
    op.create_index("ix_tas_discovered_elements_batch_id", "tas_discovered_elements", ["batch_id"])
    op.create_index(
        "ix_tas_discovered_elements_discovery_run_id", "tas_discovered_elements", ["discovery_run_id"]
    )
    op.create_index("ix_tas_discovered_elements_element_name", "tas_discovered_elements", ["element_name"])

    # ── Screen 1: how the crawl signs in ─────────────────────────────────────
    # auth_config holds only the non-secret shape of the login form (which URL,
    # which field labels). The username and password live in
    # auth_secret_encrypted as one Fernet blob and are never returned by the
    # API — the read model exposes `has_credentials` and nothing more.
    op.add_column(
        "tas_intake_batches",
        sa.Column("auth_mode", sa.String(length=20), nullable=False, server_default="none"),
    )
    op.add_column(
        "tas_intake_batches",
        sa.Column("auth_config", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column("tas_intake_batches", sa.Column("auth_secret_encrypted", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_tas_intake_batch_auth_mode", "tas_intake_batches", "auth_mode IN ('none','form')"
    )

    # ── Screen 2: did each step resolve to a real element ────────────────────
    op.add_column(
        "tas_refined_test_cases",
        sa.Column("grounding_status", sa.String(length=30), nullable=False, server_default="not_checked"),
    )
    op.add_column(
        "tas_refined_test_cases", sa.Column("grounding_summary", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "tas_refined_test_cases", sa.Column("grounded_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tas_refined_test_cases",
        sa.Column(
            "discovery_run_id",
            sa.Integer(),
            sa.ForeignKey("tas_discovery_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_tas_refined_tc_grounding_status",
        "tas_refined_test_cases",
        "grounding_status IN ('not_checked','grounded','partially_grounded','ungrounded')",
    )
    op.create_index(
        "ix_tas_refined_test_cases_grounding_status", "tas_refined_test_cases", ["grounding_status"]
    )

    # ── Screen 3: was it compiled, and did it run ────────────────────────────
    op.add_column(
        "tas_script_assets",
        sa.Column("generation_mode", sa.String(length=20), nullable=False, server_default="freeform"),
    )
    # The compiled bundle's entry path within `files` + `code` (e.g.
    # "specs/tc-0007.spec.ts"). The runner needs it to know which file to
    # execute; `script_key` is a display/download filename and is not a path
    # into the bundle.
    op.add_column("tas_script_assets", sa.Column("entry_path", sa.String(length=300), nullable=True))
    op.add_column("tas_script_assets", sa.Column("contract", postgresql.JSONB(), nullable=True))
    op.add_column("tas_script_assets", sa.Column("static_gate_result", postgresql.JSONB(), nullable=True))
    op.add_column("tas_script_assets", sa.Column("grounding", postgresql.JSONB(), nullable=True))
    op.add_column(
        "tas_script_assets",
        sa.Column("dry_run_status", sa.String(length=30), nullable=False, server_default="not_run"),
    )
    op.add_column("tas_script_assets", sa.Column("dry_run_summary", postgresql.JSONB(), nullable=True))
    op.add_column("tas_script_assets", sa.Column("dry_run_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_tas_script_asset_generation_mode",
        "tas_script_assets",
        "generation_mode IN ('compiled','freeform')",
    )
    op.create_check_constraint(
        "ck_tas_script_asset_dry_run_status",
        "tas_script_assets",
        "dry_run_status IN ('not_run','queued','running','passed','failed','blocked')",
    )
    op.create_index("ix_tas_script_assets_dry_run_status", "tas_script_assets", ["dry_run_status"])


def downgrade() -> None:
    op.drop_index("ix_tas_script_assets_dry_run_status", table_name="tas_script_assets")
    op.drop_constraint("ck_tas_script_asset_dry_run_status", "tas_script_assets", type_="check")
    op.drop_constraint("ck_tas_script_asset_generation_mode", "tas_script_assets", type_="check")
    for column in (
        "dry_run_at",
        "dry_run_summary",
        "dry_run_status",
        "grounding",
        "static_gate_result",
        "contract",
        "entry_path",
        "generation_mode",
    ):
        op.drop_column("tas_script_assets", column)

    op.drop_index("ix_tas_refined_test_cases_grounding_status", table_name="tas_refined_test_cases")
    op.drop_constraint("ck_tas_refined_tc_grounding_status", "tas_refined_test_cases", type_="check")
    for column in ("discovery_run_id", "grounded_at", "grounding_summary", "grounding_status"):
        op.drop_column("tas_refined_test_cases", column)

    op.drop_constraint("ck_tas_intake_batch_auth_mode", "tas_intake_batches", type_="check")
    for column in ("auth_secret_encrypted", "auth_config", "auth_mode"):
        op.drop_column("tas_intake_batches", column)

    op.drop_table("tas_discovered_elements")
    op.drop_table("tas_discovery_runs")
