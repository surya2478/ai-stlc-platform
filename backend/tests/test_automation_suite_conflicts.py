"""Cross-member conflict detection — the capability suite scope adds."""
from types import SimpleNamespace

from app.services.automation_suite.conflicts import detect_cross_member_conflicts
from app.services.automation_suite.inheritance import MemberInheritance, SuiteInheritance


def _member(
    member_id: int,
    *,
    frameworks=("playwright",),
    environment="SIT",
    inclusion_status="included",
    execution_mode="automation",
) -> MemberInheritance:
    scripts = [
        SimpleNamespace(id=member_id * 10 + i, framework=f, status="approved", version=1)
        for i, f in enumerate(frameworks)
    ]
    return MemberInheritance(
        member=SimpleNamespace(
            id=member_id,
            test_case_id=member_id,
            inclusion_status=inclusion_status,
            last_evaluated_at=None,
            source_test_case_version=0,
            resolved_classification_id=None,
            resolved_application_id=None,
            resolved_model_id=None,
        ),
        test_case=SimpleNamespace(id=member_id, status="approved", version=1, is_deleted=False, execution_mode=execution_mode),
        application=SimpleNamespace(id=5, name="CRM", lifecycle_status="active", environment_urls={"SIT": "u"}),
        classification=None,
        model=None,
        model_is_stale=False,
        open_model_gaps=[],
        scripts=scripts,
        current_scripts=scripts,
        frameworks=frozenset(frameworks),
        test_data=[],
        recordings=[],
        resolved_environment=environment,
        environment_source="suite_default" if environment else None,
        mandatory_capability_keys=(),
        drift_reasons=(),
    )


def _types(conflicts):
    return {c.gap_type for c in conflicts}


def test_no_conflicts_when_members_agree():
    suite = SuiteInheritance(members=[_member(1), _member(2)])
    assert detect_cross_member_conflicts(suite) == []


def test_two_frameworks_across_members_is_critical():
    suite = SuiteInheritance(members=[_member(1, frameworks=("playwright",)), _member(2, frameworks=("pytest",))])
    conflicts = detect_cross_member_conflicts(suite)
    conflict = next(c for c in conflicts if c.gap_type == "MULTIPLE_FRAMEWORKS" and c.scope == "suite")
    assert conflict.severity == "critical"
    assert conflict.category == "conflict"
    assert sorted(conflict.evidence["frameworks"]) == ["playwright", "pytest"]
    assert conflict.evidence["frameworks"]["playwright"] == [1]


def test_one_member_spanning_two_frameworks_is_a_member_conflict():
    suite = SuiteInheritance(members=[_member(1, frameworks=("playwright", "pytest"))])
    conflicts = detect_cross_member_conflicts(suite)
    conflict = next(c for c in conflicts if c.scope == "member")
    assert conflict.gap_type == "MULTIPLE_FRAMEWORKS"
    assert conflict.member_id == 1
    assert conflict.severity == "critical"


def test_two_environments_is_critical():
    suite = SuiteInheritance(members=[_member(1, environment="SIT"), _member(2, environment="UAT")])
    conflict = next(c for c in detect_cross_member_conflicts(suite) if c.gap_type == "MULTIPLE_ENVIRONMENTS")
    assert conflict.severity == "critical"
    assert conflict.evidence["environments"] == ["SIT", "UAT"]


def test_an_unresolved_environment_is_not_a_second_environment():
    suite = SuiteInheritance(members=[_member(1, environment="SIT"), _member(2, environment=None)])
    assert "MULTIPLE_ENVIRONMENTS" not in _types(detect_cross_member_conflicts(suite))


def test_mixed_execution_modes_is_a_warning():
    suite = SuiteInheritance(
        members=[_member(1, execution_mode="automation"), _member(2, execution_mode="manual")]
    )
    conflict = next(c for c in detect_cross_member_conflicts(suite) if c.gap_type == "MIXED_MANUAL_AUTOMATED")
    assert conflict.severity == "warning"


def test_excluded_members_never_contribute_a_conflict():
    suite = SuiteInheritance(
        members=[
            _member(1, frameworks=("playwright",), environment="SIT"),
            _member(2, frameworks=("pytest",), environment="UAT", inclusion_status="excluded"),
        ]
    )
    assert detect_cross_member_conflicts(suite) == []


def test_manual_only_members_do_not_create_framework_conflicts():
    suite = SuiteInheritance(
        members=[
            _member(1, frameworks=("playwright",)),
            _member(2, frameworks=("pytest",), inclusion_status="manual_only"),
        ]
    )
    assert "MULTIPLE_FRAMEWORKS" not in _types(detect_cross_member_conflicts(suite))


def test_unsupported_pairing_is_never_raised():
    """No pairing matrix exists in this repo, so the type must stay unraised."""
    suite = SuiteInheritance(members=[_member(1), _member(2)])
    assert "UNSUPPORTED_FRAMEWORK_APPLICATION" not in _types(detect_cross_member_conflicts(suite))
