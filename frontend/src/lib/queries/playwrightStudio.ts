"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  mcpConnectionsApi,
  playwrightStudioApi,
  type McpConnectionCreatePayload,
  type StudioRun,
  type StudioRunCreatePayload,
} from "@/lib/api";
import { useAIAction } from "@/hooks/useAIAction";
import { AI_PROCESSING_STAGES } from "@/lib/ai-processing-stages";

export const studioKeys = {
  runs: (projectId: number) => ["playwright-studio", "runs", projectId] as const,
  run: (runId: number) => ["playwright-studio", "run", runId] as const,
  mcpConnections: (projectId: number) => ["mcp-connections", projectId] as const,
};

// Stages with an agent/execution in flight — the UI polls while one of
// these is active; gate stages (plan_ready/scripts_ready) wait for a human.
const ACTIVE_STUDIO_STATUSES = new Set(["exploring", "generating", "executing", "healing"]);

export function isActiveStudioRun(run: Pick<StudioRun, "status"> | undefined | null): boolean {
  return Boolean(run && ACTIVE_STUDIO_STATUSES.has(run.status));
}

export function useStudioRuns(projectId: number | null) {
  return useQuery({
    queryKey: studioKeys.runs(projectId ?? -1),
    queryFn: async () => (await playwrightStudioApi.listRuns(projectId as number)).data,
    enabled: projectId !== null && projectId > 0,
    refetchInterval: (query) =>
      query.state.data?.some(isActiveStudioRun) ? 5000 : false,
  });
}

export function useStudioRun(runId: number | null) {
  return useQuery({
    queryKey: studioKeys.run(runId ?? -1),
    queryFn: async () => (await playwrightStudioApi.getRun(runId as number)).data,
    enabled: runId !== null && runId > 0,
    refetchInterval: (query) => (isActiveStudioRun(query.state.data) ? 3500 : false),
  });
}

function useInvalidateStudio(projectId: number | null) {
  const queryClient = useQueryClient();
  return (runId?: number) => {
    if (projectId) queryClient.invalidateQueries({ queryKey: studioKeys.runs(projectId) });
    if (runId) queryClient.invalidateQueries({ queryKey: studioKeys.run(runId) });
  };
}

export function useCreateStudioRun(projectId: number | null) {
  const invalidate = useInvalidateStudio(projectId);
  return useMutation({
    mutationFn: async (payload: StudioRunCreatePayload) =>
      (await playwrightStudioApi.createRun(payload)).data,
    onSuccess: (run) => invalidate(run.id),
  });
}

export function useStartStudioRun(projectId: number | null) {
  const invalidate = useInvalidateStudio(projectId);
  const { runAIAction } = useAIAction();
  return useMutation({
    mutationFn: async (runId: number) => (
      await runAIAction({
        actionName: "start_playwright_studio",
        title: "Preparing Application Discovery",
        module: "Playwright AI Studio",
        artifactType: "Studio Run",
        projectId: projectId ?? undefined,
        stages: AI_PROCESSING_STAGES.applicationDiscovery,
        successMessage: "Playwright AI Studio started successfully.",
        execute: () => playwrightStudioApi.startRun(runId),
      })
    ).data,
    onSuccess: (data) => invalidate(data.studio_run_id),
  });
}

export function useApproveStudioPlan(projectId: number | null) {
  const invalidate = useInvalidateStudio(projectId);
  const { runAIAction } = useAIAction();
  return useMutation({
    mutationFn: async (vars: { runId: number; includedKeys?: string[] | null; notes?: string }) =>
      (await runAIAction({
        actionName: "generate_studio_scripts",
        title: "Generating Playwright Scripts",
        module: "Playwright AI Studio",
        artifactType: "Automation Scripts",
        projectId: projectId ?? undefined,
        stages: AI_PROCESSING_STAGES.scriptGeneration,
        successMessage: "Studio script generation started.",
        execute: () => playwrightStudioApi.approvePlan(vars.runId, {
          included_keys: vars.includedKeys ?? null,
          notes: vars.notes,
        }),
      })).data,
    onSuccess: (data) => invalidate(data.studio_run_id),
  });
}

export function useApproveStudioScripts(projectId: number | null) {
  const invalidate = useInvalidateStudio(projectId);
  return useMutation({
    mutationFn: async (vars: { runId: number; notes?: string }) =>
      (await playwrightStudioApi.approveScripts(vars.runId, { notes: vars.notes })).data,
    onSuccess: (data) => invalidate(data.studio_run_id),
  });
}

export function useCancelStudioRun(projectId: number | null) {
  const invalidate = useInvalidateStudio(projectId);
  return useMutation({
    mutationFn: async (runId: number) => (await playwrightStudioApi.cancelRun(runId)).data,
    onSuccess: (data) => invalidate(data.studio_run_id),
  });
}

// ── MCP connections ──────────────────────────────────────────────────────────

export function useMcpConnections(projectId: number | null) {
  return useQuery({
    queryKey: studioKeys.mcpConnections(projectId ?? -1),
    queryFn: async () => (await mcpConnectionsApi.list(projectId as number)).data,
    enabled: projectId !== null && projectId > 0,
  });
}

export function useCreateMcpConnection(projectId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: McpConnectionCreatePayload) =>
      (await mcpConnectionsApi.create(payload)).data,
    onSuccess: () => {
      if (projectId) queryClient.invalidateQueries({ queryKey: studioKeys.mcpConnections(projectId) });
    },
  });
}

export function useDeleteMcpConnection(projectId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => (await mcpConnectionsApi.remove(id)).data,
    onSuccess: () => {
      if (projectId) queryClient.invalidateQueries({ queryKey: studioKeys.mcpConnections(projectId) });
    },
  });
}

export function useTestMcpConnection(projectId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => (await mcpConnectionsApi.test(id)).data,
    onSuccess: () => {
      if (projectId) queryClient.invalidateQueries({ queryKey: studioKeys.mcpConnections(projectId) });
    },
  });
}

export function useTestAllMcpConnections(projectId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await mcpConnectionsApi.testAll(projectId as number)).data,
    onSuccess: () => {
      if (projectId) queryClient.invalidateQueries({ queryKey: studioKeys.mcpConnections(projectId) });
    },
  });
}
