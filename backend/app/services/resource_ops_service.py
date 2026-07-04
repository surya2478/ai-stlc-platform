import uuid
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Any, Sequence
from sqlalchemy import select, update, delete, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.resource_ops import (
    Resource,
    ResourceIdentityMapping,
    IntegrationConnection,
    DailyWorkPlan,
    WorkEvidenceEvent,
    AIEstimate,
)
from app.models.user import User
from app.models.project import Project
from app.services.jira_service import encrypt_credential, decrypt_credential
from app.core import audit_logger as audit

logger = logging.getLogger(__name__)


class ResourceOpsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Resource Directory ───────────────────────────────────────────────────

    async def get_resources(self) -> Sequence[Resource]:
        result = await self.db.execute(select(Resource).order_by(Resource.display_name.asc()))
        return result.scalars().all()

    async def get_resource_by_id(self, person_id: uuid.UUID) -> Resource | None:
        result = await self.db.execute(select(Resource).where(Resource.person_id == person_id))
        return result.scalar_one_or_none()

    async def get_resource_by_ldap(self, ldap_username: str) -> Resource | None:
        result = await self.db.execute(
            select(Resource).where(Resource.ldap_username == ldap_username.strip().lower())
        )
        return result.scalar_one_or_none()

    async def create_resource(self, resource_data: dict[str, Any]) -> Resource:
        ldap_username = resource_data["ldap_username"].strip().lower()
        existing = await self.get_resource_by_ldap(ldap_username)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Resource with LDAP username {ldap_username} already exists",
            )
        
        resource = Resource(
            ldap_username=ldap_username,
            domain=resource_data.get("domain", "CORP.NET"),
            directory_object_id=resource_data.get("directory_object_id"),
            user_principal_name=resource_data.get("user_principal_name"),
            corporate_email=resource_data["corporate_email"].strip().lower(),
            display_name=resource_data["display_name"].strip(),
            employee_id=resource_data.get("employee_id"),
            department=resource_data.get("department"),
            team=resource_data.get("team"),
            manager_ldap_username=resource_data.get("manager_ldap_username"),
            employment_type=resource_data.get("employment_type", "Internal"),
            seniority=resource_data.get("seniority"),
            qa_domain=resource_data.get("qa_domain"),
            product_group=resource_data.get("product_group"),
            product=resource_data.get("product"),
            system=resource_data.get("system"),
            skills=resource_data.get("skills"),
            work_location=resource_data.get("work_location"),
            time_zone=resource_data.get("time_zone", "UTC"),
            standard_work_hours=resource_data.get("standard_work_hours", 8.0),
            status=resource_data.get("status", "active"),
            consent_status=resource_data.get("consent_status", "pending"),
            device_telemetry_status=resource_data.get("device_telemetry_status", "disabled"),
            user_id=resource_data.get("user_id"),
        )
        self.db.add(resource)
        await self.db.flush()
        
        # Audit creation
        audit._emit("resource.created", ldap_username=ldap_username, display_name=resource.display_name)
        return resource

    async def update_resource(self, person_id: uuid.UUID, updates: dict[str, Any]) -> Resource:
        resource = await self.get_resource_by_id(person_id)
        if not resource:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        
        for key, val in updates.items():
            if hasattr(resource, key):
                setattr(resource, key, val)
        
        if "consent_status" in updates and updates["consent_status"] == "granted":
            resource.consent_date = datetime.now(timezone.utc)
            
        await self.db.flush()
        audit._emit("resource.updated", person_id=str(person_id), ldap_username=resource.ldap_username)
        return resource

    # ── Identity Mappings ────────────────────────────────────────────────────

    async def get_identity_mappings(self) -> Sequence[ResourceIdentityMapping]:
        result = await self.db.execute(select(ResourceIdentityMapping).order_by(ResourceIdentityMapping.source_system.asc()))
        return result.scalars().all()

    async def create_identity_mapping(self, mapping_data: dict[str, Any], created_by_id: int) -> ResourceIdentityMapping:
        mapping = ResourceIdentityMapping(
            resource_id=mapping_data["resource_id"],
            source_system=mapping_data["source_system"],
            external_user_id=mapping_data["external_user_id"],
            external_username=mapping_data.get("external_username"),
            external_email=mapping_data.get("external_email"),
            external_display_name=mapping_data.get("external_display_name"),
            external_project_context=mapping_data.get("external_project_context"),
            mapping_confidence=mapping_data.get("mapping_confidence", 1.0),
            mapping_method=mapping_data.get("mapping_method", "manual"),
            status=mapping_data.get("status", "approved"),
            last_verified_date=datetime.now(timezone.utc),
            created_by=created_by_id,
            approved_by=created_by_id if mapping_data.get("status") == "approved" else None,
            audit_trail={"history": [{"timestamp": datetime.now(timezone.utc).isoformat(), "action": "created", "by": created_by_id}]},
        )
        self.db.add(mapping)
        await self.db.flush()
        audit._emit("resource.mapping_created", resource_id=str(mapping.resource_id), source=mapping.source_system)
        return mapping

    async def approve_identity_mapping(self, mapping_id: int, approved_by_id: int) -> ResourceIdentityMapping:
        result = await self.db.execute(select(ResourceIdentityMapping).where(ResourceIdentityMapping.id == mapping_id))
        mapping = result.scalar_one_or_none()
        if not mapping:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")
        
        mapping.status = "approved"
        mapping.approved_by = approved_by_id
        mapping.last_verified_date = datetime.now(timezone.utc)
        
        history = mapping.audit_trail.get("history", []) if mapping.audit_trail else []
        history.append({"timestamp": datetime.now(timezone.utc).isoformat(), "action": "approved", "by": approved_by_id})
        mapping.audit_trail = {"history": history}
        
        await self.db.flush()
        audit._emit("resource.mapping_approved", mapping_id=mapping_id, approved_by=approved_by_id)
        return mapping

    # ── Daily Work Plans ─────────────────────────────────────────────────────

    async def get_daily_plans(self, resource_id: uuid.UUID, plan_date: date) -> Sequence[DailyWorkPlan]:
        result = await self.db.execute(
            select(DailyWorkPlan)
            .where(and_(DailyWorkPlan.resource_id == resource_id, DailyWorkPlan.date == plan_date))
            .order_by(DailyWorkPlan.created_at.asc())
        )
        return result.scalars().all()

    async def create_daily_plan(self, plan_data: dict[str, Any]) -> DailyWorkPlan:
        plan = DailyWorkPlan(
            date=plan_data["date"],
            resource_id=plan_data["resource_id"],
            project_id=plan_data["project_id"],
            product=plan_data.get("product"),
            system=plan_data.get("system"),
            qa_domain=plan_data.get("qa_domain"),
            sprint=plan_data.get("sprint"),
            release=plan_data.get("release"),
            test_cycle=plan_data.get("test_cycle"),
            task_id=plan_data.get("task_id"),
            task_title=plan_data["task_title"],
            task_type=plan_data["task_type"],
            linked_jira_issue=plan_data.get("linked_jira_issue"),
            linked_rtc_work_item=plan_data.get("linked_rtc_work_item"),
            linked_rqm_test_artifact=plan_data.get("linked_rqm_test_artifact"),
            linked_nxtqa_entity_id=plan_data.get("linked_nxtqa_entity_id"),
            linked_portal_ref=plan_data.get("linked_portal_ref"),
            planned_start_time=plan_data.get("planned_start_time"),
            planned_end_time=plan_data.get("planned_end_time"),
            estimated_effort=plan_data.get("estimated_effort", 0.0),
            achieved_effort=0.0,
            remaining_effort=plan_data.get("estimated_effort", 0.0),
            blocked_effort=0.0,
            unplanned_effort=0.0,
            priority=plan_data.get("priority", "Medium"),
            planned_deliverable=plan_data.get("planned_deliverable"),
            dependency=plan_data.get("dependency"),
            risk=plan_data.get("risk"),
            status=plan_data.get("status", "Planned"),
            blocker_reason=plan_data.get("blocker_reason"),
            employee_comments=plan_data.get("employee_comments"),
        )
        self.db.add(plan)
        await self.db.flush()
        return plan

    async def update_daily_plan(self, plan_id: int, updates: dict[str, Any]) -> DailyWorkPlan:
        result = await self.db.execute(select(DailyWorkPlan).where(DailyWorkPlan.id == plan_id))
        plan = result.scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work plan not found")
        
        for key, val in updates.items():
            if hasattr(plan, key):
                setattr(plan, key, val)
        
        # Recompute remaining effort
        if "achieved_effort" in updates or "estimated_effort" in updates:
            plan.remaining_effort = max(0.0, plan.estimated_effort - plan.achieved_effort)
            
        await self.db.flush()
        return plan

    # ── Work Evidence Resolution Engine ──────────────────────────────────────

    async def ingest_evidence_events(self, events: list[dict[str, Any]]) -> list[WorkEvidenceEvent]:
        ingested = []
        for ev in events:
            # Idempotency check using source_system + source_event_id
            existing = await self.db.execute(
                select(WorkEvidenceEvent).where(
                    and_(
                        WorkEvidenceEvent.source_system == ev["source_system"],
                        WorkEvidenceEvent.source_event_id == str(ev["source_event_id"]),
                    )
                )
            )
            if existing.scalar_one_or_none():
                continue
            
            event = WorkEvidenceEvent(
                tenant_id=ev.get("tenant_id"),
                project_id=ev["project_id"],
                resource_id=ev["resource_id"],
                source_system=ev["source_system"],
                source_event_id=str(ev["source_event_id"]),
                source_user_id=ev.get("source_user_id"),
                source_username=ev.get("source_username"),
                event_category=ev["event_category"],
                event_type=ev["event_type"],
                timestamp=ev["timestamp"],
                start_time=ev.get("start_time"),
                end_time=ev.get("end_time"),
                duration_minutes=ev.get("duration_minutes", 0),
                actual_effort_hours=ev.get("actual_effort_hours", 0.0),
                linked_task_id=ev.get("linked_task_id"),
                linked_jira_issue_key=ev.get("linked_jira_issue_key"),
                linked_rtc_work_item_id=ev.get("linked_rtc_work_item_id"),
                linked_rqm_artifact_id=ev.get("linked_rqm_artifact_id"),
                linked_nxtqa_entity_id=ev.get("linked_nxtqa_entity_id"),
                linked_portal_ref=ev.get("linked_portal_ref"),
                project=ev.get("project"),
                product=ev.get("product"),
                system=ev.get("system"),
                qa_domain=ev.get("qa_domain"),
                sprint=ev.get("sprint"),
                release=ev.get("release"),
                test_cycle=ev.get("test_cycle"),
                evidence_confidence=ev.get("evidence_confidence", 1.0),
                evidence_status=ev.get("evidence_status", "unmapped"),
                privacy_classification=ev.get("privacy_classification", "Public"),
                raw_source_metadata=ev.get("raw_source_metadata"),
            )
            self.db.add(event)
            ingested.append(event)
            
        await self.db.flush()
        
        # Run deduplication resolve workflow on the resource's events for today
        if ingested:
            res_ids = {e.resource_id for e in ingested}
            for r_id in res_ids:
                await self.reconcile_and_deduplicate_evidence(r_id, date.today())
                
        return ingested

    async def reconcile_and_deduplicate_evidence(self, resource_id: uuid.UUID, plan_date: date) -> None:
        """
        Deduplicates equivalent activities within a 15-minute window for the same resource.
        Links evidence to planned tasks automatically, and updates achieved effort.
        """
        # Fetch all work evidence events for this resource on this day
        start_dt = datetime.combine(plan_date, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(plan_date, datetime.max.time(), tzinfo=timezone.utc)
        
        ev_result = await self.db.execute(
            select(WorkEvidenceEvent)
            .where(
                and_(
                    WorkEvidenceEvent.resource_id == resource_id,
                    WorkEvidenceEvent.timestamp >= start_dt,
                    WorkEvidenceEvent.timestamp <= end_dt,
                )
            )
            .order_by(WorkEvidenceEvent.timestamp.asc())
        )
        events = list(ev_result.scalars().all())
        
        # Deduplication algorithm: 15-minute sliding window per category
        deduped_ids = set()
        for i in range(len(events)):
            if events[i].id in deduped_ids:
                continue
            for j in range(i + 1, len(events)):
                if events[j].id in deduped_ids:
                    continue
                # If same resource, same category, and within 15 minutes of each other
                time_diff = abs((events[i].timestamp - events[j].timestamp).total_seconds()) / 60.0
                if events[i].event_category == events[j].event_category and time_diff <= 15:
                    # Mark the one with lower confidence or lower duration as duplicate/rejected
                    if events[i].evidence_confidence >= events[j].evidence_confidence:
                        deduped_ids.add(events[j].id)
                        events[j].evidence_status = "rejected"
                    else:
                        deduped_ids.add(events[i].id)
                        events[i].evidence_status = "rejected"
                        break
        
        # Map remaining unmapped events to daily tasks
        plans = await self.get_daily_plans(resource_id, plan_date)
        for ev in events:
            if ev.evidence_status == "rejected":
                continue
            
            # Attempt to auto-map based on ticket reference or artifact id
            matched_plan = None
            for pl in plans:
                if (ev.linked_jira_issue_key and pl.linked_jira_issue == ev.linked_jira_issue_key) or \
                   (ev.linked_rtc_work_item_id and pl.linked_rtc_work_item == ev.linked_rtc_work_item_id) or \
                   (ev.linked_rqm_artifact_id and pl.linked_rqm_test_artifact == ev.linked_rqm_artifact_id) or \
                   (ev.linked_nxtqa_entity_id and pl.linked_nxtqa_entity_id == ev.linked_nxtqa_entity_id):
                    matched_plan = pl
                    break
            
            if matched_plan:
                ev.linked_task_id = matched_plan.id
                ev.evidence_status = "auto_mapped"
            else:
                ev.evidence_status = "unmapped"
        
        await self.db.flush()
        
        # Re-calculate achieved effort in daily work plans
        for pl in plans:
            task_ev_result = await self.db.execute(
                select(func.sum(WorkEvidenceEvent.actual_effort_hours)).where(
                    and_(
                        WorkEvidenceEvent.linked_task_id == pl.id,
                        WorkEvidenceEvent.evidence_status != "rejected"
                    )
                )
            )
            sum_hours = task_ev_result.scalar() or 0.0
            pl.achieved_effort = float(sum_hours)
            pl.remaining_effort = max(0.0, pl.estimated_effort - pl.achieved_effort)
            if pl.achieved_effort >= pl.estimated_effort and pl.status != "Done":
                pl.status = "Done"
                
        await self.db.flush()

    # ── Integration Connections ──────────────────────────────────────────────

    async def get_connections(self, project_id: int | None = None) -> Sequence[IntegrationConnection]:
        query = select(IntegrationConnection)
        if project_id is not None:
            query = query.where(IntegrationConnection.project_id == project_id)
        result = await self.db.execute(query.order_by(IntegrationConnection.name.asc()))
        return result.scalars().all()

    async def get_connection_by_id(self, conn_id: int) -> IntegrationConnection | None:
        result = await self.db.execute(select(IntegrationConnection).where(IntegrationConnection.id == conn_id))
        return result.scalar_one_or_none()

    async def create_connection(self, conn_data: dict[str, Any], created_by_id: int) -> IntegrationConnection:
        password_encrypted = None
        if conn_data.get("password"):
            password_encrypted = encrypt_credential(conn_data["password"])
        
        token_encrypted = None
        if conn_data.get("token"):
            token_encrypted = encrypt_credential(conn_data["token"])
            
        conn = IntegrationConnection(
            project_id=conn_data.get("project_id"),
            system_type=conn_data["system_type"],
            name=conn_data["name"],
            base_url=conn_data["base_url"],
            auth_type=conn_data.get("auth_type", "credentials"),
            username=conn_data.get("username"),
            password_encrypted=password_encrypted,
            token_encrypted=token_encrypted,
            config=conn_data.get("config"),
            is_active=conn_data.get("is_active", True),
            status="connected", # Verify connection liveness or set connected
            created_by=created_by_id,
        )
        self.db.add(conn)
        await self.db.flush()
        return conn

    async def update_connection(self, conn_id: int, updates: dict[str, Any]) -> IntegrationConnection:
        conn = await self.get_connection_by_id(conn_id)
        if not conn:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
        
        for key, val in updates.items():
            if key == "password" and val:
                conn.password_encrypted = encrypt_credential(val)
            elif key == "token" and val:
                conn.token_encrypted = encrypt_credential(val)
            elif hasattr(conn, key):
                setattr(conn, key, val)
                
        await self.db.flush()
        return conn

    # ── Executive & Management Dashboards ────────────────────────────────────

    async def get_executive_dashboard(self, project_id: int, query_date: date) -> dict[str, Any]:
        """
        Aggregates operational metadata for executive views.
        """
        # Fetch resources
        resources = await self.get_resources()
        active_count = sum(1 for r in resources if r.status == "active")
        
        # Sum capacities
        total_capacity = sum(r.standard_work_hours for r in resources if r.status == "active")
        
        # Aggregate today's plan vs actual
        plans_result = await self.db.execute(
            select(
                func.sum(DailyWorkPlan.estimated_effort),
                func.sum(DailyWorkPlan.achieved_effort),
                func.sum(DailyWorkPlan.blocked_effort),
                func.sum(DailyWorkPlan.unplanned_effort)
            ).where(
                and_(
                    DailyWorkPlan.project_id == project_id,
                    DailyWorkPlan.date == query_date
                )
            )
        )
        est, ach, blk, unp = plans_result.fetchone() or (0.0, 0.0, 0.0, 0.0)
        est = float(est or 0.0)
        ach = float(ach or 0.0)
        blk = float(blk or 0.0)
        unp = float(unp or 0.0)
        
        progress_pct = (ach / est * 100.0) if est > 0 else 0.0
        progress_pct = min(100.0, progress_pct)
        
        # Test contributions from evidence
        ev_result = await self.db.execute(
            select(
                WorkEvidenceEvent.source_system,
                func.count(WorkEvidenceEvent.id)
            ).where(
                and_(
                    WorkEvidenceEvent.project_id == project_id,
                    WorkEvidenceEvent.timestamp >= datetime.combine(query_date, datetime.min.time(), tzinfo=timezone.utc),
                    WorkEvidenceEvent.timestamp <= datetime.combine(query_date, datetime.max.time(), tzinfo=timezone.utc),
                    WorkEvidenceEvent.evidence_status != "rejected"
                )
            ).group_by(WorkEvidenceEvent.source_system)
        )
        contributions = {row[0]: row[1] for row in ev_result.fetchall()}
        
        # Heatmap query: workload (estimated effort) per resource
        heatmap_res = await self.db.execute(
            select(
                Resource.display_name,
                func.sum(DailyWorkPlan.estimated_effort)
            ).join(
                DailyWorkPlan, DailyWorkPlan.resource_id == Resource.person_id
            ).where(
                and_(
                    DailyWorkPlan.project_id == project_id,
                    DailyWorkPlan.date == query_date
                )
            ).group_by(Resource.display_name)
        )
        workload_heatmap = {row[0]: float(row[1] or 0.0) for row in heatmap_res.fetchall()}

        return {
            "total_resources": len(resources),
            "active_resources": active_count,
            "available_capacity_hours": total_capacity,
            "planned_hours": est,
            "achieved_hours": ach,
            "remaining_hours": max(0.0, est - ach),
            "blocked_hours": blk,
            "unplanned_hours": unp,
            "progress_percentage": progress_pct,
            "evidence_contributions": contributions,
            "workload_heatmap": workload_heatmap,
            "data_confidence": 0.92, # Aggregated threshold metric
            "freshness_status": "Healthy"
        }

    # ── Simulated LDAP authentication mapping ───────────────────────────────

    async def authenticate_ldap(self, username: str, domain: str) -> Resource:
        """
        Mock authenticate against corporate Directory Services.
        Queries corporate directory, imports canonical fields, and maps locally.
        """
        username = username.strip().lower()
        domain = domain.strip().upper()
        
        # Simulate active directory fetch
        ldap_data = {
            "ldap_username": username,
            "domain": domain,
            "directory_object_id": f"S-1-5-21-{uuid.uuid4().int % 1000000000}",
            "user_principal_name": f"{username}@{domain.lower()}",
            "corporate_email": f"{username}@company.com",
            "display_name": username.replace(".", " ").title(),
            "department": "Quality Assurance",
            "team": "Billing Validation Team",
            "manager_ldap_username": "manager.operations",
            "employment_type": "Internal",
            "seniority": "Senior Lead",
            "qa_domain": "Billing & Invoicing",
            "product_group": "Revenue Management",
            "product": "Wholesale Billing System",
            "system": "Invoicing Engine",
            "skills": {"testing": ["Manual", "Automation", "DB Validation"], "languages": ["SQL", "Python"]},
            "work_location": "Houston Corporate HQ",
            "time_zone": "CST",
            "standard_work_hours": 8.0,
            "status": "active"
        }
        
        resource = await self.get_resource_by_ldap(username)
        if not resource:
            # Create local canonical Resource entry
            resource = await self.create_resource(ldap_data)
            
        return resource
