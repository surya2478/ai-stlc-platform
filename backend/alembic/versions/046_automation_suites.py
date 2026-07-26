"""046 - UI-018 Automation Workspace: Automation Test Suite (Phase A)

Replaces the retired per-test-case automation_workspaces aggregate with the
suite aggregate: automation_suites, automation_suite_test_cases,
automation_suite_gaps, automation_suite_activity.

Revision ID: 046
Revises: 045
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None

SUITE_STATUSES = (
    "DRAFT", "SCOPE_SELECTED", "INHERITANCE_REVIEW_REQUIRED", "MAPPING_INCOMPLETE",
    "CONFLICT_REVIEW_REQUIRED", "READY_FOR_VALIDATION", "VALIDATION_PENDING",
    "VALIDATION_FAILED", "READY_FOR_REVIEW", "APPROVED", "PUBLISHED", "DEPRECATED",
    "ARCHIVED",
)
MEMBER_INCLUSION_STATUSES = ("included", "excluded", "manual_only")
MEMBER_STATUSES = ("NOT_EVALUATED", "READY", "WARNING", "BLOCKED")
MEMBER_SOURCE_SYSTEMS = ("platform", "external")
SUITE_GAP_TYPES = (
    "TEST_CASE_NOT_APPROVED", "CLASSIFICATION_NOT_APPROVED", "APPLICATION_MAPPING_MISSING",
    "MODEL_NOT_APPROVED", "MODEL_STALE", "LOCATOR_MISSING", "LOCATOR_AMBIGUOUS",
    "ENVIRONMENT_NOT_READY", "MANDATORY_MCP_UNAVAILABLE", "POLICY_STALE",
    "SCRIPT_MISSING", "SCRIPT_DEPRECATED", "TEST_DATA_MISSING", "ENVIRONMENT_UNRESOLVED",
    "SOURCE_TEST_CASE_CHANGED", "TEST_CASE_DELETED",
    "MULTIPLE_FRAMEWORKS", "MULTIPLE_ENVIRONMENTS", "MIXED_MANUAL_AUTOMATED",
    "DUPLICATE_TEST_CASE",
    "AUTOMATION_IR_MISSING", "FRAMEWORK_PROFILE_MISSING", "UNSUPPORTED_FRAMEWORK_APPLICATION",
    "REPOSITORY_LINK_INVALID", "EVIDENCE_POLICY_INCOMPLETE", "PERMISSION_DENIED",
    "VALIDATION_FAILED", "SEPARATION_OF_DUTY_VIOLATION", "SNAPSHOT_DRIFT",
)
GAP_SCOPES = ("member", "suite")
GAP_CATEGORIES = ("gap", "conflict")
GAP_SEVERITIES = ("critical", "warning")
GAP_STATUSES = ("open", "resolved", "exception_approved", "excluded")
GAP_RESOLUTION_ACTIONS = (
    "keep_per_test_case", "split_execution_groups", "apply_default_to_missing",
    "exclude_test_case", "open_source", "approve_exception", "send_for_mapping_review",
)
SUITE_STAGES = (
    "test_intent", "grounding", "live_recording", "automation_ir",
    "script_generation", "validation_review", "approval_publish", "execution_readiness",
)


def _in_list(column: str, values) -> str:
    return f"{column} IN ('" + "','".join(values) + "')"


def upgrade() -> None:
    op.create_table(
        "automation_suites",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="DRAFT"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "parent_suite_id", sa.Integer(), sa.ForeignKey("automation_suites.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("default_environment", sa.String(length=100), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("archived_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_inheritance_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("members_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("members_included", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("members_ready", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("members_blocked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("members_manual_only", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("members_drifted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gaps_critical_open", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gaps_warning_open", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflicts_open", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(_in_list("status", SUITE_STATUSES), name="ck_automation_suites_status"),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_automation_suites_project_idempotency"),
    )
    op.create_index("ix_automation_suites_project_id", "automation_suites", ["project_id"])
    op.create_index("ix_automation_suites_is_current", "automation_suites", ["is_current"])
    op.create_index("ix_automation_suites_correlation_id", "automation_suites", ["correlation_id"])
    op.create_index(
        "uq_automation_suites_project_name_active",
        "automation_suites",
        ["project_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("is_current AND status <> 'ARCHIVED'"),
    )

    op.create_table(
        "automation_suite_test_cases",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "suite_id", sa.Integer(), sa.ForeignKey("automation_suites.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("test_case_id", sa.Integer(), sa.ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inclusion_status", sa.String(length=20), nullable=False, server_default="included"),
        sa.Column("planned_sequence", sa.Integer(), nullable=True),
        sa.Column("source_system", sa.String(length=50), nullable=False, server_default="platform"),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("added_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("excluded_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("excluded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exclusion_reason", sa.Text(), nullable=True),
        sa.Column("member_status", sa.String(length=30), nullable=False, server_default="NOT_EVALUATED"),
        sa.Column("readiness_checks_passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("readiness_checks_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_test_case_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "resolved_application_id",
            sa.Integer(),
            sa.ForeignKey("project_applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "resolved_classification_id",
            sa.Integer(),
            sa.ForeignKey("test_case_automation_classifications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "resolved_model_id",
            sa.Integer(),
            sa.ForeignKey("application_models.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "resolved_script_id",
            sa.Integer(),
            sa.ForeignKey("automation_scripts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_framework", sa.String(length=50), nullable=True),
        sa.Column("resolved_environment", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            _in_list("inclusion_status", MEMBER_INCLUSION_STATUSES),
            name="ck_automation_suite_test_cases_inclusion",
        ),
        sa.CheckConstraint(
            _in_list("member_status", MEMBER_STATUSES), name="ck_automation_suite_test_cases_member_status"
        ),
        sa.CheckConstraint(
            _in_list("source_system", MEMBER_SOURCE_SYSTEMS),
            name="ck_automation_suite_test_cases_source_system",
        ),
        sa.UniqueConstraint("suite_id", "test_case_id", name="uq_automation_suite_test_cases"),
    )
    op.create_index("ix_automation_suite_test_cases_suite_id", "automation_suite_test_cases", ["suite_id"])
    op.create_index("ix_automation_suite_test_cases_test_case_id", "automation_suite_test_cases", ["test_case_id"])
    op.create_index("ix_automation_suite_test_cases_member_status", "automation_suite_test_cases", ["member_status"])

    op.create_table(
        "automation_suite_gaps",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "suite_id", sa.Integer(), sa.ForeignKey("automation_suites.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "suite_test_case_id",
            sa.Integer(),
            sa.ForeignKey("automation_suite_test_cases.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("test_case_id", sa.Integer(), sa.ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("gap_type", sa.String(length=60), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
        sa.Column("stage", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("resolution_action", sa.String(length=40), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_closed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(_in_list("gap_type", SUITE_GAP_TYPES), name="ck_automation_suite_gaps_type"),
        sa.CheckConstraint(_in_list("scope", GAP_SCOPES), name="ck_automation_suite_gaps_scope"),
        sa.CheckConstraint(_in_list("category", GAP_CATEGORIES), name="ck_automation_suite_gaps_category"),
        sa.CheckConstraint(_in_list("severity", GAP_SEVERITIES), name="ck_automation_suite_gaps_severity"),
        sa.CheckConstraint(_in_list("stage", SUITE_STAGES), name="ck_automation_suite_gaps_stage"),
        sa.CheckConstraint(_in_list("status", GAP_STATUSES), name="ck_automation_suite_gaps_status"),
        sa.CheckConstraint(
            "resolution_action IS NULL OR " + _in_list("resolution_action", GAP_RESOLUTION_ACTIONS),
            name="ck_automation_suite_gaps_resolution_action",
        ),
        sa.UniqueConstraint("suite_id", "fingerprint", name="uq_automation_suite_gaps_fingerprint"),
    )
    op.create_index("ix_automation_suite_gaps_suite_id", "automation_suite_gaps", ["suite_id"])
    op.create_index("ix_automation_suite_gaps_suite_test_case_id", "automation_suite_gaps", ["suite_test_case_id"])
    op.create_index("ix_automation_suite_gaps_gap_type", "automation_suite_gaps", ["gap_type"])
    op.create_index("ix_automation_suite_gaps_status", "automation_suite_gaps", ["status"])

    op.create_table(
        "automation_suite_activity",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "suite_id", sa.Integer(), sa.ForeignKey("automation_suites.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "suite_test_case_id",
            sa.Integer(),
            sa.ForeignKey("automation_suite_test_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_automation_suite_activity_project_id", "automation_suite_activity", ["project_id"])
    op.create_index("ix_automation_suite_activity_suite_id", "automation_suite_activity", ["suite_id"])
    op.create_index("ix_automation_suite_activity_event_type", "automation_suite_activity", ["event_type"])
    op.create_index("ix_automation_suite_activity_correlation_id", "automation_suite_activity", ["correlation_id"])


def downgrade() -> None:
    op.drop_table("automation_suite_activity")
    op.drop_table("automation_suite_gaps")
    op.drop_table("automation_suite_test_cases")
    op.drop_table("automation_suites")
