"""Test Execution service — CRUD operations."""
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.execution import ExecutionRun, ExecutionResult
from app.models.test_case import TestCase
from app.models.test_suite import TestSuite
from app.models.user import User


async def _attach_triggered_by_names(db: AsyncSession, runs: list[ExecutionRun]) -> None:
    """Populate the dynamic `triggered_by_name` attribute so ExecutionRunOut
    (from_attributes=True) can surface who ran it without a schema/column
    change — same batch-lookup pattern as execution_dashboard_service."""
    user_ids = {r.triggered_by for r in runs if r.triggered_by is not None}
    if not user_ids:
        return
    result = await db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids)))
    name_by_id = {row[0]: row[1] for row in result.all()}
    for run in runs:
        run.triggered_by_name = name_by_id.get(run.triggered_by)  # type: ignore[attr-defined]


async def _attach_test_suite_info(db: AsyncSession, runs: list[ExecutionRun]) -> None:
    """Populate dynamic `test_suite_name` / `test_environment` attributes,
    resolved live from the Test Cases module (TestCase.test_suite_id ->
    TestSuite.name/.environment) rather than snapshotted at run-creation
    time — so the run list always reflects the test case's current suite
    assignment, the same single source of truth the Test Cases screen shows.

    A run's constituent tests can in principle span more than one suite (an
    "All Eligible" run isn't suite-scoped); we attribute the run to whichever
    suite the most of its ExecutionResults belong to.
    """
    run_ids = [r.id for r in runs]
    if not run_ids:
        return

    pairs = (
        await db.execute(
            select(ExecutionResult.execution_run_id, ExecutionResult.test_case_id)
            .where(ExecutionResult.execution_run_id.in_(run_ids), ExecutionResult.test_case_id.isnot(None))
        )
    ).all()
    if not pairs:
        return

    test_case_ids = {tc_id for _, tc_id in pairs}
    suite_id_by_test_case = dict(
        (
            await db.execute(
                select(TestCase.id, TestCase.test_suite_id).where(TestCase.id.in_(test_case_ids))
            )
        ).all()
    )

    suite_ids = {sid for sid in suite_id_by_test_case.values() if sid is not None}
    if not suite_ids:
        return
    suite_info_by_id = {
        row[0]: (row[1], row[2])
        for row in (
            await db.execute(
                select(TestSuite.id, TestSuite.name, TestSuite.environment).where(TestSuite.id.in_(suite_ids))
            )
        ).all()
    }

    suite_ids_by_run: dict[int, list[int]] = {}
    for run_id, test_case_id in pairs:
        suite_id = suite_id_by_test_case.get(test_case_id)
        if suite_id is not None:
            suite_ids_by_run.setdefault(run_id, []).append(suite_id)

    for run in runs:
        candidate_suite_ids = suite_ids_by_run.get(run.id)
        if not candidate_suite_ids:
            continue
        dominant_suite_id = Counter(candidate_suite_ids).most_common(1)[0][0]
        name, environment = suite_info_by_id.get(dominant_suite_id, (None, None))
        run.test_suite_name = name  # type: ignore[attr-defined]
        run.test_environment = environment  # type: ignore[attr-defined]


async def list_runs(
    db: AsyncSession,
    project_id: int,
    status: str | None = None,
) -> list[ExecutionRun]:
    stmt = (
        select(ExecutionRun)
        .where(ExecutionRun.project_id == project_id)
        .order_by(ExecutionRun.created_at.desc())
    )
    if status:
        stmt = stmt.where(ExecutionRun.status == status)
    result = await db.execute(stmt)
    runs = list(result.scalars().all())
    await _attach_triggered_by_names(db, runs)
    await _attach_test_suite_info(db, runs)
    return runs


async def get_run(db: AsyncSession, run_id: int) -> ExecutionRun | None:
    result = await db.execute(
        select(ExecutionRun).where(ExecutionRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if run:
        await _attach_triggered_by_names(db, [run])
        await _attach_test_suite_info(db, [run])
    return run


async def list_results(
    db: AsyncSession,
    execution_run_id: int,
) -> list[ExecutionResult]:
    result = await db.execute(
        select(ExecutionResult)
        .where(ExecutionResult.execution_run_id == execution_run_id)
        .order_by(ExecutionResult.created_at.asc())
    )
    return list(result.scalars().all())


async def count_runs_by_project(db: AsyncSession, project_id: int) -> dict:
    result = await db.execute(
        select(ExecutionRun.status, func.count())
        .where(ExecutionRun.project_id == project_id)
        .group_by(ExecutionRun.status)
    )
    return {row[0]: row[1] for row in result.all()}
