"""The reaper's whole job is choosing correctly between "this worker is dead"
and "this agent is still thinking". Getting that wrong in one direction leaves
the spinner that motivated it; in the other it destroys work in progress."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import anyio

from app.worker.tasks import agent_reaper_tasks as reaper


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarsResult(self._values)


class _FakeDB:
    def __init__(self, runs):
        self.runs = runs
        self.committed = 0

    async def execute(self, _stmt):
        return _ExecuteResult(self.runs)

    async def commit(self):
        self.committed += 1

    async def flush(self):
        return None


def _run(run_id: int, agent_name: str, *, age_seconds: float, status: str = "running",
         updated_age_seconds: float | None = None):
    created = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    updated = (
        created if updated_age_seconds is None
        else datetime.now(timezone.utc) - timedelta(seconds=updated_age_seconds)
    )
    return SimpleNamespace(
        id=run_id,
        agent_name=agent_name,
        status=status,
        output_data=None,
        created_at=created,
        updated_at=updated,
    )


def _install(monkeypatch, runs):
    """Point the reaper at a fake session and record what it fails."""
    db = _FakeDB(runs)
    failed: list[tuple[int, str]] = []

    class _Session:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_exc):
            return False

    async def _fail(_db, run, *, error_message, output_data=None):
        run.status = "failed"
        failed.append((run.id, error_message))
        return run

    monkeypatch.setattr(reaper, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(reaper.agent_run_service, "fail_agent_run", _fail)
    return db, failed


def test_a_run_past_its_own_timeout_plus_grace_is_reaped(monkeypatch):
    # automation_script declares 900s; +300s grace = 1200s before it is
    # considered abandoned.
    runs = [_run(284, "automation_script", age_seconds=1500)]
    _db, failed = _install(monkeypatch, runs)

    result = anyio.run(reaper._reap_abandoned_agent_runs)

    assert result["reaped"] == [284]
    assert runs[0].status == "failed"
    assert "Interrupted" in failed[0][1]
    assert "re-run it to retry" in failed[0][1]


def test_a_long_agent_still_inside_its_budget_is_left_alone(monkeypatch):
    """The failure mode that matters most: automation_script legitimately runs
    for many minutes on a wave, without necessarily writing anything."""
    runs = [_run(300, "automation_script", age_seconds=800)]  # under 900 + 300
    _db, failed = _install(monkeypatch, runs)

    result = anyio.run(reaper._reap_abandoned_agent_runs)

    assert result["reaped"] == []
    assert failed == []
    assert runs[0].status == "running"


def test_the_grace_period_protects_a_run_that_just_passed_its_ceiling(monkeypatch):
    """A run one second past its timeout is most likely being failed by its own
    runner right now — reaping it would race that and double-report."""
    runs = [_run(301, "automation_script", age_seconds=901)]
    _db, failed = _install(monkeypatch, runs)

    assert anyio.run(reaper._reap_abandoned_agent_runs)["reaped"] == []


def test_each_agent_is_judged_against_its_own_ceiling(monkeypatch):
    """automation_eligibility declares 60s and repair_loop 1800s — one age must
    not be applied to both."""
    runs = [
        _run(310, "automation_eligibility", age_seconds=400),   # 60 + 300 = 360 -> reap
        _run(311, "automation_repair_loop", age_seconds=400),   # 1800 + 300  -> keep
    ]
    _db, _failed = _install(monkeypatch, runs)

    assert anyio.run(reaper._reap_abandoned_agent_runs)["reaped"] == [310]


def test_a_pending_run_that_never_started_is_reaped_too(monkeypatch):
    """A task lost between enqueue and pickup never reaches a worker at all, so
    nothing would ever move it off pending."""
    runs = [_run(320, "automation_eligibility", age_seconds=400, status="pending")]
    _db, failed = _install(monkeypatch, runs)

    assert anyio.run(reaper._reap_abandoned_agent_runs)["reaped"] == [320]


def test_an_unknown_agent_name_still_gets_a_ceiling(monkeypatch):
    """A renamed or deleted agent must not leave its rows unreapable forever."""
    runs = [_run(330, "an_agent_that_no_longer_exists", age_seconds=1000)]
    _db, _failed = _install(monkeypatch, runs)

    # FALLBACK_TIMEOUT_SECONDS (120) + grace (300) = 420
    assert anyio.run(reaper._reap_abandoned_agent_runs)["reaped"] == [330]


def test_nothing_to_reap_does_not_commit(monkeypatch):
    runs = [_run(340, "automation_script", age_seconds=10)]
    db, _failed = _install(monkeypatch, runs)

    anyio.run(reaper._reap_abandoned_agent_runs)

    assert db.committed == 0


def test_a_naive_created_at_is_treated_as_utc_not_crashed_on(monkeypatch):
    """Some deployments store this column naive; comparing it to an aware now()
    raises TypeError and would take the whole sweep down with it."""
    run = _run(350, "automation_script", age_seconds=1500)
    run.created_at = run.created_at.replace(tzinfo=None)
    run.updated_at = run.updated_at.replace(tzinfo=None)
    _db, _failed = _install(monkeypatch, [run])

    assert anyio.run(reaper._reap_abandoned_agent_runs)["reaped"] == [350]


def test_a_requeued_run_is_judged_from_its_retry_not_its_original_creation(monkeypatch):
    """enqueue_agent_run reuses a failed run's row in place rather than
    inserting a new one, so a retried run keeps an ancient created_at. Judging
    it by that would reap a legitimately running retry on the next sweep — which
    is exactly what the Studio retry button would have triggered."""
    run = _run(360, "automation_script", age_seconds=90_000, updated_age_seconds=30)
    _db, failed = _install(monkeypatch, [run])

    assert anyio.run(reaper._reap_abandoned_agent_runs)["reaped"] == []
    assert failed == []


def test_an_abandoned_run_is_still_reaped_when_both_timestamps_are_old(monkeypatch):
    """The monotonic max() must not become a way to never reap anything."""
    run = _run(361, "automation_script", age_seconds=90_000, updated_age_seconds=5000)

    _db, _failed = _install(monkeypatch, [run])

    assert anyio.run(reaper._reap_abandoned_agent_runs)["reaped"] == [361]
