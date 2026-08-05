"use client";

import { useState, useEffect, useCallback, useMemo, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  defectsApi, executionApi, projectsApi,
  type DefectDraft, type ExecutionRun, type ExecutionResult,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Bug, Bot, CheckCircle, XCircle, ChevronDown, ChevronUp,
  AlertTriangle, Layers, ExternalLink, ShieldAlert, X, RefreshCw, Loader2
} from "lucide-react";
import { useAIAction } from "@/hooks/useAIAction";
import { AI_PROCESSING_STAGES } from "@/lib/ai-processing-stages";

// Status Chip Variant Mapping
function getStatusVariant(status: string | null | undefined): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  if (!status) return "outline";
  const s = status.toLowerCase();
  if (["approved", "completed", "yes"].includes(s)) return "success";
  if (["rejected", "no"].includes(s)) return "destructive";
  if (["pending_approval", "running", "queued", "draft"].includes(s)) return "warning";
  if (["pushed_to_jira"].includes(s)) return "info";
  return "outline";
}

function getSeverityVariant(severity: string | null | undefined): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  if (!severity) return "outline";
  const s = severity.toLowerCase();
  if (s === "critical") return "destructive";
  if (s === "high") return "warning";
  if (s === "medium") return "info";
  return "secondary";
}

function getClassificationVariant(cls: string | null | undefined): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  if (!cls) return "outline";
  const s = cls.toLowerCase();
  if (s === "product_defect") return "destructive";
  if (s === "automation_issue") return "purple";
  if (s === "environment_issue") return "info";
  if (s === "test_data_issue") return "warning";
  return "secondary";
}

function StepList({ steps }: { steps: string[] }) {
  return (
    <ol className="list-decimal list-inside space-y-1 bg-gray-50 border rounded-lg p-3">
      {steps.map((s, i) => (
        <li key={i} className="text-xs text-gray-600 font-medium leading-relaxed">{s}</li>
      ))}
    </ol>
  );
}

function messageFromError(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

function DefectRow({
  defect,
  onApprove,
  onReject,
  onPushToJira,
}: {
  defect: DefectDraft;
  onApprove: (id: number) => Promise<void>;
  onReject: (id: number) => Promise<void>;
  onPushToJira: (id: number) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [confirming, setConfirming] = useState<"approve" | "reject" | null>(null);
  const [pushing, setPushing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Every action here hits the backend and can fail for reasons the user must see
  // (e.g. Jira rejecting the credentials). Without this the rejection escapes as an
  // unhandled promise and the user only gets a dev-overlay stack trace.
  const runAction = async (action: () => Promise<void>, fallback: string) => {
    setActionError(null);
    try {
      await action();
    } catch (e: unknown) {
      setActionError(messageFromError(e, fallback));
    }
  };

  const handleJiraPush = async () => {
    setPushing(true);
    try {
      await runAction(() => onPushToJira(defect.id), "Push to Jira failed");
    } finally {
      setPushing(false);
    }
  };

  return (
    <div className={cn(
      "bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden transition-all duration-200 hover:border-gray-300",
      expanded && "ring-1 ring-[#B71920]/10"
    )}>
      <div className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex-1 min-w-0" onClick={() => setExpanded(!expanded)}>
          <div className="flex flex-wrap items-center gap-2 mb-1.5 cursor-pointer">
            <span className="text-[10px] font-mono font-bold text-gray-400">{defect.defect_id}</span>
            <Badge variant={getSeverityVariant(defect.severity)}>{defect.severity}</Badge>
            <Badge variant={getStatusVariant(defect.status)} className="capitalize">{defect.status.replace(/_/g, " ")}</Badge>
            <Badge variant={getClassificationVariant(defect.classification)} className="capitalize">{defect.classification.replace(/_/g, " ")}</Badge>
          </div>
          <h4 className="text-xs font-bold text-gray-800 leading-snug cursor-pointer hover:text-[#B71920] transition-colors">{defect.summary}</h4>
          {defect.description && !expanded && (
            <p className="text-[11px] text-gray-500 mt-1 line-clamp-1">{defect.description}</p>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0 self-end md:self-center">
          {defect.status === "draft" && (
            <div className="flex items-center gap-1.5">
              {confirming === "approve" ? (
                <div className="flex gap-1">
                  <Button onClick={() => { void runAction(() => onApprove(defect.id), "Approve failed"); setConfirming(null); }} size="sm" variant="default" className="h-7 text-[10px] bg-emerald-600 hover:bg-emerald-700">Confirm</Button>
                  <Button onClick={() => setConfirming(null)} size="sm" variant="outline" className="h-7 text-[10px] border-gray-200 text-gray-600">Cancel</Button>
                </div>
              ) : confirming === "reject" ? (
                <div className="flex gap-1">
                  <Button onClick={() => { void runAction(() => onReject(defect.id), "Reject failed"); setConfirming(null); }} size="sm" variant="default" className="h-7 text-[10px] bg-rose-600 hover:bg-rose-700">Confirm</Button>
                  <Button onClick={() => setConfirming(null)} size="sm" variant="outline" className="h-7 text-[10px] border-gray-200 text-gray-600">Cancel</Button>
                </div>
              ) : (
                <>
                  <Button onClick={() => setConfirming("approve")} size="sm" variant="outline" className="h-7 text-[10px] text-emerald-600 border-emerald-100 hover:bg-emerald-50 bg-emerald-50/20 font-bold">
                    <CheckCircle className="h-3 w-3 mr-1" /> Approve
                  </Button>
                  <Button onClick={() => setConfirming("reject")} size="sm" variant="outline" className="h-7 text-[10px] text-rose-600 border-rose-100 hover:bg-rose-50 bg-rose-50/20 font-bold">
                    <XCircle className="h-3 w-3 mr-1" /> Reject
                  </Button>
                </>
              )}
            </div>
          )}
          {defect.status === "approved" && (
            <Button
              onClick={handleJiraPush}
              disabled={pushing}
              variant="default"
              size="sm"
              className="h-8 text-[11px] font-bold"
            >
              {pushing ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
              ) : (
                <ExternalLink className="h-3.5 w-3.5 mr-1" />
              )}
              Push to Jira
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => setExpanded(!expanded)} className="h-8 w-8 p-0 border-gray-200">
            {expanded ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
          </Button>
        </div>
      </div>

      {actionError && (
        <div className="mx-4 mb-4 -mt-1 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3">
          <AlertTriangle className="h-3.5 w-3.5 text-rose-500 shrink-0 mt-px" />
          <p className="text-[11px] font-semibold text-rose-700 leading-relaxed">{actionError}</p>
        </div>
      )}

      {expanded && (
        <div className="border-t border-gray-100 bg-gray-50/30 p-5 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-1">Expected Result</label>
              <p className="text-xs text-gray-600 bg-white border border-gray-200 rounded-lg p-3 leading-relaxed font-semibold">{defect.expected_result || "—"}</p>
            </div>
            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-rose-500 block mb-1">Actual Result</label>
              <p className="text-xs text-gray-600 bg-rose-50/30 border border-rose-100 rounded-lg p-3 leading-relaxed font-semibold">{defect.actual_result || "—"}</p>
            </div>
          </div>

          {defect.steps_to_reproduce && defect.steps_to_reproduce.length > 0 && (
            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-1.5">Steps to Reproduce</label>
              <StepList steps={defect.steps_to_reproduce} />
            </div>
          )}

          {defect.root_cause_hypothesis && (
            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-1">Root Cause Hypothesis</label>
              <p className="text-xs text-gray-700 bg-amber-50/30 border border-amber-100 rounded-lg p-3 italic leading-relaxed font-semibold">{defect.root_cause_hypothesis}</p>
            </div>
          )}

          <div className="flex gap-4 text-[10px] text-gray-400 font-bold border-t pt-3 border-gray-100">
            <span>PRIORITY: <span className="text-gray-600 font-extrabold">{defect.priority.toUpperCase()}</span></span>
            <span>SEVERITY: <span className="text-gray-600 font-extrabold">{defect.severity.toUpperCase()}</span></span>
            <span>JIRA SYNC READY: <span className="text-gray-600 font-extrabold">{defect.jira_ready ? "YES" : "NO"}</span></span>
          </div>
        </div>
      )}
    </div>
  );
}

function DefectsContent() {
  const { runAIAction } = useAIAction();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProject = Number(searchParams.get("project")) || null;

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

  // Load Projects on mount
  useEffect(() => {
    projectsApi.list()
      .then((res) => {
        if (res.data.length > 0 && !searchParams.get("project")) {
          const params = new URLSearchParams(searchParams.toString());
          params.set("project", String(res.data[0].id));
          router.push(`${pathname}?${params.toString()}`);
        }
      })
      .catch(() => console.error("Could not load projects."));
  }, [searchParams]);

  // Load Defects and Runs
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
    } catch {
      console.error("Could not load defects data.");
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Reset page when project changes
  useEffect(() => {
    setSelectedRunId(null);
    setFailedResults([]);
    setSelectedResultIds(new Set());
    setAgentStatus("idle");
    setAgentError(null);
    setShowAgentPanel(false);
  }, [selectedProject]);

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
      const res = await runAIAction({
        actionName: "analyze_execution_failures",
        title: "Diagnosing Execution Failures",
        module: "Defects and Evidence",
        artifactType: "Defect Recommendations",
        projectId: selectedProject,
        stages: AI_PROCESSING_STAGES.failureDiagnosis,
        successMessage: "Failure diagnosis and defect recommendations are ready.",
        execute: async () => {
          const response = await defectsApi.analyseDefects(selectedProject, Array.from(selectedResultIds));
          const generated = (response.data as { defect_ids?: number[] }).defect_ids?.length ?? 0;
          if (generated === 0) throw new Error("AI analysis completed but produced no defect recommendations.");
          return response;
        },
      });
      const data = res.data as { defect_ids?: number[]; message?: string };
      const count = data.defect_ids?.length ?? 0;
      if (count === 0) {
        setAgentStatus("error");
        setAgentError("Agent ran but generated 0 defects — the LLM may have failed to parse. Check backend logs.");
      } else {
        setAgentStatus("done");
        setSelectedResultIds(new Set());
        setShowAgentPanel(false);
        await loadData();
      }
    } catch (e: unknown) {
      setAgentStatus("error");
      setAgentError(messageFromError(e, "Agent analysis failed"));
    }
  };

  const handleApprove = async (id: number) => { await defectsApi.approve(id, "approve"); await loadData(); };
  const handleReject = async (id: number) => { await defectsApi.approve(id, "reject"); await loadData(); };
  const handlePushToJira = async (id: number) => { await defectsApi.pushToJira(id); await loadData(); };

  // Filtered defects list
  const filtered = useMemo(() => {
    let list = defects;
    if (filterStatus !== "all") list = list.filter((d) => d.status === filterStatus);
    if (filterSeverity !== "all") list = list.filter((d) => d.severity === filterSeverity);
    return list;
  }, [defects, filterStatus, filterSeverity]);

  const stats = useMemo(() => {
    const total = defects.length;
    const critical = defects.filter((d) => d.severity === "Critical").length;
    const high = defects.filter((d) => d.severity === "High").length;
    const pushed = defects.filter((d) => d.status === "pushed_to_jira").length;

    const criticalPct = total > 0 ? ((critical / total) * 100).toFixed(1) : "0.0";
    const highPct = total > 0 ? ((high / total) * 100).toFixed(1) : "0.0";
    const pushedPct = total > 0 ? ((pushed / total) * 100).toFixed(1) : "0.0";

    return [
      {
        title: "Total Defects",
        icon: Bug,
        iconBg: "bg-app-brand-75 border-app-brand-100",
        iconColor: "text-app-brand-500",
        value: total.toLocaleString(),
        sublabel: "Defects",
        footer: "Total AI identified defect drafts",
      },
      {
        title: "Critical Severity",
        icon: ShieldAlert,
        iconBg: "bg-red-50 border-red-100",
        iconColor: "text-red-500",
        value: critical.toLocaleString(),
        sublabel: "Critical",
        footer: `${criticalPct}% of total defects`,
      },
      {
        title: "High Severity",
        icon: AlertTriangle,
        iconBg: "bg-amber-50 border-amber-100",
        iconColor: "text-amber-500",
        value: high.toLocaleString(),
        sublabel: "High",
        footer: `${highPct}% of total defects`,
      },
      {
        title: "Pushed to Jira",
        icon: ExternalLink,
        iconBg: "bg-emerald-50 border-emerald-100",
        iconColor: "text-emerald-500",
        value: pushed.toLocaleString(),
        sublabel: "Synced",
        footer: `${pushedPct}% synced to Jira boards`,
      },
    ];
  }, [defects]);

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Global Controls ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-red-50 border border-red-100 p-2.5">
            <Bug className="h-6 w-6 text-red-500" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Defect Management</h1>
            <p className="text-xs text-gray-500 mt-1">Audit AI-generated defect drafts, review root cause analysis, and push verified issues to Jira</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadData} className="h-8 w-8 p-0 border-gray-200">
            <RefreshCw className={cn("h-3.5 w-3.5 text-gray-500", loading && "animate-spin")} />
          </Button>

          <Button
            variant="default"
            size="sm"
            onClick={() => setShowAgentPanel(!showAgentPanel)}
            className="h-8 text-xs font-semibold"
          >
            <Bot className="h-3.5 w-3.5 mr-1" />
            Analyse Failures
          </Button>
        </div>
      </div>

      {/* ── Status Counts Cards ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {stats.map((card) => {
          const Icon = card.icon;
          return (
            <Card key={card.title} className="border-gray-200 hover:-translate-y-0.5 transition-all">
              <CardContent className="p-4 flex flex-col justify-between h-full space-y-3">
                <div className="flex items-center gap-2">
                  <div className={cn("rounded-lg p-1.5 flex items-center justify-center shrink-0 border", card.iconBg)}>
                    <Icon className={cn("h-4 w-4", card.iconColor)} />
                  </div>
                  <span className="text-xs font-bold text-gray-700 truncate">{card.title}</span>
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-gray-900">{card.value}</span>
                  {card.sublabel && (
                    <span className="text-[10px] font-bold text-gray-400">{card.sublabel}</span>
                  )}
                </div>
                <div className="text-[10px] text-gray-400 font-semibold border-t border-gray-50 pt-2">
                  {card.footer}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* ── Analyse Failures Panel ─────────────────────────────────────────────── */}
      {showAgentPanel && (
        <Card className="border-red-200 bg-red-50/20">
          <CardContent className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-5 w-5 text-red-500" />
                <div>
                  <h3 className="text-xs font-bold text-gray-800">Failure Analysis Hub (Agent 9)</h3>
                  <p className="text-[10px] text-gray-400 mt-0.5">Select failed test cases from a completed run to draft defects</p>
                </div>
              </div>
              <button onClick={() => setShowAgentPanel(false)} className="text-gray-400 hover:text-gray-600"><X className="h-4 w-4" /></button>
            </div>

            {runs.length === 0 ? (
              <p className="text-xs text-red-700 bg-red-100/50 border border-red-200 rounded-lg p-3 font-semibold">
                No completed execution cycles found. Execute automated tests first.
              </p>
            ) : (
              <div className="space-y-4">
                {/* Run selector */}
                <div>
                  <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-2">Select Completed Execution Run</label>
                  <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto pr-1">
                    {runs.map((run) => (
                      <button
                        key={run.id}
                        onClick={() => handleSelectRun(run.id)}
                        className={cn(
                          "px-3 py-1.5 text-xs font-semibold rounded-lg border transition-all",
                          selectedRunId === run.id
                            ? "bg-red-500 border-red-500 text-white shadow-sm"
                            : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"
                        )}
                      >
                        {run.execution_id} ({run.failed} failed)
                      </button>
                    ))}
                  </div>
                </div>

                {selectedRunId && failedResults.length === 0 && (
                  <p className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-lg p-3 font-semibold">
                    All tests passed in this execution cycle. Nothing to analyse.
                  </p>
                )}

                {selectedRunId && failedResults.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between text-xs font-semibold">
                      <span className="text-gray-700">Failed results selection ({selectedResultIds.size})</span>
                      <button
                        onClick={() => setSelectedResultIds(
                          selectedResultIds.size === failedResults.length
                            ? new Set()
                            : new Set(failedResults.map((r) => r.id))
                        )}
                        className="text-red-500 hover:underline"
                      >
                        {selectedResultIds.size === failedResults.length ? "Deselect All" : "Select All"}
                      </button>
                    </div>

                    <div className="max-h-48 overflow-y-auto space-y-1.5 pr-1">
                      {failedResults.map((r) => (
                        <label key={r.id} className="flex items-start gap-2.5 bg-white border border-gray-250 rounded-lg p-3 cursor-pointer hover:border-red-300 transition-colors">
                          <input
                            type="checkbox"
                            checked={selectedResultIds.has(r.id)}
                            onChange={() => toggleResult(r.id)}
                            className="rounded border-gray-350 text-red-500 focus:ring-red-500 mt-0.5 h-4.5 w-4.5"
                          />
                          <div className="min-w-0 flex-1">
                            <span className="block truncate text-xs font-bold text-gray-800">{r.test_name}</span>
                            {r.error_message && (
                              <p className="text-[10px] text-red-500 truncate mt-0.5 font-semibold font-mono">{r.error_message}</p>
                            )}
                          </div>
                        </label>
                      ))}
                    </div>

                    <div className="flex items-center gap-3">
                      <Button
                        onClick={handleAnalyse}
                        disabled={selectedResultIds.size === 0 || agentStatus === "running"}
                        className="text-xs font-semibold h-9"
                      >
                        {agentStatus === "running" ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin mr-1 text-white" />
                            Drafting {selectedResultIds.size} Defects...
                          </>
                        ) : (
                          <>
                            <Bot className="h-4 w-4 mr-1 text-white" />
                            Analyse {selectedResultIds.size} Failure{selectedResultIds.size !== 1 ? "s" : ""}
                          </>
                        )}
                      </Button>
                      {agentStatus === "done" && (
                        <span className="inline-flex items-center gap-1 text-xs text-emerald-600 font-bold">
                          <CheckCircle className="h-4 w-4" /> Defect drafts successfully created!
                        </span>
                      )}
                      {agentStatus === "error" && (
                        <span className="inline-flex items-center gap-1 text-xs text-rose-600 font-bold bg-rose-50 border border-rose-100 rounded px-2.5 py-1">
                          <AlertTriangle className="h-4 w-4" /> {agentError}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Filters Bar ────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 items-center justify-between">
        <div className="flex flex-wrap gap-1.5 rounded-lg border border-gray-200 bg-white p-1">
          {["all", "draft", "approved", "pushed_to_jira", "rejected"].map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={cn(
                "rounded-md px-3 py-1 text-xs font-semibold capitalize transition-all",
                filterStatus === s
                  ? "bg-gray-900 text-gray-50 shadow-sm"
                  : "text-gray-500 hover:text-gray-900"
              )}
            >
              {s === "all" ? "All Status" : s.replace(/_/g, " ")}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap gap-1.5 rounded-lg border border-gray-200 bg-white p-1">
          {["all", "Critical", "High", "Medium", "Low"].map((sv) => (
            <button
              key={sv}
              onClick={() => setFilterSeverity(sv)}
              className={cn(
                "rounded-md px-3 py-1 text-xs font-semibold capitalize transition-all",
                filterSeverity === sv
                  ? "bg-gray-900 text-gray-50 shadow-sm"
                  : "text-gray-500 hover:text-gray-900"
              )}
            >
              {sv === "all" ? "All Severity" : sv}
            </button>
          ))}
        </div>
      </div>

      {/* ── Defects List Catalog ───────────────────────────────────────────────── */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-16 text-gray-400 text-xs font-semibold">
          <Loader2 className="h-6 w-6 animate-spin text-[#B71920] mb-2" />
          Loading defects registry...
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-dashed border-gray-250">
          <Bug className="h-10 w-10 text-gray-300 mx-auto mb-2" />
          <p className="text-xs text-gray-500 font-bold">No defect drafts found matching filters</p>
          <p className="text-[10px] text-gray-400 font-semibold mt-1">Select completed execution runs above and let AI Analyse Failures</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((d) => (
            <DefectRow key={d.id} defect={d} onApprove={handleApprove} onReject={handleReject} onPushToJira={handlePushToJira} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function DefectsPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-gray-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-red-500 mr-2" />
        Loading Defects Center...
      </div>
    }>
      <DefectsContent />
    </Suspense>
  );
}
