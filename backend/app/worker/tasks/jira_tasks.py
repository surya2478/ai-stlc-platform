"""Background Jira sync tasks."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.jira_connection import JiraConnection
from app.models.jira_sync import JiraSyncHistory, WebhookEvent
from app.schemas.jira import JiraSyncTriggerRequest
from app.services.jira_service import JiraService
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _run_inbound_sync(
    connection_id: int,
    sync_history_id: int | None = None,
    body: dict[str, Any] | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(JiraConnection).where(JiraConnection.id == connection_id))
        connection = result.scalar_one_or_none()
        if connection is None:
            raise ValueError(f"JiraConnection {connection_id} not found")
        service = JiraService(db)
        try:
            history = await service.sync_inbound(
                connection,
                JiraSyncTriggerRequest(**(body or {})),
                user_id=user_id,
                sync_history_id=sync_history_id,
            )
            await db.commit()
            return {"sync_job_id": history.id, "status": history.status}
        except Exception:
            await _commit_or_rollback(db)
            raise


async def _run_outbound_sync(
    connection_id: int,
    sync_history_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(JiraConnection).where(JiraConnection.id == connection_id))
        connection = result.scalar_one_or_none()
        if connection is None:
            raise ValueError(f"JiraConnection {connection_id} not found")
        service = JiraService(db)
        try:
            history = await service.sync_outbound(
                connection,
                user_id=user_id,
                sync_history_id=sync_history_id,
            )
            await db.commit()
            return {"sync_job_id": history.id, "status": history.status}
        except Exception:
            await _commit_or_rollback(db)
            raise


async def _run_two_way_sync(
    connection_id: int,
    sync_history_id: int | None = None,
    body: dict[str, Any] | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(JiraConnection).where(JiraConnection.id == connection_id))
        connection = result.scalar_one_or_none()
        if connection is None:
            raise ValueError(f"JiraConnection {connection_id} not found")
        service = JiraService(db)
        try:
            inbound_history = await service.sync_inbound(
                connection,
                JiraSyncTriggerRequest(**(body or {})),
                user_id=user_id,
                sync_history_id=sync_history_id,
            )
            outbound_history = await service.sync_outbound(connection, user_id=user_id)
            await db.commit()
            return {
                "sync_job_id": inbound_history.id,
                "status": inbound_history.status,
                "outbound_sync_job_id": outbound_history.id,
            }
        except Exception:
            await _commit_or_rollback(db)
            raise


async def _run_webhook_event(event_id: int) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id))
        event = result.scalar_one_or_none()
        if event is None:
            raise ValueError(f"WebhookEvent {event_id} not found")
        try:
            event = await JiraService(db).process_webhook_event(event)
            await db.commit()
            return {"webhook_event_id": event.id, "status": event.status}
        except Exception:
            await _commit_or_rollback(db)
            raise


async def _commit_or_rollback(db) -> None:
    try:
        await db.commit()
    except Exception:
        await db.rollback()


@celery_app.task(bind=True, name="jira_tasks.inbound_sync", max_retries=2)
def inbound_sync(self, connection_id: int, sync_history_id: int | None = None, body: dict[str, Any] | None = None, user_id: int | None = None):
    try:
        return asyncio.run(_run_inbound_sync(connection_id, sync_history_id, body, user_id))
    except Exception:
        logger.exception("Inbound Jira sync failed: connection_id=%s sync_history_id=%s", connection_id, sync_history_id)
        raise


@celery_app.task(bind=True, name="jira_tasks.outbound_sync", max_retries=2)
def outbound_sync(self, connection_id: int, sync_history_id: int | None = None, user_id: int | None = None):
    try:
        return asyncio.run(_run_outbound_sync(connection_id, sync_history_id, user_id))
    except Exception:
        logger.exception("Outbound Jira sync failed: connection_id=%s sync_history_id=%s", connection_id, sync_history_id)
        raise


@celery_app.task(bind=True, name="jira_tasks.two_way_sync", max_retries=2)
def two_way_sync(self, connection_id: int, sync_history_id: int | None = None, body: dict[str, Any] | None = None, user_id: int | None = None):
    try:
        return asyncio.run(_run_two_way_sync(connection_id, sync_history_id, body, user_id))
    except Exception:
        logger.exception("Two-way Jira sync failed: connection_id=%s sync_history_id=%s", connection_id, sync_history_id)
        raise


@celery_app.task(bind=True, name="jira_tasks.process_jira_webhook", max_retries=2)
def process_jira_webhook(self, event_id: int):
    try:
        return asyncio.run(_run_webhook_event(event_id))
    except Exception:
        logger.exception("Jira webhook processing failed: event_id=%s", event_id)
        raise


async def set_sync_task_id(sync_history_id: int, task_id: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(JiraSyncHistory).where(JiraSyncHistory.id == sync_history_id))
        history = result.scalar_one_or_none()
        if history is not None:
            history.celery_task_id = task_id
            await db.commit()
