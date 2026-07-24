"""Enrollment of reusable TestCases into a TestPlan's UAT cycle.

Distinct from `TestCase.linked_test_plan_id` (the single plan a TC was
authored/generated under, set by the Test Case Development Agent). This
service manages `plan_test_cases`, the many-to-many table that lets the same
TestCase be enrolled into multiple plans/cycles over time, each carrying its
own planned Environment, Tester assignment and Planned Execution Sequence —
the UAT template's per-cycle tracking fields.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.test_case import TestCase
from app.models.test_plan import PlanTestCase, TestPlan
from app.schemas.plan_enrollment import PlanTestCaseCreate, PlanTestCaseReorder, PlanTestCaseUpdate


async def list_enrollments(db: AsyncSession, plan_id: int) -> list[PlanTestCase]:
    stmt = (
        select(PlanTestCase)
        .where(PlanTestCase.test_plan_id == plan_id)
        .options(
            selectinload(PlanTestCase.test_case),
            selectinload(PlanTestCase.environment),
        )
        .order_by(PlanTestCase.order_index, PlanTestCase.id)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def enroll_test_case(
    db: AsyncSession, plan: TestPlan, data: PlanTestCaseCreate, user_id: int
) -> PlanTestCase:
    tc = await db.get(TestCase, data.test_case_id)
    if tc is None or tc.project_id != plan.project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test case not found in this project",
        )

    max_order = await db.execute(
        select(PlanTestCase.order_index)
        .where(PlanTestCase.test_plan_id == plan.id)
        .order_by(PlanTestCase.order_index.desc())
        .limit(1)
    )
    next_order = (max_order.scalar_one_or_none() or 0) + 1

    enrollment = PlanTestCase(
        test_plan_id=plan.id,
        test_case_id=data.test_case_id,
        environment_id=data.environment_id,
        tester_user_id=data.tester_user_id,
        planned_execution_sequence=data.planned_execution_sequence,
        order_index=data.order_index if data.order_index is not None else next_order,
        created_by=user_id,
    )
    db.add(enrollment)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This test case is already enrolled in this plan.",
        ) from exc
    return enrollment


async def get_enrollment(db: AsyncSession, plan_id: int, enrollment_id: int) -> PlanTestCase:
    stmt = select(PlanTestCase).where(
        PlanTestCase.id == enrollment_id, PlanTestCase.test_plan_id == plan_id
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
    return obj


async def update_enrollment(
    db: AsyncSession, plan_id: int, enrollment_id: int, data: PlanTestCaseUpdate
) -> PlanTestCase:
    obj = await get_enrollment(db, plan_id, enrollment_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.flush()
    return obj


async def reorder_enrollments(db: AsyncSession, plan_id: int, data: PlanTestCaseReorder) -> list[PlanTestCase]:
    enrollments = await list_enrollments(db, plan_id)
    by_id = {e.id: e for e in enrollments}
    for position, enrollment_id in enumerate(data.ordered_enrollment_ids):
        obj = by_id.get(enrollment_id)
        if obj is not None:
            obj.order_index = position
    await db.flush()
    return await list_enrollments(db, plan_id)


async def unenroll_test_case(db: AsyncSession, plan_id: int, enrollment_id: int) -> None:
    obj = await get_enrollment(db, plan_id, enrollment_id)
    await db.delete(obj)
    await db.flush()
