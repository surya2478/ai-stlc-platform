"use client";

import { useEffect, useMemo, useState } from "react";
import { Globe, Loader2, Sparkles } from "lucide-react";
import { api, type StudioRunnerMode } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { useCreateStudioRun, useStartStudioRun } from "@/lib/queries/playwrightStudio";
import { McpConnectionsPanel } from "./McpConnectionsPanel";

type ProjectApplication = {
  id: number;
  name: string;
  environment_urls: Record<string, string>;
  is_default?: boolean;
  is_active?: boolean;
};

const COVERAGE_OPTIONS = [
  { key: "positive", label: "Positive" },
  { key: "negative", label: "Negative" },
  { key: "boundary", label: "Boundary" },
  { key: "e2e", label: "E2E" },
];

const inputClass =
  "w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500";
const labelClass = "mb-1 block text-xs font-medium text-muted-foreground";

/** Step 1 — Planner Input. Application-first: pick a registered application
 * + environment, describe the objective, bound the exploration, and launch
 * the planner agent. */
export function NewRunForm({
  projectId,
  onStarted,
  onCancel,
}: {
  projectId: number | null;
  onStarted: (runId: number) => void;
  onCancel: () => void;
}) {
  const { toast } = useToast();
  const createRun = useCreateStudioRun(projectId);
  const startRun = useStartStudioRun(projectId);

  const [applications, setApplications] = useState<ProjectApplication[]>([]);
  const [name, setName] = useState("");
  const [applicationId, setApplicationId] = useState<number | null>(null);
  const [environment, setEnvironment] = useState("");
  const [objective, setObjective] = useState("");
  const [coverageTypes, setCoverageTypes] = useState<string[]>(["positive", "negative"]);
  const [excludedPaths, setExcludedPaths] = useState("");
  const [maxPages, setMaxPages] = useState(10);
  const [maxMinutes, setMaxMinutes] = useState(20);
  const [targetTestCaseCount, setTargetTestCaseCount] = useState<string>("");
  // Executor, not docker: "docker" drives the daemon from whichever service
  // dispatches the job, and neither the backend nor the worker mounts the
  // socket (AUT-002) — so every run started from this form failed with
  // "docker daemon not reachable" before a browser ever opened. The executor
  // service is the one that holds the socket, and it runs the same containers.
  const [runnerMode, setRunnerMode] = useState<StudioRunnerMode>("executor");
  const [parallelism, setParallelism] = useState(4);
  const [timeoutSeconds, setTimeoutSeconds] = useState(600);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    api
      .get<{ applications: ProjectApplication[] }>(`/projects/${projectId}/applications`)
      .then((res) => {
        const active = (res.data.applications ?? []).filter((a) => a.is_active !== false);
        setApplications(active);
        const preferred = active.find((a) => a.is_default) ?? active[0];
        if (preferred) {
          setApplicationId(preferred.id);
          const envs = Object.keys(preferred.environment_urls ?? {});
          if (envs.length > 0) setEnvironment(envs.includes("SIT") ? "SIT" : envs[0]);
        }
      })
      .catch(() => setApplications([]));
  }, [projectId]);

  const selectedApp = useMemo(
    () => applications.find((a) => a.id === applicationId) ?? null,
    [applications, applicationId],
  );
  const environmentOptions = useMemo(
    () => Object.keys(selectedApp?.environment_urls ?? {}),
    [selectedApp],
  );
  const targetUrl = selectedApp?.environment_urls?.[environment] ?? "";

  function toggleCoverage(key: string) {
    setCoverageTypes((prev) =>
      prev.includes(key) ? prev.filter((c) => c !== key) : [...prev, key],
    );
  }

  async function handleSubmit() {
    if (!projectId || !applicationId || !environment || !name.trim()) return;
    setSubmitting(true);
    try {
      const run = await createRun.mutateAsync({
        project_id: projectId,
        name: name.trim(),
        application_id: applicationId,
        environment,
        objective: objective.trim(),
        coverage_types: coverageTypes,
        excluded_paths: excludedPaths
          .split(",")
          .map((p) => p.trim())
          .filter(Boolean),
        max_pages: maxPages,
        max_minutes: maxMinutes,
        target_test_case_count: targetTestCaseCount.trim() ? Number(targetTestCaseCount) : undefined,
        framework: "playwright",
        runner_mode: runnerMode,
        parallelism,
        timeout_seconds: timeoutSeconds,
      });
      await startRun.mutateAsync(run.id);
      toast({
        title: "Exploration started",
        description: "The planner agent is mapping the application and drafting a test plan.",
      });
      onStarted(run.id);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast({
        title: "Could not start run",
        description: typeof detail === "string" ? detail : "Unknown error",
        variant: "error",
      });
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = Boolean(projectId && applicationId && environment && name.trim() && targetUrl);

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="flex items-center gap-2">
            <Globe className="h-4 w-4 text-violet-600" />
            <span className="text-sm font-semibold">Application Context</span>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div>
              <label className={labelClass}>Run name *</label>
              <input
                className={inputClass}
                placeholder="e.g. B2B Portal SIT sweep"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div>
              <label className={labelClass}>Application *</label>
              <select
                className={inputClass}
                value={applicationId ?? ""}
                onChange={(e) => {
                  const id = Number(e.target.value);
                  setApplicationId(id);
                  const app = applications.find((a) => a.id === id);
                  const envs = Object.keys(app?.environment_urls ?? {});
                  setEnvironment(envs.includes(environment) ? environment : envs[0] ?? "");
                }}
              >
                {applications.length === 0 && <option value="">No applications configured</option>}
                {applications.map((app) => (
                  <option key={app.id} value={app.id}>{app.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass}>Environment *</label>
              <select
                className={inputClass}
                value={environment}
                onChange={(e) => setEnvironment(e.target.value)}
              >
                {environmentOptions.length === 0 && <option value="">No environments</option>}
                {environmentOptions.map((env) => (
                  <option key={env} value={env}>{env}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className={labelClass}>Target Application URL</label>
            <div className={cn(inputClass, "flex items-center justify-between bg-muted/40")}>
              <span className="truncate">{targetUrl || "Select an application + environment with a configured URL"}</span>
              {targetUrl && <Badge variant="success">resolved</Badge>}
            </div>
            {!targetUrl && selectedApp && (
              <p className="mt-1 text-[11px] text-amber-600">
                No URL configured for {selectedApp.name} in “{environment}” — add one under Settings → Applications.
              </p>
            )}
          </div>
          <div>
            <label className={labelClass}>Planner Objective *</label>
            <input
              className={inputClass}
              maxLength={500}
              placeholder="e.g. Explore and create a plan for B2B mobile order creation"
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
            />
            <p className="mt-1 text-[11px] text-muted-foreground">
              Mentioning a count here (e.g. “generate 5 test cases”) is honored on a best-effort basis —
              for a reliable cap, use “Target test case count” below instead.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-violet-600" />
            <span className="text-sm font-semibold">Exploration & Execution Settings</span>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div>
              <label className={labelClass}>Coverage types</label>
              <div className="flex flex-wrap gap-1">
                {COVERAGE_OPTIONS.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    onClick={() => toggleCoverage(option.key)}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-xs",
                      coverageTypes.includes(option.key)
                        ? "border-violet-600 bg-violet-600 text-white"
                        : "border-border bg-card text-muted-foreground hover:border-violet-300",
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className={labelClass}>Max pages to explore</label>
              <input
                type="number" min={1} max={25} className={inputClass}
                value={maxPages}
                onChange={(e) => setMaxPages(Math.max(1, Math.min(25, Number(e.target.value) || 1)))}
              />
            </div>
            <div>
              <label className={labelClass}>Max exploration time (min)</label>
              <input
                type="number" min={1} max={60} className={inputClass}
                value={maxMinutes}
                onChange={(e) => setMaxMinutes(Math.max(1, Math.min(60, Number(e.target.value) || 1)))}
              />
            </div>
            <div>
              <label className={labelClass}>Target test case count (optional)</label>
              <input
                type="number" min={1} max={200} className={inputClass}
                placeholder="e.g. 5 — leave blank to let coverage decide"
                value={targetTestCaseCount}
                onChange={(e) => setTargetTestCaseCount(e.target.value)}
              />
            </div>
            <div>
              <label className={labelClass}>Browser</label>
              <select className={inputClass} value="chromium" disabled>
                <option value="chromium">Chromium (headless)</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className={labelClass}>Excluded areas (comma-separated paths)</label>
              <input
                className={inputClass}
                placeholder="e.g. /admin, /settings, /profile/delete"
                value={excludedPaths}
                onChange={(e) => setExcludedPaths(e.target.value)}
              />
            </div>
            <div>
              <label className={labelClass}>Execution runner</label>
              <select
                className={inputClass}
                value={runnerMode}
                onChange={(e) => setRunnerMode(e.target.value as StudioRunnerMode)}
              >
                <option value="executor">Executor (isolated service, parallel)</option>
                <option value="docker">Docker containers (needs the socket here)</option>
                <option value="local">Local subprocess (sequential)</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>
                {runnerMode === "local" ? "Parallel runners" : "Parallel containers"}
              </label>
              <input
                type="number" min={1} max={16} className={inputClass}
                value={parallelism}
                disabled={runnerMode === "local"}
                onChange={(e) => setParallelism(Math.max(1, Math.min(16, Number(e.target.value) || 1)))}
              />
            </div>
            <div>
              <label className={labelClass}>Per-script timeout (s)</label>
              <input
                type="number" min={30} max={3600} className={inputClass}
                value={timeoutSeconds}
                onChange={(e) => setTimeoutSeconds(Math.max(30, Math.min(3600, Number(e.target.value) || 600)))}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <McpConnectionsPanel projectId={projectId} />

      <div className="flex items-center justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
        <Button onClick={handleSubmit} disabled={!canSubmit || submitting}>
          {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
          Explore Application and Create Test Plan
        </Button>
      </div>
    </div>
  );
}
