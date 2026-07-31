"""UI-018 Automation Workspace — the Automation Test Suite aggregate (Phase A).

An Automation Test Suite is an orchestration and grouping container over
selected `TestCase` rows. It owns *only* orchestration state (name, tags,
membership, scope decisions, one default environment) and stores references
to authoritative entities rather than copying their editable values — the
application, framework, script, model, classification and traceability data
shown on this screen all belong to those sources, not here.

Phase A reaches 7 of the contract's 13 statuses (see `SUITE_REACHABLE_STATUSES`).
The other 6 need UI-023 Validation and Review, the approval workflow, or
immutable published snapshots, none of which exist yet; they are kept as
reserved CHECK-constraint values so later phases can write them without a
migration — the same phasing UI-016 used for its unpopulated node types.

`resolved_framework` and `resolved_environment` on a member row are the one
deliberate denormalization: the authoritative values are themselves plain
strings (`automation_scripts.framework`, and environment-as-data is a
free-text key into `project_applications.environment_urls`), so there is no
entity to point a foreign key at. Both are recomputed on every evaluation and
are never writable through the API.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

# Full contract enum (Section 8.2). Phase A only ever writes the 7 in
# SUITE_REACHABLE_STATUSES; the rest are reserved.
SUITE_STATUSES = (
    "DRAFT",
    "SCOPE_SELECTED",
    "INHERITANCE_REVIEW_REQUIRED",
    "MAPPING_INCOMPLETE",
    "CONFLICT_REVIEW_REQUIRED",
    "READY_FOR_VALIDATION",
    "VALIDATION_PENDING",
    "VALIDATION_FAILED",
    "READY_FOR_REVIEW",
    "APPROVED",
    "PUBLISHED",
    "DEPRECATED",
    "ARCHIVED",
)

# Reachable today. VALIDATION_PENDING/VALIDATION_FAILED still need UI-023
# Validation and Review, which does not exist yet.
SUITE_REACHABLE_STATUSES = (
    "DRAFT",
    "SCOPE_SELECTED",
    "INHERITANCE_REVIEW_REQUIRED",
    "MAPPING_INCOMPLETE",
    "CONFLICT_REVIEW_REQUIRED",
    "READY_FOR_VALIDATION",
    "READY_FOR_REVIEW",
    "APPROVED",
    "PUBLISHED",
    "DEPRECATED",
    "ARCHIVED",
)

# Statuses the approval workflow owns explicitly. Once a suite reaches one of
# these, re-evaluation refreshes its rollup and findings but must NOT recompute
# its status — otherwise approving a suite would be silently undone by the next
# evaluation pass.
WORKFLOW_OWNED_STATUSES = (
    "READY_FOR_REVIEW",
    "APPROVED",
    "PUBLISHED",
    "DEPRECATED",
    "ARCHIVED",
)

# A published suite is immutable: its membership and scope are frozen by the
# snapshot taken at publication. Changes require a new draft version.
IMMUTABLE_STATUSES = ("APPROVED", "PUBLISHED", "DEPRECATED", "ARCHIVED")

EXECUTION_GROUP_STATUSES = ("draft", "ready", "blocked")

MEMBER_INCLUSION_STATUSES = ("included", "excluded", "manual_only")
MEMBER_STATUSES = ("NOT_EVALUATED", "READY", "WARNING", "BLOCKED")
MEMBER_SOURCE_SYSTEMS = ("platform", "external")

# UI-020/021/023 (migration 051). Two independent axes, never one field.
#   autonomy_state — machine-owned; written only by the autonomy policy.
#   approval_state — human-owned; written only by a human action.
# AI_PENDING means the policy has not evaluated this member yet, which is
# distinct from AI_HELD (evaluated and refused).
MEMBER_AUTONOMY_STATES = ("AI_PENDING", "AI_HELD", "AI_APPROVED")
MEMBER_APPROVAL_STATES = ("PENDING_FINAL", "FINAL_APPROVED", "REJECTED")

# The autonomy counterpart of WORKFLOW_OWNED_STATUSES above. Once a human has
# ruled, re-evaluation may refresh the score for display but must never rewrite
# autonomy_state — otherwise the next evaluation pass silently undoes or
# re-grants an approval. UI-018 Phase B hit exactly this bug at suite level.
APPROVAL_OWNED_STATES = ("FINAL_APPROVED", "REJECTED")

# Gap taxonomy. The first block ports the retired per-test-case engine's
# blocker types 1:1 so no check's user-visible output changes. The second is
# new but sourced from real columns. The third is what only a suite can see.
# The fourth is reserved and never raised in Phase A — see the module note in
# services/automation_suite/readiness.py for why each is unavailable.
SUITE_MEMBER_GAP_TYPES = (
    "TEST_CASE_NOT_APPROVED",
    "CLASSIFICATION_NOT_APPROVED",
    "APPLICATION_MAPPING_MISSING",
    "MODEL_NOT_APPROVED",
    "MODEL_STALE",
    "LOCATOR_MISSING",
    "LOCATOR_AMBIGUOUS",
    "ENVIRONMENT_NOT_READY",
    "MANDATORY_MCP_UNAVAILABLE",
    "POLICY_STALE",
    "SCRIPT_MISSING",
    "SCRIPT_DEPRECATED",
    "TEST_DATA_MISSING",
    "ENVIRONMENT_UNRESOLVED",
    "SOURCE_TEST_CASE_CHANGED",
    "TEST_CASE_DELETED",
)
SUITE_CONFLICT_TYPES = (
    "MULTIPLE_FRAMEWORKS",
    "MULTIPLE_ENVIRONMENTS",
    "MIXED_MANUAL_AUTOMATED",
    "DUPLICATE_TEST_CASE",
)
SUITE_RESERVED_GAP_TYPES = (
    "AUTOMATION_IR_MISSING",
    "FRAMEWORK_PROFILE_MISSING",
    "UNSUPPORTED_FRAMEWORK_APPLICATION",
    "REPOSITORY_LINK_INVALID",
    "EVIDENCE_POLICY_INCOMPLETE",
    "PERMISSION_DENIED",
    "VALIDATION_FAILED",
    "SEPARATION_OF_DUTY_VIOLATION",
    "SNAPSHOT_DRIFT",
)
SUITE_GAP_TYPES = SUITE_MEMBER_GAP_TYPES + SUITE_CONFLICT_TYPES + SUITE_RESERVED_GAP_TYPES

GAP_SCOPES = ("member", "suite")
GAP_CATEGORIES = ("gap", "conflict")
GAP_SEVERITIES = ("critical", "warning")
# `resolved` is also written by re-evaluation (auto_closed=True); the other
# two are only ever set by a human decision.
GAP_STATUSES = ("open", "resolved", "exception_approved", "excluded")
GAP_RESOLUTION_ACTIONS = (
    "keep_per_test_case",
    "split_execution_groups",
    "apply_default_to_missing",
    "exclude_test_case",
    "open_source",
    "approve_exception",
    "send_for_mapping_review",
)

# Reused verbatim from the retired workspace model so blockers keep bucketing
# into the same 8 lifecycle stages the rest of P1-S5 will navigate.
SUITE_STAGES = (
    "test_intent",
    "grounding",
    "live_recording",
    "automation_ir",
    "script_generation",
    "validation_review",
    "approval_publish",
    "execution_readiness",
)


class AutomationSuite(TimestampMixin, Base):
    """One version in an Automation Test Suite's chain."""

    __tablename__ = "automation_suites"
    __table_args__ = (
        CheckConstraint(
            "status IN ('" + "','".join(SUITE_STATUSES) + "')", name="ck_automation_suites_status"
        ),
        UniqueConstraint("project_id", "idempotency_key", name="uq_automation_suites_project_idempotency"),
        # Contract Section 16 name uniqueness. Partial so an archived suite's
        # name is reusable and so a Phase B version chain does not collide
        # with its own parent.
        Index(
            "uq_automation_suites_project_name_active",
            "project_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("is_current AND status <> 'ARCHIVED'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT", server_default="DRAFT")

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    parent_suite_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_suites.id", ondelete="SET NULL"), nullable=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # The only default Phase A captures. Contract Section 19 permits a
    # suite-owned default *only* where the member has no value of its own.
    default_environment: Mapped[str | None] = mapped_column(String(100), nullable=True)

    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    archived_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    archived_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Phase B approval workflow audit ──
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Client-supplied, one per wizard session, so a browser refresh or a
    # double-submit replays onto the same suite instead of creating a second.
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    last_evaluated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_inheritance_sync_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Persisted rollup of the last evaluation so the list view is one query
    # rather than an N+1 over members and gaps.
    members_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    members_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    members_ready: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    members_blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    members_manual_only: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    members_drifted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    gaps_critical_open: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    gaps_warning_open: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    conflicts_open: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    project: Mapped["Project"] = relationship("Project")
    parent_suite: Mapped["AutomationSuite | None"] = relationship("AutomationSuite", remote_side=[id])
    members: Mapped[list["AutomationSuiteTestCase"]] = relationship(
        "AutomationSuiteTestCase", back_populates="suite", cascade="all, delete-orphan"
    )
    gaps: Mapped[list["AutomationSuiteGap"]] = relationship(
        "AutomationSuiteGap", back_populates="suite", cascade="all, delete-orphan"
    )
    execution_groups: Mapped[list["AutomationSuiteExecutionGroup"]] = relationship(
        "AutomationSuiteExecutionGroup", back_populates="suite", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list["AutomationSuiteSnapshot"]] = relationship(
        "AutomationSuiteSnapshot", back_populates="suite", cascade="all, delete-orphan"
    )


class AutomationSuiteTestCase(TimestampMixin, Base):
    """One Test Case's membership of a suite, plus its last evaluation."""

    __tablename__ = "automation_suite_test_cases"
    __table_args__ = (
        CheckConstraint(
            "inclusion_status IN ('" + "','".join(MEMBER_INCLUSION_STATUSES) + "')",
            name="ck_automation_suite_test_cases_inclusion",
        ),
        CheckConstraint(
            "member_status IN ('" + "','".join(MEMBER_STATUSES) + "')",
            name="ck_automation_suite_test_cases_member_status",
        ),
        CheckConstraint(
            "source_system IN ('" + "','".join(MEMBER_SOURCE_SYSTEMS) + "')",
            name="ck_automation_suite_test_cases_source_system",
        ),
        CheckConstraint(
            "autonomy_state IN ('" + "','".join(MEMBER_AUTONOMY_STATES) + "')",
            name="ck_automation_suite_test_cases_autonomy_state",
        ),
        CheckConstraint(
            "approval_state IN ('" + "','".join(MEMBER_APPROVAL_STATES) + "')",
            name="ck_automation_suite_test_cases_approval_state",
        ),
        UniqueConstraint("suite_id", "test_case_id", name="uq_automation_suite_test_cases"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    suite_id: Mapped[int] = mapped_column(
        ForeignKey("automation_suites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Suite-owned scope decisions.
    inclusion_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="included", server_default="included"
    )
    planned_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Phase B. Nullable: an ungrouped member is legitimate until the suite is
    # split into groups.
    execution_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_suite_execution_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, default="platform", server_default="platform")
    # Provenance of how the member arrived, e.g. "test_suite:12" when added
    # by expanding a pack — drives the "Inherited from ..." label.
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    excluded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    excluded_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Last evaluation output.
    member_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NOT_EVALUATED", server_default="NOT_EVALUATED", index=True
    )
    readiness_checks_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    readiness_checks_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_evaluated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Drift high-water mark — the live test case advancing past this is what
    # makes the suite INHERITANCE_REVIEW_REQUIRED.
    source_test_case_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # References to the authoritative entities this evaluation resolved
    # against. Not copies of their values.
    resolved_application_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_applications.id", ondelete="SET NULL"), nullable=True
    )
    resolved_classification_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_case_automation_classifications.id", ondelete="SET NULL"), nullable=True
    )
    resolved_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_models.id", ondelete="SET NULL"), nullable=True
    )
    resolved_script_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_scripts.id", ondelete="SET NULL"), nullable=True
    )
    # See the module docstring: no entity exists to key these to.
    resolved_framework: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolved_environment: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── UI-020/021/023: the two independent state axes (migration 051) ───────
    # Deliberately two columns, not one. `autonomy_state` is written only by the
    # autonomy policy; `approval_state` is written only by a human action. One
    # combined field would let the generating agent write what a reviewer writes
    # — the separation-of-duty violation lifecycle.py already refuses for humans.
    autonomy_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="AI_PENDING", server_default="AI_PENDING"
    )
    approval_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING_FINAL", server_default="PENDING_FINAL"
    )

    suite: Mapped["AutomationSuite"] = relationship("AutomationSuite", back_populates="members")
    test_case: Mapped["TestCase"] = relationship("TestCase")


class AutomationSuiteExecutionGroup(TimestampMixin, Base):
    """A suite-owned grouping of members that can execute together.

    This is orchestration metadata the suite owns outright — it groups members
    by an inherited discriminator (framework, application, environment) without
    changing any of them. Splitting a `MULTIPLE_FRAMEWORKS` or
    `MULTIPLE_ENVIRONMENTS` conflict into groups is what resolves it without
    overwriting anything at source.

    Parallelism, retry, timeout and agent-pool policy are deliberately absent
    from this table: they are execution-time concerns, and P1-S7 put them where
    they belong. As of migration 052 a suite-to-execution path does exist —
    `execution_runs.suite_snapshot_id` — and the run row owns `parallel_limit`
    and the per-item `attempts_allowed`, because those apply to one dispatch of
    a snapshot rather than to the grouping decision recorded here.
    """

    __tablename__ = "automation_suite_execution_groups"
    __table_args__ = (
        CheckConstraint(
            "status IN ('" + "','".join(EXECUTION_GROUP_STATUSES) + "')",
            name="ck_automation_suite_execution_groups_status",
        ),
        UniqueConstraint("suite_id", "name", name="uq_automation_suite_execution_groups_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    suite_id: Mapped[int] = mapped_column(
        ForeignKey("automation_suites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")

    # The inherited discriminators this group was formed on. References and
    # plain strings, mirroring the member row — never a copy of editable data.
    framework: Mapped[str | None] = mapped_column(String(50), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_applications.id", ondelete="SET NULL"), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    suite: Mapped["AutomationSuite"] = relationship("AutomationSuite", back_populates="execution_groups")


class AutomationSuiteSnapshot(TimestampMixin, Base):
    """An immutable record of exactly what was published.

    Written once at publication and never updated. Historical executions and
    impact review both read from here, so a later change to a test case,
    script or Application Model cannot rewrite what a published version was.
    """

    __tablename__ = "automation_suite_snapshots"
    __table_args__ = (
        UniqueConstraint("suite_id", "suite_version", name="uq_automation_suite_snapshots_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    suite_id: Mapped[int] = mapped_column(
        ForeignKey("automation_suites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suite_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # The frozen resolved scope: one entry per member with the exact source
    # entity ids and versions it was published against.
    members: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    execution_groups: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    # sha256 of the canonical member payload — lets impact review prove a
    # snapshot has not been tampered with.
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    suite: Mapped["AutomationSuite"] = relationship("AutomationSuite", back_populates="snapshots")


class AutomationSuiteGap(TimestampMixin, Base):
    """One readiness gap or cross-member conflict on a suite.

    Distinct from `ApplicationModelGap`, which grades a single model version's
    quality. These are suite-scope findings that additionally carry the
    suite's adjudication of them, so re-evaluation upserts by `fingerprint`
    and auto-closes what it no longer detects — it never deletes, because a
    delete would silently discard an approved exception and its audit trail.

    An approved exception is a row with `status='exception_approved'`, not a
    separate table.
    """

    __tablename__ = "automation_suite_gaps"
    __table_args__ = (
        CheckConstraint(
            "gap_type IN ('" + "','".join(SUITE_GAP_TYPES) + "')", name="ck_automation_suite_gaps_type"
        ),
        CheckConstraint("scope IN ('" + "','".join(GAP_SCOPES) + "')", name="ck_automation_suite_gaps_scope"),
        CheckConstraint(
            "category IN ('" + "','".join(GAP_CATEGORIES) + "')", name="ck_automation_suite_gaps_category"
        ),
        CheckConstraint(
            "severity IN ('" + "','".join(GAP_SEVERITIES) + "')", name="ck_automation_suite_gaps_severity"
        ),
        CheckConstraint("stage IN ('" + "','".join(SUITE_STAGES) + "')", name="ck_automation_suite_gaps_stage"),
        CheckConstraint("status IN ('" + "','".join(GAP_STATUSES) + "')", name="ck_automation_suite_gaps_status"),
        CheckConstraint(
            "resolution_action IS NULL OR resolution_action IN ('" + "','".join(GAP_RESOLUTION_ACTIONS) + "')",
            name="ck_automation_suite_gaps_resolution_action",
        ),
        UniqueConstraint("suite_id", "fingerprint", name="uq_automation_suite_gaps_fingerprint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    suite_id: Mapped[int] = mapped_column(
        ForeignKey("automation_suites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL means a suite-level finding that belongs to no single member.
    suite_test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_suite_test_cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True
    )

    gap_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="warning", server_default="warning")
    stage: Mapped[str] = mapped_column(String(30), nullable=False)

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open", server_default="open", index=True)
    resolution_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # True when re-evaluation closed it, so the UI can distinguish "fixed at
    # source" from "a human decided".
    auto_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # Deterministic identity across evaluations. Must be built from stable
    # parts only — see services/automation_suite/gaps.py.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    first_detected_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    last_detected_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    suite: Mapped["AutomationSuite"] = relationship("AutomationSuite", back_populates="gaps")


class AutomationSuiteActivity(TimestampMixin, Base):
    """Append-only audit of suite events.

    Covers what the generic `ApprovalAction` table does not: membership
    changes, inheritance refreshes, evaluations, gap auto-closes and
    exclusions. Exception approvals write here *and* to `ApprovalAction`.
    """

    __tablename__ = "automation_suite_activity"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    suite_id: Mapped[int] = mapped_column(
        ForeignKey("automation_suites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suite_test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_suite_test_cases.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
