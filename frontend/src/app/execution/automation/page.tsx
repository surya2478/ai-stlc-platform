"use client";

import { Suspense, useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, Bot, Brain, Clock3, Code2, FileText, Loader2, Play,
  RefreshCw, ShieldCheck, Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { defectsApi, type ExecutionRun } from "@/lib/api";
import { usePlanning, useScripts, useAutomationMappings } from "@/lib/queries/automation";
import { useRuns, isActiveRun } from "@/lib/queries/execution";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EnvironmentFilter } from "@/components/execution/EnvironmentFilter";
import {
  EmptyState,
  ErrorState,
  ExecutionPageHeader,
} from "../_components/execution-shared";
import { runVerdict } from "../_components/run-utils";
import { AutomationBuilderTab } from "../_components/AutomationBuilderTab";
import { ActiveRunsTab } from "../_components/ActiveRunsTab";
import { RunHistoryTab } from "../_components/RunHistoryTab";
import { AutomationInsightsTab } from "../_components/AutomationInsightsTab";

type ExecutionMode = "standard" | "ai-assisted";
type AutomationTab = "builder" | "active" | "history" | "insights";

const TAB_KEYS: AutomationTab[] = ["builder", "active", "history", "insights"];

function AutomationExecutionContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();

  const projectId = searchParams.get("project");
  const projectNum = projectId ? Number(projectId) : null;
  const environment = searchParams.get("env") ?? "QA-Staging";
  const mode: ExecutionMode =
    searchParams.get("mode") === "ai-assisted" ? "ai-assisted" : "standard";
  const rawTab = searchParams.get("tab") as AutomationTab | null;
  const tab: AutomationTab = rawTab && TAB_KEYS.includes(rawTab) ? rawTab : "builder";

  const updateParam = useCallback(
    (key: string, value: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value == null) params.delete(key);
      else params.set(key, value);
      router.replace(`${pathname}?${params.toString()}`);
    },
    [searchParams, router, pathname],
  );

  const setMode = useCallback(
    (next: ExecutionMode) => updateParam("mode", next === "ai-assisted" ? "ai-assisted" : null),
    [updateParam],
  );
  const setTab = useCallback(
    (next: AutomationTab) => updateParam("tab", next === "builder" ? null : next),
    [updateParam],
  );

  // Data — React Query with live polling on runs while any run is active.
  const planningQuery = usePlanning(projectNum);
  const scriptsQuery = useScripts(projectNum);
  const runsQuery = useRuns(projectNum);
  const mappingsQuery = useAutomationMappings(projectNum, { active_only: true });
  const defectsQuery = useQuery({
    queryKey: ["defects", "list", projectNum],
    queryFn: async () => (await defectsApi.list(projectNum as number)).data,
    enabled: projectNum !== null && projectNum > 0,
  });

  const planning = planningQuery.data ?? null;
  const scripts = useMemo(() => scriptsQuery.data ?? [], [scriptsQuery.data]);
  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);
  const mappings = useMemo(() => mappingsQuery.data ?? [], [mappingsQuery.data]);

  const loading =
    planningQuery.isLoading || scriptsQuery.isLoading || runsQuery.isLoading || mappingsQuery.isLoading;
  const refreshing =
    planningQuery.isFetching || scriptsQuery.isFetching || runsQuery.isFetching || mappingsQuery.isFetching;

  const reload = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["automation"] });
    queryClient.invalidateQueries({ queryKey: ["execution"] });
    queryClient.invalidateQueries({ queryKey: ["defects"] });
  }, [queryClient]);

  // Surface a non-fatal warning if any primary fetch failed — the page still
  // renders with whatever did succeed.
  const loadError = useMemo(() => {
    const failures: string[] = [];
    if (planningQuery.isError) failures.push("automation planning");
    if (scriptsQuery.isError) failures.push("scripts");
    if (runsQuery.isError) failures.push("runs");
    if (mappingsQuery.isError) failures.push("external mappings");
    return failures.length > 0
      ? `Couldn't load: ${failures.join(", ")}. Some panels may be empty or stale.`
      : null;
  }, [planningQuery.isError, scriptsQuery.isError, runsQuery.isError, mappingsQuery.isError]);

  // Derived ---------------------------------------------------------------

  const automationRuns = useMemo(
    () => runs.filter((r) => r.execution_type === "automation"),
    [runs],
  );
  const activeRuns = useMemo(
    () => automationRuns.filter(isActiveRun),
    [automationRuns],
  );
  const historyRuns = useMemo(
    () => [...automationRuns].sort((a, b) => (b.started_at ?? b.created_at ?? "").localeCompare(a.started_at ?? a.created_at ?? "")),
    [automationRuns],
  );

  const defectsToday = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return (defectsQuery.data ?? []).filter((d) => (d.created_at ?? "").slice(0, 10) === today).length;
  }, [defectsQuery.data]);

  const totals = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    const d = new Date();
    d.setDate(d.getDate() - 1);
    const yesterday = d.toISOString().slice(0, 10);

    const startedOn = (r: ExecutionRun, day: string) =>
      (r.started_at ?? r.created_at ?? "").slice(0, 10) === day;
    const executedToday = automationRuns.filter((r) => startedOn(r, today)).length;
    const executedYesterday = automationRuns.filter((r) => startedOn(r, yesterday)).length;
    const eligibleCount = planning?.summary.total_candidates ?? planning?.candidates.length ?? mappings.length;
    const pendingApproval = scripts.filter((s) =>
      ["pending_approval", "under_review", "in_review"].includes((s.status ?? "").toLowerCase()),
    ).length;
    const approved = scripts.filter((s) => (s.status ?? "").toLowerCase() === "approved").length;

    // Percentage-change-from-yesterday, guarded against divide-by-zero.
    const pctChange = (t: number, y: number): number | null => {
      if (y === 0) return null; // no baseline; "vs yesterday" is meaningless
      return Math.round(((t - y) / y) * 100);
    };

    return {
      eligibleTcs: eligibleCount,
      scriptsGenerated: scripts.length,
      approved,
      pendingApproval,
      executedToday,
      executedTodayDeltaPct: pctChange(executedToday, executedYesterday),
    };
  }, [automationRuns, planning, scripts, mappings]);

  if (!projectId) {
    return (
      <div className="space-y-4">
        <ExecutionPageHeader title="Automation Execution" subtitle="Generate, approve, execute, and sync automation runs" />
        <EmptyState icon={Code2} title="Pick a project" description="Select a project from the header to see automation execution." />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ExecutionPageHeader
        title="Automation Execution"
        subtitle="Generate, approve, execute, and sync automation runs"
        actions={
          <div className="flex items-center gap-2">
            <EnvironmentFilter defaultValue="QA-Staging" />
            <ExecutionModeToggle mode={mode} onChange={setMode} />
            <Button variant="outline" size="sm" className="gap-1.5" onClick={reload} disabled={refreshing}>
              <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} /> Refresh
            </Button>
          </div>
        }
      />

      {mode === "ai-assisted" && <AiAssistedInfoCard />}

      {/* ── KPI row ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <AutomationKpiCard
          icon={FileText} tone="blue" label="Eligible Automation TCs"
          value={totals.eligibleTcs.toLocaleString()}
          footnote={
            totals.eligibleTcs > 0
              ? `${Math.round((Math.min(totals.scriptsGenerated, totals.eligibleTcs) / Math.max(totals.eligibleTcs, 1)) * 100)}% have scripts`
              : "no candidates yet"
          }
          loading={loading}
        />
        <AutomationKpiCard
          icon={Code2} tone="emerald" label="Scripts Generated"
          value={totals.scriptsGenerated.toLocaleString()}
          footnote={totals.scriptsGenerated > 0 ? `${totals.approved} approved` : "none generated yet"}
          loading={loading}
        />
        <AutomationKpiCard
          icon={Clock3} tone="orange" label="Pending Approval"
          value={totals.pendingApproval.toLocaleString()}
          footnote={totals.pendingApproval > 0 ? "awaiting reviewer" : "nothing in the queue"}
          loading={loading}
        />
        <AutomationKpiCard
          icon={Play} tone="violet" label="Executed Today"
          value={totals.executedToday.toLocaleString()}
          deltaPct={totals.executedTodayDeltaPct}
          footnote={totals.executedToday === 0 && totals.executedTodayDeltaPct == null ? "no runs today" : undefined}
          loading={loading}
        />
      </div>

      {loadError && <ErrorState title="Something went wrong" description={loadError} onRetry={reload} />}

      <AutomationExecutionTabs
        tab={tab}
        onChange={setTab}
        counts={{ active: activeRuns.length, history: automationRuns.length }}
      />

      {tab === "builder" && (
        <AutomationBuilderTab
          projectId={projectId}
          environment={environment}
          planning={planning}
          scripts={scripts}
          mappings={mappings}
          loading={loading}
          activeRunCount={activeRuns.length}
          totalRunCount={automationRuns.length}
          defectsToday={defectsToday}
          onViewActiveRuns={() => setTab("active")}
        />
      )}
      {tab === "active" && (
        <ActiveRunsTab
          runs={activeRuns}
          loading={loading}
          isPolling={activeRuns.length > 0}
        />
      )}
      {tab === "history" && (
        <RunHistoryTab runs={historyRuns} loading={loading} projectId={Number(projectId)} />
      )}
      {tab === "insights" && (
        <AutomationInsightsTab
          projectId={projectId}
          environment={environment}
          runs={historyRuns}
          mappings={mappings}
          planning={planning}
          scripts={scripts}
          defectsToday={defectsToday}
          lastLoadedAt={runsQuery.dataUpdatedAt ? new Date(runsQuery.dataUpdatedAt) : null}
        />
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* KPI card                                                                    */
/* ────────────────────────────────────────────────────────────────────────── */

type KpiTone = "blue" | "emerald" | "orange" | "violet";
const KPI_TONE: Record<KpiTone, { iconBg: string; iconColor: string }> = {
  blue:    { iconBg: "bg-blue-500",    iconColor: "text-white" },
  emerald: { iconBg: "bg-emerald-500", iconColor: "text-white" },
  orange:  { iconBg: "bg-orange-500",  iconColor: "text-white" },
  violet:  { iconBg: "bg-violet-500",  iconColor: "text-white" },
};

function AutomationKpiCard({
  icon: Icon, tone, label, value, footnote, deltaPct, loading,
}: {
  icon: React.ComponentType<{ className?: string }>;
  tone: KpiTone;
  label: string;
  value: React.ReactNode;
  /** Neutral context text shown when a vs-yesterday delta can't be computed. */
  footnote?: string;
  /** Real delta vs yesterday. Positive = up, negative = down, null = no data. */
  deltaPct?: number | null;
  loading?: boolean;
}) {
  const t = KPI_TONE[tone];
  const direction: "up" | "down" | "flat" | null =
    deltaPct == null ? null : deltaPct > 0 ? "up" : deltaPct < 0 ? "down" : "flat";
  const arrow = direction === "up" ? "↑" : direction === "down" ? "↓" : direction === "flat" ? "→" : "";
  const deltaCol =
    direction === "up" ? "text-emerald-600"
    : direction === "down" ? "text-red-600"
    : direction === "flat" ? "text-slate-500"
    : "text-slate-400";
  return (
    <Card className="shadow-sm">
      <CardContent className="p-3">
        <div className="flex items-center gap-2.5">
          <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-lg", t.iconBg)}>
            <Icon className={cn("h-5 w-5", t.iconColor)} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-medium leading-tight text-slate-500">{label}</p>
            <p className="mt-0.5 text-xl font-bold leading-tight tabular-nums text-slate-900">
              {loading ? <span className="inline-block h-6 w-16 animate-pulse rounded bg-slate-100" /> : value}
            </p>
            {!loading && deltaPct != null && (
              <p className={cn("text-[10px] font-medium leading-tight", deltaCol)}>
                {arrow} {Math.abs(deltaPct)}% vs yesterday
              </p>
            )}
            {!loading && deltaPct == null && footnote && (
              <p className="text-[10px] leading-tight text-slate-400">{footnote}</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Tabs, mode toggle, AI info card                                             */
/* ────────────────────────────────────────────────────────────────────────── */

function AutomationExecutionTabs({
  tab,
  onChange,
  counts,
}: {
  tab: AutomationTab;
  onChange: (next: AutomationTab) => void;
  counts: { active: number; history: number };
}) {
  const items: { key: AutomationTab; label: string; badge?: number }[] = [
    { key: "builder", label: "Run Builder" },
    { key: "active", label: "Active Runs", badge: counts.active },
    { key: "history", label: "Run History", badge: counts.history },
    { key: "insights", label: "Results & Insights" },
  ];
  return (
    <div className="border-b border-slate-200">
      <div className="flex items-center gap-1 overflow-x-auto">
        {items.map((item) => {
          const active = tab === item.key;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => onChange(item.key)}
              aria-pressed={active}
              className={cn(
                "shrink-0 border-b-2 px-3 py-2 text-xs font-semibold transition -mb-px",
                active
                  ? "border-[#1b59f8] text-[#1b59f8]"
                  : "border-transparent text-slate-500 hover:text-slate-800",
              )}
            >
              {item.label}
              {item.badge != null && item.badge > 0 && (
                <span className={cn(
                  "ml-1.5 inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
                  active ? "bg-blue-100 text-[#1b59f8]" : "bg-slate-100 text-slate-600",
                )}>
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ExecutionModeToggle({
  mode,
  onChange,
}: {
  mode: ExecutionMode;
  onChange: (next: ExecutionMode) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Execution mode"
      className="inline-flex items-center rounded-lg border border-slate-200 bg-white p-0.5"
    >
      <ModeButton
        active={mode === "standard"}
        onClick={() => onChange("standard")}
        icon={<Play className="h-3.5 w-3.5" />}
        label="Standard"
      />
      <ModeButton
        active={mode === "ai-assisted"}
        onClick={() => onChange("ai-assisted")}
        icon={<Sparkles className="h-3.5 w-3.5" />}
        label="AI-Assisted"
        activeToneClass="bg-violet-600 text-white hover:bg-violet-700"
      />
    </div>
  );
}

function ModeButton({
  active,
  onClick,
  icon,
  label,
  activeToneClass = "bg-slate-900 text-white hover:bg-slate-800",
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  activeToneClass?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold transition",
        active ? activeToneClass : "text-slate-600 hover:bg-slate-50",
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function AiAssistedInfoCard() {
  return (
    <Card className="border-violet-100 bg-violet-50/50">
      <CardContent className="flex flex-wrap items-start gap-3 p-4">
        <div className="rounded-lg border border-violet-200 bg-white p-2">
          <Brain className="h-4 w-4 text-violet-600" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-bold text-violet-900">AI-Assisted mode is on</p>
          <p className="mt-1 text-[11px] leading-relaxed text-violet-800">
            Runs still use Playwright, Pytest, or the configured external tool as the authority
            for pass/fail. AI adds a layer on top: pre-run data validation, failure
            classification, intelligent retry for transient failures, business-readable summary,
            and defect-draft preparation.
          </p>
          <ul className="mt-2 grid gap-1 text-[11px] text-violet-800 sm:grid-cols-2">
            <li className="flex items-center gap-1.5">
              <ShieldCheck className="h-3 w-3" /> Runner still decides pass / fail
            </li>
            <li className="flex items-center gap-1.5">
              <Bot className="h-3 w-3" /> AI drafts a defect on failures
            </li>
            <li className="flex items-center gap-1.5">
              <Sparkles className="h-3 w-3" /> Failures categorized automatically
            </li>
            <li className="flex items-center gap-1.5">
              <ArrowRight className="h-3 w-3" /> Transient failures re-run once
            </li>
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div className="flex h-96 items-center justify-center text-slate-400"><Loader2 className="mr-2 h-5 w-5 animate-spin" />Loading…</div>}>
      <AutomationExecutionContent />
    </Suspense>
  );
}
