from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_application import ProjectApplication, ProjectExternalDependency
from app.models.llm_settings import ProjectSettingAuditLog
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.schemas.applications import (
    ProjectApplicationUpdate,
    ProjectApplicationsUpdateRequest,
    ProjectExternalDependencyUpdate,
    ProjectExternalDependenciesUpdateRequest,
)

_FALLBACK_ENVIRONMENTS = ["development", "staging", "production", "ci"]


def _application_snapshot(app: ProjectApplication) -> dict[str, Any]:
    return {
        "id": app.id,
        "project_id": app.project_id,
        "key": app.key,
        "name": app.name,
        "description": app.description,
        "is_default": app.is_default,
        "environment_urls": app.environment_urls or {},
        "is_active": app.is_active,
        "updated_by": app.updated_by,
        "updated_at": app.updated_at.isoformat() if app.updated_at else None,
    }


def _dependency_snapshot(dep: ProjectExternalDependency) -> dict[str, Any]:
    return {
        "id": dep.id,
        "project_id": dep.project_id,
        "application_id": dep.application_id,
        "service_name": dep.service_name,
        "note": dep.note,
        "sandbox_url": dep.sandbox_url,
        "mock_strategy": dep.mock_strategy,
        "is_active": dep.is_active,
        "updated_by": dep.updated_by,
        "updated_at": dep.updated_at.isoformat() if dep.updated_at else None,
    }


def _validate_application_updates(updates: list[ProjectApplicationUpdate]) -> None:
    keys = [item.key for item in updates]
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        raise HTTPException(status_code=422, detail=f"Duplicate application key(s): {', '.join(sorted(dupes))}")

    defaults = [item for item in updates if item.is_default and item.is_active]
    if len(defaults) > 1:
        raise HTTPException(status_code=400, detail="Only one application can be the default per project.")


async def list_applications(db: AsyncSession, project_id: int) -> list[ProjectApplication]:
    result = await db.execute(
        select(ProjectApplication)
        .where(ProjectApplication.project_id == project_id)
        .order_by(ProjectApplication.name.asc())
    )
    return list(result.scalars().all())


async def list_external_dependencies(db: AsyncSession, project_id: int) -> list[ProjectExternalDependency]:
    result = await db.execute(
        select(ProjectExternalDependency)
        .where(ProjectExternalDependency.project_id == project_id)
        .order_by(ProjectExternalDependency.service_name.asc())
    )
    return list(result.scalars().all())


async def resolve_default_application(db: AsyncSession, project_id: int) -> ProjectApplication | None:
    result = await db.execute(
        select(ProjectApplication).where(
            ProjectApplication.project_id == project_id,
            ProjectApplication.is_default.is_(True),
            ProjectApplication.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


def resolve_environment_url(application: ProjectApplication | None, environment: str | None) -> str | None:
    if not application or not application.environment_urls or not environment:
        return None
    url = application.environment_urls.get(environment)
    return url.strip() if isinstance(url, str) and url.strip() else None


async def resolve_application_context(
    db: AsyncSession, *, project_id: int, requirement: Requirement | None
) -> dict:
    """Resolve a real application URL (+ any scraped page analysis) to ground
    AI-generated scenario/test-case text, instead of letting the LLM invent a
    placeholder domain like example.com.

    Precedence: the requirement's own scraped source_url (most specific — the
    actual page the requirement came from) and its ui_analysis, then the
    project's default ProjectApplication URL, else nothing (callers must
    instruct the user to configure one).
    """
    metadata = (requirement.metadata_ or {}) if requirement else {}
    source_url = metadata.get("source_url")
    if isinstance(source_url, str) and source_url.strip():
        return {
            "url": source_url.strip(),
            "source": "requirement",
            "ui_analysis": metadata.get("ui_analysis"),
        }

    application = await resolve_default_application(db, project_id)
    if application and application.environment_urls:
        # Text grounding doesn't need per-environment precision — pick any
        # configured URL; the execution-time chain (automation_tasks.py)
        # already re-resolves the correct one per run.environment for actual
        # script runs.
        url = next(
            (v.strip() for v in application.environment_urls.values() if isinstance(v, str) and v.strip()),
            None,
        )
        if url:
            return {"url": url, "source": "project_default", "ui_analysis": None}

    return {"url": None, "source": None, "ui_analysis": None}


async def build_test_case_application_context(db: AsyncSession, tc: TestCase) -> dict:
    """Resolve the application a test case targets (falling back to the
    project's default application when untagged) so script generation can be
    told a real application exists instead of inventing a placeholder domain.

    Deliberately does NOT resolve an environment-specific URL here — that
    stays exclusively at execution time (automation_tasks.py), which already
    re-resolves per run.environment. Generation only needs to know whether a
    real base URL will be available and what to mock.
    """
    application: ProjectApplication | None = None
    if tc.application_id:
        application = await db.get(ProjectApplication, tc.application_id)
    if application is None:
        application = await resolve_default_application(db, tc.project_id)

    external_dependencies: list[dict] = []
    if application is not None:
        result = await db.execute(
            select(ProjectExternalDependency).where(
                ProjectExternalDependency.project_id == tc.project_id,
                ProjectExternalDependency.is_active.is_(True),
                (ProjectExternalDependency.application_id == application.id)
                | (ProjectExternalDependency.application_id.is_(None)),
            )
        )
        external_dependencies = [
            {
                "service_name": dep.service_name,
                "mock_strategy": dep.mock_strategy,
                "sandbox_url": dep.sandbox_url,
            }
            for dep in result.scalars().all()
        ]

    return {
        "application_name": application.name if application else None,
        "has_configured_base_url": bool(application and application.environment_urls),
        "external_dependencies": external_dependencies,
    }


async def build_project_applications_response(db: AsyncSession, project_id: int) -> dict:
    applications = await list_applications(db, project_id)
    dependencies = await list_external_dependencies(db, project_id)

    available_environments = sorted({env for app in applications for env in (app.environment_urls or {})})
    if not available_environments:
        available_environments = list(_FALLBACK_ENVIRONMENTS)

    all_rows = [*applications, *dependencies]
    last_updated_row = max(all_rows, key=lambda r: r.updated_at or r.created_at, default=None)

    return {
        "project_id": project_id,
        "applications": applications,
        "external_dependencies": dependencies,
        "available_environments": available_environments,
        "last_updated": last_updated_row.updated_at if last_updated_row else None,
        "updated_by": last_updated_row.updated_by if last_updated_row else None,
    }


async def update_project_applications(
    db: AsyncSession,
    *,
    project_id: int,
    payload: ProjectApplicationsUpdateRequest,
    user_id: int,
    source: str = "ui",
) -> dict:
    _validate_application_updates(payload.applications)

    existing = {item.key: item for item in await list_applications(db, project_id)}
    old_snapshot = [_application_snapshot(item) for item in existing.values()]

    payload_keys = {item.key for item in payload.applications}
    new_default_keys = {item.key for item in payload.applications if item.is_default and item.is_active}

    for item in payload.applications:
        row = existing.get(item.key)
        if row is None:
            row = ProjectApplication(project_id=project_id, key=item.key, created_by=user_id)
            db.add(row)
        row.name = item.name
        row.description = item.description
        row.environment_urls = item.environment_urls
        row.is_active = item.is_active
        row.is_default = item.is_default and item.is_active
        row.updated_by = user_id

    # Clear default on any untouched row when a new default was set in this payload.
    if new_default_keys:
        for key, row in existing.items():
            if key not in payload_keys:
                row.is_default = False

    await db.flush()
    new_rows = await list_applications(db, project_id)
    audit = ProjectSettingAuditLog(
        project_id=project_id,
        setting_type="applications",
        old_value={"applications": old_snapshot},
        new_value={"applications": [_application_snapshot(item) for item in new_rows]},
        changed_by=user_id,
        source=source,
        change_reason=payload.change_reason,
    )
    db.add(audit)
    await db.flush()
    return await build_project_applications_response(db, project_id)


async def update_project_external_dependencies(
    db: AsyncSession,
    *,
    project_id: int,
    payload: ProjectExternalDependenciesUpdateRequest,
    user_id: int,
    source: str = "ui",
) -> dict:
    existing = {item.id: item for item in await list_external_dependencies(db, project_id)}
    old_snapshot = [_dependency_snapshot(item) for item in existing.values()]

    kept_ids: set[int] = set()
    for item in payload.dependencies:
        row = None
        item_id = getattr(item, "id", None)
        if item_id is not None:
            row = existing.get(item_id)
        if row is None:
            row = ProjectExternalDependency(project_id=project_id, created_by=user_id)
            db.add(row)
        else:
            kept_ids.add(row.id)
        row.application_id = item.application_id
        row.service_name = item.service_name
        row.note = item.note
        row.sandbox_url = item.sandbox_url
        row.mock_strategy = item.mock_strategy
        row.is_active = item.is_active
        row.updated_by = user_id

    # Rows present before this update but omitted from the payload are treated
    # as removed — soft-delete via is_active rather than a hard DELETE so any
    # historical audit snapshot referencing them stays meaningful.
    for dep_id, row in existing.items():
        if dep_id not in kept_ids:
            row.is_active = False
            row.updated_by = user_id

    await db.flush()
    new_rows = await list_external_dependencies(db, project_id)
    audit = ProjectSettingAuditLog(
        project_id=project_id,
        setting_type="external_dependencies",
        old_value={"dependencies": old_snapshot},
        new_value={"dependencies": [_dependency_snapshot(item) for item in new_rows]},
        changed_by=user_id,
        source=source,
        change_reason=payload.change_reason,
    )
    db.add(audit)
    await db.flush()
    return await build_project_applications_response(db, project_id)
