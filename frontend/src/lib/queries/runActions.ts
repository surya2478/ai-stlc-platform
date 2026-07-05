"use client";

import { useMemo } from "react";
import type { ExecutionResult, ExecutionRun } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import { isActiveRun } from "@/lib/queries/execution";
import { useCancelRun, useExecuteBatch } from "@/lib/queries/automation";

const LOCAL_RUNNER_SOURCE_TYPES = new Set(["automation_local", "automation_local_batch"]);
// Mirrors the backend's cancel_automation_run status guard exactly (a
// broader "active" check would let the button render for e.g.
// review_required, which the endpoint would then reject with a 422).
const CANCELLABLE_STATUSES = new Set(["pending", "queued", "running"]);

export function isLocalRunnerRun(run: ExecutionRun | null): boolean {
  const sourceType = (run?.metadata_ as { source_type?: string } | undefined)?.source_type;
  return Boolean(sourceType && LOCAL_RUNNER_SOURCE_TYPES.has(sourceType));
}

/** Unique automation_script_id of every result whose test failed, errored, or was blocked. */
export function collectFailedScriptIds(results: ExecutionResult[]): number[] {
  const ids = new Set<number>();
  for (const r of results) {
    if (!["fail", "error", "blocked"].includes(String(r.status).toLowerCase())) continue;
    const scriptId = (r.metadata_ as { automation_script_id?: number } | undefined)?.automation_script_id;
    if (typeof scriptId === "number") ids.add(scriptId);
  }
  return Array.from(ids);
}

/**
 * Cancel / retry-failed / live-progress logic shared between RunDetailDrawer
 * and the Command Center's inline run panel — one implementation so both
 * surfaces enforce the exact same rules the backend enforces.
 */
export function useRunLifecycleActions(run: ExecutionRun | null, results: ExecutionResult[]) {
  const { toast } = useToast();
  const cancelRun = useCancelRun(run?.project_id ?? null);
  const executeBatch = useExecuteBatch(run?.project_id ?? null);

  const localRunnerRun = isLocalRunnerRun(run);
  const runActive = run != null && isActiveRun(run);
  const runCancellable = run != null && CANCELLABLE_STATUSES.has(run.status);
  const failedScriptIds = useMemo(() => collectFailedScriptIds(results), [results]);

  const progressPct = useMemo(() => {
    if (!run || !runActive || !run.total_tests) return null;
    const done = (run.passed ?? 0) + (run.failed ?? 0) + (run.skipped ?? 0);
    return Math.min(100, Math.round((done / run.total_tests) * 100));
  }, [run, runActive]);

  const handleCancel = async () => {
    if (!run) return;
    if (!window.confirm(`Cancel run ${run.execution_id}? Tests still pending will be marked skipped.`)) return;
    try {
      const res = await cancelRun.mutateAsync(run.id);
      toast({ title: "Run cancelled", description: res.message, variant: "success" });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({ title: "Could not cancel run", description: err?.response?.data?.detail ?? err?.message, variant: "error" });
    }
  };

  /** Retries the given script ids (defaults to every failed script) as a new
   * batch run linked back to this one via parent_run_id. */
  const handleRetry = async (scriptIds: number[], onSuccess?: (executionRunId: number) => void) => {
    if (!run || scriptIds.length === 0) return;
    try {
      const res = await executeBatch.mutateAsync({
        scriptIds,
        environment: run.environment,
        runName: `Retry: ${run.suite_name ?? run.execution_id}`,
        parentRunId: run.id,
      });
      toast({ title: "Retry queued", description: res.message, variant: "success" });
      onSuccess?.(res.execution_run_id);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({ title: "Could not queue retry", description: err?.response?.data?.detail ?? err?.message, variant: "error" });
    }
  };

  const handleRetryFailed = (onSuccess?: (executionRunId: number) => void) => handleRetry(failedScriptIds, onSuccess);

  return {
    localRunnerRun,
    runActive,
    runCancellable,
    failedScriptIds,
    progressPct,
    cancelPending: cancelRun.isPending,
    retryPending: executeBatch.isPending,
    handleCancel,
    handleRetry,
    handleRetryFailed,
  };
}
