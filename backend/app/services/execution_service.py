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
    resolved live from the Test Cases module rather than snapshotted at
    run-creation time — so the run list always reflects the test case's
    current data, the same single source of truth the Test Cases screen
    shows.

    - test_suite_name: TestCase.test_suite_id -> TestSuite.name.
    - test_environment: TestCase.test_phase — this is the field the Test
      Cases module actually labels "Test Environment" (SIT/QA/UAT/
      Regression/...); it's independent of TestSuite.environment, which is
      a separate column most projects leave unset.

    Both are resolved independently per run: a run's constituent tests can
    span more than one suite or phase (an "All Eligible" run isn't
    suite-scoped), so each attribute is attributed to whichever value the
    majority of that run's test cases carry.
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
    test_case_rows = (
        await db.execute(
            select(TestCase.id, TestCase.test_suite_id, TestCase.test_phase).where(TestCase.id.in_(test_case_ids))
        )
    ).all()
    suite_id_by_test_case = {row[0]: row[1] for row in test_case_rows}
    test_phase_by_test_case = {row[0]: row[2] for row in test_case_rows}

    suite_ids = {sid for sid in suite_id_by_test_case.values() if sid is not None}
    suite_name_by_id: dict[int, str] = {}
    if suite_ids:
        suite_name_by_id = dict(
            (await db.execute(select(TestSuite.id, TestSuite.name).where(TestSuite.id.in_(suite_ids)))).all()
        )

    suite_ids_by_run: dict[int, list[int]] = {}
    phases_by_run: dict[int, list[str]] = {}
    for run_id, test_case_id in pairs:
        suite_id = suite_id_by_test_case.get(test_case_id)
        if suite_id is not None:
            suite_ids_by_run.setdefault(run_id, []).append(suite_id)
        phase = test_phase_by_test_case.get(test_case_id)
        if phase:
            phases_by_run.setdefault(run_id, []).append(phase)

    for run in runs:
        candidate_suite_ids = suite_ids_by_run.get(run.id)
        if candidate_suite_ids:
            dominant_suite_id = Counter(candidate_suite_ids).most_common(1)[0][0]
            run.test_suite_name = suite_name_by_id.get(dominant_suite_id)  # type: ignore[attr-defined]

        candidate_phases = phases_by_run.get(run.id)
        if candidate_phases:
            run.test_environment = Counter(candidate_phases).most_common(1)[0][0]  # type: ignore[attr-defined]


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
