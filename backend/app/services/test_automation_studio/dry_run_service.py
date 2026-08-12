"""Screen 3: execute a generated script once, before anyone reviews it.

"Runnable" is a claim, and until a script has actually run it is an untested
one. A dry run is the cheapest possible check of that claim: materialise the
bundle, start a real browser, execute, and record what happened. A script
that passes is grounded AND executable; one that fails names the locator or
assertion that broke, which is the only feedback that makes the next
regeneration better rather than merely different.

Reuses `DryRunAgent` — the same agent, the same runner, the same evidence
parsing the classic automation module uses. Studio scripts are ordinary
Playwright bundles once compiled, so a studio-specific executor would be a
second implementation of subprocess handling, timeout enforcement and JSON
reporter parsing, each of which took live debugging to get right.

Katalon and Appium are reported `blocked`, never `failed`. No runner is
registered for either (Katalon needs a Katalon Studio install, Appium needs a
device or emulator), and calling that a failure would put a red badge on a
script whose only problem is that this deployment cannot execute its
framework.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.automation.dry_run_agent import DryRunAgent
from app.config import get_settings
from app.models.test_automation_studio import TasRefinedTestCase, TasScriptAsset
from app.services import agent_run_service
from app.services.test_automation_studio.progress import ProgressCallback
from app.services.test_automation_studio.progress import report as _report

logger = logging.getLogger(__name__)
settings = get_settings()

# Frameworks with a runner registered in automation_runner.dispatcher.
RUNNABLE_FRAMEWORKS = frozenset({"playwright"})

BLOCKED_REASONS = {
    "katalon": (
        "Katalon scripts run in Katalon Studio, which this deployment does not host. "
        "Download the script and run it there."
    ),
    "appium": (
        "Appium scripts need a connected device or emulator, which this deployment does not "
        "provide. Download the script and run it against your device farm."
    ),
}


def _script_payload(asset: TasScriptAsset, test_case: TasRefinedTestCase) -> dict:
    """Shape `DryRunAgent` expects, built from a studio asset.

    A compiled bundle hands over `compiled_files` including the entry file, so
    the whole tree is materialised and the page objects the spec imports
    actually exist on disk. A free-form script has no tree, so it is written
    as a single file.
    """
    compiled_files = None
    if asset.entry_path:
        compiled_files = {**(asset.files or {}), asset.entry_path: asset.code}
    return {
        "script_id": asset.id,
        "framework": asset.framework,
        "code": asset.code,
        "compiled_files": compiled_files,
        "file_path": asset.entry_path or asset.script_key,
        "application_url": test_case.application_url,
        "execution_command": asset.execution_command,
        "environment": None,
        "timeout_seconds": settings.tas_dry_run_timeout_seconds,
    }


async def validate_dry_run_request(
    db: AsyncSession, *, project_id: int, script_ids: list[int]
) -> None:
    found = list(
        (
            await db.execute(
                select(TasScriptAsset.id).where(
                    TasScriptAsset.id.in_(script_ids),
                    TasScriptAsset.project_id == project_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="None of the requested scripts were found in this project",
        )
    if len(found) > settings.tas_max_dry_runs_per_run:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{len(found)} scripts selected, over the "
                f"{settings.tas_max_dry_runs_per_run} limit for one dry-run batch. Each one "
                "starts a real browser."
            ),
        )


async def mark_queued(db: AsyncSession, *, project_id: int, script_ids: list[int]) -> None:
    """Flip runnable scripts to `queued` before the worker picks them up.

    Without this the screen shows "not run" between clicking Dry Run and the
    worker starting, which reads as though the click did nothing.
    """
    rows = list(
        (
            await db.execute(
                select(TasScriptAsset).where(
                    TasScriptAsset.id.in_(script_ids),
                    TasScriptAsset.project_id == project_id,
                )
            )
        )
        .scalars()
        .all()
    )
    for asset in rows:
        if asset.framework in RUNNABLE_FRAMEWORKS:
            asset.dry_run_status = "queued"
            db.add(asset)
    await db.commit()


async def execute_dry_runs(
    db: AsyncSession,
    *,
    project_id: int,
    script_ids: list[int],
    run=None,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[TasScriptAsset], list[dict]]:
    pairs = list(
        (
            await db.execute(
                select(TasScriptAsset, TasRefinedTestCase)
                .join(
                    TasRefinedTestCase,
                    TasScriptAsset.refined_test_case_id == TasRefinedTestCase.id,
                )
                .where(
                    TasScriptAsset.id.in_(script_ids),
                    TasScriptAsset.project_id == project_id,
                )
            )
        ).all()
    )
    if not pairs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="None of the requested scripts were found in this project",
        )

    runnable: list[tuple[TasScriptAsset, TasRefinedTestCase]] = []
    blocked: list[dict] = []
    now = datetime.now(timezone.utc)

    for asset, test_case in pairs:
        if asset.framework not in RUNNABLE_FRAMEWORKS:
            reason = BLOCKED_REASONS.get(
                asset.framework, f"No runner is registered for '{asset.framework}'."
            )
            asset.dry_run_status = "blocked"
            asset.dry_run_summary = {"reason": reason, "results": []}
            asset.dry_run_at = now
            db.add(asset)
            blocked.append(
                {"script_id": asset.id, "framework": asset.framework, "reason": reason}
            )
            continue
        asset.dry_run_status = "running"
        db.add(asset)
        runnable.append((asset, test_case))

    await db.commit()

    if not runnable:
        if run is not None:
            await agent_run_service.complete_agent_run(
                db, run, output_data={"executed": 0, "blocked": blocked}
            )
            await db.commit()
        return [], blocked

    await _report(on_progress, 20, f"Executing {len(runnable)} script(s)")

    agent = DryRunAgent()
    result = await agent.run(scripts=[_script_payload(a, tc) for a, tc in runnable])

    by_id = {asset.id: asset for asset, _tc in runnable}
    outcomes = {entry["script_id"]: entry for entry in (result.data or {}).get("dry_runs", [])}

    await _report(on_progress, 85, "Recording results")
    finished = datetime.now(timezone.utc)
    updated: list[TasScriptAsset] = []

    for script_id, asset in by_id.items():
        outcome = outcomes.get(script_id)
        if outcome is None:
            # The agent returned nothing for this script — it crashed rather
            # than failing a test. Recorded as failed with the run-level error
            # so the drawer has something to show; a script silently left
            # "running" would spin on the screen forever.
            asset.dry_run_status = "failed"
            asset.dry_run_summary = {
                "run_status": "error",
                "passed": False,
                "results": [],
                "error_message": result.error or "The dry run did not report a result.",
            }
        else:
            asset.dry_run_status = "passed" if outcome["passed"] else "failed"
            asset.dry_run_summary = {
                "run_status": outcome.get("run_status"),
                "passed": outcome.get("passed"),
                "results": outcome.get("results") or [],
                "log_path": outcome.get("log_path"),
                "error_message": outcome.get("error_message"),
            }
        asset.dry_run_at = finished
        db.add(asset)
        updated.append(asset)

    if run is not None:
        await agent_run_service.complete_agent_run(
            db,
            run,
            output_data={
                "executed": len(updated),
                "passed": sum(1 for a in updated if a.dry_run_status == "passed"),
                "blocked": blocked,
            },
        )
    await db.commit()
    for asset in updated:
        await db.refresh(asset)
    return updated, blocked
