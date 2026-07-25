"""UI-017 API and Network Explorer service — Phase 1.

Same queued-response fake DB pattern as test_application_model_service.py.
`_read_capture_text` (real file I/O against the managed discovery workspace)
is monkeypatched in build/rebuild tests so the parser logic is exercised
without touching disk.
"""
from types import SimpleNamespace

import anyio
import pytest

from app.models.network_event import NetworkEvent
from app.schemas.network_event import NetworkEventOut
from app.services import network_event_service as svc


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
        self.executed_statements = []
        self.added = []
        self.next_id = 1

    async def get(self, _model, _id):
        return self.get_queue.pop(0) if self.get_queue else None

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self.next_id
            self.next_id += 1
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, _obj, attribute_names=None):
        return None


def _session(session_id=1, project_id=1, app_id=1, environment="staging", correlation_id=None):
    return SimpleNamespace(
        id=session_id, project_id=project_id, application_id=app_id, environment=environment,
        correlation_id=correlation_id,
    )


def _application(env_urls=None):
    return SimpleNamespace(environment_urls=env_urls or {"staging": "https://app.b2b-retail.com/home"})


def _capture(capture_id=1, action_id=None, captured_at="2026-07-25T00:00:00Z"):
    return SimpleNamespace(id=capture_id, session_id=1, action_id=action_id, storage_path=f"/fake/{capture_id}.txt", captured_at=captured_at)


# ─── _parse_line ──────────────────────────────────────────────────────────

def test_parse_line_parses_full_request_and_response():
    result = svc._parse_line("[GET] https://api.b2b-retail.com/v1/products?page=1 => [200] OK")
    assert result["parse_state"] == "parsed"
    assert result["method"] == "GET"
    assert result["host"] == "api.b2b-retail.com"
    assert result["path"] == "/v1/products"
    assert result["status_code"] == 200
    assert result["status_text"] == "OK"


def test_parse_line_parses_pending_request_without_response():
    result = svc._parse_line("[POST] https://api.b2b-retail.com/v1/cart/items")
    assert result["parse_state"] == "parsed"
    assert result["method"] == "POST"
    assert result["status_code"] is None


def test_parse_line_handles_the_real_numbered_list_format():
    # The real @playwright/mcp `browser_network_requests` tool numbers each
    # entry ("5. [GET] ...", "12. [GET] ... => [200]") — confirmed against a
    # live capture. A regex that only handled a bare "[METHOD] url" line
    # marked every real request as unparsed.
    result = svc._parse_line("12. [GET] https://www.google.ae/xjs/_/js/foo?cb=[REDACTED] => [200]")
    assert result["parse_state"] == "parsed"
    assert result["method"] == "GET"
    assert result["status_code"] == 200

    pending = svc._parse_line("5. [GET] https://www.google.ae/async/hpba?yv=3&cs=0")
    assert pending["parse_state"] == "parsed"
    assert pending["status_code"] is None


def test_parse_line_falls_back_to_unparsed_for_unrecognized_text():
    result = svc._parse_line("some unrelated console noise, not a request line")
    assert result == {"parse_state": "unparsed"}


# ─── build_or_rebuild ──────────────────────────────────────────────────────

def test_build_or_rebuild_parses_lines_and_flags_external_hosts(monkeypatch):
    texts = {
        1: "[GET] https://app.b2b-retail.com/api/v1/products => [200] OK\nnot a request line at all",
        2: "[POST] https://payments.gateway.com/v1/charge => [201] Created",
    }
    monkeypatch.setattr(svc, "_read_capture_text", lambda capture: texts[capture.id])

    captures = [_capture(capture_id=1, action_id=42), _capture(capture_id=2, action_id=None)]
    db = _FakeDB(
        get_queue=[_session(), _application()],
        execute_queue=[[], captures],  # delete(...) result ignored, then the captures select
    )

    session = anyio.run(lambda: svc.build_or_rebuild(db, project_id=1, session_id=1, actor_id=10))
    assert session.id == 1

    events = [obj for obj in db.added if isinstance(obj, NetworkEvent)]
    assert len(events) == 3

    parsed_events = [e for e in events if e.parse_state == "parsed"]
    unparsed_events = [e for e in events if e.parse_state == "unparsed"]
    assert len(parsed_events) == 2
    assert len(unparsed_events) == 1
    assert unparsed_events[0].raw_line == "not a request line at all"

    internal = next(e for e in parsed_events if e.host == "app.b2b-retail.com")
    external = next(e for e in parsed_events if e.host == "payments.gateway.com")
    assert internal.is_external is False
    assert external.is_external is True
    assert internal.action_id == 42
    assert external.action_id is None


def test_build_or_rebuild_deletes_existing_events_first(monkeypatch):
    monkeypatch.setattr(svc, "_read_capture_text", lambda capture: None)
    db = _FakeDB(get_queue=[_session(), _application()], execute_queue=[[], []])

    anyio.run(lambda: svc.build_or_rebuild(db, project_id=1, session_id=1, actor_id=10))

    # First execute() call must be the delete-in-place, before the captures fetch.
    assert "DELETE" in str(db.executed_statements[0]).upper()


def test_build_or_rebuild_rejects_session_from_another_project():
    db = _FakeDB(get_queue=[_session(project_id=2)])

    try:
        anyio.run(lambda: svc.build_or_rebuild(db, project_id=1, session_id=1, actor_id=10))
        assert False, "expected a project-isolation failure"
    except Exception as exc:
        assert exc.status_code == 404
        assert exc.detail["code"] == "SESSION_NOT_FOUND"


# ─── review actions ─────────────────────────────────────────────────────────

def test_mark_ignored_requires_a_reason():
    event = SimpleNamespace(id=1, project_id=1, session_id=1, review_state="unreviewed")
    db = _FakeDB()

    try:
        anyio.run(lambda: svc.mark_ignored(db, event, actor_id=10, reason="  "))
        assert False, "expected a reason-required failure"
    except Exception as exc:
        assert exc.status_code == 422
        assert exc.detail["code"] == "REASON_REQUIRED"


def test_mark_ignored_sets_review_state():
    event = SimpleNamespace(
        id=1, project_id=1, session_id=1, review_state="unreviewed", review_reason=None,
        reviewed_by=None, reviewed_at=None,
    )
    db = _FakeDB()

    result = anyio.run(lambda: svc.mark_ignored(db, event, actor_id=10, reason="Not relevant to this journey"))

    assert result.review_state == "ignored"
    assert result.reviewed_by == 10
    assert result.review_reason == "Not relevant to this journey"


# ─── KPIs ────────────────────────────────────────────────────────────────

def test_compute_kpis_never_fabricates_a_validation_result():
    events = [
        SimpleNamespace(parse_state="parsed", method="GET", path="/v1/products", host="app.b2b-retail.com", is_external=False, action_id=1, review_state="unreviewed"),
        SimpleNamespace(parse_state="parsed", method="POST", path="/v1/charge", host="payments.gateway.com", is_external=True, action_id=None, review_state="ignored"),
        SimpleNamespace(parse_state="unparsed", method=None, path=None, host=None, is_external=None, action_id=None, review_state="unreviewed"),
    ]
    db = _FakeDB(execute_queue=[events])

    kpis = anyio.run(lambda: svc.compute_kpis(db, session_id=1))

    assert kpis["requests_captured"] == 3
    assert kpis["requests_parsed"] == 2
    assert kpis["requests_unparsed"] == 1
    assert kpis["apis_identified"] == 2
    assert kpis["external_systems"] == 1
    assert kpis["mapping_readiness_pct"] == 33  # 1 of 3 events has an action_id
    assert kpis["ignored"] == 1
    assert kpis["validation_available"] is False


# ─── sensitive-data containment (spec-level) ────────────────────────────────

def test_network_event_schema_never_exposes_headers_or_body():
    forbidden = {"headers", "request_headers", "response_headers", "body", "authorization", "cookies", "token"}
    assert forbidden.isdisjoint(NetworkEventOut.model_fields.keys())
