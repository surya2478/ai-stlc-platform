"""Celery tasks for the Test Automation Studio's long-running operations.

All three studio operations run one or more LLM calls and take minutes. Held
open as a synchronous request they exceed any proxy's read timeout: the work
completes and commits, but the client has already given up and shows a failure.

Each task therefore owns an `agent_runs` row created by the endpoint, reports
progress onto it as it goes, and the UI polls that row — the same contract the
platform's other agent-driven screens already use.

A dedicated module rather than a branch inside agent_tasks.run_agent: that
dispatcher maps one agent name to one agent class, while these are
orchestrations (multi-pass agents, test data materialisation, classification,
per-item loops). Adding them there would mean studio branches in two shared
functions, against this module's isolation.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.database import AsyncSessionLocal
from app.models.agent import AgentRun
from app.services import agent_run_service
from app.services.test_automation_studio.progress import db_progress_callback
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _load_run(db, agent_run_id: int) -> AgentRun:
    run = await db.get(AgentRun, agent_run_id)
    if run is None:
        raise ValueError(f"Agent run {agent_run_id} not found")
    run.status = "running"
    run.progress_percent = max(run.progress_percent or 0, 10)
    run.progress_message = "Started"
    await db.commit()
    return run


async def _fail(agent_run_id: int, error: str) -> None:
    """Mark a run failed in its own session.

    Separate session on purpose: the session that raised may be in a broken
    transaction, and a run left "running" after a crash is exactly what the
    reaper has to clean up later while the user watches a spinner.
    """
    async with AsyncSessionLocal() as db:
        await agent_run_service.fail_agent_run(db, agent_run_id, error_message=error[:2000])
        await db.commit()


def _detail(exc: Exception) -> str:
    """Readable message from an HTTPException or any other error."""
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        return str(detail.get("message") or detail)
    return f"{type(exc).__name__}: {exc}"


# ── Screen 1: coverage assessment ────────────────────────────────────────────

async def _assess_coverage(agent_run_id: int, batch_id: int, user_id: int, payload: dict[str, Any]):
    async with AsyncSessionLocal() as db:
        run = await _load_run(db, agent_run_id)
        from app.services.test_automation_studio import coverage_service

        assessment = await coverage_service.execute_assessment(
            db,
            run=run,
            batch_id=batch_id,
            derive_gap_requirements=bool(payload.get("derive_gap_requirements", True)),
            user_id=user_id,
            on_progress=db_progress_callback(db, run),
        )
        return {"assessment_id": assessment.id, "coverage_percent": assessment.coverage_percent}


@celery_app.task(bind=True, name="tas.assess_coverage")
def tas_assess_coverage(self, agent_run_id: int, batch_id: int, user_id: int, payload: dict | None = None):
    try:
        return asyncio.run(_assess_coverage(agent_run_id, batch_id, user_id, payload or {}))
    except Exception as exc:  # noqa: BLE001 - every failure must land on the run
        logger.exception("TAS coverage assessment failed (run %s)", agent_run_id)
        try:
            asyncio.run(_fail(agent_run_id, _detail(exc)))
        except Exception:  # noqa: BLE001
            logger.exception("Could not mark TAS run %s failed", agent_run_id)
        raise


async def _extract_test_cases(agent_run_id: int, batch_id: int, user_id: int):
    async with AsyncSessionLocal() as db:
        run = await _load_run(db, agent_run_id)
        from app.services.test_automation_studio import coverage_service

        rows = await coverage_service.execute_test_case_extraction(
            db,
            run=run,
            batch_id=batch_id,
            user_id=user_id,
            on_progress=db_progress_callback(db, run),
        )
        return {"test_cases": len(rows), "batch_id": batch_id}


@celery_app.task(bind=True, name="tas.extract_test_cases")
def tas_extract_test_cases(self, agent_run_id: int, batch_id: int, user_id: int):
    try:
        return asyncio.run(_extract_test_cases(agent_run_id, batch_id, user_id))
    except Exception as exc:  # noqa: BLE001 - every failure must land on the run
        logger.exception("TAS test case extraction failed (run %s)", agent_run_id)
        try:
            asyncio.run(_fail(agent_run_id, _detail(exc)))
        except Exception:  # noqa: BLE001
            logger.exception("Could not mark TAS run %s failed", agent_run_id)
        raise


# ── Screen 1: application discovery ──────────────────────────────────────────

async def _discover_application(agent_run_id: int, batch_id: int, user_id: int):
    async with AsyncSessionLocal() as db:
        run = await _load_run(db, agent_run_id)
        from app.services.test_automation_studio import discovery_service

        discovery_run = await discovery_service.execute_discovery(
            db,
            batch_id=batch_id,
            user_id=user_id,
            run=run,
            on_progress=db_progress_callback(db, run),
        )
        return {
            "discovery_run_id": discovery_run.id,
            "status": discovery_run.status,
            "elements": discovery_run.elements_discovered,
            "auth_status": discovery_run.auth_status,
        }


@celery_app.task(bind=True, name="tas.discover_application")
def tas_discover_application(self, agent_run_id: int, batch_id: int, user_id: int):
    """Crawl the batch's application.

    Longer-running than the LLM tasks around it and for a different reason:
    it starts a browser subprocess and waits on a real network. Failures here
    are routine (the environment is down, the credentials are wrong) and must
    land on the run rather than vanishing into a worker log.
    """
    try:
        return asyncio.run(_discover_application(agent_run_id, batch_id, user_id))
    except Exception as exc:  # noqa: BLE001 - every failure must land on the run
        logger.exception("TAS application discovery failed (run %s)", agent_run_id)
        try:
            asyncio.run(_fail(agent_run_id, _detail(exc)))
        except Exception:  # noqa: BLE001
            logger.exception("Could not mark TAS run %s failed", agent_run_id)
        raise


# ── Screen 2: refined test case generation ───────────────────────────────────

async def _generate_test_cases(agent_run_id: int, project_id: int, user_id: int, payload: dict[str, Any]):
    async with AsyncSessionLocal() as db:
        run = await _load_run(db, agent_run_id)
        from app.schemas.test_automation_studio import GenerateRefinedTestCasesRequest
        from app.services.test_automation_studio import refinement_service

        created, skipped, _ = await refinement_service.generate_refined_test_cases(
            db,
            project_id=project_id,
            body=GenerateRefinedTestCasesRequest(**payload),
            user_id=user_id,
            run=run,
            on_progress=db_progress_callback(db, run),
        )
        return {
            "generated": len(created),
            "skipped": skipped,
            "test_case_ids": [row.id for row in created],
        }


@celery_app.task(bind=True, name="tas.generate_test_cases")
def tas_generate_test_cases(self, agent_run_id: int, project_id: int, user_id: int, payload: dict):
    try:
        return asyncio.run(_generate_test_cases(agent_run_id, project_id, user_id, payload))
    except Exception as exc:  # noqa: BLE001
        logger.exception("TAS test case generation failed (run %s)", agent_run_id)
        try:
            asyncio.run(_fail(agent_run_id, _detail(exc)))
        except Exception:  # noqa: BLE001
            logger.exception("Could not mark TAS run %s failed", agent_run_id)
        raise


# ── Screen 3: script generation ──────────────────────────────────────────────

async def _generate_scripts(agent_run_id: int, project_id: int, user_id: int, payload: dict[str, Any]):
    async with AsyncSessionLocal() as db:
        run = await _load_run(db, agent_run_id)
        from app.schemas.test_automation_studio import GenerateScriptsRequest
        from app.services.test_automation_studio import script_lab_service

        created, skipped, _ = await script_lab_service.generate_scripts(
            db,
            project_id=project_id,
            body=GenerateScriptsRequest(**payload),
            user_id=user_id,
            run=run,
            on_progress=db_progress_callback(db, run),
        )
        return {
            "generated": len(created),
            "skipped": skipped,
            "script_ids": [row.id for row in created],
        }


@celery_app.task(bind=True, name="tas.generate_scripts")
def tas_generate_scripts(self, agent_run_id: int, project_id: int, user_id: int, payload: dict):
    try:
        return asyncio.run(_generate_scripts(agent_run_id, project_id, user_id, payload))
    except Exception as exc:  # noqa: BLE001
        logger.exception("TAS script generation failed (run %s)", agent_run_id)
        try:
            asyncio.run(_fail(agent_run_id, _detail(exc)))
        except Exception:  # noqa: BLE001
            logger.exception("Could not mark TAS run %s failed", agent_run_id)
        raise


async def _dry_run_scripts(agent_run_id: int, project_id: int, script_ids: list[int]):
    async with AsyncSessionLocal() as db:
        run = await _load_run(db, agent_run_id)
        from app.services.test_automation_studio import dry_run_service

        updated, blocked = await dry_run_service.execute_dry_runs(
            db,
            project_id=project_id,
            script_ids=script_ids,
            run=run,
            on_progress=db_progress_callback(db, run),
        )
        return {
            "executed": len(updated),
            "passed": sum(1 for asset in updated if asset.dry_run_status == "passed"),
            "blocked": blocked,
        }


@celery_app.task(bind=True, name="tas.dry_run_scripts")
def tas_dry_run_scripts(self, agent_run_id: int, project_id: int, script_ids: list[int]):
    try:
        return asyncio.run(_dry_run_scripts(agent_run_id, project_id, script_ids))
    except Exception as exc:  # noqa: BLE001
        logger.exception("TAS dry run failed (run %s)", agent_run_id)
        try:
            asyncio.run(_fail(agent_run_id, _detail(exc)))
            asyncio.run(_release_dry_runs(project_id, script_ids))
        except Exception:  # noqa: BLE001
            logger.exception("Could not mark TAS run %s failed", agent_run_id)
        raise


async def _release_dry_runs(project_id: int, script_ids: list[int]) -> None:
    """Clear `running`/`queued` after a crash.

    Status is set before the work starts so the screen shows progress; a task
    that dies mid-flight would otherwise leave a permanent spinner on every
    script it had claimed.
    """
    from sqlalchemy import select

    from app.models.test_automation_studio import TasScriptAsset

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(TasScriptAsset).where(
                    TasScriptAsset.id.in_(script_ids),
                    TasScriptAsset.project_id == project_id,
                    TasScriptAsset.dry_run_status.in_(("queued", "running")),
                )
            )
        ).scalars().all()
        for asset in rows:
            asset.dry_run_status = "failed"
            asset.dry_run_summary = {
                "run_status": "error",
                "passed": False,
                "results": [],
                "error_message": "The dry run worker stopped before reporting a result.",
            }
            db.add(asset)
        await db.commit()
