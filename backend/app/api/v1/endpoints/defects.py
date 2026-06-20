"""
Defect Management endpoints — Phase 6.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, func

from app.api.deps import CurrentUser, DBSession, require_entity_permission, require_entity_project_access, require_permission, require_project_access
from app.config import get_settings
from app.models.defect import DefectDraft, JiraDefect
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.test_case import TestCase
from app.models.project import Project
from app.schemas.defect import DefectDraftOut, DefectDraftUpdate, JiraDefectOut, AgentDefectTrigger, DefectDraftCreate
from app.schemas.requirement import ApprovalRequest
from app.services import agent_run_service, approval_service, defect_service, traceability_service
from app.services.agent_dispatch_service import enqueue_agent_run
from app.services.display_id_service import display_id, temporary_id
from app.services.rbac_service import PUSH_DEFECTS_TO_JIRA, RAISE_DEFECTS
from app.agents.defect.defect_agent import DefectAnalysisAgent
from app.models.jira_connection import JiraConnection
from app.services.jira_service import JiraService

router = APIRouter()
settings = get_settings()


def _run_agents_synchronously() -> bool:
    return False


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.post("", response_model=DefectDraftOut, status_code=201)
@router.post("/", response_model=DefectDraftOut, status_code=201)
async def create_defect(
    body: DefectDraftCreate,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_project_access(body.project_id, current_user, db)
    await require_permission(RAISE_DEFECTS, body.project_id, current_user, db)

    execution_result_id = body.execution_result_id
    if execution_result_id is not None:
        if execution_result_id <= 0:
            execution_result_id = None
        else:
            result = await db.execute(
                select(ExecutionResult).where(ExecutionResult.id == execution_result_id)
            )
            execution_result = result.scalar_one_or_none()
            if not execution_result:
                raise HTTPException(status_code=422, detail="Execution result not found")
            if execution_result.project_id != body.project_id:
                raise HTTPException(status_code=403, detail="Execution result does not belong to this project")

    test_case_id = body.test_case_id
    if test_case_id is not None:
        result = await db.execute(select(TestCase).where(TestCase.id == test_case_id))
        test_case = result.scalar_one_or_none()
        if not test_case:
            raise HTTPException(status_code=422, detail="Test case not found")
        if test_case.project_id != body.project_id:
            raise HTTPException(status_code=403, detail="Test case does not belong to this project")
    
    # Create the draft
    draft = DefectDraft(
        project_id=body.project_id,
        test_case_id=test_case_id,
        execution_result_id=execution_result_id,
        created_by=current_user.id,
        defect_id=temporary_id("DEF"),
        summary=body.summary,
        description=body.description,
        steps_to_reproduce=body.steps_to_reproduce,
        expected_result=body.expected_result,
        actual_result=body.actual_result,
        severity=body.severity,
        priority=body.priority,
        root_cause_hypothesis=body.root_cause_hypothesis,
        classification=body.classification,
        status="draft",
        jira_ready=False,
    )
    db.add(draft)
    await db.flush()
    draft.defect_id = display_id("DEF", draft.id)
    await db.flush()
    
    # Lineage and traceability linkage
    parents = []
    if body.execution_result_id is not None:
        parents.append(("execution_result", body.execution_result_id))
    if body.test_case_id is not None:
        parents.append(("test_case", body.test_case_id))
        
    if parents:
        await traceability_service.create_lineage_many(
            db,
            project_id=body.project_id,
            parents=parents,
            child_type="defect_draft",
            child_id=draft.id,
        )
    await db.commit()
    await db.refresh(draft)
    return draft


@router.get("/project/{project_id}", response_model=list[DefectDraftOut])
async def list_defects(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    status: str | None = Query(None),
):
    await require_project_access(project_id, current_user, db)
    return await defect_service.list_defects(db, project_id, status)


@router.get("/{defect_id}", response_model=DefectDraftOut)
async def get_defect(
    defect_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    defect = await defect_service.get_defect(db, defect_id)
    if not defect:
        raise HTTPException(status_code=404, detail="Defect not found")
    await require_entity_permission(defect, RAISE_DEFECTS, current_user, db)
    return defect


@router.patch("/{defect_id}", response_model=DefectDraftOut)
async def update_defect(
    defect_id: int,
    updates: DefectDraftUpdate,
    db: DBSession,
    current_user: CurrentUser,
):
    defect = await defect_service.get_defect(db, defect_id)
    if not defect:
        raise HTTPException(status_code=404, detail="Defect not found")
    await require_entity_permission(defect, RAISE_DEFECTS, current_user, db)
    defect = await defect_service.update_defect(db, defect, updates)
    await db.commit()
    await db.refresh(defect)
    return defect


@router.post("/{defect_id}/approve", response_model=DefectDraftOut)
async def approve_defect(
    defect_id: int,
    body: ApprovalRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    defect = await defect_service.get_defect(db, defect_id)
    if not defect:
        raise HTTPException(status_code=404, detail="Defect not found")
    await require_entity_permission(defect, PUSH_DEFECTS_TO_JIRA, current_user, db)
    defect = await defect_service.approve_defect(db, defect, body.action, body.notes)
    await approval_service.create_approval_action(
        db,
        project_id=defect.project_id,
        user_id=current_user.id,
        entity_type="defect_draft",
        entity_id=defect.id,
        action=body.action,
        notes=body.notes,
    )
    await db.commit()
    await db.refresh(defect)
    return defect


# ── Jira Defect Push ─────────────────────────────────────────────────────────

@router.post("/{defect_id}/push-to-jira", response_model=JiraDefectOut)
async def push_defect_to_jira(
    defect_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Push an approved defect draft to Jira.
    """
    defect = await defect_service.get_defect(db, defect_id)
    if not defect:
        raise HTTPException(status_code=404, detail="Defect not found")
    await require_entity_permission(defect, PUSH_DEFECTS_TO_JIRA, current_user, db)
    if defect.status != "approved":
        raise HTTPException(status_code=422, detail="Only approved defects can be pushed to Jira")

    # Look up active Jira connection
    connection_result = await db.execute(
        select(JiraConnection)
        .where(JiraConnection.project_id == defect.project_id)
        .where(JiraConnection.is_active == True)
        .limit(1)
    )
    connection = connection_result.scalar_one_or_none()
    if not connection:
        raise HTTPException(
            status_code=400,
            detail="No active Jira connection configured for this project. Please configure it in Requirements -> Integrations."
        )

    # Construct description in Atlassian Document Format (ADF)
    description_lines = []
    if defect.description:
        description_lines.append(defect.description)
    if defect.steps_to_reproduce:
        steps = defect.steps_to_reproduce
        if isinstance(steps, list):
            steps_str = "\n".join(f"- {s}" for s in steps)
        else:
            steps_str = str(steps)
        description_lines.append(f"Steps to Reproduce:\n{steps_str}")
    if defect.expected_result:
        description_lines.append(f"Expected Result:\n{defect.expected_result}")
    if defect.actual_result:
        description_lines.append(f"Actual Result:\n{defect.actual_result}")
    
    full_description = "\n\n".join(description_lines) if description_lines else "No description provided."

    payload = {
        "fields": {
            "project": {
                "key": connection.jira_project_key
            },
            "summary": defect.summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": full_description
                            }
                        ]
                    }
                ]
            },
            "issuetype": {
                "name": "Bug"
            }
        }
    }

    # Call Jira REST API
    jira_service_inst = JiraService(db)
    response_data = await jira_service_inst._request(
        connection,
        "POST",
        "/rest/api/3/issue",
        token=jira_service_inst.decrypt_token(connection),
        json=payload
    )

    issue_key = response_data.get("key")
    if not issue_key:
        raise HTTPException(
            status_code=502,
            detail="Jira responded successfully but did not return an issue key."
        )

    base_url = connection.jira_base_url.rstrip("/")
    jira_url = f"{base_url}/browse/{issue_key}"

    jira_defect = JiraDefect(
        defect_draft_id=defect.id,
        project_id=defect.project_id,
        created_by=current_user.id,
        jira_issue_key=issue_key,
        jira_url=jira_url,
        jira_status="Open",
        status="created",
    )
    db.add(jira_defect)

    defect.status = "pushed_to_jira"
    defect.jira_ready = True
    await db.flush()
    await db.refresh(jira_defect)
    await db.commit()
    return jira_defect


# ── Agent ─────────────────────────────────────────────────────────────────────

@router.post("/agent/analyse-defects")
async def trigger_defect_agent(
    body: AgentDefectTrigger,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Trigger Agent 9 (Defect Analysis) from failed execution results.
    Generates DefectDraft records.
    """
    project = await require_permission(RAISE_DEFECTS, body.project_id, current_user, db)

    failed_results = []

    if body.execution_result_ids:
        for er_id in body.execution_result_ids:
            r = await db.execute(select(ExecutionResult).where(ExecutionResult.id == er_id))
            er = r.scalar_one_or_none()
            if er and er.status == "failed":
                if er.project_id != body.project_id:
                    raise HTTPException(status_code=403, detail="Execution result does not belong to this project")
                failed_results.append({
                    "id": er.id,
                    "test_name": er.test_name,
                    "test_case_id": er.test_case_id,
                    "error_message": er.error_message,
                    "stack_trace": er.stack_trace,
                    "logs": er.logs,
                })
    elif body.test_case_ids:
        # Find latest failed results for these test cases
        for tc_id in body.test_case_ids:
            tc_result = await db.execute(select(TestCase).where(TestCase.id == tc_id))
            tc = tc_result.scalar_one_or_none()
            if tc and tc.project_id != body.project_id:
                raise HTTPException(status_code=403, detail="Test case does not belong to this project")
            r = await db.execute(
                select(ExecutionResult)
                .where(ExecutionResult.test_case_id == tc_id)
                .where(ExecutionResult.status == "failed")
                .order_by(ExecutionResult.created_at.desc())
                .limit(1)
            )
            er = r.scalar_one_or_none()
            if er:
                failed_results.append({
                    "id": er.id,
                    "test_name": er.test_name,
                    "test_case_id": er.test_case_id,
                    "error_message": er.error_message,
                    "stack_trace": er.stack_trace,
                    "logs": er.logs,
                })

    if not failed_results:
        raise HTTPException(status_code=422, detail="No failed execution results found for defect analysis")

    if not _run_agents_synchronously():
        agent_run, task_id = await enqueue_agent_run(
            db,
            project_id=body.project_id,
            user_id=current_user.id,
            agent_name="defect_analysis",
            input_data={"failed_results": failed_results, "project_name": project.name},
            metadata={"failed_execution_result_ids": [r["id"] for r in failed_results]},
        )
        return JSONResponse(
            status_code=202,
            content={"message": "Defect analysis queued", "agent_run_id": agent_run.id, "task_id": task_id},
        )

    user_id = current_user.id
    agent_run = await agent_run_service.start_agent_run(
        db,
        project_id=body.project_id,
        user_id=user_id,
        agent_name="defect_analysis",
        input_data=body.model_dump(mode="json"),
        metadata={"failed_execution_result_ids": [r["id"] for r in failed_results]},
    )

    agent = DefectAnalysisAgent()
    agent_result = await agent.run(
        failed_results=failed_results,
        project_name=project.name,
    )

    if not agent_result.success:
        await agent_run_service.fail_agent_run(
            db,
            agent_run,
            error_message=agent_result.error or "Agent failed",
            agent_result=agent_result,
        )
        await db.commit()
        raise HTTPException(status_code=500, detail=agent_result.error or "Agent failed")

    # Map execution_result ref → DB id
    er_map = {r["test_name"]: r["id"] for r in failed_results}
    er_tc_map = {r["test_name"]: r.get("test_case_id") for r in failed_results}

    created_ids = []
    for i, d_data in enumerate(agent_result.data.get("defects", [])):
        ref = d_data.get("execution_result_ref", "")
        er_id = er_map.get(ref)
        tc_id = er_tc_map.get(ref)

        draft = DefectDraft(
            project_id=body.project_id,
            test_case_id=tc_id,
            execution_result_id=er_id,
            created_by=user_id,
            defect_id=temporary_id("DEF"),
            summary=d_data.get("summary", "Defect detected"),
            description=d_data.get("description"),
            steps_to_reproduce=d_data.get("steps_to_reproduce"),
            expected_result=d_data.get("expected_result"),
            actual_result=d_data.get("actual_result"),
            severity=d_data.get("severity", "Medium"),
            priority=d_data.get("priority", "Medium"),
            root_cause_hypothesis=d_data.get("root_cause_hypothesis"),
            classification=d_data.get("classification", "product_defect"),
            status="draft",
            jira_ready=False,
            agent_run_id=agent_run.id,
        )
        db.add(draft)
        await db.flush()
        draft.defect_id = display_id("DEF", draft.id)
        await db.flush()
        parents = []
        if er_id is not None:
            parents.append(("execution_result", er_id))
        if tc_id is not None:
            parents.append(("test_case", tc_id))
        await traceability_service.create_lineage_many(
            db,
            project_id=body.project_id,
            parents=parents,
            child_type="defect_draft",
            child_id=draft.id,
            agent_run_id=agent_run.id,
        )
        created_ids.append(draft.id)

    if not created_ids:
        agent_errors = [
            log["message"] for log in (agent_result.logs or [])
            if log.get("level") == "warning"
        ]
        detail = "; ".join(agent_errors) if agent_errors else "LLM returned 0 parseable defects"
        await agent_run_service.fail_agent_run(
            db,
            agent_run,
            error_message=f"Agent generated 0 defects: {detail}",
            agent_result=agent_result,
        )
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Agent generated 0 defects: {detail}")

    await agent_run_service.complete_agent_run(
        db,
        agent_run,
        agent_result=agent_result,
        output_data={"defect_ids": created_ids, "count": len(created_ids)},
    )
    await db.commit()

    return {
        "message": f"Generated {len(created_ids)} defect drafts from {len(failed_results)} failed tests",
        "defect_ids": created_ids,
        "agent_logs": agent_result.logs,
        "agent_run_id": agent_run.id,
    }
