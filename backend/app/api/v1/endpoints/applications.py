"""Project-scoped Applications, Environments & External Dependencies endpoints."""
from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession, require_permission, require_project_access
from app.schemas.applications import (
    ProjectApplicationsResponse,
    ProjectApplicationsSummary,
    ProjectApplicationsUpdateRequest,
    ProjectExternalDependenciesUpdateRequest,
    ProjectSettingAuditLogOut,
)
from app.services.project_application_service import (
    build_project_applications_response,
    build_registry_summary,
    list_application_audit_log,
    seed_canonical_applications,
    update_project_applications,
    update_project_external_dependencies,
)
from app.services.rbac_service import MANAGE_PROJECT

router = APIRouter()


@router.get("/projects/{project_id}/applications", response_model=ProjectApplicationsResponse)
async def get_project_applications(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_project_access(project_id, current_user, db)
    return await build_project_applications_response(db, project_id)


@router.get("/projects/{project_id}/applications/summary", response_model=ProjectApplicationsSummary)
async def get_project_applications_summary(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_project_access(project_id, current_user, db)
    return await build_registry_summary(db, project_id)


@router.get("/projects/{project_id}/applications/audit-log", response_model=list[ProjectSettingAuditLogOut])
async def get_project_applications_audit_log(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_project_access(project_id, current_user, db)
    return await list_application_audit_log(db, project_id)


@router.post("/projects/{project_id}/applications/seed-canonical", response_model=ProjectApplicationsResponse)
async def post_seed_canonical_applications(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_permission(MANAGE_PROJECT, project_id, current_user, db)
    return await seed_canonical_applications(db, project_id, current_user.id)


@router.put("/projects/{project_id}/applications", response_model=ProjectApplicationsResponse)
async def put_project_applications(
    project_id: int,
    payload: ProjectApplicationsUpdateRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_permission(MANAGE_PROJECT, project_id, current_user, db)
    return await update_project_applications(
        db,
        project_id=project_id,
        payload=payload,
        user_id=current_user.id,
        source="ui",
    )


@router.put("/projects/{project_id}/external-dependencies", response_model=ProjectApplicationsResponse)
async def put_project_external_dependencies(
    project_id: int,
    payload: ProjectExternalDependenciesUpdateRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_permission(MANAGE_PROJECT, project_id, current_user, db)
    return await update_project_external_dependencies(
        db,
        project_id=project_id,
        payload=payload,
        user_id=current_user.id,
        source="ui",
    )
