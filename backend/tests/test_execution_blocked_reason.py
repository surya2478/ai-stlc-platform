"""execution_blocked_reason: the eligibility gate that stops a script from
being executed (single or batch) when it's known-bad, not just unapproved.

Regression context: every script in project 8 already carried grounding and
last_dry_run outcomes in metadata_, but the execute endpoints only ever
checked status in {"approved", "executed"} — so a script with unresolved
locators or a dry run that had already failed would still run, forever
reproducing the same failure on every "Retry"."""
from app.models.automation_script import AutomationScript
from app.services.automation_service import execution_blocked_reason


def _script(**overrides) -> AutomationScript:
    data = {
        "id": 1, "project_id": 8, "created_by": 1, "script_id": "AS-0001",
        "framework": "playwright", "code": "code", "status": "approved",
    }
    data.update(overrides)
    return AutomationScript(**data)


def test_approved_script_with_no_metadata_is_not_blocked():
    assert execution_blocked_reason(_script()) is None


def test_draft_script_is_blocked_as_not_approved():
    reason = execution_blocked_reason(_script(status="draft"))
    assert reason == "Script is not approved for execution yet."


def test_needs_regeneration_status_gets_a_specific_reason():
    reason = execution_blocked_reason(_script(status="needs_regeneration"))
    assert reason is not None
    assert "regenerate" in reason.lower()


def test_ungrounded_elements_block_execution_even_if_approved():
    script = _script(metadata_={"grounding": {"grounded": True, "ungrounded_elements": ["Page.searchBar"]}})
    reason = execution_blocked_reason(script)
    assert reason is not None
    assert "Page.searchBar" in reason
    assert "1 element" in reason


def test_ungrounded_elements_list_is_truncated_with_a_count():
    elements = [f"Page.el{i}" for i in range(5)]
    script = _script(metadata_={"grounding": {"ungrounded_elements": elements}})
    reason = execution_blocked_reason(script)
    assert "+2 more" in reason


def test_failed_last_dry_run_blocks_execution():
    script = _script(metadata_={"last_dry_run": {"passed": False}})
    reason = execution_blocked_reason(script)
    assert reason is not None
    assert "dry run" in reason.lower()


def test_passing_last_dry_run_is_not_blocked():
    script = _script(metadata_={"grounding": {"ungrounded_elements": []}, "last_dry_run": {"passed": True}})
    assert execution_blocked_reason(script) is None


def test_dry_run_never_run_is_not_treated_as_a_failure():
    # last_dry_run absent entirely (e.g. externally authored script) is
    # unknown, not bad — must not be blocked just for lacking the metadata.
    script = _script(metadata_={})
    assert execution_blocked_reason(script) is None


def test_executed_status_is_treated_like_approved():
    assert execution_blocked_reason(_script(status="executed")) is None
