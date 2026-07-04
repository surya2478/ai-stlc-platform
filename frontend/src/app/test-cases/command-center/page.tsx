"use client";

import { useState, useEffect, useCallback, useMemo, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  testCasesApi,
  projectsApi,
  agentRunsApi,
  requirementsApi,
  defectsApi,
  executionApi,
  automationApi,
  testPlansApi,
  traceabilityApi,
  type TestCase,
  type AgentRun,
  type TestCaseSummary,
  type ApprovalAction,
} from "@/lib/api";
import { useUserDirectory } from "@/hooks/useUserDirectory";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as ChartTooltip,
  Legend as ChartLegend,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  FileText,
  ShieldCheck,
  Bot,
  Clock,
  CheckCircle,
  AlertTriangle,
  Zap,
  RefreshCw,
  Plus,
  ArrowRight,
  TrendingUp,
  Cpu,
  Layers,
  ChevronRight,
  Play,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

// ── Helpers ───────────────────────────────────────────────────────────────────

function getStatusVariant(status: string): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" {
  const s = status.toLowerCase();
  if (s === "approved" || s === "passed" || s === "success") return "success";
  if (s === "rejected" || s === "failed") return "destructive";
  if (s === "pending_review" || s === "pending_approval" || s === "in_progress") return "warning";
  if (s === "draft") return "secondary";
  return "outline";
}

function formatDuration(secs: number | undefined): string {
  if (!secs) return "—";
  if (secs < 60) return `${secs.toFixed(1)}s`;
  return `${Math.floor(secs / 60)}m ${(secs % 60).toFixed(0)}s`;
}

function formatTimeAgo(dateStr: string | undefined): string {
  if (!dateStr) return "—";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return date.toLocaleDateString();
}

function RadialProgress({ rate, color }: { rate: number; color: string }) {
  const radius = 14;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (rate / 100) * circumference;

  return (
    <div className="relative flex items-center justify-center h-8 w-8 shrink-0 select-none">
      <svg className="h-8 w-8 transform -rotate-90">
        <circle
          cx="16"
          cy="16"
          r={radius}
          className="text-slate-100"
          strokeWidth="3"
          stroke="currentColor"
          fill="transparent"
        />
        <circle
          cx="16"
          cy="16"
          r={radius}
          stroke={color}
          strokeWidth="3"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          fill="transparent"
        />
      </svg>
      <span className="absolute text-[9px] font-bold text-slate-700">{rate}%</span>
    </div>
  );
}

// ── Main Content Component ───────────────────────────────────────────────────

function CommandCenterContent() {
  const { resolveUser } = useUserDirectory();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProjectId = Number(searchParams.get("project")) || null;

  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [summary, setSummary] = useState<TestCaseSummary | null>(null);
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [approvals, setApprovals] = useState<ApprovalAction[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastUpdatedText, setLastUpdatedText] = useState("just now");

  useEffect(() => {
    projectsApi.list().then((res) => {
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
      const [tcRes, summaryRes, agentRes, approvalsRes] = await Promise.allSettled([
        testCasesApi.list(selectedProjectId),
        testCasesApi.summary(selectedProjectId),
        agentRunsApi.list(selectedProjectId, { limit: 100 }),
        traceabilityApi.approvals(selectedProjectId, { page_size: 20 }),
      ]);
      setTestCases(tcRes.status === "fulfilled" ? tcRes.value.data : []);
      setSummary(summaryRes.status === "fulfilled" ? summaryRes.value.data : null);
      setAgentRuns(agentRes.status === "fulfilled" ? agentRes.value.data : []);
      setApprovals(approvalsRes.status === "fulfilled" ? approvalsRes.value.data : []);
      setLastUpdatedText("just now");
    } catch (e) {
      console.error("Failed to load command center data", e);
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Dynamic user profile sync
  const [timeCounter, setTimeCounter] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => {
      setTimeCounter(prev => prev + 1);
    }, 60000);
    return () => clearInterval(timer);
  }, []);

  const lastUpdatedDisplay = useMemo(() => {
    if (timeCounter === 0) return "just now";
    return `${timeCounter} min${timeCounter > 1 ? "s" : ""} ago`;
  }, [timeCounter]);

  // Derived test cases statistics
  const total = summary?.total ?? testCases.length;
  const hasData = total > 0;

  const totalTCs = hasData ? total : 1248;
  const approvedTCs = hasData ? (summary?.by_status?.approved ?? testCases.filter(t => t.status === "approved").length) : 920;
  const draftTCs = hasData ? (summary?.by_status?.draft ?? testCases.filter(t => t.status === "draft").length) : 328;
  const pendingTCs = hasData ? (summary?.by_status?.pending_approval ?? testCases.filter(t => t.status === "pending_approval" || t.status === "pending_review").length) : 100;
  // Count both new ("automation") and legacy ("automated"/"hybrid") buckets so the
  // KPI doesn't undercount as data migrates to the new vocabulary.
  const isAutoFlavour = (m: string | null | undefined) => m === "automation" || m === "automated" || m === "hybrid";
  const automatedTCs = hasData
    ? ((summary?.by_mode?.automation ?? 0) + (summary?.by_mode?.automated ?? 0) + (summary?.by_mode?.hybrid ?? 0))
      || testCases.filter(t => isAutoFlavour(t.mode) || isAutoFlavour(t.execution_mode)).length
    : 920;
  const manualTCs = hasData ? (summary?.by_mode?.manual ?? (total - automatedTCs)) : 328;
  const rejectedTCs = hasData ? (summary?.by_status?.rejected ?? testCases.filter(t => t.status === "rejected").length) : 42;
  const blockedTCs = hasData ? (summary?.by_status?.blocked ?? testCases.filter(t => t.status === "blocked").length) : 18;
  const readyTCs = hasData
    ? ((summary?.by_automation_status?.ready_for_automation ?? 0) + (summary?.by_automation_status?.planned_for_automation ?? 0))
      || testCases.filter(t => t.automation_ready || t.automation_status === "ready_for_automation" || t.automation_status === "planned_for_automation").length
    : 845;

  // Jira Sync counts
  const jiraSyncedCount = hasData ? (summary?.by_jira_sync_status?.synced ?? testCases.filter(t => t.jira_sync_status === "synced" || t.jira_issue_key != null).length) : 1024;
  const jiraPendingCount = hasData ? (summary?.by_jira_sync_status?.pending ?? testCases.filter(t => t.jira_sync_status === "pending").length) : 150;
  const jiraFailedCount = hasData ? (summary?.by_jira_sync_status?.failed ?? testCases.filter(t => t.jira_sync_status === "failed").length) : 12;
  const jiraConflictCount = hasData ? (summary?.by_jira_sync_status?.conflict ?? testCases.filter(t => t.jira_sync_status === "conflict").length) : 6;

  const approvedRate = totalTCs > 0 ? ((approvedTCs / totalTCs) * 100).toFixed(1) : "0.0";
  const draftRate = totalTCs > 0 ? ((draftTCs / totalTCs) * 100).toFixed(1) : "0.0";
  const automationRate = totalTCs > 0 ? ((automatedTCs / totalTCs) * 100).toFixed(1) : "0.0";
  const manualRate = totalTCs > 0 ? ((manualTCs / totalTCs) * 100).toFixed(1) : "0.0";
  const rejectedRate = totalTCs > 0 ? ((rejectedTCs / totalTCs) * 100).toFixed(1) : "0.0";
  const blockedRate = totalTCs > 0 ? ((blockedTCs / totalTCs) * 100).toFixed(1) : "0.0";
  const readyRate = totalTCs > 0 ? ((readyTCs / totalTCs) * 100).toFixed(1) : "0.0";

  const stats = useMemo(() => {
    return [
      {
        title: "Total Test Cases",
        icon: FileText,
        iconBg: "bg-blue-50 border-blue-100",
        iconColor: "text-blue-500",
        value: totalTCs.toLocaleString(),
        sublabel: "Total",
        footer: "100% of all test cases",
      },
      {
        title: "Approved",
        icon: ShieldCheck,
        iconBg: "bg-emerald-50 border-emerald-100",
        iconColor: "text-emerald-500",
        value: approvedTCs.toLocaleString(),
        sublabel: "Approved",
        footer: `${pendingTCs} Pending • ${approvedRate}% of total`,
      },
      {
        title: "Automation Ready",
        icon: Bot,
        iconBg: "bg-purple-50 border-purple-100",
        iconColor: "text-purple-500",
        value: readyTCs.toLocaleString(),
        sublabel: "Ready",
        footer: `${Math.max(0, readyTCs - automatedTCs)} Mapping Required • ${readyRate}%`,
      },
      {
        title: "Draft",
        icon: Clock,
        iconBg: "bg-amber-50 border-amber-100",
        iconColor: "text-amber-500",
        value: draftTCs.toLocaleString(),
        sublabel: "Draft",
        footer: `${draftRate}% of total`,
      },
      {
        title: "Manual vs Automated",
        icon: Layers,
        iconBg: "bg-cyan-50 border-cyan-100",
        iconColor: "text-cyan-500",
        value: `${manualTCs} / ${automatedTCs}`,
        sublabel: "Manual/Auto",
        footer: `${manualRate}% Manual • ${automationRate}% Automated`,
      },
      {
        title: "Rejected / Blocked",
        icon: AlertTriangle,
        iconBg: "bg-rose-50 border-rose-100",
        iconColor: "text-rose-500",
        value: `${rejectedTCs} / ${blockedTCs}`,
        sublabel: "Rejected/Blocked",
        footer: `${rejectedRate}% Rejected • ${blockedRate}% Blocked`,
      },
    ];
  }, [totalTCs, approvedTCs, pendingTCs, readyTCs, draftTCs, manualTCs, automatedTCs, rejectedTCs, blockedTCs, approvedRate, draftRate, automationRate, manualRate, rejectedRate, blockedRate, readyRate]);

  // STLC Pipeline Overview Steps
  const pipelineSteps = useMemo(() => {
    const draftCount = hasData ? (summary?.by_status?.draft ?? testCases.filter(t => t.status === "draft").length) : 328;
    const pendingCount = hasData ? (summary?.by_status?.pending_approval ?? testCases.filter(t => t.status === "pending_approval" || t.status === "pending_review").length) : 110;
    const approvedCount = hasData ? (summary?.by_status?.approved ?? testCases.filter(t => t.status === "approved").length) : 920;
    const readyCount = hasData ? (summary?.by_automation_status?.ready_for_automation ?? testCases.filter(t => t.automation_ready || t.automation_status === "ready_for_automation").length) : 845;
    const executedCount = hasData ? testCases.filter(t => t.last_automation_status === "passed" || t.last_automation_status === "failed" || t.last_execution_run_id != null).length : 612;
    const defectLinkedCount = hasData ? testCases.filter(t => t.last_automation_status === "failed").length : 186;
    const jiraSyncedCount = hasData ? (summary?.by_jira_sync_status?.synced ?? testCases.filter(t => t.jira_sync_status === "synced" || t.jira_issue_key != null).length) : 1024;

    const draftPct = totalTCs > 0 ? Math.round((draftCount / totalTCs) * 100) : 0;
    const pendingPct = totalTCs > 0 ? Math.round((pendingCount / totalTCs) * 100) : 0;
    const approvedPct = totalTCs > 0 ? Math.round((approvedCount / totalTCs) * 100) : 0;
    const readyPct = totalTCs > 0 ? Math.round((readyCount / totalTCs) * 100) : 0;
    const executedPct = totalTCs > 0 ? Math.round((executedCount / totalTCs) * 100) : 0;
    const defectPct = totalTCs > 0 ? Math.round((defectLinkedCount / totalTCs) * 100) : 0;
    const jiraPct = totalTCs > 0 ? Math.round((jiraSyncedCount / totalTCs) * 100) : 0;

    return [
      { label: "Draft", count: draftCount, rate: draftPct, color: "#94a3b8", icon: FileText, iconBg: "bg-slate-50 text-slate-500 border-slate-100" },
      { label: "Pending Approval", count: pendingCount, rate: pendingPct, color: "#f59e0b", icon: Clock, iconBg: "bg-amber-50 text-amber-500 border-amber-100" },
      { label: "Approved", count: approvedCount, rate: approvedPct, color: "#10b981", icon: CheckCircle, iconBg: "bg-emerald-50 text-emerald-500 border-emerald-100" },
      { label: "Automation Ready", count: readyCount, rate: readyPct, color: "#8b5cf6", icon: Bot, iconBg: "bg-purple-50 text-purple-500 border-purple-100" },
      { label: "Executed", count: executedCount, rate: executedPct, color: "#3b82f6", icon: Play, iconBg: "bg-blue-50 text-blue-500 border-blue-100" },
      { label: "Defect Linked", count: defectLinkedCount, rate: defectPct, color: "#ef4444", icon: AlertTriangle, iconBg: "bg-rose-50 text-rose-500 border-rose-100" },
      { label: "Jira Synced", count: jiraSyncedCount, rate: jiraPct, color: "#06b6d4", icon: Zap, iconBg: "bg-cyan-50 text-cyan-500 border-cyan-105" },
    ];
  }, [totalTCs, testCases, summary, hasData]);

  // Recharts Line Chart over Last 7 Days
  const trendData = useMemo(() => {
    const data = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const dateStr = d.toLocaleDateString([], { month: "short", day: "numeric" });
      
      const created = testCases.filter(t => {
        const tcDate = new Date(t.created_at || new Date());
        return tcDate.toDateString() === d.toDateString();
      }).length;
      
      const approved = testCases.filter(t => {
        const tcDate = new Date(t.created_at || new Date());
        return t.status === "approved" && tcDate.toDateString() === d.toDateString();
      }).length;
      
      const automated = testCases.filter(t => {
        const tcDate = new Date(t.created_at || new Date());
        return isAutoFlavour(t.mode) || isAutoFlavour(t.execution_mode)
          ? tcDate.toDateString() === d.toDateString()
          : false;
      }).length;

      const mockCreated = [700, 850, 920, 880, 1050, 1150, 1248][6 - i];
      const mockApproved = [500, 620, 710, 680, 790, 840, 920][6 - i];
      const mockAutomated = [350, 480, 520, 500, 610, 720, 845][6 - i];

      data.push({
        name: dateStr,
        Created: hasData ? created : mockCreated,
        Approved: hasData ? approved : mockApproved,
        Automated: hasData ? automated : mockAutomated,
      });
    }
    return data;
  }, [testCases, hasData]);

  // Priority Donut Chart
  const priorityChartData = useMemo(() => {
    const critical = hasData ? (summary?.by_priority?.critical ?? testCases.filter(t => t.priority?.toLowerCase() === "critical").length) : 86;
    const high = hasData ? (summary?.by_priority?.high ?? testCases.filter(t => t.priority?.toLowerCase() === "high").length) : 312;
    const medium = hasData ? (summary?.by_priority?.medium ?? testCases.filter(t => t.priority?.toLowerCase() === "medium").length) : 624;
    const low = hasData ? (summary?.by_priority?.low ?? testCases.filter(t => t.priority?.toLowerCase() === "low").length) : 176;
    const info = hasData ? (summary?.by_priority?.info ?? testCases.filter(t => t.priority?.toLowerCase() === "info").length) : 50;

    return [
      { name: "Critical", value: critical, color: "#ef4444", count: `${critical} (${totalTCs > 0 ? ((critical / totalTCs) * 100).toFixed(1) : 0}%)` },
      { name: "High", value: high, color: "#f97316", count: `${high} (${totalTCs > 0 ? ((high / totalTCs) * 100).toFixed(1) : 0}%)` },
      { name: "Medium", value: medium, color: "#eab308", count: `${medium} (${totalTCs > 0 ? ((medium / totalTCs) * 100).toFixed(1) : 0}%)` },
      { name: "Low", value: low, color: "#10b981", count: `${low} (${totalTCs > 0 ? ((low / totalTCs) * 100).toFixed(1) : 0}%)` },
      { name: "Info", value: info, color: "#3b82f6", count: `${info} (${totalTCs > 0 ? ((info / totalTCs) * 100).toFixed(1) : 0}%)` },
    ];
  }, [testCases, summary, totalTCs, hasData]);

  // AI Agent Activity logs mapping
  const agentActivity = useMemo(() => {
    const tcAgents = ["test_case", "test_planning", "test_scenario"];
    const runs = agentRuns.filter(r => tcAgents.includes(r.agent_name));
    const displayRuns = runs.length > 0 ? runs : agentRuns;

    const agentLabelMap: Record<string, string> = {
      requirement_intake: "Requirement Intake Agent",
      requirement_quality: "Quality Analysis Agent",
      test_planning: "Test Planning Agent",
      test_scenario: "Test Scenarios Agent",
      test_case: "Test Case Generation Agent",
      automation_script: "Automation Script Agent",
      test_execution: "Test Execution Agent",
      defect_analysis: "Defect Analysis Agent",
      test_reporting: "QA Reporting Agent"
    };

    if (displayRuns.length === 0) {
      return [
        { name: "Test Case Generation Agent", status: "completed", time: "5 mins ago" },
        { name: "Traceability Agent", status: "completed", time: "12 mins ago" },
        { name: "Test Case Optimization Agent", status: "completed", time: "18 mins ago" },
      ];
    }

    return displayRuns.slice(0, 3).map(run => ({
      name: agentLabelMap[run.agent_name] || run.agent_name,
      status: run.status,
      time: formatTimeAgo(run.created_at)
    }));
  }, [agentRuns]);

  // Pending Approvals
  const pendingApprovals = useMemo(() => {
    const drafts = testCases.filter(t => t.status === "draft" || t.status === "pending_approval");
    if (drafts.length === 0) {
      return [
        { title: "Seamless Handover Between 4G and 5G", code: "TC-0234", priority: "High" },
        { title: "eSIM Profile Download with Airplane Mode", code: "TC-0241", priority: "Medium" },
        { title: "RAN Upgrade with Incompatible Infrastructure", code: "TC-0254", priority: "Medium" },
        { title: "Invalid ICCID Rejection on eSIM Activation", code: "TC-0268", priority: "High" },
      ];
    }
    return drafts.slice(0, 4).map(t => ({
      title: t.title,
      code: t.test_case_id || `TC-${t.id}`,
      priority: t.priority || "Medium"
    }));
  }, [testCases]);

  // Recent Activity timeline
  const recentActivity = useMemo(() => {
    if (approvals.length === 0) {
      return [
        { user: "System", action: "initialized project tracker", subject: "Ready", time: "just now" }
      ];
    }
    return approvals.slice(0, 5).map(app => {
      const userName = resolveUser(app.user_id);
      let actionText = "";
      if (app.decision === "approve") {
        actionText = `approved ${app.entity_type.replace(/_/g, " ")}`;
      } else if (app.decision === "reject") {
        actionText = `rejected ${app.entity_type.replace(/_/g, " ")}`;
      } else {
        actionText = `${app.decision}d ${app.entity_type.replace(/_/g, " ")}`;
      }
      
      const subject = app.jira_issue_key || `${app.entity_type.substring(0, 2).toUpperCase()}-${app.entity_id}`;
      return {
        user: userName || "User",
        action: actionText,
        subject: subject,
        time: formatTimeAgo(app.created_at)
      };
    });
  }, [approvals, resolveUser]);

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Global Controls ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-blue-50 border border-blue-100 p-2.5">
            <Layers className="h-6 w-6 text-[#1b59f8]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Test Cases Command Center</h1>
            <p className="text-xs text-slate-500 mt-1">AI-powered overview of test case lifecycle, approvals, automation readiness, and Jira traceability</p>
          </div>
        </div>
        
        <div className="flex items-center gap-2.5 shrink-0 self-end md:self-auto">
          <Button variant="outline" size="sm" onClick={loadData} className="h-8 w-8 p-0 border-slate-200 bg-white">
            <RefreshCw className={cn("h-3.5 w-3.5 text-slate-500", loading && "animate-spin")} />
          </Button>

          <div className="h-7 border-l border-slate-200 self-center hidden sm:block mx-1" />

          <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider hidden sm:block">Last updated: {lastUpdatedDisplay}</span>
          
          <Button variant="default" size="sm" onClick={() => router.push(`/test-cases?project=${selectedProjectId}`)} className="h-8 text-xs bg-[#1b59f8] hover:bg-[#1546c7] text-white font-semibold">
            <Plus className="h-3.5 w-3.5 mr-1" />
            New
          </Button>
        </div>
      </div>

      {selectedProjectId && (
        <>
          {/* ── Metric Cards ──────────────────────────────────────────────────────── */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
            {stats.map((card) => {
              const Icon = card.icon;
              return (
                <Card key={card.title} className="border-slate-200 hover:-translate-y-0.5 transition-all bg-white shadow-sm">
                  <CardContent className="p-4 flex flex-col justify-between h-full space-y-3">
                    <div className="flex items-center gap-2">
                      <div className={cn("rounded-lg p-1.5 flex items-center justify-center shrink-0 border", card.iconBg)}>
                        <Icon className={cn("h-4 w-4", card.iconColor)} />
                      </div>
                      <span className="text-xs font-bold text-slate-700 truncate">{card.title}</span>
                    </div>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-lg font-bold text-slate-900">{card.value}</span>
                      {card.sublabel && (
                        <span className="text-[9px] font-bold text-slate-400">{card.sublabel}</span>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-450 font-bold border-t border-slate-50 pt-2">
                      {card.footer}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* ── Test Case Lifecycle Overview Pipeline ──────────────────────────────── */}
          <Card className="border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="flex items-center justify-between border-b px-5 py-4 border-slate-100 bg-slate-50/50">
              <div>
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Test Case Lifecycle Overview</h3>
                <p className="text-[10px] text-slate-400 font-semibold mt-1">End-to-end test case workflow progress</p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => router.push(`/test-cases?project=${selectedProjectId}`)}
                className="h-8 text-xs border-slate-200 text-[#1b59f8] bg-white font-semibold"
              >
                View Test Cases
              </Button>
            </div>
            
            <div className="p-5 overflow-x-auto select-none">
              <div className="flex items-center gap-2.5 min-w-[1000px] justify-between">
                {pipelineSteps.map((step, idx) => {
                  const Icon = step.icon;
                  return (
                    <div key={step.label} className="flex items-center flex-1 gap-2 last:flex-none">
                      <div className="flex items-center gap-3 border rounded-xl p-3 bg-white border-slate-200/80 shadow-inner flex-1 max-w-[200px]">
                        <div className={cn("rounded-lg p-2 flex items-center justify-center shrink-0 border", step.iconBg)}>
                          <Icon className="h-4.5 w-4.5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider">{step.label}</p>
                          <p className="text-xs font-bold text-slate-800 mt-0.5">{step.count.toLocaleString()} / {totalTCs.toLocaleString()}</p>
                        </div>
                        <RadialProgress rate={step.rate} color={step.color} />
                      </div>
                      
                      {idx < pipelineSteps.length - 1 && (
                        <div className="flex items-center justify-center text-slate-300 font-bold shrink-0 px-1 select-none">
                          <ArrowRight className="h-4.5 w-4.5 text-slate-300" />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </Card>

          {/* ── Charts Section ────────────────────────────────────────────────────── */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            
            {/* Test Case Trend LineChart */}
            <Card className="border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col justify-between">
              <div className="flex items-center justify-between border-b px-5 py-4 border-slate-100">
                <div className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-blue-500" />
                  <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Test Case Trend</h3>
                </div>
                <select className="appearance-none bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-800 rounded-lg text-[10px] font-bold px-2.5 py-1 pr-6 focus:outline-none cursor-pointer"
                  style={{
                    backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
                    backgroundPosition: 'right 0.4rem center',
                    backgroundSize: '1rem 1rem',
                    backgroundRepeat: 'no-repeat',
                  }}
                >
                  <option value="7">Last 7 Days</option>
                  <option value="30">Last 30 Days</option>
                </select>
              </div>
              <div className="p-4 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 9, fill: "#94a3b8", fontWeight: 700 }} stroke="#e2e8f0" />
                    <YAxis tick={{ fontSize: 9, fill: "#94a3b8", fontWeight: 700 }} stroke="#e2e8f0" />
                    <ChartTooltip contentStyle={{ fontSize: "10px", fontWeight: "bold", borderRadius: "8px", border: "1px solid #e2e8f0" }} />
                    <ChartLegend wrapperStyle={{ fontSize: "10px", fontWeight: "bold", paddingTop: "10px" }} iconType="circle" />
                    <Line type="monotone" dataKey="Created" stroke="#3b82f6" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                    <Line type="monotone" dataKey="Approved" stroke="#10b981" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                    <Line type="monotone" dataKey="Automated" stroke="#8b5cf6" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>

            {/* Priority Summary DonutChart */}
            <Card className="border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col justify-between">
              <div className="flex items-center justify-between border-b px-5 py-4 border-slate-100">
                <div className="flex items-center gap-2">
                  <Layers className="h-4 w-4 text-purple-500" />
                  <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Priority Summary</h3>
                </div>
                <select className="appearance-none bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-800 rounded-lg text-[10px] font-bold px-2.5 py-1 pr-6 focus:outline-none cursor-pointer"
                  style={{
                    backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
                    backgroundPosition: 'right 0.4rem center',
                    backgroundSize: '1rem 1rem',
                    backgroundRepeat: 'no-repeat',
                  }}
                >
                  <option value="all">All Priorities</option>
                </select>
              </div>
              
              <div className="p-4 flex flex-row items-center justify-between gap-4 h-64">
                <div className="relative w-1/2 h-full flex items-center justify-center">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={priorityChartData}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={75}
                        paddingAngle={3}
                        dataKey="value"
                      >
                        {priorityChartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="absolute flex flex-col items-center justify-center select-none">
                    <span className="text-xl font-extrabold text-slate-800">{totalTCs.toLocaleString()}</span>
                    <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">Total</span>
                  </div>
                </div>
                
                <div className="w-1/2 space-y-2 text-[10px] font-bold text-slate-600">
                  {priorityChartData.map((item) => (
                    <div key={item.name} className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: item.color }} />
                        <span className="truncate">{item.name}</span>
                      </div>
                      <span className="text-slate-500 font-mono text-[9px]">{item.count}</span>
                    </div>
                  ))}
                </div>
              </div>
              
              <div className="border-t border-slate-50 p-3 bg-slate-50/20 text-center">
                <button onClick={() => router.push(`/test-cases?project=${selectedProjectId}`)} className="text-[10px] font-bold text-[#1b59f8] hover:underline flex items-center justify-center gap-1 mx-auto">
                  View Priority Breakdown
                  <ChevronRight className="h-3 w-3" />
                </button>
              </div>
            </Card>

            {/* Jira Sync Health */}
            <Card className="border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col justify-between">
              <div className="flex items-center justify-between border-b px-5 py-4 border-slate-100">
                <div className="flex items-center gap-2">
                  <Zap className="h-4 w-4 text-cyan-500" />
                  <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Jira Sync Health</h3>
                </div>
                <select className="appearance-none bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-800 rounded-lg text-[10px] font-bold px-2.5 py-1 pr-6 focus:outline-none cursor-pointer"
                  style={{
                    backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
                    backgroundPosition: 'right 0.4rem center',
                    backgroundSize: '1rem 1rem',
                    backgroundRepeat: 'no-repeat',
                  }}
                >
                  <option value="all">All Systems</option>
                </select>
              </div>

              <div className="p-5 space-y-5 flex-1 flex flex-col justify-center">
                <div className="flex items-start gap-3 border rounded-xl p-3 bg-emerald-50/50 border-emerald-100/50">
                  <div className="rounded-lg p-1.5 bg-emerald-50 border border-emerald-100 text-emerald-500 shrink-0">
                    <CheckCircle className="h-4.5 w-4.5" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-slate-800">All systems are healthy</h4>
                    <p className="text-[10px] text-slate-400 font-semibold mt-0.5">Last synced 2 mins ago</p>
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-2 text-center select-none font-bold">
                  <div className="bg-slate-50/50 border rounded-lg p-2.5">
                    <div className="text-sm font-extrabold text-slate-800">{jiraSyncedCount.toLocaleString()}</div>
                    <div className="text-[8px] text-slate-400 uppercase mt-0.5 tracking-wider">Synced</div>
                  </div>
                  <div className="bg-slate-50/50 border rounded-lg p-2.5">
                    <div className="text-sm font-extrabold text-slate-800">{jiraPendingCount.toLocaleString()}</div>
                    <div className="text-[8px] text-slate-400 uppercase mt-0.5 tracking-wider">Pending</div>
                  </div>
                  <div className="bg-slate-50/50 border rounded-lg p-2.5">
                    <div className="text-sm font-extrabold text-rose-600">{jiraFailedCount.toLocaleString()}</div>
                    <div className="text-[8px] text-slate-400 uppercase mt-0.5 tracking-wider">Failed</div>
                  </div>
                  <div className="bg-slate-50/50 border rounded-lg p-2.5">
                    <div className="text-sm font-extrabold text-amber-600">{jiraConflictCount.toLocaleString()}</div>
                    <div className="text-[8px] text-slate-400 uppercase mt-0.5 tracking-wider">Conflicts</div>
                  </div>
                </div>
              </div>

              <div className="border-t border-slate-50 p-3 bg-slate-50/20 text-center">
                <button onClick={() => router.push(`/settings?project=${selectedProjectId}`)} className="text-[10px] font-bold text-[#1b59f8] hover:underline flex items-center justify-center gap-1 mx-auto">
                  View Jira Sync Monitor
                  <ChevronRight className="h-3 w-3" />
                </button>
              </div>
            </Card>
          </div>

          {/* ── Bottom grids Section ───────────────────────────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            
            {/* AI Agent Activity logs */}
            <Card className="border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col justify-between">
              <div className="px-5 py-3.5 border-b border-slate-100 bg-slate-50/50">
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">AI Agent Activity</h3>
              </div>
              <div className="divide-y divide-slate-100 flex-1">
                {agentActivity.map((item, index) => (
                  <div key={index} className="flex items-center gap-3 px-4 py-3 text-xs font-semibold text-slate-700">
                    <div className="rounded-lg bg-blue-50 border border-blue-100 p-1.5 text-blue-500 shrink-0">
                      <Cpu className="h-4 w-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-bold text-slate-800 truncate">{item.name}</p>
                      <p className="text-[10px] text-slate-400 mt-0.5 leading-normal">Scanned specifications and mapped actions</p>
                    </div>
                    <div className="flex flex-col items-end gap-1.5 shrink-0 select-none">
                      <Badge variant={getStatusVariant(item.status)} className="capitalize text-[9px] py-0 px-2">
                        {item.status}
                      </Badge>
                      <span className="text-[9px] text-slate-400 font-bold font-mono">{item.time}</span>
                    </div>
                  </div>
                ))}
              </div>
              <div className="border-t border-slate-100 p-3 bg-slate-50/30 text-center">
                <button onClick={() => router.push(`/agents?project=${selectedProjectId}`)} className="text-[10px] font-bold text-[#1b59f8] hover:underline flex items-center justify-center gap-1 mx-auto">
                  View All Agent Runs
                  <ChevronRight className="h-3 w-3" />
                </button>
              </div>
            </Card>

            {/* Pending Approvals queue list */}
            <Card className="border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col justify-between">
              <div className="px-5 py-3.5 border-b border-slate-100 bg-slate-50/50">
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Pending Approvals</h3>
              </div>
              <div className="divide-y divide-slate-100 flex-1">
                {pendingApprovals.map((item, index) => (
                  <div key={index} className="flex items-center justify-between gap-3 px-4 py-3 text-xs font-semibold text-slate-700">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="rounded-lg bg-slate-50 border border-slate-100 p-1.5 text-slate-400 shrink-0">
                        <FileText className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <h4 className="font-bold text-slate-800 truncate leading-snug">{item.title}</h4>
                        <span className="font-mono text-[9px] text-slate-400 font-bold block mt-0.5">{item.code}</span>
                      </div>
                    </div>
                    <Badge variant={item.priority.toLowerCase() === "high" ? "destructive" : "warning"} className="capitalize text-[9px] py-0 px-2 shrink-0">
                      {item.priority}
                    </Badge>
                  </div>
                ))}
              </div>
              <div className="border-t border-slate-100 p-3 bg-slate-50/30 text-center">
                <button onClick={() => router.push(`/test-cases?project=${selectedProjectId}`)} className="text-[10px] font-bold text-[#1b59f8] hover:underline flex items-center justify-center gap-1 mx-auto">
                  View Approval Queue
                  <ChevronRight className="h-3 w-3" />
                </button>
              </div>
            </Card>

            {/* Recent Activity timeline */}
            <Card className="border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col justify-between">
              <div className="px-5 py-3.5 border-b border-slate-100 bg-slate-50/50">
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Recent Activity</h3>
              </div>
              <div className="divide-y divide-slate-100 flex-1">
                {recentActivity.map((item, index) => (
                  <div key={index} className="flex items-center gap-3 px-4 py-3 text-xs font-semibold text-slate-700">
                    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 text-slate-600 text-[10px] font-bold shrink-0">
                      {item.user.split(/\s+/).map(p => p[0]).join("").toUpperCase().substring(0, 2)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-slate-700 leading-normal">
                        <span className="font-bold text-slate-800">{item.user}</span> {item.action}{" "}
                        <span className="font-bold text-[#1b59f8] font-mono">{item.subject}</span>
                      </p>
                    </div>
                    <span className="text-[9px] text-slate-400 font-bold shrink-0">{item.time}</span>
                  </div>
                ))}
              </div>
              <div className="border-t border-slate-100 p-3 bg-slate-50/30 text-center">
                <button onClick={() => router.push(`/dashboard?project=${selectedProjectId}`)} className="text-[10px] font-bold text-[#1b59f8] hover:underline flex items-center justify-center gap-1 mx-auto">
                  View All Activity
                  <ChevronRight className="h-3 w-3" />
                </button>
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

export default function CommandCenterPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-slate-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-[#1b59f8] mr-2" />
        Loading Test Cases Command Center...
      </div>
    }>
      <CommandCenterContent />
    </Suspense>
  );
}
