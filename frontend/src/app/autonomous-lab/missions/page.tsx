"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import {
  Bell,
  Bot,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  FileText,
  PauseCircle,
  Play,
  RefreshCw,
  Search,
  Shield,
  Sparkles,
  TriangleAlert,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  agentRunsApi,
  applicationsApi,
  automationApi,
  discoveryApi,
  executionApi,
  projectsApi,
  requirementsApi,
  testCasesApi,
  type AgentRun,
  type AutomationScript,
  type DashboardMetrics,
  type DiscoverySession,
  type ExecutionDashboardPayload,
  type Project,
  type ProjectApplicationsSummary,
  type Requirement,
  type TestCase,
} from "@/lib/api";

type BadgeVariant = "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple";

type MetricItem = {
  title: string;
  value: string;
  suffix: string;
  note: string;
  badge: string;
  badgeVariant: BadgeVariant;
  icon: LucideIcon;
  tone: string;
};

type LifecycleItem = {
  title: string;
  status: string;
  detail: string;
  icon: LucideIcon;
  tone: string;
  badgeVariant: BadgeVariant;
};

function pct(part: number, total: number): number {
  return total > 0 ? Math.round((part / total) * 100) : 0;
}

function formatRelativeTime(value?: string | null): string {
  if (!value) return "No timestamp";
  // Some older records were serialized as "...+00:00Z"; normalize that
  // redundant suffix so the real activity timestamp still renders correctly.
  const normalizedValue = value.replace(/([+-]\d{2}:\d{2})Z$/, "$1");
  const timestamp = new Date(normalizedValue).getTime();
  if (!Number.isFinite(timestamp)) return "Unknown";
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return days < 30 ? `${days}d ago` : new Date(value).toLocaleDateString();
}

function projectHref(href: string, projectId: number | null): string {
  if (!projectId) return href;
  const [path, query = ""] = href.split("?");
  const params = new URLSearchParams(query);
  params.set("project", String(projectId));
  return `${path}?${params.toString()}`;
}

function statusPresentation(
  state: "complete" | "ready" | "progress" | "warning" | "empty",
): Pick<LifecycleItem, "tone" | "badgeVariant"> {
  if (state === "complete" || state === "ready") {
    return { tone: "border-emerald-100 bg-emerald-50 text-emerald-600", badgeVariant: "success" };
  }
  if (state === "progress") {
    return { tone: "border-blue-100 bg-blue-50 text-[#1b59f8]", badgeVariant: "info" };
  }
  if (state === "warning") {
    return { tone: "border-amber-100 bg-amber-50 text-amber-600", badgeVariant: "warning" };
  }
  return { tone: "border-slate-200 bg-slate-50 text-slate-500", badgeVariant: "outline" };
}

function MetricCard({ item }: { item: MetricItem }) {
  const Icon = item.icon;
  return (
    <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
      <CardContent className="p-4">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${item.tone}`}>
            <Icon className="h-5 w-5" />
          </div>
          <Badge variant={item.badgeVariant} className="whitespace-nowrap text-[10px]">{item.badge}</Badge>
        </div>
        <p className="text-sm font-semibold text-slate-900">{item.title}</p>
        <div className="mt-5 flex items-end gap-2">
          <span className="text-3xl font-bold tracking-tight text-slate-950">{item.value}</span>
          <span className="pb-1 text-xs text-slate-500">{item.suffix}</span>
        </div>
        <p className="mt-3 text-xs text-slate-500">{item.note}</p>
      </CardContent>
    </Card>
  );
}

function LifecycleStep({ item, index, last }: { item: LifecycleItem; index: number; last?: boolean }) {
  const Icon = item.icon;
  return (
    <div className="flex min-w-0 flex-1 items-center">
      <div className="flex min-w-[150px] items-center gap-3">
        <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full border ${item.tone}`}>
          <Icon className="h-6 w-6" />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-semibold leading-5 text-slate-950">{index}. {item.title}</p>
          <Badge variant={item.badgeVariant} className="mt-1 text-[10px]">{item.status}</Badge>
          <p className="mt-1 text-xs text-slate-500">{item.detail}</p>
        </div>
      </div>
      {!last && <div className="mx-4 hidden h-px min-w-8 flex-1 bg-slate-300 xl:block" />}
    </div>
  );
}

function ReadinessRow({ label, value, warning = false }: { label: string; value: string; warning?: boolean }) {
  const Icon = warning ? TriangleAlert : CheckCircle2;
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <div className="flex min-w-0 items-center gap-3">
        <Icon className={`h-4 w-4 shrink-0 ${warning ? "text-amber-500" : "text-emerald-500"}`} />
        <span className="truncate text-slate-700">{label}</span>
      </div>
      <span className={`shrink-0 text-xs font-medium ${warning ? "text-amber-600" : "text-emerald-600"}`}>{value}</span>
    </div>
  );
}

function QueueRow({ icon: Icon, label, count, variant }: { icon: LucideIcon; label: string; count: number; variant: BadgeVariant }) {
  const iconColor = variant === "warning" ? "text-amber-500" : variant === "destructive" ? "text-red-500" : "text-blue-500";
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <div className="flex min-w-0 items-center gap-3">
        <Icon className={`h-4 w-4 shrink-0 ${iconColor}`} />
        <span className="truncate text-slate-700">{label}</span>
      </div>
      <Badge variant={variant} className="min-w-6 justify-center px-2 text-[10px]">{count}</Badge>
    </div>
  );
}

function EvidenceRing({ coverage, results }: { coverage: number; results: Array<{ label: string; count: number; color: string }> }) {
  const total = results.reduce((sum, item) => sum + item.count, 0);
  let cursor = 0;
  const segments = results.map((item) => {
    const start = cursor;
    cursor += total ? (item.count / total) * 100 : 0;
    return `${item.color} ${start}% ${cursor}%`;
  });
  const background = total ? `conic-gradient(${segments.join(", ")})` : "#e2e8f0";
  return (
    <div className="relative flex h-36 w-36 shrink-0 items-center justify-center rounded-full p-3" style={{ background }} aria-label={`Evidence coverage is ${coverage} percent`}>
      <div className="flex h-full w-full flex-col items-center justify-center rounded-full bg-white">
        <span className="text-3xl font-bold text-slate-950">{coverage}%</span>
        <span className="text-xs text-slate-500">Evidence Coverage</span>
      </div>
    </div>
  );
}

function ActionRow({ label, href, button }: { label: string; href: string; button: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 text-sm">
      <span className="text-slate-700">{label}</span>
      <Button asChild variant="outline" size="sm" className="border-violet-300 text-violet-700 hover:bg-violet-50">
        <Link href={href}>{button}</Link>
      </Button>
    </div>
  );
}

function ExecutiveOverviewContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [projects, setProjects] = useState<Project[]>([]);
  const [dashboard, setDashboard] = useState<DashboardMetrics | null>(null);
  const [applicationSummary, setApplicationSummary] = useState<ProjectApplicationsSummary | null>(null);
  const [availableEnvironments, setAvailableEnvironments] = useState<string[]>([]);
  const [discoverySessions, setDiscoverySessions] = useState<DiscoverySession[]>([]);
  const [automationScripts, setAutomationScripts] = useState<AutomationScript[]>([]);
  const [executionDashboard, setExecutionDashboard] = useState<ExecutionDashboardPayload | null>(null);
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [environment, setEnvironment] = useState("");
  const [releaseVersion, setReleaseVersion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  const requestedProjectId = Number(searchParams.get("project")) || null;
  const selectedProjectId = requestedProjectId ?? projects[0]?.id ?? null;
  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null;

  useEffect(() => {
    projectsApi.list()
      .then((response) => setProjects(response.data))
      .catch((requestError: any) => setError(requestError?.response?.data?.detail || "Unable to load projects."));
  }, []);

  useEffect(() => {
    if (requestedProjectId || !projects.length) return;
    const params = new URLSearchParams(searchParams.toString());
    params.set("project", String(projects[0].id));
    router.replace(`${pathname}?${params.toString()}`);
  }, [pathname, projects, requestedProjectId, router, searchParams]);

  useEffect(() => {
    setEnvironment("");
    setReleaseVersion("");
  }, [selectedProjectId]);

  const loadCommandCentre = useCallback(async () => {
    if (!selectedProjectId) return;
    setLoading(true);
    setError(null);
    const results = await Promise.allSettled([
      projectsApi.dashboardMetrics(selectedProjectId, releaseVersion || undefined),
      applicationsApi.summary(selectedProjectId),
      applicationsApi.getForProject(selectedProjectId),
      discoveryApi.listSessions(selectedProjectId),
      automationApi.list(selectedProjectId),
      executionApi.getDashboard({ project_id: selectedProjectId, environment: environment || null }),
      agentRunsApi.list(selectedProjectId, { limit: 100 }),
      testCasesApi.list(selectedProjectId),
      requirementsApi.list(selectedProjectId),
    ]);

    const [dashboardResult, appSummaryResult, appConfigResult, discoveryResult, automationResult, executionResult, agentsResult, testCasesResult, requirementsResult] = results;
    if (dashboardResult.status === "fulfilled") setDashboard(dashboardResult.value.data);
    else setDashboard(null);
    setApplicationSummary(appSummaryResult.status === "fulfilled" ? appSummaryResult.value.data : null);
    setAvailableEnvironments(appConfigResult.status === "fulfilled" ? appConfigResult.value.data.available_environments : []);
    setDiscoverySessions(discoveryResult.status === "fulfilled" ? discoveryResult.value.data : []);
    setAutomationScripts(automationResult.status === "fulfilled" ? automationResult.value.data : []);
    setExecutionDashboard(executionResult.status === "fulfilled" ? executionResult.value.data : null);
    setAgentRuns(agentsResult.status === "fulfilled" ? agentsResult.value.data : []);
    setTestCases(testCasesResult.status === "fulfilled" ? testCasesResult.value.data : []);
    setRequirements(requirementsResult.status === "fulfilled" ? requirementsResult.value.data : []);
    if (dashboardResult.status === "rejected") {
      const reason = dashboardResult.reason as any;
      setError(reason?.response?.data?.detail || "Unable to load Command Centre metrics.");
    }
    setLastRefreshed(new Date());
    setLoading(false);
  }, [environment, releaseVersion, selectedProjectId]);

  useEffect(() => {
    void loadCommandCentre();
  }, [loadCommandCentre]);

  const releaseOptions = useMemo(() => Array.from(new Set(
    requirements.map((requirement) => requirement.release_version).filter(Boolean) as string[],
  )).sort(), [requirements]);

  const approvedTestCases = testCases.filter((testCase) => ["approved", "automated"].includes((testCase.approval_status || testCase.status || "").toLowerCase())).length;
  const completedDiscoverySessions = discoverySessions.filter((session) => ["COMPLETED", "APPROVED"].includes(session.status)).length;
  const activeDiscoverySessions = discoverySessions.filter((session) => ["INITIALISING", "RECORDING", "PAUSE_REQUESTED", "RESUMING", "STOP_REQUESTED"].includes(session.status)).length;
  const readyAutomationScripts = automationScripts.filter((script) => ["approved", "ci_ready"].includes(script.status.toLowerCase())).length;
  const automationReadiness = pct(readyAutomationScripts, automationScripts.length);
  const evidenceReadyCount = testCases.filter((testCase) => testCase.latest_evidence_available).length;
  const evidenceCoverage = pct(evidenceReadyCount, testCases.length);
  const executionKpis = executionDashboard?.kpis;
  const runningAgentRuns = agentRuns.filter((run) => ["running", "queued", "pending", "in_progress"].includes(run.status.toLowerCase())).length;
  const pausedAgentRuns = agentRuns.filter((run) => ["paused", "waiting", "awaiting_input"].includes(run.status.toLowerCase())).length;
  const failedAgentRuns = agentRuns.filter((run) => run.status.toLowerCase() === "failed").length;
  const pendingApprovalCount = dashboard?.pendingApprovals.reduce((sum, item) => sum + item.count, 0) ?? 0;

  const metrics = useMemo<MetricItem[]>(() => {
    const requirementMetrics = dashboard?.requirements;
    const executionMetrics = dashboard?.execution;
    const applicationCount = applicationSummary?.total_applications ?? 0;
    return [
      {
        title: "Requirements",
        value: String(requirementMetrics?.total ?? 0),
        suffix: "Total",
        note: `${requirementMetrics?.approved ?? 0} approved · ${requirementMetrics?.pending ?? 0} pending`,
        badge: requirementMetrics?.total && requirementMetrics.pending === 0 ? "Complete" : requirementMetrics?.pending ? "Pending Review" : "No Data",
        badgeVariant: requirementMetrics?.total && requirementMetrics.pending === 0 ? "success" : requirementMetrics?.pending ? "warning" : "outline",
        icon: FileText,
        tone: "bg-blue-50 text-blue-600",
      },
      {
        title: "Test Cases",
        value: String(testCases.length),
        suffix: "Total",
        note: `${pct(approvedTestCases, testCases.length)}% approved · ${dashboard?.testCases.automated ?? 0} automated`,
        badge: approvedTestCases === testCases.length && testCases.length > 0 ? "Approved" : testCases.length ? "Pending Review" : "No Data",
        badgeVariant: approvedTestCases === testCases.length && testCases.length > 0 ? "success" : testCases.length ? "warning" : "outline",
        icon: ClipboardCheck,
        tone: "bg-amber-50 text-amber-600",
      },
      {
        title: "Discovery",
        value: String(applicationCount),
        suffix: "Applications",
        note: `${completedDiscoverySessions} completed · ${activeDiscoverySessions} active sessions`,
        badge: applicationSummary?.discovery_ready === applicationCount && applicationCount > 0 ? "Ready" : applicationCount ? "Needs Attention" : "Not Configured",
        badgeVariant: applicationSummary?.discovery_ready === applicationCount && applicationCount > 0 ? "success" : applicationCount ? "warning" : "outline",
        icon: Search,
        tone: "bg-emerald-50 text-emerald-600",
      },
      {
        title: "Automation",
        value: `${automationReadiness}%`,
        suffix: "Approved / CI Ready",
        note: `${readyAutomationScripts} of ${automationScripts.length} scripts ready`,
        badge: automationScripts.length ? (automationReadiness === 100 ? "Ready" : "In Progress") : "No Scripts",
        badgeVariant: automationReadiness === 100 && automationScripts.length ? "success" : automationScripts.length ? "info" : "outline",
        icon: Sparkles,
        tone: "bg-blue-50 text-[#1b59f8]",
      },
      {
        title: "Execution",
        value: String(executionKpis?.total_executions ?? executionMetrics?.totalRuns ?? 0),
        suffix: "Runs",
        note: `${executionKpis?.in_progress ?? executionMetrics?.runningRuns ?? 0} running · ${executionKpis?.review_required ?? 0} need review`,
        badge: (executionKpis?.in_progress ?? executionMetrics?.runningRuns ?? 0) > 0 ? "In Progress" : (executionKpis?.total_executions ?? executionMetrics?.totalRuns ?? 0) > 0 ? "Current" : "No Runs",
        badgeVariant: (executionKpis?.in_progress ?? executionMetrics?.runningRuns ?? 0) > 0 ? "purple" : (executionKpis?.total_executions ?? executionMetrics?.totalRuns ?? 0) > 0 ? "success" : "outline",
        icon: Play,
        tone: "bg-violet-50 text-violet-600",
      },
      {
        title: "Evidence",
        value: `${evidenceCoverage}%`,
        suffix: "Test Cases Covered",
        note: `${evidenceReadyCount} with evidence · ${Math.max(0, testCases.length - evidenceReadyCount)} missing`,
        badge: evidenceCoverage === 100 && testCases.length ? "Complete" : testCases.length ? "Incomplete" : "No Test Cases",
        badgeVariant: evidenceCoverage === 100 && testCases.length ? "success" : testCases.length ? "warning" : "outline",
        icon: Shield,
        tone: "bg-emerald-50 text-emerald-600",
      },
    ];
  }, [activeDiscoverySessions, applicationSummary, approvedTestCases, automationReadiness, completedDiscoverySessions, dashboard, evidenceCoverage, evidenceReadyCount, executionKpis, readyAutomationScripts, testCases, automationScripts.length]);

  const lifecycle = useMemo<LifecycleItem[]>(() => {
    const requirementTotal = dashboard?.requirements.total ?? 0;
    const requirementApproved = dashboard?.requirements.approved ?? 0;
    const applicationTotal = applicationSummary?.total_applications ?? 0;
    const applicationReady = applicationSummary?.discovery_ready ?? 0;
    const totalExecutions = executionKpis?.total_executions ?? dashboard?.execution.totalRuns ?? 0;
    const runningExecutions = executionKpis?.in_progress ?? dashboard?.execution.runningRuns ?? 0;

    const requirementState = requirementTotal === 0 ? "empty" : requirementApproved === requirementTotal ? "complete" : "warning";
    const designState = testCases.length === 0 ? "empty" : approvedTestCases === testCases.length ? "complete" : "warning";
    const discoveryState = applicationTotal === 0 ? "empty" : applicationReady === applicationTotal ? "ready" : "warning";
    const automationState = automationScripts.length === 0 ? "empty" : automationReadiness === 100 ? "ready" : "progress";
    const executionState = totalExecutions === 0 ? "empty" : runningExecutions > 0 ? "progress" : "complete";
    const evidenceState = testCases.length === 0 ? "empty" : evidenceCoverage === 100 ? "complete" : "warning";

    return [
      { title: "Requirement Intelligence", status: requirementState === "complete" ? "Complete" : requirementState === "empty" ? "Not Started" : "Needs Review", detail: `${requirementApproved} of ${requirementTotal} approved`, icon: CheckCircle2, ...statusPresentation(requirementState) },
      { title: "Test Design", status: designState === "complete" ? "Complete" : designState === "empty" ? "Not Started" : "Pending Review", detail: `${approvedTestCases} of ${testCases.length} approved`, icon: ClipboardCheck, ...statusPresentation(designState) },
      { title: "Application Discovery", status: discoveryState === "ready" ? "Ready" : discoveryState === "empty" ? "Not Configured" : "Needs Attention", detail: `${applicationReady} of ${applicationTotal} discovery ready`, icon: Search, ...statusPresentation(discoveryState) },
      { title: "Automation Studio", status: automationState === "ready" ? "Ready" : automationState === "empty" ? "Not Started" : "In Progress", detail: `${readyAutomationScripts} of ${automationScripts.length} approved / CI ready`, icon: Sparkles, ...statusPresentation(automationState) },
      { title: "Execution", status: executionState === "complete" ? "Current" : executionState === "empty" ? "Not Started" : "In Progress", detail: `${totalExecutions} runs · ${runningExecutions} active`, icon: Play, ...statusPresentation(executionState) },
      { title: "Evidence & Review", status: evidenceState === "complete" ? "Complete" : evidenceState === "empty" ? "Not Started" : "Incomplete", detail: `${evidenceCoverage}% test-case evidence coverage`, icon: Shield, ...statusPresentation(evidenceState) },
    ];
  }, [applicationSummary, approvedTestCases, automationReadiness, automationScripts.length, dashboard, evidenceCoverage, executionKpis, readyAutomationScripts, testCases.length]);

  const resultDistribution = useMemo(() => {
    const passed = executionKpis?.passed ?? dashboard?.execution.passed ?? 0;
    const failed = executionKpis?.failed ?? dashboard?.execution.failed ?? 0;
    const blocked = executionKpis?.blocked ?? dashboard?.execution.blocked ?? 0;
    const notRun = (executionKpis?.skipped ?? 0) + (dashboard?.execution.notRun ?? 0);
    return [
      { label: "Pass", count: passed, color: "#34d399" },
      { label: "Fail", count: failed, color: "#ef4444" },
      { label: "Blocked", count: blocked, color: "#f59e0b" },
      { label: "Not Run / Skipped", count: notRun, color: "#94a3b8" },
    ];
  }, [dashboard, executionKpis]);
  const resultTotal = resultDistribution.reduce((sum, item) => sum + item.count, 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 bg-white px-1 pb-4">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span>QAI Command Center</span><ChevronRight className="h-3 w-3" /><span className="font-medium text-[#1b59f8]">Command Centre</span>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-slate-400">
            Project
            <select
              aria-label="Command Centre project"
              value={selectedProjectId ?? ""}
              onChange={(event) => {
                const params = new URLSearchParams(searchParams.toString());
                params.set("project", event.target.value);
                router.push(`${pathname}?${params.toString()}`);
              }}
              className="h-9 min-w-[220px] rounded-lg border border-slate-200 bg-white px-3 text-sm normal-case tracking-normal text-slate-900"
            >
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </label>
          {dashboard && (
            <Badge variant={dashboard.jiraSync.isHealthy ? "success" : "warning"} className="gap-1">
              {dashboard.jiraSync.isHealthy ? <CheckCircle2 className="h-3 w-3" /> : <TriangleAlert className="h-3 w-3" />}
              Jira: {dashboard.jiraSync.syncedCount} synced{dashboard.jiraSync.failureCount ? ` · ${dashboard.jiraSync.failureCount} failed` : ""}
            </Badge>
          )}
        </div>
      </div>

      <section className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-50 text-[#1b59f8]"><FileText className="h-6 w-6" /></div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-950">Executive Overview</h1>
            <p className="mt-1 text-sm text-slate-500">Live lifecycle status for {selectedProject?.name || "the selected project"} across requirements, design, discovery, automation, execution and evidence.</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
          <label className="flex items-center gap-2">
            Environment:
            <select aria-label="Execution environment" value={environment} onChange={(event) => setEnvironment(event.target.value)} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900">
              <option value="">All environments</option>
              {availableEnvironments.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2">
            Release:
            <select aria-label="Release version" value={releaseVersion} onChange={(event) => setReleaseVersion(event.target.value)} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900">
              <option value="">All releases</option>
              {releaseOptions.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <span>{lastRefreshed ? `Last refreshed: ${lastRefreshed.toLocaleString()}` : "Not refreshed"}</span>
          <Button variant="outline" size="icon" aria-label="Refresh Command Centre" onClick={() => void loadCommandCentre()} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </section>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div>}

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        {metrics.map((metric) => <MetricCard key={metric.title} item={metric} />)}
      </section>

      <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
        <CardContent className="p-6">
          <h2 className="mb-6 text-sm font-semibold text-slate-950">AAF Lifecycle - Live Operating Domains</h2>
          <div className="flex flex-col gap-5 xl:flex-row xl:items-center">
            {lifecycle.map((item, index) => <LifecycleStep key={item.title} item={item} index={index + 1} last={index === lifecycle.length - 1} />)}
          </div>
        </CardContent>
      </Card>

      <section className="grid gap-4 xl:grid-cols-3">
        <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
          <CardContent className="p-5">
            <h2 className="mb-4 text-sm font-semibold text-slate-950">Readiness &amp; Blockers</h2>
            <ReadinessRow label="Application Environments" value={applicationSummary ? (applicationSummary.environment_gaps ? `${applicationSummary.environment_gaps} gaps` : "Configured") : "Not available"} warning={!applicationSummary || applicationSummary.environment_gaps > 0} />
            <ReadinessRow label="Discovery & App Model" value={applicationSummary ? `${applicationSummary.discovery_ready}/${applicationSummary.total_applications} ready` : "Not available"} warning={!applicationSummary || applicationSummary.discovery_ready < applicationSummary.total_applications} />
            <ReadinessRow label="Automation Approval" value={`${readyAutomationScripts}/${automationScripts.length} ready`} warning={automationScripts.length === 0 || readyAutomationScripts < automationScripts.length} />
            <ReadinessRow label="Mandatory Evidence" value={`${evidenceCoverage}% covered`} warning={testCases.length === 0 || evidenceCoverage < 100} />
            <ReadinessRow label="Agent Run Health" value={failedAgentRuns ? `${failedAgentRuns} failed` : "No failed runs"} warning={failedAgentRuns > 0} />
            <Link className="mt-4 inline-flex text-sm font-medium text-[#1b59f8]" href={projectHref("/applications", selectedProjectId)}>Open readiness sources <ChevronRight className="ml-1 h-4 w-4" /></Link>
          </CardContent>
        </Card>

        <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
          <CardContent className="p-5">
            <h2 className="mb-4 text-sm font-semibold text-slate-950">Work Queue</h2>
            <QueueRow icon={Bell} label="Pending Approvals" count={pendingApprovalCount} variant={pendingApprovalCount ? "warning" : "outline"} />
            <QueueRow icon={Bot} label="Active Agent Runs" count={runningAgentRuns} variant={runningAgentRuns ? "info" : "outline"} />
            <QueueRow icon={PauseCircle} label="Paused / Waiting Runs" count={pausedAgentRuns} variant={pausedAgentRuns ? "warning" : "outline"} />
            <QueueRow icon={XCircle} label="Failed Agent Runs" count={failedAgentRuns} variant={failedAgentRuns ? "destructive" : "outline"} />
            <Link className="mt-4 inline-flex text-sm font-medium text-[#1b59f8]" href={projectHref("/agents/logs", selectedProjectId)}>Open Agent Run Logs <ChevronRight className="ml-1 h-4 w-4" /></Link>
          </CardContent>
        </Card>

        <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
          <CardContent className="p-5">
            <h2 className="mb-4 text-sm font-semibold text-slate-950">Execution &amp; Evidence Summary</h2>
            <div className="flex flex-col items-center gap-5 sm:flex-row">
              <EvidenceRing coverage={evidenceCoverage} results={resultDistribution} />
              <div className="w-full space-y-3 text-sm">
                {resultDistribution.map((item) => (
                  <div key={item.label} className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-slate-600"><span className="h-2 w-2 rounded-full" style={{ background: item.color }} />{item.label}</span>
                    <span className="text-slate-500">{pct(item.count, resultTotal)}% ({item.count})</span>
                  </div>
                ))}
              </div>
            </div>
            <Link className="mt-4 inline-flex text-sm font-medium text-[#1b59f8]" href={projectHref("/execution/dashboard", selectedProjectId)}>Open Execution Dashboard <ChevronRight className="ml-1 h-4 w-4" /></Link>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
          <CardContent className="p-5">
            <h2 className="mb-4 text-sm font-semibold text-slate-950">Recent Activity</h2>
            <div className="divide-y divide-slate-100">
              {(dashboard?.recentActivities || []).map((item, index) => (
                <div key={`${item.action}-${item.subject}-${index}`} className="grid grid-cols-[1fr_auto_auto] items-center gap-4 py-3 text-sm">
                  <span className="min-w-0 truncate text-slate-700">{item.action}: {item.subject}</span>
                  <span className="text-xs text-slate-500">{formatRelativeTime(item.time)}</span>
                  <Badge variant="outline" className="max-w-40 truncate text-[10px]">{item.user}</Badge>
                </div>
              ))}
              {!dashboard?.recentActivities.length && <div className="py-8 text-center text-sm text-slate-400">No project activity is available.</div>}
            </div>
            <Link className="mt-4 inline-flex text-sm font-medium text-[#1b59f8]" href={projectHref("/agents/logs", selectedProjectId)}>View agent run timeline <ChevronRight className="ml-1 h-4 w-4" /></Link>
          </CardContent>
        </Card>

        <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
          <CardContent className="p-5">
            <h2 className="mb-4 text-sm font-semibold text-slate-950">Next Actions</h2>
            <div className="divide-y divide-slate-100">
              <ActionRow label={`Review ${Math.max(0, testCases.length - approvedTestCases)} pending test cases`} href={projectHref("/test-cases?view=approval", selectedProjectId)} button="Open Approvals" />
              <ActionRow label={`${Math.max(0, automationScripts.length - readyAutomationScripts)} automation scripts need readiness`} href={projectHref("/automation", selectedProjectId)} button="Open Automation" />
              <ActionRow label={`Monitor ${executionKpis?.in_progress ?? dashboard?.execution.runningRuns ?? 0} active executions`} href={projectHref("/execution/dashboard", selectedProjectId)} button="Live Execution" />
              <ActionRow label={`Resolve ${Math.max(0, testCases.length - evidenceReadyCount)} evidence gaps`} href={projectHref("/execution/dashboard", selectedProjectId)} button="View Evidence" />
              <ActionRow label={`Review ${dashboard?.requirements.pending ?? 0} pending requirements`} href={projectHref("/requirements?view=review", selectedProjectId)} button="Open Reviews" />
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

export default function ExecutiveOverviewPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading command centre...</div>}>
      <ExecutiveOverviewContent />
    </Suspense>
  );
}
