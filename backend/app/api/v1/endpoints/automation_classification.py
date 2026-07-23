"""Test Automation Classification & Routing endpoints —
/api/v1/automation-classifications/*.

A deliberately isolated namespace, same isolation pattern as
grounded_poc.py: every route 404s when AUTOMATION_CLASSIFICATION_ENABLED
is off, so a disabled deployment is externally indistinguishable from one
where this capability was never added. Extends the existing P1-S3 Test
Design & Approval domain (test_cases, project_applications, approval_actions)
rather than a separate /lab namespace — see
docs/test-automation-classification-routing-implementation-prompt.md and
the approved implementation plan for why.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, require_entity_permission, require_permission
from app.config import get_settings
from app.models.automation_classification import TestCaseAutomationClassification
from app.models.test_case import TestCase
from app.schemas.automation_classification import (
    AutomationClassificationPolicyOut,
    ClassificationDecisionRequest,
    ClassificationEvaluateRequest,
    ClassificationEvaluateResponse,
    ClassificationEvaluateResponseItem,
    ClassificationPolicySimulateRequest,
    ClassificationPolicySimulateResponse,
    ClassificationReviewRequest,
    TestCaseAutomationClassificationOut,
)
from app.services import approval_service
from app.services.rbac_service import (
    AUTOMATION_CLASSIFICATION_APPROVE,
    AUTOMATION_CLASSIFICATION_EVALUATE,
    AUTOMATION_CLASSIFICATION_OVERRIDE,
    AUTOMATION_CLASSIFICATION_REVIEW,
    AUTOMATION_CLASSIFICATION_SIMULATE_POLICY,
    AUTOMATION_CLASSIFICATION_VIEW,
    user_has_permission,
)
from app.services.test_classification import classification_service, deterministic_rules, policy_resolver

router = APIRouter()

DECISION_ENDPOINTS = {
    "approve": "approve",
    "approve-conditional": "approve_conditional",
    "reject": "not_recommended",
    "defer": "defer",
    "request-changes": "request_changes",
}


def _require_enabled() -> None:
    if not get_settings().automation_classification_enabled:
        raise HTTPException(
            status_code=404,
            detail="Automation classification is disabled (AUTOMATION_CLASSIFICATION_ENABLED=false)",
        )


def _out(row: TestCaseAutomationClassification, test_case: TestCase | None = None) -> TestCaseAutomationClassificationOut:
    payload = TestCaseAutomationClassificationOut.model_validate(row, from_attributes=True)
    if test_case is not None:
        payload.is_stale = classification_service.is_stale(row, test_case)
    return payload


@router.get("/projects/{project_id}/policies/effective", response_model=AutomationClassificationPolicyOut)
async def get_effective_policy(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    application_id: int | None = None,
):
    _require_enabled()
    await require_permission(AUTOMATION_CLASSIFICATION_VIEW, project_id, current_user, db)
    policy = await policy_resolver.resolve_effective_policy(db, project_id=project_id, application_id=application_id)
    return policy


@router.get("/policies/{policy_id}", response_model=AutomationClassificationPolicyOut)
async def get_policy(policy_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    policy = await policy_resolver.get_policy_or_404(db, policy_id)
    if policy.project_id is not None:
        await require_permission(AUTOMATION_CLASSIFICATION_VIEW, policy.project_id, current_user, db)
    return policy


@router.post("/projects/{project_id}/policies/simulate", response_model=ClassificationPolicySimulateResponse)
async def simulate_policy(
    project_id: int,
    payload: ClassificationPolicySimulateRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    _require_enabled()
    await require_permission(AUTOMATION_CLASSIFICATION_SIMULATE_POLICY, project_id, current_user, db)
    ctx = await classification_service.load_context(db, project_id=project_id, test_case_id=payload.test_case_id)
    pre_result = deterministic_rules.evaluate_pre_agent(ctx)
    default_adapter, default_mandatory, default_optional = classification_service.routing_default_adapter(ctx)
    return ClassificationPolicySimulateResponse(
        policy=ctx.policy,
        deterministic_blockers=[{"code": f.code, "label": f.label, "detail": f.detail} for f in pre_result.blockers],
        deterministic_warnings=[{"code": f.code, "label": f.label, "detail": f.detail} for f in pre_result.warnings],
        routing_default_adapter=default_adapter,
        routing_default_mandatory_validators=default_mandatory,
        routing_default_optional_validators=default_optional,
    )


@router.post("/projects/{project_id}/evaluate", response_model=ClassificationEvaluateResponse)
async def evaluate_classifications(
    project_id: int,
    payload: ClassificationEvaluateRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    _require_enabled()
    await require_permission(AUTOMATION_CLASSIFICATION_EVALUATE, project_id, current_user, db)
    agent_enabled = get_settings().automation_classification_agent_enabled
    results = []
    for test_case_id in payload.test_case_ids:
        run, _task_id = await classification_service.evaluate_test_case(
            db, project_id=project_id, test_case_id=test_case_id, user_id=current_user.id, agent_enabled=agent_enabled
        )
        results.append(ClassificationEvaluateResponseItem(test_case_id=test_case_id, agent_run_id=run.id, status=run.status))
    await db.commit()
    return ClassificationEvaluateResponse(project_id=project_id, results=results)


@router.get("/projects/{project_id}", response_model=list[TestCaseAutomationClassificationOut])
async def list_project_classifications(project_id: int, db: DBSession, current_user: CurrentUser):
    """Every current-version classification in the project, in one query —
    UI-010/UI-013 use this to render per-row status without an N+1 fetch
    per test case."""
    _require_enabled()
    await require_permission(AUTOMATION_CLASSIFICATION_VIEW, project_id, current_user, db)
    rows = await classification_service.list_current_classifications(db, project_id=project_id)
    test_cases = {tc.id: tc for tc in (await db.execute(select(TestCase).where(TestCase.project_id == project_id))).scalars().all()}
    return [_out(row, test_cases.get(row.test_case_id)) for row in rows]


@router.get("/test-cases/{test_case_id}", response_model=TestCaseAutomationClassificationOut)
async def get_current_classification_for_test_case(test_case_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    tc = await db.get(TestCase, test_case_id)
    if tc is None:
        raise HTTPException(status_code=404, detail="Test case not found")
    await require_entity_permission(tc, AUTOMATION_CLASSIFICATION_VIEW, current_user, db)
    row = await classification_service.get_current_classification(db, project_id=tc.project_id, test_case_id=test_case_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "TEST_CASE_NOT_ELIGIBLE", "message": "Test case has not been classified yet."})
    return _out(row, tc)


@router.get("/{classification_id}", response_model=TestCaseAutomationClassificationOut)
async def get_classification(classification_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    row = await classification_service.get_classification_or_404(db, classification_id)
    await require_entity_permission(row, AUTOMATION_CLASSIFICATION_VIEW, current_user, db)
    tc = await db.get(TestCase, row.test_case_id)
    return _out(row, tc)


@router.post("/{classification_id}/review", response_model=TestCaseAutomationClassificationOut)
async def review_classification(
    classification_id: int,
    payload: ClassificationReviewRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    _require_enabled()
    row = await classification_service.get_classification_or_404(db, classification_id)
    await require_entity_permission(row, AUTOMATION_CLASSIFICATION_REVIEW, current_user, db)
    updated = await classification_service.apply_review_corrections(
        db, classification=row, corrections=payload.corrections, user_id=current_user.id, reason=payload.reason
    )
    await db.commit()
    await db.refresh(updated)
    tc = await db.get(TestCase, updated.test_case_id)
    return _out(updated, tc)


@router.post("/{classification_id}/reclassify", response_model=ClassificationEvaluateResponseItem)
async def reclassify(classification_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    row = await classification_service.get_classification_or_404(db, classification_id)
    await require_entity_permission(row, AUTOMATION_CLASSIFICATION_EVALUATE, current_user, db)
    agent_enabled = get_settings().automation_classification_agent_enabled
    run, _task_id = await classification_service.evaluate_test_case(
        db, project_id=row.project_id, test_case_id=row.test_case_id, user_id=current_user.id, agent_enabled=agent_enabled
    )
    await db.commit()
    return ClassificationEvaluateResponseItem(test_case_id=row.test_case_id, agent_run_id=run.id, status=run.status)


async def _decide(
    endpoint_decision: str,
    classification_id: int,
    payload: ClassificationDecisionRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> TestCaseAutomationClassificationOut:
    _require_enabled()
    row = await classification_service.get_classification_or_404(db, classification_id)
    await require_entity_permission(row, AUTOMATION_CLASSIFICATION_APPROVE, current_user, db)

    override_allowed = await user_has_permission(db, current_user, row.project_id, AUTOMATION_CLASSIFICATION_OVERRIDE)
    decision = DECISION_ENDPOINTS[endpoint_decision]
    updated = await classification_service.decide_classification(
        db,
        classification=row,
        decision=decision,
        user_id=current_user.id,
        reason=payload.reason,
        actor_role=current_user.role,
        allow_self_review_override=override_allowed,
    )
    await approval_service.create_approval_action(
        db,
        project_id=row.project_id,
        user_id=current_user.id,
        entity_type="test_case_automation_classification",
        entity_id=row.id,
        action=endpoint_decision.replace("-", "_"),
        notes=payload.reason,
        actor_role=current_user.role,
        decision="approved" if endpoint_decision in {"approve", "approve-conditional"} else (
            "rejected" if endpoint_decision == "reject" else "requested_changes"
        ),
    )
    await db.commit()
    await db.refresh(updated)
    tc = await db.get(TestCase, updated.test_case_id)
    return _out(updated, tc)


@router.post("/{classification_id}/approve", response_model=TestCaseAutomationClassificationOut)
async def approve_classification(classification_id: int, payload: ClassificationDecisionRequest, db: DBSession, current_user: CurrentUser):
    return await _decide("approve", classification_id, payload, db, current_user)


@router.post("/{classification_id}/approve-conditional", response_model=TestCaseAutomationClassificationOut)
async def approve_classification_conditional(classification_id: int, payload: ClassificationDecisionRequest, db: DBSession, current_user: CurrentUser):
    return await _decide("approve-conditional", classification_id, payload, db, current_user)


@router.post("/{classification_id}/reject", response_model=TestCaseAutomationClassificationOut)
async def reject_classification(classification_id: int, payload: ClassificationDecisionRequest, db: DBSession, current_user: CurrentUser):
    return await _decide("reject", classification_id, payload, db, current_user)


@router.post("/{classification_id}/defer", response_model=TestCaseAutomationClassificationOut)
async def defer_classification(classification_id: int, payload: ClassificationDecisionRequest, db: DBSession, current_user: CurrentUser):
    return await _decide("defer", classification_id, payload, db, current_user)


@router.post("/{classification_id}/request-changes", response_model=TestCaseAutomationClassificationOut)
async def request_changes_classification(classification_id: int, payload: ClassificationDecisionRequest, db: DBSession, current_user: CurrentUser):
    return await _decide("request-changes", classification_id, payload, db, current_user)
