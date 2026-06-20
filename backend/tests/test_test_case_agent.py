import pytest

from app.agents.test_planning import test_case_agent
from app.agents.test_planning.test_case_agent import TestCaseDevelopmentAgent


class FailingLLM:
    async def generate(self, **kwargs):
        raise RuntimeError("provider rate limit")


@pytest.mark.anyio
async def test_test_case_agent_fails_when_all_scenarios_error(monkeypatch):
    monkeypatch.setattr(test_case_agent, "get_llm", lambda provider, model: FailingLLM())

    result = await TestCaseDevelopmentAgent().run(
        scenarios=[
            {
                "id": 145,
                "scenario_id": "TS-0145",
                "title": "Successful eSIM Replacement",
                "description": "Validate successful eSIM replacement.",
                "_source_requirement_id": 73,
            }
        ]
    )

    assert result.success is False
    assert result.data["count"] == 0
    assert "Test case generation failed for all scenarios" in result.error
    assert any(log["level"] == "warning" for log in result.logs)
