"""
Automation Scripts endpoints — Phase 4.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, require_entity_permission, require_entity_project_access, require_permission, require_project_access
from app.config import get_settings
from app.models.automation_script import AutomationScript
from app.models.test_case import TestCase
from app.schemas.automation import (
    AgentAutomationTrigger,
    AutomationScriptOut,
    AutomationScriptUpdate,
    AutomationTestMappingCreate,
    AutomationTestMappingOut,
    AutomationTestMappingUpdate,
    ExternalAutomationRunOut,
    ExternalAutomationRunRequest,
    ExternalAutomationSyncRequest,
    JiraExecutionStatusOut,
    JiraExecutionStatusSyncRequest,
)
from app.schemas.execution import ExecutionResultOut
from app.schemas.requirement import ApprovalRequest
from app.services import agent_run_service, approval_service, automation_service, traceability_service
from app.services.agent_dispatch_service import enqueue_agent_run
from app.services.display_id_service import display_id, temporary_id
from app.services.rbac_service import GENERATE_AUTOMATION
from app.agents.automation.automation_agent import AutomationScriptAgent

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
            input_data={"test_cases": test_cases, "framework": body.framework},
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
            status="draft",
            agent_run_id=agent_run.id,
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
