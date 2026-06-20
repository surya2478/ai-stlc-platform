"use client";

import { useState, useEffect, useCallback, useMemo, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { agentRunsApi, projectsApi, type AgentRun, type AgentLog, type Project } from "@/lib/api";
import { Cpu, ChevronDown, ChevronUp, RefreshCw, AlertTriangle, Info, Bug, CheckCircle, Loader2, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

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

function getStatusVariant(status: string): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" {
  const s = status.toLowerCase();
  if (s === "completed" || s === "passed" || s === "success") return "success";
  if (s === "failed" || s === "error") return "destructive";
  if (s === "running" || s === "pending") return "warning";
  if (s === "cancelled") return "secondary";
  return "outline";
}

function LevelIcon({ level }: { level: string }) {
  const s = level.toLowerCase();
  if (s === "error" || s === "critical") return <AlertTriangle size={13} className="text-rose-500 shrink-0 mt-0.5" />;
  if (s === "warning") return <AlertTriangle size={13} className="text-amber-500 shrink-0 mt-0.5" />;
  if (s === "info") return <Info size={13} className="text-blue-500 shrink-0 mt-0.5" />;
  return <Bug size={13} className="text-slate-400 shrink-0 mt-0.5" />;
}

function LevelBadge({ level }: { level: string }) {
  const s = level.toLowerCase();
  const map: Record<string, string> = {
    debug:    "bg-slate-50 text-slate-500 border-slate-150",
    info:     "bg-blue-50 text-blue-600 border-blue-150",
    warning:  "bg-amber-50 text-amber-600 border-amber-150",
    error:    "bg-rose-50 text-rose-600 border-rose-150",
    critical: "bg-rose-100 text-rose-700 border-rose-200 font-bold",
  };
  return (
    <span className={cn("px-1.5 py-0.5 rounded text-[10px] uppercase font-bold border tracking-wider select-none shrink-0", map[s] ?? "bg-slate-50 text-slate-500 border-slate-150")}>
      {level}
    </span>
  );
}

function LogEntry({ log }: { log: AgentLog }) {
  const [expanded, setExpanded] = useState(false);
  const hasData = log.data && Object.keys(log.data).length > 0;
  const isErr = log.level.toLowerCase() === "error" || log.level.toLowerCase() === "critical";

  return (
    <div className={cn(
      "border-b border-slate-100 last:border-0",
      isErr && "bg-rose-50/20"
    )}>
      <div
        className={cn(
          "flex items-start gap-3 px-4 py-3 font-semibold text-xs transition-colors",
          hasData ? "cursor-pointer hover:bg-slate-50/50" : ""
        )}
        onClick={() => hasData && setExpanded(!expanded)}
      >
        <span className="text-[10px] text-slate-400 font-mono shrink-0 mt-0.5 w-18 select-none">
          {new Date(log.created_at).toLocaleTimeString()}
        </span>
        <LevelIcon level={log.level} />
        <LevelBadge level={log.level} />
        {log.step && (
          <span className="text-[10px] font-mono font-bold text-slate-400 shrink-0 mt-0.5">[{log.step}]</span>
        )}
        <span className="text-slate-700 flex-1 leading-relaxed break-words">{log.message}</span>
        {hasData && (
          <span className="text-slate-350 shrink-0 mt-0.5">
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </span>
        )}
      </div>
      {expanded && hasData && (
        <div className="px-4 pb-3.5 pt-0.5 pl-24 animate-in slide-in-from-top-1 duration-100">
          <pre className="text-[11px] bg-slate-900 text-slate-100 p-3.5 rounded-lg overflow-x-auto max-h-56 font-mono leading-relaxed shadow-inner">
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
      className={cn(
        "px-4 py-3 cursor-pointer border-b border-slate-100 hover:bg-slate-50/50 transition-colors select-none font-semibold",
        selected ? "bg-[#1b59f8]/5 border-l-2 border-l-[#1b59f8]" : ""
      )}
    >
      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        <Badge variant={getStatusVariant(run.status)} className="capitalize text-[9px] py-0 px-1.5">
          {run.status}
        </Badge>
        <span className="text-[10px] font-mono text-slate-400 font-bold">#{run.id}</span>
        {run.status === "failed" && <AlertTriangle size={12} className="text-rose-500 shrink-0" />}
      </div>
      <p className="text-xs font-bold text-slate-800 truncate">{label}</p>
      <div className="flex items-center gap-2 mt-1.5 text-[10px] text-slate-400 font-bold">
        <span>{new Date(run.created_at).toLocaleDateString()} {new Date(run.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
        <span>·</span>
        <span className="flex items-center gap-0.5"><Clock className="h-3 w-3" /> {durSec}</span>
      </div>
    </div>
  );
}

// ── Main Content Component ───────────────────────────────────────────────────

function AgentLogsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProject = Number(searchParams.get("project")) || null;

  const [projects, setProjects] = useState<Project[]>([]);
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
      if (r.data.length > 0 && !searchParams.get("project")) {
        const params = new URLSearchParams(searchParams.toString());
        params.set("project", String(r.data[0].id));
        router.push(`${pathname}?${params.toString()}`);
      }
    });
  }, [searchParams, pathname, router]);

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
  const filteredLogs = filterLevel === "all" ? logs : logs.filter(l => l.level.toLowerCase() === filterLevel.toLowerCase());

  const uniqueAgents = useMemo(() => Array.from(new Set(runs.map(r => r.agent_name))), [runs]);

  const logStats = useMemo(() => {
    return {
      total: logs.length,
      errors: logs.filter(l => {
        const lv = l.level.toLowerCase();
        return lv === "error" || lv === "critical";
      }).length,
      warnings: logs.filter(l => l.level.toLowerCase() === "warning").length,
    };
  }, [logs]);

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Global Controls ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-blue-50 border border-blue-100 p-2.5">
            <Cpu className="h-6 w-6 text-[#1b59f8]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Agent Run Logs</h1>
            <p className="text-xs text-slate-500 mt-1">Detailed execution trace, debugging outputs, and LLM telemetry for every agent task</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedProject ?? ""}
            onChange={(e) => {
              const val = e.target.value;
              const params = new URLSearchParams(searchParams.toString());
              params.set("project", val);
              router.push(`${pathname}?${params.toString()}`);
              setSelectedRunId(null);
              setLogs([]);
            }}
            className="appearance-none bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 rounded-lg text-xs font-semibold px-3 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-[#1b59f8] transition-colors cursor-pointer"
            style={{
              backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
              backgroundPosition: 'right 0.5rem center',
              backgroundSize: '1.25rem 1.25rem',
              backgroundRepeat: 'no-repeat',
            }}
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>

          <Button variant="outline" size="sm" onClick={loadRuns} className="h-8 w-8 p-0 border-slate-200">
            <RefreshCw className={cn("h-3.5 w-3.5 text-slate-500", loading && "animate-spin")} />
          </Button>
        </div>
      </div>

      {selectedProject && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4" style={{ minHeight: "70vh" }}>
          {/* ── Left side: Run List Panel ────────────────────────────────────────── */}
          <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-full">
            <div className="px-4 py-3.5 border-b border-slate-100 bg-slate-50/50 space-y-2.5">
              <h2 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Runs ({filteredRuns.length})</h2>
              
              <select
                value={filterAgent}
                onChange={(e) => setFilterAgent(e.target.value)}
                className="w-full text-xs font-semibold border border-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none bg-white"
              >
                <option value="all">All Agents</option>
                {uniqueAgents.map(a => (
                  <option key={a} value={a}>{AGENT_LABELS[a] ?? a}</option>
                ))}
              </select>
            </div>

            {loading ? (
              <div className="flex-1 flex items-center justify-center py-12">
                <RefreshCw className="h-6 w-6 animate-spin text-[#1b59f8]" />
              </div>
            ) : filteredRuns.length === 0 ? (
              <div className="flex-1 flex items-center justify-center py-16 text-center p-4">
                <div>
                  <Cpu className="mx-auto text-slate-200 mb-3 h-8 w-8" />
                  <p className="text-xs font-bold text-slate-450">No runs logged yet</p>
                </div>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto max-h-[60vh] divide-y divide-slate-50">
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

          {/* ── Right side: Log Details ─────────────────────────────────────────── */}
          <div className="lg:col-span-3 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-full">
            {selectedRun ? (
              <>
                {/* Header detail */}
                <div className="px-4 py-3.5 border-b border-slate-100 bg-slate-50/50">
                  <div className="flex items-center justify-between gap-4 flex-wrap">
                    <div>
                      <p className="text-xs font-bold text-slate-850">
                        {AGENT_LABELS[selectedRun.agent_name] ?? selectedRun.agent_name}
                        <span className="text-slate-400 font-mono font-bold"> #{selectedRun.id}</span>
                      </p>
                      <p className="text-[10px] text-slate-400 font-bold mt-0.5 leading-relaxed">
                        {new Date(selectedRun.created_at).toLocaleString()}
                        {selectedRun.duration_seconds !== undefined && ` · ${selectedRun.duration_seconds.toFixed(1)}s`}
                        {selectedRun.llm_model && ` · ${selectedRun.llm_model}`}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {selectedRun.status === "failed" && selectedRun.error_message && (
                        <span className="text-[10px] font-bold text-rose-600 bg-rose-50 border border-rose-100 px-2.5 py-0.5 rounded max-w-[200px] truncate" title={selectedRun.error_message}>
                          {selectedRun.error_message}
                        </span>
                      )}
                      <Badge variant={getStatusVariant(selectedRun.status)} className="capitalize text-[10px] py-0 px-2.5">
                        {selectedRun.status}
                      </Badge>
                    </div>
                  </div>
                  
                  {/* Status count filters */}
                  {logs.length > 0 && (
                    <div className="flex items-center gap-3.5 mt-3 border-t border-slate-100/50 pt-2 flex-wrap">
                      <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider">{logStats.total} entries</span>
                      {logStats.errors > 0 && (
                        <span className="text-[10px] font-extrabold text-rose-500 bg-rose-50 border border-rose-100 rounded px-1.5 py-0.5">{logStats.errors} error{logStats.errors !== 1 ? "s" : ""}</span>
                      )}
                      {logStats.warnings > 0 && (
                        <span className="text-[10px] font-extrabold text-amber-500 bg-amber-50 border border-amber-100 rounded px-1.5 py-0.5">{logStats.warnings} warning{logStats.warnings !== 1 ? "s" : ""}</span>
                      )}
                      
                      <div className="sm:ml-auto flex gap-1 rounded bg-slate-100/80 p-0.5 w-fit border border-slate-200">
                        {["all", "info", "warning", "error"].map(l => (
                          <button
                            key={l}
                            onClick={() => setFilterLevel(l)}
                            className={cn(
                              "px-2 py-0.5 text-[9px] font-bold rounded capitalize transition-all select-none",
                              filterLevel === l 
                                ? "bg-slate-800 text-white shadow-sm" 
                                : "text-slate-500 hover:text-slate-800"
                            )}
                          >
                            {l}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Logs listings viewport */}
                {logsLoading ? (
                  <div className="flex-1 flex items-center justify-center py-12">
                    <RefreshCw className="h-6 w-6 animate-spin text-[#1b59f8]" />
                  </div>
                ) : filteredLogs.length === 0 ? (
                  <div className="flex-1 flex items-center justify-center py-16 text-center p-4">
                    {logs.length === 0 ? (
                      <div>
                        <CheckCircle size={28} className="mx-auto text-slate-200 mb-2" />
                        <p className="text-xs font-bold text-slate-450">No logs generated for this run</p>
                      </div>
                    ) : (
                      <p className="text-xs font-bold text-slate-450">No {filterLevel} logs found</p>
                    )}
                  </div>
                ) : (
                  <div className="flex-1 overflow-y-auto max-h-[60vh] font-medium divide-y divide-slate-100">
                    {filteredLogs.map(log => (
                      <LogEntry key={log.id} log={log} />
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center py-16 text-center p-4">
                <div>
                  <Cpu className="mx-auto text-slate-200 mb-3 h-9 w-9" />
                  <p className="text-xs font-bold text-slate-450">Select an execution run to view logs</p>
                  <p className="text-[10px] text-slate-400 font-semibold mt-1">Select one of the runs from the left panel catalog</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function AgentLogsPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-slate-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-[#1b59f8] mr-2" />
        Loading Agent Logs...
      </div>
    }>
      <AgentLogsContent />
    </Suspense>
  );
}
