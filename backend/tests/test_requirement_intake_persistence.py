"""Regression test: the async worker's requirement_intake persistence branch
must copy telecom_domain/risk_level/test_phase/etc from the intake agent's
LLM output onto the created Requirement, same as the ui_image_analysis and
url_analysis branches already do. This field mapping was previously missing
here, which left the Edit Requirement Classification dialog blank for every
doc_upload-sourced requirement created via the queued (non-synchronous)
agent path."""
from types import SimpleNamespace

import anyio

from app.models.agent import AgentRun
from app.models.requirement import Requirement
from app.worker.tasks.agent_tasks import _persist_agent_artifacts


class _FakeDB:
    def __init__(self):
        self.added = []

    async def get(self, _model, _id):
        return None

    async def execute(self, _stmt):
        class _Result:
            def scalar_one_or_none(self_inner):
                return None

            def scalars(self_inner):
                class _Scalars:
                    def all(self_inner2):
                        return []
                return _Scalars()
        return _Result()

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 1
        self.added.append(obj)

    async def flush(self):
        return None


def _agent_run() -> AgentRun:
    return AgentRun(id=50, project_id=1, triggered_by=1, agent_name="requirement_intake", status="running", metadata_={})


def test_requirement_intake_persistence_copies_classification_fields():
    db = _FakeDB()
    run = _agent_run()
    input_data = {"document_text": "...", "project_id": 1}
    agent_result = SimpleNamespace(data={
        "requirements": [{
            "title": "Service Provisioning",
            "summary": "Provision voice/data services.",
            "telecom_domain": "Billing",
            "risk_level": "High",
            "test_phase": "SIT",
            "release_version": "2026.1",
            "impacted_interfaces": ["Diameter Gy"],
            "regulatory_impact": True,
            "revenue_impact": True,
        }],
    })

    async def run_test():
        return await _persist_agent_artifacts(db, run, "requirement_intake", input_data, agent_result)

    output = anyio.run(run_test)

    req = next(obj for obj in db.added if isinstance(obj, Requirement))
    assert req.telecom_domain == "Billing"
    assert req.risk_level == "High"
    assert req.test_phase == "SIT"
    assert req.release_version == "2026.1"
    assert req.impacted_interfaces == ["Diameter Gy"]
    assert req.regulatory_impact is True
    assert req.revenue_impact is True
    assert output["count"] == 1
