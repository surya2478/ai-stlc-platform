"""Pydantic schemas for plan_test_cases (TestPlan <-> TestCase enrollment)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlanTestCaseCreate(BaseModel):
    test_case_id: int
    environment_id: int | None = None
    tester_user_id: int | None = None
    planned_execution_sequence: str | None = Field(default=None, max_length=50)
    order_index: int | None = None


class PlanTestCaseUpdate(BaseModel):
    environment_id: int | None = None
    tester_user_id: int | None = None
    planned_execution_sequence: str | None = Field(default=None, max_length=50)
    order_index: int | None = None


class PlanTestCaseReorder(BaseModel):
    ordered_enrollment_ids: list[int]


class PlanTestCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_plan_id: int
    test_case_id: int
    test_case_display_id: str | None = None
    test_case_title: str | None = None
    environment_id: int | None = None
    environment_name: str | None = None
    tester_user_id: int | None = None
    planned_execution_sequence: str | None = None
    order_index: int
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime
