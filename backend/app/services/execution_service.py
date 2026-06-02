"""Test Execution service — CRUD operations."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.execution import ExecutionRun, ExecutionResult


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
    return list(result.scalars().all())


async def get_run(db: AsyncSession, run_id: int) -> ExecutionRun | None:
    result = await db.execute(
        select(ExecutionRun).where(ExecutionRun.id == run_id)
    )
    return result.scalar_one_or_none()


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
