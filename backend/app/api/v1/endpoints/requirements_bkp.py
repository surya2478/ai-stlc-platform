"""Requirements endpoints."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, func

from app.api.deps import CurrentUser, DBSession, require_entity_permission, require_entity_project_access, require_permission, require_project_access
from app.config import get_settings
from app.models.requirement import Requirement
from app.models.document import UploadedDocument
from app.schemas.requirement import (
    RequirementCreate, RequirementUpdate, RequirementOut,
    RequirementListOut, AgentTriggerRequest, ApprovalRequest,
)
from app.schemas.common import MessageResponse
from app.services import agent_run_service, approval_service, requirement_service, traceability_service
from app.services.agent_dispatch_service import enqueue_agent_run
from app.services.rbac_service import APPROVE_REQUIREMENTS, VIEW_PROJECT
from app.agents.requirement.intake_agent import RequirementIntakeAgent
from app.agents.requirement.quality_agent import RequirementQualityAgent

router = APIRouter()
settings = get_settings()


def _run_agents_synchronously() -> bool:
    return False


@router.get("/project/{project_id}", response_model=list[RequirementOut])
async def list_requirements(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    status: str | None = Query(None),
    qa_domain: str | None = Query(None),
    product_group: str | None = Query(None),
    product: str | None = Query(None),
    sub_request_type: str | None = Query(None),
    risk_level: str | None = Query(None),
    test_phase: str | None = Query(None),
    readiness_status: str | None = Query(None),
    sync_status: str | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    if limit > 200:
        limit = 200
    await require_project_access(project_id, current_user, db)
    return await requirement_service.list_requirements(
        db=db,
        project_id=project_id,
        status=status,
        qa_domain=qa_domain,
        product_group=product_group,
        product=product,
        sub_request_type=sub_request_type,
        risk_level=risk_level,
        test_phase=test_phase,
        readiness_status=readiness_status,
        sync_status=sync_status,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.post("/", response_model=RequirementOut, status_code=201)
async def create_requirement(
    data: RequirementCreate,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_permission(APPROVE_REQUIREMENTS, data.project_id, current_user, db)
    req = await requirement_service.create_requirement(db, data, current_user.id)
    await db.commit()
    return req


@router.get("/{req_id}", response_model=RequirementOut)
async def get_requirement(
    req_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    req = await requirement_service.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    await require_entity_permission(req, VIEW_PROJECT, current_user, db)
    return req


@router.patch("/{req_id}", response_model=RequirementOut)
async def update_requirement(
    req_id: int,
    updates: RequirementUpdate,
    db: DBSession,
    current_user: CurrentUser,
):
    req = await requirement_service.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    await require_entity_permission(req, APPROVE_REQUIREMENTS, current_user, db)
    req = await requirement_service.update_requirement(db, req, updates)
    await db.commit()
    return req


@router.delete("/{req_id}", response_model=MessageResponse)
async def delete_requirement(
    req_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    req = await requirement_service.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    await require_entity_permission(req, APPROVE_REQUIREMENTS, current_user, db)
    await requirement_service.delete_requirement(db, req)
    await db.commit()
    return {"message": "Requirement deleted"}


@router.post("/{req_id}/approve", response_model=RequirementOut)
async def approve_requirement(
    req_id: int,
    body: ApprovalRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    req = await requirement_service.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    await require_entity_permission(req, APPROVE_REQUIREMENTS, current_user, db)
    req = await requirement_service.approve_requirement(db, req, body.action, body.notes)
    await approval_service.create_approval_action(
        db,
        project_id=req.project_id,
        user_id=current_user.id,
        entity_type="requirement",
        entity_id=req.id,
        action=body.action,
        notes=body.notes,
    )
    await db.commit()
    return req


@router.post("/agent/intake")
async def trigger_intake_agent(
    body: AgentTriggerRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Trigger Agent 1 (Requirement Intake) on an uploaded document."""
    if not body.document_id:
        raise HTTPException(status_code=422, detail="document_id is required for intake agent")
    await require_permission(APPROVE_REQUIREMENTS, body.project_id, current_user, db)

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

    if not _run_agents_synchronously():
        agent_run, task_id = await enqueue_agent_run(
            db,
            project_id=body.project_id,
            user_id=current_user.id,
            agent_name="requirement_intake",
            input_data={"document_text": doc.extracted_text, "project_id": body.project_id},
            metadata={"document_id": doc.id},
        )
        return JSONResponse(
            status_code=202,
            content={"message": "Requirement intake queued", "agent_run_id": agent_run.id, "task_id": task_id},
        )

    user_id = current_user.id
    agent_run = await agent_run_service.start_agent_run(
        db,
        project_id=body.project_id,
        user_id=user_id,
        agent_name="requirement_intake",
        input_data=body.model_dump(mode="json"),
        metadata={"document_id": doc.id},
    )

    agent = RequirementIntakeAgent()
    try:
        agent_result = await agent.run(
            document_text=doc.extracted_text,
            project_id=body.project_id,
        )

        if not agent_result.success:
            await agent_run_service.fail_agent_run(
                db,
                agent_run,
                error_message=agent_result.error or "Agent failed",
                agent_result=agent_result,
            )
            await db.commit()
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
                user_id=user_id,
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
            await traceability_service.create_lineage(
                db,
                project_id=body.project_id,
                parent_type="uploaded_document",
                parent_id=doc.id,
                child_type="requirement",
                child_id=req.id,
                agent_run_id=agent_run.id,
            )
            created.append(req.id)

        await agent_run_service.complete_agent_run(
            db,
            agent_run,
            agent_result=agent_result,
            output_data={"requirement_ids": created, "count": len(created)},
        )
        await db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        await agent_run_service.fail_agent_run(db, agent_run.id, error_message=str(exc))
        await db.commit()
        raise

    return {
        "message": f"Intake agent completed. {len(created)} requirements extracted.",
        "requirement_ids": created,
        "agent_logs": agent_result.logs,
        "agent_run_id": agent_run.id,
    }


@router.post("/agent/quality")
async def trigger_quality_agent(
    body: AgentTriggerRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Trigger Agent 2 (Quality Review) on selected or all requirements."""
    await require_permission(APPROVE_REQUIREMENTS, body.project_id, current_user, db)

    if body.requirement_ids:
        reqs = []
        for rid in body.requirement_ids:
            r = await requirement_service.get_requirement(db, rid)
            if r:
                if r.project_id != body.project_id:
                    raise HTTPException(status_code=403, detail="Requirement does not belong to this project")
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

    if not _run_agents_synchronously():
        agent_run, task_id = await enqueue_agent_run(
            db,
            project_id=body.project_id,
            user_id=current_user.id,
            agent_name="requirement_quality",
            input_data={"requirements": req_dicts, "project_id": body.project_id},
            metadata={"requirement_ids": [r.id for r in reqs]},
        )
        return JSONResponse(
            status_code=202,
            content={"message": "Requirement quality review queued", "agent_run_id": agent_run.id, "task_id": task_id},
        )

    user_id = current_user.id
    agent_run = await agent_run_service.start_agent_run(
        db,
        project_id=body.project_id,
        user_id=user_id,
        agent_name="requirement_quality",
        input_data=body.model_dump(mode="json"),
        metadata={"requirement_ids": [r.id for r in reqs]},
    )

    agent = RequirementQualityAgent()
    try:
        agent_result = await agent.run(
            requirements=req_dicts,
            project_id=body.project_id,
        )

        if not agent_result.success:
            await agent_run_service.fail_agent_run(
                db,
                agent_run,
                error_message=agent_result.error or "Quality agent failed",
                agent_result=agent_result,
            )
            await db.commit()
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

        await agent_run_service.complete_agent_run(
            db,
            agent_run,
            agent_result=agent_result,
            output_data={"requirement_ids": updated_ids, "count": len(updated_ids)},
        )
        await db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        await agent_run_service.fail_agent_run(db, agent_run.id, error_message=str(exc))
        await db.commit()
        raise

    return {
        "message": f"Quality review completed. {len(updated_ids)} requirements updated.",
        "requirement_ids": updated_ids,
        "agent_logs": agent_result.logs,
        "agent_run_id": agent_run.id,
    }
