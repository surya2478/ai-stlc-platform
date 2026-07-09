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
