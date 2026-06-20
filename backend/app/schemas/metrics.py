from typing import Any
from pydantic import BaseModel


class RequirementMetrics(BaseModel):
    total: int
    approved: int
    pending: int
    rejected: int
    completionPercentage: float


class TestPlanMetrics(BaseModel):
    total: int
    approved: int
    completionPercentage: float


class TestCaseMetrics(BaseModel):
    total: int
    automated: int
    manual: int
    automationCoveragePercentage: float
    testCaseCoveragePercentage: float


class TestDataMetrics(BaseModel):
    total: int
    approved: int
    pending: int
    readinessPercentage: float


class ExecutionMetrics(BaseModel):
    totalRuns: int
    completedRuns: int
    failedRuns: int
    runningRuns: int
    passed: int
    failed: int
    blocked: int
    notRun: int
    completionPercentage: float
    passRatePercentage: float


class DefectMetrics(BaseModel):
    total: int
    open: int
    critical: int
    high: int
    medium: int
    low: int
    closurePercentage: float


class ReportMetrics(BaseModel):
    total: int
    published: int
    completionPercentage: float


class ReleaseReadinessMetrics(BaseModel):
    score: float
    status: str
    target: float
    reasons: list[str]


class JiraSyncMetrics(BaseModel):
    syncedCount: int
    failureCount: int
    conflictCount: int
    isHealthy: bool


class DomainQualityMetrics(BaseModel):
    domain: str
    passRate: float
    total: int
    hasData: bool


class PipelineStepMetrics(BaseModel):
    label: str
    current: int
    total: int
    rate: float
    color: str
    isDefects: bool = False


class DefectChartItem(BaseModel):
    name: str
    value: int
    color: str


class ExecutionTrendItem(BaseModel):
    name: str
    Passed: int
    Failed: int
    InProgress: int


class PendingApprovalItem(BaseModel):
    title: str
    subtitle: str
    count: int
    priority: str
    priorityColor: str


class RecentActivityItem(BaseModel):
    user: str
    action: str
    subject: str
    time: str


class DashboardMetricsOut(BaseModel):
    requirements: RequirementMetrics
    testPlans: TestPlanMetrics
    testCases: TestCaseMetrics
    testData: TestDataMetrics
    execution: ExecutionMetrics
    defects: DefectMetrics
    reports: ReportMetrics
    releaseReadiness: ReleaseReadinessMetrics
    jiraSync: JiraSyncMetrics
    domainQuality: list[DomainQualityMetrics]
    pipelineOverview: list[PipelineStepMetrics]
    defectChartData: list[DefectChartItem]
    executionTrend: list[ExecutionTrendItem]
    pendingApprovals: list[PendingApprovalItem]
    recentActivities: list[RecentActivityItem]
