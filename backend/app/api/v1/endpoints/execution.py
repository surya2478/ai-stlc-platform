"""
Test Execution endpoints — Phase 5.
"""
import os

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from datetime import datetime, timezone

from app.api.deps import CurrentUser, DBSession, require_entity_project_access, require_permission, require_project_access
from app.config import get_settings
from app.models.execution import ExecutionRun, ExecutionResult
from app.models.test_case import TestCase
from app.models.project import Project
from app.schemas.execution import (
    AgentExecutionTrigger,
    AiAssistResponse,
    AiRunDetail,
    AiRunGovernance,
    AiRunReviewDecision,
    AiRunStart,
    ExecutionDashboardResponse,
    ExecutionResultOut,
    ExecutionResultUATUpdate,
    ExecutionRunOut,
    ManualResultDetail,
    ManualRunDetail,
    ManualRunStart,
    ManualStepResultOut,
    ManualStepUpdate,
)
from app.services import (
    agent_run_service,
    ai_assist_service,
    ai_execution_service,
    ai_run_detection,
    execution_dashboard_service,
    execution_service,
    manual_execution_service,
    traceability_service,
)
from app.core import audit_logger
from app.services.agent_dispatch_service import enqueue_agent_run
from app.services.display_id_service import display_id, temporary_id
from app.services.project_llm_settings_service import project_llm_role_context
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


# ── Dashboard ─────────────────────────────────────────────────────────────────


@router.get("/dashboard", response_model=ExecutionDashboardResponse)
async def execution_dashboard(
    db: DBSession,
    current_user: CurrentUser,
    project_id: int = Query(..., description="Project to aggregate"),
    environment: str | None = Query(None, description="Filter by environment (SIT, UAT, PROD, …)"),
    execution_type: str | None = Query(None, description="manual | automation | ai"),
    date_from: str | None = Query(None, description="ISO date (inclusive)"),
    date_to: str | None = Query(None, description="ISO date (inclusive)"),
):
    """Unified Execution Dashboard payload across Manual, Automation, and AI."""
    await require_project_access(project_id, current_user, db)

    df = datetime.fromisoformat(date_from) if date_from else None
    dt = datetime.fromisoformat(date_to) if date_to else None

    return await execution_dashboard_service.dashboard_payload(
        db,
        project_id=project_id,
        environment=environment,
        execution_type=execution_type,
        date_from=df,
        date_to=dt,
    )


# ── AI Execution lifecycle ────────────────────────────────────────────────────


@router.get("/ai/governance", response_model=AiRunGovernance)
async def ai_governance_snapshot(
    db: DBSession,
    current_user: CurrentUser,
):
    """Return the current AI governance config (thresholds, env allow-list, evidence policy)."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return ai_execution_service.governance_snapshot()


@router.post("/ai/runs", response_model=ExecutionRunOut, status_code=202)
async def start_ai_run(
    body: AiRunStart,
    db: DBSession,
    current_user: CurrentUser,
):
    """Start an AI execution run.

    Creates an ExecutionRun (execution_type='ai', status='queued') and enqueues
    the Test Execution agent. When the agent finishes, the worker applies the
    AI completion rule (`ai_execution_service.finalize_ai_run`) which sets the
    run to either `auto_completed` or `review_required`.
    """
    project = await require_permission(EXECUTE_TESTS, body.project_id, current_user, db)

    test_cases: list[dict] = []
    skipped_wrong_project: list[int] = []
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
        raise HTTPException(status_code=422, detail="No valid AI-eligible test cases found")

    suite_name = body.suite_name or f"{project.name} — AI-Assisted Run"
    # Phase 3: AI is a mode of automation, not its own execution_type. The row
    # stores execution_type='automation' + metadata.ai_assisted=true; anything
    # else keeps its shape so existing dashboards keep working.
    metadata = {
        "ai_assisted": True,
        "agent_name": body.agent_name,
        "model": body.model,
        "mode": body.mode,
    }
    if body.confidence_threshold is not None:
        metadata["confidence_threshold_override"] = body.confidence_threshold

    # Create an ExecutionRun placeholder so the UI can show "queued" immediately
    # even before the worker materializes the agent results.
    run = ExecutionRun(
        project_id=body.project_id,
        created_by=current_user.id,
        triggered_by=current_user.id,
        execution_id=temporary_id("AI"),
        suite_name=suite_name,
        environment=body.environment,
        execution_type="automation",
        source_type="ai",
        status="queued",
        total_tests=len(test_cases),
        passed=0, failed=0, skipped=0,
        started_at=datetime.now(timezone.utc),
        metadata_=metadata,
    )
    db.add(run)
    await db.flush()
    run.execution_id = display_id("AI", run.id)
    await db.flush()

    audit_logger.execution_run_started(
        by_user_id=current_user.id,
        run_id=run.id,
        project_id=body.project_id,
        execution_type="automation",
        environment=body.environment,
        test_case_count=len(test_cases),
    )

    agent_run, _task_id = await enqueue_agent_run(
        db,
        project_id=body.project_id,
        user_id=current_user.id,
        agent_name="test_execution",
        input_data={
            "test_cases": test_cases,
            "environment": body.environment,
            "suite_name": suite_name,
            "source_type": "ai",
            "ai_run": True,
            "agent_name": body.agent_name,
            "model": body.model,
            "mode": body.mode,
            "placeholder_run_id": run.id,
        },
        metadata={"test_case_ids": [tc["id"] for tc in test_cases], "ai_run": True},
    )
    run.agent_run_id = agent_run.id
    await db.commit()
    await db.refresh(run)
    return run


@router.get("/ai/runs/{run_id}", response_model=AiRunDetail)
async def get_ai_run(
    run_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """Detail view for an AI run — includes per-result rows, governance snapshot,
    and the human-review audit trail stored on `metadata_.review_log`."""
    run = await execution_service.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    if not ai_run_detection.is_ai_assisted_run(run):
        raise HTTPException(status_code=409, detail="Run is not an AI execution run")
    await require_entity_project_access(run, current_user, db)
    results = await execution_service.list_results(db, run_id)
    review_log = list((run.metadata_ or {}).get("review_log") or [])
    return AiRunDetail(
        run=run,
        results=results,
        governance=ai_execution_service.governance_snapshot(),
        review_log=review_log,
    )


@router.post("/ai/runs/{run_id}/review", response_model=ExecutionRunOut)
async def submit_ai_run_review(
    run_id: int,
    body: AiRunReviewDecision,
    db: DBSession,
    current_user: CurrentUser,
):
    """Apply a human reviewer's decision to an AI run.

    Only runs in `review_required` state are reviewable. Every decision creates
    an audit event with actor, reason, previous state, and new state.
    """
    run = await execution_service.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    if not ai_run_detection.is_ai_assisted_run(run):
        raise HTTPException(status_code=409, detail="Run is not an AI execution run")
    if run.status not in ("review_required",):
        raise HTTPException(
            status_code=409,
            detail=f"Run is in status '{run.status}' — only 'review_required' runs can be reviewed",
        )
    await require_permission(EXECUTE_TESTS, run.project_id, current_user, db)
    try:
        await ai_execution_service.submit_review_decision(
            db,
            run=run,
            user_id=current_user.id,
            decision=body.decision,
            reason=body.reason,
            override_status=body.override_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/ai/runs/{run_id}/finalize", response_model=ExecutionRunOut)
async def finalize_ai_run_now(
    run_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """Re-evaluate the AI completion rule for a run.

    Useful when (a) governance settings change and a run should be re-decided,
    (b) the worker callback was lost, or (c) an admin wants to retry the rule
    after evidence is added. No-op when the run is already terminal.
    """
    run = await execution_service.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    if not ai_run_detection.is_ai_assisted_run(run):
        raise HTTPException(status_code=409, detail="Run is not an AI execution run")
    await require_permission(EXECUTE_TESTS, run.project_id, current_user, db)
    await ai_execution_service.finalize_ai_run(db, run=run)
    await db.commit()
    await db.refresh(run)
    return run


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
        source_type=body.source_type,
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
    # Phase 3 convention (see /ai/run above): 'ai' is a mode of automation, not
    # its own execution_type — ck_execution_runs_execution_type only allows
    # manual | automation | hybrid.
    run_metadata = {"source_type": body.source_type}
    if body.source_type == "ai":
        run_metadata["ai_assisted"] = True
    run = ExecutionRun(
        project_id=body.project_id,
        created_by=user_id,
        execution_id=temporary_id("ER"),
        suite_name=body.suite_name or f"{project.name} — Test Suite",
        environment=body.environment,
        status="completed",
        execution_type="automation" if body.source_type == "ai" else body.source_type,
        source_type=body.source_type,
        metadata_=run_metadata,
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
    now = datetime.now(timezone.utc)
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
            metadata_=r_data.get("metadata") if isinstance(r_data.get("metadata"), dict) else None,
        )
        db.add(exec_result)
        await db.flush()
        if db_tc_id is not None:
            tc = await db.get(TestCase, db_tc_id)
            if tc:
                tc.last_execution_run_id = run.id
                tc.last_automation_status = exec_result.status
                tc.last_automation_run_at = now
                tc.latest_evidence_available = bool(exec_result.logs or exec_result.error_message or exec_result.stack_trace)
                tc.last_status_updated_by = user_id
                tc.last_status_updated_at = now
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


# ── Manual Execution ──────────────────────────────────────────────────────────


def _build_manual_run_detail(run: ExecutionRun) -> ManualRunDetail:
    result_details: list[ManualResultDetail] = []
    for result in run.results:
        steps = [
            ManualStepResultOut.model_validate(manual_execution_service.serialize_step(step))
            for step in sorted(result.manual_steps, key=lambda s: s.step_number)
        ]
        result_details.append(
            ManualResultDetail(
                result=ExecutionResultOut.model_validate(result),
                steps=steps,
            )
        )
    return ManualRunDetail(
        run=ExecutionRunOut.model_validate(run),
        results=result_details,
    )


@router.post("/manual/runs", response_model=ManualRunDetail, status_code=201)
async def start_manual_execution_run(
    body: ManualRunStart,
    db: DBSession,
    current_user: CurrentUser,
):
    """Start a new manual execution run with one ExecutionResult per test case
    and a ManualStepResult per structured step.
    """
    project = await require_permission(EXECUTE_TESTS, body.project_id, current_user, db)
    run = await manual_execution_service.start_manual_run(
        db,
        project_id=body.project_id,
        user_id=current_user.id,
        test_case_ids=body.test_case_ids,
        environment=body.environment,
        suite_name=body.suite_name or f"{project.name} — Manual Run",
        bound_data_records=body.bound_data_records,
    )
    await db.commit()
    fresh = await manual_execution_service.load_manual_run(db, run.id)
    if not fresh:
        raise HTTPException(status_code=500, detail="Run was created but could not be loaded")
    return _build_manual_run_detail(fresh)


@router.get("/manual/runs/{run_id}/details", response_model=ManualRunDetail)
async def get_manual_run_details(
    run_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    run = await manual_execution_service.load_manual_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    await require_entity_project_access(run, current_user, db)
    return _build_manual_run_detail(run)


@router.patch("/manual/steps/{step_id}", response_model=ManualStepResultOut)
async def update_manual_step(
    step_id: int,
    body: ManualStepUpdate,
    db: DBSession,
    current_user: CurrentUser,
):
    bundle = await manual_execution_service.get_step_with_run(db, step_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Manual step not found")
    step, _result, run = bundle
    await require_permission(EXECUTE_TESTS, run.project_id, current_user, db)
    updated = await manual_execution_service.update_step(
        db,
        step,
        user_id=current_user.id,
        status_value=body.status,
        actual_result=body.actual_result,
        comments=body.comments,
    )
    await db.commit()
    await db.refresh(updated)
    return ManualStepResultOut.model_validate(manual_execution_service.serialize_step(updated))


@router.patch("/manual/results/{result_id}/uat", response_model=ExecutionResultOut)
async def update_manual_result_uat_fields(
    result_id: int,
    body: ExecutionResultUATUpdate,
    db: DBSession,
    current_user: CurrentUser,
):
    """UAT template tracking fields for a single ExecutionResult: Overall
    Status outcome (incl. 'Passed with Snag'), Tested By, SIT status, and
    Blocking Snag ID / Other Reason. Distinct from the step-level roll-up."""
    bundle = await manual_execution_service.get_result_with_run(db, result_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Execution result not found")
    result, run = bundle
    await require_permission(EXECUTE_TESTS, run.project_id, current_user, db)
    updated = await manual_execution_service.update_result_uat_fields(
        db,
        result,
        user_id=current_user.id,
        status=body.status,
        tested_by_id=body.tested_by_id,
        sit_status=body.sit_status,
        blocking_defect_id=body.blocking_defect_id,
        other_reason=body.other_reason,
    )
    await db.commit()
    await db.refresh(updated, attribute_names=["tested_by", "blocking_defect"])
    return ExecutionResultOut.model_validate(updated)


@router.post("/manual/steps/{step_id}/evidence", response_model=ManualStepResultOut, status_code=201)
async def upload_manual_evidence(
    step_id: int,
    db: DBSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
):
    bundle = await manual_execution_service.get_step_with_run(db, step_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Manual step not found")
    step, _result, run = bundle
    await require_permission(EXECUTE_TESTS, run.project_id, current_user, db)
    await manual_execution_service.attach_evidence(
        db, step=step, run=run, user_id=current_user.id, file=file
    )
    await db.commit()
    await db.refresh(step)
    return ManualStepResultOut.model_validate(manual_execution_service.serialize_step(step))


@router.get("/manual/evidence/{evidence_id}")
async def download_manual_evidence(
    evidence_id: str,
    db: DBSession,
    current_user: CurrentUser,
):
    found = await manual_execution_service.find_evidence(db, evidence_id)
    if not found:
        raise HTTPException(status_code=404, detail="Evidence not found")
    step, descriptor = found
    bundle = await manual_execution_service.get_step_with_run(db, step.id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Evidence parent run not found")
    _step, _result, run = bundle
    await require_permission(EXECUTE_TESTS, run.project_id, current_user, db)
    file_path = descriptor.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=410, detail="Evidence file is no longer available")

    # Defence in depth: only serve files under the configured storage path.
    # The path is server-generated today (manual_execution_service writes
    # storage_dir / stored_name), so this is not exploitable as it stands —
    # but the automation artifact endpoint already guards the same way, and an
    # unguarded FileResponse over a database-supplied path is one bad write
    # away from being an arbitrary-file-read primitive.
    storage_root = os.path.realpath(settings.file_storage_path)
    real_path = os.path.realpath(file_path)
    if not real_path.startswith(storage_root + os.sep) and real_path != storage_root:
        raise HTTPException(status_code=403, detail="Evidence path is outside the storage root")

    return FileResponse(
        real_path,
        media_type=descriptor.get("content_type") or "application/octet-stream",
        filename=descriptor.get("filename") or "evidence",
    )


@router.delete("/manual/evidence/{evidence_id}", response_model=ManualStepResultOut)
async def delete_manual_evidence(
    evidence_id: str,
    db: DBSession,
    current_user: CurrentUser,
):
    found = await manual_execution_service.find_evidence(db, evidence_id)
    if not found:
        raise HTTPException(status_code=404, detail="Evidence not found")
    step, _descriptor = found
    bundle = await manual_execution_service.get_step_with_run(db, step.id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Evidence parent run not found")
    _step, _result, run = bundle
    await require_permission(EXECUTE_TESTS, run.project_id, current_user, db)
    removed = await manual_execution_service.detach_evidence(db, step, evidence_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Evidence not found on step")
    await db.commit()
    await db.refresh(step)
    return ManualStepResultOut.model_validate(manual_execution_service.serialize_step(step))


@router.post("/manual/runs/{run_id}/complete", response_model=ManualRunDetail)
async def complete_manual_run(
    run_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    run = await manual_execution_service.load_manual_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")
    await require_permission(EXECUTE_TESTS, run.project_id, current_user, db)
    if run.status == "completed":
        # Idempotent: just return current state
        return _build_manual_run_detail(run)
    completed = await manual_execution_service.complete_run(db, run, user_id=current_user.id)
    await db.commit()
    fresh = await manual_execution_service.load_manual_run(db, completed.id)
    if not fresh:
        raise HTTPException(status_code=500, detail="Run completed but could not be reloaded")
    return _build_manual_run_detail(fresh)


@router.post("/manual/steps/{step_id}/ai-assist", response_model=AiAssistResponse)
async def ai_assist_manual_step(
    step_id: int,
    db: DBSession,
    current_user: CurrentUser,
    actual_result: str | None = Form(None),
    comments: str | None = Form(None),
    file: UploadFile | None = File(None),
):
    """Ask the configured LLM for a pass/fail/blocked suggestion on a step.

    Form fields are optional — when present, they override what's currently on
    the step (so the tester can ask "if I write this as actual_result, does it
    look like a pass?" without saving first).

    A `file` (screenshot) is also optional. If supplied AND vision is configured,
    a vision model is used; otherwise we fall back to text-only with no error.
    Screenshots are capped at max_upload_size_mb to keep the worker from OOMing
    on an accidental huge upload.

    The suggestion is persisted on the step's metadata for audit; the tester
    must explicitly apply it to change the step's status.
    """
    bundle = await manual_execution_service.get_step_with_run(db, step_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Manual step not found")
    step, _result, run = bundle
    await require_permission(EXECUTE_TESTS, run.project_id, current_user, db)

    screenshot_bytes: bytes | None = None
    if file is not None:
        # Read with an explicit cap. UploadFile.read(N) returns at most N bytes;
        # if more remained on the wire, the user gets a clean 413 instead of
        # the worker silently chewing through a 200MB allocation.
        cap = settings.max_upload_size_mb * 1024 * 1024
        screenshot_bytes = await file.read(cap + 1)
        if screenshot_bytes and len(screenshot_bytes) > cap:
            raise HTTPException(
                status_code=413,
                detail=f"Screenshot exceeds the {settings.max_upload_size_mb} MB limit.",
            )
        if not screenshot_bytes:
            screenshot_bytes = None

    try:
        async with project_llm_role_context(db, run.project_id):
            suggestion = await ai_assist_service.suggest_step_outcome(
                step,
                actual_result_override=actual_result,
                comments_override=comments,
                screenshot_bytes=screenshot_bytes,
            )
    except ai_assist_service.AiAssistUnavailable as exc:
        # Don't 500 the user when the LLM is down — return a graceful
        # "blocked + decide manually" response so the UI can surface a
        # friendly message and the tester can keep moving.
        return AiAssistResponse(
            suggested_status="blocked",
            confidence=0,
            reasoning=str(exc),
            observations=[],
            inputs_used={"mode": "text_only", "vision_blocker": None, "llm_unavailable": True},
            raw_response=None,
        )

    # Persist the suggestion on the step's metadata (append-only audit list).
    existing_meta = dict(step.metadata_ or {})
    history = list(existing_meta.get("ai_assist_history") or [])
    history.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "by_user_id": current_user.id,
        "suggested_status": suggestion["suggested_status"],
        "confidence": suggestion["confidence"],
        "reasoning": suggestion["reasoning"],
        "observations": suggestion.get("observations") or [],
        "inputs_used": suggestion.get("inputs_used") or {},
    })
    # Cap history at the last 10 entries — keep audit useful without bloat
    existing_meta["ai_assist_history"] = history[-10:]
    step.metadata_ = existing_meta
    await db.commit()

    return AiAssistResponse(
        suggested_status=suggestion["suggested_status"],
        confidence=suggestion["confidence"],
        reasoning=suggestion["reasoning"],
        observations=suggestion.get("observations") or [],
        inputs_used=suggestion.get("inputs_used") or {},
        raw_response=suggestion.get("raw_response"),
    )
