"""Pydantic schemas for test plans, scenarios, and test cases."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel


# ── Test Plan ─────────────────────────────────────────────────────────────────

class TestPlanOut(BaseModel):
    id: int
    project_id: int
    test_plan_id: str
    title: str
    scope: list | None = None
    out_of_scope: list | None = None
    test_types: list | None = None
    entry_criteria: list | None = None
    exit_criteria: list | None = None
    risks: list | None = None
    mitigations: list | None = None
    automation_candidates: list | None = None
    estimated_effort: str | None = None
    resource_recommendation: str | None = None
    status: str
    agent_run_id: int | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestPlanUpdate(BaseModel):
    title: str | None = None
    scope: list | None = None
    out_of_scope: list | None = None
    test_types: list | None = None
    entry_criteria: list | None = None
    exit_criteria: list | None = None
    risks: list | None = None
    mitigations: list | None = None
    automation_candidates: list | None = None
    estimated_effort: str | None = None
    resource_recommendation: str | None = None
    status: str | None = None


# ── Test Scenario ─────────────────────────────────────────────────────────────

class TestScenarioOut(BaseModel):
    id: int
    project_id: int
    requirement_id: int | None = None
    scenario_id: str
    title: str
    description: str | None = None
    scenario_type: str | None = None
    priority: str
    coverage_mapping: list | None = None
    status: str
    agent_run_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Test Case ─────────────────────────────────────────────────────────────────

class TestCaseOut(BaseModel):
    id: int
    project_id: int
    scenario_id: int | None = None
    requirement_id: int | None = None
    test_case_id: str
    title: str
    preconditions: list | None = None
    test_data: dict | None = None
    steps: list | None = None
    expected_result: str | None = None
    bdd_scenario: str | None = None
    priority: str
    severity: str
    test_type: str | None = None
    automation_candidate: bool
    status: str
    agent_run_id: int | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestCaseUpdate(BaseModel):
    title: str | None = None
    preconditions: list | None = None
    test_data: dict | None = None
    steps: list | None = None
    expected_result: str | None = None
    bdd_scenario: str | None = None
    priority: str | None = None
    severity: str | None = None
    automation_candidate: bool | None = None
    status: str | None = None


class AgentPlanTrigger(BaseModel):
    project_id: int
    requirement_ids: list[int]


class AgentCaseTrigger(BaseModel):
    project_id: int
    scenario_ids: list[int] | None = None
    requirement_ids: list[int] | None = None
