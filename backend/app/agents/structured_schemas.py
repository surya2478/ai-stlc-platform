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


class MissingInfoLLMItem(LLMBaseModel):
    """One declared unknown, with the agent's judgement of whether it gates.

    Severity exists because the old bare-string list made every unknown a hard
    blocker, which punished a thorough extraction — an agent that declared nothing
    advanced further than one that did its job. "Exact API endpoint and payload
    structure" genuinely stops a tester writing a case; "success message wording"
    does not.
    """

    item: str = ""
    severity: str = "blocking"

    @field_validator("severity", mode="before")
    @classmethod
    def _clean_severity(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        # Anything unrecognized is treated as blocking: an unreadable severity
        # must not quietly downgrade a real gap.
        return text if text in ("blocking", "advisory") else "blocking"


def _missing_info_list(value: Any) -> list[dict]:
    """Accept the legacy bare-string list as well as the object form.

    Historical rows and any older prompt still produce plain strings; those
    normalize to blocking, so nothing silently unblocks without an agent having
    re-judged it.
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    normalized: list[dict] = []
    for entry in value:
        # `str(None)` is "None"; a null in the model's array must not become an
        # item literally reading "None".
        if entry is None:
            continue
        if isinstance(entry, dict):
            text = str(entry.get("item") or entry.get("text") or "").strip()
            severity = entry.get("severity")
        else:
            text = str(entry).strip()
            severity = "blocking"
        if text:
            normalized.append({"item": text, "severity": severity})
    return normalized


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
    missing_information: list[MissingInfoLLMItem] = Field(default_factory=list)
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
        "impacted_interfaces",
        "upstream_systems",
        "downstream_systems",
        mode="before",
    )(_string_list)

    # Not a plain string list — it carries severity, and older data is strings.
    _normalize_missing_info = field_validator("missing_information", mode="before")(
        _missing_info_list
    )


class ScenarioReviewLLMOutput(LLMBaseModel):
    """LLM output for the scenario_review agent (Phase 1 reviewer)."""
    scenario_id: str = ""  # business scenario_id, e.g. "TS-001" — for matching

    coverage_score: float = Field(default=3.0, ge=1, le=5)
    business_alignment_score: float = Field(default=3.0, ge=1, le=5)
    clarity_score: float = Field(default=3.0, ge=1, le=5)
    prioritization_score: float = Field(default=3.0, ge=1, le=5)
    overall_score: float = Field(default=3.0, ge=1, le=5)

    verdict: str = "needs_revision"
    # verdict: pass | needs_revision | fail

    coverage_gaps: list[str] = Field(default_factory=list)
    # acceptance criteria / business rules this scenario set does not cover
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    _normalize_lists = field_validator("coverage_gaps", "issues", "suggestions", mode="before")(_string_list)


class TestCaseReviewLLMOutput(LLMBaseModel):
    """LLM output for the test_case_review agent (Phase 1 reviewer)."""
    test_case_id: str = ""  # business test_case_id, e.g. "TC-0001" — for matching

    step_quality_score: float = Field(default=3.0, ge=1, le=5)
    data_readiness_score: float = Field(default=3.0, ge=1, le=5)
    expected_result_clarity_score: float = Field(default=3.0, ge=1, le=5)
    phase_fit_score: float = Field(default=3.0, ge=1, le=5)
    coverage_score: float = Field(default=3.0, ge=1, le=5)
    overall_score: float = Field(default=3.0, ge=1, le=5)

    verdict: str = "needs_revision"
    # verdict: pass | needs_revision | fail

    coverage_gaps: list[str] = Field(default_factory=list)
    # scenario steps / acceptance criteria this test case set does not cover
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    _normalize_lists = field_validator("coverage_gaps", "issues", "suggestions", mode="before")(_string_list)


class AutomationScriptReviewLLMOutput(LLMBaseModel):
    """LLM output for the automation_script_review agent (Phase 4.5 reviewer).
    Hybrid: the Static Quality Gate result and dry-run evidence are already
    computed facts given to the LLM; this schema captures what only a
    senior human reviewer's judgement can add on top of them."""
    test_case_id: str = ""  # for matching, e.g. "TC-0001"

    business_step_coverage_score: float = Field(default=3.0, ge=1, le=5)
    assertion_meaningfulness_score: float = Field(default=3.0, ge=1, le=5)
    code_cleanliness_score: float = Field(default=3.0, ge=1, le=5)
    cleanup_presence_score: float = Field(default=3.0, ge=1, le=5)
    overall_score: float = Field(default=3.0, ge=1, le=5)

    verdict: str = "needs_revision"
    # verdict: pass | needs_revision | fail

    coverage_gaps: list[str] = Field(default_factory=list)
    # test case steps/expected results this script does not actually exercise
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    _normalize_lists = field_validator("coverage_gaps", "issues", "suggestions", mode="before")(_string_list)


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
    # Fuller UAT-template "Test Case Objective" — a one-sentence statement of
    # intent, distinct from the short `title` above (e.g. title "Verify login
    # rejects bad password", objective "Verify the login form rejects an
    # incorrect password with a clear inline error and no session created").
    objective: str = ""
    preconditions: list[str] = Field(default_factory=list)
    test_data: dict[str, Any] = Field(default_factory=dict)
    steps: list[TestCaseStepLLMOutput] = Field(default_factory=list)
    expected_result: str = ""
    bdd_scenario: str = ""
    priority: str = "Medium"
    severity: str = "Medium"
    # test_type: one of the UAT taxonomy's controlled values — see
    # TESTCASE_SYSTEM in test_case_agent.py for the exact closed vocabulary
    # (Positive | Negative | Edge / Boundary | Regression).
    test_type: str = "Positive"
    # complexity: Low | Medium | High — the UAT template's Test Case
    # Complexity column; a same-weight-class judgment call as priority/severity.
    complexity: str = "Medium"
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


class AiAssistSuggestion(LLMBaseModel):
    """LLM output for "Ask AI" on a manual test step.

    The model is asked to look at the step's action, the expected result, the
    tester's actual_result text (and optionally a screenshot) and decide whether
    the step looks like a pass / fail / blocked. Confidence is honest — if the
    model cannot tell, it should return low confidence and explain why.
    """
    suggested_status: str = "blocked"          # pass | fail | blocked
    confidence: int = 0                         # 0-100
    reasoning: str = ""
    observations: list[str] = Field(default_factory=list)

    _normalize_lists = field_validator("observations", mode="before")(_string_list)

    @field_validator("suggested_status", mode="before")
    @classmethod
    def _normalize_status(cls, value: Any) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"pass", "passed", "success"}:
            return "pass"
        if raw in {"fail", "failed", "failure", "error"}:
            return "fail"
        if raw in {"blocked", "block", "uncertain", "unknown", "skip", "skipped"}:
            return "blocked"
        return "blocked"

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, value: Any) -> int:
        try:
            n = int(round(float(value)))
        except (TypeError, ValueError):
            return 0
        return max(0, min(100, n))


class ClassificationAgentLLMOutput(LLMBaseModel):
    """LLM output for the Test Classification Agent — advisory only. The
    caller (classification_service.persist_classification_result) always
    applies deterministic blockers and capability-resolution results on top
    of this; the agent's `candidate_status` here can be downgraded but never
    used to override a blocker (constraint: "Do not let the AI agent make
    the final approval decision").
    """
    candidate_status: str = "NOT_RECOMMENDED"
    # RECOMMENDED | CONDITIONAL | NOT_RECOMMENDED | BLOCKED | DEFERRED
    primary_adapter: str | None = None
    supporting_adapters: list[str] = Field(default_factory=list)
    mandatory_validators: list[str] = Field(default_factory=list)
    optional_validators: list[str] = Field(default_factory=list)
    discovery_required: bool = False
    recommended_discovery_mode: str | None = None
    # GUIDED_USER | FREE_USER_ACTION | SUPERVISED_AGENT
    reasons: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    matched_rules: list[str] = Field(default_factory=list)
    confidence: int = 0  # advisory only — never used as an approval criterion

    _normalize_lists = field_validator(
        "supporting_adapters", "mandatory_validators", "optional_validators",
        "reasons", "assumptions", "warnings", "matched_rules",
        mode="before",
    )(_string_list)

    @field_validator("candidate_status", mode="before")
    @classmethod
    def _normalize_candidate_status(cls, value: Any) -> str:
        raw = str(value or "").strip().upper().replace(" ", "_")
        allowed = {"RECOMMENDED", "CONDITIONAL", "NOT_RECOMMENDED", "BLOCKED", "DEFERRED"}
        return raw if raw in allowed else "NOT_RECOMMENDED"

    @field_validator("recommended_discovery_mode", mode="before")
    @classmethod
    def _normalize_discovery_mode(cls, value: Any) -> str | None:
        if not value:
            return None
        raw = str(value).strip().upper().replace(" ", "_")
        allowed = {"GUIDED_USER", "FREE_USER_ACTION", "SUPERVISED_AGENT"}
        return raw if raw in allowed else None

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_agent_confidence(cls, value: Any) -> int:
        try:
            n = int(round(float(value)))
        except (TypeError, ValueError):
            return 0
        return max(0, min(100, n))
