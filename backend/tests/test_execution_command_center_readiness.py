"""UI-046 five-way readiness gate.

No DB fixture exists in this suite, so the application lookup is faked the same
way `test_automation_suite_readiness.py` fakes its inputs. The runner probes and
the Celery ping are monkeypatched — this module's job is the five-axis rollup and
the blocking rules, not re-testing `automation_runner`'s HTTP checks.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.automation_runner import readiness as runner_readiness
from app.services.execution_command_center import readiness as gate


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """Returns one canned application for any select."""

    def __init__(self, application=None):
        self.application = application

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self.application)


def _patch_ping(monkeypatch, ping):
    """Replace `celery_app.control` with an object whose ping is `ping`."""
    import app.worker.celery_app as celery_module

    monkeypatch.setattr(
        celery_module.celery_app, "control", SimpleNamespace(ping=ping), raising=False
    )


def _application(**overrides):
    return SimpleNamespace(
        id=overrides.pop("id", 5),
        name=overrides.pop("name", "CRM Web"),
        environment_urls=overrides.pop("environment_urls", {"SIT-UAE-01": "https://sit.example.com"}),
    )


@pytest.fixture(autouse=True)
def _stub_probes(monkeypatch):
    """All probes green by default; each test degrades exactly one thing."""

    async def _all_good(_inputs):
        return runner_readiness.ReadinessResult(
            checks=[
                runner_readiness.ReadinessCheck("application_url_reachable", True, "200"),
                runner_readiness.ReadinessCheck("credentials_configured", True, "skipped"),
                runner_readiness.ReadinessCheck("test_data_present", True, "skipped"),
                runner_readiness.ReadinessCheck("api_dependency_healthy", True, "skipped"),
                runner_readiness.ReadinessCheck("db_validation_endpoint_reachable", True, "skipped"),
                runner_readiness.ReadinessCheck("browser_deps_installed", True, "playwright 1.53"),
                runner_readiness.ReadinessCheck("environment_not_under_maintenance", True, "ok"),
            ]
        )

    monkeypatch.setattr(gate.runner_readiness, "check_readiness", _all_good)
    monkeypatch.setattr(gate.preflight, "is_available", lambda f: (True, f"{f} available"))
    # Stub the broker rather than `_worker_check` itself, so the real check runs
    # here too and the tests further down can override it independently.
    _patch_ping(monkeypatch, lambda timeout=0: [{"celery@test": {"ok": "pong"}}])


async def _run(session=None, **kwargs):
    params = dict(
        application_id=5,
        environment="SIT-UAE-01",
        frameworks={"playwright"},
    )
    params.update(kwargs)
    return await gate.check_suite_run_readiness(
        session or _FakeSession(_application()), **params
    )


@pytest.mark.asyncio
async def test_all_five_axes_ready():
    result = await _run()
    assert result.ready is True
    assert set(result.as_dict()["axes"]) == set(gate.AXES)
    assert all(result.as_dict()["axes"].values())


@pytest.mark.asyncio
async def test_missing_environment_url_blocks_on_the_application_axis():
    session = _FakeSession(_application(environment_urls={"QA": "https://qa.example.com"}))
    result = await _run(session)
    assert result.ready is False
    assert result.axis_ready("application") is False
    # The operator needs to know which environments *are* configured.
    blocker = next(c for c in result.blockers if c.name == "application_url_configured")
    assert "QA" in blocker.detail and "SIT-UAE-01" in blocker.detail


@pytest.mark.asyncio
async def test_member_with_no_application_blocks():
    result = await _run(_FakeSession(None), application_id=None)
    assert result.ready is False
    assert result.axis_ready("application") is False


@pytest.mark.asyncio
async def test_deleted_application_blocks_with_a_specific_reason():
    result = await _run(_FakeSession(None))
    assert result.ready is False
    assert any("no longer exists" in c.detail for c in result.blockers)


@pytest.mark.asyncio
async def test_every_framework_in_a_mixed_suite_is_checked(monkeypatch):
    monkeypatch.setattr(
        gate.preflight,
        "is_available",
        lambda f: (f == "playwright", f"{f} availability"),
    )
    result = await _run(frameworks={"playwright", "katalon", "appium"})
    names = {c.name for c in result.checks if c.axis == "framework"}
    assert names == {
        "framework_available:playwright",
        "framework_available:katalon",
        "framework_available:appium",
    }
    # A mixed suite is only as ready as its least-supported framework.
    assert result.ready is False
    assert result.axis_ready("framework") is False
    assert {c.name for c in result.blockers} == {
        "framework_available:katalon",
        "framework_available:appium",
    }


@pytest.mark.asyncio
async def test_runner_browser_deps_probe_is_not_double_counted():
    """The per-framework checks supersede the runner's single probe."""
    result = await _run(frameworks={"playwright"})
    assert not any(c.name == "browser_deps_installed" for c in result.checks)


@pytest.mark.asyncio
async def test_dead_worker_blocks_the_run(monkeypatch):
    monkeypatch.setattr(
        gate,
        "_worker_check",
        lambda: gate.GateCheck("worker", "worker_available", False, "No Celery worker responded"),
    )
    result = await _run()
    assert result.ready is False
    assert result.axis_ready("worker") is False


@pytest.mark.asyncio
async def test_test_data_axis_is_reported_but_not_blocking():
    """P1-S6 does not exist, so this axis must not gate the demo."""
    result = await _run()
    check = next(c for c in result.checks if c.name == "test_data_present")
    assert check.blocking is False
    assert check.axis == "data"


@pytest.mark.asyncio
async def test_failing_non_blocking_check_does_not_block_the_run(monkeypatch):
    async def _data_missing(_inputs):
        return runner_readiness.ReadinessResult(
            checks=[
                runner_readiness.ReadinessCheck("application_url_reachable", True, "200"),
                runner_readiness.ReadinessCheck("test_data_present", False, "no reservation"),
            ]
        )

    monkeypatch.setattr(gate.runner_readiness, "check_readiness", _data_missing)
    result = await _run()
    assert result.ready is True
    assert result.blockers == []


@pytest.mark.asyncio
async def test_unreachable_application_blocks_on_the_application_axis(monkeypatch):
    async def _unreachable(_inputs):
        return runner_readiness.ReadinessResult(
            checks=[
                runner_readiness.ReadinessCheck(
                    "application_url_reachable", False, "https://sit.example.com unreachable"
                )
            ]
        )

    monkeypatch.setattr(gate.runner_readiness, "check_readiness", _unreachable)
    result = await _run()
    assert result.ready is False
    assert result.axis_ready("application") is False


@pytest.mark.asyncio
async def test_verdict_serializes_by_value_for_persistence():
    """It is stored on the run, so it must survive without a re-probe."""
    payload = (await _run()).as_dict()
    assert payload["ready"] is True
    assert isinstance(payload["checks"], list) and payload["checks"]
    assert all({"axis", "name", "passed", "detail", "blocking"} <= set(c) for c in payload["checks"])


def test_worker_check_reports_a_broker_failure_as_a_blocker(monkeypatch):
    """A dead broker must be a stated blocker, not an exception."""
    import app.worker.celery_app as celery_module

    class _Control:
        def ping(self, timeout=0):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(celery_module.celery_app, "control", _Control())
    check = gate._worker_check()
    assert check.passed is False
    assert "connection refused" in check.detail


def test_worker_check_reports_no_replies_as_a_blocker(monkeypatch):
    import app.worker.celery_app as celery_module

    class _Control:
        def ping(self, timeout=0):
            return []

    monkeypatch.setattr(celery_module.celery_app, "control", _Control())
    check = gate._worker_check()
    assert check.passed is False
    assert "No Celery worker responded" in check.detail


def test_worker_check_passes_when_a_worker_replies(monkeypatch):
    import app.worker.celery_app as celery_module

    class _Control:
        def ping(self, timeout=0):
            return [{"celery@worker1": {"ok": "pong"}}]

    monkeypatch.setattr(celery_module.celery_app, "control", _Control())
    check = gate._worker_check()
    assert check.passed is True
    assert "celery@worker1" in check.detail
