"""Defect service — CRUD operations."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.defect import DefectDraft, JiraDefect
from app.schemas.defect import DefectDraftUpdate


async def list_defects(
    db: AsyncSession,
    project_id: int,
    status: str | None = None,
) -> list[DefectDraft]:
    stmt = (
        select(DefectDraft)
        .where(DefectDraft.project_id == project_id)
        .order_by(DefectDraft.created_at.desc())
    )
    if status:
        stmt = stmt.where(DefectDraft.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_defect(db: AsyncSession, defect_id: int) -> DefectDraft | None:
    result = await db.execute(
        select(DefectDraft).where(DefectDraft.id == defect_id)
    )
    return result.scalar_one_or_none()


async def update_defect(
    db: AsyncSession, defect: DefectDraft, updates: DefectDraftUpdate
) -> DefectDraft:
    data = updates.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(defect, key, value)
    await db.flush()
    await db.refresh(defect)
    return defect


async def approve_defect(
    db: AsyncSession, defect: DefectDraft, action: str, notes: str | None
) -> DefectDraft:
    defect.status = "approved" if action == "approve" else "rejected"
    if notes:
        defect.metadata_ = {**(defect.metadata_ or {}), "review_notes": notes}
    await db.flush()
    await db.refresh(defect)
    return defect


async def count_defects_by_project(db: AsyncSession, project_id: int) -> dict:
    result = await db.execute(
        select(DefectDraft.status, func.count())
        .where(DefectDraft.project_id == project_id)
        .group_by(DefectDraft.status)
    )
    return {row[0]: row[1] for row in result.all()}
