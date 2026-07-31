"""Execution control semantics — pause, resume, stop, cancel.

Contract Section 9 and Section 14.9. Three rules shape this module:

1. **Nothing is claimed before the backend acknowledges it.** A control request
   writes an `ExecutionRunCommand`, sets `pending_command`, and moves the run to
   a `*_REQUESTED` state. The orchestrator re-reads `pending_command` at its next
   dispatch boundary and only then does the run reach `PAUSED` or `STOPPED`. The
   UI renders the requested state as pending, not as done.

2. **A stale command is rejected, not applied.** `expectedRunVersion` is compared
   against the run's current `run_version`. If an operator's screen was showing a
   run that has since moved on, the pause they clicked was a decision about a
   different situation.

3. **Pause does not claim to suspend an in-flight browser command.** Section 9.1
   is explicit. The boundary is between test cases, so a pause takes effect after
   the current item completes — and the acknowledgement says so.

Rejected commands are kept with their reason. "The operator tried to cancel and
was refused" is audit-relevant.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import ExecutionRun
from app.models.execution_command_center import ExecutionRunCommand
from app.services.execution_command_center import events


class ExecutionControlError(HTTPException):
    """Same error shape as AutomationSuiteError, so the frontend has one contract."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


# Which run states each action may be requested from. Anything else is an
# INVALID_TRANSITION rather than a silently ignored click.
ALLOWED_FROM: dict[str, tuple[str, ...]] = {
    "PAUSE_AFTER_CURRENT": ("RUNNING", "QUEUED"),
    "RESUME": ("PAUSED",),
    # A queued-but-not-started run can still be stopped; there is simply nothing
    # in flight to finish first.
    "STOP_GRACEFULLY": ("RUNNING", "QUEUED", "PAUSED", "PAUSE_REQUESTED"),
    "CANCEL_NOW": ("RUNNING", "QUEUED", "PAUSED", "PAUSE_REQUESTED", "STOP_REQUESTED"),
    "EMERGENCY_STOP": ("RUNNING", "QUEUED", "PAUSED", "PAUSE_REQUESTED", "STOP_REQUESTED"),
}

# The state the run moves to the moment the request is accepted. Resume is the
# only one that takes effect immediately, because nothing is in flight to wait
# for — the orchestrator task has already exited.
REQUESTED_STATE: dict[str, str] = {
    "PAUSE_AFTER_CURRENT": "PAUSE_REQUESTED",
    "RESUME": "QUEUED",
    "STOP_GRACEFULLY": "STOP_REQUESTED",
    "CANCEL_NOW": "STOP_REQUESTED",
    "EMERGENCY_STOP": "STOP_REQUESTED",
}

# Section 9: a destructive action requires reason entry.
REASON_REQUIRED = ("STOP_GRACEFULLY", "CANCEL_NOW", "EMERGENCY_STOP")

# Requesting one of these means the orchestrator should stop dispatching as soon
# as it notices, rather than at a safe unit boundary.
IMMEDIATE_ACTIONS = ("CANCEL_NOW", "EMERGENCY_STOP")

ACKNOWLEDGEMENT: dict[str, str] = {
    "PAUSE_AFTER_CURRENT": (
        "Pause accepted. No further test cases will be dispatched. The test "
        "currently in flight will finish first — an in-progress browser command "
        "is not suspended."
    ),
    "RESUME": "Resume accepted. Dispatch continues from the next eligible test case.",
    "STOP_GRACEFULLY": (
        "Stop accepted. The current test case will complete, no new work will be "
        "dispatched, and available results and evidence will be finalized."
    ),
    "CANCEL_NOW": (
        "Cancel accepted. Runners and queued work are being terminated. Partial "
        "evidence already captured is retained."
    ),
    "EMERGENCY_STOP": "Emergency stop accepted.",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _command_key() -> str:
    return f"CMD-{uuid.uuid4().hex[:10].upper()}"


async def request_control(
    db: AsyncSession,
    run: ExecutionRun,
    *,
    action: str,
    actor_id: int,
    reason: str | None = None,
    expected_run_version: int | None = None,
) -> ExecutionRunCommand:
    """Validate, record and acknowledge a control request.

    Returns the persisted command. Does not commit; the endpoint owns the
    transaction so the command, the run state change and the event all land
    together.

    Raises `ExecutionControlError` for every refusal, so a rejection is a real
    HTTP error the UI can surface rather than a success with no effect.
    """
    if action not in ALLOWED_FROM:
        raise ExecutionControlError(400, "UNKNOWN_ACTION", f"Unknown control action '{action}'.")

    # Deferred in this slice. Refusing loudly beats a button that appears to work:
    # an emergency stop needs the project/global kill path that belongs to P2-S1
    # Operational Command Centre, and a "best-effort emergency stop" is precisely
    # the thing an operator must not have to guess about.
    if action == "EMERGENCY_STOP":
        raise ExecutionControlError(
            501,
            "EMERGENCY_STOP_UNAVAILABLE",
            "Emergency stop is not available yet: it requires the project-wide "
            "kill path delivered with P2-S1 Operational Command Centre. Use "
            "'Cancel now', which terminates this run's runners and queued work.",
        )

    if action in REASON_REQUIRED and not (reason or "").strip():
        raise ExecutionControlError(
            400,
            "REASON_REQUIRED",
            f"'{action}' is a destructive action and requires a reason.",
        )

    current = run.lifecycle_state
    if current is None:
        raise ExecutionControlError(
            409,
            "NOT_A_SUITE_RUN",
            "This execution run is not a suite run and has no controllable lifecycle.",
        )

    # Version check before the transition check: if the operator was looking at a
    # stale run, the transition they attempted is not the question.
    if expected_run_version is not None and expected_run_version != run.run_version:
        command = ExecutionRunCommand(
            execution_run_id=run.id,
            command_key=_command_key(),
            action=action,
            reason=reason,
            requested_by=actor_id,
            state="REJECTED",
            expected_run_version=expected_run_version,
            run_version_at_request=run.run_version,
            rejection_reason=(
                f"Run has moved on: expected version {expected_run_version}, "
                f"current version {run.run_version}."
            ),
            created_at=_now(),
        )
        db.add(command)
        await events.emit(
            db,
            run.id,
            event_type="control_rejected",
            message=f"{action} rejected — the run state had already changed.",
            payload={"action": action, "expected_run_version": expected_run_version},
        )
        raise ExecutionControlError(
            409,
            "RUN_VERSION_CONFLICT",
            f"This run has changed since the screen last updated (expected version "
            f"{expected_run_version}, now {run.run_version}). Review the current "
            f"state and try again.",
        )

    if current not in ALLOWED_FROM[action]:
        command = ExecutionRunCommand(
            execution_run_id=run.id,
            command_key=_command_key(),
            action=action,
            reason=reason,
            requested_by=actor_id,
            state="REJECTED",
            expected_run_version=expected_run_version,
            run_version_at_request=run.run_version,
            rejection_reason=f"'{action}' is not valid from state '{current}'.",
            created_at=_now(),
        )
        db.add(command)
        await events.emit(
            db,
            run.id,
            event_type="control_rejected",
            message=f"{action} rejected — not valid from {current}.",
            payload={"action": action, "from_state": current},
        )
        raise ExecutionControlError(
            409,
            "INVALID_TRANSITION",
            f"'{action}' cannot be requested while the run is {current}.",
        )

    resulting_state = REQUESTED_STATE[action]
    run.lifecycle_state = resulting_state
    run.run_version = (run.run_version or 0) + 1

    if action == "RESUME":
        # Clear the pause so the re-dispatched orchestrator does not immediately
        # pause again on the command it was resumed from.
        run.pending_command = None
        run.pending_command_reason = None
        run.pending_command_by = None
    else:
        run.pending_command = action
        run.pending_command_reason = reason
        run.pending_command_by = actor_id

    command = ExecutionRunCommand(
        execution_run_id=run.id,
        command_key=_command_key(),
        action=action,
        reason=reason,
        requested_by=actor_id,
        state="ACKNOWLEDGED",
        expected_run_version=expected_run_version,
        run_version_at_request=run.run_version,
        resulting_state=resulting_state,
        acknowledged_at=_now(),
        created_at=_now(),
    )
    db.add(command)

    await events.emit(
        db,
        run.id,
        event_type="control_requested",
        message=ACKNOWLEDGEMENT[action],
        payload={
            "action": action,
            "resulting_state": resulting_state,
            "reason": reason,
            "requested_by": actor_id,
        },
    )
    return command


def should_redispatch(action: str) -> bool:
    """Whether accepting this action means a new orchestrator task is needed.

    Only RESUME: pause and stop are noticed by the running task, but a paused run
    has no task left to notice anything.
    """
    return action == "RESUME"
