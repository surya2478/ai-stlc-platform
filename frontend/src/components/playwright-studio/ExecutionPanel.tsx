"use client";

import { Container, Loader2, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { StudioRunDetail } from "@/lib/api";
import { FailureInsights } from "./FailureInsights";
import { runnerIsContainerised, runnerModeLabel } from "./studio-utils";

function executionStatusVariant(status: string): "success" | "warning" | "destructive" | "outline" {
  if (status === "completed") return "success";
  if (status === "failed") return "destructive";
  if (["running", "queued", "pending"].includes(status)) return "warning";
  return "outline";
}

/** Step 4 — Execution & Healing. Live progress of the batch ExecutionRun(s);
 * failures are auto-classified, and repair happens through the existing
 * classification → repair chain (visible per-result in the Execution pages). */
export function ExecutionPanel({ run }: { run: StudioRunDetail }) {
  const totals = run.executions.reduce(
    (acc, execution) => ({
      total: acc.total + execution.total_tests,
      passed: acc.passed + execution.passed,
      failed: acc.failed + execution.failed,
      skipped: acc.skipped + execution.skipped,
    }),
    { total: 0, passed: 0, failed: 0, skipped: 0 },
  );
  const done = totals.passed + totals.failed + totals.skipped;
  const progress = totals.total > 0 ? Math.round((done / totals.total) * 100) : 0;
  const containerised = runnerIsContainerised(run.config.runner_mode);

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="font-semibold">Execution Progress</span>
            {containerised ? (
              <Badge variant="purple">
                <Container className="mr-1 h-3 w-3" />
                {runnerModeLabel(run.config.runner_mode)} · up to {run.config.parallelism ?? 1} parallel containers
              </Badge>
            ) : (
              <Badge variant="outline">{runnerModeLabel(run.config.runner_mode)} runner</Badge>
            )}
            <Badge variant="outline">{run.config.environment}</Badge>
            {run.status === "executing" && <Loader2 className="h-4 w-4 animate-spin text-violet-600" />}
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-violet-600 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span>{done}/{totals.total} finished ({progress}%)</span>
            <span className="text-emerald-600">{totals.passed} passed</span>
            <span className="text-red-600">{totals.failed} failed</span>
            <span>{totals.skipped} skipped</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-border text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Batch Run</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Tests</th>
                <th className="px-3 py-2 font-medium">Passed</th>
                <th className="px-3 py-2 font-medium">Failed</th>
                <th className="px-3 py-2 font-medium">Skipped</th>
              </tr>
            </thead>
            <tbody>
              {run.executions.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                    Waiting for execution batches to be created…
                  </td>
                </tr>
              )}
              {run.executions.map((execution) => (
                <tr key={execution.id} className="border-b border-border/60 last:border-0">
                  <td className="px-3 py-2 font-medium">{execution.execution_id}</td>
                  <td className="px-3 py-2">
                    <Badge variant={executionStatusVariant(execution.status)}>{execution.status}</Badge>
                  </td>
                  <td className="px-3 py-2">{execution.total_tests}</td>
                  <td className="px-3 py-2 text-emerald-600">{execution.passed}</td>
                  <td className="px-3 py-2 text-red-600">{execution.failed}</td>
                  <td className="px-3 py-2">{execution.skipped}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <FailureInsights insights={run.failure_insights ?? []} />

      {run.executions.some((e) => e.auto_heal) && (
        <Card>
          <CardContent className="space-y-2 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Wrench className="h-4 w-4 text-violet-600" /> Auto-Heal Results
            </div>
            {run.executions.filter((e) => e.auto_heal).map((execution) => {
              const heal = execution.auto_heal!;
              return (
                <div key={execution.id} className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-medium">{execution.execution_id}:</span>
                  <Badge variant={heal.repaired > 0 ? "success" : "outline"}>
                    {heal.repaired}/{heal.attempted} healed
                  </Badge>
                  {heal.not_repairable > 0 && (
                    <Badge variant="warning">{heal.not_repairable} not auto-repairable</Badge>
                  )}
                  {heal.errors > 0 && <Badge variant="destructive">{heal.errors} heal error(s)</Badge>}
                  {heal.new_script_ids.length > 0 && (
                    <span className="text-muted-foreground">
                      {heal.new_script_ids.length} fixed script version(s) created — approve them and
                      start a new run to re-execute.
                    </span>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="flex items-start gap-2 p-4 text-xs text-muted-foreground">
          <Wrench className="mt-0.5 h-4 w-4 shrink-0 text-violet-600" />
          <span>
            When a batch finishes, every failure is classified (app defect / locator issue / data /
            environment / API / timeout), and Studio batches then <b>auto-heal</b>: each repairable
            failure (locator/timeout) gets a contract patch → compile → static gate → dry run cycle,
            persisting fixed scripts as new versions with full rollback history. Non-repairable
            classes (real defects, test data, environment) are routed to you — no LLM can fix a
            wrong password. Per-result detail lives in{" "}
            <a
              className="text-violet-600 underline"
              href={`/execution/automation?project=${run.project_id}`}
            >
              Automation Execution
            </a>.
          </span>
        </CardContent>
      </Card>
    </div>
  );
}
