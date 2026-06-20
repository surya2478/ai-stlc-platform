"""Add project-scoped uniqueness for artifact display IDs.

Revision ID: 002_project_scoped_artifact_ids
Revises: 001
Create Date: 2026-06-10
"""
from alembic import op


revision = "002_project_scoped_artifact_ids"
down_revision = "001"
branch_labels = None
depends_on = None


CONSTRAINTS = [
    ("requirements", "uq_requirements_project_requirement_id", ["project_id", "requirement_id"]),
    ("test_plans", "uq_test_plans_project_test_plan_id", ["project_id", "test_plan_id"]),
    ("test_scenarios", "uq_test_scenarios_project_scenario_id", ["project_id", "scenario_id"]),
    ("test_cases", "uq_test_cases_project_test_case_id", ["project_id", "test_case_id"]),
    ("automation_scripts", "uq_automation_scripts_project_script_id", ["project_id", "script_id"]),
    ("execution_runs", "uq_execution_runs_project_execution_id", ["project_id", "execution_id"]),
    ("defect_drafts", "uq_defect_drafts_project_defect_id", ["project_id", "defect_id"]),
    ("reports", "uq_reports_project_report_id", ["project_id", "report_id"]),
]


def upgrade() -> None:
    for table_name, constraint_name, columns in CONSTRAINTS:
        op.create_unique_constraint(constraint_name, table_name, columns)


def downgrade() -> None:
    for table_name, constraint_name, _columns in reversed(CONSTRAINTS):
        op.drop_constraint(constraint_name, table_name, type_="unique")
