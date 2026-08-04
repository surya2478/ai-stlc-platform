"""Test-data bindings are dotted paths into the authored test data.

Regression: TC-0109's contract bound `validOtherFields.first` while its test
data held `valid_other_fields.firstName`. The fixture rendered
`validOtherFields: string`, so the spec's `TEST_DATA.validOtherFields.first`
was `undefined` and the dry run died with "locator.fill: value: expected
string, got undefined" — after compiling cleanly, because Playwright strips
types with esbuild rather than checking them.
"""
import pytest

from app.agents.automation.automation_agent import _check_data_bindings
from app.agents.automation.generation_contract import AutomationGenerationContract
from app.services.script_compiler import compile_contract, data_bindings

NESTED_CONTRACT = {
    "contractVersion": "1.0",
    "testCaseId": "TC-0109",
    "requirementId": "REQ-0001",
    "scriptType": "playwright-typescript",
    "environmentProfile": "QA",
    "businessFlow": "Registration rejects malformed email",
    "testDataBindings": [{"name": "validOtherFields", "placeholder": "${validOtherFields}"}],
    "pageObjects": [{
        "name": "RegistrationPage",
        "route": "/register",
        "elements": [
            {"name": "firstNameInput", "locatorStrategy": "label", "locatorValue": "First Name"},
            {"name": "mobileInput", "locatorStrategy": "label", "locatorValue": "Mobile"},
        ],
    }],
    "steps": [
        {"phase": "arrange", "action": "navigate", "value": "/register"},
        {"phase": "act", "action": "fill", "target": "RegistrationPage.firstNameInput",
         "dataBinding": "validOtherFields.firstName"},
        {"phase": "act", "action": "fill", "target": "RegistrationPage.mobileInput",
         "dataBinding": "validOtherFields.userMobile"},
    ],
    "assertions": [
        {"type": "visible", "target": "RegistrationPage.firstNameInput", "expected": "true"}
    ],
}

TEST_DATA = {"validOtherFields": {"firstName": "John", "userMobile": "1234567890"}}


def _contract(**overrides) -> AutomationGenerationContract:
    data = dict(NESTED_CONTRACT)
    data.update(overrides)
    return AutomationGenerationContract.model_validate(data)


# ── Rendering ────────────────────────────────────────────────────────────────

def test_fixture_declares_the_object_shape_the_spec_dereferences():
    bundle = compile_contract(_contract())
    fixture = bundle.files["fixtures/testData.fixture.ts"]

    assert "validOtherFields: {" in fixture
    assert "firstName: string;" in fixture
    assert "userMobile: string;" in fixture
    # The flat declaration is what made `.firstName` undefined at runtime.
    assert "validOtherFields: string;" not in fixture


def test_every_leaf_reads_its_own_environment_variable():
    fixture = compile_contract(_contract()).files["fixtures/testData.fixture.ts"]

    assert "process.env.TEST_VALID_OTHER_FIELDS_FIRST_NAME" in fixture
    assert "process.env.TEST_VALID_OTHER_FIELDS_USER_MOBILE" in fixture


def test_spec_reads_the_same_paths_the_fixture_declares():
    bundle = compile_contract(_contract())
    spec = bundle.files[bundle.entry_path]

    assert "TEST_DATA.validOtherFields.firstName" in spec
    assert "TEST_DATA.validOtherFields.userMobile" in spec


def test_flat_bindings_still_render_as_plain_strings():
    """A binding with no dots is unchanged — the common case must not regress."""
    contract = _contract(
        testDataBindings=[{"name": "username", "placeholder": "${username}", "fallback": "demo"}],
        steps=[
            {"phase": "arrange", "action": "navigate", "value": "/register"},
            {"phase": "act", "action": "fill", "target": "RegistrationPage.firstNameInput",
             "dataBinding": "username"},
        ],
    )
    fixture = compile_contract(contract).files["fixtures/testData.fixture.ts"]

    assert "username: string;" in fixture
    assert "username: process.env.TEST_USERNAME ?? 'demo'," in fixture


def test_pytest_bundle_indexes_nested_paths_step_by_step():
    """`test_data['a.b']` would raise KeyError against a nested fixture."""
    contract = _contract(scriptType="pytest-python")
    bundle = compile_contract(contract)
    module = bundle.files[bundle.entry_path]

    assert "test_data[\"validOtherFields\"][\"firstName\"]" in module
    assert "test_data['validOtherFields.firstName']" not in module


# ── Validation ───────────────────────────────────────────────────────────────

def test_binding_that_is_absent_from_the_test_data_is_reported():
    contract = _contract(steps=[
        {"phase": "act", "action": "fill", "target": "RegistrationPage.firstNameInput",
         "dataBinding": "validOtherFields.first"},
    ])

    unresolved = _check_data_bindings(contract, TEST_DATA)

    assert len(unresolved) == 1
    assert "validOtherFields.first" in unresolved[0]


def test_bindings_that_all_resolve_report_nothing():
    assert _check_data_bindings(_contract(), TEST_DATA) == []


def test_binding_resolving_to_a_container_is_reported():
    """An object cannot be filled into a field."""
    contract = _contract(steps=[
        {"phase": "act", "action": "fill", "target": "RegistrationPage.firstNameInput",
         "dataBinding": "validOtherFields"},
    ])

    unresolved = _check_data_bindings(contract, TEST_DATA)

    assert len(unresolved) == 1
    assert "resolves to an object" in unresolved[0]


@pytest.mark.parametrize("test_data", [{}, None, "not-a-dict"])
def test_validation_is_skipped_when_the_test_case_carries_no_data(test_data):
    """Bindings may be satisfied from the Test Data module or the environment;
    failing those would block generation for a test case that is not broken."""
    assert _check_data_bindings(_contract(), test_data) == []


# ── Path helpers ─────────────────────────────────────────────────────────────

def test_a_root_with_children_is_not_itself_a_leaf():
    tree = data_bindings.binding_tree(_contract())

    assert data_bindings.leaf_paths(tree) == [
        "validOtherFields.firstName",
        "validOtherFields.userMobile",
    ]


def test_resolve_path_walks_nested_dictionaries():
    assert data_bindings.resolve_path(TEST_DATA, "validOtherFields.firstName") == (True, "John")
    assert data_bindings.resolve_path(TEST_DATA, "validOtherFields.nope") == (False, None)
    assert data_bindings.resolve_path(TEST_DATA, "missing.deeper") == (False, None)
