from datetime import datetime, timedelta, timezone

import anyio

from app.models.artifact_review import ArtifactReview
from app.models.project import Project
from app.services import artifact_review_service as svc


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


class _FakeDB:
    def __init__(self, *, project=None, reviews=None):
        self._project = project
        self._reviews = reviews or []
        self.added = []

    async def get(self, _model, _id):
        return self._project

    async def execute(self, _stmt):
        return _ExecuteResult(list(self._reviews))

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 1
        self.added.append(obj)

    async def flush(self):
        return None


def _review(**overrides):
    base = dict(
        id=None,
        project_id=1,
        agent_run_id=None,
        artifact_type="requirement_scenario_coverage",
        artifact_id=1,
        reviewer_agent="scenario_review",
        verdict="pass",
        created_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return ArtifactReview(**base)


def test_get_review_mode_returns_project_setting():
    db = _FakeDB(project=Project(id=1, owner_id=1, name="P", review_mode="gating"))
    mode = anyio.run(svc.get_review_mode, db, 1)
    assert mode == "gating"


def test_get_review_mode_defaults_to_advisory_when_project_missing():
    db = _FakeDB(project=None)
    mode = anyio.run(svc.get_review_mode, db, 999)
    assert mode == "advisory"


def test_create_review_normalizes_invalid_verdict():
    db = _FakeDB()

    async def run():
        return await svc.create_review(
            db,
            project_id=1,
            agent_run_id=5,
            artifact_type="requirement",
            artifact_id=1,
            reviewer_agent="requirement_quality",
            scores={"completeness": 4.0},
            overall_score=4.0,
            verdict="bogus",
            findings=None,
            coverage_gaps=None,
            review_mode="advisory",
        )

    review = anyio.run(run)
    assert review.verdict == "needs_revision"
    assert review in db.added


def test_latest_reviews_picks_most_recent_per_artifact():
    now = datetime.now(timezone.utc)
    older = _review(id=1, artifact_id=1, verdict="fail", created_at=now - timedelta(hours=1))
    newer = _review(id=2, artifact_id=1, verdict="pass", created_at=now)
    other = _review(id=3, artifact_id=2, verdict="needs_revision", created_at=now)
    db = _FakeDB(reviews=[newer, older, other])

    async def run():
        return await svc.latest_reviews(
            db, artifact_type="requirement_scenario_coverage", artifact_ids=[1, 2]
        )

    result = anyio.run(run)
    assert result[1].id == 2
    assert result[2].id == 3


def test_latest_reviews_empty_ids_returns_empty_without_query():
    db = _FakeDB(reviews=[_review(id=1)])

    async def run():
        return await svc.latest_reviews(db, artifact_type="requirement", artifact_ids=[])

    result = anyio.run(run)
    assert result == {}
