"""Background sync tasks for Resource Intelligence."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from app.database import AsyncSessionLocal
from app.models.resource_ops import IntegrationConnection, WorkEvidenceEvent, Resource
from app.worker.celery_app import celery_app
from app.core import audit_logger as audit

logger = logging.getLogger(__name__)


async def _run_mock_sync(connection_id: int, user_id: int) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        
        # 1. Fetch connection details
        result = await db.execute(select(IntegrationConnection).where(IntegrationConnection.id == connection_id))
        conn = result.scalar_one_or_none()
        if not conn:
            raise ValueError(f"IntegrationConnection {connection_id} not found")
            
        logger.info("Starting sync for connection %s (%s)", conn.name, conn.system_type)
        
        # 2. Fetch resources to map evidence events to
        res_result = await db.execute(select(Resource))
        resources = list(res_result.scalars().all())
        if not resources:
            logger.warning("No resources found in directory, skipping mock events sync")
            return {"status": "skipped", "reason": "no_resources"}
            
        # 3. Simulate and ingest events based on system type
        now = datetime.now(timezone.utc)
        synced_events = []
        
        if conn.system_type == "Jira":
            # Ingest simulated Jira worklogs
            for res in resources:
                synced_events.append({
                    "project_id": conn.project_id or 1,
                    "resource_id": res.person_id,
                    "source_system": "Jira",
                    "source_event_id": f"jira-log-{res.ldap_username}-{now.strftime('%d%m%Y')}",
                    "source_user_id": res.ldap_username,
                    "source_username": res.display_name,
                    "event_category": "Defect Management",
                    "event_type": "worklog_added",
                    "timestamp": now - timedelta(hours=3),
                    "actual_effort_hours": 3.0,
                    "linked_jira_issue_key": f"{conn.config.get('project_key', 'PROJ')}-102",
                    "project": "nxtQA Core",
                    "evidence_confidence": 1.0,
                    "evidence_status": "unmapped",
                })
        
        elif conn.system_type == "RTC":
            # Ingest simulated IBM RTC change implementation tasks
            for res in resources:
                synced_events.append({
                    "project_id": conn.project_id or 1,
                    "resource_id": res.person_id,
                    "source_system": "RTC",
                    "source_event_id": f"rtc-change-{res.ldap_username}-{now.strftime('%d%m%Y')}",
                    "source_user_id": res.ldap_username,
                    "source_username": res.display_name,
                    "event_category": "Change Management",
                    "event_type": "change_completed",
                    "timestamp": now - timedelta(hours=1),
                    "actual_effort_hours": 2.5,
                    "linked_rtc_work_item_id": "RTC-9943",
                    "project": "nxtQA Core",
                    "evidence_confidence": 0.95,
                    "evidence_status": "unmapped",
                })
                
        elif conn.system_type == "RQM":
            # Ingest simulated IBM RQM test executions
            for res in resources:
                synced_events.append({
                    "project_id": conn.project_id or 1,
                    "resource_id": res.person_id,
                    "source_system": "RQM",
                    "source_event_id": f"rqm-exec-{res.ldap_username}-{now.strftime('%d%m%Y')}",
                    "source_user_id": res.ldap_username,
                    "source_username": res.display_name,
                    "event_category": "Manual Execution",
                    "event_type": "test_executed",
                    "timestamp": now - timedelta(minutes=45),
                    "actual_effort_hours": 1.5,
                    "linked_rqm_artifact_id": "RQM-TC-1230",
                    "project": "nxtQA Core",
                    "evidence_confidence": 1.0,
                    "evidence_status": "unmapped",
                })
                
        elif conn.system_type == "LDAP":
            # Sync directory: simulate directory updates
            for res in resources:
                res.last_directory_sync_at = now
            await db.flush()
            
        # Ingest the evidence events
        if synced_events:
            from app.services.resource_ops_service import ResourceOpsService
            service = ResourceOpsService(db)
            await service.ingest_evidence_events(synced_events)
            
        # Update connection last sync time
        conn.last_sync_at = now
        conn.status = "connected"
        await db.commit()
        
        audit.ldap_sync(by_user_id=user_id, synced_count=len(synced_events))
        return {"status": "success", "synced_count": len(synced_events)}


@celery_app.task(bind=True, name="resource_ops_tasks.run_mock_sync", max_retries=2)
def run_mock_sync(self, connection_id: int, user_id: int):
    try:
        return asyncio.run(_run_mock_sync(connection_id, user_id))
    except Exception as exc:
        logger.exception("Resource Ops sync failed: connection_id=%s", connection_id)
        raise exc
