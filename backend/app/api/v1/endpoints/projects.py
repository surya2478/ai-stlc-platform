"""Project CRUD endpoints."""
from fastapi import APIRouter, status, Query

from app.api.deps import CurrentUser, DBSession
from app.schemas.project_membership import (
    ProjectMembershipCreate,
    ProjectMembershipOut,
    ProjectMembershipUpdate,
    ProjectRoleOut,
    available_project_roles,
)
from app.schemas.project import ProjectCreate, ProjectRead, ProjectStats, ProjectUpdate
from app.schemas.metrics import DashboardMetricsOut
from app.services.project_service import ProjectService
from app.services.metrics_service import MetricsService

router = APIRouter()


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    return await svc.create_project(data, current_user.id)


@router.get("", response_model=list[ProjectRead])
@router.get("/", response_model=list[ProjectRead])
async def list_projects(
    skip: int = 0,
    limit: int = 50,
    current_user: CurrentUser = ...,
    db: DBSession = ...,
):
    svc = ProjectService(db)
    return await svc.list_projects(current_user, skip=skip, limit=limit)


@router.get("/roles", response_model=list[ProjectRoleOut])
async def list_project_roles(current_user: CurrentUser):
    return available_project_roles()


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    return await svc.get_project(project_id, current_user)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    return await svc.update_project(project_id, data, current_user)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    await svc.delete_project(project_id, current_user)


@router.get("/{project_id}/stats", response_model=ProjectStats)
async def get_project_stats(
    project_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    return await svc.get_stats(project_id, current_user)


@router.get("/{project_id}/dashboard-metrics", response_model=DashboardMetricsOut)
async def get_project_dashboard_metrics(
    project_id: int,
    current_user: CurrentUser,
    db: DBSession,
    release_version: str | None = Query(None),
):
    await ProjectService(db).get_project(project_id, current_user)
    svc = MetricsService(db)
    return await svc.get_dashboard_metrics(project_id, release_version)


@router.get("/{project_id}/memberships", response_model=list[ProjectMembershipOut])
async def list_project_memberships(
    project_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    return await svc.list_memberships(project_id, current_user)


@router.post("/{project_id}/memberships", response_model=ProjectMembershipOut, status_code=status.HTTP_201_CREATED)
async def add_project_membership(
    project_id: int,
    data: ProjectMembershipCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    return await svc.add_membership(project_id, data, current_user)


@router.patch("/{project_id}/memberships/{membership_id}", response_model=ProjectMembershipOut)
async def update_project_membership(
    project_id: int,
    membership_id: int,
    data: ProjectMembershipUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    return await svc.update_membership(project_id, membership_id, data, current_user)


@router.delete("/{project_id}/memberships/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_membership(
    project_id: int,
    membership_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    await svc.remove_membership(project_id, membership_id, current_user)
