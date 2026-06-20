"""Approval audit helpers."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalAction


async def create_approval_action(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    entity_type: str,
    entity_id: int,
    action: str,
    notes: str | None = None,
    actor_role: str | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    source: str = "platform",
    jira_issue_key: str | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
    agent_run_id: int | None = None,
) -> ApprovalAction:
    decision = "approved" if action == "approve" else "rejected"
    entry = ApprovalAction(
        project_id=project_id,
        user_id=user_id,
        action_type=f"{action}_{entity_type}",
        entity_type=entity_type,
        entity_id=entity_id,
        decision=decision,
        notes=notes,
        actor_role=actor_role,
        old_value=old_value,
        new_value=new_value,
        source=source,
        jira_issue_key=jira_issue_key,
        correlation_id=correlation_id,
        request_id=request_id,
        agent_run_id=agent_run_id,
    )
    db.add(entry)
    await db.flush()
    return entry
