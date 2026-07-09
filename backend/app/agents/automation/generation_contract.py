"""
Automation Generation Contract (Phase 2, ADR-001).

The single JSON shape every automation-generating agent must emit. No agent
persists `.spec.ts` / `.py` source as final output — ever, including
repair/healing loops (see ADR_001_CONTROLLED_AUTOMATION_GENERATION.md). This
contract is that boundary: LLMs produce this (validated) structure; the
Script Compiler (`app/services/script_compiler/`) is the only thing that
renders code from it.

`contract_version` is versioned independently of the compiler itself — the
compiler must keep supporting version N and N-1 so previously generated
assets never break silently when the schema evolves (see the plan's Phase
2.1 exit criteria).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ContractVersion = Literal["1.0"]
ScriptType = Literal["playwright-typescript", "pytest-python"]
EnvironmentProfile = Literal["DEV", "SIT", "QA", "UAT", "PREPROD", "PROD_SANITY"]
LocatorStrategy = Literal["role", "label", "placeholder", "text", "testid", "css", "xpath"]
StepPhase = Literal["arrange", "act", "assert"]
# A closed vocabulary, not free prose — the compiler maps each action 1:1 to a
# real Playwright call. "custom" is the escape hatch: it never silently
# fabricates code, it renders `description` as a visible TODO comment.
StepAction = Literal[
    "navigate", "fill", "click", "check", "uncheck", "select",
    "hover", "wait_for_visible", "wait_for_url", "custom",
]
AssertionType = Literal["visible", "text", "url", "value", "count"]
CleanupActionType = Literal["api_call", "ui_action"]


def _string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


class ContractBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class TestDataBinding(ContractBaseModel):
    """A `${placeholder}` reference resolved via app.services.parameter_binding
    against a bound TestDataRecord — never an inline literal in the compiled
    script."""
    name: str
    placeholder: str  # e.g. "${customer_id}" or "${address.city}"
    fallback: str | None = None


class PageElement(ContractBaseModel):
    name: str
    locator_strategy: LocatorStrategy = Field(alias="locatorStrategy")
    locator_value: str = Field(alias="locatorValue")
    # role_hint is only meaningful when locator_strategy == "role" (e.g. "button", "heading")
    role_hint: str | None = Field(default=None, alias="roleHint")
    business_meaning: str | None = Field(default=None, alias="businessMeaning")

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class PageObject(ContractBaseModel):
    name: str
    route: str | None = None
    elements: list[PageElement] = Field(default_factory=list)


class ContractStep(ContractBaseModel):
    phase: StepPhase
    action: StepAction
    target: str | None = None  # "<PageObjectName>.<elementName>" reference, or a raw path for "navigate"
    # `value`: a plain, non-sensitive literal (a select option label, a URL
    # path fragment) — fine to inline since it isn't test/customer data.
    value: str | None = None
    # `data_binding`: a name from testDataBindings — resolved via
    # parameter_binding at compile time, NEVER inlined as a literal.
    data_binding: str | None = Field(default=None, alias="dataBinding")
    # Required when action == "custom": rendered as a visible TODO comment,
    # never fabricated into a guessed Playwright call.
    description: str | None = None
    expected_result: str | None = Field(default=None, alias="expectedResult")

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ContractAssertion(ContractBaseModel):
    type: AssertionType
    target: str
    expected: str
    web_first: bool = Field(default=True, alias="webFirst")

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ApiValidation(ContractBaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    path: str
    expected_status: int = Field(default=200, alias="expectedStatus")
    expected_fields: dict[str, str] = Field(default_factory=dict, alias="expectedFields")

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class DbValidation(ContractBaseModel):
    table: str
    query: dict[str, str] = Field(default_factory=dict)
    expect_found: bool = Field(default=True, alias="expectFound")

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class CleanupAction(ContractBaseModel):
    type: CleanupActionType
    description: str
    target: str | None = None  # API path for api_call, page/element ref for ui_action


class AutomationGenerationContract(ContractBaseModel):
    """The Automation Generation Contract — agent output, compiler input."""
    contract_version: ContractVersion = Field(default="1.0", alias="contractVersion")
    test_case_id: str = Field(alias="testCaseId")
    requirement_id: str | None = Field(default=None, alias="requirementId")
    test_type: str = Field(default="functional", alias="testType")
    script_type: ScriptType = Field(default="playwright-typescript", alias="scriptType")
    environment_profile: EnvironmentProfile = Field(default="QA", alias="environmentProfile")
    business_flow: str = Field(default="", alias="businessFlow")

    preconditions: list[str] = Field(default_factory=list)
    test_data_bindings: list[TestDataBinding] = Field(default_factory=list, alias="testDataBindings")
    page_objects: list[PageObject] = Field(default_factory=list, alias="pageObjects")
    steps: list[ContractStep] = Field(default_factory=list)
    expected_results: list[str] = Field(default_factory=list, alias="expectedResults")
    assertions: list[ContractAssertion] = Field(default_factory=list)
    api_validations: list[ApiValidation] = Field(default_factory=list, alias="apiValidations")
    db_validations: list[DbValidation] = Field(default_factory=list, alias="dbValidations")
    cleanup_actions: list[CleanupAction] = Field(default_factory=list, alias="cleanupActions")
    evidence_required: list[str] = Field(default_factory=list, alias="evidenceRequired")

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    _normalize_lists = field_validator(
        "preconditions", "expected_results", "evidence_required", mode="before"
    )(_string_list)

    @property
    def all_locators(self) -> list[PageElement]:
        """Flattened, deduped-by-nothing view of every locator across every
        page object — the shape the static gate's locator-policy check and
        `automation_intelligence` operate on."""
        return [el for page in self.page_objects for el in page.elements]
