"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bug, Check, CheckCircle2, Clock, Download, Loader2, PlayCircle, RotateCcw, Search, XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AutomationPlanning, ExecutionResult, ExecutionRun } from "@/lib/api";
import { isActiveRun, useRun, useRunResults } from "@/lib/queries/execution";
import { useRunLifecycleActions } from "@/lib/queries/runActions";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ExecutionStatusBadge, LoadingSkeleton } from "./execution-shared";
import {
  AiAssistedBadge, buildArtifactLinks, formatDate, formatDuration,
  runVerdict, RunVerdictBadge,
} from "./run-utils";
import { RunAllEligibleDialog, type BatchRunCandidate } from "./AutomationBuilderTab";
import { CreateDefectDialog, type DefectPrefill } from "./CreateDefectDialog";
import { TraceabilityDrawer, type TraceTarget } from "./TraceabilityDrawer";

const PAGE_SIZE = 8;

type RailFilter = "all" | "active" | "failed" | "completed";

const RAIL_FILTERS: { key: RailFilter; label: string }[] = [
  { key: "all", label: "All Runs" },
  { key: "active", label: "Active" },
  { key: "failed", label: "Failed" },
  { key: "completed", label: "Completed" },
];

function isFailedRun(run: ExecutionRun): boolean {
  const v = runVerdict(run);
  return v === "failed" || v === "blocked";
}
function isCompletedRun(run: ExecutionRun): boolean {
  return !isActiveRun(run) && !isFailedRun(run) && runVerdict(run) !== "cancelled";
}

function runnerLabel(run: ExecutionRun): string {
  const sourceType = (run.metadata_ as { source_type?: string } | undefined)?.source_type;
  if (sourceType === "automation_local_batch") return "Local Runner (Batch)";
  if (sourceType === "automation_local") return "Local Runner";
  if (run.execution_type === "ai") return "AI-Assisted";
  if (run.execution_type === "manual") return "Manual";
  if (run.external_tool_name) return `External: ${run.external_tool_name}`;
  return sourceType ? sourceType.replace(/_/g, " ") : "—";
}

function triggerSourceLabel(run: ExecutionRun): string {
  const parentRunId = (run.metadata_ as { parent_run_id?: number } | undefined)?.parent_run_id;
  return parentRunId ? "Retry" : "Manual";
}

/* ------------------------------------------------------------------ */
/* Main tab                                                            */
/* ------------------------------------------------------------------ */

export function CommandCenterTab({
  projectId,
  environment,
  runs,
  loading,
  planning,
  initialSelectedRunId,
}: {
  projectId: string;
  environment: string;
  runs: ExecutionRun[];
  loading: boolean;
  planning: AutomationPlanning | null;
  initialSelectedRunId?: number | null;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<RailFilter>("all");
  const [page, setPage] = useState(1);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(initialSelectedRunId ?? null);
  const [selectedResultId, setSelectedResultId] = useState<number | null>(null);
  const [runAllOpen, setRunAllOpen] = useState(false);
  const [defectPrefill, setDefectPrefill] = useState<DefectPrefill | null>(null);
  const [traceTarget, setTraceTarget] = useState<TraceTarget | null>(null);

  const sorted = useMemo(
    () => [...runs].sort((a, b) => (b.started_at ?? b.created_at ?? "").localeCompare(a.started_at ?? a.created_at ?? "")),
    [runs],
  );

  const counts = useMemo(() => ({
    all: sorted.length,
    active: sorted.filter(isActiveRun).length,
    failed: sorted.filter(isFailedRun).length,
    completed: sorted.filter(isCompletedRun).length,
  }), [sorted]);

  const filtered = useMemo(() => {
    let list = sorted;
    if (filter === "active") list = list.filter(isActiveRun);
    else if (filter === "failed") list = list.filter(isFailedRun);
    else if (filter === "completed") list = list.filter(isCompletedRun);
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter((r) =>
        (r.suite_name ?? "").toLowerCase().includes(q) || r.execution_id.toLowerCase().includes(q));
    }
    return list;
  }, [sorted, filter, search]);

  useEffect(() => { setPage(1); }, [filter, search]);

  // Keep a run selected: default to the first visible one, and fall back to
  // it whenever the current selection scrolls out of the active filter/search.
  useEffect(() => {
    if (selectedRunId != null && filtered.some((r) => r.id === selectedRunId)) return;
    setSelectedRunId(filtered[0]?.id ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRuns = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const selectedRunSummary = runs.find((r) => r.id === selectedRunId) ?? null;
  const runQuery = useRun(selectedRunId);
  const run = runQuery.data ?? selectedRunSummary;
  const resultsQuery = useRunResults(selectedRunId);
  const results = useMemo(() => resultsQuery.data ?? [], [resultsQuery.data]);

  const lifecycle = useRunLifecycleActions(run, results);

  // Pick a result to show in Failure Details: whatever's selected if it's
  // still in this run's results, else the first failing one.
  useEffect(() => {
    if (selectedResultId != null && results.some((r) => r.id === selectedResultId)) return;
    const firstFailing = results.find((r) => ["fail", "error", "blocked"].includes(String(r.status).toLowerCase()));
    setSelectedResultId(firstFailing?.id ?? null);
  }, [results, selectedResultId]);

  const runAllCandidates = useMemo<BatchRunCandidate[]>(
    () =>
      (planning?.candidates ?? [])
        .filter((c) => Boolean(c.script_id) && ["approved", "executed"].includes((c.script_status ?? "").toLowerCase()))
        .map((c) => ({
          scriptId: c.script_id as number,
          framework: c.recommended_framework,
          key: c.test_case_key,
          label: `${c.test_case_key} — ${c.title}`,
          testSuiteId: c.test_suite_id,
          testSuiteName: c.test_suite_name,
        })),
    [planning],
  );

  const openDefectDialog = (result: ExecutionResult) => {
    setDefectPrefill({
      summary: `Automation failure: ${result.test_name}`,
      description: `Failure detected in execution run ${run?.execution_id ?? result.execution_run_id} (${run?.environment ?? "unknown environment"}).`,
      actual_result: result.error_message ?? undefined,
      steps_to_reproduce: run
        ? [`Run automation suite "${run.suite_name ?? run.execution_id}" on ${run.environment ?? "target environment"}`]
        : [],
      severity: "High",
      test_case_id: result.test_case_id,
      execution_result_id: result.id,
    });
  };

  const onRunStarted = (executionRunId: number) => {
    setFilter("all");
    setSearch("");
    setSelectedRunId(executionRunId);
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[320px_1fr_300px]">
      <RunsRail
        runs={pageRuns}
        totalFiltered={filtered.length}
        loading={loading}
        counts={counts}
        filter={filter}
        onFilterChange={setFilter}
        search={search}
        onSearchChange={setSearch}
        selectedRunId={selectedRunId}
        onSelect={setSelectedRunId}
        page={page}
        pageCount={pageCount}
        onPageChange={setPage}
        onNewRun={() => setRunAllOpen(true)}
        newRunDisabled={runAllCandidates.length === 0}
      />

      <RunDetailPanel
        run={run}
        loading={runQuery.isLoading && !run}
        results={results}
        resultsLoading={resultsQuery.isLoading}
        lifecycle={lifecycle}
        selectedResultId={selectedResultId}
        onSelectResult={setSelectedResultId}
        onTrace={(runId, label) => setTraceTarget({ entityType: "execution_run", entityId: runId, label })}
      />

      <FailureDetailsPanel
        run={run}
        results={results}
        resultsLoading={resultsQuery.isLoading}
        selectedResultId={selectedResultId}
        onSelectResult={setSelectedResultId}
        lifecycle={lifecycle}
        onCreateDefect={openDefectDialog}
      />

      <RunAllEligibleDialog
        open={runAllOpen}
        onClose={() => setRunAllOpen(false)}
        projectId={Number(projectId)}
        candidates={runAllCandidates}
        defaultEnvironment={environment}
        environments={planning?.summary.available_environments ?? []}
        onStarted={onRunStarted}
      />

      <CreateDefectDialog
        open={defectPrefill !== null}
        onClose={() => setDefectPrefill(null)}
        projectId={Number(projectId)}
        prefill={defectPrefill ?? undefined}
      />

      <TraceabilityDrawer target={traceTarget} onClose={() => setTraceTarget(null)} />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Left rail — runs list                                               */
/* ------------------------------------------------------------------ */

function RunsRail({
  runs, totalFiltered, loading, counts, filter, onFilterChange, search, onSearchChange,
  selectedRunId, onSelect, page, pageCount, onPageChange, onNewRun, newRunDisabled,
}: {
  runs: ExecutionRun[];
  totalFiltered: number;
  loading: boolean;
  counts: Record<RailFilter, number>;
  filter: RailFilter;
  onFilterChange: (f: RailFilter) => void;
  search: string;
  onSearchChange: (v: string) => void;
  selectedRunId: number | null;
  onSelect: (id: number) => void;
  page: number;
  pageCount: number;
  onPageChange: (p: number) => void;
  onNewRun: () => void;
  newRunDisabled: boolean;
}) {
  return (
    <Card className="flex flex-col overflow-hidden">
      <CardContent className="flex flex-1 flex-col p-0">
        <div className="border-b border-slate-100 p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-800">Runs &amp; Run History</h3>
            <Button
              size="sm"
              onClick={onNewRun}
              disabled={newRunDisabled}
              className="h-7 shrink-0 gap-1 px-2 text-[11px]"
              title={newRunDisabled ? "No approved scripts ready to run" : undefined}
            >
              <PlayCircle className="h-3.5 w-3.5" /> New Run
            </Button>
          </div>
          <div className="relative mb-2">
            <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search by run ID or name…"
              className="w-full rounded-md border border-slate-200 bg-white py-1.5 pl-7 pr-2 text-xs focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          </div>
          <div className="flex gap-1 overflow-x-auto">
            {RAIL_FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => onFilterChange(f.key)}
                className={cn(
                  "shrink-0 rounded-md px-2 py-1 text-[10px] font-semibold transition",
                  filter === f.key ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200",
                )}
              >
                {f.label} ({counts[f.key]})
              </button>
            ))}
          </div>
        </div>

        <div className="max-h-[560px] flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-3"><LoadingSkeleton rows={5} /></div>
          ) : runs.length === 0 ? (
            <div className="p-4">
              <EmptyState
                icon={Clock}
                title="No runs found"
                description={totalFiltered === 0 ? "No runs match this filter yet." : "No runs on this page."}
              />
            </div>
          ) : (
            <div className="divide-y divide-slate-50">
              {runs.map((r) => (
                <RunCard key={r.id} run={r} selected={r.id === selectedRunId} onClick={() => onSelect(r.id)} />
              ))}
            </div>
          )}
        </div>

        {totalFiltered > 0 && (
          <div className="flex items-center justify-between border-t border-slate-100 px-3 py-2 text-[11px] text-slate-500">
            <span>
              {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, totalFiltered)} of {totalFiltered}
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => onPageChange(page - 1)}
                className="rounded px-2 py-0.5 font-semibold hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-30"
              >
                ‹
              </button>
              <button
                type="button"
                disabled={page >= pageCount}
                onClick={() => onPageChange(page + 1)}
                className="rounded px-2 py-0.5 font-semibold hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-30"
              >
                ›
              </button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RunCard({ run, selected, onClick }: { run: ExecutionRun; selected: boolean; onClick: () => void }) {
  const active = isActiveRun(run);
  const done = (run.passed ?? 0) + (run.failed ?? 0) + (run.skipped ?? 0);
  const pct = active && run.total_tests > 0 ? Math.round((done / run.total_tests) * 100) : null;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn("block w-full px-3 py-2.5 text-left transition", selected ? "bg-blue-50/70" : "hover:bg-slate-50")}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={cn("truncate font-mono text-[11px]", selected ? "text-violet-700" : "text-[#1b59f8]")}>
          {run.execution_id}
        </span>
        <RunVerdictBadge run={run} />
      </div>
      <div className="mt-0.5 flex items-center gap-1.5">
        <p className="truncate text-xs font-semibold text-slate-800">{run.suite_name ?? "Untitled run"}</p>
        <AiAssistedBadge run={run} />
      </div>
      <div className="mt-1 flex items-center gap-1.5 text-[10px] text-slate-400">
        {/* Sourced from the Test Cases module: test_environment is
            TestCase.test_phase, test_suite_name is TestCase.test_suite_id ->
            TestSuite.name — not the run's own deployment environment field.
            See execution_service._attach_test_suite_info. */}
        <span className="truncate" title="Test Environment">{run.test_environment ?? "—"}</span>
        <span>·</span>
        <span className="truncate" title="Test Suite">{run.test_suite_name ?? "—"}</span>
        <span className="ml-auto shrink-0">{formatDate(run.started_at ?? run.created_at)}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-3 text-[10px] tabular-nums text-slate-500">
        <span className="text-emerald-600">✓ {run.passed}</span>
        <span className="text-red-600">✕ {run.failed}</span>
        <span className="text-slate-400">↷ {run.skipped}</span>
        {pct !== null && <span className="ml-auto font-semibold text-[#1b59f8]">{pct}%</span>}
      </div>
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Center — run detail                                                 */
/* ------------------------------------------------------------------ */

type LifecycleActions = ReturnType<typeof useRunLifecycleActions>;

type RunDetailSubTab = "monitor" | "tests" | "logs";

function RunDetailPanel({
  run, loading, results, resultsLoading, lifecycle, selectedResultId, onSelectResult, onTrace,
}: {
  run: ExecutionRun | null;
  loading: boolean;
  results: ExecutionResult[];
  resultsLoading: boolean;
  lifecycle: LifecycleActions;
  selectedResultId: number | null;
  onSelectResult: (id: number) => void;
  onTrace: (runId: number, label: string) => void;
}) {
  const [subTab, setSubTab] = useState<RunDetailSubTab>("monitor");

  if (!run) {
    return (
      <Card>
        <CardContent className="flex h-full min-h-[400px] items-center justify-center p-6">
          {loading ? (
            <Loader2 className="h-5 w-5 animate-spin text-slate-300" />
          ) : (
            <EmptyState icon={PlayCircle} title="No run selected" description="Pick a run from the list, or start a new one." />
          )}
        </CardContent>
      </Card>
    );
  }

  const {
    localRunnerRun, runCancellable, failedScriptIds, progressPct,
    cancelPending, retryPending, handleCancel, handleRetryFailed,
  } = lifecycle;

  const displayPct = progressPct ?? (run.total_tests > 0 ? 100 : 0);
  const notRun = Math.max(0, run.total_tests - run.passed - run.failed - run.skipped);
  const currentlyRunning = progressPct !== null
    ? results.find((r) => (r.status ?? "").toLowerCase() === "pending")
    : undefined;

  return (
    <Card className="flex flex-col">
      <CardContent className="flex flex-1 flex-col p-4">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-sm font-bold text-slate-900">{run.suite_name ?? run.execution_id}</h3>
              <RunVerdictBadge run={run} />
              <AiAssistedBadge run={run} />
            </div>
            <button
              type="button"
              onClick={() => onTrace(run.id, run.execution_id)}
              className="mt-0.5 font-mono text-[11px] text-slate-400 hover:text-[#1b59f8] hover:underline"
              title="Show the Requirement → Test Case → Script → Run chain"
            >
              {run.execution_id}
            </button>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {localRunnerRun && runCancellable && (
              <Button
                size="sm" variant="outline" onClick={handleCancel} disabled={cancelPending}
                className="h-7 gap-1 border-red-200 px-2 text-[10px] text-red-700 hover:bg-red-50"
              >
                {cancelPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <XCircle className="h-3.5 w-3.5" />}
                Cancel Run
              </Button>
            )}
            {localRunnerRun && failedScriptIds.length > 0 && (
              <Button
                size="sm" variant="outline" onClick={() => handleRetryFailed()} disabled={retryPending}
                className="h-7 gap-1 border-orange-200 px-2 text-[10px] text-orange-700 hover:bg-orange-50"
              >
                {retryPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
                Retry Failed ({failedScriptIds.length})
              </Button>
            )}
          </div>
        </div>

        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <MetaItem label="Trigger Source" value={triggerSourceLabel(run)} />
          <MetaItem label="Triggered By" value={run.triggered_by_name ?? "—"} />
          <MetaItem label="Environment" value={run.environment ?? "—"} />
          <MetaItem label="Runner" value={runnerLabel(run)} />
          <MetaItem label="Start Time" value={formatDate(run.started_at)} />
          <MetaItem label="Duration" value={formatDuration(run.duration_seconds)} />
          <MetaItem label="Total Tests" value={String(run.total_tests)} />
          <MetaItem
            label="Confidence"
            value={run.confidence_score != null ? `${Math.round(run.confidence_score)}%` : "—"}
          />
        </div>

        <div className="mb-3 flex items-center gap-4 rounded-lg border border-slate-200 bg-slate-50/50 p-3">
          <ProgressRing pct={displayPct} />
          <div className="grid flex-1 grid-cols-4 gap-2 text-center">
            <div>
              <p className="text-lg font-bold tabular-nums text-emerald-600">{run.passed}</p>
              <p className="text-[10px] text-slate-400">Passed</p>
            </div>
            <div>
              <p className="text-lg font-bold tabular-nums text-red-600">{run.failed}</p>
              <p className="text-[10px] text-slate-400">Failed</p>
            </div>
            <div>
              <p className="text-lg font-bold tabular-nums text-slate-500">{run.skipped}</p>
              <p className="text-[10px] text-slate-400">Skipped</p>
            </div>
            <div>
              <p className="text-lg font-bold tabular-nums text-slate-700">{notRun}</p>
              <p className="text-[10px] text-slate-400">Not Run</p>
            </div>
          </div>
        </div>

        <RunLifecycleStepper run={run} />

        <div className="mt-3 flex gap-4 border-b border-slate-200">
          {([
            ["monitor", "Execution Monitor"],
            ["tests", `Test Cases (${run.total_tests})`],
            ["logs", "Logs"],
          ] as [RunDetailSubTab, string][]).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setSubTab(key)}
              className={cn(
                "-mb-px border-b-2 pb-2 text-xs font-semibold transition-colors",
                subTab === key ? "border-[#1b59f8] text-[#1b59f8]" : "border-transparent text-slate-500 hover:text-slate-700",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="mt-3 flex-1">
          {subTab === "monitor" && (
            <>
              {currentlyRunning && (
                <div className="mb-3 flex items-center gap-2 rounded-lg border border-blue-100 bg-blue-50/60 p-3 text-xs">
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-blue-500" />
                  <div className="min-w-0">
                    <p className="font-semibold text-blue-700">Currently running</p>
                    <p className="truncate text-slate-600">{currentlyRunning.test_name}</p>
                  </div>
                </div>
              )}
              <ResultsTable
                results={[...results].reverse().slice(0, 6)}
                loading={resultsLoading}
                selectedResultId={selectedResultId}
                onSelectResult={onSelectResult}
              />
              {results.length > 6 && (
                <button
                  type="button"
                  onClick={() => setSubTab("tests")}
                  className="mt-2 text-[11px] font-semibold text-[#1b59f8] hover:underline"
                >
                  View all {results.length} test cases →
                </button>
              )}
            </>
          )}
          {subTab === "tests" && (
            <ResultsTable
              results={results}
              loading={resultsLoading}
              selectedResultId={selectedResultId}
              onSelectResult={onSelectResult}
            />
          )}
          {subTab === "logs" && <LogsPanel run={run} />}
        </div>
      </CardContent>
    </Card>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50/50 px-2.5 py-1.5">
      <p className="text-[9px] font-semibold uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-0.5 truncate text-xs font-semibold text-slate-800">{value}</p>
    </div>
  );
}

function ProgressRing({ pct }: { pct: number }) {
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (Math.min(100, Math.max(0, pct)) / 100) * circumference;
  return (
    <div className="relative h-16 w-16 shrink-0">
      <svg viewBox="0 0 64 64" className="h-16 w-16 -rotate-90">
        <circle cx="32" cy="32" r={radius} fill="none" stroke="#e2e8f0" strokeWidth="6" />
        <circle
          cx="32" cy="32" r={radius} fill="none" stroke="#1b59f8" strokeWidth="6"
          strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round"
          className="transition-all"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center text-sm font-bold text-slate-800">{pct}%</div>
    </div>
  );
}

function terminalStageLabel(run: ExecutionRun): string {
  const v = runVerdict(run);
  if (v === "cancelled") return "Cancelled";
  if (v === "failed") return "Failed";
  if (v === "blocked") return "Blocked";
  if (v === "passed") return "Passed";
  return "Completed";
}

interface StageEvent {
  stage: string;
  at: string;
  runner_availability?: Record<string, boolean>;
  [key: string]: unknown;
}

function getRunStages(run: ExecutionRun): StageEvent[] {
  const raw = (run.metadata_ as { stages?: unknown } | undefined)?.stages;
  return Array.isArray(raw) ? (raw as StageEvent[]) : [];
}

function preflightNote(availability: Record<string, boolean> | undefined): string | undefined {
  if (!availability) return undefined;
  return Object.entries(availability)
    .map(([framework, available]) => `${framework}: ${available ? "available" : "unavailable"}`)
    .join(" · ");
}

/**
 * Lifecycle stepper — reads real stage events the batch/single-script task
 * recorded (preflight runtime check, running, finalizing, terminal), each
 * with a genuine timestamp. Runs from before this instrumentation shipped
 * (or non-local-runner runs, which never populate metadata_.stages) fall
 * back to the honest 3-stage view: Queued → Running → terminal.
 */
function RunLifecycleStepper({ run }: { run: ExecutionRun }) {
  const recorded = getRunStages(run);
  const preflight = recorded.find((s) => s.stage === "preflight");
  const runningEvent = recorded.find((s) => s.stage === "running");
  const finalizing = recorded.find((s) => s.stage === "finalizing");

  const stages: { label: string; at: string | null | undefined; note?: string }[] = [
    { label: "Queued", at: run.created_at },
  ];
  if (preflight) stages.push({ label: "Pre-flight", at: preflight.at, note: preflightNote(preflight.runner_availability) });
  stages.push({ label: "Running", at: runningEvent?.at ?? run.started_at });
  if (finalizing) stages.push({ label: "Finalizing", at: finalizing.at });
  stages.push({ label: terminalStageLabel(run), at: run.completed_at });

  const status = (run.status ?? "").toLowerCase();
  const runningIndex = stages.findIndex((s) => s.label === "Running");
  const currentIndex = ["queued", "pending"].includes(status)
    ? 0
    : status === "running"
    ? runningIndex
    : stages.length - 1;

  return (
    <div className="mt-3 flex items-center gap-2 rounded-lg border border-slate-200 bg-white p-3">
      {stages.map((s, i) => (
        <div key={s.label} className="flex flex-1 items-center gap-2">
          <div className="flex flex-col items-center gap-1 text-center" title={s.note}>
            <div
              className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold",
                i < currentIndex ? "bg-emerald-500 text-white" : i === currentIndex ? "bg-[#1b59f8] text-white" : "bg-slate-100 text-slate-400",
              )}
            >
              {i < currentIndex ? <Check className="h-3.5 w-3.5" /> : i + 1}
            </div>
            <p className="whitespace-nowrap text-[10px] font-semibold text-slate-600">{s.label}</p>
            <p className="text-[9px] text-slate-400">{s.at ? formatDate(s.at) : "—"}</p>
          </div>
          {i < stages.length - 1 && <div className="h-px flex-1 bg-slate-200" />}
        </div>
      ))}
    </div>
  );
}

function ResultsTable({
  results, loading, selectedResultId, onSelectResult,
}: {
  results: ExecutionResult[];
  loading: boolean;
  selectedResultId: number | null;
  onSelectResult: (id: number) => void;
}) {
  if (loading) return <LoadingSkeleton rows={4} />;
  if (results.length === 0) {
    return (
      <EmptyState icon={Clock} title="No test results yet" description="Results appear here as the run executes." />
    );
  }
  return (
    <div className="max-h-[320px] overflow-y-auto rounded-md border border-slate-200">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-slate-50">
          <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400">
            <th className="px-3 py-2">Test</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2 text-right">Duration</th>
            <th className="px-3 py-2 text-right">Updated</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => (
            <tr
              key={r.id}
              onClick={() => onSelectResult(r.id)}
              className={cn(
                "cursor-pointer border-t border-slate-50 hover:bg-slate-50/70",
                selectedResultId === r.id && "bg-blue-50/60",
              )}
            >
              <td className="max-w-[220px] truncate px-3 py-2 font-medium text-slate-700">{r.test_name}</td>
              <td className="px-3 py-2"><ExecutionStatusBadge status={r.status} className="text-[10px]" /></td>
              <td className="px-3 py-2 text-right tabular-nums text-slate-500">
                {r.duration_ms != null ? `${(r.duration_ms / 1000).toFixed(1)}s` : "—"}
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-slate-400">{formatDate(r.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function logLine(entry: unknown): string {
  if (typeof entry === "string") return entry;
  if (entry && typeof entry === "object") {
    const obj = entry as Record<string, unknown>;
    const level = typeof obj.level === "string" ? `[${obj.level.toUpperCase()}] ` : "";
    const message = typeof obj.message === "string" ? obj.message : JSON.stringify(entry);
    return `${level}${message}`;
  }
  return String(entry);
}

function LogsPanel({ run }: { run: ExecutionRun }) {
  const logs = Array.isArray(run.execution_logs) ? run.execution_logs.map(logLine) : [];
  if (logs.length === 0) {
    return <EmptyState icon={Clock} title="No logs yet" description="Run-level logs appear here once the worker starts." />;
  }
  return (
    <pre className="max-h-[400px] overflow-auto whitespace-pre-wrap rounded-lg bg-slate-900 p-3 font-mono text-[11px] leading-relaxed text-slate-100">
      {logs.join("\n")}
    </pre>
  );
}

/* ------------------------------------------------------------------ */
/* Right — failure details + quick actions                             */
/* ------------------------------------------------------------------ */

function FailureDetailsPanel({
  run, results, resultsLoading, selectedResultId, onSelectResult, lifecycle, onCreateDefect,
}: {
  run: ExecutionRun | null;
  results: ExecutionResult[];
  resultsLoading: boolean;
  selectedResultId: number | null;
  onSelectResult: (id: number) => void;
  lifecycle: LifecycleActions;
  onCreateDefect: (result: ExecutionResult) => void;
}) {
  const { localRunnerRun, failedScriptIds, retryPending, handleRetry, handleRetryFailed } = lifecycle;

  const failing = useMemo(
    () => results.filter((r) => ["fail", "error", "blocked"].includes(String(r.status).toLowerCase())),
    [results],
  );
  const selected = failing.find((r) => r.id === selectedResultId) ?? failing[0] ?? null;

  if (!run) {
    return (
      <Card>
        <CardContent className="flex h-full min-h-[400px] items-center justify-center p-6 text-xs text-slate-400">
          Select a run to see failure details.
        </CardContent>
      </Card>
    );
  }

  const singleScriptId = (selected?.metadata_ as { automation_script_id?: number } | undefined)?.automation_script_id;
  const canRetrySingle = localRunnerRun && typeof singleScriptId === "number";
  const artifacts = selected ? buildArtifactLinks(selected) : [];

  return (
    <Card className="flex flex-col">
      <CardContent className="flex flex-1 flex-col p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-800">Failure Details</h3>
          {failing.length > 0 && <Badge variant="destructive">{failing.length} failing</Badge>}
        </div>

        {resultsLoading ? (
          <LoadingSkeleton rows={4} />
        ) : !selected ? (
          <EmptyState
            icon={CheckCircle2}
            title="No failures"
            description="Every test that has finished in this run passed."
          />
        ) : (
          <>
            <div className="mb-4 rounded-lg border border-red-100 bg-red-50/60 p-3">
              <div className="mb-1.5 flex items-center gap-2">
                <ExecutionStatusBadge status={selected.status} />
                <span className="truncate font-mono text-[11px] text-slate-500">{selected.test_name}</span>
              </div>
              <p className="text-[11px] text-slate-500">
                Duration: {selected.duration_ms != null ? `${(selected.duration_ms / 1000).toFixed(1)}s` : "—"}
                {" · "}Updated: {formatDate(selected.updated_at)}
              </p>
              {selected.error_message && (
                <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-white p-2 font-mono text-[11px] text-red-700">
                  {selected.error_message}
                </pre>
              )}
            </div>

            {failing.length > 1 && (
              <div className="mb-4 space-y-1">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Other failures</p>
                {failing.filter((f) => f.id !== selected.id).slice(0, 4).map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => onSelectResult(f.id)}
                    className="block w-full truncate rounded-md px-2 py-1 text-left text-[11px] text-slate-600 hover:bg-slate-50"
                  >
                    {f.test_name}
                  </button>
                ))}
              </div>
            )}

            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Quick Actions</p>
              <QuickAction
                icon={RotateCcw}
                label="Retry this test case"
                onClick={() => canRetrySingle && handleRetry([singleScriptId as number])}
                disabled={!canRetrySingle || retryPending}
                title={canRetrySingle ? undefined : "Only local-runner scripts can be retried from here"}
              />
              <QuickAction
                icon={RotateCcw}
                label={`Retry all failed (${failedScriptIds.length})`}
                onClick={() => handleRetryFailed()}
                disabled={failedScriptIds.length === 0 || retryPending}
              />
              <QuickAction icon={Bug} label="Draft defect" onClick={() => onCreateDefect(selected)} />
              {artifacts.map((a) => (
                <QuickAction
                  key={a.kind}
                  icon={a.icon}
                  label={`Download ${a.label}`}
                  href={a.href}
                />
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function QuickAction({
  icon: Icon, label, onClick, href, disabled, title,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick?: () => void;
  href?: string;
  disabled?: boolean;
  title?: string;
}) {
  const className = cn(
    "flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 transition",
    disabled ? "cursor-not-allowed opacity-40" : "hover:bg-slate-50",
  );
  if (href) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className={className} title={title}>
        <Icon className="h-3.5 w-3.5 text-slate-400" />
        {label}
        <Download className="ml-auto h-3 w-3 text-slate-400" />
      </a>
    );
  }
  return (
    <button type="button" onClick={onClick} disabled={disabled} className={className} title={title}>
      <Icon className="h-3.5 w-3.5 text-slate-400" />
      {label}
    </button>
  );
}
