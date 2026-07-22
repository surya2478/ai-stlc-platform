"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  Bot,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  Filter,
  Layers,
  Loader2,
  MoreHorizontal,
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
  reviewsApi,
  scenariosApi,
  testCasesApi,
  usersApi,
  type ArtifactReview,
  type CoverageMatrixEntry,
  type Requirement,
  type TestCase,
  type TestCaseHistory,
  type TestScenario,
  type TestCaseSummary,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { JourneyGraphView } from "./JourneyGraphView";
import { TestCaseApprovalView } from "./TestCaseApprovalView";

type DrawerTab = "overview" | "cases" | "coverage" | "ai" | "activity";
type Tone = "blue" | "emerald" | "red" | "purple" | "amber" | "slate";


const TABS = [
  { key: "all", label: "All Generated" },
  { key: "positive", label: "Positive" },
  { key: "negative", label: "Negative" },
  { key: "edge", label: "Edge / Boundary" },
  { key: "regression", label: "Regression" },
  { key: "integration", label: "Integration" },
  { key: "gaps", label: "Gaps / Blocked" },
];

type KpiValues = {
  requirementsSelected: number;
  totalGenerated: number;
  positive: number;
  negative: number;
  edge: number;
  gaps: number;
  regression: number;
  integration: number;
};

function pct(part: number, total: number): string {
  if (!total) return "0% of total";
  return `${Math.round((part / total) * 1000) / 10}% of total`;
}

function pctOf(part: number, total: number, label: string): string {
  if (!total) return `0% ${label}`;
  return `${Math.round((part / total) * 1000) / 10}% ${label}`;
}

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

function splitLines(value: string): string[] {
  return value.split("\n").map((line) => line.trim()).filter(Boolean);
}

type EditorDraft = {
  title: string;
  priority: string;
  testType: string;
  automationCandidate: boolean;
  preconditionsText: string;
  steps: Array<{ step_number: number; action: string; expected_result: string }>;
  expectedResult: string;
};

function draftFromCase(t: TestCase | null): EditorDraft {
  return {
    title: t?.title ?? "",
    priority: t?.priority ?? "",
    testType: t?.test_type ?? "",
    automationCandidate: !!t?.automation_candidate,
    preconditionsText: (t?.preconditions ?? []).join("\n"),
    steps: (t?.steps ?? []).map((s) => ({ ...s })),
    expectedResult: t?.expected_result ?? "",
  };
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalize(value: string | null | undefined) {
  return (value || "").toLowerCase().replace(/[_-]/g, " ");
}

function displayDate(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function displayDateTime(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function relativeTime(value?: string | null) {
  if (!value) return "";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "";
  const diffMs = Date.now() - then;
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function ppmFromRequirement(req?: Requirement) {
  const ppm = req?.metadata_?.ppm_id;
  return ppm ? String(ppm) : "—";
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

function resolveUserName(names: Map<number, string>, id?: number | null): string {
  if (!id) return "—";
  return names.get(id) || `User #${id}`;
}

function scenarioForCase(
  tc: TestCase | null | undefined,
  scenariosById: Map<number, TestScenario>,
): TestScenario | undefined {
  if (!tc) return undefined;
  const dbId = tc.linked_scenario_id ?? tc.scenario_id;
  if (!dbId) return undefined;
  return scenariosById.get(dbId);
}

// scenario_test_case_coverage reviews are keyed by the scenario's DB id — the
// test case's review context is the review of its parent scenario's coverage.
function reviewForCase(
  tc: TestCase | null | undefined,
  reviews: ArtifactReview[],
): ArtifactReview | undefined {
  if (!tc) return undefined;
  const dbId = tc.linked_scenario_id ?? tc.scenario_id;
  if (!dbId) return undefined;
  return reviews
    .filter((r) => r.artifact_id === dbId)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0];
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

type SummaryItem = { label: string; value: number | string; tone: Tone; subtitle?: string };

function SummaryStrip({ items }: { items: SummaryItem[] }) {
  const toneMap: Record<Tone, string> = {
    blue: "text-blue-700",
    emerald: "text-emerald-700",
    red: "text-red-700",
    purple: "text-purple-700",
    amber: "text-amber-700",
    slate: "text-slate-700",
  };
  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap divide-x divide-slate-100">
        {items.map((item) => (
          <div key={item.label} className="flex-1 min-w-[120px] px-4 py-3">
            <p className="truncate text-[10px] font-bold uppercase tracking-wide text-slate-500">{item.label}</p>
            <p className={cn("mt-1 text-xl font-extrabold leading-none", toneMap[item.tone])}>{item.value}</p>
            {item.subtitle && <p className="mt-1 text-[10px] font-semibold text-slate-400">{item.subtitle}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

function ScenarioSelectionPanel({
  scenarios,
  requirementsById,
  selectedScenarioIds,
  setSelectedScenarioIds,
  generating,
  onGenerate,
  onRegenerate,
}: {
  scenarios: TestScenario[];
  requirementsById: Map<number, Requirement>;
  selectedScenarioIds: number[];
  setSelectedScenarioIds: (updater: (prev: number[]) => number[]) => void;
  generating: boolean;
  onGenerate: () => void;
  onRegenerate: () => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const selectedSet = useMemo(() => new Set(selectedScenarioIds), [selectedScenarioIds]);
  const allSelected = scenarios.length > 0 && selectedScenarioIds.length === scenarios.length;
  const someSelected = selectedScenarioIds.length > 0 && !allSelected;

  const toggleAll = () => {
    if (allSelected) setSelectedScenarioIds(() => []);
    else setSelectedScenarioIds(() => scenarios.map((s) => s.id));
  };

  const toggleOne = (id: number) => {
    setSelectedScenarioIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <button onClick={() => setExpanded((v) => !v)} className="flex items-center gap-2 text-left">
          <ChevronDown className={cn("h-4 w-4 text-slate-400 transition", !expanded && "-rotate-90")} />
          <span className="text-xs font-extrabold uppercase tracking-wide text-slate-800">Select Scenarios to Generate From</span>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
            {selectedScenarioIds.length} / {scenarios.length} selected
          </span>
        </button>
        <div className="flex items-center gap-2">
          <Button
            variant="ai"
            size="sm"
            onClick={onGenerate}
            disabled={generating || selectedScenarioIds.length === 0}
            className="h-9 gap-2 text-xs font-bold"
          >
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Generate Test Cases
            {selectedScenarioIds.length > 0 && <span className="rounded-full bg-white/20 px-1.5 py-0.5 text-[10px]">{selectedScenarioIds.length}</span>}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onRegenerate}
            disabled={generating || selectedScenarioIds.length === 0}
            className="h-9 gap-2 border-slate-200 text-xs font-bold"
          >
            <RefreshCw className="h-4 w-4" />
            Re-generate
          </Button>
        </div>
      </div>
      {expanded && (
        <div className="max-h-64 overflow-y-auto">
          {scenarios.length === 0 ? (
            <p className="px-4 py-6 text-center text-xs font-semibold text-slate-400">
              No approved scenarios available. Approve scenarios in Test Planning before generating test cases.
            </p>
          ) : (
            <>
              <div className="flex items-center gap-3 border-b border-slate-100 bg-slate-50/50 px-4 py-2">
                <input
                  type="checkbox"
                  aria-label="Select all scenarios"
                  checked={allSelected}
                  ref={(el) => { if (el) el.indeterminate = someSelected; }}
                  onChange={toggleAll}
                  className="h-3.5 w-3.5 rounded border-slate-300 accent-[#1b59f8]"
                />
                <span className="text-[10px] font-extrabold uppercase tracking-wide text-slate-500">
                  {allSelected ? "Deselect all" : "Select all"}
                </span>
              </div>
              <ul className="divide-y divide-slate-50">
                {scenarios.map((scenario) => {
                  const req = scenario.requirement_id ? requirementsById.get(scenario.requirement_id) : undefined;
                  const checked = selectedSet.has(scenario.id);
                  return (
                    <li key={scenario.id}>
                      <label className={cn("flex cursor-pointer items-center gap-3 px-4 py-2 hover:bg-slate-50", checked && "bg-blue-50/30")}>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleOne(scenario.id)}
                          className="h-3.5 w-3.5 rounded border-slate-300 accent-[#1b59f8]"
                        />
                        <span className="w-24 shrink-0 font-mono text-[11px] font-bold text-[#1b59f8]">{scenario.scenario_id}</span>
                        <span className="min-w-0 flex-1 truncate text-xs font-semibold text-slate-700">{scenario.title}</span>
                        {req && (
                          <span className="shrink-0 text-[10px] font-bold text-slate-500">
                            {req.requirement_id}
                          </span>
                        )}
                        <span className={cn("shrink-0", badgeClass(priorityTone(scenario.priority)))}>{scenario.priority}</span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>
      )}
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
    if (Object.keys(data).length) return `${Object.keys(data).length} data field${Object.keys(data).length === 1 ? "" : "s"}`;
  }
  return "None";
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
  const [userNames, setUserNames] = useState<Map<number, string>>(new Map());
  const [coverageByCase, setCoverageByCase] = useState<Map<number, CoverageMatrixEntry>>(new Map());
  const [scenarioReviews, setScenarioReviews] = useState<ArtifactReview[]>([]);
  const [scenariosById, setScenariosById] = useState<Map<number, TestScenario>>(new Map());

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
      const [tcRes, summaryRes, reqRes, scRes, coverageRes, reviewsRes, usersRes] = await Promise.all([
        testCasesApi.list(selectedProject),
        testCasesApi.summary(selectedProject),
        requirementsApi.list(selectedProject, { status: "approved" }),
        scenariosApi.list(selectedProject),
        reviewsApi.coverageMatrix(selectedProject).catch(() => ({ data: [] as CoverageMatrixEntry[] })),
        reviewsApi.listForProject(selectedProject, "scenario_test_case_coverage").catch(() => ({ data: [] as ArtifactReview[] })),
        usersApi.list().catch(() => ({ data: [] as Array<{ id: number; full_name: string }> })),
      ]);
      const approvedScenarios = scRes.data.filter((scenario) => scenario.status === "approved");
      setTestCases(tcRes.data);
      setSummary(summaryRes.data);
      setRequirements(reqRes.data);
      setScenarios(approvedScenarios);
      setScenariosById(new Map(scRes.data.map((s) => [s.id, s])));
      const coverageMap = new Map<number, CoverageMatrixEntry>();
      coverageRes.data.forEach((entry) => { if (entry.test_case_id) coverageMap.set(entry.test_case_id, entry); });
      setCoverageByCase(coverageMap);
      setScenarioReviews(reviewsRes.data);
      setUserNames(new Map(usersRes.data.map((u) => [u.id, u.full_name])));
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

  useEffect(() => {
    const requestedCase = searchParams.get("case");
    if (!requestedCase || !testCases.length) return;
    const match = testCases.find((item) => String(item.id) === requestedCase || item.test_case_id === requestedCase);
    if (match) setSelectedTestCase(match);
  }, [searchParams, testCases]);

  const requirementsByKey = useMemo(() => new Map(requirements.map((req) => [req.requirement_id, req])), [requirements]);
  const requirementsById = useMemo(() => new Map(requirements.map((req) => [req.id, req])), [requirements]);

  const generatedTotal = summary?.total ?? testCases.length;
  const positiveCount = testCases.filter((tc) => testType(tc) === "Positive").length;
  const negativeCount = testCases.filter((tc) => testType(tc) === "Negative").length;
  const edgeCount = testCases.filter((tc) => testType(tc) === "Edge / Boundary").length;
  const gapsCount = Math.max(0, requirements.length - new Set(testCases.map((tc) => tc.linked_requirement_key || tc.requirement_id)).size);
  const regressionCount = testCases.filter((tc) => testType(tc) === "Regression").length;
  const integrationCount = testCases.filter((tc) => normalize(scenarioClass(tc)).includes("integration")).length;

  const kpiValues: KpiValues = {
    requirementsSelected: requirements.length,
    totalGenerated: generatedTotal,
    positive: positiveCount,
    negative: negativeCount,
    edge: edgeCount,
    gaps: gapsCount,
    regression: regressionCount,
    integration: integrationCount,
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
  const selectedScenario = scenarioForCase(selectedTestCase, scenariosById);
  const selectedReview = reviewForCase(selectedTestCase, scenarioReviews);
  const selectedEligibility = (selectedTestCase?.metadata_ as { automation_eligibility?: { verdict?: string; reason?: string; automation_style?: string; agent_run_id?: number } } | undefined)?.automation_eligibility;

  async function sendCaseToApproval(id: number) {
    try {
      await testCasesApi.update(id, { status: "pending_approval" });
      setNotice("Test case sent to approval.");
      await loadData();
    } catch (updateError) {
      setError(messageFromError(updateError, "Could not send test case to approval."));
    }
  }

  function openInEditor(id: number) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("view", "editor");
    params.set("case", String(id));
    router.push(`${pathname}?${params.toString()}`);
  }

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

  if (view === "journey-graph") {
    return <JourneyGraphView projectId={selectedProject} />;
  }

  if (view === "approval") {
    return <TestCaseApprovalView projectId={selectedProject} />;
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
        userNames={userNames}
        scenarioReviews={scenarioReviews}
        scenariosById={scenariosById}
        onReload={loadData}
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
            <Button variant="outline" size="sm" onClick={() => exportToCSV(filtered, requirementsByKey, requirementsById)} className="h-9 gap-2 border-slate-200 text-xs font-bold">
              <Download className="h-4 w-4" />
              Export
            </Button>
          </div>
        </div>

        <SummaryStrip
          items={[
            { label: "Approved Requirements", value: requirements.length, tone: "blue" },
            { label: "Approved Scenarios", value: scenarios.length, tone: "blue" },
            { label: "Test Cases Generated", value: kpiValues.totalGenerated, tone: "emerald" },
            { label: "Positive", value: kpiValues.positive, tone: "emerald", subtitle: pct(kpiValues.positive, kpiValues.totalGenerated) },
            { label: "Negative", value: kpiValues.negative, tone: "red", subtitle: pct(kpiValues.negative, kpiValues.totalGenerated) },
            { label: "Edge / Boundary", value: kpiValues.edge, tone: "purple", subtitle: pct(kpiValues.edge, kpiValues.totalGenerated) },
            { label: "Requirements Without a Case", value: kpiValues.gaps, tone: "amber" },
          ]}
        />

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

        <ScenarioSelectionPanel
          scenarios={scenarios}
          requirementsById={requirementsById}
          selectedScenarioIds={selectedScenarioIds}
          setSelectedScenarioIds={setSelectedScenarioIds}
          generating={generating}
          onGenerate={() => generateCases()}
          onRegenerate={() => generateCases(true)}
        />

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
              {filtered.map((tc) => {
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
                      <span className="block font-bold text-slate-800">{tc.linked_requirement_key || req?.requirement_id || "—"}</span>
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
              Showing {filtered.length} of {kpiValues.totalGenerated} test cases
            </span>
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
                Linked Requirement: <span className="text-[#1b59f8]">{selectedTestCase.linked_requirement_key || selectedRequirement?.requirement_id || "—"}</span>
                <span className="ml-4">{ppmFromRequirement(selectedRequirement)}</span>
              </p>
            </div>

            <div className="flex border-b border-slate-100 px-4">
              {([
                ["overview", "Overview"],
                ["cases", `Sibling Cases (${linkedCases.length})`],
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
                    {selectedRequirement?.summary ? (
                      <p className="text-xs font-semibold leading-6 text-slate-600">{selectedRequirement.summary}</p>
                    ) : (
                      <p className="text-xs font-semibold text-slate-400">No linked requirement summary.</p>
                    )}
                    {selectedRequirement && selectedTestCase.project_id && (
                      <button
                        onClick={() => router.push(`/requirements?project=${selectedTestCase.project_id}&view=analysis&requirement=${selectedRequirement.id}`)}
                        className="mt-3 text-xs font-bold text-[#1b59f8]"
                      >
                        View requirement <ChevronRight className="inline h-3 w-3" />
                      </button>
                    )}
                  </DrawerCard>

                  <DrawerCard title="Generation Summary" icon={Bot}>
                    <div className="space-y-4">
                      <div>
                        <p className="text-xs font-semibold text-slate-500">Generated on: {displayDate(selectedTestCase.created_at)}</p>
                        <div className="mt-4 flex items-center justify-between text-xs font-semibold text-slate-600">
                          <span>Cases linked to this requirement</span>
                          <span className="font-extrabold text-slate-950">{linkedCases.length}</span>
                        </div>
                      </div>
                      <div className="space-y-3">
                        <SummaryRow tone="emerald" label="Positive" value={linkedCases.filter((tc) => testType(tc) === "Positive").length} />
                        <SummaryRow tone="red" label="Negative" value={linkedCases.filter((tc) => testType(tc) === "Negative").length} />
                        <SummaryRow tone="red" label="Edge / Boundary" value={linkedCases.filter((tc) => testType(tc) === "Edge / Boundary").length} />
                        <SummaryRow tone="amber" label="Regression" value={linkedCases.filter((tc) => testType(tc) === "Regression").length} />
                      </div>
                      {selectedReview && (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between text-xs font-bold text-slate-700">
                            <span>Coverage review score</span>
                            <span>{typeof selectedReview.overall_score === "number" ? `${selectedReview.overall_score}/100` : selectedReview.verdict.replace(/_/g, " ")}</span>
                          </div>
                          {typeof selectedReview.overall_score === "number" && <MiniProgress value={selectedReview.overall_score} />}
                        </div>
                      )}
                    </div>
                  </DrawerCard>

                  <DrawerCard title="Coverage & Gaps" icon={Layers}>
                    {selectedReview?.coverage_gaps?.length ? (
                      <div className="space-y-2">
                        <p className="text-xs font-bold text-slate-700">Coverage gaps</p>
                        <div className="space-y-2">
                          {selectedReview.coverage_gaps.map((gap, index) => (
                            <div key={index} className="flex items-start gap-2 text-xs font-semibold text-slate-600">
                              <span className={badgeClass(gap.severity === "high" ? "red" : gap.severity === "medium" ? "amber" : "slate")}>{gap.severity}</span>
                              <span>{gap.description}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs font-semibold text-slate-400">{selectedReview ? "No coverage gaps on the latest review." : "No coverage review recorded yet."}</p>
                    )}
                  </DrawerCard>

                  <DrawerCard title="Test Data Dependency" icon={FileText}>
                    {selectedTestCase.test_data && Object.keys(selectedTestCase.test_data).length ? (
                      <div className="space-y-1 text-xs font-semibold text-slate-700">
                        {Object.entries(selectedTestCase.test_data).map(([key, value]) => (
                          <div key={key} className="flex gap-2">
                            <span className="font-bold text-slate-500">{key}:</span>
                            <span className="min-w-0 break-words">{typeof value === "object" ? JSON.stringify(value) : String(value)}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs font-semibold text-slate-400">No test data dependency recorded.</p>
                    )}
                  </DrawerCard>
                </>
              )}

              {drawerTab === "cases" && (
                <DrawerCard title="Sibling Cases" icon={TestTube2}>
                  {linkedCases.length ? (
                    <div className="space-y-2">
                      {linkedCases.map((tc) => (
                        <button key={tc.id} onClick={() => setSelectedTestCase(tc)} className="flex w-full items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-left hover:bg-slate-50">
                          <span>
                            <span className="block font-mono text-xs font-bold text-[#1b59f8]">{tc.test_case_id}</span>
                            <span className="block text-xs font-semibold text-slate-700">{tc.title}</span>
                          </span>
                          <span className={badgeClass(testType(tc) === "Positive" ? "emerald" : "red")}>{testType(tc)}</span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs font-semibold text-slate-400">No sibling cases for this requirement.</p>
                  )}
                </DrawerCard>
              )}

              {drawerTab === "coverage" && (
                <DrawerCard title="Coverage & Gaps" icon={Layers}>
                  <div className="space-y-4">
                    <SummaryRow tone={selectedTestCase.linked_requirement_key || selectedTestCase.requirement_id ? "emerald" : "amber"} label="Requirement linked" value={selectedTestCase.linked_requirement_key || selectedTestCase.requirement_id ? "Yes" : "No"} />
                    <SummaryRow tone={selectedScenario ? "emerald" : "amber"} label="Scenario linked" value={selectedScenario ? selectedScenario.scenario_id : "No"} />
                    <SummaryRow tone={selectedReview?.coverage_gaps?.length ? "amber" : "emerald"} label="Coverage gaps" value={selectedReview?.coverage_gaps?.length ?? 0} />
                    <SummaryRow tone={traceabilityHealth(selectedTestCase) === "Good" ? "emerald" : "red"} label="Traceability health" value={traceabilityHealth(selectedTestCase)} />
                  </div>
                </DrawerCard>
              )}

              {drawerTab === "ai" && (
                <DrawerCard title="AI Info" icon={Bot}>
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    <InfoPair label="Generation Run" value={selectedTestCase.agent_run_id ? `#${selectedTestCase.agent_run_id}` : "—"} />
                    <InfoPair label="Generated At" value={displayDateTime(selectedTestCase.created_at)} />
                    <InfoPair label="Automation Eligibility" value={selectedEligibility?.verdict ? selectedEligibility.verdict : "Not assessed"} />
                    <InfoPair label="Automation Style" value={selectedEligibility?.automation_style || "—"} />
                  </div>
                  {selectedEligibility?.reason && (
                    <p className="mt-3 text-xs font-semibold text-slate-500">{selectedEligibility.reason}</p>
                  )}
                </DrawerCard>
              )}

              {drawerTab === "activity" && (
                <DrawerCard title="Activity" icon={RefreshCw}>
                  <div className="space-y-3 text-xs font-semibold text-slate-600">
                    <Activity text="Created" time={displayDate(selectedTestCase.created_at)} />
                    {selectedTestCase.last_status_updated_at && <Activity text="Status updated" time={displayDate(selectedTestCase.last_status_updated_at)} />}
                    {selectedTestCase.updated_at && selectedTestCase.updated_at !== selectedTestCase.created_at && <Activity text="Last modified" time={displayDate(selectedTestCase.updated_at)} />}
                  </div>
                </DrawerCard>
              )}
            </div>

            <div className="border-t border-slate-100 p-4">
              <p className="mb-3 text-xs font-extrabold text-slate-800">Actions</p>
              <div className="grid grid-cols-2 gap-3">
                <Button variant="outline" size="sm" onClick={() => openInEditor(selectedTestCase.id)} className="h-9 border-blue-200 text-xs font-bold text-[#1b59f8]">Open in Editor</Button>
                <Button variant="outline" size="sm" onClick={() => sendCaseToApproval(selectedTestCase.id)} disabled={selectedTestCase.status === "pending_approval" || selectedTestCase.status === "approved"} className="h-9 border-blue-200 text-xs font-bold text-[#1b59f8]">Send to Approval</Button>
                <Button variant="outline" size="sm" onClick={() => exportToCSV([selectedTestCase], requirementsByKey, requirementsById)} className="col-span-2 h-9 gap-2 border-blue-200 text-xs font-bold text-[#1b59f8]">
                  <Download className="h-3.5 w-3.5" />
                  Export Test Case
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
  userNames,
  scenarioReviews,
  scenariosById,
  onReload,
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
  kpiValues: KpiValues;
  userNames: Map<number, string>;
  scenarioReviews: ArtifactReview[];
  scenariosById: Map<number, TestScenario>;
  onReload: () => void | Promise<void>;
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
  const steps = tc?.steps ?? [];
  const preconditions = tc?.preconditions ?? [];
  const scenario = scenarioForCase(tc, scenariosById);
  const review = reviewForCase(tc, scenarioReviews);
  const reviewFindings = review?.findings ?? [];
  const reviewSuggestions = (review?.findings ?? [])
    .map((f) => f.suggestion)
    .filter((s): s is string => Boolean(s));
  const editableTotal = testCases.length;
  const draftEdits = testCases.filter((row) => row.status === "draft").length;
  const validationIssues = testCases.filter((row) => traceabilityHealth(row) !== "Good" || reviewStatus(row) === "Needs Review").length;
  const readyForApproval = testCases.filter((row) => traceabilityHealth(row) === "Good" && reviewStatus(row) !== "Needs Review").length;
  const automationReady = testCases.filter((row) => row.automation_candidate).length;
  const blocked = testCases.filter((row) => row.status === "blocked").length;
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
  const router = useRouter();
  const [uiNotice, setUiNotice] = useState("");
  const [uiError, setUiError] = useState("");
  const [busyAction, setBusyAction] = useState<"save" | "validate" | "approval" | null>(null);
  const [showMore, setShowMore] = useState(false);
  const [history, setHistory] = useState<TestCaseHistory[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [draft, setDraft] = useState<EditorDraft>(() => draftFromCase(tc));

  useEffect(() => {
    setDraft(draftFromCase(tc));
  }, [tc?.id]);

  const savedDraft = useMemo(() => draftFromCase(tc), [tc]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(savedDraft);

  const priorityOptions = useMemo(() => {
    const set = new Set(["Critical", "High", "Medium", "Low"]);
    testCases.forEach((row) => row.priority && set.add(row.priority));
    if (draft.priority) set.add(draft.priority);
    return Array.from(set);
  }, [testCases, draft.priority]);

  const testTypeOptions = useMemo(() => {
    const set = new Set(["functional", "integration", "regression", "performance", "security", "ui", "positive", "negative", "edge"]);
    testCases.forEach((row) => row.test_type && set.add(row.test_type));
    if (draft.testType) set.add(draft.testType);
    return Array.from(set).sort();
  }, [testCases, draft.testType]);

  const loadHistory = useCallback((caseId: number) => {
    setHistoryLoading(true);
    return testCasesApi.history(caseId)
      .then((res) => setHistory(res.data))
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
  }, []);

  useEffect(() => {
    if (!tc) {
      setHistory([]);
      return;
    }
    let cancelled = false;
    setHistoryLoading(true);
    testCasesApi.history(tc.id)
      .then((res) => { if (!cancelled) setHistory(res.data); })
      .catch(() => { if (!cancelled) setHistory([]); })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [tc?.id]);

  const notify = (message: string) => {
    setUiError("");
    setUiNotice(message);
  };

  function updateDraft<K extends keyof EditorDraft>(key: K, value: EditorDraft[K]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function updateStep(index: number, field: "action" | "expected_result", value: string) {
    setDraft((prev) => ({
      ...prev,
      steps: prev.steps.map((step, i) => i === index ? { ...step, [field]: value } : step),
    }));
  }

  function addStep() {
    setDraft((prev) => ({
      ...prev,
      steps: [...prev.steps, { step_number: prev.steps.length + 1, action: "", expected_result: "" }],
    }));
  }

  function removeStep(index: number) {
    setDraft((prev) => ({
      ...prev,
      steps: prev.steps.filter((_, i) => i !== index).map((step, i) => ({ ...step, step_number: i + 1 })),
    }));
  }

  function revertChanges() {
    setDraft(draftFromCase(tc));
    notify("Unsaved changes reverted to the last saved values.");
  }

  async function saveDraft() {
    if (!tc) return;
    setBusyAction("save");
    setUiError("");
    try {
      // Only send fields that actually changed. The backend locks title
      // edits once execution results exist (409 "Cannot change title after
      // execution results exist") based on the field's mere presence in the
      // payload, not whether its value differs — so an unchanged title must
      // never ride along with an unrelated edit (e.g. priority).
      const payload: Partial<TestCase> & { comment?: string; status: string } = { status: "draft" };
      if (draft.title !== savedDraft.title) payload.title = draft.title;
      if (draft.priority !== savedDraft.priority) payload.priority = draft.priority;
      if (draft.testType !== savedDraft.testType) payload.test_type = draft.testType;
      if (draft.automationCandidate !== savedDraft.automationCandidate) payload.automation_candidate = draft.automationCandidate;
      if (draft.preconditionsText !== savedDraft.preconditionsText) payload.preconditions = splitLines(draft.preconditionsText);
      if (JSON.stringify(draft.steps) !== JSON.stringify(savedDraft.steps)) payload.steps = draft.steps;
      if (draft.expectedResult !== savedDraft.expectedResult) payload.expected_result = draft.expectedResult;

      const res = await testCasesApi.update(tc.id, payload);
      setDraft(draftFromCase(res.data));
      notify(`${tc.test_case_id} saved as draft.`);
      await Promise.all([onReload(), loadHistory(tc.id)]);
    } catch (error) {
      setUiError(messageFromError(error, "Could not save draft."));
    } finally {
      setBusyAction(null);
    }
  }

  // No on-demand test-case validation endpoint exists — automated validation is
  // performed by the coverage review agent. Surface its real verdict/score
  // instead of fabricating a result.
  function validateCase() {
    if (!tc) return;
    if (!review) {
      notify(`${tc.test_case_id} has no automated coverage review yet. Validation runs when the review agent processes its scenario.`);
      return;
    }
    const score = typeof review.overall_score === "number" ? `, overall score ${review.overall_score}/100` : "";
    notify(`Latest coverage review for ${tc.test_case_id}: ${review.verdict.replace(/_/g, " ")}${score}.`);
  }

  // Contract gate: title, preconditions, steps and expected result must be
  // present before a test case can move to approval.
  const approvalBlockers: string[] = [];
  if (dirty) approvalBlockers.push("Save your changes before sending to approval.");
  if (!draft.title.trim()) approvalBlockers.push("Title is required.");
  if (!splitLines(draft.preconditionsText).length) approvalBlockers.push("At least one precondition is required.");
  if (!draft.steps.length || draft.steps.some((s) => !s.action.trim() || !s.expected_result.trim())) {
    approvalBlockers.push("Every test step needs an action and expected result.");
  }
  if (!draft.expectedResult.trim()) approvalBlockers.push("Overall expected result is required.");

  async function sendToApproval() {
    if (!tc || approvalBlockers.length) return;
    setBusyAction("approval");
    setUiError("");
    try {
      await testCasesApi.update(tc.id, { status: "pending_approval" });
      notify(`${tc.test_case_id} sent to approval.`);
      await Promise.all([onReload(), loadHistory(tc.id)]);
    } catch (error) {
      setUiError(messageFromError(error, "Could not send test case to approval."));
    } finally {
      setBusyAction(null);
    }
  }

  function viewRequirement() {
    const reqId = tc?.linked_requirement_id ?? req?.id;
    if (!tc?.project_id || !reqId) {
      setUiError("No linked requirement to open for this test case.");
      return;
    }
    router.push(`/requirements?project=${tc.project_id}&view=analysis&requirement=${reqId}`);
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
            {tc && dirty && (
              <Button variant="outline" size="sm" onClick={revertChanges} disabled={busyAction !== null} className="h-9 gap-2 border-slate-200 text-xs font-bold text-slate-600">
                Revert
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={saveDraft} disabled={!tc || busyAction !== null || !dirty} className="h-9 gap-2 border-blue-200 text-xs font-bold text-[#1b59f8]">
              {busyAction === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
              Save Draft
              {tc && dirty && <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />}
            </Button>
            <Button variant="outline" size="sm" onClick={validateCase} disabled={!tc || busyAction !== null} className="h-9 gap-2 border-blue-200 text-xs font-bold text-[#1b59f8]">
              {busyAction === "validate" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              Validate
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={sendToApproval}
              disabled={!tc || busyAction !== null || approvalBlockers.length > 0}
              title={approvalBlockers.length ? approvalBlockers.join(" ") : undefined}
              className="h-9 gap-2 bg-[#1b59f8] text-xs font-bold text-white hover:bg-[#1546c2]"
            >
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
          <StatCard title="Total Editable Cases" value={editableTotal} subtitle="All generated cases" icon={FileText} tone="blue" />
          <StatCard title="Draft" value={draftEdits} subtitle={pctOf(draftEdits, editableTotal, "in draft")} icon={FileText} tone="blue" />
          <StatCard title="Validation Issues" value={validationIssues} subtitle={pctOf(validationIssues, editableTotal, "need fixes")} icon={AlertTriangle} tone="red" />
          <StatCard title="Ready for Approval" value={readyForApproval} subtitle={pctOf(readyForApproval, editableTotal, "ready")} icon={ShieldCheck} tone="emerald" />
          <StatCard title="Automation Ready" value={automationReady} subtitle={pctOf(automationReady, editableTotal, "automation candidate")} icon={Layers} tone="emerald" />
          <StatCard title="Blocked" value={blocked} subtitle={pctOf(blocked, editableTotal, "blocked")} icon={Zap} tone="red" />
        </div>

        <div className="grid grid-cols-[minmax(0,1fr)_160px] gap-4">
          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <p className="mb-4 text-[11px] font-extrabold uppercase tracking-wide text-slate-800">Editing Readiness Check</p>
            <div className="grid grid-cols-2 gap-x-6 gap-y-4 xl:grid-cols-4">
              <ReadinessItem
                label="Requirement Linked"
                value={tc?.linked_requirement_key || req?.requirement_id || "Not linked"}
                tone={tc?.linked_requirement_key || req?.requirement_id ? "emerald" : "amber"}
              />
              <ReadinessItem
                label="Scenario Linked"
                value={scenario?.scenario_id || "Not linked"}
                tone={scenario ? "emerald" : "amber"}
              />
              <ReadinessItem
                label="Steps"
                value={steps.length ? `${steps.length} step${steps.length === 1 ? "" : "s"}` : "None"}
                tone={steps.length ? "emerald" : "amber"}
              />
              <ReadinessItem
                label="Expected Result"
                value={tc?.expected_result ? "Present" : "Missing"}
                tone={tc?.expected_result ? "emerald" : "amber"}
              />
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-bold text-slate-500">Coverage Review</p>
            {review ? (
              <>
                <p className="mt-5 text-xl font-extrabold text-slate-950">
                  {typeof review.overall_score === "number" ? `${review.overall_score}/100` : "—"}
                </p>
                <span className={badgeClass(review.verdict === "pass" ? "emerald" : review.verdict === "fail" ? "red" : "amber")}>
                  {review.verdict.replace(/_/g, " ")}
                </span>
              </>
            ) : (
              <p className="mt-5 text-xs font-semibold text-slate-500">No automated coverage review recorded yet.</p>
            )}
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
                  {editorRows.length === 0 ? (
                    <div className="py-16 text-center text-xs font-semibold text-slate-400">No test cases match the selected filters.</div>
                  ) : editorRows.map((row) => {
                    const rowReq = findRequirementForCase(row, requirementsByKey, requirementsById);
                    const selected = tc?.id === row.id;
                    const issue = traceabilityHealth(row) !== "Good" || reviewStatus(row) === "Needs Review";
                    return (
                      <button
                        key={row.id}
                        onClick={() => setSelectedTestCase(row)}
                        className={cn("grid w-full items-center px-3 py-3 text-left text-[10px] transition hover:bg-slate-50", selected && "border-l-2 border-[#1b59f8] bg-blue-50/30")}
                        style={{ gridTemplateColumns: EDITOR_TABLE_GRID }}
                      >
                        <span className="font-mono font-extrabold text-[#1b59f8]">{row.test_case_id}</span>
                        <span>
                          <span className="block font-bold text-slate-800">{row.linked_requirement_key || rowReq?.requirement_id || "—"}</span>
                          <span className="block text-slate-500">{ppmFromRequirement(rowReq)}</span>
                        </span>
                        <span className="pr-2 font-bold leading-4 text-slate-800">{row.title}</span>
                        <span><span className={badgeClass(testType(row) === "Negative" ? "red" : "blue")}>{testType(row)}</span></span>
                        <span><span className={badgeClass("slate")}>{scenarioClass(row)}</span></span>
                        <span><span className={badgeClass(priorityTone(row.priority))}>{row.priority}</span></span>
                        <span><span className={badgeClass("slate")}>{row.status.replace(/_/g, " ")}</span></span>
                        <span><span className={badgeClass(issue ? "amber" : "emerald")}>{issue ? "Issues" : "Valid"}</span></span>
                        <span className="flex justify-end"><span className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 text-slate-500"><MoreHorizontal className="h-3.5 w-3.5" /></span></span>
                      </button>
                    );
                  })}
                </div>
              )}
              <div className="flex items-center justify-between border-t border-slate-100 px-3 py-3">
                <span className="text-xs font-semibold text-slate-500">{editorRows.length} of {editableTotal} test cases</span>
              </div>
            </div>
          </div>

          <div className="min-w-0 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            {tc ? (
              <>
                <div className="mb-4 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-extrabold text-slate-950">{tc.test_case_id}</h2>
                    <span className={badgeClass(dirty ? "purple" : "slate")}>{dirty ? "Editing" : tc.status.replace(/_/g, " ")}</span>
                    {dirty ? (
                      <span className="text-[10px] font-bold text-amber-600">Unsaved changes</span>
                    ) : tc.updated_at && (
                      <span className="text-[10px] font-bold text-slate-400">Updated {relativeTime(tc.updated_at)}</span>
                    )}
                  </div>
                  <div className="flex gap-2 text-slate-500">
                    <button aria-label="Close" onClick={() => setSelectedTestCase(null)}><X className="h-4 w-4" /></button>
                  </div>
                </div>
                <div className="mb-4 flex items-center gap-5 rounded-lg border border-slate-200 bg-slate-50/40 px-3 py-2 text-xs font-semibold text-slate-600">
                  <span>Linked Requirement: <span className="font-bold text-[#1b59f8]">{tc.linked_requirement_key || req?.requirement_id || "—"}</span></span>
                  <span>{ppmFromRequirement(req)}</span>
                  <span className="min-w-0 flex-1 truncate">{req?.title || ""}</span>
                  {(tc.linked_requirement_id ?? req?.id) && <button onClick={viewRequirement} className="font-bold text-[#1b59f8]">View</button>}
                </div>
                <div className="grid grid-cols-4 gap-3">
                  <EditorField label="Test Type" value={draft.testType} onChange={(v) => updateDraft("testType", v)} select options={testTypeOptions} />
                  <EditorField label="Scenario Class" value={scenarioClass(tc)} />
                  <EditorField label="Priority" value={draft.priority} onChange={(v) => updateDraft("priority", v)} select options={priorityOptions} />
                  <EditorField label="Automation Candidate" value={draft.automationCandidate ? "Yes" : "No"} onChange={(v) => updateDraft("automationCandidate", v === "Yes")} select options={["Yes", "No"]} />
                </div>
                <div className="mt-3 grid grid-cols-[minmax(0,1fr)_120px_120px] gap-3">
                  <EditorField label="Title" value={draft.title} onChange={(v) => updateDraft("title", v)} />
                  <EditorField label="Test Case ID" value={tc.test_case_id} muted />
                  <EditorField label="Status" value={tc.status.replace(/_/g, " ")} muted />
                </div>
                <EditorSection title="Preconditions">
                  <textarea
                    aria-label="Preconditions"
                    value={draft.preconditionsText}
                    onChange={(event) => updateDraft("preconditionsText", event.target.value)}
                    rows={3}
                    placeholder="One precondition per line"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                  />
                </EditorSection>
                <EditorSection title="Test Steps" action="+ Add Step" onAction={addStep}>
                  {draft.steps.length ? (
                    <div className="overflow-hidden rounded-lg border border-slate-200">
                      <div className="grid grid-cols-[40px_minmax(160px,1fr)_minmax(160px,1fr)_32px] bg-slate-50 px-3 py-2 text-[10px] font-extrabold uppercase text-slate-500">
                        <span>#</span><span>Action</span><span>Expected Result</span><span></span>
                      </div>
                      {draft.steps.map((step, index) => (
                        <div key={index} className="grid grid-cols-[40px_minmax(160px,1fr)_minmax(160px,1fr)_32px] items-start gap-2 border-t border-slate-100 px-3 py-2 text-xs font-semibold text-slate-700">
                          <span className="mt-2 text-slate-500">{step.step_number}</span>
                          <textarea
                            aria-label={`Step ${step.step_number} action`}
                            value={step.action}
                            onChange={(event) => updateStep(index, "action", event.target.value)}
                            rows={2}
                            className="w-full rounded-md border border-slate-200 px-2 py-1 text-xs font-semibold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                          />
                          <textarea
                            aria-label={`Step ${step.step_number} expected result`}
                            value={step.expected_result}
                            onChange={(event) => updateStep(index, "expected_result", event.target.value)}
                            rows={2}
                            className="w-full rounded-md border border-slate-200 px-2 py-1 text-xs font-semibold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                          />
                          <button aria-label={`Remove step ${step.step_number}`} onClick={() => removeStep(index)} className="mt-1.5 text-slate-400 hover:text-red-600">
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs font-semibold text-slate-400">No test steps recorded. Use + Add Step to create one.</p>
                  )}
                </EditorSection>
                <EditorSection title="Expected Result (Overall)">
                  <textarea
                    aria-label="Overall expected result"
                    value={draft.expectedResult}
                    onChange={(event) => updateDraft("expectedResult", event.target.value)}
                    rows={3}
                    placeholder="Describe the overall expected outcome"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                  />
                </EditorSection>
                <EditorSection title="Test Data Dependency">
                  {tc.test_data && Object.keys(tc.test_data).length ? (
                    <div className="space-y-1 text-xs font-semibold text-slate-700">
                      {Object.entries(tc.test_data).map(([key, value]) => (
                        <div key={key} className="flex gap-2">
                          <span className="font-bold text-slate-500">{key}:</span>
                          <span className="min-w-0 break-words">{typeof value === "object" ? JSON.stringify(value) : String(value)}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs font-semibold text-slate-400">No test data dependency recorded.</p>
                  )}
                </EditorSection>
              </>
            ) : (
              <div className="flex h-full items-center justify-center text-xs font-semibold text-slate-500">Select a test case to edit.</div>
            )}
          </div>
        </div>
      </section>

      <aside className="sticky top-0 h-[calc(100vh-6rem)] overflow-y-auto rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-5 text-sm font-extrabold text-slate-950">Test Case Inspector</h2>
        <InspectorCard title="Traceability">
          <div className="grid grid-cols-[1fr_18px_1fr_18px_1fr] items-center gap-2 text-center text-[10px] font-bold">
            <TraceBox label="Requirement" value={`${tc?.linked_requirement_key || req?.requirement_id || "—"}\n${ppmFromRequirement(req)}`} />
            <ChevronRight className="h-4 w-4 text-slate-400" />
            <TraceBox label="Scenario" value={scenario?.scenario_id || "—"} />
            <ChevronRight className="h-4 w-4 text-slate-400" />
            <TraceBox label="Test Case" value={tc?.test_case_id || "—"} />
          </div>
        </InspectorCard>
        <InspectorCard title="Validation Findings" badge={reviewFindings.length ? `${reviewFindings.length} finding${reviewFindings.length === 1 ? "" : "s"}` : undefined}>
          {reviewFindings.length ? (
            <div className="space-y-3 text-xs font-semibold text-slate-700">
              {reviewFindings.map((f, index) => <Issue key={index} text={`${f.dimension}: ${f.issue}`} />)}
            </div>
          ) : (
            <p className="text-xs font-semibold text-slate-400">{review ? "No open findings on the latest coverage review." : "No automated review recorded yet."}</p>
          )}
        </InspectorCard>
        <InspectorCard title="Review Suggestions" badge={reviewSuggestions.length ? `${reviewSuggestions.length}` : undefined}>
          {reviewSuggestions.length ? (
            <div className="space-y-3 text-xs font-semibold text-slate-700">
              {reviewSuggestions.map((s, index) => <Suggestion key={index} text={s} />)}
            </div>
          ) : (
            <p className="text-xs font-semibold text-slate-400">No suggestions on the latest coverage review.</p>
          )}
        </InspectorCard>
        <InspectorCard title="Change History">
          {historyLoading ? (
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-400"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading history…</div>
          ) : history.length ? (
            <div className="space-y-4 text-xs">
              {history.slice(0, 8).map((h) => (
                <HistoryRow
                  key={h.id}
                  time={displayDate(h.created_at)}
                  actor={h.source === "platform" || !h.changed_by ? (h.source ? h.source.replace(/_/g, " ") : "System") : resolveUserName(userNames, h.changed_by)}
                  text={h.comment || `${h.field_name.replace(/_/g, " ")}${h.new_value ? ` → ${h.new_value}` : ""}`}
                />
              ))}
            </div>
          ) : (
            <p className="text-xs font-semibold text-slate-400">No change history recorded.</p>
          )}
        </InspectorCard>
        <InspectorCard title="Review & Audit">
          <div className="grid grid-cols-2 gap-3 text-xs">
            <InfoPair label="Created By" value={resolveUserName(userNames, tc?.created_by)} />
            <InfoPair label="Created On" value={displayDateTime(tc?.created_at)} />
            <InfoPair label="Last Updated By" value={resolveUserName(userNames, tc?.updated_by ?? tc?.last_status_updated_by)} />
            <InfoPair label="Last Updated On" value={displayDateTime(tc?.updated_at)} />
            <InfoPair label="Status" value={tc ? tc.status.replace(/_/g, " ") : "—"} />
            <InfoPair label="Coverage Verdict" value={review ? review.verdict.replace(/_/g, " ") : "Not reviewed"} />
          </div>
        </InspectorCard>
        <div className="space-y-3 pt-1">
          <p className="text-xs font-extrabold text-slate-800">Actions</p>
          <Button onClick={saveDraft} disabled={!tc || busyAction !== null || !dirty} className="h-10 w-full bg-[#1b59f8] text-xs font-bold text-white hover:bg-[#1546c2]">Save Draft</Button>
          <Button onClick={validateCase} disabled={!tc || busyAction !== null} variant="outline" className="h-10 w-full border-emerald-300 text-xs font-bold text-emerald-700">Check Coverage Review</Button>
          <Button
            onClick={sendToApproval}
            disabled={!tc || busyAction !== null || approvalBlockers.length > 0}
            title={approvalBlockers.length ? approvalBlockers.join(" ") : undefined}
            variant="outline"
            className="h-10 w-full border-blue-300 text-xs font-bold text-[#1b59f8]"
          >
            Send to Approval
          </Button>
          {tc && approvalBlockers.length > 0 && (
            <p className="flex items-start gap-1.5 text-[10px] font-semibold leading-snug text-amber-700">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              <span>{approvalBlockers[0]}</span>
            </p>
          )}
        </div>
      </aside>
    </div>
  );
}

// Editable when onChange is supplied (writes into the editor draft, saved
// via Save Draft — see saveDraft). Falls back to a read-only display for
// derived fields (Scenario Class) and identifiers (Test Case ID, Status).
function EditorField({
  label,
  value,
  onChange,
  select,
  options,
  muted,
}: {
  label: string;
  value: string;
  onChange?: (value: string) => void;
  select?: boolean;
  options?: string[];
  muted?: boolean;
}) {
  if (!onChange) {
    return (
      <div className="block">
        <span className="mb-1.5 block text-[10px] font-extrabold text-slate-500">{label}</span>
        <div className={cn("flex h-10 w-full items-center truncate rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-800", muted ? "bg-slate-50" : "bg-white")}>
          {value}
        </div>
      </div>
    );
  }
  return (
    <label className="block">
      <span className="mb-1.5 block text-[10px] font-extrabold text-slate-500">{label}</span>
      {select ? (
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
        >
          {(options ?? []).map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      ) : (
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
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
      {value.split("\n").map((line, index) => (
        <p key={index} className={cn("font-extrabold", line.startsWith("REQ") || line.startsWith("TC") || line.startsWith("SCN") ? "text-[#1b59f8]" : "text-slate-600")}>{line}</p>
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
