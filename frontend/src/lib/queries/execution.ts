"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  aiExecutionApi,
  automationApi,
  executionApi,
  type AiRunDetail,
  type ExecutionResult,
  type ExecutionRun,
} from "@/lib/api";

/** Run statuses that mean work is still in flight and worth polling for. */
export const ACTIVE_RUN_STATUSES = new Set([
  "pending",
  "queued",
  "running",
  "review_required",
]);

export function isActiveRun(run: Pick<ExecutionRun, "status">): boolean {
  return ACTIVE_RUN_STATUSES.has(String(run.status).toLowerCase());
}

export const executionKeys = {
  runs: (projectId: number) => ["execution", "runs", projectId] as const,
  run: (runId: number) => ["execution", "run", runId] as const,
  results: (runId: number) => ["execution", "results", runId] as const,
  aiRun: (runId: number) => ["execution", "ai-run", runId] as const,
  governance: () => ["execution", "ai-governance"] as const,
  runnerStatus: () => ["automation", "runner-status"] as const,
};

/**
 * Project runs with live polling: refetches every 4s while any run is
 * active (pending/queued/running/review_required), otherwise stops.
 */
export function useRuns(projectId: number | null) {
  return useQuery({
    queryKey: executionKeys.runs(projectId ?? -1),
    queryFn: async () => (await executionApi.listRuns(projectId as number)).data,
    enabled: projectId !== null && projectId > 0,
    refetchInterval: (query) => {
      const runs = query.state.data;
      return runs?.some(isActiveRun) ? 4000 : false;
    },
  });
}

export function useRun(runId: number | null) {
  return useQuery({
    queryKey: executionKeys.run(runId ?? -1),
    queryFn: async () => (await executionApi.getRun(runId as number)).data,
    enabled: runId !== null && runId > 0,
    refetchInterval: (query) => {
      const run = query.state.data;
      return run && isActiveRun(run) ? 3000 : false;
    },
  });
}

export function useRunResults(runId: number | null, opts?: { enabled?: boolean }) {
  return useQuery<ExecutionResult[]>({
    queryKey: executionKeys.results(runId ?? -1),
    queryFn: async () => (await executionApi.getResults(runId as number)).data,
    enabled: (opts?.enabled ?? true) && runId !== null && runId > 0,
  });
}

export function useAiRunDetail(runId: number | null, opts?: { enabled?: boolean }) {
  return useQuery<AiRunDetail>({
    queryKey: executionKeys.aiRun(runId ?? -1),
    queryFn: async () => (await aiExecutionApi.getRun(runId as number)).data,
    enabled: (opts?.enabled ?? true) && runId !== null && runId > 0,
    refetchInterval: (query) => {
      const detail = query.state.data;
      return detail && isActiveRun(detail.run) ? 3000 : false;
    },
  });
}

export function useAiGovernance() {
  return useQuery({
    queryKey: executionKeys.governance(),
    queryFn: async () => (await aiExecutionApi.governance()).data,
    staleTime: 5 * 60_000,
  });
}

/** Host framework availability (Playwright / Pytest). Refreshes every 30s. */
export function useRunnerStatus() {
  return useQuery({
    queryKey: executionKeys.runnerStatus(),
    queryFn: async () => (await automationApi.getRunnerStatus()).data,
    refetchInterval: 30_000,
  });
}

export function useSubmitAiReview(runId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      decision: "approve" | "override" | "request_rerun" | "reject";
      reason: string;
      override_status?: "completed" | "failed" | "auto_completed" | "cancelled";
    }) => (await aiExecutionApi.submitReview(runId, payload)).data,
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: executionKeys.aiRun(runId) });
      queryClient.invalidateQueries({ queryKey: executionKeys.runs(run.project_id) });
    },
  });
}

export function useFinalizeAiRun(runId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await aiExecutionApi.finalize(runId)).data,
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: executionKeys.aiRun(runId) });
      queryClient.invalidateQueries({ queryKey: executionKeys.runs(run.project_id) });
    },
  });
}
