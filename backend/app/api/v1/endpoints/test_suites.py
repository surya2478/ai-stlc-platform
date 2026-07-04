"""Test Suite endpoints — a named tag test cases are assigned to."""
from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DBSession, require_permission, require_project_access
from app.schemas.common import MessageResponse
from app.schemas.test_suite import TestSuiteCreate, TestSuiteOut, TestSuiteUpdate
from app.services import test_suite_service
from app.services.rbac_service import APPROVE_TEST_CASES

router = APIRouter()


def _to_out(suite, case_count: int = 0) -> TestSuiteOut:
    return TestSuiteOut(
        id=suite.id,
        project_id=suite.project_id,
        name=suite.name,
        description=suite.description,
        environment=suite.environment,
        status=suite.status,
        case_count=case_count,
        created_by=suite.created_by,
        updated_by=suite.updated_by,
        created_at=suite.created_at,
        updated_at=suite.updated_at,
    )


@router.get("/project/{project_id}", response_model=list[TestSuiteOut])
async def list_project_test_suites(project_id: int, db: DBSession, current_user: CurrentUser):
    await require_project_access(project_id, current_user, db)
    suites = await test_suite_service.list_suites(db, project_id)
    counts = await test_suite_service.get_suite_case_counts(db, [s.id for s in suites])
    return [_to_out(s, counts.get(s.id, 0)) for s in suites]


@router.post("", response_model=TestSuiteOut, status_code=201)
@router.post("/", response_model=TestSuiteOut, status_code=201)
async def create_test_suite(data: TestSuiteCreate, db: DBSession, current_user: CurrentUser):
    await require_permission(APPROVE_TEST_CASES, data.project_id, current_user, db)
    suite = await test_suite_service.create_suite(db, data, current_user.id)
    await db.commit()
    return _to_out(suite, 0)


@router.get("/{suite_id}", response_model=TestSuiteOut)
async def get_test_suite(suite_id: int, db: DBSession, current_user: CurrentUser):
    suite = await test_suite_service.get_suite(db, suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail="Test suite not found")
    await require_project_access(suite.project_id, current_user, db)
    counts = await test_suite_service.get_suite_case_counts(db, [suite.id])
    return _to_out(suite, counts.get(suite.id, 0))


@router.patch("/{suite_id}", response_model=TestSuiteOut)
async def update_test_suite(suite_id: int, updates: TestSuiteUpdate, db: DBSession, current_user: CurrentUser):
    suite = await test_suite_service.get_suite(db, suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail="Test suite not found")
    await require_permission(APPROVE_TEST_CASES, suite.project_id, current_user, db)
    suite = await test_suite_service.update_suite(db, suite, updates, current_user.id)
    await db.commit()
    counts = await test_suite_service.get_suite_case_counts(db, [suite.id])
    return _to_out(suite, counts.get(suite.id, 0))


@router.delete("/{suite_id}", response_model=MessageResponse)
async def delete_test_suite(suite_id: int, db: DBSession, current_user: CurrentUser):
    suite = await test_suite_service.get_suite(db, suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail="Test suite not found")
    await require_permission(APPROVE_TEST_CASES, suite.project_id, current_user, db)
    await test_suite_service.delete_suite(db, suite)
    await db.commit()
    return {"message": "Test suite deleted"}
