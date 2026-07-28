"""Requirements endpoints — updated with telecom fields, stats, filters, fixed permissions."""
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, func

from app.api.deps import CurrentUser, DBSession, require_entity_permission, require_project_access, require_permission
from app.config import get_settings
from app.models.requirement import Requirement
from app.models.requirement_review import RequirementQualityReview
from app.models.document import UploadedDocument
from app.schemas.requirement import (
    RequirementCreate, RequirementUpdate, RequirementOut,
    RequirementListOut, AgentTriggerRequest, ApprovalRequest, RequirementStatsOut,
    URLAnalysisRequest, CodeAnalysisRequest, RequirementTransitionRequest,
)
from app.schemas.common import MessageResponse
from app.services import agent_run_service, approval_service, coverage_service, requirement_service, traceability_service
from app.services.agent_dispatch_service import enqueue_agent_run
from app.services.rbac_service import APPROVE_REQUIREMENTS, VIEW_PROJECT
from app.agents.requirement.intake_agent import RequirementIntakeAgent
from app.agents.requirement.quality_agent import RequirementQualityAgent
from app.llm.provider import validate_vision_configuration

router = APIRouter()
settings = get_settings()


def _normalize_github_repo_target(raw_url: str, fallback_branch: str) -> tuple[str, str, str | None]:
    """
    Accept either a cloneable repo URL:
      https://github.com/org/repo
    or a GitHub tree URL:
      https://github.com/org/repo/tree/main/path/to/folder

    Returns:
      (repo_clone_url, branch, subpath)
    """
    parsed = urlparse(raw_url.strip())
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        raise HTTPException(status_code=422, detail="github_url must point to a GitHub repository")

    owner, repo = path_parts[0], path_parts[1]
    repo_url = f"{parsed.scheme}://{parsed.netloc}/{owner}/{repo}"

    if len(path_parts) >= 4 and path_parts[2] == "tree":
        branch = path_parts[3].strip() or fallback_branch
        subpath = "/".join(path_parts[4:]).strip("/") or None
        return repo_url, branch, subpath

    return repo_url, fallback_branch, None


def _run_agents_synchronously() -> bool:
    return False


# ── READ endpoints — require view_project (not approve_requirements) ───────────

@router.get("/project/{project_id}/stats", response_model=RequirementStatsOut)
async def get_requirement_stats(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """Summary statistics for the Requirements Command Center."""
    await require_project_access(project_id, current_user, db)
    return await requirement_service.get_requirement_stats(db, project_id)


@router.get("/project/{project_id}", response_model=list[RequirementOut])
async def list_requirements(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    status: str | None = Query(None),
    search: str | None = Query(None, description="Text search on title, summary, req ID, Jira key"),
    telecom_domain: str | None = Query(None),
    risk_level: str | None = Query(None),
    test_phase: str | None = Query(None),
    readiness_status: str | None = Query(None),
    sync_status: str | None = Query(None),
    has_quality_review: bool | None = Query(None),
    source: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    # P0-06 fix: use require_project_access (VIEW_PROJECT), not APPROVE_REQUIREMENTS
    await require_project_access(project_id, current_user, db)
    return await requirement_service.list_requirements(
        db, project_id,
        status=status,
        skip=skip,
        limit=limit,
        search=search,
        telecom_domain=telecom_domain,
        risk_level=risk_level,
        test_phase=test_phase,
        readiness_status=readiness_status,
        sync_status=sync_status,
        has_quality_review=has_quality_review,
        source=source,
    )


@router.get("/{req_id}", response_model=RequirementOut)
async def get_requirement(
    req_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    req = await requirement_service.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    # P0-06 fix: use require_project_access, not APPROVE_REQUIREMENTS
    await require_project_access(req.project_id, current_user, db)
    return req


@router.get("/{req_id}/quality-reviews")
async def get_requirement_quality_reviews(
    req_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """Return all quality reviews for a requirement (approval history)."""
    req = await requirement_service.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    await require_project_access(req.project_id, current_user, db)
    result = await db.execute(
        select(RequirementQualityReview)
        .where(RequirementQualityReview.requirement_id == req_id)
        .order_by(RequirementQualityReview.created_at.desc())
    )
    reviews = result.scalars().all()
    return [
        {
            "id": r.id,
            "quality_score": r.quality_score,
            "verdict": r.verdict,
            "completeness_score": r.completeness_score,
            "clarity_score": r.clarity_score,
            "testability_score": r.testability_score,
            "ambiguity_score": r.ambiguity_score,
            "acceptance_criteria_score": r.acceptance_criteria_score,
            "interface_readiness_score": r.interface_readiness_score,
            "telecom_domain_completeness": r.qa_domain_completeness,  # live DB column name
            "scenario_generation_readiness": r.scenario_generation_readiness,
            "ambiguities": r.ambiguities,
            "missing_details": r.missing_details,
            "recommendations": r.recommendations,
            "clarification_questions": r.clarification_questions,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "agent_run_id": r.agent_run_id,
        }
        for r in reviews
    ]


# ── GAP-4d: Coverage & prioritization analytics ───────────────────────────────

@router.get("/project/{project_id}/coverage-summary")
async def get_project_coverage_summary(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    limit: int = Query(200, ge=1, le=500),
):
    """Coverage matrix and risk-based test-first ranking for all requirements."""
    await require_project_access(project_id, current_user, db)
    return await coverage_service.get_project_coverage_summary(db, project_id, limit=limit)


@router.get("/{req_id}/coverage")
async def get_requirement_coverage(
    req_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """Coverage detail (test-type mix, gaps, priority score) for one requirement."""
    req = await requirement_service.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    await require_project_access(req.project_id, current_user, db)
    return await coverage_service.get_requirement_coverage(db, req)


# ── WRITE endpoints — require approve_requirements ────────────────────────────

@router.post("", response_model=RequirementOut, status_code=201)
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
    await require_permission(APPROVE_REQUIREMENTS, req.project_id, current_user, db)
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
    await require_permission(APPROVE_REQUIREMENTS, req.project_id, current_user, db)
    await requirement_service.delete_requirement(db, req)
    await db.commit()
    return {"message": "Requirement archived"}


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
    await require_permission(APPROVE_REQUIREMENTS, req.project_id, current_user, db)
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


@router.post("/{req_id}/transition", response_model=RequirementOut)
async def transition_requirement(
    req_id: int,
    body: RequirementTransitionRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    req = await requirement_service.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    await require_permission(APPROVE_REQUIREMENTS, req.project_id, current_user, db)
    previous_stage = requirement_service.requirement_workflow_stage(req)
    req = await requirement_service.transition_requirement(
        db, req, body.action, body.notes, current_user.id
    )
    await approval_service.create_approval_action(
        db,
        project_id=req.project_id,
        user_id=current_user.id,
        entity_type="requirement",
        entity_id=req.id,
        action=body.action,
        notes=body.notes,
        decision="transitioned",
        old_value={"workflow_stage": previous_stage},
        new_value={"workflow_stage": requirement_service.requirement_workflow_stage(req)},
    )
    await db.commit()
    return req


# ── Agent endpoints ────────────────────────────────────────────────────────────

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
    if doc.project_id != body.project_id:
        raise HTTPException(status_code=403, detail="Document does not belong to this project")
    if doc.status == "failed":
        raise HTTPException(status_code=422, detail="Document extraction failed — please re-upload the file")
    if not doc.extracted_text:
        raise HTTPException(status_code=422, detail="Document has no extracted text yet")

    existing_count_res = await db.execute(
        select(func.count()).where(
            Requirement.project_id == body.project_id,
            Requirement.source_document_id == doc.id,
            Requirement.is_deleted.is_(False),
        )
    )
    existing_count = existing_count_res.scalar_one()
    if existing_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This document has already been processed and produced {existing_count} requirement(s). "
                "Archive the existing requirements first if you want to re-run extraction."
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
                db, agent_run,
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
                    telecom_domain=req_data.get("telecom_domain"),
                    qa_domain=req_data.get("qa_domain"),
                    risk_level=req_data.get("risk_level"),
                    test_phase=req_data.get("test_phase"),
                    release_version=req_data.get("release_version"),
                ),
                user_id=user_id,
            )
            # Set all structured fields from agent output
            req.acceptance_criteria = req_data.get("acceptance_criteria")
            req.business_rules = req_data.get("business_rules")
            req.user_roles = req_data.get("user_roles")
            req.systems_impacted = req_data.get("systems_impacted")
            req.ui_pages = req_data.get("ui_pages")
            req.apis = req_data.get("apis")
            req.dependencies = req_data.get("dependencies")
            req.risks = req_data.get("risks")
            req.missing_information = req_data.get("missing_information")
            # Telecom fields from intake agent
            req.impacted_interfaces = req_data.get("impacted_interfaces")
            req.upstream_systems = req_data.get("upstream_systems")
            req.downstream_systems = req_data.get("downstream_systems")
            req.regulatory_impact = req_data.get("regulatory_impact", False)
            req.revenue_impact = req_data.get("revenue_impact", False)
            req.readiness_status = "intake_ready"
            req.status = "draft"
            req.metadata_ = {**(req.metadata_ or {}), "workflow_stage": "intake"}
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
            db, agent_run,
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


@router.post("/agent/ui-analysis")
async def trigger_ui_analysis_agent(
    body: AgentTriggerRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """GAP-1: Trigger the UI Analysis (vision) agent on an uploaded screenshot.

    Generates structured requirements (fields, validations, flows, negative and
    edge cases) from a UI image. Downstream quality/scenario/test-case agents
    work on the result unchanged.
    """
    if not body.document_id:
        raise HTTPException(status_code=422, detail="document_id is required for UI analysis")
    await require_permission(APPROVE_REQUIREMENTS, body.project_id, current_user, db)

    result = await db.execute(
        select(UploadedDocument).where(UploadedDocument.id == body.document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.project_id != body.project_id:
        raise HTTPException(status_code=403, detail="Document does not belong to this project")
    if doc.file_type not in ("png", "jpg", "webp"):
        raise HTTPException(
            status_code=422,
            detail=f"Document is not a UI image (type: {doc.file_type}). Upload a PNG, JPG, or WebP screenshot.",
        )

    vision_config_error = validate_vision_configuration()
    if vision_config_error:
        raise HTTPException(status_code=422, detail=vision_config_error)

    existing_count_res = await db.execute(
        select(func.count()).where(
            Requirement.project_id == body.project_id,
            Requirement.source_document_id == doc.id,
            Requirement.is_deleted.is_(False),
        )
    )
    existing_count = existing_count_res.scalar_one()
    if existing_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This screenshot has already been analysed and produced {existing_count} requirement(s). "
                "Archive the existing requirements first if you want to re-run the analysis."
            ),
        )

    agent_run, task_id = await enqueue_agent_run(
        db,
        project_id=body.project_id,
        user_id=current_user.id,
        agent_name="ui_image_analysis",
        input_data={
            "image_path": doc.file_path,
            "image_name": doc.original_filename,
            "context_note": body.context_note or "",
            "project_id": body.project_id,
        },
        metadata={"document_id": doc.id},
    )
    return JSONResponse(
        status_code=202,
        content={"message": "UI screenshot analysis queued", "agent_run_id": agent_run.id, "task_id": task_id},
    )


@router.post("/agent/url-analysis")
async def trigger_url_analysis_agent(
    body: URLAnalysisRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """GAP-2: Trigger the Portal URL Analysis agent on a live application URL.

    The worker renders the page(s) with Playwright, extracts the DOM inventory,
    captures screenshots, and derives structured requirements (source
    'portal_url'). Same-origin crawling only, depth 0-2, max 5 pages.
    """
    await require_permission(APPROVE_REQUIREMENTS, body.project_id, current_user, db)

    # Fast-fail validation before queueing (scheme + SSRF guard)
    from app.services.url_capture_service import UnsafeURLError, validate_url_safety

    try:
        normalized_url = validate_url_safety(body.url)
    except UnsafeURLError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    agent_run, task_id = await enqueue_agent_run(
        db,
        project_id=body.project_id,
        user_id=current_user.id,
        agent_name="url_analysis",
        input_data={
            "url": normalized_url,
            "crawl_depth": body.crawl_depth,
            "context_note": body.context_note or "",
            "project_id": body.project_id,
        },
        metadata={"source_url": normalized_url, "crawl_depth": body.crawl_depth},
    )
    return JSONResponse(
        status_code=202,
        content={"message": "Portal URL analysis queued", "agent_run_id": agent_run.id, "task_id": task_id},
    )


@router.post("/agent/code-analysis")
async def trigger_code_analysis_agent(
    body: CodeAnalysisRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """GAP-3: Trigger code analysis on a GitHub repository or local directory.

    The agent:
      1. Clones the repo (GitHub) or walks the directory tree (local).
      2. Extracts public functions, classes, REST endpoints, and module docstrings
         for the requested language(s).
      3. Sends each logical unit to the LLM to derive structured requirements
         (source 'github_repo' or 'local_repo').

    Edge cases:
      - Private repos require a PAT with repo read scope.
      - Local paths must be reachable by the backend process.
      - Repos > 500 MB are rejected before cloning.
      - Hidden dirs (.git, node_modules, __pycache__, .venv) are always skipped.
    """
    await require_permission(APPROVE_REQUIREMENTS, body.project_id, current_user, db)

    # Basic source-specific validation
    if body.source == "github":
        if not body.github_url:
            raise HTTPException(status_code=422, detail="github_url is required when source='github'")
        normalized_repo_url, normalized_branch, github_subpath = _normalize_github_repo_target(
            body.github_url,
            body.github_branch or "main",
        )
        body.github_url = normalized_repo_url
        body.github_branch = normalized_branch
    elif body.source == "local":
        if not body.local_path:
            raise HTTPException(status_code=422, detail="local_path is required when source='local'")
        github_subpath = None
        import os

        # Translate Windows host path to container-accessible path if possible
        local_path = body.local_path
        normalized_path = local_path.replace("\\", "/")
        allowed_raw = settings.allowed_code_analysis_paths or ""
        allowed_list = [p.strip() for p in allowed_raw.split(",") if p.strip()]

        translated_path = None
        for allowed in allowed_list:
            normalized_allowed = allowed.replace("\\", "/")
            if normalized_path.lower().startswith(normalized_allowed.lower()):
                relative_part = normalized_path[len(normalized_allowed):].lstrip("/")
                # Check /repo mount
                candidate_repo = os.path.join("/repo", relative_part)
                if os.path.exists(candidate_repo):
                    translated_path = candidate_repo
                    break
                # Check /app mount (if backend subfolder)
                backend_allowed = os.path.join(normalized_allowed, "backend").replace("\\", "/")
                if normalized_path.lower().startswith(backend_allowed.lower()):
                    relative_backend = normalized_path[len(backend_allowed):].lstrip("/")
                    candidate_app = os.path.join("/app", relative_backend)
                    if os.path.exists(candidate_app):
                        translated_path = candidate_app
                        break

        if translated_path:
            body.local_path = translated_path

        if not os.path.exists(body.local_path):
            raise HTTPException(status_code=422, detail=f"local_path does not exist: {body.local_path}")
        if not os.path.isdir(body.local_path):
            raise HTTPException(status_code=422, detail="local_path must be a directory")

        # SEC-013 Path Traversal Fix
        resolved_local_path = os.path.realpath(body.local_path)
        allowed_paths = settings.allowed_code_analysis_paths_list
        is_allowed = False
        for allowed in allowed_paths:
            try:
                if os.path.commonpath([allowed, resolved_local_path]) == allowed:
                    is_allowed = True
                    break
            except ValueError:
                continue
        if not is_allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Access denied: path is outside allowed directories for code analysis: {body.local_path}"
            )

    source_label = "github_repo" if body.source == "github" else "local_repo"
    display_target = body.github_url or body.local_path or ""
    if body.source == "github" and github_subpath:
        display_target = f"{display_target}/tree/{body.github_branch}/{github_subpath}"

    agent_run, task_id = await enqueue_agent_run(
        db,
        project_id=body.project_id,
        user_id=current_user.id,
        agent_name="code_analysis",
        input_data={
            "source": body.source,
            "github_url": body.github_url,
            "github_branch": body.github_branch,
            "github_token": body.github_token,
            "github_subpath": github_subpath,
            "local_path": body.local_path,
            "languages": body.languages,
            "project_id": body.project_id,
            "source_label": source_label,
        },
        metadata={
            "repo_target": display_target,
            "source_type": source_label,
            "languages": body.languages,
        },
    )
    return JSONResponse(
        status_code=202,
        content={
            "message": f"Code analysis queued for {display_target}",
            "agent_run_id": agent_run.id,
            "task_id": task_id,
        },
    )


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
        reqs = await requirement_service.list_requirements(db, body.project_id, limit=200)

    if not reqs:
        raise HTTPException(status_code=404, detail="No requirements found")

    analysis_reqs = [r for r in reqs if requirement_service.requirement_workflow_stage(r) == "analysis"]
    if not body.requirement_ids:
        analysis_reqs = [r for r in analysis_reqs if r.quality_score is None]
    if not analysis_reqs:
        raise HTTPException(
            status_code=409,
            detail="No selected requirements are eligible for analysis. Send intake records to Analysis first."
        )
    reqs = analysis_reqs

    # Include the current persisted revision and every quality-relevant field.
    # This makes a post-edit Re-run distinct from the completed pre-edit run.
    req_dicts = [requirement_service.build_quality_agent_input(r) for r in reqs]

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
                db, agent_run,
                error_message=agent_result.error or "Quality agent failed",
                agent_result=agent_result,
            )
            await db.commit()
            raise HTTPException(status_code=500, detail=agent_result.error or "Quality agent failed")

        updated_ids = []
        quality_data: dict = agent_result.data.get("quality_results", {})

        req_by_id = {r.id: r for r in reqs}

        for str_id, qr in quality_data.items():
            try:
                req_id = int(str_id)
            except (ValueError, TypeError):
                continue
            req = req_by_id.get(req_id)
            if not req or not qr:
                continue

            overall = qr.get("overall_score")
            verdict = qr.get("verdict")
            scenario_readiness = qr.get("scenario_generation_readiness")

          
            # Denormalise quality scores onto the Requirement row
            feedback_parts = []
            if qr.get("issues"):
                feedback_parts.append("Issues: " + "; ".join(qr["issues"][:3]))
            if qr.get("suggestions"):
                feedback_parts.append("Suggestions: " + "; ".join(qr["suggestions"][:2]))
            feedback = " | ".join(feedback_parts) if feedback_parts else None

            await requirement_service.update_quality_scores(
                db, req,
                quality_score=overall,
                quality_feedback=feedback,
                quality_verdict=verdict,
                scenario_generation_readiness=scenario_readiness,
            )

            # Compact summary in metadata_ — Requirements UI reads this
            metadata = dict(req.metadata_ or {})
            metadata["quality_review"] = {
                "overall_score": overall,
                "verdict": verdict,
                "scenario_generation_readiness": scenario_readiness,
                "agent_run_id": agent_run.id,
            }
            req.metadata_ = metadata
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
