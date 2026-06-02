"""
Test Plan, Test Scenario, and Test Case service — CRUD operations.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.test_plan import TestPlan
from app.models.test_scenario import TestScenario
from app.models.test_case import TestCase
from app.schemas.test_plan import TestPlanUpdate, TestCaseUpdate


# ── Test Plan ─────────────────────────────────────────────────────────────────

async def list_test_plans(db: AsyncSession, project_id: int) -> list[TestPlan]:
    result = await db.execute(
        select(TestPlan)
        .where(TestPlan.project_id == project_id)
        .order_by(TestPlan.created_at.desc())
    )
    return list(result.scalars().all())


async def get_test_plan(db: AsyncSession, plan_id: int) -> TestPlan | None:
    result = await db.execute(select(TestPlan).where(TestPlan.id == plan_id))
    return result.scalar_one_or_none()


async def update_test_plan(db: AsyncSession, plan: TestPlan, updates: TestPlanUpdate) -> TestPlan:
    data = updates.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(plan, key, value)
    await db.flush()
    await db.refresh(plan)
    return plan


async def approve_test_plan(db: AsyncSession, plan: TestPlan, action: str, notes: str | None) -> TestPlan:
    plan.status = "approved" if action == "approve" else "rejected"
    if notes:
        plan.metadata_ = {**(plan.metadata_ or {}), "review_notes": notes}
    await db.flush()
    await db.refresh(plan)
    return plan


# ── Test Scenario ─────────────────────────────────────────────────────────────

async def list_scenarios(
    db: AsyncSession,
    project_id: int,
    requirement_id: int | None = None,
) -> list[TestScenario]:
    stmt = (
        select(TestScenario)
        .where(TestScenario.project_id == project_id)
        .order_by(TestScenario.created_at.desc())
    )
    if requirement_id:
        stmt = stmt.where(TestScenario.requirement_id == requirement_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_scenario(db: AsyncSession, scenario_id: int) -> TestScenario | None:
    result = await db.execute(select(TestScenario).where(TestScenario.id == scenario_id))
    return result.scalar_one_or_none()


# ── Test Case ─────────────────────────────────────────────────────────────────

async def list_test_cases(
    db: AsyncSession,
    project_id: int,
    scenario_id: int | None = None,
    requirement_id: int | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[TestCase]:
    stmt = (
        select(TestCase)
        .where(TestCase.project_id == project_id)
        .order_by(TestCase.created_at.desc())
    )
    if scenario_id:
        stmt = stmt.where(TestCase.scenario_id == scenario_id)
    if requirement_id:
        stmt = stmt.where(TestCase.requirement_id == requirement_id)
    if status:
        stmt = stmt.where(TestCase.status == status)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_test_case(db: AsyncSession, tc_id: int) -> TestCase | None:
    result = await db.execute(select(TestCase).where(TestCase.id == tc_id))
    return result.scalar_one_or_none()


async def update_test_case(db: AsyncSession, tc: TestCase, updates: TestCaseUpdate) -> TestCase:
    data = updates.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(tc, key, value)
    await db.flush()
    await db.refresh(tc)
    return tc


async def approve_test_case(db: AsyncSession, tc: TestCase, action: str, notes: str | None) -> TestCase:
    tc.status = "approved" if action == "approve" else "rejected"
    if notes:
        tc.metadata_ = {**(tc.metadata_ or {}), "review_notes": notes}
    await db.flush()
    await db.refresh(tc)
    return tc


async def count_test_cases_by_project(db: AsyncSession, project_id: int) -> dict:
    result = await db.execute(
        select(TestCase.status, func.count())
        .where(TestCase.project_id == project_id)
        .group_by(TestCase.status)
    )
    return {row[0]: row[1] for row in result.all()}
