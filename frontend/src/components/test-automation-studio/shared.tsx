"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type {
  TasApprovalStatus,
  TasClassification,
  TasCoverageState,
  TasTestDataStatus,
} from "@/lib/api";

export function StatTile({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: number | string;
  hint?: string;
  tone?: "default" | "warning" | "success";
}) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-white px-4 py-3 shadow-sm",
        tone === "warning" && "border-amber-200 bg-amber-50/60",
        tone === "success" && "border-emerald-200 bg-emerald-50/60",
        tone === "default" && "border-gray-200",
      )}
    >
      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-bold leading-none text-gray-900">{value}</p>
      {hint && <p className="mt-1 text-[11px] text-gray-500">{hint}</p>}
    </div>
  );
}

export function SectionCard({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-xl border border-gray-200 bg-white shadow-sm", className)}>
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-gray-100 px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
          {description && <p className="mt-0.5 text-xs text-gray-500">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

/** Live progress for a queued studio job.
 *
 *  Shows the worker's own `progress_message` rather than a canned stage list
 *  on a timer: the message names the actual test case being generated, and an
 *  invented one can only ever be a guess at what the job is doing. */
export function JobProgress({
  percent,
  message,
}: {
  percent: number;
  message: string;
}) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50/70 px-3 py-2">
      <div className="mb-1.5 flex items-center justify-between gap-3">
        <p className="min-w-0 truncate text-[11px] font-medium text-gray-700">
          {message || "Working..."}
        </p>
        <span className="shrink-0 text-[11px] font-semibold tabular-nums text-gray-500">
          {clamped}%
        </span>
      </div>
      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-gray-200"
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={message || "Job progress"}
      >
        <div
          className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-violet-500 transition-[width] duration-500 ease-out"
          style={{ width: `${clamped}%` }}
        />
      </div>
      <p className="mt-1 text-[10px] text-gray-500">
        This runs in the background - leaving the page will not stop it.
      </p>
    </div>
  );
}

/** Read the skipped entries out of a finished job's output.
 *
 *  Defensive because `output_data` is free-form JSON on the agent run: an
 *  older run, or a future change that writes a count instead of a list, must
 *  degrade to "no detail" rather than throwing inside a toast handler. */
export function skippedEntries(output: Record<string, unknown> | null | undefined) {
  const value = (output ?? {}).skipped;
  if (!Array.isArray(value)) return [];
  return value as Array<{
    requirement_key?: string | null;
    tc_display_id?: string | null;
    reason?: string | null;
  }>;
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50/60 px-6 py-10 text-center">
      <p className="text-sm font-semibold text-gray-700">{title}</p>
      <p className="mx-auto mt-1 max-w-lg text-xs text-gray-500">{description}</p>
    </div>
  );
}

const APPROVAL_VARIANTS: Record<TasApprovalStatus, "secondary" | "warning" | "success" | "destructive"> = {
  draft: "secondary",
  pending_approval: "warning",
  approved: "success",
  rejected: "destructive",
};

const APPROVAL_LABELS: Record<TasApprovalStatus, string> = {
  draft: "Draft",
  pending_approval: "Pending approval",
  approved: "Approved",
  rejected: "Rejected",
};

export function StatusBadge({ status }: { status: TasApprovalStatus }) {
  return <Badge variant={APPROVAL_VARIANTS[status] ?? "secondary"}>{APPROVAL_LABELS[status] ?? status}</Badge>;
}

const COVERAGE_VARIANTS: Record<TasCoverageState, "success" | "warning" | "destructive"> = {
  covered: "success",
  partially_covered: "warning",
  uncovered: "destructive",
};

const COVERAGE_LABELS: Record<TasCoverageState, string> = {
  covered: "Covered",
  partially_covered: "Partial",
  uncovered: "Not covered",
};

export function CoverageBadge({ state }: { state: TasCoverageState }) {
  return <Badge variant={COVERAGE_VARIANTS[state] ?? "secondary"}>{COVERAGE_LABELS[state] ?? state}</Badge>;
}

export function ClassificationBadge({ classification }: { classification: TasClassification }) {
  if (classification === "automation") return <Badge variant="info">Automation</Badge>;
  if (classification === "manual") return <Badge variant="purple">Manual</Badge>;
  return <Badge variant="secondary">Unclassified</Badge>;
}

/** The "Test Data Required Yes/No" column. `needs_user_action` is the only
 *  state that blocks approval, so it is the only one styled as a warning —
 *  colouring agent-provided data the same way would train users to ignore it. */
export function TestDataBadge({
  required,
  status,
}: {
  required: boolean;
  status: TasTestDataStatus;
}) {
  if (status === "needs_user_action" || required) {
    return <Badge variant="warning">Yes - action needed</Badge>;
  }
  if (status === "agent_provided") return <Badge variant="success">No - agent provided</Badge>;
  if (status === "user_provided") return <Badge variant="success">No - user provided</Badge>;
  return <Badge variant="secondary">No</Badge>;
}

export function OriginBadge({
  origin,
}: {
  origin: "existing" | "imported" | "derived" | "extracted";
}) {
  if (origin === "existing") return <Badge variant="outline">Existing TC</Badge>;
  // An uploaded test case refined in place — it kept the ID and name from the
  // sheet, which is a different provenance from one the studio invented.
  if (origin === "imported") return <Badge variant="outline">Uploaded TC</Badge>;
  if (origin === "extracted") return <Badge variant="outline">From document</Badge>;
  return <Badge variant="purple">Gap-derived</Badge>;
}
