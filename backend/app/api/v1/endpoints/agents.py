"""
Agent Runs & Logs endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from datetime import datetime
from typing import Any
from pydantic import BaseModel

from app.api.deps import DBSession, OptionalUser
from app.models.agent import AgentRun, AgentLog

router = APIRouter()


class AgentRunOut(BaseModel):
    id: int
    project_id: int
    agent_name: str
    status: str
    duration_seconds: float | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class AgentLogOut(BaseModel):
    id: int
    agent_run_id: int
    level: str
    step: str | None = None
    message: str
    data: dict[str, Any] | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


@router.get("/project/{project_id}", response_model=list[AgentRunOut])
async def list_agent_runs(
    project_id: int,
    db: DBSession,
    current_user: OptionalUser,
    agent_name: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    stmt = (
        select(AgentRun)
        .where(AgentRun.project_id == project_id)
        .order_by(AgentRun.created_at.desc())
        .limit(limit)
    )
    if agent_name:
        stmt = stmt.where(AgentRun.agent_name == agent_name)
    if status:
        stmt = stmt.where(AgentRun.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{run_id}", response_model=AgentRunOut)
async def get_agent_run(run_id: int, db: DBSession, current_user: OptionalUser):
    result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@router.get("/{run_id}/logs", response_model=list[AgentLogOut])
async def get_agent_run_logs(run_id: int, db: DBSession, current_user: OptionalUser):
    result = await db.execute(
        select(AgentLog)
        .where(AgentLog.agent_run_id == run_id)
        .order_by(AgentLog.created_at.asc())
    )
    return list(result.scalars().all())
