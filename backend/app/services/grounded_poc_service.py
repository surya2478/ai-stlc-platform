"""Grounded Automation PoC — pipeline orchestration.

Stage machine per PocGroundingRun (see models/grounded_poc.py):

  draft → routing_ready        create_run computes the deterministic routing
  routing_ready → capturing    start_capture enqueues the capture agent
  capturing → awaiting_confirmation   assisted mode paused on ambiguity
  awaiting_confirmation → capturing   confirm_step folds in the choice, re-walks
  capturing → gate_passed | gate_blocked   apply_capture_output runs the gate
  gate_blocked → capturing     user fixes data/environment and re-captures
  gate_passed → generating     start_generation (hard-blocked otherwise)
  generating → generated | failed     reconciled at read time

Isolation rules honored here:
  - TestCase rows are read, never written, by this module.
  - locator_map is NOT written — generation grounding for a PoC run uses
    ONLY that run's captured evidence (evidence-exclusive locator_map),
    so the existing studios' grounding data is untouched.
  - Generation itself reuses the standard audited chain (contract →
    compile → static gate → dry run → repair) by enqueueing the existing
    automation_script agent — scripts land in the normal inventory where
    the mandatory live-validation and human-approval lifecycle applies.
"""
from __future__ import annotations

import logging
import uuid
from urllib.parse import urlparse

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.models.automation_script import AutomationScript
from app.models.grounded_poc import PocGroundingRun, PocStateEvidence
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.services import grounded_gate_service, grounded_routing_service
from app.services.agent_dispatch_service import enqueue_agent_run
from app.services.automation_generation_service import build_generation_payload
from app.services.project_application_service import resolve_default_application, resolve_environment_url

logger = logging.getLogger(__name__)

_TERMINAL = {"generated", "failed", "cancelled"}
ACTIVE_STATUSES = {"capturing", "generating"}


class PocStateError(Exception):
    """The run is not in a stage that allows the requested action."""


class PocValidationError(Exception):
    """Invalid input for this run (bad TC, missing URL, gate not passed...)."""


def _tc_dict(tc: TestCase) -> dict:
    return {
        "id": tc.id,
        "test_case_id": tc.test_case_id,
        "title": tc.title,
        "preconditions": tc.preconditions,
        "test_data": tc.test_data,
        "steps": tc.steps,
        "expected_result": tc.expected_result,
        "test_type": tc.test_type,
        "priority": tc.priority,
    }


async def get_run(db: AsyncSession, run_id: int) -> PocGroundingRun | None:
    return await db.get(PocGroundingRun, run_id)


async def list_runs(db: AsyncSession, project_id: int) -> list[PocGroundingRun]:
    result = await db.execute(
        select(PocGroundingRun)
        .where(PocGroundingRun.project_id == project_id)
        .order_by(PocGroundingRun.id.desc())
    )
    return list(result.scalars().all())


async def create_run(
    db: AsyncSession, *, project_id: int, user_id: int, test_case_id: int,
    environment: str, capture_mode: str = "automated",
) -> PocGroundingRun:
    tc = await db.get(TestCase, test_case_id)
    if tc is None or tc.project_id != project_id:
        raise PocValidationError(f"Test case {test_case_id} not found in project {project_id}")
    if tc.status != "approved":
        raise PocValidationError(
            f"Test case {tc.test_case_id} is '{tc.status}' — only approved test cases can be grounded"
        )

    # Same fallback build_generation_payload already uses: most test cases
    # don't set application_id explicitly and are meant to resolve to the
    # project's default application (confirmed via a live run: TC-0013 has
    # application_id=NULL yet its project has a default "Web" application
    # with a real SIT URL — this module rejected it outright before this
    # fallback existed, even though the URL was right there).
    application = await db.get(ProjectApplication, tc.application_id) if tc.application_id else None
    if application is None:
        application = await resolve_default_application(db, project_id)
    target_url = resolve_environment_url(application, environment) if application else None
    if not target_url:
        raise PocValidationError(
            "No application URL resolved — the test case's application needs a URL for "
            f"environment '{environment}' under Settings → Applications."
        )

    # Routing is deterministic and cheap — computed inline at creation so the
    # user sees the classification before deciding to launch a browser walk.
    routing = grounded_routing_service.route_test_case(_tc_dict(tc))

    run = PocGroundingRun(
        project_id=project_id,
        created_by=user_id,
        test_case_id=tc.id,
        application_id=application.id if application else None,
        status="routing_ready",
        capture_mode=capture_mode,
        config={
            "environment": environment,
            "target_url": target_url,
            "application_name": application.name if application else None,
            "test_case_display_id": tc.test_case_id,
            "test_case_title": tc.title,
            "confirmed_actions": {},
        },
        routing=routing,
    )
    db.add(run)
    await db.flush()
    return run


async def start_capture(db: AsyncSession, run: PocGroundingRun, user_id: int) -> tuple[AgentRun, str | None]:
    if run.status not in {"routing_ready", "gate_blocked", "gate_passed", "failed", "awaiting_confirmation"}:
        raise PocStateError(f"Cannot start capture from status '{run.status}'")
    if run.capture_mode == "manual_guided":
        raise PocValidationError(
            "Manual-guided capture is not implemented in this PoC phase — "
            "use automated or assisted mode."
        )
    tc = await db.get(TestCase, run.test_case_id)
    if tc is None:
        raise PocValidationError("Linked test case no longer exists")

    agent_run, task_id = await enqueue_agent_run(
        db,
        project_id=run.project_id,
        user_id=user_id,
        agent_name="grounded_capture",
        input_data={
            "grounding_run_id": run.id,
            "test_case": _tc_dict(tc),
            "application_url": (run.config or {}).get("target_url"),
            "application_id": run.application_id,
            "environment": (run.config or {}).get("environment"),
            "capture_mode": run.capture_mode,
            "routing": run.routing,
            "confirmed_actions": (run.config or {}).get("confirmed_actions") or {},
        },
        metadata={"grounding_run_id": run.id},
        # enqueue_agent_run's default idempotency key is derived from
        # (project, user, agent_name, input_data) — a gate_blocked retry with
        # unchanged inputs (same TC, same env) would silently hash-collide
        # with the prior completed run and be reused WITHOUT re-executing
        # (confirmed via a live run: the grounding run stuck in "capturing"
        # forever because no new agent task ever fired). Re-capture is
        # deliberately re-triggerable — gate_blocked retries and assisted-mode
        # resumes both call this with identical inputs on purpose — so a
        # fresh key every call is correct here, unlike Studio's one-shot
        # explore.
        idempotency_key=f"grounded_capture:{run.id}:{uuid.uuid4().hex}",
    )
    run.status = "capturing"
    run.error = None
    run.pending_confirmation = None
    agent_runs = dict(run.agent_runs or {})
    agent_runs["capture"] = [*agent_runs.get("capture", []), agent_run.id]
    run.agent_runs = agent_runs
    await db.flush()
    return agent_run, task_id


async def apply_capture_output(
    db: AsyncSession, *, grounding_run_id: int, agent_run: AgentRun, output: dict
) -> dict:
    """Called from agent_tasks.py's grounded_capture persistence branch.

    Persists the evidence packages, then either pauses for confirmation
    (assisted mode) or runs the coverage gate and lands on
    gate_passed / gate_blocked.
    """
    run = await db.get(PocGroundingRun, grounding_run_id)
    if run is None:
        logger.warning("Capture output for unknown grounding run %s; dropping", grounding_run_id)
        return {"grounding_run_id": grounding_run_id, "dropped": True}
    if run.status not in {"capturing", "awaiting_confirmation"}:
        logger.warning(
            "Capture output for grounding run %s arrived in status '%s'; dropping",
            grounding_run_id, run.status,
        )
        return {"grounding_run_id": grounding_run_id, "dropped": True}

    # Each capture is a full re-walk (confirmed_actions included), so prior
    # evidence for this run is replaced, not appended.
    await db.execute(
        delete(PocStateEvidence).where(PocStateEvidence.grounding_run_id == run.id)
    )

    evidence_rows: list[PocStateEvidence] = []
    prev_id: int | None = None
    for state in output.get("states", []):
        row = PocStateEvidence(
            project_id=run.project_id,
            grounding_run_id=run.id,
            sequence=state.get("sequence", 0),
            state_fingerprint=state.get("state_fingerprint") or "",
            url=(state.get("url") or "")[:1000] or None,
            title=(state.get("title") or "")[:500] or None,
            environment=state.get("environment"),
            elements=state.get("elements") or [],
            snapshot_text=state.get("snapshot_text"),
            screenshot_path=state.get("screenshot_path"),
            blockers=state.get("blockers") or [],
            console_evidence=state.get("console_evidence") or [],
            produced_by_step=state.get("produced_by_step"),
            prev_evidence_id=prev_id,
        )
        db.add(row)
        await db.flush()
        prev_id = row.id
        evidence_rows.append(row)

    config = dict(run.config or {})
    config["step_trace"] = output.get("step_trace") or []
    config["capture_output_dir"] = output.get("output_dir")
    run.config = config

    paused = output.get("paused")
    if paused:
        run.status = "awaiting_confirmation"
        run.pending_confirmation = paused
        await db.flush()
        return {
            "grounding_run_id": run.id,
            "evidence_count": len(evidence_rows),
            "status": run.status,
        }

    tc = await db.get(TestCase, run.test_case_id)
    packages = [
        {
            "id": row.id,
            "state_fingerprint": row.state_fingerprint,
            "url": row.url,
            "elements": row.elements,
            "snapshot_text": row.snapshot_text,
            "blockers": row.blockers,
        }
        for row in evidence_rows
    ]
    coverage = grounded_gate_service.evaluate_coverage(
        test_case=_tc_dict(tc) if tc else {},
        evidence_packages=packages,
        routing=run.routing or {},
    )
    run.coverage = coverage
    run.pending_confirmation = None
    run.status = "gate_passed" if coverage.get("generationAllowed") else "gate_blocked"
    await db.flush()
    return {
        "grounding_run_id": run.id,
        "evidence_count": len(evidence_rows),
        "coverage": coverage.get("overallCoverage"),
        "generation_allowed": coverage.get("generationAllowed"),
        "status": run.status,
    }


async def confirm_step(
    db: AsyncSession, run: PocGroundingRun, user_id: int, *, step_index: int, element_name: str
) -> tuple[AgentRun, str | None]:
    """Assisted mode: record the user's element choice for the paused step
    and re-run capture with it folded in."""
    if run.status != "awaiting_confirmation":
        raise PocStateError(f"Run is not awaiting confirmation (status '{run.status}')")
    pending = run.pending_confirmation or {}
    if pending.get("step_index") != step_index:
        raise PocValidationError(
            f"Confirmation is pending for step {pending.get('step_index')}, not {step_index}"
        )
    config = dict(run.config or {})
    confirmed = dict(config.get("confirmed_actions") or {})
    confirmed[str(step_index)] = element_name
    config["confirmed_actions"] = confirmed
    run.config = config
    await db.flush()
    return await start_capture(db, run, user_id)


async def start_generation(db: AsyncSession, run: PocGroundingRun, user_id: int) -> tuple[AgentRun, str | None]:
    """The gate IS the gate: generation only from gate_passed, and the LLM
    sees an evidence-exclusive locator catalog — nothing outside this run's
    captured states."""
    if run.status != "gate_passed":
        raise PocStateError(
            f"Generation requires a passed coverage gate (status is '{run.status}'). "
            "Re-capture or resolve the listed gaps first."
        )
    if not (run.coverage or {}).get("generationAllowed"):
        raise PocStateError("Coverage gate verdict does not allow generation")

    payload = await build_generation_payload(
        db, project_id=run.project_id, test_case_ids=[run.test_case_id]
    )
    if not payload.test_cases:
        raise PocValidationError("Test case is no longer eligible for generation (not approved?)")

    result = await db.execute(
        select(PocStateEvidence)
        .where(PocStateEvidence.grounding_run_id == run.id)
        .order_by(PocStateEvidence.sequence)
    )
    evidence = list(result.scalars().all())
    if not evidence:
        raise PocValidationError("No captured evidence found for this run — capture first")

    # Evidence-exclusive grounding: REPLACE whatever locator_map context the
    # standard payload builder found with ONLY this run's captured catalog.
    app_key = run.application_id if run.application_id is not None else "poc"
    evidence_catalog = [
        {
            "element_name": el.get("element_name"),
            "page": row.url or "",
            "role": el.get("recommended_strategy", "role"),
            "business_meaning": None,
            "recommended_locator": el.get("recommended_locator"),
            "confidence_score": el.get("confidence_score", 0),
        }
        for row in evidence
        for el in (row.elements or [])
        if el.get("element_name") and el.get("recommended_locator")
    ]
    tc_payload = dict(payload.test_cases[0])
    entry = evidence[0]
    tc_payload["application_id"] = app_key
    tc_payload["page_url"] = entry.url
    tc_payload["explored_page_paths"] = sorted({
        (urlparse(row.url).path or "/") + (f"?{urlparse(row.url).query}" if urlparse(row.url).query else "")
        for row in evidence if row.url
    })

    agent_run, task_id = await enqueue_agent_run(
        db,
        project_id=run.project_id,
        user_id=user_id,
        agent_name="automation_script",
        input_data={
            "test_cases": [tc_payload],
            "framework": "playwright",
            "locator_map": {str(app_key): evidence_catalog},
        },
        metadata={"grounding_run_id": run.id, "source": "grounded_poc"},
    )
    run.status = "generating"
    run.error = None
    run.agent_runs = {**(run.agent_runs or {}), "generation": agent_run.id}
    await db.flush()
    return agent_run, task_id


async def cancel_run(db: AsyncSession, run: PocGroundingRun, user_id: int) -> None:
    if run.status in _TERMINAL:
        raise PocStateError(f"Run is already terminal ('{run.status}')")
    run.status = "cancelled"
    await db.flush()


async def _agent_summary(db: AsyncSession, agent_run_id: int | None) -> dict | None:
    if not agent_run_id:
        return None
    agent_run = await db.get(AgentRun, agent_run_id)
    if agent_run is None:
        return None
    return {
        "id": agent_run.id,
        "status": agent_run.status,
        "progress_percent": agent_run.progress_percent or 0,
        "progress_message": agent_run.progress_message,
        "error_message": agent_run.error_message,
    }


async def get_run_detail(db: AsyncSession, run: PocGroundingRun) -> dict:
    """Read-time reconciliation + UI-shaped detail (mirrors studio_service:
    agent failures and generation completion flip the run status here,
    without extra worker hooks)."""
    agent_runs = run.agent_runs or {}
    capture_ids = agent_runs.get("capture") or []
    capture_summary = await _agent_summary(db, capture_ids[-1] if capture_ids else None)
    generation_summary = await _agent_summary(db, agent_runs.get("generation"))

    if run.status == "capturing" and capture_summary and capture_summary["status"] in {"failed", "cancelled"}:
        run.status = "failed"
        run.error = capture_summary.get("error_message") or "Capture agent failed"
    if run.status == "generating" and generation_summary:
        if generation_summary["status"] == "completed":
            gen_run = await db.get(AgentRun, agent_runs.get("generation"))
            script_ids = (gen_run.output_data or {}).get("script_ids") or []
            run.script_ids = script_ids
            run.status = "generated"
        elif generation_summary["status"] in {"failed", "cancelled"}:
            run.status = "failed"
            run.error = generation_summary.get("error_message") or "Generation agent failed"

    result = await db.execute(
        select(PocStateEvidence)
        .where(PocStateEvidence.grounding_run_id == run.id)
        .order_by(PocStateEvidence.sequence)
    )
    evidence = [
        {
            "id": row.id,
            "sequence": row.sequence,
            "state_fingerprint": row.state_fingerprint,
            "url": row.url,
            "title": row.title,
            "element_count": len(row.elements or []),
            "blockers": row.blockers or [],
            "produced_by_step": row.produced_by_step,
            "has_screenshot": bool(row.screenshot_path),
        }
        for row in result.scalars().all()
    ]

    scripts: list[dict] = []
    for script_id in run.script_ids or []:
        script = await db.get(AutomationScript, script_id)
        if script is not None:
            scripts.append({
                "id": script.id,
                "script_id": script.script_id,
                "status": script.status,
                "version": script.version,
                "framework": script.framework,
            })

    return {
        "evidence": evidence,
        "agent_runs": {"capture": capture_summary, "generation": generation_summary},
        "scripts": scripts,
        "step_trace": (run.config or {}).get("step_trace") or [],
    }
