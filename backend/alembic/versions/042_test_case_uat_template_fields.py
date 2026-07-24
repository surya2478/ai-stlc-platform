"""042 - Test Case UAT template field closure

Revision ID: 042
Revises: 041
Create Date: 2026-07-24

Adds the backend support needed to close the gap against the QA org's UAT
Test Case template (docs/autonomous-automation-lab/test-case_template.xlsx):

  - 3 new flat taxonomy lookup tables: test_case_types, test_case_complexities,
    environments (same shape as the existing systems/sub_request_types tables
    from migration 019), seeded with their known values.
  - plan_test_cases: many-to-many enrollment of a TestCase into a TestPlan,
    carrying the plan-time Environment, Tester assignment and Planned
    Execution Sequence. Additive — TestCase.linked_test_plan_id is untouched.
  - New nullable columns on test_cases: channel_id, domain_id, area_of_test_id,
    product_id, sub_request_type_id, test_case_type_id, test_case_complexity_id,
    test_case_objective, atc_test_case, is_critical, ppm_id. All additive —
    existing free-text columns (telecom_domain, product, sub_request_type,
    test_type) are kept for backward compatibility.
  - New nullable columns on execution_results: tested_by_id, sit_status,
    blocking_defect_id, other_reason. Extends ck_execution_results_status to
    allow 'passed_with_snag' (UAT "Overall Status" outcome).
  - Width-skew fix: product_group/product/sub_request_type on test_cases were
    declared VARCHAR(200) in the model (test_case.py:45-47) but created as
    VARCHAR(50/60) in migration 013 — aligned to VARCHAR(200) here.

Idempotent — safe to re-run after partial failure (mirrors the 019 pattern).
"""
from alembic import op
import sqlalchemy as sa

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


# ── helpers (mirrors 019_taxonomy_master_data / 017_data_layer_enterprise_hardening) ──

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


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    r = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
        ),
        {"t": table, "c": column},
    )
    return r.fetchone() is not None


def _index_exists(index_name: str) -> bool:
    conn = op.get_bind()
    r = conn.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"),
        {"n": index_name},
    )
    return r.fetchone() is not None


def _constraint_exists(table: str, name: str) -> bool:
    conn = op.get_bind()
    r = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint c JOIN pg_class t ON c.conrelid = t.oid "
            "WHERE t.relname = :t AND c.conname = :n"
        ),
        {"t": table, "n": name},
    )
    return r.fetchone() is not None


def _common_taxonomy_columns() -> list[sa.Column]:
    """Same shared columns as the taxonomy master tables (migration 019)."""
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


def _create_taxonomy_indexes(table: str) -> None:
    for col in ("organization_id", "name", "code"):
        idx = f"ix_{table}_{col}"
        if not _index_exists(idx):
            op.create_index(idx, table, [col])


def _seed_taxonomy(table: str, rows: list[tuple[str, str, int]]) -> None:
    """rows: list of (code, name, sort_order). organization_id left NULL (global seed)."""
    conn = op.get_bind()
    for code, name, sort_order in rows:
        exists = conn.execute(
            sa.text(f'SELECT 1 FROM "{table}" WHERE organization_id IS NULL AND code = :code'),
            {"code": code},
        ).fetchone()
        if not exists:
            conn.execute(
                sa.text(
                    f'INSERT INTO "{table}" (code, name, status, is_active, sort_order, created_at, updated_at) '
                    f"VALUES (:code, :name, 'active', true, :sort_order, now(), now())"
                ),
                {"code": code, "name": name, "sort_order": sort_order},
            )


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 1. New flat taxonomy lookup tables
    # ------------------------------------------------------------------
    if not _table_exists("test_case_types"):
        op.create_table(
            "test_case_types",
            *_common_taxonomy_columns(),
            sa.UniqueConstraint("organization_id", "code", name="uq_test_case_types_org_code"),
        )
    _create_taxonomy_indexes("test_case_types")
    _seed_taxonomy(
        "test_case_types",
        [
            ("positive", "Positive", 0),
            ("negative", "Negative", 1),
            ("edge_boundary", "Edge / Boundary", 2),
            ("regression", "Regression", 3),
        ],
    )

    if not _table_exists("test_case_complexities"):
        op.create_table(
            "test_case_complexities",
            *_common_taxonomy_columns(),
            sa.UniqueConstraint("organization_id", "code", name="uq_test_case_complexities_org_code"),
        )
    _create_taxonomy_indexes("test_case_complexities")
    _seed_taxonomy(
        "test_case_complexities",
        [
            ("low", "Low", 0),
            ("medium", "Medium", 1),
            ("high", "High", 2),
        ],
    )

    if not _table_exists("environments"):
        op.create_table(
            "environments",
            *_common_taxonomy_columns(),
            sa.UniqueConstraint("organization_id", "code", name="uq_environments_org_code"),
        )
    _create_taxonomy_indexes("environments")
    _seed_taxonomy(
        "environments",
        [
            ("sit", "SIT", 0),
            ("qa", "QA", 1),
            ("uat", "UAT", 2),
            ("regression", "Regression", 3),
            ("production_smoke_test", "Production Smoke Test", 4),
        ],
    )

    # ------------------------------------------------------------------
    # 2. plan_test_cases (plan <-> test case enrollment)
    # ------------------------------------------------------------------
    if not _table_exists("plan_test_cases"):
        op.create_table(
            "plan_test_cases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("test_plan_id", sa.Integer(), sa.ForeignKey("test_plans.id", ondelete="CASCADE"), nullable=False),
            sa.Column("test_case_id", sa.Integer(), sa.ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("environment_id", sa.Integer(), sa.ForeignKey("environments.id", ondelete="SET NULL"), nullable=True),
            sa.Column("tester_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("planned_execution_sequence", sa.String(length=50), nullable=True),
            sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("test_plan_id", "test_case_id", name="uq_plan_test_cases_plan_case"),
        )
    for col in ("test_plan_id", "test_case_id", "environment_id", "tester_user_id"):
        idx = f"ix_plan_test_cases_{col}"
        if not _index_exists(idx):
            op.create_index(idx, "plan_test_cases", [col])

    # ------------------------------------------------------------------
    # 3. New columns on test_cases (all nullable/additive)
    # ------------------------------------------------------------------
    tc_new_columns: list[tuple[str, sa.types.TypeEngine, dict]] = [
        ("channel_id", sa.Integer(), {"fk": ("systems.id", "SET NULL")}),
        ("domain_id", sa.Integer(), {"fk": ("qa_domains.id", "SET NULL")}),
        ("area_of_test_id", sa.Integer(), {"fk": ("product_groups.id", "SET NULL")}),
        ("product_id", sa.Integer(), {"fk": ("products.id", "SET NULL")}),
        ("sub_request_type_id", sa.Integer(), {"fk": ("sub_request_types.id", "SET NULL")}),
        ("test_case_type_id", sa.Integer(), {"fk": ("test_case_types.id", "SET NULL")}),
        ("test_case_complexity_id", sa.Integer(), {"fk": ("test_case_complexities.id", "SET NULL")}),
        ("test_case_objective", sa.Text(), {}),
        ("atc_test_case", sa.String(length=255), {}),
        ("is_critical", sa.Boolean(), {"server_default": sa.text("false"), "nullable": False}),
        ("ppm_id", sa.String(length=50), {}),
    ]
    for col_name, col_type, opts in tc_new_columns:
        if not _column_exists("test_cases", col_name):
            fk = opts.get("fk")
            column = sa.Column(
                col_name,
                col_type,
                sa.ForeignKey(fk[0], ondelete=fk[1]) if fk else None,
                nullable=opts.get("nullable", True),
                server_default=opts.get("server_default"),
            ) if fk else sa.Column(
                col_name,
                col_type,
                nullable=opts.get("nullable", True),
                server_default=opts.get("server_default"),
            )
            op.add_column("test_cases", column)
    for col_name, _, opts in tc_new_columns:
        if opts.get("fk"):
            idx = f"ix_test_cases_{col_name}"
            if not _index_exists(idx):
                op.create_index(idx, "test_cases", [col_name])

    # Width-skew fix: align DB to the model (test_case.py:45-47 declares 200).
    for col_name in ("product_group", "product", "sub_request_type"):
        op.alter_column("test_cases", col_name, type_=sa.String(length=200))

    # ------------------------------------------------------------------
    # 4. New columns on execution_results (all nullable/additive)
    # ------------------------------------------------------------------
    er_new_columns = [
        ("tested_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        ("sit_status", sa.String(length=20), None),
        ("blocking_defect_id", sa.Integer(), sa.ForeignKey("defect_drafts.id", ondelete="SET NULL")),
        ("other_reason", sa.Text(), None),
    ]
    for col_name, col_type, fk in er_new_columns:
        if not _column_exists("execution_results", col_name):
            column = sa.Column(col_name, col_type, fk, nullable=True) if fk else sa.Column(col_name, col_type, nullable=True)
            op.add_column("execution_results", column)
    for col_name in ("tested_by_id", "blocking_defect_id"):
        idx = f"ix_execution_results_{col_name}"
        if not _index_exists(idx):
            op.create_index(idx, "execution_results", [col_name])

    # Extend ck_execution_results_status to allow 'passed_with_snag'.
    if _constraint_exists("execution_results", "ck_execution_results_status"):
        op.drop_constraint("ck_execution_results_status", "execution_results", type_="check")
    conn.execute(sa.text(
        'ALTER TABLE "execution_results" ADD CONSTRAINT "ck_execution_results_status" '
        "CHECK (status IN ('pending','pass','fail','skip','error','blocked','not_run','running','passed_with_snag')) "
        "NOT VALID"
    ))


def downgrade() -> None:
    conn = op.get_bind()

    if _constraint_exists("execution_results", "ck_execution_results_status"):
        op.drop_constraint("ck_execution_results_status", "execution_results", type_="check")
    conn.execute(sa.text(
        'ALTER TABLE "execution_results" ADD CONSTRAINT "ck_execution_results_status" '
        "CHECK (status IN ('pending','pass','fail','skip','error','blocked','not_run','running')) NOT VALID"
    ))

    for col_name in ("other_reason", "blocking_defect_id", "sit_status", "tested_by_id"):
        if _column_exists("execution_results", col_name):
            op.drop_column("execution_results", col_name)

    for col_name in (
        "ppm_id", "is_critical", "atc_test_case", "test_case_objective",
        "test_case_complexity_id", "test_case_type_id", "sub_request_type_id",
        "product_id", "area_of_test_id", "domain_id", "channel_id",
    ):
        if _column_exists("test_cases", col_name):
            op.drop_column("test_cases", col_name)

    if _table_exists("plan_test_cases"):
        op.drop_table("plan_test_cases")

    for table in ("environments", "test_case_complexities", "test_case_types"):
        if _table_exists(table):
            op.drop_table(table)
