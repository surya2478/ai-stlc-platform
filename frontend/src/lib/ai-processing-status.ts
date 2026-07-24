import type { AIProcessingStatus } from "@/types/ai-processing";

const TERMINAL_AGENT_FAILURES: Record<string, AIProcessingStatus> = {
  fail: "error",
  failed: "error",
  failure: "error",
  error: "error",
  errored: "error",
  exception: "error",
  blocked: "blocked",
  cancelled: "cancelled",
  canceled: "cancelled",
  timeout: "timeout",
  timed_out: "timeout",
};

export function terminalAIStatus(value?: string | null): AIProcessingStatus | null {
  if (!value) return null;
  return TERMINAL_AGENT_FAILURES[value.trim().toLowerCase().replace(/[\s-]+/g, "_")] ?? null;
}

