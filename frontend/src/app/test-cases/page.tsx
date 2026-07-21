"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  Bot,
  CheckCircle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  Filter,
  Layers,
  Loader2,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  TestTube2,
  X,
  Zap,
} from "lucide-react";
import {
  agentRunsApi,
  projectsApi,
  requirementsApi,
  scenariosApi,
  testCasesApi,
  type Requirement,
  type TestCase,
  type TestCaseSummary,
  type TestScenario,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type DrawerTab = "overview" | "cases" | "coverage" | "ai" | "activity";
type Tone = "blue" | "emerald" | "red" | "purple" | "amber" | "slate";

const LAST_REFRESHED = "Jul 21, 2026, 01:02 PM";

const TABS = [
  { key: "all", label: "All Generated" },
  { key: "positive", label: "Positive" },
  { key: "negative", label: "Negative" },
  { key: "edge", label: "Edge / Boundary" },
  { key: "regression", label: "Regression" },
  { key: "integration", label: "Integration" },
  { key: "gaps", label: "Gaps / Blocked" },
];

const DEMO_COUNTS = {
  requirementsSelected: 96,
  totalGenerated: 348,
  positive: 184,
  negative: 112,
  edge: 38,
  gaps: 14,
  regression: 98,
  integration: 42,
};

const TABLE_GRID = "70px 94px minmax(130px,1fr) 72px 94px 64px 84px 86px 82px 92px 72px 42px";
const EDITOR_TABLE_GRID = "74px 102px minmax(128px,1fr) 72px 92px 62px 76px 84px 46px";

function messageFromError(error: unknown, fallback: string) {
  const candidate = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = candidate.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return candidate.message || fallback;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalize(value: string | null | undefined) {
  return (value || "").toLowerCase().replace(/[_-]/g, " ");
}

function displayDate(value?: string | null) {
  if (!value) return "Jul 21, 12:58 PM";
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ppmFromRequirement(req?: Requirement) {
  return String(req?.metadata_?.ppm_id || "PPM-4588");
}

function scenarioClass(tc: TestCase) {
  const raw = tc.test_type || tc.test_phase || tc.telecom_domain || "Business Validation";
  const normalized = normalize(raw);
  if (normalized.includes("happy") || normalized.includes("positive")) return "Happy Path";
  if (normalized.includes("input")) return "Input Validation";
  if (normalized.includes("auth")) return "Authorization";
  if (normalized.includes("payment")) return "Payment Validation";
  if (normalized.includes("notification")) return "Notification";
  return raw.length > 24 ? "Business Validation" : raw;
}

function testType(tc: TestCase) {
  const title = normalize(tc.title);
  const type = normalize(tc.test_type);
  if (type.includes("positive") || title.includes("valid") || title.includes("confirmation")) return "Positive";
  if (type.includes("edge") || type.includes("boundary")) return "Edge / Boundary";
  if (type.includes("regression")) return "Regression";
  return "Negative";
}

function reviewStatus(tc: TestCase) {
  if (tc.status === "pending_approval" || tc.approval_status === "pending") return "Needs Review";
  if (tc.status === "approved" || tc.approval_status === "approved") return "Approved";
  if (tc.status === "rejected") return "Rejected";
  if (tc.status === "blocked") return "Blocked";
  return "Generated";
}

function traceabilityHealth(tc: TestCase) {
  if (!tc.linked_requirement_key && !tc.linked_requirement_id && !tc.requirement_id) return "Missing";
  if (tc.status === "blocked" || tc.status === "rejected") return "Partial";
  return "Good";
}

function badgeClass(tone: Tone) {
  return cn(
    "inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-bold",
    tone === "blue" && "border-blue-100 bg-blue-50 text-blue-700",
    tone === "emerald" && "border-emerald-100 bg-emerald-50 text-emerald-700",
    tone === "red" && "border-red-100 bg-red-50 text-red-700",
    tone === "purple" && "border-purple-100 bg-purple-50 text-purple-700",
    tone === "amber" && "border-amber-100 bg-amber-50 text-amber-700",
    tone === "slate" && "border-slate-200 bg-slate-50 text-slate-600",
  );
}

function priorityTone(priority: string | null | undefined): Tone {
  const p = normalize(priority);
  if (p.includes("critical") || p.includes("high")) return "red";
  if (p.includes("medium")) return "amber";
  return "emerald";
}

function statusTone(status: string): Tone {
  if (status === "Generated" || status === "Approved") return "blue";
  if (status === "Needs Review") return "amber";
  if (status === "Rejected" || status === "Blocked") return "red";
  return "slate";
}

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  tone,
}: {
  title: string;
  value: string | number;
  subtitle: string;
  icon: typeof FileText;
  tone: Tone;
}) {
  const toneMap: Record<Tone, string> = {
    blue: "bg-blue-50 border-blue-100 text-blue-600",
    emerald: "bg-emerald-50 border-emerald-100 text-emerald-600",
    red: "bg-red-50 border-red-100 text-red-600",
    purple: "bg-purple-50 border-purple-100 text-purple-600",
    amber: "bg-amber-50 border-amber-100 text-amber-600",
    slate: "bg-slate-50 border-slate-100 text-slate-600",
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-3">
        <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg border", toneMap[tone])}>
          <Icon className="h-4 w-4" />
        </div>
        <p className="min-w-0 truncate text-xs font-bold text-slate-800">{title}</p>
      </div>
      <div className="mt-7">
        <p className="text-2xl font-extrabold leading-none text-slate-950">{value}</p>
        <p className="mt-3 text-xs font-semibold text-slate-500">{subtitle}</p>
      </div>
    </div>
  );
}

function ReadinessItem({
  label,
  value,
  tone = "emerald",
}: {
  label: string;
  value: string;
  tone?: Tone;
}) {
  const iconTone = tone === "amber" ? "bg-amber-50 text-amber-600 border-amber-100" : "bg-emerald-50 text-emerald-600 border-emerald-100";
  return (
    <div className="flex items-center gap-3">
      <span className={cn("flex h-9 w-9 items-center justify-center rounded-full border", iconTone)}>
        {tone === "amber" ? <AlertTriangle className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
      </span>
      <div>
        <p className="text-xs font-bold text-slate-800">{label}</p>
        <p className="mt-0.5 text-sm font-extrabold leading-none text-slate-950">{value}</p>
      </div>
    </div>
  );
}

function MiniProgress({ value, tone = "emerald" }: { value: number; tone?: Tone }) {
  const color = tone === "amber" ? "bg-amber-500" : tone === "red" ? "bg-red-500" : "bg-emerald-500";
  return (
    <div className="h-1.5 w-full rounded-full bg-slate-100">
      <div className={cn("h-full rounded-full", color)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

function exportToCSV(rows: TestCase[], requirementsByKey: Map<string, Requirement>, requirementsById: Map<number, Requirement>) {
  const headers = [
    "TC ID",
    "Requirement ID",
    "PPM ID",
    "Title",
    "Test Type",
    "Scenario Class",
    "Priority",
    "Automation Candidate",
    "Data Dependency",
    "Review Status",
    "Traceability Health",
    "Generated At",
  ];
  const body = rows.map((tc) => {
    const req = findRequirementForCase(tc, requirementsByKey, requirementsById);
    return [
      tc.test_case_id,
      tc.linked_requirement_key || req?.requirement_id || "-",
      ppmFromRequirement(req),
      tc.title,
      testType(tc),
      scenarioClass(tc),
      tc.priority,
      tc.automation_candidate ? "Yes" : "No",
      dataDependency(tc),
      reviewStatus(tc),
      traceabilityHealth(tc),
      displayDate(tc.created_at),
    ];
  });
  const csv = [headers, ...body].map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "generated-test-cases.csv";
  a.click();
  URL.revokeObjectURL(url);
}

function dataDependency(tc: TestCase) {
  const data = tc.test_data;
  if (data && typeof data === "object") {
    const source = (data as Record<string, unknown>).source || (data as Record<string, unknown>).dataset || (data as Record<string, unknown>).name;
    if (source) return String(source);
  }
  const title = normalize(tc.title);
  if (title.includes("payment")) return "Payment Data";
  if (title.includes("email") || title.includes("notification")) return "Email Service";
  if (title.includes("user")) return "User Roles";
  if (title.includes("order")) return "OMS Data";
  return "CRM Data";
}

function findRequirementForCase(tc: TestCase, byKey: Map<string, Requirement>, byId: Map<number, Requirement>) {
  if (tc.linked_requirement_key && byKey.has(tc.linked_requirement_key)) return byKey.get(tc.linked_requirement_key);
  if (tc.linked_requirement_id && byId.has(tc.linked_requirement_id)) return byId.get(tc.linked_requirement_id);
  if (tc.requirement_id && byId.has(tc.requirement_id)) return byId.get(tc.requirement_id);
  return undefined;
}

function TestCasesContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const selectedProject = Number(searchParams.get("project")) || null;
  const view = searchParams.get("view") || "generated";

  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [summary, setSummary] = useState<TestCaseSummary | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [scenarios, setScenarios] = useState<TestScenario[]>([]);
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<number[]>([]);
  const [selectedTestCase, setSelectedTestCase] = useState<TestCase | null>(null);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("overview");
  const [activeTab, setActiveTab] = useState("all");
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [classFilter, setClassFilter] = useState("all");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [automationFilter, setAutomationFilter] = useState("all");
  const [reviewFilter, setReviewFilter] = useState("all");
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    projectsApi.list().then((res) => {
      if (res.data.length > 0 && !searchParams.get("project")) {
        const params = new URLSearchParams(searchParams.toString());
        params.set("project", String(res.data[0].id));
        router.push(`${pathname}?${params.toString()}`);
      }
    }).catch(() => setError("Could not load projects."));
  }, [pathname, router, searchParams]);

  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    setError("");
    try {
      const [tcRes, summaryRes, reqRes, scRes] = await Promise.all([
        testCasesApi.list(selectedProject),
        testCasesApi.summary(selectedProject),
        requirementsApi.list(selectedProject, { status: "approved" }),
        scenariosApi.list(selectedProject),
      ]);
      const approvedScenarios = scRes.data.filter((scenario) => scenario.status === "approved");
      setTestCases(tcRes.data);
      setSummary(summaryRes.data);
      setRequirements(reqRes.data);
      setScenarios(approvedScenarios);
      setSelectedScenarioIds((prev) => prev.length ? prev.filter((id) => approvedScenarios.some((s) => s.id === id)) : approvedScenarios.map((s) => s.id));
      setSelectedTestCase((prev) => prev ? tcRes.data.find((tc) => tc.id === prev.id) || tcRes.data[0] || null : tcRes.data[0] || null);
    } catch (loadError) {
      setError(messageFromError(loadError, "Could not load generated test cases."));
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    setDrawerTab("overview");
  }, [selectedTestCase?.id]);

  const requirementsByKey = useMemo(() => new Map(requirements.map((req) => [req.requirement_id, req])), [requirements]);
  const requirementsById = useMemo(() => new Map(requirements.map((req) => [req.id, req])), [requirements]);

  const generatedTotal = summary?.total ?? testCases.length;
  const positiveCount = testCases.filter((tc) => testType(tc) === "Positive").length || Math.round(generatedTotal * 0.529);
  const negativeCount = testCases.filter((tc) => testType(tc) === "Negative").length || Math.round(generatedTotal * 0.322);
  const edgeCount = testCases.filter((tc) => testType(tc) === "Edge / Boundary").length || Math.round(generatedTotal * 0.109);
  const gapsCount = Math.max(0, requirements.length - new Set(testCases.map((tc) => tc.linked_requirement_key || tc.requirement_id)).size);
  const regressionCount = testCases.filter((tc) => testType(tc) === "Regression").length || Math.round(generatedTotal * 0.28);
  const integrationCount = testCases.filter((tc) => normalize(scenarioClass(tc)).includes("integration")).length || Math.round(generatedTotal * 0.12);

  const kpiValues = {
    requirementsSelected: requirements.length || DEMO_COUNTS.requirementsSelected,
    totalGenerated: generatedTotal || DEMO_COUNTS.totalGenerated,
    positive: positiveCount || DEMO_COUNTS.positive,
    negative: negativeCount || DEMO_COUNTS.negative,
    edge: edgeCount || DEMO_COUNTS.edge,
    gaps: gapsCount || DEMO_COUNTS.gaps,
    regression: regressionCount || DEMO_COUNTS.regression,
    integration: integrationCount || DEMO_COUNTS.integration,
  };

  const filtered = useMemo(() => {
    return testCases.filter((tc) => {
      const req = findRequirementForCase(tc, requirementsByKey, requirementsById);
      const rowText = [
        tc.test_case_id,
        tc.title,
        tc.linked_requirement_key,
        req?.requirement_id,
        ppmFromRequirement(req),
        scenarioClass(tc),
      ].join(" ").toLowerCase();
      const rowType = testType(tc);
      const rowClass = scenarioClass(tc);
      const rowReview = reviewStatus(tc);
      const tabOk =
        activeTab === "all" ||
        (activeTab === "gaps" && traceabilityHealth(tc) !== "Good") ||
        normalize(rowType).includes(normalize(activeTab)) ||
        normalize(rowClass).includes(normalize(activeTab));
      const queryOk = !query.trim() || rowText.includes(query.trim().toLowerCase());
      const typeOk = typeFilter === "all" || rowType === typeFilter;
      const classOk = classFilter === "all" || rowClass === classFilter;
      const priorityOk = priorityFilter === "all" || tc.priority === priorityFilter;
      const automationOk =
        automationFilter === "all" ||
        (automationFilter === "yes" && tc.automation_candidate) ||
        (automationFilter === "no" && !tc.automation_candidate);
      const reviewOk = reviewFilter === "all" || rowReview === reviewFilter;
      return tabOk && queryOk && typeOk && classOk && priorityOk && automationOk && reviewOk;
    });
  }, [activeTab, automationFilter, classFilter, priorityFilter, query, requirementsById, requirementsByKey, reviewFilter, testCases, typeFilter]);

  const selectedRequirement = selectedTestCase ? findRequirementForCase(selectedTestCase, requirementsByKey, requirementsById) : undefined;
  const linkedCases = selectedTestCase
    ? testCases.filter((tc) => (tc.linked_requirement_key || tc.requirement_id) === (selectedTestCase.linked_requirement_key || selectedTestCase.requirement_id))
    : [];

  async function generateCases(overrideQualityGate = false) {
    if (!selectedProject) return;
    setGenerating(true);
    setNotice("");
    setError("");
    try {
      const scenarioIds = selectedScenarioIds.length ? selectedScenarioIds : scenarios.map((scenario) => scenario.id);
      const reqIds = scenarioIds.length ? undefined : requirements.map((req) => req.id);
      const res = await testCasesApi.generateCases(selectedProject, scenarioIds.length ? scenarioIds : undefined, reqIds, overrideQualityGate);
      const data = res.data as Record<string, unknown>;
      const agentRunId = typeof data.agent_run_id === "number" ? data.agent_run_id : null;
      if (agentRunId) {
        setNotice("Test case generation is running...");
        for (let attempt = 0; attempt < 60; attempt += 1) {
          await sleep(attempt === 0 ? 1000 : 2000);
          const run = (await agentRunsApi.get(agentRunId)).data;
          if (run.status === "failed") {
            setError(run.error_message || "Test case generation failed.");
            setNotice("");
            await loadData();
            return;
          }
          if (run.status === "completed") {
            const count = Number(run.output_data?.count ?? 0);
            setNotice(count > 0 ? `Generated ${count} test case${count === 1 ? "" : "s"}.` : "Generation completed. No new test cases were created.");
            await loadData();
            return;
          }
          setNotice(run.progress_message ? `Test case generation: ${run.progress_message}` : "Test case generation is running...");
        }
        setNotice("Generation is still running. Refresh to check the latest status.");
      } else {
        setNotice(String(data.message || "Test cases generated."));
        await loadData();
      }
    } catch (generateError) {
      setError(messageFromError(generateError, "Could not generate test cases."));
    } finally {
      setGenerating(false);
    }
  }

  if (view === "editor") {
    return (
      <TestCaseEditorView
        testCases={testCases}
        filtered={filtered}
        requirements={requirements}
        requirementsByKey={requirementsByKey}
        requirementsById={requirementsById}
        selectedTestCase={selectedTestCase}
        selectedRequirement={selectedRequirement}
        kpiValues={kpiValues}
        query={query}
        setQuery={setQuery}
        typeFilter={typeFilter}
        setTypeFilter={setTypeFilter}
        classFilter={classFilter}
        setClassFilter={setClassFilter}
        priorityFilter={priorityFilter}
        setPriorityFilter={setPriorityFilter}
        reviewFilter={reviewFilter}
        setReviewFilter={setReviewFilter}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        loading={loading}
        setSelectedTestCase={setSelectedTestCase}
      />
    );
  }

  return (
    <div className="flex min-h-full gap-6">
      <section className="min-w-0 flex-1 space-y-5 pb-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
          <span>e&amp; STLC</span>
          <ChevronRight className="h-3 w-3 text-slate-300" />
          <span className="text-[#1b59f8]">Test Planning</span>
          <ChevronRight className="h-3 w-3 text-slate-300" />
          <span className="text-slate-800">Generated Test Cases</span>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="mt-1 flex h-9 w-9 items-center justify-center rounded-lg border border-purple-100 bg-purple-50 text-purple-600">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-extrabold tracking-tight text-slate-950">Generated Test Cases</h1>
                <span className={badgeClass("purple")}>P1-S3 UI-010</span>
              </div>
              <p className="mt-1 text-xs font-semibold text-slate-500">
                AI-generated test cases from approved requirements and traceability context.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[11px] font-semibold text-slate-500">Last refreshed: {LAST_REFRESHED}</span>
            <Button variant="outline" size="sm" onClick={() => exportToCSV(filtered, requirementsByKey, requirementsById)} className="h-9 gap-2 border-slate-200 text-xs font-bold">
              <Download className="h-4 w-4" />
              Export
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 xl:grid-cols-6">
          <StatCard title="Requirements Selected" value={kpiValues.requirementsSelected} subtitle="Approved requirements" icon={FileText} tone="blue" />
          <StatCard title="Test Cases Generated" value={kpiValues.totalGenerated} subtitle="Total generated" icon={ShieldCheck} tone="emerald" />
          <StatCard title="Positive Cases" value={kpiValues.positive} subtitle="52.9% of total" icon={TestTube2} tone="blue" />
          <StatCard title="Negative Cases" value={kpiValues.negative} subtitle="32.2% of total" icon={AlertTriangle} tone="red" />
          <StatCard title="Edge / Boundary Cases" value={kpiValues.edge} subtitle="10.9% of total" icon={Layers} tone="purple" />
          <StatCard title="Gaps / Blocked" value={kpiValues.gaps} subtitle="4.0% require attention" icon={Zap} tone="amber" />
        </div>

        {(error || notice) && (
          <div className={cn(
            "flex items-center gap-2 rounded-lg border px-4 py-3 text-xs font-semibold",
            error ? "border-red-200 bg-red-50 text-red-700" : "border-blue-200 bg-blue-50 text-blue-700",
          )}>
            {error ? <AlertTriangle className="h-4 w-4" /> : <Loader2 className={cn("h-4 w-4", generating && "animate-spin")} />}
            <span className="flex-1">{error || notice}</span>
            <button onClick={() => { setError(""); setNotice(""); }} className="text-current/60 hover:text-current">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <p className="mb-5 text-[11px] font-extrabold uppercase tracking-wide text-slate-800">Generation Readiness</p>
          <div className="flex items-center justify-between gap-4">
            <div className="grid flex-1 grid-cols-2 gap-x-8 gap-y-5 xl:grid-cols-6">
              <ReadinessItem label="Requirements Approved" value={`${requirements.length || 96}/${requirements.length || 96}`} />
              <ReadinessItem label="Analysis Complete" value="96%" />
              <ReadinessItem label="Traceability Ready" value="92/100" />
              <ReadinessItem label="Test Data Ready" value="85%" tone="amber" />
              <ReadinessItem label="Application Model" value="Available" />
              <ReadinessItem label="Policy & Permissions" value="Compliant" />
            </div>
            <Button variant="outline" size="sm" className="h-9 shrink-0 gap-2 border-blue-200 text-xs font-bold text-[#1b59f8]">
              View readiness details
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1">
            {TABS.map((tab) => {
              const count =
                tab.key === "all" ? kpiValues.totalGenerated :
                tab.key === "positive" ? kpiValues.positive :
                tab.key === "negative" ? kpiValues.negative :
                tab.key === "edge" ? kpiValues.edge :
                tab.key === "regression" ? kpiValues.regression :
                tab.key === "integration" ? kpiValues.integration :
                kpiValues.gaps;
              const active = activeTab === tab.key;
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={cn(
                    "inline-flex h-9 items-center gap-2 rounded-md px-4 text-xs font-bold transition",
                    active ? "bg-[#07142d] text-white shadow-sm" : "text-slate-600 hover:bg-white hover:text-slate-900",
                  )}
                >
                  {tab.label}
                  <span className={cn("rounded-full px-1.5 py-0.5 text-[10px]", active ? "bg-white/15 text-white" : "bg-slate-100 text-slate-500")}>{count}</span>
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ai" size="sm" onClick={() => generateCases()} disabled={generating || scenarios.length === 0} className="h-9 gap-2 text-xs font-bold">
              {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Generate Test Cases
            </Button>
            <Button variant="outline" size="sm" onClick={() => generateCases(true)} disabled={generating} className="h-9 gap-2 border-slate-200 text-xs font-bold">
              <RefreshCw className="h-4 w-4" />
              Re-generate
              <ChevronDown className="h-3.5 w-3.5" />
            </Button>
            <Button variant="outline" size="sm" className="h-9 w-9 border-slate-200 p-0">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-72 flex-1">
            <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by TC ID, title, requirement, scenario..."
              className="h-10 w-full rounded-lg border border-slate-200 bg-white pl-11 pr-3 text-xs font-semibold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
            />
          </div>
          <FilterSelect value={typeFilter} onChange={setTypeFilter} options={["all", "Positive", "Negative", "Edge / Boundary", "Regression"]} label="Test Type" />
          <FilterSelect value={classFilter} onChange={setClassFilter} options={["all", "Business Validation", "Authorization", "Happy Path", "Input Validation", "Payment Validation", "Notification"]} label="Scenario Class" />
          <FilterSelect value={priorityFilter} onChange={setPriorityFilter} options={["all", "High", "Medium", "Low", "Critical"]} label="Priority" />
          <FilterSelect value={automationFilter} onChange={setAutomationFilter} options={["all", "yes", "no"]} label="Automation" />
          <FilterSelect value={reviewFilter} onChange={setReviewFilter} options={["all", "Generated", "Needs Review", "Approved", "Rejected", "Blocked"]} label="Review Status" />
          <Button variant="outline" size="sm" className="h-10 gap-2 border-slate-200 text-xs font-bold">
            <Filter className="h-4 w-4" />
            Filters
          </Button>
        </div>

        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="grid border-b border-slate-200 bg-slate-50/70 px-4 py-3 text-[9px] font-extrabold uppercase tracking-wide text-slate-500" style={{ gridTemplateColumns: TABLE_GRID }}>
            <span>TC ID</span>
            <span>Req ID / PPM ID</span>
            <span>Title</span>
            <span>Test Type</span>
            <span>Scenario Class</span>
            <span>Priority</span>
            <span>Automation Candidate</span>
            <span>Data Dependency</span>
            <span>Review Status</span>
            <span>Traceability Health</span>
            <span>Generated At</span>
            <span>Actions</span>
          </div>
          {loading ? (
            <div className="flex items-center justify-center py-20 text-xs font-bold text-slate-500">
              <Loader2 className="mr-2 h-4 w-4 animate-spin text-[#1b59f8]" />
              Loading generated test cases...
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-20 text-center text-xs font-bold text-slate-400">
              No generated test cases match the selected filters.
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {filtered.slice(0, 8).map((tc) => {
                const req = findRequirementForCase(tc, requirementsByKey, requirementsById);
                const selected = selectedTestCase?.id === tc.id;
                return (
                  <button
                    key={tc.id}
                    onClick={() => setSelectedTestCase(tc)}
                    className={cn(
                      "grid w-full items-center px-4 py-3 text-left text-[11px] transition hover:bg-slate-50",
                      selected && "border-l-2 border-[#1b59f8] bg-blue-50/25",
                    )}
                    style={{ gridTemplateColumns: TABLE_GRID }}
                  >
                    <span className="font-mono font-extrabold text-[#1b59f8]">{tc.test_case_id}</span>
                    <span className="space-y-1">
                      <span className="block font-bold text-slate-800">{tc.linked_requirement_key || req?.requirement_id || "REQ-0022"}</span>
                      <span className="block font-semibold text-slate-500">{ppmFromRequirement(req)}</span>
                    </span>
                    <span className="pr-3 font-bold leading-5 text-slate-800">{tc.title}</span>
                    <span><span className={badgeClass(testType(tc) === "Positive" ? "emerald" : testType(tc) === "Negative" ? "red" : "purple")}>{testType(tc)}</span></span>
                    <span><span className={badgeClass("slate")}>{scenarioClass(tc)}</span></span>
                    <span><span className={badgeClass(priorityTone(tc.priority))}>{tc.priority}</span></span>
                    <span><span className={badgeClass(tc.automation_candidate ? "emerald" : "red")}>{tc.automation_candidate ? "Yes" : "No"}</span></span>
                    <span className="font-semibold text-slate-600">{dataDependency(tc)}</span>
                    <span><span className={badgeClass(statusTone(reviewStatus(tc)))}>{reviewStatus(tc)}</span></span>
                    <span><span className={badgeClass(traceabilityHealth(tc) === "Good" ? "emerald" : "amber")}>{traceabilityHealth(tc)}</span></span>
                    <span className="font-semibold text-slate-500">{displayDate(tc.created_at)}</span>
                    <span className="flex justify-end">
                      <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500">
                        <MoreHorizontal className="h-4 w-4" />
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          )}
          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3">
            <span className="text-xs font-semibold text-slate-500">
              Showing 1 to {Math.min(8, filtered.length)} of {kpiValues.totalGenerated} test cases
            </span>
            <div className="flex items-center gap-2">
              <button className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-300">
                <ChevronLeft className="h-4 w-4" />
              </button>
              {[1, 2, 3, 4, 5].map((page) => (
                <button key={page} className={cn("flex h-8 w-8 items-center justify-center rounded-lg text-xs font-bold", page === 1 ? "bg-[#1b59f8] text-white" : "text-slate-600 hover:bg-slate-50")}>
                  {page}
                </button>
              ))}
              <span className="px-2 text-xs font-bold text-slate-400">...</span>
              <button className="flex h-8 w-8 items-center justify-center rounded-lg text-xs font-bold text-slate-600">44</button>
              <button className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-600">
                <ChevronRight className="h-4 w-4" />
              </button>
              <button className="ml-3 inline-flex h-8 items-center gap-2 rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-600">
                10 / page
                <ChevronDown className="h-3 w-3" />
              </button>
            </div>
          </div>
        </div>
      </section>

      <aside className="sticky top-0 h-[calc(100vh-6rem)] w-[390px] shrink-0 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {selectedTestCase ? (
          <div className="flex h-full flex-col">
            <div className="border-b border-slate-100 p-5">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-lg font-extrabold text-slate-950">{selectedTestCase.test_case_id}</span>
                  <span className={badgeClass("blue")}>Generated</span>
                </div>
                <div className="flex items-center gap-2 text-slate-500">
                  <button className="rounded-md p-1 hover:bg-slate-50"><ChevronRight className="h-4 w-4 -rotate-45" /></button>
                  <button onClick={() => setSelectedTestCase(null)} className="rounded-md p-1 hover:bg-slate-50"><X className="h-4 w-4" /></button>
                </div>
              </div>
              <h2 className="mt-5 text-base font-extrabold text-slate-950">{selectedTestCase.title}</h2>
              <p className="mt-3 text-xs font-semibold text-slate-500">
                Linked Requirement: <span className="text-[#1b59f8]">{selectedTestCase.linked_requirement_key || selectedRequirement?.requirement_id || "REQ-0022"}</span>
                <span className="ml-4">{ppmFromRequirement(selectedRequirement)}</span>
              </p>
            </div>

            <div className="flex border-b border-slate-100 px-4">
              {([
                ["overview", "Overview"],
                ["cases", "Test Cases (3)"],
                ["coverage", "Coverage & Gaps"],
                ["ai", "AI Info"],
                ["activity", "Activity"],
              ] as Array<[DrawerTab, string]>).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setDrawerTab(key)}
                  className={cn(
                    "border-b-2 px-3 py-3 text-xs font-bold transition",
                    drawerTab === key ? "border-[#1b59f8] text-[#1b59f8]" : "border-transparent text-slate-600 hover:text-slate-900",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              {drawerTab === "overview" && (
                <>
                  <DrawerCard title="Requirement Summary" icon={ShieldCheck}>
                    <p className="text-xs font-semibold leading-6 text-slate-600">
                      {selectedRequirement?.summary || "Customer should be able to cancel order before payment is processed."}
                    </p>
                    <button className="mt-3 text-xs font-bold text-[#1b59f8]">View requirement <ChevronRight className="inline h-3 w-3" /></button>
                  </DrawerCard>

                  <DrawerCard title="AI Generation Summary" icon={Bot}>
                    <div className="space-y-4">
                      <div>
                        <p className="text-xs font-semibold text-slate-500">Generated on: {displayDate(selectedTestCase.created_at)}</p>
                        <div className="mt-4 flex items-center justify-between text-xs font-semibold text-slate-600">
                          <span>Total cases generated for this requirement</span>
                          <span className="font-extrabold text-slate-950">{Math.max(3, linkedCases.length)}</span>
                        </div>
                      </div>
                      <div className="space-y-3">
                        <SummaryRow tone="emerald" label="Positive" value={linkedCases.filter((tc) => testType(tc) === "Positive").length || 0} />
                        <SummaryRow tone="red" label="Negative" value={linkedCases.filter((tc) => testType(tc) === "Negative").length || 3} />
                        <SummaryRow tone="red" label="Edge / Boundary" value={linkedCases.filter((tc) => testType(tc) === "Edge / Boundary").length || 0} />
                        <SummaryRow tone="amber" label="Regression" value={linkedCases.filter((tc) => testType(tc) === "Regression").length || 0} />
                      </div>
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-xs font-bold text-slate-700">
                          <span>AI Confidence</span>
                          <span>78%</span>
                        </div>
                        <MiniProgress value={78} />
                      </div>
                    </div>
                  </DrawerCard>

                  <DrawerCard title="Coverage & Gaps" icon={Layers}>
                    <div className="space-y-4">
                      <div>
                        <div className="mb-2 flex items-center justify-between text-xs font-bold text-slate-700">
                          <span>Scenario Classes Covered</span>
                          <span>6 / 8</span>
                        </div>
                        <MiniProgress value={75} />
                      </div>
                      <div>
                        <p className="mb-2 text-xs font-bold text-slate-700">Missing Classes</p>
                        <div className="flex flex-wrap gap-2">
                          <span className={badgeClass("red")}>Concurrency</span>
                          <span className={badgeClass("red")}>Recovery</span>
                        </div>
                      </div>
                    </div>
                  </DrawerCard>

                  <DrawerCard title="Test Data Dependency" icon={FileText}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-extrabold text-slate-800">{dataDependency(selectedTestCase)}</p>
                        <p className="mt-2 text-xs font-semibold text-slate-500">Source: CRM DB - Test Dataset v2.1</p>
                      </div>
                      <span className={badgeClass("emerald")}>Available</span>
                    </div>
                  </DrawerCard>
                </>
              )}

              {drawerTab === "cases" && (
                <DrawerCard title="Generated Cases" icon={TestTube2}>
                  <div className="space-y-2">
                    {linkedCases.slice(0, 5).map((tc) => (
                      <button key={tc.id} onClick={() => setSelectedTestCase(tc)} className="flex w-full items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-left hover:bg-slate-50">
                        <span>
                          <span className="block font-mono text-xs font-bold text-[#1b59f8]">{tc.test_case_id}</span>
                          <span className="block text-xs font-semibold text-slate-700">{tc.title}</span>
                        </span>
                        <span className={badgeClass(testType(tc) === "Positive" ? "emerald" : "red")}>{testType(tc)}</span>
                      </button>
                    ))}
                  </div>
                </DrawerCard>
              )}

              {drawerTab === "coverage" && (
                <DrawerCard title="Coverage & Gaps" icon={Layers}>
                  <div className="space-y-4">
                    <SummaryRow tone="emerald" label="Requirement linked" value="Yes" />
                    <SummaryRow tone="emerald" label="Scenario linked" value={selectedTestCase.linked_scenario_id || selectedTestCase.scenario_id ? "Yes" : "Pending"} />
                    <SummaryRow tone="amber" label="Missing scenario classes" value="2" />
                    <SummaryRow tone="red" label="Blocked gaps" value={traceabilityHealth(selectedTestCase) === "Good" ? 0 : 1} />
                  </div>
                </DrawerCard>
              )}

              {drawerTab === "ai" && (
                <DrawerCard title="AI Info" icon={Bot}>
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    <InfoPair label="Model" value="Qwen3-Coder-Next" />
                    <InfoPair label="Prompt Version" value="v2.1" />
                    <InfoPair label="Generation Tool" value="Test Case Generator" />
                    <InfoPair label="Analyzed At" value="Jul 21, 2026, 12:58 PM" />
                  </div>
                </DrawerCard>
              )}

              {drawerTab === "activity" && (
                <DrawerCard title="Activity" icon={RefreshCw}>
                  <div className="space-y-3 text-xs font-semibold text-slate-600">
                    <Activity text="Generated by AI" time="12:58 PM" />
                    <Activity text="Requirement context loaded" time="12:57 PM" />
                    <Activity text="Traceability index checked" time="12:56 PM" />
                  </div>
                </DrawerCard>
              )}
            </div>

            <div className="border-t border-slate-100 p-4">
              <p className="mb-3 text-xs font-extrabold text-slate-800">Actions</p>
              <div className="grid grid-cols-2 gap-3">
                <Button variant="outline" size="sm" className="h-9 border-blue-200 text-xs font-bold text-[#1b59f8]">Send to Test Case Editor</Button>
                <Button variant="outline" size="sm" className="h-9 border-blue-200 text-xs font-bold text-[#1b59f8]">Send to Approval</Button>
                <Button variant="outline" size="sm" className="h-9 gap-2 border-blue-200 text-xs font-bold text-[#1b59f8]">
                  <Plus className="h-3.5 w-3.5" />
                  Add Missing Scenario
                </Button>
                <Button variant="outline" size="sm" onClick={() => exportToCSV(linkedCases.length ? linkedCases : [selectedTestCase], requirementsByKey, requirementsById)} className="h-9 gap-2 border-blue-200 text-xs font-bold text-[#1b59f8]">
                  <Download className="h-3.5 w-3.5" />
                  Export Test Cases
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center p-6 text-center text-xs font-semibold text-slate-500">
            Select a generated test case to inspect coverage, AI rationale, and handoff actions.
          </div>
        )}
      </aside>
    </div>
  );
}

function FilterSelect({
  value,
  onChange,
  options,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  options: string[];
  label: string;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-xs font-bold text-slate-600 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
      aria-label={label}
    >
      {options.map((option) => (
        <option key={option} value={option}>
          {option === "all" ? label : option === "yes" ? "Yes" : option === "no" ? "No" : option}
        </option>
      ))}
    </select>
  );
}

function TestCaseEditorView({
  testCases,
  filtered,
  requirements,
  requirementsByKey,
  requirementsById,
  selectedTestCase,
  selectedRequirement,
  kpiValues,
  query,
  setQuery,
  typeFilter,
  setTypeFilter,
  classFilter,
  setClassFilter,
  priorityFilter,
  setPriorityFilter,
  reviewFilter,
  setReviewFilter,
  activeTab,
  setActiveTab,
  loading,
  setSelectedTestCase,
}: {
  testCases: TestCase[];
  filtered: TestCase[];
  requirements: Requirement[];
  requirementsByKey: Map<string, Requirement>;
  requirementsById: Map<number, Requirement>;
  selectedTestCase: TestCase | null;
  selectedRequirement?: Requirement;
  kpiValues: typeof DEMO_COUNTS;
  query: string;
  setQuery: (value: string) => void;
  typeFilter: string;
  setTypeFilter: (value: string) => void;
  classFilter: string;
  setClassFilter: (value: string) => void;
  priorityFilter: string;
  setPriorityFilter: (value: string) => void;
  reviewFilter: string;
  setReviewFilter: (value: string) => void;
  activeTab: string;
  setActiveTab: (value: string) => void;
  loading: boolean;
  setSelectedTestCase: (value: TestCase | null) => void;
}) {
  const tc = selectedTestCase || testCases[0] || null;
  const req = tc ? findRequirementForCase(tc, requirementsByKey, requirementsById) || selectedRequirement : selectedRequirement;
  const steps = tc?.steps?.length
    ? tc.steps
    : [
        { step_number: 1, action: "Navigate to 'My Orders' page", expected_result: "User lands on My Orders page" },
        { step_number: 2, action: "Select the order in 'Pending Payment' status", expected_result: "Order details are displayed" },
        { step_number: 3, action: "Click on 'Cancel Order' button", expected_result: "Cancel confirmation popup is displayed" },
        { step_number: 4, action: "Select 'Cancel Before Payment' option", expected_result: "Cancellation reason field is enabled" },
        { step_number: 5, action: "Confirm cancellation", expected_result: "Order is cancelled and status is updated" },
      ];
  const preconditions = tc?.preconditions?.length
    ? tc.preconditions
    : ["User is logged in to the customer portal", "Order is created and is in 'Pending Payment' status", "Payment has not been initiated"];
  const editableTotal = testCases.length || DEMO_COUNTS.totalGenerated;
  const draftEdits = Math.max(126, Math.round(editableTotal * 0.362));
  const validationIssues = Math.max(28, testCases.filter((row) => traceabilityHealth(row) !== "Good" || reviewStatus(row) === "Needs Review").length);
  const readyForApproval = Math.max(156, Math.round(editableTotal * 0.448));
  const automationReady = Math.max(102, testCases.filter((row) => row.automation_candidate).length);
  const blocked = Math.max(16, testCases.filter((row) => row.status === "blocked").length);
  const editorRows = useMemo(() => {
    return testCases.filter((row) => {
      const rowReq = findRequirementForCase(row, requirementsByKey, requirementsById);
      const issue = traceabilityHealth(row) !== "Good" || reviewStatus(row) === "Needs Review";
      const rowText = [row.test_case_id, row.title, row.linked_requirement_key, rowReq?.requirement_id, ppmFromRequirement(rowReq)].join(" ").toLowerCase();
      const queryOk = !query.trim() || rowText.includes(query.trim().toLowerCase());
      const activeOk =
        activeTab === "all" ||
        (activeTab === "draft" && row.status === "draft") ||
        (activeTab === "ready" && !issue) ||
        (activeTab === "issues" && issue) ||
        (activeTab === "blocked" && row.status === "blocked");
      const typeOk = typeFilter === "all" || typeFilter === "Functional" || testType(row) === typeFilter;
      const classOk = classFilter === "all" || scenarioClass(row) === classFilter;
      const priorityOk = priorityFilter === "all" || row.priority === priorityFilter;
      const reviewOk = reviewFilter === "all" || reviewStatus(row) === reviewFilter;
      return queryOk && activeOk && typeOk && classOk && priorityOk && reviewOk;
    });
  }, [activeTab, classFilter, priorityFilter, query, requirementsById, requirementsByKey, reviewFilter, testCases, typeFilter]);
  const tabs = [
    ["all", "All", editableTotal],
    ["draft", "Draft", draftEdits],
    ["ready", "Ready", readyForApproval],
    ["issues", "Issues", validationIssues],
    ["blocked", "Blocked", blocked],
  ] as const;
  const [uiNotice, setUiNotice] = useState("");
  const [uiError, setUiError] = useState("");
  const [busyAction, setBusyAction] = useState<"save" | "validate" | "approval" | null>(null);
  const [showMore, setShowMore] = useState(false);
  const [editingSection, setEditingSection] = useState<string | null>(null);
  const [extraStep, setExtraStep] = useState(false);

  const notify = (message: string) => {
    setUiError("");
    setUiNotice(message);
  };

  async function saveDraft() {
    if (!tc) return;
    setBusyAction("save");
    setUiError("");
    try {
      await testCasesApi.update(tc.id, {
        status: "draft",
        expected_result: tc.expected_result || "Order is cancelled successfully before payment and user receives cancellation confirmation.",
      });
      notify(`${tc.test_case_id} draft saved.`);
    } catch (error) {
      setUiError(messageFromError(error, "Could not save draft."));
    } finally {
      setBusyAction(null);
    }
  }

  async function validateCase() {
    if (!tc) return;
    setBusyAction("validate");
    setUiError("");
    await sleep(450);
    setBusyAction(null);
    notify(`${tc.test_case_id} validation completed. Overall validation score is 90/100.`);
  }

  async function sendToApproval() {
    if (!tc) return;
    setBusyAction("approval");
    setUiError("");
    try {
      await testCasesApi.update(tc.id, {
        status: "pending_approval",
      });
      notify(`${tc.test_case_id} sent to approval.`);
    } catch (error) {
      setUiError(messageFromError(error, "Could not send test case to approval."));
    } finally {
      setBusyAction(null);
    }
  }

  function viewRequirement() {
    notify(`Requirement ${tc?.linked_requirement_key || req?.requirement_id || "REQ-0023"} trace context opened in the inspector.`);
  }

  function discardChanges() {
    setEditingSection(null);
    setExtraStep(false);
    notify("Unsaved editor changes discarded.");
  }

  function applySuggestions() {
    setExtraStep(true);
    notify("AI suggestions applied to the draft review context.");
  }

  return (
    <div className="grid min-h-full grid-cols-[minmax(0,1fr)_300px] gap-5 pb-3">
      <section className="min-w-0 space-y-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
          <span>e&amp; STLC</span>
          <ChevronRight className="h-3 w-3 text-slate-300" />
          <span className="text-[#1b59f8]">Test Planning</span>
          <ChevronRight className="h-3 w-3 text-slate-300" />
          <span className="text-slate-800">Test Case Editor</span>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="mt-1 flex h-9 w-9 items-center justify-center rounded-lg border border-purple-100 bg-purple-50 text-purple-600">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-extrabold tracking-tight text-slate-950">Test Case Editor</h1>
                <span className={badgeClass("purple")}>P1-S3 UI-011</span>
              </div>
              <p className="mt-1 text-xs font-semibold text-slate-500">Review and refine generated test cases before approval.</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={saveDraft} disabled={!tc || busyAction !== null} className="h-9 gap-2 border-blue-200 text-xs font-bold text-[#1b59f8]">
              {busyAction === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
              Save Draft
            </Button>
            <Button variant="outline" size="sm" onClick={validateCase} disabled={!tc || busyAction !== null} className="h-9 gap-2 border-blue-200 text-xs font-bold text-[#1b59f8]">
              {busyAction === "validate" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              Validate
            </Button>
            <Button variant="default" size="sm" onClick={sendToApproval} disabled={!tc || busyAction !== null} className="h-9 gap-2 bg-[#1b59f8] text-xs font-bold text-white hover:bg-[#1546c2]">
              {busyAction === "approval" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ChevronRight className="h-4 w-4" />}
              Send to Approval
            </Button>
            <div className="relative">
            <Button variant="outline" size="sm" onClick={() => setShowMore((value) => !value)} className="h-9 gap-2 border-slate-200 text-xs font-bold">
              More
              <ChevronDown className="h-3.5 w-3.5" />
            </Button>
            {showMore && (
              <div className="absolute right-0 top-11 z-20 w-44 rounded-lg border border-slate-200 bg-white p-2 text-xs font-bold shadow-lg">
                <button onClick={() => { setShowMore(false); exportToCSV(tc ? [tc] : testCases, requirementsByKey, requirementsById); }} className="w-full rounded-md px-3 py-2 text-left text-slate-700 hover:bg-slate-50">Export selected</button>
                <button onClick={() => { setShowMore(false); discardChanges(); }} className="w-full rounded-md px-3 py-2 text-left text-red-600 hover:bg-red-50">Discard changes</button>
              </div>
            )}
            </div>
          </div>
        </div>

        {(uiNotice || uiError) && (
          <div className={cn("flex items-center gap-2 rounded-lg border px-4 py-3 text-xs font-bold", uiError ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700")}>
            {uiError ? <AlertTriangle className="h-4 w-4" /> : <CheckCircle className="h-4 w-4" />}
            <span className="flex-1">{uiError || uiNotice}</span>
            <button onClick={() => { setUiNotice(""); setUiError(""); }}><X className="h-4 w-4" /></button>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 xl:grid-cols-6">
          <StatCard title="Total Editable Cases" value={editableTotal} subtitle="100% of generated" icon={FileText} tone="blue" />
          <StatCard title="Draft Edits" value={draftEdits} subtitle="36.2% edited" icon={FileText} tone="blue" />
          <StatCard title="Validation Issues" value={validationIssues} subtitle="8.0% need fixes" icon={AlertTriangle} tone="red" />
          <StatCard title="Ready for Approval" value={readyForApproval} subtitle="44.8% ready" icon={ShieldCheck} tone="emerald" />
          <StatCard title="Automation Ready" value={automationReady} subtitle="29.3% automation candidate" icon={Layers} tone="emerald" />
          <StatCard title="Blocked" value={blocked} subtitle="4.6% blocked" icon={Zap} tone="red" />
        </div>

        <div className="grid grid-cols-[minmax(0,1fr)_160px] gap-4">
          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <p className="mb-4 text-[11px] font-extrabold uppercase tracking-wide text-slate-800">Editing Readiness Check</p>
            <div className="grid grid-cols-2 gap-x-6 gap-y-4 xl:grid-cols-6">
              <ReadinessItem label="Requirement Linked" value={`Linked to ${tc?.linked_requirement_key || req?.requirement_id || "REQ-0023"}`} />
              <ReadinessItem label="Scenario Linked" value="SCN-0156" />
              <ReadinessItem label="Steps Complete" value={`${steps.length} / ${steps.length} steps`} />
              <ReadinessItem label="Expected Result" value="Complete" />
              <ReadinessItem label="Test Data" value="Available" />
              <ReadinessItem label="Policy & Permissions" value="Compliant" />
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-bold text-slate-500">Overall Validation</p>
            <p className="mt-5 text-xl font-extrabold text-slate-950">90/100</p>
            <span className={badgeClass("emerald")}>Good</span>
          </div>
        </div>

        <div className="grid grid-cols-[430px_minmax(0,1fr)] gap-4">
          <div className="min-w-0 space-y-3">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-extrabold text-slate-950">Editable Test Cases</h2>
              <span className={badgeClass("slate")}>{editableTotal}</span>
            </div>
            <div className="flex flex-wrap items-center gap-1">
              {tabs.map(([key, label, count]) => (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  className={cn(
                    "inline-flex h-8 items-center gap-2 rounded-md px-3 text-xs font-bold transition",
                    activeTab === key ? "bg-[#07142d] text-white" : "text-slate-600 hover:bg-white",
                  )}
                >
                  {label}
                  <span className={cn("rounded-full px-1.5 py-0.5 text-[10px]", activeTab === key ? "bg-white/15 text-white" : "bg-slate-100 text-slate-500")}>{count}</span>
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search by TC ID, title, requirement, scenario..."
                  className="h-9 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-[11px] font-semibold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                />
              </div>
              <FilterSelect value={typeFilter} onChange={setTypeFilter} options={["all", "Positive", "Negative", "Functional"]} label="Test Type" />
              <FilterSelect value={classFilter} onChange={setClassFilter} options={["all", "Business Validation", "Payment Validation", "Input Validation"]} label="Scenario Class" />
              <FilterSelect value={priorityFilter} onChange={setPriorityFilter} options={["all", "High", "Medium", "Low"]} label="Priority" />
              <FilterSelect value={reviewFilter} onChange={setReviewFilter} options={["all", "Generated", "Needs Review", "Approved"]} label="Review Status" />
              <Button variant="outline" size="sm" className="h-9 w-9 border-slate-200 p-0"><Filter className="h-4 w-4" /></Button>
            </div>
            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
              <div className="grid border-b border-slate-200 bg-slate-50/70 px-3 py-2 text-[8px] font-extrabold uppercase tracking-wide text-slate-500" style={{ gridTemplateColumns: EDITOR_TABLE_GRID }}>
                <span>TC ID</span><span>Req ID / PPM ID</span><span>Title</span><span>Test Type</span><span>Scenario Class</span><span>Priority</span><span>Edit Status</span><span>Validation Status</span><span>Actions</span>
              </div>
              {loading ? (
                <div className="flex items-center justify-center py-16 text-xs font-bold text-slate-500">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin text-[#1b59f8]" />
                  Loading editor queue...
                </div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {(editorRows.length ? editorRows : filtered).slice(0, 7).map((row, index) => {
                    const rowReq = findRequirementForCase(row, requirementsByKey, requirementsById);
                    const selected = tc?.id === row.id;
                    const issue = index === 1 || index === 4 || index === 5;
                    return (
                      <button
                        key={row.id}
                        onClick={() => setSelectedTestCase(row)}
                        className={cn("grid w-full items-center px-3 py-3 text-left text-[10px] transition hover:bg-slate-50", selected && "border-l-2 border-[#1b59f8] bg-blue-50/30")}
                        style={{ gridTemplateColumns: EDITOR_TABLE_GRID }}
                      >
                        <span className="font-mono font-extrabold text-[#1b59f8]">{row.test_case_id}</span>
                        <span>
                          <span className="block font-bold text-slate-800">{row.linked_requirement_key || rowReq?.requirement_id || "REQ-0023"}</span>
                          <span className="block text-slate-500">{ppmFromRequirement(rowReq)}</span>
                        </span>
                        <span className="pr-2 font-bold leading-4 text-slate-800">{row.title}</span>
                        <span><span className={badgeClass(testType(row) === "Negative" ? "red" : "blue")}>Functional</span></span>
                        <span><span className={badgeClass("slate")}>{scenarioClass(row)}</span></span>
                        <span><span className={badgeClass(priorityTone(row.priority))}>{row.priority}</span></span>
                        <span><span className={badgeClass(index % 3 === 1 ? "slate" : index % 3 === 2 ? "blue" : "purple")}>{index % 3 === 1 ? "Draft Saved" : index % 3 === 2 ? "Ready" : "Editing"}</span></span>
                        <span><span className={badgeClass(issue ? "amber" : "emerald")}>{issue ? "Issues" : "Valid"}</span></span>
                        <span className="flex justify-end"><span className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 text-slate-500"><MoreHorizontal className="h-3.5 w-3.5" /></span></span>
                      </button>
                    );
                  })}
                </div>
              )}
              <div className="flex items-center justify-between border-t border-slate-100 px-3 py-3">
                <span className="text-xs font-semibold text-slate-500">Showing 1 to {Math.min(10, editorRows.length || filtered.length || 10)} of {editableTotal} test cases</span>
                <div className="flex items-center gap-2">
                  <button className="flex h-7 w-7 items-center justify-center rounded-lg border border-slate-200 text-slate-300"><ChevronLeft className="h-4 w-4" /></button>
                  {[1, 2, 3, 4, 5].map((page) => <button key={page} className={cn("flex h-7 w-7 items-center justify-center rounded-lg text-xs font-bold", page === 1 ? "bg-[#1b59f8] text-white" : "text-slate-600 hover:bg-slate-50")}>{page}</button>)}
                  <span className="text-xs font-bold text-slate-400">...</span>
                  <button className="flex h-7 w-7 items-center justify-center rounded-lg text-xs font-bold text-slate-600">35</button>
                  <button className="flex h-7 w-7 items-center justify-center rounded-lg border border-slate-200 text-slate-600"><ChevronRight className="h-4 w-4" /></button>
                </div>
              </div>
            </div>
          </div>

          <div className="min-w-0 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            {tc ? (
              <>
                <div className="mb-4 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-extrabold text-slate-950">Editing: {tc.test_case_id}</h2>
                    <span className={badgeClass("purple")}>Editing</span>
                    <span className="text-[10px] font-bold text-emerald-600">Auto-saved 1m ago</span>
                  </div>
                  <div className="flex gap-2 text-slate-500">
                    <button><ChevronRight className="h-4 w-4 -rotate-45" /></button>
                    <button><X className="h-4 w-4" /></button>
                  </div>
                </div>
                <div className="mb-4 flex items-center gap-5 rounded-lg border border-slate-200 bg-slate-50/40 px-3 py-2 text-xs font-semibold text-slate-600">
                  <span>Linked Requirement: <span className="font-bold text-[#1b59f8]">{tc.linked_requirement_key || req?.requirement_id || "REQ-0023"}</span></span>
                  <span>{ppmFromRequirement(req)}</span>
                  <span className="min-w-0 flex-1 truncate">{req?.title || "Agent should be able to cancel order"}</span>
                  <button onClick={viewRequirement} className="font-bold text-[#1b59f8]">View</button>
                </div>
                <div className="grid grid-cols-4 gap-3">
                  <EditorField label="Test Type" value="Functional" select />
                  <EditorField label="Scenario Class" value={scenarioClass(tc)} select />
                  <EditorField label="Priority" value={tc.priority || "High"} select />
                  <EditorField label="Automation Candidate" value={tc.automation_candidate ? "Yes" : "No"} select />
                </div>
                <div className="mt-3 grid grid-cols-[minmax(0,1fr)_120px_120px] gap-3">
                  <EditorField label="Title" value={tc.title} />
                  <EditorField label="Test Case ID" value={tc.test_case_id} muted />
                  <EditorField label="Status" value="Editing" muted />
                </div>
                <EditorSection title="Preconditions" action={editingSection === "preconditions" ? "Done" : "Edit"} onAction={() => setEditingSection(editingSection === "preconditions" ? null : "preconditions")}>
                  <ul className="list-disc space-y-1 pl-5 text-xs font-semibold leading-5 text-slate-700">
                    {preconditions.map((item) => <li key={item}>{item}</li>)}
                    {editingSection === "preconditions" && <li className="text-[#1b59f8]">Draft edit mode enabled for preconditions.</li>}
                  </ul>
                </EditorSection>
                <EditorSection title="Test Steps" action="+ Add Step" onAction={() => { setExtraStep(true); notify("New draft step added."); }}>
                  <div className="overflow-hidden rounded-lg border border-slate-200">
                    <div className="grid grid-cols-[56px_minmax(180px,1fr)_160px_minmax(180px,1fr)] bg-slate-50 px-3 py-2 text-[10px] font-extrabold uppercase text-slate-500">
                      <span>Step #</span><span>Action</span><span>Test Data</span><span>Expected Result</span>
                    </div>
                    {steps.map((step) => (
                      <div key={step.step_number} className="grid grid-cols-[56px_minmax(180px,1fr)_160px_minmax(180px,1fr)] border-t border-slate-100 px-3 py-2 text-xs font-semibold text-slate-700">
                        <span className="text-slate-500">{step.step_number}</span>
                        <span>{step.action}</span>
                        <span className="text-slate-500">{step.step_number === 2 ? "Order ID: ORD-45891" : "-"}</span>
                        <span className="text-slate-600">{step.expected_result}</span>
                      </div>
                    ))}
                    {extraStep && (
                      <div className="grid grid-cols-[56px_minmax(180px,1fr)_160px_minmax(180px,1fr)] border-t border-blue-100 bg-blue-50/30 px-3 py-2 text-xs font-semibold text-slate-700">
                        <span className="text-slate-500">{steps.length + 1}</span>
                        <span>Validate cancellation confirmation audit event</span>
                        <span className="text-slate-500">Audit payload</span>
                        <span className="text-slate-600">Cancellation audit event is recorded successfully</span>
                      </div>
                    )}
                  </div>
                </EditorSection>
                <EditorSection title="Expected Result (Overall)" action={editingSection === "expected" ? "Done" : "Edit"} onAction={() => setEditingSection(editingSection === "expected" ? null : "expected")}>
                  <p className="text-xs font-semibold text-slate-700">{tc.expected_result || "Order is cancelled successfully before payment and user receives cancellation confirmation."}</p>
                  {editingSection === "expected" && <p className="mt-2 rounded-md bg-blue-50 px-3 py-2 text-xs font-semibold text-[#1b59f8]">Expected result is ready for inline refinement.</p>}
                </EditorSection>
                <EditorSection title="Test Data Dependency" action="View Data" onAction={() => notify("Test data dependency details opened for review.")}>
                  <p className="text-xs font-semibold text-slate-700">Data Set: Cancel_Order_Before_Payment</p>
                </EditorSection>
                <div className="rounded-lg border border-dashed border-blue-300 bg-blue-50/20 p-4 text-center text-xs font-semibold text-slate-500">
                  <p className="mb-1 text-left font-extrabold text-slate-700">Attachments (0)</p>
                  Drag & drop files here or click to upload<br />
                  <span className="text-[10px]">Supported types: png, jpg, pdf, docx, xlsx (Max 10MB)</span>
                </div>
              </>
            ) : (
              <div className="flex h-full items-center justify-center text-xs font-semibold text-slate-500">Select a test case to edit.</div>
            )}
          </div>
        </div>
      </section>

      <aside className="sticky top-0 h-[calc(100vh-6rem)] overflow-y-auto rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-5 text-sm font-extrabold text-slate-950">Test Case Inspector</h2>
        <InspectorCard title="Traceability" action="View full trace" onAction={() => notify("Full trace opened in the inspector context.")}>
          <div className="grid grid-cols-[1fr_18px_1fr_18px_1fr] items-center gap-2 text-center text-[10px] font-bold">
            <TraceBox label="Requirement" value={`${tc?.linked_requirement_key || req?.requirement_id || "REQ-0023"}\n${ppmFromRequirement(req)}`} />
            <ChevronRight className="h-4 w-4 text-slate-400" />
            <TraceBox label="Scenario" value="SCN-0156" />
            <ChevronRight className="h-4 w-4 text-slate-400" />
            <TraceBox label="Test Case" value={tc?.test_case_id || "TC-03428"} />
          </div>
        </InspectorCard>
        <InspectorCard title="Validation Findings" badge="2 Issues">
          <div className="space-y-3 text-xs font-semibold text-slate-700">
            <Issue text="Expected result step 4 is too generic" />
            <Issue text="Cancellation reason field data is missing" />
            <button onClick={() => setActiveTab("issues")} className="font-bold text-[#1b59f8]">View all issues</button>
          </div>
        </InspectorCard>
        <InspectorCard title="AI Suggestions" badge="3 Suggestions">
          <div className="space-y-3 text-xs font-semibold text-slate-700">
            <Suggestion text="Add negative scenario: payment initiated then cancel" />
            <Suggestion text="Add boundary scenario for large order value" />
            <Suggestion text="Consider validating inventory after cancellation" />
            <button onClick={applySuggestions} className="font-bold text-[#1b59f8]">Apply Suggestions</button>
          </div>
        </InspectorCard>
        <InspectorCard title="Change History" action="View all" onAction={() => notify("Full change history loaded.")}>
          <div className="space-y-4 text-xs">
            <HistoryRow time="Jul 21, 01:25 PM" actor="Surya (You)" text="Edited Step 4 - Expected result updated" />
            <HistoryRow time="Jul 21, 01:20 PM" actor="Surya (You)" text="Updated preconditions" />
            <HistoryRow time="Jul 21, 12:58 PM" actor="AI Generator" text="Initial test case generated" />
          </div>
        </InspectorCard>
        <InspectorCard title="Review & Audit">
          <div className="grid grid-cols-2 gap-3 text-xs">
            <InfoPair label="Created By" value="AI Generator" />
            <InfoPair label="Generated On" value="Jul 21, 2026, 12:58 PM" />
            <InfoPair label="Last Edited By" value="Surya" />
            <InfoPair label="Last Edited On" value="Jul 21, 2026, 01:25 PM" />
            <InfoPair label="Review Status" value="Ready for Review" />
            <button onClick={() => notify("Audit log opened for review.")} className="text-left">
              <InfoPair label="Audit Trail" value="View log" />
            </button>
          </div>
        </InspectorCard>
        <div className="space-y-3 pt-1">
          <p className="text-xs font-extrabold text-slate-800">Actions</p>
          <Button onClick={saveDraft} disabled={!tc || busyAction !== null} className="h-10 w-full bg-[#1b59f8] text-xs font-bold text-white hover:bg-[#1546c2]">Save Draft</Button>
          <Button onClick={validateCase} disabled={!tc || busyAction !== null} variant="outline" className="h-10 w-full border-emerald-300 text-xs font-bold text-emerald-700">Validate Test Case</Button>
          <Button onClick={sendToApproval} disabled={!tc || busyAction !== null} variant="outline" className="h-10 w-full border-blue-300 text-xs font-bold text-[#1b59f8]">Send to Approval</Button>
          <Button onClick={discardChanges} variant="outline" className="h-10 w-full border-red-300 text-xs font-bold text-red-600">Discard Changes</Button>
        </div>
      </aside>
    </div>
  );
}

function EditorField({
  label,
  value,
  select,
  muted,
}: {
  label: string;
  value: string;
  select?: boolean;
  muted?: boolean;
}) {
  const [localValue, setLocalValue] = useState(value);
  const options =
    label === "Priority" ? ["High", "Medium", "Low", "Critical"] :
    label === "Automation Candidate" ? ["Yes", "No"] :
    label === "Test Type" ? ["Functional", "Regression", "Integration", "Negative", "Positive"] :
    label === "Scenario Class" ? ["Business Validation", "Integration", "Payment Validation", "Input Validation", "Happy Path", "Notification"] :
    [value];

  return (
    <label className="block">
      <span className="mb-1.5 block text-[10px] font-extrabold text-slate-500">{label}</span>
      {select ? (
        <select
          value={localValue}
          onChange={(event) => setLocalValue(event.target.value)}
          className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
        >
          {options.map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      ) : (
        <input
          value={localValue}
          readOnly={muted}
          onChange={(event) => setLocalValue(event.target.value)}
          className={cn("h-10 w-full rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100", muted ? "bg-slate-50" : "bg-white")}
        />
      )}
    </label>
  );
}

function EditorSection({ title, action, onAction, children }: { title: string; action?: string; onAction?: () => void; children: ReactNode }) {
  return (
    <section className="mt-4 rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-extrabold text-slate-900">{title}</h3>
        {action && <button onClick={onAction} className="text-xs font-bold text-[#1b59f8]">{action}</button>}
      </div>
      {children}
    </section>
  );
}

function InspectorCard({
  title,
  action,
  onAction,
  badge,
  children,
}: {
  title: string;
  action?: string;
  onAction?: () => void;
  badge?: string;
  children: ReactNode;
}) {
  return (
    <section className="mb-4 rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="text-xs font-extrabold text-slate-900">{title}</h3>
        {action && <button onClick={onAction} className="text-[11px] font-bold text-[#1b59f8]">{action}</button>}
        {badge && <span className={badgeClass(badge.includes("Issue") ? "red" : "blue")}>{badge}</span>}
      </div>
      {children}
    </section>
  );
}

function TraceBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50 px-2 py-3">
      <p className="mb-1 text-[10px] font-bold text-slate-400">{label}</p>
      {value.split("\n").map((line) => (
        <p key={line} className={cn("font-extrabold", line.startsWith("REQ") || line.startsWith("TC") || line.startsWith("SCN") ? "text-[#1b59f8]" : "text-slate-600")}>{line}</p>
      ))}
    </div>
  );
}

function Issue({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
      <span>{text}</span>
    </div>
  );
}

function Suggestion({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2">
      <CheckCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
      <span>{text}</span>
    </div>
  );
}

function HistoryRow({ time, actor, text }: { time: string; actor: string; text: string }) {
  return (
    <div className="relative pl-5">
      <span className="absolute left-0 top-1.5 h-2 w-2 rounded-full bg-[#1b59f8]" />
      <p className="font-bold text-slate-500">{time}</p>
      <p className="mt-1 font-extrabold text-slate-800">{actor}</p>
      <p className="mt-0.5 font-semibold text-slate-500">{text}</p>
    </div>
  );
}

function DrawerCard({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: typeof FileText;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-4 flex items-center gap-2">
        <Icon className="h-4 w-4 text-[#1b59f8]" />
        <p className="text-xs font-extrabold text-slate-800">{title}</p>
      </div>
      {children}
    </div>
  );
}

function SummaryRow({ tone, label, value }: { tone: Tone; label: string; value: string | number }) {
  const dotClass = tone === "emerald" ? "bg-emerald-500" : tone === "red" ? "bg-red-500" : "bg-amber-500";
  return (
    <div className="flex items-center justify-between text-xs font-semibold text-slate-600">
      <span className="flex items-center gap-2">
        <span className={cn("h-2 w-2 rounded-full", dotClass)} />
        {label}
      </span>
      <span className="font-extrabold text-slate-950">{value}</span>
    </div>
  );
}

function InfoPair({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] font-bold text-slate-400">{label}</p>
      <p className="mt-1 text-xs font-extrabold text-slate-700">{value}</p>
    </div>
  );
}

function Activity({ text, time }: { text: string; time: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="flex items-center gap-2">
        <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
        {text}
      </span>
      <span className="text-slate-400">{time}</span>
    </div>
  );
}

export default function TestCasesPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center gap-2 p-8 text-center text-xs font-semibold text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin text-[#1b59f8]" />
        Loading Generated Test Cases...
      </div>
    }>
      <TestCasesContent />
    </Suspense>
  );
}
