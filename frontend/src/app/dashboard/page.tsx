"use client";

import { useEffect, useState, useCallback, useMemo, Suspense } from "react";
import Link from "next/link";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  Tooltip as RechartsTooltip, Legend, PieChart, Pie, Cell
} from "recharts";
import {
  FileText, TestTube2, Database, Play, Bug, Bot, ChevronRight,
  AlertTriangle, CheckCircle, RefreshCw, Plus, Sparkles, ChevronDown,
  ArrowUpRight, ShieldCheck, Brain, BookOpen, Zap, Clock, Activity,
  BarChart2, Target, XCircle, TrendingUp, CheckSquare, BarChart3
} from "lucide-react";
import {
  projectsApi, requirementsApi, testCasesApi,
  automationApi, executionApi, defectsApi, agentRunsApi, testPlansApi, testDataApi,
  type Project, type ExecutionRun, type AgentRun, type Requirement,
  type TestCase, type TestDataItem, type TestPlan, type DefectDraft, type DashboardMetrics
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

// ── Helpers ───────────────────────────────────────────────────────────────────
function timestampFromDate(dateString?: string | null): number {
  if (!dateString) return 0;
  const ts = new Date(dateString).getTime();
  return Number.isFinite(ts) ? ts : 0;
}

function formatTimeAgo(dateString?: string | null): string {
  const ts = timestampFromDate(dateString);
  if (!ts) return "Just now";
  const seconds = Math.floor((Date.now() - ts) / 1000);
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// ── Circular Progress Ring ────────────────────────────────────────────────────
function ProgressRing({ radius = 22, stroke = 3, progress = 0, color = "#1b59f8" }: {
  radius?: number; stroke?: number; progress?: number; color?: string;
}) {
  const r = radius - stroke * 2;
  const circ = r * 2 * Math.PI;
  const offset = circ - (Math.min(Math.max(progress, 0), 100) / 100) * circ;
  return (
    <svg height={radius * 2} width={radius * 2} className="transform -rotate-90">
      <circle stroke="#f1f5f9" fill="transparent" strokeWidth={stroke} r={r} cx={radius} cy={radius} />
      <circle
        stroke={color} fill="transparent" strokeWidth={stroke}
        strokeDasharray={`${circ} ${circ}`} style={{ strokeDashoffset: offset }}
        strokeLinecap="round" r={r} cx={radius} cy={radius}
      />
    </svg>
  );
}

// ── Mini inline bar for table cells ──────────────────────────────────────────
function MiniBar({ value, color = "#3b82f6" }: { value: number; color?: string }) {
  return (
    <div className="flex items-center gap-1">
      <span className="text-[10px] font-bold text-slate-700 w-7">{value}%</span>
      <div className="flex-1 h-1 rounded-full bg-slate-100 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${value}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

// ── Sparkline SVG ─────────────────────────────────────────────────────────────
function Sparkline({ data, color = "#8b5cf6" }: { data: number[]; color?: string }) {
  if (data.length < 2) return null;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const w = 72; const h = 28;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * (h - 4) - 2}`).join(" ");
  return (
    <svg width={w} height={h}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ── Quality gate status badge ─────────────────────────────────────────────────
type QualityGateStatus = "Passed" | "Failed" | "Pending";
type AgentStatus = "Active" | "Running" | "Waiting" | "Completed";
type ActionVariant = "high" | "ai" | "warning" | "critical";
type DashboardAction = { title: string; label: string; variant: ActionVariant; href: string };

function GateBadge({ status }: { status: QualityGateStatus }) {
  const map: Record<QualityGateStatus, string> = {
    Passed: "bg-emerald-50 text-emerald-700 border-emerald-200",
    Failed: "bg-red-50 text-red-700 border-red-200",
    Pending: "bg-amber-50 text-amber-700 border-amber-200",
  };
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[9px] font-bold tracking-wide", map[status])}>
      {status}
    </span>
  );
}

// ── Risk badge ────────────────────────────────────────────────────────────────
function RiskBadge({ risk }: { risk: "Low" | "Medium" | "High" | "Critical" }) {
  const map = {
    Low: "bg-emerald-50 text-emerald-700 border-emerald-200",
    Medium: "bg-amber-50 text-amber-700 border-amber-200",
    High: "bg-orange-50 text-orange-700 border-orange-200",
    Critical: "bg-red-50 text-red-700 border-red-200",
  };
  return (
    <span className={cn("inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] font-bold tracking-wide", map[risk])}>
      {risk}
    </span>
  );
}

// ── Agent status pill ─────────────────────────────────────────────────────────
function AgentPill({ status }: { status: AgentStatus }) {
  const map: Record<AgentStatus, string> = {
    Active: "bg-emerald-50 text-emerald-700 border-emerald-200",
    Running: "bg-blue-50 text-blue-700 border-blue-200",
    Waiting: "bg-amber-50 text-amber-700 border-amber-200",
    Completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  };
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[9px] font-bold", map[status])}>
      {status}
    </span>
  );
}

// ── NBA Tile Card (icon-left, title+badge right) ──────────────────────────────
function NBACard({ action, href }: {
  action: DashboardAction;
  href: string;
}) {
  const labelStyle = action.variant === "high"     ? "text-blue-600 bg-blue-50 border-blue-200"
    : action.variant === "ai"       ? "text-violet-600 bg-violet-50 border-violet-200"
    : action.variant === "critical" ? "text-red-600 bg-red-50 border-red-200"
    : "text-slate-500 bg-slate-50 border-slate-200";
  const iconBg = action.variant === "high"     ? "bg-blue-50 border-blue-100 text-blue-500"
    : action.variant === "ai"       ? "bg-violet-50 border-violet-100 text-violet-500"
    : action.variant === "critical" ? "bg-red-50 border-red-100 text-red-500"
    : "bg-slate-50 border-slate-100 text-slate-400";
  const ActionIcon = action.variant === "ai"       ? TestTube2
    : action.variant === "critical"                ? Bug
    : action.href.includes("test-data")            ? Database
    : action.href.includes("execution")            ? Play
    : FileText;
  return (
    <Link href={href}>
      <div className="flex items-start gap-2 p-2.5 rounded-xl border border-slate-100 hover:border-blue-200 hover:bg-blue-50/20 transition-all cursor-pointer group h-full">
        <div className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border mt-0.5", iconBg)}>
          <ActionIcon className="h-3.5 w-3.5" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-semibold text-slate-800 leading-snug group-hover:text-blue-600 transition-colors">
            {action.title}
          </p>
          <span className={cn("inline-flex items-center mt-1 text-[9px] font-bold px-1.5 py-0.5 rounded border", labelStyle)}>
            {action.label}
          </span>
        </div>
      </div>
    </Link>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
function DashboardContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const selectedProjectId = Number(searchParams.get("project")) || null;

  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [testPlans, setTestPlans] = useState<TestPlan[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [testData, setTestData] = useState<TestDataItem[]>([]);
  const [execRuns, setExecRuns] = useState<ExecutionRun[]>([]);
  const [defects, setDefects] = useState<DefectDraft[]>([]);
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [scriptsCount, setScriptsCount] = useState<number>(0);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [newDropdownOpen, setNewDropdownOpen] = useState(false);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  const [activityTab, setActivityTab] = useState<"all" | "human" | "agent">("all");

  useEffect(() => {
    setMounted(true);
    projectsApi.list().then(res => {
      setProjects(res.data);
      if (res.data.length > 0 && !searchParams.get("project")) {
        const params = new URLSearchParams(searchParams.toString());
        params.set("project", String(res.data[0].id));
        router.push(`${pathname}?${params.toString()}`);
      }
    }).catch(() => {});
  }, [searchParams, pathname, router]);

  const loadData = useCallback(async () => {
    if (!selectedProjectId) return;
    setLoading(true);
    try {
      try {
        const metricsRes = await projectsApi.dashboardMetrics(selectedProjectId);
        setMetrics(metricsRes.data);
        setMetricsError(null);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error("Failed to load centralized dashboard metrics", err);
        setMetricsError(msg);
      }
      const [reqRes, planRes, tcRes, dataRes, execRes, defRes, agentRes, autoRes] =
        await Promise.allSettled([
          requirementsApi.list(selectedProjectId),
          testPlansApi.list(selectedProjectId),
          testCasesApi.list(selectedProjectId),
          testDataApi.list(selectedProjectId),
          executionApi.listRuns(selectedProjectId),
          defectsApi.list(selectedProjectId),
          agentRunsApi.list(selectedProjectId, { limit: 100 }),
          automationApi.list(selectedProjectId),
        ]);
      setRequirements(reqRes.status === "fulfilled" ? reqRes.value.data : []);
      setTestPlans(planRes.status === "fulfilled" ? planRes.value.data : []);
      setTestCases(tcRes.status === "fulfilled" ? tcRes.value.data : []);
      setTestData(dataRes.status === "fulfilled" ? dataRes.value.data : []);
      setExecRuns(execRes.status === "fulfilled" ? execRes.value.data : []);
      setDefects(defRes.status === "fulfilled" ? defRes.value.data : []);
      setAgentRuns(agentRes.status === "fulfilled" ? agentRes.value.data : []);
      setScriptsCount(autoRes.status === "fulfilled" ? autoRes.value.data.length : 0);
      setLastUpdated(new Date());
    } catch (e) {
      console.error("Failed to load dashboard data", e);
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId]);

  useEffect(() => { loadData(); }, [loadData]);

  // Virtual runs from localStorage — guarded by `mounted` so server and client
  // initial renders are identical (avoids React hydration mismatch).
  const localVirtualRuns = useMemo<ExecutionRun[]>(() => {
    if (!mounted || !selectedProjectId) return [];
    try {
      const sr = window.localStorage.getItem(`stlc_runs_project_${selectedProjectId}`);
      return sr ? JSON.parse(sr) as ExecutionRun[] : [];
    } catch { return []; }
  }, [mounted, selectedProjectId]);

  const mergedRuns = useMemo(() => {
    const merged = [...execRuns];
    localVirtualRuns.forEach(lRun => {
      if (!merged.some(r => r.id === lRun.id)) merged.push(lRun);
    });
    merged.sort((a, b) =>
      new Date(b.updated_at || b.created_at || 0).getTime() -
      new Date(a.updated_at || a.created_at || 0).getTime()
    );
    return merged;
  }, [execRuns, localVirtualRuns]);

  // ── Core stats ──────────────────────────────────────────────────────────────
  const stats = useMemo(() => {
    if (metrics) {
      const totalRuns = metrics.execution.totalRuns + localVirtualRuns.length;
      const completedRuns = metrics.execution.completedRuns +
        localVirtualRuns.filter(r => (r.status === "completed" || r.status === "passed") && !(r.failed > 0)).length;
      const failedRuns = metrics.execution.failedRuns +
        localVirtualRuns.filter(r => r.status === "failed" || r.failed > 0).length;
      const runningRuns = metrics.execution.runningRuns +
        localVirtualRuns.filter(r => ["running", "pending", "in_progress"].includes(r.status)).length;
      const latestRun = mergedRuns[0];
      const lastPassPct = latestRun && latestRun.total_tests > 0
        ? Math.round((latestRun.passed / latestRun.total_tests) * 100)
        : metrics.execution.passRatePercentage;
      return {
        readinessIndex: metrics.releaseReadiness.score,
        totalReqs: metrics.requirements.total,
        approvedReqs: metrics.requirements.approved,
        pendingReqs: metrics.requirements.pending,
        totalTCs: metrics.testCases.total,
        automatedTCs: metrics.testCases.automated,
        manualTCs: metrics.testCases.manual,
        totalData: metrics.testData.total,
        approvedData: metrics.testData.approved,
        pendingData: metrics.testData.pending,
        totalRuns, completedRuns, failedRuns, runningRuns,
        totalDefects: metrics.defects.total,
        criticalDefects: metrics.defects.critical,
        highDefects: metrics.defects.high,
        mediumDefects: metrics.defects.medium,
        lowDefects: metrics.defects.low,
        autoPct: metrics.testCases.automationCoveragePercentage,
        lastPassPct,
      };
    }
    const totalReqs = requirements.length;
    const approvedReqs = requirements.filter(r => r.status === "approved").length;
    const pendingReqs = requirements.filter(r => r.status === "pending_review" || r.status === "draft").length;
    const totalTCs = testCases.length;
    const automatedTCs = testCases.filter(t => t.mode === "automated" || t.execution_mode === "automated").length;
    const totalData = testData.length;
    const approvedData = testData.filter(d => d.approval_status === "approved").length;
    const totalRuns = mergedRuns.length;
    const completedRuns = mergedRuns.filter(r => (r.status === "completed" || r.status === "passed") && !(r.failed > 0)).length;
    const failedRuns = mergedRuns.filter(r => r.status === "failed" || r.failed > 0).length;
    const runningRuns = mergedRuns.filter(r => ["running", "pending", "in_progress"].includes(r.status)).length;
    const totalDefects = defects.length;
    const criticalDefects = defects.filter(d => d.severity.toLowerCase() === "critical").length;
    const highDefects = defects.filter(d => d.severity.toLowerCase() === "high").length;
    const mediumDefects = defects.filter(d => ["medium", "major"].includes(d.severity.toLowerCase())).length;
    const lowDefects = totalDefects - criticalDefects - highDefects - mediumDefects;
    const autoPct = totalTCs > 0 ? Math.round((automatedTCs / totalTCs) * 100) : 0;
    const latestRun = mergedRuns[0];
    const lastPassPct = latestRun && latestRun.total_tests > 0
      ? Math.round((latestRun.passed / latestRun.total_tests) * 100) : 0;
    const readinessIndex = totalReqs > 0
      ? Math.max(0, Math.min(100, Math.round(
          (approvedReqs / totalReqs) * 40 +
          (totalTCs > 0 ? (automatedTCs / totalTCs) * 20 : 0) +
          (lastPassPct ? lastPassPct * 0.4 : 0) -
          (criticalDefects * 5 + highDefects * 2)
        )))
      : 0;
    return {
      readinessIndex, totalReqs, approvedReqs, pendingReqs,
      totalTCs, automatedTCs, manualTCs: totalTCs - automatedTCs,
      totalData, approvedData, pendingData: totalData - approvedData,
      totalRuns, completedRuns, failedRuns, runningRuns,
      totalDefects, criticalDefects, highDefects, mediumDefects, lowDefects,
      autoPct, lastPassPct,
    };
  }, [metrics, requirements, testCases, testData, defects, localVirtualRuns, mergedRuns]);

  // ── Readiness status ────────────────────────────────────────────────────────
  const readinessInfo = useMemo(() => {
    const score = metrics ? metrics.releaseReadiness.score : stats.readinessIndex;
    const status = metrics
      ? metrics.releaseReadiness.status
      : (stats.criticalDefects > 0 || stats.highDefects > 3 || score < 70) ? "NO-GO"
        : score >= 85 ? "GO" : "AT-RISK";
    return {
      score,
      status,
      barColor: status === "GO" ? "bg-emerald-500" : status === "AT-RISK" ? "bg-amber-500" : "bg-red-500",
    };
  }, [metrics, stats]);

  // ── Jira sync stats ─────────────────────────────────────────────────────────
  const jiraStats = useMemo(() => {
    if (metrics) return {
      syncedCount: metrics.jiraSync.syncedCount,
      failureCount: metrics.jiraSync.failureCount,
      conflictCount: metrics.jiraSync.conflictCount,
      isHealthy: metrics.jiraSync.isHealthy,
    };
    const reqSynced = requirements.filter(r => !!r.jira_issue_key).length;
    const tcSynced = testCases.filter(t => t.jira_sync_status === "synced").length;
    const failureCount = testCases.filter(t => t.jira_sync_status === "failed").length;
    const conflictCount = testCases.filter(t => t.jira_sync_status === "conflict").length;
    return { syncedCount: reqSynced + tcSynced, failureCount, conflictCount, isHealthy: failureCount === 0 && conflictCount === 0 };
  }, [metrics, requirements, testCases]);

  // ── STLC Pipeline with risk meta ────────────────────────────────────────────
  const pipelineSteps = useMemo(() => {
    if (metrics) return metrics.pipelineOverview;
    const reqsWithTC = new Set(testCases.map(t => t.requirement_id).filter(Boolean)).size;
    const executedTests = mergedRuns
      .filter(r => r.status === "completed" || r.status === "passed")
      .reduce((s, r) => s + (r.passed || 0) + (r.failed || 0), 0);
    const reqRate = stats.totalReqs > 0 ? Math.round((stats.approvedReqs / stats.totalReqs) * 100) : 0;
    const planRate = testPlans.length > 0 ? Math.round((testPlans.filter(p => p.status === "approved").length / testPlans.length) * 100) : 0;
    const tcRate = stats.totalReqs > 0 ? Math.round((reqsWithTC / stats.totalReqs) * 100) : 0;
    const dataRate = stats.totalData > 0 ? Math.round((stats.approvedData / stats.totalData) * 100) : 0;
    const autoRate = stats.totalTCs > 0 ? Math.round((stats.automatedTCs / stats.totalTCs) * 100) : 0;
    const execRate = stats.totalTCs > 0 ? Math.round((executedTests / stats.totalTCs) * 100) : 0;
    return [
      { label: "Requirements", current: stats.approvedReqs, total: stats.totalReqs, rate: reqRate, color: "#10b981" },
      { label: "Test Planning", current: testPlans.filter(p => p.status === "approved").length, total: testPlans.length, rate: planRate, color: "#3b82f6" },
      { label: "Test Cases", current: reqsWithTC, total: stats.totalReqs, rate: tcRate, color: "#8b5cf6" },
      { label: "Test Data", current: stats.approvedData, total: stats.totalData, rate: dataRate, color: "#06b6d4" },
      { label: "Automation", current: scriptsCount, total: stats.totalTCs, rate: autoRate, color: "#f59e0b" },
      { label: "Execution", current: executedTests, total: stats.totalTCs, rate: execRate, color: "#3b82f6" },
      { label: "Defects", current: stats.totalDefects, total: stats.totalDefects, rate: stats.totalDefects > 0 ? Math.max(0, 100 - stats.criticalDefects * 10) : 100, color: "#ef4444", isDefects: true },
      { label: "Reports", current: 0, total: 0, rate: 0, color: "#10b981" },
    ];
  }, [metrics, stats, testPlans, testCases, mergedRuns, scriptsCount]);

  const pipelineWithMeta = useMemo(() => {
    return pipelineSteps.map(step => {
      type Risk = "Low" | "Medium" | "High" | "Critical";
      let risk: Risk = "Low";
      let note = "";
      const s = step as typeof step & { isDefects?: boolean };
      if (s.label === "Requirements") {
        risk = s.rate >= 80 ? "Low" : s.rate >= 50 ? "Medium" : "High";
        note = stats.pendingReqs > 0 ? `${stats.pendingReqs} pending approval` : "All approved";
      } else if (s.label === "Test Planning") {
        risk = s.rate === 100 ? "Low" : s.rate >= 70 ? "Medium" : "High";
        note = s.rate === 100 ? "Complete" : `${Math.max(0, s.total - s.current)} pending`;
      } else if (s.label === "Test Cases") {
        risk = s.rate >= 70 ? "Medium" : "High";
        const pendingTC = testCases.filter(t => t.status === "draft" || t.approval_status === "pending").length;
        note = pendingTC > 0 ? `${pendingTC} pending review` : "All reviewed";
      } else if (s.label === "Test Data") {
        risk = s.total === 0 ? "Medium" : s.rate >= 80 ? "Low" : "Medium";
        note = s.total === 0 ? "0 synthetic data" : `${Math.max(0, s.total - s.current)} pending`;
      } else if (s.label === "Automation") {
        risk = s.rate >= 80 ? "Medium" : s.rate >= 60 ? "Medium" : "High";
        const pending = Math.max(0, (s.total || 0) - (s.current || 0));
        note = pending > 0 ? `${pending} pending scripts` : "All scripted";
      } else if (s.label === "Execution") {
        risk = s.rate >= 80 ? "Low" : "High";
        const notExec = Math.max(0, (s.total || 0) - (s.current || 0));
        note = notExec > 0 ? `${notExec} not executed` : "All executed";
      } else if (s.isDefects) {
        risk = stats.criticalDefects > 0 ? "Critical" : stats.highDefects > 2 ? "High" : "Medium";
        note = stats.criticalDefects > 0 ? `${stats.criticalDefects} critical` : "No critical defects";
      } else if (s.label === "Reports") {
        risk = "Low";
        note = s.current === 0 ? "Reports not generated" : `${s.current} generated`;
      }
      return { ...step, risk, note };
    });
  }, [pipelineSteps, stats, testCases]);

  // ── Execution trend chart data ───────────────────────────────────────────────
  const chartData = useMemo(() => {
    if (metrics) {
      return metrics.executionTrend.map(d => ({
        name: d.name,
        Passed: (d as { name: string; Passed: number; Failed: number; InProgress?: number; Blocked?: number }).Passed,
        Failed: (d as { name: string; Passed: number; Failed: number; InProgress?: number; Blocked?: number }).Failed,
        Blocked: (d as { name: string; Passed: number; Failed: number; InProgress?: number; Blocked?: number }).Blocked ??
          (d as { name: string; Passed: number; Failed: number; InProgress?: number; Blocked?: number }).InProgress ?? 0,
      }));
    }
    if (execRuns.length === 0) return [];
    return execRuns.slice(0, 7).reverse().map(run => ({
      name: run.execution_id.split("-")[1] || run.execution_id,
      Passed: run.passed,
      Failed: run.failed,
      Blocked: run.status === "running" ? Math.max(0, run.total_tests - run.passed - run.failed) : 0,
    }));
  }, [metrics, execRuns]);

  // ── Defect donut chart data ──────────────────────────────────────────────────
  const defectChartData = useMemo(() => {
    if (metrics) return metrics.defectChartData;
    return [
      { name: "Critical", value: stats.criticalDefects, color: "#ef4444" },
      { name: "High", value: stats.highDefects, color: "#f97316" },
      { name: "Medium", value: stats.mediumDefects, color: "#eab308" },
      { name: "Low", value: stats.lowDefects, color: "#10b981" },
    ].filter(d => d.value > 0 || stats.totalDefects === 0);
  }, [metrics, stats]);

  // ── Defect aging (from real defects or mock) ────────────────────────────────
  const defectAging = useMemo(() => {
    const now = Date.now();
    const buckets = [
      { label: "0-2 days",  max: 2,  color: "#10b981" },
      { label: "3-7 days",  max: 7,  color: "#3b82f6" },
      { label: "8-15 days", max: 15, color: "#f59e0b" },
      { label: ">15 days",  max: Infinity, color: "#ef4444" },
    ];
    const total = defects.length || 1;
    return buckets.map((b, index) => {
      const min = index === 0 ? 0 : buckets[index - 1].max;
      const count = defects.filter(d => {
        const age = (now - new Date(d.created_at).getTime()) / 86400000;
        return age >= min && age <= b.max;
      }).length;
      return { label: b.label, count, pct: Math.round((count / total) * 100), color: b.color };
    });
  }, [defects]);

  // ── Agent activity (real or mock) ────────────────────────────────────────────
  const agentActivity = useMemo(() => {
    const labelMap: Record<string, string> = {
      requirement_intake: "Requirement Analyst Agent",
      requirement_quality: "Quality Analysis Agent",
      test_planning: "Test Planning Agent",
      test_scenario: "Test Scenarios Agent",
      test_case: "Test Case Generator Agent",
      automation_script: "Automation Script Agent",
      test_execution: "Test Execution Agent",
      defect_analysis: "Defect Triage Agent",
      test_reporting: "Report Agent",
    };
    return agentRuns.slice(0, 5).map(run => ({
      name: labelMap[run.agent_name] || run.agent_name,
      status: (run.status === "completed" ? "Completed"
        : run.status === "running" ? "Running"
        : run.status === "pending" ? "Waiting"
        : "Active") as AgentStatus,
      detail: run.progress_message || `Executed ${run.agent_name}`,
      time: formatTimeAgo(run.created_at),
    }));
  }, [agentRuns]);

  // ── Pending approvals ────────────────────────────────────────────────────────
  const pendingApprovals = useMemo(() => {
    if (metrics) return metrics.pendingApprovals;
    const now = Date.now();
    const list: Array<{ title: string; subtitle: string; count: number; priority: string; priorityColor: string }> = [];
    const addItem = (
      items: Array<{ created_at: string; [key: string]: unknown }>,
      title: string,
      priority: string,
      keyFn: (i: unknown) => string
    ) => {
      if (!items.length) return;
      const oldest = items.reduce((a, b) => new Date(a.created_at) < new Date(b.created_at) ? a : b);
      const age = ((now - new Date(oldest.created_at).getTime()) / 86400000).toFixed(1);
      const breach = Number(age) > 2;
      list.push({
        title,
        subtitle: `Oldest: ${keyFn(oldest)} (${age}d pending)${breach ? " ⚠️ SLA Breach" : ""}`,
        count: items.length,
        priority: breach ? "SLA Breach" : priority,
        priorityColor: breach ? "text-red-600 bg-red-50 border-red-100" : "text-amber-600 bg-amber-50 border-amber-100",
      });
    };
    addItem(requirements.filter(r => r.status === "pending_review") as never[], "Requirement Approval Needed", "High Priority", (i) => (i as Requirement).requirement_id || `REQ-${(i as Requirement).id}`);
    addItem(testCases.filter(t => t.status === "draft" || t.approval_status === "pending") as never[], "Test Case Verification Review", "Medium Priority", (i) => (i as TestCase).test_case_id || `TC-${(i as TestCase).id}`);
    addItem(defects.filter(d => d.status === "draft" || d.status === "pending_review") as never[], "Defect Triage Approval", "High Priority", (i) => (i as DefectDraft).defect_id || `DEF-${(i as DefectDraft).id}`);
    if (!list.length) list.push({ title: "Test Suite Signoff & Approval", subtitle: "Release sprint package ready", count: 0, priority: "Clear", priorityColor: "text-emerald-600 bg-emerald-50 border-emerald-100" });
    return list.slice(0, 3);
  }, [metrics, requirements, testCases, defects]);

  // ── Recent activities ────────────────────────────────────────────────────────
  const recentActivities = useMemo(() => {
    type ActivityItem = { user: string; action: string; subject: string; time: string; timestamp: number; isAgent: boolean };
    if (metrics) {
      return (metrics.recentActivities ?? []).map(act => ({
        user: act.user, action: act.action, subject: act.subject,
        time: act.time ? formatTimeAgo(act.time) : "Just now",
        timestamp: timestampFromDate(act.time), isAgent: (act as any).is_agent ?? false,
      }));
    }
    const activities: ActivityItem[] = [];
    requirements.slice(0, 2).forEach(r => activities.push({ user: "System", action: `updated requirement ${r.requirement_id}`, subject: r.title, time: formatTimeAgo(r.updated_at), timestamp: timestampFromDate(r.updated_at), isAgent: false }));
    testCases.slice(0, 1).forEach(tc => activities.push({ user: "System", action: `updated test case ${tc.test_case_id}`, subject: tc.title, time: formatTimeAgo(tc.updated_at), timestamp: timestampFromDate(tc.updated_at), isAgent: false }));
    defects.slice(0, 1).forEach(d => activities.push({ user: "System", action: `logged defect ${d.defect_id || ""}`, subject: d.summary, time: formatTimeAgo(d.created_at), timestamp: timestampFromDate(d.created_at), isAgent: false }));
    agentRuns.slice(0, 2).forEach(r => activities.push({ user: "AI Agent", action: r.progress_message || `Completed ${r.agent_name}`, subject: "", time: formatTimeAgo(r.created_at), timestamp: timestampFromDate(r.created_at), isAgent: true }));
    return activities.sort((a, b) => b.timestamp - a.timestamp).slice(0, 6);
  }, [metrics, requirements, testCases, defects, agentRuns]);

  const filteredActivities = useMemo(() => {
    if (activityTab === "human") return recentActivities.filter(a => !a.isAgent);
    if (activityTab === "agent") return recentActivities.filter(a => a.isAgent);
    return recentActivities;
  }, [recentActivities, activityTab]);

  // ── Critical blockers summary ────────────────────────────────────────────────
  const criticalBlockers = useMemo(() => {
    const hcDefects = stats.criticalDefects + stats.highDefects;
    const pendingApprovalCount = pendingApprovals.filter(p => p.count > 0).length;
    const testDataGaps = stats.totalData === 0 ? 1 : 0;
    const total = (stats.criticalDefects > 0 ? 1 : 0) + (pendingApprovalCount > 0 ? 1 : 0) +
      (testDataGaps > 0 ? 1 : 0) + (stats.pendingReqs > 10 ? 1 : 0) + (stats.autoPct < 50 ? 1 : 0);
    return { total, hcDefects, pendingApprovalCount, testDataGaps };
  }, [stats, pendingApprovals]);

  // ── Domain quality matrix (merge real passRate into mock if available) ──────
  const traceability = useMemo(() => {
    const linkedRequirementIds = new Set(testCases.map(tc => tc.requirement_id ?? tc.linked_requirement_id).filter((id): id is number => Boolean(id)));
    const automated = testCases.filter(tc => Boolean(tc.automation_script_id) || tc.automation_status === "automated" || tc.execution_mode === "automation" || tc.execution_mode === "automated").length;
    const defectsWithRequirement = defects.filter(defect => {
      const tc = testCases.find(item => item.id === defect.test_case_id);
      return Boolean(tc?.requirement_id ?? tc?.linked_requirement_id);
    }).length;
    return {
      reqToTC: stats.totalReqs ? Math.round((linkedRequirementIds.size / stats.totalReqs) * 100) : 0,
      tcToAutomation: stats.totalTCs ? Math.round((automated / stats.totalTCs) * 100) : 0,
      defectsToReq: stats.totalDefects ? Math.round((defectsWithRequirement / stats.totalDefects) * 100) : 0,
      uncoveredRequirements: Math.max(0, stats.totalReqs - linkedRequirementIds.size),
      orphanTestCases: testCases.filter(tc => !(tc.requirement_id ?? tc.linked_requirement_id)).length,
    };
  }, [testCases, defects, stats]);

  const qualityGates = useMemo<Array<{ name: string; status: QualityGateStatus }>>(() => {
    const gate = (hasItems: boolean, passed: boolean): QualityGateStatus => !hasItems ? "Pending" : passed ? "Passed" : "Failed";
    return [
      { name: "Requirement Approval", status: gate(stats.totalReqs > 0, stats.pendingReqs === 0) },
      { name: "Automation Readiness", status: gate(stats.totalTCs > 0, stats.autoPct >= 80) },
      { name: "Test Planning", status: gate(testPlans.length > 0, testPlans.every(plan => plan.status === "approved")) },
      { name: "Execution Readiness", status: gate(stats.totalRuns > 0, stats.failedRuns === 0 && stats.runningRuns === 0) },
      { name: "Test Case Review", status: gate(stats.totalTCs > 0, testCases.every(tc => tc.approval_status === "approved" || tc.status === "approved")) },
      { name: "Defect Closure", status: gate(stats.totalDefects > 0, stats.criticalDefects === 0 && stats.highDefects === 0) },
      { name: "Test Data Readiness", status: gate(stats.totalData > 0, stats.pendingData === 0) },
      { name: "Release Report", status: gate((metrics?.reports.total ?? 0) > 0, (metrics?.reports.published ?? 0) > 0) },
    ];
  }, [stats, testPlans, testCases, metrics]);

  const nextBestActions = useMemo<DashboardAction[]>(() => [
    { title: `Approve ${stats.pendingReqs} requirements`, label: stats.pendingReqs ? "High impact" : "No pending items", variant: "high", href: "/requirements" },
    { title: `Review ${testCases.filter(tc => tc.status === "draft" || tc.approval_status === "pending").length} test cases`, label: "Review queue", variant: "ai", href: "/test-cases" },
    { title: stats.totalData ? `Review ${stats.pendingData} test data sets` : "Generate synthetic test data", label: stats.totalData ? "Data readiness" : "No data available", variant: "warning", href: "/test-data" },
    { title: `Triage ${stats.criticalDefects + stats.highDefects} high/critical defects`, label: "Release risk", variant: "critical", href: "/defects" },
    { title: `Monitor ${stats.runningRuns} active executions`, label: `${stats.failedRuns} failed runs`, variant: "warning", href: "/execution/dashboard" },
  ], [stats, testCases]);

  const aiQuality = useMemo(() => {
    const scored = requirements.map(req => req.quality_score).filter((score): score is number => typeof score === "number");
    return {
      confidence: scored.length ? Math.round(scored.reduce((sum, score) => sum + score, 0) / scored.length) : null,
      sparkline: scored.slice(-7),
      ambiguity: stats.totalReqs ? Math.round((requirements.filter(req => (req.missing_information?.length ?? 0) > 0).length / stats.totalReqs) * 100) : 0,
      coverageGaps: 100 - traceability.reqToTC,
      defectRisk: stats.totalDefects ? Math.round(((stats.criticalDefects + stats.highDefects) / stats.totalDefects) * 100) : 0,
    };
  }, [requirements, stats, traceability]);

  const agentStats = useMemo(() => {
    const today = new Date().toDateString();
    const todayRuns = agentRuns.filter(run => new Date(run.created_at).toDateString() === today);
    return { actionsToday: todayRuns.length, runtimeHours: todayRuns.reduce((sum, run) => sum + (run.duration_seconds ?? 0), 0) / 3600 };
  }, [agentRuns]);

  const domainMatrix = useMemo(() => {
    const domains = new Map<string, { requirements: Requirement[]; testCases: TestCase[]; defects: DefectDraft[] }>();
    const entryFor = (domain: string) => domains.get(domain) ?? { requirements: [], testCases: [], defects: [] };
    requirements.forEach(req => {
      const domain = req.telecom_domain || "Unspecified";
      const entry = entryFor(domain); entry.requirements.push(req); domains.set(domain, entry);
    });
    testCases.forEach(tc => {
      const domain = tc.telecom_domain || "Unspecified";
      const entry = entryFor(domain); entry.testCases.push(tc); domains.set(domain, entry);
    });
    defects.forEach(defect => {
      const domain = testCases.find(item => item.id === defect.test_case_id)?.telecom_domain || "Unspecified";
      const entry = entryFor(domain); entry.defects.push(defect); domains.set(domain, entry);
    });
    return Array.from(domains.entries()).map(([domain, rows]) => {
      const linkedReqs = new Set(rows.testCases.map(tc => tc.requirement_id ?? tc.linked_requirement_id).filter(Boolean)).size;
      const automated = rows.testCases.filter(tc => Boolean(tc.automation_script_id) || tc.automation_status === "automated").length;
      const passed = rows.testCases.filter(tc => tc.last_automation_status === "passed").length;
      const risk = rows.defects.some(d => d.severity.toLowerCase() === "critical") ? "High" : rows.defects.length > 2 ? "Medium" : "Low";
      return {
        domain,
        reqCoverage: rows.requirements.length ? Math.round((rows.requirements.filter(req => req.status === "approved").length / rows.requirements.length) * 100) : 0,
        tcCoverage: rows.requirements.length ? Math.round((linkedReqs / rows.requirements.length) * 100) : 0,
        automation: rows.testCases.length ? Math.round((automated / rows.testCases.length) * 100) : 0,
        passRate: rows.testCases.length ? Math.round((passed / rows.testCases.length) * 100) : 0,
        openDefects: rows.defects.length,
        risk: risk as "Low" | "Medium" | "High",
      };
    });
  }, [requirements, testCases, defects]);

  // ── project link helper ──────────────────────────────────────────────────────
  const projectLink = (href: string) =>
    selectedProjectId ? `${href}?project=${selectedProjectId}` : href;

  // ─────────────────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-5 pb-10 select-none">

      {/* ── Page Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-indigo-500" />
            STLC Command Center
          </h1>
          <p className="text-[11px] text-slate-400 mt-0.5">AI-powered quality engineering lifecycle overview</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-400 font-mono hidden sm:block">
            {mounted ? `Updated ${lastUpdated.toLocaleTimeString()}` : ""}
          </span>
          <Button variant="outline" size="sm" onClick={loadData} disabled={loading} className="h-8 w-8 p-0 border-slate-200">
            <RefreshCw className={cn("h-3.5 w-3.5 text-slate-500", loading && "animate-spin")} />
          </Button>
          <div className="relative">
            <Button variant="default" size="sm" className="h-8 font-semibold gap-1" onClick={() => setNewDropdownOpen(!newDropdownOpen)}>
              <Plus className="h-3.5 w-3.5" /> New <ChevronDown className="h-3 w-3" />
            </Button>
            {newDropdownOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setNewDropdownOpen(false)} />
                <div className="absolute right-0 mt-1.5 w-44 rounded-xl border border-slate-200 bg-white py-1 shadow-lg z-20">
                  {[["Create Project", "/projects"], ["Add Test Case", projectLink("/test-cases")], ["Draft Test Plan", projectLink("/test-planning")]].map(([label, href]) => (
                    <Link key={href} href={href} className="block px-4 py-2 text-xs text-slate-700 hover:bg-slate-50" onClick={() => setNewDropdownOpen(false)}>{label}</Link>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {metricsError && (
        <div className="p-3 bg-amber-50 border border-amber-100 text-amber-700 rounded-xl text-xs flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>Metrics endpoint unavailable — showing computed values. {metricsError}</span>
        </div>
      )}

      {/* ── Row 1: 5 Executive KPI Cards ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">

        {/* 1. Release Readiness */}
        <Card className="border-slate-200 xl:col-span-1">
          <CardHeader className="p-4 pb-2 flex flex-row items-start justify-between space-y-0">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Release Readiness</span>
            {readinessInfo.status === "GO"
              ? <CheckCircle className="h-4 w-4 text-emerald-500" />
              : <AlertTriangle className="h-4 w-4 text-red-500 animate-pulse" />
            }
          </CardHeader>
          <CardContent className="p-4 pt-1">
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-2xl font-bold text-slate-900">{readinessInfo.score}%</span>
              <span className={cn(
                "text-[10px] font-bold px-2 py-0.5 rounded-full",
                readinessInfo.status === "GO" ? "bg-emerald-600 text-white"
                  : readinessInfo.status === "AT-RISK" ? "bg-amber-500 text-white"
                  : "bg-red-600 text-white"
              )}>{readinessInfo.status}</span>
            </div>
            <div className="w-full bg-slate-100 h-1.5 rounded-full mt-2.5 overflow-hidden">
              <div className={cn("h-full rounded-full transition-all", readinessInfo.barColor)} style={{ width: `${readinessInfo.score}%` }} />
            </div>
            <p className="text-[10px] text-slate-400 mt-1.5">Target: 85%</p>
            <div className="mt-3 space-y-1.5 border-t border-slate-50 pt-2.5">
              {stats.pendingReqs > 0 && (
                <div className="flex items-center gap-1.5 text-[10px] text-slate-600">
                  <FileText className="h-3 w-3 text-amber-500 shrink-0" />
                  <span>{stats.pendingReqs} pending requirements</span>
                </div>
              )}
              {stats.totalDefects > 0 && (
                <div className="flex items-center gap-1.5 text-[10px] text-slate-600">
                  <Bug className="h-3 w-3 text-red-500 shrink-0" />
                  <span>{stats.totalDefects} open defects</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* 2. AI Quality Intelligence */}
        <Card className="border-slate-200 ai-glow-card xl:col-span-1">
          <CardHeader className="p-4 pb-2 flex flex-row items-start justify-between space-y-0">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">AI Quality Intelligence</span>
            <Brain className="h-4 w-4 text-violet-500" />
          </CardHeader>
          <CardContent className="p-4 pt-1">
            <div className="flex items-end justify-between">
              <div>
                <div className="flex items-center gap-1.5 text-[9px] text-violet-500 font-semibold mb-0.5">
                  <Bot className="h-3 w-3" /> AI Confidence
                </div>
                <span className="text-2xl font-bold text-violet-600">{aiQuality.confidence === null ? "—" : `${aiQuality.confidence}%`}</span>
              </div>
              <Sparkline data={aiQuality.sparkline} />
            </div>
            <div className="mt-3 space-y-1.5 border-t border-slate-50 pt-2.5">
              {[
                { label: "Ambiguity", value: aiQuality.ambiguity, level: aiQuality.ambiguity >= 30 ? "High" : aiQuality.ambiguity > 0 ? "Medium" : "Low" },
                { label: "Coverage Gaps", value: aiQuality.coverageGaps, level: aiQuality.coverageGaps >= 30 ? "High" : aiQuality.coverageGaps > 0 ? "Medium" : "Low" },
                { label: "Defect Pred. Risk", value: aiQuality.defectRisk, level: aiQuality.defectRisk >= 30 ? "High" : aiQuality.defectRisk > 0 ? "Medium" : "Low" },
              ].map(m => (
                <div key={m.label} className="flex items-center justify-between text-[10px]">
                  <span className="text-slate-500">{m.label}</span>
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-slate-700">{m.value}%</span>
                    <span className={cn("font-semibold", m.level === "High" ? "text-red-500" : "text-amber-500")}>
                      ● {m.level}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* 3. RAG Knowledge Health */}
        <Card className="border-slate-200 xl:col-span-1">
          <CardHeader className="p-4 pb-2 flex flex-row items-start justify-between space-y-0">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">RAG Knowledge Health</span>
            <span className="text-[9px] font-bold px-2 py-0.5 rounded border border-teal-200 bg-teal-50 text-teal-700">RAG</span>
          </CardHeader>
          <CardContent className="p-4 pt-1">
            <div className="grid grid-cols-3 gap-2 mt-1">
              {[
                { label: "Docs Indexed", value: "—" },
                { label: "Jira Stories", value: "—" },
                { label: "Chunks", value: "—" },
              ].map(m => (
                <div key={m.label} className="text-center">
                  <div className="text-base font-bold text-slate-800">{m.value}</div>
                  <div className="text-[9px] text-slate-400 leading-tight mt-0.5">{m.label}</div>
                </div>
              ))}
            </div>
            <div className="mt-3 border-t border-slate-50 pt-2.5 space-y-1.5">
              <div className="flex items-center justify-between text-[10px]">
                <span className="text-slate-500">Retrieval Accuracy</span>
                <span className="font-bold text-slate-700">—</span>
              </div>
              <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                <div className="h-full rounded-full bg-slate-300" style={{ width: "0%" }} />
              </div>
              <div className="flex items-center gap-1.5 mt-1">
                <AlertTriangle className="h-3.5 w-3.5 text-slate-400" />
                <span className="text-[10px] font-semibold text-slate-500">Metrics unavailable</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 4. Jira Sync Health */}
        <Card className="border-slate-200 xl:col-span-1">
          <CardHeader className="p-4 pb-2 flex flex-row items-start justify-between space-y-0">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Jira Sync Health</span>
            <span className="text-[9px] font-bold px-2 py-0.5 rounded border border-blue-200 bg-blue-50 text-blue-700">Jira</span>
          </CardHeader>
          <CardContent className="p-4 pt-1">
            <div className="flex items-center gap-1.5 mt-1">
              <div className={cn("h-2 w-2 rounded-full", jiraStats.isHealthy ? "bg-emerald-500 animate-pulse" : "bg-red-500")} />
              <span className="text-xs font-semibold text-slate-700">
                {jiraStats.isHealthy ? "Synced just now" : "Sync issues detected"}
              </span>
            </div>
            <div className={cn("text-[10px] font-semibold mt-0.5", jiraStats.isHealthy ? "text-emerald-600" : "text-red-500")}>
              {jiraStats.isHealthy ? "Healthy" : `${jiraStats.failureCount} failures`}
            </div>
            <div className="grid grid-cols-3 gap-1 mt-3 pt-2.5 border-t border-slate-50 text-center">
              {[
                { label: "Synced Issues", value: jiraStats.syncedCount, color: "text-slate-800" },
                { label: "Sync Failures", value: jiraStats.failureCount, color: jiraStats.failureCount > 0 ? "text-red-600" : "text-slate-800" },
                { label: "Conflicts", value: jiraStats.conflictCount, color: jiraStats.conflictCount > 0 ? "text-amber-500" : "text-slate-800" },
              ].map(m => (
                <div key={m.label}>
                  <div className={cn("text-base font-bold", m.color)}>{m.value}</div>
                  <div className="text-[9px] text-slate-400 leading-tight mt-0.5">{m.label}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* 5. Critical Blockers */}
        <Card className="border-red-100 bg-red-50/30 xl:col-span-1">
          <CardHeader className="p-4 pb-2 flex flex-row items-start justify-between space-y-0">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Critical Blockers</span>
            <AlertTriangle className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent className="p-4 pt-1">
            <div className="text-2xl font-bold text-red-600 mt-1">{criticalBlockers.total}</div>
            <div className="text-[10px] font-semibold text-red-400 mb-3">Release Blockers</div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[10px]">
                <div className="flex items-center gap-1.5 text-slate-600">
                  <XCircle className="h-3 w-3 text-red-500" />
                  <span>High/Critical Defects</span>
                </div>
                <span className="font-bold text-slate-800">{criticalBlockers.hcDefects}</span>
              </div>
              <div className="flex items-center justify-between text-[10px]">
                <div className="flex items-center gap-1.5 text-slate-600">
                  <Clock className="h-3 w-3 text-amber-500" />
                  <span>Pending Approvals</span>
                </div>
                <span className="font-bold text-slate-800">{criticalBlockers.pendingApprovalCount}</span>
              </div>
              <div className="flex items-center justify-between text-[10px]">
                <div className="flex items-center gap-1.5 text-slate-600">
                  <Database className="h-3 w-3 text-slate-400" />
                  <span>Test Data Gaps</span>
                </div>
                <span className="font-bold text-slate-800">{criticalBlockers.testDataGaps}</span>
              </div>
            </div>
            <Link href={projectLink("/defects")} className="mt-3 flex items-center gap-1 text-[10px] font-semibold text-red-600 hover:underline">
              View All Blockers <ArrowUpRight className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* ── Row 2: Next Best Actions + STLC Pipeline with Risk Overlay ──────── */}
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-5">

        {/* Next Best Actions */}
        <Card className="xl:col-span-2 border-slate-200">
          <CardHeader className="p-5 pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <CardTitle className="text-sm font-semibold">Next Best Actions</CardTitle>
              <span className="text-[9px] font-bold px-2 py-0.5 rounded-full border border-violet-200 bg-violet-50 text-violet-700 flex items-center gap-1">
                <Bot className="h-2.5 w-2.5" /> AI
              </span>
            </div>
            <CardDescription className="text-[10px] mt-0.5">Recommended actions to improve release readiness</CardDescription>
          </CardHeader>
          <CardContent className="p-4 pt-3 flex flex-col gap-2">
            {/* Row 1: 3 equal tiles */}
            <div className="grid grid-cols-3 gap-2">
              {nextBestActions.slice(0, 3).map(action => (
                <NBACard key={action.title} action={action} href={projectLink(action.href)} />
              ))}
            </div>
            {/* Row 2: 2 wider tiles — each spans half the panel width */}
            <div className="grid grid-cols-2 gap-2">
              {nextBestActions.slice(3).map(action => (
                <NBACard key={action.title} action={action} href={projectLink(action.href)} />
              ))}
            </div>
          </CardContent>
        </Card>

        {/* STLC Pipeline with Risk Overlay */}
        <Card className="xl:col-span-3 border-slate-200">
          <CardHeader className="p-5 pb-3 border-b border-slate-100 flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-sm font-semibold">STLC Pipeline with Risk Overlay</CardTitle>
              <CardDescription className="text-[10px] mt-0.5">Overall progress and risk by lifecycle stage</CardDescription>
            </div>
            <Link href={projectLink("/reports")}>
              <Button variant="outline" size="sm" className="h-7 text-[10px] border-slate-200 gap-1">
                <BarChart3 className="h-3 w-3" /> Report
              </Button>
            </Link>
          </CardHeader>
          <CardContent className="p-4 pt-3">
            <div className="flex items-start justify-between gap-1 overflow-x-auto no-scrollbar">
              {pipelineWithMeta.map((step, idx) => (
                <div key={step.label} className="flex items-center flex-1 min-w-0">
                  {/* Stage node */}
                  <div className="flex flex-col items-center text-center flex-1 min-w-[58px]">
                    <div className="relative flex items-center justify-center">
                      <ProgressRing progress={step.rate} color={step.color} radius={22} stroke={2.5} />
                      <span className="absolute text-[8px] font-bold text-slate-800">{step.rate}%</span>
                    </div>
                    <span className="text-[9px] font-bold text-slate-800 mt-1 leading-tight">{step.label}</span>
                    <span className="text-[8px] text-slate-400 mt-0.5 leading-tight">
                      {(step as typeof step & { isDefects?: boolean }).isDefects
                        ? `${step.current} Open` : `${step.current} / ${step.total}`}
                    </span>
                    <p className="text-[8px] text-slate-500 mt-0.5 leading-tight px-0.5">{step.note}</p>
                    <div className="mt-1">
                      <RiskBadge risk={step.risk as "Low" | "Medium" | "High" | "Critical"} />
                    </div>
                  </div>
                  {/* Arrow connector */}
                  {idx < pipelineWithMeta.length - 1 && (
                    <ChevronRight className="h-3.5 w-3.5 text-slate-300 shrink-0 mx-0.5" />
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Row 3: Quality Gates + Traceability + Domain Matrix ──────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* Quality Gates */}
        <Card className="border-slate-200">
          <CardHeader className="p-5 pb-3 border-b border-slate-100">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-blue-500" /> Quality Gates
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <div className="grid grid-cols-2 gap-2">
              {qualityGates.map(gate => (
                <div key={gate.name} className="flex items-center justify-between gap-2 p-2 rounded-lg bg-slate-50 border border-slate-100">
                  <span className="text-[10px] font-medium text-slate-700 truncate">{gate.name}</span>
                  <GateBadge status={gate.status} />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Traceability Health */}
        <Card className="border-slate-200">
          <CardHeader className="p-5 pb-3 border-b border-slate-100">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Activity className="h-4 w-4 text-teal-500" /> Traceability Health
            </CardTitle>
          </CardHeader>
          <CardContent className="p-5">
            <div className="space-y-4">
              {[
                { label: "Requirements mapped to Test Cases", value: traceability.reqToTC, color: "#ef4444" },
                { label: "Test Cases mapped to Automation", value: traceability.tcToAutomation, color: "#10b981" },
                { label: "Defects mapped to Requirements", value: traceability.defectsToReq, color: "#f59e0b" },
              ].map(m => (
                <div key={m.label}>
                  <div className="flex items-center justify-between text-[10px] mb-1">
                    <span className="text-slate-600">{m.label}</span>
                    <span className="font-bold text-slate-800">{m.value}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${m.value}%`, backgroundColor: m.color }} />
                  </div>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-3 mt-5 pt-4 border-t border-slate-50">
              <div className="text-center p-2 rounded-lg bg-red-50 border border-red-100">
                <div className="text-lg font-bold text-red-600">{traceability.uncoveredRequirements}</div>
                <div className="text-[9px] text-red-400 font-medium mt-0.5">Uncovered Requirements</div>
              </div>
              <div className="text-center p-2 rounded-lg bg-amber-50 border border-amber-100">
                <div className="text-lg font-bold text-amber-600">{traceability.orphanTestCases}</div>
                <div className="text-[9px] text-amber-400 font-medium mt-0.5">Orphan Test Cases</div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Domain Quality Matrix */}
        <Card className="border-slate-200">
          <CardHeader className="p-5 pb-3 border-b border-slate-100">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <BarChart2 className="h-4 w-4 text-indigo-500" /> Domain Quality Matrix
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="border-b border-slate-100">
                    {["Domain", "Req %", "TC %", "Auto %", "Pass %", "Bugs", "Risk"].map(h => (
                      <th key={h} className="px-3 py-2 text-left font-semibold text-slate-400 whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {domainMatrix.map((row, i) => (
                    <tr key={row.domain} className={cn("border-b border-slate-50 hover:bg-slate-50", i % 2 === 0 ? "" : "bg-slate-50/30")}>
                      <td className="px-3 py-2 font-semibold text-slate-700 whitespace-nowrap">{row.domain}</td>
                      <td className="px-3 py-2 w-16"><MiniBar value={row.reqCoverage} color="#3b82f6" /></td>
                      <td className="px-3 py-2 w-16"><MiniBar value={row.tcCoverage} color="#8b5cf6" /></td>
                      <td className="px-3 py-2 w-16"><MiniBar value={row.automation} color="#06b6d4" /></td>
                      <td className="px-3 py-2 w-16"><MiniBar value={row.passRate} color="#10b981" /></td>
                      <td className="px-3 py-2 font-bold text-slate-700 text-center">{row.openDefects}</td>
                      <td className="px-3 py-2"><RiskBadge risk={row.risk} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Row 4: Execution Trend + Defect Intelligence + AI Agent Status ───── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* Execution Trend */}
        <Card className="border-slate-200">
          <CardHeader className="p-5 pb-3 flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-sm font-semibold">Execution Trend</CardTitle>
              <CardDescription className="text-[10px]">Test outcomes over the last 14 days</CardDescription>
            </div>
            <select className="border border-slate-200 rounded-lg text-[10px] font-semibold px-2 py-1 text-slate-500 focus:outline-none">
              <option>Last 14 Days</option>
              <option>Last 30 Days</option>
            </select>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gPassed" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gFailed" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#ef4444" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gBlocked" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#94a3b8" stopOpacity={0.12} />
                      <stop offset="95%" stopColor="#94a3b8" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="name" stroke="#94a3b8" fontSize={9} tickLine={false} axisLine={false} />
                  <YAxis stroke="#94a3b8" fontSize={9} tickLine={false} axisLine={false} />
                  <RechartsTooltip contentStyle={{ fontSize: "11px", borderRadius: "8px", border: "1px solid #e2e8f0" }} />
                  <Legend iconSize={8} wrapperStyle={{ fontSize: "10px", paddingTop: "8px" }} />
                  <Area type="monotone" dataKey="Passed" stroke="#10b981" fill="url(#gPassed)" strokeWidth={2} dot={{ r: 2.5 }} />
                  <Area type="monotone" dataKey="Failed" stroke="#ef4444" fill="url(#gFailed)" strokeWidth={2} dot={{ r: 2.5 }} />
                  <Area type="monotone" dataKey="Blocked" stroke="#94a3b8" fill="url(#gBlocked)" strokeWidth={1.5} strokeDasharray="4 2" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Defect Intelligence */}
        <Card className="border-slate-200">
          <CardHeader className="p-5 pb-3 border-b border-slate-100">
            <CardTitle className="text-sm font-semibold">Defect Intelligence</CardTitle>
            <CardDescription className="text-[10px]">Active defect severity and aging</CardDescription>
          </CardHeader>
          <CardContent className="p-4">
            <div className="flex items-center gap-4">
              {/* Donut */}
              <div className="relative shrink-0" style={{ width: 90, height: 90 }}>
                <ResponsiveContainer width={90} height={90}>
                  <PieChart>
                    <Pie data={defectChartData.length ? defectChartData : [{ name: "None", value: 1, color: "#f1f5f9" }]}
                      cx="50%" cy="50%" innerRadius={28} outerRadius={42} paddingAngle={2} dataKey="value">
                      {(defectChartData.length ? defectChartData : [{ color: "#f1f5f9" }]).map((e, i) => (
                        <Cell key={i} fill={e.color} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-lg font-bold text-slate-800">{stats.totalDefects}</span>
                  <span className="text-[8px] text-slate-400 uppercase font-semibold">Total</span>
                </div>
              </div>
              {/* Legend */}
              <div className="flex-1 space-y-1.5">
                {defectChartData.map(d => (
                  <div key={d.name} className="flex items-center justify-between text-[10px]">
                    <div className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: d.color }} />
                      <span className="text-slate-600">{d.name}</span>
                    </div>
                    <span className="font-bold text-slate-700">
                      {d.value} ({stats.totalDefects > 0 ? Math.round((d.value / stats.totalDefects) * 100) : 0}%)
                    </span>
                  </div>
                ))}
              </div>
            </div>
            {/* Defect Aging */}
            <div className="mt-4 pt-3 border-t border-slate-50">
              <p className="text-[10px] font-semibold text-slate-500 mb-2">Defect Aging</p>
              <div className="space-y-1.5">
                {defectAging.map(b => (
                  <div key={b.label} className="flex items-center gap-2 text-[10px]">
                    <span className="w-14 text-slate-500 shrink-0">{b.label}</span>
                    <div className="flex-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${b.pct}%`, backgroundColor: b.color }} />
                    </div>
                    <span className="w-6 font-bold text-slate-700 text-right">{b.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* AI Agent Status */}
        <Card className="border-slate-200 ai-glow-card">
          <CardHeader className="p-5 pb-3 border-b border-slate-100">
            <div className="flex items-start justify-between">
              <div>
                <CardTitle className="text-sm font-semibold">AI Agent Status</CardTitle>
                <CardDescription className="text-[10px] mt-0.5">Live autonomous engineering agents</CardDescription>
              </div>
              <div className="text-right">
                <div className="text-[10px] font-bold text-violet-600">
                  <span className="text-base text-slate-800">{agentStats.actionsToday}</span> AI actions today
                </div>
                <div className="text-[10px] font-semibold text-emerald-600 mt-0.5">
                  <Zap className="inline h-2.5 w-2.5" /> {agentStats.runtimeHours.toFixed(1)} hrs runtime
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-4">
            <div className="space-y-3">
              {agentActivity.map((agent, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-50 border border-indigo-100">
                    <Bot className="h-3.5 w-3.5 text-indigo-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[11px] font-semibold text-slate-800 truncate">{agent.name}</p>
                      <span className="text-[9px] text-slate-400 shrink-0">{agent.time}</span>
                    </div>
                    <p className="text-[10px] text-slate-500 truncate mt-0.5">{agent.detail}</p>
                  </div>
                  <AgentPill status={agent.status} />
                </div>
              ))}
            </div>
            <div className="mt-4 pt-3 border-t border-slate-50">
              <Link href={projectLink("/agents")} className="text-[11px] font-semibold text-[#1b59f8] hover:underline flex items-center gap-1">
                View All Agent Runs <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Row 5: Pending Approvals + Recent Activity ───────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* Pending Approvals */}
        <Card className="border-slate-200">
          <CardHeader className="p-5 pb-3 border-b border-slate-100 flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-sm font-semibold">Pending Approvals</CardTitle>
              <CardDescription className="text-[10px]">Quality gate authorization requests</CardDescription>
            </div>
            <Badge variant="warning" className="text-[9px] font-bold">{pendingApprovals.reduce((s, a) => s + (a.count > 0 ? 1 : 0), 0)}</Badge>
          </CardHeader>
          <CardContent className="p-4">
            <div className="space-y-3">
              {pendingApprovals.map((item, i) => (
                <div key={i} className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-2.5 min-w-0">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-50 border border-slate-200">
                      <FileText className="h-3.5 w-3.5 text-slate-500" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-[11px] font-bold text-slate-800 truncate">{item.title}</p>
                      <p className="text-[10px] text-slate-500 mt-0.5 truncate">{item.subtitle}</p>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span className="text-sm font-bold text-slate-700">{item.count}</span>
                    <span className={cn("text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border", item.priorityColor)}>
                      {item.priority.split(" ")[0]}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 pt-3 border-t border-slate-50">
              <Link href={projectLink("/requirements")} className="text-[11px] font-semibold text-[#1b59f8] hover:underline flex items-center gap-1">
                View All Approvals <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Recent Activity */}
        <Card className="lg:col-span-2 border-slate-200">
          <CardHeader className="p-5 pb-0 border-b border-slate-100">
            <div className="flex items-center justify-between mb-3">
              <div>
                <CardTitle className="text-sm font-semibold">Recent Activity</CardTitle>
                <CardDescription className="text-[10px] mt-0.5">QA lifecycle audit log</CardDescription>
              </div>
              <Link href={projectLink("/dashboard")} className="text-[10px] font-semibold text-[#1b59f8] hover:underline flex items-center gap-1">
                View All <ArrowUpRight className="h-3 w-3" />
              </Link>
            </div>
            {/* Tabs */}
            <div className="flex gap-0">
              {(["all", "human", "agent"] as const).map(tab => (
                <button
                  key={tab}
                  onClick={() => setActivityTab(tab)}
                  className={cn(
                    "px-4 py-2 text-[10px] font-semibold border-b-2 capitalize transition-colors",
                    activityTab === tab
                      ? "border-[#1b59f8] text-[#1b59f8]"
                      : "border-transparent text-slate-400 hover:text-slate-600"
                  )}
                >{tab === "all" ? "All" : tab === "human" ? "Human" : "Agent"}</button>
              ))}
            </div>
          </CardHeader>
          <CardContent className="p-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {filteredActivities.slice(0, 4).map((act, i) => (
                <div key={i} className="flex items-start gap-3 p-2.5 rounded-xl border border-slate-50 hover:bg-slate-50 transition-colors">
                  <div className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs font-bold",
                    act.isAgent ? "bg-violet-50 border-violet-200 text-violet-600" : "bg-slate-100 border-slate-200 text-slate-600"
                  )}>
                    {act.isAgent ? <Bot className="h-3.5 w-3.5" /> : act.user.split(" ").map(n => n[0]).join("")}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-1">
                      <p className="text-[11px] font-semibold text-slate-800 leading-tight">
                        {act.isAgent ? "AI Agent" : act.user}
                      </p>
                      <span className="text-[9px] text-slate-400 shrink-0">{act.time}</span>
                    </div>
                    <p className="text-[10px] text-slate-500 mt-0.5 line-clamp-2">
                      {act.action}{act.subject ? ` — ${act.subject}` : ""}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-xs text-slate-500 font-semibold">Loading Command Center...</div>}>
      <DashboardContent />
    </Suspense>
  );
}
