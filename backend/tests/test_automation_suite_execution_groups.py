"""Execution group splitting — pure planning, no DB."""
from types import SimpleNamespace

import pytest

from app.services.automation_suite.errors import AutomationSuiteError
from app.services.automation_suite.execution_groups import SPLIT_DIMENSIONS, plan_auto_split
from app.services.automation_suite.inheritance import MemberInheritance


def _member(
    member_id: int,
    *,
    framework: str | None = "playwright",
    environment: str | None = "SIT",
    application_key: str | None = "crm",
    application_id: int | None = 5,
    inclusion_status: str = "included",
) -> MemberInheritance:
    script = (
        SimpleNamespace(id=member_id * 10, framework=framework, status="approved", version=1)
        if framework
        else None
    )
    application = (
        SimpleNamespace(id=application_id, key=application_key, name="CRM", lifecycle_status="active", environment_urls={})
        if application_key
        else None
    )
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
            execution_group_id=None,
            planned_sequence=None,
        ),
        test_case=SimpleNamespace(id=member_id, status="approved", version=1, is_deleted=False, execution_mode="automation"),
        application=application,
        classification=None,
        model=None,
        model_is_stale=False,
        open_model_gaps=[],
        scripts=[script] if script else [],
        current_scripts=[script] if script else [],
        frameworks=frozenset([framework]) if framework else frozenset(),
        test_data=[],
        recordings=[],
        resolved_environment=environment,
        environment_source="suite_default" if environment else None,
        mandatory_capability_keys=(),
        drift_reasons=(),
    )


def test_split_by_framework_makes_one_group_per_framework():
    groups = plan_auto_split(
        [_member(1, framework="playwright"), _member(2, framework="pytest"), _member(3, framework="playwright")],
        dimension="framework",
    )
    assert len(groups) == 2
    by_name = {g.name: g for g in groups}
    assert set(by_name) == {"Framework: playwright", "Framework: pytest"}
    assert sorted(by_name["Framework: playwright"].member_ids) == [1, 3]
    assert by_name["Framework: playwright"].framework == "playwright"
    # Sequences are assigned so the groups have a deterministic order.
    assert sorted(g.sequence for g in groups) == [1, 2]


def test_a_member_without_a_script_lands_in_an_unmapped_group():
    groups = plan_auto_split(
        [_member(1, framework="playwright"), _member(2, framework=None)], dimension="framework"
    )
    names = {g.name for g in groups}
    assert "Framework: unmapped" in names
    unmapped = next(g for g in groups if g.name == "Framework: unmapped")
    # The label is honest and the group carries no invented framework.
    assert unmapped.framework is None
    assert unmapped.member_ids == (2,)


def test_split_by_environment():
    groups = plan_auto_split(
        [_member(1, environment="SIT"), _member(2, environment="UAT"), _member(3, environment=None)],
        dimension="environment",
    )
    names = {g.name for g in groups}
    assert names == {"Environment: SIT", "Environment: UAT", "Environment: unresolved"}
    assert next(g for g in groups if g.name == "Environment: unresolved").environment is None


def test_split_by_application():
    groups = plan_auto_split(
        [_member(1, application_key="crm", application_id=5), _member(2, application_key="oms", application_id=6)],
        dimension="application",
    )
    assert {g.application_id for g in groups} == {5, 6}


def test_excluded_members_are_not_grouped():
    groups = plan_auto_split(
        [_member(1, framework="playwright"), _member(2, framework="pytest", inclusion_status="excluded")],
        dimension="framework",
    )
    assert len(groups) == 1
    assert groups[0].member_ids == (1,)


def test_manual_only_members_are_still_grouped():
    """A manual group is a real grouping decision, not an omission."""
    groups = plan_auto_split(
        [_member(1, framework="playwright"), _member(2, framework=None, inclusion_status="manual_only")],
        dimension="framework",
    )
    assert len(groups) == 2


def test_an_unknown_dimension_is_rejected():
    with pytest.raises(AutomationSuiteError) as exc:
        plan_auto_split([_member(1)], dimension="priority")
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "UNKNOWN_SPLIT_DIMENSION"


def test_no_eligible_members_plans_no_groups():
    assert plan_auto_split([_member(1, inclusion_status="excluded")], dimension="framework") == []


def test_every_declared_dimension_is_supported():
    for dimension in SPLIT_DIMENSIONS:
        assert plan_auto_split([_member(1)], dimension=dimension)
