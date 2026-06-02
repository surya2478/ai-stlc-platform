"use client";
import { useState, useEffect, useCallback } from "react";
import {
  defectsApi, executionApi, projectsApi,
  type DefectDraft, type ExecutionRun, type ExecutionResult, type Project,
} from "@/lib/api";
import {
  Bug, Bot, CheckCircle, XCircle, ChevronDown, ChevronUp,
  AlertTriangle, Layers, ExternalLink, ShieldAlert,
} from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: string }) {
  const map: Record<string, string> = {
    Critical: "bg-red-100 text-red-700 border-red-200",
    High: "bg-orange-100 text-orange-700 border-orange-200",
    Medium: "bg-yellow-100 text-yellow-700 border-yellow-200",
    Low: "bg-gray-100 text-gray-600 border-gray-200",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${map[severity] ?? "bg-gray-100 text-gray-600 border-gray-200"}`}>
      {severity}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    draft: "bg-gray-100 text-gray-600",
    pending_approval: "bg-yellow-100 text-yellow-700",
    approved: "bg-green-100 text-green-700",
    rejected: "bg-red-100 text-red-700",
    pushed_to_jira: "bg-blue-100 text-blue-700",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${map[status] ?? "bg-gray-100 text-gray-600"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function ClassificationBadge({ cls }: { cls: string }) {
  const map: Record<string, string> = {
    product_defect: "bg-red-50 text-red-600",
    automation_issue: "bg-violet-50 text-violet-600",
    environment_issue: "bg-blue-50 text-blue-600",
    test_data_issue: "bg-orange-50 text-orange-600",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs ${map[cls] ?? "bg-gray-50 text-gray-600"}`}>
      {cls.replace(/_/g, " ")}
    </span>
  );
}

function StepList({ steps }: { steps: string[] }) {
  return (
    <ol className="list-decimal list-inside space-y-1">
      {steps.map((s, i) => (
        <li key={i} className="text-xs text-gray-600">{s}</li>
      ))}
    </ol>
  );
}

function DefectCard({
  defect,
  onApprove,
  onReject,
  onPushToJira,
}: {
  defect: DefectDraft;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  onPushToJira: (id: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [confirming, setConfirming] = useState<"approve" | "reject" | null>(null);
  const [pushing, setPushing] = useState(false);

  const handleJiraPush = async () => {
    setPushing(true);
    try { await onPushToJira(defect.id); } finally { setPushing(false); }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <span className="text-xs font-mono text-gray-400">{defect.defect_id}</span>
              <SeverityBadge severity={defect.severity} />
              <StatusBadge status={defect.status} />
              <ClassificationBadge cls={defect.classification} />
            </div>
            <p className="text-sm font-semibold text-gray-800 leading-snug">{defect.summary}</p>
            {defect.description && (
              <p className="text-xs text-gray-500 mt-1 line-clamp-2">{defect.description}</p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {defect.status === "draft" && (
              <>
                {confirming === "approve" ? (
                  <div className="flex gap-1">
                    <button onClick={() => { onApprove(defect.id); setConfirming(null); }}
                      className="px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700">Confirm</button>
                    <button onClick={() => setConfirming(null)}
                      className="px-2 py-1 text-xs bg-gray-200 rounded">Cancel</button>
                  </div>
                ) : confirming === "reject" ? (
                  <div className="flex gap-1">
                    <button onClick={() => { onReject(defect.id); setConfirming(null); }}
                      className="px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700">Confirm</button>
                    <button onClick={() => setConfirming(null)}
                      className="px-2 py-1 text-xs bg-gray-200 rounded">Cancel</button>
                  </div>
                ) : (
                  <>
                    <button onClick={() => setConfirming("approve")}
                      className="flex items-center gap-1 px-2 py-1 text-xs bg-green-50 text-green-700 border border-green-200 rounded hover:bg-green-100">
                      <CheckCircle size={12} /> Approve
                    </button>
                    <button onClick={() => setConfirming("reject")}
                      className="flex items-center gap-1 px-2 py-1 text-xs bg-red-50 text-red-700 border border-red-200 rounded hover:bg-red-100">
                      <XCircle size={12} /> Reject
                    </button>
                  </>
                )}
              </>
            )}
            {defect.status === "approved" && (
              <button
                onClick={handleJiraPush}
                disabled={pushing}
                className="flex items-center gap-1 px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {pushing ? (
                  <span className="animate-spin inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full" />
                ) : (
                  <ExternalLink size={12} />
                )}
                Push to Jira
              </button>
            )}
            <button onClick={() => setExpanded(!expanded)} className="text-gray-400 hover:text-gray-600">
              {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
          </div>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-100 bg-gray-50 px-4 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {/* Expected vs Actual */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Expected Result</p>
              <p className="text-xs text-gray-600 bg-white border border-gray-100 rounded p-2">{defect.expected_result || "—"}</p>
            </div>
            <div>
              <p className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-1">Actual Result</p>
              <p className="text-xs text-gray-600 bg-red-50 border border-red-100 rounded p-2">{defect.actual_result || "—"}</p>
            </div>
          </div>

          {/* Steps to Reproduce */}
          {defect.steps_to_reproduce && defect.steps_to_reproduce.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Steps to Reproduce</p>
              <StepList steps={defect.steps_to_reproduce} />
            </div>
          )}

          {/* Root Cause */}
          {defect.root_cause_hypothesis && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Root Cause Hypothesis</p>
              <p className="text-xs text-gray-600 bg-amber-50 border border-amber-100 rounded p-2 italic">{defect.root_cause_hypothesis}</p>
            </div>
          )}

          {/* Meta */}
          <div className="flex gap-4 text-xs text-gray-400">
            <span>Priority: <span className="font-medium text-gray-600">{defect.priority}</span></span>
            <span>Severity: <span className="font-medium text-gray-600">{defect.severity}</span></span>
            <span>Jira-ready: <span className="font-medium text-gray-600">{defect.jira_ready ? "Yes" : "No"}</span></span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function DefectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | null>(null);
  const [defects, setDefects] = useState<DefectDraft[]>([]);
  const [runs, setRuns] = useState<ExecutionRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [failedResults, setFailedResults] = useState<ExecutionResult[]>([]);
  const [selectedResultIds, setSelectedResultIds] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [agentError, setAgentError] = useState<string | null>(null);
  const [showAgentPanel, setShowAgentPanel] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [filterSeverity, setFilterSeverity] = useState<string>("all");

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
      const [defectsRes, runsRes] = await Promise.all([
        defectsApi.list(selectedProject),
        executionApi.listRuns(selectedProject, { status: "completed" }),
      ]);
      setDefects(defectsRes.data);
      setRuns(runsRes.data);
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSelectRun = async (runId: number) => {
    setSelectedRunId(runId);
    const res = await executionApi.getResults(runId);
    setFailedResults(res.data.filter((r) => r.status === "failed"));
    setSelectedResultIds(new Set());
  };

  const toggleResult = (id: number) => {
    setSelectedResultIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleAnalyse = async () => {
    if (!selectedProject || selectedResultIds.size === 0) return;
    setAgentStatus("running");
    setAgentError(null);
    try {
      const res = await defectsApi.analyseDefects(selectedProject, Array.from(selectedResultIds));
      const data = res.data as { defect_ids?: number[]; message?: string };
      const count = data.defect_ids?.length ?? 0;
      if (count === 0) {
        setAgentStatus("error");
        setAgentError("Agent ran but generated 0 defects — the LLM may have failed to parse. Check backend logs.");
      } else {
        setAgentStatus("done");
        setSelectedResultIds(new Set());
        await loadData();
      }
    } catch (e: unknown) {
      setAgentStatus("error");
      const err = e as { response?: { data?: { detail?: string } } };
      setAgentError(err?.response?.data?.detail ?? "Agent failed");
    }
  };

  const handleApprove = async (id: number) => { await defectsApi.approve(id, "approve"); await loadData(); };
  const handleReject = async (id: number) => { await defectsApi.approve(id, "reject"); await loadData(); };
  const handlePushToJira = async (id: number) => { await defectsApi.pushToJira(id); await loadData(); };

  // Filtered defects
  let filtered = defects;
  if (filterStatus !== "all") filtered = filtered.filter((d) => d.status === filterStatus);
  if (filterSeverity !== "all") filtered = filtered.filter((d) => d.severity === filterSeverity);

  const stats = {
    total: defects.length,
    critical: defects.filter((d) => d.severity === "Critical").length,
    high: defects.filter((d) => d.severity === "High").length,
    pushed: defects.filter((d) => d.status === "pushed_to_jira").length,
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-red-100 rounded-lg">
            <Bug size={22} className="text-red-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Defect Management</h1>
            <p className="text-sm text-gray-500">AI-generated defect reports with Jira integration — Agent 9</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedProject ?? ""}
            onChange={(e) => setSelectedProject(Number(e.target.value))}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-red-300"
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button
            onClick={() => setShowAgentPanel(!showAgentPanel)}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700"
          >
            <Bot size={16} /> Analyse Failures
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Total Defects", value: stats.total, color: "text-gray-800" },
          { label: "Critical", value: stats.critical, color: "text-red-600" },
          { label: "High", value: stats.high, color: "text-orange-500" },
          { label: "Pushed to Jira", value: stats.pushed, color: "text-blue-600" },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
            <p className="text-xs text-gray-500 mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Agent Panel */}
      {showAgentPanel && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <ShieldAlert size={18} className="text-red-600" />
            <h2 className="font-semibold text-red-900">Analyse Failed Tests</h2>
          </div>

          {runs.length === 0 ? (
            <p className="text-sm text-red-700 bg-red-100 rounded-lg p-3">
              No completed execution runs found. Run tests in the Execution module first.
            </p>
          ) : (
            <>
              {/* Run selector */}
              <div className="mb-4">
                <p className="text-sm font-medium text-red-800 mb-2">Select an execution run</p>
                <div className="flex flex-wrap gap-2">
                  {runs.map((run) => (
                    <button
                      key={run.id}
                      onClick={() => handleSelectRun(run.id)}
                      className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                        selectedRunId === run.id
                          ? "bg-red-600 text-white border-red-600"
                          : "bg-white text-gray-600 border-gray-200 hover:border-red-300"
                      }`}
                    >
                      {run.execution_id} — {run.failed} failed
                    </button>
                  ))}
                </div>
              </div>

              {/* Failed results */}
              {selectedRunId && failedResults.length === 0 && (
                <p className="text-sm text-green-700 bg-green-50 rounded-lg p-3">
                  No failed tests in this run — nothing to analyse!
                </p>
              )}
              {selectedRunId && failedResults.length > 0 && (
                <>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-medium text-red-800">{failedResults.length} failed test(s)</p>
                    <button
                      onClick={() => setSelectedResultIds(
                        selectedResultIds.size === failedResults.length
                          ? new Set()
                          : new Set(failedResults.map((r) => r.id))
                      )}
                      className="text-xs text-red-600 hover:underline"
                    >
                      {selectedResultIds.size === failedResults.length ? "Deselect all" : "Select all"}
                    </button>
                  </div>
                  <div className="max-h-48 overflow-y-auto space-y-1 mb-4">
                    {failedResults.map((r) => (
                      <label key={r.id} className="flex items-start gap-2 p-2 bg-white rounded-lg border border-red-100 cursor-pointer hover:border-red-300">
                        <input
                          type="checkbox"
                          checked={selectedResultIds.has(r.id)}
                          onChange={() => toggleResult(r.id)}
                          className="accent-red-600 mt-0.5"
                        />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-gray-700 truncate">{r.test_name}</p>
                          {r.error_message && (
                            <p className="text-xs text-red-500 truncate">{r.error_message}</p>
                          )}
                        </div>
                      </label>
                    ))}
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={handleAnalyse}
                      disabled={selectedResultIds.size === 0 || agentStatus === "running"}
                      className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {agentStatus === "running" ? (
                        <><span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" /> Analysing...</>
                      ) : (
                        <><Bot size={16} /> Analyse {selectedResultIds.size} Failure{selectedResultIds.size !== 1 ? "s" : ""}</>
                      )}
                    </button>
                    {agentStatus === "done" && (
                      <span className="flex items-center gap-1 text-sm text-green-600">
                        <CheckCircle size={16} /> Defect drafts created!
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
            </>
          )}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="flex gap-1">
          {["all", "draft", "approved", "pushed_to_jira", "rejected"].map((s) => (
            <button key={s} onClick={() => setFilterStatus(s)}
              className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${
                filterStatus === s ? "bg-gray-800 text-white" : "bg-white text-gray-600 border border-gray-200 hover:border-gray-400"
              }`}>
              {s === "all" ? "All Status" : s.replace(/_/g, " ")}
            </button>
          ))}
        </div>
        <div className="flex gap-1 ml-2">
          {["all", "Critical", "High", "Medium", "Low"].map((sv) => (
            <button key={sv} onClick={() => setFilterSeverity(sv)}
              className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${
                filterSeverity === sv ? "bg-gray-800 text-white" : "bg-white text-gray-600 border border-gray-200 hover:border-gray-400"
              }`}>
              {sv === "all" ? "All Severity" : sv}
            </button>
          ))}
        </div>
      </div>

      {/* Defects List */}
      {loading ? (
        <div className="flex justify-center py-12">
          <span className="animate-spin w-8 h-8 border-2 border-red-500 border-t-transparent rounded-full" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-xl border border-gray-100">
          <Bug size={40} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500 font-medium">No defects found</p>
          <p className="text-sm text-gray-400 mt-1">Run test execution, then use Analyse Failures to auto-generate defect reports</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((d) => (
            <DefectCard key={d.id} defect={d} onApprove={handleApprove} onReject={handleReject} onPushToJira={handlePushToJira} />
          ))}
        </div>
      )}
    </div>
  );
}
