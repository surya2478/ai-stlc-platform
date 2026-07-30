"""UI-020/021/023 Automation Asset Workspace schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IrValidationError(BaseModel):
    """One pydantic error, already anchored to a field the editor can highlight."""

    field: str
    message: str
    type: str


class IrValidationSummary(BaseModel):
    step_count: int
    custom_step_count: int
    custom_step_indexes: list[int]
    locator_count: int
    assertion_count: int
    page_object_count: int
    binding_count: int
    ready_for_compile: bool


class IrValidationResult(BaseModel):
    valid: bool
    errors: list[IrValidationError] = Field(default_factory=list)
    summary: IrValidationSummary | None = None


class ValidateIrRequest(BaseModel):
    contract: dict[str, Any]


class SaveIrRequest(BaseModel):
    contract: dict[str, Any]
    # Which readiness entries this edit resolved. Explicit rather than inferred:
    # an entry disappears because the user resolved it, never because a
    # heuristic decided it looked fixed.
    resolved_readiness_kinds: list[str] = Field(default_factory=list)


class ReadinessItem(BaseModel):
    kind: str
    detail: str
    action_id: int | None = None
    checkpoint_id: int | None = None
    sequence: int | None = None


class IrDraftOut(BaseModel):
    id: int
    version: int
    is_current: bool
    status: str
    contract: dict[str, Any]
    contract_version: str
    readiness: dict[str, Any]
    source_action_ids: list[int]
    generated_by: int | None
    updated_at: Any | None = None


class IrVersionOut(BaseModel):
    id: int
    version: int
    is_current: bool
    status: str
    step_count: int
    custom_step_count: int
    unresolved_count: int
    generated_by: int | None
    created_at: Any | None = None


class PreconditionOut(BaseModel):
    code: str
    label: str
    met: bool
    detail: str


class AutonomyOut(BaseModel):
    """The machine axis. Never merged with the human approval axis."""

    autonomy_state: str
    approval_state: str
    verdict_state: str
    score: float | None
    threshold: int
    rubric_id: str
    held_reason: str | None
    would_approve: bool
    enabled: bool
    dimensions: dict[str, float] = Field(default_factory=dict)
    preconditions: list[PreconditionOut] = Field(default_factory=list)


class InheritedField(BaseModel):
    """A value resolved from an authoritative source, with that source named.

    Rendered read-only. Section 5 rule 4: inherited context is never re-entered.
    """

    value: str | None
    source: str | None
    available: bool = True
    reason: str | None = None


class AssetHeaderOut(BaseModel):
    member_id: int
    suite_id: int
    suite_name: str
    suite_version: int
    suite_status: str
    test_case_id: int
    test_case_display_id: str | None
    test_case_title: str | None
    requirement_id: int | None
    requirement_display_id: str | None
    application: InheritedField
    framework: InheritedField
    environment: InheritedField
    member_status: str


class TabState(BaseModel):
    """Whether a tab is reachable, and why not when it isn't.

    Section 6: a tab the asset has not reached is visible but disabled with the
    reason, never hidden.
    """

    enabled: bool
    reason: str | None = None


class ReadinessStripOut(BaseModel):
    """Section 10 — plain English state and exactly one primary action."""

    state: str
    message: str
    primary_action: str | None
    primary_action_target: str | None


class AssetOut(BaseModel):
    header: AssetHeaderOut
    readiness_strip: ReadinessStripOut
    tabs: dict[str, TabState]
    ir: IrDraftOut | None
    ir_validation: IrValidationResult | None
    autonomy: AutonomyOut
    script: dict[str, Any] | None
    # Contract Section 5 rule 6 / Section 22: anything absent is an explained
    # dash, never a zero.
    unavailable: dict[str, str] = Field(default_factory=dict)


class ElementCatalogueOut(BaseModel):
    declared: list[dict[str, Any]]
    available: list[dict[str, Any]]
    element_required_actions: list[str]


class AcceptExceptionRequest(BaseModel):
    """Waive one gate WARNING. Blocking violations are refused by the service."""

    code: str
    reason: str


class FinalApprovalRequest(BaseModel):
    """The governed human gate. A reason is mandatory on rejection."""

    approve: bool
    reason: str | None = None
