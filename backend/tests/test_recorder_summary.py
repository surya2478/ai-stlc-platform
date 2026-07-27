"""UI-019 recording summary — the "null, not zero" contract.

A figure with no source must report that it has none. "0 console errors" when
console was never captured is a claim a reviewer will act on; "not captured"
is one they will question. These tests pin that distinction, and the console
parser against the format the browser actually returns.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.recorder import summary as recorder_summary
from app.services.recorder.bindings import REDACTED_MARKER
from app.services.recorder.context import RecordingContext

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


def _context(**overrides):
    base = dict(
        session=SimpleNamespace(
            id=1,
            project_id=1,
            status="STOPPED",
            recording_mode="GUIDED_TEST_CASE",
            recording_version=1,
            ir_status="NOT_GENERATED",
            started_at=NOW,
            terminal_at=NOW + timedelta(seconds=95),
        ),
        test_case=SimpleNamespace(steps=[]),
        suite=None,
        member=None,
        application=None,
        application_model=None,
        actions=[],
        mappings=[],
        step_states=[],
        checkpoints=[],
        segments=[],
        bindings=[],
        notes=[],
        captures=[],
        events=[],
    )
    base.update(overrides)
    return RecordingContext(**base)


def _action(sequence, family="click", **kwargs):
    return SimpleNamespace(
        id=kwargs.get("id", sequence + 100),
        sequence=sequence,
        action_family=family,
        inclusion_state=kwargs.get("inclusion_state", "included"),
        target_semantic=kwargs.get("target_semantic", "Some element"),
        input_binding=kwargs.get("input_binding"),
        locator_confidence=kwargs.get("locator_confidence", 90),
        occurred_at=kwargs.get("occurred_at", NOW),
    )


# ── Console parsing ──────────────────────────────────────────────────────────


def test_console_tally_line_is_authoritative():
    stats = recorder_summary.parse_console_text(
        "### Result\nTotal messages: 4 (Errors: 1, Warnings: 2)\n"
    )
    assert stats == {"errors": 1, "warnings": 2, "other": 1, "unparsed": 0}


def test_console_tallies_from_multiple_captures_are_summed():
    stats = recorder_summary.parse_console_text(
        "### Result\nTotal messages: 4 (Errors: 1, Warnings: 2)\n"
        "### Result\nTotal messages: 2 (Errors: 2, Warnings: 0)\n"
    )
    assert stats["errors"] == 3
    assert stats["warnings"] == 2


def test_empty_console_is_zero_not_unknown():
    """The transport envelope must not be mistaken for unclassifiable output."""
    stats = recorder_summary.parse_console_text("### Result\nTotal messages: 0 (Errors: 0, Warnings: 0)\n")
    assert stats["errors"] == 0
    assert stats["unparsed"] == 0


def test_console_falls_back_to_level_prefixes():
    stats = recorder_summary.parse_console_text("[ERROR] boom\n[WARNING] hmm\nunrecognised line\n")
    assert stats["errors"] == 1
    assert stats["warnings"] == 1
    assert stats["unparsed"] == 1


# ── Measures ─────────────────────────────────────────────────────────────────


def test_console_not_captured_reports_null_with_a_reason():
    result = recorder_summary.build(_context(), console_stats=None)
    assert result["console_errors"]["value"] is None
    assert "not captured" in result["console_errors"]["reason"]


def test_console_captured_and_clean_reports_zero():
    result = recorder_summary.build(
        _context(), console_stats={"errors": 0, "warnings": 0, "other": 0, "unparsed": 0}
    )
    assert result["console_errors"]["value"] == 0
    assert result["console_errors"]["reason"] is None


def test_wholly_unparseable_console_reports_null_not_zero():
    result = recorder_summary.build(
        _context(), console_stats={"errors": 0, "warnings": 0, "other": 0, "unparsed": 12}
    )
    assert result["console_errors"]["value"] is None
    assert "12 console line(s)" in result["console_errors"]["reason"]


def test_network_not_parsed_reports_null():
    result = recorder_summary.build(_context(), network_stats=None)
    assert result["network_failures"]["value"] is None
    assert result["network_requests"]["value"] is None


def test_network_parsed_reports_counts():
    result = recorder_summary.build(_context(), network_stats={"total": 33, "failed": 2})
    assert result["network_requests"]["value"] == 33
    assert result["network_failures"]["value"] == 2


# ── Coverage ─────────────────────────────────────────────────────────────────


def _with_steps(step_count, *, mapped_keys=(), skipped_keys=()):
    return _context(
        test_case=SimpleNamespace(
            steps=[{"step_number": n, "action": f"step {n}"} for n in range(1, step_count + 1)]
        ),
        mappings=[
            SimpleNamespace(action_id=i, step_key=key, excluded_from_ir=False, mapping_source="active_step")
            for i, key in enumerate(mapped_keys)
        ],
        step_states=[
            SimpleNamespace(
                step_key=key, status="SKIPPED", source_step_index=None, parent_step_key=None,
                discovered_label=None, skip_reason="not applicable",
            )
            for key in skipped_keys
        ],
    )


def test_coverage_counts_only_steps_with_recorded_actions():
    result = recorder_summary.build(_with_steps(4, mapped_keys=["1", "2"]))
    coverage = result["test_case_coverage"]
    assert coverage["recorded_steps"] == 2
    assert coverage["steps_without_actions"] == 2
    assert coverage["percent"] == 50


def test_skipped_steps_leave_the_coverage_denominator():
    """Otherwise a legitimately complete recording can never reach 100%."""
    result = recorder_summary.build(_with_steps(4, mapped_keys=["1", "2", "3"], skipped_keys=["4"]))
    coverage = result["test_case_coverage"]
    assert coverage["skipped_steps"] == 1
    assert coverage["percent"] == 100


def test_coverage_percent_is_null_when_there_are_no_steps():
    assert recorder_summary.build(_context())["test_case_coverage"]["percent"] is None


# ── Locator, redaction and unsupported-action reporting ──────────────────────


def test_low_confidence_and_missing_locators_are_both_warnings():
    context = _context(
        actions=[
            _action(0, "click", locator_confidence=90),
            _action(1, "click", locator_confidence=40),
            _action(2, "input", locator_confidence=None),
            _action(3, "navigate", locator_confidence=None),
        ]
    )
    warnings = recorder_summary.build(context)["locator_warnings"]
    # navigate has no element, so it is not a locator warning.
    assert [w["sequence"] for w in warnings] == [1, 2]
    assert warnings[1]["confidence"] is None


def test_redacted_inputs_are_counted_and_never_offered_for_binding():
    context = _context(
        actions=[
            _action(0, "input", input_binding={"text": REDACTED_MARKER}),
            _action(1, "input", input_binding={"text": "plain value"}),
        ]
    )
    result = recorder_summary.build(context)
    assert result["redactions"]["inputs"] == 1
    unbound = {row["sequence"]: row for row in result["unbound_inputs"]}
    assert unbound[0]["sample_value"] is None
    assert unbound[0]["requires_secret_reference"] is True
    assert unbound[1]["sample_value"] == "plain value"
    assert unbound[1]["requires_secret_reference"] is False


def test_unsupported_actions_come_from_real_recorded_failures():
    context = _context(
        events=[
            SimpleNamespace(command="perform_action_failed", reason="Unsupported action_family 'drag'", occurred_at=NOW),
            SimpleNamespace(command="pause", reason=None, occurred_at=NOW),
        ]
    )
    rows = recorder_summary.build(context)["unsupported_actions"]
    assert len(rows) == 1
    assert "drag" in rows[0]["detail"]


def test_duration_uses_the_sessions_own_timestamps():
    assert recorder_summary.build(_context())["duration_seconds"] == 95


def test_duration_is_null_before_the_recording_starts():
    context = _context(
        session=SimpleNamespace(
            id=1, project_id=1, status="NOT_STARTED", recording_mode="GUIDED_TEST_CASE",
            recording_version=1, ir_status="NOT_GENERATED", started_at=None, terminal_at=None,
        )
    )
    assert recorder_summary.build(context)["duration_seconds"] is None
