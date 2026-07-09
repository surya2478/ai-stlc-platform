"""
Coverage matrix maintenance (Phase 1).

One row per test case, refreshed incrementally as later stages produce more
information about it — script linked, execution result recorded, defect
raised — rather than computed as a one-time snapshot.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coverage_matrix import CoverageMatrixEntry
from app.models.test_case import TestCase

# Maps TestScenario.scenario_type -> the coverage_matrix's case_class vocabulary.
_SCENARIO_TYPE_TO_CASE_CLASS: dict[str, str] = {
    "positive": "positive",
    "negative": "negative",
    "boundary": "boundary",
    "edge": "boundary",
    "security": "exception",
    "performance": "exception",
    "integration": "positive",
    "accessibility": "positive",
}


def case_class_from_scenario_type(scenario_type: str | None) -> str | None:
    if not scenario_type:
        return None
    return _SCENARIO_TYPE_TO_CASE_CLASS.get(scenario_type.lower(), "positive")


async def get_entry(db: AsyncSession, test_case_id: int) -> CoverageMatrixEntry | None:
    result = await db.execute(
        select(CoverageMatrixEntry).where(CoverageMatrixEntry.test_case_id == test_case_id)
    )
    return result.scalar_one_or_none()


async def _apply(entry: CoverageMatrixEntry, db: AsyncSession, **fields: Any) -> CoverageMatrixEntry:
    for key, value in fields.items():
        setattr(entry, key, value)
    await db.flush()
    return entry


async def seed_from_test_case(
    db: AsyncSession, *, project_id: int, test_case: TestCase, case_class: str | None = None
) -> CoverageMatrixEntry:
    """Initial population, called once a test case has been reviewed."""
    entry = await get_entry(db, test_case.id)
    if entry is None:
        entry = CoverageMatrixEntry(project_id=project_id, test_case_id=test_case.id)
        db.add(entry)
    return await _apply(
        entry,
        db,
        requirement_id=test_case.requirement_id,
        scenario_id=test_case.scenario_id,
        test_type=test_case.test_type,
        automation_eligible=test_case.automation_eligible,
        case_class=case_class,
    )


async def record_script_linked(db: AsyncSession, *, test_case_id: int, script_id: int) -> None:
    entry = await get_entry(db, test_case_id)
    if entry is None:
        return  # no baseline row yet (test_case_review hasn't run) — skip rather than guess
    await _apply(entry, db, script_id=script_id)


async def record_execution_status(db: AsyncSession, *, test_case_id: int, execution_status: str) -> None:
    entry = await get_entry(db, test_case_id)
    if entry is None:
        return
    await _apply(entry, db, execution_status=execution_status)


async def record_defect_linked(db: AsyncSession, *, test_case_id: int, defect_id: int) -> None:
    entry = await get_entry(db, test_case_id)
    if entry is None:
        return
    await _apply(entry, db, defect_id=defect_id, defect_linked=True)


async def record_eligibility(
    db: AsyncSession, *, test_case_id: int, automation_eligible: str, automation_reason: str
) -> None:
    entry = await get_entry(db, test_case_id)
    if entry is None:
        return
    await _apply(entry, db, automation_eligible=automation_eligible, automation_reason=automation_reason)


async def list_for_project(
    db: AsyncSession,
    *,
    project_id: int,
    requirement_id: int | None = None,
    scenario_id: int | None = None,
) -> list[CoverageMatrixEntry]:
    stmt = select(CoverageMatrixEntry).where(CoverageMatrixEntry.project_id == project_id)
    if requirement_id is not None:
        stmt = stmt.where(CoverageMatrixEntry.requirement_id == requirement_id)
    if scenario_id is not None:
        stmt = stmt.where(CoverageMatrixEntry.scenario_id == scenario_id)
    result = await db.execute(stmt.order_by(CoverageMatrixEntry.id))
    return list(result.scalars().all())
