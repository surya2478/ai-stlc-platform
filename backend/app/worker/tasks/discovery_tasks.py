"""UI-015 Live Discovery Session — dedicated Celery task (Phase 1 + 2 + 3).

Not routed through `AGENT_REGISTRY` (agent_tasks.py) — this holds one
`MCPSession` open across a step loop and checks `DiscoverySession.pending_command`
every iteration, the "DB is source of truth, worker polls it" pattern the
implementation plan calls for (same shape as agent_tasks.py's own
cancel-check and Grounded Automation PoC's reconciliation loop, just
checked every step instead of once at the end).

Pause: persist a checkpoint, set PAUSED, close the MCPSession, task exits —
tool access is inherently revoked because the subprocess is gone. Resume:
a NEW task run (dispatched by session_service via the API layer) reopens a
fresh MCPSession and continues from `current_step_index`. Emergency stop:
same as pause but skips graceful teardown.

Guided mode auto-walks the approved step list every iteration. Free mode
(Phase 2) has no step list — it idles, polling `pending_command` for a
user-submitted `perform_action` request, and self-pauses after
`_FREE_MODE_MAX_IDLE_ITERATIONS` of nothing happening so an abandoned Free
session doesn't hold a worker slot forever.

Agent-Driven mode (Phase 3) walks the same approved step list as Guided,
but never auto-executes: it idles, proposing the current step and waiting
for `approve_next_action` / `modify_next_action` / `skip_action`, with the
same idle self-pause. `take_manual_control` flips a `metadata_` flag this
loop checks every iteration — while set, an Agent-Driven session behaves
exactly like Free mode's `perform_action` idle-wait instead of walking the
step queue, until `return_control_to_agent` flips it back.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.database import AsyncSessionLocal
from app.models.discovery_session import DiscoverySession, DiscoverySessionEvent
from app.services.discovery import capture_service
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# Defense against a stuck/misbehaving MCP session never seeing a pending
# command — same idea as agent_tasks' AgentSpec.timeout_seconds ceiling.
_MAX_STEPS_PER_INVOCATION = 500

# Free mode idle polling: how long to wait between checks while nothing is
# happening, and how many such idle ticks to tolerate before self-pausing.
# 1.5s x 120 = 180s of inactivity — long enough to not punish someone
# reading the page, short enough to not tie up a worker slot indefinitely.
_FREE_MODE_POLL_SECONDS = 1.5
_FREE_MODE_MAX_IDLE_ITERATIONS = 120


async def _set_status(db, session: DiscoverySession, status: str) -> None:
    session.status = status
    await db.commit()


async def _run_capture_session(discovery_session_id: int) -> dict:
    async with AsyncSessionLocal() as db:
        session = await db.get(DiscoverySession, discovery_session_id)
        if session is None:
            return {"status": "not_found"}

        if session.status == "INITIALISING":
            await _set_status(db, session, "RECORDING")
        elif session.status == "RESUMING":
            await _set_status(db, session, "RECORDING")
        elif session.status != "RECORDING":
            logger.warning("discovery_tasks: session %s not in a runnable state (%s)", discovery_session_id, session.status)
            return {"status": session.status}

        try:
            mcp_session, output_dir, url = await capture_service.start_capture(db, session)
        except Exception as exc:  # real MCP/subprocess failure — not a guessed outcome
            session.status = "FAILED"
            session.failure_detail = str(exc)[:2000]
            await db.commit()
            logger.exception("discovery_tasks: failed to open MCP session for %s", discovery_session_id)
            return {"status": "FAILED", "error": str(exc)}

        if not url:
            session.status = "FAILED"
            session.failure_detail = f"No environment URL configured for '{session.environment}'"
            await db.commit()
            await capture_service.close_capture(mcp_session)
            return {"status": "FAILED"}

        is_free_mode = session.mode == "FREE_USER_ACTION"
        is_agent_driven = session.mode == "SUPERVISED_AGENT_DRIVEN"
        idle_iterations = 0

        async def _self_pause(reason: str) -> None:
            # Every other exit path from this loop records why it left and
            # clears `pending_command`. This one did neither, so a self-pause
            # showed up in the Activity tab as a session that entered
            # RESUMING and never arrived anywhere, while leaving the consumed
            # command in the row — a stale `resume` that reads like one still
            # waiting to be acted on.
            previous_state = session.status
            await capture_service.create_checkpoint(db, session, state_at_checkpoint="PAUSED")
            session.status = "PAUSED"
            session.pending_command = None
            db.add(DiscoverySessionEvent(
                session_id=session.id, project_id=session.project_id, actor_type="system",
                previous_state=previous_state, new_state="PAUSED",
                command="self_pause", reason=reason,
                occurred_at=datetime.now(timezone.utc),
            ))
            await db.commit()

        try:
            for _ in range(_MAX_STEPS_PER_INVOCATION):
                await db.refresh(session)
                command = (session.pending_command or {}).get("command")
                manual_control = is_agent_driven and bool((session.metadata_ or {}).get("manual_control"))

                if command == "pause":
                    await capture_service.create_checkpoint(db, session, state_at_checkpoint="PAUSED")
                    session.status = "PAUSED"
                    session.pending_command = None
                    await db.commit()
                    break

                if command in ("stop", "emergency_stop"):
                    resumable = command != "emergency_stop"
                    await capture_service.create_checkpoint(
                        db, session, state_at_checkpoint="STOPPED" if resumable else "EMERGENCY_STOPPED",
                        resumable=resumable,
                    )
                    session.status = "STOPPED" if resumable else "EMERGENCY_STOPPED"
                    if not resumable:
                        session.terminal_reason = session.terminal_reason or "Emergency stop"
                    session.pending_command = None
                    await db.commit()
                    break

                if command == "checkpoint":
                    await capture_service.create_checkpoint(db, session, state_at_checkpoint=session.status)
                    session.pending_command = None
                    idle_iterations = 0
                    await db.commit()
                    continue

                if command == "perform_action" and (is_free_mode or manual_control):
                    params = dict((session.pending_command or {}).get("params") or {})
                    # UI-019 rides on this same branch. `active_step_key` is
                    # its own concern, popped here so capture_service stays
                    # unaware of suites and step mapping.
                    active_step_key = params.pop("active_step_key", None)
                    try:
                        action = await capture_service.perform_free_action(
                            db, session, mcp_session, output_dir, **params
                        )
                        if session.recording_origin == "live_recorder":
                            from app.services.recorder import mapping as recorder_mapping

                            await recorder_mapping.auto_map_action(
                                db, session, action, step_key=active_step_key
                            )
                    except Exception as exc:
                        # A malformed/failed action request is the user's or
                        # the target page's problem, not a reason to fail the
                        # whole session — record it and keep the session
                        # RECORDING so they can simply try again.
                        logger.warning("discovery_tasks: free action failed for session %s: %s", session.id, exc)
                        db.add(DiscoverySessionEvent(
                            session_id=session.id, project_id=session.project_id, actor_type="system",
                            previous_state=session.status, new_state=session.status,
                            command="perform_action_failed", reason=str(exc)[:500],
                            occurred_at=datetime.now(timezone.utc),
                        ))
                    session.pending_command = None
                    idle_iterations = 0
                    await db.commit()
                    continue

                if is_agent_driven and not manual_control:
                    if command in ("approve_next_action", "modify_next_action", "skip_action"):
                        try:
                            if command == "approve_next_action":
                                await capture_service.capture_one_step(db, session, mcp_session, output_dir, actor="agent")
                            elif command == "modify_next_action":
                                params = dict((session.pending_command or {}).get("params") or {})
                                await capture_service.perform_modified_step(db, session, mcp_session, output_dir, **params)
                            else:
                                reason = (session.pending_command or {}).get("reason") or ""
                                await capture_service.skip_current_step(db, session, reason=reason)
                        except Exception as exc:
                            logger.warning(
                                "discovery_tasks: supervision command '%s' failed for session %s: %s",
                                command, session.id, exc,
                            )
                            db.add(DiscoverySessionEvent(
                                session_id=session.id, project_id=session.project_id, actor_type="system",
                                previous_state=session.status, new_state=session.status,
                                command=f"{command}_failed", reason=str(exc)[:500],
                                occurred_at=datetime.now(timezone.utc),
                            ))
                        session.pending_command = None
                        idle_iterations = 0
                        await db.commit()
                        continue

                    current_step = await capture_service.get_current_step(db, session)
                    if current_step is None:
                        # Every approved step already approved/modified/
                        # skipped — self-pause rather than auto-complete
                        # (Section 15 requires explicit user confirmation).
                        await _self_pause("Every approved step has been captured — stop the session to finish it.")
                        break
                    idle_iterations += 1
                    if idle_iterations >= _FREE_MODE_MAX_IDLE_ITERATIONS:
                        await _self_pause("No supervision command received for 3 minutes.")
                        break
                    await asyncio.sleep(_FREE_MODE_POLL_SECONDS)
                    continue

                if is_free_mode or manual_control:
                    # No step list to auto-walk (Free mode), or the step
                    # queue is deliberately bypassed (manual control) — wait
                    # for the user's next action request, self-pausing if
                    # they've gone quiet.
                    idle_iterations += 1
                    if idle_iterations >= _FREE_MODE_MAX_IDLE_ITERATIONS:
                        await _self_pause("No action recorded for 3 minutes.")
                        break
                    await asyncio.sleep(_FREE_MODE_POLL_SECONDS)
                    continue

                action = await capture_service.capture_one_step(db, session, mcp_session, output_dir)
                if action is None:
                    # Nothing left to capture (every approved step done). The
                    # task must not keep reporting RECORDING and then exit —
                    # that would strand the session in a state that claims a
                    # live task is still polling pending_command when none
                    # is. Instead self-pause: persist a checkpoint and drop
                    # to PAUSED, a real controllable state with no task
                    # attached, so Stop/Complete/Resume issued afterwards hit
                    # a fresh dispatch rather than a command nobody is
                    # listening for. Guided mode still never auto-completes
                    # (Section 15 requires explicit user confirmation) —
                    # PAUSED, not COMPLETED.
                    await _self_pause("Every approved step has been captured — stop the session to finish it.")
                    break
                await db.commit()
        finally:
            # Every exit path (paused, stopped, emergency-stopped, all-steps-
            # captured, or an unhandled error) closes the MCPSession — no
            # subprocess is ever left running past this task invocation.
            await capture_service.close_capture(mcp_session)

        await db.refresh(session)
        return {"status": session.status}


@celery_app.task(bind=True, name="discovery_tasks.run_capture_session", max_retries=0)
def run_capture_session(self, discovery_session_id: int):
    return asyncio.run(_run_capture_session(discovery_session_id))
