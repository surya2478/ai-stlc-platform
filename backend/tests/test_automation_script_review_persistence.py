"""Phase 4.5: persistence of automation_script_review verdicts as
ArtifactReview rows (never mutates script.status — reviewer_approved /
lead_approved are human role-gated, see Task 42), and the chain builder that
surfaces only dry_run_passed scripts reachable from either automation_dry_run
or automation_repair_loop."""
from types import SimpleNamespace

import anyio

from app.models.agent import AgentRun
from app.models.automation_script import AutomationScript
from app.models.test_case import TestCase
from app.worker.tasks.agent_tasks import _build_script_review_input, _persist_agent_artifacts


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


def _agent_run() -> AgentRun:
    return AgentRun(id=91, project_id=1, triggered_by=1, agent_name="automation_script_review", status="running")


class _FakeProject:
    review_mode = "advisory"


async def _fake_get_review_mode(db, project_id):
    return "advisory"


def test_persistence_creates_artifact_review_matched_by_test_case_id(monkeypatch):
    from app.services import artifact_review_service
    monkeypatch.setattr(artifact_review_service, "get_review_mode", _fake_get_review_mode)

    db = _FakeDB()
    run = _agent_run()
    input_data = {"scripts": [{
        "script_id": 5,
        "test_case": {"test_case_id": "TC-0001", "title": "Login"},
    }]}
    agent_result = SimpleNamespace(data={"reviews": [{
        "target_ref": "TC-0001",
        "scores": {"business_step_coverage": 4.0},
        "overall_score": 4.0,
        "verdict": "pass",
        "findings": [],
        "coverage_gaps": [],
    }], "summary": {"pass": 1, "needs_revision": 0, "fail": 0}})

    async def run_test():
        return await _persist_agent_artifacts(db, run, "automation_script_review", input_data, agent_result)

    output = anyio.run(run_test)

    assert len(db.added) == 1
    review = db.added[0]
    assert review.artifact_type == "automation_script"
    assert review.artifact_id == 5
    assert review.reviewer_agent == "automation_script_review"
    assert review.verdict == "pass"
    assert output["review_ids"] == [review.id]
    assert output["summary"] == {"pass": 1, "needs_revision": 0, "fail": 0}


def test_persistence_matches_by_script_id_when_no_test_case(monkeypatch):
    from app.services import artifact_review_service
    monkeypatch.setattr(artifact_review_service, "get_review_mode", _fake_get_review_mode)

    db = _FakeDB()
    run = _agent_run()
    input_data = {"scripts": [{"script_id": 7, "test_case": {}}]}
    agent_result = SimpleNamespace(data={"reviews": [{
        "target_ref": "7",
        "verdict": "needs_revision",
        "scores": {},
        "overall_score": 3.0,
        "findings": [],
        "coverage_gaps": [],
    }], "summary": {"pass": 0, "needs_revision": 1, "fail": 0}})

    async def run_test():
        return await _persist_agent_artifacts(db, run, "automation_script_review", input_data, agent_result)

    output = anyio.run(run_test)

    assert db.added[0].artifact_id == 7
    assert output["review_ids"] == [db.added[0].id]


def test_persistence_skips_review_with_no_matching_script(monkeypatch):
    from app.services import artifact_review_service
    monkeypatch.setattr(artifact_review_service, "get_review_mode", _fake_get_review_mode)

    db = _FakeDB()
    run = _agent_run()
    input_data = {"scripts": [{"script_id": 1, "test_case": {"test_case_id": "TC-0001"}}]}
    agent_result = SimpleNamespace(data={"reviews": [{
        "target_ref": "TC-9999", "verdict": "pass", "scores": {}, "overall_score": 4.0,
        "findings": [], "coverage_gaps": [],
    }], "summary": {}})

    async def run_test():
        return await _persist_agent_artifacts(db, run, "automation_script_review", input_data, agent_result)

    output = anyio.run(run_test)

    assert db.added == []
    assert output["review_ids"] == []


def test_build_script_review_input_from_dry_run_promoted_ids():
    script = AutomationScript(
        id=5, project_id=1, test_case_id=20, created_by=1, script_id="AS-0005",
        framework="playwright", code="const x = 1;", status="dry_run_passed",
        static_gate_result={"passed": True},
        metadata_={"last_dry_run": {"passed": True, "execution_run_id": 12}},
    )
    tc = TestCase(
        id=20, project_id=1, created_by=1, test_case_id="TC-0001", title="Login",
        preconditions=["has account"], steps=[{"step_number": 1, "action": "log in"}],
        expected_result="dashboard shown",
    )
    db = _FakeDB(get_results={(AutomationScript, 5): script, (TestCase, 20): tc})
    db.responses = [[script]]
    run = _agent_run()

    async def run_test():
        return await _build_script_review_input(db, run, {}, {"promoted_script_ids": [5]})

    chain_input = anyio.run(run_test)

    assert len(chain_input["scripts"]) == 1
    entry = chain_input["scripts"][0]
    assert entry["script_id"] == 5
    assert entry["test_case"]["test_case_id"] == "TC-0001"
    assert entry["code"] == "const x = 1;"
    assert entry["static_gate_result"] == {"passed": True}
    assert entry["dry_run_evidence"] == {"passed": True, "execution_run_id": 12}


def test_build_script_review_input_from_repair_loop_resolved_ids():
    script = AutomationScript(
        id=9, project_id=1, test_case_id=None, created_by=1, script_id="AS-0009",
        framework="playwright", code="const y = 2;", status="dry_run_passed",
        static_gate_result={"passed": True}, metadata_=None,
    )
    db = _FakeDB(get_results={(AutomationScript, 9): script})
    db.responses = [[script]]
    run = _agent_run()

    async def run_test():
        return await _build_script_review_input(db, run, {}, {"resolved_script_ids": [9]})

    chain_input = anyio.run(run_test)

    assert len(chain_input["scripts"]) == 1
    entry = chain_input["scripts"][0]
    assert entry["test_case"] == {}
    assert entry["dry_run_evidence"] == {"passed": True}  # default when no last_dry_run metadata


def test_build_script_review_input_returns_none_without_script_ids():
    db = _FakeDB()
    run = _agent_run()

    async def run_test():
        return await _build_script_review_input(db, run, {}, {})

    assert anyio.run(run_test) is None
