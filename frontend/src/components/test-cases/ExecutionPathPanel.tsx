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
  DONE: { icon: Check, ring: "border-emerald-200 bg-emerald-50 text-emerald-600", text: "text-slate-700", label: "Done" },
  BLOCKED: { icon: AlertTriangle, ring: "border-amber-300 bg-amber-100 text-amber-700", text: "text-slate-900", label: "Do this next" },
  // Deliberately muted: a consequence of an earlier step is not something to
  // act on, and colouring it like a blocker is what turns a checklist into noise.
  WAITING: { icon: CircleDot, ring: "border-slate-200 bg-slate-50 text-slate-300", text: "text-slate-400", label: "Waiting" },
  UNKNOWN: { icon: HelpCircle, ring: "border-slate-300 bg-slate-100 text-slate-500", text: "text-slate-600", label: "Unknown" },
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
        <span className={cn("block text-[11px] font-semibold", step.state === "WAITING" ? "text-slate-400" : "text-slate-500")}>
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
      <div className={cn("flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-4 text-xs font-semibold text-slate-500", className)}>
        <Loader2 className="h-4 w-4 animate-spin" />
        Checking what stands between this test case and a run…
      </div>
    );
  }

  if (error || !path) {
    return (
      <div className={cn("rounded-xl border border-slate-200 bg-white p-4", className)}>
        <p className="text-xs font-bold text-slate-700">Path to execution</p>
        <p className="mt-1 text-[11px] font-semibold text-slate-500">
          {error || "Unavailable."} The steps are unknown, not clear — check the modules directly.
        </p>
      </div>
    );
  }

  const nextKey = path.steps.find((s) => s.state === "BLOCKED" || s.state === "UNKNOWN")?.key;
  const pct = path.steps_total ? Math.round((path.steps_done / path.steps_total) * 100) : 0;

  return (
    <div className={cn("rounded-xl border bg-white p-4", path.ready_to_execute ? "border-emerald-200" : "border-slate-200", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-extrabold text-slate-800">Path to execution</p>
          <p className="text-[11px] font-semibold text-slate-500">
            {path.ready_to_execute
              ? "Every prerequisite is met."
              : path.next_action
                ? <>Next: <span className="font-bold text-amber-800">{path.next_action}</span></>
                : "Nothing outstanding."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-bold text-slate-600">{path.steps_done}/{path.steps_total}</span>
          <button
            onClick={load}
            disabled={loading}
            aria-label="Refresh path"
            className="rounded-md border border-slate-200 p-1 text-slate-500 hover:bg-slate-50"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          </button>
        </div>
      </div>

      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={cn("h-full rounded-full transition-all", path.ready_to_execute ? "bg-emerald-500" : "bg-[#1b59f8]")}
          style={{ width: `${pct}%` }}
        />
      </div>

      <ul className="mt-3 space-y-0.5">
        {path.steps.map((step) => (
          <Row key={step.key} step={step} isNext={step.key === nextKey} />
        ))}
      </ul>

      {path.errors.length > 0 && (
        <ul className="mt-2 border-t border-slate-100 pt-2">
          {path.errors.map((e) => (
            <li key={e} className="text-[10px] font-semibold text-amber-700">{e}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
