"""Agent dispatch helpers shared by API endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.models.automation_script import AutomationScript
from app.models.test_plan import TestPlan
from app.services import agent_run_service
from app.worker.tasks.agent_tasks import run_agent


# Agents whose input names a *source* rather than the content itself. The same
# URL, repository or uploaded image can legitimately produce different
# requirements on a later run — the page changed, the repo moved on, or the
# analysis itself improved — but the idempotency key never changes, because it
# is derived from project, user, agent, prompt version and input.
#
# Without a bound, the first completed run answers that input forever: an
# operator re-analysing a portal gets "generated successfully" and no new
# requirements, with nothing queued and nothing to look at. Reuse here is a
# double-click guard, not a permanent verdict.
_SOURCE_ANALYSIS_AGENTS = frozenset(
    {"url_analysis", "ui_image_analysis", "code_analysis"}
)
_SOURCE_ANALYSIS_REUSE_WINDOW = timedelta(minutes=10)


def _within_reuse_window(run: AgentRun) -> bool:
    finished = run.updated_at or run.created_at
    if finished is None:
        return False
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - finished) <= _SOURCE_ANALYSIS_REUSE_WINDOW


async def _completed_run_is_reusable(db: AsyncSession, run: AgentRun, agent_name: str) -> bool:
    if agent_name in _SOURCE_ANALYSIS_AGENTS:
        return _within_reuse_window(run)

    if agent_name == "test_planning":
        plan_id = (run.output_data or {}).get("plan_id")
        if not plan_id:
            return False
        result = await db.execute(
            select(TestPlan.id).where(
                TestPlan.id == plan_id,
                TestPlan.project_id == run.project_id,
            )
        )
        return result.scalar_one_or_none() is not None

    if agent_name == "test_scenario":
        from app.models.test_scenario import TestScenario
        result = await db.execute(
            select(TestScenario.id).where(
                TestScenario.agent_run_id == run.id
            )
        )
        return result.scalar_one_or_none() is not None

    if agent_name == "test_case":
        from app.models.test_case import TestCase
        result = await db.execute(
            select(TestCase.id).where(
                TestCase.agent_run_id == run.id
            )
        )
        return result.scalar_one_or_none() is not None

    if agent_name == "automation_script":
        # A completed run with an LLM/rate-limit failure persists zero
        # scripts (output_data={"script_ids": [], "count": 0}) but is still
        # marked "completed", not "failed" — without this check it was
        # treated as permanently reusable, silently blocking every retry
        # with the same test case forever (found via a live rate-limit run).
        result = await db.execute(
            select(AutomationScript.id).where(AutomationScript.agent_run_id == run.id)
        )
        return result.scalar_one_or_none() is not None

    if agent_name == "requirement_intake":
        # The same defect as automation_script above, in the same shape. A run
        # whose LLM calls all failed persists nothing and still completes, with
        # output_data={"count": 0, "requirement_ids": []} — and treating that as
        # reusable made every retry return the empty run instantly, queueing no
        # task at all. Observed live on run 453: a momentary gateway outage left
        # project 20 unable to extract requirements from any re-upload, because
        # re-uploading the same file derives the same idempotency key and kept
        # matching the poisoned run.
        from app.models.requirement import Requirement

        requirement_ids = (run.output_data or {}).get("requirement_ids") or []
        if not requirement_ids:
            return False
        result = await db.execute(
            select(Requirement.id).where(
                Requirement.id.in_(requirement_ids),
                Requirement.project_id == run.project_id,
                Requirement.is_deleted.is_(False),
            )
        )
        return result.first() is not None

    return True


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
    if existing is not None and existing.status in {"pending", "running"}:
        return existing, existing.celery_task_id or ""
    if existing is not None and existing.status == "completed":
        if await _completed_run_is_reusable(db, existing, agent_name):
            return existing, existing.celery_task_id or ""
        existing.status = "cancelled"
        existing.output_data = None
        # Two reasons reach here: the artifacts the run claimed are gone, or the
        # run is a source analysis old enough that its answer should not stand
        # in for a fresh one. The wording covers both because the requeue below
        # clears it either way.
        existing.error_message = "Completed run is no longer reusable; requeued."
        existing.progress_message = "Superseded by a new run"
        await agent_run_service.add_log(
            db,
            existing,
            level="info",
            step="idempotency_stale",
            message=(
                f"Completed agent '{agent_name}' run is no longer reusable "
                "(output missing or outside the reuse window); requeueing"
            ),
        )
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
