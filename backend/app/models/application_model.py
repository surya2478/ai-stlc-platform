"""UI-016 Application Model — Phase 1.

Governed, versioned application-structure model built from completed
`DiscoverySession` evidence (see `app.models.discovery_session`). Follows the
same practical version-chain pattern actually used by
`TestCaseAutomationClassification`/`application_model_service.py`: a NEW
version row (`version`+1, `parent_model_id` set) is only created by the
initial build or by an explicit "Create New Draft" issued after the current
head has already reached `approved`/`published`/`rejected`. Governance
transitions themselves (submit-review/request-changes/approve/reject/
publish) update fields on the SAME row while it is still
`draft`/`pending_review`/`changes_requested` — once a row reaches `approved`
or `published` the service refuses further node/gap/locator mutation on it,
which is what makes that version immutable; superseded versions simply stay
in the chain via `parent_model_id`. Approve/reject/publish decisions
themselves are recorded via the existing generic `ApprovalAction` table
(`entity_type="application_model"`), not a bespoke approval table —
`application_model_activity` below only covers events `ApprovalAction`
doesn't (build/rebuild, node rename, locator confirm/unstable/fallback, gap
resolution).

Phase 1 only populates `screen`/`component`/`element` nodes and `CONTAINS`/
`NAVIGATES_TO` edges from `DiscoveryAction.target_screen_ref` /
`target_component_ref` / `target_element_ref` — the only structured signal a
completed discovery session currently produces (no DOM/network-log parser
exists yet, so `journey`/`api`/`external_system`/`validator` node types are
schema-ready but unpopulated until a later phase). See the P1-S4 UI-016 UI
contract and the approved implementation plan for the full node/edge
taxonomy and why Phase 1 stops here.
"""
from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

APPLICATION_MODEL_STATUSES = (
    "draft", "pending_review", "changes_requested", "approved",
    "published", "superseded", "rejected", "stale", "archived",
)

# Full contract enum (Section 19) — Phase 1 only ever writes application,
# screen, component, element. The rest are reserved so later phases can
# start writing them without a migration.
APPLICATION_MODEL_NODE_TYPES = (
    "application", "environment", "journey", "scenario", "test_case",
    "screen", "view", "dialog", "component", "element", "api",
    "external_system", "validator", "evidence", "gap",
)
APPLICATION_MODEL_NODE_STATES = (
    "DISCOVERED", "PARTIAL", "VALIDATED", "APPROVED", "PUBLISHED",
    "AMBIGUOUS", "MISSING", "BROKEN", "STALE", "BLOCKED",
)
APPLICATION_MODEL_EDGE_TYPES = ("CONTAINS", "NAVIGATES_TO")

LOCATOR_EVIDENCE_STATUSES = ("candidate", "confirmed", "unstable", "fallback")

# Full contract enum (Section 14) — Phase 1 only ever raises the first five
# (the ones derivable from loose discovery-action target refs). The rest are
# reserved for later phases (journey/API/external-validator gaps).
APPLICATION_MODEL_GAP_TYPES = (
    "MISSING_SCREEN", "MISSING_COMPONENT", "MISSING_ELEMENT", "AMBIGUOUS_ELEMENT", "UNSTABLE_LOCATOR",
    "BROKEN_NAVIGATION", "MISSING_JOURNEY_MAPPING", "MISSING_TEST_CASE_MAPPING", "MISSING_API_MAPPING",
    "AMBIGUOUS_API_MAPPING", "MISSING_EXTERNAL_VALIDATOR", "UNAVAILABLE_MCP", "MISSING_EVIDENCE",
    "SENSITIVE_DATA_VIOLATION", "STALE_SOURCE", "CONFLICTING_DISCOVERY_EVIDENCE", "UNSUPPORTED_CONTEXT",
    "APPROVAL_BLOCKER",
)
GAP_SEVERITIES = ("critical", "warning")
GAP_STATUSES = ("open", "resolved")


class ApplicationModel(TimestampMixin, Base):
    """One version in an application's model version chain."""

    __tablename__ = "application_models"
    __table_args__ = (
        CheckConstraint(
            "status IN ('" + "','".join(APPLICATION_MODEL_STATUSES) + "')", name="ck_application_models_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("project_applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovery_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    parent_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_models.id", ondelete="SET NULL"), nullable=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")

    built_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    built_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)

    # Action-sequence high-water-mark the draft was built from — stale
    # detection compares this against the source session's current action
    # count (or a newer completed session for the same application).
    built_from_action_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    project: Mapped["Project"] = relationship("Project")
    application: Mapped["ProjectApplication"] = relationship("ProjectApplication")
    source_session: Mapped["DiscoverySession | None"] = relationship(
        "DiscoverySession", foreign_keys=[source_session_id]
    )
    parent_model: Mapped["ApplicationModel | None"] = relationship("ApplicationModel", remote_side=[id])

    nodes: Mapped[list["ApplicationModelNode"]] = relationship(
        "ApplicationModelNode", back_populates="model", cascade="all, delete-orphan"
    )
    edges: Mapped[list["ApplicationModelEdge"]] = relationship(
        "ApplicationModelEdge", back_populates="model", cascade="all, delete-orphan"
    )
    gaps: Mapped[list["ApplicationModelGap"]] = relationship(
        "ApplicationModelGap", back_populates="model", cascade="all, delete-orphan"
    )


class ApplicationModelNode(TimestampMixin, Base):
    """One typed node (screen/component/element/...) in a model version."""

    __tablename__ = "application_model_nodes"
    __table_args__ = (
        CheckConstraint(
            "node_type IN ('" + "','".join(APPLICATION_MODEL_NODE_TYPES) + "')",
            name="ck_application_model_nodes_type",
        ),
        CheckConstraint(
            "state IN ('" + "','".join(APPLICATION_MODEL_NODE_STATES) + "')",
            name="ck_application_model_nodes_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("application_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    parent_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_model_nodes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # The raw target_screen_ref/target_component_ref/target_element_ref
    # string from DiscoveryAction — used to upsert idempotently on rebuild.
    external_ref: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="DISCOVERED", server_default="DISCOVERED")
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    model: Mapped["ApplicationModel"] = relationship("ApplicationModel", back_populates="nodes")
    parent_node: Mapped["ApplicationModelNode | None"] = relationship("ApplicationModelNode", remote_side=[id])
    locator_evidence: Mapped[list["ApplicationModelLocatorEvidence"]] = relationship(
        "ApplicationModelLocatorEvidence", back_populates="node", cascade="all, delete-orphan"
    )


class ApplicationModelEdge(TimestampMixin, Base):
    """One typed relationship between two nodes in the same model version."""

    __tablename__ = "application_model_edges"
    __table_args__ = (
        CheckConstraint(
            "edge_type IN ('" + "','".join(APPLICATION_MODEL_EDGE_TYPES) + "')",
            name="ck_application_model_edges_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("application_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edge_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    from_node_id: Mapped[int] = mapped_column(
        ForeignKey("application_model_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_node_id: Mapped[int] = mapped_column(
        ForeignKey("application_model_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    model: Mapped["ApplicationModel"] = relationship("ApplicationModel", back_populates="edges")


class ApplicationModelLocatorEvidence(TimestampMixin, Base):
    """Append-only locator history for one element node.

    Confirm/Mark-unstable/Add-fallback each insert a new row rather than
    mutate — the latest row per node is the current recommendation, older
    rows are the history shown in the inspector's Locators/History tabs.
    """

    __tablename__ = "application_model_locator_evidence"
    __table_args__ = (
        CheckConstraint(
            "status IN ('" + "','".join(LOCATOR_EVIDENCE_STATUSES) + "')",
            name="ck_application_model_locator_evidence_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    node_id: Mapped[int] = mapped_column(
        ForeignKey("application_model_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    locator_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    locator_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="candidate", server_default="candidate")
    source_action_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    node: Mapped["ApplicationModelNode"] = relationship("ApplicationModelNode", back_populates="locator_evidence")


class ApplicationModelGap(TimestampMixin, Base):
    """One deterministic gap/blocker raised against a model version."""

    __tablename__ = "application_model_gaps"
    __table_args__ = (
        CheckConstraint(
            "gap_type IN ('" + "','".join(APPLICATION_MODEL_GAP_TYPES) + "')", name="ck_application_model_gaps_type"
        ),
        CheckConstraint("severity IN ('" + "','".join(GAP_SEVERITIES) + "')", name="ck_application_model_gaps_severity"),
        CheckConstraint("status IN ('" + "','".join(GAP_STATUSES) + "')", name="ck_application_model_gaps_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("application_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gap_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="warning", server_default="warning")
    node_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_model_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", server_default="open")
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    model: Mapped["ApplicationModel"] = relationship("ApplicationModel", back_populates="gaps")


class ApplicationModelActivity(TimestampMixin, Base):
    """Residual audit log for model lifecycle events not already captured by
    `ApprovalAction` (approve/reject/publish) — build/rebuild, node rename,
    locator confirm/unstable/fallback, gap resolution. Same rationale as
    `ClassificationAuditEvent` in `app.models.automation_classification`.
    """

    __tablename__ = "application_model_activity"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("application_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
