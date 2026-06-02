"""
Reports endpoints - Phase 7.
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func

from app.api.deps import DBSession, OptionalUser
from app.models.report import Report
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_scenario import TestScenario
from app.models.execution import ExecutionRun, ExecutionResult
from app.models.defect import DefectDraft
from app.schemas.report import ReportOut, AgentReportTrigger
from app.services import report_service
from app.agents.reporting.reporting_agent import TestReportingAgent

router = APIRouter()


@router.get("/project/{project_id}", response_model=list[ReportOut])
async def list_reports(project_id: int, db: DBSession, current_user: OptionalUser):
    return await report_service.list_reports(db, project_id)


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: int, db: DBSession, current_user: OptionalUser):
    report = await report_service.get_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/agent/generate-report")
async def trigger_reporting_agent(body: AgentReportTrigger, db: DBSession, current_user: OptionalUser):
    """Trigger Agent 11 - aggregates all project metrics and generates an AI QA report."""
    r = await db.execute(select(Project).where(Project.id == body.project_id))
    project = r.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Aggregate metrics from all tables
    async def count(model, *filters):
        q = select(func.count()).select_from(model).where(model.project_id == body.project_id)
        if filters:
            q = q.where(*filters)
        res = await db.execute(q)
        return res.scalar_one()

    total_reqs = await count(Requirement)
    approved_reqs = await count(Requirement, Requirement.status == "approved")
    total_tcs = await count(TestCase)
    approved_tcs = await count(TestCase, TestCase.status == "approved")
    auto_candidate_tcs = await count(TestCase, TestCase.automation_candidate == True)
    total_scenarios = await count(TestScenario)
    total_runs = await count(ExecutionRun)

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
    all_runs_res = await db.execute(
        select(ExecutionRun).where(ExecutionRun.project_id == body.project_id)
    )
    all_runs = all_runs_res.scalars().all()
    total_passed = sum(r.passed for r in all_runs)
    total_failed = sum(r.failed for r in all_runs)
    total_skipped = sum(r.skipped for r in all_runs)

    # Defect metrics
    total_defects = await count(DefectDraft)
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

    agent = TestReportingAgent()
    agent_result = await agent.run(
        metrics=metrics,
        project_name=project.name,
        report_type=body.report_type,
    )

    if not agent_result.success:
        raise HTTPException(status_code=500, detail=agent_result.error or "Agent failed")

    rep_data = agent_result.data["report"]
    count_res = await db.execute(select(func.count()).where(Report.project_id == body.project_id))
    rep_count = count_res.scalar_one()

    report = Report(
        project_id=body.project_id,
        created_by=(current_user.id if current_user else 1),
        report_id=f"RPT-{(rep_count + 1):04d}",
        report_type=body.report_type,
        title=rep_data.get("title", f"{body.report_type.capitalize()} Report"),
        summary=rep_data.get("summary"),
        coverage=rep_data.get("coverage", metrics["test_cases"]),
        execution_metrics=rep_data.get("execution_metrics", metrics["execution"]),
        defect_metrics=rep_data.get("defect_metrics", metrics["defects"]),
        risks=rep_data.get("risks", []),
        recommendations=rep_data.get("recommendations", []),
        status="draft",
        metadata_={"raw_metrics": metrics},
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    await db.commit()

    return {
        "message": "Report generated successfully",
        "report_id": report.id,
        "report_ref": report.report_id,
        "title": report.title,
    }
