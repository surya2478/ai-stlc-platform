"use client";

import { Check, Sparkles, FileEdit, Eye, ShieldCheck, PlayCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export type LifecycleStage =
  | "approved_tc"
  | "ai_draft"
  | "external_linked"
  | "draft"
  | "in_review"
  | "approved"
  | "verified"
  | "ready";

type Variant = "internal" | "external";

type Step = {
  key: LifecycleStage;
  label: string;
  icon: typeof Check;
};

const INTERNAL_STEPS: Step[] = [
  { key: "approved_tc", label: "Approved TC", icon: Check },
  { key: "ai_draft", label: "AI Draft", icon: Sparkles },
  { key: "draft", label: "Draft", icon: FileEdit },
  { key: "in_review", label: "In Review", icon: Eye },
  { key: "approved", label: "Approved", icon: ShieldCheck },
  { key: "ready", label: "Ready for Execution", icon: PlayCircle },
];

const EXTERNAL_STEPS: Step[] = [
  { key: "approved_tc", label: "Approved TC", icon: Check },
  { key: "external_linked", label: "Linked", icon: Sparkles },
  { key: "verified", label: "Verified", icon: ShieldCheck },
  { key: "ready", label: "Ready for Execution", icon: PlayCircle },
];

type Props = {
  current: LifecycleStage;
  variant?: Variant;
};

export function LifecycleStepper({ current, variant = "internal" }: Props) {
  const steps = variant === "external" ? EXTERNAL_STEPS : INTERNAL_STEPS;
  const currentIndex = steps.findIndex((s) => s.key === current);
  const effectiveIndex = currentIndex >= 0 ? currentIndex : 0;

  return (
    <div className="flex items-center gap-1 overflow-x-auto py-2">
      {steps.map((step, idx) => {
        const Icon = step.icon;
        const isDone = idx < effectiveIndex;
        const isCurrent = idx === effectiveIndex;
        const isUpcoming = idx > effectiveIndex;
        return (
          <div key={step.key} className="flex items-center gap-1 shrink-0">
            <div
              className={cn(
                "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold transition",
                isDone && "bg-emerald-50 text-emerald-700 border border-emerald-200",
                isCurrent && "bg-violet-100 text-violet-800 border border-violet-300",
                isUpcoming && "bg-slate-50 text-slate-500 border border-slate-200",
              )}
            >
              <Icon className="h-3 w-3" />
              {step.label}
            </div>
            {idx < steps.length - 1 && (
              <div
                className={cn(
                  "h-px w-4 shrink-0",
                  isDone ? "bg-emerald-300" : "bg-slate-200",
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

export function deriveLifecycleStage(
  scriptStatus: string | null | undefined,
  hasExternalMapping: boolean,
  externalVerified: boolean,
): { stage: LifecycleStage; variant: Variant } {
  if (hasExternalMapping) {
    if (externalVerified) return { stage: "ready", variant: "external" };
    return { stage: "external_linked", variant: "external" };
  }
  const s = (scriptStatus ?? "").toLowerCase();
  if (s === "approved" || s === "executed") return { stage: "ready", variant: "internal" };
  if (s === "in_review" || s === "pending_approval" || s === "under_review")
    return { stage: "in_review", variant: "internal" };
  if (s === "draft") return { stage: "draft", variant: "internal" };
  if (s === "ai_draft") return { stage: "ai_draft", variant: "internal" };
  return { stage: "approved_tc", variant: "internal" };
}
