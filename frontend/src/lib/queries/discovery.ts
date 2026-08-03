"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  discoveryApi,
  isActiveDiscoverySession,
  type DiscoverySession,
} from "@/lib/api";

export const discoveryKeys = {
  eligibleTestCases: (projectId: number, applicationId: number, mode: string) =>
    ["discovery", "eligible-test-cases", projectId, applicationId, mode] as const,
  // Keyed by application too: the request is scoped by application_id, so a
  // key that ignored it served another application's sessions from cache
  // when the picker changed.
  sessions: (projectId: number, applicationId?: number | null) =>
    ["discovery", "sessions", projectId, applicationId ?? "all"] as const,
  session: (sessionId: number) => ["discovery", "session", sessionId] as const,
  readiness: (sessionId: number) => ["discovery", "readiness", sessionId] as const,
  actions: (sessionId: number) => ["discovery", "actions", sessionId] as const,
  checkpoints: (sessionId: number) => ["discovery", "checkpoints", sessionId] as const,
  activity: (sessionId: number) => ["discovery", "activity", sessionId] as const,
};

export function useEligibleTestCases(projectId: number | null, applicationId: number | null, mode: string) {
  return useQuery({
    queryKey: discoveryKeys.eligibleTestCases(projectId ?? -1, applicationId ?? -1, mode),
    queryFn: async () => (await discoveryApi.eligibleTestCases(projectId as number, applicationId as number, mode)).data,
    enabled: Boolean(projectId && applicationId),
  });
}

export function useDiscoverySessions(projectId: number | null, applicationId?: number | null) {
  return useQuery({
    queryKey: discoveryKeys.sessions(projectId ?? -1, applicationId),
    queryFn: async () =>
      (await discoveryApi.listSessions(projectId as number, applicationId ? { application_id: applicationId } : undefined)).data,
    enabled: projectId !== null && projectId > 0,
    refetchInterval: (query) => (query.state.data?.some(isActiveDiscoverySession) ? 5000 : false),
  });
}

export function useDiscoverySession(sessionId: number | null) {
  return useQuery({
    queryKey: discoveryKeys.session(sessionId ?? -1),
    queryFn: async () => (await discoveryApi.getSession(sessionId as number)).data,
    enabled: sessionId !== null && sessionId > 0,
    refetchInterval: (query) => (isActiveDiscoverySession(query.state.data) ? 3000 : false),
  });
}

export function useDiscoveryReadiness(sessionId: number | null) {
  return useQuery({
    queryKey: discoveryKeys.readiness(sessionId ?? -1),
    queryFn: async () => (await discoveryApi.evaluateReadiness(sessionId as number)).data,
    enabled: sessionId !== null && sessionId > 0,
    refetchInterval: 10_000,
  });
}

export function useCurrentStep(sessionId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ["discovery", "current-step", sessionId ?? -1],
    queryFn: async () => (await discoveryApi.getCurrentStep(sessionId as number)).data,
    enabled: enabled && sessionId !== null && sessionId > 0,
    refetchInterval: 4000,
  });
}

export function useDiscoveryActions(sessionId: number | null) {
  return useQuery({
    queryKey: discoveryKeys.actions(sessionId ?? -1),
    queryFn: async () => (await discoveryApi.listActions(sessionId as number)).data,
    enabled: sessionId !== null && sessionId > 0,
    refetchInterval: 4000,
  });
}

export function useDiscoveryCheckpoints(sessionId: number | null) {
  return useQuery({
    queryKey: discoveryKeys.checkpoints(sessionId ?? -1),
    queryFn: async () => (await discoveryApi.listCheckpoints(sessionId as number)).data,
    enabled: sessionId !== null && sessionId > 0,
  });
}

export function useDiscoveryActivity(sessionId: number | null) {
  return useQuery({
    queryKey: discoveryKeys.activity(sessionId ?? -1),
    queryFn: async () => (await discoveryApi.getActivity(sessionId as number)).data,
    enabled: sessionId !== null && sessionId > 0,
    refetchInterval: 6000,
  });
}

export function useDiscoveryCaptures(sessionId: number | null, actionId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ["discovery", "captures", sessionId ?? -1, actionId ?? -1] as const,
    queryFn: async () => (await discoveryApi.listCaptures(sessionId as number, actionId as number)).data,
    enabled: enabled && sessionId !== null && sessionId > 0 && actionId !== null,
  });
}

export function useCaptureContent(sessionId: number | null, captureId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ["discovery", "capture-content", sessionId ?? -1, captureId ?? -1] as const,
    queryFn: async () => (await discoveryApi.getCaptureContent(sessionId as number, captureId as number)).data,
    enabled: enabled && sessionId !== null && sessionId > 0 && captureId !== null,
  });
}

function useInvalidateDiscovery(projectId: number | null) {
  const queryClient = useQueryClient();
  return (sessionId?: number) => {
    // Prefix match, so every application scope of this project's session list
    // is refreshed regardless of which one is on screen.
    if (projectId) queryClient.invalidateQueries({ queryKey: ["discovery", "sessions", projectId] });
    if (sessionId) {
      queryClient.invalidateQueries({ queryKey: discoveryKeys.session(sessionId) });
      queryClient.invalidateQueries({ queryKey: discoveryKeys.readiness(sessionId) });
      queryClient.invalidateQueries({ queryKey: discoveryKeys.actions(sessionId) });
      queryClient.invalidateQueries({ queryKey: discoveryKeys.checkpoints(sessionId) });
      queryClient.invalidateQueries({ queryKey: discoveryKeys.activity(sessionId) });
    }
  };
}

export function useCreateDiscoverySession(projectId: number | null) {
  const invalidate = useInvalidateDiscovery(projectId);
  return useMutation({
    mutationFn: async (payload: Parameters<typeof discoveryApi.createSession>[1]) =>
      (await discoveryApi.createSession(projectId as number, payload)).data,
    onSuccess: (session: DiscoverySession) => invalidate(session.id),
  });
}

export function useIssueDiscoveryCommand(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateDiscovery(projectId);
  return useMutation({
    mutationFn: async (payload: { command: string; reason?: string; params?: Record<string, unknown> }) =>
      (await discoveryApi.issueCommand(sessionId as number, {
        ...payload,
        idempotency_key: `${sessionId}-${payload.command}-${crypto.randomUUID()}`,
      })).data,
    onSuccess: () => invalidate(sessionId ?? undefined),
  });
}

export function useCorrectDiscoveryAction(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateDiscovery(projectId);
  return useMutation({
    mutationFn: async (vars: {
      actionId: number; inclusion_state: string; reviewer_note?: string; reason?: string; mapped_test_step_ref?: string;
    }) => (await discoveryApi.correctAction(sessionId as number, vars.actionId, vars)).data,
    onSuccess: () => invalidate(sessionId ?? undefined),
  });
}

export function useRecordFreeAction(projectId: number | null, sessionId: number | null) {
  const invalidate = useInvalidateDiscovery(projectId);
  return useMutation({
    mutationFn: async (payload: {
      action_family: string; target_ref?: string; target_semantic?: string; input_text?: string; url?: string;
    }) => (await discoveryApi.recordAction(sessionId as number, {
      ...payload,
      idempotency_key: `${sessionId}-action-${crypto.randomUUID()}`,
    })).data,
    onSuccess: () => invalidate(sessionId ?? undefined),
  });
}
