// UI-019 Live Recorder — shared presentation helpers.

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { RecorderMeasure, RecorderStepStatus } from "@/lib/api";

/**
 * Contract Section 14's session states, as the capture engine reports them.
 * `label` is the reader-facing wording; the raw state stays available in the
 * title attribute so nothing is hidden.
 */
const RECORDING_STATUS_TONE: Record<
  string,
  { label: string; variant: React.ComponentProps<typeof Badge>["variant"] }
> = {
  NOT_STARTED: { label: "Draft", variant: "secondary" },
  INITIALISING: { label: "Launching", variant: "info" },
  RECORDING: { label: "Recording", variant: "destructive" },
  PAUSE_REQUESTED: { label: "Pausing", variant: "warning" },
  PAUSED: { label: "Paused", variant: "warning" },
  RESUMING: { label: "Resuming", variant: "info" },
  STOP_REQUESTED: { label: "Stopping", variant: "warning" },
  STOPPED: { label: "Captured", variant: "success" },
  COMPLETED: { label: "Completed", variant: "success" },
  CANCELLED: { label: "Discarded", variant: "outline" },
  FAILED: { label: "Failed", variant: "destructive" },
  EMERGENCY_STOPPED: { label: "Emergency Stopped", variant: "destructive" },
};

export function RecordingStatusBadge({ status, className }: { status: string; className?: string }) {
  const tone = RECORDING_STATUS_TONE[status] ?? { label: status, variant: "secondary" as const };
  return (
    <Badge variant={tone.variant} className={cn("text-[9px]", className)} title={status}>
      {tone.label}
    </Badge>
  );
}

const STEP_STATUS_TONE: Record<
  RecorderStepStatus,
  { label: string; dot: string; text: string }
> = {
  PENDING: { label: "Pending", dot: "bg-slate-300", text: "text-slate-400" },
  ACTIVE: { label: "Recording…", dot: "bg-[#1b59f8] animate-pulse", text: "text-[#1b59f8]" },
  RECORDED: { label: "Recorded", dot: "bg-emerald-500", text: "text-emerald-600" },
  PARTIALLY_RECORDED: { label: "Partial", dot: "bg-amber-500", text: "text-amber-600" },
  SKIPPED: { label: "Skipped", dot: "bg-slate-400", text: "text-slate-500" },
  MISMATCH: { label: "Mismatch", dot: "bg-red-500", text: "text-red-600" },
  NEEDS_REVIEW: { label: "Needs Review", dot: "bg-amber-500", text: "text-amber-600" },
  COMPLETED: { label: "Completed", dot: "bg-emerald-600", text: "text-emerald-700" },
};

export function StepStatusPill({
  status,
  reason,
}: {
  status: RecorderStepStatus;
  reason?: string;
}) {
  const tone = STEP_STATUS_TONE[status] ?? STEP_STATUS_TONE.PENDING;
  return (
    <span className={cn("flex items-center gap-1.5 text-[10px] font-bold", tone.text)} title={reason}>
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", tone.dot)} />
      {tone.label}
    </span>
  );
}

export function stepStatusLabel(status: RecorderStepStatus): string {
  return (STEP_STATUS_TONE[status] ?? STEP_STATUS_TONE.PENDING).label;
}

/**
 * Renders a summary figure, or an explained dash when the platform genuinely
 * has no source for it. A `RecorderMeasure` carries its own reason, which is
 * the whole point of the type — a zero and an unknown are different answers.
 */
export function MeasureValue({
  measure,
  className,
}: {
  measure: RecorderMeasure | undefined;
  className?: string;
}) {
  if (!measure || measure.value === null) {
    return (
      <span
        className={cn("font-extrabold text-slate-300", className)}
        title={measure?.reason ?? "Not available."}
      >
        —
      </span>
    );
  }
  return <span className={cn("font-extrabold text-slate-950", className)}>{measure.value}</span>;
}

const CONFIDENCE_TONE = (confidence: number | null) => {
  if (confidence === null) return "bg-slate-100 text-slate-500 border-slate-200";
  if (confidence >= 80) return "bg-emerald-50 text-emerald-700 border-emerald-100";
  if (confidence >= 60) return "bg-amber-50 text-amber-700 border-amber-100";
  return "bg-red-50 text-red-700 border-red-100";
};

/** Section 19 — a locator's confidence, never hidden and never rounded up. */
export function ConfidenceChip({ confidence }: { confidence: number | null }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] font-extrabold",
        CONFIDENCE_TONE(confidence),
      )}
      title={
        confidence === null
          ? "No locator candidate was observed for this action."
          : `Best locator scored ${confidence} out of 100.`
      }
    >
      {confidence === null ? "no locator" : `${confidence}%`}
    </span>
  );
}

const ACTION_FAMILY_LABEL: Record<string, string> = {
  navigate: "Navigate",
  click: "Click",
  input: "Type",
  read: "Observe",
  select: "Select",
  upload: "Upload",
  download: "Download",
  wait: "Wait",
  api: "API",
  database_validation: "DB Check",
  context_switch: "Switch Context",
  mobile_gesture: "Gesture",
};

export function actionFamilyLabel(family: string): string {
  return ACTION_FAMILY_LABEL[family] ?? family;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

/** A read-only inherited value (Section 4) — shown, never editable here. */
export function InheritedField({
  label,
  value,
  href,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  href?: string;
  hint?: string;
}) {
  return (
    <div className="min-w-0">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[9px] font-bold uppercase tracking-wide text-slate-400">{label}</p>
        {href && (
          <a
            href={href}
            className="text-[9px] font-bold text-[#1b59f8] hover:underline"
            title="Corrections are made in the authoritative source, not in the recorder."
          >
            Change
          </a>
        )}
      </div>
      <div className="mt-0.5 truncate text-xs font-bold text-slate-800" title={hint}>
        {value ?? <span className="text-slate-300">—</span>}
      </div>
    </div>
  );
}
