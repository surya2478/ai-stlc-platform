"""
Requirement Service — CRUD operations for requirements.
"""
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.models.requirement import Requirement
from app.models.requirement_review import RequirementQualityReview
from app.schemas.requirement import RequirementCreate, RequirementUpdate, RequirementStatsOut
from app.services.display_id_service import display_id, temporary_id

# Requirements whose approval status cannot be changed again
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
        readiness_status="draft",
        is_deleted=False,
        telecom_domain=data.telecom_domain,
        risk_level=data.risk_level,
        test_phase=data.test_phase,
        release_version=data.release_version,
        release_train=data.release_train,
    )
    db.add(req)
    await db.flush()
    req.requirement_id = display_id("REQ", req.id)
    await db.flush()
    await db.refresh(req)
    return req


async def get_requirement(db: AsyncSession, req_id: int) -> Requirement | None:
    result = await db.execute(
        select(Requirement).where(Requirement.id == req_id, Requirement.is_deleted.is_(False))
    )
    return result.scalar_one_or_none()


async def list_requirements(
    db: AsyncSession,
    project_id: int,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
    # New filter params
    search: str | None = None,
    telecom_domain: str | None = None,
    risk_level: str | None = None,
    test_phase: str | None = None,
    readiness_status: str | None = None,
    sync_status: str | None = None,
    has_quality_review: bool | None = None,
    source: str | None = None,
) -> list[Requirement]:
    # Enforce max limit
    limit = min(limit, 200)

    stmt = (
        select(Requirement)
        .where(
            Requirement.project_id == project_id,
            Requirement.is_deleted.is_(False),
        )
        .order_by(Requirement.created_at.desc())
    )
    if status:
        stmt = stmt.where(Requirement.status == status)
    if telecom_domain:
        # Filter on either column — telecom_domain (new) or qa_domain (legacy)
        from sqlalchemy import or_
        stmt = stmt.where(
            or_(
                Requirement.telecom_domain == telecom_domain,
                Requirement.qa_domain == telecom_domain,
            )
        )
    if risk_level:
        stmt = stmt.where(Requirement.risk_level == risk_level)
    if test_phase:
        stmt = stmt.where(Requirement.test_phase == test_phase)
    if readiness_status:
        stmt = stmt.where(Requirement.readiness_status == readiness_status)
    if sync_status:
        stmt = stmt.where(Requirement.sync_status == sync_status)
    if source:
        stmt = stmt.where(Requirement.source == source)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Requirement.title.ilike(pattern),
                Requirement.summary.ilike(pattern),
                Requirement.requirement_id.ilike(pattern),
                Requirement.jira_issue_key.ilike(pattern),
            )
        )
    if has_quality_review is True:
        stmt = stmt.where(Requirement.quality_score.is_not(None))
    elif has_quality_review is False:
        stmt = stmt.where(Requirement.quality_score.is_(None))

    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_requirement_stats(db: AsyncSession, project_id: int) -> RequirementStatsOut:
    """Compute summary statistics for the requirements command center."""
    base = select(Requirement).where(
        Requirement.project_id == project_id,
        Requirement.is_deleted.is_(False),
    )

    def _count(extra_where=None):
        s = select(func.count()).select_from(
            select(Requirement)
            .where(Requirement.project_id == project_id, Requirement.is_deleted.is_(False))
            .subquery()
        )
        return s

    async def cnt(where_clause=None) -> int:
        stmt = select(func.count()).where(
            Requirement.project_id == project_id,
            Requirement.is_deleted.is_(False),
        )
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        r = await db.execute(stmt.select_from(Requirement))
        return r.scalar_one()

    total = await cnt()
    approved = await cnt(Requirement.status == "approved")
    pending = await cnt(Requirement.status == "pending_review")
    draft = await cnt(Requirement.status == "draft")
    rejected = await cnt(Requirement.status == "rejected")
    needs_clarif = await cnt(Requirement.readiness_status == "needs_clarification")
    ready = await cnt(Requirement.readiness_status == "ready_for_test_planning")
    # Quality issues: reviewed but score < 3.0
    quality_issues = await cnt(
        (Requirement.quality_score.is_not(None)) & (Requirement.quality_score < 3.0)
    )
    high_risk = await cnt(Requirement.risk_level.in_(["Critical", "High"]))
    # Missing AC: acceptance_criteria is null or empty array
    missing_ac = await cnt(
        or_(
            Requirement.acceptance_criteria.is_(None),
            Requirement.acceptance_criteria == [],
        )
    )
    jira_synced = await cnt(Requirement.sync_status == "synced")
    jira_conflict = await cnt(Requirement.sync_status == "conflict")

    return RequirementStatsOut(
        total=total,
        approved=approved,
        pending_review=pending,
        draft=draft,
        rejected=rejected,
        needs_clarification=needs_clarif,
        ready_for_test_planning=ready,
        quality_issues=quality_issues,
        high_risk=high_risk,
        missing_ac=missing_ac,
        jira_synced=jira_synced,
        jira_conflict=jira_conflict,
    )


async def update_requirement(
    db: AsyncSession,
    req: Requirement,
    updates: RequirementUpdate,
) -> Requirement:
    # Guard: prevent silent modification of terminal-status requirements
    if req.status in _TERMINAL_STATUSES:
        non_status_changes = {
            k: v for k, v in updates.model_dump(exclude_unset=True).items()
            if k not in {"status", "readiness_status", "review_notes"}
        }
        if non_status_changes:
            raise HTTPException(
                status_code=409,
                detail=f"Requirement is '{req.status}' and cannot be modified. "
                       "Telecom metadata fields (domain, risk, etc.) can still be updated.",
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
    req.readiness_status = "approved" if action == "approve" else "rejected"
    if notes:
        req.review_notes = notes
    await db.flush()
    await db.refresh(req)
    return req


async def soft_delete_requirement(db: AsyncSession, req: Requirement) -> None:
    """Soft-delete: sets is_deleted=True rather than hard-deleting."""
    req.is_deleted = True
    await db.flush()


async def delete_requirement(db: AsyncSession, req: Requirement) -> None:
    """Soft delete (preserves traceability)."""
    await soft_delete_requirement(db, req)


async def update_quality_scores(
    db: AsyncSession,
    req: Requirement,
    quality_score: float | None,
    quality_feedback: str | None,
    quality_verdict: str | None,
    scenario_generation_readiness: float | None = None,
) -> Requirement:
    """Denormalise quality scores onto the Requirement for fast list queries."""
    req.quality_score = quality_score
    req.quality_feedback = quality_feedback
    req.quality_verdict = quality_verdict

    # Update readiness_status based on verdict
    if quality_verdict == "fail":
        req.readiness_status = "needs_clarification"
    elif quality_verdict == "needs_revision":
        req.readiness_status = "ai_review_completed"
    elif quality_verdict == "pass":
        if scenario_generation_readiness is not None and scenario_generation_readiness >= 3.5:
            req.readiness_status = "ready_for_test_planning"
        else:
            req.readiness_status = "ai_review_completed"
    else:
        req.readiness_status = "ai_review_completed"

    await db.flush()
    return req
