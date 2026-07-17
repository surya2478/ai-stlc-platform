"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Loader2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import type { StudioProposal, StudioRunDetail } from "@/lib/api";
import { useApproveStudioPlan } from "@/lib/queries/playwrightStudio";

function coverageVariant(coverage: string): "success" | "warning" | "outline" | "purple" {
  switch (coverage) {
    case "positive": return "success";
    case "negative": return "warning";
    case "e2e": return "purple";
    default: return "outline";
  }
}

/** Step 2 — Test Plan Review. The planner's proposals grouped by page, with
 * include/exclude toggles and ONE bulk approval action ("Approve Plan &
 * Generate Scripts") instead of per-test-case review cycles. */
export function PlanReview({
  projectId,
  run,
}: {
  projectId: number | null;
  run: StudioRunDetail;
}) {
  const { toast } = useToast();
  const approvePlan = useApproveStudioPlan(projectId);
  const proposals = useMemo(() => run.plan?.proposed_test_cases ?? [], [run.plan]);

  const [included, setIncluded] = useState<Set<string>>(new Set());
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [notes, setNotes] = useState("");

  useEffect(() => {
    // Default selection = everything the planner didn't flag as blocked.
    setIncluded(new Set(proposals.filter((p) => p.blocked_reasons.length === 0).map((p) => p.key)));
  }, [proposals]);

  const byPage = useMemo(() => {
    const groups: Array<{ pageUrl: string; items: StudioProposal[] }> = [];
    for (const proposal of proposals) {
      const key = proposal.page_url || "General";
      const existing = groups.find((g) => g.pageUrl === key);
      if (existing) existing.items.push(proposal);
      else groups.push({ pageUrl: key, items: [proposal] });
    }
    return groups;
  }, [proposals]);

  function toggle(key: string) {
    setIncluded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function handleApprove() {
    try {
      const result = await approvePlan.mutateAsync({
        runId: run.id,
        includedKeys: Array.from(included),
        notes: notes.trim() || undefined,
      });
      toast({ title: "Plan approved", description: result.message });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast({
        title: "Could not approve plan",
        description: typeof detail === "string" ? detail : "Unknown error",
        variant: "error",
      });
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 p-4 text-sm">
          <span className="font-semibold">AI Test Plan</span>
          <span className="text-muted-foreground">
            {run.plan?.explored_page_count ?? 0} page(s) explored · {proposals.length} test case(s) proposed
          </span>
          <Badge variant="info">{included.size} selected</Badge>
          {proposals.some((p) => p.blocked_reasons.length > 0) && (
            <Badge variant="warning">
              {proposals.filter((p) => p.blocked_reasons.length > 0).length} blocked (OTP/CAPTCHA)
            </Badge>
          )}
          {run.plan?.target_test_case_count != null && (
            <Badge variant="purple">
              Capped to your requested {run.plan.target_test_case_count}
              {run.plan.total_proposed_before_cap
                ? ` (from ${run.plan.total_proposed_before_cap} proposed across all pages)`
                : ""}
            </Badge>
          )}
        </CardContent>
      </Card>

      {byPage.map(({ pageUrl, items: pageProposals }) => (
        <Card key={pageUrl}>
          <CardContent className="p-4">
            <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
              <span className="font-semibold text-foreground">Page:</span>
              <span className="truncate">{pageUrl}</span>
            </div>
            <div className="divide-y divide-border/60">
              {pageProposals.map((proposal: StudioProposal) => {
                const isIncluded = included.has(proposal.key);
                const isExpanded = expandedKey === proposal.key;
                return (
                  <div key={proposal.key} className="py-2">
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={isIncluded}
                        onChange={() => toggle(proposal.key)}
                        className="mt-1 h-3.5 w-3.5 accent-violet-600"
                      />
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left"
                        onClick={() => setExpandedKey(isExpanded ? null : proposal.key)}
                      >
                        <span className="flex flex-wrap items-center gap-2">
                          <span className={cn("text-sm font-medium", !isIncluded && "text-muted-foreground line-through")}>
                            {proposal.title}
                          </span>
                          <Badge variant={coverageVariant(proposal.coverage_type)}>{proposal.coverage_type}</Badge>
                          <Badge variant="outline">{proposal.priority}</Badge>
                          {proposal.blocked_reasons.length > 0 && (
                            <Badge variant="warning">
                              <AlertTriangle className="mr-1 h-3 w-3" />
                              {proposal.blocked_reasons[0]}
                            </Badge>
                          )}
                          {proposal.ungrounded_elements.length > 0 && (
                            <Badge variant="outline">{proposal.ungrounded_elements.length} unmatched element(s)</Badge>
                          )}
                          {isExpanded
                            ? <ChevronDown className="h-3 w-3 text-muted-foreground" />
                            : <ChevronRight className="h-3 w-3 text-muted-foreground" />}
                        </span>
                      </button>
                    </div>
                    {isExpanded && (
                      <div className="ml-7 mt-2 rounded-md border border-border bg-muted/30 p-3 text-xs">
                        {proposal.preconditions.length > 0 && (
                          <p className="mb-2">
                            <span className="font-semibold">Preconditions:</span>{" "}
                            {proposal.preconditions.join("; ")}
                          </p>
                        )}
                        <ol className="list-decimal space-y-1 pl-4">
                          {proposal.steps.map((step: StudioProposal["steps"][number], i: number) => (
                            <li key={i}>
                              {step.description}
                              {step.element && (
                                <code className="ml-1 rounded bg-muted px-1 text-[10px]">{step.element}</code>
                              )}
                            </li>
                          ))}
                        </ol>
                        <p className="mt-2">
                          <span className="font-semibold">Expected:</span> {proposal.expected_result || "—"}
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      ))}

      <Card>
        <CardContent className="space-y-3 p-4">
          <label className="block text-xs font-medium text-muted-foreground">
            Bulk approval note (recorded on every test case&apos;s approval audit entry)
          </label>
          <input
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
            placeholder="Optional — e.g. Reviewed plan for SIT order-management sweep"
            value={notes}
            maxLength={2000}
            onChange={(e) => setNotes(e.target.value)}
          />
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              Approving materializes {included.size} approved test case(s) and queues script
              generation (contract → compiler → static gate → dry run) in waves.
            </p>
            <Button onClick={handleApprove} disabled={included.size === 0 || approvePlan.isPending}>
              {approvePlan.isPending
                ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                : <CheckCircle2 className="mr-2 h-4 w-4" />}
              Approve Plan & Generate Scripts
            </Button>
          </div>
        </CardContent>
      </Card>

      {included.size === 0 && proposals.length > 0 && (
        <p className="flex items-center gap-2 text-xs text-amber-600">
          <Sparkles className="h-3 w-3" /> Select at least one proposal to continue.
        </p>
      )}
    </div>
  );
}
