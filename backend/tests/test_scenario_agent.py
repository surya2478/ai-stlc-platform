import pytest

from app.agents.test_planning import scenario_agent
from app.agents.test_planning.scenario_agent import TestScenarioAgent


@pytest.fixture
def anyio_backend():
    # TestScenarioAgent runs on a langgraph StateGraph, which is not
    # trio-compatible (it calls asyncio internals directly). Production only
    # ever runs under asyncio (uvicorn), so pin this module to asyncio rather
    # than testing an execution mode the app never uses.
    return "asyncio"


class FailingLLM:
    async def generate(self, **kwargs):
        raise RuntimeError("provider rate limit")


@pytest.mark.anyio
async def test_scenario_agent_fails_when_all_requirements_error(monkeypatch):
    monkeypatch.setattr(scenario_agent, "get_llm", lambda provider, model: FailingLLM())

    result = await TestScenarioAgent().run(
        requirements=[
            {
                "id": 73,
                "requirement_id": "REQ-0073",
                "title": "eSIM Replacement",
                "summary": "Allow customers to replace a damaged eSIM.",
            }
        ]
    )

    assert result.success is False
    assert result.data["count"] == 0
    assert "Scenario generation failed for all requirements" in result.error
    assert any(log["level"] == "warning" for log in result.logs)
