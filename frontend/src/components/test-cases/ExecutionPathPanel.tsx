"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, Check, CircleDot, HelpCircle, Loader2, RefreshCw } from "lucide-react";
import { testCasesApi, type ExecutionPath, type ExecutionPathStep } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Why this test case will not run yet, as one list.
 *
 * Reaching a governed execution crosses six modules, and every blocker used to
 * be found by being refused — almost never in the module that fixes it. The
 * suite wizard reports MODEL_NOT_APPROVED, resolved three modules away; publish
 * demands final member approval, granted in Automation Assets.
 *
 * Read-only. It changes no state and grants no permission; each row reports a
 * fact another service already owns, next to where to go and settle it.
 */

const STATE_STYLE: Record<
  ExecutionPathStep["state"],
  { icon: typeof Check; ring: string; text: string; label: string }
> = {
  DONE: { icon: Check, ring: "border-emerald-200 bg-emerald-50 text-emerald-600", text: "text-gray-700", label: "Done" },
  BLOCKED: { icon: AlertTriangle, ring: "border-amber-300 bg-amber-100 text-amber-700", text: "text-gray-900", label: "Do this next" },
  // Deliberately muted: a consequence of an earlier step is not something to
  // act on, and colouring it like a blocker is what turns a checklist into noise.
  WAITING: { icon: CircleDot, ring: "border-gray-200 bg-gray-50 text-gray-300", text: "text-gray-400", label: "Waiting" },
  UNKNOWN: { icon: HelpCircle, ring: "border-gray-300 bg-gray-100 text-gray-500", text: "text-gray-600", label: "Unknown" },
};

function Row({ step, isNext }: { step: ExecutionPathStep; isNext: boolean }) {
  const style = STATE_STYLE[step.state];
  const Icon = style.icon;
  return (
    <li className={cn("flex items-start gap-3 rounded-lg px-2 py-1.5", isNext && "bg-amber-50/70")}>
      <span className={cn("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border", style.ring)}>
        <Icon className="h-3 w-3" />
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn("block text-xs font-bold", style.text)}>{step.label}</span>
        <span className={cn("block text-[11px] font-semibold", step.state === "WAITING" ? "text-gray-400" : "text-gray-500")}>
          {step.detail}
        </span>
      </span>
      {step.fix_href && step.fix_label && (
        <Link
          href={step.fix_href}
          className="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-md border border-amber-300 bg-white px-2 py-1 text-[10px] font-bold text-amber-800 hover:bg-amber-50"
        >
          {step.fix_label}
          <ArrowRight className="h-3 w-3" />
        </Link>
      )}
    </li>
  );
}

export function ExecutionPathPanel({
  projectId,
  testCaseId,
  className,
}: {
  projectId: number;
  testCaseId: number;
  className?: string;
}) {
  const [path, setPath] = useState<ExecutionPath | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await testCasesApi.executionPath(projectId, testCaseId);
      setPath(res.data);
    } catch (e: unknown) {
      // Degrade to saying nothing rather than to an empty checklist, which
      // would read as "no blockers".
      setPath(null);
      setError(e instanceof Error ? e.message : "Could not load the execution path.");
    } finally {
      setLoading(false);
    }
  }, [projectId, testCaseId]);

  useEffect(() => { load(); }, [load]);

  if (loading && !path) {
    return (
      <div className={cn("flex items-center gap-2 rounded-xl border border-gray-200 bg-white p-4 text-xs font-semibold text-gray-500", className)}>
        <Loader2 className="h-4 w-4 animate-spin" />
        Checking what stands between this test case and a run…
      </div>
    );
  }

  if (error || !path) {
    return (
      <div className={cn("rounded-xl border border-gray-200 bg-white p-4", className)}>
        <p className="text-xs font-bold text-gray-700">Path to execution</p>
        <p className="mt-1 text-[11px] font-semibold text-gray-500">
          {error || "Unavailable."} The steps are unknown, not clear — check the modules directly.
        </p>
      </div>
    );
  }

  const nextKey = path.steps.find((s) => s.state === "BLOCKED" || s.state === "UNKNOWN")?.key;
  const pct = path.steps_total ? Math.round((path.steps_done / path.steps_total) * 100) : 0;

  return (
    <div className={cn("rounded-xl border bg-white p-4", path.ready_to_execute ? "border-emerald-200" : "border-gray-200", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-extrabold text-gray-800">Path to execution</p>
          <p className="text-[11px] font-semibold text-gray-500">
            {path.ready_to_execute
              ? "Every prerequisite is met."
              : path.next_action
                ? <>Next: <span className="font-bold text-amber-800">{path.next_action}</span></>
                : "Nothing outstanding."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-bold text-gray-600">{path.steps_done}/{path.steps_total}</span>
          <button
            onClick={load}
            disabled={loading}
            aria-label="Refresh path"
            className="rounded-md border border-gray-200 p-1 text-gray-500 hover:bg-gray-50"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          </button>
        </div>
      </div>

      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
        <div
          className={cn("h-full rounded-full transition-all", path.ready_to_execute ? "bg-emerald-500" : "bg-[#B71920]")}
          style={{ width: `${pct}%` }}
        />
      </div>

      <ul className="mt-3 space-y-0.5">
        {path.steps.map((step) => (
          <Row key={step.key} step={step} isNext={step.key === nextKey} />
        ))}
      </ul>

      {path.errors.length > 0 && (
        <ul className="mt-2 border-t border-gray-100 pt-2">
          {path.errors.map((e) => (
            <li key={e} className="text-[10px] font-semibold text-amber-700">{e}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * The same path, one line per test case.
 *
 * A suite has many members and an empty workspace has none selected, so the
 * full nine-row panel does not fit either. This keeps what matters at a glance
 * — how far along, and the single next thing — and links through for the rest.
 *
 * Each row fetches independently: one unreachable test case must not blank the
 * list, and a row that cannot be read says so rather than showing zero.
 */
export function ExecutionPathList({
  projectId,
  testCases,
  emptyMessage = "No test cases to show.",
  className,
}: {
  projectId: number;
  testCases: Array<{ id: number; label: string }>;
  emptyMessage?: string;
  className?: string;
}) {
  if (!testCases.length) {
    return <p className={cn("text-[11px] font-semibold text-gray-400", className)}>{emptyMessage}</p>;
  }
  return (
    <ul className={cn("space-y-1", className)}>
      {testCases.map((tc) => (
        <ExecutionPathRow key={tc.id} projectId={projectId} testCaseId={tc.id} label={tc.label} />
      ))}
    </ul>
  );
}

function ExecutionPathRow({
  projectId,
  testCaseId,
  label,
}: {
  projectId: number;
  testCaseId: number;
  label: string;
}) {
  const [path, setPath] = useState<ExecutionPath | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    testCasesApi
      .executionPath(projectId, testCaseId)
      .then((res) => live && setPath(res.data))
      .catch(() => live && setFailed(true));
    return () => { live = false; };
  }, [projectId, testCaseId]);

  const pct = path?.steps_total ? Math.round((path.steps_done / path.steps_total) * 100) : 0;

  return (
    <li className="flex items-center gap-3 rounded-lg border border-gray-100 px-2.5 py-1.5">
      <span className="w-20 shrink-0 truncate font-mono text-[11px] font-bold text-gray-700">{label}</span>
      <span className="h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-gray-100">
        <span
          className={cn("block h-full rounded-full", path?.ready_to_execute ? "bg-emerald-500" : "bg-[#B71920]")}
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="w-9 shrink-0 text-[11px] font-bold text-gray-600">
        {path ? `${path.steps_done}/${path.steps_total}` : failed ? "—" : "…"}
      </span>
      <span className="min-w-0 flex-1 truncate text-[11px] font-semibold">
        {failed ? (
          <span className="text-gray-400">Path unavailable — check the modules directly.</span>
        ) : !path ? (
          <span className="text-gray-400">Checking…</span>
        ) : path.ready_to_execute ? (
          <span className="text-emerald-700">Ready to execute</span>
        ) : (
          <span className="text-gray-600">
            Next: <span className="font-bold text-amber-800">{path.next_action}</span>
          </span>
        )}
      </span>
      {path?.next_action_href && (
        <Link
          href={path.next_action_href}
          className="shrink-0 rounded-md border border-amber-300 bg-white px-2 py-0.5 text-[10px] font-bold text-amber-800 hover:bg-amber-50"
        >
          Go
        </Link>
      )}
    </li>
  );
}
