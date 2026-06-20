"""
Test Execution endpoints — Phase 5.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, require_entity_project_access, require_permission, require_project_access
from app.config import get_settings
from app.models.execution import ExecutionRun, ExecutionResult
from app.models.test_case import TestCase
from app.models.project import Project
from app.schemas.execution import ExecutionRunOut, ExecutionResultOut, AgentExecutionTrigger
from app.services import agent_run_service, execution_service, traceability_service
from app.services.agent_dispatch_service import enqueue_agent_run
from app.services.display_id_service import display_id, temporary_id
from app.services.rbac_service import EXECUTE_TESTS
from app.agents.execution.execution_agent import TestExecutionAgent

router = APIRouter()
settings = get_settings()


def _run_agents_synchronously() -> bool:
    return False


def _to_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        import json
        return json.dumps(value)
    return str(value)


def _to_log_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/project/{project_id}", response_model=list[ExecutionRunOut])
async def list_execution_runs(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    status: str | None = Query(None),
):
    await require_project_access(project_id, current_user, db)
    return await execution_service.list_runs(db, project_id, status)


@router.get("/{run_id}", response_model=ExecutionRunOut)
async def get_execution_run(
    run_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    run = await execution_service.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    await require_entity_project_access(run, current_user, db)
    return run


@router.get("/{run_id}/results", response_model=list[ExecutionResultOut])
async def get_execution_results(
    run_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    run = await execution_service.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    await require_entity_project_access(run, current_user, db)
    return await execution_service.list_results(db, run_id)


# ── Agent ─────────────────────────────────────────────────────────────────────

@router.post("/agent/run-tests")
async def trigger_execution_agent(
    body: AgentExecutionTrigger,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Trigger Agent 8 (Test Execution) to execute a set of test cases.
    Creates an ExecutionRun with individual ExecutionResult records.
    """
    project = await require_permission(EXECUTE_TESTS, body.project_id, current_user, db)

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

    if not _run_agents_synchronously():
        agent_run, task_id = await enqueue_agent_run(
            db,
            project_id=body.project_id,
            user_id=current_user.id,
            agent_name="test_execution",
            input_data={
                "test_cases": test_cases,
                "environment": body.environment,
                "suite_name": body.suite_name or f"{project.name} — Test Suite",
                "source_type": body.source_type,
            },
            metadata={"test_case_ids": [tc["id"] for tc in test_cases]},
        )
        return JSONResponse(
            status_code=202,
            content={"message": "Test execution queued", "agent_run_id": agent_run.id, "task_id": task_id},
        )

    user_id = current_user.id
    agent_run = await agent_run_service.start_agent_run(
        db,
        project_id=body.project_id,
        user_id=user_id,
        agent_name="test_execution",
        input_data=body.model_dump(mode="json"),
        metadata={"test_case_ids": [tc["id"] for tc in test_cases]},
    )

    agent = TestExecutionAgent()
    agent_result = await agent.run(
        test_cases=test_cases,
        environment=body.environment,
        suite_name=body.suite_name or f"{project.name} — Test Suite",
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

    summary = agent_result.data.get("summary", {})
    results = agent_result.data.get("results", [])

    # Create ExecutionRun
    run = ExecutionRun(
        project_id=body.project_id,
        created_by=user_id,
        execution_id=temporary_id("ER"),
        suite_name=body.suite_name or f"{project.name} — Test Suite",
        environment=body.environment,
        status="completed",
        source_type=body.source_type,
        total_tests=summary.get("total", len(results)),
        passed=summary.get("passed", 0),
        failed=summary.get("failed", 0),
        skipped=summary.get("skipped", 0),
        execution_logs=agent_result.logs,
        agent_run_id=agent_run.id,
    )
    db.add(run)
    await db.flush()
    run.execution_id = display_id("ER", run.id)
    await db.flush()
    await traceability_service.create_lineage_many(
        db,
        project_id=body.project_id,
        parents=[("test_case", tc["id"]) for tc in test_cases],
        child_type="execution_run",
        child_id=run.id,
        agent_run_id=agent_run.id,
    )

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
            error_message=_to_text(r_data.get("error_message")),
            stack_trace=_to_text(r_data.get("stack_trace")),
            logs=_to_log_list(r_data.get("logs")),
        )
        db.add(exec_result)
        await db.flush()
        parents = [("execution_run", run.id)]
        if db_tc_id is not None:
            parents.append(("test_case", db_tc_id))
        await traceability_service.create_lineage_many(
            db,
            project_id=body.project_id,
            parents=parents,
            child_type="execution_result",
            child_id=exec_result.id,
            agent_run_id=agent_run.id,
        )
        result_ids.append(exec_result.id)

    run.total_tests = len(results)
    run.passed = sum(1 for r in results if r.get("status") == "passed")
    run.failed = sum(1 for r in results if r.get("status") == "failed")
    run.skipped = sum(1 for r in results if r.get("status") == "skipped")
    run.status = "completed"
    await db.flush()

    await agent_run_service.complete_agent_run(
        db,
        agent_run,
        agent_result=agent_result,
        output_data={"run_id": run.id, "result_ids": result_ids, "summary": summary},
    )
    await db.commit()
    return {
        "message": f"Execution completed. {run.passed} passed, {run.failed} failed, {run.skipped} skipped.",
        "run_id": run.id,
        "result_ids": result_ids,
        "agent_logs": agent_result.logs,
        "agent_run_id": agent_run.id,
    }
