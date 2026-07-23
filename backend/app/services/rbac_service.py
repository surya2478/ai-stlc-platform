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

# ─── Phase 5: granular AI Automation Studio / Execution permissions ──────────
# Aspirational — endpoints still guard on the coarse GENERATE_AUTOMATION /
# EXECUTE_TESTS keys today. These finer-grained keys are mapped into existing
# roles so nobody loses access; a future phase can move endpoint guards over
# key by key without a role migration.
AUTOMATION_VIEW = "automation.view"
AUTOMATION_GENERATE_SCRIPT = "automation.generate_script"
AUTOMATION_EDIT_DRAFT = "automation.edit_draft"
AUTOMATION_REVIEW_SCRIPT = "automation.review_script"
AUTOMATION_APPROVE_SCRIPT = "automation.approve_script"
# Phase 4.6: gates the "Environment Owner" step in the staged automation
# script approval chain (dry_run_passed -> reviewer_approved -> lead_approved
# -> [environment_approve, required when environmentProfile == PROD_SANITY]
# -> ci_ready). Distinct from AUTOMATION_APPROVE_SCRIPT since a PROD
# environment sign-off is a different accountability than lead review.
AUTOMATION_APPROVE_ENVIRONMENT = "automation.approve_environment"
AUTOMATION_CONFIGURE_EXTERNAL_CONNECTOR = "automation.configure_external_connector"
AUTOMATION_RUN_SANDBOX = "automation.run_sandbox"
EXECUTION_RUN_AUTOMATION = "execution.run_automation"
EXECUTION_RUN_AI_ASSISTED = "execution.run_ai_assisted"
EXECUTION_VIEW_LIVE_RUNS = "execution.view_live_runs"
EXECUTION_CREATE_DEFECT_DRAFT = "execution.create_defect_draft"

# ─── Test Automation Classification & Routing (P1-S3 extension) ─────────────
AUTOMATION_CLASSIFICATION_VIEW = "automation_classification.view"
AUTOMATION_CLASSIFICATION_EVALUATE = "automation_classification.evaluate"
AUTOMATION_CLASSIFICATION_REVIEW = "automation_classification.review"
AUTOMATION_CLASSIFICATION_APPROVE = "automation_classification.approve"
AUTOMATION_CLASSIFICATION_OVERRIDE = "automation_classification.override"
AUTOMATION_CLASSIFICATION_SIMULATE_POLICY = "automation_classification.simulate_policy"
AUTOMATION_CLASSIFICATION_MANAGE_POLICY = "automation_classification.manage_policy"

_GRANULAR_CLASSIFICATION_PERMISSIONS: frozenset[str] = frozenset(
    {
        AUTOMATION_CLASSIFICATION_VIEW,
        AUTOMATION_CLASSIFICATION_EVALUATE,
        AUTOMATION_CLASSIFICATION_REVIEW,
        AUTOMATION_CLASSIFICATION_APPROVE,
        AUTOMATION_CLASSIFICATION_OVERRIDE,
        AUTOMATION_CLASSIFICATION_SIMULATE_POLICY,
        AUTOMATION_CLASSIFICATION_MANAGE_POLICY,
    }
)

_GRANULAR_AUTOMATION_PERMISSIONS: frozenset[str] = frozenset(
    {
        AUTOMATION_VIEW,
        AUTOMATION_GENERATE_SCRIPT,
        AUTOMATION_EDIT_DRAFT,
        AUTOMATION_REVIEW_SCRIPT,
        AUTOMATION_APPROVE_SCRIPT,
        AUTOMATION_APPROVE_ENVIRONMENT,
        AUTOMATION_CONFIGURE_EXTERNAL_CONNECTOR,
        AUTOMATION_RUN_SANDBOX,
    }
)
_GRANULAR_EXECUTION_PERMISSIONS: frozenset[str] = frozenset(
    {
        EXECUTION_RUN_AUTOMATION,
        EXECUTION_RUN_AI_ASSISTED,
        EXECUTION_VIEW_LIVE_RUNS,
        EXECUTION_CREATE_DEFECT_DRAFT,
    }
)
GRANULAR_PERMISSIONS: frozenset[str] = (
    _GRANULAR_AUTOMATION_PERMISSIONS | _GRANULAR_EXECUTION_PERMISSIONS | _GRANULAR_CLASSIFICATION_PERMISSIONS
)

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
) | GRANULAR_PERMISSIONS

def _expand_role_permissions(base: frozenset[Permission]) -> frozenset[Permission]:
    """Derive the Phase-5 granular permissions from a role's coarse grants.

    Rule: anyone who has a coarse permission today keeps the equivalent
    granular ability. This preserves existing user access when endpoint
    guards eventually migrate to the granular keys. Applied uniformly to
    every role via the ROLE_PERMISSIONS comprehension below.
    """
    extra: set[Permission] = set()
    if VIEW_PROJECT in base:
        extra.update({AUTOMATION_VIEW, EXECUTION_VIEW_LIVE_RUNS, AUTOMATION_CLASSIFICATION_VIEW})
    if GENERATE_AUTOMATION in base:
        extra.update({
            AUTOMATION_GENERATE_SCRIPT,
            AUTOMATION_EDIT_DRAFT,
            AUTOMATION_CONFIGURE_EXTERNAL_CONNECTOR,
            AUTOMATION_RUN_SANDBOX,
            AUTOMATION_CLASSIFICATION_EVALUATE,
            AUTOMATION_CLASSIFICATION_REVIEW,
        })
    if APPROVE_TEST_CASES in base:
        extra.update({AUTOMATION_REVIEW_SCRIPT, AUTOMATION_APPROVE_SCRIPT, AUTOMATION_CLASSIFICATION_APPROVE})
    if EXECUTE_TESTS in base:
        extra.update({EXECUTION_RUN_AUTOMATION, EXECUTION_RUN_AI_ASSISTED})
    if RAISE_DEFECTS in base:
        extra.add(EXECUTION_CREATE_DEFECT_DRAFT)
    if APPROVE_RELEASE_REPORT in base:
        # Release-report approvers are the natural "Environment Owner" for
        # the automation approval chain's PROD_SANITY gate.
        extra.add(AUTOMATION_APPROVE_ENVIRONMENT)
    if MANAGE_PROJECT in base:
        # Phase-1 policy drawer editing/simulation and separation-of-duty
        # override — not the future UI-055 admin screen, just this drawer.
        extra.update({AUTOMATION_CLASSIFICATION_MANAGE_POLICY, AUTOMATION_CLASSIFICATION_SIMULATE_POLICY, AUTOMATION_CLASSIFICATION_OVERRIDE})
    return base | frozenset(extra)


_BASE_ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
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

# Phase 5: expand every role with derived granular permissions in one place.
# Downstream reads (user_permissions_for_project, permissions_for_role) see
# both coarse and granular keys transparently.
ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    role: _expand_role_permissions(perms)
    for role, perms in _BASE_ROLE_PERMISSIONS.items()
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
