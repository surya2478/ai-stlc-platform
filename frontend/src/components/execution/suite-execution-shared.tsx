// UI-046 Suite Execution Command Center — shared presentation helpers.
//
// Contract Section 14.3 requires lifecycle and result to be presented
// separately, so they have separate tone maps here and are never merged into one
// badge. The eight outcomes are also deliberately not collapsed into
// pass/fail/other: an ENVIRONMENT_FAILURE reading as a generic failure is exactly
// the confusion the outcome vocabulary exists to prevent.

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type {
  ExecutionItemResult,
  ExecutionLifecycleState,
  SuiteRunItem,
} from "@/lib/api";

type BadgeVariant = React.ComponentProps<typeof Badge>["variant"];

const LIFECYCLE_TONE: Record<
  ExecutionLifecycleState,
  { label: string; variant: BadgeVariant }
> = {
  READINESS_PENDING: { label: "Checking readiness", variant: "info" },
  BLOCKED_BEFORE_START: { label: "Blocked", variant: "destructive" },
  QUEUED: { label: "Queued", variant: "secondary" },
  RUNNING: { label: "Live", variant: "success" },
  PAUSE_REQUESTED: { label: "Pausing", variant: "warning" },
  PAUSED: { label: "Paused", variant: "warning" },
  STOP_REQUESTED: { label: "Stopping", variant: "warning" },
  STOPPED: { label: "Stopped", variant: "outline" },
  CANCELLED: { label: "Cancelled", variant: "outline" },
  COMPLETED: { label: "Completed", variant: "success" },
};

export function LifecycleBadge({
  state,
  className,
}: {
  state: ExecutionLifecycleState | null;
  className?: string;
}) {
  if (!state) return null;
  const tone = LIFECYCLE_TONE[state] ?? { label: state, variant: "secondary" as const };
  return (
    <Badge variant={tone.variant} className={cn("text-[9px]", className)} title={state}>
      {tone.label}
    </Badge>
  );
}

/**
 * The eight outcomes plus PENDING and SKIPPED. `short` is for the dense matrix
 * column; `label` is the full wording used in the inspector and the status cards.
 * The raw value always stays in a title attribute so nothing is hidden behind a
 * friendlier word.
 */
export const RESULT_TONE: Record<
  ExecutionItemResult,
  { label: string; short: string; dot: string; text: string; bar: string }
> = {
  PENDING: {
    label: "Pending",
    short: "Pending",
    dot: "bg-gray-300",
    text: "text-gray-400",
    bar: "bg-gray-200",
  },
  PASS: {
    label: "Pass",
    short: "Pass",
    dot: "bg-emerald-500",
    text: "text-emerald-600",
    bar: "bg-emerald-500",
  },
  FAIL: {
    label: "Fail",
    short: "Fail",
    dot: "bg-red-500",
    text: "text-red-600",
    bar: "bg-red-500",
  },
  INCONCLUSIVE: {
    label: "Inconclusive",
    short: "Inconclusive",
    dot: "bg-amber-500",
    text: "text-amber-600",
    bar: "bg-amber-500",
  },
  BLOCKED: {
    label: "Blocked",
    short: "Blocked",
    dot: "bg-violet-500",
    text: "text-violet-600",
    bar: "bg-violet-500",
  },
  ENVIRONMENT_FAILURE: {
    label: "Environment failure",
    short: "Env",
    dot: "bg-orange-600",
    text: "text-orange-700",
    bar: "bg-orange-600",
  },
  DATA_FAILURE: {
    label: "Data failure",
    short: "Data",
    dot: "bg-cyan-600",
    text: "text-cyan-700",
    bar: "bg-cyan-600",
  },
  AUTOMATION_FAILURE: {
    label: "Automation failure",
    short: "Harness",
    dot: "bg-pink-600",
    text: "text-pink-700",
    bar: "bg-pink-600",
  },
  POLICY_BLOCKED: {
    label: "Policy blocked",
    short: "Policy",
    dot: "bg-gray-700",
    text: "text-gray-700",
    bar: "bg-gray-700",
  },
  SKIPPED: {
    label: "Skipped",
    short: "Skipped",
    dot: "bg-gray-400",
    text: "text-gray-500",
    bar: "bg-gray-400",
  },
};

export function ResultPill({
  result,
  reason,
  className,
}: {
  result: ExecutionItemResult;
  reason?: string | null;
  className?: string;
}) {
  const tone = RESULT_TONE[result] ?? RESULT_TONE.PENDING;
  return (
    <span
      className={cn("flex items-center gap-1.5 text-[10px] font-bold", tone.text, className)}
      // Section 6.2: the exact reason belongs in the tooltip, not only in the
      // inspector.
      title={reason ? `${result} — ${reason}` : result}
    >
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", tone.dot)} />
      {tone.short}
    </span>
  );
}

const ITEM_LIFECYCLE_LABEL: Record<SuiteRunItem["lifecycle_state"], string> = {
  QUEUED: "Queued",
  STARTING: "Starting",
  RUNNING: "Running",
  PAUSED: "Paused",
  COMPLETED: "Completed",
};

export function ItemLifecyclePill({ item }: { item: SuiteRunItem }) {
  const running = item.lifecycle_state === "RUNNING" || item.lifecycle_state === "STARTING";
  return (
    <span
      className={cn(
        "flex items-center gap-1.5 text-[10px] font-semibold",
        running ? "text-[#B71920]" : "text-gray-500",
      )}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 shrink-0 rounded-full",
          running
            ? // Respects reduced-motion per Section 13; the colour alone still
              // distinguishes a running row for anyone who suppresses animation.
              "bg-[#B71920] motion-safe:animate-pulse"
            : item.lifecycle_state === "COMPLETED"
              ? "bg-gray-400"
              : "bg-gray-300",
        )}
      />
      {ITEM_LIFECYCLE_LABEL[item.lifecycle_state] ?? item.lifecycle_state}
    </span>
  );
}

/** Derived from the last successful poll and the age of the newest backend
 *  event. There is no socket to report on — Section 2.1.7. */
export type ConnectionState = "LIVE" | "DELAYED" | "RECONNECTING" | "OFFLINE_SNAPSHOT";

const CONNECTION_TONE: Record<
  ConnectionState,
  { label: string; variant: BadgeVariant; title: string }
> = {
  LIVE: {
    label: "LIVE",
    variant: "success",
    title: "Polling the backend on schedule; the newest event is recent.",
  },
  DELAYED: {
    label: "DELAYED",
    variant: "warning",
    title: "Polls are succeeding but the newest backend event is stale.",
  },
  RECONNECTING: {
    label: "RECONNECTING",
    variant: "warning",
    title: "A poll failed. Showing the last known data; execution continues in the backend.",
  },
  OFFLINE_SNAPSHOT: {
    label: "OFFLINE SNAPSHOT",
    variant: "outline",
    title: "Live updates have stopped. The data shown is the last successful read.",
  },
};

export function ConnectionBadge({ state }: { state: ConnectionState }) {
  const tone = CONNECTION_TONE[state];
  return (
    <Badge variant={tone.variant} className="text-[9px]" title={tone.title}>
      {tone.label}
    </Badge>
  );
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) return `${seconds}s`;
  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

/** Elapsed time as HH:MM:SS, computed from the server's started_at. */
export function formatElapsed(startedAt: string | null, endedAt: string | null): string {
  if (!startedAt) return "—";
  const start = new Date(startedAt).getTime();
  const end = endedAt ? new Date(endedAt).getTime() : Date.now();
  const totalSeconds = Math.max(0, Math.floor((end - start) / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [hours, minutes, seconds].map((v) => String(v).padStart(2, "0")).join(":");
}

export function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

const PRIORITY_TONE: Record<string, string> = {
  "very critical": "text-red-700",
  critical: "text-red-600",
  high: "text-orange-600",
  medium: "text-gray-600",
  low: "text-gray-400",
};

export function priorityClass(priority: string | null): string {
  return PRIORITY_TONE[(priority ?? "").toLowerCase()] ?? "text-gray-500";
}

/** Human wording for the readiness axis names the backend returns. */
export const AXIS_LABEL: Record<string, string> = {
  environment: "Environment",
  application: "Application",
  data: "Test data",
  framework: "Framework",
  worker: "Worker",
};
