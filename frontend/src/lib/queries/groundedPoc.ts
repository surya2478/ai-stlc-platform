"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { groundedPocApi, type PocGroundingRun } from "@/lib/api";
import { useAIAction } from "@/hooks/useAIAction";
import { AI_PROCESSING_STAGES } from "@/lib/ai-processing-stages";

export const groundedPocKeys = {
  status: ["grounded-poc", "status"] as const,
  runs: (projectId: number) => ["grounded-poc", "runs", projectId] as const,
  run: (runId: number) => ["grounded-poc", "run", runId] as const,
  evidence: (runId: number, evidenceId: number) =>
    ["grounded-poc", "evidence", runId, evidenceId] as const,
};

// Stages with an agent in flight — the UI polls while one is active; gate
// stages (gate_passed/gate_blocked/awaiting_confirmation) wait for a human.
const ACTIVE_POC_STATUSES = new Set(["capturing", "generating"]);

export function isActivePocRun(run: Pick<PocGroundingRun, "status"> | undefined | null): boolean {
  return Boolean(run && ACTIVE_POC_STATUSES.has(run.status));
}

export function usePocStatus() {
  return useQuery({
    queryKey: groundedPocKeys.status,
    queryFn: async () => (await groundedPocApi.status()).data,
    staleTime: 60_000,
  });
}

export function usePocRuns(projectId: number | null, enabled = true) {
  return useQuery({
    queryKey: groundedPocKeys.runs(projectId ?? -1),
    queryFn: async () => (await groundedPocApi.listRuns(projectId as number)).data,
    enabled: enabled && projectId !== null && projectId > 0,
    refetchInterval: (query) => (query.state.data?.some(isActivePocRun) ? 5000 : false),
  });
}

export function usePocRun(runId: number | null) {
  return useQuery({
    queryKey: groundedPocKeys.run(runId ?? -1),
    queryFn: async () => (await groundedPocApi.getRun(runId as number)).data,
    enabled: runId !== null && runId > 0,
    refetchInterval: (query) => (isActivePocRun(query.state.data) ? 3500 : false),
  });
}

export function usePocEvidence(runId: number | null, evidenceId: number | null) {
  return useQuery({
    queryKey: groundedPocKeys.evidence(runId ?? -1, evidenceId ?? -1),
    queryFn: async () =>
      (await groundedPocApi.getEvidence(runId as number, evidenceId as number)).data,
    enabled: runId !== null && evidenceId !== null && evidenceId > 0,
  });
}

function useInvalidatePoc(projectId: number | null) {
  const queryClient = useQueryClient();
  return (runId?: number) => {
    if (projectId) queryClient.invalidateQueries({ queryKey: groundedPocKeys.runs(projectId) });
    if (runId) queryClient.invalidateQueries({ queryKey: groundedPocKeys.run(runId) });
  };
}

export function useCreatePocRun(projectId: number | null) {
  const invalidate = useInvalidatePoc(projectId);
  return useMutation({
    mutationFn: async (payload: {
      project_id: number;
      test_case_id: number;
      environment: string;
      capture_mode?: string;
    }) => (await groundedPocApi.createRun(payload)).data,
    onSuccess: (run) => invalidate(run.id),
  });
}

export function useStartPocCapture(projectId: number | null) {
  const invalidate = useInvalidatePoc(projectId);
  const { runAIAction } = useAIAction();
  return useMutation({
    mutationFn: async (runId: number) => (
      await runAIAction({
        actionName: "start_grounded_capture",
        title: "Preparing Application Discovery",
        module: "Grounded Automation",
        artifactType: "Discovery Evidence",
        projectId: projectId ?? undefined,
        stages: AI_PROCESSING_STAGES.applicationDiscovery,
        successMessage: "Grounded evidence capture started.",
        execute: () => groundedPocApi.startCapture(runId),
      })
    ).data,
    onSuccess: (data) => invalidate(data.grounding_run_id),
  });
}

export function useConfirmPocStep(projectId: number | null) {
  const invalidate = useInvalidatePoc(projectId);
  return useMutation({
    mutationFn: async (vars: { runId: number; stepIndex: number; elementName: string }) =>
      (await groundedPocApi.confirmStep(vars.runId, {
        step_index: vars.stepIndex,
        element_name: vars.elementName,
      })).data,
    onSuccess: (data) => invalidate(data.grounding_run_id),
  });
}

export function useGeneratePocScript(projectId: number | null) {
  const invalidate = useInvalidatePoc(projectId);
  const { runAIAction } = useAIAction();
  return useMutation({
    mutationFn: async (runId: number) => (
      await runAIAction({
        actionName: "generate_grounded_script",
        title: "Generating Script from Evidence",
        module: "Grounded Automation",
        artifactType: "Automation Script",
        projectId: projectId ?? undefined,
        stages: AI_PROCESSING_STAGES.scriptGeneration,
        successMessage: "Grounded script generation started.",
        execute: () => groundedPocApi.generate(runId),
      })
    ).data,
    onSuccess: (data) => invalidate(data.grounding_run_id),
  });
}

export function useCancelPocRun(projectId: number | null) {
  const invalidate = useInvalidatePoc(projectId);
  return useMutation({
    mutationFn: async (runId: number) => (await groundedPocApi.cancelRun(runId)).data,
    onSuccess: (data) => invalidate(data.grounding_run_id),
  });
}
