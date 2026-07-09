from app.agents.automation.generation_contract import AutomationGenerationContract
from app.models.automation_script import AutomationScript
from app.services.script_compiler import compile_contract
from app.services.static_quality_gate import run_static_quality_gate

LOGIN_CONTRACT = {
    "contractVersion": "1.0",
    "testCaseId": "TC-0001",
    "requirementId": "REQ-0001",
    "scriptType": "playwright-typescript",
    "environmentProfile": "QA",
    "businessFlow": "Valid login succeeds",
    "pageObjects": [{
        "name": "LoginPage",
        "elements": [{"name": "usernameInput", "locatorStrategy": "label", "locatorValue": "Username"}],
    }],
    "steps": [{"phase": "act", "action": "fill", "target": "LoginPage.usernameInput", "value": "someone"}],
    "assertions": [{"type": "url", "target": "page", "expected": "dashboard"}],
}


def _compiled_script(**overrides) -> AutomationScript:
    contract = AutomationGenerationContract.model_validate(LOGIN_CONTRACT)
    bundle = compile_contract(contract)
    defaults = dict(
        id=1, project_id=1, created_by=1, script_id="AS-1", framework="playwright",
        code=bundle.files[bundle.entry_path], file_path=bundle.entry_path,
        compiled_files=dict(bundle.files), status="generated",
    )
    defaults.update(overrides)
    return AutomationScript(**defaults)


def test_compiled_script_passes_the_gate():
    result = run_static_quality_gate(_compiled_script())
    assert result.passed is True
    assert result.violations == []


def test_raw_script_without_generation_header_is_blocked():
    raw = AutomationScript(
        id=2, project_id=1, created_by=1, script_id="AS-2", framework="playwright",
        code="test('x', async ({ page }) => { await page.click('#foo'); });", status="ai_draft",
    )
    result = run_static_quality_gate(raw)
    assert result.passed is False
    codes = {v.code for v in result.violations}
    assert "missing_generation_header" in codes
    assert "missing_tc_req_mapping" in codes


def _script_with_hard_wait(**overrides) -> AutomationScript:
    base = _compiled_script()
    code_with_wait = base.code + "\nawait page.waitForTimeout(5000);\n"
    compiled_files = dict(base.compiled_files)
    compiled_files[base.file_path] = code_with_wait
    return _compiled_script(code=code_with_wait, compiled_files=compiled_files, **overrides)


def test_hard_wait_is_blocking_by_default():
    result = run_static_quality_gate(_script_with_hard_wait())
    assert result.passed is False
    assert any(v.code == "hard_wait" for v in result.violations)


def test_hard_wait_becomes_a_warning_with_accepted_exception():
    script = _script_with_hard_wait(metadata_={"static_gate_exceptions": ["hard_wait"]})
    result = run_static_quality_gate(script)
    assert result.passed is True
    assert any(w.code == "hard_wait" for w in result.warnings)
    assert not any(v.code == "hard_wait" for v in result.violations)


def test_weak_locator_in_a_page_object_file_is_a_warning_not_a_blocker():
    # Locators typically live in the page-object file, not the spec — the
    # gate must scan the whole compiled bundle, not just script.code.
    base = _compiled_script()
    compiled_files = dict(base.compiled_files)
    compiled_files["pages/LoginPage.ts"] = compiled_files["pages/LoginPage.ts"].replace(
        "page.getByLabel('Username')", "page.locator('#username')"
    )
    script = _compiled_script(compiled_files=compiled_files)
    result = run_static_quality_gate(script)
    assert any(w.code == "weak_locator" for w in result.warnings)
    assert result.passed is True
