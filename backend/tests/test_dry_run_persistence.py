"""Phase 4.2: persistence of the automation_dry_run agent's output —
ExecutionRun/ExecutionResult rows tagged source_type="dry_run" + script
promotion to dry_run_passed only when every test passed."""
from types import SimpleNamespace

import anyio

from app.models.agent import AgentRun
from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult, ExecutionRun
from app.worker.tasks.agent_tasks import _build_dry_run_input, _persist_agent_artifacts


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


def _agent_run() -> AgentRun:
    return AgentRun(id=70, project_id=1, triggered_by=1, agent_name="automation_dry_run", status="running")


def test_dry_run_persistence_promotes_script_on_full_pass():
    script = AutomationScript(
        id=5, project_id=1, created_by=1, script_id="AS-0005", framework="playwright",
        code="x", status="static_passed",
    )
    db = _FakeDB(get_results={(AutomationScript, 5): script})
    run = _agent_run()
    agent_result = SimpleNamespace(data={"dry_runs": [{
        "script_id": 5, "run_status": "completed", "passed": True,
        "results": [{"name": "t1", "status": "pass", "duration_ms": 500}],
    }]})

    async def run_test():
        return await _persist_agent_artifacts(db, run, "automation_dry_run", {}, agent_result)

    output = anyio.run(run_test)

    exec_run = next(obj for obj in db.added if isinstance(obj, ExecutionRun))
    assert exec_run.source_type == "dry_run"
    assert exec_run.passed == 1
    exec_result = next(obj for obj in db.added if isinstance(obj, ExecutionResult))
    assert exec_result.status == "pass"
    assert script.status == "dry_run_passed"
    assert output["promoted_script_ids"] == [5]


def test_dry_run_persistence_does_not_promote_on_failure():
    script = AutomationScript(
        id=6, project_id=1, created_by=1, script_id="AS-0006", framework="playwright",
        code="x", status="static_passed",
    )
    db = _FakeDB(get_results={(AutomationScript, 6): script})
    run = _agent_run()
    agent_result = SimpleNamespace(data={"dry_runs": [{
        "script_id": 6, "run_status": "completed", "passed": False,
        "results": [{"name": "t1", "status": "fail", "error_message": "boom"}],
    }]})

    async def run_test():
        return await _persist_agent_artifacts(db, run, "automation_dry_run", {}, agent_result)

    output = anyio.run(run_test)

    assert script.status == "static_passed"  # not promoted
    assert output["promoted_script_ids"] == []
    assert script.metadata_["last_dry_run"]["passed"] is False


def test_build_dry_run_input_only_includes_static_passed_scripts():
    static_passed = AutomationScript(
        id=1, project_id=1, created_by=1, script_id="AS-0001", framework="playwright",
        code="x", status="static_passed", test_case_id=10,
    )
    still_generated = AutomationScript(
        id=2, project_id=1, created_by=1, script_id="AS-0002", framework="playwright",
        code="x", status="generated", test_case_id=11,
    )
    db = _FakeDB(responses=[[static_passed, still_generated]])
    run = _agent_run()
    input_data = {"test_cases": [{"id": 10, "application_url": "http://app/", "test_phase": "SIT"}]}
    output_data = {"script_ids": [1, 2]}

    async def run_test():
        return await _build_dry_run_input(db, run, input_data, output_data)

    chain_input = anyio.run(run_test)

    assert len(chain_input["scripts"]) == 1
    assert chain_input["scripts"][0]["script_id"] == 1
    assert chain_input["scripts"][0]["application_url"] == "http://app/"
    assert chain_input["scripts"][0]["environment"] == "SIT"


def test_build_dry_run_input_returns_none_without_script_ids():
    db = _FakeDB()
    run = _agent_run()

    async def run_test():
        return await _build_dry_run_input(db, run, {}, {})

    assert anyio.run(run_test) is None
