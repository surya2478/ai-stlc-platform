"""UI-020 IR Editor — validation and error anchoring. Pure, no DB fake needed.

Acceptance criteria 3 and 4 of the contract hang on this module: a target can
never be typed, and an invalid edit surfaces the real pydantic message inline
against the offending row. The anchoring tests are what make "inline" true —
`_targets_resolve_to_real_elements` is a model-level validator, so pydantic
reports it with an empty `loc` and the editor would otherwise only be able to
show a page-level error.
"""
import copy

import pytest

from app.services.automation_asset.ir_service import _target_anchors, validate_contract

BASE = {
    "contractVersion": "1.0",
    "testCaseId": "TC-101",
    "requirementId": "REQ-0042",
    "scriptType": "playwright-typescript",
    "environmentProfile": "QA",
    "businessFlow": "Login happy path",
    "pageObjects": [
        {
            "name": "LoginPage",
            "route": "/auth/login",
            "elements": [
                {"name": "usernameInput", "locatorStrategy": "testid", "locatorValue": "username"},
                {"name": "loginButton", "locatorStrategy": "role", "locatorValue": "Login",
                 "roleHint": "button"},
            ],
        }
    ],
    "steps": [
        {"phase": "arrange", "action": "navigate", "target": "/auth/login"},
        {"phase": "act", "action": "fill", "target": "LoginPage.usernameInput", "value": "x"},
        {"phase": "act", "action": "click", "target": "LoginPage.loginButton"},
    ],
    "assertions": [{"type": "url", "target": "page", "expected": "/dashboard"}],
}


def contract(**overrides):
    payload = copy.deepcopy(BASE)
    payload.update(overrides)
    return payload


def with_step(step):
    payload = copy.deepcopy(BASE)
    payload["steps"].append(step)
    return payload


# ── Happy path ───────────────────────────────────────────────────────────────


def test_valid_contract_reports_a_summary():
    result = validate_contract(BASE)
    assert result["valid"] is True
    assert result["errors"] == []
    s = result["summary"]
    assert s["step_count"] == 3
    assert s["custom_step_count"] == 0
    assert s["locator_count"] == 2
    assert s["ready_for_compile"] is True


def test_custom_steps_block_compile_readiness():
    """A custom step is the emitter's honest TODO — it compiles to a comment,
    so the asset is not ready even though the contract is valid."""
    payload = with_step(
        {"phase": "act", "action": "custom", "description": "confirm the SMS arrived"}
    )
    result = validate_contract(payload)
    assert result["valid"] is True
    assert result["summary"]["custom_step_count"] == 1
    assert result["summary"]["custom_step_indexes"] == [3]
    assert result["summary"]["ready_for_compile"] is False


# ── Invalid drafts are a normal state, not an exception ──────────────────────


def test_invalid_contract_returns_valid_false_rather_than_raising():
    result = validate_contract(with_step(
        {"phase": "act", "action": "click", "target": "Nope.missing"}
    ))
    assert result["valid"] is False
    assert result["summary"] is None
    assert result["errors"]


def test_garbage_payload_does_not_raise():
    result = validate_contract({"nonsense": True})
    assert result["valid"] is False
    assert isinstance(result["errors"], list)


# ── Error anchoring (acceptance criterion 4) ─────────────────────────────────


@pytest.mark.parametrize(
    "step,expected_fragment",
    [
        ({"phase": "act", "action": "click", "target": "LoginPage.nope"},
         "does not match any declared"),
        ({"phase": "act", "action": "click", "target": "LoginPage"},
         "is not a <PageObject>.<element>"),
        ({"phase": "act", "action": "click", "target": "page"},
         "only valid for url assertions"),
        ({"phase": "act", "action": "fill", "target": None},
         "needs a specific element"),
    ],
)
def test_every_bad_target_is_anchored_to_its_row(step, expected_fragment):
    payload = with_step(step)
    result = validate_contract(payload)
    assert result["valid"] is False
    anchored = [e for e in result["errors"] if e["field"] == "steps.3.target"]
    assert anchored, f"no row anchor produced; got {result['errors']}"
    assert expected_fragment in anchored[0]["message"]


def test_bad_assertion_target_is_anchored():
    payload = copy.deepcopy(BASE)
    payload["assertions"].append(
        {"type": "visible", "target": "LoginPage.ghost", "expected": "true"}
    )
    result = validate_contract(payload)
    assert result["valid"] is False
    assert any(e["field"] == "assertions.1.target" for e in result["errors"])


def test_anchors_skip_actions_that_take_no_element():
    """navigate, custom and wait_for_url are not element-driven, so they must
    never be flagged for a missing target."""
    payload = copy.deepcopy(BASE)
    payload["steps"] += [
        {"phase": "act", "action": "navigate", "target": "/somewhere"},
        {"phase": "act", "action": "custom", "description": "manual step"},
        {"phase": "assert", "action": "wait_for_url", "value": "/done"},
    ]
    assert _target_anchors(payload) == []


def test_url_assertion_on_page_is_allowed():
    assert _target_anchors(BASE) == []


def test_multiple_bad_rows_each_get_their_own_anchor():
    payload = copy.deepcopy(BASE)
    payload["steps"] += [
        {"phase": "act", "action": "click", "target": "A.b"},
        {"phase": "act", "action": "hover", "target": "C.d"},
    ]
    fields = {a["field"] for a in _target_anchors(payload)}
    assert fields == {"steps.3.target", "steps.4.target"}


def test_no_error_is_silently_dropped_when_anchoring():
    """Anchoring replaces unanchored *target* errors only. An unrelated failure
    — here an unsafe identifier — must still be reported."""
    payload = copy.deepcopy(BASE)
    payload["pageObjects"][0]["elements"].append(
        {"name": "bad-name!", "locatorStrategy": "css", "locatorValue": ".x"}
    )
    result = validate_contract(payload)
    assert result["valid"] is False
    assert any("safe identifier" in e["message"] for e in result["errors"])
