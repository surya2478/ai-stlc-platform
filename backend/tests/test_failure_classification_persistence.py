from types import SimpleNamespace

import anyio

from app.models.agent import AgentRun
from app.models.execution import ExecutionResult
from app.worker.tasks.agent_tasks import _build_failure_classification_input, _persist_agent_artifacts


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, values=None):
        self._values = values if values is not None else []

    def scalars(self):
        return _ScalarsResult(self._values)


class _FakeDB:
    def __init__(self, *, responses=None, get_results=None):
        self.responses = list(responses or [])
        self.get_results = dict(get_results or {})

    async def execute(self, _stmt):
        if not self.responses:
            return _ExecuteResult()
        return _ExecuteResult(values=self.responses.pop(0))

    async def get(self, model, obj_id):
        return self.get_results.get((model, obj_id))


def _agent_run(agent_name="failure_classification") -> AgentRun:
    return AgentRun(id=80, project_id=1, triggered_by=1, agent_name=agent_name, status="running")


def test_build_failure_classification_input_only_includes_non_passing_results():
    failed = ExecutionResult(
        id=1, execution_run_id=1, project_id=1, test_name="t1", status="fail",
        error_message="Timeout 5000ms exceeded", metadata_={"console_logs": [], "network_logs": []},
    )
    db = _FakeDB(responses=[[failed]])
    run = _agent_run()

    async def run_test():
        return await _build_failure_classification_input(db, run, {}, {})

    chain_input = anyio.run(run_test)
    assert len(chain_input["results"]) == 1
    assert chain_input["results"][0]["result_id"] == 1
    assert chain_input["results"][0]["error_message"] == "Timeout 5000ms exceeded"


def test_build_failure_classification_input_returns_none_when_nothing_failed():
    db = _FakeDB(responses=[[]])
    run = _agent_run()

    async def run_test():
        return await _build_failure_classification_input(db, run, {}, {})

    assert anyio.run(run_test) is None


def test_persistence_writes_classification_onto_execution_result():
    exec_result = ExecutionResult(id=9, execution_run_id=1, project_id=1, test_name="t1", status="fail")
    db = _FakeDB(get_results={(ExecutionResult, 9): exec_result})
    run = _agent_run()
    agent_result = SimpleNamespace(data={"classifications": [
        {"result_id": 9, "classification": "locator_issue", "reason": "stale selector", "source": "rules", "repairable": True},
    ]})

    async def run_test():
        return await _persist_agent_artifacts(db, run, "failure_classification", {}, agent_result)

    output = anyio.run(run_test)

    assert exec_result.metadata_["failure_classification"]["classification"] == "locator_issue"
    assert exec_result.metadata_["failure_classification"]["repairable"] is True
    assert output["classified_result_ids"] == [9]
