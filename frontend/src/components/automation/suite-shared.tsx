// UI-018 Automation Workspace — shared presentation helpers.

import type { LucideIcon } from "lucide-react";
import { AlertTriangle, Lock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { AutomationSuiteStatus, SuiteMemberStatus } from "@/lib/api";

export type Tone = "blue" | "emerald" | "red" | "purple" | "amber" | "slate";

const TONE_MAP: Record<Tone, string> = {
  blue: "bg-blue-50 border-blue-100 text-blue-600",
  emerald: "bg-emerald-50 border-emerald-100 text-emerald-600",
  red: "bg-red-50 border-red-100 text-red-600",
  purple: "bg-purple-50 border-purple-100 text-purple-600",
  amber: "bg-amber-50 border-amber-100 text-amber-600",
  slate: "bg-slate-50 border-slate-100 text-slate-600",
};

export function messageFromError(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (d as { msg?: string })?.msg ?? String(d)).join("; ");
  }
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: string }).message;
    if (message) return message;
  }
  const fallback = (error as { message?: string })?.message;
  return fallback || "Something went wrong.";
}

/** Renders a metric, or an explained dash when the platform has no source for it. */
export function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  tone,
  unavailableReason,
}: {
  title: string;
  value: string | number | null | undefined;
  subtitle: string;
  icon: LucideIcon;
  tone: Tone;
  unavailableReason?: string;
}) {
  const missing = value === null || value === undefined;
  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
      title={missing ? unavailableReason : undefined}
    >
      <div className="flex items-center gap-2.5">
        <div
          className={cn(
            "flex h-8 w-8 items-center justify-center rounded-lg border",
            TONE_MAP[missing ? "slate" : tone],
          )}
        >
          <Icon className="h-4 w-4" />
        </div>
        <p className="min-w-0 truncate text-xs font-bold text-slate-700">{title}</p>
      </div>
      <p
        className={cn(
          "mt-3 text-2xl font-extrabold leading-none",
          missing ? "text-slate-300" : "text-slate-950",
        )}
      >
        {missing ? "—" : value}
      </p>
      <p className="mt-1.5 text-[11px] font-semibold text-slate-500">
        {missing ? (unavailableReason ?? "Not tracked") : subtitle}
      </p>
    </div>
  );
}

export function Panel({
  title,
  action,
  children,
  className,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-lg border border-slate-200 bg-white p-3", className)}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-[10px] font-extrabold uppercase tracking-wide text-slate-800">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

const SUITE_STATUS_TONE: Record<
  AutomationSuiteStatus,
  { label: string; variant: React.ComponentProps<typeof Badge>["variant"] }
> = {
  DRAFT: { label: "Draft", variant: "secondary" },
  SCOPE_SELECTED: { label: "Scope Selected", variant: "info" },
  INHERITANCE_REVIEW_REQUIRED: { label: "Inheritance Review", variant: "warning" },
  MAPPING_INCOMPLETE: { label: "Mapping Incomplete", variant: "destructive" },
  CONFLICT_REVIEW_REQUIRED: { label: "Conflict Review", variant: "destructive" },
  READY_FOR_VALIDATION: { label: "Ready for Validation", variant: "success" },
  VALIDATION_PENDING: { label: "Validation Pending", variant: "info" },
  VALIDATION_FAILED: { label: "Validation Failed", variant: "destructive" },
  READY_FOR_REVIEW: { label: "Ready for Review", variant: "info" },
  APPROVED: { label: "Approved", variant: "success" },
  PUBLISHED: { label: "Published", variant: "purple" },
  DEPRECATED: { label: "Deprecated", variant: "outline" },
  ARCHIVED: { label: "Archived", variant: "outline" },
};

export function SuiteStatusBadge({
  status,
  className,
}: {
  status: AutomationSuiteStatus;
  className?: string;
}) {
  const tone = SUITE_STATUS_TONE[status] ?? { label: status, variant: "secondary" as const };
  return (
    <Badge variant={tone.variant} className={cn("text-[9px]", className)}>
      {tone.label}
    </Badge>
  );
}

const MEMBER_STATUS_TONE: Record<
  SuiteMemberStatus,
  { label: string; variant: React.ComponentProps<typeof Badge>["variant"] }
> = {
  NOT_EVALUATED: { label: "Not Evaluated", variant: "outline" },
  READY: { label: "Ready", variant: "success" },
  WARNING: { label: "Warning", variant: "warning" },
  BLOCKED: { label: "Blocked", variant: "destructive" },
};

export function MemberStatusBadge({ status }: { status: SuiteMemberStatus }) {
  const tone = MEMBER_STATUS_TONE[status] ?? { label: status, variant: "secondary" as const };
  return (
    <Badge variant={tone.variant} className="text-[9px]">
      {tone.label}
    </Badge>
  );
}

export function SeverityBadge({ severity }: { severity: "critical" | "warning" }) {
  return (
    <Badge variant={severity === "critical" ? "destructive" : "warning"} className="text-[9px]">
      {severity === "critical" ? "Critical" : "Warning"}
    </Badge>
  );
}

/** A control that exists in the contract but has no backing capability yet. */
export function DisabledAction({
  label,
  reason,
  icon: Icon,
  className,
}: {
  label: string;
  reason: string;
  icon?: LucideIcon;
  className?: string;
}) {
  return (
    <button
      type="button"
      disabled
      title={reason}
      className={cn(
        "flex w-full cursor-not-allowed items-start gap-2.5 rounded-lg border border-dashed border-slate-200 bg-slate-50/60 px-3 py-2.5 text-left",
        className,
      )}
    >
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-400">
        {Icon ? <Icon className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-xs font-bold text-slate-500">{label}</span>
        <span className="block text-[10px] font-semibold text-slate-400">{reason}</span>
      </span>
    </button>
  );
}

export function DisabledTab({ label, reason }: { label: string; reason: string }) {
  return (
    <button
      type="button"
      disabled
      title={reason}
      className="flex cursor-not-allowed items-center gap-1 whitespace-nowrap border-b-2 border-transparent px-2.5 py-2 text-[10px] font-bold text-slate-300"
    >
      <Lock className="h-3 w-3" />
      {label}
    </button>
  );
}

export function Banner({
  kind,
  message,
  onDismiss,
}: {
  kind: "error" | "info";
  message: string;
  onDismiss?: () => void;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-lg border px-4 py-3 text-xs font-semibold",
        kind === "error"
          ? "border-red-200 bg-red-50 text-red-700"
          : "border-blue-200 bg-blue-50 text-blue-700",
      )}
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span className="min-w-0 flex-1">{message}</span>
      {onDismiss && (
        <button type="button" onClick={onDismiss} className="shrink-0 text-[10px] font-bold underline">
          Dismiss
        </button>
      )}
    </div>
  );
}

export function EmptyRow({ colSpan, message }: { colSpan: number; message: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="p-6 text-center text-[10px] font-semibold text-slate-400">
        {message}
      </td>
    </tr>
  );
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Turns MAPPING_INCOMPLETE-style codes into readable labels. */
export function humanizeCode(code: string): string {
  return code
    .toLowerCase()
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
