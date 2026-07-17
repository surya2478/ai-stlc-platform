"use client";

import { CheckCircle2, ExternalLink, FileText, ShieldCheck, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { StudioRunDetail } from "@/lib/api";
import { FailureInsights } from "./FailureInsights";

/** Step 5 — Artifacts & Audit. Merged outcome stats, links into the
 * execution pages for artifacts (logs/screenshots/traces per result), and
 * the bulk-approval audit summary. */
export function ArtifactsAudit({ run }: { run: StudioRunDetail }) {
  const totals = run.executions.reduce(
    (acc, execution) => ({
      total: acc.total + execution.total_tests,
      passed: acc.passed + execution.passed,
      failed: acc.failed + execution.failed,
      skipped: acc.skipped + execution.skipped,
    }),
    { total: 0, passed: 0, failed: 0, skipped: 0 },
  );
  const passRate = totals.total > 0 ? Math.round((totals.passed / totals.total) * 100) : 0;
  const approvedKeys = run.plan?.approved_keys ?? [];
  const healed = run.executions.reduce((acc, e) => acc + (e.auto_heal?.repaired ?? 0), 0);
  const healAttempted = run.executions.reduce((acc, e) => acc + (e.auto_heal?.attempted ?? 0), 0);

  const stats: Array<{ label: string; value: string; tone?: "good" | "bad" }> = [
    { label: "Pages explored", value: String(run.plan?.explored_page_count ?? 0) },
    { label: "Test cases created", value: String(run.test_case_ids?.length ?? approvedKeys.length) },
    { label: "Scripts generated", value: String(run.scripts.length) },
    { label: "Tests executed", value: String(totals.total) },
    { label: "Pass rate", value: `${passRate}%`, tone: passRate >= 80 ? "good" : "bad" },
    { label: "Failures", value: String(totals.failed), tone: totals.failed === 0 ? "good" : "bad" },
    { label: "Auto-healed", value: healAttempted > 0 ? `${healed}/${healAttempted}` : "—", tone: healed > 0 ? "good" : undefined },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-7">
        {stats.map((stat) => (
          <Card key={stat.label}>
            <CardContent className="p-3">
              <p className="text-[11px] text-muted-foreground">{stat.label}</p>
              <p
                className={
                  stat.tone === "good"
                    ? "text-lg font-semibold text-emerald-600"
                    : stat.tone === "bad"
                      ? "text-lg font-semibold text-red-600"
                      : "text-lg font-semibold"
                }
              >
                {stat.value}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <FailureInsights insights={run.failure_insights ?? []} />

      <Card>
        <CardContent className="space-y-2 p-4 text-sm">
          <div className="flex items-center gap-2 font-semibold">
            <FileText className="h-4 w-4 text-violet-600" /> Artifacts
          </div>
          <p className="text-xs text-muted-foreground">
            Per-test logs, screenshots, videos, and Playwright traces are attached to each
            execution result. Open a batch run to browse and download them:
          </p>
          <ul className="space-y-1 text-xs">
            {run.executions.map((execution) => (
              <li key={execution.id}>
                <a
                  className="inline-flex items-center gap-1 text-violet-600 underline"
                  href={`/execution/automation?project=${run.project_id}`}
                >
                  {execution.execution_id} — {execution.passed}/{execution.total_tests} passed
                  <ExternalLink className="h-3 w-3" />
                </a>
              </li>
            ))}
            {run.executions.length === 0 && <li className="text-muted-foreground">No executions were run.</li>}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-2 p-4 text-sm">
          <div className="flex items-center gap-2 font-semibold">
            <ShieldCheck className="h-4 w-4 text-violet-600" /> Audit Trail
          </div>
          <ul className="space-y-1.5 text-xs text-muted-foreground">
            <li className="flex items-center gap-2">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
              Planner exploration grounded {run.plan?.explored_page_count ?? 0} page(s) into the locator map
              (agent run #{run.agent_runs.planner?.id ?? "—"}).
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
              Bulk plan approval created {run.test_case_ids?.length ?? 0} approved test case(s), each with its own
              ApprovalAction audit row.
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
              Bulk script approval recorded one audit entry per script; scripts with known issues required an
              override note.
            </li>
            {healAttempted > 0 && (
              <li className="flex items-center gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                Auto-heal repaired {healed} of {healAttempted} failed test(s); fixed scripts were
                persisted as new versions (approve them and start a new run to re-execute).
              </li>
            )}
            <li className="flex items-center gap-2">
              {run.status === "completed" ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
              ) : (
                <XCircle className="h-3.5 w-3.5 text-red-500" />
              )}
              Run finished with status “{run.status}”
              {run.error ? ` — ${run.error}` : ""}.
            </li>
          </ul>
          <p className="pt-1 text-[11px] text-muted-foreground">
            Test cases, scripts, coverage matrix, and traceability created by this run are first-class
            artifacts — they appear in Test Cases, AI Automation Studio, and the Coverage Matrix like
            any other, tagged with origin “playwright_studio”.
          </p>
        </CardContent>
      </Card>

      {run.status === "failed" && run.error && (
        <Card>
          <CardContent className="p-4 text-sm text-red-600">
            <Badge variant="destructive" className="mb-2">Run failed</Badge>
            <p className="text-xs">{run.error}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
