"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  isLiveRecording,
  recorderApi,
  type Recording,
  type RecordingMode,
} from "@/lib/api";

export const recorderKeys = {
  recordings: (projectId: number, suiteId?: number | null) =>
    ["recorder", "recordings", projectId, suiteId ?? null] as const,
  recording: (sessionId: number) => ["recorder", "recording", sessionId] as const,
  context: (sessionId: number) => ["recorder", "context", sessionId] as const,
  preconditions: (sessionId: number) => ["recorder", "preconditions", sessionId] as const,
  steps: (sessionId: number) => ["recorder", "steps", sessionId] as const,
  actions: (sessionId: number) => ["recorder", "actions", sessionId] as const,
  mappings: (sessionId: number) => ["recorder", "mappings", sessionId] as const,
  checkpoints: (sessionId: number) => ["recorder", "checkpoints", sessionId] as const,
  segments: (sessionId: number) => ["recorder", "segments", sessionId] as const,
  bindings: (sessionId: number) => ["recorder", "bindings", sessionId] as const,
  notes: (sessionId: number) => ["recorder", "notes", sessionId] as const,
  captures: (sessionId: number) => ["recorder", "captures", sessionId] as const,
  latestView: (sessionId: number) => ["recorder", "latest-view", sessionId] as const,
  summary: (sessionId: number) => ["recorder", "summary", sessionId] as const,
  irDraft: (sessionId: number) => ["recorder", "ir-draft", sessionId] as const,
  activity: (sessionId: number) => ["recorder", "activity", sessionId] as const,
};

const enabledFor = (sessionId: number | null) => sessionId !== null && sessionId > 0;

/**
 * While a recording is live the browser is being driven asynchronously by the
 * capture worker, so the UI polls. Once it is not live nothing changes on its
 * own and polling would be pure noise.
 */
function livePoll(interval: number) {
  return (recording: Recording | undefined) => (isLiveRecording(recording) ? interval : false);
}

export function useRecordings(projectId: number | null, suiteId?: number | null) {
  return useQuery({
    queryKey: recorderKeys.recordings(projectId ?? -1, suiteId),
    queryFn: async () =>
      (await recorderApi.list(projectId as number, suiteId ? { suite_id: suiteId } : undefined)).data,
    enabled: enabledFor(projectId),
    refetchInterval: (query) => (query.state.data?.some(isLiveRecording) ? 5000 : false),
  });
}

export function useRecording(sessionId: number | null) {
  return useQuery({
    queryKey: recorderKeys.recording(sessionId ?? -1),
    queryFn: async () => (await recorderApi.get(sessionId as number)).data,
    enabled: enabledFor(sessionId),
    refetchInterval: (query) => livePoll(2500)(query.state.data),
  });
}

export function useRecorderContext(sessionId: number | null) {
  return useQuery({
    queryKey: recorderKeys.context(sessionId ?? -1),
    queryFn: async () => (await recorderApi.inheritedContext(sessionId as number)).data,
    enabled: enabledFor(sessionId),
  });
}

export function useRecorderPreconditions(sessionId: number | null) {
  return useQuery({
    queryKey: recorderKeys.preconditions(sessionId ?? -1),
    queryFn: async () => (await recorderApi.preconditions(sessionId as number)).data,
    enabled: enabledFor(sessionId),
  });
}

/**
 * The step the backend will actually attach the next action to. Not the same
 * as "the step whose status is ACTIVE": when nothing is explicitly active the
 * backend falls back to the first step with nothing recorded, so showing only
 * the explicit one would tell the user their action is going to be unmapped
 * when it is not.
 */
export function useResolvedActiveStep(sessionId: number | null, live: boolean) {
  return useQuery({
    queryKey: ["recorder", "active-step", sessionId ?? -1] as const,
    queryFn: async () => (await recorderApi.activeStep(sessionId as number)).data,
    enabled: enabledFor(sessionId),
    refetchInterval: live ? 4000 : false,
  });
}

/**
 * Polls while live. Step status is derived from recorded actions, and those
 * are created asynchronously by the capture worker *after* the API call that
 * queued them returns — so invalidating on mutation alone leaves the panel a
 * step behind until something else happens to refetch it.
 */
export function useRecorderSteps(sessionId: number | null, live: boolean) {
  return useQuery({
    queryKey: recorderKeys.steps(sessionId ?? -1),
    queryFn: async () => (await recorderApi.steps(sessionId as number)).data,
    enabled: enabledFor(sessionId),
    refetchInterval: live ? 2500 : false,
  });
}

export function useRecordedActions(sessionId: number | null, live: boolean) {
  return useQuery({
    queryKey: recorderKeys.actions(sessionId ?? -1),
    queryFn: async () => (await recorderApi.actions(sessionId as number)).data,
    enabled: enabledFor(sessionId),
    refetchInterval: live ? 2500 : false,
  });
}

export function useRecorderMappings(sessionId: number | null, live: boolean) {
  return useQuery({
    queryKey: recorderKeys.mappings(sessionId ?? -1),
    queryFn: async () => (await recorderApi.mappings(sessionId as number)).data,
    enabled: enabledFor(sessionId),
    refetchInterval: live ? 2500 : false,
  });
}

export function useRecorderCheckpoints(sessionId: number | null) {
  return useQuery({
    queryKey: recorderKeys.checkpoints(sessionId ?? -1),
    queryFn: async () => (await recorderApi.checkpoints(sessionId as number)).data,
    enabled: enabledFor(sessionId),
  });
}

export function useRecorderSegments(sessionId: number | null) {
  return useQuery({
    queryKey: recorderKeys.segments(sessionId ?? -1),
    queryFn: async () => (await recorderApi.segments(sessionId as number)).data,
    enabled: enabledFor(sessionId),
  });
}

export function useRecorderBindings(sessionId: number | null) {
  return useQuery({
    queryKey: recorderKeys.bindings(sessionId ?? -1),
    queryFn: async () => (await recorderApi.dataBindings(sessionId as number)).data,
    enabled: enabledFor(sessionId),
  });
}

export function useRecorderNotes(sessionId: number | null) {
  return useQuery({
    queryKey: recorderKeys.notes(sessionId ?? -1),
    queryFn: async () => (await recorderApi.notes(sessionId as number)).data,
    enabled: enabledFor(sessionId),
  });
}

export function useRecorderCaptures(sessionId: number | null, live: boolean) {
  return useQuery({
    queryKey: recorderKeys.captures(sessionId ?? -1),
    queryFn: async () => (await recorderApi.captures(sessionId as number)).data,
    enabled: enabledFor(sessionId),
    refetchInterval: live ? 4000 : false,
  });
}

/** The centre viewport's picture of the application — polled while live. */
export function useRecorderLatestView(sessionId: number | null, live: boolean) {
  return useQuery({
    queryKey: recorderKeys.latestView(sessionId ?? -1),
    queryFn: async () => (await recorderApi.latestView(sessionId as number)).data,
    enabled: enabledFor(sessionId),
    refetchInterval: live ? 2500 : false,
  });
}

export function useRecordingSummary(sessionId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: recorderKeys.summary(sessionId ?? -1),
    queryFn: async () => (await recorderApi.summary(sessionId as number)).data,
    enabled: enabled && enabledFor(sessionId),
  });
}

export function useIrDraft(sessionId: number | null) {
  return useQuery({
    queryKey: recorderKeys.irDraft(sessionId ?? -1),
    queryFn: async () => (await recorderApi.irDraft(sessionId as number)).data,
    enabled: enabledFor(sessionId),
  });
}

export function useRecorderActivity(sessionId: number | null) {
  return useQuery({
    queryKey: recorderKeys.activity(sessionId ?? -1),
    queryFn: async () => (await recorderApi.activity(sessionId as number)).data,
    enabled: enabledFor(sessionId),
  });
}

function useInvalidateRecorder(projectId: number | null, sessionId: number | null) {
  const queryClient = useQueryClient();
  return (scope: "all" | "steps" | "evidence" = "all") => {
    if (projectId) {
      queryClient.invalidateQueries({ queryKey: ["recorder", "recordings", projectId] });
    }
    if (!sessionId) return;
    const invalidate = (key: readonly unknown[]) => queryClient.invalidateQueries({ queryKey: key });
    invalidate(recorderKeys.recording(sessionId));
    invalidate(recorderKeys.steps(sessionId));
    invalidate(["recorder", "active-step", sessionId]);
    invalidate(recorderKeys.summary(sessionId));
    if (scope === "steps") return;
    invalidate(recorderKeys.actions(sessionId));
    invalidate(recorderKeys.mappings(sessionId));
    invalidate(recorderKeys.checkpoints(sessionId));
    invalidate(recorderKeys.segments(sessionId));
    invalidate(recorderKeys.bindings(sessionId));
    invalidate(recorderKeys.notes(sessionId));
    invalidate(recorderKeys.captures(sessionId));
    invalidate(recorderKeys.latestView(sessionId));
    invalidate(recorderKeys.preconditions(sessionId));
    invalidate(recorderKeys.activity(sessionId));
    invalidate(recorderKeys.irDraft(sessionId));
  };
}

export function useCreateRecording(projectId: number | null) {
  const invalidate = useInvalidateRecorder(projectId, null);
  return useMutation({
    mutationFn: async (payload: {
      suite_id: number; test_case_id: number; recording_mode: RecordingMode; environment?: string | null;
    }) => (await recorderApi.create(projectId as number, payload)).data,
    onSuccess: () => invalidate(),
  });
}

export function useRecorderCommand(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateRecorder(projectId, sessionId);
  return useMutation({
    mutationFn: async (payload: {
      command: string; reason?: string | null; params?: Record<string, unknown>;
    }) => (await recorderApi.command(sessionId as number, {
      ...payload,
      idempotency_key: `${sessionId}-${payload.command}-${crypto.randomUUID()}`,
    })).data,
    onSuccess: () => invalidate(),
  });
}

export function useRecordAction(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateRecorder(projectId, sessionId);
  return useMutation({
    mutationFn: async (payload: {
      action_family: string; target_ref?: string | null; target_semantic?: string | null;
      input_text?: string | null; url?: string | null; active_step_key?: string | null;
    }) => (await recorderApi.recordAction(sessionId as number, {
      ...payload,
      idempotency_key: `${sessionId}-action-${crypto.randomUUID()}`,
    })).data,
    onSuccess: () => invalidate(),
  });
}

export function useStepMutations(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateRecorder(projectId, sessionId);

  const activate = useMutation({
    mutationFn: async (stepKey: string) =>
      (await recorderApi.activateStep(sessionId as number, stepKey)).data,
    onSuccess: () => invalidate("steps"),
  });
  const setStatus = useMutation({
    mutationFn: async (vars: { stepKey: string; status: string; reason?: string | null }) =>
      (await recorderApi.setStepStatus(sessionId as number, vars.stepKey, {
        status: vars.status,
        reason: vars.reason,
      })).data,
    onSuccess: () => invalidate("steps"),
  });
  const addSubstep = useMutation({
    mutationFn: async (vars: { parent_step_key: string; label: string }) =>
      (await recorderApi.addDiscoveredSubstep(sessionId as number, vars)).data,
    onSuccess: () => invalidate("steps"),
  });

  return { activate, setStatus, addSubstep };
}

export function useMappingMutations(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateRecorder(projectId, sessionId);

  const map = useMutation({
    mutationFn: async (vars: { actionId: number; stepKey: string | null }) =>
      (await recorderApi.mapAction(sessionId as number, vars.actionId, vars.stepKey)).data,
    onSuccess: () => invalidate(),
  });
  const update = useMutation({
    mutationFn: async (vars: {
      actionId: number; lifecycle_phase?: string | null; excluded_from_ir?: boolean;
      exclusion_reason?: string | null; review_state?: string;
    }) => {
      const { actionId, ...payload } = vars;
      return (await recorderApi.updateMapping(sessionId as number, actionId, payload)).data;
    },
    onSuccess: () => invalidate(),
  });

  return { map, update };
}

export function useCheckpointMutations(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateRecorder(projectId, sessionId);

  const create = useMutation({
    mutationFn: async (payload: {
      checkpoint_type: string; step_key?: string | null; action_id?: number | null;
      target?: string | null; expected_value?: string | null; expected_result_ref?: string | null;
    }) => (await recorderApi.createCheckpoint(sessionId as number, payload)).data,
    onSuccess: () => invalidate(),
  });
  const review = useMutation({
    mutationFn: async (vars: { checkpointId: number; review_state: string; expected_value?: string | null }) =>
      (await recorderApi.reviewCheckpoint(sessionId as number, vars.checkpointId, {
        review_state: vars.review_state,
        expected_value: vars.expected_value,
      })).data,
    onSuccess: () => invalidate(),
  });
  const remove = useMutation({
    mutationFn: async (checkpointId: number) =>
      (await recorderApi.deleteCheckpoint(sessionId as number, checkpointId)).data,
    onSuccess: () => invalidate(),
  });

  return { create, review, remove };
}

export function useBindingMutations(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateRecorder(projectId, sessionId);

  const upsert = useMutation({
    mutationFn: async (payload: {
      name: string; classification: string; action_id?: number | null; test_data_id?: number | null;
      secret_reference?: string | null; source_action_id?: number | null;
      environment_key?: string | null; sample_value?: string | null;
    }) => (await recorderApi.upsertDataBinding(sessionId as number, payload)).data,
    onSuccess: () => invalidate(),
  });
  const remove = useMutation({
    mutationFn: async (bindingId: number) =>
      (await recorderApi.deleteDataBinding(sessionId as number, bindingId)).data,
    onSuccess: () => invalidate(),
  });

  return { upsert, remove };
}

export function useNoteMutations(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateRecorder(projectId, sessionId);

  const create = useMutation({
    mutationFn: async (payload: {
      body: string; scope?: string; step_key?: string | null; action_id?: number | null;
    }) => (await recorderApi.createNote(sessionId as number, payload)).data,
    onSuccess: () => invalidate(),
  });
  const remove = useMutation({
    mutationFn: async (noteId: number) => (await recorderApi.deleteNote(sessionId as number, noteId)).data,
    onSuccess: () => invalidate(),
  });

  return { create, remove };
}

export function useFinalizeRecording(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateRecorder(projectId, sessionId);
  return useMutation({
    mutationFn: async () => (await recorderApi.finalize(sessionId as number)).data,
    onSuccess: () => invalidate(),
  });
}

export function useEmitIrDraft(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateRecorder(projectId, sessionId);
  return useMutation({
    mutationFn: async () => (await recorderApi.emitIrDraft(sessionId as number)).data,
    onSuccess: () => invalidate(),
  });
}

export function useDiscardRecording(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateRecorder(projectId, sessionId);
  return useMutation({
    mutationFn: async (reason: string) => (await recorderApi.discard(sessionId as number, reason)).data,
    onSuccess: () => invalidate(),
  });
}

export function useCreateRecordingVersion(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateRecorder(projectId, sessionId);
  return useMutation({
    mutationFn: async (reason: string) => (await recorderApi.newVersion(sessionId as number, reason)).data,
    onSuccess: () => invalidate(),
  });
}
