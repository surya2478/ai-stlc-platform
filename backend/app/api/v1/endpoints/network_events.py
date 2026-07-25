"""UI-017 API and Network Explorer endpoints — /api/v1/lab/network-explorer/*.

Deliberately isolated namespace, same 404-when-disabled pattern as
discovery.py / application_models.py: every route 404s when
NETWORK_EXPLORER_ENABLED is off. Phase 1 only — see
`app.services.network_event_service` for what is genuinely parsed from
captured evidence versus intentionally out of scope this phase.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DBSession, require_entity_permission
from app.config import get_settings
from app.schemas.network_event import (
    BuildEventsRequest,
    IgnoreEventRequest,
    NetworkEventActivityOut,
    NetworkEventKpisOut,
    NetworkEventOut,
    ReviewEventRequest,
)
from app.services import network_event_service as svc
from app.services.rbac_service import (
    NETWORK_EXPLORER_BUILD,
    NETWORK_EXPLORER_EXPORT,
    NETWORK_EXPLORER_REVIEW,
    NETWORK_EXPLORER_VIEW,
    NETWORK_EXPLORER_VIEW_AUDIT,
)

router = APIRouter()


def _require_enabled() -> None:
    if not get_settings().network_explorer_enabled:
        raise HTTPException(status_code=404, detail="API & Network Explorer is disabled (NETWORK_EXPLORER_ENABLED=false)")


@router.post("/build", response_model=NetworkEventKpisOut)
async def build_events(payload: BuildEventsRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await svc.get_session_or_404(db, project_id=payload.project_id, session_id=payload.session_id)
    await require_entity_permission(session, NETWORK_EXPLORER_BUILD, current_user, db)
    session = await svc.build_or_rebuild(
        db, project_id=payload.project_id, session_id=payload.session_id, actor_id=current_user.id
    )
    return await svc.compute_kpis(db, session.id)


@router.get("/sessions/{session_id}/kpis", response_model=NetworkEventKpisOut)
async def get_kpis(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await svc.get_session_by_id_or_404(db, session_id)
    await require_entity_permission(session, NETWORK_EXPLORER_VIEW, current_user, db)
    return await svc.compute_kpis(db, session_id)


@router.get("/sessions/{session_id}/events", response_model=list[NetworkEventOut])
async def list_events(
    session_id: int, db: DBSession, current_user: CurrentUser,
    method: str | None = None, status_bucket: str | None = None,
    external_only: bool = False, unmapped_only: bool = False, review_state: str | None = None,
    search: str | None = None,
):
    _require_enabled()
    session = await svc.get_session_by_id_or_404(db, session_id)
    await require_entity_permission(session, NETWORK_EXPLORER_VIEW, current_user, db)
    return await svc.list_events(
        db, session_id=session_id, method=method, status_bucket=status_bucket,
        external_only=external_only, unmapped_only=unmapped_only, review_state=review_state, search=search,
    )


@router.get("/events/{event_id}", response_model=NetworkEventOut)
async def get_event(event_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    event = await svc.get_event_or_404(db, event_id)
    session = await svc.get_session_by_id_or_404(db, event.session_id)
    await require_entity_permission(session, NETWORK_EXPLORER_VIEW, current_user, db)
    return event


@router.post("/events/{event_id}/ignore", response_model=NetworkEventOut)
async def ignore_event(event_id: int, payload: IgnoreEventRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    event = await svc.get_event_or_404(db, event_id)
    session = await svc.get_session_by_id_or_404(db, event.session_id)
    await require_entity_permission(session, NETWORK_EXPLORER_REVIEW, current_user, db)
    return await svc.mark_ignored(db, event, actor_id=current_user.id, reason=payload.reason)


@router.post("/events/{event_id}/review", response_model=NetworkEventOut)
async def review_event(event_id: int, payload: ReviewEventRequest, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    event = await svc.get_event_or_404(db, event_id)
    session = await svc.get_session_by_id_or_404(db, event.session_id)
    await require_entity_permission(session, NETWORK_EXPLORER_REVIEW, current_user, db)
    return await svc.mark_reviewed(db, event, actor_id=current_user.id, note=payload.note)


@router.get("/sessions/{session_id}/activity", response_model=list[NetworkEventActivityOut])
async def get_activity(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await svc.get_session_by_id_or_404(db, session_id)
    await require_entity_permission(session, NETWORK_EXPLORER_VIEW_AUDIT, current_user, db)
    return await svc.list_activity(db, session_id)


@router.get("/sessions/{session_id}/export")
async def export_events(session_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    session = await svc.get_session_by_id_or_404(db, session_id)
    await require_entity_permission(session, NETWORK_EXPLORER_EXPORT, current_user, db)
    events = await svc.list_events(db, session_id=session_id)
    kpis = await svc.compute_kpis(db, session_id)

    payload = {
        "session_id": session_id,
        "kpis": kpis,
        "events": [NetworkEventOut.model_validate(e).model_dump(mode="json") for e in events],
    }
    headers = {"Content-Disposition": f'attachment; filename="network-events-session-{session_id}.json"'}
    return JSONResponse(content=json.loads(json.dumps(payload, default=str)), headers=headers)
