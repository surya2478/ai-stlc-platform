import anyio

from app.agents.automation.eligibility_agent import AutomationEligibilityAgent, classify_test_case


def test_classify_flags_otp_as_not_eligible():
    tc = {"test_case_id": "TC-1", "title": "Verify OTP login", "steps": [
        {"action": "Enter phone number and request OTP", "expected_result": "OTP received"},
    ]}
    result = classify_test_case(tc)
    assert result["verdict"] == "no"
    assert "OTP" in result["reason"]


def test_classify_flags_captcha_as_not_eligible():
    tc = {"title": "Register a new account", "steps": [{"action": "Solve the CAPTCHA and submit"}]}
    result = classify_test_case(tc)
    assert result["verdict"] == "no"


def test_classify_flags_physical_sim_environment_dependency():
    tc = {"title": "Activate service", "steps": [{"action": "Insert the physical SIM card into the device"}]}
    result = classify_test_case(tc)
    assert result["verdict"] == "no"
    assert "physical SIM" in result["reason"]


def test_classify_yes_for_ordinary_ui_flow():
    tc = {
        "title": "Valid login succeeds",
        "preconditions": ["User account exists"],
        "steps": [{"action": "Click the login button", "expected_result": "Dashboard is shown"}],
    }
    result = classify_test_case(tc)
    assert result["verdict"] == "yes"
    assert result["automation_style"] == "ui"


def test_classify_unknown_for_empty_test_case():
    result = classify_test_case({"test_case_id": "TC-9"})
    assert result["verdict"] == "unknown"


def test_classify_detects_api_only_style():
    tc = {"title": "Order API returns 201", "steps": [{"action": "POST /api/orders and check the response status"}]}
    result = classify_test_case(tc)
    assert result["automation_style"] == "api"


def test_classify_detects_mixed_style():
    tc = {"title": "Order flow", "steps": [
        {"action": "Click checkout"},
        {"action": "Call the /api/orders endpoint to confirm creation"},
    ]}
    result = classify_test_case(tc)
    assert result["automation_style"] == "mixed"


def test_agent_run_produces_summary_counts():
    async def run():
        return await AutomationEligibilityAgent().run(test_cases=[
            {"test_case_id": "TC-1", "title": "Valid login", "steps": [{"action": "click login"}]},
            {"test_case_id": "TC-2", "title": "OTP verification", "steps": [{"action": "enter OTP code"}]},
        ])

    result = anyio.run(run)
    assert result.success is True
    assert result.data["summary"]["yes"] == 1
    assert result.data["summary"]["no"] == 1


def test_agent_run_fails_when_no_test_cases_given():
    async def run():
        return await AutomationEligibilityAgent().run(test_cases=[])

    result = anyio.run(run)
    assert result.success is False
