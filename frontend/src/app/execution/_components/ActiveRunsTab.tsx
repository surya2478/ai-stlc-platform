"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, Radio } from "lucide-react";
import type { ExecutionRun } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RunsTable, isAiAssistedRun } from "./run-utils";
import { RunDetailDrawer } from "./RunDetailDrawer";
import { AiReviewPanel } from "./AiReviewPanel";
import { DrawerFooter } from "@/components/ui/drawer";

const QUEUED_STALL_MS = 60_000;

/**
 * In-flight runs, refreshed by the useRuns polling hook upstream. Runs in
 * `review_required` are surfaced here too — they block on a human decision,
 * which makes them "active" from the tester's point of view.
 */
export function ActiveRunsTab({
  runs,
  loading,
  isPolling,
}: {
  runs: ExecutionRun[];
  loading: boolean;
  isPolling: boolean;
}) {
  const [selectedRun, setSelectedRun] = useState<ExecutionRun | null>(null);

  // A run stuck in queued/pending for over a minute usually means the Celery
  // worker or Redis is down — surface that instead of an endless spinner.
  const stalled = useMemo(() => {
    const now = Date.now();
    return runs.filter((r) => {
      const s = (r.status ?? "").toLowerCase();
      if (s !== "queued" && s !== "pending") return false;
      const created = new Date(r.created_at).getTime();
      return Number.isFinite(created) && now - created > QUEUED_STALL_MS;
    });
  }, [runs]);

  const reviewRequired = (run: ExecutionRun | null) =>
    Boolean(run && (run.status ?? "").toLowerCase() === "review_required" && isAiAssistedRun(run));

  return (
    <>
      <Card>
        <CardContent className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                Active runs
                {isPolling && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 ring-1 ring-emerald-100">
                    <Radio className="h-2.5 w-2.5 animate-pulse" /> Live
                  </span>
                )}
              </h3>
              <p className="text-[11px] text-slate-500">
                Queued, in-flight, and review-blocked runs. Updates automatically while runs are active.
              </p>
            </div>
            <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-[#1b59f8]">
              {runs.length}
            </span>
          </div>

          {stalled.length > 0 && (
            <div className="mb-3 flex items-start gap-2 rounded-md border border-orange-200 bg-orange-50 p-2.5 text-[11px] text-orange-700">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                {stalled.length} run{stalled.length > 1 ? "s have" : " has"} been queued for over a
                minute — the Celery worker or Redis may be offline. Check the backend worker before
                triggering more runs.
              </span>
            </div>
          )}

          <RunsTable
            runs={runs}
            loading={loading}
            emptyMessage="No active runs. Trigger one from Run Builder to see it here."
            onRowClick={setSelectedRun}
            rowAction={(r) =>
              reviewRequired(r) ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-6 px-2 text-[10px] text-violet-700 border-violet-200 hover:bg-violet-50"
                  onClick={() => setSelectedRun(r)}
                >
                  Review
                </Button>
              ) : null
            }
          />
        </CardContent>
      </Card>

      <RunDetailDrawer
        runId={selectedRun?.id ?? null}
        open={selectedRun !== null}
        onOpenChange={(o) => { if (!o) setSelectedRun(null); }}
        initialRun={selectedRun}
        footer={
          reviewRequired(selectedRun) && selectedRun ? (
            <DrawerFooter className="block bg-white">
              <AiReviewPanel run={selectedRun} onDecided={() => setSelectedRun(null)} />
            </DrawerFooter>
          ) : undefined
        }
      />
    </>
  );
}
