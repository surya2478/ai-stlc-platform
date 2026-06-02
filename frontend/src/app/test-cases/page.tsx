"use client";

import { useState, useEffect, useCallback } from "react";
import { TestTube2, Bot, CheckCircle, XCircle, RefreshCw, ChevronDown, ChevronUp, Zap, Download } from "lucide-react";
import { testCasesApi, scenariosApi, requirementsApi, projectsApi, type TestCase, type TestScenario, type Requirement, type Project } from "@/lib/api";

function PriorityBadge({ priority }: { priority: string }) {
  const map: Record<string, string> = {
    High: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
    Medium: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    Low: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  };
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${map[priority] ?? map.Medium}`}>{priority}</span>;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    draft: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
    pending_approval: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    approved: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
    rejected: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
    automated: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  };
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${map[status] ?? map.draft}`}>{status.replace(/_/g, " ")}</span>;
}

function TestCaseRow({ tc, onApprove }: { tc: TestCase; onApprove: (id: number, action: "approve" | "reject") => Promise<void> }) {
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleAction = async (action: "approve" | "reject") => {
    setLoading(true);
    try { await onApprove(tc.id, action); } finally { setLoading(false); }
  };

  return (
    <>
      <tr className="border-b hover:bg-muted/20 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <td className="px-4 py-3 text-xs font-mono text-muted-foreground whitespace-nowrap">{tc.test_case_id}</td>
        <td className="px-4 py-3">
          <p className="text-sm font-medium leading-snug">{tc.title}</p>
          {tc.test_type && <p className="text-xs text-muted-foreground capitalize mt-0.5">{tc.test_type}</p>}
        </td>
        <td className="px-4 py-3"><PriorityBadge priority={tc.priority} /></td>
        <td className="px-4 py-3"><StatusBadge status={tc.status} /></td>
        <td className="px-4 py-3 text-center">
          {tc.automation_candidate && <Zap className="h-4 w-4 text-amber-500 mx-auto" title="Automation candidate" />}
        </td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-1.5 justify-end">
            {tc.status === "draft" && (
              <>
                <button onClick={(e) => { e.stopPropagation(); handleAction("approve"); }} disabled={loading}
                  className="rounded p-1 hover:bg-emerald-100 dark:hover:bg-emerald-900/30 text-emerald-600" title="Approve">
                  <CheckCircle className="h-4 w-4" />
                </button>
                <button onClick={(e) => { e.stopPropagation(); handleAction("reject"); }} disabled={loading}
                  className="rounded p-1 hover:bg-red-100 dark:hover:bg-red-900/30 text-red-600" title="Reject">
                  <XCircle className="h-4 w-4" />
                </button>
              </>
            )}
            {expanded ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
          </div>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b bg-muted/10">
          <td colSpan={6} className="px-4 py-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 text-sm">
              {tc.bdd_scenario && (
                <div className="sm:col-span-2">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">BDD Scenario</p>
                  <pre className="rounded-lg bg-slate-900 text-slate-100 text-xs p-3 overflow-x-auto whitespace-pre-wrap">{tc.bdd_scenario}</pre>
                </div>
              )}
              {tc.preconditions?.length ? (
                <div>
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Preconditions</p>
                  <ul className="space-y-1">{tc.preconditions.map((p, i) => <li key={i} className="flex gap-2"><span className="text-primary shrink-0">*</span>{p}</li>)}</ul>
                </div>
              ) : null}
              {tc.steps?.length ? (
                <div className="sm:col-span-2">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Test Steps</p>
                  <div className="rounded-lg border overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-muted/50">
                        <tr>
                          <th className="px-3 py-2 text-left w-8">#</th>
                          <th className="px-3 py-2 text-left">Action</th>
                          <th className="px-3 py-2 text-left">Expected Result</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tc.steps.map((step, i) => (
                          <tr key={i} className="border-t">
                            <td className="px-3 py-2 text-muted-foreground">{step.step_number}</td>
                            <td className="px-3 py-2">{step.action}</td>
                            <td className="px-3 py-2 text-muted-foreground">{step.expected_result}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
              {tc.expected_result && (
                <div className="sm:col-span-2">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Overall Expected Result</p>
                  <p>{tc.expected_result}</p>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function exportToCSV(testCases: TestCase[]) {
  const headers = ["ID", "Title", "Priority", "Severity", "Type", "Status", "Automation", "Steps", "Expected Result", "BDD"];
  const rows = testCases.map((tc) => [
    tc.test_case_id, tc.title, tc.priority, tc.severity, tc.test_type ?? "",
    tc.status, tc.automation_candidate ? "Yes" : "No",
    tc.steps?.map((s) => `${s.step_number}. ${s.action}`).join(" | ") ?? "",
    tc.expected_result ?? "",
    tc.bdd_scenario ?? "",
  ]);
  const csv = [headers, ...rows]
    .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
    .join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "test-cases.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export default function TestCasesPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | null>(null);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [scenarios, setScenarios] = useState<TestScenario[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [loading, setLoading] = useState(false);
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentStatus, setAgentStatus] = useState<string>("");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<number[]>([]);
  const [showSelector, setShowSelector] = useState(false);

  useEffect(() => {
    projectsApi.list()
      .then((res) => {
        setProjects(res.data);
        const _urlP = typeof window !== "undefined" ? Number(new URLSearchParams(window.location.search).get("project")) || null : null;
        setSelectedProject(_urlP ?? (res.data[0]?.id ?? null));
      })
      .catch(() => {});
  }, []);

  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const [tcRes, scRes, reqRes] = await Promise.all([
        testCasesApi.list(selectedProject),
        scenariosApi.list(selectedProject),
        requirementsApi.list(selectedProject, "approved"),
      ]);
      setTestCases(tcRes.data);
      setScenarios(scRes.data);
      setRequirements(reqRes.data);
      setSelectedScenarioIds(scRes.data.map((s: TestScenario) => s.id));
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [selectedProject]);

  useEffect(() => { loadData(); }, [loadData]);

  const generateCases = async () => {
    if (!selectedProject) return;
    setAgentRunning(true);
    setAgentStatus("Agent 5 running -- generating detailed test cases...");
    try {
      const ids = selectedScenarioIds.length > 0 ? selectedScenarioIds : undefined;
      const reqIds = requirements.map((r) => r.id);
      const res = await testCasesApi.generateCases(selectedProject, ids, ids ? undefined : reqIds);
      const data = res.data as Record<string, unknown>;
      setAgentStatus(`Done: ${data.message} (${data.automation_candidates ?? 0} automation candidates)`);
      await loadData();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setAgentStatus(detail ? `Agent failed: ${detail}` : "Agent failed. Check backend logs.");
    } finally {
      setAgentRunning(false);
    }
  };

  const handleApprove = async (id: number, action: "approve" | "reject") => {
    await testCasesApi.approve(id, action);
    await loadData();
  };

  const filtered = testCases.filter((tc) => filterStatus === "all" || tc.status === filterStatus);
  const stats = {
    total: testCases.length,
    approved: testCases.filter((tc) => tc.status === "approved").length,
    automation: testCases.filter((tc) => tc.automation_candidate).length,
    draft: testCases.filter((tc) => tc.status === "draft").length,
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Test Cases</h1>
          <p className="text-sm text-muted-foreground mt-1">
            AI-generated step-by-step test cases with BDD scenarios and traceability
          </p>
        </div>
        <div className="flex items-center gap-2">
          {projects.length > 0 && (
            <select
              className="rounded-lg border bg-card px-3 py-2 text-sm focus:outline-none"
              value={selectedProject ?? ""}
              onChange={(e) => setSelectedProject(Number(e.target.value))}
            >
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          )}
          <button onClick={loadData} className="rounded-lg border p-2 hover:bg-muted">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {selectedProject && (
        <>
          {/* Stats */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: "Total", value: stats.total, color: "" },
              { label: "Approved", value: stats.approved, color: "text-emerald-600 dark:text-emerald-400" },
              { label: "Automation Ready", value: stats.automation, color: "text-amber-600 dark:text-amber-400" },
              { label: "Draft", value: stats.draft, color: "text-slate-500" },
            ].map((s) => (
              <div key={s.label} className="rounded-xl border bg-card p-4">
                <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
                <div className="text-xs text-muted-foreground">{s.label}</div>
              </div>
            ))}
          </div>

          {/* Agent Status Banner */}
          {(agentRunning || agentStatus) && (
            <div className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-sm ${
              agentRunning
                ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300"
                : agentStatus.startsWith("Done")
                ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
                : "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300"
            }`}>
              {agentRunning
                ? <RefreshCw className="h-4 w-4 animate-spin shrink-0" />
                : <Bot className="h-4 w-4 shrink-0" />}
              <span className="flex-1">{agentStatus}</span>
              {!agentRunning && (
                <button onClick={() => setAgentStatus("")} className="opacity-60 hover:opacity-100">
                  <XCircle className="h-4 w-4" />
                </button>
              )}
            </div>
          )}

          {/* Agent Panel */}
          <div className="rounded-xl border bg-card p-5 space-y-4">
            <div className="flex items-center justify-between gap-4">
              <h3 className="text-base font-semibold flex items-center gap-2">
                <Bot className="h-5 w-5 text-primary" />Generate Test Cases
              </h3>
              {scenarios.length > 0 && (
                <button
                  onClick={() => setShowSelector(!showSelector)}
                  className="flex items-center gap-1.5 rounded-lg border bg-muted/50 px-3 py-1.5 text-sm font-medium text-foreground hover:bg-muted transition-colors"
                >
                  <span className="inline-flex items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-bold w-6 h-6">
                    {selectedScenarioIds.length}
                  </span>
                  <span>scenario{selectedScenarioIds.length !== 1 ? "s" : ""} selected</span>
                  {showSelector ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
                </button>
              )}
            </div>

            {showSelector && scenarios.length > 0 && (
              <div className="rounded-lg border divide-y max-h-56 overflow-y-auto">
                <div className="flex items-center justify-between px-3 py-2 bg-muted/30 sticky top-0">
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Scenarios</span>
                  <div className="flex gap-3">
                    <button onClick={() => setSelectedScenarioIds(scenarios.map((s) => s.id))}
                      className="text-xs text-primary hover:underline font-medium">Select all</button>
                    <button onClick={() => setSelectedScenarioIds([])}
                      className="text-xs text-muted-foreground hover:text-foreground hover:underline">Clear</button>
                  </div>
                </div>
                {scenarios.map((sc) => (
                  <label key={sc.id} className="flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-muted/30 transition-colors">
                    <input
                      type="checkbox"
                      checked={selectedScenarioIds.includes(sc.id)}
                      onChange={() => setSelectedScenarioIds((prev) =>
                        prev.includes(sc.id) ? prev.filter((x) => x !== sc.id) : [...prev, sc.id]
                      )}
                      className="rounded border-gray-300 accent-primary"
                    />
                    <span className="text-xs font-mono font-medium text-primary/70 shrink-0 w-16">{sc.scenario_id}</span>
                    <span className="text-sm text-foreground truncate">{sc.title}</span>
                  </label>
                ))}
              </div>
            )}

            {scenarios.length === 0 && (
              <div className="rounded-lg border border-dashed bg-muted/20 px-4 py-5 text-center">
                <p className="text-sm font-medium text-foreground">No test scenarios found</p>
                <p className="text-xs text-muted-foreground mt-1">Go to <strong>Test Planning</strong> and generate scenarios first, then come back here.</p>
              </div>
            )}

            <div className="flex gap-2 flex-wrap">
              <button
                onClick={generateCases}
                disabled={agentRunning || scenarios.length === 0}
                title={scenarios.length === 0 ? "No scenarios found — generate scenarios in Test Planning first" : undefined}
                className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <TestTube2 className="h-4 w-4" />Generate Test Cases
              </button>
              {testCases.length > 0 && (
                <button
                  onClick={() => exportToCSV(filtered)}
                  className="flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium hover:bg-muted"
                >
                  <Download className="h-4 w-4" />Export CSV
                </button>
              )}
            </div>
          </div>

          {/* Filter Bar */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex gap-1 rounded-lg border bg-card p-1">
              {["all", "draft", "approved", "rejected"].map((s) => (
                <button
                  key={s}
                  onClick={() => setFilterStatus(s)}
                  className={`rounded-md px-3 py-1 text-xs font-medium capitalize transition-all ${
                    filterStatus === s ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {s.replace(/_/g, " ")}
                </button>
              ))}
            </div>
            <span className="text-xs text-muted-foreground ml-auto">
              {filtered.length} test case{filtered.length !== 1 ? "s" : ""}
            </span>
          </div>

          {/* Table */}
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="rounded-xl border border-dashed p-12 text-center">
              <TestTube2 className="mx-auto h-10 w-10 text-muted-foreground mb-3 opacity-40" />
              <p className="font-medium text-muted-foreground">No test cases yet</p>
              <p className="text-sm text-muted-foreground mt-1">
                Generate scenarios in Test Planning, then generate test cases here
              </p>
            </div>
          ) : (
            <div className="rounded-xl border overflow-hidden">
              <table className="w-full">
                <thead className="bg-muted/50 border-b">
                  <tr>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-muted-foreground">ID</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-muted-foreground">Title</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-muted-foreground">Priority</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-muted-foreground">Status</th>
                    <th className="px-4 py-2.5 text-center text-xs font-semibold text-muted-foreground">
                      <Zap className="h-3.5 w-3.5 mx-auto" title="Automation candidate" />
                    </th>
                    <th className="px-4 py-2.5 text-right text-xs font-semibold text-muted-foreground">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((tc) => (
                    <TestCaseRow key={tc.id} tc={tc} onApprove={handleApprove} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
