"""Phase 1: persistence of scenario_review / test_case_review agent output,
and the upgraded requirement_quality branch writing a generic ArtifactReview
alongside the existing RequirementQualityReview row."""
from types import SimpleNamespace

import anyio

from app.models.agent import AgentRun
from app.models.artifact_review import ArtifactReview
from app.models.coverage_matrix import CoverageMatrixEntry
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.requirement_review import RequirementQualityReview
from app.models.test_case import TestCase
from app.worker.tasks.agent_tasks import _persist_agent_artifacts


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, value=None, values=None):
        self._value = value
        self._values = values if values is not None else []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return _ScalarsResult(self._values)


class _FakeDB:
    def __init__(self, *, project=None, responses=None):
        self._project = project
        self.responses = list(responses or [])
        self.added = []

    async def get(self, _model, _id):
        return self._project

    async def execute(self, _stmt):
        if not self.responses:
            return _ExecuteResult()
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _ExecuteResult(values=value)
        return _ExecuteResult(value=value)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 1
        self.added.append(obj)

    async def flush(self):
        return None


def _agent_run(agent_name: str, project_id: int = 1) -> AgentRun:
    return AgentRun(id=50, project_id=project_id, triggered_by=1, agent_name=agent_name, status="running")


def test_scenario_review_persistence_writes_artifact_review():
    db = _FakeDB(project=Project(id=1, owner_id=1, name="P", review_mode="advisory"))
    run = _agent_run("scenario_review")
    input_data = {
        "requirements": [{"id": 7, "requirement_id": "REQ-0007", "title": "Login"}],
        "scenarios": [{"id": 70, "scenario_id": "TS-0070"}],
    }
    agent_result = SimpleNamespace(data={
        "target_kind": "test_scenario_set",
        "reviews": [{
            "target_ref": "REQ-0007",
            "scores": {"coverage": 4.0},
            "overall_score": 4.0,
            "verdict": "pass",
            "findings": [],
            "coverage_gaps": [],
        }],
        "summary": {"pass": 1, "needs_revision": 0, "fail": 0},
    })

    async def run_test():
        return await _persist_agent_artifacts(db, run, "scenario_review", input_data, agent_result)

    output = anyio.run(run_test)

    review = next(obj for obj in db.added if isinstance(obj, ArtifactReview))
    assert review.artifact_type == "requirement_scenario_coverage"
    assert review.artifact_id == 7
    assert review.verdict == "pass"
    assert review.review_mode == "advisory"
    assert output["count"] == 1


def test_scenario_review_persistence_skips_unresolvable_target_ref():
    db = _FakeDB(project=Project(id=1, owner_id=1, name="P", review_mode="advisory"))
    run = _agent_run("scenario_review")
    input_data = {"requirements": [{"id": 7, "requirement_id": "REQ-0007"}], "scenarios": []}
    agent_result = SimpleNamespace(data={
        "reviews": [{"target_ref": "REQ-DOES-NOT-EXIST", "verdict": "fail"}],
        "summary": {},
    })

    async def run_test():
        return await _persist_agent_artifacts(db, run, "scenario_review", input_data, agent_result)

    output = anyio.run(run_test)
    assert output["count"] == 0
    assert not any(isinstance(obj, ArtifactReview) for obj in db.added)


def test_test_case_review_persistence_seeds_coverage_matrix():
    project = Project(id=1, owner_id=1, name="P", review_mode="gating")
    test_case = TestCase(
        id=100, project_id=1, created_by=1, test_case_id="TC-0100", title="T",
        requirement_id=7, scenario_id=70, test_type="functional", automation_eligible="no",
    )
    # execute() call order inside the "test_case_review" branch:
    #   1. select(TestCase).where(id.in_(...))  -> [test_case]
    #   2. get_entry() inside seed_from_test_case -> None (no baseline row yet)
    db = _FakeDB(project=project, responses=[[test_case], None])
    run = _agent_run("test_case_review")
    input_data = {
        "scenarios": [{"id": 70, "scenario_id": "TS-0070", "scenario_type": "positive"}],
        "test_cases": [{"id": 100, "test_case_id": "TC-0100"}],
    }
    agent_result = SimpleNamespace(data={
        "target_kind": "test_case_set",
        "reviews": [{
            "target_ref": "TS-0070",
            "scores": {"coverage": 3.0},
            "overall_score": 3.0,
            "verdict": "needs_revision",
            "findings": [],
            "coverage_gaps": [{"source_ref": "x", "description": "missing negative case", "severity": "medium"}],
        }],
        "summary": {"pass": 0, "needs_revision": 1, "fail": 0},
    })

    async def run_test():
        return await _persist_agent_artifacts(db, run, "test_case_review", input_data, agent_result)

    output = anyio.run(run_test)

    review = next(obj for obj in db.added if isinstance(obj, ArtifactReview))
    assert review.artifact_type == "scenario_test_case_coverage"
    assert review.artifact_id == 70
    assert review.verdict == "needs_revision"
    assert review.review_mode == "gating"

    matrix_entry = next(obj for obj in db.added if isinstance(obj, CoverageMatrixEntry))
    assert matrix_entry.test_case_id == 100
    assert matrix_entry.requirement_id == 7
    assert matrix_entry.scenario_id == 70
    assert matrix_entry.case_class == "positive"
    assert output["count"] == 1


def test_requirement_quality_persistence_also_writes_artifact_review():
    project = Project(id=1, owner_id=1, name="P", review_mode="advisory")
    requirement = Requirement(
        id=3, project_id=1, created_by=1, requirement_id="REQ-0003",
        source="manual", title="Some requirement", status="pending_review",
    )
    # execute() order in the "requirement_quality" branch: one select(Requirement) per
    # quality_results entry.
    db = _FakeDB(project=project, responses=[requirement])
    run = _agent_run("requirement_quality")
    input_data = {}
    agent_result = SimpleNamespace(data={
        "quality_results": {
            "3": {
                "overall_score": 4.2,
                "verdict": "pass",
                "scenario_generation_readiness": 4,
                "completeness_score": 4.0,
                "clarity_score": 4.0,
                "issues": [],
                "suggestions": ["Tighten the acceptance criteria wording"],
            }
        }
    })

    async def run_test():
        return await _persist_agent_artifacts(db, run, "requirement_quality", input_data, agent_result)

    anyio.run(run_test)

    legacy_review = next(obj for obj in db.added if isinstance(obj, RequirementQualityReview))
    generic_review = next(obj for obj in db.added if isinstance(obj, ArtifactReview))
    assert legacy_review.requirement_id == 3
    assert generic_review.artifact_type == "requirement"
    assert generic_review.artifact_id == 3
    assert generic_review.reviewer_agent == "requirement_quality"
    assert generic_review.verdict == "pass"
