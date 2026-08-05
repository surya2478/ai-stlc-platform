"use client";

import { Suspense, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Bot,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  StopCircle,
} from "lucide-react";
import { projectsApi, type StudioRunnerMode } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import {
  isActiveStudioRun,
  useCancelStudioRun,
  useRetryStudioRun,
  useStartStudioRun,
  useStudioRun,
  useStudioRuns,
} from "@/lib/queries/playwrightStudio";
import { ArtifactsAudit } from "@/components/playwright-studio/ArtifactsAudit";
import { ExecutionPanel } from "@/components/playwright-studio/ExecutionPanel";
import { NewRunForm } from "@/components/playwright-studio/NewRunForm";
import { PlanReview } from "@/components/playwright-studio/PlanReview";
import { ScriptsReview } from "@/components/playwright-studio/ScriptsReview";
import { StudioStepsHeader } from "@/components/playwright-studio/StudioStepsHeader";
import {
  isTerminalStudioStatus,
  runnerIsContainerised,
  runnerModeLabel,
  stepForStatus,
  studioStatusLabel,
  studioStatusVariant,
} from "@/components/playwright-studio/studio-utils";

function elapsedLabel(since: string | null | undefined): string | null {
  if (!since) return null;
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(since).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s elapsed`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s elapsed`;
}

/**
 * What the run is doing, in the run's own words.
 *
 * This used to render a spinner and whatever the task wrapper had last
 * written, which was "Agent execution started · 30%" for the entire job — a
 * six-script wave sat on that for five and a half minutes with no way to tell
 * progress from a hang. The agent now narrates each script as it lands
 * (see app/services/agent_progress.py), so the bar and the message below are
 * real counts, not an animation.
 */
function AgentProgressCard({
  title,
  detail,
  agentRuns,
  projectId,
}: {
  title: string;
  detail: string;
  agentRuns: Array<{
    id: number;
    status: string;
    progress_percent: number;
    progress_message?: string | null;
    created_at?: string | null;
    updated_at?: string | null;
  }>;
  projectId: number | null;
}) {
  // Re-render once a second purely so "elapsed" stays honest between the
  // query's own polling intervals.
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <div className="flex items-center justify-center gap-2">
          <Loader2 className="h-5 w-5 animate-spin text-violet-600" />
          <p className="text-sm font-semibold">{title}</p>
        </div>
        <p className="text-center text-xs text-muted-foreground">{detail}</p>

        {agentRuns.map((agentRun) => {
          const percent = Math.max(0, Math.min(100, agentRun.progress_percent || 0));
          const elapsed = elapsedLabel(agentRun.created_at);
          const stalledFor = agentRun.updated_at
            ? Math.floor((Date.now() - new Date(agentRun.updated_at).getTime()) / 1000)
            : 0;
          return (
            <div key={agentRun.id} className="mx-auto max-w-lg space-y-1.5">
              <div className="flex items-baseline justify-between gap-2 text-xs">
                <span className="font-semibold text-slate-700 dark:text-slate-200">
                  {agentRun.progress_message || `Agent run #${agentRun.id} — ${agentRun.status}`}
                </span>
                <span className="shrink-0 tabular-nums text-muted-foreground">{percent}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                <div
                  className="h-full rounded-full bg-violet-600 transition-all duration-500"
                  style={{ width: `${percent}%` }}
                />
              </div>
              <div className="flex flex-wrap justify-between gap-2 text-[11px] text-muted-foreground">
                <span>Agent run #{agentRun.id} · {agentRun.status}</span>
                {elapsed && <span className="tabular-nums">{elapsed}</span>}
              </div>
              {/* Long gaps are normal here — a script takes up to three model
                  calls (each retry feeds the exact failure back to the model),
                  and generation runs one at a time against a local model.
                  Saying so is the difference between "working" and "stuck". */}
              {stalledFor > 45 && (
                <p className="text-[11px] text-amber-600 dark:text-amber-400">
                  No update for {Math.floor(stalledFor / 60)}m {String(stalledFor % 60).padStart(2, "0")}s —
                  a script takes up to three model calls, so a gap of a minute or two is expected.
                </p>
              )}
            </div>
          );
        })}

        <div className="text-center">
          <a
            className="inline-flex items-center gap-1 text-xs text-violet-600 underline"
            href={projectId ? `/agents?project=${projectId}` : "/agents"}
          >
            <Search className="h-3 w-3" /> Watch live agent logs
          </a>
        </div>
      </CardContent>
    </Card>
  );
}

function PlaywrightStudioContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { toast } = useToast();

  const projectId = Number(searchParams.get("project")) || null;
  const [view, setView] = useState<"list" | "new">("list");
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);

  const { data: runs = [], isLoading: runsLoading, refetch: refetchRuns } = useStudioRuns(projectId);
  const { data: runDetail } = useStudioRun(selectedRunId);
  const startRun = useStartStudioRun(projectId);
  const cancelRun = useCancelStudioRun(projectId);
  const retryRun = useRetryStudioRun(projectId);
  // Defaults to the executor rather than "same as before": a run reaches this
  // retry bar because it failed, and the most common reason is that it asked
  // for a runner the dispatching service cannot drive. Repeating that choice
  // reproduces the failure, so the isolated executor is the useful default.
  const [retryRunnerMode, setRetryRunnerMode] = useState<StudioRunnerMode | "">("executor");

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

  async function handleCancel() {
    if (!selectedRunId) return;
    try {
      await cancelRun.mutateAsync(selectedRunId);
      toast({ title: "Run cancelled", description: "In-flight agent and execution tasks were revoked." });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast({ title: "Could not cancel", description: detail ?? "Unknown error", variant: "error" });
    }
  }

  // Mirrors studio_service's own inference so the label matches what the
  // server will actually do: executions failed -> re-execute; otherwise a
  // failed run with approved test cases -> regenerate; else re-explore.
  const failedCount = runDetail?.failed_test_case_ids?.length ?? 0;
  // An ExecutionRun reports "completed" when it finishes, whatever its results
  // say — so failing TESTS, not just a failed run, mean the execution stage is
  // what needs attention.
  const executionsFailed =
    (runDetail?.executions ?? []).some((e) => e.status === "failed" || e.failed > 0) || failedCount > 0;
  const retryStage = executionsFailed
    ? {
        kind: "execution" as const,
        title: failedCount
          ? `${failedCount} test case(s) failed`
          : "The tests ran but the execution failed",
        detail: "Re-run the same approved scripts, or regenerate only the ones that failed. If the whole run failed on infrastructure rather than on the tests, change the runner first.",
        action: "Re-run Execution",
      }
    : runDetail?.test_case_ids?.length
      ? {
          kind: "generation" as const,
          title: "Script generation failed",
          detail: `Retry generation for the ${runDetail.test_case_ids.length} approved test case(s). The reviewed plan is kept.`,
          action: "Retry Generation",
        }
      : {
          kind: "exploration" as const,
          title: "Exploration failed",
          detail: "Nothing approvable was produced, so this maps the application again.",
          action: "Retry Exploration",
        };

  async function handleRetry(onlyFailed = false) {
    if (!selectedRunId) return;
    try {
      const result = await retryRun.mutateAsync({
        runId: selectedRunId,
        runnerMode: !onlyFailed && retryStage.kind === "execution" ? retryRunnerMode || undefined : undefined,
        onlyFailed,
      });
      toast({ title: "Retrying", description: result.message });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast({ title: "Could not retry", description: detail ?? "Unknown error", variant: "error" });
    }
  }

  const showingRun = selectedRunId !== null && view === "list";

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Bot className="h-6 w-6 text-violet-600" />
            <h1 className="text-xl font-semibold">Playwright AI Studio</h1>
            <Badge variant="purple">BETA</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            AI-powered end-to-end test generation: explore the application, prepare a test plan,
            generate scripts, execute in Docker, and heal failures — with bulk approvals at each stage.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {showingRun && (
            <Button variant="outline" onClick={() => { setSelectedRunId(null); refetchRuns(); }}>
              <ArrowLeft className="mr-2 h-4 w-4" /> View All Runs
            </Button>
          )}
          {view === "list" && !showingRun && (
            <Button onClick={() => setView("new")} disabled={!projectId}>
              <Plus className="mr-2 h-4 w-4" /> New Run
            </Button>
          )}
        </div>
      </div>

      {/* New run wizard (Step 1) */}
      {view === "new" && (
        <>
          <StudioStepsHeader currentStep={1} />
          <NewRunForm
            projectId={projectId}
            onCancel={() => setView("list")}
            onStarted={(runId) => {
              setView("list");
              setSelectedRunId(runId);
            }}
          />
        </>
      )}

      {/* Run detail (Steps 2-5) */}
      {showingRun && runDetail && (
        <div className="space-y-4">
          <StudioStepsHeader currentStep={stepForStatus(runDetail.status)} />
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm font-semibold">{runDetail.name}</span>
            <Badge variant={studioStatusVariant(runDetail.status)}>
              {studioStatusLabel(runDetail.status)}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {runDetail.config.application_name} · {runDetail.config.environment} ·{" "}
              {runDetail.config.target_url}
            </span>
            {!isTerminalStudioStatus(runDetail.status) && runDetail.status !== "draft" && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleCancel}
                disabled={cancelRun.isPending}
              >
                <StopCircle className="mr-1 h-3 w-3 text-red-500" /> Cancel Run
              </Button>
            )}
          </div>
          {runDetail.error && (
            <div className="rounded-md border border-red-300 bg-red-50 p-3 text-xs text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300">
              {runDetail.error}
            </div>
          )}

          {/* Retry lives on its own rather than inside the error banner: a run
              whose every test failed has NO error text — _reconcile_status
              calls it "completed" once the executions reach a terminal state,
              pass or fail — so a retry attached to the banner never appeared
              for the one case that most needed it. `can_retry` is computed
              server-side from the executions themselves. */}
          {runDetail.can_retry && (
            <div className="flex flex-wrap items-center gap-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-xs dark:border-amber-800 dark:bg-amber-950/30">
              <RefreshCw className="h-4 w-4 shrink-0 text-amber-600" />
              <div className="min-w-[18rem] flex-1">
                <p className="font-semibold text-amber-900 dark:text-amber-200">{retryStage.title}</p>
                <p className="mt-0.5 text-amber-800/80 dark:text-amber-300/80">{retryStage.detail}</p>
              </div>
              {retryStage.kind === "execution" && (
                <label className="flex items-center gap-1.5 text-amber-900 dark:text-amber-200">
                  Runner
                  <select
                    value={retryRunnerMode}
                    onChange={(e) => setRetryRunnerMode(e.target.value as StudioRunnerMode | "")}
                    className="h-8 rounded-md border border-amber-300 bg-white px-2 text-xs font-semibold text-slate-700 outline-none dark:bg-slate-900 dark:text-slate-200"
                  >
                    <option value="">Same as before{runDetail.config.runner_mode ? ` (${runDetail.config.runner_mode})` : ""}</option>
                    <option value="executor">Executor (isolated service)</option>
                    <option value="docker">Docker (needs the socket on the worker)</option>
                    <option value="local">Local (runs inside the worker)</option>
                  </select>
                </label>
              )}
              {/* Two distinct intents, so two buttons rather than one that
                  guesses: re-run what exists, or rebuild only what broke. The
                  second is disabled with a reason when nothing has actually
                  failed yet, so it never silently does nothing. */}
              <Button
                size="sm"
                variant="outline"
                disabled={retryRun.isPending || failedCount === 0}
                title={
                  failedCount === 0
                    ? "No script in this run has failed — there is nothing to regenerate."
                    : `Regenerate only the ${failedCount} failed script(s). The ones that work are left untouched.`
                }
                onClick={() => handleRetry(true)}
              >
                <RefreshCw className="mr-1.5 h-3 w-3" />
                Regenerate {failedCount || ""} Failed
              </Button>
              <Button size="sm" variant="outline" disabled={retryRun.isPending} onClick={() => handleRetry(false)}>
                {retryRun.isPending
                  ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
                  : <RefreshCw className="mr-1.5 h-3 w-3" />}
                {retryStage.action}
              </Button>
            </div>
          )}

          {runDetail.status === "draft" && (
            <Card>
              <CardContent className="space-y-3 p-6 text-center">
                <p className="text-sm">This run hasn&apos;t started exploring yet.</p>
                <Button
                  onClick={() => startRun.mutate(runDetail.id)}
                  disabled={startRun.isPending}
                >
                  {startRun.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Explore Application and Create Test Plan
                </Button>
              </CardContent>
            </Card>
          )}
          {runDetail.status === "exploring" && (
            <AgentProgressCard
              title="Exploring the application…"
              detail={`The planner agent is crawling ${runDetail.config.target_url} (up to ${runDetail.config.max_pages ?? 10} pages), capturing real locators, and drafting test cases.`}
              agentRuns={runDetail.agent_runs.planner ? [runDetail.agent_runs.planner] : []}
              projectId={projectId}
            />
          )}
          {runDetail.status === "plan_ready" && (
            <PlanReview projectId={projectId} run={runDetail} />
          )}
          {runDetail.status === "generating" && (
            <AgentProgressCard
              title="Generating automation scripts…"
              detail="Each approved test case becomes a generation contract, compiled to Playwright code, then static-gated and dry-run automatically. Failures auto-classify and repair."
              agentRuns={runDetail.agent_runs.generation}
              projectId={projectId}
            />
          )}
          {runDetail.status === "scripts_ready" && (
            <ScriptsReview projectId={projectId} run={runDetail} />
          )}
          {(runDetail.status === "executing" || runDetail.status === "healing") && (
            <ExecutionPanel run={runDetail} />
          )}
          {isTerminalStudioStatus(runDetail.status) && <ArtifactsAudit run={runDetail} />}
        </div>
      )}

      {/* Runs list */}
      {view === "list" && !showingRun && (
        <Card>
          <CardContent className="p-0">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <span className="text-sm font-semibold">Studio Runs</span>
              <Button variant="ghost" size="sm" onClick={() => refetchRuns()}>
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 font-medium">Run</th>
                    <th className="px-4 py-2 font-medium">Application</th>
                    <th className="px-4 py-2 font-medium">Environment</th>
                    <th className="px-4 py-2 font-medium">Runner</th>
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
                        No Studio runs yet. Click <span className="font-medium">New Run</span> to point
                        the planner at an application and generate its test plan.
                      </td>
                    </tr>
                  )}
                  {runs.map((run) => (
                    <tr
                      key={run.id}
                      className="cursor-pointer border-b border-border/60 last:border-0 hover:bg-muted/40"
                      onClick={() => setSelectedRunId(run.id)}
                    >
                      <td className="px-4 py-2.5 font-medium">{run.name}</td>
                      <td className="px-4 py-2.5">{run.config.application_name ?? "—"}</td>
                      <td className="px-4 py-2.5">{run.config.environment}</td>
                      <td className="px-4 py-2.5">
                        {runnerIsContainerised(run.config.runner_mode)
                          ? `${runnerModeLabel(run.config.runner_mode)} ×${run.config.parallelism ?? 1}`
                          : runnerModeLabel(run.config.runner_mode)}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="flex items-center gap-2">
                          <Badge variant={studioStatusVariant(run.status)}>
                            {studioStatusLabel(run.status)}
                          </Badge>
                          {isActiveStudioRun(run) && (
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

export default function PlaywrightStudioPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-violet-600" />
        </div>
      }
    >
      <PlaywrightStudioContent />
    </Suspense>
  );
}
