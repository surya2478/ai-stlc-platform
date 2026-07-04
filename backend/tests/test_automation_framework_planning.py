from app.integrations.automation.framework_adapters import assess_framework_fit, suitability_assessment


def test_assess_framework_fit_prefers_playwright_for_ui_flows():
    test_case = {
        "title": "Customer activates eSIM from account portal",
        "test_type": "UI",
        "steps": [
            {"action": "Open browser and navigate to account portal", "expected_result": "Portal loads"},
            {"action": "Click Activate eSIM and confirm", "expected_result": "Activation completes"},
        ],
        "bdd_scenario": "Given a customer is logged in When they activate eSIM Then activation succeeds",
        "execution_mode": "automated",
        "automation_ready": True,
        "priority": "High",
    }

    result = assess_framework_fit(test_case)

    assert result["recommended_framework"] == "playwright"
    assert result["framework_scores"]["playwright"] > result["framework_scores"]["pytest"]
    assert result["reasons"]


def test_assess_framework_fit_prefers_pytest_for_api_validation():
    test_case = {
        "title": "Validate activation service response schema",
        "test_type": "API",
        "steps": [{"action": "Send API request", "expected_result": "Response schema is valid"}],
        "expected_result": "Status code 200 and payload schema validation passes",
        "execution_mode": "hybrid",
        "automation_ready": True,
        "priority": "Medium",
    }

    result = assess_framework_fit(test_case)

    assert result["recommended_framework"] == "pytest"
    assert result["framework_scores"]["pytest"] >= result["framework_scores"]["playwright"]


def test_suitability_assessment_rewards_approved_ready_cases():
    test_case = {
        "status": "approved",
        "automation_eligible": "yes",
        "automation_ready": True,
        "steps": [{"action": "Step 1", "expected_result": "Done"}],
        "bdd_scenario": "Given state When action Then result",
        "last_automation_status": "passed",
    }

    result = suitability_assessment(test_case)

    assert result["band"] in {"high", "medium"}
    assert result["score"] >= 75
    assert any("Approved" in reason for reason in result["reasons"])
