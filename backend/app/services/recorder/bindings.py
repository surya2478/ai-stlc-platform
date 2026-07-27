"""Captured-input classification and parameterization (Contract Section 18).

Every value typed during a recording starts life as an observed literal. This
module is how a person says what it actually *is* — a test data parameter, a
secret reference, the output of an earlier step — so the generated script
binds to the right source instead of hard-coding whatever happened to be typed
on the day.

Section 18's prohibition is enforced in three places, not one: the recorder
already redacts sensitive fields before persistence (`capture_service`), a
`secret_reference` binding may not carry a sample value (a database check
constraint), and the IR emitter renders secret references as a named reference
rather than a value.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_session import DiscoveryAction, DiscoverySession
from app.models.recording_session import DATA_BINDING_CLASSIFICATIONS, RecordingDataBinding
from app.models.test_data import TestData
from app.services.recorder.errors import RecorderError

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

# What `capture_service` writes in place of a value it refused to persist.
REDACTED_MARKER = "[REDACTED - sensitive field]"


async def list_bindings(db: AsyncSession, session: DiscoverySession) -> list[RecordingDataBinding]:
    result = await db.execute(
        select(RecordingDataBinding)
        .where(RecordingDataBinding.session_id == session.id)
        .order_by(RecordingDataBinding.id)
    )
    return list(result.scalars().all())


def _validate_name(name: str) -> str:
    value = (name or "").strip()
    if not _NAME_RE.match(value):
        raise RecorderError(
            400,
            "INVALID_BINDING_NAME",
            "A binding name must start with a letter or underscore and contain only letters, digits "
            "and underscores — it becomes an identifier in the generated script.",
        )
    return value


async def upsert_binding(
    db: AsyncSession,
    session: DiscoverySession,
    *,
    user_id: int,
    name: str,
    classification: str,
    action_id: int | None = None,
    test_data_id: int | None = None,
    secret_reference: str | None = None,
    source_action_id: int | None = None,
    environment_key: str | None = None,
    sample_value: str | None = None,
) -> RecordingDataBinding:
    if classification not in DATA_BINDING_CLASSIFICATIONS:
        raise RecorderError(
            400,
            "INVALID_CLASSIFICATION",
            f"classification must be one of {list(DATA_BINDING_CLASSIFICATIONS)}.",
        )
    name = _validate_name(name)

    # Each classification names exactly one source. Accepting a binding whose
    # source is missing would produce an IR that cannot resolve at run time.
    if classification == "test_data_parameter":
        if test_data_id is None:
            raise RecorderError(
                400, "TEST_DATA_REQUIRED", "A test data parameter must reference a linked test data record."
            )
        test_data = await db.get(TestData, test_data_id)
        if test_data is None or test_data.project_id != session.project_id:
            raise RecorderError(404, "TEST_DATA_NOT_FOUND", "Test data record not found in this project.")
    elif classification == "secret_reference":
        if not (secret_reference or "").strip():
            raise RecorderError(
                400,
                "SECRET_REFERENCE_REQUIRED",
                "A secret reference must name the secret to resolve at run time.",
            )
        if sample_value:
            raise RecorderError(
                400,
                "SECRET_VALUE_REFUSED",
                "A secret reference must not carry a value. Reference the secret by name instead "
                "(Section 18).",
            )
    elif classification == "previous_step_output":
        if source_action_id is None:
            raise RecorderError(
                400, "SOURCE_ACTION_REQUIRED", "A previous-step output must name the action it comes from."
            )
        source = await db.get(DiscoveryAction, source_action_id)
        if source is None or source.session_id != session.id:
            raise RecorderError(404, "ACTION_NOT_FOUND", "Source action not found in this recording session.")
    elif classification == "environment_value":
        if not (environment_key or "").strip():
            raise RecorderError(
                400, "ENVIRONMENT_KEY_REQUIRED", "An environment value must name the environment key."
            )

    if action_id is not None:
        action = await db.get(DiscoveryAction, action_id)
        if action is None or action.session_id != session.id:
            raise RecorderError(404, "ACTION_NOT_FOUND", "Action not found in this recording session.")

    if sample_value == REDACTED_MARKER:
        # The recorder already refused to persist this value. Carrying the
        # marker forward as if it were data would be worse than carrying
        # nothing.
        sample_value = None

    result = await db.execute(
        select(RecordingDataBinding).where(
            RecordingDataBinding.session_id == session.id, RecordingDataBinding.name == name
        )
    )
    binding = result.scalar_one_or_none()
    if binding is None:
        binding = RecordingDataBinding(
            session_id=session.id,
            project_id=session.project_id,
            name=name,
            placeholder=f"${{{name}}}",
        )
        db.add(binding)

    binding.action_id = action_id
    binding.classification = classification
    binding.test_data_id = test_data_id if classification == "test_data_parameter" else None
    binding.secret_reference = secret_reference if classification == "secret_reference" else None
    binding.source_action_id = source_action_id if classification == "previous_step_output" else None
    binding.environment_key = environment_key if classification == "environment_value" else None
    binding.sample_value = None if classification == "secret_reference" else sample_value
    binding.created_by = user_id

    await db.commit()
    await db.refresh(binding)
    return binding


async def delete_binding(db: AsyncSession, session: DiscoverySession, *, binding_id: int) -> None:
    binding = await db.get(RecordingDataBinding, binding_id)
    if binding is None or binding.session_id != session.id:
        raise RecorderError(404, "BINDING_NOT_FOUND", "Data binding not found in this recording session.")
    await db.delete(binding)
    await db.commit()


def unbound_inputs(actions: list[DiscoveryAction], bindings: list[RecordingDataBinding]) -> list[dict]:
    """Section 15's "missing data bindings" gap: an input action whose typed
    value is still an unclassified literal. Pure — takes what the caller
    already loaded.

    A redacted value is *not* reported: the recorder deliberately did not keep
    it, and the user cannot classify what was never stored. It is surfaced
    separately, as a required secret reference.
    """
    bound_action_ids = {b.action_id for b in bindings if b.action_id is not None}
    rows: list[dict] = []
    for action in actions:
        if action.action_family != "input" or action.inclusion_state != "included":
            continue
        if action.id in bound_action_ids:
            continue
        text = (action.input_binding or {}).get("text")
        rows.append(
            {
                "action_id": action.id,
                "sequence": action.sequence,
                "target_semantic": action.target_semantic,
                "sample_value": None if text == REDACTED_MARKER else text,
                "requires_secret_reference": text == REDACTED_MARKER,
            }
        )
    return rows
