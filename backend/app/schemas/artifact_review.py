from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ArtifactReviewOut(BaseModel):
    id: int
    project_id: int
    agent_run_id: int | None = None
    artifact_type: str
    artifact_id: int
    reviewer_agent: str
    scores: dict[str, Any] | None = None
    overall_score: float | None = None
    verdict: str
    findings: list[dict[str, Any]] | None = None
    coverage_gaps: list[dict[str, Any]] | None = None
    review_mode: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CoverageMatrixEntryOut(BaseModel):
    id: int
    project_id: int
    requirement_id: int | None = None
    scenario_id: int | None = None
    test_case_id: int | None = None
    script_id: int | None = None
    execution_result_id: int | None = None
    defect_id: int | None = None
    test_type: str | None = None
    risk_level: str | None = None
    case_class: str | None = None
    automation_eligible: str | None = None
    automation_reason: str | None = None
    execution_status: str | None = None
    defect_linked: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
