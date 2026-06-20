"""GAP-4 tests: quality-review persistence, quality gating, coverage analytics."""
import anyio
import pytest

from app.api.v1.endpoints.test_plans import _quality_gate_blockers, _enforce_quality_gate
from app.models.requirement import Requirement
from app.services.coverage_service import _priority_score
from app.worker.tasks import agent_tasks
from fastapi import HTTPException


def _req(**kwargs) -> Requirement:
    base = dict(
        project_id=1,
        created_by=1,
        requirement_id="REQ-1",
        source="manual",
        title="Test requirement",
        status="approved",
    )
    base.update(kwargs)
    return Requirement(**base)


# ── GAP-4a: worker persistence handler is registered ──────────────────────────

def test_requirement_quality_in_agent_registry():
    assert "requirement_quality" in agent_tasks.AGENT_REGISTRY
    assert "requirement_enrichment" in agent_tasks.AGENT_REGISTRY


def test_requirement_enrichment_task_uses_agent_signature(monkeypatch):
    calls = {}

    class FakeEnrichmentAgent:
        async def run(self, requirements, project_id=0):
            calls["requirements"] = requirements
            calls["project_id"] = project_id
            return {"ok": True}

    monkeypatch.setattr(agent_tasks, "RequirementEnrichmentAgent", lambda: FakeEnrichmentAgent())

    result = anyio.run(
        agent_tasks._requirement_enrichment,
        {"requirements": [{"id": 7, "title": "T", "summary": "S"}], "project_id": 42},
    )
    assert result == {"ok": True}
    assert calls["project_id"] == 42


# ── GAP-4c: quality gate ──────────────────────────────────────────────────────

def test_quality_gate_blocks_failed_verdict():
    blocked = _quality_gate_blockers([_req(quality_verdict="fail")])
    assert len(blocked) == 1
    assert "fail" in blocked[0]["reasons"][0]


def test_quality_gate_blocks_low_score():
    blocked = _quality_gate_blockers([_req(quality_score=1.5)])
    assert len(blocked) == 1


def test_quality_gate_blocks_rejected():
    blocked = _quality_gate_blockers([_req(status="rejected")])
    assert len(blocked) == 1


def test_quality_gate_allows_unreviewed_and_passing():
    assert _quality_gate_blockers([_req()]) == []
    assert _quality_gate_blockers([_req(quality_verdict="pass", quality_score=4.2)]) == []


def test_enforce_quality_gate_raises_422_with_structured_detail():
    with pytest.raises(HTTPException) as exc_info:
        _enforce_quality_gate([_req(quality_verdict="fail")], override=False)
    detail = exc_info.value.detail
    assert exc_info.value.status_code == 422
    assert detail["code"] == "quality_gate_blocked"
    assert detail["blocked_requirements"]


def test_enforce_quality_gate_override_allows_generation():
    _enforce_quality_gate([_req(quality_verdict="fail")], override=True)  # no raise


# ── GAP-4d: priority scoring ──────────────────────────────────────────────────

def test_priority_score_critical_regulatory_uncovered_is_p1():
    req = _req(risk_level="Critical", regulatory_impact=True, revenue_impact=True)
    score, band = _priority_score(req, coverage_score=0)
    assert band == "P1"
    assert score >= 70


def test_priority_score_low_risk_fully_covered_is_low_band():
    req = _req(risk_level="Low", regulatory_impact=False, revenue_impact=False, customer_impact=False)
    score, band = _priority_score(req, coverage_score=100)
    assert band in ("P3", "P4")


def test_priority_score_bounded_0_100():
    req = _req(risk_level="Critical", regulatory_impact=True, revenue_impact=True, customer_impact=True)
    score, _ = _priority_score(req, coverage_score=0)
    assert 0 <= score <= 100
