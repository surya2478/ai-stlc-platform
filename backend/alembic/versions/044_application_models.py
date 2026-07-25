"""044 - UI-016 Application Model (Phase 1)

Adds the versioned Application Model tables: application_models,
application_model_nodes, application_model_edges,
application_model_locator_evidence, application_model_gaps,
application_model_activity. Also converts discovery_sessions.
draft_model_version_id from a plain placeholder Integer into a real FK now
that application_models exists.

Additive only aside from the FK conversion; the FK conversion is safe since
the column has carried no values yet (UI-016 didn't exist until now).

Revision ID: 044
Revises: 043
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_models",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "application_id", sa.Integer(), sa.ForeignKey("project_applications.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "source_session_id", sa.Integer(), sa.ForeignKey("discovery_sessions.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_model_id", sa.Integer(), sa.ForeignKey("application_models.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("built_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("built_from_action_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('draft','pending_review','changes_requested','approved','published','superseded',"
            "'rejected','stale','archived')",
            name="ck_application_models_status",
        ),
    )
    op.create_index("ix_application_models_project_id", "application_models", ["project_id"])
    op.create_index("ix_application_models_application_id", "application_models", ["application_id"])
    op.create_index("ix_application_models_source_session_id", "application_models", ["source_session_id"])
    op.create_index("ix_application_models_is_current", "application_models", ["is_current"])
    op.create_index("ix_application_models_correlation_id", "application_models", ["correlation_id"])

    op.create_table(
        "application_model_nodes",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("application_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_type", sa.String(length=30), nullable=False),
        sa.Column(
            "parent_node_id", sa.Integer(), sa.ForeignKey("application_model_nodes.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("external_ref", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="DISCOVERED"),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "node_type IN ('application','environment','journey','scenario','test_case','screen','view','dialog',"
            "'component','element','api','external_system','validator','evidence','gap')",
            name="ck_application_model_nodes_type",
        ),
        sa.CheckConstraint(
            "state IN ('DISCOVERED','PARTIAL','VALIDATED','APPROVED','PUBLISHED','AMBIGUOUS','MISSING','BROKEN',"
            "'STALE','BLOCKED')",
            name="ck_application_model_nodes_state",
        ),
    )
    op.create_index("ix_application_model_nodes_model_id", "application_model_nodes", ["model_id"])
    op.create_index("ix_application_model_nodes_node_type", "application_model_nodes", ["node_type"])
    op.create_index("ix_application_model_nodes_parent_node_id", "application_model_nodes", ["parent_node_id"])
    op.create_index("ix_application_model_nodes_external_ref", "application_model_nodes", ["external_ref"])

    op.create_table(
        "application_model_edges",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("application_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("edge_type", sa.String(length=30), nullable=False),
        sa.Column(
            "from_node_id", sa.Integer(), sa.ForeignKey("application_model_nodes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "to_node_id", sa.Integer(), sa.ForeignKey("application_model_nodes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("edge_type IN ('CONTAINS','NAVIGATES_TO')", name="ck_application_model_edges_type"),
    )
    op.create_index("ix_application_model_edges_model_id", "application_model_edges", ["model_id"])
    op.create_index("ix_application_model_edges_edge_type", "application_model_edges", ["edge_type"])
    op.create_index("ix_application_model_edges_from_node_id", "application_model_edges", ["from_node_id"])
    op.create_index("ix_application_model_edges_to_node_id", "application_model_edges", ["to_node_id"])

    op.create_table(
        "application_model_locator_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "node_id", sa.Integer(), sa.ForeignKey("application_model_nodes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("locator_value", sa.Text(), nullable=True),
        sa.Column("locator_type", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="candidate"),
        sa.Column(
            "source_action_id", sa.Integer(), sa.ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('candidate','confirmed','unstable','fallback')",
            name="ck_application_model_locator_evidence_status",
        ),
    )
    op.create_index("ix_application_model_locator_evidence_node_id", "application_model_locator_evidence", ["node_id"])

    op.create_table(
        "application_model_gaps",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("application_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gap_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
        sa.Column(
            "node_id", sa.Integer(), sa.ForeignKey("application_model_nodes.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "gap_type IN ('MISSING_SCREEN','MISSING_COMPONENT','MISSING_ELEMENT','AMBIGUOUS_ELEMENT',"
            "'UNSTABLE_LOCATOR','BROKEN_NAVIGATION','MISSING_JOURNEY_MAPPING','MISSING_TEST_CASE_MAPPING',"
            "'MISSING_API_MAPPING','AMBIGUOUS_API_MAPPING','MISSING_EXTERNAL_VALIDATOR','UNAVAILABLE_MCP',"
            "'MISSING_EVIDENCE','SENSITIVE_DATA_VIOLATION','STALE_SOURCE','CONFLICTING_DISCOVERY_EVIDENCE',"
            "'UNSUPPORTED_CONTEXT','APPROVAL_BLOCKER')",
            name="ck_application_model_gaps_type",
        ),
        sa.CheckConstraint("severity IN ('critical','warning')", name="ck_application_model_gaps_severity"),
        sa.CheckConstraint("status IN ('open','resolved')", name="ck_application_model_gaps_status"),
    )
    op.create_index("ix_application_model_gaps_model_id", "application_model_gaps", ["model_id"])
    op.create_index("ix_application_model_gaps_gap_type", "application_model_gaps", ["gap_type"])
    op.create_index("ix_application_model_gaps_node_id", "application_model_gaps", ["node_id"])

    op.create_table(
        "application_model_activity",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("application_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_application_model_activity_project_id", "application_model_activity", ["project_id"])
    op.create_index("ix_application_model_activity_model_id", "application_model_activity", ["model_id"])
    op.create_index("ix_application_model_activity_event_type", "application_model_activity", ["event_type"])
    op.create_index("ix_application_model_activity_correlation_id", "application_model_activity", ["correlation_id"])

    # discovery_sessions.draft_model_version_id was a placeholder Integer
    # (no FK) until application_models existed. Convert it to a real FK now
    # — safe, since it has carried no values yet.
    op.create_foreign_key(
        "fk_discovery_sessions_draft_model_version_id",
        "discovery_sessions",
        "application_models",
        ["draft_model_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_discovery_sessions_draft_model_version_id", "discovery_sessions", type_="foreignkey")
    op.drop_table("application_model_activity")
    op.drop_table("application_model_gaps")
    op.drop_table("application_model_locator_evidence")
    op.drop_table("application_model_edges")
    op.drop_table("application_model_nodes")
    op.drop_table("application_models")
