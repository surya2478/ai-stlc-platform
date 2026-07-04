from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ApprovalDecisionRequest(BaseModel):
    action: Literal["approve", "reject", "request_changes"]
    notes: str | None = None
    changes_requested: dict[str, Any] | None = None
    correlation_id: str | None = None


class ApprovalActionOut(BaseModel):
    id: int
    project_id: int
    user_id: int
    action_type: str
    entity_type: str
    entity_id: int
    decision: str
    notes: str | None = None
    changes_requested: dict[str, Any] | None = None
    source: str
    actor_role: str | None = None
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    jira_issue_key: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    agent_run_id: int | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArtifactLineageOut(BaseModel):
    id: int
    project_id: int
    agent_run_id: int | None = None
    parent_type: str
    parent_id: int
    child_type: str
    child_id: int
    relationship_type: str
    source: str
    correlation_id: str | None = None
    notes: str | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TraceabilityChainItem(BaseModel):
    id: int
    ref: str | None = None
    title: str
    status: str | None = None


class LineageNode(BaseModel):
    entity_type: str
    entity_id: int
    ref: str | None = None
    title: str | None = None
    status: str | None = None
    relationship_type: str | None = None
    depth: int = 1


class LineageChainOut(BaseModel):
    entity_type: str
    entity_id: int
    project_id: int
    upstream: list[LineageNode]
    downstream: list[LineageNode]


class TraceabilityMatrixRow(BaseModel):
    requirement: TraceabilityChainItem
    test_cases: list[TraceabilityChainItem]
    execution_results: list[TraceabilityChainItem]
    defects: list[TraceabilityChainItem]
    gaps: list[str]


class TraceabilityMatrixOut(BaseModel):
    items: list[TraceabilityMatrixRow]
    total: int
    page: int
    page_size: int
    pages: int
    include_drafts: bool = False


class CoverageGapsOut(BaseModel):
    project_id: int
    include_drafts: bool = False
    no_test_cases: list[int]
    no_execution: list[int]
    undecided_failures: list[int]


class TraceabilityQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    domain: str | None = None
    phase: str | None = None
    release: str | None = None
    include_drafts: bool = False
