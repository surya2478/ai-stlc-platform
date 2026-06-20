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
