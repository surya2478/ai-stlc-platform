"""automation_service.classify_and_repair: the on-demand counterpart to the
automatic dry-run chain (automation_dry_run -> failure_classification ->
automation_repair_loop), which never runs for real Command Center
executions — automation_tasks.run_automation_script has no chain wiring at
all, so a real "Retry" failure was never classified or repaired. This
covers the four paths: already-classified reuse, fresh rule-based
classification, non-repairable classifications (no repair attempted), and
a repairable classification that runs RepairLoopAgent and persists the
outcome."""
from types import SimpleNamespace

import anyio

from app.agents.base.base_agent import AgentRunResult
from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.services import automation_service


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
        self.added = []

    async def execute(self, _stmt):
        if not self.responses:
            return _ExecuteResult()
        return _ExecuteResult(values=self.responses.pop(0))

    async def get(self, model, obj_id):
        return self.get_results.get((model, obj_id))

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 100
        self.added.append(obj)

    async def flush(self):
        return None


def _result(**overrides) -> ExecutionResult:
    data = {
        "id": 1, "execution_run_id": 1, "project_id": 8, "test_case_id": 10,
        "test_name": "t1", "status": "fail",
    }
    data.update(overrides)
    return ExecutionResult(**data)


def test_reuses_existing_classification_without_reclassifying():
    result = _result(metadata_={"failure_classification": {
        "classification": "data_issue", "reason": "no rows found", "source": "rules", "repairable": False,
    }})
    db = _FakeDB()

    async def run():
        return await automation_service.classify_and_repair(db, execution_result=result, triggered_by=1)

    outcome = anyio.run(run)

    assert outcome["classification"] == "data_issue"
    assert outcome["repairable"] is False
    assert outcome["repaired"] is False
    assert outcome["attempts"] == []


def test_classifies_fresh_via_rules_and_persists_onto_the_result():
    # "waiting for locator" matches _LOCATOR_PATTERNS deterministically —
    # no LLM call needed.
    result = _result(error_message="Error: waiting for locator('button') to be visible")
    db = _FakeDB()

    async def run():
        return await automation_service.classify_and_repair(db, execution_result=result, triggered_by=1)

    outcome = anyio.run(run)

    assert outcome["classification"] == "locator_issue"
    assert outcome["repairable"] is True
    assert result.metadata_["failure_classification"]["classification"] == "locator_issue"
    assert result.metadata_["failure_classification"]["source"] == "rules"


def test_non_repairable_classification_returns_without_attempting_repair():
    # net::ERR_ pattern -> environment_issue, not in REPAIRABLE_CLASSIFICATIONS.
    result = _result(error_message="net::ERR_CONNECTION_REFUSED at https://app.example.com/")
    db = _FakeDB()

    async def run():
        return await automation_service.classify_and_repair(db, execution_result=result, triggered_by=1)

    outcome = anyio.run(run)

    assert outcome["classification"] == "environment_issue"
    assert outcome["repairable"] is False
    assert outcome["repaired"] is False
    assert outcome["error"] is None


def test_repairable_with_no_linked_script_returns_an_error_not_a_crash():
    result = _result(
        error_message="waiting for locator('button')",
        metadata_={},  # no automation_script_id
    )
    db = _FakeDB()

    async def run():
        return await automation_service.classify_and_repair(db, execution_result=result, triggered_by=1)

    outcome = anyio.run(run)

    assert outcome["repairable"] is True
    assert outcome["repaired"] is False
    assert "No linked automation script" in outcome["error"]


def test_repairable_runs_repair_loop_and_persists_a_resolved_version(monkeypatch):
    script = AutomationScript(
        id=5, project_id=8, test_case_id=20, created_by=1, script_id="AS-0005",
        framework="playwright", code="old", version=1, status="dry_run_passed",
        contract={"testCaseId": "TC-1"},
    )
    tc = TestCase(
        id=20, project_id=8, created_by=1, test_case_id="TC-1", title="x",
        application_id=7, test_phase="SIT",
    )
    application = ProjectApplication(
        id=7, project_id=8, key="web", name="Web", is_default=True, is_active=True,
        environment_urls={"SIT": "https://sit.app.example.com"},
    )
    result = _result(
        error_message="waiting for locator('button')",
        metadata_={"automation_script_id": 5},
    )
    db = _FakeDB(
        responses=[[]],  # locator_map_service.list_for_application
        get_results={
            (AutomationScript, 5): script,
            (TestCase, 20): tc,
            (ProjectApplication, 7): application,
        },
    )

    captured = {}

    class _FakeRepairAgent:
        async def run(self, *, scripts):
            captured["scripts"] = scripts
            return AgentRunResult(success=True, data={"repairs": [{
                "script_id": 5,
                "resolved": True,
                "attempts": [{
                    "attempt": 1,
                    "contract": {"testCaseId": "TC-1"},
                    "compiled_files": {"specs/x.spec.ts": "patched code"},
                    "file_path": "specs/x.spec.ts",
                    "static_gate_passed": True,
                    "dry_run_passed": True,
                    "dry_run_result": {"run_status": "completed", "results": [{"name": "t1", "status": "pass"}]},
                    "outcome": "passed",
                }],
            }]}, logs=[])

    import app.agents.automation.repair_agent as repair_agent_module
    monkeypatch.setattr(repair_agent_module, "RepairLoopAgent", _FakeRepairAgent)

    async def run():
        return await automation_service.classify_and_repair(db, execution_result=result, triggered_by=3)

    outcome = anyio.run(run)

    assert outcome["classification"] == "locator_issue"
    assert outcome["repaired"] is True
    assert outcome["new_script_id"] is not None
    assert outcome["attempts"] == [{
        "attempt": 1, "outcome": "passed", "detail": None,
        "static_gate_passed": True, "dry_run_passed": True,
    }]
    # RepairLoopAgent received a fresh catalog lookup (empty here) and the
    # script's real application_url, not generation-time data.
    assert captured["scripts"][0]["application_url"] == "https://sit.app.example.com"
    assert captured["scripts"][0]["failure"]["classification"] == "locator_issue"

    new_version = next(o for o in db.added if isinstance(o, AutomationScript))
    assert new_version.parent_script_id == 5
    assert new_version.status == "dry_run_passed"


def test_repairable_threads_studio_explored_page_paths_to_repair_loop(monkeypatch):
    """A Studio-planned test case's explored_page_paths must reach the
    repair loop — without this the repair loop can never correct a guessed
    navigation target, exactly the live bug where 4/4 Studio failures went
    through repair and 0 were fixed."""
    script = AutomationScript(
        id=5, project_id=8, test_case_id=20, created_by=1, script_id="AS-0005",
        framework="playwright", code="old", version=1, status="dry_run_passed",
        contract={"testCaseId": "TC-1"},
    )
    tc = TestCase(
        id=20, project_id=8, created_by=1, test_case_id="TC-1", title="x",
        application_id=7, test_phase="SIT",
        metadata_={
            "origin": "playwright_studio",
            "explored_page_paths": ["https://sit.app.example.com/sign-up?role=candidate"],
        },
    )
    application = ProjectApplication(
        id=7, project_id=8, key="web", name="Web", is_default=True, is_active=True,
        environment_urls={"SIT": "https://sit.app.example.com"},
    )
    result = _result(
        error_message="TimeoutError: page.waitForURL: Timeout 30000ms exceeded.",
        metadata_={"automation_script_id": 5},
    )
    db = _FakeDB(
        responses=[[]],
        get_results={
            (AutomationScript, 5): script,
            (TestCase, 20): tc,
            (ProjectApplication, 7): application,
        },
    )

    captured = {}

    class _FakeRepairAgent:
        async def run(self, *, scripts):
            captured["scripts"] = scripts
            return AgentRunResult(success=True, data={"repairs": [{
                "script_id": 5, "resolved": False, "attempts": [],
            }]}, logs=[])

    import app.agents.automation.repair_agent as repair_agent_module
    monkeypatch.setattr(repair_agent_module, "RepairLoopAgent", _FakeRepairAgent)

    async def run():
        return await automation_service.classify_and_repair(db, execution_result=result, triggered_by=3)

    anyio.run(run)

    assert captured["scripts"][0]["explored_page_paths"] == [
        "https://sit.app.example.com/sign-up?role=candidate"
    ]


def test_repair_loop_failure_surfaces_as_error_not_a_crash(monkeypatch):
    script = AutomationScript(
        id=6, project_id=8, test_case_id=None, created_by=1, script_id="AS-0006",
        framework="playwright", code="old", version=1, status="dry_run_passed",
        contract={"testCaseId": "TC-1"},
    )
    result = _result(
        error_message="Test timeout of 30000ms exceeded.",
        metadata_={"automation_script_id": 6},
    )
    db = _FakeDB(get_results={(AutomationScript, 6): script})

    class _FailingRepairAgent:
        async def run(self, *, scripts):
            return AgentRunResult(success=False, error="LLM unavailable", data={}, logs=[])

    import app.agents.automation.repair_agent as repair_agent_module
    monkeypatch.setattr(repair_agent_module, "RepairLoopAgent", _FailingRepairAgent)

    async def run():
        return await automation_service.classify_and_repair(db, execution_result=result, triggered_by=1)

    outcome = anyio.run(run)

    assert outcome["classification"] == "timeout"
    assert outcome["repairable"] is True
    assert outcome["repaired"] is False
    assert outcome["error"] == "LLM unavailable"
