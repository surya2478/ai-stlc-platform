"""Traceability matrix, approval governance, and export endpoints (GAP-5)."""
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import Response

from app.api.deps import CurrentUser, DBSession, require_permission, require_project_access
from app.schemas.traceability import (
    ApprovalActionOut,
    ApprovalDecisionRequest,
    CoverageGapsOut,
    LineageChainOut,
    TraceabilityMatrixOut,
)
from app.services import export_service, traceability_service

router = APIRouter()


@router.get("/projects/{project_id}/matrix", response_model=TraceabilityMatrixOut)
async def get_traceability_matrix(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    domain: str | None = Query(None),
    phase: str | None = Query(None),
    release: str | None = Query(None),
    include_drafts: bool = Query(False),
):
    await require_project_access(project_id, current_user, db)
    return await traceability_service.traceability_matrix(
        db,
        project_id=project_id,
        page=page,
        page_size=page_size,
        domain=domain,
        phase=phase,
        release=release,
        include_drafts=include_drafts,
    )


@router.get("/projects/{project_id}/gaps", response_model=CoverageGapsOut)
async def get_coverage_gaps(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    include_drafts: bool = Query(False),
):
    await require_project_access(project_id, current_user, db)
    return await traceability_service.coverage_gaps(db, project_id=project_id, include_drafts=include_drafts)


@router.post("/approvals/{entity_type}/{entity_id}", response_model=ApprovalActionOut, status_code=201)
async def approve_artifact(
    entity_type: str,
    entity_id: int,
    body: ApprovalDecisionRequest,
    db: DBSession,
    current_user: CurrentUser,
    x_request_id: str | None = Header(default=None),
):
    entity = await traceability_service.get_project_entity(db, entity_type, entity_id)
    permission = traceability_service.APPROVAL_PERMISSIONS.get(entity_type)
    await require_permission(permission, entity.project_id, current_user, db)
    action = await traceability_service.approve_artifact(
        db,
        entity=entity,
        entity_type=entity_type,
        user=current_user,
        body=body,
        request_id=x_request_id,
    )
    await db.commit()
    return action



# ── GAP-5: Export endpoints ────────────────────────────────────────────────

@router.get("/projects/{project_id}/export/test-cases")
async def export_test_cases(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    format: Literal["excel", "csv", "xray"] = Query("excel", description="Export format"),
    include_drafts: bool = Query(False),
    test_case_ids: str | None = Query(
        None,
        description="Optional comma-separated test-case database IDs to export",
    ),
):
    """
    Export all test cases for a project.

    - **excel** — formatted .xlsx workbook (default)
    - **csv**   — plain RFC-4180 CSV
    - **xray**  — Xray-compatible CSV (one row per step, BDD supported)

    Edge cases:
    - Empty project → returns empty file (valid but zero data rows)
    - Test cases with null fields → exported as empty strings
    - Steps with mixed dict / string format → normalised
    - BDD test cases → emitted as Cucumber type in Xray CSV
    """
    await require_project_access(project_id, current_user, db)
    selected_ids: list[int] | None = None
    if test_case_ids is not None:
        try:
            selected_ids = sorted({
                int(value.strip())
                for value in test_case_ids.split(",")
                if value.strip()
            })
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="test_case_ids must contain only integer IDs") from exc
        if not selected_ids:
            raise HTTPException(status_code=422, detail="test_case_ids must contain at least one ID")

    if format == "excel":
        data = await export_service.export_test_cases_excel(db, project_id, include_drafts, selected_ids)
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=test_cases_project_{project_id}.xlsx"},
        )
    elif format == "csv":
        data = await export_service.export_test_cases_csv(db, project_id, include_drafts, selected_ids)
        return Response(
            content=data.encode("utf-8-sig"),  # BOM for Excel compatibility
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=test_cases_project_{project_id}.csv"},
        )
    elif format == "xray":
        data = await export_service.export_test_cases_xray_csv(db, project_id, include_drafts, selected_ids)
        return Response(
            content=data.encode("utf-8-sig"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=test_cases_xray_project_{project_id}.csv"},
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{format}'. Use excel, csv, or xray.")


@router.get("/projects/{project_id}/export/traceability-matrix")
async def export_traceability_matrix(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    format: Literal["excel", "csv"] = Query("excel", description="Export format"),
    include_drafts: bool = Query(False),
):
    """
    Export the requirement-to-test-case traceability matrix.

    - **excel** — multi-sheet workbook: Matrix + Summary (default)
    - **csv**   — flat CSV of the matrix rows

    Edge cases:
    - Requirements with no test cases → flagged in Gaps column
    - Requirements with no execution → flagged
    - Rows colour-coded: green (no gaps), amber (partial), red (no test cases)
    """
    await require_project_access(project_id, current_user, db)

    if format == "excel":
        data = await export_service.export_traceability_matrix_excel(db, project_id, include_drafts)
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=traceability_matrix_project_{project_id}.xlsx"},
        )
    elif format == "csv":
        # Re-use the Excel function and convert — simpler to just delegate CSV to test-case CSV
        data = await export_service.export_test_cases_csv(db, project_id, include_drafts)
        return Response(
            content=data.encode("utf-8-sig"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=traceability_matrix_project_{project_id}.csv"},
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{format}'. Use excel or csv.")


@router.get("/requirements/{requirement_id}/chain")
async def get_requirement_traceability_chain(
    requirement_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Return the full traceability chain for a single requirement:
    requirement → scenarios → test cases → execution results → defects

    Edge cases:
    - Requirement not in project → 404
    - No downstream artifacts → returns empty lists, not an error
    - Test cases linked via scenario OR directly via requirement_id → both included
    - Execution results returned newest-first
    """
    # Need project_id to guard access — fetch via service then check
    try:
        # First get project_id from the requirement (no auth guard yet)
        from sqlalchemy import select as sa_select
        from app.models.requirement import Requirement as ReqModel
        req_row = await db.execute(sa_select(ReqModel).where(ReqModel.id == requirement_id))
        req_obj = req_row.scalar_one_or_none()
        if req_obj is None:
            raise HTTPException(status_code=404, detail="Requirement not found")
        await require_project_access(req_obj.project_id, current_user, db)
        chain = await export_service.get_requirement_traceability_chain(
            db, requirement_id=requirement_id, project_id=req_obj.project_id
        )
        return chain
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ── End GAP-5 export endpoints ─────────────────────────────────────────────

@router.get("/lineage/{entity_type}/{entity_id}", response_model=LineageChainOut)
async def get_artifact_lineage(
    entity_type: str,
    entity_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """Entity-centric lineage chain over the artifact_lineage table.

    Returns upstream ancestors (e.g. the requirement a script came from) and
    downstream descendants (e.g. the runs a script produced), each hydrated
    with display ref/title/status and ordered by STLC pipeline position.

    Edge cases:
    - Unsupported entity_type or missing entity → 404
    - Entity exists but has no lineage rows (pre-lineage data) → empty lists, 200
    """
    entity = await traceability_service.get_project_entity(db, entity_type, entity_id)
    await require_project_access(entity.project_id, current_user, db)
    return await traceability_service.get_lineage_chain(
        db,
        project_id=entity.project_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )


@router.get("/projects/{project_id}/approvals", response_model=list[ApprovalActionOut])
async def list_project_approvals(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    await require_project_access(project_id, current_user, db)
    actions, _total = await traceability_service.approval_history(
        db,
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        page_size=page_size,
    )
    return actions


@router.get("/approvals/{entity_type}/{entity_id}", response_model=list[ApprovalActionOut])
async def list_artifact_approvals(
    entity_type: str,
    entity_id: int,
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    entity = await traceability_service.get_project_entity(db, entity_type, entity_id)
    await require_project_access(entity.project_id, current_user, db)
    actions, _total = await traceability_service.approval_history(
        db,
        project_id=entity.project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        page_size=page_size,
    )
    return actions
