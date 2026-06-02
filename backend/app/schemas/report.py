"""Pydantic schemas for Reports."""
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, field_validator


class ReportOut(BaseModel):
    id: int
    project_id: int
    report_id: str
    report_type: str
    title: str
    summary: str | None = None
    coverage: dict | None = None
    execution_metrics: dict | None = None
    defect_metrics: dict | None = None
    risks: list | None = None
    recommendations: list | None = None
    status: str
    agent_run_id: int | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentReportTrigger(BaseModel):
    project_id: int
    report_type: Literal["daily", "weekly", "sprint", "release"] = "sprint"
    date_from: str | None = None
    date_to: str | None = None
    metadata_: dict[str, Any] | None = None

    @field_validator("project_id")
    @classmethod
    def project_id_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("project_id must be a positive integer")
        return v
