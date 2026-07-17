from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.models.llm_settings import ProjectLLMSetting, ProjectSettingAuditLog
from app.schemas.llm_settings import ProjectLLMSettingUpdate, ProjectLLMSettingsUpdateRequest
from app.services import project_llm_settings_service as svc
from app.services.llm_provider_registry import list_provider_metadata, provider_to_response


class _Scalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _Result:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _Scalars(self._values)


class _FakeDB:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.audit_logs = []
        self.next_id = 1

    async def execute(self, _stmt):
        return _Result(self.rows)

    def add(self, item):
        if isinstance(item, ProjectLLMSetting):
            # Mirrors TimestampMixin's server_default=func.now(): a real
            # session always has created_at populated after flush, so
            # build_project_settings_response's max(...) never compares
            # two Nones.
            if item.created_at is None:
                item.created_at = datetime.now(timezone.utc)
            self.rows.append(item)
        elif isinstance(item, ProjectSettingAuditLog):
            self.audit_logs.append(item)

    async def flush(self):
        for row in self.rows:
            if row.id is None:
                row.id = self.next_id
                self.next_id += 1


def test_provider_registry_response_never_exposes_secret_values():
    response = [provider_to_response(provider) for provider in list_provider_metadata()]

    assert {item["provider_key"] for item in response} >= {
        "groq",
        "google_gemini",
        "ollama",
        "openrouter",
        "huggingface",
        "openai",
    }
    assert all("api_key_value" not in item for item in response)
    assert all("secret" not in item for item in response)


@pytest.mark.anyio
async def test_update_project_llm_settings_creates_audit_log_for_primary_provider():
    db = _FakeDB()
    payload = ProjectLLMSettingsUpdateRequest(
        settings=[
            ProjectLLMSettingUpdate(
                provider_key="ollama",
                model_name="llama3.1",
                is_enabled=True,
                is_primary=True,
                temperature=0.3,
                max_tokens=2000,
                timeout_seconds=60,
                module_scope=["Requirement Analysis"],
            )
        ],
        change_reason="unit test",
    )

    response = await svc.update_project_llm_settings(db, project_id=8, payload=payload, user_id=42)

    assert response["active_provider"].provider_key == "ollama"
    assert response["active_model"] == "llama3.1"
    assert len(db.audit_logs) == 1
    assert db.audit_logs[0].setting_type == "llm_providers"


@pytest.mark.anyio
async def test_multiple_primary_providers_are_rejected():
    db = _FakeDB()
    payload = ProjectLLMSettingsUpdateRequest(
        settings=[
            ProjectLLMSettingUpdate(provider_key="ollama", model_name="llama3.1", is_enabled=True, is_primary=True),
            ProjectLLMSettingUpdate(provider_key="openai", model_name="gpt-4o-mini", is_enabled=True, is_primary=True),
        ],
    )

    with pytest.raises(HTTPException) as exc:
        await svc.update_project_llm_settings(db, project_id=8, payload=payload, user_id=42)

    assert exc.value.status_code == 400
    assert "Only one active provider" in exc.value.detail


@pytest.mark.anyio
async def test_missing_api_key_for_enabled_hosted_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(svc.settings, "groq_api_key", "")
    db = _FakeDB()
    payload = ProjectLLMSettingsUpdateRequest(
        settings=[
            ProjectLLMSettingUpdate(provider_key="groq", model_name="llama-3.3-70b-versatile", is_enabled=True),
        ],
    )

    with pytest.raises(HTTPException) as exc:
        await svc.update_project_llm_settings(db, project_id=8, payload=payload, user_id=42)

    assert exc.value.status_code == 422
    assert exc.value.detail == "Missing API key for selected provider."


@pytest.mark.anyio
async def test_project_route_resolves_to_system_default_when_not_configured():
    db = _FakeDB()

    routes = await svc.resolve_project_llm_routes(db, project_id=8)

    assert routes[0].source == "system_default"
    assert routes[0].provider_key == svc.settings.default_llm_provider


@pytest.mark.anyio
async def test_role_specific_and_generic_primaries_both_accepted(monkeypatch):
    monkeypatch.setattr(svc.settings, "groq_api_key", "test-key")
    db = _FakeDB()
    payload = ProjectLLMSettingsUpdateRequest(
        settings=[
            ProjectLLMSettingUpdate(provider_key="ollama", model_name="llama3.1", is_enabled=True, is_primary=True),
            ProjectLLMSettingUpdate(
                provider_key="groq", model_name="llama-3.3-70b-versatile",
                is_enabled=True, is_primary=True, llm_role="coding",
            ),
        ],
    )

    await svc.update_project_llm_settings(db, project_id=8, payload=payload, user_id=42)

    primaries = {(row.provider_key, row.llm_role) for row in db.rows if row.is_primary}
    assert primaries == {("ollama", None), ("groq", "coding")}


@pytest.mark.anyio
async def test_same_role_duplicate_primaries_are_rejected(monkeypatch):
    monkeypatch.setattr(svc.settings, "groq_api_key", "test-key")
    db = _FakeDB()
    payload = ProjectLLMSettingsUpdateRequest(
        settings=[
            ProjectLLMSettingUpdate(
                provider_key="ollama", model_name="llama3.1",
                is_enabled=True, is_primary=True, llm_role="coding",
            ),
            ProjectLLMSettingUpdate(
                provider_key="groq", model_name="llama-3.3-70b-versatile",
                is_enabled=True, is_primary=True, llm_role="coding",
            ),
        ],
    )

    with pytest.raises(HTTPException) as exc:
        await svc.update_project_llm_settings(db, project_id=8, payload=payload, user_id=42)

    assert exc.value.status_code == 400
    assert "role 'coding'" in exc.value.detail


@pytest.mark.anyio
async def test_invalid_llm_role_is_rejected():
    db = _FakeDB()
    payload = ProjectLLMSettingsUpdateRequest(
        settings=[
            ProjectLLMSettingUpdate(provider_key="ollama", model_name="llama3.1", is_enabled=True),
        ],
    )
    # llm_role is validated server-side against the ROLES tuple even though
    # the pydantic Literal already narrows it — belt-and-suspenders since
    # ROLES is the single source of truth shared with roles.py.
    payload.settings[0].llm_role = "not-a-real-role"  # type: ignore[assignment]

    with pytest.raises(HTTPException) as exc:
        await svc.update_project_llm_settings(db, project_id=8, payload=payload, user_id=42)

    assert exc.value.status_code == 422
    assert "Invalid llm_role" in exc.value.detail


@pytest.mark.anyio
async def test_resolve_project_llm_routes_role_specific_primary_beats_generic():
    generic_primary = ProjectLLMSetting(
        project_id=8, provider_key="ollama", provider_name="Ollama", model_name="llama3.1",
        is_enabled=True, is_primary=True, llm_role=None, module_scope=[],
    )
    coding_primary = ProjectLLMSetting(
        project_id=8, provider_key="groq", provider_name="Groq", model_name="llama-3.3-70b-versatile",
        is_enabled=True, is_primary=True, llm_role="coding", module_scope=[],
    )
    db = _FakeDB(rows=[generic_primary, coding_primary])

    coding_routes = await svc.resolve_project_llm_routes(db, project_id=8, role="coding")
    reasoning_routes = await svc.resolve_project_llm_routes(db, project_id=8, role="reasoning")

    assert coding_routes[0].provider_key == "groq"
    assert coding_routes[0].source == "project"
    # No reasoning-specific row exists, so the generic primary applies.
    assert reasoning_routes[0].provider_key == "ollama"


@pytest.mark.anyio
async def test_resolve_project_llm_routes_system_tier_uses_role_default(monkeypatch):
    monkeypatch.setattr(svc.settings, "ai_gateway_enabled", True)
    monkeypatch.setattr(svc.settings, "llm_coding_model", "qwen3-coder-next")
    db = _FakeDB()

    routes = await svc.resolve_project_llm_routes(db, project_id=8, role="coding")

    assert routes[-1].source == "system_default"
    assert routes[-1].provider_key == "ai_gateway"
    assert routes[-1].model_name == "qwen3-coder-next"


@pytest.mark.anyio
async def test_setting_snapshot_includes_llm_role():
    row = ProjectLLMSetting(
        project_id=8, provider_key="groq", provider_name="Groq", model_name="llama-3.3-70b-versatile",
        is_enabled=True, is_primary=True, llm_role="vision", module_scope=[],
    )

    snapshot = svc._setting_snapshot(row)

    assert snapshot["llm_role"] == "vision"


@pytest.mark.anyio
async def test_resolve_project_llm_routes_scope_label_matching_works():
    # The row is scoped via the UI's label ("Requirement Analysis"); agents
    # pass the slug ("requirement") — this must now match (previously dead
    # code compared the slug against label strings and never matched).
    row = ProjectLLMSetting(
        project_id=8, provider_key="ollama", provider_name="Ollama", model_name="llama3.1",
        is_enabled=True, is_primary=True, llm_role=None, module_scope=["Requirement Analysis"],
    )
    db = _FakeDB(rows=[row])

    matching = await svc.resolve_project_llm_routes(db, project_id=8, module_scope="requirement")
    non_matching = await svc.resolve_project_llm_routes(db, project_id=8, module_scope="defect")

    assert matching[0].provider_key == "ollama"
    assert matching[0].source == "project"
    assert non_matching[0].source == "system_default"
