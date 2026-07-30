"""UI-020/021/023 — the Automation Asset autonomy policy.

Pure functions over frozen dataclasses. This module never touches the database:
`evidence.py` is the only module that queries, exactly as `inheritance.py` is for
UI-018. Everything here is deterministic and unit-testable without a session.

The rule this module exists to enforce (contract Section 14.2):

    AI_APPROVED  <=  ALL hard preconditions met  AND  score >= threshold

The ordering matters and is not stylistic. `automation_confidence_service`
returns *neutral defaults when evidence is absent* — 0.5 for ungrounded
locators, 0.5 for no dry-run history, 0.7 for a test case with no test data.
Those defaults are correct for display and dangerous for gating: an asset that
has never been executed once still reaches roughly 0.70, and with partially
grounded locators it clears 0.75. A threshold-only gate would therefore
systematically approve the *least*-evidenced assets, which is the exact inverse
of the intent.

The preconditions below defeat that by demanding the evidence itself exist
before the score is allowed to mean anything. The score discriminates among
qualified candidates; it never certifies an unqualified one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

AutonomyState = Literal["AI_PENDING", "AI_HELD", "AI_APPROVED"]

# Precondition codes. Stable strings — they are persisted by value on every
# decision record, so renaming one breaks the readability of history.
STATIC_GATE_CLEAN = "STATIC_GATE_CLEAN"
NO_UNRESOLVED_STEPS = "NO_UNRESOLVED_STEPS"
LOCATORS_GROUNDED = "LOCATORS_GROUNDED"
DRY_RUNS_PASSED = "DRY_RUNS_PASSED"
NO_CRITICAL_GAPS = "NO_CRITICAL_GAPS"

PRECONDITION_ORDER = (
    STATIC_GATE_CLEAN,
    NO_UNRESOLVED_STEPS,
    LOCATORS_GROUNDED,
    DRY_RUNS_PASSED,
    NO_CRITICAL_GAPS,
)


@dataclass(frozen=True)
class AutonomyPolicy:
    """The rubric in force for one evaluation.

    Carried explicitly rather than read from config inside the evaluator, so a
    decision record can be reproduced exactly from its own stored values.
    """

    rubric_id: str = "automation.v1"
    threshold: int = 80
    min_passing_dry_runs: int = 1
    enabled: bool = False


@dataclass(frozen=True)
class AssetEvidence:
    """Everything the evaluator needs, already gathered. Gathered by evidence.py.

    `None` consistently means "not determinable yet", which is treated as
    unmet — never as satisfied. That is the whole point of this dataclass:
    absent evidence must not read as good evidence.
    """

    # Static Quality Gate
    static_gate_ran: bool = False
    static_gate_passed: bool | None = None
    blocking_violation_count: int = 0

    # IR completeness
    has_ir: bool = False
    custom_step_count: int | None = None
    ir_unresolved_count: int | None = None

    # Locator grounding
    element_step_count: int = 0
    referenced_locator_count: int = 0
    grounded_locator_count: int = 0

    # Execution evidence
    passing_dry_runs: int = 0
    total_dry_runs: int = 0

    # Suite readiness
    unwaived_critical_gaps: int = 0

    # Confidence score, 0-100. None when it could not be computed.
    score: float | None = None
    dimensions: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PreconditionOutcome:
    code: str
    label: str
    met: bool
    detail: str

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "label": self.label,
            "met": self.met,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AutonomyVerdict:
    state: AutonomyState
    preconditions: tuple[PreconditionOutcome, ...]
    score: float | None
    threshold: int
    rubric_id: str
    # Plain-English reason the asset is held, or None when approved. This is
    # what the readiness strip renders, so it must name the specific problem.
    held_reason: str | None
    # True when the asset qualified but the policy is switched off, so the UI
    # can say "would be AI-approved" without the state having been written.
    would_approve: bool
    # The score breakdown as computed at this evaluation. Carried on the verdict
    # rather than re-read later, because the decision record must store what was
    # true at decision time.
    dimensions: dict[str, float] = field(default_factory=dict)

    @property
    def unmet(self) -> tuple[PreconditionOutcome, ...]:
        return tuple(p for p in self.preconditions if not p.met)

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "score": self.score,
            "threshold": self.threshold,
            "rubric_id": self.rubric_id,
            "held_reason": self.held_reason,
            "would_approve": self.would_approve,
            "dimensions": dict(self.dimensions),
            "preconditions": [p.as_dict() for p in self.preconditions],
        }


# ── Individual preconditions ─────────────────────────────────────────────────


def _static_gate(ev: AssetEvidence) -> PreconditionOutcome:
    label = "Static gate passed with zero blocking violations"
    if not ev.static_gate_ran or ev.static_gate_passed is None:
        return PreconditionOutcome(
            STATIC_GATE_CLEAN, label, False, "Static Quality Gate has not run yet."
        )
    if not ev.static_gate_passed or ev.blocking_violation_count:
        n = ev.blocking_violation_count
        return PreconditionOutcome(
            STATIC_GATE_CLEAN,
            label,
            False,
            f"{n} blocking validation finding{'s' if n != 1 else ''}."
            if n
            else "Static Quality Gate did not pass.",
        )
    return PreconditionOutcome(STATIC_GATE_CLEAN, label, True, "No blocking findings.")


def _unresolved_steps(ev: AssetEvidence) -> PreconditionOutcome:
    label = "No unresolved steps in the behaviour"
    if not ev.has_ir or ev.custom_step_count is None:
        return PreconditionOutcome(
            NO_UNRESOLVED_STEPS, label, False, "No Automation IR exists for this asset yet."
        )
    custom = ev.custom_step_count
    unresolved = ev.ir_unresolved_count or 0
    # custom_step_count and unresolved_count are independent fields on the
    # emitter's readiness map: an IR can have zero custom steps and still carry
    # unresolved items (an unbound input, an unreviewed checkpoint). Both must
    # be clear.
    if custom or unresolved:
        parts = []
        if custom:
            parts.append(f"{custom} step{'s' if custom != 1 else ''} still need a locator")
        if unresolved:
            parts.append(f"{unresolved} readiness item{'s' if unresolved != 1 else ''} unresolved")
        return PreconditionOutcome(NO_UNRESOLVED_STEPS, label, False, " and ".join(parts) + ".")
    return PreconditionOutcome(
        NO_UNRESOLVED_STEPS, label, True, "Behaviour is complete and validated."
    )


def _locators_grounded(ev: AssetEvidence) -> PreconditionOutcome:
    label = "Locators grounded against the approved Application Model"
    # An asset with no element-driven steps (a pure API or DB check) has nothing
    # to ground. Not applicable is met — but only when there genuinely are no
    # element steps, never merely because no locators were found.
    if ev.element_step_count == 0:
        return PreconditionOutcome(
            LOCATORS_GROUNDED, label, True, "No element-driven steps — not applicable."
        )
    if ev.referenced_locator_count == 0:
        return PreconditionOutcome(
            LOCATORS_GROUNDED,
            label,
            False,
            "Steps drive elements but the IR declares no locators.",
        )
    if ev.grounded_locator_count < ev.referenced_locator_count:
        missing = ev.referenced_locator_count - ev.grounded_locator_count
        return PreconditionOutcome(
            LOCATORS_GROUNDED,
            label,
            False,
            f"{missing} of {ev.referenced_locator_count} locators are not in the "
            "approved Application Model.",
        )
    return PreconditionOutcome(
        LOCATORS_GROUNDED,
        label,
        True,
        f"All {ev.referenced_locator_count} locators grounded.",
    )


def _dry_runs(ev: AssetEvidence, policy: AutonomyPolicy) -> PreconditionOutcome:
    required = policy.min_passing_dry_runs
    label = f"{required} passing dry run{'s' if required != 1 else ''} recorded"
    if ev.passing_dry_runs >= required:
        return PreconditionOutcome(
            DRY_RUNS_PASSED,
            label,
            True,
            f"{ev.passing_dry_runs} of {ev.total_dry_runs} dry runs passed.",
        )
    if ev.total_dry_runs == 0:
        return PreconditionOutcome(
            DRY_RUNS_PASSED, label, False, "This asset has never been executed."
        )
    return PreconditionOutcome(
        DRY_RUNS_PASSED,
        label,
        False,
        f"Only {ev.passing_dry_runs} of {ev.total_dry_runs} dry runs passed; "
        f"{required} passing required.",
    )


def _critical_gaps(ev: AssetEvidence) -> PreconditionOutcome:
    label = "No unwaived critical suite gaps"
    n = ev.unwaived_critical_gaps
    if n:
        return PreconditionOutcome(
            NO_CRITICAL_GAPS,
            label,
            False,
            f"{n} unwaived critical gap{'s' if n != 1 else ''} on this member.",
        )
    return PreconditionOutcome(NO_CRITICAL_GAPS, label, True, "No critical gaps outstanding.")


def evaluate_preconditions(
    evidence: AssetEvidence, policy: AutonomyPolicy
) -> tuple[PreconditionOutcome, ...]:
    """All five preconditions, always in PRECONDITION_ORDER.

    Every precondition is evaluated even after one fails, because the UI shows
    the complete checklist and a reviewer needs the whole picture, not the first
    problem encountered.
    """
    return (
        _static_gate(evidence),
        _unresolved_steps(evidence),
        _locators_grounded(evidence),
        _dry_runs(evidence, policy),
        _critical_gaps(evidence),
    )


def evaluate(evidence: AssetEvidence, policy: AutonomyPolicy) -> AutonomyVerdict:
    """The machine verdict for one asset. Pure."""
    preconditions = evaluate_preconditions(evidence, policy)
    unmet = [p for p in preconditions if not p.met]

    if unmet:
        held = unmet[0].detail if len(unmet) == 1 else (
            f"{len(unmet)} requirements not met — {unmet[0].detail}"
        )
        return AutonomyVerdict(
            state="AI_HELD",
            preconditions=preconditions,
            score=evidence.score,
            threshold=policy.threshold,
            rubric_id=policy.rubric_id,
            held_reason=held,
            would_approve=False,
            dimensions=dict(evidence.dimensions),
        )

    if evidence.score is None:
        return AutonomyVerdict(
            state="AI_HELD",
            preconditions=preconditions,
            score=None,
            threshold=policy.threshold,
            rubric_id=policy.rubric_id,
            held_reason="Confidence score could not be computed.",
            would_approve=False,
            dimensions=dict(evidence.dimensions),
        )

    if evidence.score < policy.threshold:
        return AutonomyVerdict(
            state="AI_HELD",
            preconditions=preconditions,
            score=evidence.score,
            threshold=policy.threshold,
            rubric_id=policy.rubric_id,
            held_reason=(
                f"Score {evidence.score:g} is below the {policy.threshold} threshold."
                + (f" Weakest: {_weakest(evidence)}." if evidence.dimensions else "")
            ),
            would_approve=False,
            dimensions=dict(evidence.dimensions),
        )

    # Qualified. When the policy is off we still report the verdict for display
    # but do not claim the asset was approved.
    return AutonomyVerdict(
        state="AI_APPROVED" if policy.enabled else "AI_PENDING",
        preconditions=preconditions,
        score=evidence.score,
        threshold=policy.threshold,
        rubric_id=policy.rubric_id,
        held_reason=None
        if policy.enabled
        else "Qualified, but automatic approval is disabled for this project.",
        would_approve=True,
        dimensions=dict(evidence.dimensions),
    )


def _weakest(evidence: AssetEvidence) -> str:
    name, value = min(evidence.dimensions.items(), key=lambda kv: kv[1])
    return f"{name.replace('_', ' ')} at {value:g}"


def next_autonomy_state(
    *,
    current_autonomy_state: str,
    current_approval_state: str,
    verdict: AutonomyVerdict,
) -> str:
    """What autonomy_state to persist, honouring the approval-owned guard.

    Once a human has ruled — FINAL_APPROVED or REJECTED — re-evaluation may
    refresh the score for display but must never rewrite autonomy_state. UI-018
    Phase B hit precisely this bug at suite level: an evaluation pass that
    recomputes status silently undoes an approval. `WORKFLOW_OWNED_STATUSES`
    was its fix; this is the same rule one level down.
    """
    from app.models.automation_suite import APPROVAL_OWNED_STATES

    if current_approval_state in APPROVAL_OWNED_STATES:
        return current_autonomy_state
    return verdict.state
