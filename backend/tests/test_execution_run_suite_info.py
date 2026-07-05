"""Edge cases for execution_service._attach_test_suite_info — resolving a
run's Test Suite name and Test Environment live from the Test Cases module
(rather than a snapshot frozen at run-creation time), added for the
automation Command Center's "All Runs" rail.

Test Suite name comes from TestCase.test_suite_id -> TestSuite.name.
Test Environment comes from TestCase.test_phase directly — this is the
field the Test Cases module actually labels "Test Environment"; it is NOT
TestSuite.environment (a separate column most projects leave unset), which
is why the two are resolved independently rather than from one dominant
test case.
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
    the sequence _attach_test_suite_info issues: (1) run_id/test_case_id
    pairs, (2) test_case_id/test_suite_id/test_phase triples, (3, only if
    any suite id was found) suite id/name pairs."""

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


def test_run_with_no_execution_results_gets_no_attributes():
    async def go():
        db = _QueueDB([[]])  # no (run_id, test_case_id) pairs at all
        run = _run(1)
        await _attach_test_suite_info(db, [run])
        assert not hasattr(run, "test_suite_name")
        assert not hasattr(run, "test_environment")
        assert db.call_count == 1  # short-circuits after the first (empty) query

    anyio.run(go)


def test_test_case_without_a_suite_still_resolves_environment():
    """A test case can have test_phase set but no test_suite_id (or vice
    versa) — the two must resolve independently, not both-or-nothing."""
    async def go():
        db = _QueueDB([
            [(1, 10)],                 # run 1 -> test_case 10
            [(10, None, "Regression")],  # no suite, but has a test_phase
        ])
        run = _run(1)
        await _attach_test_suite_info(db, [run])
        assert not hasattr(run, "test_suite_name")
        assert run.test_environment == "Regression"
        assert db.call_count == 2  # no suite ids found -> TestSuite query is skipped

    anyio.run(go)


def test_test_case_with_a_suite_but_no_test_phase_still_resolves_suite():
    async def go():
        db = _QueueDB([
            [(1, 10)],
            [(10, 100, None)],  # suite assigned, but test_phase unset
            [(100, "Regression001")],
        ])
        run = _run(1)
        await _attach_test_suite_info(db, [run])
        assert run.test_suite_name == "Regression001"
        assert not hasattr(run, "test_environment")

    anyio.run(go)


def test_single_test_case_resolves_both_suite_name_and_environment():
    async def go():
        db = _QueueDB([
            [(1, 10)],
            [(10, 100, "Regression")],
            [(100, "Regression001")],
        ])
        run = _run(1)
        await _attach_test_suite_info(db, [run])
        assert run.test_suite_name == "Regression001"
        assert run.test_environment == "Regression"

    anyio.run(go)


def test_mixed_suites_and_phases_attribute_to_the_dominant_value_each():
    """An "All Eligible" run isn't suite-scoped, so its results can span
    more than one suite/phase — each attribute goes to whichever value the
    majority of its test cases carry, independently of the other."""
    async def go():
        db = _QueueDB([
            [(1, 10), (1, 11), (1, 12)],
            [(10, 200, "Regression"), (11, 200, "SIT"), (12, 300, "SIT")],
            [(200, "Regression001"), (300, "SmokeSuite")],
        ])
        run = _run(1)
        await _attach_test_suite_info(db, [run])
        assert run.test_suite_name == "Regression001"  # 2 of 3 in suite 200
        assert run.test_environment == "SIT"  # 2 of 3 tagged SIT

    anyio.run(go)


def test_multiple_runs_each_get_their_own_values_independently():
    async def go():
        db = _QueueDB([
            [(1, 10), (2, 20)],
            [(10, 100, "Regression"), (20, 200, "SIT")],
            [(100, "Regression001"), (200, "SIT-Core")],
        ])
        run1, run2 = _run(1), _run(2)
        await _attach_test_suite_info(db, [run1, run2])
        assert run1.test_suite_name == "Regression001"
        assert run1.test_environment == "Regression"
        assert run2.test_suite_name == "SIT-Core"
        assert run2.test_environment == "SIT"

    anyio.run(go)


def test_run_with_no_matching_pairs_is_skipped_while_others_resolve():
    async def go():
        db = _QueueDB([
            [(2, 20)],  # only run 2 has an eligible pair; run 1 has none
            [(20, 200, "SIT")],
            [(200, "SIT-Core")],
        ])
        run1, run2 = _run(1), _run(2)
        await _attach_test_suite_info(db, [run1, run2])
        assert not hasattr(run1, "test_suite_name")
        assert not hasattr(run1, "test_environment")
        assert run2.test_suite_name == "SIT-Core"
        assert run2.test_environment == "SIT"

    anyio.run(go)
