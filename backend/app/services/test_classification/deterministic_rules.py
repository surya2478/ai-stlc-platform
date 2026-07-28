"""Deterministic eligibility rules — the tier that always wins over the
classification agent's recommendation (non-negotiable constraint #9 in
docs/test-automation-classification-routing-implementation-prompt.md:
"Do not let the AI agent make the final approval decision").

Two passes:
  - `evaluate_pre_agent` runs before the agent is invoked, from context the
    platform already has (test case / requirement / scenario / application
    state, plus the resolved policy's own block_if/conditional_if lists).
  - `evaluate_capability` runs after capability_resolver has resolved the
    agent's recommended adapter/validators against real registries — only
    then can "mandatory validator not configured" be checked.

Every check name below is a fixed, named predicate; WHICH of them block vs.
merely warn is entirely policy-configurable via `rules.candidate_rules.
block_if` / `conditional_if` — nothing about routing, adapters, or telecom
taxonomy is hard-coded here (constraint #8).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from app.services.test_classification.context import ClassificationContext
from app.services.test_classification.policy_defaults import default_policy_rules

BLOCKING_TERMINAL_STATUSES = {"rejected"}


@dataclass
class RuleFinding:
    code: str
    label: str
    detail: str


@dataclass
class DeterministicResult:
    blockers: list[RuleFinding] = field(default_factory=list)
    warnings: list[RuleFinding] = field(default_factory=list)

    @property
    def is_blocked(self) -> bool:
        return len(self.blockers) > 0

    def as_dicts(self, items: list[RuleFinding]) -> list[dict]:
        return [{"code": f.code, "label": f.label, "detail": f.detail} for f in items]


def _classification_flags(ctx: ClassificationContext) -> dict:
    # No dedicated columns exist on TestCase for CAPTCHA/OTP/destructive/
    # production-only flags yet — reading optional, honestly-absent-by-default
    # flags from metadata_ rather than inventing new core-table columns for
    # data nothing currently produces (same philosophy as migration 039).
    meta = ctx.test_case.metadata_ or {}
    return meta.get("classification_flags") or {}


def _check_unresolved_requirement(ctx: ClassificationContext) -> RuleFinding | None:
    if ctx.requirement is None:
        return RuleFinding("unresolved_requirement", "Requirement not linked", "Test case has no linked requirement.")
    if ctx.requirement.status != "approved":
        return RuleFinding(
            "unresolved_requirement",
            "Requirement not approved",
            f"Linked requirement '{ctx.requirement.requirement_id}' is '{ctx.requirement.status}'.",
        )
    return None


def _check_missing_expected_result(ctx: ClassificationContext) -> RuleFinding | None:
    tc = ctx.test_case
    if not (tc.expected_result and tc.expected_result.strip()):
        return RuleFinding("missing_expected_result", "Expected result missing", "Test case has no expected result.")
    if not tc.steps:
        return RuleFinding("missing_expected_result", "Steps missing", "Test case has no steps.")
    return None


def _check_production_only(ctx: ClassificationContext) -> RuleFinding | None:
    if _classification_flags(ctx).get("production_only"):
        return RuleFinding(
            "production_only", "Production-only", "Test case is flagged as executable only in production."
        )
    return None


def _check_unsupported_application(ctx: ClassificationContext) -> RuleFinding | None:
    if ctx.application is None:
        return RuleFinding(
            "unsupported_application", "No application mapping", "Test case has no stable application mapping."
        )
    if not ctx.application.is_active:
        return RuleFinding(
            "unsupported_application",
            "Application inactive",
            f"Mapped application '{ctx.application.name}' is not active.",
        )
    return None


def _check_test_data_not_ready(ctx: ClassificationContext) -> RuleFinding | None:
    if not ctx.test_case.test_data:
        return RuleFinding("test_data_not_ready", "Test data not ready", "Test case has no test data defined.")
    return None


def _check_unstable_ui(ctx: ClassificationContext) -> RuleFinding | None:
    if _classification_flags(ctx).get("unstable_ui"):
        return RuleFinding("unstable_ui", "Unstable UI", "Application/journey flagged as UI-unstable.")
    return None


def _check_scenario_not_approved(ctx: ClassificationContext) -> RuleFinding | None:
    if ctx.scenario is not None and ctx.scenario.status not in {"approved"}:
        return RuleFinding(
            "unresolved_requirement",
            "Scenario not approved",
            f"Linked scenario '{ctx.scenario.scenario_id}' is '{ctx.scenario.status}'.",
        )
    return None


def _test_case_search_text(ctx: ClassificationContext) -> str:
    tc = ctx.test_case
    values = [
        tc.title,
        getattr(tc, "test_case_objective", None),
        tc.expected_result,
        tc.bdd_scenario,
        tc.preconditions,
        tc.steps,
        tc.test_data,
    ]
    return " ".join(json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value or "") for value in values).casefold()


def _manual_only_findings(ctx: ClassificationContext) -> list[RuleFinding]:
    rules = ctx.policy.rules or {}
    conditions = (
        rules["manual_only_conditions"]
        if "manual_only_conditions" in rules
        else default_policy_rules()["manual_only_conditions"]
    )
    search_text = _test_case_search_text(ctx)
    flags = _classification_flags(ctx)
    findings: list[RuleFinding] = []
    for condition in conditions:
        label = str(condition.get("label") or condition.get("code") or "Configured manual-only condition").strip()
        reason = str(condition.get("reason") or "This configured condition prevents unattended automation.").strip()
        matched = next(
            (
                str(keyword).strip()
                for keyword in condition.get("keywords") or []
                if str(keyword).strip()
                and re.search(rf"(?<!\w){re.escape(str(keyword).strip().casefold())}(?!\w)", search_text)
            ),
            None,
        )
        matched_flag = next(
            (str(flag) for flag in condition.get("metadata_flags") or [] if flags.get(str(flag))),
            None,
        )
        if matched or matched_flag:
            source = f"Matched configured keyword '{matched}'." if matched else f"Matched test-case flag '{matched_flag}'."
            findings.append(
                RuleFinding(
                    f"manual_only:{condition.get('code') or 'custom'}",
                    f"Automation not possible: {label}",
                    f"{reason} {source}",
                )
            )
    return findings


def _check_destructive(ctx: ClassificationContext) -> RuleFinding | None:
    if _classification_flags(ctx).get("destructive_action"):
        return RuleFinding(
            "production_only", "Destructive action", "Test case performs a destructive action requiring manual control."
        )
    return None


# Guardrail tier — always enforced regardless of policy, never overridable
# by the agent or by policy conditional_if downgrade (constraint: "Security
# and regulatory guardrails" sit above every other precedence tier).
_GUARDRAIL_CHECKS: list[Callable[[ClassificationContext], RuleFinding | None]] = [
    _check_destructive,
]

# Policy-configurable checks — the policy's own block_if/conditional_if
# lists decide whether a hit here blocks or merely warns.
_NAMED_CHECKS: dict[str, Callable[[ClassificationContext], RuleFinding | None]] = {
    "unresolved_requirement": _check_unresolved_requirement,
    "missing_expected_result": _check_missing_expected_result,
    "production_only": _check_production_only,
    "unsupported_application": _check_unsupported_application,
    "test_data_not_ready": _check_test_data_not_ready,
    "unstable_ui": _check_unstable_ui,
    "scenario_not_approved": _check_scenario_not_approved,
}


def evaluate_pre_agent(ctx: ClassificationContext) -> DeterministicResult:
    result = DeterministicResult()

    for check in _GUARDRAIL_CHECKS:
        finding = check(ctx)
        if finding is not None:
            result.blockers.append(finding)

    result.blockers.extend(_manual_only_findings(ctx))

    candidate_rules = (ctx.policy.rules or {}).get("candidate_rules") or {}
    block_if = set(candidate_rules.get("block_if") or [])
    conditional_if = set(candidate_rules.get("conditional_if") or [])

    for name in block_if:
        check = _NAMED_CHECKS.get(name)
        if check is None:
            continue
        finding = check(ctx)
        if finding is not None:
            result.blockers.append(finding)

    for name in conditional_if:
        check = _NAMED_CHECKS.get(name)
        if check is None:
            continue
        finding = check(ctx)
        if finding is not None:
            result.warnings.append(finding)

    if ctx.test_case.status in BLOCKING_TERMINAL_STATUSES:
        result.blockers.append(
            RuleFinding("unresolved_requirement", "Test case rejected", "Test case itself is in a rejected state.")
        )

    return result


def evaluate_capability(
    ctx: ClassificationContext,
    *,
    mandatory_unavailable: list[str],
    optional_unavailable: list[str],
) -> DeterministicResult:
    """Second pass, run once capability_resolver knows which mandatory/
    optional validators the agent's recommended route actually needs and
    whether each is configured. A mandatory validator gap is always a
    blocker — capability gaps can never be silently downgraded to
    optional (constraint: "Do not silently downgrade a mandatory validator
    to optional")."""
    result = DeterministicResult()
    for key in mandatory_unavailable:
        result.blockers.append(
            RuleFinding(
                "mandatory_validator_not_configured",
                "Mandatory validator unavailable",
                f"Mandatory validator/adapter '{key}' is not configured or not operational.",
            )
        )

    candidate_rules = (ctx.policy.rules or {}).get("candidate_rules") or {}
    conditional_if = set(candidate_rules.get("conditional_if") or [])
    if "optional_validator_unavailable" in conditional_if:
        for key in optional_unavailable:
            result.warnings.append(
                RuleFinding(
                    "optional_validator_unavailable",
                    "Optional validator unavailable",
                    f"Optional validator '{key}' is not configured.",
                )
            )
    return result
