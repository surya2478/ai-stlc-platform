"""Requirements endpoints."""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func

from app.api.deps import DBSession, OptionalUser
from app.models.requirement import Requirement
from app.models.document import UploadedDocument
from app.schemas.requirement import (
    RequirementCreate, RequirementUpdate, RequirementOut,
    RequirementListOut, AgentTriggerRequest, ApprovalRequest,
)
from app.schemas.common import MessageResponse
from app.services import requirement_service
from app.agents.requirement.intake_agent import RequirementIntakeAgent
from app.agents.requirement.quality_agent import RequirementQualityAgent

router = APIRouter()


@router.get("/project/{project_id}", response_model=list[RequirementOut])
async def list_requirements(
    project_id: int,
    db: DBSession,
    current_user: OptionalUser,
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return await requirement_service.list_requirements(db, project_id, status, skip, limit)


@router.post("/", response_model=RequirementOut, status_code=201)
async def create_requirement(
    data: RequirementCreate,
    db: DBSession,
    current_user: OptionalUser,
):
    req = await requirement_service.create_requirement(db, data, (current_user.id if current_user else 1))
    await db.commit()
    return req


@router.get("/{req_id}", response_model=RequirementOut)
async def get_requirement(
    req_id: int,
    db: DBSession,
    current_user: OptionalUser,
):
    req = await requirement_service.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return req


@router.patch("/{req_id}", response_model=RequirementOut)
async def update_requirement(
    req_id: int,
    updates: RequirementUpdate,
    db: DBSession,
    current_user: OptionalUser,
):
    req = await requirement_service.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    req = await requirement_service.update_requirement(db, req, updates)
    await db.commit()
    return req


@router.delete("/{req_id}", response_model=MessageResponse)
async def delete_requirement(
    req_id: int,
    db: DBSession,
    current_user: OptionalUser,
):
    req = await requirement_service.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    await requirement_service.delete_requirement(db, req)
    await db.commit()
    return {"message": "Requirement deleted"}


@router.post("/{req_id}/approve", response_model=RequirementOut)
async def approve_requirement(
    req_id: int,
    body: ApprovalRequest,
    db: DBSession,
    current_user: OptionalUser,
):
    req = await requirement_service.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    req = await requirement_service.approve_requirement(db, req, body.action, body.notes)
    await db.commit()
    return req


@router.post("/agent/intake")
async def trigger_intake_agent(
    body: AgentTriggerRequest,
    db: DBSession,
    current_user: OptionalUser,
):
    """Trigger Agent 1 (Requirement Intake) on an uploaded document."""
    if not body.document_id:
        raise HTTPException(status_code=422, detail="document_id is required for intake agent")

    result = await db.execute(
        select(UploadedDocument).where(UploadedDocument.id == body.document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Guard: verify document belongs to the requested project
    if doc.project_id != body.project_id:
        raise HTTPException(status_code=403, detail="Document does not belong to this project")

    if doc.status == "failed":
        raise HTTPException(status_code=422, detail="Document extraction failed — please re-upload the file")
    if not doc.extracted_text:
        raise HTTPException(status_code=422, detail="Document has no extracted text yet — wait for processing to complete")

    # Guard: prevent re-processing a document that already produced requirements
    existing_count_res = await db.execute(
        select(func.count()).where(
            Requirement.project_id == body.project_id,
            Requirement.source_document_id == doc.id,
        )
    )
    existing_count = existing_count_res.scalar_one()
    if existing_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This document has already been processed and produced {existing_count} requirement(s). "
                "Delete the existing requirements first if you want to re-run extraction."
            ),
        )

    agent = RequirementIntakeAgent()
    agent_result = await agent.run(
        document_text=doc.extracted_text,
        project_id=body.project_id,
    )

    if not agent_result.success:
        raise HTTPException(status_code=500, detail=agent_result.error or "Agent failed")

    created = []
    for req_data in agent_result.data.get("requirements", []):
        req = await requirement_service.create_requirement(
            db=db,
            data=RequirementCreate(
                project_id=body.project_id,
                title=req_data.get("title", "Untitled Requirement"),
                summary=req_data.get("summary"),
                source="doc_upload",
                source_document_id=doc.id,
            ),
            user_id=(current_user.id if current_user else 1),
        )
        req.acceptance_criteria = req_data.get("acceptance_criteria")
        req.business_rules = req_data.get("business_rules")
        req.user_roles = req_data.get("user_roles")
        req.systems_impacted = req_data.get("systems_impacted")
        req.ui_pages = req_data.get("ui_pages")
        req.apis = req_data.get("apis")
        req.dependencies = req_data.get("dependencies")
        req.risks = req_data.get("risks")
        req.missing_information = req_data.get("missing_information")
        req.status = "pending_review"
        await db.flush()
        created.append(req.id)

    await db.commit()
    return {
        "message": f"Intake agent completed. {len(created)} requirements extracted.",
        "requirement_ids": created,
        "agent_logs": agent_result.logs,
    }


@router.post("/agent/quality")
async def trigger_quality_agent(
    body: AgentTriggerRequest,
    db: DBSession,
    current_user: OptionalUser,
):
    """Trigger Agent 2 (Quality Review) on selected or all requirements."""
    if body.requirement_ids:
        reqs = []
        for rid in body.requirement_ids:
            r = await requirement_service.get_requirement(db, rid)
            if r:
                reqs.append(r)
    else:
        reqs = await requirement_service.list_requirements(db, body.project_id)

    if not reqs:
        raise HTTPException(status_code=404, detail="No requirements found")

    req_dicts = [
        {
            "id": r.id,
            "requirement_id": r.requirement_id,
            "title": r.title,
            "summary": r.summary,
            "acceptance_criteria": r.acceptance_criteria,
            "business_rules": r.business_rules,
            "user_roles": r.user_roles,
            "systems_impacted": r.systems_impacted,
            "ui_pages": r.ui_pages,
            "apis": r.apis,
            "dependencies": r.dependencies,
            "risks": r.risks,
            "missing_information": r.missing_information,
        }
        for r in reqs
    ]

    agent = RequirementQualityAgent()
    agent_result = await agent.run(
        requirements=req_dicts,
        project_id=body.project_id,
    )

    if not agent_result.success:
        raise HTTPException(status_code=500, detail=agent_result.error or "Quality agent failed")

    # Apply quality scores / feedback back to each requirement
    updated_ids = []
    quality_data = agent_result.data.get("quality_results", {})
    for req in reqs:
        qr = quality_data.get(str(req.id)) or quality_data.get(req.id)
        if qr:
            if "quality_score" in qr:
                req.quality_score = qr["quality_score"]
            if "quality_feedback" in qr:
                req.quality_feedback = qr["quality_feedback"]
            if "missing_information" in qr:
                req.missing_information = qr["missing_information"]
            await db.flush()
            updated_ids.append(req.id)

    await db.commit()
    return {
        "message": f"Quality review completed. {len(updated_ids)} requirements updated.",
        "requirement_ids": updated_ids,
        "agent_logs": agent_result.logs,
    }
