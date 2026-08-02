"""Per-member readiness — pure, so no DB fake is needed.

The first four tests are parity ports of the retired per-test-case engine's
tests, so a behaviour change during the move to suite scope would fail here.
"""
from types import SimpleNamespace

from app.services.automation_suite.inheritance import MemberInheritance
from app.services.automation_suite.readiness import evaluate_member
from app.services.test_classification.capability_resolver import CapabilityStatus


def _member(**overrides):
    return SimpleNamespace(
        id=overrides.pop("member_id", 1),
        test_case_id=overrides.pop("test_case_id", 10),
        inclusion_status=overrides.pop("inclusion_status", "included"),
        last_evaluated_at=overrides.pop("last_evaluated_at", None),
        source_test_case_version=overrides.pop("source_test_case_version", 0),
        resolved_classification_id=overrides.pop("resolved_classification_id", None),
        resolved_application_id=overrides.pop("resolved_application_id", None),
        resolved_model_id=overrides.pop("resolved_model_id", None),
    )


def _inheritance(**overrides) -> MemberInheritance:
    """A fully ready member; each test degrades exactly one thing."""
    member = overrides.pop("member", None) or _member(
        inclusion_status=overrides.pop("inclusion_status", "included")
    )
    test_case = overrides.pop(
        "test_case", SimpleNamespace(id=10, status="approved", version=3, is_deleted=False, execution_mode="automation")
    )
    application = overrides.pop(
        "application",
        SimpleNamespace(id=5, name="CRM", lifecycle_status="active", environment_urls={"SIT": "https://sit"}),
    )
    classification = overrides.pop(
        "classification",
        SimpleNamespace(
            id=7,
            review_status="APPROVED",
            candidate_status="RECOMMENDED",
            test_case_version=3,
            primary_adapter="PLAYWRIGHT_MCP",
            mandatory_validators=[],
        ),
    )
    model = overrides.pop("model", SimpleNamespace(id=9, status="approved", version=2, source_session_id=4))
    script = overrides.pop(
        "script", SimpleNamespace(id=11, framework="playwright", status="approved", version=1)
    )
    scripts = overrides.pop("scripts", [script] if script else [])
    current_scripts = overrides.pop("current_scripts", scripts)

    defaults = dict(
        member=member,
        test_case=test_case,
        application=application,
        classification=classification,
        model=model,
        model_is_stale=False,
        open_model_gaps=[],
        scripts=scripts,
        current_scripts=current_scripts,
        frameworks=frozenset(s.framework for s in current_scripts if s.framework),
        test_data=[SimpleNamespace(id=1, environment="SIT", approval_status="approved")],
        recordings=[],
        resolved_environment="SIT",
        environment_source="suite_default",
        mandatory_capability_keys=("PLAYWRIGHT_MCP",),
        drift_reasons=(),
    )
    defaults.update(overrides)
    return MemberInheritance(**defaults)


_CONNECTED = {
    "PLAYWRIGHT_MCP": CapabilityStatus(
        key="PLAYWRIGHT_MCP", maturity="REAL", mcp_connection_id=1, detail="connected"
    )
}


def _types(evaluation):
    return {g.gap_type for g in evaluation.gaps}


def test_fully_ready_member_passes_every_check():
    evaluation = evaluate_member(_inheritance(), capability_status=_CONNECTED)
    assert evaluation.member_status == "READY"
    assert evaluation.gaps == []
    assert evaluation.checks_passed == evaluation.checks_total
    assert evaluation.checks_total > 0


def test_unapproved_test_case_blocks_the_member():
    inh = _inheritance(
        test_case=SimpleNamespace(id=10, status="draft", version=3, is_deleted=False, execution_mode="automation")
    )
    evaluation = evaluate_member(inh, capability_status=_CONNECTED)
    assert evaluation.member_status == "BLOCKED"
    gap = next(g for g in evaluation.gaps if g.gap_type == "TEST_CASE_NOT_APPROVED")
    assert gap.severity == "critical"
    assert gap.stage == "test_intent"
    assert "'draft'" in gap.reason


def test_unavailable_mandatory_mcp_blocks_and_names_the_key():
    unavailable = {
        "OMS_MCP": CapabilityStatus(
            key="OMS_MCP", maturity="NOT_CONFIGURED", mcp_connection_id=None, detail="registered but not connected"
        )
    }
    inh = _inheritance(mandatory_capability_keys=("OMS_MCP",))
    evaluation = evaluate_member(inh, capability_status=unavailable)
    assert evaluation.member_status == "BLOCKED"
    gap = next(g for g in evaluation.gaps if g.gap_type == "MANDATORY_MCP_UNAVAILABLE")
    assert "OMS_MCP" in gap.reason
    assert gap.evidence["unavailable_keys"] == ["OMS_MCP"]


def test_missing_application_skips_the_model_checks():
    inh = _inheritance(application=None, model=None)
    evaluation = evaluate_member(inh, capability_status=_CONNECTED)
    types = _types(evaluation)
    assert "APPLICATION_MAPPING_MISSING" in types
    assert "ENVIRONMENT_NOT_READY" in types
    # No application means no model to judge — reporting on one would be noise.
    assert "MODEL_NOT_APPROVED" not in types


def test_classification_severity_splits_on_the_decision():
    rejected = _inheritance(
        classification=SimpleNamespace(
            id=7, review_status="REJECTED", candidate_status="NOT_RECOMMENDED", test_case_version=3,
            primary_adapter=None, mandatory_validators=[],
        ),
        mandatory_capability_keys=(),
    )
    assert next(
        g for g in evaluate_member(rejected, capability_status={}).gaps
        if g.gap_type == "CLASSIFICATION_NOT_APPROVED"
    ).severity == "critical"

    pending = _inheritance(
        classification=SimpleNamespace(
            id=7, review_status="PENDING", candidate_status="RECOMMENDED", test_case_version=3,
            primary_adapter=None, mandatory_validators=[],
        ),
        mandatory_capability_keys=(),
    )
    assert next(
        g for g in evaluate_member(pending, capability_status={}).gaps
        if g.gap_type == "CLASSIFICATION_NOT_APPROVED"
    ).severity == "warning"


def test_missing_classification_is_critical():
    inh = _inheritance(classification=None, mandatory_capability_keys=())
    gap = next(
        g for g in evaluate_member(inh, capability_status={}).gaps
        if g.gap_type == "CLASSIFICATION_NOT_APPROVED"
    )
    assert gap.severity == "critical"
    assert "No automation classification" in gap.reason


def test_policy_stale_when_test_case_moved_past_the_classification():
    inh = _inheritance(
        classification=SimpleNamespace(
            id=7, review_status="APPROVED", candidate_status="APPROVED", test_case_version=2,
            primary_adapter="PLAYWRIGHT_MCP", mandatory_validators=[],
        )
    )
    gap = next(g for g in evaluate_member(inh, capability_status=_CONNECTED).gaps if g.gap_type == "POLICY_STALE")
    assert gap.severity == "warning"
    assert "version 2" in gap.reason and "version 3" in gap.reason


def test_stale_model_is_a_warning_not_a_blocker():
    evaluation = evaluate_member(_inheritance(model_is_stale=True), capability_status=_CONNECTED)
    assert evaluation.member_status == "WARNING"
    assert next(g for g in evaluation.gaps if g.gap_type == "MODEL_STALE").severity == "warning"


def _model_gap(gap_id, gap_type, severity):
    return SimpleNamespace(id=gap_id, gap_type=gap_type, severity=severity)


def test_locator_gaps_split_critical_from_ambiguous():
    critical = _inheritance(
        open_model_gaps=[
            _model_gap(1, "MISSING_ELEMENT", "critical"),
            _model_gap(2, "UNSTABLE_LOCATOR", "warning"),
        ]
    )
    evaluation = evaluate_member(critical, capability_status=_CONNECTED)
    missing = next(g for g in evaluation.gaps if g.gap_type == "LOCATOR_MISSING")
    ambiguous = next(g for g in evaluation.gaps if g.gap_type == "LOCATOR_AMBIGUOUS")
    assert missing.severity == "critical"
    assert ambiguous.severity == "warning"
    # Fingerprint identity keys on the model, not the churning gap-id list.
    assert missing.subject == "model:9"
    assert missing.evidence["gap_ids"] == [1]


# ── The suite honours the model's severity ──────────────────────────────────
#
# Observed on a real suite: the Application Model showed "2 gaps, 0 critical"
# and sat approved, while the suite built from it reported "Critical Gaps 4"
# over those same two gaps and refused submission — and its own findings table
# listed every one of them as Warning. The suite was partitioning by gap_type
# alone, so any MISSING_* gap counted as critical regardless of what the model
# had recorded.


def test_a_warning_severity_missing_gap_does_not_block_the_suite():
    """The exact contradiction: a MISSING_COMPONENT the model recorded as a
    warning must not become a suite-blocking critical."""
    inh = _inheritance(open_model_gaps=[_model_gap(1, "MISSING_COMPONENT", "warning")])
    evaluation = evaluate_member(inh, capability_status=_CONNECTED)

    missing = next(g for g in evaluation.gaps if g.gap_type == "LOCATOR_MISSING")
    assert missing.severity == "warning"
    assert evaluation.member_status == "WARNING"


def test_a_critical_missing_gap_still_blocks():
    """The control has to keep working — this is not a general relaxation."""
    inh = _inheritance(open_model_gaps=[_model_gap(1, "MISSING_SCREEN", "critical")])
    evaluation = evaluate_member(inh, capability_status=_CONNECTED)

    assert next(g for g in evaluation.gaps if g.gap_type == "LOCATOR_MISSING").severity == "critical"
    assert evaluation.member_status == "BLOCKED"


def test_one_critical_among_warnings_still_blocks():
    """Severity is taken from the worst gap in the group, not the first."""
    inh = _inheritance(open_model_gaps=[
        _model_gap(1, "MISSING_COMPONENT", "warning"),
        _model_gap(2, "MISSING_ELEMENT", "critical"),
        _model_gap(3, "MISSING_COMPONENT", "warning"),
    ])
    evaluation = evaluate_member(inh, capability_status=_CONNECTED)

    missing = next(g for g in evaluation.gaps if g.gap_type == "LOCATOR_MISSING")
    assert missing.severity == "critical"
    assert "3 missing" in missing.reason and "1 critical" in missing.reason
    assert evaluation.member_status == "BLOCKED"


def test_an_ambiguous_gap_escalated_by_the_model_is_honoured_too():
    """Severity flows in both directions — the model may decide an unstable
    locator is critical for a given application."""
    inh = _inheritance(open_model_gaps=[_model_gap(1, "UNSTABLE_LOCATOR", "critical")])
    evaluation = evaluate_member(inh, capability_status=_CONNECTED)

    assert next(g for g in evaluation.gaps if g.gap_type == "LOCATOR_AMBIGUOUS").severity == "critical"
    assert evaluation.member_status == "BLOCKED"


def test_a_model_with_only_warning_gaps_matches_its_own_verdict():
    """End state of the bug: model says approvable, suite agrees."""
    inh = _inheritance(open_model_gaps=[
        _model_gap(1, "MISSING_COMPONENT", "warning"),
        _model_gap(2, "UNSTABLE_LOCATOR", "warning"),
    ])
    evaluation = evaluate_member(inh, capability_status=_CONNECTED)

    assert not [g for g in evaluation.gaps if g.severity == "critical"]
    assert evaluation.member_status == "WARNING"


def test_unresolved_environment_is_reported_without_counting_a_check():
    resolved = evaluate_member(_inheritance(), capability_status=_CONNECTED)
    unresolved = evaluate_member(
        _inheritance(resolved_environment=None, environment_source=None), capability_status=_CONNECTED
    )
    assert "ENVIRONMENT_UNRESOLVED" in _types(unresolved)
    assert "ENVIRONMENT_NOT_READY" not in _types(unresolved)
    # The environment check is skipped rather than failed.
    assert unresolved.checks_total == resolved.checks_total - 1
    assert unresolved.member_status == "WARNING"


def test_environment_without_a_configured_url_is_blocked():
    inh = _inheritance(
        application=SimpleNamespace(id=5, name="CRM", lifecycle_status="active", environment_urls={"QA": "https://qa"})
    )
    evaluation = evaluate_member(inh, capability_status=_CONNECTED)
    assert evaluation.member_status == "BLOCKED"
    assert "SIT" in next(g for g in evaluation.gaps if g.gap_type == "ENVIRONMENT_NOT_READY").reason


def test_manual_only_member_skips_the_automation_checks():
    inh = _inheritance(member=_member(inclusion_status="manual_only"), model=None, application=None)
    evaluation = evaluate_member(inh, capability_status={})
    types = _types(evaluation)
    assert types == set()
    assert evaluation.member_status == "READY"


def test_deleted_test_case_short_circuits_everything():
    inh = _inheritance(
        test_case=SimpleNamespace(id=10, status="approved", version=3, is_deleted=True, execution_mode="automation")
    )
    evaluation = evaluate_member(inh, capability_status=_CONNECTED)
    assert _types(evaluation) == {"TEST_CASE_DELETED"}
    assert evaluation.member_status == "BLOCKED"


def test_missing_script_and_test_data_are_warnings_only():
    inh = _inheritance(script=None, scripts=[], current_scripts=[], test_data=[])
    evaluation = evaluate_member(inh, capability_status=_CONNECTED)
    types = _types(evaluation)
    assert "SCRIPT_MISSING" in types
    assert "TEST_DATA_MISSING" in types
    # A draft suite legitimately has no assets yet.
    assert evaluation.member_status == "WARNING"


def test_all_scripts_deprecated_reports_the_deprecation():
    deprecated = SimpleNamespace(id=11, framework="playwright", status="deprecated", version=1)
    inh = _inheritance(scripts=[deprecated], current_scripts=[])
    types = _types(evaluate_member(inh, capability_status=_CONNECTED))
    assert "SCRIPT_DEPRECATED" in types


def test_waiving_a_member_s_criticals_stops_it_reading_as_blocked():
    """A member cannot stay BLOCKED once its blockers are waived.

    The suite would otherwise report READY_FOR_VALIDATION while its members
    reported BLOCKED, which contradicts itself.
    """
    from app.services.automation_suite.gaps import fingerprint

    # Unapproved (critical) and missing test data (warning) together.
    inh = _inheritance(
        test_case=SimpleNamespace(id=10, status="draft", version=3, is_deleted=False, execution_mode="automation"),
        test_data=[],
    )
    evaluation = evaluate_member(inh, capability_status=_CONNECTED)
    assert evaluation.member_status == "BLOCKED"
    assert {g.severity for g in evaluation.gaps} == {"critical", "warning"}

    # Nothing is blocking any more: every finding was adjudicated.
    assert evaluation.effective_status(set()) == "READY"

    # Only the warning survives as blocking.
    warnings_only = {
        fingerprint(g) for g in evaluation.gaps if g.severity == "warning"
    }
    assert evaluation.effective_status(warnings_only) == "WARNING"

    # Everything still blocking leaves it BLOCKED.
    everything = {fingerprint(g) for g in evaluation.gaps}
    assert evaluation.effective_status(everything) == "BLOCKED"


def test_drift_is_reported_as_a_source_change():
    inh = _inheritance(drift_reasons=("Test case is now version 4, evaluated against version 3.",))
    gap = next(
        g for g in evaluate_member(inh, capability_status=_CONNECTED).gaps
        if g.gap_type == "SOURCE_TEST_CASE_CHANGED"
    )
    assert "version 4" in gap.reason
