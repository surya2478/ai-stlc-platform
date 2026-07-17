from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.llm.provider import (
    LLMRouteOverride,
    reset_llm_role_route_overrides,
    set_llm_role_route_overrides,
)
from app.llm.roles import ROLES, role_default_route
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

# UI-facing module_scope checkboxes (see LLMProvidersTab.tsx MODULE_SCOPES)
# store human labels, while agents pass slugs via AgentSpec.module_scope /
# role_for_scope. This maps slug -> the label set it corresponds to so
# resolve_project_llm_routes can actually match a project setting scoped in
# the UI against an agent's scope slug (previously `module_scope in
# row.module_scope` compared a slug against label strings and never matched).
SCOPE_SLUG_TO_LABELS: dict[str, set[str]] = {
    "requirement": {"Requirement Analysis"},
    "test_planning": {"Test Plan Generation", "Test Scenario Generation", "Test Case Generation"},
    "execution": {"Test Execution Assistance"},
    "defect": {"Defect Triage"},
    "reporting": {"Test Reporting"},
}


def _scope_matches(row_scope: list[str] | None, module_scope: str | None) -> bool:
    if not row_scope:
        return True
    if module_scope is None:
        return True
    labels = SCOPE_SLUG_TO_LABELS.get(module_scope, {module_scope})
    return bool(labels & set(row_scope))


@dataclass(frozen=True)
class LLMRouteConfig:
    provider_key: str
    provider_name: str
    model_name: str
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: int | None = None
    source: str = "project"
    llm_role: str | None = None


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
        "llm_role": setting.llm_role,
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
    # NULL llm_role ("applies to all roles") is its own group, same as a
    # real role — one primary and unique fallback priorities per group.
    # Checked as its own pass first (same precedence as the original
    # single-group check) so "multiple primaries" always wins over a later
    # per-item error like a missing API key on one of the offending rows.
    active_by_role: dict[str | None, list[ProjectLLMSettingUpdate]] = {}
    for item in updates:
        if item.is_primary and item.is_enabled:
            active_by_role.setdefault(item.llm_role, []).append(item)
    for llm_role, active in active_by_role.items():
        if len(active) > 1:
            scope = f" for role '{llm_role}'" if llm_role else ""
            raise HTTPException(
                status_code=400,
                detail=f"Only one active provider can be selected per project{scope}.",
            )

    fallback_priorities_by_role: dict[str | None, set[int]] = {}

    for item in updates:
        llm_role = item.llm_role
        if llm_role is not None and llm_role not in ROLES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid llm_role '{llm_role}'. Must be one of: {', '.join(ROLES)}.",
            )

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
            role_priorities = fallback_priorities_by_role.setdefault(llm_role, set())
            if item.fallback_priority in role_priorities:
                raise HTTPException(status_code=422, detail="Fallback providers must have unique priorities.")
            role_priorities.add(item.fallback_priority)


async def list_settings(db: AsyncSession, project_id: int) -> list[ProjectLLMSetting]:
    result = await db.execute(
        select(ProjectLLMSetting)
        .where(ProjectLLMSetting.project_id == project_id)
        .order_by(ProjectLLMSetting.provider_name.asc())
    )
    return list(result.scalars().all())


async def build_project_settings_response(db: AsyncSession, project_id: int) -> dict:
    settings_rows = await list_settings(db, project_id)
    # Legacy top-level "active provider" = the generic (llm_role IS NULL) primary,
    # for callers that don't care about per-role routing.
    active = next((item for item in settings_rows if item.is_primary and item.is_enabled and item.llm_role is None), None)
    fallback_order = sorted(
        [item for item in settings_rows if item.is_fallback and item.is_enabled and item.llm_role is None],
        key=lambda item: item.fallback_priority or 999,
    )
    last_updated_setting = max(settings_rows, key=lambda item: item.updated_at or item.created_at, default=None)

    role_defaults = {role: {"provider_key": p, "model_name": m} for role in ROLES for p, m in [role_default_route(role)]}
    active_by_role: dict[str, dict] = {}
    for role in ROLES:
        role_primary = next((r for r in settings_rows if r.is_primary and r.is_enabled and r.llm_role == role), None)
        if role_primary is None:
            role_primary = active
        if role_primary is not None:
            active_by_role[role] = {
                "provider_key": role_primary.provider_key,
                "provider_name": role_primary.provider_name,
                "model_name": role_primary.model_name,
                "source": "project",
            }
        else:
            active_by_role[role] = {**role_defaults[role], "source": "system_default"}

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
        "role_defaults": role_defaults,
        "active_by_role": active_by_role,
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

    existing = {(item.provider_key, item.llm_role): item for item in await list_settings(db, project_id)}
    old_snapshot = [_setting_snapshot(item) for item in existing.values()]
    touched: list[ProjectLLMSetting] = []

    for item in payload.settings:
        provider = get_provider_metadata(item.provider_key)
        assert provider is not None
        row = existing.get((item.provider_key, item.llm_role))
        if row is None:
            row = ProjectLLMSetting(
                project_id=project_id,
                provider_key=item.provider_key,
                provider_name=provider.provider_name,
                model_name=item.model_name,
                llm_role=item.llm_role,
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
        row.llm_role = item.llm_role
        row.config_status = _status_for(item)
        row.updated_by = user_id
        touched.append(row)

    # Defensive cleanup if a partial payload marked a new active provider:
    # clear active on untouched providers within the same llm_role group
    # (a role-specific primary must not clear a different role's primary).
    active_keys_by_role: dict[str | None, set[str]] = {}
    for item in payload.settings:
        if item.is_primary and item.is_enabled:
            active_keys_by_role.setdefault(item.llm_role, set()).add(item.provider_key)

    touched_keys = {(item.provider_key, item.llm_role) for item in payload.settings}
    if active_keys_by_role:
        for key, row in existing.items():
            if key in touched_keys:
                continue
            role_active_keys = active_keys_by_role.get(row.llm_role)
            if role_active_keys and row.provider_key not in role_active_keys:
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
    role: str | None = None,
    rows: list[ProjectLLMSetting] | None = None,
) -> list[LLMRouteConfig]:
    if rows is None:
        rows = await list_settings(db, project_id)
    eligible = [
        row for row in rows
        if row.is_enabled
        and _scope_matches(row.module_scope, module_scope)
        and (role is None or row.llm_role is None or row.llm_role == role)
    ]

    # A role-specific primary beats a generic (llm_role IS NULL) primary.
    if role is not None:
        primary = next((row for row in eligible if row.is_primary and row.llm_role == role), None)
        if primary is None:
            primary = next((row for row in eligible if row.is_primary and row.llm_role is None), None)
    else:
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
                llm_role=primary.llm_role,
            )
        )

    # Role-specific fallbacks first, then generic ones; each group ordered
    # by its own fallback_priority. Dedup by row identity (not provider_key)
    # so a same-provider row tagged for a different role isn't excluded.
    fallback_rows = sorted(
        [row for row in eligible if row.is_fallback and row.id != (primary.id if primary else None)],
        key=lambda row: (0 if (role is not None and row.llm_role == role) else 1, row.fallback_priority or 999),
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
                llm_role=row.llm_role,
            )
        )

    if role is not None:
        default_provider, default_model = role_default_route(role)
    else:
        default_provider, default_model = settings.default_llm_provider, settings.default_llm_model
    routes.append(
        LLMRouteConfig(
            provider_key=default_provider,
            provider_name=default_provider,
            model_name=default_model,
            source="system_default",
            llm_role=role,
        )
    )
    return routes


@asynccontextmanager
async def project_llm_role_context(db: AsyncSession, project_id: int) -> AsyncIterator[None]:
    """Pin each role's first resolved route as a ContextVar override for the
    duration of the block, so request-path services (AI assist, AI estimate,
    assistant chat) route by role the same way worker agents do."""
    overrides: dict[str, LLMRouteOverride] = {}
    rows = await list_settings(db, project_id)
    for role in ROLES:
        routes = await resolve_project_llm_routes(db, project_id=project_id, role=role, rows=rows)
        if not routes:
            continue
        top = routes[0]
        overrides[role] = LLMRouteOverride(
            provider=top.provider_key,
            model=top.model_name,
            temperature=top.temperature,
            max_tokens=top.max_tokens,
            timeout_seconds=top.timeout_seconds,
            role=role,
        )
    token = set_llm_role_route_overrides(overrides)
    try:
        yield
    finally:
        reset_llm_role_route_overrides(token)


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
