"""Gap sync planning — the upsert-and-auto-close contract.

The retired engine deleted and rebuilt its blockers every evaluation. These
tests pin the behaviour that replaced it, because a regression here would
silently discard an approved exception.
"""
from types import SimpleNamespace

from app.services.automation_suite.gaps import DetectedGap, fingerprint, plan_gap_sync


def _detected(gap_type="LOCATOR_MISSING", *, member_id=1, evidence=None, severity="critical", subject="model:9"):
    return DetectedGap(
        gap_type=gap_type,
        scope="member",
        category="gap",
        severity=severity,
        stage="grounding",
        reason="reason",
        remediation="fix it",
        evidence=evidence or {},
        member_id=member_id,
        test_case_id=10,
        subject=subject,
    )


def _existing(detected, *, status="open", auto_closed=False):
    return SimpleNamespace(
        id=1,
        fingerprint=fingerprint(detected),
        status=status,
        auto_closed=auto_closed,
        gap_type=detected.gap_type,
        severity=detected.severity,
        reason="stale reason",
        remediation=None,
        evidence={},
        resolved_by=7,
        resolved_at="earlier",
        last_detected_at=None,
        suite_test_case_id=detected.member_id,
    )


def test_a_new_finding_is_inserted():
    plan = plan_gap_sync([], [_detected()])
    assert len(plan.to_insert) == 1
    assert plan.to_update == [] and plan.to_auto_close == []


def test_a_still_present_finding_is_updated_not_duplicated():
    detected = _detected()
    plan = plan_gap_sync([_existing(detected)], [detected])
    assert plan.to_insert == []
    assert len(plan.to_update) == 1


def test_a_disappeared_finding_is_auto_closed_never_deleted():
    detected = _detected()
    plan = plan_gap_sync([_existing(detected)], [])
    assert len(plan.to_auto_close) == 1
    assert plan.to_insert == [] and plan.to_update == []


def test_a_reappearing_finding_is_reopened():
    detected = _detected()
    plan = plan_gap_sync([_existing(detected, status="resolved", auto_closed=True)], [detected])
    assert len(plan.to_reopen) == 1
    assert plan.to_insert == []


def test_an_approved_exception_survives_re_detection_and_stops_blocking():
    detected = _detected()
    row = _existing(detected, status="exception_approved")
    plan = plan_gap_sync([row], [detected])
    assert len(plan.to_leave_adjudicated) == 1
    assert plan.to_update == [] and plan.to_reopen == []
    # The waived finding must not count against readiness.
    assert fingerprint(detected) not in plan.blocking_fingerprints


def test_an_excluded_finding_also_stops_blocking():
    detected = _detected()
    plan = plan_gap_sync([_existing(detected, status="excluded")], [detected])
    assert len(plan.to_leave_adjudicated) == 1
    assert plan.blocking_fingerprints == set()


def test_fingerprint_ignores_churning_evidence():
    """A model rebuild changes the gap-id list but not the finding's identity."""
    first = _detected(evidence={"gap_ids": [1, 2]})
    second = _detected(evidence={"gap_ids": [7, 8, 9]})
    assert fingerprint(first) == fingerprint(second)

    plan = plan_gap_sync([_existing(first)], [second])
    assert plan.to_insert == []
    assert len(plan.to_update) == 1


def test_fingerprints_differ_across_members_and_types():
    assert fingerprint(_detected(member_id=1)) != fingerprint(_detected(member_id=2))
    assert fingerprint(_detected(gap_type="LOCATOR_MISSING")) != fingerprint(
        _detected(gap_type="MODEL_NOT_APPROVED")
    )


def test_open_findings_are_blocking():
    detected = _detected()
    plan = plan_gap_sync([], [detected])
    assert fingerprint(detected) in plan.blocking_fingerprints
