"""
Requirement Service — CRUD operations for requirements.
"""
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.requirement import Requirement
from app.schemas.requirement import RequirementCreate, RequirementUpdate
from app.services.display_id_service import display_id, temporary_id

# Requirements whose status cannot be changed again
_TERMINAL_STATUSES = {"approved", "rejected"}


async def create_requirement(
    db: AsyncSession,
    data: RequirementCreate,
    user_id: int,
) -> Requirement:
    req = Requirement(
        project_id=data.project_id,
        created_by=user_id,
        requirement_id=temporary_id("REQ"),
        source=data.source,
        title=data.title,
        summary=data.summary,
        source_document_id=data.source_document_id,
        status="draft",
    )
    db.add(req)
    await db.flush()
    req.requirement_id = display_id("REQ", req.id)
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
    qa_domain: str | None = None,
    product_group: str | None = None,
    product: str | None = None,
    sub_request_type: str | None = None,
    risk_level: str | None = None,
    test_phase: str | None = None,
    readiness_status: str | None = None,
    sync_status: str | None = None,
    search: str | None = None,
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
    if qa_domain:
        stmt = stmt.where(Requirement.qa_domain == qa_domain)
    if product_group:
        stmt = stmt.where(Requirement.product_group == product_group)
    if product:
        stmt = stmt.where(Requirement.product == product)
    if sub_request_type:
        stmt = stmt.where(Requirement.sub_request_type == sub_request_type)
    if risk_level:
        stmt = stmt.where(Requirement.risk_level == risk_level)
    if test_phase:
        stmt = stmt.where(Requirement.test_phase == test_phase)
    if readiness_status:
        stmt = stmt.where(Requirement.readiness_status == readiness_status)
    if sync_status:
        stmt = stmt.where(Requirement.sync_status == sync_status)
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            (Requirement.title.ilike(search_pattern)) | 
            (Requirement.summary.ilike(search_pattern))
        )
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_requirement(
    db: AsyncSession,
    req: Requirement,
    updates: RequirementUpdate,
    force: bool = False,
) -> Requirement:
    if req.status in _TERMINAL_STATUSES and not force:
        raise HTTPException(
            status_code=409,
            detail=f"Requirement is already '{req.status}' and cannot be updated.",
        )
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
