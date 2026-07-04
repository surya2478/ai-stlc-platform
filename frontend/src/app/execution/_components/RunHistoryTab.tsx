"use client";

import { useMemo, useState } from "react";
import type { ExecutionResult, ExecutionRun } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { RunsTable, runVerdict, type RunVerdict } from "./run-utils";
import { RunDetailDrawer } from "./RunDetailDrawer";
import { CreateDefectDialog, type DefectPrefill } from "./CreateDefectDialog";

const VERDICT_FILTERS: Array<{ key: RunVerdict | "all"; label: string }> = [
  { key: "all", label: "All" },
  { key: "passed", label: "Passed" },
  { key: "failed", label: "Failed" },
  { key: "in_progress", label: "In Progress" },
  { key: "review_required", label: "Review" },
  { key: "cancelled", label: "Cancelled" },
];

const DATE_FILTERS: Array<{ key: string; label: string; days: number | null }> = [
  { key: "all", label: "All time", days: null },
  { key: "7d", label: "Last 7 days", days: 7 },
  { key: "30d", label: "Last 30 days", days: 30 },
];

export function RunHistoryTab({
  runs,
  loading,
  projectId,
}: {
  runs: ExecutionRun[];
  loading: boolean;
  projectId: number;
}) {
  const [verdictFilter, setVerdictFilter] = useState<RunVerdict | "all">("all");
  const [dateFilter, setDateFilter] = useState("all");
  const [selectedRun, setSelectedRun] = useState<ExecutionRun | null>(null);
  const [defectPrefill, setDefectPrefill] = useState<DefectPrefill | null>(null);

  const filtered = useMemo(() => {
    const days = DATE_FILTERS.find((d) => d.key === dateFilter)?.days ?? null;
    const cutoff = days ? Date.now() - days * 86_400_000 : null;
    return runs.filter((r) => {
      if (verdictFilter !== "all" && runVerdict(r) !== verdictFilter) return false;
      if (cutoff) {
        const t = new Date(r.started_at ?? r.created_at ?? "").getTime();
        if (Number.isFinite(t) && t < cutoff) return false;
      }
      return true;
    });
  }, [runs, verdictFilter, dateFilter]);

  const openDefectDialog = (result: ExecutionResult) => {
    setDefectPrefill({
      summary: `Automation failure: ${result.test_name}`,
      description: `Failure detected in execution run ${selectedRun?.execution_id ?? result.execution_run_id} (${selectedRun?.environment ?? "unknown environment"}).`,
      actual_result: result.error_message ?? undefined,
      steps_to_reproduce: selectedRun
        ? [`Run automation suite "${selectedRun.suite_name ?? selectedRun.execution_id}" on ${selectedRun.environment ?? "target environment"}`]
        : [],
      severity: "High",
      test_case_id: result.test_case_id,
      execution_result_id: result.id,
    });
  };

  return (
    <>
      <Card>
        <CardContent className="p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-slate-800">Run history</h3>
              <p className="text-[11px] text-slate-500">
                Every automation run for this project, newest first. Click a run for logs,
                artifacts, and defect drafting.
              </p>
            </div>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
              {filtered.length} / {runs.length}
            </span>
          </div>

          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1">
              {VERDICT_FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setVerdictFilter(f.key)}
                  className={cn(
                    "rounded-md px-2 py-1 text-[11px] font-medium transition",
                    verdictFilter === f.key
                      ? "bg-slate-900 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200",
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <select
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
              className="ml-auto rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-100"
            >
              {DATE_FILTERS.map((d) => (
                <option key={d.key} value={d.key}>{d.label}</option>
              ))}
            </select>
          </div>

          <RunsTable
            runs={filtered}
            loading={loading}
            emptyMessage={runs.length === 0 ? "No runs yet." : "No runs match the current filters."}
            onRowClick={setSelectedRun}
          />
        </CardContent>
      </Card>

      <RunDetailDrawer
        runId={selectedRun?.id ?? null}
        open={selectedRun !== null}
        onOpenChange={(o) => { if (!o) setSelectedRun(null); }}
        initialRun={selectedRun}
        onCreateDefect={openDefectDialog}
      />

      <CreateDefectDialog
        open={defectPrefill !== null}
        onClose={() => setDefectPrefill(null)}
        projectId={projectId}
        prefill={defectPrefill ?? undefined}
      />
    </>
  );
}
