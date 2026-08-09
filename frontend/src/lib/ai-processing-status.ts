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

/** Category shown in the AI processing modal for a failed agent run.
 *
 *  Poll sites used to hardcode "AI processing failed" for every terminal run,
 *  which told the user nothing about whether retrying could help. Truncation in
 *  particular is a capacity limit, not a transient fault: the same request hits
 *  the same cap, so it needs its own label rather than the generic one that
 *  invites a pointless Retry.
 */
export function agentRunErrorCategory(message?: string | null): string {
  const lower = (message || "").toLowerCase();
  if (lower.includes("truncated") || lower.includes("output limit")) return "AI response truncated";
  if (lower.includes("circuit is open")) return "AI service unavailable";
  if (lower.includes("not valid json") || lower.includes("schema validation") || lower.includes("pydantic")) {
    return "Invalid AI response";
  }
  if (lower.includes("timed out") || lower.includes("timeout")) return "Request timed out";
  return "AI processing failed";
}

