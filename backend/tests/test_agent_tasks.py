import anyio

from app.worker.tasks import agent_tasks


def test_requirement_quality_task_uses_agent_signature(monkeypatch):
    calls = {}

    class FakeQualityAgent:
        async def run(self, requirements):
            calls["requirements"] = requirements
            return {"ok": True}

    monkeypatch.setattr(agent_tasks, "RequirementQualityAgent", lambda: FakeQualityAgent())

    result = anyio.run(
        agent_tasks._requirement_quality,
        {"requirements": [{"id": 1}], "project_id": 123},
    )

    assert result == {"ok": True}
    assert calls["requirements"] == [{"id": 1}]
