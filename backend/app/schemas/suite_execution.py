"""Request/response schemas for UI-046 Suite Execution Command Center.

Response shaping matters here more than usual, for two reasons the contract calls
out explicitly:

* **Section 4.3 count reconciliation.** The summary carries a `reconciled` flag
  computed on the server. The UI is required to show "Status data delayed" rather
  than a total it cannot justify, so the server must state whether the numbers
  add up rather than leaving the client to guess.

* **Section 14.14 masking.** Evidence metadata is returned; evidence *content* is
  not. Payload entries (console and network captures) are summarised by count,
  and artifacts are referenced by id for an authenticated download that applies
  the masking pass. Returning raw captured payloads inline would leak whatever a
  request header happened to contain.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.execution_command_center import CONTROL_ACTIONS


class ReadinessCheckOut(BaseModel):
    axis: str
    name: str
    passed: bool
    detail: str
    blocking: bool


class ReadinessOut(BaseModel):
    ready: bool
    axes: dict[str, bool]
    checks: list[ReadinessCheckOut]
    blockers: list[ReadinessCheckOut]


class RunIdentityOut(BaseModel):
    """Contract Section 3 — everything the header band and its detail popover need."""

    id: int
    execution_id: str
    project_id: int
    suite_id: int | None
    suite_name: str | None
    # The immutable snapshot version actually executing, which is the number the
    # operator must be able to trust.
    suite_snapshot_id: int | None
    suite_version: int | None
    snapshot_checksum: str | None
    environment: str | None
    execution_purpose: str | None
    frameworks: list[str]
    trigger_source: str | None
    triggered_by: int | None
    triggered_by_name: str | None
    lifecycle_state: str | None
    outcome: str | None
    run_version: int
    pending_command: str | None
    correlation_id: str | None
    parallel_limit: int
    started_at: datetime | None
    completed_at: datetime | None
    readiness: ReadinessOut | None
    # Section 3.1 — computed server-side so the UI cannot drift from the state
    # machine on what the primary action should be.
    primary_action: str
    is_terminal: bool
    latest_sequence: int
    # What this user may actually do, so the UI disables rather than guesses.
    can_control: bool
    can_cancel: bool


class StatusCountsOut(BaseModel):
    passed: int = 0
    failed: int = 0
    inconclusive: int = 0
    blocked: int = 0
    environment_failure: int = 0
    data_failure: int = 0
    automation_failure: int = 0
    policy_blocked: int = 0
    skipped: int = 0
    running: int = 0
    queued: int = 0


class RunSummaryOut(BaseModel):
    """Contract Section 4 — the status command strip."""

    total: int
    completed: int
    completion_percent: float
    counts: StatusCountsOut
    # Section 4.3. False means the UI must show "Status data delayed" instead of
    # a total it cannot justify.
    reconciled: bool
    reconciliation_detail: str | None
    parallel_in_use: int
    parallel_allowed: int
    queue_depth: int
    evidence_captured: int
    evidence_required: int
    environment_ready: bool
    operational_message: str


class ItemOut(BaseModel):
    """One row of the execution matrix (Section 6.1)."""

    id: int
    order_index: int
    test_case_id: int | None
    test_case_key: str | None
    title: str | None
    journey: str | None
    application_id: int | None
    priority: str | None
    framework: str | None
    runner_name: str | None
    lifecycle_state: str
    result: str
    attempt: int
    attempts_allowed: int
    # `steps_total` is real: the orchestrator writes it from the Automation IR
    # at seeding time. `steps_completed` is deliberately NOT exposed — no runner
    # reports per-step progress, so the column never moves off zero, and
    # publishing it made the API claim a progress figure that does not exist.
    # The column stays for the adapter step telemetry that will populate it.
    steps_total: int
    evidence_captured: int
    evidence_required: int
    evidence_total_captured: int
    assertions_passed: int
    assertions_total: int
    duration_ms: int | None
    attention_reason: str | None
    started_at: datetime | None
    completed_at: datetime | None


class ItemPageOut(BaseModel):
    items: list[ItemOut]
    # Cursor, not offset: Section 14.13 requires this to stay usable at 10,000
    # items, and an offset scan degrades as the operator pages deeper.
    next_cursor: int | None
    total_matching: int


class StepOut(BaseModel):
    id: int
    step_number: int
    action_text: str | None
    expected_text: str | None
    actual_text: str | None
    status: str
    application_context: str | None
    elapsed_ms: int | None
    started_at: datetime | None
    completed_at: datetime | None


class AssertionOut(BaseModel):
    id: int
    source: str
    description: str
    expected_value: str | None
    actual_value: str | None
    mandatory: bool
    # None means not evaluated — the UI shows a pending count rather than
    # collapsing it into a failure.
    passed: bool | None
    # How the verdict was reached: "runner_verdict" is inferred from the
    # test-level result, "reported" is a per-assertion evaluation by the
    # adapter. NULL whenever `passed` is NULL.
    evaluation_source: str | None = None
    evaluated_at: datetime | None


class EvidenceOut(BaseModel):
    """Metadata only — never content. See the module docstring."""

    id: int
    evidence_type: str
    status: str
    mandatory: bool
    summary: str | None
    # A count, not the entries. The payload can contain request headers.
    payload_entry_count: int | None
    size_bytes: int | None
    has_artifact: bool
    sanitized: bool
    # Why `sanitized` reads as it does: "masked" means the pass rewrote the
    # content, "not_maskable" means no text pass applies (screenshot, video,
    # trace) and serving it is a policy decision.
    redaction_state: str = "pending"
    checksum_sha256: str | None = None
    content_type: str | None = None
    downloadable: bool = False
    unavailable_reason: str | None
    captured_at: datetime | None


class ItemDetailOut(BaseModel):
    item: ItemOut
    # Frozen provenance from the snapshot: the versions this actually ran against.
    script_id: int | None
    test_case_version: int | None
    environment: str | None
    session_id: str | None
    retry_reason: str | None
    error_message: str | None
    snapshot_member: dict[str, Any]
    current_step: StepOut | None
    steps: list[StepOut]
    assertions: list[AssertionOut]
    evidence: list[EvidenceOut]
    quorum_met: bool
    quorum_missing: list[str]
    # The most recent captured screenshot, surfaced as last-captured rather than
    # as a live feed — contract Section 2.1.6.
    latest_screenshot_evidence_id: int | None
    latest_screenshot_captured_at: datetime | None


class EventOut(BaseModel):
    sequence: int
    event_type: str
    message: str
    item_id: int | None
    payload: dict[str, Any] | None
    occurred_at: datetime


class EventPageOut(BaseModel):
    events: list[EventOut]
    # The client stores this and passes it back as `after`. Dense and ordered, so
    # a reconnect replays exactly the gap, once each.
    latest_sequence: int
    # Age of the newest backend event, which is what the connection badge and the
    # latency indicator are derived from — there is no socket to report on.
    newest_event_age_seconds: float | None
    has_more: bool


class ControlRequest(BaseModel):
    action: Literal[
        "PAUSE_AFTER_CURRENT", "RESUME", "STOP_GRACEFULLY", "CANCEL_NOW", "EMERGENCY_STOP"
    ]
    reason: str | None = Field(default=None, max_length=2000)
    # Optional so a caller that does not track versions still works; when present
    # a mismatch is a 409 rather than a silently applied command.
    expectedRunVersion: int | None = None

    @field_validator("action")
    @classmethod
    def _known_action(cls, value: str) -> str:
        # Belt and braces: the Literal above and the model vocabulary must not be
        # able to drift apart.
        if value not in CONTROL_ACTIONS:
            raise ValueError(f"Unknown control action '{value}'.")
        return value


class ControlResponse(BaseModel):
    commandId: str
    accepted: bool
    currentState: str
    runVersion: int
    message: str


class StartRunRequest(BaseModel):
    environment: str | None = None
    execution_purpose: str | None = Field(default=None, max_length=255)
