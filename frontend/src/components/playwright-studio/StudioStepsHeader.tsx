"use client";

import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { STUDIO_STEPS, type StudioStepIndex } from "./studio-utils";

/** The 5-step pipeline rail across the top of the Studio (mirrors the
 * Planner Input → … → Artifacts & Audit mockup). Purely presentational —
 * the current step derives from the run status. */
export function StudioStepsHeader({ currentStep }: { currentStep: StudioStepIndex }) {
  return (
    <div className="flex flex-wrap items-stretch gap-2">
      {STUDIO_STEPS.map((step, i) => {
        const state =
          step.index === currentStep ? "active" : step.index < currentStep ? "done" : "todo";
        return (
          <div key={step.index} className="flex items-center gap-2">
            <div
              className={cn(
                "flex min-w-[180px] items-center gap-3 rounded-lg border px-3 py-2",
                state === "active" && "border-violet-600 bg-violet-600 text-white shadow-sm",
                state === "done" && "border-violet-200 bg-violet-50 text-violet-900",
                state === "todo" && "border-border bg-card text-muted-foreground",
              )}
            >
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                  state === "active" && "bg-white text-violet-700",
                  state === "done" && "bg-violet-600 text-white",
                  state === "todo" && "bg-muted text-muted-foreground",
                )}
              >
                {step.index}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-xs font-semibold">{step.title}</span>
                <span
                  className={cn(
                    "block truncate text-[10px]",
                    state === "active" ? "text-violet-100" : "text-muted-foreground",
                  )}
                >
                  {step.subtitle}
                </span>
              </span>
            </div>
            {i < STUDIO_STEPS.length - 1 && (
              <ChevronRight className="hidden h-4 w-4 shrink-0 text-muted-foreground md:block" />
            )}
          </div>
        );
      })}
    </div>
  );
}
