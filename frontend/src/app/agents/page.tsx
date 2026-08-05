"use client";

import { useState, useEffect, useCallback, useMemo, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { agentRunsApi, projectsApi, type AgentRun } from "@/lib/api";
import { Bot, CheckCircle, XCircle, Clock, AlertTriangle, RefreshCw, ChevronRight, Zap, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

// ── Agent pipeline definition ─────────────────────────────────────────────────

const PIPELINE = [
  { name: "requirement_intake",  label: "Requirement Intake",   description: "Extracts requirements from uploaded documents",        phase: "Phase 2", color: "bg-app-brand-75 text-app-brand-700 border-app-brand-150" },
  { name: "requirement_quality", label: "Quality Analysis",     description: "Validates and enriches requirements with QA lens",     phase: "Phase 2", color: "bg-cyan-50 text-cyan-700 border-cyan-150" },
  { name: "test_planning",       label: "Test Planning",        description: "Generates structured test plan from requirements",     phase: "Phase 3", color: "bg-violet-50 text-violet-700 border-violet-150" },
  { name: "test_scenario",       label: "Test Scenarios",       description: "Creates high-level test scenarios per requirement",    phase: "Phase 3", color: "bg-purple-50 text-purple-700 border-purple-150" },
  { name: "test_case",           label: "Test Cases",           description: "Generates detailed step-by-step test cases",          phase: "Phase 3", color: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-150" },
  { name: "automation_script",   label: "Automation Scripts",   description: "Writes Playwright / Pytest scripts for automation",   phase: "Phase 4", color: "bg-pink-50 text-pink-700 border-pink-150" },
  { name: "test_execution",      label: "Test Execution",       description: "Executes test suite and records pass/fail results",   phase: "Phase 5", color: "bg-rose-50 text-rose-700 border-rose-150" },
  { name: "defect_analysis",     label: "Defect Analysis",      description: "Analyses failures and writes defect reports",         phase: "Phase 6", color: "bg-orange-50 text-orange-700 border-orange-150" },
  { name: "test_reporting",      label: "QA Reporting",         description: "Aggregates metrics and generates executive report",   phase: "Phase 7", color: "bg-emerald-50 text-emerald-700 border-emerald-150" },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function getStatusVariant(status: string): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" {
  const s = status.toLowerCase();
  if (s === "completed" || s === "passed" || s === "success") return "success";
  if (s === "failed" || s === "error") return "destructive";
  if (s === "running" || s === "pending") return "warning";
  if (s === "cancelled") return "secondary";
  return "outline";
}

function StatusDot({ status }: { status: string | null }) {
  if (!status) return <span className="w-2 h-2 rounded-full bg-gray-200 inline-block" />;
  const map: Record<string, string> = {
    completed: "bg-emerald-500",
    running: "bg-app-brand-500 animate-pulse",
    failed: "bg-rose-500",
    pending: "bg-amber-400",
    cancelled: "bg-gray-450",
  };
  return <span className={cn("w-2 h-2 rounded-full inline-block shrink-0", map[status.toLowerCase()] ?? "bg-gray-300")} />;
}

function formatDuration(secs: number | undefined): string {
  if (!secs) return "—";
  if (secs < 60) return `${secs.toFixed(1)}s`;
  return `${Math.floor(secs / 60)}m ${(secs % 60).toFixed(0)}s`;
}

function AgentPipelineCard({
  agent,
  latestRun,
  runCount,
  onSelect,
  isSelected,
}: {
  agent: typeof PIPELINE[0];
  latestRun: AgentRun | null;
  runCount: number;
  onSelect: () => void;
  isSelected: boolean;
}) {
  return (
    <Card
      onClick={onSelect}
      className={cn(
        "cursor-pointer hover:border-gray-350 hover:shadow-sm transition-all group p-4 flex flex-col justify-between h-full bg-white select-none",
        isSelected ? "border-[#B71920] ring-1 ring-[#B71920]/10 bg-[#B71920]/5" : "border-gray-250"
      )}
    >
      <div className="space-y-2 mb-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <StatusDot status={latestRun?.status ?? null} />
            <span className={cn("px-2 py-0.5 rounded text-[10px] font-bold border capitalize", agent.color)}>
              {agent.phase}
            </span>
          </div>
          <ChevronRight size={14} className="text-gray-300 group-hover:text-gray-500 shrink-0 transition-colors" />
        </div>
        <div>
          <h3 className="text-xs font-bold text-gray-800 group-hover:text-gray-900 leading-tight">
            {agent.label}
          </h3>
          <p className="text-[11px] font-semibold text-gray-400 mt-1 leading-relaxed">
            {agent.description}
          </p>
        </div>
      </div>
      
      <div className="flex items-center justify-between pt-2.5 border-t border-gray-50 text-[10px] text-gray-450 font-bold">
        {latestRun ? (
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <Badge variant={getStatusVariant(latestRun.status)} className="capitalize px-1.5 py-0 text-[9px]">
              {latestRun.status}
            </Badge>
            <span className="flex items-center gap-1 font-bold text-gray-400 shrink-0">
              <Clock className="h-3 w-3" /> 
              {formatDuration(latestRun.duration_seconds)}
            </span>
            <span className="ml-auto text-gray-400 font-bold shrink-0">
              {new Date(latestRun.created_at).toLocaleDateString()}
            </span>
          </div>
        ) : (
          <span className="text-gray-350 italic font-bold">No runs yet</span>
        )}
        {runCount > 0 && !latestRun && (
          <span className="ml-auto text-gray-400 font-bold">
            {runCount} run{runCount !== 1 ? "s" : ""}
          </span>
        )}
      </div>
    </Card>
  );
}

function RunHistoryRow({ run, onSelect }: { run: AgentRun; onSelect: (id: number) => void }) {
  const agentLabel = PIPELINE.find(a => a.name === run.agent_name)?.label ?? run.agent_name;
  return (
    <div
      onClick={() => onSelect(run.id)}
      className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50/50 cursor-pointer border-b border-gray-100 last:border-0 transition-colors font-semibold text-xs text-gray-700"
    >
      <StatusDot status={run.status} />
      <div className="flex-1 min-w-0">
        <p className="font-bold text-gray-800 truncate">{agentLabel}</p>
        <p className="text-[10px] text-gray-400 font-bold mt-0.5">{new Date(run.created_at).toLocaleString()}</p>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant={getStatusVariant(run.status)} className="capitalize text-[10px] py-0 px-2">
          {run.status}
        </Badge>
        <span className="text-[10px] font-bold text-gray-400 w-16 text-right shrink-0">{formatDuration(run.duration_seconds)}</span>
        {run.status === "failed" && <AlertTriangle size={14} className="text-rose-500 shrink-0" />}
      </div>
    </div>
  );
}

// ── Main Content Component ───────────────────────────────────────────────────

function AgentWorkflowContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProject = Number(searchParams.get("project")) || null;

  const [allRuns, setAllRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  useEffect(() => {
    projectsApi.list()
      .then((r) => {
        if (r.data.length > 0 && !searchParams.get("project")) {
          const params = new URLSearchParams(searchParams.toString());
          params.set("project", String(r.data[0].id));
          router.push(`${pathname}?${params.toString()}`);
        }
      })
      .catch((e) => console.error("[Projects] Failed to load:", e?.response?.status));
  }, [searchParams, pathname, router]);

  const loadRuns = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const res = await agentRunsApi.list(selectedProject, { limit: 200 });
      setAllRuns(res.data);
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => { loadRuns(); }, [loadRuns]);

  // Build per-agent stats
  const agentStats = useMemo(() => {
    const stats: Record<string, { latest: AgentRun | null; count: number }> = {};
    for (const a of PIPELINE) {
      const runs = allRuns.filter(r => r.agent_name === a.name);
      stats[a.name] = {
        latest: runs[0] ?? null,
        count: runs.length,
      };
    }
    return stats;
  }, [allRuns]);

  const filteredRuns = useMemo(() => {
    return selectedAgent
      ? allRuns.filter(r => r.agent_name === selectedAgent)
      : allRuns;
  }, [allRuns, selectedAgent]);

  const summary = useMemo(() => {
    const total = allRuns.length;
    const completed = allRuns.filter(r => r.status === "completed").length;
    const failed = allRuns.filter(r => r.status === "failed").length;
    const timedRuns = allRuns.filter(r => r.duration_seconds);
    const avgDuration = timedRuns.length > 0
      ? timedRuns.reduce((sum, r) => sum + (r.duration_seconds ?? 0), 0) / timedRuns.length
      : 0;

    return { total, completed, failed, avgDuration };
  }, [allRuns]);

  const stats = useMemo(() => {
    return [
      {
        title: "Total Agent Runs",
        icon: Zap,
        iconBg: "bg-app-brand-75 border-app-brand-100",
        iconColor: "text-app-brand-505",
        value: summary.total.toLocaleString(),
        sublabel: "Runs",
        footer: "Total triggers in project lifecycle",
      },
      {
        title: "Completed Runs",
        icon: CheckCircle,
        iconBg: "bg-emerald-50 border-emerald-100",
        iconColor: "text-emerald-505",
        value: summary.completed.toLocaleString(),
        sublabel: "Completed",
        footer: `${summary.total > 0 ? ((summary.completed / summary.total) * 100).toFixed(1) : "0.0"}% successful execution`,
      },
      {
        title: "Failed Runs",
        icon: XCircle,
        iconBg: "bg-rose-50 border-rose-100",
        iconColor: "text-rose-505",
        value: summary.failed.toLocaleString(),
        sublabel: "Failed",
        footer: `${summary.total > 0 ? ((summary.failed / summary.total) * 100).toFixed(1) : "0.0"}% failed runs logged`,
      },
      {
        title: "Avg Duration",
        icon: Clock,
        iconBg: "bg-app-brand-75 border-app-brand-100",
        iconColor: "text-app-brand-505",
        value: formatDuration(summary.avgDuration),
        sublabel: "Avg",
        footer: "Average runtime execution delay",
      },
    ];
  }, [summary]);

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Global Controls ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-app-brand-75 border border-app-brand-100 p-2.5">
            <Bot className="h-6 w-6 text-[#B71920]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Agent Workflow</h1>
            <p className="text-xs text-gray-500 mt-1">Full 9-agent STLC pipeline — status monitor, executions, and runtime diagnostics</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadRuns} className="h-8 w-8 p-0 border-gray-200">
            <RefreshCw className={cn("h-3.5 w-3.5 text-gray-500", loading && "animate-spin")} />
          </Button>
        </div>
      </div>

      {selectedProject && (
        <>
          {/* ── Status Counts Cards ─────────────────────────────────────────────────── */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {stats.map((card) => {
              const Icon = card.icon;
              return (
                <Card key={card.title} className="border-gray-200 hover:-translate-y-0.5 transition-all bg-white">
                  <CardContent className="p-4 flex flex-col justify-between h-full space-y-3">
                    <div className="flex items-center gap-2">
                      <div className={cn("rounded-lg p-1.5 flex items-center justify-center shrink-0 border", card.iconBg)}>
                        <Icon className={cn("h-4 w-4", card.iconColor)} />
                      </div>
                      <span className="text-xs font-bold text-gray-700 truncate">{card.title}</span>
                    </div>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-xl font-bold text-gray-900">{card.value}</span>
                      {card.sublabel && (
                        <span className="text-[10px] font-bold text-gray-400">{card.sublabel}</span>
                      )}
                    </div>
                    <div className="text-[10px] text-gray-400 font-semibold border-t border-gray-50 pt-2">
                      {card.footer}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* ── Pipeline Grid ─────────────────────────────────────────────────────── */}
          <div className="space-y-3">
            <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider">Pipeline Agents Grid</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {PIPELINE.map((agent) => (
                <div key={agent.name} className="relative">
                  <AgentPipelineCard
                    agent={agent}
                    latestRun={agentStats[agent.name]?.latest ?? null}
                    runCount={agentStats[agent.name]?.count ?? 0}
                    onSelect={() => setSelectedAgent(selectedAgent === agent.name ? null : agent.name)}
                    isSelected={selectedAgent === agent.name}
                  />
                </div>
              ))}
            </div>
          </div>

          {/* ── Run History List ──────────────────────────────────────────────────── */}
          <Card className="border-gray-200 shadow-sm overflow-hidden bg-white">
            <div className="flex items-center justify-between px-4 py-3.5 border-b border-gray-100 bg-gray-50/50">
              <div className="flex items-center gap-2">
                <h2 className="text-xs font-bold text-gray-800 uppercase tracking-wider">Run History</h2>
                {selectedAgent && (
                  <span className="text-[10px] font-bold bg-[#B71920]/10 text-[#B71920] px-2 py-0.5 rounded-full border border-[#B71920]/20 flex items-center gap-1 select-none">
                    {PIPELINE.find(a => a.name === selectedAgent)?.label}
                    <button onClick={() => setSelectedAgent(null)} className="ml-1 hover:text-red-500 font-bold">×</button>
                  </span>
                )}
              </div>
              <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{filteredRuns.length} runs logged</span>
            </div>
            {loading ? (
              <div className="flex justify-center py-12">
                <RefreshCw className="h-6 w-6 animate-spin text-[#B71920]" />
              </div>
            ) : filteredRuns.length === 0 ? (
              <div className="text-center py-16">
                <Bot className="mx-auto text-gray-200 mb-3 h-8 w-8" />
                <p className="text-xs font-bold text-gray-450">No agent runs recorded yet</p>
                <p className="text-[10px] text-gray-400 font-semibold mt-1">Runs appear here as you run the AI actions across the platform</p>
              </div>
            ) : (
              <div className="divide-y divide-gray-100 max-h-96 overflow-y-auto">
                {filteredRuns.slice(0, 100).map((run) => (
                  <RunHistoryRow key={run.id} run={run} onSelect={() => {}} />
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

export default function AgentWorkflowPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-gray-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-[#B71920] mr-2" />
        Loading Agent Workflow...
      </div>
    }>
      <AgentWorkflowContent />
    </Suspense>
  );
}
