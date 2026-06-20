"""Role and permission helpers for project-level RBAC."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_membership import ProjectMembership
from app.models.user import User

Permission = str

VIEW_PROJECT = "view_project"
MANAGE_PROJECT = "manage_project"
SYNC_JIRA = "sync_jira"
APPROVE_REQUIREMENTS = "approve_requirements"
APPROVE_TEST_PLANS = "approve_test_plans"
APPROVE_TEST_CASES = "approve_test_cases"
VIEW_TEST_DATA = "view_test_data"
CREATE_TEST_DATA = "create_test_data"
EDIT_TEST_DATA = "edit_test_data"
DELETE_TEST_DATA = "delete_test_data"
GENERATE_TEST_DATA = "generate_test_data"
IMPORT_TEST_DATA = "import_test_data"
APPROVE_TEST_DATA = "approve_test_data"
RESERVE_TEST_DATA = "reserve_test_data"
CONSUME_TEST_DATA = "consume_test_data"
MASK_TEST_DATA = "mask_test_data"
SYNC_TEST_DATA_JIRA = "sync_test_data_jira"
VIEW_SENSITIVE_TEST_DATA = "view_sensitive_test_data"
GENERATE_AUTOMATION = "generate_automation"
EXECUTE_TESTS = "execute_tests"
RAISE_DEFECTS = "raise_defects"
PUSH_DEFECTS_TO_JIRA = "push_defects_to_jira"
APPROVE_RELEASE_REPORT = "approve_release_report"
VIEW_AUDIT_LOGS = "view_audit_logs"

ALL_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        VIEW_PROJECT,
        MANAGE_PROJECT,
        SYNC_JIRA,
        APPROVE_REQUIREMENTS,
        APPROVE_TEST_PLANS,
        APPROVE_TEST_CASES,
        VIEW_TEST_DATA,
        CREATE_TEST_DATA,
        EDIT_TEST_DATA,
        DELETE_TEST_DATA,
        GENERATE_TEST_DATA,
        IMPORT_TEST_DATA,
        APPROVE_TEST_DATA,
        RESERVE_TEST_DATA,
        CONSUME_TEST_DATA,
        MASK_TEST_DATA,
        SYNC_TEST_DATA_JIRA,
        VIEW_SENSITIVE_TEST_DATA,
        GENERATE_AUTOMATION,
        EXECUTE_TESTS,
        RAISE_DEFECTS,
        PUSH_DEFECTS_TO_JIRA,
        APPROVE_RELEASE_REPORT,
        VIEW_AUDIT_LOGS,
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "Project Admin": ALL_PERMISSIONS,
    "QA Manager": frozenset(
        {
            VIEW_PROJECT,
            MANAGE_PROJECT,
            SYNC_JIRA,
            APPROVE_REQUIREMENTS,
            APPROVE_TEST_PLANS,
            APPROVE_TEST_CASES,
            VIEW_TEST_DATA,
            CREATE_TEST_DATA,
            EDIT_TEST_DATA,
            DELETE_TEST_DATA,
            GENERATE_TEST_DATA,
            IMPORT_TEST_DATA,
            APPROVE_TEST_DATA,
            RESERVE_TEST_DATA,
            CONSUME_TEST_DATA,
            MASK_TEST_DATA,
            SYNC_TEST_DATA_JIRA,
            VIEW_SENSITIVE_TEST_DATA,
            GENERATE_AUTOMATION,
            EXECUTE_TESTS,
            RAISE_DEFECTS,
            PUSH_DEFECTS_TO_JIRA,
            APPROVE_RELEASE_REPORT,
            VIEW_AUDIT_LOGS,
        }
    ),
    "Test Lead": frozenset(
        {
            VIEW_PROJECT,
            APPROVE_TEST_PLANS,
            APPROVE_TEST_CASES,
            VIEW_TEST_DATA,
            CREATE_TEST_DATA,
            EDIT_TEST_DATA,
            GENERATE_TEST_DATA,
            IMPORT_TEST_DATA,
            APPROVE_TEST_DATA,
            RESERVE_TEST_DATA,
            CONSUME_TEST_DATA,
            MASK_TEST_DATA,
            VIEW_SENSITIVE_TEST_DATA,
            GENERATE_AUTOMATION,
            EXECUTE_TESTS,
            RAISE_DEFECTS,
            VIEW_AUDIT_LOGS,
        }
    ),
    "Tester": frozenset({VIEW_PROJECT, VIEW_TEST_DATA, RESERVE_TEST_DATA, CONSUME_TEST_DATA, EXECUTE_TESTS, RAISE_DEFECTS}),
    "Automation Engineer": frozenset({VIEW_PROJECT, VIEW_TEST_DATA, CREATE_TEST_DATA, GENERATE_TEST_DATA, RESERVE_TEST_DATA, CONSUME_TEST_DATA, GENERATE_AUTOMATION, EXECUTE_TESTS}),
    "Release Manager": frozenset({VIEW_PROJECT, VIEW_TEST_DATA, APPROVE_RELEASE_REPORT, VIEW_AUDIT_LOGS}),
    "Defect Manager": frozenset({VIEW_PROJECT, VIEW_TEST_DATA, RAISE_DEFECTS, PUSH_DEFECTS_TO_JIRA, VIEW_AUDIT_LOGS}),
    "Business Analyst": frozenset({VIEW_PROJECT, VIEW_TEST_DATA, APPROVE_REQUIREMENTS}),
    "Viewer/Auditor": frozenset({VIEW_PROJECT, VIEW_AUDIT_LOGS}),
}

GLOBAL_ADMIN_ROLES = {"admin", "platform_admin", "Platform Admin"}


def is_platform_admin(user: User) -> bool:
    return bool(user.is_superuser or user.role in GLOBAL_ADMIN_ROLES)


async def get_project_membership(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
) -> ProjectMembership | None:
    result = await db.execute(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user_id,
            ProjectMembership.is_active.is_(True),
        )
    )
    membership = result.scalar_one_or_none()
    return membership if isinstance(membership, ProjectMembership) else None


async def list_user_memberships(db: AsyncSession, user_id: int) -> list[ProjectMembership]:
    result = await db.execute(
        select(ProjectMembership)
        .where(ProjectMembership.user_id == user_id, ProjectMembership.is_active.is_(True))
        .order_by(ProjectMembership.project_id.asc())
    )
    return list(result.scalars().all())


def permissions_for_role(role: str) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())


async def user_permissions_for_project(db: AsyncSession, user: User, project_id: int) -> frozenset[Permission]:
    if is_platform_admin(user):
        return ALL_PERMISSIONS
    membership = await get_project_membership(db, project_id=project_id, user_id=user.id)
    if not membership:
        return frozenset()
    return permissions_for_role(membership.role)


async def user_has_permission(db: AsyncSession, user: User, project_id: int, permission: Permission) -> bool:
    return permission in await user_permissions_for_project(db, user, project_id)
