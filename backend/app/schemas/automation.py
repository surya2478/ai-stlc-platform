"""Pydantic schemas for Automation Scripts."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, field_validator


class AutomationScriptOut(BaseModel):
    id: int
    project_id: int
    test_case_id: int | None = None
    script_id: str
    framework: str
    title: str | None = None
    script_content: str | None = None
    imports: str | None = None
    fixtures: str | None = None
    page_objects: str | None = None
    file_path: str | None = None
    status: str
    agent_run_id: int | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AutomationScriptUpdate(BaseModel):
    framework: Literal["playwright", "pytest"] | None = None
    title: str | None = None
    script_content: str | None = None
    imports: str | None = None
    fixtures: str | None = None
    page_objects: str | None = None
    file_path: str | None = None
    status: Literal["draft", "approved", "rejected"] | None = None


class AgentAutomationTrigger(BaseModel):
    project_id: int
    test_case_ids: list[int]
    framework: Literal["playwright", "pytest"] = "playwright"

    @field_validator("test_case_ids")
    @classmethod
    def test_case_ids_non_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("test_case_ids must contain at least one ID")
        return v
