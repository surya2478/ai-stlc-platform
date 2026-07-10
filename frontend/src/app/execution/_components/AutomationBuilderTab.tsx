"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight, BarChart3, CheckSquare, Code2, ListChecks, Loader2, Play, PlayCircle,
  RefreshCw, ShieldCheck, Square, UserCheck, Workflow, ChevronRight as ChevronRightIcon,
  AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  automationApi,
  type AutomationPlanning,
  type AutomationPlanningCandidate,
  type AutomationScript,
  type AutomationTestMapping,
} from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import { useExecuteBatch, useExecuteScript } from "@/lib/queries/automation";
import { executionKeys } from "@/lib/queries/execution";
import { useToast } from "@/components/ui/toast";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Drawer, DrawerBody, DrawerContent, DrawerDescription, DrawerFooter, DrawerHeader, DrawerTitle,
} from "@/components/ui/drawer";
import { buildHref, ExecutionStatusBadge } from "./execution-shared";
import { RunnerStatusChip, useFrameworkAvailable } from "./RunnerStatusChip";
import { formatDate } from "./run-utils";

const EXTERNAL_TOOLS = ["Katalon", "Selenium", "Zapier", "Others"] as const;
type ExternalTool = (typeof EXTERNAL_TOOLS)[number];

const TOOL_DEFAULTS: Record<ExternalTool, { suiteId: string; endpoint: string }> = {
  Katalon: { suiteId: "KS-EC-Regression", endpoint: "https://katalon.example.com/api/v1" },
  Selenium: { suiteId: "selenium-grid", endpoint: "https://selenium.example.com/wd/hub" },
  Zapier: { suiteId: "stlc-run-trigger", endpoint: "https://hooks.zapier.com/hooks/catch/…" },
  Others: { suiteId: "", endpoint: "" },
};

const FALLBACK_ENVIRONMENTS = ["staging", "development", "production", "ci"];

function approvalStatusBadge(c: AutomationPlanningCandidate): { variant: "success" | "warning" | "secondary" | "outline" | "destructive" | "info"; label: string } {
  const ms = (c.mapping_status ?? "").toLowerCase();
  const ss = (c.script_status ?? "").toLowerCase();
  if (ss === "needs_regeneration") return { variant: "destructive", label: "Needs regeneration" };
  if (ms === "approved" || ss === "approved") return { variant: "success", label: "Approved" };
  if (ss === "rejected" || ms === "rejected") return { variant: "destructive", label: "Rejected" };
  if (ms === "pending" || ms === "pending_approval" || ss === "pending_approval" || ss === "under_review" || ss === "in_review") {
    return { variant: "warning", label: "Pending" };
  }
  if (ms === "draft" || !ms) return { variant: "outline", label: "Draft" };
  return { variant: "secondary", label: ms.replace(/_/g, " ") };
}

const HANDOFF_LABELS: Record<string, { variant: "success" | "warning" | "outline" | "info" | "secondary"; label: string }> = {
  ready_for_execution: { variant: "success", label: "Ready to Run" },
  repository_ready:    { variant: "info", label: "Repo Ready" },
  human_review:        { variant: "warning", label: "Under Review" },
  draft_generation:    { variant: "outline", label: "Draft" },
};

function handoffBadge(c: AutomationPlanningCandidate) {
  return (
    HANDOFF_LABELS[c.execution_handoff] ??
    ({ variant: "secondary", label: String(c.execution_handoff ?? "—").replace(/_/g, " ") } as const)
  );
}

function scoreBandClass(band: string): string {
  if (band === "high") return "text-emerald-600";
  if (band === "medium") return "text-amber-600";
  return "text-red-500";
}

/* ------------------------------------------------------------------ */
/* Run trigger dialog                                                  */
/* ------------------------------------------------------------------ */

export interface RunTarget {
  scriptId: number;
  framework: string;
  label: string;
}

export function RunTriggerDialog({
  target,
  onClose,
  projectId,
  defaultEnvironment,
  environments,
  onStarted,
}: {
  target: RunTarget | null;
  onClose: () => void;
  projectId: number;
  defaultEnvironment: string;
  environments: string[];
  onStarted?: (executionRunId: number) => void;
}) {
  const { toast } = useToast();
  const executeScript = useExecuteScript(projectId);
  const [environment, setEnvironment] = useState(defaultEnvironment);
  const [timeoutSeconds, setTimeoutSeconds] = useState(600);
  const frameworkAvailable = useFrameworkAvailable(target?.framework);

  // Re-seed the form each time the dialog opens for a (new) script so a
  // changed page environment or previous run's overrides don't leak through.
  useEffect(() => {
    if (target) {
      setEnvironment(defaultEnvironment);
      setTimeoutSeconds(600);
    }
  }, [target, defaultEnvironment]);

  const envOptions = useMemo(() => {
    const opts = new Set([defaultEnvironment, ...environments, ...FALLBACK_ENVIRONMENTS]);
    return Array.from(opts).filter(Boolean);
  }, [defaultEnvironment, environments]);

  const start = async () => {
    if (!target) return;
    try {
      const res = await executeScript.mutateAsync({
        scriptId: target.scriptId,
        environment,
        // The number input's min/max are advisory only — clamp before sending.
        timeoutSeconds: Math.min(3600, Math.max(30, timeoutSeconds)),
      });
      toast({
        title: "Run queued",
        description: res.message,
        variant: "success",
      });
      onStarted?.(res.execution_run_id);
      onClose();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({
        title: "Failed to start run",
        description: err?.response?.data?.detail ?? err?.message,
        variant: "error",
      });
    }
  };

  return (
    <Drawer open={target !== null} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DrawerContent size="sm">
        <DrawerHeader>
          <div>
            <DrawerTitle className="flex items-center gap-2">
              <Play className="h-4 w-4 text-[#1b59f8]" /> Trigger automation run
            </DrawerTitle>
            <DrawerDescription>{target?.label}</DrawerDescription>
          </div>
        </DrawerHeader>
        <DrawerBody>
          {frameworkAvailable === false && (
            <div className="rounded-md border border-orange-200 bg-orange-50 p-2.5 text-[11px] text-orange-700">
              The <b className="capitalize">{target?.framework}</b> runtime was not detected on the
              backend host — the run will fail its preflight check. Install the runtime or pick a
              script for an available framework.
            </div>
          )}
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              Environment
            </label>
            <select
              value={environment}
              onChange={(e) => setEnvironment(e.target.value)}
              className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100"
            >
              {envOptions.map((env) => (
                <option key={env} value={env}>{env}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              Timeout (seconds)
            </label>
            <input
              type="number"
              min={30}
              max={3600}
              value={timeoutSeconds}
              onChange={(e) => setTimeoutSeconds(Number(e.target.value) || 600)}
              className="w-full rounded-md border border-slate-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          </div>
          <p className="text-[11px] text-slate-400">
            The run executes on the backend host via the local {target?.framework} runner and
            appears under Active Runs within a few seconds.
          </p>
        </DrawerBody>
        <DrawerFooter>
          <Button variant="outline" size="sm" onClick={onClose} disabled={executeScript.isPending}>
            Cancel
          </Button>
          <Button size="sm" onClick={start} disabled={executeScript.isPending} className="gap-1.5">
            {executeScript.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            Start run
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

/* ------------------------------------------------------------------ */
/* Run All Eligible — batch run dialog                                 */
/* ------------------------------------------------------------------ */

export interface BatchRunCandidate {
  scriptId: number;
  framework: string;
  /** Stable key for the checkbox list — usually the test case key. */
  key: string;
  label: string;
  /** Real Test Suite tag (TestCase.test_suite_id) — assigned from the Test
   * Cases module. Powers the "By Suite" run scope below. */
  testSuiteId?: number | null;
  testSuiteName?: string | null;
}

/** A candidate with a script that exists but isn't safe to run — shown so
 * the exclusion is visible and explained, not just a silently smaller
 * "eligible" count. */
export interface BlockedRunCandidate {
  key: string;
  label: string;
  reason: string;
}

const ALL_ELIGIBLE_SCOPE = "__all__";

export function RunAllEligibleDialog({
  open,
  onClose,
  projectId,
  candidates,
  blockedCandidates,
  defaultEnvironment,
  environments,
  onStarted,
  title = "Run all eligible automation",
}: {
  open: boolean;
  onClose: () => void;
  projectId: number;
  candidates: BatchRunCandidate[];
  /** Scripts excluded from `candidates` because they're known-bad, not just
   * unapproved — shown with their reason instead of vanishing silently. */
  blockedCandidates?: BlockedRunCandidate[];
  defaultEnvironment: string;
  environments: string[];
  onStarted?: (executionRunId: number) => void;
  title?: string;
}) {
  const { toast } = useToast();
  const executeBatch = useExecuteBatch(projectId);
  const [environment, setEnvironment] = useState(defaultEnvironment);
  const [timeoutSeconds, setTimeoutSeconds] = useState(600);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  // "__all__" or a stringified test_suite_id.
  const [scope, setScope] = useState<string>(ALL_ELIGIBLE_SCOPE);
  const [runName, setRunName] = useState("");
  const [runNameTouched, setRunNameTouched] = useState(false);

  const suites = useMemo(() => {
    const map = new Map<number, string>();
    for (const c of candidates) {
      if (c.testSuiteId != null) map.set(c.testSuiteId, c.testSuiteName || `Suite #${c.testSuiteId}`);
    }
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [candidates]);

  const scopedCandidates = useMemo(() => {
    if (scope === ALL_ELIGIBLE_SCOPE) return candidates;
    const suiteId = Number(scope);
    return candidates.filter((c) => c.testSuiteId === suiteId);
  }, [candidates, scope]);

  // Re-seed each time the dialog opens for a fresh candidate set.
  useEffect(() => {
    if (open) {
      setEnvironment(defaultEnvironment);
      setTimeoutSeconds(600);
      setScope(ALL_ELIGIBLE_SCOPE);
      setRunNameTouched(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, defaultEnvironment]);

  // Selection follows the scope until the user hand-edits the checkboxes.
  useEffect(() => {
    if (open) setSelected(new Set(scopedCandidates.map((c) => c.scriptId)));
  }, [open, scope, scopedCandidates]);

  // Auto-derive a run name from the scope unless the user has typed their own.
  useEffect(() => {
    if (runNameTouched) return;
    if (scope === ALL_ELIGIBLE_SCOPE) {
      setRunName(`All Eligible Automation (${scopedCandidates.length})`);
    } else {
      const suite = suites.find((s) => String(s.id) === scope);
      setRunName(suite ? suite.name : "Suite run");
    }
  }, [scope, scopedCandidates.length, suites, runNameTouched]);

  const envOptions = useMemo(() => {
    const opts = new Set([defaultEnvironment, ...environments, ...FALLBACK_ENVIRONMENTS]);
    return Array.from(opts).filter(Boolean);
  }, [defaultEnvironment, environments]);

  const toggle = (scriptId: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(scriptId)) next.delete(scriptId);
      else next.add(scriptId);
      return next;
    });
  };

  const allSelected = scopedCandidates.length > 0 && selected.size === scopedCandidates.length;
  const toggleAll = () => {
    setSelected(allSelected ? new Set() : new Set(scopedCandidates.map((c) => c.scriptId)));
  };

  const start = async () => {
    const scriptIds = Array.from(selected);
    if (scriptIds.length === 0) return;
    try {
      const res = await executeBatch.mutateAsync({
        scriptIds,
        environment,
        timeoutSeconds: Math.min(3600, Math.max(30, timeoutSeconds)),
        runName: runName.trim() || undefined,
      });
      toast({ title: "Batch run queued", description: res.message, variant: "success" });
      onStarted?.(res.execution_run_id);
      onClose();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({
        title: "Failed to start batch run",
        description: err?.response?.data?.detail ?? err?.message,
        variant: "error",
      });
    }
  };

  return (
    <Drawer open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DrawerContent size="lg">
        <DrawerHeader>
          <div>
            <DrawerTitle className="flex items-center gap-2">
              <PlayCircle className="h-4 w-4 text-[#1b59f8]" /> {title}
            </DrawerTitle>
            <DrawerDescription>
              Runs the selected scripts sequentially as one automation run. Progress updates live under Active Runs.
            </DrawerDescription>
          </div>
        </DrawerHeader>
        <DrawerBody>
          {candidates.length === 0 ? (
            <p className="rounded-md border border-dashed border-slate-200 px-3 py-6 text-center text-[11px] text-slate-400">
              No eligible scripts to run — a test case needs an approved script (or a verified
              external mapping) before it can be included in a batch run.
            </p>
          ) : (
            <>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  Run scope
                </label>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={scope}
                    onChange={(e) => setScope(e.target.value)}
                    className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100"
                  >
                    <option value={ALL_ELIGIBLE_SCOPE}>All eligible ({candidates.length})</option>
                    {suites.map((s) => {
                      const count = candidates.filter((c) => c.testSuiteId === s.id).length;
                      return (
                        <option key={s.id} value={String(s.id)}>
                          Suite: {s.name} ({count})
                        </option>
                      );
                    })}
                  </select>
                  {suites.length === 0 && (
                    <span className="text-[11px] text-slate-400">
                      No suites tagged yet — assign a Test Suite to test cases from the Test Cases module.
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                    Environment
                  </label>
                  <select
                    value={environment}
                    onChange={(e) => setEnvironment(e.target.value)}
                    className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100"
                  >
                    {envOptions.map((env) => (
                      <option key={env} value={env}>{env}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                    Timeout per script (seconds)
                  </label>
                  <input
                    type="number"
                    min={30}
                    max={3600}
                    value={timeoutSeconds}
                    onChange={(e) => setTimeoutSeconds(Number(e.target.value) || 600)}
                    className="w-full rounded-md border border-slate-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  Run name
                </label>
                <input
                  type="text"
                  value={runName}
                  onChange={(e) => { setRunName(e.target.value); setRunNameTouched(true); }}
                  placeholder="e.g. Smoke_Regression_QA"
                  className="w-full rounded-md border border-slate-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100"
                />
              </div>

              <div className="mt-1 flex items-center justify-between">
                <button
                  type="button"
                  onClick={toggleAll}
                  className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-[#1b59f8] hover:underline"
                >
                  {allSelected ? <CheckSquare className="h-3.5 w-3.5" /> : <Square className="h-3.5 w-3.5" />}
                  {allSelected ? "Deselect all" : "Select all"}
                </button>
                <span className="text-[11px] text-slate-500">
                  {selected.size} of {scopedCandidates.length} selected
                </span>
              </div>

              <div className="mt-2 max-h-[280px] space-y-1 overflow-y-auto rounded-md border border-slate-200 p-1.5">
                {scopedCandidates.length === 0 ? (
                  <p className="px-2 py-3 text-center text-[11px] text-slate-400">
                    No eligible scripts in this suite.
                  </p>
                ) : (
                  scopedCandidates.map((c) => (
                    <label
                      key={c.key}
                      className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-slate-50"
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(c.scriptId)}
                        onChange={() => toggle(c.scriptId)}
                        className="h-3.5 w-3.5 rounded border-slate-300 text-[#1b59f8] focus:ring-blue-100"
                      />
                      <span className="min-w-0 flex-1 truncate text-slate-700">{c.label}</span>
                      <Badge variant="info" className="shrink-0 text-[9px] capitalize">{c.framework}</Badge>
                    </label>
                  ))
                )}
              </div>

              {blockedCandidates && blockedCandidates.length > 0 && (
                <BlockedCandidatesNotice candidates={blockedCandidates} />
              )}
            </>
          )}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="outline" size="sm" onClick={onClose} disabled={executeBatch.isPending}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={start}
            disabled={executeBatch.isPending || selected.size === 0}
            className="gap-1.5"
          >
            {executeBatch.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            Run {selected.size > 0 ? selected.size : ""} script{selected.size === 1 ? "" : "s"}
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

/** Scripts that exist but were left out of the runnable list — shown so the
 * exclusion has a visible, specific reason instead of just a smaller count. */
function BlockedCandidatesNotice({ candidates }: { candidates: BlockedRunCandidate[] }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? candidates : candidates.slice(0, 3);
  return (
    <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-2.5">
      <div className="flex items-start gap-1.5">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
        <p className="text-[11px] font-semibold text-amber-800">
          {candidates.length} script{candidates.length === 1 ? "" : "s"} excluded — not safe to run
        </p>
      </div>
      <ul className="mt-1.5 space-y-1 pl-5">
        {shown.map((c) => (
          <li key={c.key} className="text-[10px] text-amber-700">
            <span className="font-mono">{c.key}</span> — {c.reason}
          </li>
        ))}
      </ul>
      {candidates.length > 3 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 pl-5 text-[10px] font-semibold text-amber-800 hover:underline"
        >
          {expanded ? "Show less" : `Show ${candidates.length - 3} more`}
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Builder tab                                                         */
/* ------------------------------------------------------------------ */

export function AutomationBuilderTab({
  projectId,
  environment,
  planning,
  scripts,
  mappings,
  loading,
  activeRunCount,
  totalRunCount,
  defectsToday,
  onViewActiveRuns,
}: {
  projectId: string;
  environment: string;
  planning: AutomationPlanning | null;
  scripts: AutomationScript[];
  mappings: AutomationTestMapping[];
  loading: boolean;
  activeRunCount: number;
  totalRunCount: number;
  defectsToday: number;
  onViewActiveRuns: () => void;
}) {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [activeTool, setActiveTool] = useState<ExternalTool>("Katalon");
  const [runTarget, setRunTarget] = useState<RunTarget | null>(null);
  const [externalRunning, setExternalRunning] = useState(false);
  const [runAllOpen, setRunAllOpen] = useState(false);

  const eligibleCandidates = useMemo(
    () => (planning?.candidates ?? []).slice(0, 8),
    [planning],
  );
  const totalCandidates = planning?.summary.total_candidates ?? planning?.candidates.length ?? 0;

  // Every candidate with a script that's actually safe to run — the full
  // "Run All Eligible" batch, not just the top-8 preview row above. Mirrors
  // the backend's execution_blocked_reason gate, not just "approved":
  // approval alone doesn't mean the script is grounded or ever passed a
  // dry run.
  const runAllCandidates = useMemo<BatchRunCandidate[]>(
    () =>
      (planning?.candidates ?? [])
        .filter((c) => Boolean(c.script_id) && !c.execution_blocked_reason)
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
  const blockedCandidates = useMemo<BlockedRunCandidate[]>(
    () =>
      (planning?.candidates ?? [])
        .filter((c) => Boolean(c.script_id) && Boolean(c.execution_blocked_reason))
        .map((c) => ({
          key: c.test_case_key,
          label: `${c.test_case_key} — ${c.title}`,
          reason: c.execution_blocked_reason as string,
        })),
    [planning],
  );

  const externalMappingsForTool = useMemo(
    () => mappings.filter((m) => (m.external_tool_name ?? "").toLowerCase().includes(activeTool.toLowerCase())),
    [mappings, activeTool],
  );
  const toolConnected = externalMappingsForTool.length > 0;


  // Script readiness counts — authoring/review/approval happen in the AI
  // Automation Studio; this tab only shows a summary + deep link (see
  // Section B below) so there's exactly one place scripts get approved.
  const scriptCounts = useMemo(() => {
    const byStatus = (statuses: string[]) =>
      scripts.filter((s) => statuses.includes((s.status ?? "").toLowerCase())).length;
    return {
      approved: byStatus(["approved"]),
      inReview: byStatus(["in_review", "pending_approval", "under_review"]),
      draft: byStatus(["draft", "ai_draft"]),
      rejected: byStatus(["rejected"]),
      playwright: scripts.filter((s) => (s.framework ?? "").toLowerCase() === "playwright").length,
      pytest: scripts.filter((s) => (s.framework ?? "").toLowerCase() === "pytest").length,
    };
  }, [scripts]);
  const approvedCount = scriptCounts.approved;

  const triggerExternalRun = async () => {
    if (externalMappingsForTool.length === 0) return;
    setExternalRunning(true);
    try {
      const tcIds = externalMappingsForTool.map((m) => m.test_case_id);
      const res = await automationApi.runExternalAutomation(Number(projectId), tcIds, environment);
      // The external connector creates an ExecutionRun synchronously — pull it
      // into the polled run list right away.
      queryClient.invalidateQueries({ queryKey: executionKeys.runs(Number(projectId)) });
      toast({ title: "External run triggered", description: res.data.message, variant: "success" });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({ title: "External run failed", description: err?.response?.data?.detail ?? err?.message, variant: "error" });
    } finally {
      setExternalRunning(false);
    }
  };

  return (
    <>
      <RunTriggerDialog
        target={runTarget}
        onClose={() => setRunTarget(null)}
        projectId={Number(projectId)}
        defaultEnvironment={environment}
        environments={planning?.summary.available_environments ?? []}
        onStarted={onViewActiveRuns}
      />

      <RunAllEligibleDialog
        open={runAllOpen}
        onClose={() => setRunAllOpen(false)}
        projectId={Number(projectId)}
        candidates={runAllCandidates}
        blockedCandidates={blockedCandidates}
        defaultEnvironment={environment}
        environments={planning?.summary.available_environments ?? []}
        onStarted={onViewActiveRuns}
      />

      <div className="grid gap-4 xl:grid-cols-2">
        {/* ─── Section A: Eligible Automation Test Cases ───────────── */}
        <Card>
          <CardContent className="p-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <SectionMark letter="A" />
                <h3 className="text-sm font-semibold text-slate-800">Eligible Automation Test Cases</h3>
              </div>
              <div className="flex items-center gap-2">
                <RunnerStatusChip />
                <Button
                  size="sm"
                  onClick={() => setRunAllOpen(true)}
                  disabled={runAllCandidates.length === 0}
                  className="h-7 gap-1.5 px-2.5 text-[11px]"
                  title={
                    runAllCandidates.length === 0
                      ? "No scripts are currently safe to run"
                      : blockedCandidates.length > 0
                        ? `${blockedCandidates.length} script(s) excluded — see the dialog for why`
                        : undefined
                  }
                >
                  <PlayCircle className="h-3.5 w-3.5" /> Run All Eligible ({runAllCandidates.length})
                </Button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-[10px] uppercase tracking-wider text-slate-400">
                    <th className="py-2 pr-3">TC ID</th>
                    <th className="py-2 pr-3">Framework</th>
                    <th className="py-2 pr-3">Fit Score</th>
                    <th className="py-2 pr-3">Approval</th>
                    <th className="py-2 pr-3">Stage</th>
                    <th className="py-2 pr-3">Last Run</th>
                    <th className="py-2 pr-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {eligibleCandidates.length === 0 && !loading ? (
                    <tr><td colSpan={7} className="py-6 text-center text-[11px] text-slate-400">No eligible candidates yet — generate a plan from the Automation module.</td></tr>
                  ) : (
                    eligibleCandidates.map((c) => {
                      const approval = approvalStatusBadge(c);
                      const stage = handoffBadge(c);
                      const canRun = Boolean(c.script_id) && !c.execution_blocked_reason;
                      return (
                        <tr key={c.test_case_id} className="border-b border-slate-50 hover:bg-slate-50/50" title={c.title}>
                          <td className="whitespace-nowrap py-2 pr-3 font-mono text-slate-700">{c.test_case_key}</td>
                          <td className="py-2 pr-3">
                            <Badge variant="info" className="text-[10px] capitalize">{c.recommended_framework}</Badge>
                          </td>
                          <td className="py-2 pr-3">
                            <span
                              className={cn("font-semibold tabular-nums", scoreBandClass(c.assessment_band))}
                              title={c.assessment_reasons.join("\n")}
                            >
                              {Math.round(c.assessment_score)}
                              <span className="ml-1 text-[10px] font-medium uppercase text-slate-400">{c.assessment_band}</span>
                            </span>
                          </td>
                          <td className="py-2 pr-3">
                            <Badge variant={approval.variant} className="text-[10px]">{approval.label}</Badge>
                          </td>
                          <td className="py-2 pr-3">
                            <Badge variant={stage.variant} className="text-[10px]">{stage.label}</Badge>
                          </td>
                          <td className="whitespace-nowrap py-2 pr-3">
                            {c.last_execution_status ? (
                              <span className="inline-flex items-center gap-1.5" title={formatDate(c.last_execution_at)}>
                                <ExecutionStatusBadge status={c.last_execution_status} className="text-[10px]" />
                              </span>
                            ) : (
                              <span className="text-[10px] text-slate-300">never run</span>
                            )}
                          </td>
                          <td className="py-2 pr-3 text-right">
                            {canRun ? (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() =>
                                  setRunTarget({
                                    scriptId: c.script_id as number,
                                    framework: c.recommended_framework,
                                    label: `${c.test_case_key} — ${c.title}`,
                                  })
                                }
                                className="h-6 gap-1 px-2 text-[10px]"
                              >
                                <Play className="h-3 w-3" /> Run
                              </Button>
                            ) : (
                              <span
                                className="text-[10px] text-slate-300"
                                title={c.execution_blocked_reason ?? "Script must be generated and approved before it can run"}
                              >
                                —
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500">
              <span>
                {eligibleCandidates.length === 0
                  ? `0 of ${totalCandidates.toLocaleString()} entries`
                  : `Showing 1 to ${eligibleCandidates.length} of ${totalCandidates.toLocaleString()} entries`}
              </span>
              <Link href={buildHref("/automation", { project: projectId })} className="inline-flex items-center gap-0.5 text-[#1b59f8] hover:underline">
                View all eligible TCs <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* ─── Section B: Script Readiness ─────────────────────────── */}
        {/* Authoring, code review, and approval happen in the AI Automation
            Studio only — this is a read-only summary so there's exactly one
            place scripts get approved, not two disagreeing surfaces. */}
        <Card>
          <CardContent className="flex h-full flex-col p-4">
            <div className="mb-1 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <SectionMark letter="B" />
                <h3 className="text-sm font-semibold text-slate-800">Script Readiness</h3>
              </div>
              <Link
                href={buildHref("/automation", { project: projectId })}
                className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#1b59f8] hover:underline"
              >
                Open AI Automation Studio <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            <p className="mb-4 text-[11px] leading-relaxed text-slate-500">
              Generate, review, and approve Playwright / Pytest scripts in the Studio. Execution
              only runs scripts that are already approved there.
            </p>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <ReadinessStat label="Approved" value={scriptCounts.approved} tone="emerald" />
              <ReadinessStat label="In Review" value={scriptCounts.inReview} tone="orange" />
              <ReadinessStat label="Draft" value={scriptCounts.draft} tone="slate" />
              <ReadinessStat label="Rejected" value={scriptCounts.rejected} tone="red" />
            </div>

            <div className="mt-auto flex items-center gap-4 border-t border-slate-100 pt-3 text-[11px] text-slate-500">
              <span>{scriptCounts.playwright} Playwright</span>
              <span>{scriptCounts.pytest} Pytest</span>
              <span className="ml-auto font-semibold text-slate-700">{scripts.length} total scripts</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Execution Flow (horizontal) ───────────────────────────── */}
      <Card>
        <CardContent className="p-4">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Execution Flow</p>
          <ExecutionFlow
            steps={[
              { icon: ListChecks, label: "Approved TCs", tone: "blue", value: `${totalCandidates} eligible` },
              { icon: Code2, label: "Generate Script", tone: "violet", value: `${scripts.length} generated` },
              { icon: UserCheck, label: "Review & Approval", tone: "orange", value: `${approvedCount} approved` },
              { icon: Play, label: "Execute Run", tone: "cyan", value: `${activeRunCount} running` },
              { icon: RefreshCw, label: "Results Sync to\nAutomation Execution", tone: "blue", value: `${totalRunCount} synced` },
              { icon: BarChart3, label: "Dashboard & Reports", tone: "slate", value: `${defectsToday} defects today` },
            ]}
          />
        </CardContent>
      </Card>

      {/* ── Section C: External Automation Tools ─────── */}
      <Card>
        <CardContent className="p-4">
          <div className="mb-2 flex items-center gap-2">
            <SectionMark letter="C" />
            <h3 className="text-sm font-semibold text-slate-800">External Automation Tools</h3>
          </div>

          <div className="mb-4 border-b border-slate-200">
            <div className="flex items-center gap-4">
              {EXTERNAL_TOOLS.map((t) => (
                <button
                  key={t}
                  onClick={() => setActiveTool(t)}
                  className={cn(
                    "-mb-px border-b-2 pb-2 text-xs font-semibold transition-colors",
                    activeTool === t ? "border-[#1b59f8] text-[#1b59f8]" : "border-transparent text-slate-500 hover:text-slate-700",
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/*
            Fields are read-only displays of the FIRST active mapping for this
            tool. Credentials, endpoints, and triggers are managed in the
            Automation module so secrets never round-trip through the browser.
          */}
          {(() => {
            const firstMapping = externalMappingsForTool[0];
            const suiteId = firstMapping?.external_suite_id ?? TOOL_DEFAULTS[activeTool].suiteId ?? "—";
            const endpoint = TOOL_DEFAULTS[activeTool].endpoint;
            return (
              <div className="grid grid-cols-2 gap-3 text-xs">
                <FormField label="Tool Name">
                  <ReadOnlyValue value={activeTool} />
                </FormField>
                <FormField label="Suite ID">
                  <ReadOnlyValue value={suiteId} mono />
                </FormField>
                <div className="col-span-2">
                  <FormField label="Endpoint / API">
                    <ReadOnlyValue value={endpoint || "—"} mono />
                  </FormField>
                </div>
                <FormField label="Trigger Type">
                  <ReadOnlyValue value="On Demand" />
                </FormField>
                <FormField label="Credentials">
                  <div className="flex items-center justify-between rounded-md border border-slate-200 bg-white px-2.5 py-1.5">
                    <span className={cn("flex items-center gap-1.5 text-xs font-semibold", toolConnected ? "text-emerald-600" : "text-slate-500")}>
                      <span className={cn("h-2 w-2 rounded-full", toolConnected ? "bg-emerald-500" : "bg-slate-300")} />
                      {toolConnected ? "Connected" : "Not configured"}
                    </span>
                    <ShieldCheck className="h-3.5 w-3.5 text-slate-300" />
                  </div>
                </FormField>
                <div className="col-span-2 flex items-center justify-between">
                  <Link href={buildHref("/automation", { project: projectId })} className="inline-flex items-center gap-0.5 text-[11px] text-[#1b59f8] hover:underline">
                    Edit credentials &amp; mappings <ArrowRight className="h-3 w-3" />
                  </Link>
                  <Button
                    size="sm"
                    disabled={!toolConnected || externalRunning || externalMappingsForTool.length === 0}
                    onClick={triggerExternalRun}
                    className="gap-1.5"
                    title={!toolConnected ? "No active mapping for this tool" : `Trigger ${externalMappingsForTool.length} test case(s)`}
                  >
                    {externalRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />} Trigger Run
                  </Button>
                </div>
              </div>
            );
          })()}

          <div className="mt-5 border-t border-slate-100 pt-4">
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Execution Flow</p>
            <ExternalFlow tool={activeTool} />
          </div>
        </CardContent>
      </Card>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Local sub-components                                                */
/* ------------------------------------------------------------------ */

function SectionMark({ letter }: { letter: string }) {
  return (
    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#1b59f8] text-xs font-bold text-white shadow-sm">
      {letter}
    </span>
  );
}

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-400">{label}</label>
      {children}
    </div>
  );
}

function ReadOnlyValue({ value, mono }: { value: string; mono?: boolean }) {
  return (
    <div
      className={cn(
        "w-full truncate rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-700",
        mono && "font-mono",
      )}
      title={value}
    >
      {value}
    </div>
  );
}

const READINESS_TONE: Record<string, string> = {
  emerald: "bg-emerald-50 text-emerald-700 ring-emerald-100",
  orange: "bg-orange-50 text-orange-700 ring-orange-100",
  slate: "bg-slate-50 text-slate-600 ring-slate-100",
  red: "bg-red-50 text-red-700 ring-red-100",
};

function ReadinessStat({ label, value, tone }: { label: string; value: number; tone: keyof typeof READINESS_TONE }) {
  return (
    <div className={cn("rounded-lg px-3 py-2 ring-1", READINESS_TONE[tone])}>
      <p className="text-lg font-bold tabular-nums leading-none">{value}</p>
      <p className="mt-1 text-[10px] font-semibold uppercase tracking-wider opacity-80">{label}</p>
    </div>
  );
}

function ExecutionFlow({ steps }: { steps: Array<{ icon: React.ComponentType<{ className?: string }>; label: string; tone: "blue" | "violet" | "orange" | "cyan" | "slate"; value?: string }> }) {
  const TONE_BG: Record<string, { bg: string; ring: string; icon: string }> = {
    blue:   { bg: "bg-blue-50",    ring: "ring-blue-100",    icon: "text-[#1b59f8]" },
    violet: { bg: "bg-violet-50",  ring: "ring-violet-100",  icon: "text-violet-600" },
    orange: { bg: "bg-orange-50",  ring: "ring-orange-100",  icon: "text-orange-600" },
    cyan:   { bg: "bg-cyan-50",    ring: "ring-cyan-100",    icon: "text-cyan-600" },
    slate:  { bg: "bg-slate-100",  ring: "ring-slate-200",   icon: "text-slate-600" },
  };
  return (
    <div className="flex items-start justify-between gap-1 overflow-x-auto pb-1">
      {steps.map((s, i) => {
        const t = TONE_BG[s.tone];
        return (
          <div key={s.label + i} className="flex min-w-[100px] flex-1 items-start gap-1">
            <div className="flex min-w-[90px] flex-col items-center text-center">
              <div className={cn("flex h-10 w-10 items-center justify-center rounded-xl ring-1", t.bg, t.ring)}>
                <s.icon className={cn("h-4 w-4", t.icon)} />
              </div>
              <p className="mt-1.5 whitespace-pre-line text-[10px] font-semibold leading-tight text-slate-700">
                {s.label}
              </p>
              {s.value != null && (
                <p className="text-[10px] font-bold tabular-nums text-slate-900">{s.value}</p>
              )}
            </div>
            {i < steps.length - 1 && (
              <div className="flex h-10 items-center text-slate-300">
                <ChevronRightIcon className="h-3.5 w-3.5" />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ExternalFlow({ tool }: { tool: ExternalTool }) {
  const steps: Array<{ icon: React.ComponentType<{ className?: string }>; label: string }> = [
    { icon: Workflow, label: `${tool} Tool` },
    { icon: BarChart3, label: "Execution Results" },
    { icon: Code2, label: "Automation Execution\nModule" },
    { icon: ListChecks, label: "Main Dashboard\n& Reports" },
  ];
  return (
    <div className="flex items-start justify-between gap-1">
      {steps.map((s, i) => (
        <div key={i} className="flex min-w-[80px] flex-1 items-start gap-1">
          <div className="flex min-w-[70px] flex-col items-center text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 ring-1 ring-blue-100">
              <s.icon className="h-4 w-4 text-[#1b59f8]" />
            </div>
            <p className="mt-1.5 whitespace-pre-line text-[10px] font-semibold leading-tight text-slate-700">{s.label}</p>
          </div>
          {i < steps.length - 1 && (
            <div className="flex h-10 items-center text-slate-300">
              <ChevronRightIcon className="h-3.5 w-3.5" />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
