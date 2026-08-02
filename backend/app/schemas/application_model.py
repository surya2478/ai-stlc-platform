from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApplicationModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    application_id: int
    source_session_id: int | None
    version: int
    parent_model_id: int | None
    is_current: bool
    status: str
    built_by: int | None
    built_at: datetime | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    approved_by: int | None
    approved_at: datetime | None
    published_by: int | None
    published_at: datetime | None
    decision_reason: str | None
    built_from_action_count: int
    created_at: datetime
    updated_at: datetime


class ApplicationModelDetailOut(ApplicationModelOut):
    kpis: dict
    stale: bool
    # Whether this deployment requires a different person to approve than the
    # one who built. Sent so the UI states the rule actually in force rather
    # than assuming it — the server remains the authority either way.
    requires_separate_approver: bool = True


class ApplicationModelNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_id: int
    node_type: str
    parent_node_id: int | None
    external_ref: str
    display_name: str
    description: str | None
    state: str
    attributes: dict


class ApplicationModelEdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_id: int
    edge_type: str
    from_node_id: int
    to_node_id: int


class LocatorEvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: int
    locator_value: str | None
    locator_type: str | None
    confidence: int | None
    status: str
    source_action_id: int | None
    reason: str | None
    created_by: int | None
    created_at: datetime


class ApplicationModelGapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_id: int
    gap_type: str
    severity: str
    node_id: int | None
    evidence: dict
    remediation: str | None
    owner_id: int | None
    status: str
    reviewer_notes: str | None
    resolved_by: int | None
    resolved_at: datetime | None


class BuildModelRequest(BaseModel):
    project_id: int
    application_id: int
    session_id: int


class DecisionRequest(BaseModel):
    reason: str | None = None


class RenameNodeRequest(BaseModel):
    display_name: str


class LocatorConfirmRequest(BaseModel):
    pass


class LocatorUnstableRequest(BaseModel):
    reason: str


class LocatorFallbackRequest(BaseModel):
    locator_value: str
    locator_type: str | None = None


class ResolveGapRequest(BaseModel):
    reviewer_notes: str | None = None


class ApplicationModelActivityOut(BaseModel):
    id: int
    at: datetime
    actor_id: int | None
    event_type: str
    node_id: int | None
    reason: str | None
    old_value: dict | None
    new_value: dict | None
