"""UI-016 Application Model endpoints — /api/v1/lab/application-models/*.

Deliberately isolated namespace, same 404-when-disabled pattern as
discovery.py / automation_classification.py: every route 404s when
APPLICATION_MODELS_ENABLED is off. Phase 1 only — see the approved
implementation plan for what's deferred.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, require_entity_permission, require_permission
from app.config import get_settings
from app.models.application_model import (
    ApplicationModel,
    ApplicationModelActivity,
    ApplicationModelEdge,
    ApplicationModelGap,
    ApplicationModelLocatorEvidence,
    ApplicationModelNode,
)
from app.models.approval import ApprovalAction
from app.schemas.application_model import (
    ApplicationModelDetailOut,
    ApplicationModelEdgeOut,
    ApplicationModelGapOut,
    ApplicationModelNodeOut,
    ApplicationModelOut,
    BuildModelRequest,
    DecisionRequest,
    LocatorConfirmRequest,
    LocatorEvidenceOut,
    LocatorFallbackRequest,
    LocatorUnstableRequest,
    RenameNodeRequest,
    ResolveGapRequest,
)
from app.services import application_model_service as svc
from app.services.rbac_service import (
    APPLICATION_MODEL_APPROVE,
    APPLICATION_MODEL_BUILD,
    APPLICATION_MODEL_EDIT,
    APPLICATION_MODEL_EXPORT,
    APPLICATION_MODEL_PUBLISH,
    APPLICATION_MODEL_RESOLVE_GAPS,
    APPLICATION_MODEL_REVIEW,
    APPLICATION_MODEL_VALIDATE_LOCATORS,
    APPLICATION_MODEL_VIEW,
    APPLICATION_MODEL_VIEW_AUDIT,
)

router = APIRouter()


def _require_enabled() -> None:
    if not get_settings().application_models_enabled:
        raise HTTPException(status_code=404, detail="Application Model is disabled (APPLICATION_MODELS_ENABLED=false)")


async def _detail(db: DBSession, model: ApplicationModel) -> ApplicationModelDetailOut:
    kpis = await svc.compute_kpis(db, model)
    stale = await svc.is_stale(db, model)
    return ApplicationModelDetailOut(
        **ApplicationModelOut.model_validate(model).model_dump(),
        kpis=kpis,
        stale=stale,
        requires_separate_approver=get_settings().require_separate_approver,
    )


@router.get("/projects/{project_id}/applications/{application_id}/models", response_model=list[ApplicationModelOut])
async def list_models(project_id: int, application_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    await require_permission(APPLICATION_MODEL_VIEW, project_id, current_user, db)
    return await svc.list_models(db, project_id=project_id, application_id=application_id)


@router.post("/build", response_model=ApplicationModelDetailOut)
async def build_model(payload: BuildModelRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    await require_permission(APPLICATION_MODEL_BUILD, payload.project_id, current_user, db)
    model = await svc.build_or_rebuild_draft(
        db, project_id=payload.project_id, application_id=payload.application_id, session_id=payload.session_id,
        actor_id=current_user.id,
    )
    return await _detail(db, model)


@router.get("/{model_id}", response_model=ApplicationModelDetailOut)
async def get_model(model_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_VIEW, current_user, db)
    return await _detail(db, model)


@router.get("/{model_id}/nodes", response_model=list[ApplicationModelNodeOut])
async def list_nodes(model_id: int, db: DBSession, current_user: CurrentUser, node_type: str | None = None):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_VIEW, current_user, db)
    query = select(ApplicationModelNode).where(ApplicationModelNode.model_id == model_id)
    if node_type:
        query = query.where(ApplicationModelNode.node_type == node_type)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{model_id}/edges", response_model=list[ApplicationModelEdgeOut])
async def list_edges(model_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_VIEW, current_user, db)
    result = await db.execute(select(ApplicationModelEdge).where(ApplicationModelEdge.model_id == model_id))
    return list(result.scalars().all())


@router.get("/{model_id}/gaps", response_model=list[ApplicationModelGapOut])
async def list_gaps(model_id: int, db: DBSession, current_user: CurrentUser, status: str | None = None):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_VIEW, current_user, db)
    query = select(ApplicationModelGap).where(ApplicationModelGap.model_id == model_id)
    if status:
        query = query.where(ApplicationModelGap.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{model_id}/nodes/{node_id}/locator-history", response_model=list[LocatorEvidenceOut])
async def locator_history(model_id: int, node_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_VIEW, current_user, db)
    node = await db.get(ApplicationModelNode, node_id)
    if node is None or node.model_id != model_id:
        raise HTTPException(status_code=404, detail="Node not found in this model")
    result = await db.execute(
        select(ApplicationModelLocatorEvidence)
        .where(ApplicationModelLocatorEvidence.node_id == node_id)
        .order_by(ApplicationModelLocatorEvidence.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/{model_id}/submit-review", response_model=ApplicationModelDetailOut)
async def submit_review(model_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_EDIT, current_user, db)
    model = await svc.submit_for_review(db, model, actor_id=current_user.id)
    return await _detail(db, model)


@router.post("/{model_id}/request-changes", response_model=ApplicationModelDetailOut)
async def request_changes(model_id: int, payload: DecisionRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_REVIEW, current_user, db)
    model = await svc.request_changes(db, model, actor_id=current_user.id, reason=payload.reason or "")
    await approval_entry(db, model, current_user.id, "request_changes", "requested_changes", payload.reason)
    return await _detail(db, model)


@router.post("/{model_id}/reject", response_model=ApplicationModelDetailOut)
async def reject_model(model_id: int, payload: DecisionRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_REVIEW, current_user, db)
    model = await svc.reject(db, model, actor_id=current_user.id, reason=payload.reason or "")
    await approval_entry(db, model, current_user.id, "reject", "rejected", payload.reason)
    return await _detail(db, model)


@router.post("/{model_id}/approve", response_model=ApplicationModelDetailOut)
async def approve_model(model_id: int, payload: DecisionRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_APPROVE, current_user, db)
    model = await svc.approve(db, model, actor_id=current_user.id, reason=payload.reason)
    await approval_entry(db, model, current_user.id, "approve", "approved", payload.reason)
    return await _detail(db, model)


@router.post("/{model_id}/publish", response_model=ApplicationModelDetailOut)
async def publish_model(model_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_PUBLISH, current_user, db)
    model = await svc.publish(db, model, actor_id=current_user.id)
    await approval_entry(db, model, current_user.id, "publish", "approved", None)
    return await _detail(db, model)


@router.post("/{model_id}/new-draft", response_model=ApplicationModelDetailOut)
async def new_draft(model_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_EDIT, current_user, db)
    model = await svc.create_new_draft(db, model, actor_id=current_user.id)
    return await _detail(db, model)


@router.patch("/{model_id}/nodes/{node_id}", response_model=ApplicationModelNodeOut)
async def rename_node(model_id: int, node_id: int, payload: RenameNodeRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_EDIT, current_user, db)
    return await svc.rename_node(db, model, node_id, display_name=payload.display_name, actor_id=current_user.id)


@router.post("/{model_id}/nodes/{node_id}/locator/confirm", response_model=LocatorEvidenceOut)
async def confirm_locator(model_id: int, node_id: int, payload: LocatorConfirmRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_VALIDATE_LOCATORS, current_user, db)
    return await svc.confirm_locator(db, model, node_id, actor_id=current_user.id)


@router.post("/{model_id}/nodes/{node_id}/locator/mark-unstable", response_model=LocatorEvidenceOut)
async def mark_locator_unstable(model_id: int, node_id: int, payload: LocatorUnstableRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_VALIDATE_LOCATORS, current_user, db)
    return await svc.mark_locator_unstable(db, model, node_id, actor_id=current_user.id, reason=payload.reason)


@router.post("/{model_id}/nodes/{node_id}/locator/fallback", response_model=LocatorEvidenceOut)
async def add_fallback_locator(model_id: int, node_id: int, payload: LocatorFallbackRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_VALIDATE_LOCATORS, current_user, db)
    return await svc.add_fallback_locator(
        db, model, node_id, actor_id=current_user.id, locator_value=payload.locator_value, locator_type=payload.locator_type,
    )


@router.post("/{model_id}/gaps/{gap_id}/resolve", response_model=ApplicationModelGapOut)
async def resolve_gap(model_id: int, gap_id: int, payload: ResolveGapRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_RESOLVE_GAPS, current_user, db)
    return await svc.resolve_gap(db, model, gap_id, actor_id=current_user.id, reviewer_notes=payload.reviewer_notes)


@router.get("/{model_id}/activity")
async def get_activity(model_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_VIEW_AUDIT, current_user, db)

    activity_result = await db.execute(
        select(ApplicationModelActivity).where(ApplicationModelActivity.model_id == model_id)
    )
    approvals_result = await db.execute(
        select(ApprovalAction).where(ApprovalAction.entity_type == "application_model", ApprovalAction.entity_id == model_id)
    )
    entries = [
        {
            "id": f"activity-{row.id}", "at": row.created_at.isoformat(), "actor_id": row.actor_id,
            "event_type": row.event_type, "node_id": row.node_id, "reason": row.reason,
            "old_value": row.old_value, "new_value": row.new_value,
        }
        for row in activity_result.scalars().all()
    ] + [
        {
            "id": f"approval-{row.id}", "at": row.created_at.isoformat(), "actor_id": row.user_id,
            "event_type": row.decision, "node_id": None, "reason": row.notes,
            "old_value": row.old_value, "new_value": row.new_value,
        }
        for row in approvals_result.scalars().all()
    ]
    entries.sort(key=lambda e: e["at"], reverse=True)
    return entries


@router.get("/{model_id}/export")
async def export_model(model_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    model = await svc.get_model_or_404(db, model_id)
    await require_entity_permission(model, APPLICATION_MODEL_EXPORT, current_user, db)

    nodes_result = await db.execute(select(ApplicationModelNode).where(ApplicationModelNode.model_id == model_id))
    edges_result = await db.execute(select(ApplicationModelEdge).where(ApplicationModelEdge.model_id == model_id))
    gaps_result = await db.execute(select(ApplicationModelGap).where(ApplicationModelGap.model_id == model_id))

    payload = {
        "model": ApplicationModelOut.model_validate(model).model_dump(mode="json"),
        "nodes": [ApplicationModelNodeOut.model_validate(n).model_dump(mode="json") for n in nodes_result.scalars().all()],
        "edges": [ApplicationModelEdgeOut.model_validate(e).model_dump(mode="json") for e in edges_result.scalars().all()],
        "gaps": [ApplicationModelGapOut.model_validate(g).model_dump(mode="json") for g in gaps_result.scalars().all()],
    }
    headers = {"Content-Disposition": f'attachment; filename="application-model-{model_id}-v{model.version}.json"'}
    return JSONResponse(content=json.loads(json.dumps(payload, default=str)), headers=headers)


async def approval_entry(db: DBSession, model: ApplicationModel, user_id: int, action: str, decision: str, notes: str | None) -> None:
    from app.services import approval_service

    await approval_service.create_approval_action(
        db, project_id=model.project_id, user_id=user_id, entity_type="application_model", entity_id=model.id,
        action=action, decision=decision, notes=notes,
    )
    await db.commit()
