"""Phase 4.6b: Automation Confidence Score — a composite 0-1 aggregate over
locator grounding, the Static Quality Gate, TDM/data readiness, environment
readiness, and dry-run stability. Every dimension reads facts the pipeline
already computed; this service only aggregates, so tests check both the
per-dimension reads and the weighted overall."""
import anyio

from app.models.automation_script import AutomationScript
from app.models.locator_map import LocatorMapEntry
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.services import automation_confidence_service as svc


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, values=None):
        self._values = values or []

    def scalars(self):
        return _ScalarsResult(self._values)

    def scalar_one_or_none(self):
        return self._values[0] if self._values else None


class _FakeDB:
    def __init__(self, *, responses=None, get_results=None):
        self.responses = list(responses or [])
        self.get_results = dict(get_results or {})

    async def execute(self, _stmt):
        if not self.responses:
            return _ExecuteResult()
        return _ExecuteResult(values=self.responses.pop(0))

    async def get(self, model, obj_id):
        return self.get_results.get((model, obj_id))


CONTRACT_WITH_ONE_ELEMENT = {
    "pageObjects": [{"name": "LoginPage", "elements": [{"name": "usernameInput"}]}],
}


def _script(**overrides):
    data = {
        "id": 1, "project_id": 1, "created_by": 1, "script_id": "AS-0001",
        "framework": "playwright", "code": "x", "test_case_id": 10,
        "contract": CONTRACT_WITH_ONE_ELEMENT,
        "static_gate_result": {"passed": True, "violations": [], "warnings": []},
    }
    data.update(overrides)
    return AutomationScript(**data)


def test_locator_confidence_averages_matched_entries():
    tc = TestCase(id=10, project_id=1, created_by=1, test_case_id="TC-1", title="x", application_id=7)
    entry = LocatorMapEntry(
        id=1, project_id=1, application_id=7, page="/login", element_name="usernameInput",
        recommended_locator="#user", recommended_strategy="css", confidence_score=80,
    )
    db = _FakeDB(responses=[[entry]], get_results={(TestCase, 10): tc})
    script = _script()

    result = anyio.run(svc._locator_confidence, db, script)

    assert result == 0.8


def test_locator_confidence_neutral_when_no_elements_in_contract():
    db = _FakeDB()
    script = _script(contract={})

    result = anyio.run(svc._locator_confidence, db, script)

    assert result == 0.5


def test_assertion_confidence_full_when_gate_passed_clean():
    script = _script(static_gate_result={"passed": True, "violations": [], "warnings": []})
    assert svc._assertion_confidence(script) == 1.0


def test_assertion_confidence_zero_when_gate_failed():
    script = _script(static_gate_result={"passed": False, "violations": [{"code": "x"}], "warnings": []})
    assert svc._assertion_confidence(script) == 0.0


def test_assertion_confidence_scaled_down_by_warnings():
    script = _script(static_gate_result={"passed": True, "violations": [], "warnings": [{"code": "a"}, {"code": "b"}]})
    assert svc._assertion_confidence(script) == 0.9


def test_assertion_confidence_neutral_when_no_gate_result():
    script = _script(static_gate_result=None)
    assert svc._assertion_confidence(script) == 0.5


def test_data_readiness_full_when_test_data_present():
    tc = TestCase(id=10, project_id=1, created_by=1, test_case_id="TC-1", title="x", test_data={"username": "a"})
    db = _FakeDB(get_results={(TestCase, 10): tc})
    script = _script()

    assert anyio.run(svc._data_readiness, db, script) == 1.0


def test_data_readiness_partial_when_no_test_data():
    tc = TestCase(id=10, project_id=1, created_by=1, test_case_id="TC-1", title="x", test_data=None)
    db = _FakeDB(get_results={(TestCase, 10): tc})
    script = _script()

    assert anyio.run(svc._data_readiness, db, script) == 0.7


def test_environment_readiness_full_when_url_resolves():
    tc = TestCase(id=10, project_id=1, created_by=1, test_case_id="TC-1", title="x", application_id=7, test_phase="QA")
    application = ProjectApplication(
        id=7, project_id=1, key="web", name="Web", is_default=True, is_active=True,
        environment_urls={"QA": "http://qa.app.example.com"},
    )
    db = _FakeDB(get_results={(TestCase, 10): tc, (ProjectApplication, 7): application})
    script = _script()

    assert anyio.run(svc._environment_readiness, db, script) == 1.0


def test_environment_readiness_zero_when_no_application_found():
    tc = TestCase(id=10, project_id=1, created_by=1, test_case_id="TC-1", title="x", application_id=None, test_phase="QA")
    db = _FakeDB(get_results={(TestCase, 10): tc})
    script = _script()

    assert anyio.run(svc._environment_readiness, db, script) == 0.0


def test_dry_run_stability_computes_pass_rate():
    from app.models.execution import ExecutionResult

    results = [
        ExecutionResult(
            id=i, execution_run_id=1, project_id=1, test_name="t", status=status,
            metadata_={"automation_script_id": 1, "dry_run": True},
        )
        for i, status in enumerate([True, True, False], start=1)
    ]
    # translate booleans to actual status strings
    for r, passed in zip(results, [True, True, False]):
        r.status = "pass" if passed else "fail"

    db = _FakeDB(responses=[results])
    script = _script()

    assert anyio.run(svc._dry_run_stability, db, script) == 2 / 3


def test_dry_run_stability_neutral_when_no_history():
    db = _FakeDB(responses=[[]])
    script = _script()

    assert anyio.run(svc._dry_run_stability, db, script) == 0.5


def test_compute_confidence_score_aggregates_all_dimensions(monkeypatch):
    async def fake_locator(db, script):
        return 1.0

    async def fake_data(db, script):
        return 1.0

    async def fake_env(db, script):
        return 1.0

    async def fake_dry_run(db, script):
        return 1.0

    monkeypatch.setattr(svc, "_locator_confidence", fake_locator)
    monkeypatch.setattr(svc, "_data_readiness", fake_data)
    monkeypatch.setattr(svc, "_environment_readiness", fake_env)
    monkeypatch.setattr(svc, "_dry_run_stability", fake_dry_run)

    db = _FakeDB()
    script = _script(static_gate_result={"passed": True, "violations": [], "warnings": []})

    result = anyio.run(svc.compute_confidence_score, db, script)

    assert result["overall"] == 1.0
    assert result["locator_confidence"] == 1.0
    assert result["assertion_confidence"] == 1.0
