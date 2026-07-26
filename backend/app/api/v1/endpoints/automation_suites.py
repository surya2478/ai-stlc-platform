"""UI-018 Automation Workspace endpoints — /api/v1/lab/automation-suites/*.

Isolated namespace with the same 404-when-disabled pattern as
application_models.py / network_events.py: every route 404s when
AUTOMATION_SUITE_ENABLED is off.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DBSession, require_entity_permission, require_permission
from app.config import get_settings
from app.schemas.automation_suite import (
    AddMembersRequest,
    ApproveExceptionRequest,
    AssignExecutionGroupRequest,
    AutomationSuiteActivityOut,
    AutomationSuiteGapOut,
    AutomationSuiteOut,
    AutomationSuiteSnapshotOut,
    CreateExecutionGroupRequest,
    CreateSuiteRequest,
    DecisionRequest,
    PreviewInheritanceRequest,
    RequiredReasonRequest,
    ResolveGapRequest,
    SetDefaultEnvironmentRequest,
    SplitExecutionGroupsRequest,
    UpdateMemberRequest,
    UpdateSuiteRequest,
)
from app.services.automation_suite import dashboard as dashboard_svc
from app.services.automation_suite import lifecycle
from app.services.automation_suite import suite_service as svc
from app.services.rbac_service import (
    AUTOMATION_SUITE_APPROVE,
    AUTOMATION_SUITE_APPROVE_EXCEPTION,
    AUTOMATION_SUITE_ARCHIVE,
    AUTOMATION_SUITE_CREATE,
    AUTOMATION_SUITE_CREATE_VERSION,
    AUTOMATION_SUITE_EVALUATE,
    AUTOMATION_SUITE_EXPORT,
    AUTOMATION_SUITE_MANAGE_GROUPS,
    AUTOMATION_SUITE_MANAGE_MEMBERS,
    AUTOMATION_SUITE_PUBLISH,
    AUTOMATION_SUITE_RESOLVE_GAP,
    AUTOMATION_SUITE_REVIEW,
    AUTOMATION_SUITE_SUBMIT_REVIEW,
    AUTOMATION_SUITE_UPDATE,
    AUTOMATION_SUITE_VIEW,
    AUTOMATION_SUITE_VIEW_AUDIT,
)

router = APIRouter()


def _require_enabled() -> None:
    if not get_settings().automation_suite_enabled:
        raise HTTPException(
            status_code=404, detail="Automation Workspace is disabled (AUTOMATION_SUITE_ENABLED=false)"
        )


# ─── Landing dashboard ────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/dashboard")
async def get_dashboard(project_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    await require_permission(AUTOMATION_SUITE_VIEW, project_id, current_user, db)
    return await dashboard_svc.compute_workspace_kpis(db, project_id=project_id)


@router.get("/projects/{project_id}/active-executions")
async def get_active_executions(
    project_id: int, db: DBSession, current_user: CurrentUser, limit: int = Query(20, ge=1, le=50)
):
    _require_enabled()
    await require_permission(AUTOMATION_SUITE_VIEW, project_id, current_user, db)
    return await dashboard_svc.list_active_executions(db, project_id=project_id, limit=limit)


@router.get("/projects/{project_id}/footer-status")
async def get_footer_status(project_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    await require_permission(AUTOMATION_SUITE_VIEW, project_id, current_user, db)
    return await dashboard_svc.compute_footer_status(db, project_id=project_id)


# ─── Suite list and creation ──────────────────────────────────────────────────

@router.get("/projects/{project_id}/suites")
async def list_suites(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    search: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str = "updated_desc",
):
    _require_enabled()
    await require_permission(AUTOMATION_SUITE_VIEW, project_id, current_user, db)
    return await svc.list_suites(
        db,
        project_id=project_id,
        search=search,
        status_filter=status,
        page=page,
        page_size=page_size,
        sort=sort,
    )


@router.post("/projects/{project_id}/suites", response_model=AutomationSuiteOut)
async def create_suite(
    project_id: int, payload: CreateSuiteRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    await require_permission(AUTOMATION_SUITE_CREATE, project_id, current_user, db)
    suite, _created = await svc.create_suite(
        db,
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        test_case_ids=payload.test_case_ids,
        test_suite_ids=payload.test_suite_ids,
        default_environment=payload.default_environment,
        idempotency_key=payload.idempotency_key,
        actor_id=current_user.id,
    )
    return suite


# ─── Wizard support ───────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/selectable-test-cases")
async def list_selectable_test_cases(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    search: str | None = None,
    status: str | None = None,
    automation_status: str | None = None,
    execution_mode: str | None = None,
    automation_candidate: bool | None = None,
    test_type: str | None = None,
    priority: str | None = None,
    is_critical: bool | None = None,
    application_id: int | None = None,
    requirement_id: int | None = None,
    test_suite_id: int | None = None,
    framework: str | None = None,
    has_script: bool | None = None,
    exclude_suite_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    _require_enabled()
    await require_permission(AUTOMATION_SUITE_VIEW, project_id, current_user, db)
    return await svc.list_selectable_test_cases(
        db,
        project_id=project_id,
        search=search,
        status_filter=status,
        automation_status=automation_status,
        execution_mode=execution_mode,
        automation_candidate=automation_candidate,
        test_type=test_type,
        priority=priority,
        is_critical=is_critical,
        application_id=application_id,
        requirement_id=requirement_id,
        test_suite_id=test_suite_id,
        framework=framework,
        has_script=has_script,
        exclude_suite_id=exclude_suite_id,
        page=page,
        page_size=page_size,
    )


@router.post("/projects/{project_id}/suites/preview-inheritance")
async def preview_inheritance(
    project_id: int, payload: PreviewInheritanceRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    await require_permission(AUTOMATION_SUITE_VIEW, project_id, current_user, db)
    return await svc.preview_inheritance(
        db,
        project_id=project_id,
        test_case_ids=payload.test_case_ids,
        default_environment=payload.default_environment,
    )


# ─── Suite detail ─────────────────────────────────────────────────────────────

@router.get("/suites/{suite_id}")
async def get_suite(suite_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_VIEW, current_user, db)
    return await svc.compute_suite_overview(db, suite)


@router.patch("/suites/{suite_id}", response_model=AutomationSuiteOut)
async def update_suite(suite_id: int, payload: UpdateSuiteRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_UPDATE, current_user, db)
    return await svc.update_suite(
        db,
        suite,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        actor_id=current_user.id,
    )


@router.patch("/suites/{suite_id}/default-environment", response_model=AutomationSuiteOut)
async def set_default_environment(
    suite_id: int, payload: SetDefaultEnvironmentRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_UPDATE, current_user, db)
    return await svc.set_default_environment(
        db, suite, environment=payload.environment, actor_id=current_user.id
    )


@router.post("/suites/{suite_id}/evaluate", response_model=AutomationSuiteOut)
async def evaluate_suite(suite_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_EVALUATE, current_user, db)
    return await svc.evaluate_suite(db, suite, actor_id=current_user.id)


@router.post("/suites/{suite_id}/archive", response_model=AutomationSuiteOut)
async def archive_suite(suite_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_ARCHIVE, current_user, db)
    return await svc.archive_suite(db, suite, actor_id=current_user.id)


@router.get("/suites/{suite_id}/inherited-scope")
async def get_inherited_scope(suite_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_VIEW, current_user, db)
    return await svc.get_inherited_scope(db, suite)


# ─── Members ──────────────────────────────────────────────────────────────────

@router.get("/suites/{suite_id}/members")
async def list_members(
    suite_id: int,
    db: DBSession,
    current_user: CurrentUser,
    inclusion_status: str | None = None,
    member_status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_VIEW, current_user, db)
    return await svc.list_members(
        db,
        suite,
        inclusion_status=inclusion_status,
        member_status=member_status,
        page=page,
        page_size=page_size,
    )


@router.post("/suites/{suite_id}/members")
async def add_members(suite_id: int, payload: AddMembersRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_MANAGE_MEMBERS, current_user, db)
    return await svc.add_members(
        db,
        suite,
        test_case_ids=payload.test_case_ids,
        test_suite_ids=payload.test_suite_ids,
        actor_id=current_user.id,
    )


@router.patch("/suites/{suite_id}/members/{member_id}")
async def update_member(
    suite_id: int, member_id: int, payload: UpdateMemberRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_MANAGE_MEMBERS, current_user, db)
    member = await svc.update_member(
        db,
        suite,
        member_id,
        inclusion_status=payload.inclusion_status,
        planned_sequence=payload.planned_sequence,
        exclusion_reason=payload.exclusion_reason,
        actor_id=current_user.id,
    )
    return {"id": member.id, "inclusion_status": member.inclusion_status, "member_status": member.member_status}


@router.delete("/suites/{suite_id}/members/{member_id}")
async def remove_member(suite_id: int, member_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_MANAGE_MEMBERS, current_user, db)
    await svc.remove_member(db, suite, member_id, actor_id=current_user.id)
    return {"message": "Test case removed from suite."}


@router.get("/suites/{suite_id}/members/{member_id}/grounding")
async def get_member_grounding(suite_id: int, member_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_VIEW, current_user, db)
    return await svc.member_grounding(db, suite, member_id)


# ─── Gaps and conflicts ───────────────────────────────────────────────────────

@router.get("/suites/{suite_id}/gaps")
async def list_gaps(
    suite_id: int,
    db: DBSession,
    current_user: CurrentUser,
    category: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    member_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_VIEW, current_user, db)
    return await svc.list_gaps(
        db,
        suite,
        category=category,
        severity=severity,
        status_filter=status,
        member_id=member_id,
        page=page,
        page_size=page_size,
    )


@router.post("/suites/{suite_id}/gaps/{gap_id}/resolve", response_model=AutomationSuiteGapOut)
async def resolve_gap(
    suite_id: int, gap_id: int, payload: ResolveGapRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_RESOLVE_GAP, current_user, db)
    return await svc.resolve_gap(
        db,
        suite,
        gap_id=gap_id,
        resolution_action=payload.resolution_action,
        reviewer_notes=payload.reviewer_notes,
        actor_id=current_user.id,
    )


@router.post("/suites/{suite_id}/gaps/{gap_id}/approve-exception", response_model=AutomationSuiteGapOut)
async def approve_exception(
    suite_id: int, gap_id: int, payload: ApproveExceptionRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_APPROVE_EXCEPTION, current_user, db)
    return await svc.approve_exception(
        db, suite, gap_id=gap_id, reason=payload.reason, actor_id=current_user.id
    )


# ─── Execution groups (Phase B) ───────────────────────────────────────────────

@router.get("/suites/{suite_id}/execution-groups")
async def list_execution_groups(suite_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_VIEW, current_user, db)
    return await svc.list_execution_groups(db, suite)


@router.post("/suites/{suite_id}/execution-groups")
async def create_execution_group(
    suite_id: int, payload: CreateExecutionGroupRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_MANAGE_GROUPS, current_user, db)
    return await svc.create_execution_group(
        db,
        suite,
        name=payload.name,
        framework=payload.framework,
        environment=payload.environment,
        notes=payload.notes,
        actor_id=current_user.id,
    )


@router.post("/suites/{suite_id}/execution-groups/split")
async def split_execution_groups(
    suite_id: int, payload: SplitExecutionGroupsRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_MANAGE_GROUPS, current_user, db)
    created = await svc.split_into_execution_groups(
        db, suite, dimension=payload.dimension, actor_id=current_user.id
    )
    await svc.evaluate_suite(db, suite, actor_id=current_user.id)
    return {"groups_created": created, "dimension": payload.dimension}


@router.delete("/suites/{suite_id}/execution-groups/{group_id}")
async def delete_execution_group(
    suite_id: int, group_id: int, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_MANAGE_GROUPS, current_user, db)
    await svc.delete_execution_group(db, suite, group_id=group_id, actor_id=current_user.id)
    return {"message": "Execution group deleted."}


@router.patch("/suites/{suite_id}/members/{member_id}/execution-group")
async def assign_execution_group(
    suite_id: int,
    member_id: int,
    payload: AssignExecutionGroupRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_MANAGE_GROUPS, current_user, db)
    await svc.assign_member_to_group(
        db, suite, member_id=member_id, group_id=payload.execution_group_id, actor_id=current_user.id
    )
    return {"message": "Execution group updated."}


# ─── Approval workflow (Phase B) ──────────────────────────────────────────────

@router.post("/suites/{suite_id}/submit-for-review", response_model=AutomationSuiteOut)
async def submit_for_review(suite_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_SUBMIT_REVIEW, current_user, db)
    return await lifecycle.submit_for_review(db, suite, actor_id=current_user.id)


@router.post("/suites/{suite_id}/request-changes", response_model=AutomationSuiteOut)
async def request_changes(
    suite_id: int, payload: RequiredReasonRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_REVIEW, current_user, db)
    return await lifecycle.request_changes(db, suite, actor_id=current_user.id, reason=payload.reason)


@router.post("/suites/{suite_id}/reject", response_model=AutomationSuiteOut)
async def reject_suite(
    suite_id: int, payload: RequiredReasonRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_REVIEW, current_user, db)
    return await lifecycle.reject(db, suite, actor_id=current_user.id, reason=payload.reason)


@router.post("/suites/{suite_id}/approve", response_model=AutomationSuiteOut)
async def approve_suite(
    suite_id: int, payload: DecisionRequest, db: DBSession, current_user: CurrentUser
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_APPROVE, current_user, db)
    return await lifecycle.approve(db, suite, actor_id=current_user.id, reason=payload.reason)


@router.post("/suites/{suite_id}/publish", response_model=AutomationSuiteOut)
async def publish_suite(suite_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_PUBLISH, current_user, db)
    return await lifecycle.publish(db, suite, actor_id=current_user.id)


# ─── Versions, snapshots and impact review (Phase B) ──────────────────────────

@router.get("/suites/{suite_id}/versions")
async def list_versions(suite_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_VIEW, current_user, db)
    return {"items": await lifecycle.list_versions(db, suite)}


@router.post("/suites/{suite_id}/new-version", response_model=AutomationSuiteOut)
async def create_new_version(suite_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_CREATE_VERSION, current_user, db)
    new_suite = await lifecycle.create_new_draft(db, suite, actor_id=current_user.id)
    return await svc.evaluate_suite(db, new_suite, actor_id=current_user.id)


@router.get("/suites/{suite_id}/snapshot", response_model=AutomationSuiteSnapshotOut | None)
async def get_snapshot(suite_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_VIEW, current_user, db)
    return await lifecycle.get_snapshot(db, suite)


@router.get("/suites/{suite_id}/impact-review")
async def impact_review(suite_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_VIEW, current_user, db)
    _findings, summary = await lifecycle.detect_snapshot_drift(db, suite)
    return summary


# ─── Audit and export ─────────────────────────────────────────────────────────

@router.get("/suites/{suite_id}/activity")
async def list_activity(
    suite_id: int,
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_VIEW_AUDIT, current_user, db)
    return await svc.list_activity(db, suite, page=page, page_size=page_size)


@router.get("/suites/{suite_id}/export")
async def export_suite(suite_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    suite = await svc.get_suite_or_404(db, suite_id)
    await require_entity_permission(suite, AUTOMATION_SUITE_EXPORT, current_user, db)

    overview = await svc.compute_suite_overview(db, suite)
    inherited = await svc.get_inherited_scope(db, suite)
    members = await svc.list_members(db, suite, page=1, page_size=get_settings().automation_suite_max_members)
    gaps = await svc.list_gaps(db, suite, page=1, page_size=100)

    payload = {
        "suite": AutomationSuiteOut.model_validate(suite).model_dump(mode="json"),
        "overview": overview,
        "inherited_scope": inherited,
        "members": members["items"],
        "gaps": [AutomationSuiteGapOut.model_validate(g).model_dump(mode="json") for g in gaps["items"]],
    }
    return JSONResponse(
        content=json.loads(json.dumps(payload, default=str)),
        headers={"Content-Disposition": f'attachment; filename="automation-suite-{suite.id}.json"'},
    )
