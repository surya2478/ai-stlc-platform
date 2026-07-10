"""Real bug found via a live run: a completed automation_script run that hit
an LLM rate limit persists zero scripts (output_data={"script_ids": [],
"count": 0}) but is still marked "completed", not "failed". Before this fix,
_completed_run_is_reusable's default `return True` treated it as
permanently reusable — every retry with the same test case silently
short-circuited to the same empty result forever, with no way to actually
regenerate."""
import anyio

from app.models.agent import AgentRun
from app.services.agent_dispatch_service import _completed_run_is_reusable


class _ScalarsResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, value):
        self._value = value

    async def execute(self, _stmt):
        return _ScalarsResult(self._value)


def _run(**overrides) -> AgentRun:
    data = {"id": 42, "project_id": 1, "triggered_by": 1, "agent_name": "automation_script", "status": "completed"}
    data.update(overrides)
    return AgentRun(**data)


def test_automation_script_run_with_no_persisted_scripts_is_not_reusable():
    db = _FakeDB(None)  # no AutomationScript row references this run
    run = _run()

    async def check():
        return await _completed_run_is_reusable(db, run, "automation_script")

    assert anyio.run(check) is False


def test_automation_script_run_with_a_persisted_script_is_reusable():
    db = _FakeDB(7)  # an AutomationScript.id was found
    run = _run()

    async def check():
        return await _completed_run_is_reusable(db, run, "automation_script")

    assert anyio.run(check) is True


def test_unrecognized_agent_name_defaults_to_reusable():
    db = _FakeDB(None)
    run = _run(agent_name="automation_dry_run")

    async def check():
        return await _completed_run_is_reusable(db, run, "automation_dry_run")

    assert anyio.run(check) is True
