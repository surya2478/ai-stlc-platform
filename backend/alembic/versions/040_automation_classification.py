"""040 - automation classification and routing (P1-S3 extension)

Adds the versioned policy/classification tables backing the Test Automation
Classification and Routing capability across UI-010/011/012/013, plus a
nullable `capability_key` on mcp_connections so classification policy rules
can reference a validator by stable key instead of matching free-text
`name`.

New tables carry no rows on upgrade — every column that needs a default
(status, version, is_current, review_status, JSONB collections) has one, so
existing test cases simply read back as NOT_EVALUATED until classified. No
backfill required.

Revision ID: 040
Revises: 039
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mcp_connections", sa.Column("capability_key", sa.String(length=80), nullable=True))
    op.create_index("ix_mcp_connections_capability_key", "mcp_connections", ["capability_key"])

    op.create_table(
        "automation_classification_policies",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("project_applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "parent_policy_id",
            sa.Integer(),
            sa.ForeignKey("automation_classification_policies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_automation_classification_policies_project_id", "automation_classification_policies", ["project_id"]
    )
    op.create_index(
        "ix_automation_classification_policies_application_id",
        "automation_classification_policies",
        ["application_id"],
    )
    op.create_index("ix_automation_classification_policies_code", "automation_classification_policies", ["code"])
    op.create_index(
        "ix_automation_classification_policies_parent_policy_id",
        "automation_classification_policies",
        ["parent_policy_id"],
    )
    op.create_index(
        "ix_automation_classification_policies_scope",
        "automation_classification_policies",
        ["project_id", "application_id", "status"],
    )

    op.create_table(
        "test_case_automation_classifications",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("test_case_id", sa.Integer(), sa.ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("test_case_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "parent_classification_id",
            sa.Integer(),
            sa.ForeignKey("test_case_automation_classifications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("candidate_status", sa.String(length=40), nullable=False, server_default="NOT_EVALUATED"),
        sa.Column("primary_adapter", sa.String(length=100), nullable=True),
        sa.Column("supporting_adapters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("mandatory_validators", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("optional_validators", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("discovery_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recommended_discovery_mode", sa.String(length=40), nullable=True),
        sa.Column("complexity_score", sa.Integer(), nullable=True),
        sa.Column("automation_value_score", sa.Integer(), nullable=True),
        sa.Column("score_factors", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("required_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("required_capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("deterministic_blockers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("advisory_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("matched_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column(
            "policy_id",
            sa.Integer(),
            sa.ForeignKey("automation_classification_policies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("policy_version", sa.Integer(), nullable=True),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("review_status", sa.String(length=30), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_test_case_automation_classifications_project_id",
        "test_case_automation_classifications",
        ["project_id"],
    )
    op.create_index(
        "ix_test_case_automation_classifications_test_case_id",
        "test_case_automation_classifications",
        ["test_case_id"],
    )
    op.create_index(
        "ix_test_case_automation_classifications_parent_id",
        "test_case_automation_classifications",
        ["parent_classification_id"],
    )
    op.create_index(
        "ix_test_case_automation_classifications_is_current",
        "test_case_automation_classifications",
        ["is_current"],
    )
    op.create_index(
        "ix_test_case_automation_classifications_policy_id",
        "test_case_automation_classifications",
        ["policy_id"],
    )
    op.create_index(
        "ix_test_case_automation_classifications_current",
        "test_case_automation_classifications",
        ["test_case_id", "is_current"],
    )

    op.create_table(
        "classification_field_corrections",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "classification_id",
            sa.Integer(),
            sa.ForeignKey("test_case_automation_classifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_name", sa.String(length=100), nullable=False),
        sa.Column("ai_value", sa.Text(), nullable=True),
        sa.Column("reviewer_value", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_classification_field_corrections_classification_id",
        "classification_field_corrections",
        ["classification_id"],
    )
    op.create_index(
        "ix_classification_field_corrections_field_name", "classification_field_corrections", ["field_name"]
    )

    op.create_table(
        "classification_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "classification_id",
            sa.Integer(),
            sa.ForeignKey("test_case_automation_classifications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("test_case_id", sa.Integer(), sa.ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="platform"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_classification_audit_events_project_id", "classification_audit_events", ["project_id"])
    op.create_index(
        "ix_classification_audit_events_classification_id", "classification_audit_events", ["classification_id"]
    )
    op.create_index("ix_classification_audit_events_test_case_id", "classification_audit_events", ["test_case_id"])
    op.create_index("ix_classification_audit_events_event_type", "classification_audit_events", ["event_type"])
    op.create_index(
        "ix_classification_audit_events_correlation_id", "classification_audit_events", ["correlation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_classification_audit_events_correlation_id", table_name="classification_audit_events")
    op.drop_index("ix_classification_audit_events_event_type", table_name="classification_audit_events")
    op.drop_index("ix_classification_audit_events_test_case_id", table_name="classification_audit_events")
    op.drop_index("ix_classification_audit_events_classification_id", table_name="classification_audit_events")
    op.drop_index("ix_classification_audit_events_project_id", table_name="classification_audit_events")
    op.drop_table("classification_audit_events")

    op.drop_index("ix_classification_field_corrections_field_name", table_name="classification_field_corrections")
    op.drop_index(
        "ix_classification_field_corrections_classification_id", table_name="classification_field_corrections"
    )
    op.drop_table("classification_field_corrections")

    op.drop_index(
        "ix_test_case_automation_classifications_current", table_name="test_case_automation_classifications"
    )
    op.drop_index(
        "ix_test_case_automation_classifications_policy_id", table_name="test_case_automation_classifications"
    )
    op.drop_index(
        "ix_test_case_automation_classifications_is_current", table_name="test_case_automation_classifications"
    )
    op.drop_index(
        "ix_test_case_automation_classifications_parent_id",
        table_name="test_case_automation_classifications",
    )
    op.drop_index(
        "ix_test_case_automation_classifications_test_case_id", table_name="test_case_automation_classifications"
    )
    op.drop_index(
        "ix_test_case_automation_classifications_project_id", table_name="test_case_automation_classifications"
    )
    op.drop_table("test_case_automation_classifications")

    op.drop_index("ix_automation_classification_policies_scope", table_name="automation_classification_policies")
    op.drop_index(
        "ix_automation_classification_policies_parent_policy_id", table_name="automation_classification_policies"
    )
    op.drop_index("ix_automation_classification_policies_code", table_name="automation_classification_policies")
    op.drop_index(
        "ix_automation_classification_policies_application_id", table_name="automation_classification_policies"
    )
    op.drop_index(
        "ix_automation_classification_policies_project_id", table_name="automation_classification_policies"
    )
    op.drop_table("automation_classification_policies")

    op.drop_index("ix_mcp_connections_capability_key", table_name="mcp_connections")
    op.drop_column("mcp_connections", "capability_key")
