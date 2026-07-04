import uuid
from datetime import datetime, date
from sqlalchemy import Boolean, DateTime, Date, ForeignKey, Integer, String, Text, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Resource(TimestampMixin, Base):
    __tablename__ = "resources"

    person_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    ldap_username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    domain: Mapped[str] = mapped_column(String(100), nullable=False)
    directory_object_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    user_principal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    corporate_email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    employee_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    department: Mapped[str | None] = mapped_column(String(150), nullable=True)
    team: Mapped[str | None] = mapped_column(String(150), nullable=True)
    manager_ldap_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(50), default="Internal") # Internal, Vendor, Contractor, Partner
    seniority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    qa_domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product: Mapped[str | None] = mapped_column(String(100), nullable=True)
    system: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skills: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    work_location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    time_zone: Mapped[str] = mapped_column(String(50), default="UTC")
    standard_work_hours: Mapped[float] = mapped_column(Float, default=8.0)
    status: Mapped[str] = mapped_column(String(30), default="active") # active, inactive, suspended
    last_directory_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_status: Mapped[str] = mapped_column(String(30), default="pending")
    consent_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_telemetry_status: Mapped[str] = mapped_column(String(30), default="disabled")

    user: Mapped["User"] = relationship("User", lazy="select")


class ResourceIdentityMapping(TimestampMixin, Base):
    __tablename__ = "resource_identity_mappings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.person_id", ondelete="CASCADE"), nullable=False, index=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True) # Jira, RTC, RQM, Portal, Database, Agent
    external_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    external_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_project_context: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mapping_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    mapping_method: Mapped[str] = mapped_column(String(50), default="auto_sync") # auto_sync, email_match, manual
    status: Mapped[str] = mapped_column(String(30), default="approved") # pending_review, approved, rejected
    last_verified_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    audit_trail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    resource: Mapped["Resource"] = relationship("Resource", lazy="select")


class IntegrationConnection(TimestampMixin, Base):
    __tablename__ = "integration_connections"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    system_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True) # LDAP, RTC, RQM, Jira, Portal, Database
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(50), default="credentials") # credentials, token, oauth
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(50), default="disconnected") # connected, error, disconnected
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class DailyWorkPlan(TimestampMixin, Base):
    __tablename__ = "daily_work_plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.person_id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    product: Mapped[str | None] = mapped_column(String(100), nullable=True)
    system: Mapped[str | None] = mapped_column(String(100), nullable=True)
    qa_domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sprint: Mapped[str | None] = mapped_column(String(100), nullable=True)
    release: Mapped[str | None] = mapped_column(String(100), nullable=True)
    test_cycle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    task_title: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    
    linked_jira_issue: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linked_rtc_work_item: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linked_rqm_test_artifact: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linked_nxtqa_entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linked_portal_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    planned_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_effort: Mapped[float] = mapped_column(Float, default=0.0)
    achieved_effort: Mapped[float] = mapped_column(Float, default=0.0)
    remaining_effort: Mapped[float] = mapped_column(Float, default=0.0)
    blocked_effort: Mapped[float] = mapped_column(Float, default=0.0)
    unplanned_effort: Mapped[float] = mapped_column(Float, default=0.0)
    
    priority: Mapped[str] = mapped_column(String(30), default="Medium")
    planned_deliverable: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dependency: Mapped[str | None] = mapped_column(String(255), nullable=True)
    risk: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="Planned") # Planned, In Progress, Blocked, Done
    blocker_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    employee_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    lead_validation: Mapped[str] = mapped_column(String(30), default="pending") # pending, approved, rejected
    manager_validation: Mapped[str] = mapped_column(String(30), default="pending") # pending, approved, rejected

    resource: Mapped["Resource"] = relationship("Resource", lazy="select")


class WorkEvidenceEvent(TimestampMixin, Base):
    __tablename__ = "work_evidence_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.person_id", ondelete="CASCADE"), nullable=False, index=True)
    
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True) # Jira, RTC, RQM, nxtQA, Portal, Database, Agent
    source_event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    event_category: Mapped[str] = mapped_column(String(100), nullable=False) # Planning, Test Design, Manual Execution, AI Execution, etc.
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    actual_effort_hours: Mapped[float] = mapped_column(Float, default=0.0)
    
    linked_task_id: Mapped[int | None] = mapped_column(ForeignKey("daily_work_plans.id", ondelete="SET NULL"), nullable=True)
    linked_jira_issue_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linked_rtc_work_item_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linked_rqm_artifact_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linked_nxtqa_entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linked_portal_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    project: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product: Mapped[str | None] = mapped_column(String(100), nullable=True)
    system: Mapped[str | None] = mapped_column(String(100), nullable=True)
    qa_domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sprint: Mapped[str | None] = mapped_column(String(100), nullable=True)
    release: Mapped[str | None] = mapped_column(String(100), nullable=True)
    test_cycle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    evidence_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_status: Mapped[str] = mapped_column(String(30), default="unmapped") # unmapped, auto_mapped, manually_mapped, rejected
    privacy_classification: Mapped[str] = mapped_column(String(50), default="Public")
    raw_source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    resource: Mapped["Resource"] = relationship("Resource", lazy="select")


class AIEstimate(TimestampMixin, Base):
    __tablename__ = "ai_estimates"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    complexity: Mapped[str] = mapped_column(String(30), default="Medium") # Low, Medium, High
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    baseline_hours: Mapped[float] = mapped_column(Float, default=0.0)
    historical_hours_adj: Mapped[float] = mapped_column(Float, default=0.0)
    complexity_hours_adj: Mapped[float] = mapped_column(Float, default=0.0)
    risk_hours_adj: Mapped[float] = mapped_column(Float, default=0.0)
    team_env_hours_adj: Mapped[float] = mapped_column(Float, default=0.0)
    
    optimistic_hours: Mapped[float] = mapped_column(Float, default=0.0)
    most_likely_hours: Mapped[float] = mapped_column(Float, default=0.0)
    pessimistic_hours: Mapped[float] = mapped_column(Float, default=0.0)
    recommended_hours: Mapped[float] = mapped_column(Float, default=0.0)
    pert_hours: Mapped[float] = mapped_column(Float, default=0.0)
    
    confidence_score: Mapped[float] = mapped_column(Float, default=0.8)
    assumptions: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_factors: Mapped[str | None] = mapped_column(Text, nullable=True)
    historical_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    suggested_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    status: Mapped[str] = mapped_column(String(30), default="suggested") # suggested, approved, rejected, overridden
    overridden_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibration_error: Mapped[float | None] = mapped_column(Float, nullable=True)
