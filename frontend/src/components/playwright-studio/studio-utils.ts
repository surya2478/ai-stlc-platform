import type { StudioRun } from "@/lib/api";

export type StudioStepIndex = 1 | 2 | 3 | 4 | 5;

export const STUDIO_STEPS: Array<{ index: StudioStepIndex; title: string; subtitle: string }> = [
  { index: 1, title: "Planner Input", subtitle: "Define exploration context" },
  { index: 2, title: "Test Plan Review", subtitle: "Review AI generated plan" },
  { index: 3, title: "Generated Tests", subtitle: "Review generated scripts" },
  { index: 4, title: "Execution & Healing", subtitle: "Run tests and heal failures" },
  { index: 5, title: "Artifacts & Audit", subtitle: "Reports, traces & audit trail" },
];

const STATUS_TO_STEP: Record<string, StudioStepIndex> = {
  draft: 1,
  exploring: 2,
  plan_ready: 2,
  generating: 3,
  scripts_ready: 3,
  executing: 4,
  healing: 4,
  completed: 5,
};

export function stepForStatus(status: string | undefined): StudioStepIndex {
  return STATUS_TO_STEP[status ?? "draft"] ?? 1;
}

export function studioStatusVariant(
  status: string | undefined,
): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  switch (status) {
    case "completed":
      return "success";
    case "failed":
      return "destructive";
    case "cancelled":
      return "secondary";
    case "exploring":
    case "generating":
    case "executing":
    case "healing":
      return "warning";
    case "plan_ready":
    case "scripts_ready":
      return "info";
    default:
      return "outline";
  }
}

export function studioStatusLabel(status: string | undefined): string {
  switch (status) {
    case "draft": return "Draft";
    case "exploring": return "Exploring application";
    case "plan_ready": return "Plan ready for review";
    case "generating": return "Generating scripts";
    case "scripts_ready": return "Scripts ready for approval";
    case "executing": return "Executing";
    case "healing": return "Healing failures";
    case "completed": return "Completed";
    case "failed": return "Failed";
    case "cancelled": return "Cancelled";
    default: return status ?? "—";
  }
}

export function isTerminalStudioStatus(status: string | undefined): boolean {
  return status === "completed" || status === "failed" || status === "cancelled";
}

export function runEnvironmentLabel(run: StudioRun): string {
  return run.config?.environment ?? "—";
}

/** "executor" runs the same containers as "docker", but through the isolated
 *  runner-executor service — the only process in the deployment that holds the
 *  Docker socket. The Studio screens used to test `=== "docker"` and call
 *  everything else "local", so an executor run was labelled as a local
 *  subprocess run it has nothing in common with. */
export function runnerIsContainerised(mode: string | undefined): boolean {
  return mode === "docker" || mode === "executor";
}

export function runnerModeLabel(mode: string | undefined): string {
  switch (mode) {
    case "executor": return "Executor";
    case "docker": return "Docker";
    case "local": return "Local subprocess";
    default: return "Server default";
  }
}
