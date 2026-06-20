"""Agent dispatch helpers shared by API endpoints."""
from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.services import agent_run_service
from app.worker.tasks.agent_tasks import run_agent


async def enqueue_agent_run(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    agent_name: str,
    input_data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    prompt_version: str | None = None,
) -> tuple[AgentRun, str]:
    # Mask sensitive keys for database writes
    db_input_data = dict(input_data)
    if "github_token" in db_input_data and db_input_data["github_token"]:
        db_input_data["github_token"] = "***REDACTED***"

    derived_key, digest = agent_run_service.derive_idempotency_key(
        project_id=project_id,
        user_id=user_id,
        agent_name=agent_name,
        input_data=db_input_data,
        prompt_version=prompt_version,
    )
    key = idempotency_key or derived_key
    existing = await agent_run_service.find_agent_run_by_idempotency_key(
        db,
        project_id=project_id,
        idempotency_key=key,
    )
    if existing is not None and existing.status in {"pending", "running", "completed"}:
        return existing, existing.celery_task_id or ""
    if existing is not None and existing.status in {"failed", "cancelled"}:
        previous_status = existing.status
        existing.status = "pending"
        existing.input_data = db_input_data
        existing.input_hash = digest
        existing.prompt_version = prompt_version or agent_run_service.DEFAULT_PROMPT_VERSION
        existing.metadata_ = metadata
        existing.error_message = None
        existing.output_data = None
        existing.progress_percent = 0
        existing.progress_message = "Requeued"
        await agent_run_service.add_log(
            db,
            existing,
            level="info",
            step="requeued",
            message=f"Agent '{agent_name}' requeued after {previous_status}",
        )
        try:
            task = run_agent.delay(existing.id, agent_name, input_data)
        except Exception as exc:
            await agent_run_service.fail_agent_run(db, existing, error_message=f"Agent enqueue failed: {exc}")
            await db.commit()
            raise
        existing.celery_task_id = task.id
        existing.progress_percent = 5
        existing.progress_message = "Queued for worker"
        await db.commit()
        await db.refresh(existing)
        return existing, task.id

    try:
        agent_run = await agent_run_service.start_agent_run(
            db,
            project_id=project_id,
            user_id=user_id,
            agent_name=agent_name,
            input_data=db_input_data,
            metadata=metadata,
            status="pending",
            idempotency_key=key,
            input_hash_value=digest,
            prompt_version=prompt_version,
            progress_percent=0,
            progress_message="Queued",
        )
    except IntegrityError:
        await db.rollback()
        existing = await agent_run_service.find_agent_run_by_idempotency_key(
            db,
            project_id=project_id,
            idempotency_key=key,
        )
        if existing is not None:
            return existing, existing.celery_task_id or ""
        raise

    try:
        task = run_agent.delay(agent_run.id, agent_name, input_data)
    except Exception as exc:
        await agent_run_service.fail_agent_run(db, agent_run, error_message=f"Agent enqueue failed: {exc}")
        await db.commit()
        raise
    agent_run.celery_task_id = task.id
    agent_run.progress_percent = 5
    agent_run.progress_message = "Queued for worker"
    await db.commit()
    await db.refresh(agent_run)
    return agent_run, task.id
