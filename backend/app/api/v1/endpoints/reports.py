"""
Reports endpoints - Phase 7.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, func

from app.api.deps import CurrentUser, DBSession, require_entity_project_access, require_permission, require_project_access
from app.config import get_settings
from app.models.report import Report
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_scenario import TestScenario
from app.models.execution import ExecutionRun, ExecutionResult
from app.models.defect import DefectDraft
from app.schemas.report import ReportOut, AgentReportTrigger
from app.services import agent_run_service, report_service, traceability_service
from app.services.agent_dispatch_service import enqueue_agent_run
from app.services.automation_baseline_service import capture_and_persist_baseline, capture_and_persist_comparison
from app.services.display_id_service import display_id, temporary_id
from app.services.rbac_service import APPROVE_RELEASE_REPORT
from app.agents.reporting.reporting_agent import TestReportingAgent

router = APIRouter()
settings = get_settings()


def _run_agents_synchronously() -> bool:
    return False


@router.get("/project/{project_id}", response_model=list[ReportOut])
async def list_reports(project_id: int, db: DBSession, current_user: CurrentUser):
    await require_project_access(project_id, current_user, db)
    return await report_service.list_reports(db, project_id)


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: int, db: DBSession, current_user: CurrentUser):
    report = await report_service.get_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    await require_entity_project_access(report, current_user, db)
    return report


@router.post("/automation-baseline/{project_id}", response_model=ReportOut)
async def capture_automation_baseline_report(project_id: int, db: DBSession, current_user: CurrentUser):
    """Capture a point-in-time automation-generation quality snapshot (Phase 0
    foundation hardening) — script generation success rate, execution pass
    rate, and static quality issue counts. Intended to be run once before
    Playwright MCP grounding (Phase 3) lands, and again after, so the
    improvement can be measured against a real baseline rather than asserted.
    """
    await require_permission(APPROVE_RELEASE_REPORT, project_id, current_user, db)
    report = await capture_and_persist_baseline(db, project_id=project_id, user_id=current_user.id)
    await db.commit()
    await db.refresh(report)
    return report


@router.post("/automation-baseline-comparison/{project_id}", response_model=ReportOut)
async def capture_automation_baseline_comparison_report(project_id: int, db: DBSession, current_user: CurrentUser):
    """Phase 4 exit criterion: diff a fresh snapshot against the earliest
    pre-MCP baseline for this project, surfacing the grounded-generation
    metrics (grounded pass rate, avg locator confidence, repair-loop success
    rate, dry-run stability) alongside the original Phase 0 metrics.
    """
    await require_permission(APPROVE_RELEASE_REPORT, project_id, current_user, db)
    try:
        report = await capture_and_persist_comparison(db, project_id=project_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(report)
    return report


@router.post("/agent/generate-report")
async def trigger_reporting_agent(
    body: AgentReportTrigger,
    db: DBSession,
    current_user: CurrentUser,
    include_drafts: bool = Query(False),
):
    """Trigger Agent 11 - aggregates all project metrics and generates an AI QA report."""
    project = await require_permission(APPROVE_RELEASE_REPORT, body.project_id, current_user, db)

    rule14_metrics = await traceability_service.reporting_metrics(db, body.project_id, include_drafts=include_drafts)

    # Aggregate metrics from all tables
    async def count(model, *filters):
        q = select(func.count()).select_from(model).where(model.project_id == body.project_id)
        if filters:
            q = q.where(*filters)
        res = await db.execute(q)
        return res.scalar_one()

    total_reqs = await count(Requirement) if include_drafts else rule14_metrics["requirements"]["total"]
    approved_reqs = await count(Requirement, Requirement.status == "approved")
    total_tcs = await count(TestCase) if include_drafts else rule14_metrics["test_cases"]["total"]
    approved_tcs = await count(TestCase, TestCase.status == "approved")
    auto_candidate_tcs = await count(TestCase, TestCase.automation_candidate == True)
    total_scenarios = await count(TestScenario)
    total_runs = await count(ExecutionRun) if include_drafts else rule14_metrics["execution"]["total_runs"]

    # Latest run stats
    latest_run_res = await db.execute(
        select(ExecutionRun)
        .where(ExecutionRun.project_id == body.project_id, ExecutionRun.status == "completed")
        .order_by(ExecutionRun.created_at.desc())
        .limit(1)
    )
    latest_run = latest_run_res.scalar_one_or_none()
    latest_pass_pct = 0.0
    if latest_run and latest_run.total_tests > 0:
        latest_pass_pct = round(latest_run.passed / latest_run.total_tests * 100, 1)

    # Aggregate all execution results
    run_stmt = select(ExecutionRun).where(ExecutionRun.project_id == body.project_id)
    if not include_drafts:
        run_stmt = run_stmt.where(ExecutionRun.status == "approved")
    all_runs_res = await db.execute(run_stmt)
    all_runs = all_runs_res.scalars().all()
    total_passed = sum(r.passed for r in all_runs)
    total_failed = sum(r.failed for r in all_runs)
    total_skipped = sum(r.skipped for r in all_runs)

    # Defect metrics
    total_defects = await count(DefectDraft) if include_drafts else rule14_metrics["defects"]["total"]
    critical_defects = await count(DefectDraft, DefectDraft.severity == "Critical")
    high_defects = await count(DefectDraft, DefectDraft.severity == "High")
    medium_defects = await count(DefectDraft, DefectDraft.severity == "Medium")
    low_defects = await count(DefectDraft, DefectDraft.severity == "Low")
    open_defects = await count(DefectDraft, DefectDraft.status.in_(["draft", "pending_approval", "approved"]))
    jira_pushed = await count(DefectDraft, DefectDraft.status == "pushed_to_jira")
    product_defects = await count(DefectDraft, DefectDraft.classification == "product_defect")

    metrics = {
        "requirements": {
            "total": total_reqs,
            "approved": approved_reqs,
            "coverage_pct": round(approved_reqs / total_reqs * 100, 1) if total_reqs > 0 else 0,
        },
        "test_cases": {
            "total": total_tcs,
            "approved": approved_tcs,
            "automation_candidates": auto_candidate_tcs,
            "automation_coverage_pct": round(auto_candidate_tcs / total_tcs * 100, 1) if total_tcs > 0 else 0,
        },
        "scenarios": {"total": total_scenarios},
        "execution": {
            "total_runs": total_runs,
            "latest_pass_pct": latest_pass_pct,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "total_skipped": total_skipped,
        },
        "defects": {
            "total": total_defects,
            "critical": critical_defects,
            "high": high_defects,
            "medium": medium_defects,
            "low": low_defects,
            "open": open_defects,
            "pushed_to_jira": jira_pushed,
            "product_defect_pct": round(product_defects / total_defects * 100, 1) if total_defects > 0 else 0,
        },
    }

    if not _run_agents_synchronously():
        agent_run, task_id = await enqueue_agent_run(
            db,
            project_id=body.project_id,
            user_id=current_user.id,
            agent_name="test_reporting",
            input_data={
                "metrics": metrics,
                "project_name": project.name,
                "report_type": body.report_type,
            },
            metadata={"metrics": metrics},
        )
        return JSONResponse(
            status_code=202,
            content={"message": "Report generation queued", "agent_run_id": agent_run.id, "task_id": task_id},
        )

    user_id = current_user.id
    agent_run = await agent_run_service.start_agent_run(
        db,
        project_id=body.project_id,
        user_id=user_id,
        agent_name="test_reporting",
        input_data=body.model_dump(mode="json"),
        metadata={"metrics": metrics},
    )

    agent = TestReportingAgent()
    agent_result = await agent.run(
        metrics=metrics,
        project_name=project.name,
        report_type=body.report_type,
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

    rep_data = agent_result.data["report"]
    report = Report(
        project_id=body.project_id,
        created_by=user_id,
        report_id=temporary_id("RPT"),
        report_type=body.report_type,
        title=rep_data.get("title", f"{body.report_type.capitalize()} Report"),
        summary=rep_data.get("summary"),
        coverage=rep_data.get("coverage", metrics["test_cases"]),
        execution_metrics=rep_data.get("execution_metrics", metrics["execution"]),
        defect_metrics=rep_data.get("defect_metrics", metrics["defects"]),
        risks=rep_data.get("risks", []),
        recommendations=rep_data.get("recommendations", []),
        status="draft",
        agent_run_id=agent_run.id,
        metadata_={"raw_metrics": metrics},
    )
    db.add(report)
    await db.flush()
    report.report_id = display_id("RPT", report.id)
    await db.flush()
    await db.refresh(report)
    await traceability_service.create_lineage(
        db,
        project_id=body.project_id,
        parent_type="project",
        parent_id=body.project_id,
        child_type="report",
        child_id=report.id,
        agent_run_id=agent_run.id,
        metadata={"include_drafts": include_drafts},
    )
    await agent_run_service.complete_agent_run(
        db,
        agent_run,
        agent_result=agent_result,
        output_data={"report_id": report.id, "report_ref": report.report_id},
    )
    await db.commit()

    return {
        "message": "Report generated successfully",
        "report_id": report.id,
        "report_ref": report.report_id,
        "title": report.title,
        "agent_run_id": agent_run.id,
    }
