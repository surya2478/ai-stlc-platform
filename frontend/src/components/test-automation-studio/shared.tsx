"use client";

import { AlertTriangle, Loader2, Trash2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type {
  TasApprovalStatus,
  TasClassification,
  TasCoverageState,
  TasDeletionSummary,
  TasDryRunStatus,
  TasGroundingStatus,
  TasTestDataStatus,
} from "@/lib/api";

/** Button tints for the studio, keyed by what the action *does*.
 *
 *  The Script Lab already spoke in colour — a cyan-to-violet gradient for the
 *  agent run, red for the delete — while every other action on all three
 *  screens was the same grey outline, so a row of eight buttons read as one
 *  undifferentiated block. These extend that existing language rather than
 *  replace it: the gradient still marks a headline agent run (`variant="ai"`)
 *  and the brand red still marks the primary commit (`variant="default"`);
 *  everything else takes a soft tint from the same family as the badge that
 *  describes its result, so the button and the state it produces agree.
 *
 *  Applied as a `className` over `variant="outline"` (or `"default"` for the
 *  two solid tones) — `cn` runs through tailwind-merge, so the tone's border,
 *  background and text simply win over the variant's neutrals. Purely
 *  presentational: no tone changes what a button is wired to, and disabled
 *  buttons keep the variant's `disabled:opacity-50`. */
export const tasButtonTone = {
  /** Runs against the live application — Discover, Check Grounding, Dry run. */
  live: "border-cyan-200 bg-cyan-50 text-cyan-700 hover:border-cyan-300 hover:bg-cyan-100 hover:text-cyan-800",
  /** A secondary agent job: the gradient of `variant="ai"`, softened so it
   *  reads as "same kind of work, not the headline action". */
  agentSoft:
    "border-violet-200 bg-gradient-to-r from-cyan-50 to-violet-50 text-violet-700 hover:from-cyan-100 hover:to-violet-100 hover:text-violet-800",
  /** Feeds the studio or saves its configuration — the brand colour, softened
   *  so it sits beside the solid brand primary without competing with it. */
  brandSoft:
    "border-[#B71920]/25 bg-[#B71920]/5 text-[#B71920] hover:border-[#B71920]/40 hover:bg-[#B71920]/10 hover:text-[#B71920]",
  /** Takes something out of the studio — every download and export. */
  export:
    "border-indigo-200 bg-indigo-50 text-indigo-700 hover:border-indigo-300 hover:bg-indigo-100 hover:text-indigo-800",
  /** Matches the Automation classification badge (`info`). */
  automation:
    "border-blue-200 bg-blue-50 text-blue-700 hover:border-blue-300 hover:bg-blue-100 hover:text-blue-800",
  /** Matches the Manual classification badge (`purple`). */
  manual:
    "border-purple-200 bg-purple-50 text-purple-700 hover:border-purple-300 hover:bg-purple-100 hover:text-purple-800",
  /** Solid, on `variant="default"`. Approve was the brand red, which is also
   *  the delete colour — two opposite outcomes in one hue. Emerald is what the
   *  Approved badge already uses. */
  approve: "bg-emerald-600 text-white hover:bg-emerald-700 hover:text-white",
  /** Sends something back rather than destroying it — Reject, Reopen. Amber,
   *  as the warning badges use. */
  reject:
    "border-amber-200 bg-amber-50 text-amber-700 hover:border-amber-300 hover:bg-amber-100 hover:text-amber-800",
  /** Not undoable. Already the convention here; now stated once. */
  danger: "border-red-200 bg-red-50 text-red-600 hover:border-red-300 hover:bg-red-100 hover:text-red-700",
  /** Low-emphasis utility that changes nothing — Refresh. */
  neutral:
    "border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:bg-slate-100 hover:text-slate-800",
} as const;

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

/** Confirmation for deleting generated artefacts.
 *
 *  Deletes in the studio are not undoable and rarely remove only the row that
 *  was clicked, so the dialog names the target and lists what goes with it
 *  rather than asking a bare "are you sure?". */
export function ConfirmDeleteDialog({
  title,
  target,
  consequences,
  confirmLabel = "Delete",
  busy = false,
  onCancel,
  onConfirm,
}: {
  title: string;
  target: string;
  consequences: string[];
  confirmLabel?: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="w-full max-w-md rounded-xl bg-white shadow-xl">
        <header className="flex items-start gap-2.5 border-b border-gray-100 px-5 py-3">
          <span className="mt-0.5 rounded-full bg-red-50 p-1.5 text-red-600">
            <AlertTriangle className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
            <p className="mt-0.5 text-xs text-gray-600">{target}</p>
          </div>
        </header>
        <div className="px-5 py-4">
          <ul className="space-y-1.5">
            {consequences.map((line) => (
              <li key={line} className="flex gap-2 text-xs text-gray-600">
                <span aria-hidden className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-gray-400" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[11px] font-medium text-red-700">This cannot be undone.</p>
        </div>
        <footer className="flex items-center justify-end gap-2 border-t border-gray-100 px-5 py-3">
          <Button
            size="sm"
            variant="outline"
            className={tasButtonTone.neutral}
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button size="sm" variant="destructive" onClick={onConfirm} disabled={busy}>
            {busy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
            {confirmLabel}
          </Button>
        </footer>
      </div>
    </div>
  );
}

/** The one-line "and this went too" for a finished delete.
 *
 *  Returns undefined when nothing beyond the selected rows was affected, so
 *  the caller can leave the toast description off entirely rather than show a
 *  row of zeroes. */
export function describeDeletion(summary: TasDeletionSummary): string | undefined {
  const parts: string[] = [];
  if (summary.versions_deleted) parts.push(`${summary.versions_deleted} earlier version(s)`);
  if (summary.scripts_deleted) parts.push(`${summary.scripts_deleted} generated script(s)`);
  if (summary.approved_deleted) parts.push(`${summary.approved_deleted} were approved`);
  if (summary.test_cases_unlinked) {
    parts.push(`${summary.test_cases_unlinked} test case(s) kept but no longer linked`);
  }
  if (summary.not_found.length) {
    parts.push(`${summary.not_found.length} had already gone`);
  }
  return parts.length ? parts.join(" | ") : undefined;
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

/** Whether a test case's steps resolve to elements that really exist.
 *
 *  `not_checked` is deliberately neutral rather than a warning: it means
 *  grounding has never run, which is the state every test case starts in and
 *  says nothing about the test case's quality. Only a grounding pass that ran
 *  and found nothing earns a red badge. */
export function GroundingBadge({ status }: { status: TasGroundingStatus }) {
  if (status === "grounded") return <Badge variant="success">Grounded</Badge>;
  if (status === "partially_grounded") return <Badge variant="warning">Partly grounded</Badge>;
  if (status === "ungrounded") return <Badge variant="destructive">Not grounded</Badge>;
  return <Badge variant="secondary">Not checked</Badge>;
}

/** Whether the generated script has actually been executed.
 *
 *  `blocked` is styled neutrally, not as a failure: it means this deployment
 *  has no runner for the framework (Katalon needs Katalon Studio, Appium needs
 *  a device), which is a property of the environment rather than a defect in
 *  the script. */
export function DryRunBadge({ status }: { status: TasDryRunStatus }) {
  if (status === "passed") return <Badge variant="success">Dry run passed</Badge>;
  if (status === "failed") return <Badge variant="destructive">Dry run failed</Badge>;
  if (status === "running") {
    return (
      <Badge variant="info">
        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
        Running
      </Badge>
    );
  }
  if (status === "queued") return <Badge variant="info">Queued</Badge>;
  if (status === "blocked") return <Badge variant="outline">Not runnable here</Badge>;
  return <Badge variant="secondary">Not run</Badge>;
}

/** How a script's code was produced.
 *
 *  Worth its own badge because the two modes carry genuinely different
 *  guarantees: a compiled script had its locators substituted from discovered
 *  evidence, a free-form one was only shown that evidence and asked nicely. */
export function GenerationModeBadge({ mode }: { mode: "compiled" | "freeform" }) {
  return mode === "compiled" ? (
    <Badge variant="info">Compiled</Badge>
  ) : (
    <Badge variant="outline">LLM-authored</Badge>
  );
}

/** Right-hand slide-over used by the discovery, grounding and dry-run
 *  detail panels.
 *
 *  A drawer rather than a route: all three answer "why does this row say
 *  that?", which is a question about a row and belongs beside it. Navigating
 *  away to answer it would lose the grid's selection and filters. */
export function SideDrawer({
  title,
  subtitle,
  onClose,
  footer,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  footer?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" role="dialog" aria-modal="true">
      {/* Backdrop closes the drawer; the panel stops the click so an
          interaction inside it never dismisses what it is interacting with. */}
      <button
        type="button"
        aria-label="Close"
        className="absolute inset-0 h-full w-full cursor-default"
        onClick={onClose}
      />
      <aside className="relative flex h-full w-full max-w-2xl flex-col bg-white shadow-2xl">
        <header className="flex items-start justify-between gap-3 border-b border-gray-100 px-5 py-3">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-gray-900">{title}</h3>
            {subtitle && <p className="mt-0.5 truncate text-xs text-gray-500">{subtitle}</p>}
          </div>
          <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close panel">
            <X className="h-4 w-4" />
          </Button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <footer className="flex items-center justify-end gap-2 border-t border-gray-100 px-5 py-3">
            {footer}
          </footer>
        )}
      </aside>
    </div>
  );
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
