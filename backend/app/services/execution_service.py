"""Test Execution service — CRUD operations."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.execution import ExecutionRun, ExecutionResult
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
    return runs


async def get_run(db: AsyncSession, run_id: int) -> ExecutionRun | None:
    result = await db.execute(
        select(ExecutionRun).where(ExecutionRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if run:
        await _attach_triggered_by_names(db, [run])
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
