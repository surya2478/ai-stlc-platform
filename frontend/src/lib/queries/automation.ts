"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { automationApi, type AutomationScript } from "@/lib/api";
import { executionKeys } from "@/lib/queries/execution";

export const automationKeys = {
  scripts: (projectId: number) => ["automation", "scripts", projectId] as const,
  planning: (projectId: number) => ["automation", "planning", projectId] as const,
  mappings: (projectId: number) => ["automation", "mappings", projectId] as const,
  executionHistory: (testCaseId: number) =>
    ["automation", "execution-history", testCaseId] as const,
};

export function useScripts(
  projectId: number | null,
  params?: { test_case_id?: number; status?: string },
) {
  return useQuery({
    queryKey: [...automationKeys.scripts(projectId ?? -1), params ?? {}],
    queryFn: async () => (await automationApi.list(projectId as number, params)).data,
    enabled: projectId !== null && projectId > 0,
  });
}

export function usePlanning(projectId: number | null) {
  return useQuery({
    queryKey: automationKeys.planning(projectId ?? -1),
    queryFn: async () => (await automationApi.getPlanning(projectId as number)).data,
    enabled: projectId !== null && projectId > 0,
  });
}

export function useAutomationMappings(
  projectId: number | null,
  params?: { test_case_id?: number; active_only?: boolean },
) {
  return useQuery({
    queryKey: [...automationKeys.mappings(projectId ?? -1), params ?? {}],
    queryFn: async () =>
      (await automationApi.getAutomationMappings(projectId as number, params)).data,
    enabled: projectId !== null && projectId > 0,
  });
}

export function useExecutionHistory(testCaseId: number | null, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: automationKeys.executionHistory(testCaseId ?? -1),
    queryFn: async () => (await automationApi.getExecutionHistory(testCaseId as number)).data,
    enabled: (opts?.enabled ?? true) && testCaseId !== null && testCaseId > 0,
  });
}

function invalidateScriptQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  script: AutomationScript,
) {
  queryClient.invalidateQueries({ queryKey: automationKeys.scripts(script.project_id) });
  queryClient.invalidateQueries({ queryKey: automationKeys.planning(script.project_id) });
}

export function useUpdateScript() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: Partial<AutomationScript> }) =>
      (await automationApi.update(id, data)).data,
    onSuccess: (script) => invalidateScriptQueries(queryClient, script),
  });
}

export function useApproveScript() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      action,
      notes,
    }: {
      id: number;
      action: "approve" | "reject";
      notes?: string;
    }) => (await automationApi.approve(id, action, notes)).data,
    onSuccess: (script) => invalidateScriptQueries(queryClient, script),
  });
}

export function useTransitionScript() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      action,
      notes,
    }: {
      id: number;
      action: "submit_for_review" | "request_changes" | "restore_draft";
      notes?: string;
    }) => (await automationApi.transition(id, action, notes)).data,
    onSuccess: (script) => invalidateScriptQueries(queryClient, script),
  });
}

export function useRegenerateScript() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (scriptId: number) =>
      (await automationApi.regenerateScript(scriptId)).data,
    onSuccess: (script) => invalidateScriptQueries(queryClient, script),
  });
}

/**
 * Triggers a local runner execution (202). On success invalidates the
 * project's run list so polling picks the new run up immediately.
 */
export function useExecuteScript(projectId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      scriptId,
      environment,
      timeoutSeconds,
    }: {
      scriptId: number;
      environment?: string;
      timeoutSeconds?: number;
    }) =>
      (
        await automationApi.executeScript(scriptId, {
          environment,
          timeout_seconds: timeoutSeconds,
        })
      ).data,
    onSuccess: () => {
      if (projectId) {
        queryClient.invalidateQueries({ queryKey: executionKeys.runs(projectId) });
      }
    },
  });
}

/**
 * Triggers a batch local-runner execution ("Run All Eligible") covering
 * several approved scripts as one ExecutionRun. On success invalidates the
 * project's run list so polling picks the new run up immediately.
 */
export function useExecuteBatch(projectId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      scriptIds,
      environment,
      timeoutSeconds,
      runName,
      parentRunId,
    }: {
      scriptIds: number[];
      environment?: string;
      timeoutSeconds?: number;
      runName?: string;
      parentRunId?: number;
    }) =>
      (
        await automationApi.executeBatch(projectId as number, scriptIds, {
          environment,
          timeout_seconds: timeoutSeconds,
          run_name: runName,
          parent_run_id: parentRunId,
        })
      ).data,
    onSuccess: () => {
      if (projectId) {
        queryClient.invalidateQueries({ queryKey: executionKeys.runs(projectId) });
      }
    },
  });
}

/** Best-effort cancel for an in-flight local-runner run (single or batch). */
export function useCancelRun(projectId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (runId: number) => (await automationApi.cancelRun(runId)).data,
    onSuccess: (_data, runId) => {
      if (projectId) {
        queryClient.invalidateQueries({ queryKey: executionKeys.runs(projectId) });
      }
      queryClient.invalidateQueries({ queryKey: executionKeys.run(runId) });
      queryClient.invalidateQueries({ queryKey: executionKeys.results(runId) });
    },
  });
}
