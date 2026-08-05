// Centralized mock/fallback data for dashboard panels not yet backed by real APIs.
// Used when the backend cannot provide AI quality, RAG, or quality-gate metrics.

export const AI_QUALITY_MOCK = {
  confidence: 82,
  sparkline: [60, 65, 70, 72, 75, 79, 82],
  ambiguity: { value: 18, level: "Medium" as const },
  coverageGaps: { value: 24, level: "High" as const },
  defectPredictionRisk: { value: 31, level: "High" as const },
};

export const RAG_KNOWLEDGE_MOCK = {
  documentsIndexed: 12,
  jiraStoriesIndexed: 32,
  chunks: 248,
  retrievalAccuracy: 87,
  status: "Healthy" as const,
};

export type QualityGateStatus = "Passed" | "Failed" | "Pending";

export const QUALITY_GATES_MOCK: Array<{ name: string; status: QualityGateStatus }> = [
  { name: "Requirement Approval", status: "Failed" },
  { name: "Automation Readiness", status: "Passed" },
  { name: "Test Planning", status: "Passed" },
  { name: "Execution Readiness", status: "Pending" },
  { name: "Test Case Review", status: "Failed" },
  { name: "Defect Closure", status: "Failed" },
  { name: "Test Data Readiness", status: "Pending" },
  { name: "Release Report", status: "Pending" },
];

export const TRACEABILITY_MOCK = {
  reqToTC: 28,
  tcToAutomation: 81,
  defectsToReq: 43,
  uncoveredRequirements: 23,
  orphanTestCases: 14,
};

export type ActionVariant = "high" | "ai" | "warning" | "critical";

export const NEXT_BEST_ACTIONS_MOCK: Array<{
  title: string;
  label: string;
  variant: ActionVariant;
  href: string;
}> = [
  { title: "Approve 23 requirements", label: "High impact", variant: "high", href: "/requirements" },
  { title: "Review 56 AI-generated test cases", label: "AI Generated", variant: "ai", href: "/test-cases" },
  { title: "Generate synthetic test data", label: "No data available", variant: "warning", href: "/test-data" },
  { title: "Triage 5 high/critical defects", label: "Release Blocker", variant: "critical", href: "/defects" },
  { title: "Run critical-path execution", label: "10 tests blocked", variant: "warning", href: "/execution" },
];

export type AgentStatus = "Active" | "Running" | "Waiting" | "Scheduled" | "Completed";

export const AI_AGENTS_MOCK: Array<{
  name: string;
  status: AgentStatus;
  detail: string;
  time: string;
}> = [
  { name: "Requirement Analyst Agent", status: "Active", detail: "Analyzed 32 requirements", time: "10m ago" },
  { name: "Test Case Generator Agent", status: "Running", detail: "Generated 56 test cases", time: "5m ago" },
  { name: "Defect Triage Agent", status: "Active", detail: "Triaged 7 defects", time: "8m ago" },
  { name: "Test Execution Agent", status: "Waiting", detail: "Queued 10 runs", time: "—" },
  { name: "Report Agent", status: "Scheduled", detail: "Next run 10:00 AM", time: "—" },
];

export const AI_AGENT_STATS_MOCK = {
  actionsToday: 48,
  timeSavedHrs: 6.5,
};

export type DomainRisk = "Low" | "Medium" | "High";

export const DOMAIN_QUALITY_MOCK: Array<{
  domain: string;
  reqCoverage: number;
  tcCoverage: number;
  automation: number;
  passRate: number;
  openDefects: number;
  risk: DomainRisk;
}> = [
  { domain: "Mobile",           reqCoverage: 72, tcCoverage: 68, automation: 55, passRate: 78, openDefects: 4, risk: "High" },
  { domain: "Fixed",            reqCoverage: 85, tcCoverage: 82, automation: 76, passRate: 88, openDefects: 2, risk: "Medium" },
  { domain: "Digital Business", reqCoverage: 61, tcCoverage: 58, automation: 40, passRate: 64, openDefects: 6, risk: "High" },
  { domain: "Billing",          reqCoverage: 90, tcCoverage: 87, automation: 82, passRate: 92, openDefects: 1, risk: "Low" },
  { domain: "Digital Consumer", reqCoverage: 75, tcCoverage: 71, automation: 65, passRate: 81, openDefects: 3, risk: "Medium" },
  { domain: "Data",             reqCoverage: 68, tcCoverage: 65, automation: 50, passRate: 70, openDefects: 4, risk: "High" },
  { domain: "BSS",              reqCoverage: 88, tcCoverage: 84, automation: 78, passRate: 90, openDefects: 2, risk: "Low" },
  { domain: "Network",          reqCoverage: 57, tcCoverage: 53, automation: 35, passRate: 60, openDefects: 7, risk: "High" },
  { domain: "Sales",            reqCoverage: 93, tcCoverage: 91, automation: 88, passRate: 95, openDefects: 1, risk: "Low" },
];

export const EXECUTION_TREND_MOCK = [
  { name: "May 3",  Passed: 42, Failed: 8,  Blocked: 5 },
  { name: "May 5",  Passed: 55, Failed: 12, Blocked: 7 },
  { name: "May 7",  Passed: 48, Failed: 6,  Blocked: 4 },
  { name: "May 9",  Passed: 60, Failed: 15, Blocked: 9 },
  { name: "May 11", Passed: 68, Failed: 18, Blocked: 14 },
  { name: "May 13", Passed: 68, Failed: 18, Blocked: 14 },
  { name: "May 16", Passed: 68, Failed: 18, Blocked: 14 },
];

export const DEFECT_AGING_MOCK = [
  { label: "0-2 days",  count: 28, pct: 37, color: "#10b981" },
  { label: "3-7 days",  count: 18, pct: 24, color: "#D52B31" },
  { label: "8-15 days", count: 14, pct: 18, color: "#f59e0b" },
  { label: ">15 days",  count: 16, pct: 21, color: "#ef4444" },
];
