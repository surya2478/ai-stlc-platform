"""Add external automation control center foundation.

Revision ID: 007_external_automation_control
Revises: 006_async_agent_workflow
Create Date: 2026-06-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "007_external_automation_control"
down_revision: Union[str, None] = "006_async_agent_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("test_cases", sa.Column("execution_mode", sa.String(50), nullable=False, server_default="not_applicable"))
    op.add_column("test_cases", sa.Column("automation_eligible", sa.String(50), nullable=False, server_default="under_review"))
    op.add_column("test_cases", sa.Column("automation_status", sa.String(50), nullable=False, server_default="not_automated"))
    op.add_column("test_cases", sa.Column("jira_issue_key", sa.String(100), nullable=True))
    op.add_column("test_cases", sa.Column("jira_test_key", sa.String(100), nullable=True))
    op.create_index("ix_test_cases_jira_issue_key", "test_cases", ["jira_issue_key"])
    op.create_index("ix_test_cases_jira_test_key", "test_cases", ["jira_test_key"])
    op.execute(
        """
        UPDATE test_cases
        SET execution_mode = CASE WHEN automation_candidate THEN 'automated' ELSE 'manual' END,
            automation_eligible = CASE WHEN automation_candidate THEN 'yes' ELSE 'under_review' END,
            automation_status = CASE WHEN automation_candidate THEN 'automation_candidate' ELSE 'not_automated' END
        """
    )

    op.create_table(
        "automation_test_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("test_case_id", sa.Integer(), nullable=False),
        sa.Column("external_tool_name", sa.String(100), nullable=False),
        sa.Column("external_project_id", sa.String(255), nullable=True),
        sa.Column("external_suite_id", sa.String(255), nullable=True),
        sa.Column("external_test_case_id", sa.String(255), nullable=False),
        sa.Column("external_script_id", sa.String(255), nullable=True),
        sa.Column("automation_status", sa.String(50), nullable=False, server_default="automation_candidate"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "external_tool_name", "external_test_case_id", name="uq_auto_mapping_project_tool_external_tc"),
    )
    op.create_index("ix_automation_test_mappings_id", "automation_test_mappings", ["id"])
    op.create_index("ix_automation_test_mappings_project_id", "automation_test_mappings", ["project_id"])
    op.create_index("ix_automation_test_mappings_test_case_id", "automation_test_mappings", ["test_case_id"])

    op.add_column("execution_runs", sa.Column("test_cycle_id", sa.String(100), nullable=True))
    op.add_column("execution_runs", sa.Column("source_type", sa.String(50), nullable=False, server_default="manual"))
    op.add_column("execution_runs", sa.Column("external_tool_name", sa.String(100), nullable=True))
    op.add_column("execution_runs", sa.Column("external_run_id", sa.String(255), nullable=True))
    op.add_column("execution_runs", sa.Column("triggered_by", sa.Integer(), nullable=True))
    op.add_column("execution_runs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("execution_runs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("execution_runs", sa.Column("duration_seconds", sa.Float(), nullable=True))
    op.create_index("ix_execution_runs_test_cycle_id", "execution_runs", ["test_cycle_id"])
    op.create_index("ix_execution_runs_external_run_id", "execution_runs", ["external_run_id"])
    op.create_foreign_key("fk_execution_runs_triggered_by_users", "execution_runs", "users", ["triggered_by"], ["id"])

    op.add_column("execution_results", sa.Column("automation_mapping_id", sa.Integer(), nullable=True))
    op.add_column("execution_results", sa.Column("execution_mode", sa.String(50), nullable=True))
    op.add_column("execution_results", sa.Column("external_tool_name", sa.String(100), nullable=True))
    op.add_column("execution_results", sa.Column("external_test_case_id", sa.String(255), nullable=True))
    op.add_column("execution_results", sa.Column("automation_execution_status", sa.String(50), nullable=True))
    op.add_column("execution_results", sa.Column("manual_execution_status", sa.String(50), nullable=True))
    op.add_column("execution_results", sa.Column("jira_execution_status", sa.String(50), nullable=True))
    op.add_column("execution_results", sa.Column("duration_seconds", sa.Float(), nullable=True))
    op.add_column("execution_results", sa.Column("screenshot_url", sa.Text(), nullable=True))
    op.add_column("execution_results", sa.Column("video_url", sa.Text(), nullable=True))
    op.add_column("execution_results", sa.Column("log_url", sa.Text(), nullable=True))
    op.add_column("execution_results", sa.Column("external_result_url", sa.Text(), nullable=True))
    op.add_column("execution_results", sa.Column("jira_issue_key", sa.String(100), nullable=True))
    op.add_column("execution_results", sa.Column("jira_test_key", sa.String(100), nullable=True))
    op.add_column("execution_results", sa.Column("raw_result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index("ix_execution_results_automation_mapping_id", "execution_results", ["automation_mapping_id"])
    op.create_index("ix_execution_results_jira_issue_key", "execution_results", ["jira_issue_key"])
    op.create_index("ix_execution_results_jira_test_key", "execution_results", ["jira_test_key"])
    op.create_foreign_key(
        "fk_execution_results_automation_mapping",
        "execution_results",
        "automation_test_mappings",
        ["automation_mapping_id"],
        ["id"],
    )
    op.execute(
        """
        UPDATE execution_results
        SET automation_execution_status = status,
            duration_seconds = CASE WHEN duration_ms IS NULL THEN NULL ELSE duration_ms / 1000.0 END
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_execution_results_automation_mapping", "execution_results", type_="foreignkey")
    op.drop_index("ix_execution_results_jira_test_key", table_name="execution_results")
    op.drop_index("ix_execution_results_jira_issue_key", table_name="execution_results")
    op.drop_index("ix_execution_results_automation_mapping_id", table_name="execution_results")
    for column in (
        "raw_result_json",
        "jira_test_key",
        "jira_issue_key",
        "external_result_url",
        "log_url",
        "video_url",
        "screenshot_url",
        "duration_seconds",
        "jira_execution_status",
        "manual_execution_status",
        "automation_execution_status",
        "external_test_case_id",
        "external_tool_name",
        "execution_mode",
        "automation_mapping_id",
    ):
        op.drop_column("execution_results", column)

    op.drop_constraint("fk_execution_runs_triggered_by_users", "execution_runs", type_="foreignkey")
    op.drop_index("ix_execution_runs_external_run_id", table_name="execution_runs")
    op.drop_index("ix_execution_runs_test_cycle_id", table_name="execution_runs")
    for column in ("duration_seconds", "completed_at", "started_at", "triggered_by", "external_run_id", "external_tool_name", "source_type", "test_cycle_id"):
        op.drop_column("execution_runs", column)

    op.drop_index("ix_automation_test_mappings_test_case_id", table_name="automation_test_mappings")
    op.drop_index("ix_automation_test_mappings_project_id", table_name="automation_test_mappings")
    op.drop_index("ix_automation_test_mappings_id", table_name="automation_test_mappings")
    op.drop_table("automation_test_mappings")

    op.drop_index("ix_test_cases_jira_test_key", table_name="test_cases")
    op.drop_index("ix_test_cases_jira_issue_key", table_name="test_cases")
    for column in ("jira_test_key", "jira_issue_key", "automation_status", "automation_eligible", "execution_mode"):
        op.drop_column("test_cases", column)
