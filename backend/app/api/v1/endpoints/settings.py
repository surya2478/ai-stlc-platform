"""
Settings endpoint — returns non-sensitive config and lets UI display current setup.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import OptionalUser
from app.config import get_settings

router = APIRouter()
settings = get_settings()


class SettingsOut(BaseModel):
    app_name: str
    app_version: str
    app_env: str
    llm_provider: str
    llm_model: str
    ollama_base_url: str
    openai_base_url: str
    openai_model: str
    openai_key_configured: bool
    jira_base_url: str
    jira_email: str
    jira_project_key: str
    jira_configured: bool
    max_upload_size_mb: int
    file_storage_path: str


@router.get("/", response_model=SettingsOut)
async def get_settings_info(current_user: OptionalUser):
    return SettingsOut(
        app_name=settings.app_name,
        app_version=settings.app_version,
        app_env=settings.app_env,
        llm_provider=settings.default_llm_provider,
        llm_model=settings.default_llm_model,
        ollama_base_url=settings.ollama_base_url,
        openai_base_url=settings.openai_base_url,
        openai_model=settings.openai_model,
        openai_key_configured=bool(settings.openai_api_key),
        jira_base_url=settings.jira_base_url,
        jira_email=settings.jira_email,
        jira_project_key=settings.jira_project_key,
        jira_configured=bool(settings.jira_base_url and settings.jira_api_token),
        max_upload_size_mb=settings.max_upload_size_mb,
        file_storage_path=settings.file_storage_path,
    )
