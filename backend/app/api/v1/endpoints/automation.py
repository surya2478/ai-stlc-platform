"""
Automation Scripts endpoints — Phase 4.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func

from app.api.deps import DBSession, OptionalUser
from app.models.automation_script import AutomationScript
from app.models.test_case import TestCase
from app.models.project import Project
from app.schemas.automation import AutomationScriptOut, AutomationScriptUpdate, AgentAutomationTrigger
from app.schemas.requirement import ApprovalRequest
from app.services import automation_service
from app.agents.automation.automation_agent import AutomationScriptAgent

router = APIRouter()


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/project/{project_id}", response_model=list[AutomationScriptOut])
async def list_automation_scripts(
    project_id: int,
    db: DBSession,
    current_user: OptionalUser,
    test_case_id: int | None = Query(None),
    status: str | None = Query(None),
):
    return await automation_service.list_scripts(db, project_id, test_case_id, status)


@router.get("/{script_id}", response_model=AutomationScriptOut)
async def get_automation_script(
    script_id: int,
    db: DBSession,
    current_user: OptionalUser,
):
    script = await automation_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Automation script not found")
    return script


@router.patch("/{script_id}", response_model=AutomationScriptOut)
async def update_automation_script(
    script_id: int,
    updates: AutomationScriptUpdate,
    db: DBSession,
    current_user: OptionalUser,
):
    script = await automation_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Automation script not found")
    script = await automation_service.update_script(db, script, updates)
    await db.commit()
    return script


@router.post("/{script_id}/approve", response_model=AutomationScriptOut)
async def approve_automation_script(
    script_id: int,
    body: ApprovalRequest,
    db: DBSession,
    current_user: OptionalUser,
):
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="action must be 'approve' or 'reject'")
    script = await automation_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Automation script not found")
    script = await automation_service.approve_script(db, script, body.action, body.notes)
    await db.commit()
    return script


# ── Agent ─────────────────────────────────────────────────────────────────────

@router.post("/agent/generate-scripts")
async def trigger_automation_agent(
    body: AgentAutomationTrigger,
    db: DBSession,
    current_user: OptionalUser,
):
    """
    Trigger Agent 7 (Automation Script) from approved test cases.
    Generates Playwright or Pytest scripts.
    """
    result = await db.execute(select(Project).where(Project.id == body.project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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

    agent = AutomationScriptAgent()
    agent_result = await agent.run(test_cases=test_cases, framework=body.framework)

    if not agent_result.success:
        raise HTTPException(status_code=500, detail=agent_result.error or "Agent failed")

    count_result = await db.execute(
        select(func.count()).where(AutomationScript.project_id == body.project_id)
    )
    script_count = count_result.scalar_one()

    # Map test_case_id string back to DB id
    tc_map = {tc["test_case_id"]: tc["id"] for tc in test_cases}

    scripts_data = agent_result.data.get("scripts", [])
    agent_errors = [log["message"] for log in (agent_result.logs or []) if log.get("level") == "warning"]
    if not scripts_data:
        detail = "; ".join(agent_errors) if agent_errors else "LLM returned no parseable scripts"
        raise HTTPException(status_code=500, detail=f"Agent generated 0 scripts: {detail}")

    def _to_str(val) -> str | None:
        """Coerce LLM value to string if needed (handles list/dict returns)."""
        if val is None:
            return None
        if isinstance(val, str):
            return val
        import json as _json
        return _json.dumps(val)

    created_ids = []
    for i, sc_data in enumerate(scripts_data):
        tc_id_str = sc_data.get("test_case_id")
        db_tc_id = tc_map.get(tc_id_str)

        script = AutomationScript(
            project_id=body.project_id,
            test_case_id=db_tc_id,
            created_by=(current_user.id if current_user else 1),
            script_id=f"AS-{(script_count + i + 1):04d}",
            framework=body.framework,
            title=sc_data.get("title", "Untitled Script"),
            script_content=_to_str(sc_data.get("script_content")),
            imports=_to_str(sc_data.get("imports")),
            fixtures=_to_str(sc_data.get("fixtures")),
            page_objects=_to_str(sc_data.get("page_objects")),
            status="draft",
        )
        db.add(script)
        await db.flush()
        created_ids.append(script.id)

    await db.commit()
    return {
        "message": f"Generated {len(created_ids)} automation scripts",
        "script_ids": created_ids,
        "agent_logs": agent_result.logs,
    }
