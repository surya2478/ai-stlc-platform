"""Orchestrates the classification lifecycle:

resolve policy -> deterministic pre-agent rules -> dispatch Classification
Agent (async, via the existing AgentRun/Celery path) -> [worker persists:]
capability resolution -> deterministic post-capability rules -> scoring ->
versioned TestCaseAutomationClassification row -> reviewer corrections ->
independent approval.

`evaluate_test_case` runs on the request path (builds context, resolves
policy, dispatches the agent). `persist_classification_result` runs on the
worker path, called from agent_tasks.py's `_persist_agent_artifacts` once
the agent completes — it never runs on the request path so an in-flight
evaluation never blocks the API.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.models.automation_classification import (
    ClassificationAuditEvent,
    ClassificationFieldCorrection,
    TestCaseAutomationClassification,
)
from app.models.project_application import ProjectApplication
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_scenario import TestScenario
from app.services.test_classification import capability_resolver, deterministic_rules, policy_resolver, scoring_service
from app.services.test_classification.context import ClassificationContext

CANDIDATE_STATUSES = {
    "NOT_EVALUATED", "RECOMMENDED", "CONDITIONAL", "NOT_RECOMMENDED", "BLOCKED",
    "DEFERRED", "APPROVED", "POLICY_STALE", "RECLASSIFICATION_REQUIRED",
}
REVIEWABLE_REVIEW_STATUSES = {"PENDING_REVIEW", "CHANGES_REQUESTED", "REVIEWED"}


class ClassificationError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


async def load_context(db: AsyncSession, *, project_id: int, test_case_id: int) -> ClassificationContext:
    tc = await db.get(TestCase, test_case_id)
    if tc is None or tc.project_id != project_id or tc.is_deleted:
        raise ClassificationError(404, "TEST_CASE_NOT_ELIGIBLE", "Test case not found in this project.")

    requirement = await db.get(Requirement, tc.requirement_id) if tc.requirement_id else None
    scenario = await db.get(TestScenario, tc.scenario_id) if tc.scenario_id else None
    application = await db.get(ProjectApplication, tc.application_id) if tc.application_id else None

    policy = await policy_resolver.resolve_effective_policy(
        db, project_id=project_id, application_id=tc.application_id
    )
    return ClassificationContext(
        test_case=tc, requirement=requirement, scenario=scenario, application=application, policy=policy
    )


def routing_default_adapter(ctx: ClassificationContext) -> tuple[str | None, list[str], list[str]]:
    """Fallback adapter/validator selection purely from the policy's own
    routing/external-validation rules, used when the agent is disabled or
    fails to produce a usable recommendation — never a hard-coded default."""
    rules = ctx.policy.rules or {}
    channel = (ctx.test_case.test_type or "").upper()
    primary_adapter = None
    for rule in rules.get("routing_rules") or []:
        when = rule.get("when") or {}
        if when.get("channel") and when["channel"].upper() != channel:
            continue
        primary_adapter = rule.get("primary_adapter")
        if primary_adapter:
            break

    mandatory: list[str] = []
    optional: list[str] = []
    journey_key = ctx.scenario.scenario_id if ctx.scenario else None
    for rule in rules.get("external_validation_rules") or []:
        if journey_key and rule.get("journey") and rule.get("journey") != journey_key:
            continue
        mandatory.extend(rule.get("required") or [])
        optional.extend(rule.get("optional") or [])
    return primary_adapter, mandatory, optional


async def evaluate_test_case(
    db: AsyncSession, *, project_id: int, test_case_id: int, user_id: int, agent_enabled: bool = True
) -> tuple[AgentRun, str]:
    # Local import: agent_dispatch_service imports app.worker.tasks.agent_tasks
    # (for run_agent), and agent_tasks imports this module (for
    # persist_classification_result) — a module-level import here would be
    # circular. Same pattern used by document_service.py /
    # automation_execution_service.py for the equivalent worker-task cycle.
    from app.services import agent_dispatch_service

    ctx = await load_context(db, project_id=project_id, test_case_id=test_case_id)
    policy_resolver.require_published(ctx.policy)

    pre_result = deterministic_rules.evaluate_pre_agent(ctx)

    default_adapter, default_mandatory, default_optional = routing_default_adapter(ctx)

    input_data: dict[str, Any] = {
        "project_id": project_id,
        "test_case_id": test_case_id,
        "test_case_version": ctx.test_case.version,
        "test_case": {
            "title": ctx.test_case.title,
            "test_type": ctx.test_case.test_type,
            "priority": ctx.test_case.priority,
            "severity": ctx.test_case.severity,
            "steps": ctx.test_case.steps,
            "expected_result": ctx.test_case.expected_result,
            "preconditions": ctx.test_case.preconditions,
            "test_data": ctx.test_case.test_data,
            "automation_candidate": ctx.test_case.automation_candidate,
        },
        "requirement": {"id": ctx.requirement.id, "status": ctx.requirement.status} if ctx.requirement else None,
        "scenario": {"id": ctx.scenario.id, "status": ctx.scenario.status} if ctx.scenario else None,
        "application": {"id": ctx.application.id, "name": ctx.application.name} if ctx.application else None,
        "policy_id": ctx.policy.id,
        "policy_version": ctx.policy.version,
        "policy_rules": ctx.policy.rules,
        "deterministic_blockers": [asdict(f) for f in pre_result.blockers],
        "deterministic_warnings": [asdict(f) for f in pre_result.warnings],
        "routing_default_adapter": default_adapter,
        "routing_default_mandatory_validators": default_mandatory,
        "routing_default_optional_validators": default_optional,
        "agent_enabled": agent_enabled,
    }

    run, task_id = await agent_dispatch_service.enqueue_agent_run(
        db,
        project_id=project_id,
        user_id=user_id,
        agent_name="test_classification",
        input_data=input_data,
        prompt_version="v1",
    )
    db.add(
        ClassificationAuditEvent(
            project_id=project_id,
            test_case_id=test_case_id,
            event_type="classification_requested",
            actor_id=user_id,
            new_value={"policy_id": ctx.policy.id, "policy_version": ctx.policy.version, "agent_run_id": run.id},
            source="platform",
        )
    )
    await db.flush()
    return run, task_id


async def persist_classification_result(
    db: AsyncSession, run: AgentRun, input_data: dict[str, Any], data: dict[str, Any]
) -> dict[str, Any]:
    project_id = run.project_id
    test_case_id = input_data["test_case_id"]
    ctx = await load_context(db, project_id=project_id, test_case_id=test_case_id)

    pre_blockers = [
        deterministic_rules.RuleFinding(**f) for f in input_data.get("deterministic_blockers", [])
    ]
    pre_warnings = [
        deterministic_rules.RuleFinding(**f) for f in input_data.get("deterministic_warnings", [])
    ]

    agent_status = data.get("candidate_status") or "NOT_RECOMMENDED"
    if agent_status not in CANDIDATE_STATUSES:
        agent_status = "NOT_RECOMMENDED"

    primary_adapter = data.get("primary_adapter") or input_data.get("routing_default_adapter")
    supporting_adapters = data.get("supporting_adapters") or []
    mandatory_validators = data.get("mandatory_validators") or input_data.get(
        "routing_default_mandatory_validators", []
    )
    optional_validators = data.get("optional_validators") or input_data.get(
        "routing_default_optional_validators", []
    )

    capability_keys = [k for k in [primary_adapter, *supporting_adapters, *mandatory_validators, *optional_validators] if k]
    capability_map = await capability_resolver.resolve_capabilities(db, project_id=project_id, keys=capability_keys)
    mandatory_unavailable = [
        k for k in mandatory_validators if capability_map.get(k) and capability_map[k].maturity not in {"REAL", "MOCK", "VIRTUALIZED", "RECORDED"}
    ]
    optional_unavailable = [
        k for k in optional_validators if capability_map.get(k) and capability_map[k].maturity not in {"REAL", "MOCK", "VIRTUALIZED", "RECORDED"}
    ]
    post_result = deterministic_rules.evaluate_capability(
        ctx, mandatory_unavailable=mandatory_unavailable, optional_unavailable=optional_unavailable
    )

    all_blockers = pre_blockers + post_result.blockers
    all_warnings = pre_warnings + post_result.warnings

    complexity_score, automation_value_score, factors = scoring_service.compute_scores(
        ctx, mandatory_validator_count=len(mandatory_validators), optional_validator_count=len(optional_validators)
    )

    candidate_rules = (ctx.policy.rules or {}).get("candidate_rules") or {}
    min_value = candidate_rules.get("minimum_automation_value_score")

    final_status = agent_status
    if all_blockers:
        final_status = "BLOCKED"
    elif min_value is not None and automation_value_score < min_value and final_status == "RECOMMENDED":
        final_status = "CONDITIONAL"
        all_warnings.append(
            deterministic_rules.RuleFinding(
                "below_value_threshold", "Below automation-value threshold",
                f"Automation value score {automation_value_score} is below policy minimum {min_value}.",
            )
        )
    elif all_warnings and final_status == "RECOMMENDED":
        final_status = "CONDITIONAL"

    current_res = await db.execute(
        select(TestCaseAutomationClassification).where(
            TestCaseAutomationClassification.test_case_id == test_case_id,
            TestCaseAutomationClassification.is_current.is_(True),
        )
    )
    current = current_res.scalars().first()
    if current is not None:
        current.is_current = False

    row = TestCaseAutomationClassification(
        project_id=project_id,
        test_case_id=test_case_id,
        test_case_version=ctx.test_case.version,
        version=(current.version + 1) if current else 1,
        parent_classification_id=current.id if current else None,
        is_current=True,
        candidate_status=final_status,
        primary_adapter=primary_adapter,
        supporting_adapters=supporting_adapters,
        mandatory_validators=mandatory_validators,
        optional_validators=optional_validators,
        discovery_required=bool(data.get("discovery_required", False)),
        recommended_discovery_mode=data.get("recommended_discovery_mode"),
        complexity_score=complexity_score,
        automation_value_score=automation_value_score,
        score_factors=factors,
        required_evidence=(ctx.policy.rules or {}).get("evidence_rules", {}).get("web_e2e", {}).get("mandatory", []),
        required_capabilities=capability_keys,
        deterministic_blockers=[asdict(f) for f in all_blockers],
        advisory_warnings=[asdict(f) for f in all_warnings] + (data.get("warnings") or []),
        matched_rules=data.get("matched_rules") or [],
        policy_id=ctx.policy.id,
        policy_version=ctx.policy.version,
        agent_run_id=run.id,
        review_status="PENDING_REVIEW",
        decision_reason=None,
    )
    db.add(row)
    await db.flush()

    db.add(
        ClassificationAuditEvent(
            project_id=project_id,
            classification_id=row.id,
            test_case_id=test_case_id,
            event_type="classification_recommended",
            actor_id=None,
            new_value={"candidate_status": final_status, "agent_run_id": run.id},
            source="agent",
        )
    )
    await db.flush()
    return {"classification_id": row.id, "candidate_status": final_status, "version": row.version}


async def list_current_classifications(
    db: AsyncSession, *, project_id: int
) -> list[TestCaseAutomationClassification]:
    """All current-version classifications for a project in one query — used
    by UI-010/UI-013 to render per-row status without N+1 requests."""
    result = await db.execute(
        select(TestCaseAutomationClassification).where(
            TestCaseAutomationClassification.project_id == project_id,
            TestCaseAutomationClassification.is_current.is_(True),
        )
    )
    return list(result.scalars().all())


async def get_current_classification(
    db: AsyncSession, *, project_id: int, test_case_id: int
) -> TestCaseAutomationClassification | None:
    result = await db.execute(
        select(TestCaseAutomationClassification).where(
            TestCaseAutomationClassification.project_id == project_id,
            TestCaseAutomationClassification.test_case_id == test_case_id,
            TestCaseAutomationClassification.is_current.is_(True),
        )
    )
    return result.scalars().first()


async def get_classification_or_404(db: AsyncSession, classification_id: int) -> TestCaseAutomationClassification:
    row = await db.get(TestCaseAutomationClassification, classification_id)
    if row is None:
        raise ClassificationError(404, "TEST_CASE_NOT_ELIGIBLE", "Classification not found.")
    return row


def is_stale(row: TestCaseAutomationClassification, test_case: TestCase) -> bool:
    return row.test_case_version != test_case.version


async def apply_review_corrections(
    db: AsyncSession,
    *,
    classification: TestCaseAutomationClassification,
    corrections: dict[str, Any],
    user_id: int,
    reason: str | None,
) -> TestCaseAutomationClassification:
    if classification.review_status not in REVIEWABLE_REVIEW_STATUSES:
        raise ClassificationError(
            409, "CLASSIFICATION_ALREADY_APPROVED", "Approved classifications cannot be corrected in place."
        )
    for field_name, new_value in corrections.items():
        if not hasattr(classification, field_name):
            continue
        old_value = getattr(classification, field_name)
        if old_value == new_value:
            continue
        db.add(
            ClassificationFieldCorrection(
                classification_id=classification.id,
                field_name=field_name,
                ai_value=str(old_value) if old_value is not None else None,
                reviewer_value=str(new_value) if new_value is not None else None,
                changed_by=user_id,
                reason=reason,
            )
        )
        setattr(classification, field_name, new_value)

    classification.review_status = "REVIEWED"
    classification.reviewed_by = user_id
    classification.reviewed_at = datetime.now(timezone.utc)
    await db.flush()
    return classification


DECISION_TO_CANDIDATE_STATUS = {
    "approve": "APPROVED",
    "approve_conditional": "CONDITIONAL",
    "not_recommended": "NOT_RECOMMENDED",
    "defer": "DEFERRED",
}
REASON_REQUIRED_DECISIONS = {"approve_conditional", "not_recommended", "defer", "request_changes"}


async def decide_classification(
    db: AsyncSession,
    *,
    classification: TestCaseAutomationClassification,
    decision: str,
    user_id: int,
    reason: str | None,
    actor_role: str | None,
    allow_self_review_override: bool,
) -> TestCaseAutomationClassification:
    if decision in REASON_REQUIRED_DECISIONS and not (reason and reason.strip()):
        raise ClassificationError(422, "PERMISSION_DENIED", f"Decision '{decision}' requires a reason.")

    if classification.reviewed_by == user_id and not allow_self_review_override:
        raise ClassificationError(
            409, "SEPARATION_OF_DUTY_VIOLATION",
            "The user who corrected this classification cannot also approve it.",
        )

    if decision in {"approve", "approve_conditional"}:
        test_case = await db.get(TestCase, classification.test_case_id)
        if is_stale(classification, test_case):
            raise ClassificationError(
                409, "TEST_CASE_VERSION_STALE", "Test case has changed since this classification was produced."
            )
        effective_policy = await policy_resolver.resolve_effective_policy(
            db, project_id=classification.project_id, application_id=test_case.application_id
        )
        if effective_policy.id != classification.policy_id or effective_policy.version != classification.policy_version:
            raise ClassificationError(
                409, "RECLASSIFICATION_REQUIRED", "The effective policy has changed since this classification was produced."
            )
        if classification.deterministic_blockers:
            raise ClassificationError(
                409, "TEST_CASE_NOT_ELIGIBLE", "Deterministic blockers must be resolved before approval."
            )

    old_value = {"candidate_status": classification.candidate_status, "review_status": classification.review_status}

    if decision == "request_changes":
        classification.review_status = "CHANGES_REQUESTED"
    elif decision in DECISION_TO_CANDIDATE_STATUS:
        classification.candidate_status = DECISION_TO_CANDIDATE_STATUS[decision]
        classification.review_status = "APPROVED" if decision in {"approve", "approve_conditional"} else (
            "REJECTED" if decision == "not_recommended" else "CHANGES_REQUESTED"
        )
        if decision in {"approve", "approve_conditional"}:
            classification.approved_by = user_id
            classification.approved_at = datetime.now(timezone.utc)
    else:
        raise ClassificationError(422, "PERMISSION_DENIED", f"Unknown decision '{decision}'.")

    classification.decision_reason = reason
    await db.flush()

    db.add(
        ClassificationAuditEvent(
            project_id=classification.project_id,
            classification_id=classification.id,
            test_case_id=classification.test_case_id,
            event_type=f"classification_{decision}",
            actor_id=user_id,
            old_value=old_value,
            new_value={"candidate_status": classification.candidate_status, "review_status": classification.review_status},
            reason=reason,
            source="platform",
        )
    )
    await db.flush()
    return classification
