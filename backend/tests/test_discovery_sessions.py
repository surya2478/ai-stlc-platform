"""UI-015 Live Discovery Session (Phase 1 — Guided User Recording).

Follows the queued-response _FakeDB pattern from
test_automation_classification.py — this codebase has no real-DB test
fixture for service-layer unit tests; async service functions are exercised
against a fake session that replays queued execute()/get() responses in
call order. Migration up/down and full app/RBAC wiring were additionally
verified live against the real Postgres/Docker stack (see PR description),
not re-asserted here.
"""
from datetime import datetime, timedelta, timezone

import anyio
import pytest
from fastapi import HTTPException

from app.models.discovery_session import (
    DISCOVERY_SESSION_TRANSITIONS,
    DiscoveryAction,
    DiscoveryCapture,
    DiscoveryCheckpoint,
    DiscoverySession,
    DiscoverySessionEvent,
)
from app.models.locator_map import LocatorMapEntry
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.services.discovery import capture_service, resume_validation_service, session_service


class _Result:
    def __init__(self, value=None, values=None):
        self._value = value
        self._values = values if values is not None else []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


class _FakeDB:
    def __init__(self, responses=(), gets=None):
        self.responses = list(responses)
        self.gets = gets or {}
        self.added = []
        self.committed = 0

    async def execute(self, _stmt):
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _Result(values=value)
        return _Result(value=value)

    async def get(self, model, pk):
        return self.gets.get((model, pk))

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 1
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None

    async def commit(self):
        self.committed += 1


def _application(id_: int = 1, **overrides) -> ProjectApplication:
    data = {
        "id": id_, "project_id": 1, "key": "web", "name": "Web App", "is_active": True,
        "environment_urls": {"SIT": "https://sit.example.com"}, "is_default": True,
        "aliases": [], "lifecycle_status": "active",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return ProjectApplication(**data)


def _test_case(id_: int = 1, **overrides) -> TestCase:
    data = {
        "id": id_, "project_id": 1, "test_case_id": f"TC-{id_}", "title": "Login works",
        "priority": "High", "severity": "High", "status": "approved", "application_id": 1,
        "version": 1, "steps": [{"step_number": 1, "action": "Go to login"}],
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return TestCase(**data)


def _session(id_: int = 1, **overrides) -> DiscoverySession:
    data = {
        "id": id_, "project_id": 1, "application_id": 1, "environment": "SIT",
        "mode": "GUIDED_USER", "status": "NOT_STARTED", "framework": "playwright",
        "test_case_id": 1, "allowed_hosts": ["sit.example.com"], "current_step_index": 0,
        "correlation_id": None, "latest_checkpoint_id": None,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return DiscoverySession(**data)


# ── state-transition matrix (Section 9) ──────────────────────────────────

@pytest.mark.parametrize(
    "current_state,command,expect_target",
    [
        ("NOT_STARTED", "start", "INITIALISING"),
        ("RECORDING", "pause", "PAUSE_REQUESTED"),
        ("PAUSE_REQUESTED", "emergency_stop", "EMERGENCY_STOPPED"),
        ("PAUSED", "resume", "RESUMING"),
        ("RESUMING", "stop", "STOP_REQUESTED"),
        ("STOP_REQUESTED", "emergency_stop", "EMERGENCY_STOPPED"),
        ("STOPPED", "complete", "COMPLETED"),
        ("STOPPED", "cancel", "CANCELLED"),
    ],
)
def test_valid_transitions_apply(current_state, command, expect_target):
    async def _run():
        session = _session(status=current_state)
        db = _FakeDB(responses=[None])
        updated = await session_service.issue_command(
            db, session, command=command, user_id=7, idempotency_key=f"key-{command}",
        )
        assert updated.status == expect_target

    anyio.run(_run)


@pytest.mark.parametrize(
    "current_state,command",
    [
        ("NOT_STARTED", "pause"),          # can't pause before starting
        ("RECORDING", "resume"),           # not paused/stopped
        ("COMPLETED", "cancel"),           # terminal state, no further commands
        ("PAUSED", "start"),               # already past NOT_STARTED
        ("CANCELLED", "resume"),           # terminal state
    ],
)
def test_invalid_transitions_are_rejected_and_do_not_mutate_state(current_state, command):
    async def _run():
        session = _session(status=current_state)
        db = _FakeDB(responses=[None])
        with pytest.raises(HTTPException) as exc_info:
            await session_service.issue_command(db, session, command=command, user_id=7, idempotency_key="key-1")
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "INVALID_TRANSITION"
        assert session.status == current_state  # never mutated

    anyio.run(_run)


def test_stop_from_paused_finalizes_synchronously_without_a_live_task():
    """Regression test for a real bug found via live browser testing: a
    session that finished its capture loop settles into PAUSED with no live
    Celery task attached. Issuing 'stop' from PAUSED must not strand the
    session in STOP_REQUESTED forever waiting for a task that will never
    run — session_service must finalize it to STOPPED synchronously."""
    async def _run():
        session = _session(status="PAUSED")
        # idempotency lookup miss, then capture_service.create_checkpoint's
        # two execute() calls (last screen lookup, next sequence lookup).
        db = _FakeDB(responses=[None, None, []], gets={(ProjectApplication, 1): _application()})
        updated = await session_service.issue_command(
            db, session, command="stop", user_id=7, idempotency_key="stop-1",
        )
        assert updated.status == "STOPPED"
        assert updated.pending_command is None
        # A checkpoint was actually persisted, not skipped.
        assert any(isinstance(obj, DiscoveryCheckpoint) for obj in db.added)

    anyio.run(_run)


def test_every_terminal_state_has_no_outbound_transitions():
    for terminal in ("COMPLETED", "CANCELLED", "FAILED", "EMERGENCY_STOPPED"):
        assert DISCOVERY_SESSION_TRANSITIONS[terminal] == ()


# ── idempotent command issuance ──────────────────────────────────────────

def test_repeated_idempotency_key_replays_without_remutating_state():
    async def _run():
        session = _session(status="RECORDING")
        existing_event = DiscoverySessionEvent(
            id=1, session_id=1, project_id=1, actor_type="user", new_state="PAUSE_REQUESTED",
            command="pause", idempotency_key="dup-key", occurred_at=datetime.now(timezone.utc),
        )
        db = _FakeDB(responses=[existing_event])
        updated = await session_service.issue_command(
            db, session, command="pause", user_id=7, idempotency_key="dup-key",
        )
        # Session status is untouched by the replay — the first call already
        # applied it; a second call with the same key must not re-transition
        # a session that (in real usage) has since moved on.
        assert updated.status == "RECORDING"
        assert db.committed == 0

    anyio.run(_run)


# ── agent-driven-only commands refused in Phase 1 ────────────────────────

@pytest.mark.parametrize(
    "command", ["approve_next_action", "modify_next_action", "skip_action", "take_manual_control", "rollback"],
)
def test_supervision_commands_refused_outside_agent_driven_mode(command):
    async def _run():
        session = _session(status="RECORDING", mode="GUIDED_USER")
        db = _FakeDB(responses=[None])  # idempotency lookup miss
        with pytest.raises(HTTPException) as exc_info:
            await session_service.issue_command(db, session, command=command, user_id=7, idempotency_key="key-1")
        assert exc_info.value.status_code == 400
        assert "Supervised Agent-Driven" in exc_info.value.detail

    anyio.run(_run)


# ── checkpoint command (no state transition) ─────────────────────────────

def test_checkpoint_command_defers_to_live_task_when_recording():
    async def _run():
        session = _session(status="RECORDING")
        db = _FakeDB(responses=[None])
        updated = await session_service.issue_command(
            db, session, command="checkpoint", user_id=7, idempotency_key="ckpt-1",
        )
        assert updated.status == "RECORDING"
        assert updated.pending_command["command"] == "checkpoint"

    anyio.run(_run)


def test_checkpoint_command_from_paused_creates_checkpoint_synchronously():
    """PAUSED has no live task to notice a pending_command, so a checkpoint
    requested here must be created directly rather than deferred."""
    async def _run():
        session = _session(status="PAUSED")
        db = _FakeDB(responses=[None, None, []], gets={(ProjectApplication, 1): _application()})
        updated = await session_service.issue_command(
            db, session, command="checkpoint", user_id=7, idempotency_key="ckpt-1",
        )
        assert updated.status == "PAUSED"
        assert updated.pending_command is None
        assert any(isinstance(obj, DiscoveryCheckpoint) for obj in db.added)

    anyio.run(_run)


def test_checkpoint_command_rejected_outside_recording_or_paused():
    async def _run():
        session = _session(status="NOT_STARTED")
        db = _FakeDB(responses=[None])
        with pytest.raises(HTTPException) as exc_info:
            await session_service.issue_command(db, session, command="checkpoint", user_id=7, idempotency_key="ckpt-1")
        assert exc_info.value.status_code == 409

    anyio.run(_run)


# ── test-case eligibility (Section 3.1) ──────────────────────────────────

def test_eligibility_blocks_unapproved_test_case():
    tc = _test_case(status="pending_approval")
    blocker = session_service._eligibility_blocker(tc, application_id=1, mode="GUIDED_USER")
    assert blocker is not None and "not approved" in blocker


def test_eligibility_blocks_mismatched_application():
    tc = _test_case(application_id=99)
    blocker = session_service._eligibility_blocker(tc, application_id=1, mode="GUIDED_USER")
    assert blocker is not None and "different application" in blocker


def test_eligibility_blocks_unmapped_application():
    tc = _test_case(application_id=None)
    blocker = session_service._eligibility_blocker(tc, application_id=1, mode="GUIDED_USER")
    assert blocker is not None and "no Application Registry mapping" in blocker


def test_eligibility_passes_for_approved_mapped_test_case():
    tc = _test_case(status="approved", application_id=1)
    assert session_service._eligibility_blocker(tc, application_id=1, mode="GUIDED_USER") is None


def test_free_mode_has_no_test_case_eligibility_requirement():
    tc = _test_case(status="draft", application_id=None)
    assert session_service._eligibility_blocker(tc, application_id=1, mode="FREE_USER_ACTION") is None


def test_create_session_rejects_guided_mode_without_test_case():
    async def _run():
        db = _FakeDB(gets={(ProjectApplication, 1): _application()})
        with pytest.raises(HTTPException) as exc_info:
            await session_service.create_session(
                db, project_id=1, user_id=7, application_id=1, environment="SIT", mode="GUIDED_USER",
                test_case_id=None, purpose=None, browser_target=None, framework="playwright",
                auth_profile_reference=None, capture_options=None, evidence_policy=None,
                allowed_hosts=None, correlation_id=None,
            )
        assert exc_info.value.status_code == 400

    anyio.run(_run)


def test_create_session_rejects_free_mode_without_purpose():
    async def _run():
        db = _FakeDB(gets={(ProjectApplication, 1): _application()})
        with pytest.raises(HTTPException) as exc_info:
            await session_service.create_session(
                db, project_id=1, user_id=7, application_id=1, environment="SIT", mode="FREE_USER_ACTION",
                test_case_id=None, purpose="   ", browser_target=None, framework="playwright",
                auth_profile_reference=None, capture_options=None, evidence_policy=None,
                allowed_hosts=None, correlation_id=None,
            )
        assert exc_info.value.status_code == 400

    anyio.run(_run)


def test_create_session_rejects_unconfigured_environment():
    async def _run():
        db = _FakeDB(gets={(ProjectApplication, 1): _application(environment_urls={})})
        with pytest.raises(HTTPException) as exc_info:
            await session_service.create_session(
                db, project_id=1, user_id=7, application_id=1, environment="SIT", mode="FREE_USER_ACTION",
                test_case_id=None, purpose="Explore checkout", browser_target=None, framework="playwright",
                auth_profile_reference=None, capture_options=None, evidence_policy=None,
                allowed_hosts=None, correlation_id=None,
            )
        assert exc_info.value.status_code == 400

    anyio.run(_run)


def test_create_session_rejects_cross_project_application():
    async def _run():
        db = _FakeDB(gets={(ProjectApplication, 1): _application(project_id=999)})
        with pytest.raises(HTTPException) as exc_info:
            await session_service.create_session(
                db, project_id=1, user_id=7, application_id=1, environment="SIT", mode="FREE_USER_ACTION",
                test_case_id=None, purpose="Explore checkout", browser_target=None, framework="playwright",
                auth_profile_reference=None, capture_options=None, evidence_policy=None,
                allowed_hosts=None, correlation_id=None,
            )
        assert exc_info.value.status_code == 404

    anyio.run(_run)


# ── resume-state classification (Section 12) ─────────────────────────────

def test_resume_state_unknown_with_no_checkpoint():
    validation = resume_validation_service.classify_resume_state(_session(), None)
    assert validation.classification == "UNKNOWN"
    assert "restart_step" in validation.allowed_recovery_options


def test_resume_state_session_expired_when_checkpoint_not_resumable():
    checkpoint = DiscoveryCheckpoint(
        id=1, session_id=1, project_id=1, sequence=0, state_at_checkpoint="EMERGENCY_STOPPED",
        resumable=False, created_by_actor="system", created_at=datetime.now(timezone.utc),
    )
    validation = resume_validation_service.classify_resume_state(_session(), checkpoint)
    assert validation.classification == "SESSION_EXPIRED"


def test_resume_state_unchanged_for_recent_resumable_checkpoint():
    checkpoint = DiscoveryCheckpoint(
        id=1, session_id=1, project_id=1, sequence=0, state_at_checkpoint="PAUSED",
        resumable=True, created_by_actor="system", created_at=datetime.now(timezone.utc),
    )
    validation = resume_validation_service.classify_resume_state(_session(), checkpoint)
    assert validation.classification == "UNCHANGED"
    assert validation.allowed_recovery_options == ("continue", "restore_checkpoint", "stop_and_save")


def test_resume_state_unknown_when_checkpoint_stale():
    stale = datetime.now(timezone.utc) - timedelta(hours=2)
    checkpoint = DiscoveryCheckpoint(
        id=1, session_id=1, project_id=1, sequence=0, state_at_checkpoint="PAUSED",
        resumable=True, created_by_actor="system", created_at=stale,
    )
    validation = resume_validation_service.classify_resume_state(_session(), checkpoint)
    assert validation.classification == "UNKNOWN"


def test_resume_state_expired_past_explicit_expiry():
    checkpoint = DiscoveryCheckpoint(
        id=1, session_id=1, project_id=1, sequence=0, state_at_checkpoint="PAUSED",
        resumable=True, created_by_actor="system", created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    validation = resume_validation_service.classify_resume_state(_session(), checkpoint)
    assert validation.classification == "SESSION_EXPIRED"


# ── Free User-Action Recording (Phase 2) ─────────────────────────────────

def test_record_free_action_rejected_outside_free_mode():
    async def _run():
        session = _session(mode="GUIDED_USER", status="RECORDING")
        db = _FakeDB()
        with pytest.raises(HTTPException) as exc_info:
            await session_service.record_free_action(
                db, session, user_id=7, idempotency_key="k1", action_family="navigate", url="https://sit.example.com",
            )
        assert exc_info.value.status_code == 400

    anyio.run(_run)


def test_record_free_action_rejected_in_agent_driven_mode_without_manual_control():
    async def _run():
        session = _session(mode="SUPERVISED_AGENT_DRIVEN", status="RECORDING", metadata_={})
        db = _FakeDB()
        with pytest.raises(HTTPException) as exc_info:
            await session_service.record_free_action(
                db, session, user_id=7, idempotency_key="k1", action_family="navigate", url="https://sit.example.com",
            )
        assert exc_info.value.status_code == 400

    anyio.run(_run)


def test_record_free_action_allowed_in_agent_driven_mode_with_manual_control():
    """Regression coverage for a real gap caught before it shipped: the
    worker loop already treats manual-control Agent-Driven sessions like
    Free mode for perform_action, but record_free_action's mode gate had
    not been widened to match — it would have rejected the very requests
    the loop was built to handle."""
    async def _run():
        session = _session(mode="SUPERVISED_AGENT_DRIVEN", status="RECORDING", metadata_={"manual_control": True})
        db = _FakeDB()
        updated = await session_service.record_free_action(
            db, session, user_id=7, idempotency_key="k1", action_family="navigate", url="https://sit.example.com",
        )
        assert updated.pending_command["command"] == "perform_action"

    anyio.run(_run)


def test_record_free_action_rejected_when_not_recording():
    async def _run():
        session = _session(mode="FREE_USER_ACTION", status="PAUSED")
        db = _FakeDB()
        with pytest.raises(HTTPException) as exc_info:
            await session_service.record_free_action(
                db, session, user_id=7, idempotency_key="k1", action_family="navigate", url="https://sit.example.com",
            )
        assert exc_info.value.status_code == 409

    anyio.run(_run)


def test_record_free_action_queues_pending_command():
    async def _run():
        session = _session(mode="FREE_USER_ACTION", status="RECORDING")
        db = _FakeDB()
        updated = await session_service.record_free_action(
            db, session, user_id=7, idempotency_key="k1", action_family="click", target_ref="ref-3",
            target_semantic="Submit button",
        )
        assert updated.pending_command["command"] == "perform_action"
        assert updated.pending_command["params"]["action_family"] == "click"
        assert updated.pending_command["params"]["target_ref"] == "ref-3"

    anyio.run(_run)


def test_record_free_action_idempotent_replay_does_not_requeue():
    async def _run():
        session = _session(
            mode="FREE_USER_ACTION", status="RECORDING",
            pending_command={"command": "perform_action", "idempotency_key": "dup-key", "params": {"action_family": "read"}},
        )
        db = _FakeDB()
        updated = await session_service.record_free_action(
            db, session, user_id=7, idempotency_key="dup-key", action_family="navigate", url="https://sit.example.com",
        )
        # Unchanged — the already-queued action, not a second one, wins.
        assert updated.pending_command["params"]["action_family"] == "read"
        assert db.committed == 0

    anyio.run(_run)


class _FakeMCPSession:
    """Minimal stand-in for MCPSession — records what was called instead of
    spawning a real @playwright/mcp subprocess. Defaults are backward
    compatible with every pre-Phase-4 test (plain snapshot text with no
    parseable elements, so locator ranking finds nothing and no test needed
    to change); Phase 4 tests pass `snapshot_text`/`evaluate_responses` to
    exercise the new ranking/console/network paths explicitly."""

    def __init__(
        self, snapshot_text="fake accessibility snapshot", evaluate_responses=None,
        console_text="### Result\nTotal messages: 0 (Errors: 0, Warnings: 0)\n",
        network_text="### Result\n\nNote: 0 static requests not shown.",
    ):
        self.calls: list[tuple] = []
        self._snapshot_text = snapshot_text
        self._evaluate_responses = list(evaluate_responses or [])
        self._console_text = console_text
        self._network_text = network_text

    async def navigate(self, url):
        self.calls.append(("navigate", url))

    async def click(self, *, element, target):
        self.calls.append(("click", element, target))

    async def type_text(self, *, element, target, text, submit=False):
        self.calls.append(("type_text", element, target, text))

    async def snapshot(self):
        return self._snapshot_text

    async def console_messages(self, *, level="info"):
        self.calls.append(("console_messages", level))
        return self._console_text

    async def network_requests(self, *, static=False):
        self.calls.append(("network_requests", static))
        return self._network_text

    async def evaluate(self, *, function, element=None, target=None):
        self.calls.append(("evaluate", function, element, target))
        if self._evaluate_responses:
            response = self._evaluate_responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return "### Result\nnull\n### Ran Playwright code\n```js\n```"

    async def call(self, tool_name, arguments):
        # perform_free_action's screenshot helper calls this, then looks
        # for the file at Path.cwd()/<filename> — it won't exist in a unit
        # test, so _capture_screenshot returns None and no DiscoveryCapture
        # is created. That's real, correct behavior, not a test shortcut.
        self.calls.append((tool_name, arguments))
        return ""


def _free_session(**overrides) -> DiscoverySession:
    return _session(mode="FREE_USER_ACTION", status="RECORDING", test_case_id=None, **overrides)


def test_perform_free_action_navigate():
    async def _run():
        session = _free_session()
        mcp = _FakeMCPSession()
        db = _FakeDB(responses=[None])  # next-sequence lookup: no prior actions
        action = await capture_service.perform_free_action(
            db, session, mcp, output_dir=None, action_family="navigate", url="https://sit.example.com/checkout",
        )
        assert ("navigate", "https://sit.example.com/checkout") in mcp.calls
        assert action.action_family == "navigate"
        assert action.actor == "user"
        assert action.input_binding == {"url": "https://sit.example.com/checkout"}
        assert action.sequence == 0

    anyio.run(_run)


def test_perform_free_action_click_requires_target_ref():
    async def _run():
        session = _free_session()
        mcp = _FakeMCPSession()
        db = _FakeDB(responses=[None])
        with pytest.raises(capture_service.FreeActionError):
            await capture_service.perform_free_action(db, session, mcp, output_dir=None, action_family="click")

    anyio.run(_run)


def test_perform_free_action_masks_sensitive_field_by_name():
    async def _run():
        session = _free_session()
        mcp = _FakeMCPSession()
        db = _FakeDB(responses=[None])
        action = await capture_service.perform_free_action(
            db, session, mcp, output_dir=None, action_family="input",
            target_ref="ref-9", target_semantic="Password field", input_text="hunter2",
        )
        # The real browser still receives the real value...
        assert ("type_text", "Password field", "ref-9", "hunter2") in mcp.calls
        # ...but nothing sensitive is ever persisted.
        assert action.input_binding["text"] == "[REDACTED - sensitive field]"

    anyio.run(_run)


def test_perform_free_action_persists_non_sensitive_input_text():
    async def _run():
        session = _free_session()
        mcp = _FakeMCPSession()
        db = _FakeDB(responses=[None])
        action = await capture_service.perform_free_action(
            db, session, mcp, output_dir=None, action_family="input",
            target_ref="ref-4", target_semantic="Promo code field", input_text="SAVE10",
        )
        assert action.input_binding["text"] == "SAVE10"

    anyio.run(_run)


def test_perform_free_action_rejects_unknown_family():
    async def _run():
        session = _free_session()
        mcp = _FakeMCPSession()
        db = _FakeDB(responses=[None])
        with pytest.raises(capture_service.FreeActionError):
            await capture_service.perform_free_action(db, session, mcp, output_dir=None, action_family="teleport")

    anyio.run(_run)


def test_perform_free_action_sequence_increments_from_existing_actions():
    async def _run():
        session = _free_session()
        mcp = _FakeMCPSession()
        db = _FakeDB(responses=[4])  # highest existing sequence is 4
        action = await capture_service.perform_free_action(
            db, session, mcp, output_dir=None, action_family="read", target_semantic="Observed cart total",
        )
        assert action.sequence == 5

    anyio.run(_run)


def test_perform_free_action_sequence_increments_past_zero():
    """Regression test for a real bug found via live browser testing:
    `(existing_max_sequence or -1) + 1` silently reused sequence 0 for
    every action once the first one existed, because `0 or -1` evaluates to
    -1 in Python (0 is falsy) — a second real action got persisted with the
    same sequence as the first instead of sequence 1."""
    async def _run():
        session = _free_session()
        mcp = _FakeMCPSession()
        db = _FakeDB(responses=[0])  # highest existing sequence is a real 0, not "no rows"
        action = await capture_service.perform_free_action(
            db, session, mcp, output_dir=None, action_family="read", target_semantic="Second observation",
        )
        assert action.sequence == 1

    anyio.run(_run)


# ── Supervised Agent-Driven Recording (Phase 3) ──────────────────────────

def _agent_session(**overrides) -> DiscoverySession:
    defaults = {"mode": "SUPERVISED_AGENT_DRIVEN", "status": "RECORDING", "test_case_id": 1}
    defaults.update(overrides)
    return _session(**defaults)


@pytest.mark.parametrize("command", ["approve_next_action", "modify_next_action", "skip_action"])
def test_supervision_step_commands_queue_pending_command(command):
    async def _run():
        session = _agent_session()
        db = _FakeDB(responses=[None])
        kwargs = {"reason": "not applicable here"} if command == "skip_action" else {}
        params = {"action_family": "click", "target_ref": "ref-1"} if command == "modify_next_action" else None
        updated = await session_service.issue_command(
            db, session, command=command, user_id=7, idempotency_key="k1", params=params, **kwargs,
        )
        assert updated.pending_command["command"] == command
        assert updated.status == "RECORDING"  # these never transition session status

    anyio.run(_run)


@pytest.mark.parametrize("command", ["approve_next_action", "modify_next_action", "skip_action"])
def test_supervision_step_commands_rejected_when_not_recording(command):
    async def _run():
        session = _agent_session(status="PAUSED")
        db = _FakeDB(responses=[None])
        kwargs = {"reason": "n/a"} if command == "skip_action" else {}
        with pytest.raises(HTTPException) as exc_info:
            await session_service.issue_command(db, session, command=command, user_id=7, idempotency_key="k1", **kwargs)
        assert exc_info.value.status_code == 409

    anyio.run(_run)


def test_skip_action_requires_a_reason():
    async def _run():
        session = _agent_session()
        db = _FakeDB(responses=[None])
        with pytest.raises(HTTPException) as exc_info:
            await session_service.issue_command(db, session, command="skip_action", user_id=7, idempotency_key="k1")
        assert exc_info.value.status_code == 400

    anyio.run(_run)


def test_modify_next_action_requires_action_family():
    async def _run():
        session = _agent_session()
        db = _FakeDB(responses=[None])
        with pytest.raises(HTTPException) as exc_info:
            await session_service.issue_command(
                db, session, command="modify_next_action", user_id=7, idempotency_key="k1", params={},
            )
        assert exc_info.value.status_code == 400

    anyio.run(_run)


def test_take_manual_control_sets_metadata_flag():
    async def _run():
        session = _agent_session()
        db = _FakeDB(responses=[None])
        updated = await session_service.issue_command(
            db, session, command="take_manual_control", user_id=7, idempotency_key="k1",
        )
        assert updated.metadata_["manual_control"] is True

    anyio.run(_run)


def test_return_control_to_agent_clears_metadata_flag():
    async def _run():
        session = _agent_session(metadata_={"manual_control": True})
        db = _FakeDB(responses=[None])
        updated = await session_service.issue_command(
            db, session, command="return_control_to_agent", user_id=7, idempotency_key="k1",
        )
        assert updated.metadata_["manual_control"] is False

    anyio.run(_run)


def test_rollback_requires_paused_status():
    async def _run():
        session = _agent_session(status="RECORDING")
        db = _FakeDB(responses=[None])
        with pytest.raises(HTTPException) as exc_info:
            await session_service.issue_command(
                db, session, command="rollback", user_id=7, idempotency_key="k1", reason="bad path",
                params={"checkpoint_id": 1},
            )
        assert exc_info.value.status_code == 409

    anyio.run(_run)


def test_rollback_requires_reason():
    async def _run():
        session = _agent_session(status="PAUSED")
        db = _FakeDB(responses=[None])
        with pytest.raises(HTTPException) as exc_info:
            await session_service.issue_command(
                db, session, command="rollback", user_id=7, idempotency_key="k1", params={"checkpoint_id": 1},
            )
        assert exc_info.value.status_code == 400

    anyio.run(_run)


def test_rollback_requires_checkpoint_id():
    async def _run():
        session = _agent_session(status="PAUSED")
        db = _FakeDB(responses=[None])
        with pytest.raises(HTTPException) as exc_info:
            await session_service.issue_command(
                db, session, command="rollback", user_id=7, idempotency_key="k1", reason="bad path", params={},
            )
        assert exc_info.value.status_code == 400

    anyio.run(_run)


def test_rollback_marks_later_actions_rolled_back_and_resets_step_index():
    async def _run():
        session = _agent_session(status="PAUSED", current_step_index=3)
        checkpoint = DiscoveryCheckpoint(
            id=9, session_id=1, project_id=1, sequence=0, state_at_checkpoint="PAUSED",
            action_position=1, resumable=True, created_by_actor="system",
        )
        later_action = DiscoveryAction(
            id=5, session_id=1, project_id=1, sequence=2, actor="agent", action_family="read",
            occurred_at=datetime.now(timezone.utc), inclusion_state="included", correction_history=[],
        )
        db = _FakeDB(
            responses=[None, [later_action]],
            gets={(DiscoveryCheckpoint, 1): checkpoint},
        )
        updated = await session_service.issue_command(
            db, session, command="rollback", user_id=7, idempotency_key="k1", reason="Data changed mid-run",
            params={"checkpoint_id": 1},
        )
        assert updated.current_step_index == 1
        assert later_action.inclusion_state == "rolled_back"
        assert later_action.correction_history[-1]["reason"] == "Data changed mid-run"

    anyio.run(_run)


def test_get_current_step_returns_none_when_no_test_case():
    async def _run():
        session = _agent_session(test_case_id=None)
        db = _FakeDB(gets={(TestCase, None): None})
        step = await capture_service.get_current_step(db, session)
        assert step is None

    anyio.run(_run)


def test_get_current_step_returns_text_and_ref():
    async def _run():
        session = _agent_session(current_step_index=0)
        tc = _test_case(steps=[{"step_number": 1, "action": "Click login"}])
        db = _FakeDB(gets={(TestCase, 1): tc})
        step = await capture_service.get_current_step(db, session)
        assert step == {"text": "Click login", "step_ref": "1"}

    anyio.run(_run)


def test_skip_current_step_records_skip_without_browser_call():
    async def _run():
        session = _agent_session(current_step_index=0)
        tc = _test_case(steps=[{"step_number": 1, "action": "Click login"}])
        db = _FakeDB(gets={(TestCase, 1): tc})
        action = await capture_service.skip_current_step(db, session, reason="Login button not present in this build")
        assert action.inclusion_state == "skipped"
        assert action.issue_note == "Login button not present in this build"
        assert session.current_step_index == 1
        # No MCP interaction, no evidence — nothing happened in the browser
        # (the model's JSONB default=list only applies on a real flush, not
        # this fake one, so accept the unset None too).
        assert not action.evidence_refs

    anyio.run(_run)


def test_skip_current_step_returns_none_when_exhausted():
    async def _run():
        session = _agent_session(current_step_index=1)
        tc = _test_case(steps=[{"step_number": 1, "action": "Click login"}])
        db = _FakeDB(gets={(TestCase, 1): tc})
        action = await capture_service.skip_current_step(db, session, reason="n/a")
        assert action is None

    anyio.run(_run)


def test_perform_modified_step_marks_corrected_and_links_to_step():
    async def _run():
        session = _agent_session(current_step_index=0)
        tc = _test_case(steps=[{"step_number": 1, "action": "Click the sign-in link"}])
        mcp = _FakeMCPSession()
        db = _FakeDB(gets={(TestCase, 1): tc})
        action = await capture_service.perform_modified_step(
            db, session, mcp, output_dir=None, action_family="click", target_ref="ref-42",
            target_semantic="Alternate sign-in button",
        )
        assert ("click", "Alternate sign-in button", "ref-42") in mcp.calls
        assert action.inclusion_state == "corrected"
        assert action.test_step_ref == "1"
        assert session.current_step_index == 1

    anyio.run(_run)


def test_perform_modified_step_returns_none_when_exhausted():
    async def _run():
        session = _agent_session(current_step_index=1)
        tc = _test_case(steps=[{"step_number": 1, "action": "Click login"}])
        mcp = _FakeMCPSession()
        db = _FakeDB(gets={(TestCase, 1): tc})
        action = await capture_service.perform_modified_step(db, session, mcp, output_dir=None, action_family="read")
        assert action is None

    anyio.run(_run)


# ── Phase 4: ranked fallback locators + network/console capture ─────────

_SNAPSHOT_ONE_BUTTON = (
    "### Page\n- Page URL: https://sit.example.com/checkout\n- Page Title: Checkout\n"
    "### Snapshot\n```yaml\n- generic [ref=e1]:\n  - button \"Save\" [ref=e2]\n```\n"
)
_NULL_ATTRS_RESULT = (
    '### Result\n{"id": null, "testidAttr": null, "testid": null, "ariaLabel": null, '
    '"placeholder": null, "text": "", "tag": "button", "className": null}\n'
    "### Ran Playwright code\n```js\n```"
)


def test_perform_free_action_click_sets_locator_evidence_and_upserts_locator_map(tmp_path):
    async def _run():
        session = _free_session()
        mcp = _FakeMCPSession(snapshot_text=_SNAPSHOT_ONE_BUTTON, evaluate_responses=[_NULL_ATTRS_RESULT])
        db = _FakeDB(responses=[None, None])  # next-sequence lookup, then locator_map lookup (no existing row)
        action = await capture_service.perform_free_action(
            db, session, mcp, output_dir=tmp_path, action_family="click",
            target_ref="e2", target_semantic="Save",
        )
        assert action.locator_confidence == 90
        assert action.locator_evidence["candidates"][0]["strategy"] == "role"

        upserted = next(o for o in db.added if isinstance(o, LocatorMapEntry))
        assert upserted.application_id == session.application_id
        assert upserted.recommended_strategy == "role"
        assert upserted.page == "https://sit.example.com/checkout"

        capture_types = sorted(c.capture_type for c in db.added if isinstance(c, DiscoveryCapture))
        assert capture_types == ["console_log", "network_log"]
        assert len(action.evidence_refs) == 2
        assert (tmp_path / "free_0_console.txt").exists()
        assert (tmp_path / "free_0_network.txt").exists()

    anyio.run(_run)


def test_perform_free_action_read_never_gets_locator_ranking(tmp_path):
    async def _run():
        session = _free_session()
        mcp = _FakeMCPSession(snapshot_text=_SNAPSHOT_ONE_BUTTON)
        db = _FakeDB(responses=[None])
        action = await capture_service.perform_free_action(
            db, session, mcp, output_dir=tmp_path, action_family="read", target_semantic="Observed totals",
        )
        assert action.locator_evidence is None
        assert action.locator_confidence is None
        # "read" never changed the page — no console/network capture either.
        assert not any(isinstance(o, DiscoveryCapture) for o in db.added)

    anyio.run(_run)


def test_perform_free_action_navigate_skips_capture_when_disabled(tmp_path):
    async def _run():
        session = _free_session(capture_options={"console_capture": False, "network_capture": False})
        mcp = _FakeMCPSession()
        db = _FakeDB(responses=[None])
        action = await capture_service.perform_free_action(
            db, session, mcp, output_dir=tmp_path, action_family="navigate", url="https://sit.example.com/checkout",
        )
        assert not action.evidence_refs
        assert not any(isinstance(o, DiscoveryCapture) for o in db.added)

    anyio.run(_run)


def test_perform_modified_step_click_shares_locator_ranking_path(tmp_path):
    async def _run():
        session = _agent_session(current_step_index=0)
        tc = _test_case(steps=[{"step_number": 1, "action": "Click save"}])
        mcp = _FakeMCPSession(snapshot_text=_SNAPSHOT_ONE_BUTTON, evaluate_responses=[_NULL_ATTRS_RESULT])
        db = _FakeDB(gets={(TestCase, 1): tc}, responses=[None])  # locator_map lookup only
        action = await capture_service.perform_modified_step(
            db, session, mcp, output_dir=tmp_path, action_family="click",
            target_ref="e2", target_semantic="Save",
        )
        assert action.locator_evidence["candidates"][0]["strategy"] == "role"
        assert action.locator_confidence == 90

    anyio.run(_run)


# ── worker self-pause (step plan exhausted / idle) ───────────────────────

def test_self_pause_records_its_transition_and_clears_pending_command(tmp_path, monkeypatch):
    """A step-driven session that runs out of approved steps drops to PAUSED
    without auto-completing (Section 15). It must still leave the audit trail
    every other exit path leaves: an event naming why it stopped, and no
    stale `pending_command` claiming a command is still waiting to be read."""
    from app.worker.tasks import discovery_tasks

    async def _run():
        session = _agent_session(
            id_=27, status="RESUMING", current_step_index=4,
            pending_command={"command": "resume", "idempotency_key": "k-1"},
        )
        db = _FakeDB(gets={(DiscoverySession, 27): session})

        monkeypatch.setattr(discovery_tasks, "AsyncSessionLocal", _fake_session_factory(db))
        monkeypatch.setattr(
            discovery_tasks.capture_service, "start_capture",
            _async_return((_FakeMCPSession(), tmp_path, "https://sit.example.com")),
        )
        monkeypatch.setattr(discovery_tasks.capture_service, "close_capture", _async_return(None))
        monkeypatch.setattr(discovery_tasks.capture_service, "create_checkpoint", _async_return(None))
        # Every approved step already consumed.
        monkeypatch.setattr(discovery_tasks.capture_service, "get_current_step", _async_return(None))

        result = await discovery_tasks._run_capture_session(27)

        assert result["status"] == "PAUSED"
        assert session.status == "PAUSED"
        assert session.pending_command is None
        events = [o for o in db.added if isinstance(o, DiscoverySessionEvent)]
        assert len(events) == 1
        assert events[0].new_state == "PAUSED"
        assert events[0].previous_state == "RECORDING"
        assert events[0].command == "self_pause"
        assert "stop the session" in events[0].reason.lower()

    anyio.run(_run)


def _async_return(value):
    async def _call(*_args, **_kwargs):
        return value

    return _call


def _fake_session_factory(db):
    """`async with AsyncSessionLocal() as db` — hand the task the _FakeDB
    instead of opening a real connection."""
    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return db

        async def __aexit__(self, *_exc):
            return False

    return _Factory()
