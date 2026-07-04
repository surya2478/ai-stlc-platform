"""Celery task that runs an AutomationScript against the local subprocess runner.

The endpoint creates the ExecutionRun + ExecutionResult rows synchronously
(status=pending) so the API can return immediately. This task then:

  1. Marks the run "running"
  2. Materialises the script to its workspace dir
  3. Dispatches to the LocalPytestRunner or LocalPlaywrightRunner
  4. Writes per-test results and the run-level totals back to the DB
  5. Copies artifact paths (log.txt, screenshots, video, trace) onto the
     ExecutionResult rows so the artifacts endpoint can serve them
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.project_application import ProjectApplication
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.services.automation_runner import run_script_for_execution
from app.services.project_application_service import resolve_environment_url
from app.services.automation_runner.workspace import (
    materialize_script,
    reset_workspace,
    write_playwright_config,
    write_pytest_config,
)
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


_URL_METADATA_KEYS = ("base_url", "baseUrl", "source_url", "sourceUrl", "target_url", "targetUrl")


def _extract_url(metadata: dict | None) -> str | None:
    if not metadata:
        return None
    for key in _URL_METADATA_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def _resolve_playwright_base_url(
    db: AsyncSession, script: AutomationScript, environment: str | None
) -> str | None:
    """Resolve the baseURL for a Playwright run, in precedence order:

    1. Linked TestCase.application -> ProjectApplication.environment_urls[environment]
       (the real, project-configured URL for this run's environment)
    2. AutomationScript.metadata
    3. Linked TestCase.metadata
    4. Linked Requirement.metadata (source_url is set by the requirement parser
       when the user supplies a portal URL)
    5. AUTOMATION_BASE_URL env var

    Tier 1 falls through to tier 2+ (rather than erroring) when the
    application has no entry for this specific environment — we don't want to
    silently resolve to the wrong environment's URL.
    """
    test_case: TestCase | None = None
    if script.test_case_id:
        test_case = await db.get(TestCase, script.test_case_id)

    if test_case and test_case.application_id:
        application = await db.get(ProjectApplication, test_case.application_id)
        env_url = resolve_environment_url(application, environment)
        if env_url:
            return env_url

    url = _extract_url(script.metadata_)
    if url:
        return url

    if test_case:
        url = _extract_url(test_case.metadata_)
        if url:
            return url

        if test_case.requirement_id:
            requirement = await db.get(Requirement, test_case.requirement_id)
            url = _extract_url(requirement.metadata_) if requirement else None
            if url:
                return url

    env_url = os.environ.get("AUTOMATION_BASE_URL")
    return env_url.strip() if env_url and env_url.strip() else None


async def _execute_run(execution_run_id: int, timeout_seconds: int) -> dict:
    async with AsyncSessionLocal() as db:
        run = await db.get(ExecutionRun, execution_run_id)
        if not run:
            return {"status": "skipped", "reason": "execution_run not found"}

        script_id = (run.metadata_ or {}).get("automation_script_id")
        if not script_id:
            run.status = "failed"
            run.metadata_ = {**(run.metadata_ or {}), "error": "no automation_script_id on run"}
            await db.commit()
            return {"status": "failed", "reason": "missing automation_script_id"}

        script = await db.get(AutomationScript, int(script_id))
        if not script:
            run.status = "failed"
            run.metadata_ = {**(run.metadata_ or {}), "error": f"script {script_id} missing"}
            await db.commit()
            return {"status": "failed", "reason": "script_not_found"}

        # Move run -> running
        run.status = "running"
        run.metadata_ = {**(run.metadata_ or {}), "started_at": datetime.now(timezone.utc).isoformat()}
        await db.commit()

        # Set up workspace
        workspace = reset_workspace(run.id)
        framework = (script.framework or "").lower()
        if framework == "playwright":
            base_url = await _resolve_playwright_base_url(db, script, run.environment)
            if not base_url:
                logger.warning(
                    "No baseURL resolved for run %s (script %s); page.goto('/') style "
                    "calls in the generated spec will fail with 'Cannot navigate to invalid URL'.",
                    run.id, script.id,
                )
            write_playwright_config(workspace, base_url=base_url)
        elif framework == "pytest":
            write_pytest_config(workspace)

        script_file = materialize_script(
            workspace=workspace,
            framework=framework,
            code=script.code,
            suggested_file_path=script.file_path,
        )

        # Run
        runner_result = await run_script_for_execution(
            framework=framework,
            workspace=workspace,
            script_file_name=script_file,
            execution_command=script.execution_command,
            environment=run.environment,
            timeout_seconds=timeout_seconds,
        )

        # Persist results
        existing = await db.execute(
            select(ExecutionResult).where(ExecutionResult.execution_run_id == run.id)
        )
        placeholders = list(existing.scalars().all())

        # The endpoint creates one pre-allocated ExecutionResult to keep the
        # IDs stable for the artifacts route. If we got more rows from the
        # runner than placeholders, allocate new ExecutionResult rows; if
        # fewer, leave the extras as "skipped" so the user sees something
        # consistent.
        passed = failed = skipped = 0
        result_rows = runner_result.results
        for idx, per_test in enumerate(result_rows):
            if idx < len(placeholders):
                exec_result = placeholders[idx]
            else:
                exec_result = ExecutionResult(
                    execution_run_id=run.id,
                    test_case_id=placeholders[0].test_case_id if placeholders else None,
                    project_id=run.project_id,
                    test_name=per_test.name,
                    status="pending",
                )
                db.add(exec_result)
                await db.flush()

            exec_result.test_name = per_test.name or exec_result.test_name
            exec_result.status = per_test.status
            exec_result.duration_ms = per_test.duration_ms
            exec_result.error_message = per_test.error_message
            exec_result.stack_trace = per_test.stack_trace
            exec_result.screenshot_path = per_test.screenshot_path
            exec_result.video_path = per_test.video_path
            exec_result.trace_path = per_test.trace_path
            exec_result.logs = [runner_result.log_path] if runner_result.log_path else None
            exec_result.metadata_ = {
                **(exec_result.metadata_ or {}),
                "runner": runner_result.metadata,
                "raw": per_test.raw,
            }
            if per_test.status == "pass":
                passed += 1
            elif per_test.status == "fail":
                failed += 1
            else:
                skipped += 1

        # If the runner produced fewer rows than placeholders, attribute the gap.
        # When the runner itself failed (subprocess crashed, syntax error, missing
        # dependency), surface that failure on the placeholder instead of pretending
        # the test was skipped — and always attach the log path so the user can
        # download the captured stdout/stderr.
        runner_failed = bool(runner_result.error_message) or runner_result.run_status == "failed"
        leftover_status = "fail" if runner_failed else "skip"
        leftover_message = (
            runner_result.error_message
            or f"Runner finished with status '{runner_result.run_status}' but produced no result row for this test case."
        )
        for leftover in placeholders[len(result_rows):]:
            leftover.status = leftover_status
            leftover.error_message = leftover_message
            leftover.logs = [runner_result.log_path] if runner_result.log_path else None
            leftover.metadata_ = {**(leftover.metadata_ or {}), "runner": runner_result.metadata}
            if leftover_status == "fail":
                failed += 1
            else:
                skipped += 1

        # Roll the outcome up onto the linked TestCase so "last run" status is
        # visible in the planning/inventory views without opening the run.
        # Mirrors the equivalent update in execution.py's agent/run-tests path.
        now = datetime.now(timezone.utc)
        touched_test_case_ids: set[int] = set()
        for result_row in placeholders:
            if result_row.test_case_id is None or result_row.test_case_id in touched_test_case_ids:
                continue
            touched_test_case_ids.add(result_row.test_case_id)
            tc = await db.get(TestCase, result_row.test_case_id)
            if tc:
                tc.last_execution_run_id = run.id
                tc.last_automation_status = result_row.status
                tc.last_automation_run_at = now
                tc.latest_evidence_available = bool(
                    result_row.logs or result_row.error_message or result_row.stack_trace
                    or result_row.screenshot_path or result_row.video_path or result_row.trace_path
                )

        # Run-level roll-up
        run.passed = passed
        run.failed = failed
        run.skipped = skipped
        run.total_tests = passed + failed + skipped
        run.status = runner_result.run_status
        run.execution_logs = (run.execution_logs or []) + [
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "stage": "subprocess_runner",
                "metadata": runner_result.metadata,
                "log_path": runner_result.log_path,
                "error": runner_result.error_message,
            }
        ]
        run.metadata_ = {
            **(run.metadata_ or {}),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "runner": runner_result.metadata,
            "runner_error": runner_result.error_message,
        }
        await db.commit()
        return {
            "execution_run_id": run.id,
            "status": run.status,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        }


@celery_app.task(bind=True, name="automation_tasks.run_automation_script", max_retries=0)
def run_automation_script(self, execution_run_id: int, timeout_seconds: int = 600):
    """Entry point invoked by the API after creating the ExecutionRun row."""
    try:
        return asyncio.run(_execute_run(execution_run_id, timeout_seconds))
    except Exception as exc:
        logger.exception("Automation runner crashed for run_id=%s", execution_run_id)
        try:
            asyncio.run(_mark_run_failed(execution_run_id, str(exc)))
        except Exception:
            logger.exception("Failed to mark run %s as failed after crash", execution_run_id)
        raise


async def _mark_run_failed(execution_run_id: int, message: str) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(ExecutionRun, execution_run_id)
        if not run:
            return
        run.status = "failed"
        run.metadata_ = {**(run.metadata_ or {}), "error": message}
        await db.commit()
