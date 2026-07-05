"""Edge cases for execution_service._attach_test_suite_info — resolving a
run's Test Suite name/environment live from the Test Cases module (rather
than a snapshot frozen at run-creation time), added for the automation
Command Center's "All Runs" rail.
"""
import anyio

from app.models.execution import ExecutionRun
from app.services.execution_service import _attach_test_suite_info


class _ExecResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _QueueDB:
    """`db.execute()` returns each queued response in call order — mirrors
    the exact sequence _attach_test_suite_info issues: (1) run_id/test_case_id
    pairs, (2) test_case_id/test_suite_id pairs, (3) suite id/name/environment
    triples."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    async def execute(self, _stmt):
        self.call_count += 1
        return _ExecResult(self.responses.pop(0))


def _run(run_id: int) -> ExecutionRun:
    return ExecutionRun(
        id=run_id, project_id=1, execution_id=f"ER-{run_id:04d}", status="completed",
        execution_type="automation", total_tests=1, passed=1, failed=0, skipped=0,
    )


def test_empty_runs_list_is_a_no_op_and_issues_no_queries():
    async def go():
        db = _QueueDB([])
        await _attach_test_suite_info(db, [])
        assert db.call_count == 0

    anyio.run(go)


def test_run_with_no_execution_results_gets_no_suite_attributes():
    async def go():
        db = _QueueDB([[]])  # no (run_id, test_case_id) pairs at all
        run = _run(1)
        await _attach_test_suite_info(db, [run])
        assert not hasattr(run, "test_suite_name")
        assert db.call_count == 1  # short-circuits after the first (empty) query

    anyio.run(go)


def test_test_case_without_a_suite_assignment_yields_no_attributes():
    async def go():
        db = _QueueDB([
            [(1, 10)],       # run 1 -> test_case 10
            [(10, None)],    # test_case 10 has no test_suite_id
        ])
        run = _run(1)
        await _attach_test_suite_info(db, [run])
        assert not hasattr(run, "test_suite_name")
        assert db.call_count == 2  # short-circuits before the TestSuite query — nothing to look up

    anyio.run(go)


def test_single_suite_resolves_name_and_environment():
    async def go():
        db = _QueueDB([
            [(1, 10), (1, 11)],           # run 1 -> test_cases 10, 11
            [(10, 100), (11, 100)],       # both in suite 100
            [(100, "Regression001", "Regression")],
        ])
        run = _run(1)
        await _attach_test_suite_info(db, [run])
        assert run.test_suite_name == "Regression001"
        assert run.test_environment == "Regression"

    anyio.run(go)


def test_mixed_suites_attribute_to_the_dominant_one():
    """An "All Eligible" run isn't suite-scoped, so its results can span
    more than one suite — we attribute the run to whichever suite the
    majority of its test cases belong to."""
    async def go():
        db = _QueueDB([
            [(1, 10), (1, 11), (1, 12)],           # 3 test cases in run 1
            [(10, 200), (11, 200), (12, 300)],     # 2 in suite 200, 1 in suite 300
            [(200, "Regression001", "Regression"), (300, "SmokeSuite", "SIT")],
        ])
        run = _run(1)
        await _attach_test_suite_info(db, [run])
        assert run.test_suite_name == "Regression001"  # majority (2 of 3)
        assert run.test_environment == "Regression"

    anyio.run(go)


def test_multiple_runs_each_get_their_own_suite_independently():
    async def go():
        db = _QueueDB([
            [(1, 10), (2, 20)],
            [(10, 100), (20, 200)],
            [(100, "Regression001", "Regression"), (200, "SIT-Core", "SIT")],
        ])
        run1, run2 = _run(1), _run(2)
        await _attach_test_suite_info(db, [run1, run2])
        assert run1.test_suite_name == "Regression001"
        assert run1.test_environment == "Regression"
        assert run2.test_suite_name == "SIT-Core"
        assert run2.test_environment == "SIT"

    anyio.run(go)


def test_run_with_results_but_none_carrying_a_test_case_id_is_skipped():
    """ExecutionResult.test_case_id is nullable (e.g. manually-added rows);
    the query already filters these out, so the pairs list would simply be
    empty for that run — verifies no crash when a run has zero eligible pairs
    while another run in the same batch does have some."""
    async def go():
        db = _QueueDB([
            [(2, 20)],           # only run 2 has an eligible pair; run 1 has none
            [(20, 200)],
            [(200, "SIT-Core", "SIT")],
        ])
        run1, run2 = _run(1), _run(2)
        await _attach_test_suite_info(db, [run1, run2])
        assert not hasattr(run1, "test_suite_name")
        assert run2.test_suite_name == "SIT-Core"

    anyio.run(go)
