from sqlalchemy import or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.defect import DefectDraft
from app.repositories.base_repository import BaseRepository
from app.schemas.project import ProjectStats


class ProjectRepository(BaseRepository[Project]):
    def __init__(self, db: AsyncSession):
        super().__init__(Project, db)

    async def get_by_owner(self, owner_id: int, skip: int = 0, limit: int = 100) -> list[Project]:
        result = await self.db.execute(
            select(Project)
            .where(Project.owner_id == owner_id)
            .offset(skip)
            .limit(limit)
            .order_by(Project.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_visible_to_user(self, user_id: int, skip: int = 0, limit: int = 100) -> list[Project]:
        result = await self.db.execute(
            select(Project)
            .outerjoin(
                ProjectMembership,
                (ProjectMembership.project_id == Project.id)
                & (ProjectMembership.user_id == user_id)
                & (ProjectMembership.is_active.is_(True)),
            )
            .where(or_(Project.owner_id == user_id, ProjectMembership.id.is_not(None)))
            .order_by(Project.created_at.desc())
            .offset(skip)
            .limit(limit)
            .distinct()
        )
        return list(result.scalars().all())

    async def get_all_projects(self, skip: int = 0, limit: int = 100) -> list[Project]:
        result = await self.db.execute(
            select(Project).order_by(Project.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def get_stats(self, project_id: int) -> ProjectStats:
        req_count = await self.db.scalar(
            select(func.count()).select_from(Requirement).where(Requirement.project_id == project_id)
        ) or 0
        tc_count = await self.db.scalar(
            select(func.count()).select_from(TestCase).where(TestCase.project_id == project_id)
        ) or 0
        defect_count = await self.db.scalar(
            select(func.count()).select_from(DefectDraft)
            .where(DefectDraft.project_id == project_id)
            .where(DefectDraft.status.notin_(["pushed_to_jira", "rejected"]))
        ) or 0
        return ProjectStats(
            project_id=project_id,
            total_requirements=req_count,
            total_test_cases=tc_count,
            open_defects=defect_count,
        )
