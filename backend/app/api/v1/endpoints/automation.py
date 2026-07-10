"""
Automation Scripts endpoints — Phase 4.
"""
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, require_entity_permission, require_entity_project_access, require_permission, require_project_access
from app.config import get_settings
from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.schemas.automation import (
    AgentAutomationTrigger,
    AgentMCPDiscoveryTrigger,
    AutomationBatchExecuteRequest,
    AutomationBatchExecuteResponse,
    AutomationConfidenceScoreOut,
    AutomationPlanningOut,
    AutomationRunCancelResponse,
    AutomationScriptExecuteRequest,
    AutomationScriptExecuteResponse,
    AutomationScriptOut,
    AutomationScriptUpdate,
    AutomationTestMappingCreate,
    AutomationTestMappingOut,
    AutomationTestMappingUpdate,
    BulkScriptApprovalRequest,
    BulkScriptApprovalResponse,
    BulkScriptApprovalResult,
    ExternalAutomationRunOut,
    ExternalAutomationRunRequest,
    ExternalAutomationSyncRequest,
    JiraExecutionStatusOut,
    JiraExecutionStatusSyncRequest,
    LifecycleApprovalRequest,
    RecommendationDecisionRequest,
    RunnerFrameworkStatus,
    RunnerStatusOut,
    ScriptTransitionRequest,
)
from app.services import automation_confidence_service, automation_intelligence, locator_map_service
from app.schemas.execution import ExecutionResultOut
from app.schemas.requirement import ApprovalRequest
from app.services import agent_run_service, approval_service, automation_service, traceability_service
from app.services.agent_dispatch_service import enqueue_agent_run
from app.services.automation_runner import runtime_status
from app.services.project_application_service import (
    build_test_case_application_context,
    resolve_default_application,
    resolve_environment_url,
)
from app.services.display_id_service import display_id, temporary_id
from app.services.rbac_service import (
    APPROVE_RELEASE_REPORT,
    AUTOMATION_APPROVE_ENVIRONMENT,
    AUTOMATION_APPROVE_SCRIPT,
    AUTOMATION_REVIEW_SCRIPT,
    EXECUTE_TESTS,
    GENERATE_AUTOMATION,
)
from app.agents.automation.automation_agent import AutomationScriptAgent
from app.integrations.automation.framework_adapters import framework_language

router = APIRouter()
settings = get_settings()


def _run_agents_synchronously() -> bool:
    return False


def _run_summary(run) -> ExternalAutomationRunOut:
    return ExternalAutomationRunOut(
        execution_run_id=run.id,
        external_run_id=run.external_run_id or "",
        status=run.status,
        total_tests=run.total_tests,
        passed_tests=run.passed,
        failed_tests=run.failed,
        skipped_tests=run.skipped,
        message="External automation evidence captured. Jira execution status remains the final QA source of truth.",
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.post("/mappings", response_model=AutomationTestMappingOut, status_code=201)
async def create_automation_mapping(
    body: AutomationTestMappingCreate,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_permission(GENERATE_AUTOMATION, body.project_id, current_user, db)
    mapping = await automation_service.create_mapping(db, body)
    await db.commit()
    return mapping


@router.get("/mappings", response_model=list[AutomationTestMappingOut])
async def get_automation_mappings(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    test_case_id: int | None = Query(None),
    active_only: bool = Query(False),
):
    await require_project_access(project_id, current_user, db)
    return await automation_service.list_mappings(db, project_id=project_id, test_case_id=test_case_id, active_only=active_only)


@router.put("/mappings/{mapping_id}", response_model=AutomationTestMappingOut)
async def update_automation_mapping(
    mapping_id: int,
    body: AutomationTestMappingUpdate,
    db: DBSession,
    current_user: CurrentUser,
):
    mapping = await automation_service.get_mapping(db, mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Automation mapping not found")
    await require_permission(GENERATE_AUTOMATION, mapping.project_id, current_user, db)
    mapping = await automation_service.update_mapping(db, mapping, body)
    await db.commit()
    return mapping


@router.delete("/mappings/{mapping_id}", response_model=AutomationTestMappingOut)
async def delete_automation_mapping(
    mapping_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    mapping = await automation_service.get_mapping(db, mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Automation mapping not found")
    await require_permission(GENERATE_AUTOMATION, mapping.project_id, current_user, db)
    mapping = await automation_service.deactivate_mapping(db, mapping)
    await db.commit()
    return mapping


@router.post("/external/run", response_model=ExternalAutomationRunOut)
async def run_external_automation(
    body: ExternalAutomationRunRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_permission(GENERATE_AUTOMATION, body.project_id, current_user, db)
    run = await automation_service.run_external_automation(
        db,
        project_id=body.project_id,
        test_case_ids=body.test_case_ids,
        environment=body.environment,
        user_id=current_user.id,
    )
    await db.commit()
    return _run_summary(run)


@router.post("/external/sync-result", response_model=ExternalAutomationRunOut)
async def sync_external_automation_result(
    body: ExternalAutomationSyncRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    mapping = await automation_service.get_mapping(db, body.mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Automation mapping not found")
    await require_permission(GENERATE_AUTOMATION, mapping.project_id, current_user, db)
    run = await automation_service.sync_external_automation_result(
        db,
        mapping=mapping,
        environment=body.environment,
        user_id=current_user.id,
    )
    await db.commit()
    return _run_summary(run)


@router.get("/test-cases/{test_case_id}/execution-history", response_model=list[ExecutionResultOut])
async def get_execution_history(
    test_case_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    test_case = await automation_service.get_test_case_or_404(db, test_case_id)
    await require_project_access(test_case.project_id, current_user, db)
    return await automation_service.execution_history(db, test_case_id=test_case_id)


@router.post("/jira/sync-execution-status", response_model=JiraExecutionStatusOut)
async def sync_jira_execution_status(
    body: JiraExecutionStatusSyncRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    test_case = await automation_service.get_test_case_or_404(db, body.test_case_id)
    await require_permission(GENERATE_AUTOMATION, test_case.project_id, current_user, db)
    await automation_service.sync_jira_execution_status(
        db,
        test_case_id=body.test_case_id,
        jira_execution_status=body.jira_execution_status,
        jira_issue_key=body.jira_issue_key,
        jira_test_key=body.jira_test_key,
    )
    await db.commit()
    data = await automation_service.latest_jira_execution_status(db, test_case_id=body.test_case_id)
    return JiraExecutionStatusOut(**data)


@router.get("/jira/test-cases/{test_case_id}/execution-status", response_model=JiraExecutionStatusOut)
async def get_jira_execution_status(
    test_case_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    test_case = await automation_service.get_test_case_or_404(db, test_case_id)
    await require_project_access(test_case.project_id, current_user, db)
    data = await automation_service.latest_jira_execution_status(db, test_case_id=test_case_id)
    return JiraExecutionStatusOut(**data)


@router.get("/project/{project_id}", response_model=list[AutomationScriptOut])
async def list_automation_scripts(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    test_case_id: int | None = Query(None),
    status: str | None = Query(None),
):
    await require_project_access(project_id, current_user, db)
    return await automation_service.list_scripts(db, project_id, test_case_id, status)


@router.get("/planning/project/{project_id}", response_model=AutomationPlanningOut)
async def get_automation_planning(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_project_access(project_id, current_user, db)
    return await automation_service.planning_summary(db, project_id=project_id)


@router.get("/{script_id}", response_model=AutomationScriptOut)
async def get_automation_script(
    script_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    script = await automation_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Automation script not found")
    await require_entity_permission(script, GENERATE_AUTOMATION, current_user, db)
    return script


@router.patch("/{script_id}", response_model=AutomationScriptOut)
async def update_automation_script(
    script_id: int,
    updates: AutomationScriptUpdate,
    db: DBSession,
    current_user: CurrentUser,
):
    script = await automation_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Automation script not found")
    await require_entity_permission(script, GENERATE_AUTOMATION, current_user, db)
    script = await automation_service.update_script(db, script, updates)
    await db.commit()
    return script


@router.post("/{script_id}/approve", response_model=AutomationScriptOut)
async def approve_automation_script(
    script_id: int,
    body: ApprovalRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="action must be 'approve' or 'reject'")
    script = await automation_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Automation script not found")
    await require_entity_permission(script, GENERATE_AUTOMATION, current_user, db)
    script = await automation_service.approve_script(db, script, body.action, body.notes)
    await approval_service.create_approval_action(
        db,
        project_id=script.project_id,
        user_id=current_user.id,
        entity_type="automation_script",
        entity_id=script.id,
        action=body.action,
        notes=body.notes,
    )
    await db.commit()
    return script


# Phase 4.6: staged post-generation approval chain. Distinct from
# `/approve` above, which drives the legacy draft/in_review workflow —
# this one only accepts scripts already at dry_run_passed or later and
# advances them through role-gated stages, each stamped with the acting
# user's role for audit (see automation_service.advance_script_lifecycle).
_LIFECYCLE_ACTION_PERMISSIONS = {
    "reviewer_approve": AUTOMATION_REVIEW_SCRIPT,
    "reviewer_reject": AUTOMATION_REVIEW_SCRIPT,
    "lead_approve": AUTOMATION_APPROVE_SCRIPT,
    "lead_reject": AUTOMATION_APPROVE_SCRIPT,
    "environment_approve": AUTOMATION_APPROVE_ENVIRONMENT,
    "mark_ci_ready": APPROVE_RELEASE_REPORT,
}


@router.post("/{script_id}/lifecycle-approval", response_model=AutomationScriptOut)
async def lifecycle_approval_automation_script(
    script_id: int,
    body: LifecycleApprovalRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    script = await automation_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Automation script not found")
    permission = _LIFECYCLE_ACTION_PERMISSIONS[body.action]
    await require_entity_permission(script, permission, current_user, db)
    try:
        script = await automation_service.advance_script_lifecycle(db, script, body.action, body.notes)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    decision = "rejected" if body.action.endswith("_reject") else "approved"
    await approval_service.create_approval_action(
        db,
        project_id=script.project_id,
        user_id=current_user.id,
        entity_type="automation_script",
        entity_id=script.id,
        action=body.action,
        notes=body.notes,
        actor_role=current_user.role,
        decision=decision,
    )
    await db.commit()
    return script


@router.get("/{script_id}/confidence-score", response_model=AutomationConfidenceScoreOut)
async def get_automation_confidence_score(
    script_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    script = await automation_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Automation script not found")
    await require_entity_permission(script, GENERATE_AUTOMATION, current_user, db)
    return await automation_confidence_service.compute_confidence_score(db, script)


@router.post("/scripts/bulk-approve", response_model=BulkScriptApprovalResponse)
async def bulk_approve_automation_scripts(
    body: BulkScriptApprovalRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    if not body.script_ids:
        raise HTTPException(status_code=422, detail="script_ids must not be empty")

    results: list[BulkScriptApprovalResult] = []
    for script_id in body.script_ids:
        try:
            script = await automation_service.get_script(db, script_id)
            if not script:
                results.append(BulkScriptApprovalResult(script_id=script_id, ok=False, error="Script not found"))
                continue
            await require_entity_permission(script, GENERATE_AUTOMATION, current_user, db)
            script = await automation_service.approve_script(db, script, body.action, body.notes)
            await approval_service.create_approval_action(
                db,
                project_id=script.project_id,
                user_id=current_user.id,
                entity_type="automation_script",
                entity_id=script.id,
                action=body.action,
                notes=body.notes,
            )
            results.append(BulkScriptApprovalResult(script_id=script_id, ok=True))
        except HTTPException as e:
            results.append(BulkScriptApprovalResult(script_id=script_id, ok=False, error=str(e.detail)))

    await db.commit()
    approved_count = sum(1 for r in results if r.ok)
    return BulkScriptApprovalResponse(
        results=results,
        approved_count=approved_count,
        failed_count=len(results) - approved_count,
    )


@router.post("/{script_id}/transition", response_model=AutomationScriptOut)
async def transition_automation_script(
    script_id: int,
    body: ScriptTransitionRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Move a script through its lifecycle (submit_for_review / request_changes / restore_draft).

    Approve / reject continue to use the dedicated /approve endpoint so the
    approval ledger stays unambiguous.
    """
    script = await automation_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Automation script not found")
    await require_entity_permission(script, GENERATE_AUTOMATION, current_user, db)
    try:
        script = await automation_service.transition_script(db, script, body.action, body.notes)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return script


@router.post("/{script_id}/regenerate", response_model=AutomationScriptOut)
async def regenerate_automation_script(
    script_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """Re-run generation for this script using current application/URL
    context, overwriting its code in place and resetting it to draft for
    re-review. Fixes scripts generated before a real application URL was
    configured (e.g. ones that hardcoded a placeholder domain).
    """
    script = await automation_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Automation script not found")
    await require_entity_permission(script, GENERATE_AUTOMATION, current_user, db)
    script = await automation_service.regenerate_script(db, script, current_user.id)
    await db.commit()
    return script


# ── AI Intelligence Assistant (Phase 2D) ──────────────────────────────────────


@router.get("/{script_id}/intelligence")
async def get_script_intelligence(
    script_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """Run rule-based analyzers against the script and return findings.

    Pure-Python heuristics today (regex over the source). Findings shape is
    designed to be backwards-compatible when LLM-backed analyzers replace or
    augment the rules in a later phase.
    """
    script = await automation_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Automation script not found")
    await require_entity_project_access(script, current_user, db)
    report = automation_intelligence.analyze_script(script)
    decisions = (script.metadata_ or {}).get("recommendation_decisions", [])
    return {**report.as_dict(), "decisions": decisions}


@router.post(
    "/{script_id}/recommendations/{recommendation_id}/decision",
    response_model=AutomationScriptOut,
)
async def record_recommendation_decision(
    script_id: int,
    recommendation_id: str,
    body: RecommendationDecisionRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Record an apply/dismiss decision against a recommendation.

    Phase 2D logs the decision into ``metadata_.recommendation_decisions`` for
    audit. It does NOT modify the script's code — that lands in Phase 2E when
    the inline editor materializes draft changes.
    """
    script = await automation_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Automation script not found")
    await require_entity_permission(script, GENERATE_AUTOMATION, current_user, db)
    automation_intelligence.record_decision(
        script,
        recommendation_id=recommendation_id,
        action=body.action,
        user_id=current_user.id,
        notes=body.notes,
    )
    await db.commit()
    await db.refresh(script)
    return script


# ── Agent ─────────────────────────────────────────────────────────────────────

@router.post("/agent/generate-scripts")
async def trigger_automation_agent(
    body: AgentAutomationTrigger,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Trigger Agent 7 (Automation Script) from approved test cases.
    Generates Playwright or Pytest scripts.
    """
    await require_permission(GENERATE_AUTOMATION, body.project_id, current_user, db)

    test_cases = []
    skipped_not_approved = []
    skipped_wrong_project = []
    locator_map_by_application: dict[int, list[dict]] = {}
    for tc_id in body.test_case_ids:
        r = await db.execute(select(TestCase).where(TestCase.id == tc_id))
        tc = r.scalar_one_or_none()
        if not tc:
            continue
        if tc.project_id != body.project_id:
            skipped_wrong_project.append(tc_id)
            continue
        if tc.status != "approved":
            skipped_not_approved.append(tc_id)
            continue
        app_context = await build_test_case_application_context(db, tc)
        application = None
        if tc.application_id:
            application = await db.get(ProjectApplication, tc.application_id)
        if application is None:
            application = await resolve_default_application(db, body.project_id)
        application_id = application.id if application else None
        if application_id is not None and application_id not in locator_map_by_application:
            entries = await locator_map_service.list_for_application(
                db, project_id=body.project_id, application_id=application_id
            )
            locator_map_by_application[application_id] = [
                {
                    "element_name": e.element_name,
                    "page": e.page,
                    "role": e.recommended_strategy,
                    "business_meaning": e.business_meaning,
                    "recommended_locator": e.recommended_locator,
                    "confidence_score": e.confidence_score,
                }
                for e in entries
            ]
        test_cases.append({
            "id": tc.id,
            "test_case_id": tc.test_case_id,
            "title": tc.title,
            "preconditions": tc.preconditions,
            "steps": tc.steps,
            "expected_result": tc.expected_result,
            "bdd_scenario": tc.bdd_scenario,
            "test_type": tc.test_type,
            "priority": tc.priority,
            "application_id": application_id,
            **app_context,
        })

    if skipped_wrong_project:
        raise HTTPException(
            status_code=403,
            detail=f"Test case ID(s) {skipped_wrong_project} do not belong to project {body.project_id}",
        )

    if not test_cases:
        if skipped_not_approved:
            raise HTTPException(
                status_code=422,
                detail=f"All selected test cases must be 'approved' before generating scripts. "
                       f"Not yet approved: {skipped_not_approved}",
            )
        raise HTTPException(status_code=422, detail="No valid test cases found")

    if not _run_agents_synchronously():
        agent_run, task_id = await enqueue_agent_run(
            db,
            project_id=body.project_id,
            user_id=current_user.id,
            agent_name="automation_script",
            input_data={
                "test_cases": test_cases,
                "framework": body.framework,
                "locator_map": locator_map_by_application,
            },
            metadata={"approved_test_case_ids": [tc["id"] for tc in test_cases]},
        )
        return JSONResponse(
            status_code=202,
            content={"message": "Automation script generation queued", "agent_run_id": agent_run.id, "task_id": task_id},
        )

    user_id = current_user.id
    agent_run = await agent_run_service.start_agent_run(
        db,
        project_id=body.project_id,
        user_id=user_id,
        agent_name="automation_script",
        input_data=body.model_dump(mode="json"),
        metadata={"approved_test_case_ids": [tc["id"] for tc in test_cases]},
    )

    agent = AutomationScriptAgent()
    agent_result = await agent.run(test_cases=test_cases, framework=body.framework)

    if not agent_result.success:
        await agent_run_service.fail_agent_run(
            db,
            agent_run,
            error_message=agent_result.error or "Agent failed",
            agent_result=agent_result,
        )
        await db.commit()
        raise HTTPException(status_code=500, detail=agent_result.error or "Agent failed")

    # Map test_case_id string back to DB id
    tc_map = {tc["test_case_id"]: tc["id"] for tc in test_cases}

    scripts_data = agent_result.data.get("scripts", [])
    agent_errors = [log["message"] for log in (agent_result.logs or []) if log.get("level") == "warning"]
    if not scripts_data:
        detail = "; ".join(agent_errors) if agent_errors else "LLM returned no parseable scripts"
        await agent_run_service.fail_agent_run(
            db,
            agent_run,
            error_message=f"Agent generated 0 scripts: {detail}",
            agent_result=agent_result,
        )
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Agent generated 0 scripts: {detail}")

    def _to_str(val) -> str:
        """Coerce LLM value to string if needed (handles list/dict returns)."""
        if val is None:
            return ""
        if isinstance(val, str):
            return val
        import json as _json
        return _json.dumps(val)

    def _to_str_list(val) -> list[str] | None:
        if val is None:
            return None
        if isinstance(val, list):
            return [_to_str(item) for item in val]
        return [_to_str(val)]

    created_ids = []
    for i, sc_data in enumerate(scripts_data):
        tc_id_str = sc_data.get("test_case_id")
        db_tc_id = tc_map.get(tc_id_str)

        script = AutomationScript(
            project_id=body.project_id,
            test_case_id=db_tc_id,
            created_by=user_id,
            script_id=temporary_id("AS"),
            framework=body.framework,
            file_path=_to_str(sc_data.get("file_path")) or None,
            code=_to_str(sc_data.get("code")),
            setup_required=_to_str_list(sc_data.get("setup_required")),
            execution_command=_to_str(sc_data.get("execution_command")) or None,
            status="ai_draft",
            agent_run_id=agent_run.id,
            metadata_={
                "language": framework_language(body.framework),
                "repository": "Connected repository pending",
                "branch": "codex/automation-drafts",
                "coverage_hint": "Generated from approved test case",
                "suite": "Generated Drafts",
                "review_state": "pending_human_review",
                "source": "ai_generation",
            },
        )
        db.add(script)
        await db.flush()
        script.script_id = display_id("AS", script.id)
        await db.flush()
        if db_tc_id is not None:
            await traceability_service.create_lineage(
                db,
                project_id=body.project_id,
                parent_type="test_case",
                parent_id=db_tc_id,
                child_type="automation_script",
                child_id=script.id,
                agent_run_id=agent_run.id,
            )
        created_ids.append(script.id)

    await agent_run_service.complete_agent_run(
        db,
        agent_run,
        agent_result=agent_result,
        output_data={"script_ids": created_ids, "count": len(created_ids)},
    )
    await db.commit()
    return {
        "message": f"Generated {len(created_ids)} automation scripts",
        "script_ids": created_ids,
        "agent_logs": agent_result.logs,
        "agent_run_id": agent_run.id,
    }


@router.post("/agent/discover-ui")
async def trigger_mcp_discovery_agent(
    body: AgentMCPDiscoveryTrigger,
    db: DBSession,
    current_user: CurrentUser,
):
    """Trigger the Playwright MCP Discovery Agent (Phase 3): opens the
    project-configured application in a real, isolated headless browser
    session and builds a ranked locator knowledge base for the given test
    cases. Always queued (never a synchronous fallback) — a real browser
    session belongs on the worker, not the request thread. A deliberate,
    user-triggered action (like script generation) rather than an automatic
    chain, since it spawns a real process against a live environment.
    """
    await require_permission(GENERATE_AUTOMATION, body.project_id, current_user, db)

    test_cases = []
    for tc_id in body.test_case_ids:
        result = await db.execute(select(TestCase).where(TestCase.id == tc_id))
        tc = result.scalar_one_or_none()
        if not tc or tc.project_id != body.project_id:
            continue
        application = None
        if tc.application_id:
            application = await db.get(ProjectApplication, tc.application_id)
        if application is None:
            application = await resolve_default_application(db, body.project_id)
        application_url = resolve_environment_url(application, body.environment)
        test_cases.append({
            "id": tc.id,
            "test_case_id": tc.test_case_id,
            "title": tc.title,
            "steps": tc.steps or [],
            "application_id": application.id if application else None,
            "application_url": application_url,
        })

    if not test_cases:
        raise HTTPException(status_code=422, detail="No valid test cases found in this project")
    if not any(tc["application_url"] for tc in test_cases):
        raise HTTPException(
            status_code=422,
            detail=(
                f"No application URL configured for environment '{body.environment}'. "
                "Configure one in Project Settings → Applications & Environments."
            ),
        )

    agent_run, task_id = await enqueue_agent_run(
        db,
        project_id=body.project_id,
        user_id=current_user.id,
        agent_name="playwright_mcp_discovery",
        input_data={"test_cases": test_cases},
        metadata={"test_case_ids": [tc["id"] for tc in test_cases], "environment": body.environment},
    )
    return JSONResponse(
        status_code=202,
        content={"message": "Playwright MCP discovery queued", "agent_run_id": agent_run.id, "task_id": task_id},
    )


# ── Local subprocess runner ───────────────────────────────────────────────────


@router.get("/runner/status", response_model=RunnerStatusOut)
async def get_runner_status(current_user: CurrentUser):
    """Tell the UI which frameworks can actually execute on this host.

    Caller authenticated; no project scope — runner availability is host-wide.
    """
    status = runtime_status()
    return RunnerStatusOut(
        frameworks=[
            RunnerFrameworkStatus(framework=key, available=val.available, detail=val.detail)
            for key, val in status.items()
        ]
    )


@router.post(
    "/scripts/{script_id}/execute",
    response_model=AutomationScriptExecuteResponse,
    status_code=202,
)
async def execute_automation_script(
    script_id: int,
    body: AutomationScriptExecuteRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Run an approved AutomationScript through the local subprocess runner.

    Synchronously creates an ExecutionRun + a placeholder ExecutionResult so the
    artifacts endpoint has stable IDs, then enqueues a Celery task that does the
    actual subprocess work.
    """
    script = await automation_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Automation script not found")
    await require_permission(EXECUTE_TESTS, script.project_id, current_user, db)

    if script.status not in {"approved", "executed"}:
        raise HTTPException(
            status_code=422,
            detail="Script must be approved before it can be executed.",
        )

    framework = (script.framework or "").lower()
    if framework not in {"playwright", "pytest"}:
        raise HTTPException(
            status_code=422,
            detail=f"Framework '{script.framework}' is not supported by the local runner.",
        )

    # Create the ExecutionRun. Status starts as 'queued' so the UI can render
    # it before the worker even picks the task up.
    run = ExecutionRun(
        project_id=script.project_id,
        created_by=current_user.id,
        execution_id=temporary_id("ER"),
        suite_name=f"Automation: {script.script_id}",
        environment=body.environment,
        status="queued",
        execution_type="automation",
        source_type="automation_local",
        total_tests=1,
        passed=0,
        failed=0,
        skipped=0,
        execution_logs=[],
        metadata_={
            "source_type": "automation_local",
            "automation_script_id": script.id,
            "framework": framework,
            "timeout_seconds": body.timeout_seconds,
        },
    )
    db.add(run)
    await db.flush()
    run.execution_id = display_id("ER", run.id)
    await db.flush()

    # One placeholder ExecutionResult so the UI has something to show before
    # the worker fills in the per-test outcomes.
    placeholder = ExecutionResult(
        execution_run_id=run.id,
        test_case_id=script.test_case_id,
        project_id=script.project_id,
        test_name=script.script_id,
        status="pending",
    )
    db.add(placeholder)
    await db.flush()

    await db.commit()

    # Enqueue the actual run
    from app.worker.tasks.automation_tasks import run_automation_script

    async_result = run_automation_script.delay(run.id, body.timeout_seconds)
    task_id = str(async_result.id) if async_result else None
    if task_id:
        # Persisted so a later Cancel Run request can revoke the Celery task.
        run.metadata_ = {**(run.metadata_ or {}), "task_id": task_id}
        await db.commit()
    return AutomationScriptExecuteResponse(
        execution_run_id=run.id,
        task_id=task_id,
        status="queued",
        message=(
            f"Automation script {script.script_id} queued on the local "
            f"{framework} runner."
        ),
    )


@router.post(
    "/project/{project_id}/execute-batch",
    response_model=AutomationBatchExecuteResponse,
    status_code=202,
)
async def execute_automation_batch(
    project_id: int,
    body: AutomationBatchExecuteRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Run several approved scripts as one batch — "Run All Eligible" / suite runs.

    Creates a single ExecutionRun covering every script (one placeholder
    ExecutionResult each, tagged with metadata_.automation_script_id), then
    enqueues a Celery task that executes them sequentially against the local
    subprocess runner and commits progress after each script.
    """
    await require_permission(EXECUTE_TESTS, project_id, current_user, db)

    result = await db.execute(
        select(AutomationScript).where(AutomationScript.id.in_(body.script_ids))
    )
    scripts_by_id = {s.id: s for s in result.scalars().all()}
    missing = [sid for sid in body.script_ids if sid not in scripts_by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Automation script(s) not found: {missing}")

    # Preserve caller-specified order but dedupe (a script appearing twice
    # would otherwise get two ExecutionResult placeholders).
    seen: set[int] = set()
    ordered_scripts: list[AutomationScript] = []
    for sid in body.script_ids:
        if sid in seen:
            continue
        seen.add(sid)
        ordered_scripts.append(scripts_by_id[sid])

    wrong_project = [s.script_id for s in ordered_scripts if s.project_id != project_id]
    if wrong_project:
        raise HTTPException(status_code=422, detail=f"Script(s) not in project {project_id}: {wrong_project}")

    not_approved = [s.script_id for s in ordered_scripts if s.status not in {"approved", "executed"}]
    if not_approved:
        raise HTTPException(
            status_code=422,
            detail=f"Script(s) must be approved before batch execution: {not_approved}",
        )

    unsupported = [
        f"{s.script_id} ({s.framework})"
        for s in ordered_scripts
        if (s.framework or "").lower() not in {"playwright", "pytest"}
    ]
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail=f"Framework not supported by the local runner: {unsupported}",
        )

    run = ExecutionRun(
        project_id=project_id,
        created_by=current_user.id,
        execution_id=temporary_id("ER"),
        suite_name=body.run_name or f"All Eligible Automation ({len(ordered_scripts)})",
        environment=body.environment,
        status="queued",
        execution_type="automation",
        source_type="automation_local_batch",
        total_tests=len(ordered_scripts),
        passed=0,
        failed=0,
        skipped=0,
        execution_logs=[],
        metadata_={
            "source_type": "automation_local_batch",
            "automation_script_ids": [s.id for s in ordered_scripts],
            "timeout_seconds": body.timeout_seconds,
            "parent_run_id": body.parent_run_id,
        },
    )
    db.add(run)
    await db.flush()
    run.execution_id = display_id("ER", run.id)
    await db.flush()

    for script in ordered_scripts:
        placeholder = ExecutionResult(
            execution_run_id=run.id,
            test_case_id=script.test_case_id,
            project_id=project_id,
            test_name=script.script_id,
            status="pending",
            metadata_={"automation_script_id": script.id},
        )
        db.add(placeholder)
    await db.flush()

    await db.commit()

    from app.worker.tasks.automation_tasks import run_automation_batch

    async_result = run_automation_batch.delay(run.id, body.timeout_seconds)
    task_id = str(async_result.id) if async_result else None
    if task_id:
        # Persisted so a later Cancel Run request can revoke the Celery task.
        run.metadata_ = {**(run.metadata_ or {}), "task_id": task_id}
        await db.commit()
    return AutomationBatchExecuteResponse(
        execution_run_id=run.id,
        task_id=task_id,
        status="queued",
        script_count=len(ordered_scripts),
        message=f"{len(ordered_scripts)} automation script(s) queued as batch run {run.execution_id}.",
    )


@router.post(
    "/runs/{run_id}/cancel",
    response_model=AutomationRunCancelResponse,
)
async def cancel_automation_run(
    run_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """Best-effort cancel for a local-runner automation run.

    Revokes the Celery task (terminate=True) and marks the run + any
    still-pending ExecutionResult rows as cancelled/skipped immediately, so
    the UI reflects the cancellation right away. If the task has already
    progressed past a checkpoint the revoke may not stop it mid-subprocess —
    the run's final DB state still wins once/if the task itself resumes.
    """
    run = await db.get(ExecutionRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    await require_permission(EXECUTE_TESTS, run.project_id, current_user, db)

    source_type = (run.metadata_ or {}).get("source_type")
    if source_type not in {"automation_local", "automation_local_batch"}:
        raise HTTPException(
            status_code=422,
            detail="Only local-runner automation runs (single or batch) can be cancelled here.",
        )
    if run.status not in {"pending", "queued", "running"}:
        raise HTTPException(status_code=422, detail=f"Run is already '{run.status}' — nothing to cancel.")

    task_id = (run.metadata_ or {}).get("task_id")
    if task_id:
        from app.worker.celery_app import celery_app

        try:
            celery_app.control.revoke(task_id, terminate=True)
        except Exception:
            # Best-effort — a broker hiccup shouldn't block the user from
            # marking the run cancelled in the DB.
            pass

    result = await db.execute(
        select(ExecutionResult).where(
            ExecutionResult.execution_run_id == run.id,
            ExecutionResult.status.in_(["pending", "running"]),
        )
    )
    for pending_result in result.scalars().all():
        pending_result.status = "skip"
        pending_result.error_message = pending_result.error_message or "Cancelled before this test ran."

    run.status = "cancelled"
    run.metadata_ = {**(run.metadata_ or {}), "cancelled_by": current_user.id}
    await db.commit()

    return AutomationRunCancelResponse(
        execution_run_id=run.id,
        status=run.status,
        message=f"Run {run.execution_id} cancelled.",
    )


# Artifact kinds the runner can produce. We keep this list explicit so the
# endpoint can't be tricked into serving arbitrary files.
_ARTIFACT_KIND_TO_FIELD = {
    "log": "logs",
    "screenshot": "screenshot_path",
    "video": "video_path",
    "trace": "trace_path",
}


@router.get("/runner/results/{result_id}/artifact/{kind}")
async def download_runner_artifact(
    result_id: int,
    kind: str,
    db: DBSession,
    current_user: CurrentUser,
):
    """Stream a runner-produced artifact for an ExecutionResult.

    kind ∈ { log | screenshot | video | trace }.
    """
    if kind not in _ARTIFACT_KIND_TO_FIELD:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported artifact kind '{kind}'. Allowed: {list(_ARTIFACT_KIND_TO_FIELD)}",
        )
    result = await db.get(ExecutionResult, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Execution result not found")
    await require_permission(EXECUTE_TESTS, result.project_id, current_user, db)

    field = _ARTIFACT_KIND_TO_FIELD[kind]
    if kind == "log":
        logs = result.logs or []
        # We stored the log path as a single-element list in the runner.
        path = next((p for p in logs if isinstance(p, str)), None)
    else:
        path = getattr(result, field, None)

    if not path or not os.path.exists(path):
        raise HTTPException(status_code=410, detail=f"{kind} artifact is no longer available")

    # Defence in depth: only serve files under the configured storage path.
    storage_root = os.path.realpath(settings.file_storage_path)
    real_path = os.path.realpath(path)
    if not real_path.startswith(storage_root + os.sep) and real_path != storage_root:
        raise HTTPException(status_code=403, detail="Artifact path is outside the storage root")

    media_type_map = {
        "log": "text/plain",
        "screenshot": "image/png",
        "video": "video/webm",
        "trace": "application/zip",
    }
    return FileResponse(
        real_path,
        media_type=media_type_map.get(kind, "application/octet-stream"),
        filename=os.path.basename(real_path),
    )
