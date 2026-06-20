"""
Settings endpoint — returns non-sensitive config and lets UI display current setup.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.config import get_settings
from app.llm.provider import get_latest_rate_limit_snapshot

router = APIRouter()
settings = get_settings()


class SettingsOut(BaseModel):
    """
    Non-sensitive platform configuration for UI display.
    SEC-026: Internal infrastructure paths and credentials are intentionally excluded.
    """
    app_name: str
    app_version: str
    app_env: str
    llm_provider: str
    llm_model: str
    llm_circuit_breaker_reset_seconds: int
    openai_model: str
    openai_key_configured: bool
    last_rate_limit_snapshot: dict | None
    jira_base_url: str
    jira_project_key: str
    jira_configured: bool
    max_upload_size_mb: int


@router.get("", response_model=SettingsOut)
@router.get("/", response_model=SettingsOut)
async def get_settings_info(current_user: CurrentUser):
    return SettingsOut(
        app_name=settings.app_name,
        app_version=settings.app_version,
        app_env=settings.app_env,
        llm_provider=settings.default_llm_provider,
        llm_model=settings.default_llm_model,
        llm_circuit_breaker_reset_seconds=settings.llm_circuit_breaker_reset_seconds,
        openai_model=settings.openai_model,
        openai_key_configured=bool(settings.openai_api_key),
        last_rate_limit_snapshot=get_latest_rate_limit_snapshot(
            provider=settings.default_llm_provider,
            base_url=settings.openai_base_url if settings.default_llm_provider == "openai" else settings.ollama_base_url,
            model=settings.openai_model if settings.default_llm_provider == "openai" else settings.default_llm_model,
        ),
        jira_base_url=settings.jira_base_url,
        jira_project_key=settings.jira_project_key,
        jira_configured=bool(settings.jira_base_url and settings.jira_api_token),
        max_upload_size_mb=settings.max_upload_size_mb,
    )
