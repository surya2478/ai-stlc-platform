"use client";

import { Cpu } from "lucide-react";
import { cn } from "@/lib/utils";
import { useRunnerStatus } from "@/lib/queries/execution";

/**
 * Compact host-runner readiness indicator. Shows one dot per framework the
 * backend host can (or cannot) execute, with the preflight detail on hover.
 */
export function RunnerStatusChip({ className }: { className?: string }) {
  const { data, isLoading } = useRunnerStatus();
  const frameworks = data?.frameworks ?? [];

  if (isLoading || frameworks.length === 0) return null;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5",
        className,
      )}
    >
      <Cpu className="h-3.5 w-3.5 text-slate-400" />
      {frameworks.map((f) => (
        <span
          key={f.framework}
          title={f.detail}
          className={cn(
            "inline-flex items-center gap-1 text-[11px] font-medium capitalize",
            f.available ? "text-slate-700" : "text-slate-400 line-through decoration-slate-300",
          )}
        >
          <span className={cn("h-1.5 w-1.5 rounded-full", f.available ? "bg-emerald-500" : "bg-red-400")} />
          {f.framework}
        </span>
      ))}
    </div>
  );
}

/** True if the given framework can run on the backend host. */
export function useFrameworkAvailable(framework: string | null | undefined): boolean | undefined {
  const { data } = useRunnerStatus();
  if (!data) return undefined;
  const entry = data.frameworks.find(
    (f) => f.framework.toLowerCase() === String(framework ?? "").toLowerCase(),
  );
  return entry?.available;
}
