"use client";

import { useState } from "react";
import { Loader2, ShieldCheck, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ExecutionRun } from "@/lib/api";
import {
  useAiGovernance,
  useAiRunDetail,
  useFinalizeAiRun,
  useSubmitAiReview,
} from "@/lib/queries/execution";
import { useToast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";
import { formatDate } from "./run-utils";

type Decision = "approve" | "override" | "request_rerun" | "reject";

const DECISIONS: Array<{ key: Decision; label: string; tone: string }> = [
  { key: "approve", label: "Approve", tone: "bg-emerald-600 hover:bg-emerald-700 text-white" },
  { key: "override", label: "Override status", tone: "bg-amber-600 hover:bg-amber-700 text-white" },
  { key: "request_rerun", label: "Request re-run", tone: "bg-blue-600 hover:bg-blue-700 text-white" },
  { key: "reject", label: "Reject", tone: "bg-red-600 hover:bg-red-700 text-white" },
];

const OVERRIDE_STATUSES = ["completed", "failed", "auto_completed", "cancelled"] as const;

/**
 * Human review controls for an AI-assisted run stuck in `review_required`.
 * Shows the governance thresholds that triggered the review, the prior
 * review log, and submits an audited decision.
 */
export function AiReviewPanel({
  run,
  onDecided,
}: {
  run: ExecutionRun;
  onDecided?: () => void;
}) {
  const { toast } = useToast();
  const detailQuery = useAiRunDetail(run.id);
  const governanceQuery = useAiGovernance();
  const submitReview = useSubmitAiReview(run.id);
  const finalize = useFinalizeAiRun(run.id);

  const [decision, setDecision] = useState<Decision>("approve");
  const [reason, setReason] = useState("");
  const [overrideStatus, setOverrideStatus] =
    useState<(typeof OVERRIDE_STATUSES)[number]>("completed");

  const governance = detailQuery.data?.governance ?? governanceQuery.data;
  const reviewLog = detailQuery.data?.review_log ?? [];

  const submit = async () => {
    if (!reason.trim()) {
      toast({ title: "A reason is required for the audit log", variant: "warning" });
      return;
    }
    try {
      await submitReview.mutateAsync({
        decision,
        reason: reason.trim(),
        override_status: decision === "override" ? overrideStatus : undefined,
      });
      toast({
        title: `Review submitted: ${decision.replace(/_/g, " ")}`,
        variant: "success",
      });
      setReason("");
      onDecided?.();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({
        title: "Review submission failed",
        description: err?.response?.data?.detail ?? err?.message,
        variant: "error",
      });
    }
  };

  const runFinalize = async () => {
    try {
      const updated = await finalize.mutateAsync();
      toast({
        title: `Completion rule re-evaluated: ${updated.status.replace(/_/g, " ")}`,
        variant: "success",
      });
      onDecided?.();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({
        title: "Finalize failed",
        description: err?.response?.data?.detail ?? err?.message,
        variant: "error",
      });
    }
  };

  return (
    <div className="space-y-4 rounded-lg border border-violet-200 bg-violet-50/40 p-4">
      <div className="flex items-center gap-2 text-xs font-bold text-violet-800">
        <Sparkles className="h-3.5 w-3.5" /> Human review required
      </div>

      {governance && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-violet-800">
          <span className="inline-flex items-center gap-1">
            <ShieldCheck className="h-3 w-3" />
            Confidence threshold: <b>{governance.ai_confidence_threshold}%</b>
          </span>
          <span>
            Autonomous envs: <b>{governance.ai_autonomous_environments.join(", ") || "none"}</b>
          </span>
          <span>
            Evidence required for pass: <b>{governance.ai_require_evidence_for_pass ? "yes" : "no"}</b>
          </span>
          {run.confidence_score !== null && run.confidence_score !== undefined && (
            <span>
              This run&apos;s confidence: <b>{Math.round(run.confidence_score)}%</b>
            </span>
          )}
        </div>
      )}

      {reviewLog.length > 0 && (
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-violet-700">
            Review log
          </p>
          <ul className="space-y-1">
            {reviewLog.map((entry, i) => (
              <li key={i} className="rounded-md border border-violet-100 bg-white px-2.5 py-1.5 text-[11px] text-slate-600">
                <span className="font-semibold capitalize text-slate-800">
                  {entry.decision.replace(/_/g, " ")}
                </span>
                {" — "}{entry.reason}
                <span className="ml-2 text-slate-400">{formatDate(entry.ts)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-2">
        <div className="flex flex-wrap gap-1.5">
          {DECISIONS.map((d) => (
            <button
              key={d.key}
              type="button"
              onClick={() => setDecision(d.key)}
              className={cn(
                "rounded-md px-2.5 py-1 text-[11px] font-semibold transition",
                decision === d.key
                  ? d.tone
                  : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
              )}
            >
              {d.label}
            </button>
          ))}
        </div>

        {decision === "override" && (
          <select
            value={overrideStatus}
            onChange={(e) => setOverrideStatus(e.target.value as (typeof OVERRIDE_STATUSES)[number])}
            className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs capitalize focus:outline-none focus:ring-2 focus:ring-violet-100"
          >
            {OVERRIDE_STATUSES.map((s) => (
              <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
            ))}
          </select>
        )}

        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          placeholder="Reason (recorded in the audit trail)…"
          className="w-full rounded-md border border-slate-200 px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-violet-100"
        />

        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            size="sm"
            onClick={runFinalize}
            disabled={finalize.isPending}
            className="gap-1.5 text-xs"
            title="Re-run the AI completion rule against current thresholds"
          >
            {finalize.isPending && <Loader2 className="h-3 w-3 animate-spin" />}
            Re-evaluate rule
          </Button>
          <Button size="sm" onClick={submit} disabled={submitReview.isPending} className="gap-1.5 text-xs">
            {submitReview.isPending && <Loader2 className="h-3 w-3 animate-spin" />}
            Submit decision
          </Button>
        </div>
      </div>
    </div>
  );
}
