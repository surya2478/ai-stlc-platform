"""Schemas for validating structured JSON returned by LLM agents."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        return str(value)
    return str(value)


class LLMBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RequirementLLMOutput(LLMBaseModel):
    title: str = "Untitled requirement"
    summary: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    user_roles: list[str] = Field(default_factory=list)
    systems_impacted: list[str] = Field(default_factory=list)
    ui_pages: list[str] = Field(default_factory=list)
    apis: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    # Telecom-specific fields (extracted by intake agent when detectable)
    telecom_domain: str | None = None
    impacted_interfaces: list[str] = Field(default_factory=list)
    risk_level: str | None = None
    test_phase: str | None = None
    release_version: str | None = None
    upstream_systems: list[str] = Field(default_factory=list)
    downstream_systems: list[str] = Field(default_factory=list)
    regulatory_impact: bool = False
    revenue_impact: bool = False

    _normalize_lists = field_validator(
        "acceptance_criteria",
        "business_rules",
        "user_roles",
        "systems_impacted",
        "ui_pages",
        "apis",
        "dependencies",
        "risks",
        "missing_information",
        "impacted_interfaces",
        "upstream_systems",
        "downstream_systems",
        mode="before",
    )(_string_list)


class RequirementQualityLLMOutput(LLMBaseModel):
    requirement_title: str = ""
    requirement_id: int | None = None  # numeric DB id — preferred over title matching

    # ── Core quality dimensions (1–5) ─────────────────────────────────────────
    completeness_score: float = Field(default=3.0, ge=1, le=5)
    clarity_score: float = Field(default=3.0, ge=1, le=5)
    testability_score: float = Field(default=3.0, ge=1, le=5)
    ambiguity_score: float = Field(default=3.0, ge=1, le=5)
    acceptance_criteria_score: float = Field(default=3.0, ge=1, le=5)

    # ── Telecom-specific dimensions (1–5) ─────────────────────────────────────
    interface_readiness_score: float = Field(default=3.0, ge=1, le=5)
    telecom_domain_completeness: float = Field(default=3.0, ge=1, le=5)

    # ── Downstream generation gate ─────────────────────────────────────────────
    scenario_generation_readiness: float = Field(default=3.0, ge=1, le=5)
    # 5 = fully ready, 1 = not ready

    overall_score: float = Field(default=3.0, ge=1, le=5)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    verdict: str = "needs_revision"
    # verdict: pass | needs_revision | fail

    _normalize_lists = field_validator("issues", "suggestions", mode="before")(_string_list)


class TestPlanLLMOutput(LLMBaseModel):
    title: str = ""
    scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    test_types: list[str] = Field(default_factory=list)
    entry_criteria: list[str] = Field(default_factory=list)
    exit_criteria: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)
    automation_candidates: list[str] = Field(default_factory=list)
    estimated_effort: str = ""
    resource_recommendation: str = ""

    _normalize_lists = field_validator(
        "scope",
        "out_of_scope",
        "test_types",
        "entry_criteria",
        "exit_criteria",
        "risks",
        "mitigations",
        "automation_candidates",
        mode="before",
    )(_string_list)


class TestScenarioLLMOutput(LLMBaseModel):
    requirement_title: str = ""
    scenario_id: str = ""
    title: str = "Untitled scenario"
    description: str = ""
    scenario_type: str = "positive"
    priority: str = "Medium"
    coverage_mapping: list[str] = Field(default_factory=list)

    _normalize_lists = field_validator("coverage_mapping", mode="before")(_string_list)


class TestCaseStepLLMOutput(LLMBaseModel):
    step_number: int = 1
    action: str = ""
    expected_result: str = ""


class TestCaseLLMOutput(LLMBaseModel):
    scenario_title: str = ""
    test_case_id: str = ""
    title: str = "Untitled test case"
    preconditions: list[str] = Field(default_factory=list)
    test_data: dict[str, Any] = Field(default_factory=dict)
    steps: list[TestCaseStepLLMOutput] = Field(default_factory=list)
    expected_result: str = ""
    bdd_scenario: str = ""
    priority: str = "Medium"
    severity: str = "Medium"
    test_type: str = "functional"
    automation_candidate: bool = False

    _normalize_lists = field_validator("preconditions", mode="before")(_string_list)

    @field_validator("steps", mode="before")
    @classmethod
    def normalize_steps(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return [
                {"step_number": i + 1, "action": item, "expected_result": ""}
                if isinstance(item, str)
                else item
                for i, item in enumerate(value)
            ]
        return [{"step_number": 1, "action": str(value), "expected_result": ""}]


class AutomationScriptLLMOutput(LLMBaseModel):
    test_case_id: str = ""
    framework: str = ""
    file_path: str = ""
    code: str = ""
    setup_required: list[str] = Field(default_factory=list)
    execution_command: str = ""

    _normalize_lists = field_validator("setup_required", mode="before")(_string_list)


class ExecutionResultLLMOutput(LLMBaseModel):
    test_case_id: str = ""
    test_name: str = "Unknown test"
    status: str = "passed"
    duration_ms: int = 500
    error_message: str | None = None
    stack_trace: str | None = None
    logs: list[str] = Field(default_factory=list)

    _normalize_lists = field_validator("logs", mode="before")(_string_list)
    _normalize_text = field_validator("error_message", "stack_trace", mode="before")(_optional_text)


class DefectLLMOutput(LLMBaseModel):
    execution_result_ref: str = "unknown"
    summary: str = "Defect detected in automated test"
    description: str = ""
    steps_to_reproduce: list[str] = Field(default_factory=list)
    expected_result: str = ""
    actual_result: str = ""
    severity: str = "Medium"
    priority: str = "Medium"
    root_cause_hypothesis: str = ""
    classification: str = "product_defect"

    _normalize_lists = field_validator("steps_to_reproduce", mode="before")(_string_list)


class ReportLLMOutput(LLMBaseModel):
    title: str = ""
    summary: str = ""
    coverage: dict[str, Any] = Field(default_factory=dict)
    execution_metrics: dict[str, Any] = Field(default_factory=dict)
    defect_metrics: dict[str, Any] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    _normalize_lists = field_validator("risks", "recommendations", mode="before")(_string_list)
