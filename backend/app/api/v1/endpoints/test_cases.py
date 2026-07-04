"""Direct Test Case endpoints.

The legacy API exposes test cases under /test-plans/cases. These aliases provide
the cleaner /test-cases contract while using the same service and RBAC rules.
"""
from fastapi import APIRouter, HTTPException, Query

from app.api.deps import (
    CurrentUser,
    DBSession,
    require_entity_permission,
    require_entity_project_access,
    require_permission,
    require_project_access,
)
from app.core import audit_logger
from app.schemas.test_plan import (
    TestCaseBulkUpdateRequest,
    TestCaseBulkUpdateResult,
    TestCaseHistoryOut,
    TestCaseJiraSyncOut,
    TestCaseOut,
    TestCaseSummaryOut,
    TestCaseUpdate,
)
from app.services import test_plan_service
from app.services.rbac_service import APPROVE_TEST_CASES, SYNC_JIRA

router = APIRouter()


@router.get("/projects/{project_id}", response_model=list[TestCaseOut])
async def list_project_test_cases(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    scenario_id: int | None = Query(None),
    requirement_id: int | None = Query(None),
    status: str | None = Query(None),
    automation_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    await require_project_access(project_id, current_user, db)
    return await test_plan_service.list_test_cases(db, project_id, scenario_id, requirement_id, status, automation_only, skip, limit)


@router.get("/projects/{project_id}/summary", response_model=TestCaseSummaryOut)
async def project_test_case_summary(project_id: int, db: DBSession, current_user: CurrentUser):
    await require_project_access(project_id, current_user, db)
    return await test_plan_service.test_case_summary(db, project_id)


@router.get("/{tc_id}", response_model=TestCaseOut)
async def get_test_case(tc_id: int, db: DBSession, current_user: CurrentUser):
    tc = await test_plan_service.get_test_case(db, tc_id)
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    await require_entity_project_access(tc, current_user, db)
    return tc


@router.patch("/{tc_id}", response_model=TestCaseOut)
async def update_test_case(tc_id: int, updates: TestCaseUpdate, db: DBSession, current_user: CurrentUser):
    tc = await test_plan_service.get_test_case(db, tc_id)
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    await require_entity_permission(tc, APPROVE_TEST_CASES, current_user, db)
    tc = await test_plan_service.update_test_case(db, tc, updates, user_id=current_user.id)
    await db.commit()
    return tc


@router.get("/{tc_id}/history", response_model=list[TestCaseHistoryOut])
async def get_test_case_history(tc_id: int, db: DBSession, current_user: CurrentUser):
    tc = await test_plan_service.get_test_case(db, tc_id)
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    await require_entity_project_access(tc, current_user, db)
    return await test_plan_service.list_test_case_history(db, tc)


@router.post("/projects/{project_id}/bulk-update", response_model=TestCaseBulkUpdateResult)
async def bulk_update_test_cases(
    project_id: int,
    body: TestCaseBulkUpdateRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Apply the same field patch to many test cases atomically.

    Always pass `dry_run: true` first to render the diff/conflict preview to
    the user. Once they confirm, call again with `dry_run: false` (and the
    same `reason`) to commit. The endpoint returns the per-row analysis in
    both modes; only the mutation step is skipped when dry_run is true.

    Requires APPROVE_TEST_CASES permission on the project. Every mutated row
    writes a `test_case_history` entry per changed field (source="bulk_update",
    comment=reason). A single `test_case.bulk_updated` summary event is also
    written to the audit log.
    """
    await require_permission(APPROVE_TEST_CASES, project_id, current_user, db)

    patch_dict = body.patch.model_dump(exclude_unset=True)

    result = await test_plan_service.bulk_update_test_cases(
        db,
        test_case_ids=body.test_case_ids,
        project_id=project_id,
        patch=patch_dict,
        reason=body.reason,
        user_id=current_user.id,
        dry_run=body.dry_run,
    )

    if not body.dry_run:
        await db.commit()
        audit_logger.test_case_bulk_updated(
            by_user_id=current_user.id,
            project_id=project_id,
            requested=result["requested"],
            updated=result["updated"],
            skipped=result["skipped"],
            conflicts=result["conflicts"],
            reason=body.reason,
            patch_fields=list(patch_dict.keys()),
        )

    return result


@router.post("/{tc_id}/sync-jira", response_model=TestCaseJiraSyncOut, status_code=202)
async def sync_test_case_jira(tc_id: int, db: DBSession, current_user: CurrentUser):
    tc = await test_plan_service.get_test_case(db, tc_id)
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    await require_permission(SYNC_JIRA, tc.project_id, current_user, db)
    sync_job_id, task_id = await test_plan_service.sync_test_case_jira(db, tc, current_user.id)
    await db.commit()
    return TestCaseJiraSyncOut(test_case_id=tc.id, status="queued", sync_job_id=sync_job_id, task_id=task_id)
