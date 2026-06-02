"use client";
import { useState, useEffect, useCallback } from "react";
import { reportsApi, projectsApi, type Project, type Report } from "@/lib/api";
import {
  BarChart3, Bot, CheckCircle, ChevronDown, ChevronUp,
  AlertTriangle, TrendingUp, Shield, Lightbulb, RefreshCw,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

// ── Helpers ───────────────────────────────────────────────────────────────────

function MetricCard({ label, value, unit = "", color = "text-gray-800" }: {
  label: string; value: number | string; unit?: string; color?: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
      <p className={`text-2xl font-bold ${color}`}>{value}{unit}</p>
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
    </div>
  );
}

function ProgressBar({ value, max, color = "bg-blue-500" }: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.min(100, Math.round(value / max * 100)) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-semibold text-gray-600 w-10 text-right">{pct}%</span>
    </div>
  );
}

function Section({ title, icon: Icon, iconClass, children }: {
  title: string; icon: React.ElementType; iconClass: string; children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
      <div className="flex items-center gap-2 mb-4">
        <Icon size={16} className={iconClass} />
        <h3 className="font-semibold text-gray-800 text-sm">{title}</h3>
      </div>
      {children}
    </div>
  );
}

function ReportCard({ report }: { report: Report }) {
  const [expanded, setExpanded] = useState(false);

  const badgeColor: Record<string, string> = {
    daily: "bg-blue-100 text-blue-700",
    weekly: "bg-violet-100 text-violet-700",
    sprint: "bg-green-100 text-green-700",
    release: "bg-orange-100 text-orange-700",
  };

  const cov = report.coverage || {};
  const exec = report.execution_metrics || {};
  const def = report.defect_metrics || {};

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div
        className="p-4 flex items-start gap-3 cursor-pointer hover:bg-gray-50"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="text-xs font-mono text-gray-400">{report.report_id}</span>
            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${badgeColor[report.report_type] ?? "bg-gray-100 text-gray-600"}`}>
              {report.report_type}
            </span>
            <span className="text-xs text-gray-400">{new Date(report.created_at).toLocaleString()}</span>
          </div>
          <p className="text-sm font-semibold text-gray-800">{report.title}</p>
          {report.summary && (
            <p className="text-xs text-gray-500 mt-1 line-clamp-2">{report.summary}</p>
          )}
        </div>
        <span className="text-gray-400 shrink-0">{expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</span>
      </div>

      {expanded && (
        <div className="border-t border-gray-100 p-5 space-y-5 bg-gray-50">
          {/* Summary */}
          {report.summary && (
            <div className="bg-white rounded-lg border border-gray-100 p-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Executive Summary</p>
              <p className="text-sm text-gray-700 leading-relaxed">{report.summary}</p>
            </div>
          )}

          <div className="grid grid-cols-3 gap-4">
            {/* Coverage */}
            <Section title="Test Coverage" icon={Shield} iconClass="text-blue-500">
              <div className="space-y-3">
                {cov.requirements_total !== undefined && (
                  <div>
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>Requirements approved</span>
                      <span>{cov.requirements_approved ?? 0}/{cov.requirements_total ?? 0}</span>
                    </div>
                    <ProgressBar value={Number(cov.requirements_approved ?? 0)} max={Number(cov.requirements_total ?? 1)} color="bg-blue-500" />
                  </div>
                )}
                {cov.test_cases_total !== undefined && (
                  <div>
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>Test cases approved</span>
                      <span>{cov.test_cases_approved ?? 0}/{cov.test_cases_total ?? 0}</span>
                    </div>
                    <ProgressBar value={Number(cov.test_cases_approved ?? 0)} max={Number(cov.test_cases_total ?? 1)} color="bg-purple-500" />
                  </div>
                )}
                {cov.automation_coverage_pct !== undefined && (
                  <div>
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>Automation coverage</span>
                      <span>{cov.automation_coverage_pct}%</span>
                    </div>
                    <ProgressBar value={Number(cov.automation_coverage_pct ?? 0)} max={100} color="bg-violet-500" />
                  </div>
                )}
              </div>
            </Section>

            {/* Execution */}
            <Section title="Execution Metrics" icon={TrendingUp} iconClass="text-green-500">
              <div className="space-y-2 text-sm">
                {Object.entries(exec).map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-xs text-gray-500 capitalize">{k.replace(/_/g, " ")}</span>
                    <span className="text-xs font-semibold text-gray-700">{String(v)}</span>
                  </div>
                ))}
              </div>
            </Section>

            {/* Defects */}
            <Section title="Defect Metrics" icon={AlertTriangle} iconClass="text-red-500">
              <div className="space-y-2">
                {Object.entries(def).map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-xs text-gray-500 capitalize">{k.replace(/_/g, " ")}</span>
                    <span className="text-xs font-semibold text-gray-700">{String(v)}</span>
                  </div>
                ))}
              </div>
            </Section>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* Risks */}
            {report.risks && report.risks.length > 0 && (
              <Section title="Identified Risks" icon={AlertTriangle} iconClass="text-amber-500">
                <ul className="space-y-2">
                  {report.risks.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-gray-600">
                      <span className="text-amber-400 mt-0.5 shrink-0">▲</span>
                      {r}
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {/* Recommendations */}
            {report.recommendations && report.recommendations.length > 0 && (
              <Section title="Recommendations" icon={Lightbulb} iconClass="text-yellow-500">
                <ul className="space-y-2">
                  {report.recommendations.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-gray-600">
                      <span className="text-yellow-400 mt-0.5 shrink-0">→</span>
                      {r}
                    </li>
                  ))}
                </ul>
              </Section>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ReportsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [agentError, setAgentError] = useState<string | null>(null);
  const [reportType, setReportType] = useState<string>("sprint");

  useEffect(() => {
    projectsApi.list()
      .then((r) => {
        setProjects(r.data);
        const _urlP = typeof window !== "undefined" ? Number(new URLSearchParams(window.location.search).get("project")) || null : null;
        setSelectedProject(_urlP ?? (r.data[0]?.id ?? null));
      })
      .catch((e) => console.error("[Projects] Failed to load:", e?.response?.status));
  }, []);

  const loadReports = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const res = await reportsApi.list(selectedProject);
      setReports(res.data);
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => { loadReports(); }, [loadReports]);

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
      setAgentError(err?.response?.data?.detail ?? "Agent failed");
    }
  };

  const latest = reports[0];

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-emerald-100 rounded-lg">
            <BarChart3 size={22} className="text-emerald-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Reports & Analytics</h1>
            <p className="text-sm text-gray-500">AI-generated QA status reports with coverage metrics — Agent 11</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedProject ?? ""}
            onChange={(e) => setSelectedProject(Number(e.target.value))}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-300"
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <select
            value={reportType}
            onChange={(e) => setReportType(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-300"
          >
            {["daily", "weekly", "sprint", "release"].map((t) => (
              <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
            ))}
          </select>
          <button
            onClick={handleGenerate}
            disabled={agentStatus === "running"}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 disabled:opacity-50"
          >
            {agentStatus === "running" ? (
              <><span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" /> Generating...</>
            ) : (
              <><Bot size={16} /> Generate Report</>
            )}
          </button>
          {agentStatus === "error" && (
            <span className="flex items-center gap-1 text-xs text-red-600">
              <AlertTriangle size={14} /> {agentError}
            </span>
          )}
        </div>
      </div>

      {/* Quick stats from latest report */}
      {latest && (
        <div className="grid grid-cols-4 gap-4">
          <MetricCard label="Total Reports" value={reports.length} color="text-gray-800" />
          <MetricCard
            label="Latest Pass Rate"
            value={latest.execution_metrics?.latest_pass_pct ?? 0}
            unit="%"
            color={Number(latest.execution_metrics?.latest_pass_pct ?? 0) >= 80 ? "text-green-600" : "text-yellow-600"}
          />
          <MetricCard
            label="Open Defects"
            value={latest.defect_metrics?.open ?? latest.defect_metrics?.open_defects ?? 0}
            color="text-red-500"
          />
          <MetricCard
            label="Automation Coverage"
            value={latest.coverage?.automation_coverage_pct ?? 0}
            unit="%"
            color="text-violet-600"
          />
        </div>
      )}

      {/* Reports list */}
      {loading ? (
        <div className="flex justify-center py-12">
          <span className="animate-spin w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full" />
        </div>
      ) : reports.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-xl border border-gray-100">
          <BarChart3 size={40} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500 font-medium">No reports generated yet</p>
          <p className="text-sm text-gray-400 mt-1">
            Click "Generate Report" to have Agent 11 analyse all project metrics and write a QA status report
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {reports.map((r) => <ReportCard key={r.id} report={r} />)}
        </div>
      )}
    </div>
  );
}
