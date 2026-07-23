from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CurrentStepOut(BaseModel):
    text: str | None
    step_ref: str | None


class EligibleTestCaseOut(BaseModel):
    test_case_id: int
    display_id: str
    title: str
    requirement_ref: str | None
    scenario_ref: str | None
    approval_status: str
    eligible: bool
    blocking_reason: str | None


class DiscoverySessionCreateRequest(BaseModel):
    application_id: int
    environment: str
    mode: str = "GUIDED_USER"
    test_case_id: int | None = None
    purpose: str | None = None
    browser_target: str | None = None
    framework: str = "playwright"
    auth_profile_reference: str | None = None
    capture_options: dict[str, Any] | None = None
    evidence_policy: dict[str, Any] | None = None
    allowed_hosts: list[str] | None = None
    correlation_id: str | None = None


class DiscoverySessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    application_id: int
    environment: str
    mode: str
    status: str
    browser_target: str | None
    framework: str
    auth_profile_reference: str | None
    test_case_id: int | None
    test_case_version: int | None
    requirement_ref: str | None
    ppm_ref: str | None
    journey_ref: str | None
    scenario_ref: str | None
    purpose: str | None
    evidence_policy: dict
    capture_options: dict
    allowed_hosts: list
    owner_id: int | None
    created_by: int | None
    started_at: datetime | None
    terminal_at: datetime | None
    terminal_reason: str | None
    failure_detail: str | None
    latest_checkpoint_id: int | None
    draft_model_version_id: int | None
    correlation_id: str | None
    current_step_index: int
    resume_state_classification: str | None
    metadata_: dict | None = None
    created_at: datetime
    updated_at: datetime


class DiscoverySessionCommandRequest(BaseModel):
    command: str
    idempotency_key: str
    reason: str | None = None
    params: dict[str, Any] | None = None


class ReadinessCheckOut(BaseModel):
    name: str
    passed: bool
    detail: str


class ReadinessResultOut(BaseModel):
    ready: bool
    checks: list[ReadinessCheckOut]


class DiscoveryActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    sequence: int
    actor: str
    test_step_ref: str | None
    action_family: str
    target_semantic: str | None
    target_screen_ref: str | None
    occurred_at: datetime
    duration_ms: int | None
    evidence_refs: list
    locator_confidence: int | None
    inclusion_state: str
    issue_note: str | None
    reviewer_note: str | None
    input_binding: dict | None
    # Includes accessibility_snapshot_excerpt — Free mode's target-ref picker
    # reads this to show the user what's actually on the page right now.
    post_state: dict | None


class DiscoveryActionCorrectionRequest(BaseModel):
    inclusion_state: str
    reviewer_note: str | None = None
    reason: str | None = None
    # Free-text reference to a test case/step this action maps to during
    # review (Section 5.2 — "may be mapped to a test case during review
    # before publication"). Mapping only, no publish workflow exists yet.
    mapped_test_step_ref: str | None = None


class RecordFreeActionRequest(BaseModel):
    idempotency_key: str
    action_family: str
    target_ref: str | None = None
    target_semantic: str | None = None
    input_text: str | None = None
    url: str | None = None


class DiscoveryCheckpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    sequence: int
    state_at_checkpoint: str
    action_position: int | None
    sanitized_url: str | None
    sanitized_screen: str | None
    resumable: bool
    expires_at: datetime | None
    created_by_actor: str
    created_at: datetime


class DiscoveryCaptureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    capture_type: str
    checksum: str | None
    source: str | None
    captured_at: datetime
    redaction_state: str
    retention_state: str


class DiscoverySessionEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    actor_id: int | None
    actor_type: str
    previous_state: str | None
    new_state: str
    command: str | None
    reason: str | None
    idempotency_key: str | None
    correlation_id: str | None
    occurred_at: datetime


class ResumeValidationOut(BaseModel):
    classification: str
    detail: str
    allowed_recovery_options: list[str]
