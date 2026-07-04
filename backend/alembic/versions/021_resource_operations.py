"""021 - Resource Intelligence & Utilization Hub Tables

Revision ID: 021
Revises: 020
Create Date: 2026-06-27

Fully idempotent migration — safe to re-run after partial failures.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. resources
    op.create_table(
        "resources",
        sa.Column("person_id", UUID(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("ldap_username", sa.String(length=100), nullable=False),
        sa.Column("domain", sa.String(length=100), nullable=False),
        sa.Column("directory_object_id", sa.String(length=255), nullable=True),
        sa.Column("user_principal_name", sa.String(length=255), nullable=True),
        sa.Column("corporate_email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("employee_id", sa.String(length=50), nullable=True),
        sa.Column("department", sa.String(length=150), nullable=True),
        sa.Column("team", sa.String(length=150), nullable=True),
        sa.Column("manager_ldap_username", sa.String(length=100), nullable=True),
        sa.Column("employment_type", sa.String(length=50), nullable=False, server_default="Internal"),
        sa.Column("seniority", sa.String(length=50), nullable=True),
        sa.Column("qa_domain", sa.String(length=100), nullable=True),
        sa.Column("product_group", sa.String(length=100), nullable=True),
        sa.Column("product", sa.String(length=100), nullable=True),
        sa.Column("system", sa.String(length=100), nullable=True),
        sa.Column("skills", JSONB(), nullable=True),
        sa.Column("work_location", sa.String(length=100), nullable=True),
        sa.Column("time_zone", sa.String(length=50), nullable=False, server_default="UTC"),
        sa.Column("standard_work_hours", sa.Float(), nullable=False, server_default="8.0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("last_directory_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("consent_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_telemetry_status", sa.String(length=30), nullable=False, server_default="disabled"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("person_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("ldap_username"),
        sa.UniqueConstraint("directory_object_id")
    )
    op.create_index("ix_resources_person_id", "resources", ["person_id"])
    op.create_index("ix_resources_user_id", "resources", ["user_id"])
    op.create_index("ix_resources_ldap_username", "resources", ["ldap_username"])
    op.create_index("ix_resources_corporate_email", "resources", ["corporate_email"])

    # 2. resource_identity_mappings
    op.create_table(
        "resource_identity_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("external_user_id", sa.String(length=255), nullable=False),
        sa.Column("external_username", sa.String(length=255), nullable=True),
        sa.Column("external_email", sa.String(length=255), nullable=True),
        sa.Column("external_display_name", sa.String(length=255), nullable=True),
        sa.Column("external_project_context", sa.String(length=255), nullable=True),
        sa.Column("mapping_confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("mapping_method", sa.String(length=50), nullable=False, server_default="auto_sync"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="approved"),
        sa.Column("last_verified_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("audit_trail", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.person_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL")
    )
    op.create_index("ix_resource_identity_mappings_id", "resource_identity_mappings", ["id"])
    op.create_index("ix_resource_identity_mappings_resource_id", "resource_identity_mappings", ["resource_id"])
    op.create_index("ix_resource_identity_mappings_source_system", "resource_identity_mappings", ["source_system"])
    op.create_index("ix_resource_identity_mappings_external_user_id", "resource_identity_mappings", ["external_user_id"])

    # 3. integration_connections
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("system_type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("auth_type", sa.String(length=50), nullable=False, server_default="credentials"),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("token_encrypted", sa.Text(), nullable=True),
        sa.Column("config", JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="disconnected"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"])
    )
    op.create_index("ix_integration_connections_id", "integration_connections", ["id"])
    op.create_index("ix_integration_connections_project_id", "integration_connections", ["project_id"])
    op.create_index("ix_integration_connections_system_type", "integration_connections", ["system_type"])

    # 4. daily_work_plans
    op.create_table(
        "daily_work_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("product", sa.String(length=100), nullable=True),
        sa.Column("system", sa.String(length=100), nullable=True),
        sa.Column("qa_domain", sa.String(length=100), nullable=True),
        sa.Column("sprint", sa.String(length=100), nullable=True),
        sa.Column("release", sa.String(length=100), nullable=True),
        sa.Column("test_cycle", sa.String(length=100), nullable=True),
        sa.Column("task_id", sa.String(length=100), nullable=True),
        sa.Column("task_title", sa.String(length=255), nullable=False),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column("linked_jira_issue", sa.String(length=50), nullable=True),
        sa.Column("linked_rtc_work_item", sa.String(length=50), nullable=True),
        sa.Column("linked_rqm_test_artifact", sa.String(length=50), nullable=True),
        sa.Column("linked_nxtqa_entity_id", sa.String(length=100), nullable=True),
        sa.Column("linked_portal_ref", sa.String(length=255), nullable=True),
        sa.Column("planned_start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_effort", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("achieved_effort", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("remaining_effort", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("blocked_effort", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("unplanned_effort", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("priority", sa.String(length=30), nullable=False, server_default="Medium"),
        sa.Column("planned_deliverable", sa.String(length=255), nullable=True),
        sa.Column("dependency", sa.String(length=255), nullable=True),
        sa.Column("risk", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="Planned"),
        sa.Column("blocker_reason", sa.Text(), nullable=True),
        sa.Column("employee_comments", sa.Text(), nullable=True),
        sa.Column("lead_validation", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("manager_validation", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.person_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE")
    )
    op.create_index("ix_daily_work_plans_id", "daily_work_plans", ["id"])
    op.create_index("ix_daily_work_plans_date", "daily_work_plans", ["date"])
    op.create_index("ix_daily_work_plans_resource_id", "daily_work_plans", ["resource_id"])
    op.create_index("ix_daily_work_plans_project_id", "daily_work_plans", ["project_id"])

    # 5. work_evidence_events
    op.create_table(
        "work_evidence_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("source_event_id", sa.String(length=255), nullable=False),
        sa.Column("source_user_id", sa.String(length=255), nullable=True),
        sa.Column("source_username", sa.String(length=100), nullable=True),
        sa.Column("event_category", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_effort_hours", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("linked_task_id", sa.Integer(), nullable=True),
        sa.Column("linked_jira_issue_key", sa.String(length=50), nullable=True),
        sa.Column("linked_rtc_work_item_id", sa.String(length=50), nullable=True),
        sa.Column("linked_rqm_artifact_id", sa.String(length=100), nullable=True),
        sa.Column("linked_nxtqa_entity_id", sa.String(length=100), nullable=True),
        sa.Column("linked_portal_ref", sa.String(length=255), nullable=True),
        sa.Column("project", sa.String(length=100), nullable=True),
        sa.Column("product", sa.String(length=100), nullable=True),
        sa.Column("system", sa.String(length=100), nullable=True),
        sa.Column("qa_domain", sa.String(length=100), nullable=True),
        sa.Column("sprint", sa.String(length=100), nullable=True),
        sa.Column("release", sa.String(length=100), nullable=True),
        sa.Column("test_cycle", sa.String(length=100), nullable=True),
        sa.Column("evidence_confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("evidence_status", sa.String(length=30), nullable=False, server_default="unmapped"),
        sa.Column("privacy_classification", sa.String(length=50), nullable=False, server_default="Public"),
        sa.Column("raw_source_metadata", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.person_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_task_id"], ["daily_work_plans.id"], ondelete="SET NULL")
    )
    op.create_index("ix_work_evidence_events_id", "work_evidence_events", ["id"])
    op.create_index("ix_work_evidence_events_project_id", "work_evidence_events", ["project_id"])
    op.create_index("ix_work_evidence_events_resource_id", "work_evidence_events", ["resource_id"])
    op.create_index("ix_work_evidence_events_source_system", "work_evidence_events", ["source_system"])
    op.create_index("ix_work_evidence_events_source_event_id", "work_evidence_events", ["source_event_id"])
    op.create_index("ix_work_evidence_events_timestamp", "work_evidence_events", ["timestamp"])

    # 6. ai_estimates
    op.create_table(
        "ai_estimates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("activity_type", sa.String(length=100), nullable=False),
        sa.Column("complexity", sa.String(length=30), nullable=False, server_default="Medium"),
        sa.Column("inputs", JSONB(), nullable=False),
        sa.Column("baseline_hours", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("historical_hours_adj", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("complexity_hours_adj", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("risk_hours_adj", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("team_env_hours_adj", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("optimistic_hours", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("most_likely_hours", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("pessimistic_hours", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("recommended_hours", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("pert_hours", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("assumptions", sa.Text(), nullable=True),
        sa.Column("risk_factors", sa.Text(), nullable=True),
        sa.Column("historical_context", JSONB(), nullable=True),
        sa.Column("suggested_breakdown", JSONB(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="suggested"),
        sa.Column("overridden_by", sa.Integer(), nullable=True),
        sa.Column("approved_hours", sa.Float(), nullable=True),
        sa.Column("actual_hours", sa.Float(), nullable=True),
        sa.Column("calibration_error", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["overridden_by"], ["users.id"], ondelete="SET NULL")
    )
    op.create_index("ix_ai_estimates_id", "ai_estimates", ["id"])
    op.create_index("ix_ai_estimates_project_id", "ai_estimates", ["project_id"])


def downgrade() -> None:
    op.drop_table("ai_estimates")
    op.drop_table("work_evidence_events")
    op.drop_table("daily_work_plans")
    op.drop_table("integration_connections")
    op.drop_table("resource_identity_mappings")
    op.drop_table("resources")
