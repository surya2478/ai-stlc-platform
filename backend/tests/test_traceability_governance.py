import anyio
import pytest

from app.main import app
from app.models.approval import ApprovalAction
from app.models.artifact_lineage import ArtifactLineage
from app.models.defect import DefectDraft
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.user import User
from app.schemas.traceability import ApprovalDecisionRequest
from app.schemas.traceability import TraceabilityChainItem, TraceabilityMatrixOut, TraceabilityMatrixRow
from app.services import traceability_service


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, value=None, values=None):
        self._value = value
        self._values = values or []

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value if self._value is not None else 0

    def scalars(self):
        return _ScalarsResult(self._values)


class _FakeDB:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.added = []
        self.flushed = 0
        self.refreshed = []

    async def execute(self, _stmt):
        if not self.responses:
            return _ExecuteResult(values=[])
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _ExecuteResult(values=value)
        return _ExecuteResult(value=value)

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added)

    async def flush(self):
        self.flushed += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)


class _FailingArtifactDB(_FakeDB):
    def add(self, obj):
        if isinstance(obj, Requirement):
            raise RuntimeError("artifact insert failed")
        super().add(obj)


def _user():
    return User(id=7, email="lead@example.com", full_name="Lead", hashed_password="x", role="QA Manager")


def test_lineage_created_atomically_with_artifact():
    async def run():
        db = _FakeDB()
        req = Requirement(project_id=1, created_by=7, requirement_id="REQ-1", source="manual", title="Req", status="draft")
        db.add(req)
        await db.flush()
        lineage = await traceability_service.create_lineage(
            db,
            project_id=1,
            parent_type="requirement",
            parent_id=req.id,
            child_type="test_case",
            child_id=20,
            agent_run_id=99,
        )
        return db, lineage

    db, lineage = anyio.run(run)

    assert lineage in db.added
    assert db.flushed >= 2
    assert lineage.parent_id == 1
    assert lineage.agent_run_id == 99


def test_lineage_not_created_when_artifact_insert_fails():
    async def run():
        db = _FailingArtifactDB()
        try:
            req = Requirement(project_id=1, created_by=7, requirement_id="REQ-1", source="manual", title="Req", status="draft")
            db.add(req)
            await db.flush()
            await traceability_service.create_lineage(
                db,
                project_id=1,
                parent_type="project",
                parent_id=1,
                child_type="requirement",
                child_id=req.id,
            )
        except RuntimeError:
            return db
        raise AssertionError("Expected artifact insert to fail")

    db = anyio.run(run)

    assert not any(isinstance(obj, ArtifactLineage) for obj in db.added)


def test_artifact_lineage_has_no_update_or_delete_endpoints():
    forbidden = {"PATCH", "PUT", "DELETE"}
    lineage_routes = [
        route for route in app.routes
        if "lineage" in getattr(route, "path", "").lower()
    ]

    assert all(not (set(route.methods or set()) & forbidden) for route in lineage_routes)


def test_traceability_matrix_returns_correct_chain():
    req = Requirement(id=1, project_id=1, created_by=7, requirement_id="REQ-1", source="jira", title="Req", status="approved")
    tc = TestCase(id=2, project_id=1, created_by=7, requirement_id=1, test_case_id="TC-1", title="Case", status="approved")
    run = ExecutionRun(id=3, project_id=1, created_by=7, execution_id="ER-1", status="approved")
    result = ExecutionResult(id=4, project_id=1, execution_run_id=3, test_case_id=2, test_name="Case run", status="passed")
    defect = DefectDraft(id=5, project_id=1, created_by=7, defect_id="DEF-1", summary="Defect", execution_result_id=4, status="approved")
    db = _FakeDB([[req], [tc], [result], [defect]])

    async def run_test():
        return await traceability_service.traceability_matrix(db, project_id=1, page=1, page_size=50)

    matrix = anyio.run(run_test)

    assert matrix.total == 1
    row = matrix.items[0]
    assert row.requirement.ref == "REQ-1"
    assert row.test_cases[0].ref == "TC-1"
    assert row.execution_results[0].title == "Case run"
    assert row.defects[0].ref == "DEF-1"
    assert row.gaps == []


def test_coverage_gaps_detected_for_each_gap_type():
    req_no_tc = Requirement(id=1, project_id=1, created_by=7, requirement_id="REQ-1", source="jira", title="No TC", status="approved")
    req_no_exec = Requirement(id=2, project_id=1, created_by=7, requirement_id="REQ-2", source="jira", title="No Exec", status="approved")
    req_failed = Requirement(id=3, project_id=1, created_by=7, requirement_id="REQ-3", source="jira", title="Failed", status="approved")
    tc_no_exec = TestCase(id=20, project_id=1, created_by=7, requirement_id=2, test_case_id="TC-20", title="No Exec", status="approved")
    tc_failed = TestCase(id=30, project_id=1, created_by=7, requirement_id=3, test_case_id="TC-30", title="Failed", status="approved")
    failed_result = ExecutionResult(id=40, project_id=1, execution_run_id=4, test_case_id=30, test_name="Failed", status="failed")
    db = _FakeDB([[req_no_tc, req_no_exec, req_failed], [], [tc_no_exec], [], [tc_failed], [failed_result], []])

    async def run_test():
        return await traceability_service.coverage_gaps(db, project_id=1)

    gaps = anyio.run(run_test)

    assert gaps.no_test_cases == [1]
    assert gaps.no_execution == [2]
    assert gaps.undecided_failures == [40]


def test_coverage_gaps_scan_all_matrix_pages(monkeypatch):
    async def fake_matrix(_db, *, project_id, page, page_size, include_drafts=False):
        if page == 1:
            return TraceabilityMatrixOut(
                items=[
                    TraceabilityMatrixRow(
                        requirement=TraceabilityChainItem(id=1, ref="REQ-1", title="First"),
                        test_cases=[],
                        execution_results=[],
                        defects=[],
                        gaps=["no_test_cases"],
                    )
                ],
                total=2,
                page=1,
                page_size=1,
                pages=2,
            )
        return TraceabilityMatrixOut(
            items=[
                TraceabilityMatrixRow(
                    requirement=TraceabilityChainItem(id=2, ref="REQ-2", title="Second"),
                    test_cases=[],
                    execution_results=[],
                    defects=[],
                    gaps=["no_test_cases"],
                )
            ],
            total=2,
            page=2,
            page_size=1,
            pages=2,
        )

    monkeypatch.setattr(traceability_service, "traceability_matrix", fake_matrix)

    async def run_test():
        return await traceability_service.coverage_gaps(_FakeDB(), project_id=1)

    gaps = anyio.run(run_test)

    assert gaps.no_test_cases == [1, 2]


def test_approval_action_persisted_correctly_and_updates_artifact_status():
    async def run():
        req = Requirement(id=1, project_id=1, created_by=7, requirement_id="REQ-1", source="manual", title="Req", status="draft")
        db = _FakeDB()
        action = await traceability_service.approve_artifact(
            db,
            entity=req,
            entity_type="requirement",
            user=_user(),
            body=ApprovalDecisionRequest(action="approve", notes="Looks good", correlation_id="corr-1"),
            request_id="req-1",
        )
        return db, req, action

    db, req, action = anyio.run(run)

    assert isinstance(action, ApprovalAction)
    assert action in db.added
    assert req.status == "approved"
    assert action.old_value == {"status": "draft", "approval_status": None}
    assert action.new_value == {"status": "approved", "approval_status": "approved"}
    assert action.correlation_id == "corr-1"
    assert action.request_id == "req-1"


def test_second_approval_creates_new_record_without_modifying_first():
    async def run():
        req = Requirement(id=1, project_id=1, created_by=7, requirement_id="REQ-1", source="manual", title="Req", status="draft")
        db = _FakeDB()
        first = await traceability_service.approve_artifact(
            db,
            entity=req,
            entity_type="requirement",
            user=_user(),
            body=ApprovalDecisionRequest(action="approve", notes="first"),
        )
        first_notes = first.notes
        second = await traceability_service.approve_artifact(
            db,
            entity=req,
            entity_type="requirement",
            user=_user(),
            body=ApprovalDecisionRequest(action="reject", notes="second"),
        )
        return first, first_notes, second

    first, first_notes, second = anyio.run(run)

    assert first is not second
    assert first.notes == first_notes == "first"
    assert second.notes == "second"
    assert second.old_value == {"status": "approved", "approval_status": None}


def test_execution_result_approval_preserves_test_outcome_status():
    async def run():
        result = ExecutionResult(
            id=1,
            project_id=1,
            execution_run_id=10,
            test_case_id=20,
            test_name="Failed test",
            status="failed",
            metadata_=None,
        )
        db = _FakeDB()
        action = await traceability_service.approve_artifact(
            db,
            entity=result,
            entity_type="execution_result",
            user=_user(),
            body=ApprovalDecisionRequest(action="approve", notes="Failure reviewed"),
        )
        return result, action

    result, action = anyio.run(run)

    assert result.status == "failed"
    assert result.metadata_["approval_status"] == "approved"
    assert action.old_value == {"status": "failed", "approval_status": None}
    assert action.new_value == {"status": "failed", "approval_status": "approved"}


def test_unapproved_artifacts_excluded_from_default_metrics():
    async def run():
        db = _FakeDB([1, 1, 1, 1])
        return await traceability_service.reporting_metrics(db, project_id=1)

    metrics = anyio.run(run)

    assert metrics["include_drafts"] is False
    assert metrics["requirements"]["total"] == 1
    assert metrics["test_cases"]["total"] == 1
