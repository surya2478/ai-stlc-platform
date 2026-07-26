"""Schemas for UI-018 Automation Workspace (Automation Test Suite)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AutomationSuiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: str | None
    tags: list[str]
    status: str
    version: int
    parent_suite_id: int | None
    is_current: bool
    default_environment: str | None
    owner_id: int | None
    created_by: int | None
    archived_by: int | None
    archived_at: datetime | None
    submitted_by: int | None
    submitted_at: datetime | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    approved_by: int | None
    approved_at: datetime | None
    published_by: int | None
    published_at: datetime | None
    decision_reason: str | None
    last_evaluated_at: datetime | None
    last_inheritance_sync_at: datetime | None
    members_total: int
    members_included: int
    members_ready: int
    members_blocked: int
    members_manual_only: int
    members_drifted: int
    gaps_critical_open: int
    gaps_warning_open: int
    conflicts_open: int
    created_at: datetime
    updated_at: datetime


class AutomationSuiteListItem(BaseModel):
    id: int
    name: str
    description: str | None
    tags: list[str]
    status: str
    default_environment: str | None
    members_total: int
    members_included: int
    members_ready: int
    members_blocked: int
    members_manual_only: int
    members_drifted: int
    gaps_critical_open: int
    gaps_warning_open: int
    conflicts_open: int
    frameworks: list[str]
    application_count: int
    owner_id: int | None
    last_evaluated_at: datetime | None
    updated_at: datetime
    created_at: datetime


class AutomationSuiteMemberOut(BaseModel):
    id: int
    test_case_id: int
    test_case_reference: str | None
    title: str | None
    test_case_status: str | None
    execution_mode: str | None
    priority: str | None
    automation_status: str | None
    inclusion_status: str
    planned_sequence: int | None
    source_system: str
    source_reference: str | None
    member_status: str
    readiness_checks_passed: int
    readiness_checks_total: int
    last_evaluated_at: datetime | None
    resolved_application_id: int | None
    resolved_framework: str | None
    resolved_environment: str | None
    resolved_script_id: int | None
    exclusion_reason: str | None


class AutomationSuiteGapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    suite_id: int
    suite_test_case_id: int | None
    test_case_id: int | None
    gap_type: str
    scope: str
    category: str
    severity: str
    stage: str
    reason: str
    remediation: str | None
    evidence: dict[str, Any]
    status: str
    resolution_action: str | None
    reviewer_notes: str | None
    resolved_by: int | None
    resolved_at: datetime | None
    auto_closed: bool
    first_detected_at: datetime
    last_detected_at: datetime


class AutomationSuiteActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    suite_id: int
    suite_test_case_id: int | None
    event_type: str
    actor_id: int | None
    reason: str | None
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    created_at: datetime


class SelectableTestCaseOut(BaseModel):
    id: int
    test_case_reference: str | None
    title: str | None
    objective: str | None
    status: str | None
    test_type: str | None
    priority: str | None
    is_critical: bool | None
    execution_mode: str | None
    automation_status: str | None
    automation_candidate: bool | None
    application_id: int | None
    requirement_id: int | None
    test_suite_id: int | None
    linked_release_version: str | None
    linked_script_count: int
    frameworks: list[str]
    mapping_status: str


# ─── Requests ─────────────────────────────────────────────────────────────────

class CreateSuiteRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    test_case_ids: list[int] = Field(default_factory=list)
    test_suite_ids: list[int] = Field(default_factory=list)
    default_environment: str | None = None
    # One per wizard session, so a refresh or double-submit replays onto the
    # same suite instead of creating a second one.
    idempotency_key: str | None = Field(default=None, max_length=255)


class UpdateSuiteRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    tags: list[str] | None = None


class SetDefaultEnvironmentRequest(BaseModel):
    environment: str | None = Field(default=None, max_length=100)


class AddMembersRequest(BaseModel):
    test_case_ids: list[int] = Field(default_factory=list)
    test_suite_ids: list[int] = Field(default_factory=list)


class UpdateMemberRequest(BaseModel):
    inclusion_status: str | None = None
    planned_sequence: int | None = None
    exclusion_reason: str | None = None


class ResolveGapRequest(BaseModel):
    resolution_action: str
    reviewer_notes: str | None = None


class ApproveExceptionRequest(BaseModel):
    reason: str = Field(min_length=1)


class PreviewInheritanceRequest(BaseModel):
    test_case_ids: list[int] = Field(default_factory=list)
    default_environment: str | None = None


# ─── Phase B ──────────────────────────────────────────────────────────────────

class CreateExecutionGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    framework: str | None = None
    environment: str | None = None
    notes: str | None = None


class SplitExecutionGroupsRequest(BaseModel):
    dimension: str = Field(description="framework | environment | application")


class AssignExecutionGroupRequest(BaseModel):
    execution_group_id: int | None = None


class DecisionRequest(BaseModel):
    reason: str | None = None


class RequiredReasonRequest(BaseModel):
    reason: str = Field(min_length=1)


class AutomationSuiteSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    suite_id: int
    suite_version: int
    members: list[dict[str, Any]]
    execution_groups: list[dict[str, Any]]
    summary: dict[str, Any]
    checksum: str
    created_by: int | None
    created_at: datetime
