"use client";

import { Check, Compass, Sparkles, Wrench, PlayCircle, Eye, Rocket, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { usePipelineStages } from "@/lib/queries/automation";
import type { PipelineStage, PipelineStageName } from "@/lib/api";

const STAGE_META: Record<PipelineStageName, { label: string; icon: typeof Check }> = {
  discover: { label: "Discover", icon: Compass },
  generate: { label: "Generate", icon: Sparkles },
  static: { label: "Static Gate", icon: Wrench },
  dry_run: { label: "Dry Run", icon: PlayCircle },
  review: { label: "Review", icon: Eye },
  ci_ready: { label: "CI Ready", icon: Rocket },
};

function formatAt(at: string | null): string {
  if (!at) return "";
  return new Date(at).toLocaleString();
}

/**
 * The real timeline behind a script's status — replaces the abstract,
 * status-only lifecycle stepper (which only ever showed "Approved" or
 * "Draft") with what actually happened at each stage and when, sourced
 * from ArtifactLineage/AgentRun, the script's own fields, ExecutionRun,
 * and ApprovalAction history. The first non-done stage is highlighted —
 * that's where the pipeline is stuck.
 */
export function PipelineStageRail({ scriptId }: { scriptId: number | null }) {
  const { data: stages, isLoading } = usePipelineStages(scriptId);

  if (!scriptId) return null;

  if (isLoading || !stages) {
    return (
      <div className="flex items-center gap-2 py-2 text-[11px] text-gray-400">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Loading pipeline…
      </div>
    );
  }

  const stuckIndex = stages.findIndex((s) => s.state !== "done");

  return (
    <div className="flex items-center gap-1 overflow-x-auto py-2">
      {stages.map((stage, idx) => {
        const meta = STAGE_META[stage.stage];
        const Icon = meta.icon;
        const isStuck = idx === stuckIndex;
        const tooltip = [meta.label, stage.detail, formatAt(stage.at)].filter(Boolean).join(" — ");
        return (
          <div key={stage.stage} className="flex items-center gap-1 shrink-0">
            <div
              title={tooltip}
              className={cn(
                "flex flex-col items-center gap-0.5 rounded-lg px-2.5 py-1 text-[11px] font-semibold transition",
                stage.state === "done" && "bg-emerald-50 text-emerald-700 border border-emerald-200",
                stage.state === "failed" && "bg-red-50 text-red-700 border border-red-200",
                stage.state === "pending" && "bg-gray-50 text-gray-500 border border-gray-200",
                isStuck && "ring-2 ring-offset-1 ring-violet-400",
              )}
            >
              <span className="flex items-center gap-1.5">
                {stage.state === "done" ? (
                  <Check className="h-3 w-3" />
                ) : stage.state === "failed" ? (
                  <X className="h-3 w-3" />
                ) : (
                  <Icon className="h-3 w-3" />
                )}
                {meta.label}
              </span>
              {stage.at && (
                <span className="text-[9px] font-normal text-gray-400">{formatAt(stage.at)}</span>
              )}
            </div>
            {idx < stages.length - 1 && (
              <div
                className={cn(
                  "h-px w-4 shrink-0",
                  stage.state === "done" ? "bg-emerald-300" : "bg-gray-200",
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

export type { PipelineStage };
