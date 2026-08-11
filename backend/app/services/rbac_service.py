"""Role and permission helpers for project-level RBAC."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_membership import ProjectMembership
from app.models.user import User

Permission = str

# The Test Automation Studio role. One string used in two places, which is
# why it is a constant rather than a literal: it is a *global* role on
# `users.role` (it decides which navigation groups the user sees) and a
# *project* role in ROLE_PERMISSIONS (it decides what they may do inside a
# project). Assigning it in one place without the other leaves a user who can
# see the studio but cannot act in it, or vice versa.
TEST_AUTOMATION_USER_ROLE = "Test_Automation_Users"

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

# ─── P1-S7 UI-046 Suite Execution Command Center ────────────────────────────
# Control is separated from launch: whoever may start a governed suite run is not
# automatically the person who may abort one mid-flight, and an emergency stop
# affects shared infrastructure rather than one run. Three keys, not one.
EXECUTION_CONTROL_RUN = "execution.control_run"
EXECUTION_CANCEL_RUN = "execution.cancel_run"
EXECUTION_EMERGENCY_STOP = "execution.emergency_stop"

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

# ─── UI-015 Live Discovery Session (P1-S4 extension) ─────────────────────────
DISCOVERY_VIEW = "discovery.view"
DISCOVERY_START_SESSION = "discovery.start_session"
DISCOVERY_CONTROL_SESSION = "discovery.control_session"  # pause/resume/stop/checkpoint
DISCOVERY_EMERGENCY_STOP = "discovery.emergency_stop"
DISCOVERY_CORRECT_ACTION = "discovery.correct_action"
DISCOVERY_COMPLETE_SESSION = "discovery.complete_session"

_GRANULAR_DISCOVERY_PERMISSIONS: frozenset[str] = frozenset(
    {
        DISCOVERY_VIEW,
        DISCOVERY_START_SESSION,
        DISCOVERY_CONTROL_SESSION,
        DISCOVERY_EMERGENCY_STOP,
        DISCOVERY_CORRECT_ACTION,
        DISCOVERY_COMPLETE_SESSION,
    }
)

# ─── UI-016 Application Model (P1-S4 extension) ──────────────────────────────
APPLICATION_MODEL_VIEW = "application_model.view"
APPLICATION_MODEL_BUILD = "application_model.build"
APPLICATION_MODEL_EDIT = "application_model.edit"
APPLICATION_MODEL_REVIEW = "application_model.review"
APPLICATION_MODEL_APPROVE = "application_model.approve"
APPLICATION_MODEL_PUBLISH = "application_model.publish"
APPLICATION_MODEL_RESOLVE_GAPS = "application_model.resolve_gaps"
APPLICATION_MODEL_VALIDATE_LOCATORS = "application_model.validate_locators"
APPLICATION_MODEL_EXPORT = "application_model.export"
APPLICATION_MODEL_VIEW_AUDIT = "application_model.view_audit"

_GRANULAR_APPLICATION_MODEL_PERMISSIONS: frozenset[str] = frozenset(
    {
        APPLICATION_MODEL_VIEW,
        APPLICATION_MODEL_BUILD,
        APPLICATION_MODEL_EDIT,
        APPLICATION_MODEL_REVIEW,
        APPLICATION_MODEL_APPROVE,
        APPLICATION_MODEL_PUBLISH,
        APPLICATION_MODEL_RESOLVE_GAPS,
        APPLICATION_MODEL_VALIDATE_LOCATORS,
        APPLICATION_MODEL_EXPORT,
        APPLICATION_MODEL_VIEW_AUDIT,
    }
)

# ─── UI-017 API and Network Explorer (P1-S4 extension) ───────────────────────
NETWORK_EXPLORER_VIEW = "network_explorer.view"
NETWORK_EXPLORER_BUILD = "network_explorer.build"
NETWORK_EXPLORER_REVIEW = "network_explorer.review"
NETWORK_EXPLORER_EXPORT = "network_explorer.export"
NETWORK_EXPLORER_VIEW_AUDIT = "network_explorer.view_audit"

_GRANULAR_NETWORK_EXPLORER_PERMISSIONS: frozenset[str] = frozenset(
    {
        NETWORK_EXPLORER_VIEW,
        NETWORK_EXPLORER_BUILD,
        NETWORK_EXPLORER_REVIEW,
        NETWORK_EXPLORER_EXPORT,
        NETWORK_EXPLORER_VIEW_AUDIT,
    }
)

# ─── UI-018 Automation Workspace / Automation Test Suite (P1-S5) ─────────────
AUTOMATION_SUITE_VIEW = "automation_suite.view"
AUTOMATION_SUITE_CREATE = "automation_suite.create"
AUTOMATION_SUITE_UPDATE = "automation_suite.update"
AUTOMATION_SUITE_MANAGE_MEMBERS = "automation_suite.manage_members"
AUTOMATION_SUITE_EVALUATE = "automation_suite.evaluate"
AUTOMATION_SUITE_RESOLVE_GAP = "automation_suite.resolve_gap"
AUTOMATION_SUITE_APPROVE_EXCEPTION = "automation_suite.approve_exception"
AUTOMATION_SUITE_ARCHIVE = "automation_suite.archive"
AUTOMATION_SUITE_EXPORT = "automation_suite.export"
AUTOMATION_SUITE_VIEW_AUDIT = "automation_suite.view_audit"
# ── Phase B ──
AUTOMATION_SUITE_MANAGE_GROUPS = "automation_suite.manage_groups"
AUTOMATION_SUITE_SUBMIT_REVIEW = "automation_suite.submit_review"
AUTOMATION_SUITE_REVIEW = "automation_suite.review"
AUTOMATION_SUITE_APPROVE = "automation_suite.approve"
AUTOMATION_SUITE_PUBLISH = "automation_suite.publish"
AUTOMATION_SUITE_CREATE_VERSION = "automation_suite.create_version"

# ─── UI-020/021/023 Automation Asset Workspace (P1-S5) ───────────────────────
# Authoring rides with GENERATE_AUTOMATION; governance rides with
# APPROVE_TEST_CASES — the same split UI-018 established.
AUTOMATION_ASSET_VIEW = "automation_asset.view"
AUTOMATION_ASSET_EDIT_IR = "automation_asset.edit_ir"
AUTOMATION_ASSET_COMPILE = "automation_asset.compile"
AUTOMATION_ASSET_DRY_RUN = "automation_asset.dry_run"
AUTOMATION_ASSET_ACCEPT_EXCEPTION = "automation_asset.accept_exception"
AUTOMATION_ASSET_FINAL_APPROVE = "automation_asset.final_approve"
AUTOMATION_ASSET_OVERRIDE_AUTONOMY = "automation_asset.override_autonomy"

_GRANULAR_AUTOMATION_ASSET_PERMISSIONS: frozenset[str] = frozenset(
    {
        AUTOMATION_ASSET_VIEW,
        AUTOMATION_ASSET_EDIT_IR,
        AUTOMATION_ASSET_COMPILE,
        AUTOMATION_ASSET_DRY_RUN,
        AUTOMATION_ASSET_ACCEPT_EXCEPTION,
        AUTOMATION_ASSET_FINAL_APPROVE,
        AUTOMATION_ASSET_OVERRIDE_AUTONOMY,
    }
)

# ─── UI-019 Live Recorder (P1-S5) ────────────────────────────────────────────
RECORDER_VIEW = "recorder.view"
RECORDER_START_RECORDING = "recorder.start_recording"
RECORDER_CONTROL_RECORDING = "recorder.control_recording"  # pause/resume/stop/segment
RECORDER_MAP_ACTIONS = "recorder.map_actions"  # step mapping, checkpoints, bindings, notes
RECORDER_DISCARD = "recorder.discard"
RECORDER_GENERATE_IR = "recorder.generate_ir"
RECORDER_CREATE_VERSION = "recorder.create_version"

_GRANULAR_RECORDER_PERMISSIONS: frozenset[str] = frozenset(
    {
        RECORDER_VIEW,
        RECORDER_START_RECORDING,
        RECORDER_CONTROL_RECORDING,
        RECORDER_MAP_ACTIONS,
        RECORDER_DISCARD,
        RECORDER_GENERATE_IR,
        RECORDER_CREATE_VERSION,
    }
)

# ─── Test Automation Studio (separate module) ────────────────────────────────
# The studio's own keys. They are deliberately distinct from the AUTOMATION_*
# and AUTOMATION_ASSET_* families above: those govern the existing AI
# Automation Studio's assets, and a deployment must be able to grant somebody
# the new studio without also handing them the old one.
TAS_VIEW = "tas.view"
TAS_INTAKE = "tas.intake"
TAS_ASSESS_COVERAGE = "tas.assess_coverage"
TAS_APPROVE_REQUIREMENT = "tas.approve_requirement"
TAS_REFINE_TEST_CASES = "tas.refine_test_cases"
TAS_CLASSIFY = "tas.classify"
TAS_APPROVE_TEST_CASE = "tas.approve_test_case"
TAS_GENERATE_SCRIPT = "tas.generate_script"
TAS_EDIT_SCRIPT = "tas.edit_script"
TAS_EXPORT = "tas.export"

_GRANULAR_TAS_PERMISSIONS: frozenset[str] = frozenset(
    {
        TAS_VIEW,
        TAS_INTAKE,
        TAS_ASSESS_COVERAGE,
        TAS_APPROVE_REQUIREMENT,
        TAS_REFINE_TEST_CASES,
        TAS_CLASSIFY,
        TAS_APPROVE_TEST_CASE,
        TAS_GENERATE_SCRIPT,
        TAS_EDIT_SCRIPT,
        TAS_EXPORT,
    }
)

_GRANULAR_AUTOMATION_SUITE_PERMISSIONS: frozenset[str] = frozenset(
    {
        AUTOMATION_SUITE_VIEW,
        AUTOMATION_SUITE_CREATE,
        AUTOMATION_SUITE_UPDATE,
        AUTOMATION_SUITE_MANAGE_MEMBERS,
        AUTOMATION_SUITE_EVALUATE,
        AUTOMATION_SUITE_RESOLVE_GAP,
        AUTOMATION_SUITE_APPROVE_EXCEPTION,
        AUTOMATION_SUITE_ARCHIVE,
        AUTOMATION_SUITE_EXPORT,
        AUTOMATION_SUITE_VIEW_AUDIT,
        AUTOMATION_SUITE_MANAGE_GROUPS,
        AUTOMATION_SUITE_SUBMIT_REVIEW,
        AUTOMATION_SUITE_REVIEW,
        AUTOMATION_SUITE_APPROVE,
        AUTOMATION_SUITE_PUBLISH,
        AUTOMATION_SUITE_CREATE_VERSION,
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
        EXECUTION_CONTROL_RUN,
        EXECUTION_CANCEL_RUN,
        EXECUTION_EMERGENCY_STOP,
    }
)
GRANULAR_PERMISSIONS: frozenset[str] = (
    _GRANULAR_AUTOMATION_PERMISSIONS
    | _GRANULAR_EXECUTION_PERMISSIONS
    | _GRANULAR_CLASSIFICATION_PERMISSIONS
    | _GRANULAR_DISCOVERY_PERMISSIONS
    | _GRANULAR_APPLICATION_MODEL_PERMISSIONS
    | _GRANULAR_NETWORK_EXPLORER_PERMISSIONS
    | _GRANULAR_AUTOMATION_SUITE_PERMISSIONS
    | _GRANULAR_RECORDER_PERMISSIONS
    | _GRANULAR_AUTOMATION_ASSET_PERMISSIONS
    | _GRANULAR_TAS_PERMISSIONS
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
        extra.update({
            AUTOMATION_VIEW, EXECUTION_VIEW_LIVE_RUNS, AUTOMATION_CLASSIFICATION_VIEW, DISCOVERY_VIEW,
            APPLICATION_MODEL_VIEW, APPLICATION_MODEL_EXPORT, APPLICATION_MODEL_VIEW_AUDIT,
            NETWORK_EXPLORER_VIEW, NETWORK_EXPLORER_EXPORT, NETWORK_EXPLORER_VIEW_AUDIT,
            AUTOMATION_SUITE_VIEW, AUTOMATION_SUITE_EXPORT, AUTOMATION_SUITE_VIEW_AUDIT,
            RECORDER_VIEW,
            AUTOMATION_ASSET_VIEW,
            # Reading the studio is reading project artifacts. Everything that
            # changes state in it needs one of the branches below.
            TAS_VIEW,
            TAS_EXPORT,
        })
    if GENERATE_AUTOMATION in base:
        extra.update({
            AUTOMATION_GENERATE_SCRIPT,
            AUTOMATION_EDIT_DRAFT,
            AUTOMATION_CONFIGURE_EXTERNAL_CONNECTOR,
            AUTOMATION_RUN_SANDBOX,
            AUTOMATION_CLASSIFICATION_EVALUATE,
            AUTOMATION_CLASSIFICATION_REVIEW,
            DISCOVERY_START_SESSION,
            DISCOVERY_CONTROL_SESSION,
            DISCOVERY_EMERGENCY_STOP,
            DISCOVERY_CORRECT_ACTION,
            APPLICATION_MODEL_BUILD,
            APPLICATION_MODEL_EDIT,
            APPLICATION_MODEL_RESOLVE_GAPS,
            APPLICATION_MODEL_VALIDATE_LOCATORS,
            NETWORK_EXPLORER_BUILD,
            NETWORK_EXPLORER_REVIEW,
            AUTOMATION_SUITE_CREATE,
            AUTOMATION_SUITE_UPDATE,
            AUTOMATION_SUITE_MANAGE_MEMBERS,
            AUTOMATION_SUITE_EVALUATE,
            AUTOMATION_SUITE_RESOLVE_GAP,
            AUTOMATION_SUITE_ARCHIVE,
            AUTOMATION_SUITE_MANAGE_GROUPS,
            AUTOMATION_SUITE_SUBMIT_REVIEW,
            AUTOMATION_SUITE_CREATE_VERSION,
            # Recording is engineering work, the same class as generating a
            # script — it rides with GENERATE_AUTOMATION rather than needing a
            # separate grant. Emitting the IR is part of the same act: it is a
            # deterministic transform of what was recorded, not an approval.
            RECORDER_START_RECORDING,
            RECORDER_CONTROL_RECORDING,
            RECORDER_MAP_ACTIONS,
            RECORDER_DISCARD,
            RECORDER_GENERATE_IR,
            RECORDER_CREATE_VERSION,
            # Editing the IR, compiling and dry-running are engineering work on
            # an unapproved draft — the same class as generating a script.
            AUTOMATION_ASSET_EDIT_IR,
            AUTOMATION_ASSET_COMPILE,
            AUTOMATION_ASSET_DRY_RUN,
            # Test Automation Studio authoring: uploading intake documents,
            # running the coverage assessment, refining test cases and
            # generating/editing scripts are all engineering work producing
            # unapproved drafts. The approval gates ride with the branches
            # below instead.
            TAS_INTAKE,
            TAS_ASSESS_COVERAGE,
            TAS_REFINE_TEST_CASES,
            TAS_CLASSIFY,
            TAS_GENERATE_SCRIPT,
            TAS_EDIT_SCRIPT,
        })
    if APPROVE_TEST_CASES in base:
        extra.update({
            AUTOMATION_REVIEW_SCRIPT, AUTOMATION_APPROVE_SCRIPT, AUTOMATION_CLASSIFICATION_APPROVE,
            DISCOVERY_COMPLETE_SESSION,
            APPLICATION_MODEL_REVIEW, APPLICATION_MODEL_APPROVE, APPLICATION_MODEL_PUBLISH,
            # Waiving a suite readiness gap is a governance decision, not an
            # engineering one — it rides with test-case approval, not
            # GENERATE_AUTOMATION.
            AUTOMATION_SUITE_APPROVE_EXCEPTION,
            # Reviewing, approving and publishing a suite are the same class of
            # decision. Separation of duty is enforced in the service by
            # comparing the actor against the submitter, not by the permission.
            AUTOMATION_SUITE_REVIEW,
            AUTOMATION_SUITE_APPROVE,
            AUTOMATION_SUITE_PUBLISH,
            # Accepting a gate warning, giving final approval and overriding an
            # autonomy verdict are all governance decisions on an individual
            # automation asset, so they ride with test-case approval.
            AUTOMATION_ASSET_ACCEPT_EXCEPTION,
            AUTOMATION_ASSET_FINAL_APPROVE,
            AUTOMATION_ASSET_OVERRIDE_AUTONOMY,
            # Approving a refined test case in the studio is the same class of
            # decision as approving a test case anywhere else.
            TAS_APPROVE_TEST_CASE,
        })
    if APPROVE_REQUIREMENTS in base:
        # Screen 1's bulk approve promotes studio requirements into the
        # generation flow, so it rides with requirement approval rather than
        # with test-case approval.
        extra.add(TAS_APPROVE_REQUIREMENT)
    if EXECUTE_TESTS in base:
        extra.update({EXECUTION_RUN_AUTOMATION, EXECUTION_RUN_AI_ASSISTED})
        # Pausing and gracefully stopping a run you are permitted to start is
        # part of running it — the operator watching a suite must be able to
        # halt it without escalating.
        extra.add(EXECUTION_CONTROL_RUN)
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
        # Cancelling a run mid-flight discards in-progress work and releases
        # shared runners, so it sits with project management rather than with
        # executing tests.
        #
        # EXECUTION_EMERGENCY_STOP is deliberately granted by no branch here. It
        # still reaches Project Admin, which holds ALL_PERMISSIONS, and that is
        # the correct blast radius for a project-wide kill. The capability it
        # guards ships with P2-S1; until then the endpoint refuses the action
        # with EMERGENCY_STOP_UNAVAILABLE regardless of permission.
        extra.add(EXECUTION_CANCEL_RUN)
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
    # The Test Automation Studio's own role. It owns the studio end to end —
    # intake, coverage approval, test-case approval, script generation — but
    # deliberately holds neither MANAGE_PROJECT nor EXECUTE_TESTS: this role
    # produces automation assets, it does not administer the project or run
    # suites against an environment.
    #
    # APPROVE_REQUIREMENTS and APPROVE_TEST_CASES are granted because Screens 1
    # and 2 are approval screens and a role that cannot approve cannot use
    # them. The coarse grants also expand (via _expand_role_permissions) into
    # the AUTOMATION_*/AUTOMATION_ASSET_* keys, which is intended: this role is
    # an automation role, and withholding them would leave the studio's
    # generated assets unusable everywhere else in the platform.
    TEST_AUTOMATION_USER_ROLE: frozenset(
        {
            VIEW_PROJECT,
            APPROVE_REQUIREMENTS,
            APPROVE_TEST_CASES,
            VIEW_TEST_DATA,
            CREATE_TEST_DATA,
            EDIT_TEST_DATA,
            GENERATE_TEST_DATA,
            IMPORT_TEST_DATA,
            APPROVE_TEST_DATA,
            RESERVE_TEST_DATA,
            CONSUME_TEST_DATA,
            GENERATE_AUTOMATION,
        }
    ),
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


# ─── Navigation visibility ───────────────────────────────────────────────────
# Which sidebar groups a global role may see. The frontend renders from this
# rather than deciding for itself, so hiding a group is a server decision that
# a modified client cannot undo — and so the rule lives next to the role that
# motivates it.
#
# These are the group labels in frontend/src/components/layout/Sidebar.tsx.
# A label added there must be added here too, or it will not render for
# anyone.
NAV_GROUP_OVERVIEW = "Overview"
NAV_GROUP_PLANNING = "AI Planning & Test Lab"
NAV_GROUP_AUTOMATION_LAB = "AI Automation Lab"
NAV_GROUP_EXECUTION_LAB = "AI Execution Lab"
NAV_GROUP_TEST_AUTOMATION_STUDIO = "Test Automation Studio"
NAV_GROUP_OPERATIONS = "Operations"
NAV_GROUP_KNOWLEDGE_BASE = "RAG & Knowledge Base"
NAV_GROUP_SETTINGS = "Settings"
NAV_GROUP_OTHERS = "Others"

ALL_NAV_GROUPS: tuple[str, ...] = (
    NAV_GROUP_OVERVIEW,
    NAV_GROUP_PLANNING,
    NAV_GROUP_AUTOMATION_LAB,
    NAV_GROUP_EXECUTION_LAB,
    NAV_GROUP_TEST_AUTOMATION_STUDIO,
    NAV_GROUP_OPERATIONS,
    NAV_GROUP_KNOWLEDGE_BASE,
    NAV_GROUP_SETTINGS,
    NAV_GROUP_OTHERS,
)

# The studio role's whole surface: its own studio, plus the three groups the
# requirement names. Notably absent are the Planning, Automation Lab and
# Execution Lab groups — this role works in the studio, not in the classic
# lifecycle screens.
_TEST_AUTOMATION_USER_NAV_GROUPS: tuple[str, ...] = (
    NAV_GROUP_TEST_AUTOMATION_STUDIO,
    NAV_GROUP_OPERATIONS,
    NAV_GROUP_SETTINGS,
    NAV_GROUP_OTHERS,
)

# Everyone who is neither an admin nor a studio user keeps exactly today's
# menu: every group except the new one.
_DEFAULT_NAV_GROUPS: tuple[str, ...] = tuple(
    group for group in ALL_NAV_GROUPS if group != NAV_GROUP_TEST_AUTOMATION_STUDIO
)


def navigation_groups_for_user(user: User) -> list[str]:
    """Sidebar groups this user may see, in ALL_NAV_GROUPS order."""
    if is_platform_admin(user):
        return list(ALL_NAV_GROUPS)
    if user.role == TEST_AUTOMATION_USER_ROLE:
        return list(_TEST_AUTOMATION_USER_NAV_GROUPS)
    return list(_DEFAULT_NAV_GROUPS)


def can_access_test_automation_studio(user: User) -> bool:
    """Whether the studio's routes are reachable for this user at all.

    Project-level `tas.*` permissions still gate each individual action; this
    is the coarse gate that keeps the module invisible to roles that have no
    business in it.
    """
    return is_platform_admin(user) or user.role == TEST_AUTOMATION_USER_ROLE


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
