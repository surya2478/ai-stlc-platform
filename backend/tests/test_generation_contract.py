from app.agents.automation.generation_contract import AutomationGenerationContract


def _minimal_data(**overrides):
    data = {
        "contractVersion": "1.0",
        "testCaseId": "TC-0001",
        "requirementId": "REQ-0001",
        "scriptType": "playwright-typescript",
        "environmentProfile": "QA",
        "businessFlow": "User logs in",
    }
    data.update(overrides)
    return data


def test_contract_parses_camelCase_aliases():
    contract = AutomationGenerationContract.model_validate(_minimal_data(
        pageObjects=[{
            "name": "LoginPage",
            "elements": [{"name": "usernameInput", "locatorStrategy": "label", "locatorValue": "Username"}],
        }],
    ))
    assert contract.test_case_id == "TC-0001"
    assert contract.page_objects[0].elements[0].locator_strategy == "label"


def test_contract_defaults_are_safe():
    contract = AutomationGenerationContract.model_validate(_minimal_data())
    assert contract.preconditions == []
    assert contract.steps == []
    assert contract.test_data_bindings == []
    assert contract.contract_version == "1.0"


def test_all_locators_flattens_across_page_objects():
    contract = AutomationGenerationContract.model_validate(_minimal_data(
        pageObjects=[
            {"name": "LoginPage", "elements": [
                {"name": "usernameInput", "locatorStrategy": "label", "locatorValue": "Username"},
                {"name": "submitButton", "locatorStrategy": "role", "locatorValue": "Sign in", "roleHint": "button"},
            ]},
            {"name": "DashboardPage", "elements": [
                {"name": "welcomeBanner", "locatorStrategy": "text", "locatorValue": "Welcome"},
            ]},
        ],
    ))
    assert len(contract.all_locators) == 3
    assert {el.name for el in contract.all_locators} == {"usernameInput", "submitButton", "welcomeBanner"}


def test_extra_fields_are_ignored_not_rejected():
    data = _minimal_data()
    data["somethingTheModelDoesNotKnowAbout"] = "should not raise"
    contract = AutomationGenerationContract.model_validate(data)
    assert contract.test_case_id == "TC-0001"


def test_step_action_and_locator_strategy_are_validated():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AutomationGenerationContract.model_validate(_minimal_data(
            steps=[{"phase": "act", "action": "not_a_real_action"}],
        ))


# ── Target resolution (real bug: a page object with zero elements used as a
# bare assertion target compiled to invalid TypeScript — `expect(PageClass)`
# instead of `expect(pageInstance.someElement)`) ──────────────────────────────

def test_assertion_target_must_resolve_to_a_declared_element():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="does not match any declared page object element"):
        AutomationGenerationContract.model_validate(_minimal_data(
            pageObjects=[{"name": "ResultsPage", "elements": []}],
            assertions=[{"type": "visible", "target": "ResultsPage.someElement", "expected": "true"}],
        ))


def test_assertion_target_must_include_element_not_just_page_object():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="is not a '<PageObject>.<element>' reference"):
        AutomationGenerationContract.model_validate(_minimal_data(
            pageObjects=[{"name": "ResultsPage", "elements": []}],
            assertions=[{"type": "visible", "target": "ResultsPage", "expected": "true"}],
        ))


def test_literal_page_target_rejected_for_non_url_assertions():
    # A live run produced `expect(page).toBeVisible()` — invalid, since
    # toBeVisible() is a Locator-only matcher; Page only supports
    # toHaveURL/toHaveTitle-style matchers. "page" is legitimate only where
    # the compiler hardcodes it regardless of target (url-type assertions).
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="target 'page' is only valid for url-type assertions"):
        AutomationGenerationContract.model_validate(_minimal_data(
            assertions=[{"type": "visible", "target": "page", "expected": "true"}],
        ))


def test_literal_page_target_rejected_for_element_interaction_steps():
    # `page.check()`/`page.click()`/`page.fill()` don't exist — only a
    # Locator has those methods.
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="target 'page' is only valid for url-type assertions"):
        AutomationGenerationContract.model_validate(_minimal_data(
            steps=[{"phase": "assert", "action": "check", "target": "page"}],
        ))


def test_assertion_type_url_is_exempt_from_target_resolution():
    # Renders as expect(page).toHaveURL(...) — target is conventionally the
    # literal "page", never a page-object element.
    contract = AutomationGenerationContract.model_validate(_minimal_data(
        assertions=[{"type": "url", "target": "page", "expected": "dashboard"}],
    ))
    assert contract.assertions[0].target == "page"


def test_navigate_and_custom_and_wait_for_url_steps_are_exempt_from_target_resolution():
    contract = AutomationGenerationContract.model_validate(_minimal_data(
        steps=[
            {"phase": "arrange", "action": "navigate", "value": "https://app.example.com/"},
            {"phase": "act", "action": "custom", "description": "Submit the form"},
            {"phase": "assert", "action": "wait_for_url", "value": "dashboard"},
        ],
    ))
    assert len(contract.steps) == 3


def test_fill_step_target_must_resolve_to_a_declared_element():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="does not match any declared page object element"):
        AutomationGenerationContract.model_validate(_minimal_data(
            pageObjects=[{"name": "LoginPage", "elements": [
                {"name": "usernameInput", "locatorStrategy": "label", "locatorValue": "Username"},
            ]}],
            steps=[{"phase": "act", "action": "fill", "target": "LoginPage.passwordInput"}],
        ))


def test_element_interaction_step_with_no_target_is_rejected():
    # A live run produced `await page.check();` from a "check" step with
    # target=null — playwright_renderer._resolve_target treats a missing
    # target exactly like the literal "page", and Page has no .check()
    # method (only Locator does).
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="has no target"):
        AutomationGenerationContract.model_validate(_minimal_data(
            steps=[{"phase": "assert", "action": "check", "target": None}],
        ))


def test_ui_action_cleanup_target_must_resolve_but_api_call_target_is_exempt():
    contract = AutomationGenerationContract.model_validate(_minimal_data(
        cleanupActions=[{"type": "api_call", "description": "Delete test record", "target": "/api/records/1"}],
    ))
    assert contract.cleanup_actions[0].target == "/api/records/1"

    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="does not match any declared page object element"):
        AutomationGenerationContract.model_validate(_minimal_data(
            pageObjects=[{"name": "LoginPage", "elements": []}],
            cleanupActions=[{"type": "ui_action", "description": "Log out", "target": "LoginPage.logoutButton"}],
        ))


def test_valid_targets_across_steps_assertions_and_ui_cleanup_pass():
    contract = AutomationGenerationContract.model_validate(_minimal_data(
        pageObjects=[{"name": "LoginPage", "elements": [
            {"name": "usernameInput", "locatorStrategy": "label", "locatorValue": "Username"},
            {"name": "logoutButton", "locatorStrategy": "role", "locatorValue": "Log out", "roleHint": "button"},
        ]}],
        steps=[{"phase": "act", "action": "fill", "target": "LoginPage.usernameInput"}],
        assertions=[{"type": "visible", "target": "LoginPage.usernameInput", "expected": "true"}],
        cleanupActions=[{"type": "ui_action", "description": "Log out", "target": "LoginPage.logoutButton"}],
    ))
    assert contract.test_case_id == "TC-0001"
