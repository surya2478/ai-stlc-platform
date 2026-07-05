"use client";

import { Camera, Film, Loader2, Route, ScrollText, Sparkles, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { automationApi, type ExecutionResult, type ExecutionRun } from "@/lib/api";

export interface ArtifactLink {
  kind: "log" | "screenshot" | "video" | "trace";
  label: string;
  icon: LucideIcon;
  href: string;
}

/**
 * Local-runner artifacts (`*_path`) are served through the runner artifact
 * endpoint; external-tool results only carry absolute `*_url` links — use
 * those directly so the download doesn't 404 against the local runner.
 * Shared by RunDetailDrawer's result rows and the Command Center's failure panel.
 */
export function buildArtifactLinks(result: ExecutionResult): ArtifactLink[] {
  const links: ArtifactLink[] = [];
  if (result.logs?.length) {
    links.push({ kind: "log", label: "Log", icon: ScrollText, href: automationApi.runnerArtifactUrl(result.id, "log") });
  } else if (result.log_url) {
    links.push({ kind: "log", label: "Log", icon: ScrollText, href: result.log_url });
  }
  if (result.screenshot_path) {
    links.push({ kind: "screenshot", label: "Screenshot", icon: Camera, href: automationApi.runnerArtifactUrl(result.id, "screenshot") });
  } else if (result.screenshot_url) {
    links.push({ kind: "screenshot", label: "Screenshot", icon: Camera, href: result.screenshot_url });
  }
  if (result.video_path) {
    links.push({ kind: "video", label: "Video", icon: Film, href: automationApi.runnerArtifactUrl(result.id, "video") });
  } else if (result.video_url) {
    links.push({ kind: "video", label: "Video", icon: Film, href: result.video_url });
  }
  if (result.trace_path) {
    links.push({ kind: "trace", label: "Trace", icon: Route, href: automationApi.runnerArtifactUrl(result.id, "trace") });
  }
  return links;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return "—"; }
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "—";
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export type RunVerdict =
  | "in_progress" | "passed" | "failed" | "blocked" | "review_required" | "cancelled" | "skipped";

// The runner reports status="completed" once it finishes executing, even when
// some tests inside the run failed — "completed" is a lifecycle signal, not a
// pass/fail verdict (see local_playwright.py / local_pytest.py: run_status is
// "completed" for both exit code 0 and exit code 1). So for terminal states we
// derive the visible verdict from the actual passed/failed counts instead of
// trusting the raw status string.
export function runVerdict(run: Pick<ExecutionRun, "status" | "passed" | "failed">): RunVerdict {
  const s = (run.status ?? "").toLowerCase();
  if (["running", "in_progress", "queued", "pending"].includes(s)) return "in_progress";
  if (s === "blocked") return "blocked";
  if (s === "review_required") return "review_required";
  if (s === "cancelled") return "cancelled";
  if (["failed", "error"].includes(s)) return "failed";
  if ((run.failed ?? 0) > 0) return "failed";
  if ((run.passed ?? 0) > 0) return "passed";
  return "skipped";
}

const VERDICT_BADGE: Record<RunVerdict, { cls: string; label: string }> = {
  in_progress:     { cls: "bg-amber-100 text-amber-700", label: "In Progress" },
  blocked:         { cls: "bg-orange-100 text-orange-700", label: "Blocked" },
  review_required: { cls: "bg-violet-100 text-violet-700", label: "Review" },
  cancelled:       { cls: "bg-slate-100 text-slate-600", label: "Cancelled" },
  failed:          { cls: "bg-red-100 text-red-700", label: "Failed" },
  passed:          { cls: "bg-emerald-100 text-emerald-700", label: "Passed" },
  skipped:         { cls: "bg-slate-100 text-slate-600", label: "Skipped" },
};

export function RunVerdictBadge({ run }: { run: Pick<ExecutionRun, "status" | "passed" | "failed"> }) {
  const b = VERDICT_BADGE[runVerdict(run)];
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold", b.cls)}>
      {b.label}
    </span>
  );
}

export function isAiAssistedRun(run: ExecutionRun): boolean {
  const meta = (run.metadata_ as { ai_assisted?: boolean } | undefined) ?? {};
  return meta.ai_assisted === true || run.source_type === "ai" || run.execution_type === "ai";
}

export function AiAssistedBadge({ run }: { run: ExecutionRun }) {
  if (!isAiAssistedRun(run)) return null;
  return (
    <span className="inline-flex items-center gap-0.5 rounded-md bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700">
      <Sparkles className="h-2.5 w-2.5" /> AI
    </span>
  );
}

export function RunsTable({
  runs,
  loading,
  emptyMessage,
  onRowClick,
  rowAction,
}: {
  runs: ExecutionRun[];
  loading: boolean;
  emptyMessage: string;
  /** Row click handler — typically opens the RunDetailDrawer. */
  onRowClick?: (run: ExecutionRun) => void;
  /** Optional per-row trailing action cell (e.g. Review button). */
  rowAction?: (run: ExecutionRun) => React.ReactNode;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-xs text-slate-400">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading runs…
      </div>
    );
  }
  if (runs.length === 0) {
    return (
      <p className="rounded border border-dashed border-slate-200 px-3 py-6 text-center text-[11px] text-slate-400">
        {emptyMessage}
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400 border-b border-slate-100">
            <th className="py-2 pr-3">Run ID</th>
            <th className="py-2 pr-3">Suite</th>
            <th className="py-2 pr-3">Mode</th>
            <th className="py-2 pr-3">Environment</th>
            <th className="py-2 pr-3">Status</th>
            <th className="py-2 pr-3 text-right">Pass / Fail</th>
            <th className="py-2 pr-3">Started</th>
            <th className="py-2 pr-3 text-right">Duration</th>
            {rowAction && <th className="py-2 pr-3 text-right">Actions</th>}
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr
              key={r.id}
              className={cn(
                "border-b border-slate-50 hover:bg-slate-50/40",
                onRowClick && "cursor-pointer",
              )}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
            >
              <td className="py-2 pr-3 font-mono text-[#1b59f8] whitespace-nowrap">{r.execution_id}</td>
              <td className="py-2 pr-3 truncate max-w-[220px] text-slate-700">{r.suite_name ?? "—"}</td>
              <td className="py-2 pr-3"><AiAssistedBadge run={r} /></td>
              <td className="py-2 pr-3 text-slate-500">{r.environment ?? "—"}</td>
              <td className="py-2 pr-3"><RunVerdictBadge run={r} /></td>
              <td className="py-2 pr-3 text-right tabular-nums">
                <span className="text-emerald-600">{r.passed}</span>
                <span className="text-slate-300 mx-1">/</span>
                <span className="text-red-600">{r.failed}</span>
              </td>
              <td className="py-2 pr-3 text-slate-500 whitespace-nowrap">{formatDate(r.started_at ?? r.created_at)}</td>
              <td className="py-2 pr-3 text-right tabular-nums text-slate-500 font-mono">{formatDuration(r.duration_seconds)}</td>
              {rowAction && (
                <td className="py-2 pr-3 text-right" onClick={(e) => e.stopPropagation()}>
                  {rowAction(r)}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
