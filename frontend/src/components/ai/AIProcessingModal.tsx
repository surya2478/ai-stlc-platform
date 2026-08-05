"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import {
  AlertTriangle,
  Ban,
  Bot,
  CheckCircle2,
  Clock3,
  Loader2,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AIProcessingContext } from "@/types/ai-processing";

const ACTIVE_STATUSES = new Set(["queued", "processing", "waiting"]);

function formatElapsed(seconds = 0) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remaining = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remaining}`;
}

function statusPresentation(status: AIProcessingContext["status"]) {
  if (status === "success") {
    return { label: "Completed", title: "AI Processing Completed", tone: "emerald" as const, Icon: CheckCircle2 };
  }
  if (status === "blocked") {
    return { label: "Blocked", title: "AI Action Blocked", tone: "amber" as const, Icon: Ban };
  }
  if (status === "timeout") {
    return { label: "Timed Out", title: "AI Processing Timed Out", tone: "red" as const, Icon: Clock3 };
  }
  if (status === "cancelled") {
    return { label: "Cancelled", title: "AI Processing Cancelled", tone: "slate" as const, Icon: X };
  }
  if (status === "error") {
    return { label: "Unable to Complete", title: "Unable to Complete AI Processing", tone: "red" as const, Icon: AlertTriangle };
  }
  return { label: "eNexus AI Processing", title: "AI is Working", tone: "violet" as const, Icon: Bot };
}

function fallbackStage(context: AIProcessingContext) {
  if (context.currentStage) return context.currentStage;
  if (!context.stages?.length) return context.status === "queued" ? "Request queued" : "Processing the requested operation";
  const elapsedIndex = Math.floor((context.elapsedTimeSeconds ?? 0) / 8);
  const index = context.stageIndex ?? Math.min(elapsedIndex, context.stages.length - 1);
  return context.stages[Math.max(0, index)]?.label;
}

export function AIProcessingModal({
  context,
  onClose,
  onRetry,
}: {
  context: AIProcessingContext;
  onClose: () => void;
  onRetry: () => void;
}) {
  const active = ACTIVE_STATUSES.has(context.status);
  const presentation = statusPresentation(context.status);
  const stage = fallbackStage(context);
  const toneClasses = {
    violet: "border-violet-200 bg-violet-50 text-violet-700",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
    amber: "border-amber-200 bg-amber-50 text-amber-700",
    red: "border-red-200 bg-red-50 text-red-700",
    slate: "border-gray-200 bg-gray-50 text-gray-600",
  };
  const labelToneClasses = {
    violet: "text-violet-600",
    emerald: "text-emerald-600",
    amber: "text-amber-600",
    red: "text-red-600",
    slate: "text-gray-600",
  };
  const message =
    context.status === "success"
      ? context.successMessage || `${context.actionLabel || context.title} completed successfully.`
      : context.status === "blocked"
        ? context.blockerReason || "This action is blocked by a readiness, policy, or permission requirement."
        : context.status === "timeout"
          ? context.errorMessage || "The request did not complete within the expected time."
          : context.status === "error"
            ? context.errorMessage || "eNexus could not complete this request. Review the details below and retry when ready."
            : "eNexus is analyzing the selected inputs and preparing the requested result. Please keep this page open while processing continues.";

  return (
    <DialogPrimitive.Root open={context.isOpen} onOpenChange={(open) => { if (!open && !active) onClose(); }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-[90] bg-gray-950/45 backdrop-blur-[2px] data-[state=open]:animate-in data-[state=open]:fade-in-0 motion-reduce:animate-none" />
        <DialogPrimitive.Content
          aria-describedby="ai-processing-description"
          onEscapeKeyDown={(event) => { if (active) event.preventDefault(); }}
          onPointerDownOutside={(event) => event.preventDefault()}
          className="fixed left-1/2 top-1/2 z-[91] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-gray-200 bg-white shadow-2xl focus:outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 motion-reduce:animate-none"
        >
          <div className="p-6">
            <div className="relative flex justify-center">
              <div className={cn("flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border", toneClasses[presentation.tone])}>
                {active ? (
                  <div className="relative">
                    <Loader2 className="h-6 w-6 animate-spin motion-reduce:animate-none" />
                    <Sparkles className="absolute -right-2 -top-2 h-3.5 w-3.5" />
                  </div>
                ) : (
                  <presentation.Icon className="h-6 w-6" />
                )}
              </div>
              {!active && (
                <button aria-label="Close AI processing" onClick={onClose} className="absolute right-0 top-0 rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700">
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>

            <div className="text-center">
              <p className={cn("mt-5 text-[10px] font-extrabold uppercase tracking-[0.18em]", labelToneClasses[presentation.tone])}>
                {presentation.label}
              </p>
              <DialogPrimitive.Title className="mt-1 text-xl font-extrabold tracking-tight text-gray-950">
                {active ? "AI is Working" : presentation.title}
              </DialogPrimitive.Title>
              <p className="mt-2 text-sm font-bold text-gray-800">{context.title}</p>
              <DialogPrimitive.Description id="ai-processing-description" className="mt-2 text-xs font-medium leading-5 text-gray-500">
                {message}
              </DialogPrimitive.Description>
            </div>

            {active && (
              <div className="mt-5 overflow-hidden rounded-xl border border-violet-100 bg-violet-50/50">
                <div className="h-1 overflow-hidden bg-violet-100">
                  <div className="h-full w-1/3 animate-[ai-processing-slide_1.4s_ease-in-out_infinite] rounded-full bg-violet-500 motion-reduce:w-full motion-reduce:animate-none" />
                </div>
                <div className="p-4">
                  <p className="text-[10px] font-extrabold uppercase tracking-wide text-violet-600">Current stage</p>
                  <p aria-live="polite" className="mt-1 text-xs font-bold leading-5 text-gray-800">{stage}</p>
                  <div className="mt-4 flex items-center justify-between border-t border-violet-100 pt-3 text-[11px] font-semibold text-gray-500">
                    <span className="flex items-center gap-1.5"><Clock3 className="h-3.5 w-3.5" />Elapsed {formatElapsed(context.elapsedTimeSeconds)}</span>
                    <span className="rounded-full border border-violet-200 bg-white px-2 py-1 text-violet-700">
                      {context.status === "queued" ? "Queued" : context.status === "waiting" ? "Waiting for agent" : "Processing"}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {(context.errorCategory ||
              context.projectId ||
              context.requirementId ||
              context.testCaseId ||
              context.applicationId ||
              context.environmentId ||
              context.requestId ||
              context.jobId ||
              context.agentRunId ||
              context.correlationId) && (
              <div className="mt-4 grid [grid-template-columns:repeat(auto-fit,minmax(7rem,1fr))] gap-2 rounded-xl border border-gray-200 bg-gray-50 p-3 text-[10px]">
                {context.errorCategory && <Meta label="Category" value={context.errorCategory} />}
                {context.projectId && <Meta label="Project" value={String(context.projectId)} />}
                {context.requirementId && <Meta label="Requirement" value={String(context.requirementId)} />}
                {context.testCaseId && <Meta label="Test Case" value={String(context.testCaseId)} />}
                {context.applicationId && <Meta label="Application" value={String(context.applicationId)} />}
                {context.environmentId && <Meta label="Environment" value={String(context.environmentId)} />}
                {context.requestId && <Meta label="Request ID" value={context.requestId} />}
                {context.jobId && <Meta label="Job ID" value={context.jobId} />}
                {context.agentRunId && <Meta label="AgentRun ID" value={context.agentRunId} />}
                {context.correlationId && <Meta label="Correlation ID" value={context.correlationId} />}
              </div>
            )}

            {!active && context.status !== "success" && (
              <div className="mt-5 flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={onClose}>Close</Button>
                {context.canRetry && (
                  <Button size="sm" onClick={onRetry} className="gap-2 bg-[#B71920] text-white hover:bg-[#941216]">
                    <RefreshCw className="h-3.5 w-3.5" />Retry
                  </Button>
                )}
              </div>
            )}
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 text-center">
      <span className="block font-bold uppercase tracking-wide text-gray-400">{label}</span>
      <span className="mt-0.5 block truncate font-mono font-semibold text-gray-700">{value}</span>
    </div>
  );
}
