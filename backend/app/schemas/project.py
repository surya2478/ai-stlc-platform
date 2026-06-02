from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    metadata_: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Project name must not be blank")
        if len(v) > 255:
            raise ValueError("Project name must be 255 characters or fewer")
        return v

    @field_validator("description")
    @classmethod
    def description_max_length(cls, v: str | None) -> str | None:
        if v and len(v) > 2000:
            raise ValueError("Description must be 2000 characters or fewer")
        return v


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: Literal["active", "archived", "completed"] | None = None
    metadata_: dict[str, Any] | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    status: str
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Alias used by projects.py endpoint and project_service
ProjectRead = ProjectOut


class ProjectStats(BaseModel):
    project_id: int
    total_requirements: int = 0
    total_test_cases: int = 0
    open_defects: int = 0
