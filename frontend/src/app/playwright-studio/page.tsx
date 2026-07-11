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
import { projectsApi } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import {
  isActiveStudioRun,
  useCancelStudioRun,
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
  stepForStatus,
  studioStatusLabel,
  studioStatusVariant,
} from "@/components/playwright-studio/studio-utils";

function AgentProgressCard({
  title,
  detail,
  agentRuns,
  projectId,
}: {
  title: string;
  detail: string;
  agentRuns: Array<{ id: number; status: string; progress_percent: number; progress_message?: string | null }>;
  projectId: number | null;
}) {
  return (
    <Card>
      <CardContent className="space-y-3 p-6 text-center">
        <Loader2 className="mx-auto h-8 w-8 animate-spin text-violet-600" />
        <p className="text-sm font-semibold">{title}</p>
        <p className="text-xs text-muted-foreground">{detail}</p>
        {agentRuns.map((agentRun) => (
          <div key={agentRun.id} className="mx-auto max-w-md text-xs text-muted-foreground">
            Agent run #{agentRun.id} — {agentRun.status}
            {agentRun.progress_percent > 0 && ` · ${agentRun.progress_percent}%`}
            {agentRun.progress_message && ` · ${agentRun.progress_message}`}
          </div>
        ))}
        <a
          className="inline-flex items-center gap-1 text-xs text-violet-600 underline"
          href={projectId ? `/agents?project=${projectId}` : "/agents"}
        >
          <Search className="h-3 w-3" /> Watch live agent logs
        </a>
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

  const showingRun = selectedRunId !== null && view === "list";

  return (
    <div className="space-y-4 p-6">
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
                        {run.config.runner_mode === "docker"
                          ? `Docker ×${run.config.parallelism ?? 1}`
                          : "Local"}
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
