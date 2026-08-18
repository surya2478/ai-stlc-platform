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

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# PageObject/PageElement `name` becomes a TS class name, import identifier,
# and (unslugified) filesystem path segment (see script_compiler/compiler.py
# and automation_runner/workspace.py) — it must be a plain, safe identifier,
# never LLM-controlled free text, or a crafted value could break out of the
# generated source or escape the intended workspace directory.
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def _validate_safe_identifier(value: str) -> str:
    if not _SAFE_IDENTIFIER_RE.match(value):
        raise ValueError(
            f"{value!r} is not a safe identifier (must match {_SAFE_IDENTIFIER_RE.pattern})"
        )
    return value

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

# Actions that render `{target}.<method>()` — a Locator method call, so the
# target must resolve to a real declared element and can never be omitted.
# Module-level so UI-020's element picker can offer exactly the actions that
# require an element, using the same list the validator enforces. Keeping one
# definition is the point: a picker that disagreed with the validator would
# offer a form that cannot be saved.
ELEMENT_REQUIRED_ACTIONS_TUPLE: tuple[str, ...] = (
    "fill", "click", "check", "uncheck", "select", "hover", "wait_for_visible",
)
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
    # 0-based positional disambiguator (renders as a trailing .nth(N)) for
    # when the SAME (role, accessible name) pair genuinely resolves to
    # multiple real elements on one page — e.g. a "Show password" icon next
    # to both the Password and Confirm Password fields. Optional/backward
    # compatible: absent for the overwhelming majority of elements, which
    # resolve uniquely without it.
    nth: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("name")
    @classmethod
    def _name_is_safe_identifier(cls, value: str) -> str:
        return _validate_safe_identifier(value)


class PageObject(ContractBaseModel):
    name: str
    route: str | None = None
    elements: list[PageElement] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name_is_safe_identifier(cls, value: str) -> str:
        return _validate_safe_identifier(value)


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

    @model_validator(mode="after")
    def _targets_resolve_to_real_elements(self) -> "AutomationGenerationContract":
        """Reject a contract where a step/assertion/cleanup-action target
        doesn't resolve to an actual `<PageObjectName>.<elementName>` pair.

        Without this, a page object with zero elements (or a typo'd element
        name) silently produces a `target` string the compiler renders
        verbatim — e.g. an assertion on the bare page-object name compiles to
        invalid TypeScript that calls a method on a class reference instead
        of a locator. Caught here, at the LLM-output validation boundary
        (AutomationGenerationContract.model_validate), so it can never reach
        the compiler regardless of which agent produced the contract
        (automation_agent's first generation, or repair_agent's patches).
        """
        valid_refs = {
            f"{page.name}.{element.name}" for page in self.page_objects for element in page.elements
        }

        def check(target: str | None, where: str, *, required: bool = False) -> None:
            # playwright_renderer._resolve_target treats a missing target
            # exactly like the literal "page" — both resolve straight to
            # Playwright's raw Page object, which only supports Page-level
            # matchers (toHaveURL/toHaveTitle), never Locator methods like
            # .click()/.fill()/.check() or the .toBeVisible() matcher.
            # Confirmed via a live run: a "check" step with target=null
            # compiled to `await page.check();`, which doesn't exist.
            if target is None:
                if required:
                    raise ValueError(f"{where} has no target — needs a specific element")
                return
            if target == "page":
                raise ValueError(
                    f"{where} target 'page' is only valid for url-type assertions — "
                    "every other step/assertion needs a specific element"
                )
            if "." not in target:
                raise ValueError(
                    f"{where} target '{target}' is not a '<PageObject>.<element>' reference "
                    "(references a bare page object or path, not a specific element)"
                )
            if target not in valid_refs:
                raise ValueError(
                    f"{where} target '{target}' does not match any declared page object element"
                )

        # See ELEMENT_REQUIRED_ACTIONS_TUPLE above — one definition, shared with
        # UI-020's element picker so the form can never offer an unsaveable shape.
        ELEMENT_REQUIRED_ACTIONS = set(ELEMENT_REQUIRED_ACTIONS_TUPLE)
        for step in self.steps:
            if step.action in ("navigate", "custom", "wait_for_url"):
                # navigate's target is a raw path; custom is a TODO
                # placeholder; wait_for_url matches against `value`, not a
                # page-object element at all (see playwright_renderer.py).
                continue
            check(step.target, f"step '{step.action}'", required=step.action in ELEMENT_REQUIRED_ACTIONS)

        for assertion in self.assertions:
            if assertion.type == "url":
                # Renders as `expect(page).toHaveURL(...)` — target is
                # conventionally the literal "page", never a page-object
                # element reference (see playwright_renderer._render_assertion_line).
                continue
            check(assertion.target, f"assertion '{assertion.type}'")

        # A ui_action cleanup target is never compiled into anything. Both
        # renderers emit `// Cleanup: {description}` and drop the target on the
        # floor (playwright_renderer._render_cleanup_line, and the pytest one) —
        # only api_call targets reach generated source. So the invalid-code
        # hazard `check` exists to prevent cannot arise here, and running the
        # full check discarded an entire otherwise-valid script over a field
        # nothing reads: a live run rejected a whole contract because a cleanup
        # named the page object it happens on ('OrderCreationForm') rather than
        # a specific element. Grounding is still enforced — the target must name
        # something this contract actually declares, so a hallucinated name is
        # still caught — but a bare page object is a legitimate answer to
        # "where does this cleanup happen".
        page_names = {page.name for page in self.page_objects}
        for cleanup in self.cleanup_actions:
            if cleanup.type != "ui_action" or cleanup.target is None:
                continue
            if cleanup.target not in valid_refs and cleanup.target not in page_names:
                raise ValueError(
                    f"cleanup action target '{cleanup.target}' does not match any declared "
                    "page object or page object element"
                )

        return self

    @property
    def all_locators(self) -> list[PageElement]:
        """Flattened, deduped-by-nothing view of every locator across every
        page object — the shape the static gate's locator-policy check and
        `automation_intelligence` operate on."""
        return [el for page in self.page_objects for el in page.elements]
