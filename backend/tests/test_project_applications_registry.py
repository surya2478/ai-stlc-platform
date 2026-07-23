"""UI-014 Application Registry — governance fields, summary aggregates,
owner-reference authorization and canonical-seed idempotency.

Follows the queued-response _FakeDB pattern already used in
test_automation_baseline_service.py (execute() replays responses in call
order) since this codebase has no real-DB test fixture.
"""
from datetime import datetime, timezone

import anyio
import pytest
from fastapi import HTTPException

from app.models.project import Project
from app.models.project_application import ProjectApplication
from app.schemas.applications import ProjectApplicationUpdate
from app.services import project_application_service as svc


class _Result:
    def __init__(self, value=None, values=None):
        self._value = value
        self._values = values if values is not None else []

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


class _FakeDB:
    """Replays queued execute() responses in call order; get() is served
    from a separate keyed store since it's a distinct AsyncSession method."""

    def __init__(self, responses=(), gets=None):
        self.responses = list(responses)
        self.gets = gets or {}
        self.added = []

    async def execute(self, _stmt):
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _Result(values=value)
        return _Result(value=value)

    async def get(self, model, pk):
        return self.gets.get((model, pk))

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 1
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None


def _app(id_: int, **overrides) -> ProjectApplication:
    data = {
        "id": id_, "project_id": 1, "key": f"app-{id_}", "name": f"App {id_}",
        "environment_urls": {}, "is_active": True, "is_default": False,
        "aliases": [], "lifecycle_status": "active",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return ProjectApplication(**data)


# ── _synced_lifecycle_status ──────────────────────────────────────────────

def test_synced_lifecycle_deprecated_forces_inactive():
    assert svc._synced_lifecycle_status("deprecated", True) == ("deprecated", False)


def test_synced_lifecycle_retired_forces_inactive():
    assert svc._synced_lifecycle_status("retired", True) == ("retired", False)


def test_synced_lifecycle_active_with_inactive_downgrades_to_draft():
    assert svc._synced_lifecycle_status("active", False) == ("draft", False)


def test_synced_lifecycle_draft_stays_draft_regardless_of_active():
    assert svc._synced_lifecycle_status("draft", True) == ("draft", True)
    assert svc._synced_lifecycle_status("draft", False) == ("draft", False)


def test_synced_lifecycle_active_with_active_is_unchanged():
    assert svc._synced_lifecycle_status("active", True) == ("active", True)


# ── _application_snapshot ─────────────────────────────────────────────────

def test_application_snapshot_includes_governance_fields():
    app = _app(1, application_type="Web", domain="Billing", product_group="Consumer",
                product="Portal", channel="Web", business_owner_id=7, technical_owner_id=8,
                aliases=["Portal Alias"])
    snap = svc._application_snapshot(app)
    assert snap["application_type"] == "Web"
    assert snap["domain"] == "Billing"
    assert snap["product_group"] == "Consumer"
    assert snap["product"] == "Portal"
    assert snap["channel"] == "Web"
    assert snap["business_owner_id"] == 7
    assert snap["technical_owner_id"] == 8
    assert snap["aliases"] == ["Portal Alias"]
    assert snap["lifecycle_status"] == "active"


# ── build_registry_summary ────────────────────────────────────────────────

def test_registry_summary_computes_real_aggregates():
    apps = [
        _app(1, environment_urls={"SIT": "https://sit.example.com"}, is_active=True,
             product_group="Consumer", product="Portal", channel="Web"),
        _app(2, environment_urls={}, is_active=True,
             product_group="Consumer", product="Portal", channel="Web"),  # conflicts with app 1
        _app(3, environment_urls={}, is_active=True),  # no environments, no mapping -> gap only
        _app(4, environment_urls={"SIT": "https://sit2.example.com"}, is_active=False),  # inactive, excluded
    ]
    usage_rows = [(1, 5), (2, 2)]  # (application_id, test_case_count)
    db = _FakeDB(responses=[apps, usage_rows])

    summary = anyio.run(svc.build_registry_summary, db, 1)

    assert summary.total_applications == 4
    assert summary.active_applications == 3
    assert summary.discovery_ready == 1  # only app 1: active + has an environment URL
    assert summary.discovery_ready_is_proxy is True
    assert summary.environment_gaps == 2  # apps 2 and 3: active with no environment_urls
    assert summary.health_tracked is False
    assert summary.mapping_usage == {1: 5, 2: 2}
    assert len(summary.mapping_conflicts) == 1
    conflict = summary.mapping_conflicts[0]
    assert conflict.product_group == "Consumer"
    assert conflict.product == "Portal"
    assert conflict.channel == "Web"
    assert conflict.application_ids == [1, 2]


def test_registry_summary_no_conflict_when_mapping_unique():
    apps = [
        _app(1, environment_urls={}, is_active=True, product_group="Consumer", product="Portal", channel="Web"),
        _app(2, environment_urls={}, is_active=True, product_group="Enterprise", product="Admin", channel="Web"),
    ]
    db = _FakeDB(responses=[apps, []])

    summary = anyio.run(svc.build_registry_summary, db, 1)

    assert summary.mapping_conflicts == []


# ── _validate_owner_references ────────────────────────────────────────────

def test_owner_reference_rejects_non_member_non_owner():
    updates = [ProjectApplicationUpdate(key="app-1", name="App 1", business_owner_id=99)]
    db = _FakeDB(responses=[[]], gets={(Project, 1): Project(id=1, name="P", owner_id=5)})

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await svc._validate_owner_references(db, 1, updates)
        assert exc_info.value.status_code == 422

    anyio.run(run)


def test_owner_reference_accepts_project_owner():
    updates = [ProjectApplicationUpdate(key="app-1", name="App 1", business_owner_id=5)]
    db = _FakeDB(responses=[[]], gets={(Project, 1): Project(id=1, name="P", owner_id=5)})

    anyio.run(svc._validate_owner_references, db, 1, updates)  # must not raise


def test_owner_reference_accepts_active_project_member():
    updates = [ProjectApplicationUpdate(key="app-1", name="App 1", technical_owner_id=42)]
    db = _FakeDB(responses=[[42]], gets={(Project, 1): Project(id=1, name="P", owner_id=5)})

    anyio.run(svc._validate_owner_references, db, 1, updates)  # must not raise


def test_owner_reference_skips_query_when_no_owners_set():
    updates = [ProjectApplicationUpdate(key="app-1", name="App 1")]
    db = _FakeDB(responses=[])  # would raise IndexError if execute() were called

    anyio.run(svc._validate_owner_references, db, 1, updates)


# ── seed_canonical_applications idempotency ───────────────────────────────

def test_seed_is_noop_when_all_canonical_keys_already_exist():
    existing = [_app(i, key=key, name=name) for i, (key, name) in enumerate(svc.CANONICAL_APPLICATIONS, start=1)]
    db = _FakeDB(responses=[existing, existing, []])  # list_applications, then build_project_applications_response's applications + dependencies

    result = anyio.run(svc.seed_canonical_applications, db, 1, 9)

    assert len(result["applications"]) == len(svc.CANONICAL_APPLICATIONS)
    assert db.added == []  # nothing was created — every canonical key was already present


def test_seed_only_submits_missing_keys(monkeypatch):
    existing_key, existing_name = svc.CANONICAL_APPLICATIONS[0]
    existing = [_app(1, key=existing_key, name=existing_name)]
    db = _FakeDB(responses=[existing])

    captured = {}

    async def fake_update(db_arg, *, project_id, payload, user_id, source):
        captured["payload"] = payload
        captured["source"] = source
        return {"applications": [], "external_dependencies": [], "project_id": project_id,
                "available_environments": [], "last_updated": None, "updated_by": None}

    monkeypatch.setattr(svc, "update_project_applications", fake_update)

    anyio.run(svc.seed_canonical_applications, db, 1, 9)

    submitted_keys = {item.key for item in captured["payload"].applications}
    assert existing_key not in submitted_keys
    assert submitted_keys == {key for key, _ in svc.CANONICAL_APPLICATIONS if key != existing_key}
    assert captured["source"] == "seed"
    assert all(not item.is_default for item in captured["payload"].applications)
