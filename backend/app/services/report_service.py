"""Report service — CRUD operations."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.report import Report


async def list_reports(db: AsyncSession, project_id: int) -> list[Report]:
    result = await db.execute(
        select(Report)
        .where(Report.project_id == project_id)
        .order_by(Report.created_at.desc())
    )
    return list(result.scalars().all())


async def get_report(db: AsyncSession, report_id: int) -> Report | None:
    result = await db.execute(select(Report).where(Report.id == report_id))
    return result.scalar_one_or_none()
