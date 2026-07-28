from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AutomationClassificationPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None = None
    application_id: int | None = None
    code: str
    name: str
    version: int
    parent_policy_id: int | None = None
    status: str
    rules: dict
    created_by: int | None = None
    published_by: int | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AutomationClassificationPolicyUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rules: dict


class ClassificationPolicySimulateRequest(BaseModel):
    test_case_id: int


class ClassificationRuleFindingOut(BaseModel):
    code: str
    label: str
    detail: str


class ClassificationPolicySimulateResponse(BaseModel):
    policy: AutomationClassificationPolicyOut
    deterministic_blockers: list[ClassificationRuleFindingOut]
    deterministic_warnings: list[ClassificationRuleFindingOut]
    routing_default_adapter: str | None = None
    routing_default_mandatory_validators: list[str]
    routing_default_optional_validators: list[str]


class ScoreFactorOut(BaseModel):
    factor: str
    weight: int
    score: int
    category: str | None = None


class TestCaseAutomationClassificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    test_case_id: int
    test_case_version: int
    version: int
    parent_classification_id: int | None = None
    is_current: bool

    candidate_status: str
    primary_adapter: str | None = None
    supporting_adapters: list[str]
    mandatory_validators: list[str]
    optional_validators: list[str]

    discovery_required: bool
    recommended_discovery_mode: str | None = None

    complexity_score: int | None = None
    automation_value_score: int | None = None
    score_factors: list[ScoreFactorOut]

    required_evidence: list[str]
    required_capabilities: list[str]
    deterministic_blockers: list[ClassificationRuleFindingOut]
    advisory_warnings: list
    matched_rules: list

    policy_id: int | None = None
    policy_version: int | None = None
    agent_run_id: int | None = None

    review_status: str
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    approved_by: int | None = None
    approved_at: datetime | None = None
    decision_reason: str | None = None

    created_at: datetime
    updated_at: datetime

    is_stale: bool = False


class ClassificationEvaluateRequest(BaseModel):
    test_case_ids: list[int]


class ClassificationEvaluateResponseItem(BaseModel):
    test_case_id: int
    agent_run_id: int
    status: str


class ClassificationEvaluateResponse(BaseModel):
    project_id: int
    results: list[ClassificationEvaluateResponseItem]


class ClassificationReviewRequest(BaseModel):
    corrections: dict
    reason: str | None = None


class ClassificationDecisionRequest(BaseModel):
    reason: str | None = None


class ClassificationFieldCorrectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    classification_id: int
    field_name: str
    ai_value: str | None = None
    reviewer_value: str | None = None
    changed_by: int | None = None
    reason: str | None = None
    created_at: datetime
