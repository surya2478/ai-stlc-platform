"""Project CRUD endpoints."""
from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DBSession
from app.schemas.project import ProjectCreate, ProjectRead, ProjectStats, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter()


@router.post("/", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    return await svc.create_project(data, current_user.id)


@router.get("/", response_model=list[ProjectRead])
async def list_projects(
    skip: int = 0,
    limit: int = 50,
    current_user: CurrentUser = ...,
    db: DBSession = ...,
):
    svc = ProjectService(db)
    return await svc.list_projects(current_user.id, skip=skip, limit=limit)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    return await svc.get_project(project_id, current_user.id)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    return await svc.update_project(project_id, data, current_user.id)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    await svc.delete_project(project_id, current_user.id)


@router.get("/{project_id}/stats", response_model=ProjectStats)
async def get_project_stats(
    project_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = ProjectService(db)
    return await svc.get_stats(project_id, current_user.id)
