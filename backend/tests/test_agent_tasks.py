import anyio

from app.models.agent import AgentRun
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.models.test_scenario import TestScenario
from app.worker.tasks import agent_tasks


def test_requirement_quality_task_uses_agent_signature(monkeypatch):
    calls = {}

    class FakeQualityAgent:
        async def run(self, requirements):
            calls["requirements"] = requirements
            return {"ok": True}

    monkeypatch.setattr(agent_tasks, "RequirementQualityAgent", lambda: FakeQualityAgent())

    result = anyio.run(
        agent_tasks._requirement_quality,
        {"requirements": [{"id": 1}], "project_id": 123},
    )

    assert result == {"ok": True}
    assert calls["requirements"] == [{"id": 1}]


# ── Phase 1: reviewer chain-input builders ────────────────────────────────────

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


class _FakeQueryDB:
    def __init__(self, values):
        self._values = values

    async def execute(self, _stmt):
        return _ExecuteResult(self._values)


def _run() -> AgentRun:
    return AgentRun(id=1, project_id=1, triggered_by=1, agent_name="test_scenario", status="running")


def test_build_scenario_review_input_fetches_persisted_scenarios():
    scenario = TestScenario(
        id=70, project_id=1, created_by=1, scenario_id="TS-0070", title="Login works",
        requirement_id=7, description="d", scenario_type="positive", priority="High",
    )
    db = _FakeQueryDB([scenario])
    input_data = {"requirements": [{"id": 7, "requirement_id": "REQ-0007"}]}
    output_data = {"scenario_ids": [70], "count": 1}

    async def run_test():
        return await agent_tasks._build_scenario_review_input(db, _run(), input_data, output_data)

    chain_input = anyio.run(run_test)

    assert chain_input["requirements"] == input_data["requirements"]
    assert chain_input["scenarios"][0]["scenario_id"] == "TS-0070"
    assert chain_input["scenarios"][0]["_source_requirement_id"] == 7


def test_build_scenario_review_input_returns_none_without_scenario_ids():
    db = _FakeQueryDB([])
    input_data = {"requirements": [{"id": 7}]}

    async def run_test():
        return await agent_tasks._build_scenario_review_input(db, _run(), input_data, {})

    assert anyio.run(run_test) is None


def test_build_test_case_review_input_fetches_persisted_test_cases():
    test_case = TestCase(
        id=100, project_id=1, created_by=1, test_case_id="TC-0100", title="Login succeeds",
        scenario_id=70, steps=[{"step_number": 1, "action": "a", "expected_result": "b"}],
        expected_result="ok", priority="High", test_type="functional",
    )
    db = _FakeQueryDB([test_case])
    input_data = {"scenarios": [{"id": 70, "scenario_id": "TS-0070"}]}
    output_data = {"test_case_ids": [100], "count": 1}

    async def run_test():
        return await agent_tasks._build_test_case_review_input(db, _run(), input_data, output_data)

    chain_input = anyio.run(run_test)

    assert chain_input["scenarios"] == input_data["scenarios"]
    assert chain_input["test_cases"][0]["test_case_id"] == "TC-0100"
    assert chain_input["test_cases"][0]["_source_scenario_id"] == 70


def test_build_test_case_review_input_returns_none_without_test_case_ids():
    db = _FakeQueryDB([])
    input_data = {"scenarios": [{"id": 70}]}

    async def run_test():
        return await agent_tasks._build_test_case_review_input(db, _run(), input_data, {})

    assert anyio.run(run_test) is None


def test_build_automation_eligibility_input_passes_through_test_cases():
    db = _FakeQueryDB([])  # not queried — test cases come straight from input_data
    input_data = {"test_cases": [{"id": 100, "test_case_id": "TC-0100"}]}

    async def run_test():
        return await agent_tasks._build_automation_eligibility_input(db, _run(), input_data, {})

    chain_input = anyio.run(run_test)
    assert chain_input == {"test_cases": [{"id": 100, "test_case_id": "TC-0100"}]}


def test_build_automation_eligibility_input_returns_none_without_test_cases():
    db = _FakeQueryDB([])

    async def run_test():
        return await agent_tasks._build_automation_eligibility_input(db, _run(), {}, {})

    assert anyio.run(run_test) is None


# ── Phase 5: auto-chained discovery after eligibility ─────────────────────────
# Reverses the earlier deliberate manual-only design — see the AgentSpec
# comment on "playwright_mcp_discovery". Safety net: only chains for test
# cases whose application already resolves a real environment URL.

class _FakeResult:
    def __init__(self, value=None, values=None):
        self._value = value
        self._values = values if values is not None else []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return _ScalarsResult(self._values)


class _FakeDiscoveryDB:
    """Response-queue fake — db.get() is a separate lookup method, but
    resolve_default_application/list_for_application-style queries go
    through db.execute() and need .scalar_one_or_none(), not just
    .scalars().all(), so responses are popped in call order."""

    def __init__(self, *, responses, get_results=None):
        self.responses = list(responses)
        self.get_results = dict(get_results or {})

    async def execute(self, _stmt):
        if not self.responses:
            return _FakeResult()
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _FakeResult(values=value)
        return _FakeResult(value=value)

    async def get(self, model, obj_id):
        return self.get_results.get((model, obj_id))


def test_build_mcp_discovery_input_includes_only_eligible_test_cases_with_a_resolvable_url():
    tc_eligible = TestCase(
        id=100, project_id=1, created_by=1, test_case_id="TC-0100", title="Login succeeds",
        automation_eligible="yes", application_id=7, test_phase="SIT",
    )
    tc_ineligible = TestCase(
        id=101, project_id=1, created_by=1, test_case_id="TC-0101", title="Requires OTP",
        automation_eligible="no", application_id=7, test_phase="SIT",
    )
    application = ProjectApplication(
        id=7, project_id=1, key="web", name="Web App", is_default=True, is_active=True,
        environment_urls={"SIT": "https://app.example.com/"},
    )
    # execute() call order: TestCase select (list). application_id=7 is
    # resolved via db.get(), not execute() — no further execute() calls.
    db = _FakeDiscoveryDB(
        responses=[[tc_eligible, tc_ineligible]],
        get_results={(ProjectApplication, 7): application},
    )
    output_data = {"test_case_ids": [100, 101]}

    async def run_test():
        return await agent_tasks._build_mcp_discovery_input(db, _run(), {}, output_data)

    chain_input = anyio.run(run_test)

    assert len(chain_input["test_cases"]) == 1
    entry = chain_input["test_cases"][0]
    assert entry["test_case_id"] == "TC-0100"
    assert entry["application_id"] == 7
    assert entry["application_url"] == "https://app.example.com/"


def test_build_mcp_discovery_input_skips_test_case_with_no_application_url():
    tc = TestCase(
        id=100, project_id=1, created_by=1, test_case_id="TC-0100", title="Login succeeds",
        automation_eligible="yes", application_id=7, test_phase="SIT",
    )
    application = ProjectApplication(
        id=7, project_id=1, key="web", name="Web App", is_default=True, is_active=True,
        environment_urls={},  # no URL configured for any environment
    )
    db = _FakeDiscoveryDB(responses=[[tc]], get_results={(ProjectApplication, 7): application})
    output_data = {"test_case_ids": [100]}

    async def run_test():
        return await agent_tasks._build_mcp_discovery_input(db, _run(), {}, output_data)

    assert anyio.run(run_test) is None


def test_build_mcp_discovery_input_skips_test_case_with_no_application_at_all():
    tc = TestCase(
        id=100, project_id=1, created_by=1, test_case_id="TC-0100", title="Login succeeds",
        automation_eligible="yes", application_id=None, test_phase="SIT",
    )
    # execute() call order: TestCase select (list), then
    # resolve_default_application's own select (scalar -> None, nothing configured).
    db = _FakeDiscoveryDB(responses=[[tc], None])
    output_data = {"test_case_ids": [100]}

    async def run_test():
        return await agent_tasks._build_mcp_discovery_input(db, _run(), {}, output_data)

    assert anyio.run(run_test) is None


def test_build_mcp_discovery_input_returns_none_without_test_case_ids():
    db = _FakeDiscoveryDB(responses=[])

    async def run_test():
        return await agent_tasks._build_mcp_discovery_input(db, _run(), {}, {})

    assert anyio.run(run_test) is None
