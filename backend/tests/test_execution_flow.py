from types import SimpleNamespace

import anyio
from fastapi.testclient import TestClient

from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.agents.execution.execution_agent import TestExecutionAgent
from app.models.agent import AgentRun
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.project import Project
from app.models.test_case import TestCase
from app.models.user import User
from app.worker.tasks.agent_tasks import _persist_agent_artifacts


class _ExecutionDB:
    def __init__(self, test_case: TestCase):
        self.test_case = test_case
        self.added = []
        self.next_id = 1

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self.next_id
            self.next_id += 1
        self.added.append(obj)

    async def flush(self):
        return None

    async def get(self, model, object_id):
        if model is TestCase and object_id == self.test_case.id:
            return self.test_case
        return None


class _ExecuteResult:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _EndpointDB:
    def __init__(self, responses):
        self.responses = list(responses)

    async def execute(self, _stmt):
        if self.responses:
            return _ExecuteResult(self.responses.pop(0))
        return _ExecuteResult()


async def _owner_user():
    return User(
        id=1,
        email="owner@example.com",
        full_name="Owner",
        hashed_password="x",
        role="qa_engineer",
        is_active=True,
        is_superuser=False,
    )


def _override_db(db):
    async def fake_db():
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _owner_user


def test_test_execution_artifacts_update_latest_test_case_status():
    async def run_test():
        test_case = TestCase(
            id=10,
            project_id=1,
            created_by=1,
            test_case_id="TC-0010",
            title="Validate login",
            status="approved",
        )
        db = _ExecutionDB(test_case)
        agent_run = AgentRun(
            id=99,
            project_id=1,
            triggered_by=7,
            agent_name="test_execution",
            status="running",
        )
        agent_result = SimpleNamespace(
            data={
                "summary": {"total": 1, "passed": 0, "failed": 1, "skipped": 0},
                "results": [
                    {
                        "test_case_id": "TC-0010",
                        "test_name": "Validate login",
                        "status": "failed",
                        "duration_ms": 1250,
                        "error_message": "AssertionError: login banner missing",
                        "stack_trace": "at login.spec.ts:12",
                        "logs": ["open login", "submit credentials"],
                    }
                ],
            },
            logs=["Execution complete"],
        )

        output = await _persist_agent_artifacts(
            db,
            agent_run,
            "test_execution",
            {
                "test_cases": [{"id": test_case.id, "test_case_id": test_case.test_case_id}],
                "environment": "staging",
                "suite_name": "AI Execution",
                "source_type": "ai",
            },
            agent_result,
        )

        execution_run = next(obj for obj in db.added if isinstance(obj, ExecutionRun))
        execution_result = next(obj for obj in db.added if isinstance(obj, ExecutionResult))

        assert output["run_id"] == execution_run.id
        assert execution_result.status == "failed"
        assert test_case.last_execution_run_id == execution_run.id
        assert test_case.last_automation_status == "failed"
        assert test_case.latest_evidence_available is True
        assert test_case.last_status_updated_by == agent_run.triggered_by
        assert test_case.last_status_updated_at is not None

    anyio.run(run_test)


def test_ai_execution_does_not_mock_success_without_controlled_gateway():
    async def run_test():
        result = await TestExecutionAgent().run(
            test_cases=[{"id": 10, "test_case_id": "TC-0010", "title": "Validate login"}],
            environment="staging",
            suite_name="AI Execution",
            source_type="ai",
        )

        execution_result = result.data["results"][0]
        assert result.success is True
        assert result.data["summary"]["failed"] == 1
        assert execution_result["status"] == "failed"
        assert execution_result["metadata"]["actual_tool_run"] is False
        assert "no mock pass/fail decision" in " ".join(execution_result["logs"]).lower()

    anyio.run(run_test)


def test_execution_trigger_rejects_missing_test_cases():
    db = _EndpointDB([Project(id=1, owner_id=1, name="Project"), None])
    _override_db(db)
    try:
        response = TestClient(app).post(
            "/api/v1/execution/agent/run-tests",
            json={"project_id": 1, "test_case_ids": [999], "environment": "staging", "source_type": "ai"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "No valid test cases found for execution"


def test_execution_trigger_rejects_cross_project_test_cases():
    db = _EndpointDB([
        Project(id=1, owner_id=1, name="Project"),
        TestCase(id=20, project_id=2, created_by=1, test_case_id="TC-0020", title="Other project"),
    ])
    _override_db(db)
    try:
        response = TestClient(app).post(
            "/api/v1/execution/agent/run-tests",
            json={"project_id": 1, "test_case_ids": [20], "environment": "staging", "source_type": "ai"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert "do not belong to project 1" in response.json()["detail"]
