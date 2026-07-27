"""UI-019 Live Recorder request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


# ── Session ──────────────────────────────────────────────────────────────────


class RecordingCreateRequest(BaseModel):
    suite_id: int
    test_case_id: int
    recording_mode: str = "GUIDED_TEST_CASE"
    # Optional override of the inherited environment. Everything else —
    # application, framework, traceability — is resolved from the suite member
    # and deliberately not accepted here (Section 4).
    environment: str | None = None
    correlation_id: str | None = None


class RecordingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    suite_id: int | None
    suite_member_id: int | None
    test_case_id: int | None
    test_case_version: int | None
    application_id: int
    environment: str
    framework: str
    status: str
    recording_mode: str | None
    recording_origin: str
    recording_version: int
    parent_recording_id: int | None
    ir_status: str
    current_step_index: int
    purpose: str | None
    requirement_ref: str | None
    scenario_ref: str | None
    started_at: datetime | None
    terminal_at: datetime | None
    terminal_reason: str | None
    failure_detail: str | None
    resume_state_classification: str | None
    latest_checkpoint_id: int | None
    created_at: datetime
    updated_at: datetime


class RecordingCommandRequest(BaseModel):
    command: str
    idempotency_key: str
    reason: str | None = None
    params: dict[str, Any] | None = None


class RecordingReasonRequest(BaseModel):
    reason: str


class PreconditionOut(BaseModel):
    name: str
    passed: bool
    blocking: bool
    detail: str
    remediation_href: str | None


class PreconditionResultOut(BaseModel):
    ready: bool
    checks: list[PreconditionOut]
    blockers: list[PreconditionOut]
    advisories: list[PreconditionOut]


# ── Steps and mapping ────────────────────────────────────────────────────────


class RecorderStepOut(BaseModel):
    step_key: str
    source_step_index: int | None
    action_text: str | None
    expected_result: str | None
    status: str
    recorded_action_count: int
    checkpoint_count: int
    accepted_checkpoint_count: int
    skip_reason: str | None
    is_discovered_substep: bool
    parent_step_key: str | None
    status_reason: str


class StepStatusRequest(BaseModel):
    status: str
    reason: str | None = None


class DiscoveredSubstepRequest(BaseModel):
    parent_step_key: str
    label: str


class MapActionRequest(BaseModel):
    # Null unmaps the action, returning it to the unmapped list.
    step_key: str | None = None


class UpdateMappingRequest(BaseModel):
    lifecycle_phase: str | None = None
    excluded_from_ir: bool | None = None
    exclusion_reason: str | None = None
    review_state: str | None = None


class StepMappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action_id: int
    step_key: str
    mapping_source: str
    confidence: int | None
    review_state: str
    lifecycle_phase: str | None
    excluded_from_ir: bool
    exclusion_reason: str | None


# ── Actions ──────────────────────────────────────────────────────────────────


class RecordActionRequest(BaseModel):
    idempotency_key: str
    action_family: str
    target_ref: str | None = None
    target_semantic: str | None = None
    input_text: str | None = None
    url: str | None = None
    # The step new actions attach to. Omitted means "whatever the recorder
    # resolves as active", which is what the UI sends by default.
    active_step_key: str | None = None


class RecordedActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sequence: int
    actor: str
    action_family: str
    target_semantic: str | None
    test_step_ref: str | None
    input_binding: dict | None
    occurred_at: datetime
    duration_ms: int | None
    evidence_refs: list
    locator_evidence: dict | None
    locator_confidence: int | None
    inclusion_state: str
    issue_note: str | None
    reviewer_note: str | None


# ── Checkpoints ──────────────────────────────────────────────────────────────


class CheckpointCreateRequest(BaseModel):
    checkpoint_type: str
    step_key: str | None = None
    action_id: int | None = None
    target: str | None = None
    expected_value: str | None = None
    expected_result_ref: str | None = None


class CheckpointReviewRequest(BaseModel):
    review_state: str
    expected_value: str | None = None


class CheckpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action_id: int | None
    step_key: str | None
    checkpoint_type: str
    target: str | None
    expected_value: str | None
    source: str
    review_state: str
    recommendation_reason: str | None
    expected_result_ref: str | None
    evidence_capture_id: int | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    created_at: datetime


# ── Segments ─────────────────────────────────────────────────────────────────


class SegmentTransitionRequest(BaseModel):
    application_id: int
    environment: str
    transition_reason: str


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sequence: int
    application_id: int
    environment: str
    framework: str | None
    adapter: str | None
    started_at: datetime
    ended_at: datetime | None
    start_action_sequence: int | None
    end_action_sequence: int | None
    transition_reason: str | None


# ── Data bindings ────────────────────────────────────────────────────────────


class DataBindingRequest(BaseModel):
    name: str
    classification: str
    action_id: int | None = None
    test_data_id: int | None = None
    secret_reference: str | None = None
    source_action_id: int | None = None
    environment_key: str | None = None
    sample_value: str | None = None


class DataBindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action_id: int | None
    name: str
    placeholder: str
    classification: str
    test_data_id: int | None
    secret_reference: str | None
    source_action_id: int | None
    environment_key: str | None
    sample_value: str | None


# ── Notes ────────────────────────────────────────────────────────────────────


class NoteCreateRequest(BaseModel):
    body: str
    scope: str = "session"
    step_key: str | None = None
    action_id: int | None = None
    checkpoint_id: int | None = None
    segment_id: int | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scope: str
    step_key: str | None
    action_id: int | None
    checkpoint_id: int | None
    segment_id: int | None
    body: str
    created_by: int | None
    created_at: datetime


# ── IR draft ─────────────────────────────────────────────────────────────────


class IrDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    suite_id: int | None
    test_case_id: int
    version: int
    is_current: bool
    status: str
    contract: dict
    contract_version: str
    source_action_ids: list
    readiness: dict
    generated_by: int | None
    created_at: datetime
