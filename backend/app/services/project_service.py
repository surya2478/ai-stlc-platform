"""Business logic for project management and membership RBAC."""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectStats, ProjectUpdate
from app.schemas.project_membership import ProjectMembershipCreate, ProjectMembershipUpdate
from app.services.rbac_service import (
    MANAGE_PROJECT,
    ROLE_PERMISSIONS,
    VIEW_PROJECT,
    is_platform_admin,
    user_has_permission,
)


class ProjectService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ProjectRepository(db)

    async def create_project(self, data: ProjectCreate, owner_id: int) -> Project:
        project = Project(
            name=data.name,
            description=data.description,
            owner_id=owner_id,
            metadata_=data.metadata_,
            # HP PPM & Governance fields
            ppm_id=data.ppm_id,
            project_manager_name=data.project_manager_name,
            business_pm_name=data.business_pm_name,
            domain=data.domain,
        )
        project = await self.repo.create(project)
        self.db.add(ProjectMembership(project_id=project.id, user_id=owner_id, role="Project Admin"))
        await self.db.flush()
        return project

    async def get_project(self, project_id: int, user: User) -> Project:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        if project.owner_id == user.id or await user_has_permission(self.db, user, project_id, VIEW_PROJECT):
            return project
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    async def require_manage_project(self, project_id: int, user: User) -> Project:
        project = await self.get_project(project_id, user)
        if project.owner_id == user.id or await user_has_permission(self.db, user, project_id, MANAGE_PROJECT):
            return project
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    async def list_projects(self, user: User, skip: int = 0, limit: int = 50) -> list[Project]:
        if is_platform_admin(user):
            return await self.repo.get_all_projects(skip=skip, limit=limit)
        return await self.repo.get_visible_to_user(user.id, skip=skip, limit=limit)

    async def update_project(self, project_id: int, data: ProjectUpdate, user: User) -> Project:
        project = await self.require_manage_project(project_id, user)
        updates = data.model_dump(exclude_unset=True)
        return await self.repo.update(project, updates)

    async def delete_project(self, project_id: int, user: User) -> None:
        project = await self.require_manage_project(project_id, user)

        # Delete child records in dependency order using parameterised ORM deletes.
        # This avoids the SQL-injection risk of text(f"DELETE FROM {table}").
        from sqlalchemy import delete as sa_delete
        from app.models.artifact import Artifact
        from app.models.approval import ApprovalAction
        from app.models.agent import AgentRun, AgentLog
        from app.models.report import Report
        from app.models.execution import ExecutionRun, ExecutionResult
        from app.models.automation_script import AutomationScript
        from app.models.automation_mapping import AutomationTestMapping
        from app.models.test_case import TestCase, TestCaseHistory
        from app.models.test_data import TestData, TestDataImportPreview, TestDataRecord, TestDataTemplate
        from app.models.test_plan import TestPlan
        from app.models.test_scenario import TestScenario
        from app.models.requirement import Requirement, RequirementChunk
        from app.models.requirement_review import RequirementQualityReview
        from app.models.defect import DefectDraft, JiraDefect
        from app.models.document import UploadedDocument
        from app.models.project_membership import ProjectMembership
        from app.models.jira_connection import JiraConnection
        from app.models.jira_sync import ConflictRecord, JiraSyncHistory, WebhookEvent
        from app.models.artifact_lineage import ArtifactLineage
        from app.models.rag import KnowledgeChunk, ArtifactCitation, RagRetrievalEvent

        # Leaf tables first (no outward FKs to other project-scoped tables)
        for model in (
            AgentLog,           # FK → agent_runs
            ArtifactLineage,
            ArtifactCitation,    # FK → knowledge_chunks, must precede it
            RagRetrievalEvent,
            KnowledgeChunk,
            ApprovalAction,
            ConflictRecord,
            JiraSyncHistory,
            JiraDefect,
            RequirementChunk,
            RequirementQualityReview,
            DefectDraft,
            AutomationTestMapping,
            ExecutionResult,
            TestCaseHistory,
            TestDataRecord,
            TestDataTemplate,
            TestDataImportPreview,
            TestData,
            Artifact,
            Report,
            ExecutionRun,
            AutomationScript,
            TestCase,
            TestScenario,
            TestPlan,
            Requirement,
            UploadedDocument,
            AgentRun,
            JiraConnection,
            WebhookEvent,
            ProjectMembership,
        ):
            # Only delete if the model has a project_id column (all listed models do)
            await self.db.execute(
                sa_delete(model).where(model.project_id == project_id)
            )

        await self.repo.delete(project)

    async def get_stats(self, project_id: int, user: User) -> ProjectStats:
        await self.get_project(project_id, user)
        return await self.repo.get_stats(project_id)

    async def list_memberships(self, project_id: int, user: User) -> list[ProjectMembership]:
        await self.require_manage_project(project_id, user)
        result = await self.db.execute(
            select(ProjectMembership)
            .where(ProjectMembership.project_id == project_id)
            .order_by(ProjectMembership.created_at.asc())
        )
        return list(result.scalars().all())

    async def add_membership(
        self,
        project_id: int,
        data: ProjectMembershipCreate,
        user: User,
    ) -> ProjectMembership:
        await self.require_manage_project(project_id, user)
        if data.role not in ROLE_PERMISSIONS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid project role")

        target = await self.db.get(User, data.user_id)
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        result = await self.db.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == data.user_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.role = data.role
            existing.is_active = True
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        membership = ProjectMembership(project_id=project_id, user_id=data.user_id, role=data.role)
        self.db.add(membership)
        await self.db.flush()
        await self.db.refresh(membership)
        return membership

    async def update_membership(
        self,
        project_id: int,
        membership_id: int,
        data: ProjectMembershipUpdate,
        user: User,
    ) -> ProjectMembership:
        project = await self.require_manage_project(project_id, user)
        result = await self.db.execute(
            select(ProjectMembership).where(
                ProjectMembership.id == membership_id,
                ProjectMembership.project_id == project_id,
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
        if membership.user_id == project.owner_id and data.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Project owner membership cannot be disabled",
            )
        if data.role is not None:
            if data.role not in ROLE_PERMISSIONS:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid project role")
            membership.role = data.role
        if data.is_active is not None:
            membership.is_active = data.is_active
        await self.db.flush()
        await self.db.refresh(membership)
        return membership

    async def remove_membership(self, project_id: int, membership_id: int, user: User) -> None:
        await self.update_membership(
            project_id,
            membership_id,
            ProjectMembershipUpdate(is_active=False),
            user,
        )
