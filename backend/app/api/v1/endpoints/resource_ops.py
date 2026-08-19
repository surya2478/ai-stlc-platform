import uuid
import logging
from datetime import date
from typing import Any, Sequence
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request

from app.api.deps import CurrentUser, DBSession
from app.schemas.resource_ops import (
    ResourceCreate,
    ResourceUpdate,
    ResourceRead,
    ResourceIdentityMappingCreate,
    ResourceIdentityMappingRead,
    DailyWorkPlanCreate,
    DailyWorkPlanUpdate,
    DailyWorkPlanRead,
    WorkEvidenceEventCreate,
    WorkEvidenceEventRead,
    IntegrationConnectionCreate,
    IntegrationConnectionRead,
    IntegrationConnectionUpdate,
    AIEstimateRequest,
    AIEstimateRead,
    LDAPLoginRequest,
)
from app.services.resource_ops_service import ResourceOpsService
from app.services.ai_estimate_service import AIEstimateService
from app.core.security import create_access_token, create_refresh_token
from app.services.rbac_service import list_user_memberships, permissions_for_role
from app.config import get_settings
from app.core import audit_logger as audit

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


# ── LDAP Auth / Login ────────────────────────────────────────────────────────

@router.post("/ldap-login")
async def ldap_login(request: Request, response: Response, payload: LDAPLoginRequest, db: DBSession):
    """
    LDAP Login Endpoint: validates LDAP credentials and signs user in,
    generating a standard JWT access token. Keeps original DB login flow intact.
    """
    service = ResourceOpsService(db)
    
    # 1. Authenticate with LDAP
    try:
        resource = await service.authenticate_ldap(payload.username, payload.domain)
    except Exception as exc:
        audit.login_failure(email=f"{payload.username}@{payload.domain}", ip=request.client.host if request.client else None, reason="ldap_auth_failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"LDAP Authentication failed: {exc}",
        )
        
    # 2. Get or create matching local User
    from app.models.user import User
    from app.repositories.user_repository import UserRepository
    user_repo = UserRepository(db)
    
    user = await user_repo.get_by_email(resource.corporate_email)
    if not user:
        # Create local User mapped to the LDAP identity
        # Random password since they authenticate via LDAP
        import secrets
        from app.core.security import hash_password
        
        user = User(
            email=resource.corporate_email,
            full_name=resource.display_name,
            hashed_password=hash_password(secrets.token_urlsafe(24)),
            role="qa_engineer",
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        await db.flush()
        
        # Link the resource to the new user
        resource.user_id = user.id
        await db.flush()
        logger.info("Auto-registered local user %s for LDAP resource", user.email)
        
    elif not resource.user_id:
        # Map user_id if not already set
        resource.user_id = user.id
        await db.flush()
        
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user account")
        
    # 3. Create access tokens
    memberships = await list_user_memberships(db, user.id)
    membership_claims = [
        {
            "project_id": membership.project_id,
            "role": membership.role,
            "permissions": sorted(permissions_for_role(membership.role)),
        }
        for membership in memberships
    ]
    
    token = create_access_token(
        user.id,
        extra_claims={
            "global_role": user.role,
            "project_memberships": membership_claims,
        },
    )
    refresh_token = create_refresh_token(user.id)
    
    client_ip = request.client.host if request.client else None
    audit.login_success(user_id=user.id, email=user.email, ip=client_ip)
    
    # 4. Set httpOnly cookies
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=15 * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=7 * 24 * 3600,
    )
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "global_role": user.role,
        "project_memberships": membership_claims,
    }


# ── Executive & Management Dashboard ─────────────────────────────────────────

@router.get("/dashboard", response_model=dict[str, Any])
async def get_dashboard_metrics(project_id: int, db: DBSession, current_user: CurrentUser, date_val: str | None = None):
    service = ResourceOpsService(db)
    q_date = date.fromisoformat(date_val) if date_val else date.today()
    return await service.get_executive_dashboard(project_id, q_date)


# ── Resource Directory ───────────────────────────────────────────────────────

@router.get("/resources", response_model=list[ResourceRead])
async def list_resources(db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    return await service.get_resources()


@router.get("/resources/{person_id}", response_model=ResourceRead)
async def get_resource(person_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    resource = await service.get_resource_by_id(person_id)
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return resource


@router.post("/resources", response_model=ResourceRead, status_code=status.HTTP_201_CREATED)
async def create_resource(payload: ResourceCreate, db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    return await service.create_resource(payload.model_dump())


@router.put("/resources/{person_id}", response_model=ResourceRead)
async def update_resource(person_id: uuid.UUID, payload: ResourceUpdate, db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    return await service.update_resource(person_id, payload.model_dump(exclude_unset=True))


# ── Identity Mappings ────────────────────────────────────────────────────────

@router.get("/mappings", response_model=list[ResourceIdentityMappingRead])
async def list_mappings(db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    return await service.get_identity_mappings()


@router.post("/mappings", response_model=ResourceIdentityMappingRead, status_code=status.HTTP_201_CREATED)
async def create_mapping(payload: ResourceIdentityMappingCreate, db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    return await service.create_identity_mapping(payload.model_dump(), current_user.id)


@router.put("/mappings/{mapping_id}/approve", response_model=ResourceIdentityMappingRead)
async def approve_mapping(mapping_id: int, db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    return await service.approve_identity_mapping(mapping_id, current_user.id)


# ── Daily Work Plans ─────────────────────────────────────────────────────────

@router.get("/work-plans", response_model=list[DailyWorkPlanRead])
async def list_work_plans(resource_id: uuid.UUID, date_val: str, db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    q_date = date.fromisoformat(date_val)
    return await service.get_daily_plans(resource_id, q_date)


@router.post("/work-plans", response_model=DailyWorkPlanRead, status_code=status.HTTP_201_CREATED)
async def create_work_plan(payload: DailyWorkPlanCreate, db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    return await service.create_daily_plan(payload.model_dump())


@router.put("/work-plans/{plan_id}", response_model=DailyWorkPlanRead)
async def update_work_plan(plan_id: int, payload: DailyWorkPlanUpdate, db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    return await service.update_daily_plan(plan_id, payload.model_dump(exclude_unset=True))


# ── Work Evidence Event Ingestion ────────────────────────────────────────────

@router.post("/evidence-events", response_model=list[WorkEvidenceEventRead], status_code=status.HTTP_201_CREATED)
async def ingest_evidence(payload: list[WorkEvidenceEventCreate], db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    events = [item.model_dump() for item in payload]
    return await service.ingest_evidence_events(events)


@router.get("/timeline", response_model=dict[str, Any])
async def get_timeline(resource_id: uuid.UUID, date_val: str, db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    q_date = date.fromisoformat(date_val)
    plans = await service.get_daily_plans(resource_id, q_date)
    
    # Query evidence events
    from sqlalchemy import select, and_, func
    from app.models.resource_ops import WorkEvidenceEvent
    from datetime import datetime, timezone
    
    start_dt = datetime.combine(q_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(q_date, datetime.max.time(), tzinfo=timezone.utc)
    
    result = await db.execute(
        select(WorkEvidenceEvent)
        .where(
            and_(
                WorkEvidenceEvent.resource_id == resource_id,
                WorkEvidenceEvent.timestamp >= start_dt,
                WorkEvidenceEvent.timestamp <= end_dt,
                WorkEvidenceEvent.evidence_status != "rejected"
            )
        )
        .order_by(WorkEvidenceEvent.timestamp.asc())
    )
    events = result.scalars().all()
    
    total_achieved = sum(p.achieved_effort for p in plans)
    total_planned = sum(p.estimated_effort for p in plans)
    
    return {
        "date": date_val,
        "resource_id": str(resource_id),
        "total_planned_hours": total_planned,
        "total_achieved_hours": total_achieved,
        "events": events
    }


# ── Integration Connections ──────────────────────────────────────────────────

@router.get("/connections", response_model=list[IntegrationConnectionRead])
async def list_connections(db: DBSession, current_user: CurrentUser, project_id: int | None = None):
    service = ResourceOpsService(db)
    return await service.get_connections(project_id)


@router.post("/connections", response_model=IntegrationConnectionRead, status_code=status.HTTP_201_CREATED)
async def create_connection(payload: IntegrationConnectionCreate, db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    return await service.create_connection(payload.model_dump(), current_user.id)


@router.put("/connections/{conn_id}", response_model=IntegrationConnectionRead)
async def update_connection(conn_id: int, payload: IntegrationConnectionUpdate, db: DBSession, current_user: CurrentUser):
    service = ResourceOpsService(db)
    return await service.update_connection(conn_id, payload.model_dump(exclude_unset=True))


@router.post("/connections/{conn_id}/sync")
async def trigger_connection_sync(conn_id: int, db: DBSession, current_user: CurrentUser):
    """
    Triggers periodic connector sync tasks in background.
    """
    service = ResourceOpsService(db)
    conn = await service.get_connection_by_id(conn_id)
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
        
    # Trigger local Celery tasks asynchronously or directly run mock sync for readiness
    from app.worker.tasks.resource_ops_tasks import run_mock_sync
    run_mock_sync.delay(conn_id, current_user.id)
    
    return {"status": "Sync task scheduled"}


# ── AI Estimate Intelligence ──────────────────────────────────────────────────

@router.post("/estimate", response_model=AIEstimateRead)
async def generate_ai_estimate(payload: AIEstimateRequest, db: DBSession, current_user: CurrentUser):
    service = AIEstimateService(db)
    return await service.generate_estimate(
        project_id=payload.project_id,
        activity_type=payload.activity_type,
        complexity=payload.complexity,
        inputs=payload.inputs,
    )


@router.get("/estimates/calibration", response_model=dict[str, Any])
async def get_calibration_metrics(project_id: int, db: DBSession, current_user: CurrentUser):
    service = AIEstimateService(db)
    return await service.get_calibration_metrics(project_id)
