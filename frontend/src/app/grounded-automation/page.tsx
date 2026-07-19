"use client";

/**
 * Grounded Automation (PoC) — evidence-first script generation.
 *
 * Pipeline per test case: Route → Capture (live app walk) → Coverage Gate →
 * Generate (evidence-exclusive). Entirely additive to the platform; the
 * backend namespace is feature-flagged and this page shows a clear disabled
 * state when GROUNDED_AUTOMATION_ENABLED is off.
 */

import { Suspense, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Camera,
  CheckCircle2,
  ChevronRight,
  Loader2,
  Plus,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  StopCircle,
  Target,
  Wand2,
  XCircle,
} from "lucide-react";
import { projectsApi, testCasesApi, type PocGroundingRunDetail, type TestCase } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import {
  isActivePocRun,
  useCancelPocRun,
  useConfirmPocStep,
  useCreatePocRun,
  useGeneratePocScript,
  usePocRun,
  usePocRuns,
  usePocStatus,
  useStartPocCapture,
} from "@/lib/queries/groundedPoc";

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  routing_ready: "Routed",
  capturing: "Capturing…",
  awaiting_confirmation: "Needs Confirmation",
  gate_passed: "Gate Passed",
  gate_blocked: "Gate Blocked",
  generating: "Generating…",
  generated: "Generated",
  failed: "Failed",
  cancelled: "Cancelled",
};

function statusVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  if (status === "generated" || status === "gate_passed") return "success";
  if (status === "failed" || status === "gate_blocked") return "destructive";
  if (status === "awaiting_confirmation") return "warning";
  if (status === "capturing" || status === "generating") return "purple";
  if (status === "cancelled") return "secondary";
  return "outline";
}

const PIPELINE_STEPS = ["Route", "Capture", "Coverage Gate", "Generate"] as const;

function stepForStatus(status: string): number {
  if (status === "routing_ready") return 1;
  if (status === "capturing" || status === "awaiting_confirmation") return 2;
  if (status === "gate_passed" || status === "gate_blocked") return 3;
  return 4;
}

function PipelineHeader({ status }: { status: string }) {
  const current = stepForStatus(status);
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {PIPELINE_STEPS.map((label, i) => {
        const stepNumber = i + 1;
        const done = stepNumber < current || status === "generated";
        const active = stepNumber === current && status !== "generated";
        return (
          <div key={label} className="flex items-center gap-2">
            <span
              className={
                "flex items-center gap-1.5 rounded-full px-3 py-1 font-medium " +
                (done
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
                  : active
                  ? "bg-violet-100 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300"
                  : "bg-muted text-muted-foreground")
              }
            >
              {done ? <CheckCircle2 className="h-3 w-3" /> : <span>{stepNumber}.</span>}
              {label}
            </span>
            {i < PIPELINE_STEPS.length - 1 && <ChevronRight className="h-3 w-3 text-muted-foreground" />}
          </div>
        );
      })}
    </div>
  );
}

function NewRunForm({
  projectId,
  onCancel,
  onCreated,
}: {
  projectId: number | null;
  onCancel: () => void;
  onCreated: (runId: number) => void;
}) {
  const { toast } = useToast();
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [testCaseId, setTestCaseId] = useState<number | "">("");
  const [environment, setEnvironment] = useState("QA");
  const [captureMode, setCaptureMode] = useState<"automated" | "assisted">("automated");
  const createRun = useCreatePocRun(projectId);

  useEffect(() => {
    if (!projectId) return;
    testCasesApi
      .list(projectId, { status: "approved" })
      .then((res) => setTestCases(res.data))
      .catch(() => toast({ title: "Could not load approved test cases", variant: "error" }));
  }, [projectId, toast]);

  async function handleCreate() {
    if (!projectId || testCaseId === "") return;
    try {
      const run = await createRun.mutateAsync({
        project_id: projectId,
        test_case_id: Number(testCaseId),
        environment,
        capture_mode: captureMode,
      });
      onCreated(run.id);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast({ title: "Could not create run", description: detail ?? "Unknown error", variant: "error" });
    }
  }

  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <p className="text-sm font-semibold">New Grounding Run</p>
        <p className="text-xs text-muted-foreground">
          Pick an approved test case. The pipeline classifies each step (routing matrix), launches the
          application in a real browser, captures every screen the test case touches as evidence, and
          only generates a script when 100% of the required evidence exists — no guesswork.
        </p>
        <div className="grid gap-4 md:grid-cols-3">
          <label className="space-y-1 text-xs">
            <span className="font-medium">Approved test case</span>
            <select
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={testCaseId}
              onChange={(e) => setTestCaseId(e.target.value === "" ? "" : Number(e.target.value))}
            >
              <option value="">Select a test case…</option>
              {testCases.map((tc) => (
                <option key={tc.id} value={tc.id}>
                  {tc.test_case_id} — {tc.title}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-xs">
            <span className="font-medium">Environment</span>
            <input
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={environment}
              onChange={(e) => setEnvironment(e.target.value)}
              placeholder="QA"
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="font-medium">Capture mode</span>
            <select
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={captureMode}
              onChange={(e) => setCaptureMode(e.target.value as "automated" | "assisted")}
            >
              <option value="automated">Automated — agent walks the whole journey</option>
              <option value="assisted">Assisted — agent pauses on ambiguous steps</option>
            </select>
          </label>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={testCaseId === "" || createRun.isPending}>
            {createRun.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Create &amp; Route
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function RoutingPanel({ run }: { run: PocGroundingRunDetail }) {
  const routing = run.routing;
  if (!routing) return null;
  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold">Routing Decision</p>
          <Badge variant="info">
            {routing.overall.type} → {routing.overall.adapter}
          </Badge>
          <span className="text-xs text-muted-foreground">
            confidence {routing.overall_confidence}%{routing.is_hybrid && " · hybrid test case"}
          </span>
        </div>
        {routing.unimplemented_adapters.length > 0 && (
          <p className="text-xs text-amber-700 dark:text-amber-300">
            Routed-only in this PoC (adapters land in later phases):{" "}
            {routing.unimplemented_adapters.join(", ")}
          </p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-border text-muted-foreground">
              <tr>
                <th className="py-1.5 pr-3 font-medium">#</th>
                <th className="py-1.5 pr-3 font-medium">Step</th>
                <th className="py-1.5 pr-3 font-medium">Action adapter</th>
                <th className="py-1.5 pr-3 font-medium">Assertion channel</th>
                <th className="py-1.5 font-medium">Cleanup</th>
              </tr>
            </thead>
            <tbody>
              {routing.steps.map((s) => (
                <tr key={s.index} className="border-b border-border/60 last:border-0 align-top">
                  <td className="py-1.5 pr-3">{s.index + 1}</td>
                  <td className="max-w-[320px] py-1.5 pr-3">{s.action_text}</td>
                  <td className="py-1.5 pr-3">
                    <Badge variant={s.action_route.implemented ? "success" : "warning"}>
                      {s.action_route.adapter}
                    </Badge>{" "}
                    <span className="text-muted-foreground">{s.action_confidence}%</span>
                  </td>
                  <td className="py-1.5 pr-3">
                    <Badge variant={s.assertion_route.implemented ? "success" : "warning"}>
                      {s.assertion_route.adapter}
                    </Badge>{" "}
                    <span className="text-muted-foreground">{s.assertion_confidence}%</span>
                  </td>
                  <td className="py-1.5">{s.requires_cleanup ? "required" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function EvidencePanel({ run }: { run: PocGroundingRunDetail }) {
  if (run.evidence.length === 0) return null;
  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <p className="text-sm font-semibold">
          Application State Evidence ({run.evidence.length} captured state
          {run.evidence.length === 1 ? "" : "s"})
        </p>
        <div className="grid gap-2 md:grid-cols-2">
          {run.evidence.map((ev) => (
            <div key={ev.id} className="rounded-md border border-border p-3 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">
                  #{ev.sequence} {ev.title || ev.url || "(untitled state)"}
                </span>
                <span className="font-mono text-[10px] text-muted-foreground">
                  {ev.state_fingerprint.slice(0, 10)}
                </span>
              </div>
              <p className="mt-1 truncate text-muted-foreground">{ev.url}</p>
              <p className="mt-1 text-muted-foreground">
                {ev.element_count} elements
                {ev.produced_by_step !== null && ev.produced_by_step !== undefined
                  ? ` · produced by step ${ev.produced_by_step + 1}`
                  : " · entry state"}
                {ev.has_screenshot && " · screenshot ✓"}
              </p>
              {ev.blockers.length > 0 && (
                <p className="mt-1 text-red-600 dark:text-red-400">Blockers: {ev.blockers.join("; ")}</p>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function CoveragePanel({ run }: { run: PocGroundingRunDetail }) {
  const coverage = run.coverage;
  if (!coverage) return null;
  const pct = Math.round(coverage.overallCoverage * 100);
  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex flex-wrap items-center gap-2">
          {coverage.generationAllowed ? (
            <ShieldCheck className="h-5 w-5 text-emerald-600" />
          ) : (
            <ShieldAlert className="h-5 w-5 text-red-500" />
          )}
          <p className="text-sm font-semibold">Coverage Gate</p>
          <Badge variant={coverage.generationAllowed ? "success" : "destructive"}>
            {coverage.coveredSteps}/{coverage.totalSteps} steps · {pct}%
          </Badge>
          <span className="text-xs text-muted-foreground">
            {coverage.generationAllowed
              ? "100% required evidence — generation unlocked"
              : "Generation is blocked until every gap below is resolved"}
          </span>
        </div>
        {coverage.liveBlockers.length > 0 && (
          <p className="text-xs text-red-600 dark:text-red-400">
            Live blockers observed: {coverage.liveBlockers.join("; ")}
          </p>
        )}
        {coverage.warnings.map((w) => (
          <p key={w} className="text-xs text-amber-700 dark:text-amber-300">
            ⚠ {w}
          </p>
        ))}
        <div className="space-y-2">
          {coverage.steps.map((s) => (
            <div
              key={s.step}
              className={
                "rounded-md border p-3 text-xs " +
                (s.status === "covered"
                  ? "border-emerald-200 dark:border-emerald-900"
                  : "border-red-300 dark:border-red-800")
              }
            >
              <div className="flex items-center gap-2">
                {s.status === "covered" ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                ) : (
                  <XCircle className="h-3.5 w-3.5 text-red-500" />
                )}
                <span className="font-medium">Step {s.step}</span>
                <span className="truncate text-muted-foreground">{s.action_text}</span>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                <EvidenceChip label="action" evidence={s.action_evidence} />
                <EvidenceChip label="data" evidence={s.data_evidence} />
                <EvidenceChip label="assertion" evidence={s.assertion_evidence} />
                <EvidenceChip label="cleanup" evidence={s.cleanup_evidence} optional />
              </div>
              {s.gaps.map((g) => (
                <p key={g} className="mt-1 text-red-600 dark:text-red-400">
                  ✗ {g}
                </p>
              ))}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function EvidenceChip({
  label,
  evidence,
  optional,
}: {
  label: string;
  evidence: Record<string, unknown> | null;
  optional?: boolean;
}) {
  const grounded = evidence !== null && evidence !== undefined;
  const kind = grounded ? String((evidence as { kind?: string }).kind ?? "evidence") : null;
  return (
    <span
      className={
        "rounded-full px-2 py-0.5 text-[10px] font-medium " +
        (grounded
          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
          : optional
          ? "bg-muted text-muted-foreground"
          : "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300")
      }
      title={grounded ? JSON.stringify(evidence) : undefined}
    >
      {label}: {grounded ? kind : optional ? "n/a" : "missing"}
    </span>
  );
}

function ConfirmationPanel({
  run,
  projectId,
}: {
  run: PocGroundingRunDetail;
  projectId: number | null;
}) {
  const { toast } = useToast();
  const confirmStep = useConfirmPocStep(projectId);
  const pending = run.pending_confirmation;
  if (!pending) return null;
  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <p className="text-sm font-semibold">
          Assisted capture — step {pending.step_index + 1} needs your confirmation
        </p>
        <p className="text-xs text-muted-foreground">
          “{pending.action_text}” — several elements match equally well. Pick the right one and the
          agent re-walks the journey with your choice.
        </p>
        <div className="grid gap-2 md:grid-cols-2">
          {pending.candidates.map((c) => (
            <Button
              key={c.element_name}
              variant="outline"
              size="sm"
              disabled={confirmStep.isPending}
              onClick={async () => {
                try {
                  await confirmStep.mutateAsync({
                    runId: run.id,
                    stepIndex: pending.step_index,
                    elementName: c.element_name,
                  });
                  toast({ title: "Choice recorded", description: "Re-walking the journey…" });
                } catch (err: unknown) {
                  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
                  toast({ title: "Could not confirm", description: detail ?? "Unknown error", variant: "error" });
                }
              }}
            >
              <span className="truncate">
                {c.role}: {c.accessible_name || c.element_name}
              </span>
            </Button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function GroundedAutomationContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { toast } = useToast();

  const projectId = Number(searchParams.get("project")) || null;
  const [view, setView] = useState<"list" | "new">("list");
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);

  const { data: pocStatus, isLoading: statusLoading } = usePocStatus();
  const enabled = pocStatus?.enabled ?? false;
  const { data: runs = [], isLoading: runsLoading, refetch: refetchRuns } = usePocRuns(projectId, enabled);
  const { data: runDetail } = usePocRun(enabled ? selectedRunId : null);
  const startCapture = useStartPocCapture(projectId);
  const generate = useGeneratePocScript(projectId);
  const cancelRun = useCancelPocRun(projectId);

  useEffect(() => {
    projectsApi
      .list()
      .then((res) => {
        if (res.data.length > 0 && !searchParams.get("project")) {
          const params = new URLSearchParams(searchParams.toString());
          params.set("project", String(res.data[0].id));
          router.push(`${pathname}?${params.toString()}`);
        }
      })
      .catch(() => console.error("Could not load projects."));
  }, [searchParams, router, pathname]);

  const showingRun = selectedRunId !== null && view === "list";
  const captureBusy = useMemo(
    () => Boolean(runDetail && (runDetail.status === "capturing" || runDetail.status === "generating")),
    [runDetail],
  );

  async function act(fn: () => Promise<{ message: string }>, errTitle: string) {
    try {
      const res = await fn();
      toast({ title: res.message });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast({ title: errTitle, description: detail ?? "Unknown error", variant: "error" });
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Target className="h-6 w-6 text-emerald-600" />
            <h1 className="text-xl font-semibold">Grounded Automation</h1>
            <Badge variant="success">PoC</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Evidence-first script generation: launch the application, capture every screen the test
            case touches, pass a deterministic coverage gate — and only then generate. 100% grounded,
            zero guesswork.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {showingRun && (
            <Button variant="outline" onClick={() => { setSelectedRunId(null); refetchRuns(); }}>
              <ArrowLeft className="mr-2 h-4 w-4" /> All Runs
            </Button>
          )}
          {view === "list" && !showingRun && enabled && (
            <Button onClick={() => setView("new")} disabled={!projectId}>
              <Plus className="mr-2 h-4 w-4" /> New Grounding Run
            </Button>
          )}
        </div>
      </div>

      {statusLoading && (
        <div className="flex h-40 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-emerald-600" />
        </div>
      )}

      {!statusLoading && !enabled && (
        <Card>
          <CardContent className="space-y-2 p-8 text-center">
            <ShieldAlert className="mx-auto h-8 w-8 text-amber-500" />
            <p className="text-sm font-semibold">Feature disabled</p>
            <p className="text-xs text-muted-foreground">
              {pocStatus?.message ?? "Set GROUNDED_AUTOMATION_ENABLED=true in the backend environment to activate the PoC."}
            </p>
          </CardContent>
        </Card>
      )}

      {enabled && view === "new" && (
        <NewRunForm
          projectId={projectId}
          onCancel={() => setView("list")}
          onCreated={(runId) => {
            setView("list");
            setSelectedRunId(runId);
          }}
        />
      )}

      {enabled && showingRun && runDetail && (
        <div className="space-y-4">
          <PipelineHeader status={runDetail.status} />
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm font-semibold">
              {runDetail.config.test_case_display_id} — {runDetail.config.test_case_title}
            </span>
            <Badge variant={statusVariant(runDetail.status)}>
              {STATUS_LABELS[runDetail.status] ?? runDetail.status}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {runDetail.config.application_name} · {runDetail.config.environment} ·{" "}
              {runDetail.config.target_url} · {runDetail.capture_mode} capture
            </span>
            {!["generated", "failed", "cancelled"].includes(runDetail.status) && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => act(() => cancelRun.mutateAsync(runDetail.id), "Could not cancel")}
                disabled={cancelRun.isPending}
              >
                <StopCircle className="mr-1 h-3 w-3 text-red-500" /> Cancel
              </Button>
            )}
          </div>
          {runDetail.error && (
            <div className="rounded-md border border-red-300 bg-red-50 p-3 text-xs text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300">
              {runDetail.error}
            </div>
          )}

          <RoutingPanel run={runDetail} />

          {(runDetail.status === "routing_ready" || runDetail.status === "gate_blocked") && (
            <Card>
              <CardContent className="space-y-3 p-6 text-center">
                <Camera className="mx-auto h-7 w-7 text-emerald-600" />
                <p className="text-sm">
                  {runDetail.status === "gate_blocked"
                    ? "Fix the gaps (test data, environment, blockers) and re-capture."
                    : "Launch the application and capture the test case's journey as evidence."}
                </p>
                <Button
                  onClick={() => act(() => startCapture.mutateAsync(runDetail.id), "Could not start capture")}
                  disabled={startCapture.isPending}
                >
                  {startCapture.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {runDetail.status === "gate_blocked" ? "Re-capture Evidence" : "Launch & Capture Evidence"}
                </Button>
              </CardContent>
            </Card>
          )}

          {captureBusy && (
            <Card>
              <CardContent className="space-y-3 p-6 text-center">
                <Loader2 className="mx-auto h-7 w-7 animate-spin text-violet-600" />
                <p className="text-sm font-semibold">
                  {runDetail.status === "capturing"
                    ? "Walking the application…"
                    : "Generating from captured evidence…"}
                </p>
                {(["capture", "generation"] as const).map((k) => {
                  const ar = runDetail.agent_runs[k];
                  return ar ? (
                    <p key={k} className="text-xs text-muted-foreground">
                      Agent run #{ar.id} — {ar.status}
                      {ar.progress_percent > 0 && ` · ${ar.progress_percent}%`}
                      {ar.progress_message && ` · ${ar.progress_message}`}
                    </p>
                  ) : null;
                })}
              </CardContent>
            </Card>
          )}

          {runDetail.status === "awaiting_confirmation" && (
            <ConfirmationPanel run={runDetail} projectId={projectId} />
          )}

          <EvidencePanel run={runDetail} />
          <CoveragePanel run={runDetail} />

          {runDetail.status === "gate_passed" && (
            <Card>
              <CardContent className="space-y-3 p-6 text-center">
                <Wand2 className="mx-auto h-7 w-7 text-emerald-600" />
                <p className="text-sm">
                  Every step is grounded in captured evidence. Generation is restricted to this
                  run&apos;s element catalog; the script then goes through the standard static gate,
                  live dry run and human approval.
                </p>
                <Button
                  onClick={() => act(() => generate.mutateAsync(runDetail.id), "Could not start generation")}
                  disabled={generate.isPending}
                >
                  {generate.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Generate Script from Evidence
                </Button>
              </CardContent>
            </Card>
          )}

          {runDetail.status === "generated" && (
            <Card>
              <CardContent className="space-y-3 p-5">
                <p className="text-sm font-semibold">Generated Scripts</p>
                {runDetail.scripts.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    Generation finished but produced no script — check the agent logs.
                  </p>
                )}
                {runDetail.scripts.map((s) => (
                  <div key={s.id} className="flex flex-wrap items-center gap-2 text-xs">
                    <Badge variant="info">{s.script_id}</Badge>
                    <span>v{s.version}</span>
                    <span>{s.framework}</span>
                    <Badge variant={statusVariant(s.status === "static_passed" ? "gate_passed" : s.status)}>
                      {s.status}
                    </Badge>
                    <a
                      className="text-violet-600 underline"
                      href={projectId ? `/automation?project=${projectId}` : "/automation"}
                    >
                      Review in AI Automation Studio →
                    </a>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {enabled && view === "list" && !showingRun && (
        <Card>
          <CardContent className="p-0">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <span className="text-sm font-semibold">Grounding Runs</span>
              <Button variant="ghost" size="sm" onClick={() => refetchRuns()}>
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 font-medium">Test Case</th>
                    <th className="px-4 py-2 font-medium">Application</th>
                    <th className="px-4 py-2 font-medium">Environment</th>
                    <th className="px-4 py-2 font-medium">Mode</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 font-medium">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {runsLoading && (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                        <Loader2 className="mx-auto h-4 w-4 animate-spin" />
                      </td>
                    </tr>
                  )}
                  {!runsLoading && runs.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                        No grounding runs yet. Click{" "}
                        <span className="font-medium">New Grounding Run</span> to launch the
                        application and capture evidence for an approved test case.
                      </td>
                    </tr>
                  )}
                  {runs.map((run) => (
                    <tr
                      key={run.id}
                      className="cursor-pointer border-b border-border/60 last:border-0 hover:bg-muted/40"
                      onClick={() => setSelectedRunId(run.id)}
                    >
                      <td className="px-4 py-2.5 font-medium">
                        {run.config.test_case_display_id} — {run.config.test_case_title}
                      </td>
                      <td className="px-4 py-2.5">{run.config.application_name ?? "—"}</td>
                      <td className="px-4 py-2.5">{run.config.environment}</td>
                      <td className="px-4 py-2.5">{run.capture_mode}</td>
                      <td className="px-4 py-2.5">
                        <span className="flex items-center gap-2">
                          <Badge variant={statusVariant(run.status)}>
                            {STATUS_LABELS[run.status] ?? run.status}
                          </Badge>
                          {isActivePocRun(run) && (
                            <Loader2 className="h-3 w-3 animate-spin text-violet-600" />
                          )}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground">
                        {run.created_at ? new Date(run.created_at).toLocaleString() : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function GroundedAutomationPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-emerald-600" />
        </div>
      }
    >
      <GroundedAutomationContent />
    </Suspense>
  );
}
