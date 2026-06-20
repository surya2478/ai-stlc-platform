"use client";

import { useState, useEffect, useCallback, useMemo, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { reportsApi, projectsApi, type Project, type Report } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  BarChart3, Bot, CheckCircle, ChevronDown, ChevronUp,
  AlertTriangle, TrendingUp, Shield, Lightbulb, RefreshCw, X, Loader2
} from "lucide-react";

// Status Chip Variant Mapping
function getStatusVariant(status: string | null | undefined): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  if (!status) return "outline";
  const s = status.toLowerCase();
  if (["approved", "completed", "yes", "sprint"].includes(s)) return "success";
  if (["rejected", "no", "critical", "release"].includes(s)) return "destructive";
  if (["pending_approval", "running", "queued", "weekly"].includes(s)) return "warning";
  if (["daily"].includes(s)) return "info";
  return "outline";
}

function ProgressBar({ value, max, color = "bg-[#1b59f8]" }: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.min(100, Math.round(value / max * 100)) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden border">
        <div className={cn("h-full rounded-full transition-all duration-500", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] font-bold text-slate-500 w-8 text-right shrink-0">{pct}%</span>
    </div>
  );
}

function GridSection({ title, icon: Icon, iconColor, children }: {
  title: string; icon: React.ElementType; iconColor: string; children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4 shadow-sm">
      <div className="flex items-center gap-2">
        <Icon className={cn("h-4.5 w-4.5", iconColor)} />
        <h4 className="font-bold text-slate-800 text-xs">{title}</h4>
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function ReportRow({ report }: { report: Report }) {
  const [expanded, setExpanded] = useState(false);

  const cov = report.coverage || {};
  const exec = report.execution_metrics || {};
  const def = report.defect_metrics || {};

  return (
    <div className={cn(
      "bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden transition-all duration-200 hover:border-slate-350",
      expanded && "ring-1 ring-[#1b59f8]/10"
    )}>
      <div
        className="p-4 flex items-start justify-between gap-3 cursor-pointer hover:bg-slate-50/50"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            <span className="text-[10px] font-mono font-bold text-slate-400">{report.report_id}</span>
            <Badge variant={getStatusVariant(report.report_type)} className="uppercase py-0 text-[9px]">
              {report.report_type}
            </Badge>
            <span className="text-[10px] text-slate-400 font-bold">{new Date(report.created_at).toLocaleString()}</span>
          </div>
          <h4 className="text-xs font-bold text-slate-800 leading-snug">{report.title}</h4>
          {report.summary && !expanded && (
            <p className="text-[11px] text-slate-500 mt-1 line-clamp-1">{report.summary}</p>
          )}
        </div>
        <span className="text-slate-400 shrink-0 self-center">
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </span>
      </div>

      {expanded && (
        <div className="border-t border-slate-100 p-5 space-y-5 bg-slate-50/30">
          {/* Executive Summary */}
          {report.summary && (
            <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-1.5 shadow-sm">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Executive Summary</label>
              <p className="text-xs text-slate-700 leading-relaxed font-semibold">{report.summary}</p>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Coverage */}
            <GridSection title="Test Coverage Summary" icon={Shield} iconColor="text-blue-500">
              {cov.requirements_total !== undefined && (
                <div>
                  <div className="flex justify-between text-[10px] font-semibold text-slate-500 mb-1">
                    <span>Requirements Spec Coverage</span>
                    <span className="font-bold text-slate-700">{cov.requirements_approved ?? 0} / {cov.requirements_total ?? 0}</span>
                  </div>
                  <ProgressBar value={Number(cov.requirements_approved ?? 0)} max={Number(cov.requirements_total ?? 1)} color="bg-blue-500" />
                </div>
              )}
              {cov.test_cases_total !== undefined && (
                <div>
                  <div className="flex justify-between text-[10px] font-semibold text-slate-500 mb-1">
                    <span>Test Cases Approval Gate</span>
                    <span className="font-bold text-slate-700">{cov.test_cases_approved ?? 0} / {cov.test_cases_total ?? 0}</span>
                  </div>
                  <ProgressBar value={Number(cov.test_cases_approved ?? 0)} max={Number(cov.test_cases_total ?? 1)} color="bg-purple-500" />
                </div>
              )}
              {cov.automation_coverage_pct !== undefined && (
                <div>
                  <div className="flex justify-between text-[10px] font-semibold text-slate-500 mb-1">
                    <span>Automation Coverage Rate</span>
                    <span className="font-bold text-slate-700">{cov.automation_coverage_pct}%</span>
                  </div>
                  <ProgressBar value={Number(cov.automation_coverage_pct ?? 0)} max={100} color="bg-violet-500" />
                </div>
              )}
            </GridSection>

            {/* Execution */}
            <GridSection title="Execution Metrics Pipeline" icon={TrendingUp} iconColor="text-emerald-500">
              <div className="space-y-2 text-xs font-semibold">
                {Object.entries(exec).map(([k, v]) => (
                  <div key={k} className="flex justify-between border-b border-slate-50 pb-1.5 last:border-b-0 last:pb-0">
                    <span className="text-[10px] text-slate-500 capitalize">{k.replace(/_/g, " ")}</span>
                    <span className="text-slate-800 font-bold">{String(v)}</span>
                  </div>
                ))}
              </div>
            </GridSection>

            {/* Defects */}
            <GridSection title="Defect Distribution" icon={AlertTriangle} iconColor="text-rose-500">
              <div className="space-y-2 text-xs font-semibold">
                {Object.entries(def).map(([k, v]) => (
                  <div key={k} className="flex justify-between border-b border-slate-50 pb-1.5 last:border-b-0 last:pb-0">
                    <span className="text-[10px] text-slate-500 capitalize">{k.replace(/_/g, " ")}</span>
                    <span className="text-slate-800 font-bold">{String(v)}</span>
                  </div>
                ))}
              </div>
            </GridSection>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Risks */}
            {report.risks && report.risks.length > 0 && (
              <GridSection title="Identified QA Risks & Blockers" icon={AlertTriangle} iconColor="text-amber-500">
                <ul className="space-y-2 text-xs font-semibold text-slate-600">
                  {report.risks.map((r, i) => (
                    <li key={i} className="flex items-start gap-2.5 bg-amber-50/20 border border-amber-100/50 rounded-lg p-2.5">
                      <span className="text-amber-500 font-bold mt-0.5 select-none">▲</span>
                      <span className="leading-relaxed">{r}</span>
                    </li>
                  ))}
                </ul>
              </GridSection>
            )}
            {/* Recommendations */}
            {report.recommendations && report.recommendations.length > 0 && (
              <GridSection title="Strategic Quality Recommendations" icon={Lightbulb} iconColor="text-yellow-500">
                <ul className="space-y-2 text-xs font-semibold text-slate-600">
                  {report.recommendations.map((r, i) => (
                    <li key={i} className="flex items-start gap-2.5 bg-yellow-50/20 border border-yellow-100/50 rounded-lg p-2.5">
                      <span className="text-yellow-500 font-bold mt-0.5 select-none">→</span>
                      <span className="leading-relaxed">{r}</span>
                    </li>
                  ))}
                </ul>
              </GridSection>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ReportsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProject = Number(searchParams.get("project")) || null;

  const [projects, setProjects] = useState<Project[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [agentError, setAgentError] = useState<string | null>(null);
  const [reportType, setReportType] = useState<string>("sprint");

  // Load Projects on mount
  useEffect(() => {
    projectsApi.list()
      .then((res) => {
        setProjects(res.data);
        if (res.data.length > 0 && !searchParams.get("project")) {
          const params = new URLSearchParams(searchParams.toString());
          params.set("project", String(res.data[0].id));
          router.push(`${pathname}?${params.toString()}`);
        }
      })
      .catch(() => console.error("Could not load projects."));
  }, [searchParams]);

  // Load Reports list
  const loadReports = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const res = await reportsApi.list(selectedProject);
      setReports(res.data);
    } catch {
      console.error("Could not load reports list.");
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  // Reset page when project changes
  useEffect(() => {
    setAgentStatus("idle");
    setAgentError(null);
  }, [selectedProject]);

  const handleGenerate = async () => {
    if (!selectedProject) return;
    setAgentStatus("running");
    setAgentError(null);
    try {
      await reportsApi.generate(selectedProject, reportType);
      setAgentStatus("done");
      await loadReports();
    } catch (e: unknown) {
      setAgentStatus("error");
      const err = e as { response?: { data?: { detail?: string } } };
      setAgentError(err?.response?.data?.detail ?? "Agent report compilation failed");
    }
  };

  const latest = reports[0];

  const stats = useMemo(() => {
    if (!latest) return [];
    const openDef = latest.defect_metrics?.open ?? latest.defect_metrics?.open_defects ?? 0;
    const passRate = latest.execution_metrics?.latest_pass_pct ?? 0;
    const autoCov = latest.coverage?.automation_coverage_pct ?? 0;

    return [
      {
        title: "Total Reports",
        icon: BarChart3,
        iconBg: "bg-blue-50 border-blue-100",
        iconColor: "text-blue-500",
        value: reports.length.toLocaleString(),
        sublabel: "Reports",
        footer: "Historical compiled analytics reports",
      },
      {
        title: "Latest Pass Rate",
        icon: TrendingUp,
        iconBg: "bg-emerald-50 border-emerald-100",
        iconColor: "text-emerald-500",
        value: `${passRate}%`,
        sublabel: "Pass Rate",
        footer: "Gate compliance metric in last cycle",
      },
      {
        title: "Open Defects",
        icon: AlertTriangle,
        iconBg: "bg-red-50 border-red-100",
        iconColor: "text-red-500",
        value: openDef.toLocaleString(),
        sublabel: "Defects",
        footer: "Active open items on dashboard boards",
      },
      {
        title: "Automation Coverage",
        icon: Bot,
        iconBg: "bg-purple-50 border-purple-100",
        iconColor: "text-purple-500",
        value: `${autoCov}%`,
        sublabel: "Coverage",
        footer: "Automated scripts coverage percentage",
      },
    ];
  }, [reports, latest]);

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Global Controls ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-blue-50 border border-blue-100 p-2.5">
            <BarChart3 className="h-6 w-6 text-[#1b59f8]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Reports & Analytics</h1>
            <p className="text-xs text-slate-500 mt-1">Compile sprint quality metrics, analyse risks, and view coverage health trends (Agent 11)</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedProject ?? ""}
            onChange={(e) => {
              const val = e.target.value;
              const params = new URLSearchParams(searchParams.toString());
              params.set("project", val);
              router.push(`${pathname}?${params.toString()}`);
            }}
            className="appearance-none bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 rounded-lg text-xs font-semibold px-3 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-[#1b59f8] transition-colors cursor-pointer"
            style={{
              backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
              backgroundPosition: 'right 0.5rem center',
              backgroundSize: '1.25rem 1.25rem',
              backgroundRepeat: 'no-repeat',
            }}
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>

          <select
            value={reportType}
            onChange={(e) => setReportType(e.target.value)}
            className="appearance-none bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 rounded-lg text-xs font-semibold px-3 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-[#1b59f8] transition-colors cursor-pointer"
            style={{
              backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
              backgroundPosition: 'right 0.5rem center',
              backgroundSize: '1.25rem 1.25rem',
              backgroundRepeat: 'no-repeat',
            }}
          >
            {["daily", "weekly", "sprint", "release"].map((t) => (
              <option key={t} value={t}>{t.toUpperCase()} REPORT</option>
            ))}
          </select>

          <Button
            variant="default"
            size="sm"
            disabled={agentStatus === "running"}
            onClick={handleGenerate}
            className="h-8 text-xs font-semibold"
          >
            {agentStatus === "running" ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1 text-white" />
                Compiling...
              </>
            ) : (
              <>
                <Bot className="h-3.5 w-3.5 mr-1 text-white" />
                Generate Report
              </>
            )}
          </Button>
        </div>
      </div>

      {agentError && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="flex-1 font-semibold">{agentError}</span>
          <button onClick={() => setAgentError(null)}><X className="h-4 w-4 text-red-400 hover:text-red-700" /></button>
        </div>
      )}

      {/* ── Status Counts Cards ─────────────────────────────────────────────────── */}
      {latest && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {stats.map((card) => {
            const Icon = card.icon;
            return (
              <Card key={card.title} className="border-slate-200 hover:-translate-y-0.5 transition-all">
                <CardContent className="p-4 flex flex-col justify-between h-full space-y-3">
                  <div className="flex items-center gap-2">
                    <div className={cn("rounded-lg p-1.5 flex items-center justify-center shrink-0 border", card.iconBg)}>
                      <Icon className={cn("h-4 w-4", card.iconColor)} />
                    </div>
                    <span className="text-xs font-bold text-slate-700 truncate">{card.title}</span>
                  </div>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-xl font-bold text-slate-900">{card.value}</span>
                    {card.sublabel && (
                      <span className="text-[10px] font-bold text-slate-400">{card.sublabel}</span>
                    )}
                  </div>
                  <div className="text-[10px] text-slate-400 font-semibold border-t border-slate-50 pt-2">
                    {card.footer}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* ── Reports catalog list ───────────────────────────────────────────────── */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-16 text-slate-400 text-xs font-semibold">
          <Loader2 className="h-6 w-6 animate-spin text-[#1b59f8] mb-2" />
          Loading reports ledger...
        </div>
      ) : reports.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-dashed border-slate-250">
          <BarChart3 className="h-10 w-10 text-slate-300 mx-auto mb-2" />
          <p className="text-xs text-slate-500 font-bold">No reports generated yet</p>
          <p className="text-[10px] text-slate-400 font-semibold mt-1">Select project and type above, then click Generate Report to run AI analysis</p>
        </div>
      ) : (
        <div className="space-y-3">
          {reports.map((r) => <ReportRow key={r.id} report={r} />)}
        </div>
      )}
    </div>
  );
}

export default function ReportsPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-slate-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-[#1b59f8] mr-2" />
        Loading Reports Center...
      </div>
    }>
      <ReportsContent />
    </Suspense>
  );
}
