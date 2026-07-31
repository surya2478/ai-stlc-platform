"""UI-021 Script Editor — the ADR-001 invariants, without a DB.

These pin the properties that make the tab read-only-by-construction. The
compile and dry-run paths themselves are exercised live (see contract Section
33); what is asserted here is the set of rules a future change could break
silently.
"""
import pytest

from app.agents.automation.generation_contract import (
    ELEMENT_REQUIRED_ACTIONS_TUPLE,
    AutomationGenerationContract,
)
from app.services import static_quality_gate
from app.services.automation_asset.script_service import _FRAMEWORK_FOR_SCRIPT_TYPE
from app.services.script_compiler import compiler

CONTRACT = {
    "contractVersion": "1.0",
    "testCaseId": "TC-500",
    "requirementId": "REQ-500",
    "scriptType": "playwright-typescript",
    "businessFlow": "Compile invariants",
    "pageObjects": [
        {
            "name": "HomePage",
            "route": "/",
            "elements": [
                {"name": "searchBox", "locatorStrategy": "testid", "locatorValue": "q"},
            ],
        }
    ],
    "steps": [
        {"phase": "arrange", "action": "navigate", "target": "/"},
        {"phase": "act", "action": "fill", "target": "HomePage.searchBox", "value": "hello"},
    ],
    "assertions": [{"type": "url", "target": "page", "expected": "/"}],
}


def compiled():
    return compiler.compile_contract(AutomationGenerationContract.model_validate(CONTRACT))


# ── ADR-001: the compiler is the only writer of code ─────────────────────────


def test_compiled_entry_carries_the_generation_header():
    """Without this marker the Static Quality Gate hard-blocks the script, which
    is what makes "no free-form script generation" enforceable rather than
    aspirational."""
    bundle = compiled()
    entry = bundle.files[bundle.entry_path]
    assert static_quality_gate._GENERATION_HEADER_MARKER in entry


def test_compiled_entry_carries_the_test_case_and_requirement_mapping():
    bundle = compiled()
    entry = bundle.files[bundle.entry_path]
    assert static_quality_gate._TC_HEADER_RE.search(entry)
    assert static_quality_gate._REQ_HEADER_RE.search(entry)


def test_a_hand_edited_script_is_rejected_by_the_gate():
    """The reason UI-021 is read-only: stripping the header — which any manual
    edit risks — makes the platform's own gate refuse the script."""
    from types import SimpleNamespace

    bundle = compiled()
    tampered = bundle.files[bundle.entry_path].replace(
        static_quality_gate._GENERATION_HEADER_MARKER, "hand written"
    )
    script = SimpleNamespace(
        id=1, framework="playwright", code=tampered, compiled_files={}, file_path=None, metadata_={}
    )
    result = static_quality_gate.run_static_quality_gate(script)
    assert result.passed is False
    assert any(v.code == "missing_generation_header" for v in result.violations)


# ── Compiler output shape ────────────────────────────────────────────────────


def test_bundle_is_multi_file_with_a_real_entry_path():
    bundle = compiled()
    assert bundle.entry_path in bundle.files
    assert bundle.entry_path.startswith("specs/")
    assert any(p.startswith("pages/") for p in bundle.files)
    assert bundle.execution_command.startswith("npx playwright test")


def test_compilation_is_deterministic():
    """Two compiles of the same contract must be byte-identical, or a recompile
    would look like a change and churn the version chain."""
    assert compiled().files == compiled().files


def test_unsupported_contract_version_is_refused():
    payload = {**CONTRACT, "contractVersion": "9.9"}
    with pytest.raises(Exception):
        # Rejected at the model boundary — ContractVersion is a closed Literal,
        # so an unsupported version cannot even be constructed.
        AutomationGenerationContract.model_validate(payload)


# ── Framework mapping ────────────────────────────────────────────────────────


def test_every_script_type_maps_to_a_runner_framework():
    """A ScriptType with no mapping would silently fall back to playwright and
    run the wrong runner."""
    from app.agents.automation.generation_contract import ScriptType

    for script_type in ScriptType.__args__:
        assert script_type in _FRAMEWORK_FOR_SCRIPT_TYPE, script_type
    assert set(_FRAMEWORK_FOR_SCRIPT_TYPE.values()) <= {"playwright", "pytest"}


def test_pytest_contract_compiles_to_a_pytest_bundle():
    payload = {**CONTRACT, "scriptType": "pytest-python"}
    bundle = compiler.compile_contract(AutomationGenerationContract.model_validate(payload))
    assert bundle.entry_path.endswith(".py")
    assert bundle.execution_command.startswith("pytest")


# ── The element-action list shared with UI-020's picker ──────────────────────


def test_element_required_actions_is_the_list_the_validator_enforces():
    """UI-020's picker offers exactly these. If the tuple and the validator ever
    diverge the form would offer a shape that cannot be saved."""
    payload = {
        **CONTRACT,
        "steps": CONTRACT["steps"] + [{"phase": "act", "action": "click", "target": None}],
    }
    with pytest.raises(Exception):
        AutomationGenerationContract.model_validate(payload)
    assert "click" in ELEMENT_REQUIRED_ACTIONS_TUPLE
    assert "navigate" not in ELEMENT_REQUIRED_ACTIONS_TUPLE


# ── Base URL resolution ───────────────────────────────────────────────────────
# A live run failed with `page.goto: Cannot navigate to invalid URL ... "/"`
# because _base_url fell back to a hardcoded "QA" the application did not have,
# resolved nothing, and left the Playwright config with no baseURL. Guessing an
# environment name is worse than using the real one or refusing.

import pytest
from types import SimpleNamespace

from app.services.automation_asset import script_service
from app.services.automation_suite.errors import AutomationSuiteError


class _DB:
    def __init__(self, test_case=None, application=None):
        self._test_case = test_case
        self._application = application

    async def get(self, model, pk):
        name = getattr(model, "__name__", "")
        if name == "TestCase":
            return self._test_case
        if name == "ProjectApplication":
            return self._application
        return None


def _app(**urls):
    return SimpleNamespace(id=13, name="WebApp", environment_urls=dict(urls))


def _member(environment=None):
    return SimpleNamespace(id=21, test_case_id=25, resolved_environment=environment)


def _suite(default_environment=None):
    return SimpleNamespace(id=6, project_id=5, default_environment=default_environment)


def _test_case(application_id=13):
    return SimpleNamespace(id=25, application_id=application_id)


@pytest.mark.asyncio
async def test_member_environment_is_used_when_it_resolves():
    db = _DB(_test_case(), _app(Regression="https://rankix.ai/", QA="https://qa.example"))
    url = await script_service._base_url(db, _member("Regression"), _suite())
    assert url == "https://rankix.ai/"


@pytest.mark.asyncio
async def test_suite_default_environment_is_the_next_fallback():
    db = _DB(_test_case(), _app(Regression="https://rankix.ai/", QA="https://qa.example"))
    url = await script_service._base_url(db, _member(None), _suite("QA"))
    assert url == "https://qa.example"


@pytest.mark.asyncio
async def test_sole_configured_environment_is_used_rather_than_guessing():
    """The live failure: environment unset, and the app has only 'Regression'.
    The old code guessed 'QA', found nothing, and produced goto('/')."""
    db = _DB(_test_case(), _app(Regression="https://rankix.ai/"))
    url = await script_service._base_url(db, _member(None), _suite(None))
    assert url == "https://rankix.ai/"


@pytest.mark.asyncio
async def test_ambiguous_environment_refuses_and_names_the_options():
    """Two environments and no stated choice — refusing beats picking one."""
    db = _DB(_test_case(), _app(SIT="https://sit.example", QA="https://qa.example"))
    with pytest.raises(AutomationSuiteError) as exc:
        await script_service._base_url(db, _member(None), _suite(None))
    assert exc.value.detail["code"] == "NO_ENVIRONMENT_URL"
    assert "QA" in exc.value.detail["message"] and "SIT" in exc.value.detail["message"]


@pytest.mark.asyncio
async def test_unknown_environment_name_refuses_rather_than_running_blind():
    db = _DB(_test_case(), _app(SIT="https://sit.example", QA="https://qa.example"))
    with pytest.raises(AutomationSuiteError) as exc:
        await script_service._base_url(db, _member("Staging"), _suite(None))
    assert exc.value.detail["code"] == "NO_ENVIRONMENT_URL"
    assert "Staging" in exc.value.detail["message"]


@pytest.mark.asyncio
async def test_application_with_no_urls_refuses():
    db = _DB(_test_case(), _app())
    with pytest.raises(AutomationSuiteError) as exc:
        await script_service._base_url(db, _member(None), _suite(None))
    assert exc.value.detail["code"] == "NO_ENVIRONMENT_URL"
    assert "none" in exc.value.detail["message"]
