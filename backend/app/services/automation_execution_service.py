"""Shared batch-execution starter for approved automation scripts.

Extracted from the /automation/project/{id}/execute-batch endpoint so
Playwright AI Studio can launch (possibly several chunked) batch runs
through the same validation, ExecutionRun bookkeeping, and Celery dispatch.
Raises typed errors instead of HTTPException so callers map them to their
own transport semantics.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult, ExecutionRun
from app.services import automation_service
from app.services.display_id_service import display_id, temporary_id

SUPPORTED_FRAMEWORKS = {"playwright", "pytest"}


class ScriptsNotFoundError(Exception):
    def __init__(self, missing: list[int]):
        self.missing = missing
        super().__init__(f"Automation script(s) not found: {missing}")


class BatchValidationError(Exception):
    """Scripts exist but cannot run as requested (wrong project / blocked /
    unsupported framework)."""


async def start_batch_execution(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    script_ids: list[int],
    environment: str | None,
    timeout_seconds: int,
    run_name: str | None = None,
    parent_run_id: int | None = None,
    extra_metadata: dict | None = None,
) -> tuple[ExecutionRun, str | None]:
    """Create one ExecutionRun covering every script and enqueue the batch
    Celery task. Commits (the task must see the rows). Returns (run, task_id).
    """
    result = await db.execute(
        select(AutomationScript).where(AutomationScript.id.in_(script_ids))
    )
    scripts_by_id = {s.id: s for s in result.scalars().all()}
    missing = [sid for sid in script_ids if sid not in scripts_by_id]
    if missing:
        raise ScriptsNotFoundError(missing)

    # Preserve caller-specified order but dedupe (a script appearing twice
    # would otherwise get two ExecutionResult placeholders).
    seen: set[int] = set()
    ordered_scripts: list[AutomationScript] = []
    for sid in script_ids:
        if sid in seen:
            continue
        seen.add(sid)
        ordered_scripts.append(scripts_by_id[sid])

    wrong_project = [s.script_id for s in ordered_scripts if s.project_id != project_id]
    if wrong_project:
        raise BatchValidationError(f"Script(s) not in project {project_id}: {wrong_project}")

    blocked = [
        f"{s.script_id} ({reason})"
        for s in ordered_scripts
        if (reason := automation_service.execution_blocked_reason(s))
    ]
    if blocked:
        raise BatchValidationError(f"Script(s) cannot be executed: {'; '.join(blocked)}")

    unsupported = [
        f"{s.script_id} ({s.framework})"
        for s in ordered_scripts
        if (s.framework or "").lower() not in SUPPORTED_FRAMEWORKS
    ]
    if unsupported:
        raise BatchValidationError(f"Framework not supported by the local runner: {unsupported}")

    run = ExecutionRun(
        project_id=project_id,
        created_by=user_id,
        execution_id=temporary_id("ER"),
        suite_name=run_name or f"All Eligible Automation ({len(ordered_scripts)})",
        environment=environment,
        status="queued",
        execution_type="automation",
        source_type="automation_local_batch",
        total_tests=len(ordered_scripts),
        passed=0,
        failed=0,
        skipped=0,
        execution_logs=[],
        metadata_={
            "source_type": "automation_local_batch",
            "automation_script_ids": [s.id for s in ordered_scripts],
            "timeout_seconds": timeout_seconds,
            "parent_run_id": parent_run_id,
            **(extra_metadata or {}),
        },
    )
    db.add(run)
    await db.flush()
    run.execution_id = display_id("ER", run.id)
    await db.flush()

    for script in ordered_scripts:
        placeholder = ExecutionResult(
            execution_run_id=run.id,
            test_case_id=script.test_case_id,
            project_id=project_id,
            test_name=script.script_id,
            status="pending",
            metadata_={"automation_script_id": script.id},
        )
        db.add(placeholder)
    await db.flush()

    await db.commit()

    from app.worker.tasks.automation_tasks import run_automation_batch

    async_result = run_automation_batch.delay(run.id, timeout_seconds)
    task_id = str(async_result.id) if async_result else None
    if task_id:
        # Persisted so a later Cancel Run request can revoke the Celery task.
        run.metadata_ = {**(run.metadata_ or {}), "task_id": task_id}
        await db.commit()
    return run, task_id
