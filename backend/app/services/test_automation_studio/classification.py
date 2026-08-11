"""Automation/Manual classification for refined test cases.

The platform already has a governed classification engine
(`app.services.test_classification`), but it evaluates rows in the shared
`test_cases` table via a ClassificationContext built from that model. A
refined studio test case is not such a row, so this module reuses the part
that matters — the project's *published policy* — and applies its
`manual_only_conditions` to the studio's own content.

That is what "based on configuration in the project settings" means here: a
project that edits its manual-only conditions changes what this bulk action
does, and no new configuration surface is introduced.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_classification import AutomationClassificationPolicy
from app.models.test_automation_studio import TasRefinedTestCase
from app.services.test_classification.policy_defaults import default_policy_rules
from app.services.test_classification.policy_resolver import (
    ClassificationPolicyError,
    resolve_effective_policy,
)


async def effective_policy(
    db: AsyncSession, *, project_id: int, application_id: int | None = None
) -> AutomationClassificationPolicy | None:
    """The project's published policy, or None when none is published.

    None is a legitimate answer here, unlike in the governed classification
    flow: bulk-classifying without a published policy falls back to the
    built-in default conditions and records that it did, rather than blocking
    the screen on a policy the project may never have set up.
    """
    try:
        return await resolve_effective_policy(
            db, project_id=project_id, application_id=application_id
        )
    except ClassificationPolicyError:
        return None


def _search_text(test_case: TasRefinedTestCase) -> str:
    parts: list[Any] = [
        test_case.title,
        test_case.objective,
        test_case.expected_result,
        test_case.bdd_scenario,
        test_case.preconditions,
        test_case.steps,
        test_case.test_data_requirements,
        test_case.test_data_notes,
    ]
    return " ".join(
        json.dumps(part, default=str) if isinstance(part, (dict, list)) else str(part or "")
        for part in parts
    ).casefold()


def manual_only_findings(
    test_case: TasRefinedTestCase, policy: AutomationClassificationPolicy | None
) -> list[dict]:
    """Conditions in the policy that force this test case to stay manual."""
    rules = (policy.rules if policy is not None else None) or {}
    conditions = rules.get("manual_only_conditions")
    if conditions is None:
        conditions = default_policy_rules()["manual_only_conditions"]

    haystack = _search_text(test_case)
    findings: list[dict] = []
    for condition in conditions:
        keywords = [str(k).strip() for k in (condition.get("keywords") or []) if str(k).strip()]
        matched = next(
            (
                keyword
                for keyword in keywords
                # Word-boundary match, mirroring the governed engine: a
                # substring match would classify every test case mentioning
                # "photo" as biometric because of "otp" inside it.
                if re.search(rf"(?<!\w){re.escape(keyword.casefold())}(?!\w)", haystack)
            ),
            None,
        )
        if matched:
            findings.append(
                {
                    "code": condition.get("code") or "custom",
                    "label": condition.get("label") or "Configured manual-only condition",
                    "reason": condition.get("reason")
                    or "This configured condition prevents unattended automation.",
                    "matched_keyword": matched,
                }
            )
    return findings


def classify(
    test_case: TasRefinedTestCase, policy: AutomationClassificationPolicy | None
) -> tuple[str, str, list[dict]]:
    """Decide automation vs manual for one refined test case.

    Returns (classification, reason, manual_only_findings).
    """
    findings = manual_only_findings(test_case, policy)
    if findings:
        labels = ", ".join(str(f["label"]) for f in findings)
        return "manual", f"Policy manual-only condition matched: {labels}.", findings

    # The refinement agent records what it could not automate at all. That is
    # a stronger signal than any keyword rule, so it is checked next.
    blockers = ((test_case.metadata_ or {}).get("automation_blockers")) or []
    if blockers:
        return (
            "manual",
            "The refinement agent reported automation blockers: " + "; ".join(str(b) for b in blockers),
            findings,
        )

    if not test_case.steps:
        return "manual", "The test case has no steps to automate.", findings

    # Missing test data does NOT force manual. It is a readiness problem that
    # `test_data_required` already surfaces and that approval already blocks
    # on; classifying it manual would permanently mislabel a test case that is
    # automatable the moment its data arrives.
    if test_case.test_data_required:
        return (
            "automation",
            "Automatable once the outstanding test data is provided.",
            findings,
        )

    return "automation", "No manual-only condition matched and every step is scriptable.", findings
