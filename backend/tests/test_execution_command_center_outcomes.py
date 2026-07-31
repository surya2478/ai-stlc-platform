"""UI-046 outcome classification and evidence quorum.

Covers all eight outcomes plus SKIPPED, the precedence between them, and the two
Phase 1 exit criteria this module is responsible for: a green runner cannot pass
without a proven assertion, and missing mandatory evidence yields INCONCLUSIVE.
"""
from __future__ import annotations

import pytest

from app.services.execution_command_center.outcomes import (
    AssertionFact,
    EvidenceFact,
    ItemFacts,
    classify_item,
    classify_run,
    evidence_quorum,
)


def _passing_assertion(mandatory: bool = True) -> AssertionFact:
    return AssertionFact(mandatory=mandatory, passed=True)


def _captured(evidence_type: str = "screenshot", mandatory: bool = True) -> EvidenceFact:
    return EvidenceFact(evidence_type=evidence_type, mandatory=mandatory, status="captured")


def _clean_pass_facts(**overrides) -> ItemFacts:
    base = dict(
        runner_status="pass",
        assertions=(_passing_assertion(),),
        evidence=(_captured(),),
    )
    base.update(overrides)
    return ItemFacts(**base)


# ── The happy path, so the negative cases below mean something ──────────────


def test_proven_assertions_captured_evidence_and_green_runner_pass():
    assert classify_item(_clean_pass_facts()).result == "PASS"


def test_pass_has_no_attention_reason():
    assert classify_item(_clean_pass_facts()).attention_reason is None


# ── Section 14.11: a green runner is not a pass ──────────────────────────────


def test_green_runner_with_no_assertions_is_inconclusive_not_pass():
    """The single most important rule in this module."""
    result = classify_item(ItemFacts(runner_status="pass", assertions=(), evidence=()))
    assert result.result == "INCONCLUSIVE"
    assert "proves nothing" in result.attention_reason


def test_unevaluated_mandatory_assertion_is_inconclusive():
    facts = _clean_pass_facts(assertions=(AssertionFact(mandatory=True, passed=None),))
    result = classify_item(facts)
    assert result.result == "INCONCLUSIVE"
    assert "never evaluated" in result.attention_reason


def test_optional_assertions_alone_cannot_produce_a_pass():
    """Only mandatory assertions can prove anything."""
    facts = _clean_pass_facts(assertions=(AssertionFact(mandatory=False, passed=True),))
    assert classify_item(facts).result == "INCONCLUSIVE"


def test_proven_assertions_without_a_runner_verdict_are_inconclusive():
    facts = _clean_pass_facts(runner_status=None)
    result = classify_item(facts)
    assert result.result == "INCONCLUSIVE"
    assert "never reported a verdict" in result.attention_reason


# ── Section 14.12: missing evidence produces INCONCLUSIVE ───────────────────


def test_missing_mandatory_evidence_is_inconclusive_despite_passing_assertions():
    facts = _clean_pass_facts(
        evidence=(EvidenceFact("screenshot", mandatory=True, status="pending"),)
    )
    result = classify_item(facts)
    assert result.result == "INCONCLUSIVE"
    assert "screenshot" in result.attention_reason


def test_unavailable_mandatory_evidence_is_inconclusive():
    facts = _clean_pass_facts(
        evidence=(EvidenceFact("trace", mandatory=True, status="unavailable"),)
    )
    assert classify_item(facts).result == "INCONCLUSIVE"


def test_missing_optional_evidence_does_not_block_a_pass():
    facts = _clean_pass_facts(
        evidence=(
            _captured("screenshot"),
            EvidenceFact("video", mandatory=False, status="unavailable"),
        )
    )
    assert classify_item(facts).result == "PASS"


# ── Section 10: infrastructure failure is never an application FAIL ─────────


def test_automation_failure_is_not_a_fail():
    facts = _clean_pass_facts(automation_failure_reason="Runner could not start: npx not found")
    result = classify_item(facts)
    assert result.result == "AUTOMATION_FAILURE"
    assert result.result != "FAIL"


def test_runner_error_status_is_automation_failure_not_fail():
    """An errored test threw; it did not assert a false expectation."""
    facts = _clean_pass_facts(runner_status="error")
    assert classify_item(facts).result == "AUTOMATION_FAILURE"


def test_environment_failure_outranks_a_failed_assertion():
    """If the environment broke, we do not know the product misbehaved."""
    facts = ItemFacts(
        environment_failure_reason="CRM Web returned 503",
        runner_status="fail",
        assertions=(AssertionFact(mandatory=True, passed=False),),
    )
    assert classify_item(facts).result == "ENVIRONMENT_FAILURE"


def test_data_failure_is_classified_separately():
    facts = _clean_pass_facts(data_failure_reason="No unallocated ICCID in the reserved pool")
    assert classify_item(facts).result == "DATA_FAILURE"


def test_policy_blocked_outranks_everything():
    facts = ItemFacts(
        policy_blocked_reason="Member is not FINAL_APPROVED",
        blocked_reason="No runner for framework 'katalon'",
        environment_failure_reason="down",
        data_failure_reason="missing",
        automation_failure_reason="crashed",
        runner_status="fail",
    )
    assert classify_item(facts).result == "POLICY_BLOCKED"


def test_blocked_reason_produces_blocked():
    facts = ItemFacts(blocked_reason="No runner registered for framework 'katalon'")
    result = classify_item(facts)
    assert result.result == "BLOCKED"
    assert "katalon" in result.attention_reason


def test_runner_blocked_status_produces_blocked():
    assert classify_item(ItemFacts(runner_status="blocked")).result == "BLOCKED"


def test_runner_skip_produces_skipped():
    assert classify_item(ItemFacts(runner_status="skip")).result == "SKIPPED"


# ── The one genuine application verdict ─────────────────────────────────────


def test_failed_mandatory_assertion_is_fail():
    facts = _clean_pass_facts(
        runner_status="fail", assertions=(AssertionFact(mandatory=True, passed=False),)
    )
    result = classify_item(facts)
    assert result.result == "FAIL"
    assert "1 mandatory assertion(s) failed" in result.attention_reason


def test_fail_outranks_missing_evidence():
    """We know the product misbehaved whether or not every artifact landed."""
    facts = ItemFacts(
        runner_status="fail",
        assertions=(AssertionFact(mandatory=True, passed=False),),
        evidence=(EvidenceFact("screenshot", mandatory=True, status="unavailable"),),
    )
    assert classify_item(facts).result == "FAIL"


def test_failing_runner_with_declared_assertions_is_fail():
    """Playwright fails the test when a web-first assertion fails, but its
    reporter does not say which one — the verdict still has to be FAIL."""
    facts = _clean_pass_facts(
        runner_status="fail",
        assertions=(AssertionFact(mandatory=True, passed=None),),
    )
    result = classify_item(facts)
    assert result.result == "FAIL"
    assert "not attributable" in result.attention_reason


def test_failing_runner_with_no_assertions_is_inconclusive_not_fail():
    """The failure cannot be attributed to a business expectation."""
    facts = ItemFacts(runner_status="fail", assertions=(), evidence=())
    result = classify_item(facts)
    assert result.result == "INCONCLUSIVE"
    assert "cannot be attributed" in result.attention_reason


def test_every_outcome_is_reachable():
    """Guards against a precedence edit silently orphaning a branch."""
    reached = {
        classify_item(f).result
        for f in (
            _clean_pass_facts(),
            _clean_pass_facts(
                runner_status="fail", assertions=(AssertionFact(True, False),)
            ),
            ItemFacts(runner_status="pass"),
            ItemFacts(blocked_reason="no runner"),
            ItemFacts(environment_failure_reason="503"),
            ItemFacts(data_failure_reason="no data"),
            ItemFacts(automation_failure_reason="crash"),
            ItemFacts(policy_blocked_reason="not approved"),
            ItemFacts(runner_status="skip"),
        )
    }
    assert reached == {
        "PASS",
        "FAIL",
        "INCONCLUSIVE",
        "BLOCKED",
        "ENVIRONMENT_FAILURE",
        "DATA_FAILURE",
        "AUTOMATION_FAILURE",
        "POLICY_BLOCKED",
        "SKIPPED",
    }


# ── Quorum ──────────────────────────────────────────────────────────────────


def test_quorum_counts_only_mandatory_evidence():
    verdict = evidence_quorum(
        [
            _captured("screenshot"),
            EvidenceFact("video", mandatory=False, status="pending"),
        ]
    )
    assert verdict.met is True
    assert verdict.required == 1
    assert verdict.captured == 1


def test_quorum_lists_each_missing_type_once():
    verdict = evidence_quorum(
        [
            EvidenceFact("api", mandatory=True, status="pending"),
            EvidenceFact("api", mandatory=True, status="unavailable"),
            EvidenceFact("trace", mandatory=True, status="pending"),
        ]
    )
    assert verdict.met is False
    assert verdict.missing == ("api", "trace")
    assert "api, trace" in verdict.reason


def test_quorum_with_no_mandatory_evidence_is_trivially_met():
    """Correct, not lenient — the assertion rule is what stops a false pass."""
    assert evidence_quorum([]).met is True


# ── Run rollup ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "items,expected",
    [
        (["PASS", "PASS"], "PASS"),
        (["PASS", "SKIPPED"], "PASS"),
        (["PASS", "FAIL"], "FAIL"),
        (["PASS", "INCONCLUSIVE"], "INCONCLUSIVE"),
        # Infrastructure outranks an application failure at run level too.
        (["FAIL", "ENVIRONMENT_FAILURE"], "ENVIRONMENT_FAILURE"),
        (["FAIL", "POLICY_BLOCKED"], "POLICY_BLOCKED"),
        # BLOCKED sits above FAIL: a suite where a prerequisite was unsatisfiable
        # is not adequately described by one of its tests failing.
        (["BLOCKED", "FAIL"], "BLOCKED"),
        (["AUTOMATION_FAILURE", "BLOCKED"], "AUTOMATION_FAILURE"),
    ],
)
def test_run_rollup_precedence(items, expected):
    assert classify_run(items) == expected


def test_empty_run_is_inconclusive_not_pass():
    assert classify_run([]) == "INCONCLUSIVE"


def test_all_skipped_run_is_inconclusive():
    assert classify_run(["SKIPPED", "SKIPPED"]) == "INCONCLUSIVE"


def test_run_with_pending_items_is_inconclusive():
    assert classify_run(["PASS", "PENDING"]) == "INCONCLUSIVE"
