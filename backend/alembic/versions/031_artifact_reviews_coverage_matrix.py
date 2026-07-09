"""031 - artifact_reviews, coverage_matrix, and project review_mode

Phase 1 of the agentic automation initiative (see
AGENTIC_AUTOMATION_IMPLEMENTATION_PLAN.md at the repo root): the review &
coverage backbone that stage reviewer agents (scenario_review,
test_case_review, and the upgraded requirement_quality) write to.

- artifact_reviews: generic senior-reviewer output, polymorphic
  (artifact_type, artifact_id) reference — same convention as
  artifact_lineage.
- coverage_matrix: Requirement -> Scenario -> Test Case -> Script ->
  Execution -> Defect rollup, one row per test case.
- projects.review_mode: off | advisory | gating — governs whether a
  fail-verdict review blocks approval.

Revision ID: 031
Revises: 030
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifact_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("agent_run_id", sa.Integer(), nullable=True),
        sa.Column("artifact_type", sa.String(length=100), nullable=False),
        sa.Column("artifact_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_agent", sa.String(length=100), nullable=False),
        sa.Column("scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("verdict", sa.String(length=20), nullable=False, server_default="needs_revision"),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("coverage_gaps", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("review_mode", sa.String(length=20), nullable=False, server_default="advisory"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("verdict IN ('pass','needs_revision','fail')", name="ck_artifact_reviews_verdict"),
        sa.CheckConstraint("review_mode IN ('off','advisory','gating')", name="ck_artifact_reviews_review_mode"),
    )
    op.create_index("ix_artifact_reviews_project_id", "artifact_reviews", ["project_id"])
    op.create_index("ix_artifact_reviews_agent_run_id", "artifact_reviews", ["agent_run_id"])
    op.create_index("ix_artifact_reviews_artifact_type", "artifact_reviews", ["artifact_type"])
    op.create_index("ix_artifact_reviews_artifact_id", "artifact_reviews", ["artifact_id"])
    op.create_index(
        "ix_artifact_reviews_type_id", "artifact_reviews", ["artifact_type", "artifact_id"]
    )

    op.create_table(
        "coverage_matrix",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("requirement_id", sa.Integer(), nullable=True),
        sa.Column("scenario_id", sa.Integer(), nullable=True),
        sa.Column("test_case_id", sa.Integer(), nullable=True),
        sa.Column("script_id", sa.Integer(), nullable=True),
        sa.Column("execution_result_id", sa.Integer(), nullable=True),
        sa.Column("defect_id", sa.Integer(), nullable=True),
        sa.Column("test_type", sa.String(length=100), nullable=True),
        sa.Column("risk_level", sa.String(length=20), nullable=True),
        sa.Column("case_class", sa.String(length=20), nullable=True),
        sa.Column("automation_eligible", sa.String(length=20), nullable=True),
        sa.Column("automation_reason", sa.Text(), nullable=True),
        sa.Column("execution_status", sa.String(length=50), nullable=True),
        sa.Column("defect_linked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requirement_id"], ["requirements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scenario_id"], ["test_scenarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["script_id"], ["automation_scripts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["execution_result_id"], ["execution_results.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["defect_id"], ["defect_drafts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("test_case_id", name="uq_coverage_matrix_test_case_id"),
    )
    op.create_index("ix_coverage_matrix_project_id", "coverage_matrix", ["project_id"])
    op.create_index("ix_coverage_matrix_requirement_id", "coverage_matrix", ["requirement_id"])
    op.create_index("ix_coverage_matrix_scenario_id", "coverage_matrix", ["scenario_id"])
    op.create_index("ix_coverage_matrix_script_id", "coverage_matrix", ["script_id"])
    op.create_index("ix_coverage_matrix_execution_result_id", "coverage_matrix", ["execution_result_id"])
    op.create_index("ix_coverage_matrix_defect_id", "coverage_matrix", ["defect_id"])

    op.add_column(
        "projects",
        sa.Column("review_mode", sa.String(length=20), nullable=False, server_default="advisory"),
    )
    op.create_check_constraint(
        "ck_projects_review_mode", "projects", "review_mode IN ('off','advisory','gating')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_projects_review_mode", "projects", type_="check")
    op.drop_column("projects", "review_mode")

    op.drop_index("ix_coverage_matrix_defect_id", table_name="coverage_matrix")
    op.drop_index("ix_coverage_matrix_execution_result_id", table_name="coverage_matrix")
    op.drop_index("ix_coverage_matrix_script_id", table_name="coverage_matrix")
    op.drop_index("ix_coverage_matrix_scenario_id", table_name="coverage_matrix")
    op.drop_index("ix_coverage_matrix_requirement_id", table_name="coverage_matrix")
    op.drop_index("ix_coverage_matrix_project_id", table_name="coverage_matrix")
    op.drop_table("coverage_matrix")

    op.drop_index("ix_artifact_reviews_type_id", table_name="artifact_reviews")
    op.drop_index("ix_artifact_reviews_artifact_id", table_name="artifact_reviews")
    op.drop_index("ix_artifact_reviews_artifact_type", table_name="artifact_reviews")
    op.drop_index("ix_artifact_reviews_agent_run_id", table_name="artifact_reviews")
    op.drop_index("ix_artifact_reviews_project_id", table_name="artifact_reviews")
    op.drop_table("artifact_reviews")
