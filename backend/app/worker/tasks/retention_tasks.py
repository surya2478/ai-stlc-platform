"""
Data retention and cleanup Celery tasks.

Scheduled tasks that enforce retention policies defined in settings:
  - Purge expired JWT blocklist entries from Redis
  - Archive / delete old AgentLog records
  - Purge old RagRetrievalEvent records
  - Flag UploadedDocuments past retention window

Schedule these via Celery Beat in production, e.g.:

    celery_app.conf.beat_schedule = {
        "nightly-retention": {
            "task": "retention_tasks.run_all_retention",
            "schedule": crontab(hour=2, minute=0),
        },
    }
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(bind=True, name="retention_tasks.purge_jwt_blocklist", max_retries=1)
def purge_jwt_blocklist(self) -> dict:
    """
    Redis TTL handles blocklist expiry automatically; this task is a no-op
    placeholder that logs the current blocklist key count for observability.
    """
    async def _run():
        from app.core.redis_client import redis_client
        keys = await redis_client.keys("blocklist:*")
        logger.info("JWT blocklist health check: %d active revoked tokens in Redis", len(keys))
        return {"blocklist_entries": len(keys)}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("JWT blocklist check failed")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="retention_tasks.archive_old_agent_logs", max_retries=1)
def archive_old_agent_logs(self) -> dict:
    """
    Delete AgentLog records older than retention_agent_logs_days.
    AgentRun records are kept (they hold output_data and metadata).
    """
    async def _run():
        from sqlalchemy import delete
        from app.database import AsyncSessionLocal
        from app.models.agent import AgentLog

        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_agent_logs_days)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(AgentLog).where(AgentLog.created_at < cutoff)
            )
            await db.commit()
            count = result.rowcount
            from app.core.audit_logger import retention_purge
            retention_purge("agent_logs", count, cutoff.isoformat())
            logger.info("Retention: deleted %d agent log rows older than %s", count, cutoff.date())
            return {"deleted_agent_logs": count, "cutoff": cutoff.isoformat()}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("Agent log retention task failed")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="retention_tasks.purge_old_rag_events", max_retries=1)
def purge_old_rag_events(self) -> dict:
    """
    Delete RagRetrievalEvent records older than retention_rag_events_days.
    """
    async def _run():
        from sqlalchemy import delete
        from app.database import AsyncSessionLocal
        from app.models.rag import RagRetrievalEvent

        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_rag_events_days)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(RagRetrievalEvent).where(RagRetrievalEvent.created_at < cutoff)
            )
            await db.commit()
            count = result.rowcount
            from app.core.audit_logger import retention_purge
            retention_purge("rag_retrieval_events", count, cutoff.isoformat())
            logger.info("Retention: deleted %d RAG retrieval event rows older than %s", count, cutoff.date())
            return {"deleted_rag_events": count, "cutoff": cutoff.isoformat()}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("RAG event retention task failed")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="retention_tasks.flag_old_documents", max_retries=1)
def flag_old_documents(self) -> dict:
    """
    Mark UploadedDocuments past the retention window with metadata flag.
    Does not delete — deletion should be a conscious admin action.
    """
    async def _run():
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models.document import UploadedDocument

        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_uploaded_files_days)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UploadedDocument).where(
                    UploadedDocument.created_at < cutoff,
                )
            )
            docs = result.scalars().all()
            flagged = 0
            for doc in docs:
                meta = doc.metadata_ or {}
                if not meta.get("retention_flagged"):
                    doc.metadata_ = {**meta, "retention_flagged": True, "retention_flag_date": datetime.now(timezone.utc).isoformat()}
                    flagged += 1
            if flagged:
                await db.commit()
            logger.info("Retention: flagged %d documents past retention window (%d days)", flagged, settings.retention_uploaded_files_days)
            return {"flagged_documents": flagged, "cutoff": cutoff.isoformat()}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("Document retention flag task failed")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="retention_tasks.run_all_retention", max_retries=0)
def run_all_retention(self) -> dict:
    """Convenience task that fans out all retention jobs."""
    purge_jwt_blocklist.delay()
    archive_old_agent_logs.delay()
    purge_old_rag_events.delay()
    flag_old_documents.delay()
    logger.info("Retention: all cleanup tasks queued")
    return {"queued": ["purge_jwt_blocklist", "archive_old_agent_logs", "purge_old_rag_events", "flag_old_documents"]}
