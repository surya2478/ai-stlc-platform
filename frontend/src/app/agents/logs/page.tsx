"use client";
import { useState, useEffect, useCallback } from "react";
import { agentRunsApi, projectsApi, type AgentRun, type AgentLog, type Project } from "@/lib/api";
import { Cpu, ChevronDown, ChevronUp, RefreshCw, AlertTriangle, Info, Bug, CheckCircle } from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

const AGENT_LABELS: Record<string, string> = {
  requirement_intake:  "Requirement Intake",
  requirement_quality: "Quality Analysis",
  test_planning:       "Test Planning",
  test_scenario:       "Test Scenarios",
  test_case:           "Test Cases",
  automation_script:   "Automation Scripts",
  test_execution:      "Test Execution",
  defect_analysis:     "Defect Analysis",
  test_reporting:      "QA Reporting",
};

function LevelIcon({ level }: { level: string }) {
  if (level === "error" || level === "critical") return <AlertTriangle size={13} className="text-red-500 shrink-0" />;
  if (level === "warning") return <AlertTriangle size={13} className="text-yellow-500 shrink-0" />;
  if (level === "info") return <Info size={13} className="text-blue-400 shrink-0" />;
  return <Bug size={13} className="text-gray-400 shrink-0" />;
}

function LevelBadge({ level }: { level: string }) {
  const map: Record<string, string> = {
    debug:    "bg-gray-100 text-gray-500",
    info:     "bg-blue-50 text-blue-600",
    warning:  "bg-yellow-50 text-yellow-600",
    error:    "bg-red-50 text-red-600",
    critical: "bg-red-100 text-red-700 font-bold",
  };
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs uppercase tracking-wide ${map[level] ?? "bg-gray-50 text-gray-500"}`}>
      {level}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: "bg-green-100 text-green-700",
    running:   "bg-blue-100 text-blue-700",
    failed:    "bg-red-100 text-red-700",
    pending:   "bg-yellow-100 text-yellow-700",
    cancelled: "bg-gray-100 text-gray-600",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${map[status] ?? "bg-gray-100 text-gray-600"}`}>
      {status}
    </span>
  );
}

function LogEntry({ log }: { log: AgentLog }) {
  const [expanded, setExpanded] = useState(false);
  const hasData = log.data && Object.keys(log.data).length > 0;

  return (
    <div className={`border-b border-gray-50 last:border-0 ${log.level === "error" || log.level === "critical" ? "bg-red-50/50" : ""}`}>
      <div
        className={`flex items-start gap-3 px-4 py-2.5 ${hasData ? "cursor-pointer hover:bg-gray-50" : ""}`}
        onClick={() => hasData && setExpanded(!expanded)}
      >
        <span className="text-xs text-gray-300 font-mono shrink-0 mt-0.5 w-20">
          {new Date(log.created_at).toLocaleTimeString()}
        </span>
        <LevelIcon level={log.level} />
        <LevelBadge level={log.level} />
        {log.step && (
          <span className="text-xs font-mono text-gray-400 shrink-0">[{log.step}]</span>
        )}
        <span className="text-xs text-gray-700 flex-1 leading-relaxed">{log.message}</span>
        {hasData && (
          <span className="text-gray-300 shrink-0">
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </span>
        )}
      </div>
      {expanded && hasData && (
        <div className="px-4 pb-3 pt-1">
          <pre className="text-xs bg-gray-900 text-gray-100 p-3 rounded-lg overflow-x-auto max-h-48 font-mono">
            {JSON.stringify(log.data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function RunPanel({
  run,
  selected,
  onSelect,
}: {
  run: AgentRun;
  selected: boolean;
  onSelect: () => void;
}) {
  const label = AGENT_LABELS[run.agent_name] ?? run.agent_name;
  const durSec = run.duration_seconds ? `${run.duration_seconds.toFixed(1)}s` : "—";

  return (
    <div
      onClick={onSelect}
      className={`px-4 py-3 cursor-pointer border-b border-gray-50 hover:bg-gray-50 transition-colors ${
        selected ? "bg-indigo-50 border-l-2 border-l-indigo-400" : ""
      }`}
    >
      <div className="flex items-center gap-2 mb-1">
        <StatusBadge status={run.status} />
        <span className="text-xs text-gray-400">#{run.id}</span>
        {run.status === "failed" && <AlertTriangle size={12} className="text-red-400" />}
      </div>
      <p className="text-sm font-medium text-gray-700 truncate">{label}</p>
      <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
        <span>{new Date(run.created_at).toLocaleString()}</span>
        <span>·</span>
        <span>{durSec}</span>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AgentLogsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [logsLoading, setLogsLoading] = useState(false);
  const [filterAgent, setFilterAgent] = useState<string>("all");
  const [filterLevel, setFilterLevel] = useState<string>("all");

  useEffect(() => {
    projectsApi.list().then((r) => {
      setProjects(r.data);
      if (r.data.length > 0) setSelectedProject(r.data[0].id);
    });
  }, []);

  const loadRuns = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const res = await agentRunsApi.list(selectedProject, { limit: 100 });
      setRuns(res.data);
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => { loadRuns(); }, [loadRuns]);

  const loadLogs = useCallback(async (runId: number) => {
    setLogsLoading(true);
    try {
      const res = await agentRunsApi.getLogs(runId);
      setLogs(res.data);
    } finally {
      setLogsLoading(false);
    }
  }, []);

  const handleSelectRun = (id: number) => {
    setSelectedRunId(id);
    loadLogs(id);
  };

  const selectedRun = runs.find(r => r.id === selectedRunId);
  const filteredRuns = filterAgent === "all" ? runs : runs.filter(r => r.agent_name === filterAgent);
  const filteredLogs = filterLevel === "all" ? logs : logs.filter(l => l.level === filterLevel);

  const uniqueAgents = [...new Set(runs.map(r => r.agent_name))];

  const logStats = {
    total: logs.length,
    errors: logs.filter(l => l.level === "error" || l.level === "critical").length,
    warnings: logs.filter(l => l.level === "warning").length,
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-slate-100 rounded-lg">
            <Cpu size={22} className="text-slate-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Agent Logs</h1>
            <p className="text-sm text-gray-500">Detailed audit trail for every AI agent run</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedProject ?? ""}
            onChange={(e) => { setSelectedProject(Number(e.target.value)); setSelectedRunId(null); setLogs([]); }}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-300"
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button
            onClick={loadRuns}
            disabled={loading}
            className="p-2 rounded-lg border border-gray-200 hover:border-gray-400 text-gray-500 disabled:opacity-50"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Split layout */}
      <div className="grid grid-cols-5 gap-4" style={{ minHeight: "70vh" }}>
        {/* Left: run list */}
        <div className="col-span-2 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
          {/* Run filters */}
          <div className="px-4 py-3 border-b border-gray-100 space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-700">Runs ({filteredRuns.length})</h2>
            </div>
            <select
              value={filterAgent}
              onChange={(e) => setFilterAgent(e.target.value)}
              className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5 focus:outline-none"
            >
              <option value="all">All agents</option>
              {uniqueAgents.map(a => (
                <option key={a} value={a}>{AGENT_LABELS[a] ?? a}</option>
              ))}
            </select>
          </div>

          {loading ? (
            <div className="flex justify-center py-8">
              <span className="animate-spin w-6 h-6 border-2 border-slate-400 border-t-transparent rounded-full" />
            </div>
          ) : filteredRuns.length === 0 ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Cpu size={28} className="mx-auto text-gray-200 mb-2" />
                <p className="text-sm text-gray-400">No runs yet</p>
              </div>
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto">
              {filteredRuns.map(run => (
                <RunPanel
                  key={run.id}
                  run={run}
                  selected={run.id === selectedRunId}
                  onSelect={() => handleSelectRun(run.id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Right: log detail */}
        <div className="col-span-3 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
          {selectedRun ? (
            <>
              {/* Log header */}
              <div className="px-4 py-3 border-b border-gray-100">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold text-gray-800">
                      {AGENT_LABELS[selectedRun.agent_name] ?? selectedRun.agent_name}
                      <span className="text-gray-400 font-normal"> #{selectedRun.id}</span>
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {new Date(selectedRun.created_at).toLocaleString()}
                      {selectedRun.duration_seconds && ` · ${selectedRun.duration_seconds.toFixed(1)}s`}
                      {selectedRun.llm_model && ` · ${selectedRun.llm_model}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {selectedRun.status === "failed" && selectedRun.error_message && (
                      <span className="text-xs text-red-600 bg-red-50 px-2 py-1 rounded max-w-xs truncate">
                        {selectedRun.error_message}
                      </span>
                    )}
                    <StatusBadge status={selectedRun.status} />
                  </div>
                </div>
                {/* Log stats + filter */}
                {logs.length > 0 && (
                  <div className="flex items-center gap-3 mt-2">
                    <span className="text-xs text-gray-400">{logStats.total} entries</span>
                    {logStats.errors > 0 && (
                      <span className="text-xs text-red-500">{logStats.errors} error{logStats.errors !== 1 ? "s" : ""}</span>
                    )}
                    {logStats.warnings > 0 && (
                      <span className="text-xs text-yellow-500">{logStats.warnings} warning{logStats.warnings !== 1 ? "s" : ""}</span>
                    )}
                    <div className="ml-auto flex gap-1">
                      {["all", "info", "warning", "error"].map(l => (
                        <button
                          key={l}
                          onClick={() => setFilterLevel(l)}
                          className={`px-2 py-0.5 text-xs rounded transition-colors ${
                            filterLevel === l ? "bg-slate-700 text-white" : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                          }`}
                        >
                          {l}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Log entries */}
              {logsLoading ? (
                <div className="flex justify-center py-10">
                  <span className="animate-spin w-6 h-6 border-2 border-slate-400 border-t-transparent rounded-full" />
                </div>
              ) : filteredLogs.length === 0 ? (
                <div className="flex-1 flex items-center justify-center">
                  {logs.length === 0 ? (
                    <div className="text-center">
                      <CheckCircle size={28} className="mx-auto text-gray-200 mb-2" />
                      <p className="text-sm text-gray-400">No log entries for this run</p>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400">No {filterLevel} entries</p>
                  )}
                </div>
              ) : (
                <div className="flex-1 overflow-y-auto font-mono">
                  {filteredLogs.map(log => (
                    <LogEntry key={log.id} log={log} />
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Cpu size={36} className="mx-auto text-gray-200 mb-3" />
                <p className="text-sm text-gray-400 font-medium">Select a run to view logs</p>
                <p className="text-xs text-gray-300 mt-1">Click any run on the left</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
