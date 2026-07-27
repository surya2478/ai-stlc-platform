"""Test case step derivation and status computation (Contract Section 10.3).

Pure functions over a loaded `RecordingContext`. Nothing here queries, and
nothing here writes — a step's displayed status is *computed* from the
recording every time rather than stored and kept in sync, so it cannot drift
away from the actions that justify it. The only stored statuses are the ones a
computation could never infer, because they encode a human decision: SKIPPED,
COMPLETED, ACTIVE, MISMATCH and NEEDS_REVIEW.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.recorder.context import RecordingContext

# Statuses a person sets deliberately. When one of these is stored it always
# wins over the derived value — otherwise marking a step Skipped would be
# silently undone by the next action that happened to land on it.
USER_OWNED_STATES = ("ACTIVE", "SKIPPED", "COMPLETED", "MISMATCH", "NEEDS_REVIEW")


@dataclass(frozen=True)
class RecorderStep:
    """One row of the left panel (Section 10.3)."""

    step_key: str
    source_step_index: int | None
    action_text: str | None
    expected_result: str | None
    status: str
    recorded_action_count: int
    checkpoint_count: int
    accepted_checkpoint_count: int
    skip_reason: str | None
    is_discovered_substep: bool
    parent_step_key: str | None
    # Why the status is what it is, in one sentence, so the panel never shows
    # a state the user cannot account for.
    status_reason: str


def step_text(step: dict) -> str | None:
    value = step.get("action") or step.get("description")
    return str(value) if value else None


def expected_result(step: dict) -> str | None:
    value = step.get("expected_result")
    return str(value) if value else None


def step_key_for_index(index: int) -> str:
    """Step keys are the 1-based *position* in the test case's step array.

    Deliberately not the step's own `step_number` field: that is free-form
    JSON and is neither guaranteed present nor guaranteed unique, and a step
    key has to be both — it is the unique constraint on `recording_step_states`
    and the thing every recorded action is mapped to. A test case numbering
    its steps 10/20/30 would otherwise produce mappings that cannot be
    resolved back to a position, or two steps that collide on one key.
    """
    return str(index + 1)


def next_substep_key(parent_step_key: str, existing_keys: set[str]) -> str:
    """"3" -> "3.1", then "3.2", and so on (Section 7.1 discovered sub-steps)."""
    suffix = 1
    while f"{parent_step_key}.{suffix}" in existing_keys:
        suffix += 1
    return f"{parent_step_key}.{suffix}"


def _sort_key(step_key: str) -> tuple:
    """Orders "1", "2", "2.1", "2.2", "10" the way a reader expects — numeric
    per segment, so "10" sorts after "2" rather than before it."""
    parts = []
    for segment in step_key.split("."):
        try:
            parts.append((0, int(segment)))
        except ValueError:
            parts.append((1, segment))
    return tuple(parts)


def _derive_status(
    *,
    stored_status: str | None,
    recorded_action_count: int,
    has_expected_result: bool,
    accepted_checkpoint_count: int,
) -> tuple[str, str]:
    """Returns (status, reason). See the module docstring for why stored
    user decisions win."""
    if stored_status in USER_OWNED_STATES:
        return stored_status, "Set explicitly by a user."
    if recorded_action_count == 0:
        return "PENDING", "No recorded action is mapped to this step yet."
    if has_expected_result and accepted_checkpoint_count == 0:
        return (
            "PARTIALLY_RECORDED",
            f"{recorded_action_count} action(s) recorded, but the step's expected result "
            "has no accepted validation checkpoint.",
        )
    return "RECORDED", f"{recorded_action_count} action(s) recorded."


def build_step_list(context: RecordingContext) -> list[RecorderStep]:
    """The full left-panel step list: every step of the live test case, plus
    any sub-step discovered during recording, in reading order."""
    mappings_by_step = context.mappings_by_step_key
    checkpoints_by_step = context.checkpoints_by_step_key
    state_by_key = context.step_state_by_key

    rows: list[RecorderStep] = []
    seen_keys: set[str] = set()

    def _append(
        *,
        step_key: str,
        source_step_index: int | None,
        action_text: str | None,
        expected: str | None,
        is_discovered: bool,
        parent_step_key: str | None,
    ) -> None:
        state = state_by_key.get(step_key)
        mapped = [m for m in mappings_by_step.get(step_key, []) if not m.excluded_from_ir]
        checkpoints = checkpoints_by_step.get(step_key, [])
        accepted = [c for c in checkpoints if c.review_state == "accepted"]
        status, reason = _derive_status(
            stored_status=state.status if state else None,
            recorded_action_count=len(mapped),
            has_expected_result=bool(expected),
            accepted_checkpoint_count=len(accepted),
        )
        rows.append(
            RecorderStep(
                step_key=step_key,
                source_step_index=source_step_index,
                action_text=action_text,
                expected_result=expected,
                status=status,
                recorded_action_count=len(mapped),
                checkpoint_count=len(checkpoints),
                accepted_checkpoint_count=len(accepted),
                skip_reason=state.skip_reason if state else None,
                is_discovered_substep=is_discovered,
                parent_step_key=parent_step_key,
                status_reason=reason,
            )
        )
        seen_keys.add(step_key)

    for index, step in enumerate(context.source_steps):
        _append(
            step_key=step_key_for_index(index),
            source_step_index=index,
            action_text=step_text(step),
            expected=expected_result(step),
            is_discovered=False,
            parent_step_key=None,
        )

    for state in context.step_states:
        if state.step_key in seen_keys:
            continue
        # A stored state with no counterpart in the live test case is either a
        # discovered sub-step or a step that has since been deleted from the
        # test case. Both must stay visible: silently dropping either would
        # hide recorded actions that are still mapped to them.
        _append(
            step_key=state.step_key,
            source_step_index=state.source_step_index,
            action_text=state.discovered_label,
            expected=None,
            is_discovered=state.parent_step_key is not None,
            parent_step_key=state.parent_step_key,
        )

    rows.sort(key=lambda r: _sort_key(r.step_key))
    return rows


def active_step_key(context: RecordingContext) -> str | None:
    """The step new actions will be attached to. The explicitly ACTIVE step if
    there is one; otherwise the first step with nothing recorded against it, so
    a user who never touches the step list still gets sensible mapping."""
    state_by_key = context.step_state_by_key
    for key, state in state_by_key.items():
        if state.status == "ACTIVE":
            return key
    for step in build_step_list(context):
        if step.status == "PENDING":
            return step.step_key
    return None


def unmapped_actions(context: RecordingContext) -> list:
    """Recorded actions with no step (Section 15). `read` actions are excluded:
    an explicit observation is not a gap, it is how a user checks state."""
    mapped_ids = set(context.mapping_by_action_id)
    return [
        action
        for action in context.actions
        if action.id not in mapped_ids
        and action.action_family != "read"
        and action.inclusion_state == "included"
    ]


def steps_without_actions(context: RecordingContext) -> list[RecorderStep]:
    """Section 15's "steps without actions".

    Keyed on whether anything was actually recorded, not on the status label.
    A step marked ACTIVE or COMPLETED with zero mapped actions is still a step
    with nothing recorded against it, and reporting it as covered because of
    its label is exactly the kind of misleading figure the summary exists to
    avoid. A SKIPPED step was a decision, not an omission, so it is excluded.
    """
    return [
        step
        for step in build_step_list(context)
        if step.recorded_action_count == 0 and step.status != "SKIPPED"
    ]


def steps_with_actions(context: RecordingContext) -> list[RecorderStep]:
    """The complement: steps that have at least one recorded action mapped."""
    return [step for step in build_step_list(context) if step.recorded_action_count > 0]


def expected_results_without_checkpoints(context: RecordingContext) -> list[RecorderStep]:
    """Section 15/21 — a step that states an expected result but has no
    accepted checkpoint to assert it. The generated script would silently not
    check the thing the test case exists to check."""
    return [
        step
        for step in build_step_list(context)
        if step.expected_result and step.accepted_checkpoint_count == 0 and step.status != "SKIPPED"
    ]
