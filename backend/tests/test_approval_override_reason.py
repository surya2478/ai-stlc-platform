"""approval_override_reason: a reviewer approving a script had no way to
see it had unresolved locators or had already failed its own dry run —
"Approved" looked identical either way, and the problem only surfaced
later at execution time. Rather than block approval outright, it still
proceeds, but only with the reviewer's own notes as an explicit, audited
acknowledgement of what they're overriding."""
from app.models.automation_script import AutomationScript
from app.services.automation_service import (
    approval_override_reason,
    approve_script,
    execution_blocked_reason,
)


def _script(**overrides) -> AutomationScript:
    data = {
        "id": 1, "project_id": 8, "created_by": 1, "script_id": "AS-0001",
        "framework": "playwright", "code": "code", "status": "in_review",
    }
    data.update(overrides)
    return AutomationScript(**data)


def test_clean_script_needs_no_override_reason():
    assert approval_override_reason(_script(), None) is None
    assert approval_override_reason(_script(), "") is None


def test_ungrounded_script_blocked_without_notes():
    script = _script(metadata_={"grounding": {"ungrounded_elements": ["Page.searchBar"]}})
    reason = approval_override_reason(script, None)
    assert reason is not None
    assert "Page.searchBar" in reason
    assert "notes field" in reason


def test_ungrounded_script_allowed_with_notes():
    script = _script(metadata_={"grounding": {"ungrounded_elements": ["Page.searchBar"]}})
    assert approval_override_reason(script, "Aware of this, approving for manual follow-up") is None


def test_failed_dry_run_blocked_without_notes():
    script = _script(metadata_={"last_dry_run": {"passed": False}})
    reason = approval_override_reason(script, None)
    assert reason is not None
    assert "dry run failed" in reason


def test_failed_dry_run_allowed_with_notes():
    script = _script(metadata_={"last_dry_run": {"passed": False}})
    assert approval_override_reason(script, "Env issue unrelated to the script, approving") is None


def test_whitespace_only_notes_do_not_count_as_an_override():
    script = _script(metadata_={"last_dry_run": {"passed": False}})
    reason = approval_override_reason(script, "   ")
    assert reason is not None


def test_never_dry_run_and_no_grounding_metadata_is_not_blocked():
    # Unknown is not the same as known-bad — a script with no quality
    # metadata at all (e.g. externally authored) must not be gated.
    script = _script(metadata_={})
    assert approval_override_reason(script, None) is None


# ── the override has to reach execution ───────────────────────────────────────
# Observed live 2026-08-03: Playwright AI Studio asked for an override note,
# accepted one, approved all five scripts — and then the execution gate refused
# the same scripts anyway, with no second override available. The advice
# ("regenerate before running") could not help: an error banner that only
# exists after a failed submit can never appear in a catalog crawled from the
# form, so regeneration reproduces the same "ungrounded" element forever.

def _approved_with_issue(**overrides) -> AutomationScript:
    data = {
        "status": "approved",
        "metadata_": {"grounding": {"ungrounded_elements": ["ErrorBanner.invalid_credentials"]}},
    }
    data.update(overrides)
    return _script(**data)


def test_an_approved_script_with_an_unacknowledged_issue_is_still_blocked():
    """The gate must keep working — this is not a way to switch it off."""
    reason = execution_blocked_reason(_approved_with_issue())
    assert reason is not None
    assert "ErrorBanner.invalid_credentials" in reason
    # And the advice now names a route that actually exists.
    assert "note explaining why" in reason


def test_an_override_recorded_at_approval_unblocks_execution():
    script = _approved_with_issue()
    script.metadata_ = {
        **script.metadata_,
        "execution_override": {
            "issue": "1 element(s) not grounded to a real page (ErrorBanner.invalid_credentials)",
            "reason": "Error banner only renders after a failed submit; cannot be pre-discovered.",
        },
    }
    assert execution_blocked_reason(script) is None


def test_an_override_for_a_different_issue_does_not_unblock():
    """An override covers what the approver actually reviewed. If the script
    later develops a different problem, the old note must not wave it through."""
    script = _approved_with_issue()
    script.metadata_ = {
        **script.metadata_,
        "execution_override": {"issue": "the last dry run failed", "reason": "flaky environment"},
    }
    assert execution_blocked_reason(script) is not None


def test_an_empty_override_reason_does_not_unblock():
    script = _approved_with_issue()
    script.metadata_ = {
        **script.metadata_,
        "execution_override": {
            "issue": "1 element(s) not grounded to a real page (ErrorBanner.invalid_credentials)",
            "reason": "   ",
        },
    }
    assert execution_blocked_reason(script) is not None


def test_approving_with_a_note_records_what_was_overridden():
    import anyio

    class _DB:
        async def flush(self):
            return None

        async def refresh(self, _obj):
            return None

    script = _script(
        status="in_review",
        metadata_={"grounding": {"ungrounded_elements": ["ErrorBanner.invalid_credentials"]}},
    )

    anyio.run(lambda: approve_script(_DB(), script, "approve", "Runtime-only element; accepted."))

    override = script.metadata_["execution_override"]
    assert "ErrorBanner.invalid_credentials" in override["issue"]
    assert override["reason"] == "Runtime-only element; accepted."
    assert execution_blocked_reason(script) is None


def test_rejecting_with_a_note_records_no_override():
    import anyio

    class _DB:
        async def flush(self):
            return None

        async def refresh(self, _obj):
            return None

    script = _script(
        status="in_review",
        metadata_={"grounding": {"ungrounded_elements": ["ErrorBanner.invalid_credentials"]}},
    )

    anyio.run(lambda: approve_script(_DB(), script, "reject", "Not acceptable."))

    assert "execution_override" not in script.metadata_
