"""Recording summary (Contract Section 21).

Pure functions over a loaded `RecordingContext` plus whatever the caller has
already read from disk or from UI-017's network events. Nothing here queries.

The rule this module follows throughout: a figure with no real source is
reported as `null` alongside the reason, never as `0`. A summary that says
"0 console errors" when console output was never captured is worse than one
that says it does not know, because a reviewer will act on the first and
question the second.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.recorder import bindings as recorder_bindings
from app.services.recorder import steps as recorder_steps
from app.services.recorder.context import RecordingContext

# `browser_console_messages` opens its response with an explicit tally, e.g.
#   ### Result
#   Total messages: 4 (Errors: 1, Warnings: 2)
# When that line is present it is the authoritative answer and is used
# directly — it comes from the browser rather than from parsing prose.
_CONSOLE_TOTALS_RE = re.compile(
    r"Total messages:\s*(?P<total>\d+)\s*\(\s*Errors:\s*(?P<errors>\d+)\s*,\s*Warnings:\s*(?P<warnings>\d+)\s*\)",
    re.IGNORECASE,
)

# Fallback for a response without the tally line: classify each message by its
# level prefix.
_CONSOLE_LINE_RE = re.compile(r"^\s*\[?(?P<level>ERROR|WARNING|WARN|LOG|INFO|DEBUG|VERBOSE)\]?\b", re.IGNORECASE)

# The MCP tool response wraps its payload in "### Result" headers and fenced
# blocks. Those are transport, not console output — counting them as
# unclassifiable lines made a genuinely empty console report as "unknown"
# instead of as zero errors, which is the opposite of the intent.
_CONSOLE_ENVELOPE_RE = re.compile(r"^\s*(###\s|```)")

# A locator below this is not trustworthy enough to publish unreviewed
# (Section 19's "low-confidence locators must not be automatically published").
LOW_CONFIDENCE_THRESHOLD = 60


@dataclass(frozen=True)
class Measure:
    """A summary figure and, when it has no source, why."""

    value: int | None
    reason: str | None = None

    def as_dict(self) -> dict:
        return {"value": self.value, "reason": self.reason}


def parse_console_text(text: str) -> dict:
    """Counts console entries by level.

    Prefers the browser's own tally line when the capture has one; otherwise
    classifies each message by its level prefix and reports how many lines it
    could not classify, so a caller never mistakes an unrecognised format for
    silence.

    Concatenated captures (one per action) are summed: each is an independent
    console read taken at a different point in the recording.
    """
    errors = warnings = other = unparsed = 0
    totals_found = False

    for match in _CONSOLE_TOTALS_RE.finditer(text or ""):
        totals_found = True
        total = int(match.group("total"))
        captured_errors = int(match.group("errors"))
        captured_warnings = int(match.group("warnings"))
        errors += captured_errors
        warnings += captured_warnings
        other += max(total - captured_errors - captured_warnings, 0)

    if totals_found:
        return {"errors": errors, "warnings": warnings, "other": other, "unparsed": 0}

    for line in (text or "").splitlines():
        if not line.strip() or _CONSOLE_ENVELOPE_RE.match(line):
            continue
        match = _CONSOLE_LINE_RE.match(line)
        if match is None:
            unparsed += 1
            continue
        level = match.group("level").upper()
        if level == "ERROR":
            errors += 1
        elif level in ("WARNING", "WARN"):
            warnings += 1
        else:
            other += 1
    return {"errors": errors, "warnings": warnings, "other": other, "unparsed": unparsed}


def _duration_seconds(context: RecordingContext) -> int | None:
    session = context.session
    if session.started_at is None:
        return None
    end = session.terminal_at
    if end is None and context.actions:
        end = context.actions[-1].occurred_at
    if end is None:
        return None
    return max(int((end - session.started_at).total_seconds()), 0)


def _locator_warnings(context: RecordingContext) -> list[dict]:
    rows: list[dict] = []
    for action in context.actions:
        if action.action_family not in ("click", "input") or action.inclusion_state != "included":
            continue
        confidence = action.locator_confidence
        if confidence is None:
            rows.append(
                {
                    "action_id": action.id,
                    "sequence": action.sequence,
                    "confidence": None,
                    "detail": "No locator candidate was observed for this action.",
                }
            )
        elif confidence < LOW_CONFIDENCE_THRESHOLD:
            rows.append(
                {
                    "action_id": action.id,
                    "sequence": action.sequence,
                    "confidence": confidence,
                    "detail": f"Best locator scored {confidence}, below the {LOW_CONFIDENCE_THRESHOLD} "
                              "threshold for unreviewed publication.",
                }
            )
    return rows


def _unsupported_actions(context: RecordingContext) -> list[dict]:
    """Section 21/24 — actions the user asked for that the adapter refused.
    These are real recorded failures on the session event log, not inferred."""
    return [
        {
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "detail": event.reason,
        }
        for event in context.events
        if event.command == "perform_action_failed"
    ]


def build(
    context: RecordingContext,
    *,
    console_stats: dict | None = None,
    network_stats: dict | None = None,
) -> dict:
    """Section 21's summary. `console_stats` and `network_stats` are passed in
    because they come from files and from UI-017's parsed network events —
    both outside this module's reach by design."""
    session = context.session
    step_rows = recorder_steps.build_step_list(context)
    # "Recorded" means something was actually recorded against the step, not
    # that it carries a particular status label — see steps.steps_without_actions.
    recorded_steps = recorder_steps.steps_with_actions(context)
    skipped_steps = [s for s in step_rows if s.status == "SKIPPED"]
    unmapped = recorder_steps.unmapped_actions(context)
    missing = recorder_steps.steps_without_actions(context)
    uncovered_expectations = recorder_steps.expected_results_without_checkpoints(context)

    included_actions = [a for a in context.actions if a.inclusion_state == "included"]
    evidence_by_type: dict[str, int] = {}
    for capture in context.captures:
        evidence_by_type[capture.capture_type] = evidence_by_type.get(capture.capture_type, 0) + 1

    redacted_inputs = sum(
        1
        for a in context.actions
        if (a.input_binding or {}).get("text") == recorder_bindings.REDACTED_MARKER
    )
    redacted_captures = sum(1 for c in context.captures if c.redaction_state == "applied")

    if console_stats is None:
        console_errors = Measure(None, "Console output was not captured for this recording.")
        console_warnings = Measure(None, "Console output was not captured for this recording.")
    elif console_stats.get("unparsed") and not any(
        console_stats.get(k) for k in ("errors", "warnings", "other")
    ):
        note = (
            f"{console_stats['unparsed']} console line(s) captured but none matched a known level "
            "format, so no error count can be stated."
        )
        console_errors = Measure(None, note)
        console_warnings = Measure(None, note)
    else:
        console_errors = Measure(console_stats.get("errors", 0))
        console_warnings = Measure(console_stats.get("warnings", 0))

    if network_stats is None:
        network_failures = Measure(None, "Network activity has not been parsed for this recording yet.")
        network_total = Measure(None, "Network activity has not been parsed for this recording yet.")
    else:
        network_failures = Measure(network_stats.get("failed", 0))
        network_total = Measure(network_stats.get("total", 0))

    # Skipped steps leave the denominator: a step deliberately not recorded is
    # not a coverage failure, and counting it as one would push a legitimately
    # complete recording below 100%.
    coverage_denominator = len(step_rows) - len(skipped_steps)
    coverage_pct = (
        round(len(recorded_steps) * 100 / coverage_denominator) if coverage_denominator else None
    )

    return {
        "session_id": session.id,
        "status": session.status,
        "recording_mode": session.recording_mode,
        "recording_version": session.recording_version,
        "ir_status": session.ir_status,
        "duration_seconds": _duration_seconds(context),
        "recorded_actions": len(included_actions),
        "excluded_actions": len(context.actions) - len(included_actions),
        "test_case_coverage": {
            "total_steps": len(step_rows),
            "recorded_steps": len(recorded_steps),
            "skipped_steps": len(skipped_steps),
            "steps_without_actions": len(missing),
            # Skipped steps are excluded from the denominator — see above.
            "percent": coverage_pct,
            "percent_basis": "recorded steps / (total steps - skipped steps)",
        },
        "unmapped_actions": [
            {"action_id": a.id, "sequence": a.sequence, "action_family": a.action_family,
             "target_semantic": a.target_semantic}
            for a in unmapped
        ],
        "missing_steps": [
            {"step_key": s.step_key, "action_text": s.action_text} for s in missing
        ],
        "expected_results_without_checkpoints": [
            {"step_key": s.step_key, "expected_result": s.expected_result} for s in uncovered_expectations
        ],
        "checkpoints": {
            "total": len(context.checkpoints),
            "accepted": sum(1 for c in context.checkpoints if c.review_state == "accepted"),
            "needs_review": sum(1 for c in context.checkpoints if c.review_state == "needs_review"),
            "rejected": sum(1 for c in context.checkpoints if c.review_state == "rejected"),
        },
        "applications_visited": [
            {
                "segment": seg.sequence,
                "application_id": seg.application_id,
                "environment": seg.environment,
                "transition_reason": seg.transition_reason,
            }
            for seg in context.segments
        ],
        "network_requests": network_total.as_dict(),
        "network_failures": network_failures.as_dict(),
        "console_errors": console_errors.as_dict(),
        "console_warnings": console_warnings.as_dict(),
        "locator_warnings": _locator_warnings(context),
        "evidence_generated": evidence_by_type,
        "redactions": {"inputs": redacted_inputs, "captures": redacted_captures},
        "unsupported_actions": _unsupported_actions(context),
        "unbound_inputs": recorder_bindings.unbound_inputs(context.actions, context.bindings),
        "data_bindings": len(context.bindings),
        "notes": len(context.notes),
    }
