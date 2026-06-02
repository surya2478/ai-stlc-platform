"""
Test Execution endpoints — Phase 5.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func

from app.api.deps import DBSession, OptionalUser
from app.models.execution import ExecutionRun, ExecutionResult
from app.models.test_case import TestCase
from app.models.project import Project
from app.schemas.execution import ExecutionRunOut, ExecutionResultOut, AgentExecutionTrigger
from app.services import execution_service
from app.agents.execution.execution_agent import TestExecutionAgent

router = APIRouter()


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/project/{project_id}", response_model=list[ExecutionRunOut])
async def list_execution_runs(
    project_id: int,
    db: DBSession,
    current_user: OptionalUser,
    status: str | None = Query(None),
):
    return await execution_service.list_runs(db, project_id, status)


@router.get("/{run_id}", response_model=ExecutionRunOut)
async def get_execution_run(
    run_id: int,
    db: DBSession,
    current_user: OptionalUser,
):
    run = await execution_service.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    return run


@router.get("/{run_id}/results", response_model=list[ExecutionResultOut])
async def get_execution_results(
    run_id: int,
    db: DBSession,
    current_user: OptionalUser,
):
    run = await execution_service.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    return await execution_service.list_results(db, run_id)


# ── Agent ─────────────────────────────────────────────────────────────────────

@router.post("/agent/run-tests")
async def trigger_execution_agent(
    body: AgentExecutionTrigger,
    db: DBSession,
    current_user: OptionalUser,
):
    """
    Trigger Agent 8 (Test Execution) to execute a set of test cases.
    Creates an ExecutionRun with individual ExecutionResult records.
    """
    result = await db.execute(select(Project).where(Project.id == body.project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    test_cases = []
    skipped_wrong_project = []
    if body.test_case_ids:
        for tc_id in body.test_case_ids:
            r = await db.execute(select(TestCase).where(TestCase.id == tc_id))
            tc = r.scalar_one_or_none()
            if not tc:
                continue
            if tc.project_id != body.project_id:
                skipped_wrong_project.append(tc_id)
                continue
            test_cases.append({
                    "id": tc.id,
                    "test_case_id": tc.test_case_id,
                    "title": tc.title,
                    "steps": tc.steps,
                    "test_type": tc.test_type,
                    "priority": tc.priority,
                })

    if skipped_wrong_project:
        raise HTTPException(
            status_code=403,
            detail=f"Test case ID(s) {skipped_wrong_project} do not belong to project {body.project_id}",
        )
    if not test_cases:
        raise HTTPException(status_code=422, detail="No valid test cases found for execution")

    agent = TestExecutionAgent()
    agent_result = await agent.run(
        test_cases=test_cases,
        environment=body.environment,
        suite_name=body.suite_name or f"{project.name} — Test Suite",
    )

    if not agent_result.success:
        raise HTTPException(status_code=500, detail=agent_result.error or "Agent failed")

    summary = agent_result.data.get("summary", {})
    results = agent_result.data.get("results", [])

    # Count existing runs
    count_result = await db.execute(
        select(func.count()).where(ExecutionRun.project_id == body.project_id)
    )
    run_count = count_result.scalar_one()

    # Create ExecutionRun
    run = ExecutionRun(
        project_id=body.project_id,
        created_by=(current_user.id if current_user else 1),
        execution_id=f"ER-{(run_count + 1):04d}",
        suite_name=body.suite_name or f"{project.name} — Test Suite",
        environment=body.environment,
        status="completed",
        total_tests=summary.get("total", len(results)),
        passed=summary.get("passed", 0),
        failed=summary.get("failed", 0),
        skipped=summary.get("skipped", 0),
        execution_logs=agent_result.logs,
    )
    db.add(run)
    await db.flush()

    # Map test_case_id string → DB id
    tc_map = {tc["test_case_id"]: tc["id"] for tc in test_cases}

    result_ids = []
    for r_data in results:
        tc_id_str = r_data.get("test_case_id")
        db_tc_id = tc_map.get(tc_id_str)

        exec_result = ExecutionResult(
            execution_run_id=run.id,
            test_case_id=db_tc_id,
            project_id=body.project_id,
            test_name=r_data.get("test_name", "Unknown"),
            status=r_data.get("status", "passed"),
            duration_ms=r_data.get("duration_ms"),
            error_message=r_data.get("error_message"),
            stack_trace=r_data.get("stack_trace"),
            logs=r_data.get("logs", []),
        )
        db.add(exec_result)
        await db.flush()
        result_ids.append(exec_result.id)

    run.total_tests = len(results)
    run.passed = sum(1 for r in results if r.get("status") == "passed")
    run.failed = sum(1 for r in results if r.get("status") == "failed")
    run.skipped = sum(1 for r in results if r.get("status") == "skipped")
    run.status = "completed"
    await db.flush()

    await db.commit()
    return {
        "message": f"Execution completed. {run.passed} passed, {run.failed} failed, {run.skipped} skipped.",
        "run_id": run.id,
        "result_ids": result_ids,
        "agent_logs": agent_result.logs,
    }
