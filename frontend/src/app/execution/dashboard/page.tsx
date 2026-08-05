"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  Activity, ListChecks, CheckCircle2, XCircle, Loader2, Pause, Clock3, RefreshCw,
  TrendingUp, AlertTriangle, Bug, Sparkles, BarChart3, Eye, ArrowRight,
} from "lucide-react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend,
  PieChart, Pie, Cell, BarChart, Bar,
} from "recharts";
import {
  ExecutionPageHeader,
  KpiCard,
  EmptyState,
  ErrorState,
  ExecutionStatusBadge,
  ExecutionTypeBadge,
  buildHref,
} from "../_components/execution-shared";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EnvironmentFilter } from "@/components/execution/EnvironmentFilter";
import { executionApi, type ExecutionDashboardPayload } from "@/lib/api";
import { cn } from "@/lib/utils";

const TYPE_COLOR: Record<string, string> = {
  manual: "#D52B31",
  automation: "#10b981",
  ai: "#8b5cf6",
  hybrid: "#f59e0b",
};

const ENV_COLOR = ["#B71920", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#06b6d4"];

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

function ExecutionDashboardContent() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");
  const environment = searchParams.get("env");

  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const sevenDaysAgo = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  }, []);

  const [dateFrom, setDateFrom] = useState(sevenDaysAgo);
  const [dateTo, setDateTo] = useState(today);
  const [data, setData] = useState<ExecutionDashboardPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    executionApi
      .getDashboard({
        project_id: Number(projectId),
        environment: environment || null,
        date_from: dateFrom || null,
        date_to: dateTo || null,
      })
      .then((res) => {
        setData(res.data);
        setLastUpdated(new Date());
      })
      .catch((err) => setError(err?.response?.data?.detail ?? err?.message ?? "Failed to load dashboard"))
      .finally(() => setLoading(false));
  }, [projectId, environment, dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

  if (!projectId) {
    return (
      <div className="space-y-5">
        <ExecutionPageHeader
          title="Execution Dashboard"
          subtitle="Real-time overview of test execution results across Manual, Automation & AI"
        />
        <EmptyState
          icon={Activity}
          title="Pick a project"
          description="Choose a project from the header to see the unified Execution Dashboard."
        />
      </div>
    );
  }

  const kpis = data?.kpis;
  const byType = data?.by_type ?? [];
  const trend = data?.trend ?? [];
  const recent = data?.recent_runs ?? [];

  return (
    <div className="space-y-5">
      <ExecutionPageHeader
        title="Execution Dashboard"
        subtitle="Real-time overview of test execution results across Manual, Automation & AI"
        actions={
          <div className="flex items-center gap-2">
            <EnvironmentFilter />
            <div className="hidden md:flex items-center gap-1.5 text-[11px] text-gray-500">
              <input
                type="date"
                value={dateFrom}
                max={dateTo || undefined}
                onChange={(e) => setDateFrom(e.target.value)}
                className="rounded-md border border-gray-200 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[#B71920]"
              />
              <span>→</span>
              <input
                type="date"
                value={dateTo}
                min={dateFrom || undefined}
                onChange={(e) => setDateTo(e.target.value)}
                className="rounded-md border border-gray-200 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[#B71920]"
              />
            </div>
            <Button variant="outline" size="sm" className="gap-1.5" onClick={load} disabled={loading}>
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} /> Refresh
            </Button>
          </div>
        }
      />

      {lastUpdated && (
        <div className="text-[11px] text-gray-400">
          Last updated {lastUpdated.toLocaleTimeString()}
          {environment && <> · environment: <span className="text-gray-600 font-medium">{environment}</span></>}
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <KpiCard icon={Activity}    tone="blue"    label="Total Executions"   value={kpis?.total_executions ?? 0} loading={loading} />
        <KpiCard icon={ListChecks}  tone="violet"  label="Total Test Cases"   value={kpis?.total_test_cases ?? 0} loading={loading} />
        <KpiCard icon={CheckCircle2} tone="emerald" label="Passed"            value={kpis?.passed ?? 0}
          delta={kpis ? `${kpis.overall_pass_rate}% pass rate` : undefined}
          deltaDirection="up" loading={loading} />
        <KpiCard icon={XCircle}     tone="red"     label="Failed"             value={kpis?.failed ?? 0} loading={loading} />
        <KpiCard icon={Loader2}     tone="cyan"    label="In Progress"        value={kpis?.in_progress ?? 0} loading={loading} />
        <KpiCard icon={Pause}       tone="orange"  label="Blocked"            value={kpis?.blocked ?? 0} loading={loading} />
        <KpiCard icon={Clock3}      tone="slate"   label="Avg. Execution Time" value={formatDuration(kpis?.avg_execution_seconds)} loading={loading} />
      </div>

      {error && (
        <ErrorState title="Couldn't load dashboard" description={error} onRetry={load} />
      )}

      {/* Main grid: by-type donut + trend + insights */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardContent className="p-5">
            <h3 className="text-sm font-semibold text-gray-800">Execution Overview by Type</h3>
            <p className="mt-0.5 text-[11px] text-gray-400">Run count and per-type outcomes</p>

            <div className="mt-3 flex items-center justify-center">
              {byType.length > 0 ? (
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie
                      data={byType}
                      dataKey="run_count"
                      nameKey="execution_type"
                      innerRadius={50}
                      outerRadius={75}
                      paddingAngle={3}
                      stroke="none"
                    >
                      {byType.map((d) => (
                        <Cell key={d.execution_type} fill={TYPE_COLOR[d.execution_type] ?? "#9CA3AF"} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="text-xs text-gray-400 py-12">No data</div>
              )}
            </div>

            <div className="mt-2 space-y-2">
              {byType.map((b) => (
                <div key={b.execution_type} className="rounded-lg border border-gray-100 p-2.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: TYPE_COLOR[b.execution_type] ?? "#9CA3AF" }}
                      />
                      <span className="text-xs font-semibold capitalize text-gray-800">
                        {b.execution_type} ({b.run_count})
                      </span>
                    </div>
                    <Link
                      href={buildHref(`/execution/${b.execution_type}`, { project: projectId, env: environment })}
                      className="text-[11px] text-[#B71920] hover:underline"
                    >
                      View →
                    </Link>
                  </div>
                  <div className="mt-1.5 grid grid-cols-4 gap-1 text-[10px]">
                    <span className="text-emerald-600">{b.passed} pass</span>
                    <span className="text-red-600">{b.failed} fail</span>
                    <span className="text-orange-600">{b.blocked} blkd</span>
                    <span className="text-gray-500">{b.pass_rate}%</span>
                  </div>
                </div>
              ))}
              {byType.length === 0 && !loading && (
                <p className="text-[11px] text-gray-400 text-center py-4">No runs in this window</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-gray-800">Execution Trend</h3>
                <p className="mt-0.5 text-[11px] text-gray-400">Daily run counts by type</p>
              </div>
              <Badge variant="secondary" className="text-[10px]">
                {dateFrom} → {dateTo}
              </Badge>
            </div>
            <div className="mt-4">
              {trend.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={trend} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
                    <CartesianGrid stroke="#F4F5F7" vertical={false} />
                    <XAxis dataKey="date" tickFormatter={(v) => v.slice(5)} tick={{ fontSize: 11, fill: "#6B7280" }} stroke="#D1D5DB" />
                    <YAxis tick={{ fontSize: 11, fill: "#6B7280" }} stroke="#D1D5DB" allowDecimals={false} />
                    <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line type="monotone" dataKey="manual"     stroke={TYPE_COLOR.manual}     strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="automation" stroke={TYPE_COLOR.automation} strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="ai"         stroke={TYPE_COLOR.ai}         strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-64 text-xs text-gray-400">No execution activity in this date range</div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Insights row */}
      {data && data.insights.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {data.insights.map((insight) => (
            <Card key={insight.kind} className="border-l-4" style={{ borderLeftColor: insight.kind === "ai_pass_rate" ? TYPE_COLOR.ai : insight.kind === "blocked" ? "#f97316" : insight.kind === "defects" ? "#ef4444" : "#B71920" }}>
              <CardContent className="p-4">
                <div className="flex items-start gap-2">
                  {insight.kind === "ai_pass_rate" && <Sparkles className="h-4 w-4 text-violet-500 mt-0.5" />}
                  {insight.kind === "blocked" && <AlertTriangle className="h-4 w-4 text-orange-500 mt-0.5" />}
                  {insight.kind === "review" && <Eye className="h-4 w-4 text-violet-500 mt-0.5" />}
                  {insight.kind === "defects" && <Bug className="h-4 w-4 text-red-500 mt-0.5" />}
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-gray-800">{insight.title}</p>
                    <p className="text-[11px] text-gray-500 mt-0.5">{insight.body}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Recent + Module + Env */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-800">Recent Executions</h3>
              <Link href={buildHref("/execution/legacy", { project: projectId })} className="text-[11px] text-[#B71920] hover:underline">
                View all →
              </Link>
            </div>
            {recent.length === 0 && !loading ? (
              <EmptyState icon={Activity} title="No recent executions" description="Trigger a run from any execution module to populate this list." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wider text-gray-400 border-b border-gray-100">
                      <th className="py-2 pr-3">Run ID</th>
                      <th className="py-2 pr-3">Type</th>
                      <th className="py-2 pr-3">Suite</th>
                      <th className="py-2 pr-3">Env</th>
                      <th className="py-2 pr-3">Status</th>
                      <th className="py-2 pr-3 text-right">Pass/Fail</th>
                      <th className="py-2 pr-3">Started</th>
                      <th className="py-2 pr-3 text-right">Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent.map((r) => (
                      <tr key={r.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                        <td className="py-2 pr-3 font-mono text-[#B71920]">RUN-{r.id}</td>
                        <td className="py-2 pr-3"><ExecutionTypeBadge type={r.execution_type} /></td>
                        <td className="py-2 pr-3 max-w-[200px] truncate text-gray-700">{r.suite_name ?? "—"}</td>
                        <td className="py-2 pr-3 text-gray-500">{r.environment ?? "—"}</td>
                        <td className="py-2 pr-3"><ExecutionStatusBadge status={r.status} /></td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          <span className="text-emerald-600">{r.passed}</span>
                          <span className="text-gray-300 mx-1">/</span>
                          <span className="text-red-600">{r.failed}</span>
                        </td>
                        <td className="py-2 pr-3 text-gray-500">{formatDate(r.started_at)}</td>
                        <td className="py-2 pr-3 text-right tabular-nums text-gray-500">{formatDuration(r.duration_seconds)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardContent className="p-5">
              <h3 className="text-sm font-semibold text-gray-800">Execution by Module</h3>
              {data?.by_module && data.by_module.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {data.by_module.map((m) => {
                    const max = Math.max(...data.by_module.map((x) => x.executions), 1);
                    const pct = Math.round((m.executions / max) * 100);
                    return (
                      <div key={m.module}>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-gray-700 truncate max-w-[120px]">{m.module}</span>
                          <span className="text-gray-500 tabular-nums">{m.executions}</span>
                        </div>
                        <div className="mt-1 h-1.5 rounded-full bg-gray-100 overflow-hidden">
                          <div className="h-full rounded-full bg-[#B71920]" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="mt-3 text-[11px] text-gray-400">No module data</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5">
              <h3 className="text-sm font-semibold text-gray-800">Execution by Environment</h3>
              {data?.by_environment && data.by_environment.length > 0 ? (
                <ResponsiveContainer width="100%" height={160}>
                  <PieChart>
                    <Pie data={data.by_environment} dataKey="run_count" nameKey="environment" innerRadius={40} outerRadius={62} stroke="none">
                      {data.by_environment.map((d, i) => (
                        <Cell key={d.environment} fill={ENV_COLOR[i % ENV_COLOR.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="mt-3 text-[11px] text-gray-400">No environment data</p>
              )}
              <div className="mt-2 space-y-1 text-[11px]">
                {data?.by_environment?.map((e, i) => (
                  <div key={e.environment} className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-gray-600">
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: ENV_COLOR[i % ENV_COLOR.length] }} />
                      {e.environment}
                    </span>
                    <span className="text-gray-500 tabular-nums">{e.run_count}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Pass rate cards + defects */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardContent className="p-5">
            <h3 className="text-sm font-semibold text-gray-800">Pass Rate by Execution Type</h3>
            <div className="mt-3 grid grid-cols-3 gap-3">
              {["manual", "automation", "ai"].map((t) => {
                const row = byType.find((b) => b.execution_type === t);
                const rate = row?.pass_rate ?? 0;
                return (
                  <div key={t} className="rounded-xl border border-gray-100 p-3 text-center">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">{t}</p>
                    <p className="mt-1 text-2xl font-bold tabular-nums" style={{ color: TYPE_COLOR[t] }}>
                      {rate}%
                    </p>
                    <p className="mt-1 text-[10px] text-gray-500">
                      {row ? `${row.passed} / ${row.total_tests}` : "no runs"}
                    </p>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-800">Defects from Executions</h3>
              <Link href={buildHref("/defects", { project: projectId })} className="text-[11px] text-[#B71920] hover:underline">
                View all defects →
              </Link>
            </div>
            <div className="grid grid-cols-4 gap-3">
              <div className="text-center">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">Total</p>
                <p className="mt-1 text-2xl font-bold text-gray-900 tabular-nums">{data?.defects.total ?? 0}</p>
              </div>
              {(["manual", "automation", "ai"] as const).map((t) => (
                <div key={t} className="text-center">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">From {t}</p>
                  <p className="mt-1 text-2xl font-bold tabular-nums" style={{ color: TYPE_COLOR[t] }}>
                    {data?.defects.by_type[t] ?? 0}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Execution summary */}
      <Card>
        <CardContent className="p-5">
          <h3 className="text-sm font-semibold text-gray-800">Execution Summary</h3>
          <div className="mt-3 grid grid-cols-2 gap-4 md:grid-cols-4 text-sm">
            <SummaryItem label="Total Execution Time" value={formatDuration(kpis?.total_execution_seconds)} />
            <SummaryItem label="Avg. Execution Time" value={formatDuration(kpis?.avg_execution_seconds)} />
            <SummaryItem label="Total Test Cases" value={kpis?.total_test_cases ?? 0} />
            <SummaryItem label="Pending AI Reviews" value={kpis?.review_required ?? 0} />
          </div>
        </CardContent>
      </Card>

      <p className="text-[10px] text-gray-400 px-1">
        * Dashboard figures are computed from unified ExecutionRun + ExecutionResult tables and de-duplicated per run.
      </p>
    </div>
  );
}

function SummaryItem({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-gray-100 p-3">
      <p className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">{label}</p>
      <p className="mt-1 text-base font-semibold text-gray-800 tabular-nums">{value}</p>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div className="flex h-96 items-center justify-center text-gray-400"><Loader2 className="h-5 w-5 animate-spin mr-2" />Loading…</div>}>
      <ExecutionDashboardContent />
    </Suspense>
  );
}
