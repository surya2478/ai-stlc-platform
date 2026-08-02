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

from app.models.application_model import ApplicationModel, ApplicationModelGap, ApplicationModelNode
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
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _application(project_id=1, app_id=1):
    return SimpleNamespace(id=app_id, project_id=project_id)


def _session(session_id=1, project_id=1, app_id=1, status="COMPLETED"):
    return SimpleNamespace(id=session_id, project_id=project_id, application_id=app_id, status=status)


def test_build_draft_creates_screens_components_elements_and_gaps():
    actions = [
        _action(id=1, sequence=1, action_family="navigate", target_screen_ref="SCR-LOGIN"),
        _action(
            id=2, sequence=2, action_family="click", target_screen_ref="SCR-LOGIN",
            target_component_ref="CMP-LOGINFORM", target_element_ref="ELM-SUBMIT",
            locator_evidence={"value": "#submit", "type": "css"}, locator_confidence=95,
        ),
        _action(id=3, sequence=3, action_family="navigate", target_screen_ref="SCR-DASHBOARD"),
        _action(id=4, sequence=4, action_family="click", target_component_ref="CMP-WIDGET"),
        _action(id=5, sequence=5, action_family="click", target_screen_ref="SCR-DASHBOARD"),
    ]
    db = _FakeDB(
        get_queue=[_application(), _session()],
        execute_queue=[actions, []],  # actions fetch, then get_current_model() -> no head
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
    db = _FakeDB(execute_queue=[[]])

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
        execute_queue=[actions, []],
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
    db = _FakeDB(execute_queue=[[]])

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
