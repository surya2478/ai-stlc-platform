import pytest

from app.agents.requirement import code_analysis_agent
from app.agents.requirement.code_analysis_agent import CodeAnalysisAgent


class EmptyRequirementsLLM:
    async def generate(self, **_kwargs):
        return '{"requirements": []}'


@pytest.mark.anyio
async def test_code_analysis_agent_fails_when_no_requirements_are_derived(monkeypatch, tmp_path):
    monkeypatch.setattr(code_analysis_agent, "_repo_size_bytes", lambda _root: 1024)
    monkeypatch.setattr(code_analysis_agent, "_collect_files", lambda _root, _languages: ["fake.py"])
    monkeypatch.setattr(code_analysis_agent, "_chunk_files", lambda _files, _root: ["# File: fake.py\ndef useful_feature(): pass"])
    monkeypatch.setattr(code_analysis_agent, "get_llm_for_role", lambda _role: EmptyRequirementsLLM())

    result = await CodeAnalysisAgent().run(
        source="local",
        local_path=str(tmp_path),
        languages=["python"],
    )

    assert result.success is False
    assert result.data["count"] == 0
    assert "Code analysis produced no requirements" in result.error
