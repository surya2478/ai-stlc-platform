"""UI-016 Application Model service — Phase 1.

Uses the same queued-response fake DB pattern as
test_async_agent_workflow.py's `_AgentDB`: `execute()` pops pre-programmed
responses in the exact order the service issues them, `get()` similarly
pops from its own queue. The node-building loop itself only calls
add()/flush() (no execute()), so only two execute() calls need queuing for
a first build: the actions fetch, then get_current_model's (empty) lookup.
"""
from types import SimpleNamespace

import anyio
import pytest

from app.models.application_model import (
    ApplicationModel,
    ApplicationModelGap,
    ApplicationModelLocatorEvidence,
    ApplicationModelNode,
)
from app.services import application_model_service as svc


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)

    def first(self):
        return self._values[0] if self._values else None


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarsResult(self._values)

    def scalar_one(self):
        # Emptiness checks queue a bare count rather than a row list.
        return self._values if isinstance(self._values, int) else len(self._values)

    def all(self):
        # The emptiness check counts screens and elements in one grouped query,
        # so it reads (node_type, count) rows rather than a single scalar.
        return list(self._values)


class _FakeDB:
    def __init__(self, *, get_queue=None, execute_queue=None):
        self.get_queue = list(get_queue or [])
        self.execute_queue = list(execute_queue or [])
        self.added = []
        self.deleted = []
        self.next_id = 1

    async def get(self, _model, _id):
        return self.get_queue.pop(0) if self.get_queue else None

    async def execute(self, _stmt):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self.next_id
            self.next_id += 1
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, _obj, attribute_names=None):
        return None


def _action(**overrides):
    base = dict(
        id=None, session_id=1, project_id=1, sequence=0, actor="user", action_family="click",
        target_semantic=None, target_screen_ref=None, target_component_ref=None, target_element_ref=None,
        locator_evidence=None, locator_confidence=None,
        # Set only when capture_service degraded the action because it could
        # not resolve the element the step named; NULL on every other action.
        intended_action_family=None, issue_note=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _ranking(*, locator="#submit", strategy="css", element_name="button_submit",
             page_url="https://shop.example.com/checkout", role="button"):
    """A DiscoveryAction.locator_evidence payload in its real shape.

    This is what `locator_ranking.rank_and_validate` returns — the locator
    lives inside `candidates`, not at the top level. Tests used to pass
    `{"value": …, "type": …}`, which no producer ever writes, and that fiction
    is why the builder's own `.get("value")` read looked correct.
    """
    return {
        "element_name": element_name,
        "role": role,
        "page_url": page_url,
        "candidates": [
            {"strategy": strategy, "value": locator, "locator": locator, "confidence": 95},
            {"strategy": "text", "value": "Submit", "locator": "text=Submit", "confidence": 60},
        ],
    }


def _application(project_id=1, app_id=1):
    return SimpleNamespace(id=app_id, project_id=project_id)


def _session(session_id=1, project_id=1, app_id=1, status="COMPLETED", test_case_id=None):
    """A completed discovery session.

    `test_case_id` defaults to None — an ad-hoc session, which contributes to
    the build on its own. `contributing_sessions` collapses sessions that name
    the SAME test case down to the newest one, so tests that care about
    accumulation across test cases must set this explicitly.
    """
    return SimpleNamespace(
        id=session_id, project_id=project_id, application_id=app_id,
        status=status, test_case_id=test_case_id,
    )


def test_build_draft_creates_screens_components_elements_and_gaps():
    actions = [
        _action(id=1, sequence=1, action_family="navigate", target_screen_ref="SCR-LOGIN"),
        _action(
            id=2, sequence=2, action_family="click", target_screen_ref="SCR-LOGIN",
            target_component_ref="CMP-LOGINFORM", target_element_ref="ELM-SUBMIT",
            locator_evidence=_ranking(locator="#submit", strategy="css"), locator_confidence=95,
        ),
        _action(id=3, sequence=3, action_family="navigate", target_screen_ref="SCR-DASHBOARD"),
        _action(id=4, sequence=4, action_family="click", target_component_ref="CMP-WIDGET"),
        _action(id=5, sequence=5, action_family="click", target_screen_ref="SCR-DASHBOARD"),
    ]
    db = _FakeDB(
        get_queue=[_application(), _session()],
        # contributing-sessions lookup, actions fetch, then get_current_model() -> no head
        execute_queue=[[_session()], actions, []],
    )

    model = anyio.run(
        lambda: svc.build_or_rebuild_draft(db, project_id=1, application_id=1, session_id=1, actor_id=10)
    )

    assert model.status == "draft"
    assert model.version == 1
    assert model.built_by == 10
    assert model.built_from_action_count == 5

    nodes = [obj for obj in db.added if isinstance(obj, ApplicationModelNode)]
    screens = [n for n in nodes if n.node_type == "screen"]
    components = [n for n in nodes if n.node_type == "component"]
    elements = [n for n in nodes if n.node_type == "element"]
    assert {n.external_ref for n in screens} == {"SCR-LOGIN", "SCR-DASHBOARD"}
    assert {n.external_ref for n in components} == {"CMP-LOGINFORM", "CMP-WIDGET"}
    assert {n.external_ref for n in elements} == {"ELM-SUBMIT"}

    gaps = [obj for obj in db.added if isinstance(obj, ApplicationModelGap)]
    gap_types = [g.gap_type for g in gaps]
    assert "MISSING_SCREEN" in gap_types  # action 4 (component ref, no screen ref)
    assert "MISSING_ELEMENT" in gap_types  # action 5 (click with no element ref)
    assert all(g.severity == "critical" for g in gaps if g.gap_type in ("MISSING_SCREEN", "MISSING_ELEMENT"))
    # action 2's locator confidence (95) is well above the low-confidence
    # threshold, so it must not raise an UNSTABLE_LOCATOR gap.
    assert "UNSTABLE_LOCATOR" not in gap_types


def test_approve_blocked_by_open_critical_gap():
    model = SimpleNamespace(id=1, status="pending_review", built_by=10, project_id=1, application_id=1)
    db = _FakeDB(execute_queue=[[SimpleNamespace(id=99, severity="critical", status="open")]])

    async def run():
        return await svc.approve(db, model, actor_id=20, reason=None)

    try:
        anyio.run(run)
        assert False, "expected approval to be blocked by the open critical gap"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 409
        assert exc.detail["code"] == "CRITICAL_GAP_OPEN"


def test_approve_refuses_when_builder_is_approver(monkeypatch):
    # Pins the policy rather than inheriting it: separation of duty is now
    # configurable, and a developer machine with it switched off would
    # otherwise make this pass or fail on local config instead of on the code.
    _with_policy(monkeypatch, required=True)
    model = SimpleNamespace(id=1, status="pending_review", built_by=10, project_id=1, application_id=1)
    db = _FakeDB()

    async def run():
        return await svc.approve(db, model, actor_id=10, reason=None)

    try:
        anyio.run(run)
        assert False, "expected separation-of-duty violation"
    except Exception as exc:
        assert exc.status_code == 409
        assert exc.detail["code"] == "SEPARATION_OF_DUTY_VIOLATION"


def test_approve_succeeds_with_no_open_critical_gaps():
    model = SimpleNamespace(
        id=1, status="pending_review", built_by=10, project_id=1, application_id=1,
        approved_by=None, approved_at=None, decision_reason=None, correlation_id=None,
    )
    db = _FakeDB(execute_queue=[[], [("screen", 2), ("element", 5)]])  # no critical gaps; 2 screens, 5 elements

    result = anyio.run(lambda: svc.approve(db, model, actor_id=20, reason="looks good"))

    assert result.status == "approved"
    assert result.approved_by == 20


def test_publish_requires_approved_state():
    model = SimpleNamespace(id=1, status="draft", project_id=1, application_id=1)
    db = _FakeDB()

    try:
        anyio.run(lambda: svc.publish(db, model, actor_id=20))
        assert False, "expected publish to be refused from draft state"
    except Exception as exc:
        assert exc.status_code == 409
        assert exc.detail["code"] == "INVALID_TRANSITION"


def test_immutable_model_refuses_node_rename():
    model = SimpleNamespace(id=1, status="published", project_id=1, application_id=1, version=3)
    db = _FakeDB()

    try:
        anyio.run(lambda: svc.rename_node(db, model, node_id=1, display_name="New Name", actor_id=10))
        assert False, "expected a published model to refuse further node edits"
    except Exception as exc:
        assert exc.status_code == 409
        assert exc.detail["code"] == "MODEL_IMMUTABLE"


def test_create_new_draft_from_published_bumps_version_and_chains_parent():
    model = SimpleNamespace(
        id=7, status="published", project_id=1, application_id=1, source_session_id=3, version=2,
        is_current=True,
    )
    db = _FakeDB()

    new_model = anyio.run(lambda: svc.create_new_draft(db, model, actor_id=15))

    assert model.is_current is False
    assert new_model.status == "draft"
    assert new_model.version == 3
    assert new_model.parent_model_id == 7
    assert new_model.built_by == 15


# ── Empty models ────────────────────────────────────────────────────────────
#
# Found on a real session: a completed discovery run whose actions carried no
# screen/component/element references built a model with 0 screens, 0 elements
# and 0 gaps — which passed every governance row and was approvable. Each row
# is phrased as the absence of a gap ("no missing screens", "no unresolved
# critical blocker"), so discovering nothing satisfied all of them at once.
#
# The build now raises the missing structure as a critical gap, which is what
# approve() and publish() already refuse on. No new vocabulary, and the checks
# that exist start telling the truth.


def _build(actions):
    db = _FakeDB(
        get_queue=[_application(), _session()],
        execute_queue=[[_session()], actions, []],
    )
    anyio.run(lambda: svc.build_or_rebuild_draft(
        db, project_id=1, application_id=1, session_id=1, actor_id=10,
    ))
    return db


def _gaps(db):
    return [o for o in db.added if isinstance(o, ApplicationModelGap)]


def test_a_session_that_identified_no_screen_is_a_critical_gap():
    """The regression: this built a clean, empty, approvable model."""
    db = _build([_action(id=1, sequence=1, action_family="read", target_semantic="Click the 'Home' link")])

    missing_screen = [g for g in _gaps(db) if g.gap_type == "MISSING_SCREEN"]
    assert len(missing_screen) == 1
    assert missing_screen[0].severity == "critical"
    assert missing_screen[0].status == "open"


def test_the_gap_says_what_to_do_about_it():
    """A blocker a user cannot act on is only marginally better than a silent
    pass — it has to name the cause and the remedy."""
    db = _build([_action(id=1, sequence=1, action_family="read")])

    gap = next(g for g in _gaps(db) if g.gap_type == "MISSING_SCREEN")
    assert "no action in the source session identified a screen" in gap.evidence["reason"]
    assert gap.evidence["actions_walked"] == 1
    assert "rebuild" in gap.remediation.lower()


def test_a_session_with_no_actions_at_all_is_also_blocked():
    """Zero actions and zero useful actions are the same failure to a user."""
    db = _build([])

    assert any(g.gap_type == "MISSING_SCREEN" and g.severity == "critical" for g in _gaps(db))


def test_a_model_that_found_a_screen_raises_no_emptiness_gap():
    """Guards against the opposite error — flagging healthy models."""
    db = _build([_action(id=1, sequence=1, action_family="navigate", target_screen_ref="SCR-HOME")])

    screens = [n for n in db.added if isinstance(n, ApplicationModelNode) and n.node_type == "screen"]
    assert len(screens) == 1
    # The only MISSING_SCREEN gap the builder raises otherwise is the
    # per-action one, which needs a component/element ref without a screen.
    assert not [g for g in _gaps(db) if g.gap_type == "MISSING_SCREEN"]


def test_an_action_referencing_a_component_without_a_screen_still_reports_per_action():
    """The pre-existing per-action MISSING_SCREEN must not be swallowed by the
    new whole-model one, and must not be double-counted either."""
    db = _build([_action(id=1, sequence=1, action_family="click", target_component_ref="CMP-NAV")])

    missing_screen = [g for g in _gaps(db) if g.gap_type == "MISSING_SCREEN"]
    # One for the orphaned action, one for the model having no screen at all.
    assert len(missing_screen) == 2
    assert all(g.severity == "critical" for g in missing_screen)


# ── Separation of duty as a policy, not a constant ──────────────────────────
#
# Requiring a second approver is right where there is a second person. On a
# single-operator deployment it blocks every model permanently and adds no
# assurance, so it is configurable — but on by default, because an approval a
# builder can grant themselves records a review that did not happen.


def _pending(built_by=10):
    return SimpleNamespace(
        id=1, status="pending_review", built_by=built_by, project_id=1, application_id=1,
        approved_by=None, approved_at=None, decision_reason=None, correlation_id=None,
    )


def _with_policy(monkeypatch, *, required: bool):
    from app.config import Settings

    base = svc.get_settings()
    patched = Settings(
        app_secret_key="test-secret-key-with-sufficient-length-1234",
        require_separate_approver=required,
        database_url=base.database_url,
    )
    monkeypatch.setattr(svc, "get_settings", lambda: patched)


def test_separate_approver_is_required_by_default():
    """The safe default has to survive: nobody should have to opt in to it."""
    from app.config import Settings

    assert Settings.model_fields["require_separate_approver"].default is True


def test_a_builder_can_approve_when_the_policy_is_relaxed(monkeypatch):
    _with_policy(monkeypatch, required=False)
    model = _pending(built_by=10)
    db = _FakeDB(execute_queue=[[], [("screen", 2), ("element", 5)]])  # no critical gaps; 2 screens, 5 elements

    approved = anyio.run(lambda: svc.approve(db, model, actor_id=10, reason="single operator"))

    assert approved.status == "approved"
    # Still recorded — relaxing who may approve never means not recording who did.
    assert approved.approved_by == 10


def test_relaxing_the_policy_does_not_relax_the_gap_check(monkeypatch):
    """The two controls are independent: a self-approval of a model with an
    open critical gap must still be refused."""
    _with_policy(monkeypatch, required=False)
    model = _pending(built_by=10)
    db = _FakeDB(execute_queue=[[ApplicationModelGap(model_id=1, gap_type="MISSING_SCREEN", severity="critical", status="open")]])

    try:
        anyio.run(lambda: svc.approve(db, model, actor_id=10, reason=None))
        assert False, "expected the critical-gap check to still apply"
    except Exception as exc:
        assert exc.detail["code"] == "CRITICAL_GAP_OPEN"


def test_relaxing_the_policy_does_not_allow_approving_the_wrong_state(monkeypatch):
    _with_policy(monkeypatch, required=False)
    model = SimpleNamespace(id=1, status="draft", built_by=10, project_id=1, application_id=1)

    try:
        anyio.run(lambda: svc.approve(db=_FakeDB(), model=model, actor_id=10, reason=None))
        assert False, "expected an invalid-transition refusal"
    except Exception as exc:
        assert exc.detail["code"] == "INVALID_TRANSITION"


def test_the_refusal_says_how_to_relax_it(monkeypatch):
    """A blocker with no stated way forward is what sent a user hunting through
    the codebase for the rule."""
    _with_policy(monkeypatch, required=True)

    try:
        anyio.run(lambda: svc.approve(_FakeDB(), _pending(built_by=10), actor_id=10, reason=None))
        assert False, "expected separation-of-duty violation"
    except Exception as exc:
        assert "REQUIRE_SEPARATE_APPROVER" in exc.detail["message"]


# ── an empty model is not an approvable model ─────────────────────────────────
# Every governance check downstream is phrased as the absence of a gap, so a
# model containing nothing satisfied all of them vacuously. Observed live: an
# empty v2 was approved and published over a v1 that had two screens.

def test_approve_refuses_a_model_with_no_screens():
    model = SimpleNamespace(
        id=1, status="pending_review", built_by=10, project_id=1, application_id=1,
        approved_by=None, approved_at=None, decision_reason=None, correlation_id=None,
    )
    db = _FakeDB(execute_queue=[[], []])  # no critical gaps, and no nodes at all

    with pytest.raises(svc.ApplicationModelError) as exc:
        anyio.run(lambda: svc.approve(db, model, actor_id=20, reason="looks good"))

    assert exc.value.detail["code"] == "MODEL_EMPTY"
    assert "nothing to ground tests against" in exc.value.detail["message"]
    assert model.status == "pending_review"  # unchanged


def test_publish_refuses_a_model_with_no_screens():
    model = SimpleNamespace(
        id=1, status="approved", project_id=1, application_id=1,
        published_by=None, published_at=None, correlation_id=None,
    )
    db = _FakeDB(execute_queue=[[], []])

    with pytest.raises(svc.ApplicationModelError) as exc:
        anyio.run(lambda: svc.publish(db, model, actor_id=20))

    assert exc.value.detail["code"] == "MODEL_EMPTY"
    assert model.status == "approved"  # never superseded the prior published model


def test_publish_allows_a_model_that_has_screens():
    model = SimpleNamespace(
        id=1, status="approved", project_id=1, application_id=1,
        published_by=None, published_at=None, correlation_id=None,
    )
    db = _FakeDB(execute_queue=[[], [("screen", 3), ("element", 7)], []])  # no gaps; 3 screens, 7 elements; no prior published

    result = anyio.run(lambda: svc.publish(db, model, actor_id=20))

    assert result.status == "published"


def test_a_new_draft_starts_blocked_because_it_copies_nothing():
    """create_new_draft writes a model row with no nodes and runs no walk.
    Without a gap saying so, that emptiness was invisible to every downstream
    check — which is the exact path the empty published v2 took."""
    model = SimpleNamespace(
        id=7, status="published", project_id=1, application_id=1, source_session_id=3, version=2,
        is_current=True,
    )
    db = _FakeDB()

    new_model = anyio.run(lambda: svc.create_new_draft(db, model, actor_id=15))

    gaps = [o for o in db.added if isinstance(o, ApplicationModelGap)]
    assert len(gaps) == 1
    assert gaps[0].gap_type == "MISSING_SCREEN"
    assert gaps[0].severity == "critical"
    assert gaps[0].status == "open"
    assert gaps[0].model_id == new_model.id
    assert "Rebuild it from a completed discovery session" in gaps[0].remediation


# --- The model as a locator source -----------------------------------------
#
# Everything below exists because the model was built as a structural record
# only: it knew an element existed and how confident discovery was, but never
# recorded what to click. Grounding generation on a published model is only
# meaningful if these hold.


def _build_one_element(action_overrides=None):
    actions = [
        _action(id=1, sequence=1, action_family="navigate", target_screen_ref="SCR-CHECKOUT"),
        _action(
            id=2, sequence=2, action_family="click", target_screen_ref="SCR-CHECKOUT",
            target_component_ref="CMP-FORM", target_element_ref="ELM-SUBMIT",
            target_semantic="Click the Submit button",
            locator_confidence=95, **(action_overrides or {"locator_evidence": _ranking()}),
        ),
    ]
    db = _FakeDB(get_queue=[_application(), _session()], execute_queue=[[_session()], actions, []])
    anyio.run(
        lambda: svc.build_or_rebuild_draft(db, project_id=1, application_id=1, session_id=1, actor_id=10)
    )
    return db


def test_element_evidence_records_the_top_ranked_locator():
    db = _build_one_element()
    evidence = [obj for obj in db.added if isinstance(obj, ApplicationModelLocatorEvidence)]
    assert len(evidence) == 1
    # The best-ranked candidate, not the second one and not None.
    assert evidence[0].locator_value == "#submit"
    assert evidence[0].locator_type == "css"
    assert evidence[0].confidence == 95


def test_element_carries_the_name_and_page_a_catalog_needs():
    db = _build_one_element()
    element = next(
        obj for obj in db.added
        if isinstance(obj, ApplicationModelNode) and obj.node_type == "element"
    )
    # The slug locator_map is keyed by — so a model-sourced catalog names
    # elements exactly as the map-sourced one it replaces.
    assert element.attributes["catalog_name"] == "button_submit"
    # The real URL, which is what scopes a catalog to the host under test.
    assert element.attributes["page_url"] == "https://shop.example.com/checkout"
    assert element.attributes["role"] == "button"


def test_an_action_with_no_ranked_candidate_still_records_its_confidence():
    """A locator the ranker could not score must not invent one."""
    db = _build_one_element({"locator_evidence": {"element_name": "x", "candidates": []}})
    evidence = [obj for obj in db.added if isinstance(obj, ApplicationModelLocatorEvidence)]
    assert len(evidence) == 1
    assert evidence[0].locator_value is None
    assert evidence[0].locator_type is None
    assert evidence[0].confidence == 95


# --- A refused interaction must be visible ---------------------------------
#
# capture_service degrades an action to `read` when it cannot resolve the
# element a step named. That refusal is correct, but it used to be silent:
# the model saw a plain observation, raised no gap, and published an
# element-less version that grounded nothing. Observed live as session 33,
# where "Click the Register button" hit a page carrying both a
# link "Register" and a button "Register".


def test_a_refused_click_raises_the_missing_element_gap_it_promises():
    actions = [
        _action(id=1, sequence=1, action_family="navigate", target_screen_ref="SCR-REGISTER"),
        _action(
            id=2, sequence=2,
            # What was persisted: the click could not be performed.
            action_family="read",
            # What the step actually asked for.
            intended_action_family="click",
            target_screen_ref="SCR-REGISTER",
            issue_note="Could not identify 'Register' on this page — recorded as an observation.",
        ),
    ]
    db = _FakeDB(get_queue=[_application(), _session()], execute_queue=[[_session()], actions, []])
    anyio.run(
        lambda: svc.build_or_rebuild_draft(db, project_id=1, application_id=1, session_id=1, actor_id=10)
    )

    gaps = [g for g in db.added if isinstance(g, ApplicationModelGap)]
    missing = [g for g in gaps if g.gap_type == "MISSING_ELEMENT"]
    assert len(missing) == 1
    assert missing[0].severity == "critical"
    assert missing[0].evidence["requested_action"] == "click"
    # The reviewer reads why it was refused where the decision gets made.
    assert "Register" in missing[0].evidence["reason"]
    assert "unambiguously" in missing[0].remediation


def test_a_genuine_observation_still_raises_nothing():
    """A step that was only ever meant to be read must stay silent."""
    actions = [
        _action(id=1, sequence=1, action_family="navigate", target_screen_ref="SCR-REGISTER"),
        _action(id=2, sequence=2, action_family="read", target_screen_ref="SCR-REGISTER"),
    ]
    db = _FakeDB(get_queue=[_application(), _session()], execute_queue=[[_session()], actions, []])
    anyio.run(
        lambda: svc.build_or_rebuild_draft(db, project_id=1, application_id=1, session_id=1, actor_id=10)
    )

    gaps = [g for g in db.added if isinstance(g, ApplicationModelGap)]
    assert [g.gap_type for g in gaps if g.gap_type == "MISSING_ELEMENT"] == []


def test_a_model_with_screens_but_no_elements_cannot_be_approved():
    model = SimpleNamespace(
        id=1, status="pending_review", built_by=10, project_id=1, application_id=1,
        version=1, source_session_id=1, built_from_action_count=4,
    )
    db = _FakeDB(execute_queue=[[], [("screen", 1)]])  # no critical gaps; 1 screen, no elements

    try:
        anyio.run(lambda: svc.approve(db, model, actor_id=20, reason=None))
        assert False, "expected an element-less model to be refused"
    except Exception as exc:
        assert exc.status_code == 409
        assert exc.detail["code"] == "MODEL_HAS_NO_ELEMENTS"
        # Says what is wrong and where to look, not just that it failed.
        assert "no elements" in exc.detail["message"]
        assert "gaps" in exc.detail["message"]


# ── The model describes an application, not one test case ────────────────────
#
# The build walked a single discovery session, and a rebuild deletes the
# previous walk's nodes first. So running the Application Model for TC-106
# destroyed TC-105's evidence, and TC-107 would have destroyed TC-106's — each
# test case's model run quietly undoing the last. It stayed invisible on
# project 14 only because both sessions happened to touch the same control.


def test_every_test_cases_latest_session_contributes():
    db = _FakeDB(execute_queue=[[
        _session(session_id=34, test_case_id=105),
        _session(session_id=35, test_case_id=106),
    ]])

    sessions = anyio.run(
        lambda: svc.contributing_sessions(db, project_id=1, application_id=1, selected_session_id=35)
    )

    assert [s.id for s in sessions] == [34, 35]


def test_re_recording_a_test_case_supersedes_its_own_earlier_run():
    """Otherwise a refused capture would sit in the model forever, beside the
    good re-run that replaced it — and keep raising its critical gap."""
    db = _FakeDB(execute_queue=[[
        _session(session_id=34, test_case_id=105),
        _session(session_id=35, test_case_id=106),
        _session(session_id=36, test_case_id=106),
    ]])

    sessions = anyio.run(
        lambda: svc.contributing_sessions(db, project_id=1, application_id=1, selected_session_id=36)
    )

    assert [s.id for s in sessions] == [34, 36]


def test_the_selected_session_wins_for_its_own_test_case():
    """The Rebuild-from picker still means what it says: choosing the older
    run of a test case uses that run, not the newest."""
    db = _FakeDB(execute_queue=[[
        _session(session_id=35, test_case_id=106),
        _session(session_id=36, test_case_id=106),
    ]])

    sessions = anyio.run(
        lambda: svc.contributing_sessions(db, project_id=1, application_id=1, selected_session_id=35)
    )

    assert [s.id for s in sessions] == [35]


def test_ad_hoc_sessions_contribute_individually():
    """A session naming no test case is exploration — it is not superseded by
    another session that also names none."""
    db = _FakeDB(execute_queue=[[
        _session(session_id=10, test_case_id=None),
        _session(session_id=11, test_case_id=None),
        _session(session_id=12, test_case_id=105),
    ]])

    sessions = anyio.run(
        lambda: svc.contributing_sessions(db, project_id=1, application_id=1, selected_session_id=12)
    )

    assert [s.id for s in sessions] == [10, 11, 12]


def test_a_build_walks_every_contributing_session_not_just_the_selected_one():
    """The regression itself: TC-105's screen must survive a build triggered
    from TC-106's session."""
    actions = [
        _action(id=1, session_id=34, sequence=1, action_family="navigate", target_screen_ref="SCR-SEARCH"),
        _action(
            id=2, session_id=34, sequence=2, action_family="input", target_screen_ref="SCR-SEARCH",
            target_element_ref="ELM-SEARCHBOX", locator_evidence=_ranking(locator="#q"), locator_confidence=90,
        ),
        _action(id=3, session_id=36, sequence=1, action_family="navigate", target_screen_ref="SCR-CART"),
        _action(
            id=4, session_id=36, sequence=2, action_family="click", target_screen_ref="SCR-CART",
            target_element_ref="ELM-CHECKOUT", locator_evidence=_ranking(locator="#checkout"), locator_confidence=90,
        ),
    ]
    db = _FakeDB(
        get_queue=[_application(), _session(session_id=36, test_case_id=106)],
        execute_queue=[
            [_session(session_id=34, test_case_id=105), _session(session_id=36, test_case_id=106)],
            actions,
            [],
        ],
    )

    model = anyio.run(lambda: svc.build_or_rebuild_draft(
        db, project_id=1, application_id=1, session_id=36, actor_id=10,
    ))

    nodes = [o for o in db.added if isinstance(o, ApplicationModelNode)]
    assert {n.external_ref for n in nodes if n.node_type == "screen"} == {"SCR-SEARCH", "SCR-CART"}
    assert {n.external_ref for n in nodes if n.node_type == "element"} == {"ELM-SEARCHBOX", "ELM-CHECKOUT"}
    assert model.built_from_action_count == 4
