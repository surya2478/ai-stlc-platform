"""What still stands between a test case and a governed execution.

The platform is organised around artifacts — Requirements governs requirements,
Application Model governs models, Automation Workspace governs suites — and each
does that well. But a user arrives with a goal ("run this test") that no single
screen owns, so the goal is reached by walking six modules in an order nobody
states. Every blocker is discovered by being refused, and almost never in the
module where it is fixed: the suite wizard reports MODEL_NOT_APPROVED, which is
resolved three modules away.

This computes the whole path at once, from state that already exists. It decides
nothing and changes nothing — every step reports a fact another service already
owns, alongside where to go and fix it.

Two rules keep it honest:

**Never invent a verdict.** A step whose owning subsystem cannot be read reports
UNKNOWN, not DONE. A green path has to mean something.

**Blocked is not the same as waiting.** A step is BLOCKED only when it is the
next thing a person can act on. Everything downstream of an incomplete step is
WAITING — listing five blockers when four of them are consequences of the first
is how a checklist becomes noise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StepState(str, Enum):
    DONE = "DONE"
    BLOCKED = "BLOCKED"      # actionable now
    WAITING = "WAITING"      # depends on an earlier step
    UNKNOWN = "UNKNOWN"      # could not be determined — never reported as DONE


@dataclass
class PathStep:
    key: str
    label: str
    state: StepState
    #  What is true right now, in the reader's terms — never a bare status code.
    detail: str
    # Where this is fixed. Absent when there is nothing to do.
    fix_label: str | None = None
    fix_href: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "state": self.state.value,
            "detail": self.detail,
            "fix_label": self.fix_label,
            "fix_href": self.fix_href,
        }


@dataclass
class PathFacts:
    """Everything the path needs, gathered once. Optional fields are None when
    the owning subsystem could not be read — which becomes UNKNOWN, not DONE."""

    project_id: int
    test_case_id: int
    test_case_key: str | None = None

    requirement_status: str | None = None
    requirement_key: str | None = None
    test_case_status: str | None = None

    application_name: str | None = None
    environment: str | None = None
    environment_url: str | None = None

    discovery_session_id: int | None = None
    application_id: int | None = None

    model_id: int | None = None
    model_version: int | None = None
    model_status: str | None = None
    model_screens: int | None = None

    classification_review_status: str | None = None
    classification_candidate_status: str | None = None

    script_key: str | None = None
    script_gate_passed: bool | None = None

    suite_id: int | None = None
    suite_name: str | None = None
    suite_status: str | None = None
    members_awaiting_final_approval: int = 0

    last_run_id: int | None = None
    last_run_state: str | None = None
    last_run_result: str | None = None

    errors: list[str] = field(default_factory=list)


_APPROVED_MODEL_STATUSES = ("approved", "published")
_ACCEPTABLE_CANDIDATES = ("RECOMMENDED", "CONDITIONAL", "APPROVED")


def _q(project_id: int, extra: str = "") -> str:
    return f"?project={project_id}{extra}"


def build_path(facts: PathFacts) -> list[PathStep]:
    """The ordered path, with exactly one actionable blocker at a time."""
    p = facts.project_id
    steps: list[PathStep] = []

    def add(key, label, ok, detail, fix_label=None, fix_href=None, unknown=False):
        if unknown:
            state = StepState.UNKNOWN
        elif ok:
            state = StepState.DONE
        else:
            state = StepState.BLOCKED
        steps.append(PathStep(key, label, state, detail, fix_label, fix_href))

    # 1. Requirement approved
    add(
        "requirement",
        "Requirement approved",
        facts.requirement_status == "approved",
        f"{facts.requirement_key or 'Requirement'} is '{facts.requirement_status or 'not linked'}'."
        if facts.requirement_status != "approved"
        else f"{facts.requirement_key}",
        "Review & Approval", f"/requirements{_q(p, '&view=review')}",
        unknown=facts.requirement_status is None and facts.requirement_key is None,
    )

    # 2. Test case approved
    add(
        "test_case",
        "Test case approved",
        facts.test_case_status == "approved",
        f"{facts.test_case_key or 'Test case'} is '{facts.test_case_status or 'unknown'}'."
        if facts.test_case_status != "approved"
        else f"{facts.test_case_key}",
        "Test Case Approval", f"/test-cases{_q(p, '&view=approval')}",
    )

    # 3. Application + environment URL. The silent dead end this exists to stop:
    #    a registered application with no URL for the test's environment resolves
    #    to None at generation time and produces a script with nowhere to go.
    has_url = bool(facts.environment_url)
    add(
        "application",
        "Application and environment URL",
        has_url,
        f"{facts.application_name} → {facts.environment} {facts.environment_url}"
        if has_url
        else (
            f"'{facts.application_name}' has no URL for environment "
            f"'{facts.environment or 'unset'}'."
            if facts.application_name
            else "No application is mapped to this test case."
        ),
        "Application Registry", f"/applications{_q(p)}",
    )

    # 4. Discovery session
    add(
        "discovery",
        "Discovery session completed",
        facts.discovery_session_id is not None,
        f"Session #{facts.discovery_session_id}"
        if facts.discovery_session_id
        else "No completed session for this application — nothing to ground against.",
        "Live Discovery Session", f"/applications{_q(p, '&view=discovery')}",
    )

    # 5. Application Model
    model_ok = facts.model_status in _APPROVED_MODEL_STATUSES
    add(
        "model",
        "Application Model approved",
        model_ok,
        f"v{facts.model_version} · {facts.model_screens} screen(s)"
        if model_ok
        else (
            f"v{facts.model_version} is '{facts.model_status}'."
            if facts.model_status
            else "No model has been built from a discovery session."
        ),
        "Application Model", f"/applications{_q(p, '&view=model')}",
    )

    # 6. Automation classification
    cls_ok = (
        facts.classification_review_status == "APPROVED"
        and facts.classification_candidate_status in _ACCEPTABLE_CANDIDATES
    )
    add(
        "classification",
        "Automation classification approved",
        cls_ok,
        f"{facts.classification_candidate_status} · review {facts.classification_review_status}"
        if facts.classification_review_status
        else "No classification exists for this test case.",
        "Test Case Approval", f"/test-cases{_q(p, '&view=approval')}",
    )

    # 7. Script
    add(
        "script",
        "Automation script generated",
        facts.script_key is not None,
        f"{facts.script_key}"
        + ("" if facts.script_gate_passed is None else
           " · static gate passed" if facts.script_gate_passed else " · static gate FAILED")
        if facts.script_key
        else "No script has been generated for this test case.",
        "Automation Workspace", f"/automation{_q(p, '&view=workspace')}",
    )

    # 8. Suite published
    suite_ok = facts.suite_status == "PUBLISHED"
    if facts.suite_id and facts.members_awaiting_final_approval and not suite_ok:
        detail = (
            f"'{facts.suite_name}' is '{facts.suite_status}' — "
            f"{facts.members_awaiting_final_approval} member(s) still need final approval."
        )
        fix_label, fix_href = "Automation Assets", f"/automation{_q(p, '&view=ir')}"
    elif facts.suite_id:
        detail = f"'{facts.suite_name}' is '{facts.suite_status}'."
        fix_label, fix_href = "Automation Workspace", f"/automation{_q(p, '&view=workspace')}"
    else:
        detail = "This test case is not in an automation suite."
        fix_label, fix_href = "Automation Workspace", f"/automation{_q(p, '&view=workspace')}"
    add("suite", "Suite published", suite_ok, detail, fix_label, fix_href)

    # 9. Execution
    add(
        "execution",
        "Executed",
        facts.last_run_result == "PASS",
        f"Run #{facts.last_run_id}: {facts.last_run_result or facts.last_run_state}"
        if facts.last_run_id
        else "No governed run yet.",
        "Automation Execution", f"/execution/automation{_q(p)}",
    )

    return _demote_downstream(steps)


def _demote_downstream(steps: list[PathStep]) -> list[PathStep]:
    """Only the first unmet step is actionable; the rest are consequences.

    Reporting five blockers when four of them follow from the first is how a
    checklist stops being read. UNKNOWN also stops the path — an unreadable
    step means the ones after it cannot be judged either.
    """
    stopped = False
    for step in steps:
        if step.state is StepState.DONE:
            # A satisfied step has nothing to fix. Leaving the link attached
            # made every row look like an outstanding action.
            step.fix_label = None
            step.fix_href = None
            continue
        if stopped and step.state is StepState.BLOCKED:
            step.state = StepState.WAITING
            step.fix_label = None
            step.fix_href = None
        elif step.state in (StepState.BLOCKED, StepState.UNKNOWN):
            stopped = True
    return steps


def summarize(steps: list[PathStep]) -> dict[str, Any]:
    done = sum(1 for s in steps if s.state is StepState.DONE)
    blocker = next((s for s in steps if s.state is StepState.BLOCKED), None)
    unknown = next((s for s in steps if s.state is StepState.UNKNOWN), None)
    return {
        "steps_total": len(steps),
        "steps_done": done,
        "ready_to_execute": done == len(steps),
        "next_action": (blocker or unknown).label if (blocker or unknown) else None,
        "next_action_href": (blocker.fix_href if blocker else None),
    }
