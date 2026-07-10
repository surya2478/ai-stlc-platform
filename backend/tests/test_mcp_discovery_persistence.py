"""Phase 3: persistence of the playwright_mcp_discovery agent's output —
locator_map upserts + eligibility pass-2 overrides on TestCase/coverage_matrix.

Also covers a real gap found via live testing: discovered locator_map rows
had no traceability lineage back to the test cases that triggered them —
locator_map has no test_case_id column at all, so without an explicit
lineage edge there was no way for the Trace drawer (or any other UI) to
answer "which discovery run grounded this test case's automation?"."""
from types import SimpleNamespace

import anyio

from app.models.agent import AgentRun
from app.models.artifact_lineage import ArtifactLineage
from app.models.locator_map import LocatorMapEntry
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
    def __init__(self, *, responses=None, get_results=None):
        self.responses = list(responses or [])
        self.get_results = dict(get_results or {})
        self.added = []

    async def execute(self, _stmt):
        if not self.responses:
            return _ExecuteResult()
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _ExecuteResult(values=value)
        return _ExecuteResult(value=value)

    async def get(self, model, obj_id):
        return self.get_results.get((model, obj_id))

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 1
        self.added.append(obj)

    async def flush(self):
        return None


def _agent_run() -> AgentRun:
    return AgentRun(id=60, project_id=1, triggered_by=1, agent_name="playwright_mcp_discovery", status="running")


def test_discovery_persistence_upserts_locator_map_rows():
    db = _FakeDB(responses=[None])  # one locator_map upsert lookup -> no existing row
    run = _agent_run()
    input_data = {"test_cases": [{"test_case_id": "TC-1", "id": 5}]}
    agent_result = SimpleNamespace(data={
        "applications": [{
            "application_id": 7,
            "pages": [{
                "url": "http://app.example.com/login",
                "elements": [{
                    "element_name": "textbox_username",
                    "role": "textbox",
                    "accessible_name": "Username",
                    "recommended_locator": "page.getByRole('textbox', { name: 'Username' })",
                    "recommended_strategy": "role",
                    "confidence_score": 90,
                }],
            }],
            "eligibility_overrides": {},
        }],
    })

    async def run_test():
        return await _persist_agent_artifacts(db, run, "playwright_mcp_discovery", input_data, agent_result)

    output = anyio.run(run_test)

    entry = next(obj for obj in db.added if isinstance(obj, LocatorMapEntry))
    assert entry.application_id == 7
    assert entry.element_name == "textbox_username"
    assert entry.confidence_score == 90
    assert output["count"] == 1


def test_discovery_persistence_links_locator_entries_to_triggering_test_cases():
    db = _FakeDB(responses=[None])  # one locator_map upsert lookup -> no existing row
    run = _agent_run()
    input_data = {"test_cases": [
        {"test_case_id": "TC-1", "id": 5, "application_id": 7},
        {"test_case_id": "TC-2", "id": 6, "application_id": 7},
    ]}
    agent_result = SimpleNamespace(data={
        "applications": [{
            "application_id": 7,
            "pages": [{
                "url": "http://app.example.com/login",
                "elements": [{
                    "element_name": "textbox_username",
                    "role": "textbox",
                    "accessible_name": "Username",
                    "recommended_locator": "page.getByRole('textbox', { name: 'Username' })",
                    "recommended_strategy": "role",
                    "confidence_score": 90,
                }],
            }],
            "eligibility_overrides": {},
        }],
    })

    async def run_test():
        return await _persist_agent_artifacts(db, run, "playwright_mcp_discovery", input_data, agent_result)

    anyio.run(run_test)

    entry = next(obj for obj in db.added if isinstance(obj, LocatorMapEntry))
    lineage_rows = [obj for obj in db.added if isinstance(obj, ArtifactLineage)]
    assert len(lineage_rows) == 2  # one edge per triggering test case
    assert {(row.parent_type, row.parent_id, row.child_type, row.child_id) for row in lineage_rows} == {
        ("test_case", 5, "locator_map", entry.id),
        ("test_case", 6, "locator_map", entry.id),
    }
    assert all(row.agent_run_id == run.id for row in lineage_rows)


def test_discovery_persistence_skips_lineage_when_test_case_has_no_application_id():
    # Mirrors input_data shapes built before application_id was carried
    # through the trigger endpoint — must not crash, just skip lineage.
    db = _FakeDB(responses=[None])
    run = _agent_run()
    input_data = {"test_cases": [{"test_case_id": "TC-1", "id": 5}]}  # no application_id key
    agent_result = SimpleNamespace(data={
        "applications": [{
            "application_id": 7,
            "pages": [{
                "url": "http://app.example.com/login",
                "elements": [{
                    "element_name": "textbox_username",
                    "role": "textbox",
                    "accessible_name": "Username",
                    "recommended_locator": "page.getByRole('textbox', { name: 'Username' })",
                    "recommended_strategy": "role",
                    "confidence_score": 90,
                }],
            }],
            "eligibility_overrides": {},
        }],
    })

    async def run_test():
        return await _persist_agent_artifacts(db, run, "playwright_mcp_discovery", input_data, agent_result)

    anyio.run(run_test)

    assert not any(isinstance(obj, ArtifactLineage) for obj in db.added)


def test_discovery_persistence_applies_eligibility_override():
    tc = TestCase(
        id=5, project_id=1, created_by=1, test_case_id="TC-1", title="Verify OTP",
        automation_eligible="yes", automation_status="ready_for_automation",
    )
    db = _FakeDB(get_results={(TestCase, 5): tc}, responses=[None])
    run = _agent_run()
    input_data = {"test_cases": [{"test_case_id": "TC-1", "id": 5}]}
    agent_result = SimpleNamespace(data={
        "applications": [{
            "application_id": 7,
            "pages": [],
            "eligibility_overrides": {"TC-1": ["requires an OTP challenge"]},
        }],
    })

    async def run_test():
        return await _persist_agent_artifacts(db, run, "playwright_mcp_discovery", input_data, agent_result)

    output = anyio.run(run_test)

    assert tc.automation_eligible == "no"
    assert tc.automation_status == "not_required"
    assert tc.metadata_["automation_eligibility_live_override"]["reasons"] == ["requires an OTP challenge"]
    assert output["eligibility_overridden_test_case_ids"] == [5]
