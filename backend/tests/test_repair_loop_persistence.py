"""Phase 4.4: persistence of the repair loop's output — one new
AutomationScript version per attempt (parent never mutated), tagged
dry-run evidence, and the chain builder that only surfaces repairable
failures with their contract + fresh locator catalog."""
from types import SimpleNamespace

import anyio

from app.models.agent import AgentRun
from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.worker.tasks.agent_tasks import _build_repair_loop_input, _persist_agent_artifacts


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

    def scalar_one_or_none(self):
        # Grounding consults the published Application Model before falling
        # back to locator_map (locator_catalog.get_published_model), and that
        # lookup reads a single row rather than a scalars() list.
        return self._values[0] if self._values else None


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


def _agent_run(agent_name="automation_repair_loop") -> AgentRun:
    return AgentRun(id=90, project_id=1, triggered_by=1, agent_name=agent_name, status="running")


def test_persistence_creates_one_version_per_attempt_and_promotes_on_resolve():
    parent = AutomationScript(
        id=1, project_id=1, test_case_id=10, created_by=1, script_id="AS-0001",
        framework="playwright", code="old", version=1, status="static_passed",
    )
    db = _FakeDB(get_results={(AutomationScript, 1): parent})
    run = _agent_run()
    agent_result = SimpleNamespace(data={"repairs": [{
        "script_id": 1,
        "resolved": True,
        "attempts": [{
            "attempt": 1,
            "contract": {"testCaseId": "TC-1"},
            "compiled_files": {"specs/x.spec.ts": "new code"},
            "file_path": "specs/x.spec.ts",
            "static_gate_passed": True,
            "static_gate_result": {"passed": True},
            "dry_run_passed": True,
            "dry_run_result": {
                "run_status": "completed",
                "results": [{"name": "t1", "status": "pass", "duration_ms": 10}],
            },
            "outcome": "passed",
        }],
    }]})

    async def run_test():
        return await _persist_agent_artifacts(db, run, "automation_repair_loop", {}, agent_result)

    output = anyio.run(run_test)

    new_version = next(obj for obj in db.added if isinstance(obj, AutomationScript))
    assert new_version.version == 2
    assert new_version.parent_script_id == 1
    assert new_version.status == "dry_run_passed"
    assert new_version.code == "new code"
    assert new_version.metadata_["source"] == "repair_loop"
    assert parent.code == "old"  # parent never mutated
    assert output["resolved_script_ids"] == [new_version.id]


def test_persistence_marks_exhausted_when_never_resolved():
    parent = AutomationScript(
        id=2, project_id=1, created_by=1, script_id="AS-0002",
        framework="playwright", code="old", version=1, status="static_passed",
    )
    db = _FakeDB(get_results={(AutomationScript, 2): parent})
    run = _agent_run()
    agent_result = SimpleNamespace(data={"repairs": [{
        "script_id": 2,
        "resolved": False,
        "attempts": [{
            "attempt": 1,
            "contract": {"testCaseId": "TC-2"},
            "compiled_files": {"specs/x.spec.ts": "attempt code"},
            "file_path": "specs/x.spec.ts",
            "static_gate_passed": True,
            "static_gate_result": {"passed": True},
            "dry_run_passed": False,
            "dry_run_result": {"run_status": "completed", "results": [{"name": "t1", "status": "fail"}]},
            "outcome": "failed",
        }],
    }]})

    async def run_test():
        return await _persist_agent_artifacts(db, run, "automation_repair_loop", {}, agent_result)

    output = anyio.run(run_test)

    new_version = next(obj for obj in db.added if isinstance(obj, AutomationScript))
    assert new_version.status == "static_passed"  # dry run failed -> not promoted
    assert new_version.metadata_["repair_loop_exhausted"] is True
    assert output["resolved_script_ids"] == []


def test_persistence_skips_attempts_with_no_compiled_files():
    parent = AutomationScript(
        id=3, project_id=1, created_by=1, script_id="AS-0003",
        framework="playwright", code="old", version=1, status="static_passed",
    )
    db = _FakeDB(get_results={(AutomationScript, 3): parent})
    run = _agent_run()
    agent_result = SimpleNamespace(data={"repairs": [{
        "script_id": 3,
        "resolved": False,
        "attempts": [{"attempt": 1, "outcome": "llm_patch_failed"}],
    }]})

    async def run_test():
        return await _persist_agent_artifacts(db, run, "automation_repair_loop", {}, agent_result)

    output = anyio.run(run_test)

    assert not any(isinstance(obj, AutomationScript) and obj is not parent for obj in db.added)
    assert output["resolved_script_ids"] == []


def test_build_repair_loop_input_only_includes_repairable_failures_with_context():
    exec_result = ExecutionResult(
        id=1, execution_run_id=1, project_id=1, test_name="t1", status="fail",
        error_message="waiting for locator", stack_trace="",
        metadata_={
            "automation_script_id": 5,
            "failure_classification": {"classification": "locator_issue", "repairable": True},
        },
    )
    script = AutomationScript(
        id=5, project_id=1, test_case_id=20, created_by=1, script_id="AS-0005",
        framework="playwright", code="x", contract={"testCaseId": "TC-1"}, status="static_passed",
    )
    tc = TestCase(id=20, project_id=1, created_by=1, test_case_id="TC-1", title="x", application_id=7, test_phase="SIT")
    application = ProjectApplication(
        id=7, project_id=1, key="web", name="Web", is_default=True, is_active=True,
        environment_urls={"SIT": "http://sit.app.example.com"},
    )

    db = _FakeDB(
        # execute() calls: main select, then the published-model lookup
        # (none), then the locator_map fallback
        responses=[[exec_result], [], []],
        get_results={
            (AutomationScript, 5): script,
            (TestCase, 20): tc,
            (ProjectApplication, 7): application,
        },
    )
    run = _agent_run()

    async def run_test():
        return await _build_repair_loop_input(db, run, {}, {"classified_result_ids": [1]})

    chain_input = anyio.run(run_test)

    assert len(chain_input["scripts"]) == 1
    entry = chain_input["scripts"][0]
    assert entry["script_id"] == 5
    assert entry["contract"] == {"testCaseId": "TC-1"}
    assert entry["application_url"] == "http://sit.app.example.com"
    assert entry["environment"] == "SIT"
    assert entry["failure"]["classification"] == "locator_issue"


def test_build_repair_loop_input_excludes_non_repairable_failures():
    exec_result = ExecutionResult(
        id=2, execution_run_id=1, project_id=1, test_name="t1", status="fail",
        metadata_={
            "automation_script_id": 6,
            "failure_classification": {"classification": "data_issue", "repairable": False},
        },
    )
    db = _FakeDB(responses=[[exec_result]])
    run = _agent_run()

    async def run_test():
        return await _build_repair_loop_input(db, run, {}, {"classified_result_ids": [2]})

    assert anyio.run(run_test) is None


def test_build_repair_loop_input_returns_none_without_classified_ids():
    db = _FakeDB()
    run = _agent_run()

    async def run_test():
        return await _build_repair_loop_input(db, run, {}, {})

    assert anyio.run(run_test) is None
