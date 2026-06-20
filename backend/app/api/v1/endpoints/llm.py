"""Project-scoped LLM configuration endpoints."""
from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession, require_permission, require_project_access
from app.schemas.llm_settings import (
    LLMConnectionTestOut,
    LLMConnectionTestRequest,
    LLMProviderMetadataOut,
    ProjectLLMSettingsOut,
    ProjectLLMSettingsUpdateRequest,
)
from app.services.llm_provider_registry import list_provider_metadata, provider_to_response
from app.services.project_llm_settings_service import (
    build_project_settings_response,
    test_provider_configuration,
    update_project_llm_settings,
)
from app.services.rbac_service import MANAGE_PROJECT

router = APIRouter()


@router.get("/llm/providers", response_model=list[LLMProviderMetadataOut])
async def get_llm_providers(current_user: CurrentUser):
    return [provider_to_response(provider) for provider in list_provider_metadata()]


@router.get("/projects/{project_id}/llm-settings", response_model=ProjectLLMSettingsOut)
async def get_project_llm_settings(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_project_access(project_id, current_user, db)
    return await build_project_settings_response(db, project_id)


@router.put("/projects/{project_id}/llm-settings", response_model=ProjectLLMSettingsOut)
async def put_project_llm_settings(
    project_id: int,
    payload: ProjectLLMSettingsUpdateRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_permission(MANAGE_PROJECT, project_id, current_user, db)
    return await update_project_llm_settings(
        db,
        project_id=project_id,
        payload=payload,
        user_id=current_user.id,
        source="ui",
    )


@router.post("/projects/{project_id}/llm-settings/test", response_model=LLMConnectionTestOut)
async def post_project_llm_settings_test(
    project_id: int,
    payload: LLMConnectionTestRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_permission(MANAGE_PROJECT, project_id, current_user, db)
    return await test_provider_configuration(payload.provider_key, payload.model_name)
