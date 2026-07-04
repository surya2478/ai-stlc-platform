from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.agent import AgentRun
from app.models.test_plan import TestPlan as TestPlanModel
from app.models.user import User
from app.services.agent_dispatch_service import _completed_run_is_reusable
from app.services import test_plan_service


class _ExecuteResult:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.statements = []
        self.deleted = []
        self.flushed = False
        self.committed = False

    async def execute(self, stmt):
        self.statements.append(str(stmt))
        if not self.responses:
            return _ExecuteResult()
        return _ExecuteResult(self.responses.pop(0))

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        self.flushed = True

    async def commit(self):
        self.committed = True


def _plan(**overrides):
    data = {
        "id": 77,
        "project_id": 3,
        "created_by": 5,
        "test_plan_id": "TP-0077",
        "title": "Delete candidate",
        "status": "draft",
    }
    data.update(overrides)
    return TestPlanModel(**data)


async def _user():
    return User(
        id=5,
        email="qa@example.com",
        full_name="QA Lead",
        hashed_password="not-used",
        role="qa_manager",
        is_active=True,
        is_superuser=True,
    )


def test_delete_test_plan_service_clears_links_lineage_and_deletes_plan():
    async def run():
        db = _FakeDB()
        plan = _plan()
        await test_plan_service.delete_test_plan(db, plan)
        return db, plan

    import anyio

    db, plan = anyio.run(run)
    statements = "\n".join(db.statements)

    assert "UPDATE test_cases" in statements
    assert "linked_test_plan_id" in statements
    assert "DELETE FROM artifact_lineage" in statements
    assert "child_type" in statements
    assert "parent_type" in statements
    assert db.deleted == [plan]
    assert db.flushed is True


def test_delete_test_plan_service_invalidates_source_agent_run():
    async def run():
        db = _FakeDB()
        plan = _plan(agent_run_id=88)
        await test_plan_service.delete_test_plan(db, plan)
        return db

    import anyio

    db = anyio.run(run)
    statements = "\n".join(db.statements)

    assert "UPDATE agent_runs" in statements
    assert "output_data" in statements
    assert "error_message" in statements
    assert "progress_message" in statements


def test_completed_test_planning_run_is_not_reusable_when_output_plan_is_missing():
    async def run():
        stale_run = AgentRun(
            id=29,
            project_id=2,
            triggered_by=1,
            agent_name="test_planning",
            status="completed",
            output_data={"plan_id": 999999, "test_plan_id": "TP-999999"},
        )
        return await _completed_run_is_reusable(_FakeDB(None), stale_run, "test_planning")

    import anyio

    assert anyio.run(run) is False


def test_completed_test_planning_run_is_reusable_when_output_plan_exists():
    async def run():
        completed_run = AgentRun(
            id=30,
            project_id=2,
            triggered_by=1,
            agent_name="test_planning",
            status="completed",
            output_data={"plan_id": 2, "test_plan_id": "TP-0002"},
        )
        return await _completed_run_is_reusable(_FakeDB(2), completed_run, "test_planning")

    import anyio

    assert anyio.run(run) is True


def test_delete_test_plan_endpoint_returns_404_for_missing_plan():
    db = _FakeDB(None)

    async def fake_db() -> AsyncIterator[_FakeDB]:
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _user
    try:
        response = TestClient(app).delete("/api/v1/test-plans/999999")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Test plan not found"
    assert db.deleted == []
    assert db.committed is False


def test_delete_test_plan_route_is_registered():
    methods = {
        method
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/test-plans/{plan_id}"
        for method in getattr(route, "methods", set())
    }

    assert "DELETE" in methods
