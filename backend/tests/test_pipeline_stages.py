"""automation_service.build_pipeline_stages: the real timeline behind a
script's status — Discover -> Generate -> Static gate -> Dry-run -> Review
-> CI-ready, each with its actual state and timestamp instead of the
abstract, status-only lifecycle stepper that only ever showed "Approved" or
"Draft", never *when* or *why*."""
from datetime import datetime, timezone

import anyio

from app.models.agent import AgentRun
from app.models.approval import ApprovalAction
from app.models.artifact_lineage import ArtifactLineage
from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionRun
from app.services.automation_service import build_pipeline_stages

T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)
T1 = datetime(2026, 7, 2, tzinfo=timezone.utc)
T2 = datetime(2026, 7, 3, tzinfo=timezone.utc)


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, *, single=None, many=None):
        self._single = single
        self._many = many if many is not None else []

    def scalar_one_or_none(self):
        return self._single

    def scalar_one(self):
        return self._single

    def scalars(self):
        return _ScalarsResult(self._many)


class _FakeDB:
    def __init__(self, *, responses=None, get_results=None):
        self.responses = list(responses or [])
        self.get_results = dict(get_results or {})

    async def execute(self, _stmt):
        if not self.responses:
            return _ExecuteResult()
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _ExecuteResult(many=value)
        return _ExecuteResult(single=value)

    async def get(self, model, obj_id):
        return self.get_results.get((model, obj_id))


def _script(**overrides) -> AutomationScript:
    data = {
        "id": 1, "project_id": 8, "test_case_id": 10, "created_by": 1, "script_id": "AS-0001",
        "framework": "playwright", "code": "code", "status": "draft",
        "created_at": T0, "updated_at": T0,
    }
    data.update(overrides)
    return AutomationScript(**data)


def _stage(stages, name):
    return next(s for s in stages if s["stage"] == name)


def test_fresh_script_has_only_generate_and_static_resolved():
    script = _script()
    db = _FakeDB(responses=[[], 0, []])  # lineage: none, approval count: 0, approval rows: none

    async def run():
        return await build_pipeline_stages(db, script)

    stages = anyio.run(run)

    assert _stage(stages, "discover")["state"] == "pending"
    assert _stage(stages, "generate")["state"] == "done"
    assert _stage(stages, "generate")["at"] == T0
    assert _stage(stages, "static")["state"] == "pending"  # no static_gate_result yet
    assert _stage(stages, "dry_run")["state"] == "pending"
    assert _stage(stages, "review")["state"] == "pending"
    assert _stage(stages, "ci_ready")["state"] == "pending"


def test_discover_resolves_via_lineage_and_agent_run_timestamp():
    lineage = ArtifactLineage(
        id=1, project_id=8, agent_run_id=50, parent_type="test_case", parent_id=10,
        child_type="locator_map", child_id=5, created_at=T0,
    )
    discovery_run = AgentRun(
        id=50, project_id=8, triggered_by=1, agent_name="playwright_mcp_discovery",
        status="completed", updated_at=T1,
    )
    script = _script()
    db = _FakeDB(
        responses=[lineage, 0, []],
        get_results={(AgentRun, 50): discovery_run},
    )

    async def run():
        return await build_pipeline_stages(db, script)

    stages = anyio.run(run)

    discover = _stage(stages, "discover")
    assert discover["state"] == "done"
    assert discover["at"] == T1  # AgentRun timestamp preferred over lineage created_at
    assert discover["detail"] == "completed"


def test_generate_reports_attempt_count_when_more_than_one():
    script = _script(metadata_={"generation_attempts": [
        {"attempt": 1, "outcome": "validation_failed"},
        {"attempt": 2, "outcome": "compiled"},
    ]})
    db = _FakeDB(responses=[[], 0, []])

    async def run():
        return await build_pipeline_stages(db, script)

    stages = anyio.run(run)
    assert _stage(stages, "generate")["detail"] == "2 attempt(s)"


def test_static_gate_failed_reports_violation_count():
    script = _script(static_gate_result={
        "passed": False,
        "violations": [{"code": "x"}, {"code": "y"}],
        "warnings": [],
    })
    db = _FakeDB(responses=[[], 0, []])

    async def run():
        return await build_pipeline_stages(db, script)

    stages = anyio.run(run)
    static = _stage(stages, "static")
    assert static["state"] == "failed"
    assert static["detail"] == "2 violation(s)"


def test_dry_run_passed_uses_execution_run_timestamp():
    exec_run = ExecutionRun(
        id=77, project_id=8, execution_id="ER-0077", status="completed",
        execution_type="automation", total_tests=1, passed=1, failed=0, skipped=0,
        updated_at=T2,
    )
    script = _script(metadata_={"last_dry_run": {"passed": True, "execution_run_id": 77, "agent_run_id": 50}})
    db = _FakeDB(responses=[[], 0, []], get_results={(ExecutionRun, 77): exec_run})

    async def run():
        return await build_pipeline_stages(db, script)

    stages = anyio.run(run)
    dry_run = _stage(stages, "dry_run")
    assert dry_run["state"] == "done"
    assert dry_run["at"] == T2


def test_dry_run_failed_is_flagged():
    script = _script(metadata_={"last_dry_run": {"passed": False, "execution_run_id": None}})
    db = _FakeDB(responses=[[], 0, []])

    async def run():
        return await build_pipeline_stages(db, script)

    stages = anyio.run(run)
    dry_run = _stage(stages, "dry_run")
    assert dry_run["state"] == "failed"
    assert dry_run["detail"] == "Last dry run failed."


def test_review_done_from_reviewer_approve_action():
    action = ApprovalAction(
        id=1, project_id=8, user_id=2, action_type="reviewer_approve_automation_script",
        entity_type="automation_script", entity_id=1, decision="approved", created_at=T1,
    )
    script = _script(status="reviewer_approved")
    db = _FakeDB(responses=[[], 0, [action]])

    async def run():
        return await build_pipeline_stages(db, script)

    stages = anyio.run(run)
    review = _stage(stages, "review")
    assert review["state"] == "done"
    assert review["at"] == T1


def test_review_failed_from_rejection_with_notes():
    action = ApprovalAction(
        id=1, project_id=8, user_id=2, action_type="reviewer_reject_automation_script",
        entity_type="automation_script", entity_id=1, decision="rejected",
        notes="Coverage gap", created_at=T1,
    )
    script = _script(status="rejected")
    db = _FakeDB(responses=[[], 0, [action]])

    async def run():
        return await build_pipeline_stages(db, script)

    stages = anyio.run(run)
    review = _stage(stages, "review")
    assert review["state"] == "failed"
    assert review["detail"] == "Coverage gap"


def test_ci_ready_done_with_mark_ci_ready_timestamp():
    approve = ApprovalAction(
        id=1, project_id=8, user_id=2, action_type="lead_approve_automation_script",
        entity_type="automation_script", entity_id=1, decision="approved", created_at=T1,
    )
    ci_ready = ApprovalAction(
        id=2, project_id=8, user_id=2, action_type="mark_ci_ready_automation_script",
        entity_type="automation_script", entity_id=1, decision="approved", created_at=T2,
    )
    script = _script(status="ci_ready")
    db = _FakeDB(responses=[[], 0, [ci_ready, approve]])  # desc order: most recent first

    async def run():
        return await build_pipeline_stages(db, script)

    stages = anyio.run(run)
    assert _stage(stages, "ci_ready")["state"] == "done"
    assert _stage(stages, "ci_ready")["at"] == T2
    # review picks the most recent approve/reject action, not mark_ci_ready
    assert _stage(stages, "review")["at"] == T1


def test_ci_ready_pending_when_status_not_yet_there():
    script = _script(status="dry_run_passed")
    db = _FakeDB(responses=[[], 0, []])

    async def run():
        return await build_pipeline_stages(db, script)

    stages = anyio.run(run)
    assert _stage(stages, "ci_ready")["state"] == "pending"


def test_all_six_stages_always_present_in_order():
    script = _script()
    db = _FakeDB(responses=[[], 0, []])

    async def run():
        return await build_pipeline_stages(db, script)

    stages = anyio.run(run)
    assert [s["stage"] for s in stages] == ["discover", "generate", "static", "dry_run", "review", "ci_ready"]
