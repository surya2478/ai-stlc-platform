"""Phase 1: stage reviewer gate (_enforce_review_gate in test_plans.py)."""
import anyio
import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import test_plans
from app.models.artifact_review import ArtifactReview
from app.services import artifact_review_service


def _review(verdict: str) -> ArtifactReview:
    return ArtifactReview(
        id=1, project_id=1, artifact_type="requirement_scenario_coverage",
        artifact_id=1, reviewer_agent="scenario_review", verdict=verdict,
    )


def test_enforce_review_gate_noop_when_artifact_id_missing():
    async def run():
        await test_plans._enforce_review_gate(
            db=None, project_id=1, artifact_type="requirement_scenario_coverage",
            artifact_id=None, override=False,
        )

    anyio.run(run)  # must not raise / must not touch db


def test_enforce_review_gate_allows_when_mode_is_advisory(monkeypatch):
    async def fake_mode(_db, _project_id):
        return "advisory"

    monkeypatch.setattr(artifact_review_service, "get_review_mode", fake_mode)

    async def run():
        await test_plans._enforce_review_gate(
            db=None, project_id=1, artifact_type="requirement_scenario_coverage",
            artifact_id=1, override=False,
        )

    anyio.run(run)  # advisory never blocks, even with a fail verdict it never looked up


def test_enforce_review_gate_allows_when_mode_is_off(monkeypatch):
    async def fake_mode(_db, _project_id):
        return "off"

    monkeypatch.setattr(artifact_review_service, "get_review_mode", fake_mode)

    async def run():
        await test_plans._enforce_review_gate(
            db=None, project_id=1, artifact_type="requirement_scenario_coverage",
            artifact_id=1, override=False,
        )

    anyio.run(run)


def test_enforce_review_gate_blocks_fail_verdict_in_gating_mode(monkeypatch):
    async def fake_mode(_db, _project_id):
        return "gating"

    async def fake_latest(_db, *, artifact_type, artifact_id):
        return _review("fail")

    monkeypatch.setattr(artifact_review_service, "get_review_mode", fake_mode)
    monkeypatch.setattr(artifact_review_service, "latest_review_for", fake_latest)

    async def run():
        await test_plans._enforce_review_gate(
            db=None, project_id=1, artifact_type="requirement_scenario_coverage",
            artifact_id=1, override=False,
        )

    with pytest.raises(HTTPException) as exc_info:
        anyio.run(run)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "review_gate_blocked"


def test_enforce_review_gate_gating_mode_allows_pass_verdict(monkeypatch):
    async def fake_mode(_db, _project_id):
        return "gating"

    async def fake_latest(_db, *, artifact_type, artifact_id):
        return _review("pass")

    monkeypatch.setattr(artifact_review_service, "get_review_mode", fake_mode)
    monkeypatch.setattr(artifact_review_service, "latest_review_for", fake_latest)

    async def run():
        await test_plans._enforce_review_gate(
            db=None, project_id=1, artifact_type="requirement_scenario_coverage",
            artifact_id=1, override=False,
        )

    anyio.run(run)  # pass verdict never blocks


def test_enforce_review_gate_override_bypasses_fail_verdict(monkeypatch):
    async def fake_mode(_db, _project_id):
        return "gating"

    async def fake_latest(_db, *, artifact_type, artifact_id):
        return _review("fail")

    monkeypatch.setattr(artifact_review_service, "get_review_mode", fake_mode)
    monkeypatch.setattr(artifact_review_service, "latest_review_for", fake_latest)

    async def run():
        await test_plans._enforce_review_gate(
            db=None, project_id=1, artifact_type="requirement_scenario_coverage",
            artifact_id=1, override=True,
        )

    anyio.run(run)  # override bypasses the block


def test_enforce_review_gate_allows_unreviewed_artifact_in_gating_mode(monkeypatch):
    async def fake_mode(_db, _project_id):
        return "gating"

    async def fake_latest(_db, *, artifact_type, artifact_id):
        return None

    monkeypatch.setattr(artifact_review_service, "get_review_mode", fake_mode)
    monkeypatch.setattr(artifact_review_service, "latest_review_for", fake_latest)

    async def run():
        await test_plans._enforce_review_gate(
            db=None, project_id=1, artifact_type="requirement_scenario_coverage",
            artifact_id=1, override=False,
        )

    anyio.run(run)  # no review yet is a soft gate, same as the quality gate's convention
