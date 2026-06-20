"""test case operational metadata and history

Revision ID: 008_test_case_metadata_history
Revises: 007_external_automation_control
Create Date: 2026-06-11 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_test_case_metadata_history"
down_revision: Union[str, None] = "007_external_automation_control"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("test_cases", sa.Column("automation_ready", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("test_cases", sa.Column("test_phase", sa.String(length=80), nullable=True))
    op.add_column("test_cases", sa.Column("telecom_domain", sa.String(length=80), nullable=True))
    op.add_column("test_cases", sa.Column("external_tool", sa.String(length=100), nullable=True))
    op.add_column("test_cases", sa.Column("suite_id", sa.String(length=255), nullable=True))
    op.add_column("test_cases", sa.Column("external_tc_id", sa.String(length=255), nullable=True))
    op.add_column("test_cases", sa.Column("external_tc_url", sa.Text(), nullable=True))
    op.add_column("test_cases", sa.Column("automation_script_id", sa.Integer(), nullable=True))
    op.add_column("test_cases", sa.Column("last_automation_status", sa.String(length=50), nullable=True))
    op.add_column("test_cases", sa.Column("last_automation_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("test_cases", sa.Column("last_execution_run_id", sa.Integer(), nullable=True))
    op.add_column("test_cases", sa.Column("latest_evidence_available", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("test_cases", sa.Column("evidence_url", sa.Text(), nullable=True))
    op.add_column("test_cases", sa.Column("jira_issue_id", sa.String(length=100), nullable=True))
    op.add_column("test_cases", sa.Column("jira_url", sa.Text(), nullable=True))
    op.add_column("test_cases", sa.Column("jira_final_status", sa.String(length=50), nullable=True))
    op.add_column("test_cases", sa.Column("jira_sync_status", sa.String(length=50), nullable=False, server_default="not_synced"))
    op.add_column("test_cases", sa.Column("jira_last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("test_cases", sa.Column("jira_sync_error", sa.Text(), nullable=True))
    op.add_column("test_cases", sa.Column("linked_release_version", sa.String(length=100), nullable=True))
    op.add_column("test_cases", sa.Column("linked_test_plan_id", sa.Integer(), nullable=True))
    op.add_column("test_cases", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.add_column("test_cases", sa.Column("last_status_updated_by", sa.Integer(), nullable=True))
    op.add_column("test_cases", sa.Column("last_status_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_test_cases_jira_issue_id", "test_cases", ["jira_issue_id"])
    op.create_foreign_key("fk_test_cases_automation_script_id", "test_cases", "automation_scripts", ["automation_script_id"], ["id"])
    op.create_foreign_key("fk_test_cases_last_execution_run_id", "test_cases", "execution_runs", ["last_execution_run_id"], ["id"])
    op.create_foreign_key("fk_test_cases_linked_test_plan_id", "test_cases", "test_plans", ["linked_test_plan_id"], ["id"])
    op.create_foreign_key("fk_test_cases_updated_by", "test_cases", "users", ["updated_by"], ["id"])
    op.create_foreign_key("fk_test_cases_last_status_updated_by", "test_cases", "users", ["last_status_updated_by"], ["id"])

    op.execute("UPDATE test_cases SET execution_mode = 'manual' WHERE execution_mode IN ('not_applicable', '')")
    op.execute("UPDATE test_cases SET automation_eligible = 'no' WHERE automation_eligible IN ('under_review', '')")
    op.execute("UPDATE test_cases SET automation_status = 'not_required' WHERE automation_status IN ('not_automated', 'deprecated', '')")
    op.execute("UPDATE test_cases SET automation_status = 'ready_for_automation' WHERE automation_status = 'automation_candidate'")
    op.execute("UPDATE test_cases SET automation_status = 'maintenance_required' WHERE automation_status = 'broken'")
    op.execute("UPDATE automation_test_mappings SET automation_status = 'ready_for_automation' WHERE automation_status = 'automation_candidate'")
    op.execute("UPDATE automation_test_mappings SET automation_status = 'not_required' WHERE automation_status IN ('not_automated', 'deprecated')")
    op.execute("UPDATE automation_test_mappings SET automation_status = 'maintenance_required' WHERE automation_status = 'broken'")

    op.create_table(
        "test_case_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("test_case_id", sa.Integer(), nullable=False),
        sa.Column("changed_by", sa.Integer(), nullable=True),
        sa.Column("field_name", sa.String(length=100), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="platform"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_case_history_id", "test_case_history", ["id"])
    op.create_index("ix_test_case_history_project_id", "test_case_history", ["project_id"])
    op.create_index("ix_test_case_history_test_case_id", "test_case_history", ["test_case_id"])
    op.create_index("ix_test_case_history_field_name", "test_case_history", ["field_name"])


def downgrade() -> None:
    op.drop_index("ix_test_case_history_field_name", table_name="test_case_history")
    op.drop_index("ix_test_case_history_test_case_id", table_name="test_case_history")
    op.drop_index("ix_test_case_history_project_id", table_name="test_case_history")
    op.drop_index("ix_test_case_history_id", table_name="test_case_history")
    op.drop_table("test_case_history")
    op.drop_constraint("fk_test_cases_last_status_updated_by", "test_cases", type_="foreignkey")
    op.drop_constraint("fk_test_cases_updated_by", "test_cases", type_="foreignkey")
    op.drop_constraint("fk_test_cases_linked_test_plan_id", "test_cases", type_="foreignkey")
    op.drop_constraint("fk_test_cases_last_execution_run_id", "test_cases", type_="foreignkey")
    op.drop_constraint("fk_test_cases_automation_script_id", "test_cases", type_="foreignkey")
    op.drop_index("ix_test_cases_jira_issue_id", table_name="test_cases")
    for column in (
        "last_status_updated_at",
        "last_status_updated_by",
        "updated_by",
        "linked_test_plan_id",
        "linked_release_version",
        "jira_sync_error",
        "jira_last_synced_at",
        "jira_sync_status",
        "jira_final_status",
        "jira_url",
        "jira_issue_id",
        "evidence_url",
        "latest_evidence_available",
        "last_execution_run_id",
        "last_automation_run_at",
        "last_automation_status",
        "automation_script_id",
        "external_tc_url",
        "external_tc_id",
        "suite_id",
        "external_tool",
        "telecom_domain",
        "test_phase",
        "automation_ready",
    ):
        op.drop_column("test_cases", column)
