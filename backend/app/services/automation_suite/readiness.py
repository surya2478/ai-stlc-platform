"""Per-member readiness evaluation — pure, over resolved inheritance.

Checks 1-10 are ported 1:1 from the retired per-test-case engine
(`automation_workspace_service.evaluate_readiness`), keeping every reason
string, remediation string, severity rule and stage value, so no check's
user-visible output changed when it moved to suite scope. Checks 11-15 are
new but every one of them reads a column that really exists.

Gap types the contract asks for that are *not* raised here, because the
entity they would read does not exist in this repository yet:

  AUTOMATION_IR_MISSING            no automation_ir table (UI-020 unbuilt)
  FRAMEWORK_PROFILE_MISSING        no framework_profile table (UI-022, P2-S3)
  UNSUPPORTED_FRAMEWORK_APPLICATION  no framework/application pairing matrix
                                   exists; authoring one would be a guessed
                                   business rule
  REPOSITORY_LINK_INVALID          no repository entity to validate against
  EVIDENCE_POLICY_INCOMPLETE       no evidence-policy entity
  PERMISSION_DENIED                a suite and all its members share one
                                   project, so the check degenerates
  VALIDATION_FAILED                no validation subsystem (UI-023)
  SEPARATION_OF_DUTY_VIOLATION     belongs to the Phase B approval workflow
  SNAPSHOT_DRIFT                   published snapshots are Phase B

They stay in the model's CHECK constraint so a later phase can raise them
without a migration.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.automation_suite.gaps import DetectedGap, fingerprint
from app.services.automation_suite.inheritance import MemberInheritance
from app.services.test_classification import capability_resolver
from app.services.test_classification.capability_resolver import CapabilityStatus

_LOCATOR_CRITICAL_GAPS = {"MISSING_SCREEN", "MISSING_COMPONENT", "MISSING_ELEMENT"}
_LOCATOR_WARNING_GAPS = {"AMBIGUOUS_ELEMENT", "UNSTABLE_LOCATOR"}

_ACCEPTABLE_CANDIDATE_STATUSES = ("RECOMMENDED", "CONDITIONAL", "APPROVED")
_REJECTED_CANDIDATE_STATUSES = ("NOT_RECOMMENDED", "BLOCKED")


@dataclass
class MemberEvaluation:
    member_id: int
    checks_passed: int = 0
    checks_total: int = 0
    gaps: list[DetectedGap] = field(default_factory=list)

    @property
    def member_status(self) -> str:
        """Verdict on the raw findings, before any human adjudication."""
        return self._status_for(self.gaps)

    def effective_status(self, blocking_fingerprints: set[str]) -> str:
        """Verdict once waived and excluded findings are discounted.

        A member whose only critical findings have been waived is not
        "blocked" — the suite is cleared to proceed on it, so reporting
        BLOCKED here would contradict the suite's own status.
        """
        return self._status_for([g for g in self.gaps if fingerprint(g) in blocking_fingerprints])

    @staticmethod
    def _status_for(gaps: list[DetectedGap]) -> str:
        if any(g.severity == "critical" for g in gaps):
            return "BLOCKED"
        if gaps:
            return "WARNING"
        return "READY"


def evaluate_member(
    inh: MemberInheritance, *, capability_status: dict[str, CapabilityStatus]
) -> MemberEvaluation:
    evaluation = MemberEvaluation(member_id=inh.member_id)
    test_case = inh.test_case
    application = inh.application
    classification = inh.classification
    model = inh.model

    def check(passed: bool) -> None:
        evaluation.checks_total += 1
        if passed:
            evaluation.checks_passed += 1

    def add(
        *,
        gap_type: str,
        stage: str,
        severity: str,
        reason: str,
        remediation: str | None = None,
        evidence: dict | None = None,
        subject: str | None = None,
    ) -> None:
        evaluation.gaps.append(
            DetectedGap(
                gap_type=gap_type,
                scope="member",
                category="gap",
                severity=severity,
                stage=stage,
                reason=reason,
                remediation=remediation,
                evidence=evidence or {},
                member_id=inh.member_id,
                test_case_id=inh.test_case_id,
                subject=subject,
            )
        )

    # A deleted source is terminal — every other check would report noise
    # about a test case that no longer exists.
    if test_case is None or getattr(test_case, "is_deleted", False):
        check(False)
        add(
            gap_type="TEST_CASE_DELETED",
            stage="test_intent",
            severity="critical",
            reason="The source test case has been deleted.",
            remediation="Remove this test case from the suite, or restore it in Test Management.",
        )
        return evaluation

    # A manual-only member is intentionally not automated. Only its
    # test-intent governance is meaningful; automation grounding is not.
    manual_only = inh.is_manual_only

    # 1. Test case approved
    tc_approved = test_case.status == "approved"
    check(tc_approved)
    if not tc_approved:
        add(
            gap_type="TEST_CASE_NOT_APPROVED",
            stage="test_intent",
            severity="critical",
            reason=f"Test case status is '{test_case.status}', not 'approved'.",
            remediation="Approve this test case in Test Case Approval before starting automation.",
        )

    # 2. Automation classification approved
    classification_ok = bool(
        classification
        and classification.review_status == "APPROVED"
        and classification.candidate_status in _ACCEPTABLE_CANDIDATE_STATUSES
    )
    if not manual_only:
        check(classification_ok)
        if not classification_ok:
            if classification is None:
                reason = "No automation classification exists for this test case."
                severity = "critical"
            else:
                reason = (
                    f"Classification review status is '{classification.review_status}', "
                    f"candidate status is '{classification.candidate_status}'."
                )
                severity = (
                    "critical"
                    if classification.candidate_status in _REJECTED_CANDIDATE_STATUSES
                    or classification.review_status == "REJECTED"
                    else "warning"
                )
            add(
                gap_type="CLASSIFICATION_NOT_APPROVED",
                stage="test_intent",
                severity=severity,
                reason=reason,
                remediation="Resolve the automation classification decision in Test Case Approval.",
            )

    if manual_only:
        # Skip grounding, environment and capability checks entirely.
        return evaluation

    # 3. Application mapping resolved
    check(application is not None)
    if application is None:
        add(
            gap_type="APPLICATION_MAPPING_MISSING",
            stage="grounding",
            severity="critical",
            reason="No application could be resolved for this test case (no explicit mapping and no project default).",
            remediation="Map this test case to an application, or set a default application in the Application Registry.",
        )

    # 4/5/6/7. Application Model approval, staleness, locators
    if application is not None:
        model_ok = bool(model and model.status in ("approved", "published"))
        check(model_ok)
        if not model_ok:
            add(
                gap_type="MODEL_NOT_APPROVED",
                stage="grounding",
                severity="critical",
                reason=(
                    f"No approved/published Application Model exists for '{application.name}'."
                    if not model
                    else f"Application Model version {model.version} is '{model.status}'."
                ),
                remediation="Build, review and approve an Application Model for this application in Application Model.",
            )
        if model is not None:
            check(not inh.model_is_stale)
            if inh.model_is_stale:
                add(
                    gap_type="MODEL_STALE",
                    stage="grounding",
                    severity="warning",
                    reason="The Application Model's source discovery session has new activity since it was built.",
                    remediation="Rebuild the Application Model from the latest discovery session.",
                )

            # Severity comes from the model, not from the gap's type.
            #
            # These were partitioned by gap_type alone, so every MISSING_* gap
            # counted as critical here no matter what the Application Model had
            # recorded. A model could sit "approved" with two warning-severity
            # gaps and 0 criticals while the suite reported 4 criticals over the
            # same two gaps and refused submission — and the findings table
            # listed them all as Warning. Three views, three verdicts, one set
            # of facts.
            #
            # The model is the authority: its reviewer decided what these are
            # worth, and re-deciding it downstream overrides a governance
            # judgement that has already been made and recorded.
            missing_gaps = [g for g in inh.open_model_gaps if g.gap_type in _LOCATOR_CRITICAL_GAPS]
            ambiguous_gaps = [g for g in inh.open_model_gaps if g.gap_type in _LOCATOR_WARNING_GAPS]
            blocking_model_gaps = [
                g for g in (missing_gaps + ambiguous_gaps) if g.severity == "critical"
            ]
            check(not blocking_model_gaps)

            def _severity_of(gaps: list) -> str:
                return "critical" if any(g.severity == "critical" for g in gaps) else "warning"

            if missing_gaps:
                critical_count = sum(1 for g in missing_gaps if g.severity == "critical")
                add(
                    gap_type="LOCATOR_MISSING",
                    stage="grounding",
                    severity=_severity_of(missing_gaps),
                    reason=(
                        f"{len(missing_gaps)} missing screen/component/element gap(s) in the "
                        f"Application Model ({critical_count} critical)."
                    ),
                    remediation="Resolve missing screen/component/element gaps in Application Model.",
                    evidence={"gap_ids": [g.id for g in missing_gaps]},
                    # Keyed on the model, not the gap ids — that list churns
                    # on every model rebuild.
                    subject=f"model:{model.id}",
                )
            if ambiguous_gaps:
                add(
                    gap_type="LOCATOR_AMBIGUOUS",
                    stage="grounding",
                    severity=_severity_of(ambiguous_gaps),
                    reason=f"{len(ambiguous_gaps)} ambiguous/unstable locator gap(s) in the Application Model.",
                    remediation="Confirm or add fallback locators in Application Model.",
                    evidence={"gap_ids": [g.id for g in ambiguous_gaps]},
                    subject=f"model:{model.id}",
                )

    # 8. Environment configured. Only assessable once an environment is
    # known; an unresolved environment is reported as its own gap rather
    # than counted as a failed readiness check.
    if inh.resolved_environment is None:
        add(
            gap_type="ENVIRONMENT_UNRESOLVED",
            stage="execution_readiness",
            severity="warning",
            reason="No environment is set for this suite, so environment readiness could not be assessed.",
            remediation="Set the suite's default environment in Execution and Schedule.",
        )
    else:
        env_ready = bool(
            application
            and application.lifecycle_status == "active"
            and (application.environment_urls or {}).get(inh.resolved_environment)
        )
        check(env_ready)
        if not env_ready:
            add(
                gap_type="ENVIRONMENT_NOT_READY",
                stage="execution_readiness",
                severity="critical",
                reason=(
                    f"Environment '{inh.resolved_environment}' is not configured or the application is not active."
                    if application
                    else "No application resolved to check environment readiness."
                ),
                remediation="Configure this environment's URL in Application Registry.",
            )

    # 9. Mandatory validators/adapter connected (real MCP registry lookup)
    mandatory_keys = list(inh.mandatory_capability_keys)
    if mandatory_keys:
        resolved = {k: capability_status[k] for k in mandatory_keys if k in capability_status}
        unavailable = capability_resolver.unavailable_keys(resolved)
        # A key absent from the shared lookup was never resolvable at all.
        unavailable = unavailable + [k for k in mandatory_keys if k not in capability_status]
        check(len(unavailable) == 0)
        if unavailable:
            details = "; ".join(
                f"{k}: {resolved[k].detail}" if k in resolved else f"{k}: not declared in this project"
                for k in unavailable
            )
            add(
                gap_type="MANDATORY_MCP_UNAVAILABLE",
                stage="execution_readiness",
                severity="critical",
                reason=f"Mandatory adapter/validator(s) unavailable — {details}",
                remediation="Connect the required MCP in MCP Connections.",
                evidence={"unavailable_keys": unavailable},
                subject="|".join(sorted(unavailable)),
            )

    # 10. Classification not superseded by a newer test-case version
    policy_stale = bool(classification and classification.test_case_version < (test_case.version or 0))
    check(not policy_stale)
    if policy_stale:
        add(
            gap_type="POLICY_STALE",
            stage="test_intent",
            severity="warning",
            reason=(
                f"Classification was evaluated against test case version {classification.test_case_version}, "
                f"but the test case is now version {test_case.version}."
            ),
            remediation="Reclassify this test case after reviewing what changed.",
        )

    # 11. An automation asset exists. A Draft suite legitimately has none
    # yet (contract Section 26.2), so this is a warning, not a blocker.
    if not inh.current_scripts:
        add(
            gap_type="SCRIPT_MISSING",
            stage="script_generation",
            severity="warning",
            reason="No automation script exists for this test case.",
            remediation="Record it in Live Recorder or generate a script, then revalidate the suite.",
        )

    # 12. Every surviving asset is deprecated.
    deprecated = [s for s in inh.scripts if (s.status or "") in ("deprecated", "archived", "superseded")]
    if deprecated and not inh.current_scripts:
        add(
            gap_type="SCRIPT_DEPRECATED",
            stage="script_generation",
            severity="warning",
            reason=f"All {len(deprecated)} script(s) for this test case are deprecated or superseded.",
            remediation="Regenerate or restore an active script version.",
        )

    # 13. Test data exists.
    if not inh.test_data:
        add(
            gap_type="TEST_DATA_MISSING",
            stage="execution_readiness",
            severity="warning",
            reason="No test data is linked to this test case.",
            remediation="Create or link a test data set in Test Data Manager.",
        )

    # 14. Live sources moved since this member was last evaluated.
    if inh.drift_reasons:
        add(
            gap_type="SOURCE_TEST_CASE_CHANGED",
            stage="test_intent",
            severity="warning",
            reason=" ".join(inh.drift_reasons),
            remediation="Refresh the suite's inherited scope to re-evaluate against current sources.",
        )

    return evaluation
