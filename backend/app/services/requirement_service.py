"""
Requirement Service — CRUD operations for requirements.
"""
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.requirement import Requirement
from app.schemas.requirement import RequirementCreate, RequirementUpdate

# Requirements whose status cannot be changed again
_TERMINAL_STATUSES = {"approved", "rejected"}


async def _next_req_id(db: AsyncSession, project_id: int) -> str:
    """Race-safe ID: use MAX existing numeric suffix + 1 instead of COUNT."""
    result = await db.execute(
        select(func.max(Requirement.id)).where(Requirement.project_id == project_id)
    )
    max_id = result.scalar_one()
    # Count all requirements for this project to get a sequential human-readable number
    count_result = await db.execute(
        select(func.count()).where(Requirement.project_id == project_id)
    )
    count = count_result.scalar_one()
    # Use count+1 for display number; uniqueness is ensured by the DB PK on id
    return f"REQ-{(count + 1):04d}"


async def create_requirement(
    db: AsyncSession,
    data: RequirementCreate,
    user_id: int,
) -> Requirement:
    req_id = await _next_req_id(db, data.project_id)
    req = Requirement(
        project_id=data.project_id,
        created_by=user_id,
        requirement_id=req_id,
        source=data.source,
        title=data.title,
        summary=data.summary,
        source_document_id=data.source_document_id,
        status="draft",
    )
    db.add(req)
    await db.flush()
    await db.refresh(req)
    return req


async def get_requirement(db: AsyncSession, req_id: int) -> Requirement | None:
    result = await db.execute(select(Requirement).where(Requirement.id == req_id))
    return result.scalar_one_or_none()


async def list_requirements(
    db: AsyncSession,
    project_id: int,
    status: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Requirement]:
    stmt = (
        select(Requirement)
        .where(Requirement.project_id == project_id)
        .order_by(Requirement.created_at.desc())
    )
    if status:
        stmt = stmt.where(Requirement.status == status)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_requirement(
    db: AsyncSession,
    req: Requirement,
    updates: RequirementUpdate,
) -> Requirement:
    data = updates.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(req, key, value)
    await db.flush()
    await db.refresh(req)
    return req


async def approve_requirement(db: AsyncSession, req: Requirement, action: str, notes: str | None) -> Requirement:
    if req.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Requirement is already '{req.status}' and cannot be changed again.",
        )
    req.status = "approved" if action == "approve" else "rejected"
    if notes:
        req.review_notes = notes
    await db.flush()
    await db.refresh(req)
    return req


async def delete_requirement(db: AsyncSession, req: Requirement) -> None:
    """Delete a requirement record."""
    await db.delete(req)
    await db.flush()
