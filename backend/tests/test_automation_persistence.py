"""Phase 2: persistence of the retargeted automation_script agent's output
(compiled bundle + contract + immediate Static Quality Gate run) and the
automation_eligibility agent's output."""
from types import SimpleNamespace

import anyio

from app.agents.automation.generation_contract import AutomationGenerationContract
from app.models.agent import AgentRun
from app.models.automation_script import AutomationScript
from app.models.test_case import TestCase
from app.services.script_compiler import compile_contract
from app.worker.tasks.agent_tasks import _persist_agent_artifacts


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, value=None, values=None):
        self._value = value
        self._values = values if values is not None else []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return _ScalarsResult(self._values)


class _FakeDB:
    def __init__(self, *, responses=None, get_results=None):
        self.responses = list(responses or [])
        self.get_results = dict(get_results or {})
        self.added = []

    async def execute(self, _stmt):
        if not self.responses:
            return _ExecuteResult()
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _ExecuteResult(values=value)
        return _ExecuteResult(value=value)

    async def get(self, model, obj_id):
        return self.get_results.get((model, obj_id))

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 1
        self.added.append(obj)

    async def flush(self):
        return None


def _agent_run(agent_name: str) -> AgentRun:
    return AgentRun(id=50, project_id=1, triggered_by=1, agent_name=agent_name, status="running")


def _compiled_script_data(test_case_id: str) -> dict:
    contract = AutomationGenerationContract.model_validate({
        "contractVersion": "1.0",
        "testCaseId": test_case_id,
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
    })
    bundle = compile_contract(contract)
    return {
        "test_case_id": test_case_id,
        "framework": "playwright",
        "file_path": bundle.entry_path,
        "code": bundle.files[bundle.entry_path],
        "compiled_files": bundle.files,
        "contract": contract.model_dump(by_alias=True, mode="json"),
        "setup_required": bundle.setup_required,
        "execution_command": bundle.execution_command,
    }


def test_automation_script_persistence_runs_gate_and_marks_static_passed():
    db = _FakeDB(responses=[None])  # one coverage_matrix get_entry check -> no baseline row
    run = _agent_run("automation_script")
    input_data = {"test_cases": [{"test_case_id": "TC-0001", "id": 5}], "framework": "playwright"}
    agent_result = SimpleNamespace(data={"scripts": [_compiled_script_data("TC-0001")]})

    async def run_test():
        return await _persist_agent_artifacts(db, run, "automation_script", input_data, agent_result)

    output = anyio.run(run_test)

    script = next(obj for obj in db.added if isinstance(obj, AutomationScript))
    assert script.status == "static_passed"
    assert script.static_gate_result["passed"] is True
    assert script.compiled_files is not None
    assert script.contract["testCaseId"] == "TC-0001"
    assert output["count"] == 1


def test_automation_script_persistence_flags_gate_failure_without_promoting_status():
    db = _FakeDB(responses=[None])
    run = _agent_run("automation_script")
    input_data = {"test_cases": [{"test_case_id": "TC-0002", "id": 6}], "framework": "playwright"}
    script_data = _compiled_script_data("TC-0002")
    script_data["code"] = "test('x', async ({ page }) => { await page.click('#foo'); });"  # no header at all
    agent_result = SimpleNamespace(data={"scripts": [script_data]})

    async def run_test():
        return await _persist_agent_artifacts(db, run, "automation_script", input_data, agent_result)

    anyio.run(run_test)

    script = next(obj for obj in db.added if isinstance(obj, AutomationScript))
    assert script.status == "generated"  # never promoted past generated
    assert script.static_gate_result["passed"] is False


def test_automation_eligibility_persistence_updates_test_case_and_matrix():
    tc = TestCase(
        id=5, project_id=1, created_by=1, test_case_id="TC-0001", title="Valid login",
        automation_eligible="unknown", automation_status="not_required",
    )
    db = _FakeDB(get_results={(TestCase, 5): tc}, responses=[None])  # coverage_matrix get_entry -> skip
    run = _agent_run("automation_eligibility")
    input_data = {"test_cases": [{"test_case_id": "TC-0001", "id": 5}]}
    agent_result = SimpleNamespace(data={
        "results": [{"test_case_id": "TC-0001", "verdict": "yes", "reason": "no blockers", "automation_style": "ui"}],
        "summary": {"yes": 1, "no": 0, "unknown": 0},
    })

    async def run_test():
        return await _persist_agent_artifacts(db, run, "automation_eligibility", input_data, agent_result)

    output = anyio.run(run_test)

    assert tc.automation_eligible == "yes"
    assert tc.automation_status == "ready_for_automation"
    assert tc.metadata_["automation_eligibility"]["reason"] == "no blockers"
    assert output["count"] == 1
