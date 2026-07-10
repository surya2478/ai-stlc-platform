"""_consecutive_failure_streaks: how many times in a row (most recent
first) a test case has failed with the *same* error message.

Regression context: a test case could fail the same way across many
separate "Retry" clicks and nothing recorded that these were repeats of
each other — each ExecutionResult only ever knew about its own run. This
powers the "retrying this won't change the outcome" warning on the retry
button."""
import anyio

from app.services.automation_service import _consecutive_failure_streaks


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


def _row(tc_id, status, error, created_at="2026-07-10T00:00:00Z"):
    return (tc_id, status, error, created_at)


def test_no_results_means_no_streak():
    db = _FakeDB([])

    async def run():
        return await _consecutive_failure_streaks(db, project_id=8, test_case_ids=[110])

    assert anyio.run(run) == {}


def test_repeated_same_error_counts_the_full_streak():
    # Most-recent-first order, as the real query provides.
    rows = [
        _row(110, "fail", "Test timeout of 30000ms exceeded."),
        _row(110, "fail", "Test timeout of 30000ms exceeded."),
        _row(110, "fail", "Test timeout of 30000ms exceeded."),
    ]
    db = _FakeDB(rows)

    async def run():
        return await _consecutive_failure_streaks(db, project_id=8, test_case_ids=[110])

    result = anyio.run(run)
    assert result[110] == {"count": 3, "error_message": "Test timeout of 30000ms exceeded."}


def test_most_recent_pass_means_no_active_streak():
    rows = [
        _row(110, "pass", None),
        _row(110, "fail", "Test timeout of 30000ms exceeded."),
        _row(110, "fail", "Test timeout of 30000ms exceeded."),
    ]
    db = _FakeDB(rows)

    async def run():
        return await _consecutive_failure_streaks(db, project_id=8, test_case_ids=[110])

    assert anyio.run(run) == {}


def test_differing_error_breaks_the_streak():
    rows = [
        _row(110, "fail", "Test timeout of 30000ms exceeded."),
        _row(110, "fail", "Test timeout of 30000ms exceeded."),
        _row(110, "fail", "Cannot navigate to invalid URL"),
    ]
    db = _FakeDB(rows)

    async def run():
        return await _consecutive_failure_streaks(db, project_id=8, test_case_ids=[110])

    result = anyio.run(run)
    assert result[110] == {"count": 2, "error_message": "Test timeout of 30000ms exceeded."}


def test_streaks_are_independent_per_test_case():
    rows = [
        _row(110, "fail", "A"),
        _row(110, "fail", "A"),
        _row(109, "pass", None),
        _row(104, "fail", "B"),
    ]
    db = _FakeDB(rows)

    async def run():
        return await _consecutive_failure_streaks(db, project_id=8, test_case_ids=[110, 109, 104])

    result = anyio.run(run)
    assert result[110] == {"count": 2, "error_message": "A"}
    assert 109 not in result
    assert result[104] == {"count": 1, "error_message": "B"}


def test_error_status_and_blocked_status_count_as_failures():
    rows = [
        _row(110, "error", "Runner crashed"),
        _row(110, "blocked", "Runner crashed"),
    ]
    db = _FakeDB(rows)

    async def run():
        return await _consecutive_failure_streaks(db, project_id=8, test_case_ids=[110])

    result = anyio.run(run)
    assert result[110]["count"] == 2


def test_empty_test_case_ids_short_circuits_without_querying():
    class _ExplodingDB:
        async def execute(self, _stmt):
            raise AssertionError("should not query when test_case_ids is empty")

    async def run():
        return await _consecutive_failure_streaks(_ExplodingDB(), project_id=8, test_case_ids=[])

    assert anyio.run(run) == {}
