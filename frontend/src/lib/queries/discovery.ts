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
  sessions: (projectId: number) => ["discovery", "sessions", projectId] as const,
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
    queryKey: discoveryKeys.sessions(projectId ?? -1),
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

function useInvalidateDiscovery(projectId: number | null) {
  const queryClient = useQueryClient();
  return (sessionId?: number) => {
    if (projectId) queryClient.invalidateQueries({ queryKey: discoveryKeys.sessions(projectId) });
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
