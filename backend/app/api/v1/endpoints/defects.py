"""
Defect Management endpoints — Phase 6.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func

from app.api.deps import DBSession, OptionalUser
from app.models.defect import DefectDraft, JiraDefect
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.test_case import TestCase
from app.models.project import Project
from app.schemas.defect import DefectDraftOut, DefectDraftUpdate, JiraDefectOut, AgentDefectTrigger
from app.schemas.requirement import ApprovalRequest
from app.services import defect_service
from app.agents.defect.defect_agent import DefectAnalysisAgent

router = APIRouter()


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/project/{project_id}", response_model=list[DefectDraftOut])
async def list_defects(
    project_id: int,
    db: DBSession,
    current_user: OptionalUser,
    status: str | None = Query(None),
):
    return await defect_service.list_defects(db, project_id, status)


@router.get("/{defect_id}", response_model=DefectDraftOut)
async def get_defect(
    defect_id: int,
    db: DBSession,
    current_user: OptionalUser,
):
    defect = await defect_service.get_defect(db, defect_id)
    if not defect:
        raise HTTPException(status_code=404, detail="Defect not found")
    return defect


@router.patch("/{defect_id}", response_model=DefectDraftOut)
async def update_defect(
    defect_id: int,
    updates: DefectDraftUpdate,
    db: DBSession,
    current_user: OptionalUser,
):
    defect = await defect_service.get_defect(db, defect_id)
    if not defect:
        raise HTTPException(status_code=404, detail="Defect not found")
    defect = await defect_service.update_defect(db, defect, updates)
    await db.commit()
    return defect


@router.post("/{defect_id}/approve", response_model=DefectDraftOut)
async def approve_defect(
    defect_id: int,
    body: ApprovalRequest,
    db: DBSession,
    current_user: OptionalUser,
):
    defect = await defect_service.get_defect(db, defect_id)
    if not defect:
        raise HTTPException(status_code=404, detail="Defect not found")
    defect = await defect_service.approve_defect(db, defect, body.action, body.notes)
    await db.commit()
    return defect


# ── Simulated Jira Push ───────────────────────────────────────────────────────

@router.post("/{defect_id}/push-to-jira", response_model=JiraDefectOut)
async def push_defect_to_jira(
    defect_id: int,
    db: DBSession,
    current_user: OptionalUser,
):
    """
    Simulate pushing an approved defect draft to Jira.
    In production, this would call the Jira REST API.
    """
    defect = await defect_service.get_defect(db, defect_id)
    if not defect:
        raise HTTPException(status_code=404, detail="Defect not found")
    if defect.status != "approved":
        raise HTTPException(status_code=422, detail="Only approved defects can be pushed to Jira")

    # Count existing jira defects for this project
    count_result = await db.execute(
        select(func.count())
        .where(JiraDefect.project_id == defect.project_id)
    )
    jira_count = count_result.scalar_one()

    issue_key = f"BUG-{(jira_count + 1):04d}"
    jira_defect = JiraDefect(
        defect_draft_id=defect.id,
        project_id=defect.project_id,
        created_by=(current_user.id if current_user else 1),
        jira_issue_key=issue_key,
        jira_url=f"https://your-org.atlassian.net/browse/{issue_key}",
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
    current_user: OptionalUser,
):
    """
    Trigger Agent 9 (Defect Analysis) from failed execution results.
    Generates DefectDraft records.
    """
    result = await db.execute(select(Project).where(Project.id == body.project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    failed_results = []

    if body.execution_result_ids:
        for er_id in body.execution_result_ids:
            r = await db.execute(select(ExecutionResult).where(ExecutionResult.id == er_id))
            er = r.scalar_one_or_none()
            if er and er.status == "failed":
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

    agent = DefectAnalysisAgent()
    agent_result = await agent.run(
        failed_results=failed_results,
        project_name=project.name,
    )

    if not agent_result.success:
        raise HTTPException(status_code=500, detail=agent_result.error or "Agent failed")

    count_result = await db.execute(
        select(func.count()).where(DefectDraft.project_id == body.project_id)
    )
    defect_count = count_result.scalar_one()

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
            created_by=(current_user.id if current_user else 1),
            defect_id=f"DEF-{(defect_count + i + 1):04d}",
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
        )
        db.add(draft)
        await db.flush()
        created_ids.append(draft.id)

    await db.commit()

    if not created_ids:
        agent_errors = [
            log["message"] for log in (agent_result.logs or [])
            if log.get("level") == "warning"
        ]
        detail = "; ".join(agent_errors) if agent_errors else "LLM returned 0 parseable defects"
        raise HTTPException(status_code=500, detail=f"Agent generated 0 defects: {detail}")

    return {
        "message": f"Generated {len(created_ids)} defect drafts from {len(failed_results)} failed tests",
        "defect_ids": created_ids,
        "agent_logs": agent_result.logs,
    }
