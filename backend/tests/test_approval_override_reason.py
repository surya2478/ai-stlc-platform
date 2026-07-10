"""approval_override_reason: a reviewer approving a script had no way to
see it had unresolved locators or had already failed its own dry run —
"Approved" looked identical either way, and the problem only surfaced
later at execution time. Rather than block approval outright, it still
proceeds, but only with the reviewer's own notes as an explicit, audited
acknowledgement of what they're overriding."""
from app.models.automation_script import AutomationScript
from app.services.automation_service import approval_override_reason


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
