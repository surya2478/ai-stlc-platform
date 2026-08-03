"""Playwright AI Studio orchestration — stage machine + bulk gates.

A StudioRun is the umbrella over existing first-class artifacts (AgentRun,
TestCase, AutomationScript, ExecutionRun); this module advances its stage
machine and performs the two bulk approval gates. It deliberately reuses
the same primitives the /automation flow uses one-at-a-time:

  - Plan approval materializes proposals as real TestCase rows (status
    "approved") + ApprovalAction audit rows, then enqueues generation waves
    through automation_generation_service.build_generation_payload — from
    there the existing chain (contract → compile → static gate → dry run →
    classification → repair) takes over untouched.
  - Script approval reuses the legacy bulk-approve semantics
    (automation_service.approve_script + approval_override_reason): that is
    the status ("approved") the execution gate (execution_blocked_reason)
    actually accepts, and it keeps the audited override-note requirement
    for ungrounded/failed scripts. The reviewer/lead lifecycle chain
    (advance_script_lifecycle) remains the /automation flow's
    governance-heavy path; Studio is explicitly the bulk path.

Reconciliation happens at read time (get_run_detail): agent-run failures
and execution completion flip the StudioRun status without needing extra
worker hooks.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.project_application import ProjectApplication
from app.models.studio_run import StudioRun
from app.models.test_case import TestCase
from app.services import approval_service, automation_execution_service, automation_service
from app.services.agent_dispatch_service import enqueue_agent_run
from app.services.automation_generation_service import build_generation_payload
from app.services.display_id_service import display_id, temporary_id
from app.services.project_application_service import resolve_environment_url

logger = logging.getLogger(__name__)

GENERATION_WAVE_SIZE = 25
# Matches AutomationBatchExecuteRequest's script_ids max_length — bigger
# Studio runs fan out into several chunked ExecutionRuns.
EXECUTION_CHUNK_SIZE = 200

_AGENT_TERMINAL = {"completed", "failed", "cancelled"}
_RUN_TERMINAL = {"completed", "failed", "cancelled"}
ACTIVE_STATUSES = {"exploring", "plan_ready", "generating", "scripts_ready", "executing", "healing"}


class StudioStateError(Exception):
    """The run is not in a stage that allows the requested action."""


class StudioValidationError(Exception):
    """The request payload is invalid for this run (bad application/env,
    empty selection, missing override note, ...)."""


def _chunks(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _page_entry_path(page_url: str | None) -> str | None:
    """Path + query of a planner-captured page URL — what a test must
    navigate to first."""
    if not page_url:
        return None
    parsed = urlparse(page_url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return path


async def get_run(db: AsyncSession, run_id: int) -> StudioRun | None:
    return await db.get(StudioRun, run_id)


async def list_runs(db: AsyncSession, project_id: int) -> list[StudioRun]:
    result = await db.execute(
        select(StudioRun).where(StudioRun.project_id == project_id).order_by(StudioRun.id.desc())
    )
    return list(result.scalars().all())


# Best-effort fallback for a count the user already typed into the free-text
# Planner Objective (e.g. "generate 5 test cases") rather than the explicit
# target_test_case_count field — the reliable path is the explicit field;
# this exists so what users already type today starts being honored too.
# Deliberately does NOT match "at least"/"minimum"/"more than N ..." — those
# state a floor, not a ceiling, and capping to them would be the opposite of
# what the user asked for.
_TC_COUNT_PATTERN = re.compile(r"\b(\d{1,3})\s*(?:test\s*cases?|tcs?|tests?)\b", re.IGNORECASE)
_TC_COUNT_FLOOR_PATTERN = re.compile(r"\b(?:at\s*least|minimum(?:\s*of)?|more\s*than|over)\s*$", re.IGNORECASE)


def _parse_target_count_from_objective(objective: str | None) -> int | None:
    if not objective:
        return None
    match = _TC_COUNT_PATTERN.search(objective)
    if not match:
        return None
    preceding = objective[:match.start()]
    if _TC_COUNT_FLOOR_PATTERN.search(preceding):
        return None
    count = int(match.group(1))
    return count if 1 <= count <= 200 else None


async def create_run(db: AsyncSession, *, project_id: int, user_id: int, data) -> StudioRun:
    application = await db.get(ProjectApplication, data.application_id)
    if application is None or application.project_id != project_id:
        raise StudioValidationError(f"Application {data.application_id} not found in project {project_id}")
    target_url = resolve_environment_url(application, data.environment)
    if not target_url:
        raise StudioValidationError(
            f"Application '{application.name}' has no URL configured for environment "
            f"'{data.environment}' — add one under Settings → Applications first."
        )
    target_test_case_count = data.target_test_case_count or _parse_target_count_from_objective(data.objective)
    run = StudioRun(
        project_id=project_id,
        created_by=user_id,
        name=data.name,
        status="draft",
        config={
            "application_id": application.id,
            "application_name": application.name,
            "environment": data.environment,
            "target_url": target_url,
            "objective": data.objective,
            "coverage_types": data.coverage_types,
            "excluded_paths": data.excluded_paths,
            "browser": data.browser,
            "max_pages": data.max_pages,
            "max_minutes": data.max_minutes,
            "target_test_case_count": target_test_case_count,
            "framework": data.framework,
            "runner_mode": data.runner_mode,
            "parallelism": data.parallelism,
            "timeout_seconds": data.timeout_seconds,
        },
    )
    db.add(run)
    await db.flush()
    return run


async def start_exploration(db: AsyncSession, run: StudioRun, user_id: int) -> tuple[AgentRun, str | None]:
    if run.status not in {"draft", "failed"}:
        raise StudioStateError(f"Cannot start exploration from status '{run.status}'")
    config = run.config or {}
    agent_run, task_id = await enqueue_agent_run(
        db,
        project_id=run.project_id,
        user_id=user_id,
        agent_name="playwright_planner",
        input_data={
            "studio_run_id": run.id,
            "application_id": config.get("application_id"),
            "application_url": config.get("target_url"),
            "environment": config.get("environment"),
            "objective": config.get("objective") or "",
            "coverage_types": config.get("coverage_types") or ["positive", "negative"],
            "excluded_paths": config.get("excluded_paths") or [],
            "max_pages": config.get("max_pages") or 10,
            "max_minutes": config.get("max_minutes") or 20,
            "target_test_case_count": config.get("target_test_case_count"),
        },
        metadata={"studio_run_id": run.id},
    )
    run.status = "exploring"
    run.error = None
    run.agent_runs = {**(run.agent_runs or {}), "planner": agent_run.id}
    await db.flush()
    return agent_run, task_id


async def apply_planner_output(db: AsyncSession, *, studio_run_id: int, agent_run: AgentRun, output: dict) -> None:
    """Called from agent_tasks.py's playwright_planner persistence branch.

    Stores a UI-sized plan (page summaries + full proposals) on the run and
    advances exploring → plan_ready. Full element catalogs are NOT copied
    here — they live in locator_map, where generation grounding reads them.
    """
    run = await db.get(StudioRun, studio_run_id)
    if run is None:
        logger.warning("Planner output for unknown studio run %s; dropping", studio_run_id)
        return
    if run.status not in {"exploring", "draft"}:
        logger.warning(
            "Planner output for studio run %s arrived in status '%s'; dropping", studio_run_id, run.status
        )
        return
    pages_summary = [
        {
            "url": p.get("url"),
            "title": p.get("title"),
            "element_count": len(p.get("elements") or []),
            "blockers": p.get("blockers") or [],
        }
        for p in output.get("pages", [])
    ]
    run.plan = {
        "explored_page_count": output.get("explored_page_count", len(pages_summary)),
        "pages": pages_summary,
        "proposed_test_cases": output.get("proposed_test_cases", []),
        "planner_agent_run_id": agent_run.id,
        "total_proposed_before_cap": output.get("total_proposed_before_cap"),
        "target_test_case_count": output.get("target_test_case_count"),
    }
    run.status = "plan_ready"
    await db.flush()


async def approve_plan(
    db: AsyncSession,
    run: StudioRun,
    user_id: int,
    *,
    included_keys: list[str] | None,
    notes: str | None,
) -> dict:
    """Bulk gate 1: materialize the approved proposals as real, approved
    TestCase rows and enqueue generation waves."""
    if run.status != "plan_ready":
        raise StudioStateError(f"Cannot approve the plan from status '{run.status}'")
    proposals = (run.plan or {}).get("proposed_test_cases") or []
    if included_keys is None:
        # Default selection = everything the planner didn't flag as blocked
        # (OTP/CAPTCHA on the live page). Including a blocked proposal is
        # allowed, but only by explicit key.
        selected = [p for p in proposals if not p.get("blocked_reasons")]
    else:
        wanted = set(included_keys)
        selected = [p for p in proposals if p.get("key") in wanted]
    if not selected:
        raise StudioValidationError("No test case proposals selected for approval")

    config = run.config or {}
    audit_note = f"Playwright Studio bulk plan approval — run #{run.id}" + (f": {notes}" if notes else "")
    # Every page the planner actually visited (not just this proposal's own
    # page_url) — a multi-step flow that clicks through to a SECOND page
    # needs its wait_for_url/url-assertion targets grounded against a real
    # captured URL too, the same way locators are grounded against the
    # element catalog. Without this the LLM guesses the destination pattern
    # (observed live: '/candidate' invented for the real
    # '/sign-up?role=candidate') and both generation AND repair have no way
    # to correct it since neither ever sees the real page list.
    explored_page_paths = sorted({
        p.get("url") for p in (run.plan or {}).get("pages", []) if p.get("url")
    })
    tc_ids: list[int] = []
    for proposal in selected:
        steps = [
            {"action": s.get("description") or s.get("action") or "", "expected": ""}
            for s in (proposal.get("steps") or [])
        ]
        # Make the REAL entry route part of the test case text itself: the
        # planner captured this proposal's elements on a specific live page,
        # and LLM-guessed routes were the #1 cause of whole-batch failures
        # (e.g. '/employer/signup' invented for '/sign-up?role=employer').
        # Generation additionally force-grounds the contract's first
        # navigate step to this page (automation_agent._ground_entry_route).
        entry_path = _page_entry_path(proposal.get("page_url"))
        if entry_path and entry_path != "/":
            steps = [{"action": f"Navigate to {entry_path}", "expected": ""}] + steps
        blocked = proposal.get("blocked_reasons") or []
        tc = TestCase(
            project_id=run.project_id,
            application_id=config.get("application_id"),
            created_by=user_id,
            test_case_id=temporary_id("TC"),
            title=proposal.get("title") or "Untitled Test Case",
            preconditions=proposal.get("preconditions"),
            steps=steps,
            expected_result=proposal.get("expected_result"),
            priority=proposal.get("priority") or "Medium",
            test_type=proposal.get("coverage_type") or "positive",
            automation_candidate=True,
            execution_mode="automation",
            automation_eligible="no" if blocked else "yes",
            automation_status="not_required" if blocked else "pending",
            test_phase=config.get("environment"),
            status="approved",
            metadata_={
                "origin": "playwright_studio",
                "studio_run_id": run.id,
                "planner_key": proposal.get("key"),
                "page_url": proposal.get("page_url"),
                "explored_page_paths": explored_page_paths,
                "planner_steps": proposal.get("steps"),
                "blocked_reasons": blocked,
                "ungrounded_elements": proposal.get("ungrounded_elements") or [],
            },
        )
        db.add(tc)
        await db.flush()
        tc.test_case_id = display_id("TC", tc.id)
        await db.flush()
        await approval_service.create_approval_action(
            db,
            project_id=run.project_id,
            user_id=user_id,
            entity_type="test_case",
            entity_id=tc.id,
            action="approve",
            notes=audit_note,
        )
        tc_ids.append(tc.id)

    generation_run_ids: list[int] = []
    for wave in _chunks(tc_ids, GENERATION_WAVE_SIZE):
        payload = await build_generation_payload(db, project_id=run.project_id, test_case_ids=wave)
        if not payload.test_cases:
            continue
        agent_run, _task_id = await enqueue_agent_run(
            db,
            project_id=run.project_id,
            user_id=user_id,
            agent_name="automation_script",
            input_data={
                "test_cases": payload.test_cases,
                "framework": config.get("framework") or "playwright",
                "locator_map": payload.locator_map,
                "studio_run_id": run.id,
            },
            metadata={
                "studio_run_id": run.id,
                "approved_test_case_ids": [tc["id"] for tc in payload.test_cases],
            },
        )
        generation_run_ids.append(agent_run.id)

    run.test_case_ids = tc_ids
    run.agent_runs = {**(run.agent_runs or {}), "generation": generation_run_ids}
    run.plan = {**(run.plan or {}), "approved_keys": [p.get("key") for p in selected]}
    run.status = "generating"
    await db.flush()
    return {
        "test_case_ids": tc_ids,
        "generation_agent_run_ids": generation_run_ids,
        "wave_count": len(generation_run_ids),
    }


async def _execution_failed(db: AsyncSession, run: StudioRun) -> bool:
    """Whether this run's most recent execution ended in failure.

    `_reconcile_status` marks a run "completed" once every ExecutionRun reaches
    a terminal state — completed, failed or cancelled alike. So a run whose
    tests all failed reports "completed", which is accurate about the pipeline
    and useless as a signal of whether anything worked. Retry has to look at
    the executions themselves.
    """
    exec_ids = run.execution_run_ids or []
    if not exec_ids:
        return False
    result = await db.execute(select(ExecutionRun).where(ExecutionRun.id.in_(exec_ids)))
    runs = list(result.scalars().all())
    return bool(runs) and any(r.status == "failed" for r in runs)


async def can_retry(db: AsyncSession, run: StudioRun) -> bool:
    """Retry is offered for an outright failed run, for one whose ExecutionRun
    failed, and for one that COMPLETED with failing tests.

    That third case is the common one and was missed at first: an ExecutionRun
    reports "completed" when it finishes, whatever its results say. Observed
    live 2026-08-03 — execution 65 completed 3/5, two test cases failed, and
    can_retry came back False because the run itself had not failed. The
    failing tests are the whole reason to offer a retry.
    """
    if run.status == "failed":
        return True
    if run.status not in {"completed", "executing"}:
        return False
    return await _execution_failed(db, run) or bool(await failed_test_case_ids(db, run))


async def failed_test_case_ids(db: AsyncSession, run: StudioRun) -> list[int]:
    """The run's test cases whose latest script did not work.

    Two independent signals, because a script can fail before it ever reaches
    an execution:

      * an ExecutionResult for this run recorded a failure, or
      * the script's own dry run failed (metadata_.last_dry_run.passed false).

    Returned in the run's own test-case order so a regeneration wave is stable
    and its idempotency hash does not change between identical requests.
    """
    ordered = list(run.test_case_ids or [])
    if not ordered:
        return []

    failed: set[int] = set()

    exec_ids = run.execution_run_ids or []
    if exec_ids:
        result = await db.execute(
            select(ExecutionResult.test_case_id).where(
                ExecutionResult.execution_run_id.in_(exec_ids),
                ExecutionResult.status.in_(["fail", "failed", "error"]),
            )
        )
        failed.update(tc_id for tc_id in result.scalars().all() if tc_id is not None)

    for script in await _latest_scripts_for_run(db, run):
        last_dry_run = (script.metadata_ or {}).get("last_dry_run") or {}
        if last_dry_run.get("passed") is False and script.test_case_id:
            failed.add(script.test_case_id)

    return [tc_id for tc_id in ordered if tc_id in failed]


async def retry_run(
    db: AsyncSession,
    run: StudioRun,
    user_id: int,
    *,
    runner_mode: str | None = None,
    only_failed: bool = False,
) -> dict:
    """Resume a failed run from the stage that failed, keeping everything the
    earlier stages already produced.

    Before this, a failed run was a dead end: the only way forward was a brand
    new run, which re-crawls the application and re-proposes a plan a human has
    already reviewed. That is minutes of browser time and a second set of
    duplicate test cases, thrown away because a transient failure — a provider
    error, a worker restart — hit the last stage.

    The stage is inferred from what the run actually has rather than from a
    stored marker, because that is the same evidence `_reconcile_status` uses
    to fail it in the first place:

      * `test_case_ids` present -> the plan was approved and materialized, so
        generation is what failed. Re-enqueue generation for those exact test
        cases; the approved TestCase rows and their audit trail are reused,
        never duplicated.
      * otherwise -> the planner failed before producing anything approvable,
        so exploration is what failed. `start_exploration` already accepts
        "failed" for exactly this.
    """
    if not await can_retry(db, run):
        raise StudioStateError(
            f"Nothing to retry — this run is '{run.status}' and its executions did not fail."
        )

    # Regenerate only what failed: the diagnostics name specific test cases,
    # and re-running the whole wave to fix two of them spends model time on
    # scripts that already work and replaces them with different ones for no
    # reason. Explicitly requested rather than inferred, because "retry" and
    # "fix these two" are different intents.
    if only_failed:
        targets = await failed_test_case_ids(db, run)
        if not targets:
            raise StudioValidationError(
                "No failed test cases to regenerate — every script in this run either "
                "passed or has not been run yet."
            )
        return await _retry_generation(db, run, user_id, test_case_ids=targets, partial=True)

    # A run whose scripts are already generated and approved failed at
    # EXECUTION, so regenerating them would throw away good work to fix
    # something that was never wrong with them. Re-run the same approved
    # scripts instead.
    if run.status != "failed" or await _execution_failed(db, run):
        return await _retry_execution(db, run, user_id, runner_mode=runner_mode)

    if not run.test_case_ids:
        agent_run, _task_id = await start_exploration(db, run, user_id)
        return {"stage": "exploration", "agent_run_ids": [agent_run.id], "test_case_count": 0}

    return await _retry_generation(db, run, user_id, test_case_ids=list(run.test_case_ids))


async def _retry_generation(
    db: AsyncSession,
    run: StudioRun,
    user_id: int,
    *,
    test_case_ids: list[int],
    partial: bool = False,
) -> dict:
    """Enqueue generation waves for `test_case_ids`.

    `partial` is what a failed-only regeneration passes: the same machinery,
    but the run keeps its other scripts. It exists as a flag rather than two
    functions because the ONLY difference is the message and the fact that a
    partial wave's agent-run list still governs when the run settles.
    """
    config = run.config or {}
    generation_run_ids: list[int] = []
    for wave in _chunks(test_case_ids, GENERATION_WAVE_SIZE):
        # Rebuilt rather than replayed from the previous attempt's input: the
        # locator map may have been re-discovered since, and a retry should
        # use the best grounding available now, not the grounding that was
        # available when it failed.
        payload = await build_generation_payload(db, project_id=run.project_id, test_case_ids=wave)
        if not payload.test_cases:
            continue
        agent_run, _task_id = await enqueue_agent_run(
            db,
            project_id=run.project_id,
            user_id=user_id,
            agent_name="automation_script",
            input_data={
                "test_cases": payload.test_cases,
                "framework": config.get("framework") or "playwright",
                "locator_map": payload.locator_map,
                "studio_run_id": run.id,
            },
            metadata={
                "studio_run_id": run.id,
                "approved_test_case_ids": [tc["id"] for tc in payload.test_cases],
                "retry_of_run_id": run.id,
                "partial_regeneration": partial,
            },
        )
        generation_run_ids.append(agent_run.id)

    if not generation_run_ids:
        raise StudioValidationError(
            "None of the selected test cases can be generated from — they are no longer "
            "approved, or they have been deleted."
        )

    # The failed attempt's agent runs are replaced, not appended to:
    # _reconcile_status waits for every id here to be terminal, and a failed
    # one left in the list would fail the run again the moment it is read.
    run.agent_runs = {**(run.agent_runs or {}), "generation": generation_run_ids}
    run.status = "generating"
    run.error = None
    await db.flush()
    return {
        "stage": "generation",
        "agent_run_ids": generation_run_ids,
        "test_case_count": len(test_case_ids),
        "partial": partial,
    }


async def _retry_execution(
    db: AsyncSession, run: StudioRun, user_id: int, *, runner_mode: str | None = None
) -> dict:
    """Re-execute this run's already-approved scripts.

    `runner_mode` exists because the commonest reason an execution fails
    wholesale is that it ran in a mode this deployment is not wired for —
    observed live 2026-08-03: a run configured for "docker" failed all five
    tests with "docker daemon not reachable", because only the runner-executor
    service holds the Docker socket. Repeating the same mode would reproduce
    the same failure, so the caller can change it, and the choice is persisted
    to the run's config so the audit shows what was actually run.
    """
    scripts = await _latest_scripts_for_run(db, run)
    scripts = [s for s in scripts if s.status in {"approved", "executed"}]
    if not scripts:
        raise StudioValidationError(
            "This run has no approved scripts to execute. Approve the generated scripts first."
        )

    config = dict(run.config or {})
    if runner_mode:
        config["runner_mode"] = runner_mode
        run.config = config

    execution_run_ids: list[int] = []
    chunks = _chunks([s.id for s in scripts], EXECUTION_CHUNK_SIZE)
    for index, chunk in enumerate(chunks, start=1):
        suffix = f" — retry batch {index}/{len(chunks)}" if len(chunks) > 1 else " — retry"
        exec_run, _task_id = await automation_execution_service.start_batch_execution(
            db,
            project_id=run.project_id,
            user_id=user_id,
            script_ids=chunk,
            environment=config.get("environment"),
            timeout_seconds=int(config.get("timeout_seconds") or 600),
            run_name=f"{run.name}{suffix}",
            extra_metadata={
                "studio_run_id": run.id,
                "runner_mode": config.get("runner_mode"),
                "parallelism": config.get("parallelism") or 1,
                "retry_of_execution_run_ids": list(run.execution_run_ids or []),
            },
        )
        execution_run_ids.append(exec_run.id)

    # Replaced, not appended: _reconcile_status waits for every id here to be
    # terminal, and the failed one would settle the run again immediately.
    run.execution_run_ids = execution_run_ids
    run.status = "executing"
    run.error = None
    await db.flush()
    return {
        "stage": "execution",
        "agent_run_ids": [],
        "execution_run_ids": execution_run_ids,
        "test_case_count": len(scripts),
    }


async def _latest_scripts_for_run(db: AsyncSession, run: StudioRun) -> list[AutomationScript]:
    tc_ids = run.test_case_ids or []
    if not tc_ids:
        return []
    result = await db.execute(
        select(AutomationScript)
        .where(AutomationScript.test_case_id.in_(tc_ids))
        .order_by(AutomationScript.test_case_id, AutomationScript.id.desc())
    )
    latest: dict[int, AutomationScript] = {}
    for script in result.scalars().all():
        # Rows arrive newest-first per test case; the repair loop's new
        # versions supersede their parents automatically here.
        latest.setdefault(script.test_case_id, script)
    return list(latest.values())


async def approve_scripts(
    db: AsyncSession,
    run: StudioRun,
    user_id: int,
    *,
    notes: str | None,
) -> dict:
    """Bulk gate 2: approve every generated script (audited, override note
    required if any script has known quality issues) and launch execution."""
    if run.status != "scripts_ready":
        raise StudioStateError(f"Cannot approve scripts from status '{run.status}'")
    scripts = await _latest_scripts_for_run(db, run)
    scripts = [s for s in scripts if s.status not in {"rejected", "deprecated"}]
    if not scripts:
        raise StudioValidationError("No generated scripts found for this run")

    needs_override = [
        (s.script_id, reason)
        for s in scripts
        if (reason := automation_service.approval_override_reason(s, notes))
    ]
    if needs_override:
        listing = "; ".join(f"{sid}: {reason}" for sid, reason in needs_override[:5])
        raise StudioValidationError(
            f"{len(needs_override)} script(s) have known issues and need an override note "
            f"before bulk approval — add a note explaining why. First few: {listing}"
        )

    audit_note = f"Playwright Studio bulk script approval — run #{run.id}" + (f": {notes}" if notes else "")
    for script in scripts:
        await automation_service.approve_script(db, script, "approve", audit_note)
        await approval_service.create_approval_action(
            db,
            project_id=run.project_id,
            user_id=user_id,
            entity_type="automation_script",
            entity_id=script.id,
            action="approve",
            notes=audit_note,
        )

    config = run.config or {}
    execution_run_ids: list[int] = []
    chunks = _chunks([s.id for s in scripts], EXECUTION_CHUNK_SIZE)
    for index, chunk in enumerate(chunks, start=1):
        suffix = f" — batch {index}/{len(chunks)}" if len(chunks) > 1 else ""
        exec_run, _task_id = await automation_execution_service.start_batch_execution(
            db,
            project_id=run.project_id,
            user_id=user_id,
            script_ids=chunk,
            environment=config.get("environment"),
            timeout_seconds=int(config.get("timeout_seconds") or 600),
            run_name=f"{run.name}{suffix}",
            extra_metadata={
                "studio_run_id": run.id,
                # Absent means the server's configured mode applies; see the
                # schema. Never coerced to "local" here.
                "runner_mode": config.get("runner_mode"),
                "parallelism": config.get("parallelism") or 1,
            },
        )
        execution_run_ids.append(exec_run.id)

    run.execution_run_ids = execution_run_ids
    run.status = "executing"
    await db.flush()
    return {
        "approved_script_ids": [s.id for s in scripts],
        "execution_run_ids": execution_run_ids,
    }


async def cancel_run(db: AsyncSession, run: StudioRun, user_id: int) -> None:
    if run.status in _RUN_TERMINAL:
        raise StudioStateError(f"Run is already '{run.status}' — nothing to cancel.")

    from app.worker.celery_app import celery_app

    agent_run_ids = []
    agent_runs = run.agent_runs or {}
    if agent_runs.get("planner"):
        agent_run_ids.append(agent_runs["planner"])
    agent_run_ids.extend(agent_runs.get("generation") or [])
    for agent_run_id in agent_run_ids:
        agent_run = await db.get(AgentRun, agent_run_id)
        if agent_run is None or agent_run.status not in {"pending", "running"}:
            continue
        if agent_run.celery_task_id:
            try:
                celery_app.control.revoke(agent_run.celery_task_id, terminate=True)
            except Exception:
                logger.exception("Failed to revoke agent task %s", agent_run.celery_task_id)
        agent_run.status = "cancelled"
        agent_run.progress_message = "Cancelled with Studio run"

    for exec_run_id in run.execution_run_ids or []:
        exec_run = await db.get(ExecutionRun, exec_run_id)
        if exec_run is None or exec_run.status not in {"pending", "queued", "running"}:
            continue
        task_id = (exec_run.metadata_ or {}).get("task_id")
        if task_id:
            try:
                celery_app.control.revoke(task_id, terminate=True)
            except Exception:
                logger.exception("Failed to revoke batch task %s", task_id)
        pending = await db.execute(
            select(ExecutionResult).where(
                ExecutionResult.execution_run_id == exec_run.id,
                ExecutionResult.status.in_(["pending", "running"]),
            )
        )
        for row in pending.scalars().all():
            row.status = "skip"
            row.error_message = row.error_message or "Cancelled before this test ran."
        exec_run.status = "cancelled"
        exec_run.metadata_ = {**(exec_run.metadata_ or {}), "cancelled_by": user_id}

    run.status = "cancelled"
    await db.flush()


async def _reconcile_status(db: AsyncSession, run: StudioRun) -> None:
    """Read-time reconciliation: agent failures and execution completion
    advance/fail the run without dedicated worker callbacks."""
    agent_runs = run.agent_runs or {}
    if run.status == "exploring" and agent_runs.get("planner"):
        planner = await db.get(AgentRun, agent_runs["planner"])
        if planner is not None and planner.status in {"failed", "cancelled"}:
            run.status = "failed"
            run.error = planner.error_message or "Planner agent failed"
            await db.flush()
    elif run.status == "generating":
        generation_ids = agent_runs.get("generation") or []
        if generation_ids:
            result = await db.execute(select(AgentRun).where(AgentRun.id.in_(generation_ids)))
            runs = list(result.scalars().all())
            if runs and all(r.status in _AGENT_TERMINAL for r in runs):
                scripts = await _latest_scripts_for_run(db, run)
                if scripts:
                    run.status = "scripts_ready"
                else:
                    run.status = "failed"
                    errors = "; ".join(filter(None, (r.error_message for r in runs)))
                    run.error = errors or "Script generation produced no scripts"
                await db.flush()
    elif run.status == "executing":
        exec_ids = run.execution_run_ids or []
        if exec_ids:
            result = await db.execute(select(ExecutionRun).where(ExecutionRun.id.in_(exec_ids)))
            exec_runs = list(result.scalars().all())
            if exec_runs and all(r.status in {"completed", "failed", "cancelled"} for r in exec_runs):
                run.status = "completed"
                await db.flush()


# ── Failure insights ─────────────────────────────────────────────────────────
# Turns raw failure text into actionable, non-functional diagnostics the user
# can act on (environment, infrastructure, auth, test data) — ordered: the
# first matching rule wins, so put systemic/infrastructure causes before
# generic timeouts.
_INSIGHT_DEFINITIONS: list[dict] = [
    {
        "kind": "environment_unreachable",
        "severity": "error",
        "pattern": re.compile(r"ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ECONNREFUSED|ERR_CERT|net::ERR|ERR_TIMED_OUT", re.I),
        "message": "The target application was unreachable from the test runner container(s).",
        "action": (
            "Verify the environment URL in Settings → Applications resolves from inside Docker "
            "(DNS/proxy/VPN), or set AUTOMATION_DOCKER_NETWORK if the app runs inside the same "
            "compose stack. Re-run once reachable — these are not script problems."
        ),
    },
    {
        "kind": "runner_infrastructure",
        "severity": "error",
        "pattern": re.compile(r"browserType\.launch|Executable doesn't exist|docker CLI not found|docker daemon not reachable|Could not start docker", re.I),
        "message": "Test runner infrastructure problem — the browser or Docker runtime was unavailable.",
        "action": (
            "Rebuild the worker image (docker compose build worker && docker compose up -d) and "
            "confirm /var/run/docker.sock is mounted, or switch the run to the Local runner in Step 1."
        ),
    },
    {
        "kind": "url_assertion_mismatch",
        "severity": "warning",
        "pattern": re.compile(r"waitForURL|toHaveURL", re.I),
        "message": "URL checks never matched the page the app actually navigated to (usually an assumed route or pattern).",
        "action": (
            "Regenerate the scripts — entry routes and URL expectations are now grounded to the "
            "pages the planner really explored, instead of LLM-guessed paths."
        ),
    },
    {
        "kind": "element_not_found",
        "severity": "warning",
        "pattern": re.compile(r"waiting for (getBy|locator)|toBeVisible|strict mode violation", re.I),
        "message": (
            "Elements never appeared on the page the test landed on — typically a wrong entry "
            "route (now fixed by route grounding) or an area that requires sign-in, which Studio "
            "runs don't have yet."
        ),
        "action": (
            "Regenerate the scripts first. If the flow lives behind a login, exclude that area in "
            "Step 1 (Excluded areas) until application credentials support is configured."
        ),
    },
    {
        "kind": "slow_or_stuck",
        "severity": "info",
        "pattern": re.compile(r"Test timeout of \d+ms exceeded", re.I),
        "message": "Tests hit the per-test time budget without a more specific error.",
        "action": (
            "If the environment is genuinely slow, raise the per-script timeout in Step 1; "
            "otherwise open the trace/video on the failed result to see where it stalled."
        ),
    },
]


def _derive_failure_insights(failed_rows: list) -> list[dict]:
    """Aggregate failed ExecutionResults into ranked, deduplicated,
    actionable diagnostics. Data-classification failures take priority over
    text patterns — 'needs real test data' beats any timeout wording."""
    buckets: dict[str, dict] = {}

    def _bucket(kind: str, severity: str, message: str, action: str, test_name: str | None) -> None:
        entry = buckets.setdefault(kind, {
            "kind": kind, "severity": severity, "message": message,
            "action": action, "count": 0, "examples": [],
        })
        entry["count"] += 1
        if test_name and len(entry["examples"]) < 3 and test_name not in entry["examples"]:
            entry["examples"].append(test_name)

    for row in failed_rows:
        text = f"{row.error_message or ''}\n{row.stack_trace or ''}"
        classification = (
            ((row.metadata_ or {}).get("failure_classification") or {}).get("classification")
        )
        if classification == "data_issue":
            _bucket(
                "test_data_required", "warning",
                "Failures caused by missing/invalid test data (unique emails, registered accounts, valid credentials).",
                "Provide real test data for these flows or exclude them — auto-heal never invents credentials.",
                row.test_name,
            )
            continue
        if classification == "environment_issue":
            _bucket(
                "environment_unreachable", "error",
                _INSIGHT_DEFINITIONS[0]["message"], _INSIGHT_DEFINITIONS[0]["action"], row.test_name,
            )
            continue
        for definition in _INSIGHT_DEFINITIONS:
            if definition["pattern"].search(text):
                _bucket(
                    definition["kind"], definition["severity"],
                    definition["message"], definition["action"], row.test_name,
                )
                break
        else:
            _bucket(
                "unrecognized_failure", "info",
                "Failures without a recognized non-functional cause — likely genuine application or script issues.",
                "Open the failed results' logs/traces in Automation Execution to inspect them individually.",
                row.test_name,
            )

    severity_rank = {"error": 0, "warning": 1, "info": 2}
    return sorted(buckets.values(), key=lambda b: (severity_rank.get(b["severity"], 3), -b["count"]))


def _script_summary(script: AutomationScript) -> dict:
    metadata = script.metadata_ or {}
    gate = script.static_gate_result or {}
    return {
        "id": script.id,
        "script_id": script.script_id,
        "test_case_id": script.test_case_id,
        "status": script.status,
        "version": script.version,
        "framework": script.framework,
        "grounding": metadata.get("grounding"),
        "static_gate_passed": gate.get("passed"),
        "last_dry_run": metadata.get("last_dry_run"),
    }


async def get_run_detail(db: AsyncSession, run: StudioRun) -> dict:
    await _reconcile_status(db, run)

    agent_runs = run.agent_runs or {}
    agent_summaries: dict = {"planner": None, "generation": []}
    if agent_runs.get("planner"):
        planner = await db.get(AgentRun, agent_runs["planner"])
        if planner is not None:
            agent_summaries["planner"] = {
                "id": planner.id,
                "status": planner.status,
                "progress_percent": planner.progress_percent,
                "progress_message": planner.progress_message,
                "error_message": planner.error_message,
                "created_at": planner.created_at,
                "updated_at": planner.updated_at,
            }
    generation_ids = agent_runs.get("generation") or []
    if generation_ids:
        result = await db.execute(select(AgentRun).where(AgentRun.id.in_(generation_ids)))
        agent_summaries["generation"] = [
            {
                "id": r.id,
                "status": r.status,
                "progress_percent": r.progress_percent,
                "progress_message": r.progress_message,
                "error_message": r.error_message,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in result.scalars().all()
        ]

    scripts = await _latest_scripts_for_run(db, run)
    script_counts: dict[str, int] = {}
    for s in scripts:
        script_counts[s.status] = script_counts.get(s.status, 0) + 1

    executions = []
    failure_insights: list[dict] = []
    exec_ids = run.execution_run_ids or []
    if exec_ids:
        result = await db.execute(select(ExecutionRun).where(ExecutionRun.id.in_(exec_ids)))
        executions = [
            {
                "id": r.id,
                "execution_id": r.execution_id,
                "status": r.status,
                "total_tests": r.total_tests,
                "passed": r.passed,
                "failed": r.failed,
                "skipped": r.skipped,
                "auto_heal": (r.metadata_ or {}).get("auto_heal"),
            }
            for r in result.scalars().all()
        ]
        failed_rows = await db.execute(
            select(ExecutionResult).where(
                ExecutionResult.execution_run_id.in_(exec_ids),
                ExecutionResult.status == "fail",
            )
        )
        failure_insights = _derive_failure_insights(list(failed_rows.scalars().all()))

    return {
        "agent_runs": agent_summaries,
        "scripts": [_script_summary(s) for s in scripts],
        "script_counts": script_counts,
        "executions": executions,
        "failure_insights": failure_insights,
        # Computed here rather than inferred in the UI: "can this be retried"
        # depends on the executions' own statuses, which the run's status
        # deliberately does not reflect (a run whose every test failed still
        # reports "completed").
        "can_retry": await can_retry(db, run),
        "failed_test_case_ids": await failed_test_case_ids(db, run),
    }
