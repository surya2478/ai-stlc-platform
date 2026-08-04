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


# ── Planner: deterministic proposal capping ──────────────────────────────────
# Never trust the LLM to self-limit a GLOBAL total across independent
# per-page calls it has no visibility into — enforced here instead.

def _proposal(key, page_url, priority="Medium", title=None):
    return planner_mod.ProposedTestCase(
        key=key, title=title or key, page_url=page_url, priority=priority,
        steps=[planner_mod.PlannedStep(action="custom", description="x")],
    )


def test_cap_proposals_returns_unchanged_when_under_target():
    proposals = [_proposal("a", "/home"), _proposal("b", "/home")]
    assert planner_mod._cap_proposals(proposals, 5) == proposals


def test_cap_proposals_prefers_higher_priority_within_a_page():
    proposals = [
        _proposal("low", "/home", priority="Low"),
        _proposal("high", "/home", priority="High"),
        _proposal("medium", "/home", priority="Medium"),
    ]
    capped = planner_mod._cap_proposals(proposals, 2)
    assert [p.key for p in capped] == ["high", "medium"]


def test_cap_proposals_round_robins_across_pages_for_diversity():
    """A small target must not drain page 1 entirely before touching page 2 —
    exactly the live failure: 10 pages, only the first page's proposals
    would matter if capping just truncated the flat list."""
    proposals = (
        [_proposal(f"home-{i}", "/home", priority="High") for i in range(5)]
        + [_proposal(f"signup-{i}", "/signup", priority="High") for i in range(5)]
        + [_proposal(f"profile-{i}", "/profile", priority="High") for i in range(5)]
    )
    capped = planner_mod._cap_proposals(proposals, 3)
    pages = {p.page_url for p in capped}
    assert pages == {"/home", "/signup", "/profile"}
    assert len(capped) == 3


def test_cap_proposals_exact_count_deterministic_and_reproducible():
    proposals = [_proposal(f"p{i}", "/page", priority="Medium") for i in range(20)]
    first = planner_mod._cap_proposals(proposals, 7)
    second = planner_mod._cap_proposals(proposals, 7)
    assert len(first) == 7
    assert [p.key for p in first] == [p.key for p in second]


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


def test_planner_run_applies_target_test_case_count_end_to_end(monkeypatch, tmp_path):
    """Reproduces the exact live bug: objective said 'generate 5 Test cases'
    but 10 explored pages proposing independently produced 25. With
    target_test_case_count threaded through, the final proposal count must
    match the target regardless of how many pages were explored."""
    site = {
        f"https://sit.example.com/page{i}": _parsed_page(
            f"https://sit.example.com/page{i}", f"Page {i}",
            interactive=[("button", f"Action {i}")],
        )
        for i in range(10)
    }
    site["https://sit.example.com"] = _parsed_page(
        "https://sit.example.com", "Home",
        links=[(f"Page {i}", f"/page{i}") for i in range(10)],
        interactive=[("button", "Home action")],
    )

    async def fake_readiness(_inputs):
        return SimpleNamespace(ready=True, blockers=[])

    monkeypatch.setattr(planner_mod, "check_readiness", fake_readiness)
    monkeypatch.setattr(planner_mod, "workspace_root", lambda: tmp_path)
    monkeypatch.setattr(planner_mod, "MCPSession", _FakeMCPSession)
    monkeypatch.setattr(planner_mod, "parse_snapshot", lambda raw: site[raw])

    agent = PlaywrightPlannerAgent(llm=_FakeLLM("unused"))

    async def fake_propose(page, **_kwargs):
        # Each page proposes independently — 2 each, matching the live
        # planner's real per-page minimum, with zero cross-page awareness.
        return [
            planner_mod.ProposedTestCase(
                title=f"Case {i} for {page['title']}", page_url=page["url"],
                steps=[planner_mod.PlannedStep(action="click", description="do it")],
            )
            for i in range(2)
        ]

    monkeypatch.setattr(agent, "_propose_for_page", fake_propose)

    async def run():
        return await agent.run(
            application_id=5, application_url="https://sit.example.com",
            environment="SIT", max_pages=10, target_test_case_count=5,
        )

    result = anyio.run(run)

    assert result.success is True
    assert result.data["explored_page_count"] == 10
    assert result.data["total_proposed_before_cap"] == 20  # 10 pages x 2 each
    assert len(result.data["proposed_test_cases"]) == 5
    assert result.data["target_test_case_count"] == 5
    # Diversity: 5 selected across pages that independently proposed 20 —
    # must not all come from a single page.
    pages_represented = {tc["page_url"] for tc in result.data["proposed_test_cases"]}
    assert len(pages_represented) > 1


def test_planner_run_ignores_target_when_under_it(monkeypatch, tmp_path):
    """A target larger than what was actually proposed must not force
    fabricating more test cases — it's a ceiling, never a floor."""
    site = {
        "https://sit.example.com": _parsed_page(
            "https://sit.example.com", "Home", interactive=[("button", "Go")],
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
            title="Only case", page_url=page["url"],
            steps=[planner_mod.PlannedStep(action="click", description="do it")],
        )]

    monkeypatch.setattr(agent, "_propose_for_page", fake_propose)

    async def run():
        return await agent.run(
            application_id=5, application_url="https://sit.example.com",
            environment="SIT", max_pages=5, target_test_case_count=50,
        )

    result = anyio.run(run)
    assert len(result.data["proposed_test_cases"]) == 1


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


def test_approve_plan_stores_explored_page_paths_from_every_planner_page(monkeypatch):
    plan = _planner_output()
    # The planner explored two pages; both must be available to ground
    # multi-hop navigation, not just the proposal's own page_url.
    plan["pages"].append({
        "url": "https://sit.example.com/sign-up?role=candidate", "title": "Sign up", "elements": [], "blockers": [],
    })
    run_row = _studio_run(status="plan_ready", plan=plan)
    db = _FakeDB()

    async def fake_payload(db_, *, project_id, test_case_ids):
        return GenerationPayload(test_cases=[{"id": i} for i in test_case_ids])

    async def fake_enqueue(db_, **kwargs):
        return SimpleNamespace(id=400), "task"

    monkeypatch.setattr(studio_mod, "build_generation_payload", fake_payload)
    monkeypatch.setattr(studio_mod, "enqueue_agent_run", fake_enqueue)

    async def run():
        return await studio_mod.approve_plan(db, run_row, user_id=1, included_keys=None, notes=None)

    anyio.run(run)
    tc = [o for o in db.added if isinstance(o, TestCase)][0]
    assert tc.metadata_["explored_page_paths"] == [
        "https://sit.example.com",
        "https://sit.example.com/sign-up?role=candidate",
    ]


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


# ── Route grounding (automation_agent) ──────────────────────────────────────

def _contract(steps):
    from app.agents.automation.generation_contract import AutomationGenerationContract
    return AutomationGenerationContract.model_validate({
        "contractVersion": "1.0", "testCaseId": "TC-1", "testType": "functional",
        "scriptType": "playwright-typescript", "environmentProfile": "SIT",
        "businessFlow": "x", "preconditions": [], "testDataBindings": [],
        "pageObjects": [], "steps": steps, "expectedResults": [], "assertions": [],
        "apiValidations": [], "dbValidations": [], "cleanupActions": [], "evidenceRequired": [],
    })


def test_ground_entry_route_overrides_llm_guessed_route():
    from app.agents.automation.automation_agent import _ground_entry_route

    contract = _contract([
        {"phase": "arrange", "action": "navigate", "value": "/employer/signup"},
        {"phase": "act", "action": "custom", "description": "fill the form"},
    ])
    changed = _ground_entry_route(
        contract, "https://rankix.ai/sign-up?role=employer", "https://rankix.ai"
    )
    assert changed is True
    assert contract.steps[0].value == "/sign-up?role=employer"
    assert contract.steps[0].target is None


def test_ground_entry_route_inserts_navigate_when_missing():
    from app.agents.automation.automation_agent import _ground_entry_route

    contract = _contract([{"phase": "act", "action": "custom", "description": "do something"}])
    changed = _ground_entry_route(contract, "https://rankix.ai/profile", "https://rankix.ai")
    assert changed is True
    assert contract.steps[0].action == "navigate"
    assert contract.steps[0].value == "/profile"


def test_ground_entry_route_skips_cross_host_and_missing_page():
    from app.agents.automation.automation_agent import _ground_entry_route

    contract = _contract([{"phase": "arrange", "action": "navigate", "value": "/keep-me"}])
    assert _ground_entry_route(contract, "https://other-host.com/x", "https://rankix.ai") is False
    assert _ground_entry_route(contract, None, "https://rankix.ai") is False
    assert contract.steps[0].value == "/keep-me"


# ── Hash routes and the entry wait ──────────────────────────────────────────
#
# TC-0105 (project 14) failed four dry runs on a locator that was exactly
# right. The spec opened `/#/`, which resolves against the application's base
# URL `https://rahulshettyacademy.com/seleniumPractise/#/` to the site ROOT —
# a leading slash discards the base path — so the search box it waited for was
# never going to be there. Three repair rounds rewrote the assertion and never
# questioned the address.


def test_a_hash_route_survives_grounding():
    """The fragment is the route on a hash-routed SPA, not decoration."""
    from app.agents.automation.automation_agent import _ground_entry_route

    contract = _contract([{"phase": "arrange", "action": "navigate", "value": "/#/"}])
    changed = _ground_entry_route(
        contract,
        "https://rahulshettyacademy.com/seleniumPractise/#/",
        "https://rahulshettyacademy.com/seleniumPractise/#/",
    )

    assert changed is True
    # Keeps the base path, so `new URL(value, baseURL)` lands on the app
    # rather than on the origin root.
    assert contract.steps[0].value == "/seleniumPractise/#/"


def test_a_deep_hash_route_keeps_its_whole_path():
    from app.agents.automation.automation_agent import _ground_entry_route

    contract = _contract([{"phase": "arrange", "action": "navigate", "value": "/"}])
    _ground_entry_route(
        contract, "https://site.com/client/#/auth/register", "https://site.com"
    )

    assert contract.steps[0].value == "/client/#/auth/register"


def test_a_bare_anchor_is_not_a_route():
    """`#summary` is a position on the page you already asked for."""
    from app.agents.automation.automation_agent import _ground_entry_route

    contract = _contract([{"phase": "arrange", "action": "navigate", "value": "/x"}])
    _ground_entry_route(contract, "https://docs.site.com/guide#summary", "https://docs.site.com")

    assert contract.steps[0].value == "/guide"


def test_the_entry_wait_follows_the_grounded_route():
    """wait_for_url renders as a substring regex, so `#/` passed on the wrong
    page just as happily as on the right one — hiding the real failure."""
    from app.agents.automation.automation_agent import _ground_entry_route

    contract = _contract([
        {"phase": "arrange", "action": "navigate", "value": "/#/"},
        {"phase": "arrange", "action": "wait_for_url", "value": "#/"},
    ])
    changed = _ground_entry_route(
        contract,
        "https://rahulshettyacademy.com/seleniumPractise/#/",
        "https://rahulshettyacademy.com/seleniumPractise/#/",
    )

    assert changed is True
    assert contract.steps[1].value == "/seleniumPractise/#/"


def test_a_second_hop_wait_is_left_alone():
    """Only the step directly after the entry navigate describes the entry
    page. A wait reached after clicking through is a real second hop, grounded
    separately against explored_page_paths."""
    from app.agents.automation.automation_agent import _ground_entry_route

    contract = _contract([
        {"phase": "arrange", "action": "navigate", "value": "/#/"},
        {"phase": "act", "action": "custom", "description": "click through to checkout"},
        {"phase": "assert", "action": "wait_for_url", "value": "#/checkout"},
    ])
    _ground_entry_route(
        contract,
        "https://rahulshettyacademy.com/seleniumPractise/#/",
        "https://rahulshettyacademy.com/seleniumPractise/#/",
    )

    assert contract.steps[0].value == "/seleniumPractise/#/"
    assert contract.steps[2].value == "#/checkout"


def test_grounding_an_already_correct_route_reports_no_change():
    from app.agents.automation.automation_agent import _ground_entry_route

    contract = _contract([{"phase": "arrange", "action": "navigate", "value": "/profile"}])

    assert _ground_entry_route(contract, "https://rankix.ai/profile", "https://rankix.ai") is False


# ── The catalog as a fallback entry page ────────────────────────────────────


def test_a_single_page_catalog_supplies_the_entry_page():
    """`page_url` is written by the Studio planner. TC-0105 never went through
    Studio, so it carried none and the LLM's guess survived — while the
    catalog it grounded every element against named the page all along."""
    from app.services.automation_generation_service import _catalog_entry_page

    entries = [
        {"element_name": "searchbox", "page": "https://rahulshettyacademy.com/seleniumPractise/#/"},
        {"element_name": "cart", "page": "https://rahulshettyacademy.com/seleniumPractise/#/"},
    ]

    assert _catalog_entry_page(entries) == "https://rahulshettyacademy.com/seleniumPractise/#/"


def test_a_multi_page_catalog_names_no_entry_page():
    """Which of them the test *enters* on is exactly the guess route grounding
    exists to prevent."""
    from app.services.automation_generation_service import _catalog_entry_page

    entries = [
        {"element_name": "a", "page": "https://site.com/#/login"},
        {"element_name": "b", "page": "https://site.com/#/dashboard"},
    ]

    assert _catalog_entry_page(entries) is None


def test_an_empty_or_pageless_catalog_names_no_entry_page():
    from app.services.automation_generation_service import _catalog_entry_page

    assert _catalog_entry_page([]) is None
    assert _catalog_entry_page([{"element_name": "a"}, {"element_name": "b", "page": ""}]) is None


def test_approve_plan_prepends_grounded_navigation_step(monkeypatch):
    plan = _planner_output()
    plan["proposed_test_cases"][0]["page_url"] = "https://sit.example.com/sign-up?role=employer"
    run_row = _studio_run(status="plan_ready", plan=plan)
    db = _FakeDB()

    async def fake_payload(db_, *, project_id, test_case_ids):
        return GenerationPayload(test_cases=[{"id": i} for i in test_case_ids])

    async def fake_enqueue(db_, **kwargs):
        return SimpleNamespace(id=300), "task"

    monkeypatch.setattr(studio_mod, "build_generation_payload", fake_payload)
    monkeypatch.setattr(studio_mod, "enqueue_agent_run", fake_enqueue)

    async def run():
        return await studio_mod.approve_plan(db, run_row, user_id=1, included_keys=None, notes=None)

    anyio.run(run)
    tc = [o for o in db.added if isinstance(o, TestCase)][0]
    assert tc.steps[0]["action"] == "Navigate to /sign-up?role=employer"
    assert tc.metadata_["page_url"] == "https://sit.example.com/sign-up?role=employer"
    # Prepending must renumber, not leave two step 1s.
    assert [s["step_number"] for s in tc.steps] == list(range(1, len(tc.steps) + 1))


def test_approved_test_cases_use_the_canonical_step_shape(monkeypatch):
    """Studio used to write {action, expected} — a shape no other producer or
    consumer uses. The planner has no per-step expectation, so that key was
    invented here, and everything downstream looking for `expected_result`
    found nothing: the /test-cases page threw "Cannot read properties of
    undefined (reading 'trim')" on any project holding one (live, project 12).
    """
    run_row = _studio_run(status="plan_ready", plan=_planner_output())
    db = _FakeDB()

    async def fake_payload(db_, *, project_id, test_case_ids):
        return GenerationPayload(test_cases=[{"id": i} for i in test_case_ids])

    async def fake_enqueue(db_, **kwargs):
        return SimpleNamespace(id=301), "task"

    monkeypatch.setattr(studio_mod, "build_generation_payload", fake_payload)
    monkeypatch.setattr(studio_mod, "enqueue_agent_run", fake_enqueue)

    async def run():
        return await studio_mod.approve_plan(db, run_row, user_id=1, included_keys=None, notes=None)

    anyio.run(run)
    for tc in [o for o in db.added if isinstance(o, TestCase)]:
        assert tc.steps, "a materialized test case must carry its planned steps"
        for step in tc.steps:
            assert set(step) == {"step_number", "action", "expected_result"}
            assert isinstance(step["action"], str)
            assert isinstance(step["expected_result"], str)


# ── Failure insights ─────────────────────────────────────────────────────────

def _failed_row(error, name="t", classification=None, stack=""):
    metadata = {"failure_classification": {"classification": classification}} if classification else {}
    return SimpleNamespace(
        error_message=error, stack_trace=stack, test_name=name, metadata_=metadata
    )


def test_failure_insights_bucket_and_rank():
    rows = [
        _failed_row("TimeoutError: locator.fill: Timeout 15000ms exceeded.\nwaiting for getByRole('textbox')", "signup email"),
        _failed_row("TimeoutError: locator.click: Timeout 15000ms exceeded.\nwaiting for getByRole('link', { name: 'Dashboard' })", "menu links"),
        _failed_row("TimeoutError: page.waitForURL: Timeout 30000ms exceeded.", "candidate link"),
        _failed_row("net::ERR_NAME_NOT_RESOLVED at https://sit.example.com", "reset password"),
        _failed_row("some assertion failed", "profile", classification="data_issue"),
    ]
    insights = studio_mod._derive_failure_insights(rows)
    kinds = [i["kind"] for i in insights]
    # error severity first (environment), then warnings, then info.
    assert kinds[0] == "environment_unreachable"
    assert "element_not_found" in kinds
    assert "url_assertion_mismatch" in kinds
    assert "test_data_required" in kinds
    element = next(i for i in insights if i["kind"] == "element_not_found")
    assert element["count"] == 2
    assert "signup email" in element["examples"]
    assert all(i["action"] for i in insights)


def test_failure_insights_empty_for_no_failures():
    assert studio_mod._derive_failure_insights([]) == []


# ── Target test case count: natural-language fallback parsing ───────────────
# Reproduces the exact live bug: objective said "generate 5 Test cases" but
# the run produced 25 — each of 10 explored pages proposed independently
# with no shared awareness of a global target.

def test_parse_target_count_from_objective_matches_real_user_input():
    assert studio_mod._parse_target_count_from_objective(
        "Explore the Rankix application and generate 5 Test cases and perform testing"
    ) == 5


@pytest.mark.parametrize("objective,expected", [
    ("Generate 12 TCs for checkout", 12),
    ("Create 3 tests for login", 3),
    ("only 7 test cases please", 7),
    ("No number here at all", None),
    ("", None),
    (None, None),
])
def test_parse_target_count_from_objective_variants(objective, expected):
    assert studio_mod._parse_target_count_from_objective(objective) == expected


@pytest.mark.parametrize("objective", [
    "Cover at least 5 test cases for checkout",
    "We need a minimum of 10 test cases",
    "Generate more than 3 test cases",
])
def test_parse_target_count_from_objective_ignores_floor_phrasing(objective):
    """'At least N' / 'minimum of N' / 'more than N' state a floor, not a
    ceiling — capping to them would do the opposite of what was asked."""
    assert studio_mod._parse_target_count_from_objective(objective) is None


def test_parse_target_count_from_objective_rejects_out_of_range():
    assert studio_mod._parse_target_count_from_objective("Generate 0 test cases") is None
    assert studio_mod._parse_target_count_from_objective("Generate 500 test cases") is None


# ── create_run: explicit field takes precedence over the fallback ───────────

def test_create_run_prefers_explicit_target_over_objective_parsing():
    db = _FakeDB(get_map={(ProjectApplication, 5): _application()})
    payload = _create_payload(objective="generate 5 test cases", target_test_case_count=10)

    async def run():
        return await studio_mod.create_run(db, project_id=1, user_id=1, data=payload)

    run_row = anyio.run(run)
    assert run_row.config["target_test_case_count"] == 10


def test_create_run_falls_back_to_objective_parsing_when_field_unset():
    db = _FakeDB(get_map={(ProjectApplication, 5): _application()})
    payload = _create_payload(objective="generate 5 test cases")

    async def run():
        return await studio_mod.create_run(db, project_id=1, user_id=1, data=payload)

    run_row = anyio.run(run)
    assert run_row.config["target_test_case_count"] == 5


def test_create_run_target_test_case_count_none_when_unspecified():
    db = _FakeDB(get_map={(ProjectApplication, 5): _application()})
    payload = _create_payload(objective="Explore the order flow")

    async def run():
        return await studio_mod.create_run(db, project_id=1, user_id=1, data=payload)

    run_row = anyio.run(run)
    assert run_row.config["target_test_case_count"] is None


def test_start_exploration_forwards_target_test_case_count(monkeypatch):
    captured = {}

    async def fake_enqueue(db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=77), "task-1"

    monkeypatch.setattr(studio_mod, "enqueue_agent_run", fake_enqueue)
    run_row = _studio_run(config={
        **_studio_run().config, "target_test_case_count": 5,
    })
    db = _FakeDB()

    async def run():
        return await studio_mod.start_exploration(db, run_row, user_id=1)

    anyio.run(run)
    assert captured["input_data"]["target_test_case_count"] == 5


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


# ── retrying a failed run ─────────────────────────────────────────────────────
# A failed run used to be a dead end: the only way on was a new run, which
# re-crawls the application and re-proposes a plan a human already reviewed.
# Observed live 2026-08-03: run 6 failed at generation because the worker was
# restarted mid-flight, with three approved test cases sitting ready to use.

def _retry_stubs(monkeypatch, *, enqueued: list, reuse_id: int | None = None):
    async def _fake_payload(_db, *, project_id, test_case_ids):
        return SimpleNamespace(
            test_cases=[{"id": i, "test_case_id": f"TC-{i}"} for i in test_case_ids],
            locator_map={"5": [{"element_name": "login"}]},
            skipped_not_approved=[],
        )

    async def _fake_enqueue(_db, *, project_id, user_id, agent_name, input_data, metadata=None):
        # Mirrors enqueue_agent_run's real behaviour when reuse_id is given: a
        # failed run is requeued in place and comes back with its own id.
        run = SimpleNamespace(id=reuse_id if reuse_id is not None else 900 + len(enqueued))
        enqueued.append({"agent_name": agent_name, "input": input_data, "metadata": metadata})
        return run, f"task-{run.id}"

    monkeypatch.setattr(studio_mod, "build_generation_payload", _fake_payload)
    monkeypatch.setattr(studio_mod, "enqueue_agent_run", _fake_enqueue)


def test_retry_resumes_generation_and_keeps_the_approved_plan(monkeypatch):
    enqueued: list = []
    _retry_stubs(monkeypatch, enqueued=enqueued)
    run = _studio_run(
        status="failed", error="Script generation produced no scripts",
        test_case_ids=[75, 76, 77],
        agent_runs={"planner": 283, "generation": [284]},
    )
    db = _FakeDB()

    outcome = anyio.run(lambda: studio_mod.retry_run(db, run, 7))

    assert outcome["stage"] == "generation"
    assert outcome["test_case_count"] == 3
    assert run.status == "generating"
    assert run.error is None
    # The plan and its materialized test cases survive — no re-crawl, no
    # duplicate test cases.
    assert run.test_case_ids == [75, 76, 77]
    assert enqueued[0]["agent_name"] == "automation_script"
    assert [tc["id"] for tc in enqueued[0]["input"]["test_cases"]] == [75, 76, 77]


def test_retry_sets_generation_ids_to_exactly_what_was_enqueued(monkeypatch):
    """_reconcile_status waits for every id in agent_runs["generation"] to be
    terminal, so the list must be REPLACED, never appended to — a leftover
    failed id would re-fail the run on the next read and undo the retry.

    Note the id can legitimately be the same one: enqueue_agent_run reuses a
    failed run's row in place (status back to pending) rather than inserting a
    new row, which is why this asserts "exactly what was enqueued" rather than
    "a different id".
    """
    enqueued: list = []
    _retry_stubs(monkeypatch, enqueued=enqueued, reuse_id=284)
    run = _studio_run(status="failed", test_case_ids=[75],
                      agent_runs={"planner": 283, "generation": [284, 999]})

    anyio.run(lambda: studio_mod.retry_run(_FakeDB(), run, 7))

    # 999 was from the failed attempt and is gone; the list is not appended to.
    assert run.agent_runs["generation"] == [284]
    assert run.agent_runs["planner"] == 283  # untouched


def test_retry_without_approved_test_cases_restarts_exploration(monkeypatch):
    """The planner failed before producing anything approvable, so there is no
    plan worth keeping."""
    enqueued: list = []
    _retry_stubs(monkeypatch, enqueued=enqueued)
    run = _studio_run(status="failed", error="Planner agent failed", test_case_ids=None,
                      agent_runs={"planner": 283})

    outcome = anyio.run(lambda: studio_mod.retry_run(_FakeDB(), run, 7))

    assert outcome["stage"] == "exploration"
    assert run.status == "exploring"
    assert run.error is None
    assert enqueued[0]["agent_name"] == "playwright_planner"


def test_retry_is_refused_on_a_run_that_did_not_fail(monkeypatch):
    """"completed" is deliberately absent: a completed run whose tests failed
    IS retryable — that case has its own tests."""
    enqueued: list = []
    _retry_stubs(monkeypatch, enqueued=enqueued)

    async def _no_failures(_db, _run):
        return []

    monkeypatch.setattr(studio_mod, "failed_test_case_ids", _no_failures)
    for status in ("generating", "draft", "scripts_ready"):
        run = _studio_run(status=status, test_case_ids=[75])
        with pytest.raises(StudioStateError):
            anyio.run(lambda r=run: studio_mod.retry_run(_FakeDB(), r, 7))
    assert enqueued == []


def test_retry_refuses_when_the_test_cases_are_no_longer_generatable(monkeypatch):
    """build_generation_payload drops anything not approved; retrying into an
    empty payload would silently move the run to "generating" forever."""
    async def _empty_payload(_db, *, project_id, test_case_ids):
        return SimpleNamespace(test_cases=[], locator_map={}, skipped_not_approved=list(test_case_ids))

    monkeypatch.setattr(studio_mod, "build_generation_payload", _empty_payload)
    run = _studio_run(status="failed", test_case_ids=[75, 76])

    with pytest.raises(StudioValidationError):
        anyio.run(lambda: studio_mod.retry_run(_FakeDB(), run, 7))
    assert run.status == "failed"  # unchanged


# ── retrying a failed EXECUTION ───────────────────────────────────────────────
# The case with no way forward at all: _reconcile_status marks a run
# "completed" once every ExecutionRun is terminal, pass or fail alike. So a run
# whose five tests all failed on infrastructure reported "completed", carried no
# error text, and offered nothing to click. Observed live 2026-08-03.

def _exec_run(run_id: int, status: str):
    return SimpleNamespace(id=run_id, status=status)


def _exec_retry_stubs(monkeypatch, *, scripts, exec_runs, started: list):
    async def _fake_latest(_db, _run):
        return scripts

    async def _fake_start(_db, *, project_id, user_id, script_ids, environment,
                          timeout_seconds, run_name, extra_metadata):
        started.append({"script_ids": list(script_ids), "metadata": extra_metadata})
        return SimpleNamespace(id=900 + len(started)), f"task-{len(started)}"

    monkeypatch.setattr(studio_mod, "_latest_scripts_for_run", _fake_latest)
    monkeypatch.setattr(
        studio_mod.automation_execution_service, "start_batch_execution", _fake_start
    )
    db = _FakeDB(execute_queue=[_ExecResult(many=exec_runs), _ExecResult(many=exec_runs)])
    return db


def test_a_completed_run_whose_execution_failed_can_be_retried(monkeypatch):
    started: list = []
    scripts = [SimpleNamespace(id=61, status="approved"), SimpleNamespace(id=62, status="approved")]
    db = _exec_retry_stubs(monkeypatch, scripts=scripts, exec_runs=[_exec_run(63, "failed")], started=started)
    run = _studio_run(status="completed", execution_run_ids=[63], test_case_ids=[84, 85])

    outcome = anyio.run(lambda: studio_mod.retry_run(db, run, 7))

    assert outcome["stage"] == "execution"
    assert outcome["test_case_count"] == 2
    assert run.status == "executing"
    # The failed execution id is replaced, not appended — _reconcile_status
    # would otherwise settle the run again on the next read.
    assert run.execution_run_ids == [901]
    assert started[0]["script_ids"] == [61, 62]


def test_execution_retry_can_switch_the_runner_mode(monkeypatch):
    """The commonest wholesale execution failure is a mode this deployment is
    not wired for — repeating it would reproduce the same failure."""
    started: list = []
    db = _exec_retry_stubs(
        monkeypatch, scripts=[SimpleNamespace(id=61, status="approved")],
        exec_runs=[_exec_run(63, "failed")], started=started,
    )
    run = _studio_run(status="completed", execution_run_ids=[63], test_case_ids=[84])
    run.config = {**run.config, "runner_mode": "docker"}

    anyio.run(lambda: studio_mod.retry_run(db, run, 7, runner_mode="executor"))

    assert started[0]["metadata"]["runner_mode"] == "executor"
    # Persisted, so the audit shows what was actually run.
    assert run.config["runner_mode"] == "executor"


def test_a_completed_run_whose_execution_passed_offers_no_retry(monkeypatch):
    """Nothing failed — neither the ExecutionRun nor any individual test — so
    there is nothing to retry."""
    started: list = []
    db = _exec_retry_stubs(
        monkeypatch, scripts=[], exec_runs=[_exec_run(63, "completed")], started=started,
    )
    # No failed results and no failed dry runs.
    db.execute_queue = [_ExecResult(many=[_exec_run(63, "completed")]), _ExecResult(many=[])]
    run = _studio_run(status="completed", execution_run_ids=[63], test_case_ids=[84])

    assert anyio.run(lambda: studio_mod.can_retry(db, run)) is False


def test_execution_retry_refuses_when_no_script_is_approved(monkeypatch):
    """Re-executing nothing would move the run to "executing" and strand it."""
    started: list = []
    db = _exec_retry_stubs(
        monkeypatch, scripts=[SimpleNamespace(id=61, status="draft")],
        exec_runs=[_exec_run(63, "failed")], started=started,
    )
    run = _studio_run(status="completed", execution_run_ids=[63], test_case_ids=[84])

    with pytest.raises(StudioValidationError):
        anyio.run(lambda: studio_mod.retry_run(db, run, 7))
    assert run.status == "completed"


# ── regenerating only what failed ─────────────────────────────────────────────
# The diagnostics name specific test cases. Re-running the whole wave to fix two
# of them spends model time on scripts that already work and replaces them with
# different ones for no reason.

def test_failed_test_case_ids_combines_execution_and_dry_run_signals(monkeypatch):
    """A script can fail before it ever reaches an execution, so the dry run
    counts too."""
    scripts = [
        SimpleNamespace(id=61, test_case_id=85, metadata_={"last_dry_run": {"passed": False}}),
        SimpleNamespace(id=60, test_case_id=84, metadata_={"last_dry_run": {"passed": True}}),
        SimpleNamespace(id=64, test_case_id=88, metadata_={}),
    ]

    async def _fake_latest(_db, _run):
        return scripts

    monkeypatch.setattr(studio_mod, "_latest_scripts_for_run", _fake_latest)
    run = _studio_run(status="completed", test_case_ids=[84, 85, 86, 87, 88], execution_run_ids=[63])
    db = _FakeDB(execute_queue=[_ExecResult(many=[87])])  # execution failure for 87

    ids = anyio.run(lambda: studio_mod.failed_test_case_ids(db, run))

    # 85 from the dry run, 87 from the execution — and in the run's own order.
    assert ids == [85, 87]


def test_regenerating_only_failed_enqueues_just_those(monkeypatch):
    enqueued: list = []
    _retry_stubs(monkeypatch, enqueued=enqueued)

    async def _fake_failed(_db, _run):
        return [85, 87]

    monkeypatch.setattr(studio_mod, "failed_test_case_ids", _fake_failed)
    monkeypatch.setattr(studio_mod, "can_retry", lambda _db, _run: _true())
    run = _studio_run(status="completed", test_case_ids=[84, 85, 86, 87, 88], execution_run_ids=[63])

    outcome = anyio.run(lambda: studio_mod.retry_run(_FakeDB(), run, 7, only_failed=True))

    assert outcome["stage"] == "generation"
    assert outcome["partial"] is True
    assert outcome["test_case_count"] == 2
    assert [tc["id"] for tc in enqueued[0]["input"]["test_cases"]] == [85, 87]
    assert enqueued[0]["metadata"]["partial_regeneration"] is True


def test_regenerating_only_failed_refuses_when_nothing_failed(monkeypatch):
    """Silently regenerating everything, or nothing, would both be wrong."""
    enqueued: list = []
    _retry_stubs(monkeypatch, enqueued=enqueued)

    async def _none(_db, _run):
        return []

    monkeypatch.setattr(studio_mod, "failed_test_case_ids", _none)
    monkeypatch.setattr(studio_mod, "can_retry", lambda _db, _run: _true())
    run = _studio_run(status="completed", test_case_ids=[84], execution_run_ids=[63])

    with pytest.raises(StudioValidationError):
        anyio.run(lambda: studio_mod.retry_run(_FakeDB(), run, 7, only_failed=True))
    assert enqueued == []


async def _true():
    return True


# ── failure insights must name the right fault ────────────────────────────────
# "environment_issue" from the failure-classification agent is a coarse bucket:
# it covers both "the application URL cannot be reached" and "the runner itself
# is broken". Mapping it straight to the first told a user their app was
# unreachable — and sent them to check DNS, proxy and VPN — when the real error
# said "docker daemon not reachable — is /var/run/docker.sock mounted into this
# container?". Observed live 2026-08-03 across five tests.

_SOCKET_ERROR = (
    "docker daemon not reachable — is /var/run/docker.sock mounted into this container? "
    "(dial unix /var/run/docker.sock: connect: no such file or directory)"
)
_DNS_ERROR = "page.goto: net::ERR_NAME_NOT_RESOLVED at https://app.internal/"


def _insight_row(error: str, classification: str | None = None, test_name: str = "t"):
    return SimpleNamespace(
        error_message=error,
        stack_trace=None,
        test_name=test_name,
        metadata_={"failure_classification": {"classification": classification}} if classification else {},
    )


def test_a_runner_socket_failure_is_not_reported_as_an_unreachable_application():
    insights = studio_mod._derive_failure_insights([_insight_row(_SOCKET_ERROR, "environment_issue")])

    assert [i["kind"] for i in insights] == ["runner_infrastructure"]
    assert "docker" in insights[0]["action"].lower() or "worker" in insights[0]["action"].lower()


def test_a_genuine_dns_failure_is_still_reported_as_unreachable():
    """Narrowing must not break the case the rule was written for."""
    insights = studio_mod._derive_failure_insights([_insight_row(_DNS_ERROR, "environment_issue")])

    assert [i["kind"] for i in insights] == ["environment_unreachable"]


def test_an_environment_verdict_with_no_matching_text_keeps_the_generic_message():
    """The agent's verdict is still honoured when the text evidences nothing
    more specific."""
    insights = studio_mod._derive_failure_insights(
        [_insight_row("the run did not produce output", "environment_issue")]
    )

    assert [i["kind"] for i in insights] == ["environment_unreachable"]


def test_an_environment_verdict_cannot_be_talked_into_a_non_environment_insight():
    """Only the environment/infrastructure rules are consulted, so a
    classifier that says 'environment' never reports a missing element."""
    insights = studio_mod._derive_failure_insights(
        [_insight_row("locator resolved to 0 elements for getByRole('button')", "environment_issue")]
    )

    assert insights[0]["kind"] in studio_mod._ENVIRONMENTAL_INSIGHT_KINDS


def test_an_unclassified_socket_failure_still_matches_by_text():
    """No classifier verdict at all — the text patterns alone must get it
    right, which they always did."""
    insights = studio_mod._derive_failure_insights([_insight_row(_SOCKET_ERROR)])

    assert [i["kind"] for i in insights] == ["runner_infrastructure"]
