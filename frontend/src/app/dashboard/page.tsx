"use client";
import { useEffect, useState, useCallback } from "react";
import {
  FileText, TestTube2, Bot, Bug, BarChart3,
  CheckCircle2, AlertTriangle, Clock, Zap, Code2,
  PlayCircle, TrendingUp, RefreshCw, FolderOpen,
} from "lucide-react";
import {
  api, projectsApi, requirementsApi, testCasesApi,
  automationApi, executionApi, defectsApi, agentRunsApi,
  type Project, type ExecutionRun, type AgentRun,
} from "@/lib/api";

// ── Stat Card ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, icon: Icon, color, bg, loading = false }: {
  label: string; value: string | number; icon: React.ElementType;
  color: string; bg: string; loading?: boolean;
}) {
  return (
    <div className={`rounded-xl border bg-white p-4 shadow-sm flex items-start gap-3`}>
      <div className={`p-2 rounded-lg ${bg}`}>
        <Icon size={18} className={color} />
      </div>
      <div>
        {loading ? (
          <div className="h-6 w-10 bg-gray-100 rounded animate-pulse mb-1" />
        ) : (
          <p className="text-2xl font-bold text-gray-900">{value}</p>
        )}
        <p className="text-xs text-gray-500 mt-0.5">{label}</p>
      </div>
    </div>
  );
}

// ── Agent Status Widget ────────────────────────────────────────────────────────

const AGENT_PIPELINE = [
  { key: "requirement_intake",  label: "Requirement Intake"   },
  { key: "requirement_quality", label: "Requirement Quality"  },
  { key: "test_planning",       label: "Test Planning"        },
  { key: "test_scenario",       label: "Test Scenarios"       },
  { key: "test_case",           label: "Test Cases"           },
  { key: "automation_script",   label: "Automation Scripts"   },
  { key: "test_execution",      label: "Test Execution"       },
  { key: "defect_analysis",     label: "Defect Analysis"      },
  { key: "test_reporting",      label: "QA Reporting"         },
];

function AgentStatusPanel({ projectId }: { projectId: number | null }) {
  const [runs, setRuns] = useState<AgentRun[]>([]);

  useEffect(() => {
    if (!projectId) return;
    agentRunsApi.list(projectId, { limit: 100 }).then(r => setRuns(r.data)).catch(() => {});
  }, [projectId]);

  const latestByAgent: Record<string, AgentRun> = {};
  for (const run of runs) {
    if (!latestByAgent[run.agent_name]) latestByAgent[run.agent_name] = run;
  }

  return (
    <div className="rounded-xl border bg-white p-5 shadow-sm h-full">
      <div className="flex items-center gap-2 mb-4">
        <Bot size={16} className="text-indigo-500" />
        <h3 className="font-semibold text-sm">Agent Status</h3>
      </div>
      <div className="space-y-2">
        {AGENT_PIPELINE.map(a => {
          const latest = latestByAgent[a.key];
          const status = latest?.status ?? "idle";
          const dotColor = status === "completed" ? "bg-green-500" :
                           status === "running"   ? "bg-blue-500 animate-pulse" :
                           status === "failed"    ? "bg-red-500" : "bg-gray-300";
          const statusText = status === "idle" ? "idle" : status;
          return (
            <div key={a.key} className="flex items-center gap-2.5">
              <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${dotColor}`} />
              <span className="text-xs text-gray-600 flex-1 truncate">{a.label}</span>
              <span className={`text-xs capitalize ${
                status === "completed" ? "text-green-600" :
                status === "failed"    ? "text-red-500" :
                status === "running"   ? "text-blue-500" : "text-gray-400"
              }`}>{statusText}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Execution Mini Chart ───────────────────────────────────────────────────────

function ExecutionSummaryPanel({ runs }: { runs: ExecutionRun[] }) {
  if (runs.length === 0) {
    return (
      <div className="rounded-xl border bg-white p-5 shadow-sm h-full flex flex-col">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp size={16} className="text-blue-500" />
          <h3 className="font-semibold text-sm">Execution Trend</h3>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <PlayCircle size={28} className="mx-auto text-gray-200 mb-2" />
            <p className="text-sm text-gray-400">No execution runs yet</p>
          </div>
        </div>
      </div>
    );
  }

  const recent = runs.slice(0, 8).reverse();
  const maxTotal = Math.max(...recent.map(r => r.total_tests), 1);

  return (
    <div className="rounded-xl border bg-white p-5 shadow-sm h-full">
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp size={16} className="text-blue-500" />
        <h3 className="font-semibold text-sm">Execution Trend (last {recent.length} runs)</h3>
      </div>
      <div className="flex items-end gap-2 h-24">
        {recent.map(run => {
          const passH = run.total_tests > 0 ? Math.round(run.passed / maxTotal * 80) : 0;
          const failH = run.total_tests > 0 ? Math.round(run.failed / maxTotal * 80) : 0;
          const pct = run.total_tests > 0 ? Math.round(run.passed / run.total_tests * 100) : 0;
          return (
            <div key={run.id} className="flex-1 flex flex-col items-center gap-1" title={`${run.execution_id}: ${pct}% pass`}>
              <span className="text-xs text-gray-400">{pct}%</span>
              <div className="w-full flex flex-col-reverse gap-0.5">
                {failH > 0 && <div style={{ height: failH }} className="bg-red-300 rounded-t-sm" />}
                {passH > 0 && <div style={{ height: passH }} className="bg-green-400 rounded-t-sm" />}
              </div>
              <span className="text-xs text-gray-300 font-mono">{run.execution_id.split("-")[1]}</span>
            </div>
          );
        })}
      </div>
      <div className="flex items-center gap-4 mt-3 text-xs text-gray-400">
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-green-400 inline-block" /> Pass</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-red-300 inline-block" /> Fail</span>
      </div>
    </div>
  );
}

// ── Recent Activity ────────────────────────────────────────────────────────────

function RecentActivityPanel({ runs }: { runs: AgentRun[] }) {
  const agentLabel: Record<string, string> = {
    requirement_intake: "Requirement Intake", requirement_quality: "Quality Analysis",
    test_planning: "Test Planning", test_scenario: "Test Scenarios",
    test_case: "Test Cases", automation_script: "Automation Scripts",
    test_execution: "Test Execution", defect_analysis: "Defect Analysis",
    test_reporting: "QA Reporting",
  };

  return (
    <div className="rounded-xl border bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-4">
        <Zap size={16} className="text-yellow-500" />
        <h3 className="font-semibold text-sm">Recent Agent Activity</h3>
      </div>
      {runs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Zap size={24} className="text-gray-200 mb-2" />
          <p className="text-sm text-gray-400">No activity yet</p>
          <p className="text-xs text-gray-300 mt-1">Run your first agent to see activity here</p>
        </div>
      ) : (
        <div className="divide-y divide-gray-50">
          {runs.slice(0, 8).map(run => (
            <div key={run.id} className="flex items-center gap-3 py-2.5">
              <span className={`w-2 h-2 rounded-full shrink-0 ${
                run.status === "completed" ? "bg-green-500" :
                run.status === "failed"    ? "bg-red-500" :
                run.status === "running"   ? "bg-blue-500 animate-pulse" : "bg-gray-300"
              }`} />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-700 truncate">{agentLabel[run.agent_name] ?? run.agent_name}</p>
                <p className="text-xs text-gray-400">{new Date(run.created_at).toLocaleString()}</p>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                run.status === "completed" ? "bg-green-100 text-green-700" :
                run.status === "failed"    ? "bg-red-100 text-red-600" :
                "bg-gray-100 text-gray-500"
              }`}>{run.status}</span>
              {run.duration_seconds && (
                <span className="text-xs text-gray-300">{run.duration_seconds.toFixed(1)}s</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [execRuns, setExecRuns] = useState<ExecutionRun[]>([]);
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [stats, setStats] = useState({
    requirements: 0,
    testCases: 0,
    automationPct: 0,
    lastPassPct: "—",
    openDefects: 0,
    pendingApprovals: 0,
    agentRunsToday: 0,
    scripts: 0,
  });

  useEffect(() => {
    projectsApi.list().then(r => {
      setProjects(r.data);
      if (r.data.length > 0) setSelectedProject(r.data[0].id);
    }).catch(() => {});
  }, []);

  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const [reqRes, tcRes, autoRes, execRes, defRes, agentRes] = await Promise.allSettled([
        requirementsApi.list(selectedProject),
        testCasesApi.list(selectedProject),
        automationApi.list(selectedProject),
        executionApi.listRuns(selectedProject),
        defectsApi.list(selectedProject, { status: "draft" }),
        agentRunsApi.list(selectedProject, { limit: 100 }),
      ]);

      const reqs   = reqRes.status   === "fulfilled" ? reqRes.value.data   : [];
      const tcs    = tcRes.status    === "fulfilled" ? tcRes.value.data    : [];
      const autos  = autoRes.status  === "fulfilled" ? autoRes.value.data  : [];
      const runs   = execRes.status  === "fulfilled" ? execRes.value.data  : [];
      const defs   = defRes.status   === "fulfilled" ? defRes.value.data   : [];
      const aRuns  = agentRes.status === "fulfilled" ? agentRes.value.data : [];

      setExecRuns(runs);
      setAgentRuns(aRuns);

      const latestRun = runs[0];
      const lastPassPct = latestRun && latestRun.total_tests > 0
        ? `${Math.round(latestRun.passed / latestRun.total_tests * 100)}%`
        : "—";

      const today = new Date().toDateString();
      const agentRunsToday = aRuns.filter(r => new Date(r.created_at).toDateString() === today).length;

      const pendingApprovals =
        reqs.filter(r => r.status === "pending_review").length +
        tcs.filter(t => t.status === "draft").length;

      const autoCandidates = tcs.filter(t => t.automation_candidate).length;
      const automationPct = tcs.length > 0 ? Math.round(autoCandidates / tcs.length * 100) : 0;

      setStats({
        requirements: reqs.length,
        testCases: tcs.length,
        automationPct,
        lastPassPct,
        openDefects: defs.length,
        pendingApprovals,
        agentRunsToday,
        scripts: autos.length,
      });
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => { loadData(); }, [loadData]);

  const STAT_CARDS = [
    { label: "Requirements",      value: stats.requirements,     icon: FileText,     color: "text-blue-500",    bg: "bg-blue-50"    },
    { label: "Test Cases",        value: stats.testCases,        icon: TestTube2,    color: "text-purple-500",  bg: "bg-purple-50"  },
    { label: "Automation Scripts",value: stats.scripts,          icon: Code2,        color: "text-violet-500",  bg: "bg-violet-50"  },
    { label: "Automation Cov.",   value: `${stats.automationPct}%`, icon: Bot,       color: "text-green-500",   bg: "bg-green-50"   },
    { label: "Last Run Pass Rate",value: stats.lastPassPct,      icon: CheckCircle2, color: "text-emerald-500", bg: "bg-emerald-50" },
    { label: "Open Defects",      value: stats.openDefects,      icon: Bug,          color: "text-red-500",     bg: "bg-red-50"     },
    { label: "Pending Approvals", value: stats.pendingApprovals, icon: AlertTriangle,color: "text-orange-500",  bg: "bg-orange-50"  },
    { label: "Agent Runs Today",  value: stats.agentRunsToday,   icon: Zap,          color: "text-indigo-500",  bg: "bg-indigo-50"  },
  ];

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Command Center</h1>
          <p className="text-sm text-gray-500 mt-1">AI Agent-powered QA dashboard — full STLC visibility at a glance</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            <FolderOpen size={14} />
            <select
              value={selectedProject ?? ""}
              onChange={e => setSelectedProject(Number(e.target.value))}
              className="border border-gray-200 rounded-lg px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
            >
              {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 rounded-lg border border-gray-200 hover:border-gray-400 text-gray-500 disabled:opacity-50"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {STAT_CARDS.map(s => (
          <StatCard key={s.label} {...s} loading={loading} />
        ))}
      </div>

      {/* Charts + Agent status */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ExecutionSummaryPanel runs={execRuns} />
        </div>
        <div>
          <AgentStatusPanel projectId={selectedProject} />
        </div>
      </div>

      {/* Recent activity */}
      <RecentActivityPanel runs={agentRuns} />
    </div>
  );
}
