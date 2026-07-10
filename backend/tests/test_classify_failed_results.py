"""automation_service.classify_failed_results: real (local subprocess
runner) executions never went through the dry-run chain's
failure_classification agent — automation_tasks.run_automation_script has
no agent wiring at all, so a real failure's class was invisible until
someone clicked "Repair script" for that one result. This classifies every
not-yet-classified failure on a run automatically, so the class is already
on the ExecutionResult by the time the UI renders it."""
import anyio

from app.models.execution import ExecutionResult
from app.services.automation_service import classify_failed_results


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarsResult(self._values)


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows
        self.flush_calls = 0

    async def execute(self, _stmt):
        return _ExecuteResult(self._rows)

    async def flush(self):
        self.flush_calls += 1


def _result(**overrides) -> ExecutionResult:
    data = {
        "id": 1, "execution_run_id": 70, "project_id": 8, "test_name": "t1", "status": "fail",
    }
    data.update(overrides)
    return ExecutionResult(**data)


def test_classifies_an_unclassified_failure_via_rules():
    row = _result(error_message="Test timeout of 30000ms exceeded.")
    db = _FakeDB([row])

    async def run():
        return await classify_failed_results(db, execution_run_id=70)

    count = anyio.run(run)

    assert count == 1
    assert row.metadata_["failure_classification"]["classification"] == "timeout"
    assert row.metadata_["failure_classification"]["source"] == "rules"
    assert db.flush_calls == 1


def test_skips_a_result_that_is_already_classified():
    row = _result(metadata_={"failure_classification": {
        "classification": "data_issue", "reason": "x", "source": "rules", "repairable": False,
    }})
    db = _FakeDB([row])

    async def run():
        return await classify_failed_results(db, execution_run_id=70)

    count = anyio.run(run)

    assert count == 0
    assert row.metadata_["failure_classification"]["classification"] == "data_issue"  # untouched
    assert db.flush_calls == 0  # nothing to persist — no wasted write


def test_classifies_multiple_results_independently():
    rows = [
        _result(id=1, error_message="waiting for locator('button')"),
        _result(id=2, error_message="net::ERR_CONNECTION_REFUSED"),
    ]
    db = _FakeDB(rows)

    async def run():
        return await classify_failed_results(db, execution_run_id=70)

    count = anyio.run(run)

    assert count == 2
    assert rows[0].metadata_["failure_classification"]["classification"] == "locator_issue"
    assert rows[1].metadata_["failure_classification"]["classification"] == "environment_issue"


def test_no_failures_is_a_no_op():
    db = _FakeDB([])

    async def run():
        return await classify_failed_results(db, execution_run_id=70)

    assert anyio.run(run) == 0
    assert db.flush_calls == 0
