"""UI-046 execution control semantics (contract Section 9, Section 14.9).

Uses a fake session in the style of the other suite tests — the assertions here
are about transition legality, acknowledgement and optimistic concurrency, none
of which need a real database.
"""
from __future__ import annotations

import pytest

from app.services.execution_command_center import controls
from app.services.execution_command_center.controls import (
    ExecutionControlError,
    request_control,
)


class _FakeSession:
    """Collects added rows; `emit`'s sequence UPDATE is stubbed out."""

    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)

    async def execute(self, *_args, **_kwargs):
        class _R:
            def scalar_one(self_inner):
                return 1

        return _R()

    @property
    def commands(self):
        from app.models.execution_command_center import ExecutionRunCommand

        return [r for r in self.added if isinstance(r, ExecutionRunCommand)]

    @property
    def events(self):
        from app.models.execution_command_center import ExecutionRunEvent

        return [r for r in self.added if isinstance(r, ExecutionRunEvent)]


class _Run:
    def __init__(self, lifecycle_state="RUNNING", run_version=7):
        self.id = 42
        self.lifecycle_state = lifecycle_state
        self.run_version = run_version
        self.pending_command = None
        self.pending_command_reason = None
        self.pending_command_by = None


async def _request(run, action, **kwargs):
    db = _FakeSession()
    params = dict(action=action, actor_id=9)
    params.update(kwargs)
    command = await request_control(db, run, **params)
    return db, command


# ── Acknowledgement ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pause_is_acknowledged_and_recorded():
    run = _Run("RUNNING")
    db, command = await _request(run, "PAUSE_AFTER_CURRENT")
    assert command.state == "ACKNOWLEDGED"
    assert command.command_key.startswith("CMD-")
    assert command.resulting_state == "PAUSE_REQUESTED"
    assert command.acknowledged_at is not None


@pytest.mark.asyncio
async def test_pause_moves_to_requested_not_paused():
    """Section 14.9: the UI must not claim a control took effect early."""
    run = _Run("RUNNING")
    await _request(run, "PAUSE_AFTER_CURRENT")
    assert run.lifecycle_state == "PAUSE_REQUESTED"
    assert run.lifecycle_state != "PAUSED"


@pytest.mark.asyncio
async def test_pause_acknowledgement_does_not_overclaim_in_flight_suspension():
    """Section 9.1 is explicit that an in-flight command is not suspended."""
    run = _Run("RUNNING")
    db, _ = await _request(run, "PAUSE_AFTER_CURRENT")
    message = db.events[0].message
    assert "will finish first" in message
    assert "not suspended" in message


@pytest.mark.asyncio
async def test_accepted_control_sets_pending_command_for_the_orchestrator():
    run = _Run("RUNNING")
    await _request(run, "STOP_GRACEFULLY", reason="CRM maintenance window")
    assert run.pending_command == "STOP_GRACEFULLY"
    assert run.pending_command_reason == "CRM maintenance window"
    assert run.pending_command_by == 9


@pytest.mark.asyncio
async def test_accepted_control_bumps_run_version():
    run = _Run("RUNNING", run_version=7)
    await _request(run, "PAUSE_AFTER_CURRENT")
    assert run.run_version == 8


@pytest.mark.asyncio
async def test_resume_clears_the_pause_and_applies_immediately():
    run = _Run("PAUSED")
    run.pending_command = "PAUSE_AFTER_CURRENT"
    await _request(run, "RESUME")
    assert run.lifecycle_state == "QUEUED"
    assert run.pending_command is None
    assert controls.should_redispatch("RESUME") is True


@pytest.mark.asyncio
async def test_only_resume_triggers_redispatch():
    for action in ("PAUSE_AFTER_CURRENT", "STOP_GRACEFULLY", "CANCEL_NOW"):
        assert controls.should_redispatch(action) is False


# ── Reason enforcement ──────────────────────────────────────────────────────


@pytest.mark.parametrize("action", ["STOP_GRACEFULLY", "CANCEL_NOW"])
@pytest.mark.asyncio
async def test_destructive_action_requires_a_reason(action):
    with pytest.raises(ExecutionControlError) as exc:
        await _request(_Run("RUNNING"), action)
    assert exc.value.detail["code"] == "REASON_REQUIRED"


@pytest.mark.asyncio
async def test_whitespace_is_not_a_reason():
    with pytest.raises(ExecutionControlError) as exc:
        await _request(_Run("RUNNING"), "CANCEL_NOW", reason="   ")
    assert exc.value.detail["code"] == "REASON_REQUIRED"


@pytest.mark.asyncio
async def test_pause_does_not_require_a_reason():
    _, command = await _request(_Run("RUNNING"), "PAUSE_AFTER_CURRENT")
    assert command.state == "ACKNOWLEDGED"


# ── Optimistic concurrency ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stale_run_version_is_rejected():
    run = _Run("RUNNING", run_version=9)
    with pytest.raises(ExecutionControlError) as exc:
        await _request(run, "PAUSE_AFTER_CURRENT", expected_run_version=7)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "RUN_VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_stale_command_does_not_change_the_run():
    run = _Run("RUNNING", run_version=9)
    with pytest.raises(ExecutionControlError):
        await _request(run, "PAUSE_AFTER_CURRENT", expected_run_version=7)
    assert run.lifecycle_state == "RUNNING"
    assert run.pending_command is None
    assert run.run_version == 9


@pytest.mark.asyncio
async def test_rejected_command_is_still_persisted_for_audit():
    run = _Run("RUNNING", run_version=9)
    db = _FakeSession()
    with pytest.raises(ExecutionControlError):
        await request_control(
            db, run, action="PAUSE_AFTER_CURRENT", actor_id=9, expected_run_version=7
        )
    assert len(db.commands) == 1
    assert db.commands[0].state == "REJECTED"
    assert "expected version 7" in db.commands[0].rejection_reason


@pytest.mark.asyncio
async def test_matching_run_version_is_accepted():
    run = _Run("RUNNING", run_version=7)
    _, command = await _request(run, "PAUSE_AFTER_CURRENT", expected_run_version=7)
    assert command.state == "ACKNOWLEDGED"


@pytest.mark.asyncio
async def test_omitted_run_version_skips_the_check():
    """Not every caller tracks the version; omitting it is not a conflict."""
    _, command = await _request(_Run("RUNNING", run_version=99), "PAUSE_AFTER_CURRENT")
    assert command.state == "ACKNOWLEDGED"


# ── Transition legality ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "state,action",
    [
        ("PAUSED", "PAUSE_AFTER_CURRENT"),
        ("RUNNING", "RESUME"),
        ("COMPLETED", "PAUSE_AFTER_CURRENT"),
        ("CANCELLED", "CANCEL_NOW"),
        ("STOPPED", "STOP_GRACEFULLY"),
        ("BLOCKED_BEFORE_START", "PAUSE_AFTER_CURRENT"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_transitions_are_refused(state, action):
    with pytest.raises(ExecutionControlError) as exc:
        await _request(_Run(state), action, reason="because")
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "INVALID_TRANSITION"


@pytest.mark.asyncio
async def test_invalid_transition_is_persisted_for_audit():
    db = _FakeSession()
    with pytest.raises(ExecutionControlError):
        await request_control(db, _Run("COMPLETED"), action="RESUME", actor_id=9)
    assert db.commands[0].state == "REJECTED"
    assert "not valid from state 'COMPLETED'" in db.commands[0].rejection_reason


@pytest.mark.asyncio
async def test_cancel_is_allowed_from_a_pause_request():
    """An operator must be able to escalate without waiting for the pause."""
    _, command = await _request(_Run("PAUSE_REQUESTED"), "CANCEL_NOW", reason="urgent")
    assert command.state == "ACKNOWLEDGED"


@pytest.mark.asyncio
async def test_queued_run_can_be_stopped():
    _, command = await _request(_Run("QUEUED"), "STOP_GRACEFULLY", reason="wrong scope")
    assert command.state == "ACKNOWLEDGED"


# ── Refusals that are not transitions ───────────────────────────────────────


@pytest.mark.asyncio
async def test_emergency_stop_is_refused_with_its_reason():
    """Deferred in this slice — a button that appears to work would be worse."""
    with pytest.raises(ExecutionControlError) as exc:
        await _request(_Run("RUNNING"), "EMERGENCY_STOP", reason="fire")
    assert exc.value.status_code == 501
    assert exc.value.detail["code"] == "EMERGENCY_STOP_UNAVAILABLE"
    assert "Cancel now" in exc.value.detail["message"]


@pytest.mark.asyncio
async def test_unknown_action_is_refused():
    with pytest.raises(ExecutionControlError) as exc:
        await _request(_Run("RUNNING"), "DELETE_EVERYTHING")
    assert exc.value.detail["code"] == "UNKNOWN_ACTION"


@pytest.mark.asyncio
async def test_non_suite_run_has_no_controllable_lifecycle():
    run = _Run("RUNNING")
    run.lifecycle_state = None
    with pytest.raises(ExecutionControlError) as exc:
        await _request(run, "PAUSE_AFTER_CURRENT")
    assert exc.value.detail["code"] == "NOT_A_SUITE_RUN"


@pytest.mark.asyncio
async def test_every_control_action_has_an_acknowledgement_message():
    assert set(controls.ACKNOWLEDGEMENT) == set(controls.ALLOWED_FROM)
    assert set(controls.REQUESTED_STATE) == set(controls.ALLOWED_FROM)
