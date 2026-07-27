"""UI-019 write-side guards — the rules that must not be bypassable.

Three classes of rule live here:

- *Never guess*: an action with no active step is left unmapped rather than
  attached to a plausible one, and auto-mapping records no confidence score
  because a user's choice is a fact, not an inference.
- *Reasons are mandatory* where the contract says a decision must be
  accountable: skipping a step, excluding an action from the IR, discarding a
  recording, transitioning applications.
- *Secrets never gain a value* (Section 18), enforced in the service as well
  as by the database constraint.
"""
from types import SimpleNamespace

import pytest

from app.services.recorder import bindings, lifecycle, mapping, session_service
from app.services.recorder.errors import RecorderError


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


class _ExecuteResult:
    def __init__(self, value=None, values=None):
        self._value = value
        self._values = values or []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return _ScalarsResult(self._values)


class _FakeDB:
    """Responds to `execute` from a queue and to `get` from a type->object map."""

    def __init__(self, *responses, gets=None):
        self.responses = list(responses)
        self.gets = gets or {}
        self.added = []
        self.deleted = []
        self.committed = False

    async def execute(self, _stmt):
        if not self.responses:
            return _ExecuteResult()
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _ExecuteResult(values=value)
        return _ExecuteResult(value=value)

    async def get(self, model, obj_id):
        return self.gets.get(model)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None

    async def commit(self):
        self.committed = True

    async def delete(self, obj):
        self.deleted.append(obj)


def _session(**overrides):
    data = {
        "id": 1,
        "project_id": 1,
        "status": "RECORDING",
        "correlation_id": None,
        "suite_id": 4,
        "test_case_id": 8,
        "recording_mode": "GUIDED_TEST_CASE",
        "environment": "QA",
        "ir_status": "NOT_GENERATED",
        "terminal_at": None,
        "terminal_reason": None,
        "pending_command": None,
        "recording_version": 1,
        "allowed_hosts": [],
        "framework": "playwright",
        "application_id": 1,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


# ── Auto-mapping never guesses (Section 15) ──────────────────────────────────


@pytest.mark.anyio
async def test_auto_map_does_nothing_without_an_active_step():
    db = _FakeDB()
    action = SimpleNamespace(id=5, test_step_ref=None)

    result = await mapping.auto_map_action(db, _session(), action, step_key=None)

    assert result is None
    assert db.added == []
    assert action.test_step_ref is None


@pytest.mark.anyio
async def test_auto_map_records_no_confidence_score():
    """The user chose the active step; scoring their choice would misrepresent it."""
    db = _FakeDB(None)
    action = SimpleNamespace(id=5, test_step_ref=None)

    result = await mapping.auto_map_action(db, _session(), action, step_key="2")

    assert result.step_key == "2"
    assert result.mapping_source == "active_step"
    assert result.confidence is None
    assert action.test_step_ref == "2"


@pytest.mark.anyio
async def test_auto_map_does_not_duplicate_an_existing_mapping():
    existing = SimpleNamespace(action_id=5, step_key="1")
    db = _FakeDB(existing)
    action = SimpleNamespace(id=5, test_step_ref="1")

    assert await mapping.auto_map_action(db, _session(), action, step_key="2") is None
    assert db.added == []


# ── Accountable decisions ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_skipping_a_step_requires_a_reason():
    with pytest.raises(RecorderError) as exc:
        await mapping.set_step_status(
            _FakeDB(), _session(), step_key="1", status="SKIPPED", reason="  ", user_id=1
        )
    assert exc.value.detail["code"] == "SKIP_REASON_REQUIRED"


@pytest.mark.anyio
async def test_active_is_not_settable_through_the_status_endpoint():
    """ACTIVE is exclusive within a session, so it has its own path."""
    with pytest.raises(RecorderError) as exc:
        await mapping.set_step_status(
            _FakeDB(), _session(), step_key="1", status="ACTIVE", reason=None, user_id=1
        )
    assert exc.value.detail["code"] == "INVALID_STEP_STATUS"


@pytest.mark.anyio
async def test_excluding_an_action_from_the_ir_requires_a_reason():
    existing = SimpleNamespace(
        action_id=5, session_id=1, step_key="1", lifecycle_phase=None,
        excluded_from_ir=False, exclusion_reason=None, review_state="accepted", mapped_by=None,
    )
    with pytest.raises(RecorderError) as exc:
        await mapping.update_mapping(
            _FakeDB(existing), _session(), action_id=5, user_id=1,
            excluded_from_ir=True, exclusion_reason="",
        )
    assert exc.value.detail["code"] == "EXCLUSION_REASON_REQUIRED"


@pytest.mark.anyio
async def test_marking_an_unmapped_action_as_setup_is_refused_with_guidance():
    with pytest.raises(RecorderError) as exc:
        await mapping.update_mapping(
            _FakeDB(None), _session(), action_id=5, user_id=1, lifecycle_phase="setup"
        )
    assert exc.value.detail["code"] == "MAPPING_NOT_FOUND"
    assert "map it to a step" in exc.value.detail["message"]


@pytest.mark.anyio
async def test_invalid_lifecycle_phase_is_refused():
    existing = SimpleNamespace(
        action_id=5, session_id=1, step_key="1", lifecycle_phase=None,
        excluded_from_ir=False, exclusion_reason=None, review_state="accepted", mapped_by=None,
    )
    with pytest.raises(RecorderError) as exc:
        await mapping.update_mapping(
            _FakeDB(existing), _session(), action_id=5, user_id=1, lifecycle_phase="middle"
        )
    assert exc.value.detail["code"] == "INVALID_LIFECYCLE_PHASE"


# ── Secrets (Section 18) ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_secret_reference_carrying_a_value_is_refused():
    with pytest.raises(RecorderError) as exc:
        await bindings.upsert_binding(
            _FakeDB(), _session(), user_id=1, name="password",
            classification="secret_reference", secret_reference="vault://pw", sample_value="hunter2",
        )
    assert exc.value.detail["code"] == "SECRET_VALUE_REFUSED"


@pytest.mark.anyio
async def test_secret_reference_requires_a_reference():
    with pytest.raises(RecorderError) as exc:
        await bindings.upsert_binding(
            _FakeDB(), _session(), user_id=1, name="password", classification="secret_reference"
        )
    assert exc.value.detail["code"] == "SECRET_REFERENCE_REQUIRED"


@pytest.mark.anyio
async def test_redaction_marker_is_never_stored_as_a_sample_value():
    """The recorder refused to keep the value; keeping the marker would be worse."""
    db = _FakeDB(None)
    binding = await bindings.upsert_binding(
        db, _session(), user_id=1, name="otp", classification="static_value",
        sample_value=bindings.REDACTED_MARKER,
    )
    assert binding.sample_value is None


@pytest.mark.anyio
async def test_test_data_parameter_must_reference_a_record():
    with pytest.raises(RecorderError) as exc:
        await bindings.upsert_binding(
            _FakeDB(), _session(), user_id=1, name="msisdn", classification="test_data_parameter"
        )
    assert exc.value.detail["code"] == "TEST_DATA_REQUIRED"


@pytest.mark.anyio
async def test_binding_name_must_be_a_safe_identifier():
    """It becomes an identifier in the generated script."""
    with pytest.raises(RecorderError) as exc:
        await bindings.upsert_binding(
            _FakeDB(), _session(), user_id=1, name="order id!", classification="static_value"
        )
    assert exc.value.detail["code"] == "INVALID_BINDING_NAME"


# ── Lifecycle guards (Sections 13, 22) ───────────────────────────────────────


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["NOT_STARTED", "RECORDING", "INITIALISING", "FAILED"])
async def test_ir_cannot_be_emitted_from_a_recording_that_is_not_captured(status):
    with pytest.raises(RecorderError) as exc:
        await lifecycle.emit_ir_draft(_FakeDB(), _session(status=status), user_id=1)
    assert exc.value.detail["code"] == "RECORDING_NOT_CAPTURED"
    assert exc.value.detail["current_state"] == status


@pytest.mark.anyio
async def test_ir_cannot_be_emitted_without_a_test_case():
    with pytest.raises(RecorderError) as exc:
        await lifecycle.emit_ir_draft(_FakeDB(), _session(status="STOPPED", test_case_id=None), user_id=1)
    assert exc.value.detail["code"] == "NO_TEST_CASE"


@pytest.mark.anyio
async def test_discarding_requires_a_reason():
    with pytest.raises(RecorderError) as exc:
        await lifecycle.discard(_FakeDB(), _session(), user_id=1, reason="   ")
    assert exc.value.detail["code"] == "DISCARD_REASON_REQUIRED"


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["COMPLETED", "CANCELLED", "EMERGENCY_STOPPED"])
async def test_a_finalized_recording_cannot_be_discarded_again(status):
    with pytest.raises(RecorderError) as exc:
        await lifecycle.discard(_FakeDB(), _session(status=status), user_id=1, reason="mistake")
    assert exc.value.detail["code"] == "ALREADY_FINAL"


@pytest.mark.anyio
async def test_discard_preserves_the_captured_rows():
    """Section 25 — the discard itself must stay reviewable."""
    db = _FakeDB()
    session = _session()
    await lifecycle.discard(db, session, user_id=1, reason="Wrong environment")

    assert session.status == "CANCELLED"
    assert session.terminal_reason == "Wrong environment"
    assert db.deleted == []
    assert any(getattr(obj, "command", None) == "discard_recording" for obj in db.added)


# ── Session creation (Sections 4, 25) ────────────────────────────────────────


@pytest.mark.anyio
async def test_unknown_recording_mode_is_refused():
    with pytest.raises(RecorderError) as exc:
        await session_service.create_session(
            _FakeDB(), project_id=1, user_id=1, suite_id=4, test_case_id=8, recording_mode="FREESTYLE"
        )
    assert exc.value.detail["code"] == "INVALID_RECORDING_MODE"


@pytest.mark.anyio
async def test_versioning_requires_a_reason():
    with pytest.raises(RecorderError) as exc:
        await session_service.create_version(_FakeDB(), _session(), user_id=1, reason=" ")
    assert exc.value.detail["code"] == "VERSION_REASON_REQUIRED"


@pytest.mark.anyio
async def test_a_recording_with_no_suite_cannot_be_versioned():
    with pytest.raises(RecorderError) as exc:
        await session_service.create_version(
            _FakeDB(), _session(suite_id=None), user_id=1, reason="re-record"
        )
    assert exc.value.detail["code"] == "RECORDING_NOT_VERSIONABLE"


@pytest.mark.anyio
async def test_opening_a_discovery_session_as_a_recording_is_refused():
    """The two surfaces must never show each other's sessions."""
    from app.models.discovery_session import DiscoverySession

    db = _FakeDB(gets={DiscoverySession: _session(recording_origin="discovery")})
    with pytest.raises(RecorderError) as exc:
        await session_service.get_recording_or_404(db, 1)
    assert exc.value.detail["code"] == "NOT_A_RECORDING"


@pytest.mark.anyio
async def test_a_missing_recording_is_a_404():
    db = _FakeDB()
    with pytest.raises(RecorderError) as exc:
        await session_service.get_recording_or_404(db, 999)
    assert exc.value.detail["code"] == "RECORDING_NOT_FOUND"
