import logging
from sqlalchemy import select, func, distinct, or_
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.requirement import Requirement
from app.models.test_plan import TestPlan
from app.models.test_case import TestCase
from app.models.test_data import TestData
from app.models.execution import ExecutionRun, ExecutionResult
from app.models.defect import DefectDraft, JiraDefect
from app.models.report import Report
from app.models.user import User
from app.models.agent import AgentRun

from app.schemas.metrics import (
    DashboardMetricsOut,
    RequirementMetrics,
    TestPlanMetrics,
    TestCaseMetrics,
    TestDataMetrics,
    ExecutionMetrics,
    DefectMetrics,
    ReportMetrics,
    ReleaseReadinessMetrics,
    JiraSyncMetrics,
    DomainQualityMetrics,
    PipelineStepMetrics,
    DefectChartItem,
    ExecutionTrendItem,
    PendingApprovalItem,
    RecentActivityItem,
)

logger = logging.getLogger(__name__)


class MetricsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard_metrics(
        self, project_id: int, release_version: str | None = None
    ) -> DashboardMetricsOut:
        logger.info(
            "Calculating dashboard metrics for project_id=%s, release_version=%s",
            project_id,
            release_version,
        )

        # 1. Requirements Metrics
        req_total_stmt = select(func.count(Requirement.id)).where(
            Requirement.project_id == project_id,
            Requirement.is_deleted == False,
        )
        if release_version:
            req_total_stmt = req_total_stmt.where(
                Requirement.release_version == release_version
            )
        total_reqs = (await self.db.execute(req_total_stmt)).scalar() or 0

        req_approved_stmt = select(func.count(Requirement.id)).where(
            Requirement.project_id == project_id,
            Requirement.is_deleted == False,
            Requirement.status == "approved",
        )
        if release_version:
            req_approved_stmt = req_approved_stmt.where(
                Requirement.release_version == release_version
            )
        approved_reqs = (await self.db.execute(req_approved_stmt)).scalar() or 0

        req_rejected_stmt = select(func.count(Requirement.id)).where(
            Requirement.project_id == project_id,
            Requirement.is_deleted == False,
            Requirement.status == "rejected",
        )
        if release_version:
            req_rejected_stmt = req_rejected_stmt.where(
                Requirement.release_version == release_version
            )
        rejected_reqs = (await self.db.execute(req_rejected_stmt)).scalar() or 0

        # Rejected requirements are a terminal outcome, not work awaiting approval.
        pending_reqs = max(0, total_reqs - approved_reqs - rejected_reqs)
        req_completion = (
            round((approved_reqs / total_reqs) * 100, 1) if total_reqs > 0 else 0.0
        )

        req_metrics = RequirementMetrics(
            total=total_reqs,
            approved=approved_reqs,
            pending=pending_reqs,
            rejected=rejected_reqs,
            completionPercentage=req_completion,
        )

        # 2. Test Planning Metrics
        total_plans = (
            await self.db.scalar(
                select(func.count(TestPlan.id)).where(TestPlan.project_id == project_id)
            )
        ) or 0
        approved_plans = (
            await self.db.scalar(
                select(func.count(TestPlan.id)).where(
                    TestPlan.project_id == project_id, TestPlan.status == "approved"
                )
            )
        ) or 0
        plan_completion = (
            round((approved_plans / total_plans) * 100, 1) if total_plans > 0 else 0.0
        )

        plan_metrics = TestPlanMetrics(
            total=total_plans,
            approved=approved_plans,
            completionPercentage=plan_completion,
        )

        # 3. Test Cases Metrics
        tc_total_stmt = select(func.count(TestCase.id)).where(
            TestCase.project_id == project_id,
            TestCase.is_deleted == False,
        )
        if release_version:
            tc_total_stmt = tc_total_stmt.where(
                TestCase.linked_release_version == release_version
            )
        total_tcs = (await self.db.execute(tc_total_stmt)).scalar() or 0

        tc_automated_stmt = select(func.count(TestCase.id)).where(
            TestCase.project_id == project_id,
            TestCase.is_deleted == False,
            or_(
                TestCase.execution_mode.in_(["automation", "automated"]),
                TestCase.automation_status == "automated",
                TestCase.automation_script_id != None,
            ),
        )
        if release_version:
            tc_automated_stmt = tc_automated_stmt.where(
                TestCase.linked_release_version == release_version
            )
        automated_tcs = (await self.db.execute(tc_automated_stmt)).scalar() or 0

        manual_tcs = total_tcs - automated_tcs
        auto_coverage = (
            round((automated_tcs / total_tcs) * 100, 1) if total_tcs > 0 else 0.0
        )

        # Coverage % = Requirements with at least 1 TC / Total Requirements * 100
        req_with_tc_stmt = select(func.count(distinct(TestCase.requirement_id))).where(
            TestCase.project_id == project_id,
            TestCase.is_deleted == False,
            TestCase.requirement_id != None,
        )
        if release_version:
            req_with_tc_stmt = req_with_tc_stmt.where(
                TestCase.linked_release_version == release_version
            )
        req_with_tc = (await self.db.execute(req_with_tc_stmt)).scalar() or 0
        tc_coverage = (
            round((req_with_tc / total_reqs) * 100, 1) if total_reqs > 0 else 0.0
        )

        tc_metrics = TestCaseMetrics(
            total=total_tcs,
            automated=automated_tcs,
            manual=manual_tcs,
            automationCoveragePercentage=auto_coverage,
            testCaseCoveragePercentage=tc_coverage,
        )

        # 4. Test Data Metrics
        total_td = (
            await self.db.scalar(
                select(func.count(TestData.id)).where(TestData.project_id == project_id)
            )
        ) or 0
        approved_td = (
            await self.db.scalar(
                select(func.count(TestData.id)).where(
                    TestData.project_id == project_id,
                    TestData.approval_status == "approved",
                )
            )
        ) or 0
        pending_td = total_td - approved_td
        td_readiness = (
            round((approved_td / total_td) * 100, 1) if total_td > 0 else 0.0
        )

        td_metrics = TestDataMetrics(
            total=total_td,
            approved=approved_td,
            pending=pending_td,
            readinessPercentage=td_readiness,
        )

        # 5. Execution Metrics
        total_runs = (
            await self.db.scalar(
                select(func.count(ExecutionRun.id)).where(
                    ExecutionRun.project_id == project_id
                )
            )
        ) or 0
        completed_runs = (
            await self.db.scalar(
                select(func.count(ExecutionRun.id)).where(
                    ExecutionRun.project_id == project_id,
                    ExecutionRun.status.in_(["completed", "passed"]),
                    ExecutionRun.failed == 0,
                )
            )
        ) or 0
        failed_runs = (
            await self.db.scalar(
                select(func.count(ExecutionRun.id)).where(
                    ExecutionRun.project_id == project_id,
                    or_(
                        ExecutionRun.status == "failed",
                        ExecutionRun.failed > 0,
                    ),
                )
            )
        ) or 0
        running_runs = (
            await self.db.scalar(
                select(func.count(ExecutionRun.id)).where(
                    ExecutionRun.project_id == project_id,
                    ExecutionRun.status.in_(["running", "pending", "in_progress"]),
                )
            )
        ) or 0

        completed_runs_stmt = select(ExecutionRun).where(
            ExecutionRun.project_id == project_id,
            ExecutionRun.status.in_(["completed", "passed"]),
        )
        completed_runs_list = (
            (await self.db.execute(completed_runs_stmt)).scalars().all()
        )

        passed_tests = sum(r.passed for r in completed_runs_list)
        failed_tests = sum(r.failed for r in completed_runs_list)
        not_run_tests = sum(r.skipped for r in completed_runs_list)

        completed_run_ids = [r.id for r in completed_runs_list]
        blocked_tests = 0
        if completed_run_ids:
            blocked_tests = (
                await self.db.scalar(
                    select(func.count(ExecutionResult.id)).where(
                        ExecutionResult.execution_run_id.in_(completed_run_ids),
                        ExecutionResult.status == "blocked",
                    )
                )
            ) or 0

        executed_tests = passed_tests + failed_tests + blocked_tests
        # A case may have results in several historical runs. Release completion
        # cannot exceed 100%, even when those result totals overlap.
        exec_completion = (
            min(100.0, round((executed_tests / total_tcs) * 100, 1))
            if total_tcs > 0
            else 0.0
        )
        exec_pass_rate = (
            round((passed_tests / executed_tests) * 100, 1)
            if executed_tests > 0
            else 0.0
        )

        exec_metrics = ExecutionMetrics(
            totalRuns=total_runs,
            completedRuns=completed_runs,
            failedRuns=failed_runs,
            runningRuns=running_runs,
            passed=passed_tests,
            failed=failed_tests,
            blocked=blocked_tests,
            notRun=not_run_tests,
            completionPercentage=exec_completion,
            passRatePercentage=exec_pass_rate,
        )

        # 6. Defects Metrics
        total_defects = (
            await self.db.scalar(
                select(func.count(DefectDraft.id)).where(
                    DefectDraft.project_id == project_id
                )
            )
        ) or 0

        # Open defects: status != rejected, and (not pushed to Jira, or if pushed, Jira status is not Closed/Resolved/Done)
        open_defects_stmt = (
            select(func.count(DefectDraft.id))
            .outerjoin(JiraDefect, DefectDraft.id == JiraDefect.defect_draft_id)
            .where(
                DefectDraft.project_id == project_id,
                DefectDraft.status != "rejected",
                (JiraDefect.id == None)
                | (~JiraDefect.jira_status.in_(["Closed", "Resolved", "Done"])),
            )
        )
        open_defects = (await self.db.execute(open_defects_stmt)).scalar() or 0

        def severity_stmt(sev: str):
            return (
                select(func.count(DefectDraft.id))
                .outerjoin(JiraDefect, DefectDraft.id == JiraDefect.defect_draft_id)
                .where(
                    DefectDraft.project_id == project_id,
                    DefectDraft.status != "rejected",
                    func.lower(DefectDraft.severity) == sev.lower(),
                    (JiraDefect.id == None)
                    | (~JiraDefect.jira_status.in_(["Closed", "Resolved", "Done"])),
                )
            )

        critical_defects = (await self.db.execute(severity_stmt("critical"))).scalar() or 0
        high_defects = (await self.db.execute(severity_stmt("high"))).scalar() or 0
        medium_defects = (await self.db.execute(severity_stmt("medium"))).scalar() or 0
        low_defects = max(0, open_defects - (critical_defects + high_defects + medium_defects))

        closed_defects = total_defects - open_defects
        defect_closure = (
            round((closed_defects / total_defects) * 100, 1)
            if total_defects > 0
            else 0.0
        )

        defect_metrics = DefectMetrics(
            total=total_defects,
            open=open_defects,
            critical=critical_defects,
            high=high_defects,
            medium=medium_defects,
            low=low_defects,
            closurePercentage=defect_closure,
        )

        # 7. Reports Metrics
        total_reports = (
            await self.db.scalar(
                select(func.count(Report.id)).where(Report.project_id == project_id)
            )
        ) or 0
        published_reports = (
            await self.db.scalar(
                select(func.count(Report.id)).where(
                    Report.project_id == project_id, Report.status == "published"
                )
            )
        ) or 0
        report_completion = (
            round((published_reports / total_reports) * 100, 1)
            if total_reports > 0
            else 0.0
        )

        report_metrics = ReportMetrics(
            total=total_reports,
            published=published_reports,
            completionPercentage=report_completion,
        )

        # 8. Release Readiness score & status
        defect_health = max(0.0, 100.0 - (critical_defects * 20.0 + high_defects * 10.0))

        readiness_score = round(
            (req_completion * 0.20)
            + (plan_completion * 0.15)
            + (tc_coverage * 0.20)
            + (td_readiness * 0.10)
            + (exec_completion * 0.15)
            + (exec_pass_rate * 0.10)
            + (defect_health * 0.10),
            1,
        )

        reasons = []
        if req_completion < 80.0:
            reasons.append(f"Requirements approval rate is low ({req_completion}%)")
        if plan_completion < 80.0:
            reasons.append(f"Test plans approval rate is low ({plan_completion}%)")
        if tc_coverage < 80.0:
            reasons.append(f"Test case requirement coverage is low ({tc_coverage}%)")
        if td_readiness < 80.0:
            reasons.append(f"Test data readiness is low ({td_readiness}%)")
        if exec_completion < 80.0:
            reasons.append(f"Test execution completion is low ({exec_completion}%)")
        if exec_pass_rate < 90.0:
            reasons.append(f"Test execution pass rate is low ({exec_pass_rate}%)")
        if critical_defects > 0:
            reasons.append(f"There are {critical_defects} open critical defects")
        if high_defects > 3:
            reasons.append(f"High severity defects exceed target ({high_defects} open)")

        if critical_defects > 0 or high_defects > 3 or readiness_score < 70.0:
            readiness_status = "NO-GO"
        elif readiness_score < 85.0:
            readiness_status = "AT-RISK"
        else:
            readiness_status = "GO"

        readiness_metrics = ReleaseReadinessMetrics(
            score=readiness_score,
            status=readiness_status,
            target=85.0,
            reasons=reasons,
        )

        # 9. Jira Sync Metrics
        synced_reqs = (
            await self.db.scalar(
                select(func.count(Requirement.id)).where(
                    Requirement.project_id == project_id,
                    Requirement.is_deleted == False,
                    Requirement.jira_issue_key != None,
                )
            )
        ) or 0
        synced_tcs = (
            await self.db.scalar(
                select(func.count(TestCase.id)).where(
                    TestCase.project_id == project_id,
                    TestCase.is_deleted == False,
                    TestCase.jira_sync_status == "synced",
                )
            )
        ) or 0
        failed_tcs = (
            await self.db.scalar(
                select(func.count(TestCase.id)).where(
                    TestCase.project_id == project_id,
                    TestCase.is_deleted == False,
                    TestCase.jira_sync_status == "failed",
                )
            )
        ) or 0
        conflict_tcs = (
            await self.db.scalar(
                select(func.count(TestCase.id)).where(
                    TestCase.project_id == project_id,
                    TestCase.is_deleted == False,
                    TestCase.jira_sync_status == "conflict",
                )
            )
        ) or 0

        synced_count = synced_reqs + synced_tcs
        is_healthy = failed_tcs == 0 and conflict_tcs == 0

        jira_metrics = JiraSyncMetrics(
            syncedCount=synced_count,
            failureCount=failed_tcs,
            conflictCount=conflict_tcs,
            isHealthy=is_healthy,
        )

        # 10. Domain Quality Grid
        domains = [
            "Mobile",
            "Fixed",
            "Digital-Business",
            "Billing",
            "Digital-Consumer",
            "Data",
            "BSS",
            "Network",
            "Sales",
        ]
        domain_quality = []
        for domain in domains:
            domain_total = (
                await self.db.scalar(
                    select(func.count(TestCase.id)).where(
                        TestCase.project_id == project_id,
                        TestCase.is_deleted == False,
                        func.lower(TestCase.telecom_domain) == domain.lower(),
                    )
                )
            ) or 0
            if domain_total == 0:
                domain_quality.append(
                    DomainQualityMetrics(
                        domain=domain, passRate=0.0, total=0, hasData=False
                    )
                )
            else:
                passed_domain = (
                    await self.db.scalar(
                        select(func.count(TestCase.id)).where(
                            TestCase.project_id == project_id,
                            TestCase.is_deleted == False,
                            func.lower(TestCase.telecom_domain) == domain.lower(),
                            or_(
                                TestCase.last_automation_status == "passed",
                                TestCase.status == "approved",
                            ),
                        )
                    )
                ) or 0
                pass_rate = round((passed_domain / domain_total) * 100, 1)
                domain_quality.append(
                    DomainQualityMetrics(
                        domain=domain,
                        passRate=pass_rate,
                        total=domain_total,
                        hasData=True,
                    )
                )

        # 11. Pipeline Overview
        pipeline_overview = [
            PipelineStepMetrics(
                label="Requirements",
                current=approved_reqs,
                total=total_reqs,
                rate=req_completion,
                color="#10b981",
            ),
            PipelineStepMetrics(
                label="Test Planning",
                current=approved_plans,
                total=total_plans,
                rate=plan_completion,
                color="#3b82f6",
            ),
            PipelineStepMetrics(
                label="Test Cases",
                current=req_with_tc,
                total=total_reqs,
                rate=tc_coverage,
                color="#8b5cf6",
            ),
            PipelineStepMetrics(
                label="Test Data",
                current=approved_td,
                total=total_td,
                rate=td_readiness,
                color="#06b6d4",
            ),
            PipelineStepMetrics(
                label="Automation",
                current=automated_tcs,
                total=total_tcs,
                rate=auto_coverage,
                color="#f59e0b",
            ),
            PipelineStepMetrics(
                label="Execution",
                current=executed_tests,
                total=total_tcs,
                rate=exec_completion,
                color="#3b82f6",
            ),
            PipelineStepMetrics(
                label="Defects",
                current=open_defects,
                total=total_defects,
                rate=defect_health,
                color="#ef4444",
                isDefects=True,
            ),
            PipelineStepMetrics(
                label="Reports",
                current=published_reports,
                total=total_reports,
                rate=report_completion,
                color="#10b981",
            ),
        ]

        # 12. Defect Chart Data
        defect_chart_data = [
            DefectChartItem(name="Critical", value=critical_defects, color="#ef4444"),
            DefectChartItem(name="High", value=high_defects, color="#f97316"),
            DefectChartItem(name="Medium", value=medium_defects, color="#eab308"),
            DefectChartItem(name="Low", value=low_defects, color="#10b981"),
        ]

        # 13. Execution Trend Data (last 7 runs)
        trend_stmt = (
            select(ExecutionRun)
            .where(ExecutionRun.project_id == project_id)
            .order_by(ExecutionRun.created_at.desc())
            .limit(7)
        )
        trend_runs = (await self.db.execute(trend_stmt)).scalars().all()
        execution_trend = []
        for run in reversed(trend_runs):
            name_parts = run.execution_id.split("-")
            name = name_parts[1] if len(name_parts) > 1 else run.execution_id
            in_progress = (
                max(0, run.total_tests - (run.passed + run.failed))
                if run.status in ["running", "pending", "in_progress"]
                else 0
            )
            execution_trend.append(
                ExecutionTrendItem(
                    name=name,
                    Passed=run.passed,
                    Failed=run.failed,
                    InProgress=in_progress,
                )
            )

        # 14. Pending Approvals list
        pending_approvals = []
        # Requirement signoffs
        pend_reqs = (
            await self.db.scalar(
                select(func.count(Requirement.id)).where(
                    Requirement.project_id == project_id,
                    Requirement.is_deleted == False,
                    Requirement.status == "pending_review",
                )
            )
        ) or 0
        if pend_reqs > 0:
            pending_approvals.append(
                PendingApprovalItem(
                    title="Requirement Approval Needed",
                    subtitle=f"{pend_reqs} requirement(s) pending intake quality sign-off",
                    count=pend_reqs,
                    priority="High Priority",
                    priorityColor="text-amber-600 bg-amber-50 border-amber-100",
                )
            )

        # Test plans signoffs
        pend_plans = (
            await self.db.scalar(
                select(func.count(TestPlan.id)).where(
                    TestPlan.project_id == project_id,
                    TestPlan.status.in_(["draft", "pending_approval"]),
                )
            )
        ) or 0
        if pend_plans > 0:
            pending_approvals.append(
                PendingApprovalItem(
                    title="Test Plan Sign-off Needed",
                    subtitle=f"{pend_plans} test plan(s) pending verification",
                    count=pend_plans,
                    priority="High Priority",
                    priorityColor="text-amber-600 bg-amber-50 border-amber-100",
                )
            )

        # Test cases signoffs
        pend_tcs = (
            await self.db.scalar(
                select(func.count(TestCase.id)).where(
                    TestCase.project_id == project_id,
                    TestCase.is_deleted == False,
                    TestCase.status.in_(["draft", "pending_approval"]),
                )
            )
        ) or 0
        if pend_tcs > 0:
            pending_approvals.append(
                PendingApprovalItem(
                    title="Test Case Verification Review",
                    subtitle=f"{pend_tcs} new AI-generated test cases require baseline review",
                    count=pend_tcs,
                    priority="Medium Priority",
                    priorityColor="text-amber-600 bg-amber-50 border-amber-100",
                )
            )

        # Test data signoffs
        pend_td_count = (
            await self.db.scalar(
                select(func.count(TestData.id)).where(
                    TestData.project_id == project_id,
                    TestData.approval_status.in_(["pending_approval", "draft"]),
                )
            )
        ) or 0
        if pend_td_count > 0:
            pending_approvals.append(
                PendingApprovalItem(
                    title="Test Data Set Allocation Approval",
                    subtitle=f"{pend_td_count} synthetic customer profile payload ready for verification",
                    count=pend_td_count,
                    priority="Medium Priority",
                    priorityColor="text-amber-600 bg-amber-50 border-amber-100",
                )
            )

        # Defect triage approvals
        pend_defects = (
            await self.db.scalar(
                select(func.count(DefectDraft.id)).where(
                    DefectDraft.project_id == project_id,
                    DefectDraft.status.in_(["draft", "pending_review"]),
                )
            )
        ) or 0
        if pend_defects > 0:
            pending_approvals.append(
                PendingApprovalItem(
                    title="Defect Triage Approval",
                    subtitle=f"{pend_defects} defects pending triage sign-off",
                    count=pend_defects,
                    priority="High Priority",
                    priorityColor="text-red-600 bg-red-50 border-red-100",
                )
            )

        if not pending_approvals:
            pending_approvals.append(
                PendingApprovalItem(
                    title="Test Suite Signoff & Approval",
                    subtitle="Release sprint package ready for automated execution run",
                    count=0,
                    priority="Clear",
                    priorityColor="text-emerald-600 bg-emerald-50 border-emerald-100",
                )
            )

        # 15. Recent Activity Feed
        recent_activities = []

        # Aliases so we can join User twice (updater + creator)
        UpdaterUser = aliased(User)
        CreatorUser = aliased(User)

        # Requirements — resolve real user name from updated_by → created_by
        req_act_stmt = (
            select(
                Requirement,
                func.coalesce(UpdaterUser.full_name, CreatorUser.full_name).label("user_name"),
            )
            .outerjoin(UpdaterUser, Requirement.updated_by == UpdaterUser.id)
            .outerjoin(CreatorUser, Requirement.created_by == CreatorUser.id)
            .where(Requirement.project_id == project_id, Requirement.is_deleted == False)
            .order_by(Requirement.updated_at.desc())
            .limit(3)
        )
        req_acts = (await self.db.execute(req_act_stmt)).all()
        for r, user_name in req_acts:
            recent_activities.append(
                RecentActivityItem(
                    user=user_name or "Unknown",
                    action=f"updated requirement {r.requirement_id}",
                    subject=r.title,
                    time=r.updated_at.isoformat() if r.updated_at else "",
                    is_agent=False,
                )
            )

        # Test Cases — resolve real user name from updated_by → created_by
        UpdaterUser2 = aliased(User)
        CreatorUser2 = aliased(User)
        tc_act_stmt = (
            select(
                TestCase,
                func.coalesce(UpdaterUser2.full_name, CreatorUser2.full_name).label("user_name"),
            )
            .outerjoin(UpdaterUser2, TestCase.updated_by == UpdaterUser2.id)
            .outerjoin(CreatorUser2, TestCase.created_by == CreatorUser2.id)
            .where(
                TestCase.project_id == project_id,
                TestCase.is_deleted == False,
            )
            .order_by(TestCase.updated_at.desc())
            .limit(3)
        )
        tc_acts = (await self.db.execute(tc_act_stmt)).all()
        for tc, user_name in tc_acts:
            recent_activities.append(
                RecentActivityItem(
                    user=user_name or "Unknown",
                    action=f"updated test case {tc.test_case_id}",
                    subject=tc.title,
                    time=tc.updated_at.isoformat() if tc.updated_at else "",
                    is_agent=False,
                )
            )

        # Defects — only has created_by
        CreatorUser3 = aliased(User)
        def_act_stmt = (
            select(
                DefectDraft,
                CreatorUser3.full_name.label("user_name"),
            )
            .outerjoin(CreatorUser3, DefectDraft.created_by == CreatorUser3.id)
            .where(DefectDraft.project_id == project_id)
            .order_by(DefectDraft.created_at.desc())
            .limit(3)
        )
        def_acts = (await self.db.execute(def_act_stmt)).all()
        for d, user_name in def_acts:
            recent_activities.append(
                RecentActivityItem(
                    user=user_name or "Unknown",
                    action=f"logged defect {d.defect_id}",
                    subject=d.summary,
                    time=d.created_at.isoformat() if d.created_at else "",
                    is_agent=False,
                )
            )

        agent_labels = {
            "requirement_intake": "Requirement Intake Agent",
            "requirement_quality": "Requirement Quality Agent",
            "test_planning": "Test Planning Agent",
            "test_scenario": "Test Scenario Agent",
            "test_case": "Test Case Generator Agent",
            "test_data": "Test Data Agent",
            "automation_classification": "Automation Classification Agent",
            "automation_script": "Automation Script Agent",
            "test_execution": "Test Execution Agent",
            "defect_analysis": "Defect Analysis Agent",
            "jira_defect": "Jira Defect Agent",
            "test_reporting": "Test Reporting Agent",
        }
        agent_act_stmt = (
            select(AgentRun)
            .where(AgentRun.project_id == project_id)
            .order_by(AgentRun.updated_at.desc())
            .limit(6)
        )
        agent_acts = (await self.db.execute(agent_act_stmt)).scalars().all()
        for run in agent_acts:
            label = agent_labels.get(run.agent_name, run.agent_name.replace("_", " ").title())
            recent_activities.append(
                RecentActivityItem(
                    user="AI Agent",
                    action=run.progress_message or f"{label} {run.status}",
                    subject=label,
                    time=run.updated_at.isoformat() if run.updated_at else "",
                    is_agent=True,
                )
            )

        # Sort the combined audit feed; keep enough entries for Human/Agent tabs.
        recent_activities = sorted(
            recent_activities, key=lambda a: a.time, reverse=True
        )[:12]

        # Fallback if no real data found (empty project)
        if not recent_activities:
            recent_activities = [
                RecentActivityItem(
                    user="System",
                    action="project created",
                    subject="No activity yet — start by uploading requirements",
                    time="",
                    is_agent=False,
                ),
            ]

        return DashboardMetricsOut(
            requirements=req_metrics,
            testPlans=plan_metrics,
            testCases=tc_metrics,
            testData=td_metrics,
            execution=exec_metrics,
            defects=defect_metrics,
            reports=report_metrics,
            releaseReadiness=readiness_metrics,
            jiraSync=jira_metrics,
            domainQuality=domain_quality,
            pipelineOverview=pipeline_overview,
            defectChartData=defect_chart_data,
            executionTrend=execution_trend,
            pendingApprovals=pending_approvals,
            recentActivities=recent_activities,
        )
