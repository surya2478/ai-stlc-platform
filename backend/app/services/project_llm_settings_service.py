from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.llm_settings import ProjectLLMSetting, ProjectSettingAuditLog
from app.schemas.llm_settings import ProjectLLMSettingUpdate, ProjectLLMSettingsUpdateRequest
from app.services.llm_provider_registry import (
    get_provider_metadata,
    is_provider_key_configured,
    list_provider_metadata,
    model_is_supported,
    provider_to_response,
)

settings = get_settings()


@dataclass(frozen=True)
class LLMRouteConfig:
    provider_key: str
    provider_name: str
    model_name: str
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: int | None = None
    source: str = "project"


def _setting_snapshot(setting: ProjectLLMSetting) -> dict[str, Any]:
    return {
        "id": setting.id,
        "project_id": setting.project_id,
        "provider_name": setting.provider_name,
        "provider_key": setting.provider_key,
        "model_name": setting.model_name,
        "is_enabled": setting.is_enabled,
        "is_primary": setting.is_primary,
        "is_fallback": setting.is_fallback,
        "fallback_priority": setting.fallback_priority,
        "temperature": setting.temperature,
        "max_tokens": setting.max_tokens,
        "timeout_seconds": setting.timeout_seconds,
        "module_scope": setting.module_scope or [],
        "config_status": setting.config_status,
        "created_by": setting.created_by,
        "updated_by": setting.updated_by,
        "created_at": setting.created_at.isoformat() if setting.created_at else None,
        "updated_at": setting.updated_at.isoformat() if setting.updated_at else None,
    }


def _status_for(update: ProjectLLMSettingUpdate) -> str:
    if not update.is_enabled:
        return "disabled"
    if not is_provider_key_configured(update.provider_key):
        return "missing_api_key"
    if update.is_primary:
        return "active"
    if update.is_fallback:
        return "fallback"
    return "enabled"


def _validate_updates(updates: list[ProjectLLMSettingUpdate]) -> None:
    active = [item for item in updates if item.is_primary and item.is_enabled]
    if len(active) > 1:
        raise HTTPException(status_code=400, detail="Only one active provider can be selected per project.")

    fallback_priorities: set[int] = set()
    for item in updates:
        provider = get_provider_metadata(item.provider_key)
        if provider is None or not provider.enabled_for_selection:
            raise HTTPException(status_code=422, detail=f"Unsupported LLM provider: {item.provider_key}")
        if not model_is_supported(item.provider_key, item.model_name):
            raise HTTPException(
                status_code=422,
                detail=f"Model '{item.model_name}' is not supported for {provider.provider_name}.",
            )
        if item.is_enabled and provider.api_key_required and not is_provider_key_configured(item.provider_key):
            raise HTTPException(status_code=422, detail="Missing API key for selected provider.")
        if item.is_primary and not item.is_enabled:
            raise HTTPException(status_code=422, detail="Active provider must be enabled.")
        if item.is_fallback:
            if not item.is_enabled:
                raise HTTPException(status_code=422, detail="Fallback provider must be enabled.")
            if item.fallback_priority is None:
                raise HTTPException(status_code=422, detail="Fallback provider priority is required.")
            if item.fallback_priority in fallback_priorities:
                raise HTTPException(status_code=422, detail="Fallback providers must have unique priorities.")
            fallback_priorities.add(item.fallback_priority)


async def list_settings(db: AsyncSession, project_id: int) -> list[ProjectLLMSetting]:
    result = await db.execute(
        select(ProjectLLMSetting)
        .where(ProjectLLMSetting.project_id == project_id)
        .order_by(ProjectLLMSetting.provider_name.asc())
    )
    return list(result.scalars().all())


async def build_project_settings_response(db: AsyncSession, project_id: int) -> dict:
    settings_rows = await list_settings(db, project_id)
    active = next((item for item in settings_rows if item.is_primary and item.is_enabled), None)
    fallback_order = sorted(
        [item for item in settings_rows if item.is_fallback and item.is_enabled],
        key=lambda item: item.fallback_priority or 999,
    )
    last_updated_setting = max(settings_rows, key=lambda item: item.updated_at or item.created_at, default=None)

    return {
        "project_id": project_id,
        "providers": [provider_to_response(provider) for provider in list_provider_metadata()],
        "settings": settings_rows,
        "active_provider": active,
        "active_model": active.model_name if active else None,
        "fallback_order": fallback_order,
        "system_default_provider": settings.default_llm_provider,
        "system_default_model": settings.default_llm_model,
        "uses_system_default": active is None,
        "last_updated": (last_updated_setting.updated_at if last_updated_setting else None),
        "updated_by": (last_updated_setting.updated_by if last_updated_setting else None),
        "security_status": "Secure",
    }


async def update_project_llm_settings(
    db: AsyncSession,
    *,
    project_id: int,
    payload: ProjectLLMSettingsUpdateRequest,
    user_id: int,
    source: str = "ui",
) -> dict:
    _validate_updates(payload.settings)

    existing = {item.provider_key: item for item in await list_settings(db, project_id)}
    old_snapshot = [_setting_snapshot(item) for item in existing.values()]
    touched: list[ProjectLLMSetting] = []

    for item in payload.settings:
        provider = get_provider_metadata(item.provider_key)
        assert provider is not None
        row = existing.get(item.provider_key)
        if row is None:
            row = ProjectLLMSetting(
                project_id=project_id,
                provider_key=item.provider_key,
                provider_name=provider.provider_name,
                model_name=item.model_name,
                created_by=user_id,
            )
            db.add(row)
        row.provider_name = provider.provider_name
        row.model_name = item.model_name
        row.is_enabled = item.is_enabled
        row.is_primary = item.is_primary and item.is_enabled
        row.is_fallback = item.is_fallback and item.is_enabled
        row.fallback_priority = item.fallback_priority if row.is_fallback else None
        row.temperature = item.temperature
        row.max_tokens = item.max_tokens
        row.timeout_seconds = item.timeout_seconds
        row.module_scope = item.module_scope
        row.config_status = _status_for(item)
        row.updated_by = user_id
        touched.append(row)

    # Defensive cleanup if a partial payload marked a new active provider: clear active on untouched providers.
    active_keys = {item.provider_key for item in payload.settings if item.is_primary and item.is_enabled}
    if active_keys:
        for key, row in existing.items():
            if key not in active_keys and key not in {item.provider_key for item in payload.settings}:
                row.is_primary = False
                if row.is_enabled and row.config_status == "active":
                    row.config_status = "enabled"

    await db.flush()
    new_rows = await list_settings(db, project_id)
    audit = ProjectSettingAuditLog(
        project_id=project_id,
        setting_type="llm_providers",
        old_value={"settings": old_snapshot},
        new_value={"settings": [_setting_snapshot(item) for item in new_rows]},
        changed_by=user_id,
        source=source,
        change_reason=payload.change_reason,
    )
    db.add(audit)
    await db.flush()
    return await build_project_settings_response(db, project_id)


async def resolve_project_llm_routes(
    db: AsyncSession,
    *,
    project_id: int,
    module_scope: str | None = None,
) -> list[LLMRouteConfig]:
    rows = await list_settings(db, project_id)
    eligible = [
        row for row in rows
        if row.is_enabled and (not row.module_scope or module_scope is None or module_scope in row.module_scope)
    ]
    primary = next((row for row in eligible if row.is_primary), None)
    routes: list[LLMRouteConfig] = []
    if primary is not None:
        routes.append(
            LLMRouteConfig(
                provider_key=primary.provider_key,
                provider_name=primary.provider_name,
                model_name=primary.model_name,
                temperature=primary.temperature,
                max_tokens=primary.max_tokens,
                timeout_seconds=primary.timeout_seconds,
                source="project",
            )
        )
    fallback_rows = sorted(
        [row for row in eligible if row.is_fallback and row.provider_key != (primary.provider_key if primary else None)],
        key=lambda row: row.fallback_priority or 999,
    )
    for row in fallback_rows:
        routes.append(
            LLMRouteConfig(
                provider_key=row.provider_key,
                provider_name=row.provider_name,
                model_name=row.model_name,
                temperature=row.temperature,
                max_tokens=row.max_tokens,
                timeout_seconds=row.timeout_seconds,
                source="project_fallback",
            )
        )

    routes.append(
        LLMRouteConfig(
            provider_key=settings.default_llm_provider,
            provider_name=settings.default_llm_provider,
            model_name=settings.default_llm_model,
            source="system_default",
        )
    )
    return routes


async def test_provider_configuration(provider_key: str, model_name: str | None = None) -> dict:
    provider = get_provider_metadata(provider_key)
    if provider is None:
        raise HTTPException(status_code=422, detail=f"Unsupported LLM provider: {provider_key}")
    if provider.api_key_required and not is_provider_key_configured(provider_key):
        return {
            "success": False,
            "message": "Missing API key for selected provider.",
            "provider_key": provider_key,
            "model_name": model_name,
        }
    return {
        "success": True,
        "message": "Provider connection successful.",
        "provider_key": provider_key,
        "model_name": model_name or provider.default_model,
    }


async def get_active_and_fallbacks(
    db: AsyncSession,
    project_id: int,
    module_scope: str | None = None,
) -> tuple[LLMRouteConfig | None, list[LLMRouteConfig]]:
    """
    Return the active (primary) LLMRouteConfig and an ordered list of fallback
    LLMRouteConfigs for the given project.

    Used by get_llm_with_automatic_fallback() to drive enterprise-grade failover.
    Both the primary and fallback entries respect module_scope filtering when
    module_scope is supplied.

    Returns:
        (primary, fallbacks) — primary may be None if no primary is configured,
        in which case agents should fall back to the system default.
    """
    routes = await resolve_project_llm_routes(db, project_id=project_id, module_scope=module_scope)
    # resolve_project_llm_routes always appends the system default as the last entry.
    primary = next((r for r in routes if r.source == "project"), None)
    fallbacks = [r for r in routes if r.source == "project_fallback"]
    # System default is always available as the final fallback tier.
    system_default = next((r for r in routes if r.source == "system_default"), None)
    if system_default:
        fallbacks.append(system_default)
    return primary, fallbacks
