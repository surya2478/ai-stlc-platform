"""Pydantic schemas for Test Suites — a named tag test cases are assigned to."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

# Same taxonomy as Requirement.test_phase (app/schemas/requirement.py TEST_PHASES).
TEST_SUITE_ENVIRONMENTS = ["SIT", "QA", "UAT", "Regression", "Production Smoke Test"]


class TestSuiteCreate(BaseModel):
    project_id: int
    name: str
    description: str | None = None
    environment: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Suite name must not be blank")
        if len(v) > 200:
            raise ValueError("Suite name must be 200 characters or fewer")
        return v


class TestSuiteUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    environment: str | None = None
    status: Literal["active", "archived"] | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Suite name must not be blank")
        return v


class TestSuiteOut(BaseModel):
    id: int
    project_id: int
    name: str
    description: str | None = None
    environment: str | None = None
    status: str
    case_count: int = 0
    created_by: int | None = None
    updated_by: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
