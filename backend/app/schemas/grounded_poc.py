"""Pydantic schemas for the Grounded Automation PoC endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PocRunCreate(BaseModel):
    project_id: int
    test_case_id: int
    environment: str = Field(min_length=1, max_length=80)
    capture_mode: str = Field(default="automated", pattern="^(automated|assisted|manual_guided)$")


class PocRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_by: int
    test_case_id: int
    application_id: int | None = None
    status: str
    capture_mode: str
    config: dict
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PocAgentRunSummary(BaseModel):
    id: int
    status: str
    progress_percent: int = 0
    progress_message: str | None = None
    error_message: str | None = None


class PocEvidenceSummary(BaseModel):
    id: int
    sequence: int
    state_fingerprint: str
    url: str | None = None
    title: str | None = None
    element_count: int
    blockers: list[str] = Field(default_factory=list)
    produced_by_step: int | None = None
    has_screenshot: bool = False


class PocScriptSummary(BaseModel):
    id: int
    script_id: str
    status: str
    version: int
    framework: str | None = None


class PocRunDetailOut(PocRunOut):
    routing: dict | None = None
    coverage: dict | None = None
    pending_confirmation: dict | None = None
    script_ids: list[int] | None = None
    evidence: list[PocEvidenceSummary] = Field(default_factory=list)
    agent_runs: dict = Field(default_factory=dict)
    scripts: list[PocScriptSummary] = Field(default_factory=list)
    step_trace: list[dict] = Field(default_factory=list)


class PocEvidenceDetailOut(PocEvidenceSummary):
    environment: str | None = None
    elements: list[dict] = Field(default_factory=list)
    snapshot_text: str | None = None
    console_evidence: list[str] = Field(default_factory=list)
    prev_evidence_id: int | None = None


class PocActionResponse(BaseModel):
    grounding_run_id: int
    status: str
    agent_run_id: int | None = None
    task_id: str | None = None
    message: str


class PocConfirmStepRequest(BaseModel):
    step_index: int = Field(ge=0)
    element_name: str = Field(min_length=1, max_length=200)


class PocStatusOut(BaseModel):
    enabled: bool
    message: str
