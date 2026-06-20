"""017 - Data-layer enterprise hardening

Revision ID: 017
Revises: 016
Create Date: 2026-06-14

Fully idempotent migration — safe to re-run after partial failures.

1. Organizations table + org FK on users/projects
2. SoftDeleteMixin, VersionMixin, updated_by columns
3. FK cascade rules (dynamic constraint-name lookup)
4. Status CHECK constraints (NOT VALID for existing data)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


# ── helpers ──────────────────────────────────────────────────────────────────

def _col_exists(table, column):
    conn = op.get_bind()
    r = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
    ), {"t": table, "c": column})
    return r.fetchone() is not None


def _table_exists(table):
    conn = op.get_bind()
    r = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=:t"
    ), {"t": table})
    return r.fetchone() is not None


def _index_exists(index_name):
    conn = op.get_bind()
    r = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"
    ), {"n": index_name})
    return r.fetchone() is not None


def _constraint_exists(table, constraint_name):
    conn = op.get_bind()
    r = conn.execute(sa.text(
        "SELECT 1 FROM pg_constraint c "
        "JOIN pg_class r ON r.oid=c.conrelid "
        "JOIN pg_namespace n ON n.oid=r.relnamespace "
        "WHERE n.nspname='public' AND r.relname=:t AND c.conname=:cn"
    ), {"t": table, "cn": constraint_name})
    return r.fetchone() is not None


def _replace_fk_sql(table, local_col, ref_table, ref_col, ondelete):
    """Drop existing FK on table.local_col and recreate with ON DELETE rule."""
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        JOIN pg_attribute att ON att.attrelid = con.conrelid
            AND att.attnum = ANY(con.conkey)
        WHERE nsp.nspname = 'public'
          AND rel.relname = :table_name
          AND att.attname = :col_name
          AND con.contype = 'f'
        LIMIT 1
    """), {"table_name": table, "col_name": local_col})

    row = result.fetchone()
    if row is None:
        new_name = f"fk_{table}_{local_col}"
        if not _constraint_exists(table, new_name):
            op.create_foreign_key(new_name, table, ref_table, [local_col], [ref_col], ondelete=ondelete)
        return

    constraint_name = row[0]
    op.drop_constraint(constraint_name, table, type_="foreignkey")
    op.create_foreign_key(constraint_name, table, ref_table, [local_col], [ref_col], ondelete=ondelete)


def _add_col_if_missing(table, column_name, col_type, **kwargs):
    if not _col_exists(table, column_name):
        op.add_column(table, sa.Column(column_name, col_type, **kwargs))
        return True
    return False


def _add_fk_if_missing(name, table, ref_table, local_cols, remote_cols, **kwargs):
    if not _constraint_exists(table, name):
        op.create_foreign_key(name, table, ref_table, local_cols, remote_cols, **kwargs)


# ========================== UPGRADE ==========================

def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Organizations table
    # ------------------------------------------------------------------
    if not _table_exists("organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("name", sa.String(255), nullable=False, unique=True, index=True),
            sa.Column("slug", sa.String(100), nullable=False, unique=True, index=True),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("settings", JSONB, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 2a. organization_id on users and projects
    # ------------------------------------------------------------------
    _add_col_if_missing("users", "organization_id", sa.Integer, nullable=True)
    _add_fk_if_missing("fk_users_organization_id", "users", "organizations",
                       ["organization_id"], ["id"], ondelete="SET NULL")

    _add_col_if_missing("projects", "organization_id", sa.Integer, nullable=True)
    _add_fk_if_missing("fk_projects_organization_id", "projects", "organizations",
                       ["organization_id"], ["id"], ondelete="CASCADE")

    # ------------------------------------------------------------------
    # 2b. SoftDeleteMixin columns
    # ------------------------------------------------------------------
    soft_delete_tables = [
        "projects", "test_plans", "test_scenarios", "test_cases",
        "execution_runs", "defect_drafts", "automation_scripts",
        "reports", "uploaded_documents",
    ]
    for tbl in soft_delete_tables:
        _add_col_if_missing(tbl, "is_deleted", sa.Boolean, nullable=False, server_default="false")
        if not _index_exists(f"ix_{tbl}_is_deleted"):
            op.create_index(f"ix_{tbl}_is_deleted", tbl, ["is_deleted"])
        _add_col_if_missing(tbl, "deleted_at", sa.DateTime(timezone=True), nullable=True)
        if _add_col_if_missing(tbl, "deleted_by", sa.Integer, nullable=True):
            _add_fk_if_missing(f"fk_{tbl}_deleted_by", tbl, "users",
                               ["deleted_by"], ["id"], ondelete="SET NULL")
        else:
            _add_fk_if_missing(f"fk_{tbl}_deleted_by", tbl, "users",
                               ["deleted_by"], ["id"], ondelete="SET NULL")

    # requirements: already has is_deleted from migration 014
    _add_col_if_missing("requirements", "deleted_at", sa.DateTime(timezone=True), nullable=True)
    _add_col_if_missing("requirements", "deleted_by", sa.Integer, nullable=True)
    _add_fk_if_missing("fk_requirements_deleted_by", "requirements", "users",
                       ["deleted_by"], ["id"], ondelete="SET NULL")

    # ------------------------------------------------------------------
    # 2c. VersionMixin columns
    # ------------------------------------------------------------------
    for tbl in ["requirements", "test_plans", "test_cases", "automation_scripts"]:
        _add_col_if_missing(tbl, "version", sa.Integer, nullable=False, server_default="1")

    # ------------------------------------------------------------------
    # 2d. updated_by columns
    # ------------------------------------------------------------------
    updated_by_tables = [
        "requirements", "test_plans", "test_scenarios", "test_cases",
        "execution_runs", "defect_drafts", "automation_scripts", "reports",
    ]
    for tbl in updated_by_tables:
        if _add_col_if_missing(tbl, "updated_by", sa.Integer, nullable=True):
            _add_fk_if_missing(f"fk_{tbl}_updated_by", tbl, "users",
                               ["updated_by"], ["id"], ondelete="SET NULL")

    # ------------------------------------------------------------------
    # 3. FK cascade rules
    # ------------------------------------------------------------------
    fk_rules = [
        # (table, local_col, ref_table, ref_col, ondelete)
        ("agent_runs", "project_id", "projects", "id", "CASCADE"),
        ("agent_runs", "triggered_by", "users", "id", "SET NULL"),
        ("agent_logs", "agent_run_id", "agent_runs", "id", "CASCADE"),
        ("agent_logs", "project_id", "projects", "id", "CASCADE"),
        ("project_memberships", "project_id", "projects", "id", "CASCADE"),
        ("project_memberships", "user_id", "users", "id", "CASCADE"),
        ("automation_test_mappings", "project_id", "projects", "id", "CASCADE"),
        ("automation_test_mappings", "test_case_id", "test_cases", "id", "CASCADE"),
        ("approval_actions", "project_id", "projects", "id", "CASCADE"),
        ("approval_actions", "user_id", "users", "id", "SET NULL"),
        ("approval_actions", "agent_run_id", "agent_runs", "id", "SET NULL"),
        ("artifacts", "project_id", "projects", "id", "CASCADE"),
        ("artifacts", "created_by", "users", "id", "SET NULL"),
        ("artifact_lineage", "project_id", "projects", "id", "CASCADE"),
        ("artifact_lineage", "agent_run_id", "agent_runs", "id", "SET NULL"),
        ("uploaded_documents", "project_id", "projects", "id", "CASCADE"),
        ("uploaded_documents", "created_by", "users", "id", "SET NULL"),
        ("project_llm_settings", "created_by", "users", "id", "SET NULL"),
        ("project_llm_settings", "updated_by", "users", "id", "SET NULL"),
        ("project_setting_audit_logs", "changed_by", "users", "id", "SET NULL"),
        ("requirements", "project_id", "projects", "id", "CASCADE"),
        ("requirements", "created_by", "users", "id", "SET NULL"),
        ("requirements", "source_document_id", "uploaded_documents", "id", "SET NULL"),
        ("requirement_chunks", "requirement_id", "requirements", "id", "CASCADE"),
        ("requirement_chunks", "project_id", "projects", "id", "CASCADE"),
        ("requirement_quality_reviews", "requirement_id", "requirements", "id", "CASCADE"),
        ("requirement_quality_reviews", "project_id", "projects", "id", "CASCADE"),
        ("requirement_quality_reviews", "created_by", "users", "id", "SET NULL"),
        ("requirement_quality_reviews", "agent_run_id", "agent_runs", "id", "SET NULL"),
        ("test_plans", "project_id", "projects", "id", "CASCADE"),
        ("test_plans", "created_by", "users", "id", "SET NULL"),
        ("test_plans", "agent_run_id", "agent_runs", "id", "SET NULL"),
        ("test_scenarios", "project_id", "projects", "id", "CASCADE"),
        ("test_scenarios", "requirement_id", "requirements", "id", "SET NULL"),
        ("test_scenarios", "created_by", "users", "id", "SET NULL"),
        ("test_scenarios", "agent_run_id", "agent_runs", "id", "SET NULL"),
        ("test_cases", "project_id", "projects", "id", "CASCADE"),
        ("test_cases", "scenario_id", "test_scenarios", "id", "SET NULL"),
        ("test_cases", "requirement_id", "requirements", "id", "SET NULL"),
        ("test_cases", "created_by", "users", "id", "SET NULL"),
        ("test_cases", "agent_run_id", "agent_runs", "id", "SET NULL"),
        ("test_data", "project_id", "projects", "id", "CASCADE"),
        ("test_data", "test_case_id", "test_cases", "id", "SET NULL"),
        ("test_data", "created_by", "users", "id", "SET NULL"),
        ("test_data", "agent_run_id", "agent_runs", "id", "SET NULL"),
        ("automation_scripts", "project_id", "projects", "id", "CASCADE"),
        ("automation_scripts", "test_case_id", "test_cases", "id", "SET NULL"),
        ("automation_scripts", "created_by", "users", "id", "SET NULL"),
        ("automation_scripts", "agent_run_id", "agent_runs", "id", "SET NULL"),
        ("execution_runs", "project_id", "projects", "id", "CASCADE"),
        ("execution_runs", "created_by", "users", "id", "SET NULL"),
        ("execution_runs", "agent_run_id", "agent_runs", "id", "SET NULL"),
        ("execution_results", "execution_run_id", "execution_runs", "id", "CASCADE"),
        ("execution_results", "test_case_id", "test_cases", "id", "SET NULL"),
        ("execution_results", "project_id", "projects", "id", "CASCADE"),
        ("defect_drafts", "project_id", "projects", "id", "CASCADE"),
        ("defect_drafts", "test_case_id", "test_cases", "id", "SET NULL"),
        ("defect_drafts", "execution_result_id", "execution_results", "id", "SET NULL"),
        ("defect_drafts", "created_by", "users", "id", "SET NULL"),
        ("defect_drafts", "agent_run_id", "agent_runs", "id", "SET NULL"),
        ("jira_defects", "defect_draft_id", "defect_drafts", "id", "CASCADE"),
        ("jira_defects", "project_id", "projects", "id", "CASCADE"),
        ("jira_defects", "created_by", "users", "id", "SET NULL"),
        ("reports", "project_id", "projects", "id", "CASCADE"),
        ("reports", "created_by", "users", "id", "SET NULL"),
        ("reports", "agent_run_id", "agent_runs", "id", "SET NULL"),
        ("jira_connections", "project_id", "projects", "id", "CASCADE"),
        ("jira_connections", "created_by", "users", "id", "SET NULL"),
        ("projects", "owner_id", "users", "id", "RESTRICT"),
    ]
    for table, local_col, ref_table, ref_col, ondelete in fk_rules:
        _replace_fk_sql(table, local_col, ref_table, ref_col, ondelete)

    # ------------------------------------------------------------------
    # 4. Status CHECK constraints (NOT VALID — safe for existing data)
    # ------------------------------------------------------------------
    status_checks = [
        ("requirements",       "ck_requirements_status",       "status IN ('draft','ai_generated','pending_review','approved','rejected','archived')"),
        ("test_plans",         "ck_test_plans_status",         "status IN ('draft','ai_generated','pending_review','approved','rejected','archived')"),
        ("test_scenarios",     "ck_test_scenarios_status",     "status IN ('draft','ai_generated','pending_review','approved','rejected')"),
        ("test_cases",         "ck_test_cases_status",         "status IN ('draft','pending_approval','approved','rejected','automated')"),
        ("execution_runs",     "ck_execution_runs_status",     "status IN ('pending','queued','running','completed','failed','cancelled')"),
        ("execution_results",  "ck_execution_results_status",  "status IN ('pending','pass','fail','skip','error','blocked','not_run','running')"),
        ("defect_drafts",      "ck_defect_drafts_status",      "status IN ('draft','pending_approval','approved','rejected','pushed_to_jira')"),
        ("jira_defects",       "ck_jira_defects_status",       "status IN ('created','synced','closed','reopened')"),
        ("automation_scripts", "ck_automation_scripts_status",  "status IN ('draft','pending_approval','approved','rejected','executed')"),
        ("reports",            "ck_reports_status",             "status IN ('draft','generating','generated','published','archived')"),
        ("uploaded_documents", "ck_uploaded_documents_status",  "status IN ('uploaded','processing','processed','failed')"),
        ("agent_runs",         "ck_agent_runs_status",          "status IN ('pending','running','completed','failed','cancelled')"),
        ("projects",           "ck_projects_status",            "status IN ('active','paused','completed','archived')"),
        ("test_cases",         "ck_test_cases_priority",        "priority IN ('Critical','High','Medium','Low')"),
        ("test_cases",         "ck_test_cases_severity",        "severity IN ('Critical','High','Medium','Low')"),
        ("defect_drafts",      "ck_defect_drafts_severity",     "severity IN ('Critical','High','Medium','Low')"),
        ("defect_drafts",      "ck_defect_drafts_priority",     "priority IN ('Critical','High','Medium','Low')"),
    ]
    for table, name, expr in status_checks:
        if not _constraint_exists(table, name):
            conn.execute(sa.text(
                f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" CHECK ({expr}) NOT VALID'
            ))


# ========================== DOWNGRADE ==========================

def downgrade() -> None:
    conn = op.get_bind()

    # Drop CHECK constraints
    checks = [
        ("requirements", "ck_requirements_status"), ("test_plans", "ck_test_plans_status"),
        ("test_scenarios", "ck_test_scenarios_status"), ("test_cases", "ck_test_cases_status"),
        ("execution_runs", "ck_execution_runs_status"), ("execution_results", "ck_execution_results_status"),
        ("defect_drafts", "ck_defect_drafts_status"), ("jira_defects", "ck_jira_defects_status"),
        ("automation_scripts", "ck_automation_scripts_status"), ("reports", "ck_reports_status"),
        ("uploaded_documents", "ck_uploaded_documents_status"), ("agent_runs", "ck_agent_runs_status"),
        ("projects", "ck_projects_status"),
        ("test_cases", "ck_test_cases_priority"), ("test_cases", "ck_test_cases_severity"),
        ("defect_drafts", "ck_defect_drafts_severity"), ("defect_drafts", "ck_defect_drafts_priority"),
    ]
    for tbl, name in checks:
        if _constraint_exists(tbl, name):
            op.drop_constraint(name, tbl, type_="check")

    # Drop version columns
    for tbl in ["requirements", "test_plans", "test_cases", "automation_scripts"]:
        if _col_exists(tbl, "version"):
            op.drop_column(tbl, "version")

    # Drop updated_by columns
    for tbl in ["requirements", "test_plans", "test_scenarios", "test_cases",
                "execution_runs", "defect_drafts", "automation_scripts", "reports"]:
        if _col_exists(tbl, "updated_by"):
            if _constraint_exists(tbl, f"fk_{tbl}_updated_by"):
                op.drop_constraint(f"fk_{tbl}_updated_by", tbl, type_="foreignkey")
            op.drop_column(tbl, "updated_by")

    # Drop soft-delete columns
    for tbl in ["projects", "test_plans", "test_scenarios", "test_cases",
                "execution_runs", "defect_drafts", "automation_scripts",
                "reports", "uploaded_documents"]:
        if _constraint_exists(tbl, f"fk_{tbl}_deleted_by"):
            op.drop_constraint(f"fk_{tbl}_deleted_by", tbl, type_="foreignkey")
        if _index_exists(f"ix_{tbl}_is_deleted"):
            op.drop_index(f"ix_{tbl}_is_deleted", tbl)
        for col in ["deleted_by", "deleted_at", "is_deleted"]:
            if _col_exists(tbl, col):
                op.drop_column(tbl, col)

    # requirements special case
    if _constraint_exists("requirements", "fk_requirements_deleted_by"):
        op.drop_constraint("fk_requirements_deleted_by", "requirements", type_="foreignkey")
    for col in ["deleted_by", "deleted_at"]:
        if _col_exists("requirements", col):
            op.drop_column("requirements", col)

    # Drop organization FKs and columns
    if _constraint_exists("projects", "fk_projects_organization_id"):
        op.drop_constraint("fk_projects_organization_id", "projects", type_="foreignkey")
    if _col_exists("projects", "organization_id"):
        op.drop_column("projects", "organization_id")
    if _constraint_exists("users", "fk_users_organization_id"):
        op.drop_constraint("fk_users_organization_id", "users", type_="foreignkey")
    if _col_exists("users", "organization_id"):
        op.drop_column("users", "organization_id")

    if _table_exists("organizations"):
        op.drop_table("organizations")
