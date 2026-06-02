"use client";
import { useState, useEffect, useCallback } from "react";
import {
  executionApi, testCasesApi, projectsApi,
  type ExecutionRun, type ExecutionResult, type TestCase, type Project,
} from "@/lib/api";
import {
  PlayCircle, Bot, CheckCircle, XCircle, Clock, ChevronDown, ChevronUp,
  AlertTriangle, SkipForward, Layers, BarChart2,
} from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

function RunStatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending: "bg-gray-100 text-gray-600",
    in_progress: "bg-blue-100 text-blue-700",
    completed: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
    cancelled: "bg-orange-100 text-orange-700",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${map[status] ?? "bg-gray-100 text-gray-600"}`}>
      {status.replace("_", " ")}
    </span>
  );
}

function ResultStatusIcon({ status }: { status: string }) {
  if (status === "passed") return <CheckCircle size={14} className="text-green-500 shrink-0" />;
  if (status === "failed") return <XCircle size={14} className="text-red-500 shrink-0" />;
  if (status === "skipped") return <SkipForward size={14} className="text-gray-400 shrink-0" />;
  return <AlertTriangle size={14} className="text-orange-400 shrink-0" />;
}

function PassRate({ passed, total }: { passed: number; total: number }) {
  const pct = total > 0 ? Math.round((passed / total) * 100) : 0;
  const color = pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-yellow-400" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-xs font-semibold ${pct >= 80 ? "text-green-600" : pct >= 50 ? "text-yellow-600" : "text-red-600"}`}>
        {pct}%
      </span>
    </div>
  );
}

function RunCard({ run, onSelect, selected }: { run: ExecutionRun; onSelect: (id: number) => void; selected: boolean }) {
  return (
    <div
      onClick={() => onSelect(run.id)}
      className={`bg-white rounded-xl border cursor-pointer transition-all shadow-sm p-4 ${
        selected ? "border-blue-400 ring-2 ring-blue-100" : "border-gray-200 hover:border-blue-200"
      }`}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono text-gray-400">{run.execution_id}</span>
            <RunStatusBadge status={run.status} />
          </div>
          <p className="text-sm font-semibold text-gray-800 truncate">{run.suite_name || "Unnamed Suite"}</p>
          <p className="text-xs text-gray-400">{run.environment ?? "staging"} · {new Date(run.created_at).toLocaleString()}</p>
        </div>
      </div>
      <PassRate passed={run.passed} total={run.total_tests} />
      <div className="flex gap-4 mt-2 text-xs">
        <span className="text-green-600 font-medium">✓ {run.passed} passed</span>
        <span className="text-red-500 font-medium">✗ {run.failed} failed</span>
        <span className="text-gray-400">— {run.skipped} skipped</span>
        <span className="text-gray-400 ml-auto">{run.total_tests} total</span>
      </div>
    </div>
  );
}

function ResultRow({ result }: { result: ExecutionResult }) {
  const [expanded, setExpanded] = useState(false);
  const durationSec = result.duration_ms ? (result.duration_ms / 1000).toFixed(2) : null;

  return (
    <div className="border border-gray-100 rounded-lg overflow-hidden">
      <div
        onClick={() => result.status === "failed" && setExpanded(!expanded)}
        className={`flex items-center gap-3 px-4 py-3 ${result.status === "failed" ? "cursor-pointer hover:bg-red-50" : "bg-white"}`}
      >
        <ResultStatusIcon status={result.status} />
        <span className="text-sm text-gray-700 flex-1 truncate">{result.test_name}</span>
        {durationSec && (
          <span className="text-xs text-gray-400 shrink-0 flex items-center gap-1">
            <Clock size={11} /> {durationSec}s
          </span>
        )}
        {result.status === "failed" && (
          <span className="text-gray-400">{expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</span>
        )}
      </div>
      {expanded && result.status === "failed" && (
        <div className="bg-red-50 border-t border-red-100 px-4 py-3 space-y-2">
          {result.error_message && (
            <div>
              <p className="text-xs font-semibold text-red-700 mb-1">Error</p>
              <code className="text-xs text-red-600 bg-red-100 px-2 py-1 rounded block">{result.error_message}</code>
            </div>
          )}
          {result.stack_trace && (
            <div>
              <p className="text-xs font-semibold text-red-700 mb-1">Stack Trace</p>
              <pre className="text-xs text-red-500 bg-red-100 p-2 rounded overflow-x-auto whitespace-pre-wrap">{result.stack_trace}</pre>
            </div>
          )}
          {result.logs && result.logs.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-600 mb-1">Logs</p>
              <div className="space-y-0.5">
                {result.logs.map((log, i) => (
                  <p key={i} className="text-xs text-gray-500 font-mono">{log}</p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ExecutionPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | null>(null);
  const [runs, setRuns] = useState<ExecutionRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [results, setResults] = useState<ExecutionResult[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(false);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [agentError, setAgentError] = useState<string | null>(null);
  const [selectedTcIds, setSelectedTcIds] = useState<Set<number>>(new Set());
  const [environment, setEnvironment] = useState("staging");
  const [showAgentPanel, setShowAgentPanel] = useState(false);
  const [filterResult, setFilterResult] = useState<string>("all");

  useEffect(() => {
    projectsApi.list()
      .then((r) => {
        setProjects(r.data);
        const _urlP = typeof window !== "undefined" ? Number(new URLSearchParams(window.location.search).get("project")) || null : null;
        setSelectedProject(_urlP ?? (r.data[0]?.id ?? null));
      })
      .catch((e) => console.error("[Projects] Failed to load:", e?.response?.status));
  }, []);

  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const [runsRes, casesRes] = await Promise.all([
        executionApi.listRuns(selectedProject),
        testCasesApi.list(selectedProject, { status: "approved" }),
      ]);
      setRuns(runsRes.data);
      setTestCases(casesRes.data);
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => { loadData(); }, [loadData]);

  const loadResults = useCallback(async (runId: number) => {
    setResultsLoading(true);
    try {
      const res = await executionApi.getResults(runId);
      setResults(res.data);
    } finally {
      setResultsLoading(false);
    }
  }, []);

  const handleSelectRun = (id: number) => {
    setSelectedRunId(id);
    loadResults(id);
  };

  const toggleTc = (id: number) => {
    setSelectedTcIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleRunTests = async () => {
    if (!selectedProject || selectedTcIds.size === 0) return;
    setAgentStatus("running");
    setAgentError(null);
    try {
      const res = await executionApi.runTests(selectedProject, Array.from(selectedTcIds), environment);
      setAgentStatus("done");
      setSelectedTcIds(new Set());
      setShowAgentPanel(false);
      await loadData();
      if (res.data.execution_run_id) {
        setSelectedRunId(res.data.execution_run_id);
        await loadResults(res.data.execution_run_id);
      }
    } catch (e: unknown) {
      setAgentStatus("error");
      const err = e as { response?: { data?: { detail?: string } } };
      setAgentError(err?.response?.data?.detail ?? "Agent failed");
    }
  };

  const selectedRun = runs.find((r) => r.id === selectedRunId);
  const filteredResults = filterResult === "all" ? results : results.filter((r) => r.status === filterResult);

  const totalStats = {
    runs: runs.length,
    passed: runs.reduce((a, r) => a + r.passed, 0),
    failed: runs.reduce((a, r) => a + r.failed, 0),
    avgPassRate: runs.length > 0
      ? Math.round(runs.reduce((a, r) => a + (r.total_tests > 0 ? r.passed / r.total_tests : 0), 0) / runs.length * 100)
      : 0,
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-100 rounded-lg">
            <PlayCircle size={22} className="text-blue-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Test Execution</h1>
            <p className="text-sm text-gray-500">AI-driven test execution with pass/fail analysis — Agent 8</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedProject ?? ""}
            onChange={(e) => { setSelectedProject(Number(e.target.value)); setSelectedRunId(null); setResults([]); }}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-300"
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button
            onClick={() => setShowAgentPanel(!showAgentPanel)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700"
          >
            <Bot size={16} /> Run Tests
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Total Runs", value: totalStats.runs, color: "text-gray-800" },
          { label: "Total Passed", value: totalStats.passed, color: "text-green-600" },
          { label: "Total Failed", value: totalStats.failed, color: "text-red-500" },
          { label: "Avg Pass Rate", value: `${totalStats.avgPassRate}%`, color: totalStats.avgPassRate >= 80 ? "text-green-600" : "text-yellow-600" },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
            <p className="text-xs text-gray-500 mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Agent Panel */}
      {showAgentPanel && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Bot size={18} className="text-blue-600" />
            <h2 className="font-semibold text-blue-900">Run Test Suite</h2>
          </div>

          {/* Environment */}
          <div className="flex gap-3 mb-4">
            {["staging", "development", "production"].map((env) => (
              <button
                key={env}
                onClick={() => setEnvironment(env)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                  environment === env
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-white text-gray-600 border-gray-200 hover:border-blue-300"
                }`}
              >
                {env}
              </button>
            ))}
          </div>

          {testCases.length === 0 ? (
            <p className="text-sm text-blue-700 bg-blue-100 rounded-lg p-3">
              No approved test cases found. Approve test cases in the Test Cases module first.
            </p>
          ) : (
            <>
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm font-medium text-blue-800">Select test cases ({testCases.length} approved)</p>
                <button
                  onClick={() => setSelectedTcIds(
                    selectedTcIds.size === testCases.length ? new Set() : new Set(testCases.map((t) => t.id))
                  )}
                  className="text-xs text-blue-600 hover:underline"
                >
                  {selectedTcIds.size === testCases.length ? "Deselect all" : "Select all"}
                </button>
              </div>
              <div className="max-h-48 overflow-y-auto space-y-1 mb-4">
                {testCases.map((tc) => (
                  <label key={tc.id} className="flex items-center gap-2 p-2 bg-white rounded-lg border border-blue-100 cursor-pointer hover:border-blue-300">
                    <input
                      type="checkbox"
                      checked={selectedTcIds.has(tc.id)}
                      onChange={() => toggleTc(tc.id)}
                      className="accent-blue-600"
                    />
                    <span className="text-xs font-mono text-blue-400 shrink-0">{tc.test_case_id}</span>
                    <span className="text-sm text-gray-700 truncate">{tc.title}</span>
                    <span className={`ml-auto text-xs ${tc.automation_candidate ? "text-violet-500" : "text-gray-300"}`}>
                      {tc.automation_candidate ? "🤖" : ""}
                    </span>
                  </label>
                ))}
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleRunTests}
                  disabled={selectedTcIds.size === 0 || agentStatus === "running"}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {agentStatus === "running" ? (
                    <><span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" /> Running {selectedTcIds.size} tests...</>
                  ) : (
                    <><PlayCircle size={16} /> Run {selectedTcIds.size} Test{selectedTcIds.size !== 1 ? "s" : ""}</>
                  )}
                </button>
                {agentStatus === "done" && (
                  <span className="flex items-center gap-1 text-sm text-green-600">
                    <CheckCircle size={16} /> Execution complete!
                  </span>
                )}
                {agentStatus === "error" && (
                  <span className="flex items-center gap-1 text-sm text-red-600">
                    <AlertTriangle size={16} /> {agentError}
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* Split layout: Run list + Results */}
      <div className="grid grid-cols-5 gap-4">
        {/* Left: Run list */}
        <div className="col-span-2 space-y-3">
          <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <BarChart2 size={14} /> Execution Runs
          </h2>
          {loading ? (
            <div className="flex justify-center py-8">
              <span className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" />
            </div>
          ) : runs.length === 0 ? (
            <div className="text-center py-10 bg-white rounded-xl border border-gray-100">
              <PlayCircle size={32} className="mx-auto text-gray-200 mb-2" />
              <p className="text-sm text-gray-400">No runs yet</p>
            </div>
          ) : (
            runs.map((run) => (
              <RunCard key={run.id} run={run} onSelect={handleSelectRun} selected={run.id === selectedRunId} />
            ))
          )}
        </div>

        {/* Right: Results detail */}
        <div className="col-span-3 space-y-3">
          <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <Layers size={14} /> Test Results
            {selectedRun && (
              <span className="ml-auto font-normal text-gray-400 text-xs">{selectedRun.suite_name}</span>
            )}
          </h2>

          {selectedRunId ? (
            <>
              {/* Result filter */}
              <div className="flex gap-2">
                {["all", "passed", "failed", "skipped"].map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilterResult(f)}
                    className={`px-2.5 py-1 text-xs rounded-lg font-medium transition-colors ${
                      filterResult === f ? "bg-gray-800 text-white" : "bg-white text-gray-600 border border-gray-200 hover:border-gray-400"
                    }`}
                  >
                    {f.charAt(0).toUpperCase() + f.slice(1)}
                  </button>
                ))}
              </div>

              {resultsLoading ? (
                <div className="flex justify-center py-8">
                  <span className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" />
                </div>
              ) : filteredResults.length === 0 ? (
                <div className="text-center py-8 bg-white rounded-xl border border-gray-100">
                  <p className="text-sm text-gray-400">No results in this filter</p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  {filteredResults.map((r) => (
                    <ResultRow key={r.id} result={r} />
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="flex items-center justify-center h-40 bg-white rounded-xl border border-dashed border-gray-200">
              <p className="text-sm text-gray-400">Select a run on the left to see results</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
