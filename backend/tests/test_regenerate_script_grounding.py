"""Regression coverage for a real bug found during live testing: the
single-script Regenerate endpoint never fetched or passed the locator_map
catalog to AutomationScriptAgent, unlike the bulk generate-scripts endpoint
(trigger_automation_agent) — so a script regenerated after Playwright MCP
Discovery had already run for its application still came back ungrounded."""
from types import SimpleNamespace

import anyio

from app.agents.base.base_agent import AgentRunResult
from app.models.automation_script import AutomationScript
from app.models.locator_map import LocatorMapEntry
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.services import automation_service


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
    def __init__(self, *, responses=None, get_results=None):
        self.responses = list(responses or [])
        self.get_results = dict(get_results or {})

    async def execute(self, _stmt):
        if not self.responses:
            return _ExecuteResult()
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _ExecuteResult(values=value)
        return _ExecuteResult(value=value)

    async def get(self, model, obj_id):
        return self.get_results.get((model, obj_id))

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None


def _script(**overrides) -> AutomationScript:
    data = {
        "id": 33, "project_id": 8, "created_by": 1, "script_id": "AS-0033",
        "framework": "playwright", "code": "old", "status": "static_passed", "test_case_id": 109,
    }
    data.update(overrides)
    return AutomationScript(**data)


def _tc(**overrides) -> TestCase:
    data = {
        "id": 109, "project_id": 8, "created_by": 1, "test_case_id": "TC-0109",
        "title": "Search with non-ASCII characters", "application_id": None,
    }
    data.update(overrides)
    return TestCase(**data)


def _application(**overrides) -> ProjectApplication:
    data = {
        "id": 4, "project_id": 8, "key": "w", "name": "WebApp",
        "is_default": True, "is_active": True,
        "environment_urls": {"SIT": "https://www.google.com/"},
    }
    data.update(overrides)
    return ProjectApplication(**data)


def _locator(**overrides) -> LocatorMapEntry:
    data = {
        "id": 1, "project_id": 8, "application_id": 4, "page": "https://www.google.com/",
        "element_name": "combobox_search", "recommended_locator": "page.getByRole('combobox')",
        "recommended_strategy": "role", "confidence_score": 90,
    }
    data.update(overrides)
    return LocatorMapEntry(**data)


def test_regenerate_passes_locator_map_for_default_application(monkeypatch):
    tc = _tc(application_id=None)
    application = _application()
    entry = _locator()
    script = _script()

    # Exact db.execute() call order inside regenerate_script:
    # 1. TestCase select
    # 2. build_test_case_application_context -> resolve_default_application
    # 3. build_test_case_application_context -> ProjectExternalDependency list
    # 4. (grounding lookup) resolve_default_application again
    # 5. (grounding lookup) locator_map_service.list_for_application
    db = _FakeDB(responses=[tc, application, [], application, [entry]])

    captured = {}

    class _FakeAgent:
        async def run(self, *, test_cases, framework, locator_map=None):
            captured["test_cases"] = test_cases
            captured["locator_map"] = locator_map
            return AgentRunResult(success=True, data={"scripts": [{
                "file_path": "specs/x.spec.ts", "code": "new code",
                "compiled_files": {"specs/x.spec.ts": "new code"}, "contract": {"testCaseId": "TC-0109"},
                "grounded": True, "grounded_element_count": 1, "ungrounded_elements": [],
            }]}, logs=[])

    import app.agents.automation.automation_agent as automation_agent_module
    monkeypatch.setattr(automation_agent_module, "AutomationScriptAgent", _FakeAgent)

    async def run_test():
        return await automation_service.regenerate_script(db, script, user_id=2)

    result = anyio.run(run_test)

    assert result.code == "new code"
    assert captured["locator_map"] == {"4": [{
        "element_name": "combobox_search",
        "page": "https://www.google.com/",
        "role": "role",
        "business_meaning": None,
        "recommended_locator": "page.getByRole('combobox')",
        "confidence_score": 90,
    }]}
    assert captured["test_cases"][0]["application_id"] == 4
    # Real bug found via a live run: regenerate never updated
    # metadata_.grounding, so the UI kept showing "grounded: false" from
    # the original ungrounded generation even after a grounded regenerate.
    assert result.metadata_["grounding"] == {
        "grounded": True, "grounded_element_count": 1, "ungrounded_elements": [],
    }


def test_regenerate_passes_empty_locator_map_when_no_application_resolves(monkeypatch):
    tc = _tc(application_id=None)
    script = _script()

    # 1. TestCase select
    # 2. build_test_case_application_context -> resolve_default_application (none found)
    #    (no ProjectExternalDependency query — only runs when an application was found)
    # 3. (grounding lookup) resolve_default_application again (none found)
    #    (no locator_map_service query — only runs when an application was found)
    db = _FakeDB(responses=[tc, None, None])

    captured = {}

    class _FakeAgent:
        async def run(self, *, test_cases, framework, locator_map=None):
            captured["locator_map"] = locator_map
            return AgentRunResult(success=True, data={"scripts": [{
                "file_path": "specs/x.spec.ts", "code": "new code",
            }]}, logs=[])

    import app.agents.automation.automation_agent as automation_agent_module
    monkeypatch.setattr(automation_agent_module, "AutomationScriptAgent", _FakeAgent)

    async def run_test():
        return await automation_service.regenerate_script(db, script, user_id=2)

    anyio.run(run_test)

    assert captured["locator_map"] == {}
