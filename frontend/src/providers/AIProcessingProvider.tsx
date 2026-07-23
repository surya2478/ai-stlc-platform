"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AIProcessingModal } from "@/components/ai/AIProcessingModal";
import {
  INITIAL_AI_PROCESSING_CONTEXT,
  type AIActionMetadata,
  type AIProcessingContext,
  type RunAIActionOptions,
} from "@/types/ai-processing";

type AIProcessingApi = {
  context: AIProcessingContext;
  isProcessing: boolean;
  runAIAction: <T>(options: RunAIActionOptions<T>) => Promise<T>;
  updateAIProcessing: (metadata: AIActionMetadata) => void;
  closeAIProcessing: () => void;
};

const AIProcessingReactContext = createContext<AIProcessingApi | null>(null);
const ACTIVE_STATUSES = new Set(["queued", "processing", "waiting"]);

function safeError(error: unknown): AIActionMetadata {
  const candidate = error as {
    code?: string;
    message?: string;
    response?: { status?: number; data?: { detail?: unknown; error_code?: string; blocked_reason?: string; retryable?: boolean } };
  };
  const status = candidate.response?.status;
  const detail = candidate.response?.data?.detail;
  const detailText =
    typeof detail === "string"
      ? detail
      : detail && typeof detail === "object" && "message" in detail
        ? String((detail as { message?: unknown }).message || "")
        : candidate.message || "The AI operation could not be completed.";
  const lower = detailText.toLowerCase();
  const blocked =
    status === 403 ||
    status === 409 ||
    Boolean(candidate.response?.data?.blocked_reason) ||
    ["permission", "required", "blocked", "not ready", "unavailable", "policy"].some((value) => lower.includes(value));
  const timedOut = candidate.code === "ECONNABORTED" || lower.includes("timed out") || lower.includes("timeout");

  if (timedOut) {
    return { status: "timeout", errorCategory: "Request timed out", errorMessage: detailText };
  }
  if (blocked) {
    return {
      status: "blocked",
      errorCategory: status === 403 ? "Permission denied" : "Readiness or policy blocker",
      blockerReason: candidate.response?.data?.blocked_reason || detailText,
    };
  }
  const safeCategory =
    ["connection", "network", "dns", "enotfound", "econn"].some((value) => lower.includes(value))
      ? "Connection issue"
      : ["invalid response", "could not parse", "parse error", "malformed"].some((value) => lower.includes(value))
        ? "Invalid AI response"
        : ["file processing", "file upload", "unsupported file"].some((value) => lower.includes(value))
          ? "File processing failed"
          : lower.includes("unsupported")
            ? "Unsupported input"
            : candidate.response?.data?.error_code ||
              (status && status >= 500 ? "AI service unavailable" : status === 422 ? "Output validation failed" : "AI processing failed");
  return {
    status: "error",
    errorCategory: safeCategory,
    errorMessage: detailText,
  };
}

function resultMetadata(result: unknown): AIActionMetadata {
  const response = result as { data?: Record<string, unknown> };
  const data = response?.data && typeof response.data === "object" ? response.data : {};
  const stringValue = (key: string) => {
    const value = data[key];
    return typeof value === "string" || typeof value === "number" ? String(value) : undefined;
  };
  return {
    requestId: stringValue("request_id"),
    jobId: stringValue("job_id") || stringValue("task_id"),
    agentRunId: stringValue("agent_run_id"),
    correlationId: stringValue("correlation_id"),
  };
}

export function AIProcessingProvider({ children }: { children: React.ReactNode }) {
  const [context, setContext] = useState<AIProcessingContext>(INITIAL_AI_PROCESSING_CONTEXT);
  const activePromiseRef = useRef<Promise<unknown> | null>(null);
  const retryRef = useRef<RunAIActionOptions<unknown> | null>(null);
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timeoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimers = useCallback(() => {
    if (successTimerRef.current) clearTimeout(successTimerRef.current);
    if (timeoutTimerRef.current) clearTimeout(timeoutTimerRef.current);
    successTimerRef.current = null;
    timeoutTimerRef.current = null;
  }, []);

  useEffect(() => {
    if (!context.isOpen || !ACTIVE_STATUSES.has(context.status) || !context.startedAt) return;
    const startedAt = new Date(context.startedAt).getTime();
    const timer = setInterval(() => {
      setContext((current) => ({
        ...current,
        elapsedTimeSeconds: Math.max(0, Math.floor((Date.now() - startedAt) / 1000)),
      }));
    }, 1000);
    return () => clearInterval(timer);
  }, [context.isOpen, context.startedAt, context.status]);

  useEffect(() => () => clearTimers(), [clearTimers]);

  const closeAIProcessing = useCallback(() => {
    if (ACTIVE_STATUSES.has(context.status)) return;
    clearTimers();
    setContext(INITIAL_AI_PROCESSING_CONTEXT);
  }, [clearTimers, context.status]);

  const updateAIProcessing = useCallback((metadata: AIActionMetadata) => {
    setContext((current) => ({ ...current, ...metadata }));
  }, []);

  const runAIAction = useCallback(async <T,>(options: RunAIActionOptions<T>): Promise<T> => {
    if (activePromiseRef.current) return activePromiseRef.current as Promise<T>;
    clearTimers();
    retryRef.current = options as RunAIActionOptions<unknown>;
    const startedAt = new Date().toISOString();
    setContext({
      ...INITIAL_AI_PROCESSING_CONTEXT,
      isOpen: true,
      status: "processing",
      actionName: options.actionName,
      title: options.title,
      actionLabel: options.actionLabel,
      module: options.module,
      artifactType: options.artifactType,
      stages: options.stages,
      currentStage: options.initialStage,
      startedAt,
      projectId: options.projectId,
      requirementId: options.requirementId,
      testCaseId: options.testCaseId,
      applicationId: options.applicationId,
      environmentId: options.environmentId,
      canRetry: options.canRetry !== false,
    });

    if (options.timeoutMs) {
      timeoutTimerRef.current = setTimeout(() => {
        setContext((current) => ACTIVE_STATUSES.has(current.status) ? {
          ...current,
          status: "timeout",
          errorCategory: "Request timed out",
          errorMessage: "The request is still unresolved. The backend operation was not cancelled.",
        } : current);
      }, options.timeoutMs);
    }

    const promise = (async () => {
      try {
        const result = await options.execute();
        const metadata = {
          ...resultMetadata(result),
          ...(options.getResultMetadata?.(result) || {}),
        };
        const successMessage =
          typeof options.successMessage === "function"
            ? options.successMessage(result)
            : options.successMessage;
        setContext((current) => ({
          ...current,
          ...metadata,
          status: "success",
          successMessage: successMessage || metadata.successMessage,
        }));
        successTimerRef.current = setTimeout(() => {
          setContext(INITIAL_AI_PROCESSING_CONTEXT);
        }, 1800);
        return result;
      } catch (error) {
        setContext((current) => ({ ...current, ...safeError(error), canRetry: options.canRetry !== false }));
        throw error;
      } finally {
        if (timeoutTimerRef.current) clearTimeout(timeoutTimerRef.current);
        timeoutTimerRef.current = null;
        activePromiseRef.current = null;
      }
    })();
    activePromiseRef.current = promise;
    return promise;
  }, [clearTimers]);

  const retry = useCallback(() => {
    const retryOptions = retryRef.current;
    if (!retryOptions || activePromiseRef.current) return;
    setContext(INITIAL_AI_PROCESSING_CONTEXT);
    void runAIAction(retryOptions).catch(() => undefined);
  }, [runAIAction]);

  const value: AIProcessingApi = {
    context,
    isProcessing: Boolean(activePromiseRef.current) || ACTIVE_STATUSES.has(context.status),
    runAIAction,
    updateAIProcessing,
    closeAIProcessing,
  };

  return (
    <AIProcessingReactContext.Provider value={value}>
      {children}
      <AIProcessingModal context={context} onClose={closeAIProcessing} onRetry={retry} />
    </AIProcessingReactContext.Provider>
  );
}

export function useAIProcessingContext() {
  const value = useContext(AIProcessingReactContext);
  if (!value) throw new Error("useAIProcessingContext must be used within AIProcessingProvider");
  return value;
}
