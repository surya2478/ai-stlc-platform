import pytest
from datetime import datetime
from unittest.mock import MagicMock

from app.services.metrics_service import MetricsService


class FakeScalars:
    def __init__(self, vals):
        self.vals = vals

    def all(self):
        return self.vals


class FakeResult:
    def __init__(self, val):
        self.val = val

    def scalar(self):
        return self.val

    def scalars(self):
        return FakeScalars(self.val if isinstance(self.val, list) else [self.val])

    def all(self):
        # Recent-activity queries select (Entity, user_name) tuples; every
        # _lookup branch already returns a list of single mock rows, so pair
        # each with a mock user_name to satisfy `for row, user_name in ...`.
        if isinstance(self.val, list):
            return [(item, "Mock User") for item in self.val]
        return []


class SmartFakeSession:
    def __init__(self, behavior="normal"):
        self.behavior = behavior

    async def execute(self, stmt):
        val = self._lookup(stmt)
        return FakeResult(val)

    async def scalar(self, stmt):
        val = self._lookup(stmt)
        if isinstance(val, list):
            return val[0] if val else None
        return val

    def _lookup(self, stmt):
        compiled = str(stmt).lower()
        
        # Collect bind parameters
        param_vals = []
        try:
            for v in stmt.compile().params.values():
                if isinstance(v, (list, tuple, set)):
                    for item in v:
                        param_vals.append(str(item).lower())
                else:
                    param_vals.append(str(v).lower())
        except Exception:
            pass

        if self.behavior == "empty":
            if "count" in compiled:
                return 0
            return []

        if "from requirements" in compiled or "requirements." in compiled:
            if "count" in compiled:
                if any(x in param_vals for x in ["approved"]):
                    return 4
                elif any(x in param_vals for x in ["rejected"]):
                    return 0
                elif any(x in param_vals for x in ["pending_review", "pending_approval"]):
                    return 1
                elif any(x in param_vals for x in ["jira_issue_key"]):
                    return 3
                else:
                    return 11
            else:
                req = MagicMock()
                req.requirement_id = "REQ-1"
                req.title = "Mock Requirement"
                req.updated_at = datetime(2026, 6, 13, 12, 0, 0)
                return [req]
        elif "from test_plans" in compiled or "test_plans." in compiled:
            if "count" in compiled:
                if any(x in param_vals for x in ["approved"]):
                    return 1
                elif any(x in param_vals for x in ["draft", "pending_approval"]):
                    return 1
                else:
                    return 2
            else:
                plan = MagicMock()
                plan.id = 1
                plan.name = "Mock Plan"
                plan.status = "approved"
                plan.updated_at = datetime(2026, 6, 13, 12, 0, 0)
                return [plan]
        elif "from test_cases" in compiled or "test_cases." in compiled:
            if "count" in compiled or "distinct" in compiled:
                if any(x in param_vals for x in ["automated"]):
                    return 5
                elif "distinct" in compiled:
                    return 4
                elif any(x in param_vals for x in ["synced"]):
                    return 5
                elif any(x in param_vals for x in ["failed"]):
                    return 0
                elif any(x in param_vals for x in ["conflict"]):
                    return 0
                elif any(x in param_vals for x in ["draft", "pending_approval"]):
                    return 2
                elif "telecom_domain" in compiled:
                    return 5
                else:
                    return 10
            else:
                tc = MagicMock()
                tc.test_case_id = "TC-1"
                tc.title = "Mock Test Case"
                tc.updated_at = datetime(2026, 6, 13, 12, 0, 0)
                return [tc]
        elif "from test_data" in compiled or "test_data." in compiled:
            if "count" in compiled:
                if any(x in param_vals for x in ["approved"]):
                    return 3
                else:
                    return 5
            else:
                td = MagicMock()
                td.id = 1
                td.name = "Mock Test Data"
                td.approval_status = "approved"
                td.updated_at = datetime(2026, 6, 13, 12, 0, 0)
                return [td]
        elif "from execution_runs" in compiled or "execution_runs." in compiled:
            if "completed" in compiled or "passed" in compiled or any(x in param_vals for x in ["completed", "passed"]):
                if "count" in compiled:
                    return 2
                else:
                    run1 = MagicMock()
                    run1.id = 1
                    run1.execution_id = "RUN-1"
                    run1.passed = 10
                    run1.failed = 0
                    run1.skipped = 0
                    run1.status = "completed"
                    run1.created_at = datetime(2026, 6, 12, 12, 0, 0)
                    
                    run2 = MagicMock()
                    run2.id = 2
                    run2.execution_id = "RUN-2"
                    run2.passed = 5
                    run2.failed = 1
                    run2.skipped = 0
                    run2.status = "completed"
                    run2.created_at = datetime(2026, 6, 13, 12, 0, 0)
                    return [run1, run2]
            elif any(x in param_vals for x in ["failed"]):
                return 1
            elif any(x in param_vals for x in ["running", "pending"]):
                return 0
            else:
                if "count" in compiled:
                    return 3
                else:
                    run = MagicMock()
                    run.id = 1
                    run.execution_id = "RUN-1"
                    run.passed = 10
                    run.failed = 0
                    run.skipped = 0
                    run.status = "completed"
                    run.created_at = datetime(2026, 6, 12, 12, 0, 0)
                    return [run]
        elif "from execution_results" in compiled or "execution_results." in compiled:
            if any(x in param_vals for x in ["blocked"]):
                return 0
            else:
                return 10
        elif "from defect_drafts" in compiled or "defect_drafts." in compiled:
            if "count" in compiled:
                if any(x in param_vals for x in ["critical"]):
                    if self.behavior == "critical_defect":
                        return 1
                    return 0
                elif any(x in param_vals for x in ["high"]):
                    return 0
                elif any(x in param_vals for x in ["medium"]):
                    return 1
                elif any(x in param_vals for x in ["draft", "pending_review"]):
                    return 1
                else:
                    return 2
            else:
                d = MagicMock()
                d.defect_id = "DEF-1"
                d.summary = "Mock Defect"
                d.created_at = datetime(2026, 6, 13, 12, 0, 0)
                return [d]
        elif "from reports" in compiled or "reports." in compiled:
            if "count" in compiled:
                if any(x in param_vals for x in ["published"]):
                    return 12
                else:
                    return 15
            else:
                rep = MagicMock()
                rep.id = 1
                rep.title = "Mock Report"
                rep.status = "published"
                rep.created_at = datetime(2026, 6, 13, 12, 0, 0)
                return [rep]
        elif "from agent_runs" in compiled or "agent_runs." in compiled:
            run = MagicMock()
            run.agent_name = "test_case"
            run.status = "completed"
            run.progress_message = "Generated test cases"
            run.updated_at = datetime(2026, 6, 13, 13, 0, 0)
            return [run]
        
        return 0


@pytest.mark.anyio
async def test_metrics_service_normal_calculations():
    db = SmartFakeSession("normal")
    service = MetricsService(db)
    metrics = await service.get_dashboard_metrics(project_id=1)

    assert metrics.requirements.total == 11
    assert metrics.requirements.approved == 4
    assert metrics.requirements.completionPercentage == 36.4

    assert metrics.testPlans.total == 2
    assert metrics.testPlans.approved == 1
    assert metrics.testPlans.completionPercentage == 50.0

    assert metrics.testCases.total == 10
    assert metrics.testCases.automated == 5
    assert metrics.testCases.automationCoveragePercentage == 50.0
    assert metrics.testCases.testCaseCoveragePercentage == 36.4

    assert metrics.testData.total == 5
    assert metrics.testData.approved == 3
    assert metrics.testData.readinessPercentage == 60.0

    assert metrics.execution.totalRuns == 3
    assert metrics.execution.completedRuns == 2
    assert metrics.execution.passed == 15
    assert metrics.execution.failed == 1
    assert metrics.execution.completionPercentage == 100.0
    assert metrics.execution.passRatePercentage == 93.8

    assert metrics.defects.total == 2
    assert metrics.defects.open == 2
    assert metrics.defects.critical == 0
    assert metrics.defects.high == 0

    assert metrics.releaseReadiness.status == "NO-GO"
    assert metrics.releaseReadiness.score == 62.4
    assert any(activity.is_agent for activity in metrics.recentActivities)


@pytest.mark.anyio
async def test_metrics_service_empty_database():
    db = SmartFakeSession("empty")
    service = MetricsService(db)
    metrics = await service.get_dashboard_metrics(project_id=1)

    assert metrics.requirements.total == 0
    assert metrics.requirements.completionPercentage == 0.0
    assert metrics.testPlans.completionPercentage == 0.0
    assert metrics.testCases.automationCoveragePercentage == 0.0
    assert metrics.testData.readinessPercentage == 0.0
    assert metrics.execution.passRatePercentage == 0.0
    assert metrics.releaseReadiness.score == 10.0  # defect health starts at 100% * 0.10 = 10
    assert metrics.releaseReadiness.status == "NO-GO"


@pytest.mark.anyio
async def test_metrics_service_critical_defect():
    db = SmartFakeSession("critical_defect")
    service = MetricsService(db)
    metrics = await service.get_dashboard_metrics(project_id=1)

    assert metrics.defects.critical == 1
    assert metrics.releaseReadiness.status == "NO-GO"
