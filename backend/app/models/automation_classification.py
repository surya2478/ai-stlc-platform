from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class AutomationClassificationPolicy(TimestampMixin, Base):
    """A versioned, scoped policy the classification engine resolves against.

    Scope precedence (most specific wins, resolved by policy_resolver):
    application-scoped > project-scoped > enterprise/global default
    (project_id IS NULL). Every publish creates a NEW row via
    `parent_policy_id` (ADR-001 version-chain pattern, same as
    AutomationScript) — a published policy is never mutated in place.
    """

    __tablename__ = "automation_classification_policies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_applications.id", ondelete="SET NULL"), nullable=True, index=True
    )

    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    parent_policy_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_classification_policies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # status: draft | published | archived — only a published policy can be
    # resolved by policy_resolver; deterministic_rules rejects drafts.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")

    # candidate_rules, routing_rules, external_validation_rules,
    # evidence_rules, scoring_weights — see docs/test-automation-classification
    # -routing-implementation-prompt.md "Example policy" for the shape.
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project | None"] = relationship("Project")
    application: Mapped["ProjectApplication | None"] = relationship("ProjectApplication")
    parent_policy: Mapped["AutomationClassificationPolicy | None"] = relationship(
        "AutomationClassificationPolicy", remote_side=[id]
    )


class TestCaseAutomationClassification(TimestampMixin, Base):
    """A versioned automation-classification recommendation/decision for a
    test case. Approving never mutates a row in place — it writes a NEW row
    chained via `parent_classification_id` (same ADR-001 pattern as
    AutomationScript) so an approved version is immutable and superseded
    versions stay in history. `is_current` marks the head of the chain.
    """

    __tablename__ = "test_case_automation_classifications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Snapshot of TestCase.version at classification time — if the live
    # TestCase.version has since advanced, this classification is stale.
    test_case_version: Mapped[int] = mapped_column(Integer, nullable=False)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # No index=True here — the table/column name combo exceeds Postgres's
    # 63-char identifier limit for the auto-generated "ix_..." name. Indexed
    # explicitly below as "ix_test_case_automation_classifications_parent_id".
    parent_classification_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_case_automation_classifications.id", ondelete="SET NULL"), nullable=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # candidateStatus: NOT_EVALUATED | RECOMMENDED | CONDITIONAL |
    # NOT_RECOMMENDED | BLOCKED | DEFERRED | APPROVED | POLICY_STALE |
    # RECLASSIFICATION_REQUIRED
    candidate_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="NOT_EVALUATED", server_default="NOT_EVALUATED"
    )

    primary_adapter: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supporting_adapters: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    mandatory_validators: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    optional_validators: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    discovery_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # recommendedDiscoveryMode: GUIDED_USER | FREE_USER_ACTION | SUPERVISED_AGENT
    recommended_discovery_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)

    complexity_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    automation_value_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_factors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    required_evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    required_capabilities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    deterministic_blockers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    advisory_warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    matched_rules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    policy_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_classification_policies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Provenance (model/prompt/tool versions) lives on the AgentRun row —
    # not duplicated here.
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)

    # reviewStatus: PENDING_REVIEW | CHANGES_REQUESTED | REVIEWED | APPROVED | REJECTED
    review_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING_REVIEW", server_default="PENDING_REVIEW"
    )
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project")
    test_case: Mapped["TestCase"] = relationship("TestCase")
    policy: Mapped["AutomationClassificationPolicy | None"] = relationship("AutomationClassificationPolicy")
    parent_classification: Mapped["TestCaseAutomationClassification | None"] = relationship(
        "TestCaseAutomationClassification", remote_side=[id]
    )
    corrections: Mapped[list["ClassificationFieldCorrection"]] = relationship(
        "ClassificationFieldCorrection", back_populates="classification"
    )


class ClassificationFieldCorrection(TimestampMixin, Base):
    """Per-field reviewer correction on a classification — preserves the
    original AI value alongside the reviewer's value, mirroring
    TestCaseHistory's field-level audit shape.
    """

    __tablename__ = "classification_field_corrections"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    classification_id: Mapped[int] = mapped_column(
        ForeignKey("test_case_automation_classifications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ai_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    classification: Mapped["TestCaseAutomationClassification"] = relationship(
        "TestCaseAutomationClassification", back_populates="corrections"
    )


class ClassificationAuditEvent(TimestampMixin, Base):
    """Residual audit log for classification lifecycle events not already
    captured by ApprovalAction (approve/reject/defer/request-changes),
    ClassificationFieldCorrection (reviewer corrections), or AgentRun/AgentLog
    (job provenance/progress) — e.g. policy resolved, policy-stale
    transition, UI-015 readiness refusal.
    """

    __tablename__ = "classification_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    classification_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_case_automation_classifications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="platform")


Index(
    "ix_automation_classification_policies_scope",
    AutomationClassificationPolicy.project_id,
    AutomationClassificationPolicy.application_id,
    AutomationClassificationPolicy.status,
)
Index(
    "ix_test_case_automation_classifications_current",
    TestCaseAutomationClassification.test_case_id,
    TestCaseAutomationClassification.is_current,
)
Index(
    "ix_test_case_automation_classifications_parent_id",
    TestCaseAutomationClassification.parent_classification_id,
)
