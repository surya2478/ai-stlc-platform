"use client";

import { ReactNode, useMemo, useState } from "react";
import {
  Bug,
  Camera,
  ChevronDown,
  ChevronRight,
  Clock,
  Download,
  FileText,
  Film,
  Loader2,
  Network,
  Route,
  ScrollText,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  automationApi,
  type ExecutionResult,
  type ExecutionRun,
} from "@/lib/api";
import { useRun, useRunResults } from "@/lib/queries/execution";
import {
  Drawer,
  DrawerBody,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import { Badge } from "@/components/ui/badge";
import {
  EmptyState,
  ExecutionStatusBadge,
  ExecutionTypeBadge,
  LoadingSkeleton,
} from "./execution-shared";
import { TraceabilityDrawer, type TraceTarget } from "./TraceabilityDrawer";

function formatDuration(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

function formatTimestamp(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

function logLine(entry: unknown): string {
  if (typeof entry === "string") return entry;
  if (entry && typeof entry === "object") {
    const obj = entry as Record<string, unknown>;
    const level = typeof obj.level === "string" ? `[${obj.level.toUpperCase()}] ` : "";
    const message = typeof obj.message === "string" ? obj.message : JSON.stringify(entry);
    return `${level}${message}`;
  }
  return String(entry);
}

/* ------------------------------------------------------------------ */
/* Per-result row with error/artifact expander                         */
/* ------------------------------------------------------------------ */

function ResultRow({
  result,
  onCreateDefect,
}: {
  result: ExecutionResult;
  onCreateDefect?: (result: ExecutionResult) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  // Local-runner artifacts (`*_path`) are served through the runner artifact
  // endpoint; external-tool results only carry absolute `*_url` links — use
  // those directly so the download doesn't 404 against the local runner.
  const artifacts: Array<{ kind: string; label: string; icon: typeof FileText; href: string }> = [];
  if (result.logs?.length) {
    artifacts.push({ kind: "log", label: "Log", icon: ScrollText, href: automationApi.runnerArtifactUrl(result.id, "log") });
  } else if (result.log_url) {
    artifacts.push({ kind: "log", label: "Log", icon: ScrollText, href: result.log_url });
  }
  if (result.screenshot_path) {
    artifacts.push({ kind: "screenshot", label: "Screenshot", icon: Camera, href: automationApi.runnerArtifactUrl(result.id, "screenshot") });
  } else if (result.screenshot_url) {
    artifacts.push({ kind: "screenshot", label: "Screenshot", icon: Camera, href: result.screenshot_url });
  }
  if (result.video_path) {
    artifacts.push({ kind: "video", label: "Video", icon: Film, href: automationApi.runnerArtifactUrl(result.id, "video") });
  } else if (result.video_url) {
    artifacts.push({ kind: "video", label: "Video", icon: Film, href: result.video_url });
  }
  if (result.trace_path) {
    artifacts.push({ kind: "trace", label: "Trace", icon: Route, href: automationApi.runnerArtifactUrl(result.id, "trace") });
  }

  const hasDetails =
    Boolean(result.error_message || result.stack_trace) || artifacts.length > 0 || Boolean(result.logs?.length);

  const screenshotSrc = result.screenshot_path
    ? automationApi.runnerArtifactUrl(result.id, "screenshot")
    : result.screenshot_url ?? null;

  return (
    <div className="rounded-lg border border-slate-200">
      <button
        type="button"
        onClick={() => hasDetails && setExpanded((v) => !v)}
        className={cn(
          "flex w-full items-center gap-3 p-3 text-left",
          hasDetails ? "cursor-pointer hover:bg-slate-50" : "cursor-default",
        )}
      >
        {hasDetails ? (
          expanded ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />
          )
        ) : (
          <span className="w-4 shrink-0" />
        )}
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">
          {result.test_name}
        </span>
        {result.duration_ms !== null && result.duration_ms !== undefined && (
          <span className="shrink-0 text-xs tabular-nums text-slate-400">
            {(result.duration_ms / 1000).toFixed(1)}s
          </span>
        )}
        <ExecutionStatusBadge status={result.status} className="shrink-0" />
      </button>

      {expanded && (
        <div className="space-y-3 border-t border-slate-100 bg-slate-50/50 p-3">
          {result.error_message && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-red-600">Error</p>
              <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-red-50 p-2 font-mono text-xs text-red-800">
                {result.error_message}
              </pre>
            </div>
          )}
          {result.stack_trace && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Stack trace</p>
              <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-slate-900 p-2 font-mono text-[11px] leading-relaxed text-slate-100">
                {result.stack_trace}
              </pre>
            </div>
          )}
          {result.logs && result.logs.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Test log</p>
              <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-slate-900 p-2 font-mono text-[11px] leading-relaxed text-slate-100">
                {result.logs.map(logLine).join("\n")}
              </pre>
            </div>
          )}
          {screenshotSrc && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Screenshot</p>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={screenshotSrc}
                alt={`Screenshot for ${result.test_name}`}
                className="mt-1 max-h-64 rounded-md border border-slate-200 object-contain"
                loading="lazy"
              />
            </div>
          )}
          {(artifacts.length > 0 || onCreateDefect) && (
            <div className="flex flex-wrap items-center gap-2">
              {artifacts.map(({ kind, label, icon: Icon, href }) => (
                <a
                  key={kind}
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
                >
                  <Icon className="h-3.5 w-3.5 text-slate-400" />
                  {label}
                  <Download className="h-3 w-3 text-slate-400" />
                </a>
              ))}
              {onCreateDefect && ["fail", "failed", "error", "blocked"].includes(String(result.status).toLowerCase()) && (
                <button
                  type="button"
                  onClick={() => onCreateDefect(result)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-red-50 px-2.5 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100"
                >
                  <Bug className="h-3.5 w-3.5" /> Draft defect
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Drawer                                                              */
/* ------------------------------------------------------------------ */

export function RunDetailDrawer({
  runId,
  open,
  onOpenChange,
  initialRun,
  headerActions,
  footer,
  onCreateDefect,
}: {
  runId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Optional already-loaded run to render immediately while detail refetches. */
  initialRun?: ExecutionRun | null;
  /** Extra actions rendered next to the title (e.g. Trace button). */
  headerActions?: ReactNode;
  /** Optional footer content (e.g. AI review controls). */
  footer?: ReactNode;
  /** When set, failed/blocked results show a "Draft defect" action. */
  onCreateDefect?: (result: ExecutionResult) => void;
}) {
  const runQuery = useRun(open ? runId : null);
  const run = runQuery.data ?? initialRun ?? null;
  const resultsQuery = useRunResults(open ? runId : null);
  const results = resultsQuery.data ?? [];
  const [traceTarget, setTraceTarget] = useState<TraceTarget | null>(null);

  const executionLogs = useMemo(() => {
    const logs = run?.execution_logs;
    return Array.isArray(logs) ? logs.map(logLine) : [];
  }, [run?.execution_logs]);

  const aiAssisted = Boolean(run?.metadata_?.ai_assisted);

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent size="xl">
        <DrawerHeader>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <DrawerTitle className="font-mono">{run?.execution_id ?? `Run #${runId ?? ""}`}</DrawerTitle>
              {run && <ExecutionStatusBadge status={run.status} />}
              {run?.execution_type && <ExecutionTypeBadge type={run.execution_type} />}
              {aiAssisted && <Badge variant="purple">AI-Assisted</Badge>}
              {runId !== null && (
                <button
                  type="button"
                  onClick={() =>
                    setTraceTarget({
                      entityType: "execution_run",
                      entityId: runId,
                      label: run?.execution_id ?? `Run #${runId}`,
                    })
                  }
                  className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-0.5 text-[10px] font-semibold text-slate-600 hover:bg-slate-50"
                  title="Show the Requirement → Test Case → Script → Run chain"
                >
                  <Network className="h-3 w-3" /> Trace
                </button>
              )}
              {headerActions}
            </div>
            <DrawerDescription>
              {run?.suite_name ?? "Execution run detail"}
            </DrawerDescription>
          </div>
          <DrawerClose className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
            <span className="sr-only">Close</span>✕
          </DrawerClose>
        </DrawerHeader>

        <DrawerBody>
          {!run && runQuery.isLoading && <LoadingSkeleton rows={6} />}

          {run && (
            <>
              {/* Summary grid */}
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <SummaryItem label="Environment" value={run.environment ?? "—"} />
                <SummaryItem label="Duration" value={formatDuration(run.duration_seconds)} />
                <SummaryItem label="Started" value={formatTimestamp(run.started_at)} />
                <SummaryItem label="Completed" value={formatTimestamp(run.completed_at)} />
              </div>

              {/* Pass/fail strip */}
              <div className="flex items-center gap-4 rounded-lg border border-slate-200 bg-slate-50/50 px-4 py-3 text-sm">
                <span className="font-semibold text-slate-700">{run.total_tests} tests</span>
                <span className="text-emerald-600">✓ {run.passed} passed</span>
                <span className="text-red-600">✕ {run.failed} failed</span>
                <span className="text-slate-500">↷ {run.skipped} skipped</span>
                {run.confidence_score !== null && run.confidence_score !== undefined && (
                  <span className="ml-auto inline-flex items-center gap-1 text-violet-600">
                    Confidence: <span className="font-semibold tabular-nums">{Math.round(run.confidence_score)}%</span>
                  </span>
                )}
              </div>

              {/* Per-test results */}
              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Test results
                </h3>
                {resultsQuery.isLoading ? (
                  <LoadingSkeleton rows={3} />
                ) : results.length === 0 ? (
                  <EmptyState
                    icon={Clock}
                    title="No results yet"
                    description={
                      run.status === "queued" || run.status === "pending"
                        ? "The run is queued. Results appear as the worker executes tests."
                        : "This run has no per-test results recorded."
                    }
                  />
                ) : (
                  <div className="space-y-2">
                    {results.map((r) => (
                      <ResultRow key={r.id} result={r} onCreateDefect={onCreateDefect} />
                    ))}
                  </div>
                )}
              </section>

              {/* Run-level logs */}
              {executionLogs.length > 0 && (
                <section>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Execution log
                  </h3>
                  <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-900 p-3 font-mono text-[11px] leading-relaxed text-slate-100">
                    {executionLogs.join("\n")}
                  </pre>
                </section>
              )}

              {runQuery.isFetching && (
                <p className="flex items-center gap-1.5 text-[11px] text-slate-400">
                  <Loader2 className="h-3 w-3 animate-spin" /> Refreshing…
                </p>
              )}
            </>
          )}
        </DrawerBody>

        {footer}
      </DrawerContent>
      <TraceabilityDrawer target={traceTarget} onClose={() => setTraceTarget(null)} />
    </Drawer>
  );
}

function SummaryItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
      <p className="text-[11px] font-medium text-slate-400">{label}</p>
      <p className="mt-0.5 truncate text-sm font-semibold text-slate-800">{value}</p>
    </div>
  );
}
