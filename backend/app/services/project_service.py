"""Business logic for project management."""
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectStats, ProjectUpdate


class ProjectService:
    def __init__(self, db: AsyncSession):
        self.repo = ProjectRepository(db)

    async def create_project(self, data: ProjectCreate, owner_id: int) -> Project:
        project = Project(
            name=data.name,
            description=data.description,
            owner_id=owner_id,
            metadata_=data.metadata_,
        )
        return await self.repo.create(project)

    async def get_project(self, project_id: int, user_id: int) -> Project:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        # Basic ownership check — expand with RBAC in Phase 8
        if project.owner_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return project

    async def list_projects(self, owner_id: int, skip: int = 0, limit: int = 50) -> list[Project]:
        return await self.repo.get_by_owner(owner_id, skip=skip, limit=limit)

    async def update_project(self, project_id: int, data: ProjectUpdate, user_id: int) -> Project:
        project = await self.get_project(project_id, user_id)
        updates = data.model_dump(exclude_unset=True)
        return await self.repo.update(project, updates)

    async def delete_project(self, project_id: int, user_id: int) -> None:
        project = await self.get_project(project_id, user_id)
        await self.repo.delete(project)

    async def get_stats(self, project_id: int, user_id: int) -> ProjectStats:
        await self.get_project(project_id, user_id)  # auth check
        return await self.repo.get_stats(project_id)
