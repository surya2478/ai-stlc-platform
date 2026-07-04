"""Test Suite Service — CRUD for the Test Suite tag test cases are assigned to."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.test_case import TestCase
from app.models.test_suite import TestSuite
from app.schemas.test_suite import TestSuiteCreate, TestSuiteUpdate


async def list_suites(db: AsyncSession, project_id: int) -> list[TestSuite]:
    result = await db.execute(
        select(TestSuite)
        .where(TestSuite.project_id == project_id)
        .order_by(TestSuite.name)
    )
    return list(result.scalars().all())


async def get_suite_case_counts(db: AsyncSession, suite_ids: list[int]) -> dict[int, int]:
    if not suite_ids:
        return {}
    result = await db.execute(
        select(TestCase.test_suite_id, func.count(TestCase.id))
        .where(TestCase.test_suite_id.in_(suite_ids), TestCase.is_deleted.is_(False))
        .group_by(TestCase.test_suite_id)
    )
    return {row[0]: row[1] for row in result.all()}


async def get_suite(db: AsyncSession, suite_id: int) -> TestSuite | None:
    result = await db.execute(select(TestSuite).where(TestSuite.id == suite_id))
    return result.scalar_one_or_none()


async def create_suite(db: AsyncSession, data: TestSuiteCreate, user_id: int) -> TestSuite:
    suite = TestSuite(
        project_id=data.project_id,
        name=data.name,
        description=data.description,
        environment=data.environment,
        status="active",
        created_by=user_id,
    )
    db.add(suite)
    await db.flush()
    await db.refresh(suite)
    return suite


async def update_suite(db: AsyncSession, suite: TestSuite, updates: TestSuiteUpdate, user_id: int) -> TestSuite:
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(suite, field, value)
    suite.updated_by = user_id
    await db.flush()
    await db.refresh(suite)
    return suite


async def delete_suite(db: AsyncSession, suite: TestSuite) -> None:
    await db.delete(suite)
