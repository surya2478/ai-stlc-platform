"""Playwright AI Studio (M1): planner agent, studio_service stage machine,
bulk gates, persistence branch, and endpoint wiring.

Follows the fake-DB + dependency_overrides pattern from
test_automation_batch_execution.py and the anyio.run + monkeypatch pattern
from test_dry_run_agent.py — no real database, browser, or broker.
"""
from types import SimpleNamespace

import anyio
import pytest
from fastapi.testclient import TestClient

import app.agents.automation.planner_agent as planner_mod
import app.services.studio_service as studio_mod
import app.worker.tasks.agent_tasks as agent_tasks_mod
from app.agents.automation.planner_agent import PlaywrightPlannerAgent, _in_scope_links
from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.agent import AgentRun
from app.models.approval import ApprovalAction
from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionRun
from app.models.project import Project
from app.models.project_application import ProjectApplication
from app.models.studio_run import StudioRun
from app.models.test_case import TestCase
from app.models.user import User
from app.schemas.playwright_studio import StudioRunCreate
from app.services import automation_service
from app.services.automation_generation_service import GenerationPayload
from app.services.studio_service import StudioStateError, StudioValidationError


# ── Shared fakes (same shape as test_automation_batch_execution.py) ─────────

class _ScalarsResult:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return self._items


class _ExecResult:
    def __init__(self, *, single=None, many=None):
        self._single = single
        self._many = many if many is not None else []

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return _ScalarsResult(self._many)

    def all(self):
        return self._many


class _FakeDB:
    def __init__(self, get_map=None, execute_queue=None):
        self.get_map = dict(get_map or {})
        self.execute_queue = list(execute_queue or [])
        self.added = []
        self.next_id = 1000
        self.commits = 0

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self.next_id
            self.next_id += 1
        self.added.append(obj)
        self.get_map[(type(obj), obj.id)] = obj

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def execute(self, _stmt):
        return self.execute_queue.pop(0)


async def _owner_user():
    return User(
        id=1, email="owner@example.com", full_name="Owner", hashed_password="x",
        role="qa_engineer", is_active=True, is_superuser=False,
    )


def _override(db):
    async def fake_db():
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _owner_user


def _clear():
    app.dependency_overrides.clear()


def _project():
    return Project(id=1, owner_id=1, name="Project")


def _application(**overrides):
    defaults = dict(
        id=5, project_id=1, name="B2B Portal", is_default=True, is_active=True,
        environment_urls={"SIT": "https://sit.example.com"},
    )
    defaults.update(overrides)
    return ProjectApplication(**defaults)


def _studio_run(**overrides):
    defaults = dict(
        id=30, project_id=1, created_by=1, name="Nightly SIT", status="draft",
        config={
            "application_id": 5, "environment": "SIT",
            "target_url": "https://sit.example.com", "objective": "orders",
            "coverage_types": ["positive"], "excluded_paths": [], "max_pages": 5,
            "max_minutes": 10, "framework": "playwright", "runner_mode": "local",
            "parallelism": 2, "timeout_seconds": 300,
        },
    )
    defaults.update(overrides)
    return StudioRun(**defaults)


def _create_payload(**overrides):
    defaults = dict(
        project_id=1, name="Nightly SIT", application_id=5, environment="SIT",
        objective="Explore order flows", coverage_types=["positive", "negative"],
    )
    defaults.update(overrides)
    return StudioRunCreate(**defaults)


class _FakeParsedElement(SimpleNamespace):
    pass


class _FakeParsed(SimpleNamespace):
    pass


def _parsed_page(url, title, links=(), interactive=()):
    elements = [
        _FakeParsedElement(role="link", name=name, href=href, ref=None)
        for name, href in links
    ]
    interactive_elements = [
        _FakeParsedElement(role=role, name=name, href=None, ref=None)
        for role, name in interactive
    ]
    return _FakeParsed(
        page_url=url, page_title=title,
        elements=elements + interactive_elements,
        interactive_elements=interactive_elements,
    )


# ── Planner: link scoping ────────────────────────────────────────────────────

def test_in_scope_links_filters_host_excluded_paths_and_duplicates():
    parsed = _parsed_page(
        "https://sit.example.com/home", "Home",
        links=[
            ("Orders", "/orders"),
            ("Orders again", "https://sit.example.com/orders#tab"),
            ("Admin", "/admin/settings"),
            ("External", "https://evil.example.org/phish"),
            ("Mail", "mailto:x@example.com"),
        ],
    )
    links = _in_scope_links(
        parsed, "https://sit.example.com/home",
        allowed_host="sit.example.com", excluded_paths=["/admin"],
    )
    assert links == ["https://sit.example.com/orders"]


# ── Planner: proposal validation/coercion ────────────────────────────────────

class _FakeLLM:
    def __init__(self, response):
        self._response = response

    async def achat(self, messages):
        return self._response


def test_propose_for_page_coerces_and_grounds(monkeypatch):
    response = """[
      {"title": "Login works", "module": "Auth", "priority": "High", "coverage_type": "positive",
       "preconditions": [], "expected_result": "Dashboard visible",
       "steps": [
         {"action": "fill", "element": "textbox-username", "value": "u", "description": "Enter username"},
         {"action": "smash", "element": "button-made-up", "description": "Press the made-up button"}
       ]},
      {"title": "Weird priority", "priority": "URGENT", "coverage_type": "chaos",
       "steps": [{"action": "click", "element": "button-login", "description": "Click login"}],
       "expected_result": "x"},
      {"title": "Malformed, no steps", "steps": [], "expected_result": "x"}
    ]"""
    monkeypatch.setattr(planner_mod, "get_llm", lambda *a, **k: _FakeLLM(response))
    agent = PlaywrightPlannerAgent(llm=_FakeLLM("unused"))
    page = {
        "url": "https://sit.example.com/login", "title": "Login", "blockers": [],
        "elements": [
            {"element_name": "textbox-username", "role": "textbox", "accessible_name": "Username"},
            {"element_name": "button-login", "role": "button", "accessible_name": "Login"},
        ],
    }

    async def run():
        return await agent._propose_for_page(
            page, objective="", environment="SIT", coverage_types=["positive"]
        )

    proposals = anyio.run(run)

    assert len(proposals) == 2  # malformed third proposal dropped
    first = proposals[0]
    assert first.steps[1].action == "custom"  # unknown verb demoted, never guessed
    assert first.ungrounded_elements == ["button-made-up"]
    second = proposals[1]
    assert second.priority == "Medium"
    assert second.coverage_type == "positive"


# ── Planner: bounded exploration run ─────────────────────────────────────────

class _FakeMCPSession:
    pages: dict = {}

    def __init__(self, config, on_call=None):
        self._current = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def navigate(self, url):
        self._current = url.split("#", 1)[0]

    async def snapshot(self):
        return self._current or ""


def test_planner_run_explores_within_bounds(monkeypatch, tmp_path):
    site = {
        "https://sit.example.com": _parsed_page(
            "https://sit.example.com", "Home",
            links=[("Orders", "/orders"), ("Admin", "/admin")],
            interactive=[("button", "New Order")],
        ),
        "https://sit.example.com/orders": _parsed_page(
            "https://sit.example.com/orders", "Orders",
            interactive=[("button", "Submit Order")],
        ),
    }

    async def fake_readiness(_inputs):
        return SimpleNamespace(ready=True, blockers=[])

    monkeypatch.setattr(planner_mod, "check_readiness", fake_readiness)
    monkeypatch.setattr(planner_mod, "workspace_root", lambda: tmp_path)
    monkeypatch.setattr(planner_mod, "MCPSession", _FakeMCPSession)
    monkeypatch.setattr(planner_mod, "parse_snapshot", lambda raw: site[raw])

    agent = PlaywrightPlannerAgent(llm=_FakeLLM("unused"))

    async def fake_propose(page, **_kwargs):
        return [planner_mod.ProposedTestCase(
            title=f"Case for {page['title']}", page_url=page["url"],
            steps=[planner_mod.PlannedStep(action="click", description="do it")],
        )]

    monkeypatch.setattr(agent, "_propose_for_page", fake_propose)

    async def run():
        return await agent.run(
            application_id=5, application_url="https://sit.example.com",
            environment="SIT", excluded_paths=["/admin"], max_pages=5,
        )

    result = anyio.run(run)

    assert result.success is True
    urls = [p["url"] for p in result.data["pages"]]
    assert urls == ["https://sit.example.com", "https://sit.example.com/orders"]
    proposals = result.data["proposed_test_cases"]
    assert len(proposals) == 2
    assert proposals[0]["key"].startswith("P001-")


def test_planner_run_fails_when_environment_not_ready(monkeypatch):
    async def fake_readiness(_inputs):
        return SimpleNamespace(
            ready=False, blockers=[SimpleNamespace(name="app_url", detail="unreachable")]
        )

    monkeypatch.setattr(planner_mod, "check_readiness", fake_readiness)
    agent = PlaywrightPlannerAgent(llm=_FakeLLM("unused"))

    async def run():
        return await agent.run(application_id=5, application_url="https://sit.example.com")

    result = anyio.run(run)
    assert result.success is False
    assert "not ready" in result.error


# ── Service: create_run validation ───────────────────────────────────────────

def test_create_run_rejects_unknown_application():
    db = _FakeDB()

    async def run():
        return await studio_mod.create_run(db, project_id=1, user_id=1, data=_create_payload())

    with pytest.raises(StudioValidationError):
        anyio.run(run)


def test_create_run_rejects_missing_environment_url():
    application = _application(environment_urls={"QA": "https://qa.example.com"})
    db = _FakeDB(get_map={(ProjectApplication, 5): application})

    async def run():
        return await studio_mod.create_run(db, project_id=1, user_id=1, data=_create_payload())

    with pytest.raises(StudioValidationError) as exc:
        anyio.run(run)
    assert "SIT" in str(exc.value)


def test_create_run_snapshots_config():
    db = _FakeDB(get_map={(ProjectApplication, 5): _application()})

    async def run():
        return await studio_mod.create_run(db, project_id=1, user_id=1, data=_create_payload())

    run_row = anyio.run(run)
    assert run_row.status == "draft"
    assert run_row.config["target_url"] == "https://sit.example.com"
    assert run_row.config["application_name"] == "B2B Portal"


# ── Service: start_exploration ───────────────────────────────────────────────

def test_start_exploration_enqueues_planner(monkeypatch):
    captured = {}

    async def fake_enqueue(db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=77), "task-1"

    monkeypatch.setattr(studio_mod, "enqueue_agent_run", fake_enqueue)
    run_row = _studio_run()
    db = _FakeDB()

    async def run():
        return await studio_mod.start_exploration(db, run_row, user_id=1)

    agent_run, task_id = anyio.run(run)
    assert agent_run.id == 77
    assert task_id == "task-1"
    assert run_row.status == "exploring"
    assert run_row.agent_runs["planner"] == 77
    assert captured["agent_name"] == "playwright_planner"
    assert captured["input_data"]["application_url"] == "https://sit.example.com"
    assert captured["input_data"]["studio_run_id"] == run_row.id


def test_start_exploration_rejects_wrong_status():
    run_row = _studio_run(status="generating")

    async def run():
        return await studio_mod.start_exploration(_FakeDB(), run_row, user_id=1)

    with pytest.raises(StudioStateError):
        anyio.run(run)


# ── Service: apply_planner_output ────────────────────────────────────────────

def _planner_output():
    return {
        "explored_page_count": 1,
        "pages": [{
            "url": "https://sit.example.com", "title": "Home",
            "elements": [{"element_name": "button-login"}], "blockers": [],
        }],
        "proposed_test_cases": [
            {"key": "P001-login", "title": "Login", "page_url": "https://sit.example.com",
             "steps": [{"action": "click", "element": "button-login", "value": None,
                        "description": "Click login"}],
             "expected_result": "ok", "priority": "High", "coverage_type": "positive",
             "preconditions": [], "blocked_reasons": [], "ungrounded_elements": []},
            {"key": "P002-otp", "title": "OTP flow", "page_url": "https://sit.example.com",
             "steps": [{"action": "custom", "element": None, "value": None,
                        "description": "Enter OTP"}],
             "expected_result": "ok", "priority": "Medium", "coverage_type": "positive",
             "preconditions": [], "blocked_reasons": ["OTP required"], "ungrounded_elements": []},
        ],
    }


def test_apply_planner_output_advances_to_plan_ready():
    run_row = _studio_run(status="exploring")
    db = _FakeDB(get_map={(StudioRun, run_row.id): run_row})

    async def run():
        await studio_mod.apply_planner_output(
            db, studio_run_id=run_row.id, agent_run=SimpleNamespace(id=77), output=_planner_output()
        )

    anyio.run(run)
    assert run_row.status == "plan_ready"
    assert run_row.plan["explored_page_count"] == 1
    assert len(run_row.plan["proposed_test_cases"]) == 2
    # Page summaries carry counts, not the full element catalog.
    assert run_row.plan["pages"][0]["element_count"] == 1
    assert "elements" not in run_row.plan["pages"][0]


def test_apply_planner_output_dropped_for_terminal_run():
    run_row = _studio_run(status="cancelled")
    db = _FakeDB(get_map={(StudioRun, run_row.id): run_row})

    async def run():
        await studio_mod.apply_planner_output(
            db, studio_run_id=run_row.id, agent_run=SimpleNamespace(id=77), output=_planner_output()
        )

    anyio.run(run)
    assert run_row.status == "cancelled"
    assert run_row.plan is None


# ── Service: approve_plan (bulk gate 1) ──────────────────────────────────────

def test_approve_plan_materializes_and_enqueues_waves(monkeypatch):
    run_row = _studio_run(status="plan_ready", plan=_planner_output())
    db = _FakeDB()
    enqueued = []

    async def fake_payload(db_, *, project_id, test_case_ids):
        return GenerationPayload(
            test_cases=[{"id": tc_id, "test_case_id": f"TC-{tc_id}"} for tc_id in test_case_ids],
            locator_map={5: []},
        )

    async def fake_enqueue(db_, **kwargs):
        enqueued.append(kwargs)
        return SimpleNamespace(id=100 + len(enqueued)), "task"

    monkeypatch.setattr(studio_mod, "build_generation_payload", fake_payload)
    monkeypatch.setattr(studio_mod, "enqueue_agent_run", fake_enqueue)

    async def run():
        return await studio_mod.approve_plan(
            db, run_row, user_id=1, included_keys=None, notes="bulk ok"
        )

    outcome = anyio.run(run)

    # Default selection skips the blocked OTP proposal.
    assert len(outcome["test_case_ids"]) == 1
    test_cases = [o for o in db.added if isinstance(o, TestCase)]
    assert len(test_cases) == 1
    tc = test_cases[0]
    assert tc.status == "approved"
    assert tc.metadata_["origin"] == "playwright_studio"
    assert tc.metadata_["studio_run_id"] == run_row.id
    assert tc.application_id == 5
    assert tc.test_phase == "SIT"
    approvals = [o for o in db.added if isinstance(o, ApprovalAction)]
    assert len(approvals) == 1
    assert run_row.status == "generating"
    assert run_row.agent_runs["generation"] == [101]
    assert enqueued[0]["agent_name"] == "automation_script"
    assert enqueued[0]["input_data"]["studio_run_id"] == run_row.id


def test_approve_plan_explicit_keys_can_include_blocked(monkeypatch):
    run_row = _studio_run(status="plan_ready", plan=_planner_output())
    db = _FakeDB()

    async def fake_payload(db_, *, project_id, test_case_ids):
        return GenerationPayload(test_cases=[{"id": i} for i in test_case_ids])

    async def fake_enqueue(db_, **kwargs):
        return SimpleNamespace(id=200), "task"

    monkeypatch.setattr(studio_mod, "build_generation_payload", fake_payload)
    monkeypatch.setattr(studio_mod, "enqueue_agent_run", fake_enqueue)

    async def run():
        return await studio_mod.approve_plan(
            db, run_row, user_id=1, included_keys=["P002-otp"], notes=None
        )

    outcome = anyio.run(run)
    assert len(outcome["test_case_ids"]) == 1
    tc = [o for o in db.added if isinstance(o, TestCase)][0]
    assert tc.automation_eligible == "no"  # blocked proposal stays flagged
    assert tc.metadata_["blocked_reasons"] == ["OTP required"]


def test_approve_plan_rejects_wrong_status_and_empty_selection():
    async def wrong_status():
        return await studio_mod.approve_plan(
            _FakeDB(), _studio_run(status="draft"), user_id=1, included_keys=None, notes=None
        )

    with pytest.raises(StudioStateError):
        anyio.run(wrong_status)

    async def empty_selection():
        return await studio_mod.approve_plan(
            _FakeDB(), _studio_run(status="plan_ready", plan={"proposed_test_cases": []}),
            user_id=1, included_keys=None, notes=None,
        )

    with pytest.raises(StudioValidationError):
        anyio.run(empty_selection)


# ── Service: approve_scripts (bulk gate 2) ───────────────────────────────────

def _script(**overrides):
    defaults = dict(
        id=1, project_id=1, test_case_id=10, created_by=1, script_id="AS-0001",
        framework="playwright", code="...", status="dry_run_passed", version=1,
    )
    defaults.update(overrides)
    return AutomationScript(**defaults)


def test_approve_scripts_requires_override_note_for_flagged_scripts(monkeypatch):
    run_row = _studio_run(status="scripts_ready", test_case_ids=[10])
    flagged = _script()
    db = _FakeDB(execute_queue=[_ExecResult(many=[flagged])])

    monkeypatch.setattr(
        automation_service, "approval_override_reason",
        lambda script, notes: None if notes else "dry run failed",
    )

    async def run():
        return await studio_mod.approve_scripts(db, run_row, user_id=1, notes=None)

    with pytest.raises(StudioValidationError) as exc:
        anyio.run(run)
    assert "override note" in str(exc.value)
    assert run_row.status == "scripts_ready"


def test_approve_scripts_approves_and_launches_execution(monkeypatch):
    run_row = _studio_run(status="scripts_ready", test_case_ids=[10, 11])
    # Two versions for TC 10 — only the latest (id 3) may be approved/run.
    newer = _script(id=3, test_case_id=10, version=2, script_id="AS-0003")
    older = _script(id=1, test_case_id=10, version=1)
    other = _script(id=2, test_case_id=11, script_id="AS-0002")
    db = _FakeDB(execute_queue=[_ExecResult(many=[newer, older, other])])

    monkeypatch.setattr(automation_service, "approval_override_reason", lambda s, n: None)
    launched = {}

    async def fake_batch(db_, **kwargs):
        launched.update(kwargs)
        return SimpleNamespace(id=501), "task-batch"

    monkeypatch.setattr(studio_mod.automation_execution_service, "start_batch_execution", fake_batch)

    async def run():
        return await studio_mod.approve_scripts(db, run_row, user_id=1, notes="go")

    outcome = anyio.run(run)

    assert sorted(outcome["approved_script_ids"]) == [2, 3]
    assert newer.status == "approved"
    assert older.status == "dry_run_passed"  # superseded version untouched
    assert run_row.status == "executing"
    assert run_row.execution_run_ids == [501]
    assert launched["extra_metadata"]["studio_run_id"] == run_row.id
    assert launched["extra_metadata"]["runner_mode"] == "local"
    approvals = [o for o in db.added if isinstance(o, ApprovalAction)]
    assert len(approvals) == 2


# ── Service: read-time reconciliation ────────────────────────────────────────

def test_reconcile_marks_failed_when_planner_fails():
    run_row = _studio_run(status="exploring", agent_runs={"planner": 77})
    failed_agent = SimpleNamespace(status="failed", error_message="browser crashed")
    db = _FakeDB(get_map={(AgentRun, 77): failed_agent})

    async def run():
        await studio_mod._reconcile_status(db, run_row)

    anyio.run(run)
    assert run_row.status == "failed"
    assert run_row.error == "browser crashed"


def test_reconcile_advances_generating_to_scripts_ready():
    run_row = _studio_run(
        status="generating", test_case_ids=[10],
        agent_runs={"planner": 77, "generation": [78]},
    )
    db = _FakeDB(execute_queue=[
        _ExecResult(many=[SimpleNamespace(status="completed", error_message=None)]),
        _ExecResult(many=[_script(id=3, test_case_id=10)]),
    ])

    async def run():
        await studio_mod._reconcile_status(db, run_row)

    anyio.run(run)
    assert run_row.status == "scripts_ready"


def test_reconcile_completes_executing_run():
    run_row = _studio_run(status="executing", execution_run_ids=[501])
    db = _FakeDB(execute_queue=[
        _ExecResult(many=[SimpleNamespace(status="completed")]),
    ])

    async def run():
        await studio_mod._reconcile_status(db, run_row)

    anyio.run(run)
    assert run_row.status == "completed"


# ── Persistence branch: playwright_planner ──────────────────────────────────

def test_persist_planner_upserts_locators_and_updates_studio_run(monkeypatch):
    run_row = _studio_run(status="exploring")
    db = _FakeDB(get_map={(StudioRun, run_row.id): run_row})
    upserts = []

    async def fake_upsert(db_, **kwargs):
        upserts.append(kwargs)
        return SimpleNamespace(id=len(upserts))

    monkeypatch.setattr(agent_tasks_mod.locator_map_service, "upsert_locator", fake_upsert)

    agent_run = AgentRun(id=77, project_id=1, triggered_by=1, agent_name="playwright_planner")
    output = _planner_output()
    output["pages"][0]["elements"] = [{
        "element_name": "button-login", "role": "button", "accessible_name": "Login",
        "recommended_locator": "page.getByRole('button', { name: 'Login' })",
        "recommended_strategy": "role", "confidence_score": 90,
    }]
    output["application_id"] = 5

    async def run():
        return await agent_tasks_mod._persist_agent_artifacts(
            db, agent_run, "playwright_planner",
            {"studio_run_id": run_row.id, "application_id": 5},
            SimpleNamespace(success=True, data=output),
        )

    persisted = anyio.run(run)

    assert persisted["count"] == 1
    assert persisted["proposed_test_case_count"] == 2
    assert upserts[0]["application_id"] == 5
    assert upserts[0]["element_name"] == "button-login"
    assert run_row.status == "plan_ready"


# ── Endpoints: create + stage guards ─────────────────────────────────────────

RUNS_URL = "/api/v1/playwright-studio/runs"


def test_create_studio_run_endpoint_created():
    db = _FakeDB(
        get_map={(ProjectApplication, 5): _application()},
        execute_queue=[_ExecResult(single=_project())],  # require_permission
    )
    _override(db)
    try:
        response = TestClient(app).post(RUNS_URL, json={
            "project_id": 1, "name": "Nightly SIT", "application_id": 5,
            "environment": "SIT",
        })
    finally:
        _clear()
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["config"]["target_url"] == "https://sit.example.com"


def test_create_studio_run_endpoint_rejects_unconfigured_environment():
    db = _FakeDB(
        get_map={(ProjectApplication, 5): _application(environment_urls={})},
        execute_queue=[_ExecResult(single=_project())],
    )
    _override(db)
    try:
        response = TestClient(app).post(RUNS_URL, json={
            "project_id": 1, "name": "Nightly SIT", "application_id": 5,
            "environment": "SIT",
        })
    finally:
        _clear()
    assert response.status_code == 422
    assert "no URL configured" in response.json()["detail"]


def test_approve_plan_endpoint_conflicts_on_wrong_stage():
    run_row = _studio_run(status="draft")
    db = _FakeDB(
        get_map={(StudioRun, run_row.id): run_row},
        execute_queue=[_ExecResult(single=_project())],
    )
    _override(db)
    try:
        response = TestClient(app).post(
            f"{RUNS_URL}/{run_row.id}/approve-plan", json={"included_keys": None}
        )
    finally:
        _clear()
    assert response.status_code == 409
