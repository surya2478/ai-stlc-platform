from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NetworkEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    session_id: int
    capture_id: int
    action_id: int | None
    sequence: int
    parse_state: str
    method: str | None
    url: str | None
    host: str | None
    path: str | None
    is_external: bool | None
    status_code: int | None
    status_text: str | None
    raw_line: str
    review_state: str
    review_reason: str | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    created_at: datetime


class NetworkEventKpisOut(BaseModel):
    requests_captured: int
    requests_parsed: int
    requests_unparsed: int
    apis_identified: int
    external_systems: int
    mapping_readiness_pct: int
    ignored: int
    validation_available: bool


class BuildEventsRequest(BaseModel):
    project_id: int
    session_id: int


class IgnoreEventRequest(BaseModel):
    reason: str


class ReviewEventRequest(BaseModel):
    note: str | None = None


class NetworkEventActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    event_id: int | None
    event_type: str
    actor_id: int | None
    reason: str | None
    correlation_id: str | None
    created_at: datetime
