"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight, BarChart3, Code2, FileText, ListChecks, Loader2, Play,
  RefreshCw, ShieldCheck, UserCheck, Workflow, ChevronRight as ChevronRightIcon,
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
import { useApproveScript, useExecuteScript, useRegenerateScript } from "@/lib/queries/automation";
import { executionKeys } from "@/lib/queries/execution";
import { useToast } from "@/components/ui/toast";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Drawer, DrawerBody, DrawerContent, DrawerDescription, DrawerFooter, DrawerHeader, DrawerTitle,
} from "@/components/ui/drawer";
import { buildHref, ExecutionStatusBadge, ScriptStatusBadge } from "./execution-shared";
import { RunnerStatusChip, useFrameworkAvailable } from "./RunnerStatusChip";
import { formatDate } from "./run-utils";

type Framework = "playwright" | "pytest";
const FRAMEWORK_TABS: { key: Framework; label: string }[] = [
  { key: "playwright", label: "Playwright" },
  { key: "pytest", label: "Pytest" },
];

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
  const approveScript = useApproveScript();
  const regenerate = useRegenerateScript();

  const [activeFramework, setActiveFramework] = useState<Framework>("playwright");
  const [activeTool, setActiveTool] = useState<ExternalTool>("Katalon");
  const [activeScriptId, setActiveScriptId] = useState<number | null>(null);
  const [runTarget, setRunTarget] = useState<RunTarget | null>(null);
  const [externalRunning, setExternalRunning] = useState(false);

  const eligibleCandidates = useMemo(
    () => (planning?.candidates ?? []).slice(0, 8),
    [planning],
  );
  const totalCandidates = planning?.summary.total_candidates ?? planning?.candidates.length ?? 0;

  const filteredScripts = useMemo(
    () => scripts.filter((s) => (s.framework ?? "").toLowerCase() === activeFramework),
    [scripts, activeFramework],
  );
  const activeScript = useMemo(
    () => filteredScripts.find((s) => s.id === activeScriptId) ?? filteredScripts[0] ?? null,
    [filteredScripts, activeScriptId],
  );

  const externalMappingsForTool = useMemo(
    () => mappings.filter((m) => (m.external_tool_name ?? "").toLowerCase().includes(activeTool.toLowerCase())),
    [mappings, activeTool],
  );
  const toolConnected = externalMappingsForTool.length > 0;

  const approvedCount = scripts.filter((s) => (s.status ?? "").toLowerCase() === "approved").length;

  const runnable = (status: string | null | undefined) =>
    ["approved", "executed"].includes((status ?? "").toLowerCase());

  const approve = async (action: "approve" | "reject") => {
    if (!activeScript) return;
    try {
      await approveScript.mutateAsync({
        id: activeScript.id,
        action,
        notes: `${action === "approve" ? "Approved" : "Rejected"} via Automation Execution UI`,
      });
      toast({ title: `Script ${action === "approve" ? "approved" : "rejected"}`, variant: "success" });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({ title: `Failed to ${action}`, description: err?.response?.data?.detail ?? err?.message, variant: "error" });
    }
  };

  const regenerateActive = async () => {
    if (!activeScript) return;
    if (!window.confirm("Regenerate this script? The current code will be overwritten and the script reset to Draft for re-review.")) {
      return;
    }
    try {
      await regenerate.mutateAsync(activeScript.id);
      toast({ title: "Regeneration queued", description: "The script resets to Draft for re-review.", variant: "success" });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({ title: "Failed to regenerate", description: err?.response?.data?.detail ?? err?.message, variant: "error" });
    }
  };

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

  const busy = approveScript.isPending || regenerate.isPending;

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

      <div className="grid gap-4 xl:grid-cols-2">
        {/* ─── Section A: Eligible Automation Test Cases ───────────── */}
        <Card>
          <CardContent className="p-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <SectionMark letter="A" />
                <h3 className="text-sm font-semibold text-slate-800">Eligible Automation Test Cases</h3>
              </div>
              <RunnerStatusChip />
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
                      const canRun = Boolean(c.script_id) && runnable(c.script_status);
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
                                title="Script must be generated and approved before it can run"
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

        {/* ─── Section B: Playwright / Pytest Script Approval ─────── */}
        <Card>
          <CardContent className="p-4">
            <div className="mb-2 flex items-center gap-2">
              <SectionMark letter="B" />
              <h3 className="text-sm font-semibold text-slate-800">Playwright / Pytest Script Generation &amp; Approval</h3>
            </div>

            <div className="mb-3 border-b border-slate-200">
              <div className="flex items-center gap-4">
                {FRAMEWORK_TABS.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => { setActiveFramework(t.key); setActiveScriptId(null); }}
                    className={cn(
                      "-mb-px border-b-2 pb-2 text-xs font-semibold transition-colors",
                      activeFramework === t.key ? "border-[#1b59f8] text-[#1b59f8]" : "border-transparent text-slate-500 hover:text-slate-700",
                    )}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-5 gap-3">
              <div className="col-span-2 space-y-1">
                <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Generated Scripts</p>
                <div className="max-h-[280px] space-y-1 overflow-y-auto pr-1">
                  {filteredScripts.length === 0 ? (
                    <p className="rounded border border-dashed border-slate-200 px-2 py-3 text-center text-[11px] text-slate-400">No {activeFramework} scripts yet</p>
                  ) : filteredScripts.map((s) => {
                    const active = activeScript?.id === s.id;
                    return (
                      <button
                        key={s.id}
                        onClick={() => setActiveScriptId(s.id)}
                        className={cn(
                          "flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
                          active ? "bg-blue-50 ring-1 ring-blue-100" : "hover:bg-slate-50",
                        )}
                      >
                        <span className="flex min-w-0 items-center gap-1.5">
                          <FileText className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                          <span className="truncate font-mono text-[11px] text-slate-700">
                            {(s.file_path ?? s.script_id ?? "").split("/").pop() ?? s.script_id}
                          </span>
                        </span>
                        <ScriptStatusBadge status={s.status} className="shrink-0 text-[9px]" />
                      </button>
                    );
                  })}
                </div>
                <Link href={buildHref("/automation", { project: projectId })} className="mt-2 block text-[11px] text-[#1b59f8] hover:underline">
                  View all scripts →
                </Link>
              </div>

              <div className="col-span-3 overflow-hidden rounded-lg border border-slate-200">
                {activeScript ? (
                  <>
                    <div className="border-b border-slate-200 bg-slate-50 px-3 py-2">
                      <p className="truncate text-[11px] font-semibold text-slate-700">
                        Preview: {(activeScript.file_path ?? activeScript.script_id ?? "").split("/").pop() ?? activeScript.script_id}
                      </p>
                    </div>
                    <CodePreview code={activeScript.code ?? ""} />
                    <div className="flex items-center justify-end gap-1.5 border-t border-slate-200 bg-white p-2">
                      <Button
                        size="sm" variant="outline" disabled={busy} onClick={regenerateActive}
                        className="gap-1 text-xs" title="Re-run generation with current application/URL context"
                      >
                        <RefreshCw className="h-3 w-3" /> Regenerate
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy || !runnable(activeScript.status)}
                        title={runnable(activeScript.status) ? undefined : "Only approved scripts can run — submit for review and approve first"}
                        onClick={() =>
                          setRunTarget({
                            scriptId: activeScript.id,
                            framework: activeScript.framework,
                            label: activeScript.script_id,
                          })
                        }
                        className="gap-1 text-xs"
                      >
                        <Play className="h-3 w-3" /> Run
                      </Button>
                      <Button
                        size="sm" disabled={busy || activeScript.status === "approved"}
                        onClick={() => approve("approve")}
                        className="bg-emerald-600 text-xs text-white hover:bg-emerald-700"
                      >
                        Approve
                      </Button>
                      <Button
                        size="sm" variant="destructive" disabled={busy}
                        onClick={() => approve("reject")}
                        className="text-xs"
                      >
                        Reject
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className="p-8 text-center text-[11px] text-slate-400">Select a script to preview</div>
                )}
              </div>
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

function CodePreview({ code }: { code: string }) {
  if (!code || code.trim().length === 0) {
    return (
      <div className="bg-slate-50 p-6 text-center text-[11px] italic text-slate-400">
        No code stored for this script yet.
      </div>
    );
  }
  const lines = code.split("\n").slice(0, 12);
  return (
    <pre className="max-h-[220px] overflow-x-auto bg-white p-3 font-mono text-[11px] leading-relaxed text-slate-700">
      {lines.map((ln, i) => (
        <div key={i} className="flex">
          <span className="w-7 shrink-0 select-none pr-2 text-right tabular-nums text-slate-300">{i + 1}</span>
          <span className="whitespace-pre">{syntaxColor(ln)}</span>
        </div>
      ))}
    </pre>
  );
}

function syntaxColor(line: string): React.ReactNode {
  // Lightweight token highlighter for the preview only — not a real lexer.
  const parts: React.ReactNode[] = [];
  let rest = line;
  const patterns: { re: RegExp; cls: string }[] = [
    { re: /\b(import|from|test|expect|async|await|const|let|var|return|if|else|function)\b/, cls: "text-violet-600" },
    { re: /'[^']*'|"[^"]*"|`[^`]*`/, cls: "text-emerald-600" },
    { re: /\b\d+\b/, cls: "text-amber-600" },
  ];
  while (rest.length > 0) {
    let matched = false;
    for (const { re, cls } of patterns) {
      const m = rest.match(re);
      if (m && m.index === 0) {
        parts.push(<span key={parts.length} className={cls}>{m[0]}</span>);
        rest = rest.slice(m[0].length);
        matched = true;
        break;
      }
    }
    if (!matched) {
      parts.push(rest[0]);
      rest = rest.slice(1);
    }
  }
  return <>{parts}</>;
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
