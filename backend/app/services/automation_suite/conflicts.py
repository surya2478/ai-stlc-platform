"""Cross-member conflict detection — pure, over resolved inheritance.

This is the capability a per-test-case engine structurally could not have:
each of these findings is only visible by comparing members to each other.

`UNSUPPORTED_FRAMEWORK_APPLICATION` is deliberately not detected. It would
need a framework/application pairing matrix, and no such data exists anywhere
in this repository — inventing one in code would be a guessed business rule
presented to users as a governance finding.
"""
from __future__ import annotations

from app.services.automation_suite.gaps import DetectedGap
from app.services.automation_suite.inheritance import MemberInheritance, SuiteInheritance


def _automation_members(suite_inh: SuiteInheritance) -> list[MemberInheritance]:
    """Included members that are actually meant to be automated."""
    return [m for m in suite_inh.evaluable if m.is_included]


def detect_cross_member_conflicts(suite_inh: SuiteInheritance) -> list[DetectedGap]:
    conflicts: list[DetectedGap] = []
    members = _automation_members(suite_inh)
    if not members:
        return conflicts

    def add(
        *,
        gap_type: str,
        severity: str,
        stage: str,
        reason: str,
        remediation: str,
        evidence: dict,
        scope: str = "suite",
        member_id: int | None = None,
        test_case_id: int | None = None,
        subject: str | None = None,
    ) -> None:
        conflicts.append(
            DetectedGap(
                gap_type=gap_type,
                scope=scope,
                category="conflict",
                severity=severity,
                stage=stage,
                reason=reason,
                remediation=remediation,
                evidence=evidence,
                member_id=member_id,
                test_case_id=test_case_id,
                subject=subject,
            )
        )

    # A single member whose surviving scripts span two frameworks — the suite
    # cannot pick one on the member's behalf.
    for member in members:
        if len(member.frameworks) > 1:
            add(
                gap_type="MULTIPLE_FRAMEWORKS",
                scope="member",
                member_id=member.member_id,
                test_case_id=member.test_case_id,
                severity="critical",
                stage="script_generation",
                reason=(
                    "This test case has active scripts in more than one framework: "
                    + ", ".join(sorted(member.frameworks))
                    + "."
                ),
                remediation="Deprecate the scripts for the framework this suite should not use.",
                evidence={"frameworks": sorted(member.frameworks)},
                subject="member_frameworks",
            )

    # Frameworks across members.
    members_by_framework: dict[str, list[int]] = {}
    for member in members:
        for framework in member.frameworks:
            members_by_framework.setdefault(framework, []).append(member.test_case_id)
    if len(members_by_framework) > 1:
        add(
            gap_type="MULTIPLE_FRAMEWORKS",
            severity="critical",
            stage="script_generation",
            reason=(
                "Selected test cases span "
                f"{len(members_by_framework)} automation frameworks: "
                + ", ".join(sorted(members_by_framework))
                + "."
            ),
            remediation=(
                "Split the suite by framework, or exclude the test cases that do not belong to the "
                "framework this suite should run."
            ),
            evidence={"frameworks": {k: sorted(v) for k, v in sorted(members_by_framework.items())}},
            subject="suite_frameworks",
        )

    # Environments across members. Only real resolved values participate — an
    # unresolved environment is reported per member, never treated as a
    # distinct environment here.
    environments = sorted({m.resolved_environment for m in members if m.resolved_environment})
    if len(environments) > 1:
        add(
            gap_type="MULTIPLE_ENVIRONMENTS",
            severity="critical",
            stage="execution_readiness",
            reason="Selected test cases resolve to more than one environment: " + ", ".join(environments) + ".",
            remediation="Split the suite by environment, or align the members on one environment.",
            evidence={"environments": environments},
            subject="suite_environments",
        )

    # Manual and automated members mixed in one suite. Legal, but the suite
    # cannot execute the manual ones, so it is worth surfacing.
    modes = {(m.test_case.execution_mode or "manual") for m in members if m.test_case is not None}
    if len(modes) > 1:
        add(
            gap_type="MIXED_MANUAL_AUTOMATED",
            severity="warning",
            stage="test_intent",
            reason="Selected test cases mix execution modes: " + ", ".join(sorted(modes)) + ".",
            remediation="Mark the manual test cases as manual-only within this suite, or exclude them.",
            evidence={"execution_modes": sorted(modes)},
            subject="suite_execution_modes",
        )

    return conflicts
