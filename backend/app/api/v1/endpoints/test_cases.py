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
from app.schemas.test_plan import TestCaseHistoryOut, TestCaseJiraSyncOut, TestCaseOut, TestCaseSummaryOut, TestCaseUpdate
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


@router.post("/{tc_id}/sync-jira", response_model=TestCaseJiraSyncOut, status_code=202)
async def sync_test_case_jira(tc_id: int, db: DBSession, current_user: CurrentUser):
    tc = await test_plan_service.get_test_case(db, tc_id)
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    await require_permission(SYNC_JIRA, tc.project_id, current_user, db)
    sync_job_id, task_id = await test_plan_service.sync_test_case_jira(db, tc, current_user.id)
    await db.commit()
    return TestCaseJiraSyncOut(test_case_id=tc.id, status="queued", sync_job_id=sync_job_id, task_id=task_id)
