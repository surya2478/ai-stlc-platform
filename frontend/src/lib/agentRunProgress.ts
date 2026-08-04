"use client";

import { agentRunsApi } from "@/lib/api";
import type { AIActionMetadata } from "@/types/ai-processing";

/** Statuses an agent run does not move on from. Anything else means "still
 *  going" — listing the terminal set rather than the active set means a status
 *  nobody anticipated keeps the modal open instead of silently declaring
 *  success. */
const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled", "error", "timeout"]);

const POLL_INTERVAL_MS = 2000;
/** Long enough for a real generation wave (25 scripts, each an LLM call plus a
 *  static gate and a dry run), short enough that a job whose worker died stops
 *  spinning a modal forever. */
const MAX_WAIT_MS = 15 * 60 * 1000;
/** A couple of dropped polls is a blip; a run that cannot be read repeatedly
 *  is gone, and pretending otherwise leaves the modal open indefinitely. */
const MAX_CONSECUTIVE_ERRORS = 5;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Watch a queued agent run until it finishes, reporting progress as it goes.
 *
 * Written for `runAIAction`'s `awaitCompletion`. The generate-scripts endpoint
 * returns 202 as soon as the task is enqueued, so without this the progress
 * modal reported success about two hundred milliseconds in and closed while
 * the agent was still working.
 */
export async function waitForAgentRun(
  agentRunId: number,
  update: (metadata: AIActionMetadata) => void,
): Promise<AIActionMetadata> {
  const deadline = Date.now() + MAX_WAIT_MS;
  let consecutiveErrors = 0;

  while (Date.now() < deadline) {
    await sleep(POLL_INTERVAL_MS);
    let run;
    try {
      run = (await agentRunsApi.get(agentRunId)).data;
      consecutiveErrors = 0;
    } catch {
      consecutiveErrors += 1;
      if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
        return {
          status: "error",
          errorCategory: "Lost contact with the agent run",
          errorMessage:
            `Could not read agent run ${agentRunId} after ${MAX_CONSECUTIVE_ERRORS} attempts. ` +
            "It may still be running — check the Automation inventory for new scripts.",
        };
      }
      continue;
    }

    // The run reports its own stage; showing it beats a canned stage list that
    // advances on a timer and can only ever be a guess.
    if (run.progress_message) update({ currentStage: run.progress_message });

    if (!TERMINAL_STATUSES.has(run.status)) continue;
    if (run.status === "completed") return { status: "success" };
    return {
      status: run.status === "timeout" ? "timeout" : "error",
      errorCategory: `Agent run ${run.status}`,
      errorMessage: run.error_message || `The agent run finished as '${run.status}'.`,
    };
  }

  return {
    status: "timeout",
    errorCategory: "Still running",
    errorMessage:
      `Agent run ${agentRunId} has not finished after 15 minutes. It may still complete — ` +
      "check the Automation inventory for new scripts.",
  };
}

/** The agent run id carried by a queued-agent 202 response. */
export function agentRunIdFrom(result: unknown): number | null {
  const id = (result as { data?: { agent_run_id?: unknown } })?.data?.agent_run_id;
  return typeof id === "number" ? id : null;
}
