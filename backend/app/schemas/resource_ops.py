import uuid
from datetime import datetime, date
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, EmailStr


class LDAPLoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    domain: str = Field("CORP.NET", min_length=1)


# ── Resource Directory Schemas ───────────────────────────────────────────────

class ResourceBase(BaseModel):
    ldap_username: str
    domain: str
    directory_object_id: str | None = None
    user_principal_name: str | None = None
    corporate_email: EmailStr
    display_name: str
    employee_id: str | None = None
    department: str | None = None
    team: str | None = None
    manager_ldap_username: str | None = None
    employment_type: str = "Internal"
    seniority: str | None = None
    qa_domain: str | None = None
    product_group: str | None = None
    product: str | None = None
    system: str | None = None
    skills: dict[str, list[str]] | None = None
    work_location: str | None = None
    time_zone: str = "UTC"
    standard_work_hours: float = 8.0
    status: str = "active"
    consent_status: str = "pending"
    device_telemetry_status: str = "disabled"


class ResourceCreate(ResourceBase):
    user_id: int | None = None


class ResourceUpdate(BaseModel):
    user_id: int | None = None
    display_name: str | None = None
    corporate_email: EmailStr | None = None
    department: str | None = None
    team: str | None = None
    manager_ldap_username: str | None = None
    employment_type: str | None = None
    seniority: str | None = None
    qa_domain: str | None = None
    product_group: str | None = None
    product: str | None = None
    system: str | None = None
    skills: dict[str, list[str]] | None = None
    work_location: str | None = None
    time_zone: str | None = None
    standard_work_hours: float | None = None
    status: str | None = None
    consent_status: str | None = None
    consent_date: datetime | None = None
    device_telemetry_status: str | None = None


class ResourceRead(ResourceBase):
    model_config = ConfigDict(from_attributes=True)

    person_id: uuid.UUID
    user_id: int | None = None
    last_directory_sync_at: datetime | None = None
    consent_date: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ── Identity Mapping Schemas ─────────────────────────────────────────────────

class ResourceIdentityMappingBase(BaseModel):
    source_system: str
    external_user_id: str
    external_username: str | None = None
    external_email: str | None = None
    external_display_name: str | None = None
    external_project_context: str | None = None
    mapping_confidence: float = 1.0
    mapping_method: str = "auto_sync"
    status: str = "approved"


class ResourceIdentityMappingCreate(ResourceIdentityMappingBase):
    resource_id: uuid.UUID


class ResourceIdentityMappingUpdate(BaseModel):
    resource_id: uuid.UUID | None = None
    status: str | None = None
    approved_by: int | None = None
    mapping_confidence: float | None = None
    audit_trail: dict[str, Any] | None = None


class ResourceIdentityMappingRead(ResourceIdentityMappingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_id: uuid.UUID
    last_verified_date: datetime | None = None
    created_by: int | None = None
    approved_by: int | None = None
    audit_trail: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


# ── Daily Work Plan Schemas ──────────────────────────────────────────────────

class DailyWorkPlanBase(BaseModel):
    date: date
    product: str | None = None
    system: str | None = None
    qa_domain: str | None = None
    sprint: str | None = None
    release: str | None = None
    test_cycle: str | None = None
    task_id: str | None = None
    task_title: str
    task_type: str
    linked_jira_issue: str | None = None
    linked_rtc_work_item: str | None = None
    linked_rqm_test_artifact: str | None = None
    linked_nxtqa_entity_id: str | None = None
    linked_portal_ref: str | None = None
    planned_start_time: datetime | None = None
    planned_end_time: datetime | None = None
    estimated_effort: float = 0.0
    achieved_effort: float = 0.0
    remaining_effort: float = 0.0
    blocked_effort: float = 0.0
    unplanned_effort: float = 0.0
    priority: str = "Medium"
    planned_deliverable: str | None = None
    dependency: str | None = None
    risk: str | None = None
    status: str = "Planned"
    blocker_reason: str | None = None
    employee_comments: str | None = None
    lead_validation: str = "pending"
    manager_validation: str = "pending"


class DailyWorkPlanCreate(DailyWorkPlanBase):
    resource_id: uuid.UUID
    project_id: int


class DailyWorkPlanUpdate(BaseModel):
    product: str | None = None
    system: str | None = None
    qa_domain: str | None = None
    sprint: str | None = None
    release: str | None = None
    test_cycle: str | None = None
    task_title: str | None = None
    task_type: str | None = None
    linked_jira_issue: str | None = None
    linked_rtc_work_item: str | None = None
    linked_rqm_test_artifact: str | None = None
    linked_nxtqa_entity_id: str | None = None
    linked_portal_ref: str | None = None
    planned_start_time: datetime | None = None
    planned_end_time: datetime | None = None
    estimated_effort: float | None = None
    achieved_effort: float | None = None
    remaining_effort: float | None = None
    blocked_effort: float | None = None
    unplanned_effort: float | None = None
    priority: str | None = None
    planned_deliverable: str | None = None
    dependency: str | None = None
    risk: str | None = None
    status: str | None = None
    blocker_reason: str | None = None
    employee_comments: str | None = None
    lead_validation: str | None = None
    manager_validation: str | None = None


class DailyWorkPlanRead(DailyWorkPlanBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_id: uuid.UUID
    project_id: int
    created_at: datetime
    updated_at: datetime


# ── Work Evidence Event Schemas ──────────────────────────────────────────────

class WorkEvidenceEventBase(BaseModel):
    tenant_id: int | None = None
    source_system: str
    source_event_id: str
    source_user_id: str | None = None
    source_username: str | None = None
    event_category: str
    event_type: str
    timestamp: datetime
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_minutes: int = 0
    actual_effort_hours: float = 0.0
    linked_task_id: int | None = None
    linked_jira_issue_key: str | None = None
    linked_rtc_work_item_id: str | None = None
    linked_rqm_artifact_id: str | None = None
    linked_nxtqa_entity_id: str | None = None
    linked_portal_ref: str | None = None
    project: str | None = None
    product: str | None = None
    system: str | None = None
    qa_domain: str | None = None
    sprint: str | None = None
    release: str | None = None
    test_cycle: str | None = None
    evidence_confidence: float = 1.0
    evidence_status: str = "unmapped"
    privacy_classification: str = "Public"
    raw_source_metadata: dict[str, Any] | None = None


class WorkEvidenceEventCreate(WorkEvidenceEventBase):
    project_id: int
    resource_id: uuid.UUID


class WorkEvidenceEventRead(WorkEvidenceEventBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    resource_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ── Integration Connection Schemas ───────────────────────────────────────────

class IntegrationConnectionBase(BaseModel):
    system_type: str
    name: str
    base_url: str
    auth_type: str = "credentials"
    username: str | None = None
    is_active: bool = True
    status: str = "disconnected"
    config: dict[str, Any] | None = None


class IntegrationConnectionCreate(IntegrationConnectionBase):
    project_id: int | None = None
    password: str | None = None
    token: str | None = None


class IntegrationConnectionUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    auth_type: str | None = None
    username: str | None = None
    password: str | None = None
    token: str | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None
    status: str | None = None


class IntegrationConnectionRead(IntegrationConnectionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None = None
    last_sync_at: datetime | None = None
    created_by: int
    created_at: datetime
    updated_at: datetime


# ── AI Estimate Schemas ───────────────────────────────────────────────────────

class AIEstimateRequest(BaseModel):
    project_id: int
    activity_type: str
    complexity: str = "Medium"
    inputs: dict[str, Any]


class AIEstimateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    activity_type: str
    complexity: str
    inputs: dict[str, Any]
    baseline_hours: float
    historical_hours_adj: float
    complexity_hours_adj: float
    risk_hours_adj: float
    team_env_hours_adj: float
    optimistic_hours: float
    most_likely_hours: float
    pessimistic_hours: float
    recommended_hours: float
    pert_hours: float
    confidence_score: float
    assumptions: str | None = None
    risk_factors: str | None = None
    historical_context: dict[str, Any] | None = None
    suggested_breakdown: dict[str, Any] | None = None
    status: str
    approved_hours: float | None = None
    actual_hours: float | None = None
    calibration_error: float | None = None
    created_at: datetime
    updated_at: datetime


class AIEstimateUpdate(BaseModel):
    status: str | None = None
    approved_hours: float | None = None
    actual_hours: float | None = None
    overridden_by: int | None = None
