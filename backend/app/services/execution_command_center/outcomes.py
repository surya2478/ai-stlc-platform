"""Deterministic outcome classification and the evidence quorum rule.

The tracker's P1-S7 checklist requires eight outcomes, and two of its Phase 1
exit criteria are really statements about this module:

* "No action is generated without grounding evidence" — a PASS is impossible
  here without at least one mandatory assertion actually evaluated and passed.
  Contract Section 14.11 states it directly: no test is marked PASS because only
  the UI step succeeded. A script that navigated happily and asserted nothing is
  INCONCLUSIVE, not PASS.

* "Missing evidence produces INCONCLUSIVE" — enforced by `evidence_quorum`
  below, off the persisted evidence rows rather than off the runner's opinion.

The other load-bearing rule is contract Section 10's: an infrastructure error
must never become an application FAIL. That is why classification runs as an
ordered precedence rather than a set of independent tests — the infrastructure
outcomes are checked *before* the application verdict is even considered, so a
broken environment cannot be reported as a defect in the product under test.

Everything here is a pure function over already-collected facts. No I/O, no
runner calls, no database — which is what makes all eight branches testable
without an execution.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AssertionFact:
    """One assertion's evaluated state, as persisted."""

    mandatory: bool
    # None means never evaluated. That is not the same as failing, and the
    # difference decides PASS vs INCONCLUSIVE.
    passed: bool | None


@dataclass(slots=True)
class EvidenceFact:
    """One evidence row's state, as persisted."""

    evidence_type: str
    mandatory: bool
    status: str  # pending | captured | unavailable


@dataclass(slots=True)
class QuorumVerdict:
    met: bool
    required: int
    captured: int
    missing: tuple[str, ...]

    @property
    def reason(self) -> str | None:
        if self.met:
            return None
        if not self.missing:
            return "Mandatory evidence has not been captured."
        return (
            "Mandatory evidence missing: "
            + ", ".join(self.missing)
            + "."
        )


def evidence_quorum(evidence: list[EvidenceFact]) -> QuorumVerdict:
    """Minimum-present quorum: every mandatory artifact must be captured.

    This is the scoped-slice rule the UI-046 contract records in Section 2.1.12.
    A journey-specific weighted quorum (where, say, two of three backend
    artifacts suffice) is deliberately not implemented — there is no per-journey
    evidence policy to read it from, and inventing one would be a fabricated
    business rule.

    A run with no mandatory evidence declared has a trivially met quorum. That is
    correct rather than lenient: it is `classify_item`'s assertion rule, not the
    quorum, that stops an unasserted script from passing.
    """
    mandatory = [e for e in evidence if e.mandatory]
    captured = [e for e in mandatory if e.status == "captured"]
    missing = tuple(sorted({e.evidence_type for e in mandatory if e.status != "captured"}))
    return QuorumVerdict(
        met=len(missing) == 0,
        required=len(mandatory),
        captured=len(captured),
        missing=missing,
    )


@dataclass(slots=True)
class ItemFacts:
    """Everything classification is allowed to look at, for one item."""

    # Governance refusal — a member the policy would not let execute.
    policy_blocked_reason: str | None = None
    # A prerequisite could not be satisfied: no runner for the framework, an
    # upstream dependency item did not complete, the member had no script.
    blocked_reason: str | None = None
    # A named readiness axis failed for this item at dispatch time.
    environment_failure_reason: str | None = None
    data_failure_reason: str | None = None
    # The harness itself broke: runner could not start, crashed, or timed out.
    # Distinct from the script asserting a false expectation.
    automation_failure_reason: str | None = None
    # The runner's own per-test verdict, in its native vocabulary
    # (pass | fail | skip | error | blocked), or None if it never reported.
    runner_status: str | None = None
    assertions: tuple[AssertionFact, ...] = ()
    evidence: tuple[EvidenceFact, ...] = ()


@dataclass(slots=True)
class Classification:
    result: str
    # Always populated for anything that is not a clean PASS, because Section 6.2
    # requires the exact reason in the row tooltip and the inspector.
    attention_reason: str | None = None
    quorum: QuorumVerdict | None = None


def classify_item(facts: ItemFacts) -> Classification:
    """Classify one item into exactly one of the eight outcomes (or SKIPPED).

    Precedence, highest first. The order is the rule, not an implementation
    detail: each earlier branch describes a condition under which the product
    under test was never actually exercised, so reporting an application verdict
    would be a lie.

    1. POLICY_BLOCKED      — governance refused execution
    2. BLOCKED             — a prerequisite was unsatisfiable
    3. ENVIRONMENT_FAILURE — the environment broke
    4. DATA_FAILURE        — required data was absent or unusable
    5. AUTOMATION_FAILURE  — the harness broke
    6. SKIPPED             — deliberately not executed
    7. FAIL                — a mandatory assertion evaluated false
    8. INCONCLUSIVE        — nothing was proven, or evidence is missing
    9. PASS                — assertions proven and evidence quorum met
    """
    quorum = evidence_quorum(list(facts.evidence))

    if facts.policy_blocked_reason:
        return Classification("POLICY_BLOCKED", facts.policy_blocked_reason, quorum)
    if facts.blocked_reason:
        return Classification("BLOCKED", facts.blocked_reason, quorum)
    if facts.environment_failure_reason:
        return Classification(
            "ENVIRONMENT_FAILURE", facts.environment_failure_reason, quorum
        )
    if facts.data_failure_reason:
        return Classification("DATA_FAILURE", facts.data_failure_reason, quorum)
    if facts.automation_failure_reason:
        return Classification(
            "AUTOMATION_FAILURE", facts.automation_failure_reason, quorum
        )

    # The runner's native vocabulary maps onto the outcomes above rather than
    # onto a result directly. 'error' is the important one: an errored test threw
    # rather than asserted, which is the harness failing, not the product.
    if facts.runner_status == "error":
        return Classification(
            "AUTOMATION_FAILURE",
            "The runner reported an error rather than an assertion result — "
            "the script or harness failed, not necessarily the application.",
            quorum,
        )
    if facts.runner_status == "blocked":
        return Classification(
            "BLOCKED", "The runner reported the test as blocked.", quorum
        )
    if facts.runner_status == "skip":
        return Classification("SKIPPED", "The runner skipped this test.", quorum)

    mandatory = [a for a in facts.assertions if a.mandatory]
    failed = [a for a in mandatory if a.passed is False]
    unevaluated = [a for a in mandatory if a.passed is None]
    proven = [a for a in mandatory if a.passed is True]

    # A mandatory assertion evaluating false is the one genuine application
    # verdict, and it outranks a missing artifact: we know the product misbehaved
    # whether or not every screenshot landed.
    if failed:
        return Classification(
            "FAIL",
            f"{len(failed)} mandatory assertion(s) failed.",
            quorum,
        )

    # Section 14.11. Nothing was asserted, so nothing was proven — regardless of
    # the runner reporting a green exit.
    if not mandatory:
        # A failing run with nothing asserted is still INCONCLUSIVE, not FAIL: the
        # failure cannot be attributed to a business expectation, so calling it an
        # application defect would over-claim in the other direction.
        if facts.runner_status == "fail":
            return Classification(
                "INCONCLUSIVE",
                "The runner reported a failure, but this test declares no mandatory "
                "assertion, so the failure cannot be attributed to a business "
                "expectation.",
                quorum,
            )
        return Classification(
            "INCONCLUSIVE",
            "No mandatory assertion was evaluated, so this run proves nothing "
            "about the application. A green runner exit is not a pass.",
            quorum,
        )

    # A failing runner over a test that *does* declare mandatory assertions is a
    # real application verdict. Playwright fails the test when any web-first
    # assertion fails, but its reporter does not attribute the failure to a
    # specific expect() — so the assertion rows stay unevaluated and the verdict
    # comes from the runner plus its error text. Marking an arbitrary assertion as
    # the failed one would be fabrication.
    if facts.runner_status == "fail":
        return Classification(
            "FAIL",
            "The runner reported a failing assertion for this test. The specific "
            "assertion is not attributable from the runner report — see the error "
            "detail and trace evidence.",
            quorum,
        )

    if unevaluated:
        return Classification(
            "INCONCLUSIVE",
            f"{len(unevaluated)} mandatory assertion(s) were never evaluated.",
            quorum,
        )

    # Section 14.12. Every assertion passed, but the evidence to substantiate it
    # is incomplete.
    if not quorum.met:
        return Classification("INCONCLUSIVE", quorum.reason, quorum)

    # A green runner is necessary but not sufficient, and it is required
    # explicitly: `runner_status is None` means the runner never reported, which
    # cannot be read as agreement. Proven assertions with no runner verdict is an
    # unresolved disagreement, not a pass.
    if facts.runner_status != "pass":
        if facts.runner_status is None:
            return Classification(
                "INCONCLUSIVE",
                f"{len(proven)} mandatory assertion(s) passed but the runner never "
                "reported a verdict for this test, so the result is unconfirmed.",
                quorum,
            )
        return Classification(
            "INCONCLUSIVE",
            f"Assertions passed but the runner reported '{facts.runner_status}'. "
            "The disagreement is not resolved automatically.",
            quorum,
        )

    return Classification("PASS", None, quorum)


# Run-level rollup precedence. A run is only as good as its worst item, and the
# order mirrors classify_item so the two can never disagree about severity.
_RUN_PRECEDENCE = (
    "POLICY_BLOCKED",
    "ENVIRONMENT_FAILURE",
    "DATA_FAILURE",
    "AUTOMATION_FAILURE",
    "BLOCKED",
    "FAIL",
    "INCONCLUSIVE",
)


def classify_run(item_results: list[str]) -> str:
    """Roll item results up to one run outcome.

    An empty run is INCONCLUSIVE, not PASS: a run that executed nothing has
    proven nothing, which is the same reasoning `classify_item` applies to a
    script that asserted nothing.
    """
    if not item_results:
        return "INCONCLUSIVE"
    present = set(item_results)
    for outcome in _RUN_PRECEDENCE:
        if outcome in present:
            return outcome
    # Only PASS and SKIPPED remain. An all-skipped run proved nothing.
    if present <= {"SKIPPED"}:
        return "INCONCLUSIVE"
    if "PENDING" in present:
        return "INCONCLUSIVE"
    return "PASS"
