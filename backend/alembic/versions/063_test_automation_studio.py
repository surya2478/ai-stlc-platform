"""063 - Test Automation Studio (separate module)

Creates the six tas_* tables that back the Test Automation Studio's three
screens. Purely additive: no existing table is altered, so downgrading drops
the new tables and leaves the rest of the schema exactly as it was.

Revision ID: 063
Revises: 062
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tas_intake_batches",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("project_applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("application_url", sa.Text(), nullable=True),
        sa.Column("application_environment", sa.String(length=50), nullable=False, server_default="qa"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("status_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft','assessing','assessed','failed')",
            name="ck_tas_intake_batch_status",
        ),
    )
    op.create_index("ix_tas_intake_batches_project_id", "tas_intake_batches", ["project_id"])
    op.create_index("ix_tas_intake_batches_status", "tas_intake_batches", ["status"])

    op.create_table(
        "tas_intake_documents",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "batch_id", sa.Integer(), sa.ForeignKey("tas_intake_batches.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("uploaded_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("doc_role", sa.String(length=30), nullable=False, server_default="other"),
        sa.Column("extraction_status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column("extracted_requirement_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extracted_test_case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("batch_id", "document_id", name="uq_tas_intake_batch_document"),
        sa.CheckConstraint(
            "doc_role IN ('brd','srd','test_cases','other')", name="ck_tas_intake_document_role"
        ),
        sa.CheckConstraint(
            "extraction_status IN ('pending','extracted','failed')",
            name="ck_tas_intake_document_extraction_status",
        ),
    )
    op.create_index("ix_tas_intake_documents_batch_id", "tas_intake_documents", ["batch_id"])
    op.create_index("ix_tas_intake_documents_document_id", "tas_intake_documents", ["document_id"])
    op.create_index("ix_tas_intake_documents_doc_role", "tas_intake_documents", ["doc_role"])

    op.create_table(
        "tas_coverage_assessments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "batch_id", sa.Integer(), sa.ForeignKey("tas_intake_batches.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="running"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("total_requirements", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("covered_requirements", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partially_covered_requirements", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uncovered_requirements", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("existing_test_case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("derived_requirement_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage_rows", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("extracted_test_cases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("gap_summary", postgresql.JSONB(), nullable=False, server_default="{}"),
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
            "status IN ('running','completed','failed')", name="ck_tas_coverage_assessment_status"
        ),
    )
    op.create_index("ix_tas_coverage_assessments_project_id", "tas_coverage_assessments", ["project_id"])
    op.create_index("ix_tas_coverage_assessments_batch_id", "tas_coverage_assessments", ["batch_id"])
    op.create_index("ix_tas_coverage_assessments_is_current", "tas_coverage_assessments", ["is_current"])
    op.create_index("ix_tas_coverage_assessments_status", "tas_coverage_assessments", ["status"])

    op.create_table(
        "tas_derived_requirements",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "batch_id", sa.Integer(), sa.ForeignKey("tas_intake_batches.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "assessment_id",
            sa.Integer(),
            sa.ForeignKey("tas_coverage_assessments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("requirement_key", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("acceptance_criteria", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("business_rules", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("ui_pages", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("apis", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("test_data_needs", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("origin", sa.String(length=20), nullable=False, server_default="extracted"),
        sa.Column("coverage_state", sa.String(length=30), nullable=False, server_default="uncovered"),
        sa.Column("gap_reason", sa.Text(), nullable=True),
        sa.Column("source_refs", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("covering_test_case_refs", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("automation_relevance", sa.String(length=20), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="Medium"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending_approval"),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "promoted_requirement_id",
            sa.Integer(),
            sa.ForeignKey("requirements.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("batch_id", "requirement_key", name="uq_tas_derived_requirement_key"),
        sa.CheckConstraint("origin IN ('extracted','derived')", name="ck_tas_derived_requirement_origin"),
        sa.CheckConstraint(
            "coverage_state IN ('covered','partially_covered','uncovered')",
            name="ck_tas_derived_requirement_coverage_state",
        ),
        sa.CheckConstraint(
            "status IN ('draft','pending_approval','approved','rejected')",
            name="ck_tas_derived_requirement_status",
        ),
    )
    op.create_index("ix_tas_derived_requirements_project_id", "tas_derived_requirements", ["project_id"])
    op.create_index("ix_tas_derived_requirements_batch_id", "tas_derived_requirements", ["batch_id"])
    op.create_index("ix_tas_derived_requirements_assessment_id", "tas_derived_requirements", ["assessment_id"])
    op.create_index("ix_tas_derived_requirements_requirement_key", "tas_derived_requirements", ["requirement_key"])
    op.create_index("ix_tas_derived_requirements_status", "tas_derived_requirements", ["status"])
    op.create_index("ix_tas_derived_requirements_origin", "tas_derived_requirements", ["origin"])
    op.create_index("ix_tas_derived_requirements_coverage_state", "tas_derived_requirements", ["coverage_state"])
    op.create_index(
        "ix_tas_derived_requirements_promoted", "tas_derived_requirements", ["promoted_requirement_id"]
    )

    op.create_table(
        "tas_refined_test_cases",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "batch_id", sa.Integer(), sa.ForeignKey("tas_intake_batches.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "derived_requirement_id",
            sa.Integer(),
            sa.ForeignKey("tas_derived_requirements.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_test_case_id",
            sa.Integer(),
            sa.ForeignKey("test_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("origin", sa.String(length=20), nullable=False, server_default="derived"),
        sa.Column("tc_display_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("preconditions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("steps", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("expected_result", sa.Text(), nullable=True),
        sa.Column("bdd_scenario", sa.Text(), nullable=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("project_applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("application_url", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="Medium"),
        sa.Column("test_type", sa.String(length=100), nullable=True),
        sa.Column("classification", sa.String(length=20), nullable=False, server_default="undecided"),
        sa.Column("classification_source", sa.String(length=20), nullable=True),
        sa.Column("classification_reason", sa.Text(), nullable=True),
        sa.Column("manual_only_reasons", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("test_data_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("test_data_status", sa.String(length=30), nullable=False, server_default="not_required"),
        sa.Column("test_data_notes", sa.Text(), nullable=True),
        sa.Column("test_data_requirements", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("test_data_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("edited_by_user", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "tc_display_id", "version", name="uq_tas_refined_tc_version"),
        sa.CheckConstraint("origin IN ('existing','derived')", name="ck_tas_refined_tc_origin"),
        sa.CheckConstraint(
            "classification IN ('automation','manual','undecided')", name="ck_tas_refined_tc_classification"
        ),
        sa.CheckConstraint(
            "classification_source IS NULL OR classification_source IN ('policy','agent','manual')",
            name="ck_tas_refined_tc_classification_source",
        ),
        sa.CheckConstraint(
            "test_data_status IN ('not_required','agent_provided','needs_user_action','user_provided')",
            name="ck_tas_refined_tc_test_data_status",
        ),
        sa.CheckConstraint(
            "status IN ('draft','pending_approval','approved','rejected')", name="ck_tas_refined_tc_status"
        ),
    )
    op.create_index("ix_tas_refined_test_cases_project_id", "tas_refined_test_cases", ["project_id"])
    op.create_index("ix_tas_refined_test_cases_batch_id", "tas_refined_test_cases", ["batch_id"])
    op.create_index(
        "ix_tas_refined_test_cases_derived_requirement_id", "tas_refined_test_cases", ["derived_requirement_id"]
    )
    op.create_index(
        "ix_tas_refined_test_cases_source_test_case_id", "tas_refined_test_cases", ["source_test_case_id"]
    )
    op.create_index("ix_tas_refined_test_cases_tc_display_id", "tas_refined_test_cases", ["tc_display_id"])
    op.create_index("ix_tas_refined_test_cases_status", "tas_refined_test_cases", ["status"])
    op.create_index("ix_tas_refined_test_cases_classification", "tas_refined_test_cases", ["classification"])
    op.create_index("ix_tas_refined_test_cases_is_current", "tas_refined_test_cases", ["is_current"])
    op.create_index("ix_tas_refined_test_cases_origin", "tas_refined_test_cases", ["origin"])
    op.create_index(
        "ix_tas_refined_test_cases_test_data_required", "tas_refined_test_cases", ["test_data_required"]
    )
    op.create_index("ix_tas_refined_test_cases_test_data_status", "tas_refined_test_cases", ["test_data_status"])

    op.create_table(
        "tas_script_assets",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "refined_test_case_id",
            sa.Integer(),
            sa.ForeignKey("tas_refined_test_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("framework", sa.String(length=30), nullable=False),
        sa.Column("language", sa.String(length=30), nullable=False, server_default="typescript"),
        sa.Column("script_key", sa.String(length=150), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("files", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("execution_command", sa.Text(), nullable=True),
        sa.Column("setup_notes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("edited_by_user", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("generation_error", sa.Text(), nullable=True),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "refined_test_case_id", "framework", "version", name="uq_tas_script_asset_version"
        ),
        sa.CheckConstraint(
            "framework IN ('playwright','katalon','appium')", name="ck_tas_script_asset_framework"
        ),
        sa.CheckConstraint(
            "status IN ('draft','edited','approved')", name="ck_tas_script_asset_status"
        ),
    )
    op.create_index("ix_tas_script_assets_project_id", "tas_script_assets", ["project_id"])
    op.create_index("ix_tas_script_assets_refined_test_case_id", "tas_script_assets", ["refined_test_case_id"])
    op.create_index("ix_tas_script_assets_framework", "tas_script_assets", ["framework"])
    op.create_index("ix_tas_script_assets_script_key", "tas_script_assets", ["script_key"])
    op.create_index("ix_tas_script_assets_status", "tas_script_assets", ["status"])
    op.create_index("ix_tas_script_assets_is_current", "tas_script_assets", ["is_current"])


def downgrade() -> None:
    op.drop_table("tas_script_assets")
    op.drop_table("tas_refined_test_cases")
    op.drop_table("tas_derived_requirements")
    op.drop_table("tas_coverage_assessments")
    op.drop_table("tas_intake_documents")
    op.drop_table("tas_intake_batches")
