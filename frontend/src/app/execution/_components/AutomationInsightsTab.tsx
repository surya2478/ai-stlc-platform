"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Radar, RefreshCw, Sparkles, TrendingUp } from "lucide-react";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { cn } from "@/lib/utils";
import {
  automationApi,
  type AutomationPlanning,
  type AutomationScript,
  type AutomationTestMapping,
  type ExecutionRun,
} from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { buildHref } from "./execution-shared";
import { RunDetailDrawer } from "./RunDetailDrawer";
import { RunVerdictBadge, formatDate, formatDuration, runVerdict } from "./run-utils";

const TREND_DAYS = 14;
const FLAKY_CANDIDATE_LIMIT = 15;
const FLAKY_WINDOW = 6;

type PassOrFail = "pass" | "fail" | null;

function normalizeResultStatus(status: string | null | undefined): PassOrFail {
  const s = (status ?? "").toLowerCase();
  if (["pass", "passed"].includes(s)) return "pass";
  if (["fail", "failed", "error"].includes(s)) return "fail";
  return null;
}

export function AutomationInsightsTab({
  projectId,
  environment,
  runs,
  mappings,
  planning,
  scripts,
  defectsToday,
  lastLoadedAt,
}: {
  projectId: string;
  environment: string;
  runs: ExecutionRun[];
  mappings: AutomationTestMapping[];
  planning: AutomationPlanning | null;
  scripts: AutomationScript[];
  defectsToday: number;
  lastLoadedAt: Date | null;
}) {
  const [selectedRun, setSelectedRun] = useState<ExecutionRun | null>(null);

  const totals = useMemo(() => {
    const total = runs.length;
    const passed = runs.filter((r) => runVerdict(r) === "passed").length;
    const failed = runs.filter((r) => runVerdict(r) === "failed").length;
    const inProgress = runs.filter((r) => runVerdict(r) === "in_progress").length;
    const today = new Date().toISOString().slice(0, 10);
    const executedToday = runs.filter((r) => (r.started_at ?? r.created_at ?? "").slice(0, 10) === today).length;
    const pct = (n: number) => (total > 0 ? Math.round((n / total) * 1000) / 10 : 0);
    return { total, passed, failed, inProgress, executedToday, passedPct: pct(passed), failedPct: pct(failed), inProgressPct: pct(inProgress) };
  }, [runs]);

  // Automation coverage: approved scripts vs eligible candidates.
  const coverage = useMemo(() => {
    const eligible = planning?.summary.total_candidates ?? 0;
    const approved = scripts.filter((s) => ["approved", "executed"].includes((s.status ?? "").toLowerCase())).length;
    const pct = eligible > 0 ? Math.round((Math.min(approved, eligible) / eligible) * 100) : null;
    return { eligible, approved, pct };
  }, [planning, scripts]);

  // Test-level pass-rate trend for the last TREND_DAYS days.
  const trend = useMemo(() => {
    const byDay = new Map<string, { passed: number; failed: number }>();
    const cutoff = Date.now() - TREND_DAYS * 86_400_000;
    for (const run of runs) {
      const iso = run.started_at ?? run.created_at ?? "";
      const t = new Date(iso).getTime();
      if (!Number.isFinite(t) || t < cutoff) continue;
      // Bucket by full ISO date so sorting stays correct across a year
      // boundary (MM-DD alone would put late Dec after early Jan).
      const day = iso.slice(0, 10);
      const bucket = byDay.get(day) ?? { passed: 0, failed: 0 };
      bucket.passed += run.passed ?? 0;
      bucket.failed += run.failed ?? 0;
      byDay.set(day, bucket);
    }
    return Array.from(byDay.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, { passed, failed }]) => ({
        day: day.slice(5), // display as MM-DD
        passRate: passed + failed > 0 ? Math.round((passed / (passed + failed)) * 100) : null,
        runsTests: passed + failed,
      }))
      .filter((d) => d.passRate !== null);
  }, [runs]);

  // Client-side flaky detection: candidates whose recent execution history
  // alternates pass/fail. Bounded to the first FLAKY_CANDIDATE_LIMIT
  // candidates with scripts to keep the fan-out cheap.
  const flakyCandidates = useMemo(
    () => (planning?.candidates ?? []).filter((c) => c.script_id != null).slice(0, FLAKY_CANDIDATE_LIMIT),
    [planning],
  );
  const flakyQuery = useQuery({
    queryKey: ["automation", "flaky", projectId, flakyCandidates.map((c) => c.test_case_id)],
    enabled: flakyCandidates.length > 0,
    staleTime: 5 * 60_000,
    queryFn: async () => {
      const entries = await Promise.all(
        flakyCandidates.map(async (c) => {
          try {
            const history = (await automationApi.getExecutionHistory(c.test_case_id)).data;
            const sequence = history
              .slice(0, FLAKY_WINDOW)
              .map((r) => normalizeResultStatus(r.status))
              .filter((s): s is Exclude<PassOrFail, null> => s !== null);
            let transitions = 0;
            for (let i = 1; i < sequence.length; i++) {
              if (sequence[i] !== sequence[i - 1]) transitions += 1;
            }
            return {
              testCaseKey: c.test_case_key,
              title: c.title,
              sequence,
              transitions,
              flaky: sequence.length >= 3 && transitions >= 2,
            };
          } catch {
            return null;
          }
        }),
      );
      return entries.filter((e): e is NonNullable<typeof e> => e !== null);
    },
  });
  const flakyTests = (flakyQuery.data ?? []).filter((e) => e.flaky);

  // AI insight (computed from data, not hardcoded)
  const aiInsight = useMemo(() => {
    const byFramework = (fw: string) =>
      runs.filter(
        (r) =>
          (r.suite_name ?? "").toLowerCase().includes(fw) ||
          (r.metadata_ as { framework?: string } | null)?.framework === fw,
      );
    const passOf = (rs: ExecutionRun[]) => {
      const ok = rs.filter((r) => runVerdict(r) === "passed").length;
      return rs.length > 0 ? Math.round((ok / rs.length) * 100) : null;
    };
    const pwRate = passOf(byFramework("playwright"));
    const pyRate = passOf(byFramework("pytest"));
    if (pwRate != null && pyRate != null && pyRate > pwRate) {
      return `Pytest scripts show ${pyRate - pwRate}% higher stability in ${environment}. Consider migrating similar Playwright tests for better reliability.`;
    }
    if (pwRate != null && pyRate != null && pwRate > pyRate) {
      return `Playwright scripts are running ${pwRate - pyRate}% more reliably than Pytest in ${environment}.`;
    }
    return "Run more automation cycles to surface framework stability insights.";
  }, [runs, environment]);

  return (
    <>
      {/* ── Insight row: coverage, pass-rate trend, flaky tests ─────── */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardContent className="p-4">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
              <TrendingUp className="h-3.5 w-3.5 text-emerald-500" /> Automation coverage
            </div>
            <p className="text-3xl font-bold tabular-nums text-slate-900">
              {coverage.pct !== null ? `${coverage.pct}%` : "—"}
            </p>
            <p className="mt-1 text-[11px] text-slate-500">
              {coverage.approved} approved script{coverage.approved === 1 ? "" : "s"} covering{" "}
              {coverage.eligible} eligible test case{coverage.eligible === 1 ? "" : "s"}
            </p>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full bg-emerald-500" style={{ width: `${coverage.pct ?? 0}%` }} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
              <TrendingUp className="h-3.5 w-3.5 text-[#1b59f8]" /> Pass-rate trend ({TREND_DAYS}d)
            </div>
            {trend.length < 2 ? (
              <p className="flex h-24 items-center justify-center text-[11px] text-slate-400">
                Not enough recent runs to draw a trend.
              </p>
            ) : (
              <ResponsiveContainer width="100%" height={96}>
                <LineChart data={trend} margin={{ left: -28, right: 4, top: 6, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="day" tick={{ fontSize: 9, fill: "#94a3b8" }} tickLine={false} axisLine={false} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: "#94a3b8" }} tickLine={false} axisLine={false} />
                  <Tooltip
                    formatter={(value: number) => [`${value}%`, "Pass rate"]}
                    contentStyle={{ fontSize: 11, borderRadius: 8 }}
                  />
                  <Line type="monotone" dataKey="passRate" stroke="#1b59f8" strokeWidth={2} dot={{ r: 2 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
              <Radar className="h-3.5 w-3.5 text-orange-500" /> Flaky tests
              {flakyQuery.isLoading && <span className="text-[10px] font-normal text-slate-400">scanning…</span>}
            </div>
            {flakyTests.length === 0 ? (
              <p className="flex h-24 items-center justify-center text-[11px] text-slate-400">
                {flakyQuery.isLoading
                  ? "Checking recent execution history…"
                  : "No pass/fail alternation detected in recent history."}
              </p>
            ) : (
              <ul className="space-y-1.5">
                {flakyTests.slice(0, 4).map((f) => (
                  <li key={f.testCaseKey} className="flex items-center gap-2 text-[11px]" title={f.title}>
                    <Badge variant="warning" className="shrink-0 text-[9px]">flaky</Badge>
                    <span className="truncate font-mono text-slate-700">{f.testCaseKey}</span>
                    <span className="ml-auto flex shrink-0 gap-0.5">
                      {f.sequence.map((s, i) => (
                        <span
                          key={i}
                          className={cn("h-2 w-2 rounded-full", s === "pass" ? "bg-emerald-400" : "bg-red-400")}
                          title={s}
                        />
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-12">
        <Card className="lg:col-span-8">
          <CardContent className="p-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-800">Execution Results</h3>
            </div>

            <div className="mb-4 grid grid-cols-4 gap-2">
              <ResultStat label="Total Runs" value={totals.total} colorClass="text-slate-900" />
              <ResultStat label="Passed" value={totals.passed} suffix={`${totals.passedPct}%`} colorClass="text-emerald-600" />
              <ResultStat label="Failed" value={totals.failed} suffix={`${totals.failedPct}%`} colorClass="text-red-600" />
              <ResultStat label="In Progress" value={totals.inProgress} suffix={`${totals.inProgressPct}%`} colorClass="text-amber-600" />
            </div>

            {runs.length === 0 ? (
              <p className="rounded border border-dashed border-slate-200 px-3 py-4 text-center text-[11px] text-slate-400">No automation runs yet</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-[10px] uppercase tracking-wider text-slate-400">
                      <th className="py-2 pr-3">Run ID</th>
                      <th className="py-2 pr-3">Script Name</th>
                      <th className="py-2 pr-3">Status</th>
                      <th className="py-2 pr-3">Started At</th>
                      <th className="py-2 pr-3 text-right">Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.slice(0, 8).map((r) => (
                      <tr
                        key={r.id}
                        className="cursor-pointer border-b border-slate-50 hover:bg-slate-50/60"
                        onClick={() => setSelectedRun(r)}
                      >
                        <td className="whitespace-nowrap py-2.5 pr-3 font-mono text-[#1b59f8]">{r.execution_id}</td>
                        <td className="max-w-[200px] truncate py-2.5 pr-3 text-slate-700">{r.suite_name ?? "—"}</td>
                        <td className="py-2.5 pr-3"><RunVerdictBadge run={r} /></td>
                        <td className="whitespace-nowrap py-2.5 pr-3 text-slate-500">{formatDate(r.started_at ?? r.created_at)}</td>
                        <td className="py-2.5 pr-3 text-right font-mono tabular-nums text-slate-500">
                          {formatDuration(r.duration_seconds)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="mt-2 text-right">
              <Link href={buildHref("/execution/dashboard", { project: projectId })} className="inline-flex items-center gap-0.5 text-[11px] text-[#1b59f8] hover:underline">
                Full analytics <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Right column: AI Insight + Sync Summary */}
        <div className="space-y-4 lg:col-span-4">
          <Card className="border-violet-100 bg-gradient-to-br from-violet-50 to-blue-50">
            <CardContent className="p-4">
              <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-violet-700">
                <Sparkles className="h-3.5 w-3.5" /> AI Insight
              </div>
              <p className="text-[11px] leading-relaxed text-slate-700">{aiInsight}</p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="mb-3 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
                <RefreshCw className="h-3.5 w-3.5" /> Sync Summary
              </div>
              {(() => {
                // Real external-mapping sync timestamp wins over the page-load
                // time. Falls back to the load time if no mappings exist, and
                // clearly labels which one is shown.
                const realSync = mappings
                  .map((m) => m.last_synced_at)
                  .filter((t): t is string => !!t)
                  .sort()
                  .pop();
                const lastSyncDisplay = realSync
                  ? formatDate(realSync)
                  : lastLoadedAt
                    ? `${formatDate(lastLoadedAt.toISOString())} (page)`
                    : "—";
                return <SyncRow label="Last Sync" value={lastSyncDisplay} ok={Boolean(realSync)} />;
              })()}
              <SyncRow label="Synced Runs (Today)" value={totals.executedToday.toLocaleString()} ok={totals.executedToday > 0} />
              <SyncRow label="Defects Raised (Today)" value={defectsToday.toLocaleString()} ok={defectsToday === 0} />
              <div className="mt-2 border-t border-slate-100 pt-2 text-right">
                <Link href={buildHref("/defects", { project: projectId })} className="inline-flex items-center gap-0.5 text-[10px] text-[#1b59f8] hover:underline">
                  View sync details <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <RunDetailDrawer
        runId={selectedRun?.id ?? null}
        open={selectedRun !== null}
        onOpenChange={(o) => { if (!o) setSelectedRun(null); }}
        initialRun={selectedRun}
      />
    </>
  );
}

function ResultStat({ label, value, suffix, colorClass }: { label: string; value: number; suffix?: string; colorClass: string }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{label}</p>
      <p className={cn("mt-1 text-xl font-bold tabular-nums", colorClass)}>{value}</p>
      {suffix && <p className="text-[10px] tabular-nums text-slate-500">{suffix}</p>}
    </div>
  );
}

function SyncRow({ label, value, ok }: { label: string; value: React.ReactNode; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between py-1 text-[11px]">
      <span className="text-slate-500">{label}</span>
      <span className="flex items-center gap-1.5">
        <span className="font-medium text-slate-700">{value}</span>
        <span className={cn("h-1.5 w-1.5 rounded-full", ok ? "bg-emerald-500" : "bg-slate-300")} />
      </span>
    </div>
  );
}
