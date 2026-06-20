"""Jira connection and import endpoints."""
import json

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.api.deps import CurrentUser, DBSession, require_entity_permission, require_permission
from app.schemas.common import MessageResponse
from app.schemas.jira import (
    JiraConnectionCreate,
    JiraConnectionOut,
    JiraConnectionTestOut,
    JiraConnectionUpdate,
    JiraFetchIssuesRequest,
    JiraImportRequirementsOut,
    JiraImportRequirementsRequest,
    JiraIssuePageOut,
    JiraSyncTriggerOut,
    JiraSyncTriggerRequest,
    JiraWebhookReceiveOut,
)
from app.schemas.automation import JiraExecutionStatusOut, JiraExecutionStatusSyncRequest
from app.services import automation_service
from app.services.jira_service import JiraService, verify_webhook_signature
from app.services.rbac_service import SYNC_JIRA
from app.core import audit_logger as audit
from app.worker.tasks.jira_tasks import inbound_sync, outbound_sync, process_jira_webhook, two_way_sync

router = APIRouter()
settings = get_settings()


async def _get_authorized_connection(
    connection_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> tuple[JiraService, object]:
    service = JiraService(db)
    connection = await service.get_connection(connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Jira connection not found")
    await require_entity_permission(connection, SYNC_JIRA, current_user, db)
    return service, connection


@router.post("/sync-execution-status", response_model=JiraExecutionStatusOut)
async def sync_jira_execution_status(
    body: JiraExecutionStatusSyncRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    test_case = await automation_service.get_test_case_or_404(db, body.test_case_id)
    await require_permission(SYNC_JIRA, test_case.project_id, current_user, db)
    await automation_service.sync_jira_execution_status(
        db,
        test_case_id=body.test_case_id,
        jira_execution_status=body.jira_execution_status,
        jira_issue_key=body.jira_issue_key,
        jira_test_key=body.jira_test_key,
    )
    await db.commit()
    data = await automation_service.latest_jira_execution_status(db, test_case_id=body.test_case_id)
    return JiraExecutionStatusOut(**data)


@router.get("/test-cases/{test_case_id}/execution-status", response_model=JiraExecutionStatusOut)
async def get_jira_execution_status(
    test_case_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    test_case = await automation_service.get_test_case_or_404(db, test_case_id)
    await require_permission(SYNC_JIRA, test_case.project_id, current_user, db)
    data = await automation_service.latest_jira_execution_status(db, test_case_id=test_case_id)
    return JiraExecutionStatusOut(**data)


@router.get("/project/{project_id}/connections", response_model=list[JiraConnectionOut])
async def list_connections(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_permission(SYNC_JIRA, project_id, current_user, db)
    return await JiraService(db).list_connections(project_id)


@router.post("/connections", response_model=JiraConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_connection(
    body: JiraConnectionCreate,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_permission(SYNC_JIRA, body.project_id, current_user, db)
    connection = await JiraService(db).create_connection(body, current_user.id)
    await db.commit()
    audit.jira_connection_created(user_id=current_user.id, project_id=body.project_id, jira_base_url=body.jira_base_url)
    return connection


@router.get("/connections/{connection_id}", response_model=JiraConnectionOut)
async def get_connection(
    connection_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    _, connection = await _get_authorized_connection(connection_id, db, current_user)
    return connection


@router.patch("/connections/{connection_id}", response_model=JiraConnectionOut)
async def update_connection(
    connection_id: int,
    body: JiraConnectionUpdate,
    db: DBSession,
    current_user: CurrentUser,
):
    service, connection = await _get_authorized_connection(connection_id, db, current_user)
    connection = await service.update_connection(connection, body)
    await db.commit()
    return connection


@router.delete("/connections/{connection_id}", response_model=MessageResponse)
async def delete_connection(
    connection_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    service, connection = await _get_authorized_connection(connection_id, db, current_user)
    project_id = connection.project_id
    await service.delete_connection(connection)
    await db.commit()
    audit.jira_connection_deleted(user_id=current_user.id, project_id=project_id, connection_id=connection_id)
    return {"message": "Jira connection deleted"}


@router.post("/connections/{connection_id}/test", response_model=JiraConnectionTestOut)
async def test_connection(
    connection_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    service, connection = await _get_authorized_connection(connection_id, db, current_user)
    result = await service.test_connection(connection)
    await db.commit()
    return result


@router.post("/connections/{connection_id}/fetch-issues", response_model=JiraIssuePageOut)
async def fetch_issues(
    connection_id: int,
    db: DBSession,
    current_user: CurrentUser,
    body: JiraFetchIssuesRequest | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    service, connection = await _get_authorized_connection(connection_id, db, current_user)
    filters = body or JiraFetchIssuesRequest(page=page, page_size=page_size)
    if body is None:
        filters.page = page
        filters.page_size = page_size
    return await service.fetch_issues(connection, filters)


@router.post("/connections/{connection_id}/import-requirements", response_model=JiraImportRequirementsOut)
async def import_requirements(
    connection_id: int,
    body: JiraImportRequirementsRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    service, connection = await _get_authorized_connection(connection_id, db, current_user)
    result = await service.import_requirements(connection, body, current_user.id)

    # GAP-4b: enrich imported requirements with structured fields using the
    # intake agent (async, post-import; Jira sync semantics are untouched).
    # Only requirements still missing acceptance criteria are enriched, so
    # re-imports never overwrite previously enriched or edited records.
    if result.requirement_ids:
        from sqlalchemy import select

        from app.models.requirement import Requirement
        from app.services.agent_dispatch_service import enqueue_agent_run

        rows = await db.execute(
            select(Requirement).where(
                Requirement.id.in_(result.requirement_ids),
                Requirement.is_deleted.is_(False),
            )
        )
        to_enrich = [
            {"id": r.id, "title": r.title, "summary": r.summary}
            for r in rows.scalars().all()
            if not r.acceptance_criteria
        ]
        if to_enrich:
            try:
                agent_run, _task_id = await enqueue_agent_run(
                    db,
                    project_id=connection.project_id,
                    user_id=current_user.id,
                    agent_name="requirement_enrichment",
                    input_data={"requirements": to_enrich, "project_id": connection.project_id},
                    metadata={"requirement_ids": [r["id"] for r in to_enrich], "trigger": "jira_import"},
                )
                result.enrichment_agent_run_id = agent_run.id
            except Exception:
                # Enrichment is best-effort; never fail the import because of it.
                import logging

                logging.getLogger(__name__).exception(
                    "Failed to enqueue requirement enrichment after Jira import"
                )

    await db.commit()
    return result


@router.post("/connections/{connection_id}/sync", response_model=JiraSyncTriggerOut, status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(
    connection_id: int,
    body: JiraSyncTriggerRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    service, connection = await _get_authorized_connection(connection_id, db, current_user)
    history = await service.create_sync_history(
        connection=connection,
        direction=body.direction,
        user_id=current_user.id,
        metadata=body.model_dump(mode="json"),
    )
    if body.direction == "outbound":
        task = outbound_sync.delay(connection.id, history.id, current_user.id)
    elif body.direction == "both":
        task = two_way_sync.delay(connection.id, history.id, body.model_dump(mode="json"), current_user.id)
    else:
        task = inbound_sync.delay(connection.id, history.id, body.model_dump(mode="json"), current_user.id)
    history.celery_task_id = task.id
    await db.commit()
    return JiraSyncTriggerOut(sync_job_id=history.id, task_id=task.id, status="queued")


@router.post("/connections/{connection_id}/webhook", response_model=JiraWebhookReceiveOut)
async def receive_webhook(
    connection_id: int,
    request: Request,
    db: DBSession,
    x_jira_signature: str | None = Header(default=None),
):
    service = JiraService(db)
    connection = await service.get_connection(connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Jira connection not found")

    body = await request.body()
    client_ip = request.client.host if request.client else None
    verified = verify_webhook_signature(settings.jira_webhook_secret, body, x_jira_signature)
    if not verified:
        if not settings.jira_webhook_secret:
            audit.jira_webhook_rejected(reason="webhook_secret_not_configured", ip=client_ip)
            raise HTTPException(status_code=401, detail="Jira webhook secret is not configured — webhooks are disabled")
        audit.jira_webhook_rejected(reason="invalid_signature", ip=client_ip)
        raise HTTPException(status_code=401, detail="Invalid Jira webhook signature")
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Invalid webhook JSON payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Webhook payload must be a JSON object")

    event_type = payload.get("webhookEvent") or payload.get("event_type")
    audit.jira_webhook_received(project_id=connection.project_id, event_type=event_type, verified=True)
    event, is_new = await service.persist_webhook_event(connection, payload)
    task_id = None
    if is_new:
        task = process_jira_webhook.delay(event.id)
        event.celery_task_id = task.id
        task_id = task.id
    await db.commit()
    return JSONResponse(
        status_code=200,
        content=JiraWebhookReceiveOut(
            webhook_event_id=event.id,
            event_key=event.event_key,
            queued=is_new,
            task_id=task_id,
        ).model_dump(),
    )
