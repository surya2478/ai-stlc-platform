"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ClipboardList, Play, CheckCircle2, XCircle, Pause, Loader2,
  ArrowRight, RefreshCw, Save, AlertTriangle, Network,
  ChevronLeft, ChevronRight as ChevronRightIcon,
} from "lucide-react";
import {
  ExecutionPageHeader,
  KpiCard,
  ProcessSteps,
  EmptyState,
  ErrorState,
  ExecutionStatusBadge,
  buildHref,
} from "../_components/execution-shared";
import { StepEditor } from "../_components/manual/StepEditor";
import { StartRunDialog } from "../_components/manual/StartRunDialog";
import { CreateDefectDialog, type DefectPrefill } from "../_components/CreateDefectDialog";
import { TraceabilityDrawer, type TraceTarget } from "../_components/TraceabilityDrawer";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EnvironmentFilter } from "@/components/execution/EnvironmentFilter";
import { useToast } from "@/components/ui/toast";
import {
  executionApi, testCasesApi,
  type ExecutionRun, type ManualRunDetail, type ManualStepResult,
  type ManualStepStatus, type TestCase,
} from "@/lib/api";
import { cn } from "@/lib/utils";

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
}

function ManualExecutionContent() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");
  const environment = searchParams.get("env") ?? "SIT";
  const { toast } = useToast();

  const [allTcs, setAllTcs] = useState<TestCase[]>([]);
  const [allRuns, setAllRuns] = useState<ExecutionRun[]>([]);
  const [selectedTcIds, setSelectedTcIds] = useState<Set<number>>(new Set());
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [activeRunDetail, setActiveRunDetail] = useState<ManualRunDetail | null>(null);
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [autosaveMsg, setAutosaveMsg] = useState<string | null>(null);
  const autosaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [startOpen, setStartOpen] = useState(false);
  const [defectPrefill, setDefectPrefill] = useState<DefectPrefill | null>(null);
  const [traceTarget, setTraceTarget] = useState<TraceTarget | null>(null);

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    Promise.allSettled([
      testCasesApi.list(Number(projectId)).then((r) => setAllTcs(r.data ?? [])),
      executionApi.listRuns(Number(projectId)).then((r) => setAllRuns(r.data ?? [])),
    ]).finally(() => setLoading(false));
  }, [projectId]);

  const manualTcs = useMemo(() => {
    let list = allTcs.filter((tc) => tc.execution_mode === "manual" || tc.execution_mode === "hybrid");
    const term = search.trim().toLowerCase();
    if (term) {
      list = list.filter((tc) => tc.test_case_id.toLowerCase().includes(term) || tc.title.toLowerCase().includes(term));
    }
    return list;
  }, [allTcs, search]);

  const manualRuns = useMemo(() => allRuns.filter((r) => r.execution_type === "manual"), [allRuns]);

  useEffect(() => {
    if (!activeRunId && manualRuns.length > 0) {
      setActiveRunId(manualRuns[0].id);
    }
  }, [manualRuns, activeRunId]);

  const loadDetail = useCallback((runId: number | null) => {
    if (!runId) {
      setActiveRunDetail(null);
      return;
    }
    executionApi.getManualRun(runId)
      .then((r) => {
        setActiveRunDetail(r.data);
        setActiveStepIndex(0);
      })
      .catch((e) => setError(e?.response?.data?.detail ?? e?.message ?? "Failed to load manual run"));
  }, []);

  useEffect(() => {
    loadDetail(activeRunId);
  }, [activeRunId, loadDetail]);

  // Flatten all steps across all results in the run for the navigator
  const flatSteps = useMemo(() => {
    if (!activeRunDetail) return [] as Array<{ step: ManualStepResult; resultIdx: number; testName: string }>;
    const out: Array<{ step: ManualStepResult; resultIdx: number; testName: string }> = [];
    activeRunDetail.results.forEach((rd, idx) => {
      for (const step of rd.steps) {
        out.push({ step, resultIdx: idx, testName: rd.result.test_name });
      }
    });
    return out;
  }, [activeRunDetail]);

  // Clamp the index if the underlying run shape shrinks (e.g., a result was
  // removed between reloads). Prevents Previous/Next from gating on stale math.
  useEffect(() => {
    if (flatSteps.length === 0) {
      if (activeStepIndex !== 0) setActiveStepIndex(0);
    } else if (activeStepIndex > flatSteps.length - 1) {
      setActiveStepIndex(flatSteps.length - 1);
    }
  }, [flatSteps.length, activeStepIndex]);

  const currentStep = flatSteps[activeStepIndex] ?? null;

  const totals = useMemo(() => {
    let total = 0, passed = 0, failed = 0, blocked = 0, notRun = 0, inProgress = 0;
    for (const r of manualRuns) {
      total += r.total_tests ?? 0;
      passed += r.passed ?? 0;
      failed += r.failed ?? 0;
      const s = (r.status ?? "").toLowerCase();
      if (s === "running" || s === "pending") inProgress += 1;
    }
    if (activeRunDetail) {
      for (const rd of activeRunDetail.results) {
        for (const step of rd.steps) {
          if (step.status === "blocked") blocked += 1;
          if (step.status === "not_run") notRun += 1;
        }
      }
    }
    return { total, passed, failed, blocked, notRun, inProgress };
  }, [manualRuns, activeRunDetail]);

  const startRun = async (options: { suiteName: string; boundRecords: Record<number, number> }) => {
    if (!projectId || selectedTcIds.size === 0) return;
    setStarting(true);
    setError(null);
    try {
      const res = await executionApi.startManualRun(
        Number(projectId),
        Array.from(selectedTcIds),
        environment,
        options.suiteName,
        options.boundRecords,
      );
      setSelectedTcIds(new Set());
      setActiveRunDetail(res.data);
      setActiveRunId(res.data.run.id);
      setStartOpen(false);
      const boundCount = Object.keys(options.boundRecords).length;
      toast({
        title: `Run ${res.data.run.execution_id} started`,
        description: boundCount > 0 ? `${boundCount} test data record(s) bound to steps.` : undefined,
        variant: "success",
      });
      const fresh = await executionApi.listRuns(Number(projectId));
      setAllRuns(fresh.data ?? []);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({
        title: "Failed to start manual run",
        description: err?.response?.data?.detail ?? err?.message,
        variant: "error",
      });
    } finally {
      setStarting(false);
    }
  };

  const updateStep = useCallback(async (stepId: number, patch: { status?: ManualStepStatus; actual_result?: string; comments?: string }) => {
    setAutosaveMsg("Saving…");
    try {
      const res = await executionApi.updateManualStep(stepId, patch);
      // Patch local state with the returned step
      setActiveRunDetail((prev) => {
        if (!prev) return prev;
        const next = structuredClone(prev) as ManualRunDetail;
        for (const rd of next.results) {
          const idx = rd.steps.findIndex((s) => s.id === stepId);
          if (idx >= 0) {
            rd.steps[idx] = res.data;
            break;
          }
        }
        return next;
      });
      setAutosaveMsg("Saved");
      if (autosaveTimer.current) clearTimeout(autosaveTimer.current);
      autosaveTimer.current = setTimeout(() => setAutosaveMsg(null), 1500);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setAutosaveMsg(null);
      toast({
        title: "Step update failed",
        description: err?.response?.data?.detail ?? err?.message,
        variant: "error",
      });
    }
  }, [toast]);

  // Clean up the "Saved" message timer on unmount so React doesn't try to
  // setState on an unmounted component if the user navigates away mid-flight.
  useEffect(() => {
    return () => {
      if (autosaveTimer.current) clearTimeout(autosaveTimer.current);
    };
  }, []);

  const uploadEvidence = async (stepId: number, file: File) => {
    try {
      const res = await executionApi.uploadManualEvidence(stepId, file);
      setActiveRunDetail((prev) => {
        if (!prev) return prev;
        const next = structuredClone(prev) as ManualRunDetail;
        for (const rd of next.results) {
          const idx = rd.steps.findIndex((s) => s.id === stepId);
          if (idx >= 0) {
            rd.steps[idx] = res.data;
            break;
          }
        }
        return next;
      });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({
        title: "Evidence upload failed",
        description: err?.response?.data?.detail ?? err?.message,
        variant: "error",
      });
    }
  };

  const deleteEvidence = async (evidenceId: string, stepId: number) => {
    try {
      const res = await executionApi.deleteManualEvidence(evidenceId);
      setActiveRunDetail((prev) => {
        if (!prev) return prev;
        const next = structuredClone(prev) as ManualRunDetail;
        for (const rd of next.results) {
          const idx = rd.steps.findIndex((s) => s.id === stepId);
          if (idx >= 0) {
            rd.steps[idx] = res.data;
            break;
          }
        }
        return next;
      });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({
        title: "Evidence delete failed",
        description: err?.response?.data?.detail ?? err?.message,
        variant: "error",
      });
    }
  };

  const completionValidation = useMemo(() => {
    if (!activeRunDetail) return { canComplete: false, warnings: [] as string[], blockingFailures: [] as string[] };
    const warnings: string[] = [];
    const blockingFailures: string[] = [];
    let totalSteps = 0;
    let notRunCount = 0;
    let failedCount = 0;
    let blockedCount = 0;
    for (const rd of activeRunDetail.results) {
      for (const step of rd.steps) {
        totalSteps += 1;
        if (step.status === "not_run") notRunCount += 1;
        if (step.status === "failed") failedCount += 1;
        if (step.status === "blocked") blockedCount += 1;
        // Require reason for failed/blocked steps
        if ((step.status === "failed" || step.status === "blocked") && !(step.comments?.trim()) && !(step.actual_result?.trim())) {
          blockingFailures.push(`Step #${step.step_number} (${rd.result.test_name}) requires a comment or actual result`);
        }
      }
    }
    // BLOCK completion when nothing was executed — otherwise we'd publish a
    // run with all "not_run" steps which is meaningless and pollutes metrics.
    if (totalSteps === 0) {
      blockingFailures.push("This run has no steps — nothing to publish");
    } else if (notRunCount === totalSteps) {
      blockingFailures.push("Every step is still Not Run — execute at least one step before completing");
    } else if (notRunCount > 0) {
      warnings.push(`${notRunCount} step(s) still marked Not Run`);
    }
    if (failedCount > 0) warnings.push(`${failedCount} failed step(s) — linked defect recommended`);
    if (blockedCount > 0) warnings.push(`${blockedCount} blocked step(s)`);
    return { canComplete: blockingFailures.length === 0, warnings, blockingFailures };
  }, [activeRunDetail]);

  const completeRun = async () => {
    if (!activeRunDetail) return;
    setStarting(true);
    try {
      const res = await executionApi.completeManualRun(activeRunDetail.run.id);
      setActiveRunDetail(res.data);
      setCompleteOpen(false);
      toast({
        title: `Run ${res.data.run.execution_id} completed`,
        description: "Results published to the execution dashboard.",
        variant: "success",
      });
      const fresh = await executionApi.listRuns(Number(projectId));
      setAllRuns(fresh.data ?? []);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({
        title: "Failed to complete run",
        description: err?.response?.data?.detail ?? err?.message,
        variant: "error",
      });
    } finally {
      setStarting(false);
    }
  };

  if (!projectId) {
    return (
      <div className="space-y-5">
        <ExecutionPageHeader title="Manual Execution" subtitle="Execute and record manual test cases with complete traceability" />
        <EmptyState icon={ClipboardList} title="Pick a project" />
      </div>
    );
  }

  const runLocked = activeRunDetail?.run.status === "completed" || activeRunDetail?.run.status === "auto_completed";
  const stepProgress = flatSteps.length > 0 ? Math.round((flatSteps.filter((s) => s.step.status !== "not_run").length / flatSteps.length) * 100) : 0;

  return (
    <div className="space-y-5">
      <ExecutionPageHeader
        title="Manual Execution"
        subtitle="Execute and record manual test cases with complete traceability"
        actions={
          <div className="flex items-center gap-2">
            <EnvironmentFilter defaultValue="SIT" />
            <Link href={buildHref("/execution/legacy", { project: projectId, tab: "manual" })}>
              <Button variant="outline" size="sm" className="gap-1.5">Classic view <ArrowRight className="h-3.5 w-3.5" /></Button>
            </Link>
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <KpiCard icon={ClipboardList} tone="blue" label="Total TCs" value={totals.total} loading={loading} />
        <KpiCard icon={Play} tone="cyan" label="In Progress" value={totals.inProgress} loading={loading} />
        <KpiCard icon={CheckCircle2} tone="emerald" label="Passed" value={totals.passed} loading={loading} />
        <KpiCard icon={XCircle} tone="red" label="Failed" value={totals.failed} loading={loading} />
        <KpiCard icon={Pause} tone="orange" label="Blocked" value={totals.blocked} loading={loading} />
      </div>

      <ProcessSteps
        currentStep={!activeRunDetail ? 1 : runLocked ? 4 : flatSteps.some((s) => s.step.status !== "not_run") ? 2 : 1}
        steps={[
          { label: "Select Test Cases", description: "Choose manual test cases" },
          { label: "Execute", description: "Run and record results" },
          { label: "Review & Complete", description: "Review and finalize execution" },
          { label: "Results Published", description: "Results updated to dashboard" },
        ]}
      />

      {error && <ErrorState title="Something went wrong" description={error} onRetry={() => loadDetail(activeRunId)} />}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Left: select TCs */}
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between gap-2 mb-3">
              <div>
                <h3 className="text-sm font-semibold text-slate-800">1. Select Manual Test Cases</h3>
                <p className="text-[11px] text-slate-400">{manualTcs.length} available · {selectedTcIds.size} selected</p>
              </div>
              <input
                type="search"
                placeholder="Search…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-40 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[#1b59f8]"
              />
            </div>
            {loading ? (
              <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-10 animate-pulse rounded bg-slate-100" />)}</div>
            ) : manualTcs.length === 0 ? (
              <EmptyState icon={ClipboardList} title="No manual test cases" description="Set execution_mode='manual' on test cases to surface them here." />
            ) : (
              <div className="overflow-y-auto max-h-[460px] -mx-2">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-white">
                    <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400 border-b border-slate-100">
                      <th className="py-2 px-2 w-6"></th>
                      <th className="py-2 px-2">TC ID</th>
                      <th className="py-2 px-2">Title</th>
                      <th className="py-2 px-2">Module</th>
                      <th className="py-2 px-2">Priority</th>
                    </tr>
                  </thead>
                  <tbody>
                    {manualTcs.map((tc) => {
                      const checked = selectedTcIds.has(tc.id);
                      return (
                        <tr
                          key={tc.id}
                          className={cn("border-b border-slate-50 cursor-pointer hover:bg-slate-50/50", checked && "bg-blue-50/40")}
                          onClick={() => {
                            const next = new Set(selectedTcIds);
                            if (next.has(tc.id)) next.delete(tc.id); else next.add(tc.id);
                            setSelectedTcIds(next);
                          }}
                        >
                          <td className="py-2 px-2"><input type="checkbox" checked={checked} readOnly className="accent-[#1b59f8]" /></td>
                          <td className="py-2 px-2 font-mono text-[#1b59f8] whitespace-nowrap">{tc.test_case_id}</td>
                          <td className="py-2 px-2 truncate max-w-[220px]" title={tc.title}>{tc.title}</td>
                          <td className="py-2 px-2 text-slate-500">{tc.product ?? "—"}</td>
                          <td className="py-2 px-2"><Badge variant="secondary" className="text-[10px]">{tc.priority}</Badge></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <div className="mt-3 flex items-center justify-between">
              <span className="text-[11px] text-slate-500">{selectedTcIds.size} test case(s) selected · env {environment}</span>
              <Button size="sm" onClick={() => setStartOpen(true)} disabled={selectedTcIds.size === 0 || starting} className="gap-1.5">
                {starting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                Start Manual Execution
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Right: execute */}
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between gap-2 mb-3">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-slate-800 truncate">
                  2. Execute &amp; Record Result
                </h3>
                <p className="text-[11px] text-slate-400 truncate">
                  {activeRunDetail ? `${activeRunDetail.run.execution_id} · ${activeRunDetail.run.suite_name ?? "—"}` : "Start or select a run"}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {autosaveMsg && (
                  <span className={cn("text-[11px]", autosaveMsg === "Saved" ? "text-emerald-600" : "text-slate-400")}>
                    {autosaveMsg === "Saved" ? <CheckCircle2 className="inline h-3.5 w-3.5 mr-0.5" /> : <Save className="inline h-3.5 w-3.5 mr-0.5" />}
                    {autosaveMsg}
                  </span>
                )}
                {activeRunDetail && (
                  <button
                    onClick={() =>
                      setTraceTarget({
                        entityType: "execution_run",
                        entityId: activeRunDetail.run.id,
                        label: activeRunDetail.run.execution_id,
                      })
                    }
                    className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-800"
                    title="Show the Requirement → Test Case → Run chain"
                  >
                    <Network className="h-3 w-3" /> Trace
                  </button>
                )}
                {activeRunId && (
                  <button onClick={() => loadDetail(activeRunId)} className="text-[11px] text-[#1b59f8] hover:underline flex items-center gap-1">
                    <RefreshCw className="h-3 w-3" /> Refresh
                  </button>
                )}
              </div>
            </div>

            {!activeRunDetail || flatSteps.length === 0 ? (
              <EmptyState icon={Play} title="No active manual run" description="Start one from the left panel." />
            ) : (
              <div className="space-y-3">
                {/* Progress + step nav */}
                <div className="rounded-lg border border-slate-100 p-3">
                  <div className="flex items-center justify-between text-[11px] mb-1">
                    <span className="text-slate-500">Step progress</span>
                    <span className="text-slate-700 font-semibold tabular-nums">{stepProgress}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                    <div className="h-full bg-[#1b59f8]" style={{ width: `${stepProgress}%` }} />
                  </div>
                </div>

                {currentStep && (
                  <StepEditor
                    step={currentStep.step}
                    testName={currentStep.testName}
                    locked={runLocked}
                    onChange={(patch) => updateStep(currentStep.step.id, patch)}
                    onUpload={(file) => uploadEvidence(currentStep.step.id, file)}
                    onDeleteEvidence={(evId) => deleteEvidence(evId, currentStep.step.id)}
                    onDraftDefect={() => {
                      const result = activeRunDetail?.results[currentStep.resultIdx]?.result;
                      setDefectPrefill({
                        summary: `Manual step failure: ${currentStep.testName} — step ${currentStep.step.step_number}`,
                        description: `Failure recorded during manual run ${activeRunDetail?.run.execution_id ?? ""} on ${activeRunDetail?.run.environment ?? environment}.`,
                        steps_to_reproduce: [currentStep.step.action_text ?? `Execute step ${currentStep.step.step_number} of ${currentStep.testName}`],
                        expected_result: currentStep.step.expected_text ?? undefined,
                        actual_result: currentStep.step.actual_result ?? currentStep.step.comments ?? undefined,
                        severity: "High",
                        test_case_id: result?.test_case_id,
                        execution_result_id: result?.id,
                      });
                    }}
                  />
                )}

                <div className="flex items-center justify-between">
                  <Button
                    size="sm" variant="outline"
                    onClick={() => setActiveStepIndex(Math.max(0, activeStepIndex - 1))}
                    disabled={activeStepIndex === 0}
                  >
                    <ChevronLeft className="h-3.5 w-3.5 mr-1" /> Previous
                  </Button>
                  <span className="text-[11px] text-slate-500">
                    Step {activeStepIndex + 1} of {flatSteps.length}
                  </span>
                  <Button
                    size="sm" variant="outline"
                    onClick={() => setActiveStepIndex(Math.min(flatSteps.length - 1, activeStepIndex + 1))}
                    disabled={activeStepIndex === flatSteps.length - 1}
                  >
                    Next <ChevronRightIcon className="h-3.5 w-3.5 ml-1" />
                  </Button>
                </div>

                {/* Complete bar */}
                <div className="rounded-lg border border-slate-100 p-3 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <ExecutionStatusBadge status={activeRunDetail.run.status} />
                    {runLocked && <span className="ml-2 text-[11px] text-slate-500">Run is locked — completed</span>}
                  </div>
                  {!runLocked && (
                    <Button size="sm" onClick={() => setCompleteOpen(true)} className="gap-1.5">
                      <CheckCircle2 className="h-3.5 w-3.5" /> Complete Execution
                    </Button>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent manual runs */}
      <Card>
        <CardContent className="p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-800">Recent Manual Runs</h3>
            <div className="flex items-center gap-3">
              {totals.passed + totals.failed > 0 && (
                <div className="flex items-center gap-2" title={`${totals.passed} passed / ${totals.failed} failed / ${totals.blocked} blocked steps`}>
                  <div className="flex h-1.5 w-32 overflow-hidden rounded-full bg-slate-100">
                    {(() => {
                      const sum = Math.max(totals.passed + totals.failed + totals.blocked, 1);
                      return (
                        <>
                          <div className="h-full bg-emerald-500" style={{ width: `${(totals.passed / sum) * 100}%` }} />
                          <div className="h-full bg-red-500" style={{ width: `${(totals.failed / sum) * 100}%` }} />
                          <div className="h-full bg-orange-400" style={{ width: `${(totals.blocked / sum) * 100}%` }} />
                        </>
                      );
                    })()}
                  </div>
                  <span className="text-[10px] tabular-nums text-slate-400">
                    {totals.passed}✓ {totals.failed}✕ {totals.blocked}⏸
                  </span>
                </div>
              )}
              <Link
                href={buildHref("/execution/dashboard", { project: projectId })}
                className="inline-flex items-center gap-0.5 text-[11px] text-[#1b59f8] hover:underline"
              >
                Full analytics <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </div>
          {manualRuns.length === 0 ? (
            <EmptyState icon={ClipboardList} title="No manual runs yet" description="Pick test cases above and start one." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-100">
                    <th className="py-2 pr-3">Run ID</th>
                    <th className="py-2 pr-3">Suite</th>
                    <th className="py-2 pr-3">Env</th>
                    <th className="py-2 pr-3">Status</th>
                    <th className="py-2 pr-3 text-right">Pass/Fail</th>
                    <th className="py-2 pr-3">Started</th>
                    <th className="py-2 pr-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {manualRuns.slice(0, 10).map((r) => (
                    <tr key={r.id} className={cn("border-b border-slate-50 hover:bg-slate-50/50", activeRunId === r.id && "bg-blue-50/30")}>
                      <td className="py-2 pr-3 font-mono text-[#1b59f8]">{r.execution_id}</td>
                      <td className="py-2 pr-3 max-w-[200px] truncate text-slate-700">{r.suite_name ?? "—"}</td>
                      <td className="py-2 pr-3 text-slate-500">{r.environment ?? "—"}</td>
                      <td className="py-2 pr-3"><ExecutionStatusBadge status={r.status} /></td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        <span className="text-emerald-600">{r.passed}</span><span className="text-slate-300 mx-1">/</span><span className="text-red-600">{r.failed}</span>
                      </td>
                      <td className="py-2 pr-3 text-slate-500">{formatDate(r.started_at ?? r.created_at)}</td>
                      <td className="py-2 pr-3 text-right">
                        <button onClick={() => setActiveRunId(r.id)} className="text-[11px] text-[#1b59f8] hover:underline">Open →</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Complete dialog */}
      {completeOpen && activeRunDetail && (
        <CompleteDialog
          validation={completionValidation}
          onClose={() => setCompleteOpen(false)}
          onConfirm={completeRun}
          busy={starting}
        />
      )}

      {/* Pre-run dialog: suite name + optional test data binding */}
      <StartRunDialog
        open={startOpen}
        onClose={() => setStartOpen(false)}
        projectId={Number(projectId)}
        environment={environment}
        // Derive from the unfiltered list — the search box must not hide
        // already-selected test cases from the binding dialog.
        selectedTcs={allTcs.filter((tc) => selectedTcIds.has(tc.id))}
        busy={starting}
        onStart={startRun}
      />

      {/* Defect draft from a failed step */}
      <CreateDefectDialog
        open={defectPrefill !== null}
        onClose={() => setDefectPrefill(null)}
        projectId={Number(projectId)}
        prefill={defectPrefill ?? undefined}
      />

      {/* Requirement → Test Case → Run chain */}
      <TraceabilityDrawer target={traceTarget} onClose={() => setTraceTarget(null)} />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Complete dialog                                                     */
/* ------------------------------------------------------------------ */

function CompleteDialog({
  validation,
  onClose,
  onConfirm,
  busy,
}: {
  validation: { canComplete: boolean; warnings: string[]; blockingFailures: string[] };
  onClose: () => void;
  onConfirm: () => void;
  busy: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl bg-white shadow-2xl overflow-hidden" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-slate-100">
          <h3 className="text-sm font-semibold text-slate-900">Complete Manual Run</h3>
          <p className="text-[11px] text-slate-500 mt-0.5">Review before publishing results to the dashboard</p>
        </div>
        <div className="p-5 space-y-3 text-xs">
          {validation.blockingFailures.length > 0 && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3">
              <p className="font-semibold text-red-700 flex items-center gap-1.5"><AlertTriangle className="h-3.5 w-3.5" /> Required</p>
              <ul className="mt-1 list-disc list-inside text-red-700 space-y-0.5">
                {validation.blockingFailures.map((b, i) => <li key={i}>{b}</li>)}
              </ul>
            </div>
          )}
          {validation.warnings.length > 0 && (
            <div className="rounded-lg border border-orange-200 bg-orange-50 p-3">
              <p className="font-semibold text-orange-700 flex items-center gap-1.5"><AlertTriangle className="h-3.5 w-3.5" /> Warnings</p>
              <ul className="mt-1 list-disc list-inside text-orange-700 space-y-0.5">
                {validation.warnings.map((b, i) => <li key={i}>{b}</li>)}
              </ul>
            </div>
          )}
          {validation.canComplete && validation.warnings.length === 0 && (
            <p className="text-emerald-700 bg-emerald-50 border border-emerald-200 rounded p-3 flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5" /> All checks passed. Ready to complete.
            </p>
          )}
        </div>
        <div className="px-5 py-3 border-t border-slate-100 flex items-center justify-end gap-2">
          <Button size="sm" variant="outline" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={onConfirm} disabled={!validation.canComplete || busy}>
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Publish & Lock Run"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div className="flex h-96 items-center justify-center text-slate-400"><Loader2 className="h-5 w-5 animate-spin mr-2" />Loading…</div>}>
      <ManualExecutionContent />
    </Suspense>
  );
}
