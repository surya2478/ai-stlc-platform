"use client";
import { useState, useEffect, useCallback } from "react";
import { agentRunsApi, projectsApi, type AgentRun, type Project } from "@/lib/api";
import { Bot, CheckCircle, XCircle, Clock, AlertTriangle, RefreshCw, ChevronRight, Zap } from "lucide-react";

// ── Agent pipeline definition ─────────────────────────────────────────────────

const PIPELINE: { name: string; label: string; description: string; phase: string; color: string }[] = [
  { name: "requirement_intake",  label: "Requirement Intake",   description: "Extracts requirements from uploaded documents",        phase: "Phase 2", color: "bg-blue-100 text-blue-700 border-blue-200" },
  { name: "requirement_quality", label: "Quality Analysis",     description: "Validates and enriches requirements with QA lens",     phase: "Phase 2", color: "bg-cyan-100 text-cyan-700 border-cyan-200" },
  { name: "test_planning",       label: "Test Planning",        description: "Generates structured test plan from requirements",     phase: "Phase 3", color: "bg-violet-100 text-violet-700 border-violet-200" },
  { name: "test_scenario",       label: "Test Scenarios",       description: "Creates high-level test scenarios per requirement",    phase: "Phase 3", color: "bg-purple-100 text-purple-700 border-purple-200" },
  { name: "test_case",           label: "Test Cases",           description: "Generates detailed step-by-step test cases",          phase: "Phase 3", color: "bg-fuchsia-100 text-fuchsia-700 border-fuchsia-200" },
  { name: "automation_script",   label: "Automation Scripts",   description: "Writes Playwright / Pytest scripts for automation",   phase: "Phase 4", color: "bg-pink-100 text-pink-700 border-pink-200" },
  { name: "test_execution",      label: "Test Execution",       description: "Executes test suite and records pass/fail results",   phase: "Phase 5", color: "bg-rose-100 text-rose-700 border-rose-200" },
  { name: "defect_analysis",     label: "Defect Analysis",      description: "Analyses failures and writes defect reports",         phase: "Phase 6", color: "bg-orange-100 text-orange-700 border-orange-200" },
  { name: "test_reporting",      label: "QA Reporting",         description: "Aggregates metrics and generates executive report",   phase: "Phase 7", color: "bg-emerald-100 text-emerald-700 border-emerald-200" },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: string | null }) {
  if (!status) return <span className="w-2 h-2 rounded-full bg-gray-200 inline-block" />;
  const map: Record<string, string> = {
    completed: "bg-green-500",
    running: "bg-blue-500 animate-pulse",
    failed: "bg-red-500",
    pending: "bg-yellow-400",
    cancelled: "bg-gray-400",
  };
  return <span className={`w-2 h-2 rounded-full inline-block ${map[status] ?? "bg-gray-300"}`} />;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: "bg-green-100 text-green-700",
    running: "bg-blue-100 text-blue-700",
    failed: "bg-red-100 text-red-700",
    pending: "bg-yellow-100 text-yellow-700",
    cancelled: "bg-gray-100 text-gray-600",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${map[status] ?? "bg-gray-100 text-gray-600"}`}>
      {status}
    </span>
  );
}

function formatDuration(secs: number | undefined): string {
  if (!secs) return "—";
  if (secs < 60) return `${secs.toFixed(1)}s`;
  return `${Math.floor(secs / 60)}m ${(secs % 60).toFixed(0)}s`;
}

function AgentPipelineCard({
  agent,
  latestRun,
  runCount,
  onSelect,
}: {
  agent: typeof PIPELINE[0];
  latestRun: AgentRun | null;
  runCount: number;
  onSelect: () => void;
}) {
  return (
    <div
      onClick={onSelect}
      className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 cursor-pointer hover:border-gray-400 hover:shadow-md transition-all group"
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <StatusDot status={latestRun?.status ?? null} />
            <span className={`px-2 py-0.5 rounded text-xs font-medium border ${agent.color}`}>{agent.phase}</span>
          </div>
          <h3 className="text-sm font-semibold text-gray-800 group-hover:text-gray-900">{agent.label}</h3>
          <p className="text-xs text-gray-500 mt-0.5 leading-snug">{agent.description}</p>
        </div>
        <ChevronRight size={14} className="text-gray-300 group-hover:text-gray-500 shrink-0 mt-1" />
      </div>
      <div className="flex items-center gap-3 pt-3 border-t border-gray-50 text-xs text-gray-400">
        {latestRun ? (
          <>
            <StatusBadge status={latestRun.status} />
            <span className="flex items-center gap-1"><Clock size={10} /> {formatDuration(latestRun.duration_seconds)}</span>
            <span className="ml-auto">{new Date(latestRun.created_at).toLocaleDateString()}</span>
          </>
        ) : (
          <span className="text-gray-300 italic">No runs yet</span>
        )}
        {runCount > 0 && (
          <span className="ml-auto text-gray-400">{runCount} run{runCount !== 1 ? "s" : ""}</span>
        )}
      </div>
    </div>
  );
}

function RunHistoryRow({ run, onSelect }: { run: AgentRun; onSelect: (id: number) => void }) {
  const agentLabel = PIPELINE.find(a => a.name === run.agent_name)?.label ?? run.agent_name;
  return (
    <div
      onClick={() => onSelect(run.id)}
      className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 cursor-pointer border-b border-gray-50 last:border-0"
    >
      <StatusDot status={run.status} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-700 truncate">{agentLabel}</p>
        <p className="text-xs text-gray-400">{new Date(run.created_at).toLocaleString()}</p>
      </div>
      <StatusBadge status={run.status} />
      <span className="text-xs text-gray-400 w-16 text-right">{formatDuration(run.duration_seconds)}</span>
      {run.status === "failed" && <AlertTriangle size={14} className="text-red-400 shrink-0" />}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AgentWorkflowPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | null>(null);
  const [allRuns, setAllRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  useEffect(() => {
    projectsApi.list()
      .then((r) => {
        setProjects(r.data);
        if (r.data.length > 0) setSelectedProject(r.data[0].id);
      })
      .catch((e) => console.error("[Projects] Failed to load:", e?.response?.status));
  }, []);

  const loadRuns = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const res = await agentRunsApi.list(selectedProject, { limit: 200 });
      setAllRuns(res.data);
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => { loadRuns(); }, [loadRuns]);

  // Build per-agent stats
  const agentStats: Record<string, { latest: AgentRun | null; count: number }> = {};
  for (const a of PIPELINE) {
    const runs = allRuns.filter(r => r.agent_name === a.name);
    agentStats[a.name] = {
      latest: runs[0] ?? null,
      count: runs.length,
    };
  }

  const filteredRuns = selectedAgent
    ? allRuns.filter(r => r.agent_name === selectedAgent)
    : allRuns;

  const summary = {
    total: allRuns.length,
    completed: allRuns.filter(r => r.status === "completed").length,
    failed: allRuns.filter(r => r.status === "failed").length,
    avgDuration: allRuns.filter(r => r.duration_seconds).length > 0
      ? allRuns.filter(r => r.duration_seconds).reduce((a, r) => a + (r.duration_seconds ?? 0), 0) /
        allRuns.filter(r => r.duration_seconds).length
      : 0,
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-100 rounded-lg">
            <Bot size={22} className="text-indigo-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Agent Workflow</h1>
            <p className="text-sm text-gray-500">Full 9-agent STLC pipeline — status, runs, and performance</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedProject ?? ""}
            onChange={(e) => setSelectedProject(Number(e.target.value))}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button
            onClick={loadRuns}
            disabled={loading}
            className="p-2 rounded-lg border border-gray-200 hover:border-gray-400 text-gray-500 hover:text-gray-700 disabled:opacity-50"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Total Agent Runs", value: summary.total, color: "text-gray-800", icon: Zap },
          { label: "Completed", value: summary.completed, color: "text-green-600", icon: CheckCircle },
          { label: "Failed", value: summary.failed, color: "text-red-500", icon: XCircle },
          { label: "Avg Duration", value: formatDuration(summary.avgDuration), color: "text-indigo-600", icon: Clock },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm flex items-center gap-3">
            <s.icon size={20} className={s.color} />
            <div>
              <p className={`text-xl font-bold ${s.color}`}>{s.value}</p>
              <p className="text-xs text-gray-500">{s.label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Pipeline grid */}
      <div>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Pipeline Agents</h2>
        <div className="grid grid-cols-3 gap-3">
          {PIPELINE.map((agent, idx) => (
            <div key={agent.name} className="relative">
              {idx < PIPELINE.length - 1 && idx % 3 !== 2 && (
                <div className="absolute top-1/2 -right-1.5 z-10 text-gray-300 text-xs">▶</div>
              )}
              <AgentPipelineCard
                agent={agent}
                latestRun={agentStats[agent.name]?.latest ?? null}
                runCount={agentStats[agent.name]?.count ?? 0}
                onSelect={() => setSelectedAgent(selectedAgent === agent.name ? null : agent.name)}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Run history */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-gray-700">Run History</h2>
            {selectedAgent && (
              <span className="text-xs bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded-full">
                {PIPELINE.find(a => a.name === selectedAgent)?.label}
                <button onClick={() => setSelectedAgent(null)} className="ml-1 hover:text-red-500">×</button>
              </span>
            )}
          </div>
          <span className="text-xs text-gray-400">{filteredRuns.length} runs</span>
        </div>
        {loading ? (
          <div className="flex justify-center py-10">
            <span className="animate-spin w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full" />
          </div>
        ) : filteredRuns.length === 0 ? (
          <div className="text-center py-12">
            <Bot size={32} className="mx-auto text-gray-200 mb-2" />
            <p className="text-sm text-gray-400">No agent runs recorded yet</p>
            <p className="text-xs text-gray-300 mt-1">Runs appear here as you use the AI features across the platform</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-50 max-h-96 overflow-y-auto">
            {filteredRuns.slice(0, 100).map((run) => (
              <RunHistoryRow key={run.id} run={run} onSelect={() => {}} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
