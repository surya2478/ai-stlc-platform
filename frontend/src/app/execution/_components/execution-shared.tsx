"use client";

import { ReactNode } from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

/* ------------------------------------------------------------------ */
/* Page header                                                         */
/* ------------------------------------------------------------------ */

export function ExecutionPageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-gray-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* KPI card                                                            */
/* ------------------------------------------------------------------ */

export type KpiTone = "blue" | "violet" | "emerald" | "red" | "orange" | "cyan" | "slate";

const KPI_TONE: Record<KpiTone, { bg: string; text: string; ring: string }> = {
  blue:    { bg: "bg-app-brand-75",    text: "text-[#B71920]",  ring: "ring-app-brand-100" },
  violet:  { bg: "bg-violet-50",  text: "text-violet-600", ring: "ring-violet-100" },
  emerald: { bg: "bg-emerald-50", text: "text-emerald-600", ring: "ring-emerald-100" },
  red:     { bg: "bg-red-50",     text: "text-red-600",    ring: "ring-red-100" },
  orange:  { bg: "bg-orange-50",  text: "text-orange-600", ring: "ring-orange-100" },
  cyan:    { bg: "bg-cyan-50",    text: "text-cyan-600",   ring: "ring-cyan-100" },
  slate:   { bg: "bg-gray-100",  text: "text-gray-600",  ring: "ring-gray-200" },
};

export function KpiCard({
  icon: Icon,
  tone = "blue",
  label,
  value,
  delta,
  deltaDirection,
  loading,
}: {
  icon: React.ComponentType<{ className?: string }>;
  tone?: KpiTone;
  label: string;
  value: ReactNode;
  delta?: string;
  deltaDirection?: "up" | "down" | "neutral";
  loading?: boolean;
}) {
  const t = KPI_TONE[tone];
  const deltaColor =
    deltaDirection === "up"
      ? "text-emerald-600"
      : deltaDirection === "down"
      ? "text-red-600"
      : "text-gray-500";
  const arrow = deltaDirection === "up" ? "↑" : deltaDirection === "down" ? "↓" : "";

  return (
    <Card className="shadow-sm hover:shadow transition-shadow">
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ring-1", t.bg, t.ring)}>
            <Icon className={cn("h-5 w-5", t.text)} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-gray-500">{label}</p>
            <p className="mt-1 text-2xl font-bold text-gray-900 tabular-nums">
              {loading ? <span className="inline-block h-6 w-16 animate-pulse rounded bg-gray-100" /> : value}
            </p>
            {delta && !loading && (
              <p className={cn("mt-1 text-[11px] font-medium", deltaColor)}>
                {arrow} {delta}
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Horizontal step indicator                                           */
/* ------------------------------------------------------------------ */

export type ProcessStep = {
  label: string;
  description?: string;
};

export function ProcessSteps({
  steps,
  currentStep,
}: {
  steps: ProcessStep[];
  currentStep: number;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <ol className="flex flex-wrap items-center gap-y-3">
        {steps.map((step, idx) => {
          const stepNum = idx + 1;
          const done = stepNum < currentStep;
          const active = stepNum === currentStep;
          return (
            <li key={step.label} className="flex flex-1 min-w-[180px] items-center gap-3">
              <div className="flex items-center gap-3">
                <div
                  className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold transition-colors",
                    done
                      ? "bg-emerald-500 text-white"
                      : active
                      ? "bg-[#B71920] text-white shadow"
                      : "bg-gray-100 text-gray-500"
                  )}
                >
                  {done ? <Check className="h-4 w-4" /> : stepNum}
                </div>
                <div className="min-w-0">
                  <p
                    className={cn(
                      "text-xs font-semibold leading-tight",
                      active ? "text-gray-900" : done ? "text-gray-700" : "text-gray-500"
                    )}
                  >
                    {step.label}
                  </p>
                  {step.description && (
                    <p className="text-[11px] text-gray-400 leading-tight">{step.description}</p>
                  )}
                </div>
              </div>
              {idx < steps.length - 1 && (
                <div className="hidden md:block flex-1 h-px bg-gray-200 mx-3" aria-hidden />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Execution status badge                                              */
/* ------------------------------------------------------------------ */

export type ExecutionStatus =
  | "passed" | "pass"
  | "failed" | "fail"
  | "blocked"
  | "skipped"
  | "in_progress" | "running" | "queued"
  | "not_run" | "pending" | "not_started"
  | "auto_completed"
  | "review_required"
  | "inconclusive"
  | "completed"
  | "cancelled"
  | "error"
  | (string & {});

type BadgeVariant =
  | "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple";

function variantForStatus(status: ExecutionStatus): { variant: BadgeVariant; label: string } {
  const s = String(status).toLowerCase();
  switch (s) {
    case "passed":
    case "pass":
    case "completed":
      return { variant: "success", label: s === "completed" ? "Completed" : "Passed" };
    case "auto_completed":
      return { variant: "success", label: "Auto-Completed" };
    case "failed":
    case "fail":
    case "error":
      return { variant: "destructive", label: "Failed" };
    case "blocked":
      return { variant: "warning", label: "Blocked" };
    case "skipped":
      return { variant: "secondary", label: "Skipped" };
    case "in_progress":
    case "running":
      return { variant: "info", label: "In Progress" };
    case "queued":
      return { variant: "info", label: "Queued" };
    case "not_run":
    case "pending":
    case "not_started":
      return { variant: "outline", label: "Not Run" };
    case "review_required":
      return { variant: "purple", label: "Review Required" };
    case "inconclusive":
      return { variant: "warning", label: "Inconclusive" };
    case "cancelled":
      return { variant: "secondary", label: "Cancelled" };
    default:
      return { variant: "secondary", label: String(status).replace(/_/g, " ") };
  }
}

export function ExecutionStatusBadge({ status, className }: { status: ExecutionStatus; className?: string }) {
  const { variant, label } = variantForStatus(status);
  return (
    <Badge variant={variant as BadgeVariant} className={cn("capitalize", className)}>
      {label}
    </Badge>
  );
}

/* ------------------------------------------------------------------ */
/* Automation script status badge                                      */
/* ------------------------------------------------------------------ */

export type ScriptStatus =
  | "ai_draft"
  | "draft"
  | "in_review"
  | "pending_approval"
  | "approved"
  | "rejected"
  | "executed"
  | "deprecated"
  | "blocked"
  | (string & {});

const SCRIPT_STATUS_BADGE: Record<string, { variant: BadgeVariant; label: string }> = {
  ai_draft:         { variant: "purple",      label: "AI Draft" },
  draft:            { variant: "outline",     label: "Draft" },
  in_review:        { variant: "info",        label: "In Review" },
  pending_approval: { variant: "info",        label: "Pending Approval" },
  approved:         { variant: "success",     label: "Approved" },
  rejected:         { variant: "destructive", label: "Rejected" },
  executed:         { variant: "success",     label: "Executed" },
  deprecated:       { variant: "secondary",   label: "Deprecated" },
  blocked:          { variant: "warning",     label: "Blocked" },
};

export function ScriptStatusBadge({ status, className }: { status: ScriptStatus; className?: string }) {
  const entry =
    SCRIPT_STATUS_BADGE[String(status).toLowerCase()] ??
    ({ variant: "secondary", label: String(status).replace(/_/g, " ") } as const);
  return (
    <Badge variant={entry.variant} className={cn("capitalize", className)}>
      {entry.label}
    </Badge>
  );
}

export type ExecutionType = "manual" | "automation" | "ai" | (string & {});

export function ExecutionTypeBadge({ type, className }: { type: ExecutionType; className?: string }) {
  const t = String(type).toLowerCase();
  if (t === "manual") {
    return <Badge variant="secondary" className={cn("capitalize", className)}>Manual</Badge>;
  }
  if (t === "automation") {
    return <Badge variant="info" className={cn("capitalize", className)}>Automation</Badge>;
  }
  if (t === "ai") {
    return <Badge variant="purple" className={cn("capitalize", className)}>AI</Badge>;
  }
  return <Badge variant="secondary" className={cn("capitalize", className)}>{t}</Badge>;
}

/* ------------------------------------------------------------------ */
/* Build href preserving project + env query params                    */
/* ------------------------------------------------------------------ */

export function buildHref(base: string, params: URLSearchParams | Record<string, string | null | undefined>): string {
  const sp =
    params instanceof URLSearchParams
      ? new URLSearchParams(params.toString())
      : new URLSearchParams(Object.entries(params).reduce<Record<string, string>>((acc, [k, v]) => {
          if (v !== null && v !== undefined) acc[k] = String(v);
          return acc;
        }, {}));
  const qs = sp.toString();
  return qs ? `${base}?${qs}` : base;
}

/* ------------------------------------------------------------------ */
/* Empty + error states                                                */
/* ------------------------------------------------------------------ */

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-200 bg-gray-50/50 p-10 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white ring-1 ring-gray-200">
        <Icon className="h-6 w-6 text-gray-400" />
      </div>
      <h3 className="mt-3 text-sm font-semibold text-gray-700">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-xs text-gray-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  description,
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-red-100 bg-red-50/50 p-10 text-center">
      <h3 className="text-sm font-semibold text-red-700">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-xs text-red-500">{description}</p>}
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function LoadingSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-10 animate-pulse rounded-lg bg-gray-100" />
      ))}
    </div>
  );
}
