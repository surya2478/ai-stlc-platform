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
  Radar,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  TestTube2,
  Upload,
  X,
  Zap,
} from "lucide-react";
import {
  agentRunsApi,
  applicationsApi,
  automationClassificationApi,
  exportApi,
  isClassificationDisabled,
  projectsApi,
  requirementsApi,
  reviewsApi,
  scenariosApi,
  taxonomyApi,
  testCaseImportApi,
  testCasesApi,
  usersApi,
  type ArtifactReview,
  type AutomationClassificationPolicy,
  type ClassificationPolicySimulateResponse,
  type CoverageMatrixEntry,
  type ProjectApplication,
  type Requirement,
  type TaxonomyEntry,
  type TestCase,
  type TestCaseAutomationClassification,
  type TestCaseHistory,
  type TestCaseImportPreview,
  type TestScenario,
  type TestCaseSummary,
} from "@/lib/api";
import { AutomationHandoffPanel } from "@/components/automation/AutomationHandoffPanel";
import { Button } from "@/components/ui/button";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerBody, DrawerFooter } from "@/components/ui/drawer";
import { cn } from "@/lib/utils";
import { TestCasesTabs } from "@/components/test-cases/TestCasesTabs";
import { ExecutionPathPanel } from "@/components/test-cases/ExecutionPathPanel";
import { JourneyGraphView } from "./JourneyGraphView";
import { TestCaseApprovalView } from "./TestCaseApprovalView";
import { useAIAction } from "@/hooks/useAIAction";
import { AI_PROCESSING_STAGES } from "@/lib/ai-processing-stages";
import { terminalAIStatus } from "@/lib/ai-processing-status";

// "path" leads: "why won't this run yet?" is the question a reader arrives
// with. It is a tab rather than a banner so it does not push the rest of the
// drawer down — the existing flow stays exactly where it was.
type DrawerTab = "path" | "overview" | "cases" | "coverage" | "ai" | "activity";
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

const TABLE_GRID = "70px 110px minmax(380px,1fr) 72px 100px 64px 76px 76px 76px 68px 96px 96px 94px 98px 110px 48px";
const EDITOR_TABLE_GRID = "74px 102px minmax(128px,1fr) 72px 92px 62px 70px 70px 70px 56px 76px 84px 46px";

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
  // UAT template fields. The selected application/test-case input is stored
  // as a governed taxonomy FK; the editor loads the complete master-table
  // options whenever no FK has been provided.
  domainId: number | null;
  channelId: number | null;
  productId: number | null;
  areaOfTestId: number | null;
  subRequestTypeId: number | null;
  testCaseTypeId: number | null;
  testCaseComplexityId: number | null;
  testCaseObjective: string;
  atcTestCase: string;
  isCritical: boolean;
  ppmId: string;
};

/**
 * One step shape for the whole page, whatever the row actually stores.
 *
 * Steps reach us in two shapes. The canonical one — {step_number, action,
 * expected_result} — is what the test-case agent, the importer and this
 * editor write. Playwright Studio writes {action, expected} with no step
 * number (studio_service._approve_plan), and older agent rows omit fields
 * entirely. The declared TestCase type promises `action: string;
 * expected_result: string`, so TypeScript never flagged the difference and a
 * bare `step.expected_result.trim()` threw "Cannot read properties of
 * undefined" — taking the whole /test-cases page down for any project holding
 * a Studio-approved test case (observed live on project 12).
 *
 * Normalizing on read rather than repairing the rows: both shapes are already
 * persisted and the backend reads both too (export_service does the same
 * fallback), so the page has to cope with either regardless.
 */
function normalizedSteps(
  steps: TestCase["steps"] | null | undefined,
): Array<{ step_number: number; action: string; expected_result: string }> {
  return (steps ?? []).map((s, i) => {
    const raw = (s ?? {}) as {
      step_number?: number; action?: string; expected_result?: string; expected?: string;
    };
    return {
      step_number: raw.step_number ?? i + 1,
      action: raw.action ?? "",
      expected_result: raw.expected_result ?? raw.expected ?? "",
    };
  });
}

function draftFromCase(t: TestCase | null): EditorDraft {
  return {
    title: t?.title ?? "",
    priority: t?.priority ?? "",
    testType: t?.test_type ?? "",
    automationCandidate: !!t?.automation_candidate,
    preconditionsText: (t?.preconditions ?? []).join("\n"),
    steps: normalizedSteps(t?.steps),
    expectedResult: t?.expected_result ?? "",
    domainId: t?.domain_id ?? null,
    channelId: t?.channel_id ?? null,
    productId: t?.product_id ?? null,
    areaOfTestId: t?.area_of_test_id ?? null,
    subRequestTypeId: t?.sub_request_type_id ?? null,
    testCaseTypeId: t?.test_case_type_id ?? null,
    testCaseComplexityId: t?.test_case_complexity_id ?? null,
    testCaseObjective: t?.test_case_objective ?? "",
    atcTestCase: t?.atc_test_case ?? "",
    isCritical: !!t?.is_critical,
    ppmId: t?.ppm_id ?? "",
  };
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalize(value: string | null | undefined) {
  return (value || "").toLowerCase().replace(/[_-]/g, " ");
}

function availableFilterOptions(values: string[]) {
  return [
    "all",
    ...Array.from(new Set(values.filter((value) => value.trim()))).sort((left, right) =>
      left.localeCompare(right),
    ),
  ];
}

function reviewScorePercent(score: number) {
  return Math.round(Math.max(0, Math.min(5, score)) * 20);
}

function reviewScoreLabel(score: number) {
  return `${score.toFixed(1)}/5 (${reviewScorePercent(score)}%)`;
}

function compareTestCaseIds(left: TestCase, right: TestCase) {
  const byDisplayId = left.test_case_id.localeCompare(right.test_case_id, undefined, {
    numeric: true,
    sensitivity: "base",
  });
  return byDisplayId || left.id - right.id;
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
  // No fabricated default — an unclassified test case shows blank rather
  // than a guessed category (CLAUDE.md: never show static/fabricated
  // values as if they were live data).
  const raw = tc.test_type || tc.test_phase || tc.telecom_domain || "";
  if (!raw) return "";
  const normalized = normalize(raw);
  if (normalized.includes("happy") || normalized.includes("positive")) return "Happy Path";
  if (normalized.includes("input")) return "Input Validation";
  if (normalized.includes("auth")) return "Authorization";
  if (normalized.includes("payment")) return "Payment Validation";
  if (normalized.includes("notification")) return "Notification";
  return raw;
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

function approvalReadinessBlockers(tc: TestCase): string[] {
  const blockers: string[] = [];
  const steps = normalizedSteps(tc.steps);
  if (!(tc.title ?? "").trim()) blockers.push("Add a clear test-case title.");
  if (!(tc.preconditions ?? []).some((item) => (item ?? "").trim())) blockers.push("Add at least one precondition.");
  if (!steps.length) {
    blockers.push("Add at least one test step with an action and expected result.");
  } else if (steps.some((step) => !step.action.trim() || !step.expected_result.trim())) {
    blockers.push("Complete the action and expected result for every test step.");
  }
  if (!tc.expected_result?.trim()) blockers.push("Add the overall expected result.");
  return blockers;
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

function classificationStatusTone(status: string): Tone {
  if (status === "RECOMMENDED" || status === "APPROVED") return "emerald";
  if (status === "CONDITIONAL" || status === "DEFERRED" || status === "POLICY_STALE" || status === "RECLASSIFICATION_REQUIRED") return "amber";
  if (status === "NOT_RECOMMENDED" || status === "BLOCKED") return "red";
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
        <p className="min-w-0 truncate text-xs font-semibold text-slate-800">{title}</p>
      </div>
      <div className="mt-7">
        <p className="text-2xl font-bold leading-none text-slate-950">{value}</p>
        <p className="mt-3 text-xs font-normal text-slate-500">{subtitle}</p>
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
        <p className="text-xs font-semibold text-slate-800">{label}</p>
        <p className="mt-0.5 text-sm font-bold leading-none text-slate-950">{value}</p>
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
  testCaseCountByScenarioId,
  selectedScenarioIds,
  setSelectedScenarioIds,
  generating,
  onGenerate,
  onRegenerate,
}: {
  scenarios: TestScenario[];
  requirementsById: Map<number, Requirement>;
  testCaseCountByScenarioId: Map<number, number>;
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
                  const generatedTestCaseCount = testCaseCountByScenarioId.get(scenario.id) ?? 0;
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
                        <span className="flex min-w-0 flex-1 items-center gap-2">
                          <span className="min-w-0 truncate text-xs font-semibold text-slate-700">{scenario.title}</span>
                          <span className="inline-flex shrink-0 items-center gap-2">
                            {req && (
                              <span className="font-mono text-[10px] font-bold text-slate-500">
                                {req.requirement_id}
                              </span>
                            )}
                            <span
                              className={cn(
                                "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-bold",
                                generatedTestCaseCount > 0
                                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                  : "border-slate-200 bg-slate-50 text-slate-500",
                              )}
                              title={
                                generatedTestCaseCount > 0
                                  ? `${generatedTestCaseCount} test case${generatedTestCaseCount === 1 ? "" : "s"} generated from this scenario`
                                  : "No test cases generated from this scenario"
                              }
                            >
                              {generatedTestCaseCount > 0 && <CheckCircle className="h-3 w-3" />}
                              TCs: {generatedTestCaseCount > 0 ? `Y (${generatedTestCaseCount})` : "N"}
                            </span>
                            <span className={badgeClass(priorityTone(scenario.priority))}>{scenario.priority}</span>
                          </span>
                        </span>
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
  const { runAIAction, updateAIProcessing } = useAIAction();
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
  const [generatedTab, setGeneratedTab] = useState("all");
  const [editorTab, setEditorTab] = useState("all");
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [classFilter, setClassFilter] = useState("all");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [automationFilter, setAutomationFilter] = useState("all");
  const [reviewFilter, setReviewFilter] = useState("all");
  const [generatedFiltersOpen, setGeneratedFiltersOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [userNames, setUserNames] = useState<Map<number, string>>(new Map());
  const [coverageByCase, setCoverageByCase] = useState<Map<number, CoverageMatrixEntry>>(new Map());
  const [scenarioReviews, setScenarioReviews] = useState<ArtifactReview[]>([]);
  const [scenariosById, setScenariosById] = useState<Map<number, TestScenario>>(new Map());
  const [classifications, setClassifications] = useState<TestCaseAutomationClassification[]>([]);
  const [classificationsEnabled, setClassificationsEnabled] = useState(true);
  const [actionMenu, setActionMenu] = useState<number | null>(null);
  const [classifyBusyId, setClassifyBusyId] = useState<number | null>(null);
  const [policyDrawerTestCase, setPolicyDrawerTestCase] = useState<TestCase | null>(null);

  // Registered applications, for the Automation Handoff card below.
  //
  // `TestCase.application_id` has existed and been audited since the registry
  // shipped, and Live Discovery Session refuses any test case that lacks it
  // ("no Application Registry mapping — map it in Test Case Approval first"),
  // but no screen ever wrote the field. That message pointed at a control that
  // did not exist, which made the whole Approved TC → Discovery → Model →
  // Studio path unreachable. This is that control.
  const [applications, setApplications] = useState<ProjectApplication[]>([]);
  const [applicationSaveBusy, setApplicationSaveBusy] = useState(false);

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
      applicationsApi
        .getForProject(selectedProject)
        .then((res) => setApplications(res.data.applications.filter((a) => a.is_active)))
        .catch(() => setApplications([]));
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

    // Classification is loaded separately so a service error does not hide test-case content.
    try {
      const clsRes = await automationClassificationApi.listForProject(selectedProject);
      setClassifications(clsRes.data);
      setClassificationsEnabled(true);
    } catch (clsError) {
      setClassifications([]);
      setClassificationsEnabled(!isClassificationDisabled(clsError));
    }
  }, [selectedProject]);

  const classificationByTestCaseId = useMemo(
    () => new Map(classifications.map((item) => [item.test_case_id, item])),
    [classifications],
  );

  const exportProject = useCallback(async () => {
    if (!selectedProject || exporting) return;
    setExporting(true);
    try {
      await exportApi.downloadTestCases(selectedProject, "excel");
    } catch {
      setError("Export failed. Please try again.");
    } finally {
      setExporting(false);
    }
  }, [selectedProject, exporting]);

  const [importOpen, setImportOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<TestCaseImportPreview | null>(null);
  const [previewingImport, setPreviewingImport] = useState(false);
  const [confirmingImport, setConfirmingImport] = useState(false);
  const [importError, setImportError] = useState("");
  const [importResult, setImportResult] = useState<string>("");

  const handleImportPreview = useCallback(async () => {
    if (!selectedProject || !importFile) return;
    setPreviewingImport(true);
    setImportError("");
    setImportResult("");
    try {
      const res = await testCaseImportApi.preview(selectedProject, importFile);
      setImportPreview(res.data);
    } catch (err) {
      setImportError(messageFromError(err, "Could not parse that file."));
      setImportPreview(null);
    } finally {
      setPreviewingImport(false);
    }
  }, [selectedProject, importFile]);

  const handleImportConfirm = useCallback(async () => {
    if (!selectedProject || !importPreview) return;
    setConfirmingImport(true);
    setImportError("");
    try {
      const res = await testCaseImportApi.confirm(selectedProject, importPreview.preview_token);
      setImportResult(`Imported ${res.data.imported_count} test case(s)${res.data.skipped_count ? `, skipped ${res.data.skipped_count}` : ""}.`);
      setImportPreview(null);
      setImportFile(null);
      await loadData();
    } catch (err) {
      setImportError(messageFromError(err, "Import failed."));
    } finally {
      setConfirmingImport(false);
    }
  }, [selectedProject, importPreview, loadData]);

  const testCaseCountByScenarioId = useMemo(() => {
    const counts = new Map<number, number>();
    testCases.forEach((testCase) => {
      const scenarioId = testCase.linked_scenario_id ?? testCase.scenario_id;
      if (scenarioId) counts.set(scenarioId, (counts.get(scenarioId) ?? 0) + 1);
    });
    return counts;
  }, [testCases]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    setGeneratedTab("all");
    setEditorTab("all");
    setQuery("");
    setTypeFilter("all");
    setClassFilter("all");
    setPriorityFilter("all");
    setAutomationFilter("all");
    setReviewFilter("all");
    setGeneratedFiltersOpen(false);
  }, [selectedProject]);

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

  const typeFilterOptions = useMemo(
    () => availableFilterOptions(testCases.map(testType)),
    [testCases],
  );
  const classFilterOptions = useMemo(
    () => availableFilterOptions(testCases.map(scenarioClass)),
    [testCases],
  );
  const priorityFilterOptions = useMemo(
    () => availableFilterOptions(testCases.map((testCase) => testCase.priority)),
    [testCases],
  );
  const reviewFilterOptions = useMemo(
    () => availableFilterOptions(testCases.map(reviewStatus)),
    [testCases],
  );
  const activeGeneratedFilterCount = [
    typeFilter,
    classFilter,
    priorityFilter,
    automationFilter,
    reviewFilter,
  ].filter((filter) => filter !== "all").length;

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
        generatedTab === "all" ||
        (generatedTab === "gaps" && traceabilityHealth(tc) !== "Good") ||
        normalize(rowType).includes(normalize(generatedTab)) ||
        normalize(rowClass).includes(normalize(generatedTab));
      const queryOk = !query.trim() || rowText.includes(query.trim().toLowerCase());
      const typeOk = typeFilter === "all" || normalize(rowType) === normalize(typeFilter);
      const classOk = classFilter === "all" || normalize(rowClass) === normalize(classFilter);
      const priorityOk = priorityFilter === "all" || normalize(tc.priority) === normalize(priorityFilter);
      const automationOk =
        automationFilter === "all" ||
        (automationFilter === "yes" && tc.automation_candidate) ||
        (automationFilter === "no" && !tc.automation_candidate);
      const reviewOk = reviewFilter === "all" || normalize(rowReview) === normalize(reviewFilter);
      return tabOk && queryOk && typeOk && classOk && priorityOk && automationOk && reviewOk;
    }).sort(compareTestCaseIds);
  }, [automationFilter, classFilter, generatedTab, priorityFilter, query, requirementsById, requirementsByKey, reviewFilter, testCases, typeFilter]);

  const selectedRequirement = selectedTestCase ? findRequirementForCase(selectedTestCase, requirementsByKey, requirementsById) : undefined;
  const linkedCases = selectedTestCase
    ? testCases.filter((tc) => (tc.linked_requirement_key || tc.requirement_id) === (selectedTestCase.linked_requirement_key || selectedTestCase.requirement_id))
    : [];
  const selectedScenario = scenarioForCase(selectedTestCase, scenariosById);
  const selectedReview = reviewForCase(selectedTestCase, scenarioReviews);
  const selectedEligibility = (selectedTestCase?.metadata_ as { automation_eligibility?: { verdict?: string; reason?: string; automation_style?: string; agent_run_id?: number } } | undefined)?.automation_eligibility;
  const selectedClassification = selectedTestCase ? classificationByTestCaseId.get(selectedTestCase.id) : undefined;
  const selectedApprovalBlockers = selectedTestCase ? approvalReadinessBlockers(selectedTestCase) : [];
  const selectedIsInApproval = selectedTestCase
    ? selectedTestCase.status === "pending_approval"
      || selectedTestCase.status === "approved"
      || selectedTestCase.approval_status === "pending"
      || selectedTestCase.approval_status === "approved"
    : false;

  async function classifyTestCase(id: number) {
    if (!selectedProject) return;
    setClassifyBusyId(id);
    setError("");
    try {
      await runAIAction({
        actionName: "classify_automation_eligibility",
        title: "Classifying Automation Eligibility",
        module: "Test Design",
        artifactType: "Automation Classification",
        projectId: selectedProject,
        testCaseId: id,
        stages: AI_PROCESSING_STAGES.automationClassification,
        successMessage: "Automation classification is queued and ready to track.",
        execute: () => automationClassificationApi.evaluate(selectedProject, [id]),
      });
      setNotice("Classification queued — refresh in a moment to see the recommendation.");
      setActionMenu(null);
      await loadData();
    } catch (classifyError) {
      setError(messageFromError(classifyError, "Could not queue classification."));
    } finally {
      setClassifyBusyId(null);
    }
  }

  async function reclassifyTestCase(classificationId: number) {
    setClassifyBusyId(classificationId);
    setError("");
    try {
      await runAIAction({
        actionName: "reclassify_automation_eligibility",
        title: "Reclassifying Automation Eligibility",
        module: "Test Design",
        artifactType: "Automation Classification",
        projectId: selectedProject ?? undefined,
        stages: AI_PROCESSING_STAGES.automationClassification,
        successMessage: "Automation reclassification is queued.",
        execute: () => automationClassificationApi.reclassify(classificationId),
      });
      setNotice("Reclassification queued — refresh in a moment to see the updated recommendation.");
      setActionMenu(null);
      await loadData();
    } catch (classifyError) {
      setError(messageFromError(classifyError, "Could not queue reclassification."));
    } finally {
      setClassifyBusyId(null);
    }
  }

  async function sendCaseToApproval(id: number) {
    try {
      await testCasesApi.update(id, { status: "pending_approval" });
      setNotice("Test case sent to approval.");
      await loadData();
    } catch (updateError) {
      setError(messageFromError(updateError, "Could not send test case to approval."));
    }
  }

  async function saveApplicationMapping(id: number, applicationId: number | null) {
    setApplicationSaveBusy(true);
    setError("");
    try {
      await testCasesApi.update(id, { application_id: applicationId });
      setNotice(
        applicationId === null
          ? "Application mapping cleared."
          : "Application mapped. This test case can now be taken through Live Discovery Session.",
      );
      await loadData();
    } catch (updateError) {
      setError(messageFromError(updateError, "Could not save the application mapping."));
    } finally {
      setApplicationSaveBusy(false);
    }
  }

  function openInEditor(id: number) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("view", "editor");
    params.set("case", String(id));
    router.push(`${pathname}?${params.toString()}`);
  }

  function openInApproval(id: number) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("view", "approval");
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
      await runAIAction({
        actionName: "generate_test_cases",
        title: "Generating Test Cases",
        module: "Test Design",
        artifactType: "Test Cases",
        projectId: selectedProject,
        stages: AI_PROCESSING_STAGES.testCaseGeneration,
        successMessage: "Test cases generated successfully.",
        execute: async () => {
      const res = await testCasesApi.generateCases(selectedProject, scenarioIds.length ? scenarioIds : undefined, reqIds, overrideQualityGate);
      const data = res.data as Record<string, unknown>;
      const agentRunId = typeof data.agent_run_id === "number" ? data.agent_run_id : null;
      if (agentRunId) {
        updateAIProcessing({ status: "waiting", agentRunId: String(agentRunId), currentStage: "Waiting for the test-case agent" });
        setNotice("Test case generation is running...");
        let firstPoll = true;
        while (true) {
          await sleep(firstPoll ? 1000 : 2000);
          firstPoll = false;
          const run = (await agentRunsApi.get(agentRunId)).data;
          const terminalStatus = terminalAIStatus(run.status);
          if (terminalStatus) {
            const message = run.error_message || "Test case generation failed.";
            setNotice("");
            updateAIProcessing({ status: terminalStatus, currentStage: run.status, errorCategory: "AI processing failed", errorMessage: message });
            await loadData();
            throw new Error(message);
          }
          if (run.progress_message) {
            updateAIProcessing({ status: "processing", currentStage: run.progress_message });
          }
          if (run.status === "completed") {
            const count = Number(run.output_data?.count ?? 0);
            setNotice(count > 0 ? `Generated ${count} test case${count === 1 ? "" : "s"}.` : "Generation completed. No new test cases were created.");
            await loadData();
            return;
          }
          setNotice(run.progress_message ? `Test case generation: ${run.progress_message}` : "Test case generation is running...");
        }
      } else {
        setNotice(String(data.message || "Test cases generated."));
        await loadData();
      }
      return res;
        },
      });
    } catch (generateError) {
      setError(messageFromError(generateError, "Could not generate test cases."));
    } finally {
      setGenerating(false);
    }
  }

  if (view === "journey-graph") {
    return (
      <>
        <TestCasesTabs active="journey-graph" projectId={selectedProject} />
        <JourneyGraphView projectId={selectedProject} />
      </>
    );
  }

  if (view === "approval") {
    const requestedCaseId = Number(searchParams.get("case"));
    return (
      <>
        <TestCasesTabs active="approval" projectId={selectedProject} />
        <TestCaseApprovalView projectId={selectedProject} initialTestCaseId={Number.isFinite(requestedCaseId) ? requestedCaseId : null} />
      </>
    );
  }

  if (view === "editor") {
    return (
      <>
      <TestCasesTabs active="editor" projectId={selectedProject} />
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
        activeTab={editorTab}
        setActiveTab={setEditorTab}
        loading={loading}
        setSelectedTestCase={setSelectedTestCase}
        selectedProject={selectedProject}
        classifications={classifications}
        classificationsEnabled={classificationsEnabled}
        onClassificationsChanged={loadData}
      />
      </>
    );
  }

  return (
    <div className="min-h-full">
      <section className="space-y-5 pb-4">
        <TestCasesTabs active="generated" projectId={selectedProject} />
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
              <p className="mt-1 text-sm font-normal leading-5 text-slate-500">
                AI-generated test cases from approved requirements and traceability context.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => { setImportOpen(true); setImportError(""); setImportResult(""); }}
              disabled={!selectedProject}
              className="h-9 gap-2 border-slate-200 text-xs font-bold"
            >
              <Upload className="h-4 w-4" />
              Import
            </Button>
            <Button variant="outline" size="sm" onClick={exportProject} disabled={exporting || !selectedProject} className="h-9 gap-2 border-slate-200 text-xs font-bold">
              {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
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
          testCaseCountByScenarioId={testCaseCountByScenarioId}
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
              const active = generatedTab === tab.key;
              return (
                <button
                  key={tab.key}
                  onClick={() => setGeneratedTab(tab.key)}
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

        <div className="flex items-center gap-3">
          <div className="relative min-w-72 flex-1">
            <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by TC ID, title, requirement, scenario..."
              className="h-10 w-full rounded-lg border border-slate-200 bg-white pl-11 pr-3 text-xs font-semibold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
            />
          </div>
          <Button
            variant="outline"
            size="sm"
            className={cn(
              "h-10 gap-2 border-slate-200 text-xs font-bold",
              (generatedFiltersOpen || activeGeneratedFilterCount > 0) && "border-blue-300 bg-blue-50 text-[#1b59f8]",
            )}
            onClick={() => setGeneratedFiltersOpen((open) => !open)}
            aria-expanded={generatedFiltersOpen}
            aria-controls="generated-test-case-filters"
          >
            <Filter className="h-4 w-4" />
            Filters
            {activeGeneratedFilterCount > 0 && (
              <span className="rounded-full bg-[#1b59f8] px-1.5 py-0.5 text-[10px] text-white">
                {activeGeneratedFilterCount}
              </span>
            )}
          </Button>
        </div>
        {generatedFiltersOpen && (
          <div
            id="generated-test-case-filters"
            aria-label="Generated test case filters"
            className="flex flex-wrap items-center gap-3 rounded-lg border border-blue-100 bg-blue-50/40 p-3"
          >
            <FilterSelect value={typeFilter} onChange={setTypeFilter} options={typeFilterOptions} label="Test Type" />
            <FilterSelect value={classFilter} onChange={setClassFilter} options={classFilterOptions} label="Scenario Class" />
            <FilterSelect value={priorityFilter} onChange={setPriorityFilter} options={priorityFilterOptions} label="Priority" />
            <FilterSelect value={automationFilter} onChange={setAutomationFilter} options={["all", "yes", "no"]} label="Automation" />
            <FilterSelect value={reviewFilter} onChange={setReviewFilter} options={reviewFilterOptions} label="Review Status" />
            {activeGeneratedFilterCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="h-10 gap-2 text-xs font-bold text-slate-600"
                onClick={() => {
                  setTypeFilter("all");
                  setClassFilter("all");
                  setPriorityFilter("all");
                  setAutomationFilter("all");
                  setReviewFilter("all");
                }}
              >
                <X className="h-4 w-4" />
                Clear filters
              </Button>
            )}
          </div>
        )}

        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="grid w-full min-w-[1760px] items-center gap-x-2 border-b border-slate-200 bg-slate-50/70 px-4 py-3 text-[9px] font-extrabold uppercase leading-4 tracking-wide text-slate-500" style={{ gridTemplateColumns: TABLE_GRID }}>
            <span>TC ID</span>
            <span>Req ID / PPM ID</span>
            <span>Title</span>
            <span>Test Type</span>
            <span>Scenario Class</span>
            <span>Priority</span>
            <span>Domain</span>
            <span>Channel</span>
            <span>Complexity</span>
            <span>Critical</span>
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
                const classification = classificationByTestCaseId.get(tc.id);
                return (
                  <div
                    key={tc.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedTestCase(tc)}
                    onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setSelectedTestCase(tc); }}
                    className={cn(
                      "grid w-full min-w-[1760px] cursor-pointer items-center gap-x-2 px-4 py-3 text-left text-[11px] transition hover:bg-slate-50",
                      selected && "bg-blue-50/25 shadow-[inset_2px_0_0_#1b59f8]",
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
                    <span className="truncate font-semibold text-slate-600">{tc.domain_name || "—"}</span>
                    <span className="truncate font-semibold text-slate-600">{tc.channel_name || "—"}</span>
                    <span className="truncate font-semibold text-slate-600">{tc.test_case_complexity_name || "—"}</span>
                    <span>{tc.is_critical && <span className={badgeClass("red")}>Critical</span>}</span>
                    <span>
                      {tc.automation_candidate && classificationsEnabled && classification ? (
                        <span className={badgeClass(classificationStatusTone(classification.candidate_status))}>{classification.candidate_status.replace(/_/g, " ")}</span>
                      ) : (
                        <span className={badgeClass(tc.automation_candidate ? "emerald" : "red")}>{tc.automation_candidate ? "Yes" : "No"}</span>
                      )}
                    </span>
                    <span className="font-semibold text-slate-600">{dataDependency(tc)}</span>
                    <span><span className={badgeClass(statusTone(reviewStatus(tc)))}>{reviewStatus(tc)}</span></span>
                    <span><span className={badgeClass(traceabilityHealth(tc) === "Good" ? "emerald" : "amber")}>{traceabilityHealth(tc)}</span></span>
                    <span className="font-semibold text-slate-500">{displayDate(tc.created_at)}</span>
                    <span className="relative flex justify-end" onClick={(event) => event.stopPropagation()}>
                      <button
                        aria-label={`Actions for ${tc.test_case_id}`}
                        onClick={() => setActionMenu(actionMenu === tc.id ? null : tc.id)}
                        className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50"
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                      {actionMenu === tc.id && (
                        <div className="absolute right-0 top-9 z-30 w-52 rounded-md border border-slate-200 bg-white p-1 shadow-xl">
                          {tc.automation_candidate && classificationsEnabled && (
                            classification ? (
                              <button onClick={() => void reclassifyTestCase(classification.id)} disabled={classifyBusyId === classification.id} className="w-full rounded px-2 py-1.5 text-left text-[11px] font-bold hover:bg-slate-50 disabled:opacity-50">Reclassify</button>
                            ) : (
                              <button onClick={() => void classifyTestCase(tc.id)} disabled={classifyBusyId === tc.id} className="w-full rounded px-2 py-1.5 text-left text-[11px] font-bold hover:bg-slate-50 disabled:opacity-50">Classify</button>
                            )
                          )}
                          <button onClick={() => { setSelectedTestCase(tc); setDrawerTab("ai"); setActionMenu(null); }} className="w-full rounded px-2 py-1.5 text-left text-[11px] font-bold hover:bg-slate-50">View Recommendation</button>
                          <button onClick={() => { setSelectedTestCase(tc); setDrawerTab("ai"); setActionMenu(null); }} className="w-full rounded px-2 py-1.5 text-left text-[11px] font-bold hover:bg-slate-50">View Matched Rules</button>
                          <button onClick={() => { setPolicyDrawerTestCase(tc); setActionMenu(null); }} className="w-full rounded px-2 py-1.5 text-left text-[11px] font-bold hover:bg-slate-50">Open Classification Policy</button>
                          <button onClick={() => { openInEditor(tc.id); setActionMenu(null); }} className="w-full rounded px-2 py-1.5 text-left text-[11px] font-bold hover:bg-slate-50">Send to Test Case Editor</button>
                        </div>
                      )}
                    </span>
                  </div>
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

      <Drawer open={importOpen} onOpenChange={(open) => { setImportOpen(open); if (!open) { setImportFile(null); setImportPreview(null); setImportError(""); } }}>
        <DrawerContent size="xl">
          <DrawerHeader>
            <div className="flex items-center gap-2">
              <Upload className="h-5 w-5 text-[#1b59f8]" />
              <div>
                <DrawerTitle>Import Test Cases</DrawerTitle>
                <DrawerDescription>
                  Upload the canonical 35-column CSV or Excel template used by all test-case exports.
                </DrawerDescription>
              </div>
            </div>
            <button onClick={() => setImportOpen(false)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-50">
              <X className="h-4 w-4" />
            </button>
          </DrawerHeader>
          <DrawerBody className="space-y-4">
            {importResult && (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs font-bold text-emerald-700">{importResult}</div>
            )}
            {importError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-bold text-red-700">{importError}</div>
            )}
            <div className="flex items-center gap-3">
              <input
                type="file"
                accept=".csv,.xlsx,.xls"
                onChange={(event) => { setImportFile(event.target.files?.[0] ?? null); setImportPreview(null); }}
                className="flex-1 rounded-lg border border-slate-200 bg-white p-2 text-xs font-semibold"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={handleImportPreview}
                disabled={!importFile || previewingImport}
                className="h-9 gap-2 border-slate-200 text-xs font-bold"
              >
                {previewingImport ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                Preview
              </Button>
            </div>

            {importPreview && (
              <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                  <div>
                    <h4 className="text-xs font-bold text-slate-800">{importPreview.filename}</h4>
                    <p className="mt-0.5 text-[10px] text-slate-400">{importPreview.row_count} row(s) detected</p>
                  </div>
                  <span className={badgeClass(importPreview.can_import ? "emerald" : "red")}>
                    {importPreview.can_import ? "Ready to import" : "Cannot import"}
                  </span>
                </div>

                {importPreview.validation_errors.length > 0 && (
                  <div className="max-h-32 overflow-y-auto rounded-lg border border-red-200 bg-red-50 p-2.5 text-[11px] text-red-700">
                    {importPreview.validation_errors.map((item, idx) => (
                      <p key={idx}>Row {item.row_number ?? item.test_case_id ?? "?"}: {item.message}</p>
                    ))}
                  </div>
                )}
                {importPreview.validation_warnings.length > 0 && (
                  <div className="max-h-32 overflow-y-auto rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-[11px] text-amber-700">
                    {importPreview.validation_warnings.map((item, idx) => (
                      <p key={idx}>Row {item.row_number ?? "?"}: {item.message}</p>
                    ))}
                  </div>
                )}

                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="min-w-full border-collapse text-left text-[11px]">
                    <thead className="border-b border-slate-100 bg-slate-50 text-[9px] font-extrabold uppercase tracking-wide text-slate-500">
                      <tr>
                        <th className="px-2.5 py-1.5">Test Case ID</th>
                        <th className="px-2.5 py-1.5">Title</th>
                        <th className="px-2.5 py-1.5">Type</th>
                        <th className="px-2.5 py-1.5">Complexity</th>
                        <th className="px-2.5 py-1.5">Critical</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {importPreview.preview_rows.map((row, idx) => (
                        <tr key={idx}>
                          <td className="px-2.5 py-1.5 font-mono font-bold text-[#1b59f8]">{String(row.test_case_id ?? "—")}</td>
                          <td className="max-w-[220px] truncate px-2.5 py-1.5">{String(row.title ?? "—")}</td>
                          <td className="px-2.5 py-1.5">{row.test_case_type_id ? "Matched" : "—"}</td>
                          <td className="px-2.5 py-1.5">{row.test_case_complexity_id ? "Matched" : "—"}</td>
                          <td className="px-2.5 py-1.5">{row.is_critical ? "Yes" : "No"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="flex gap-2">
                  <Button
                    onClick={handleImportConfirm}
                    disabled={!importPreview.can_import || confirmingImport}
                    className="h-9 gap-2 bg-[#1b59f8] text-xs font-bold text-white hover:bg-[#1447c9]"
                  >
                    {confirmingImport ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
                    Confirm Import
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setImportPreview(null)} className="h-9 border-slate-200 text-xs font-bold">
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </DrawerBody>
        </DrawerContent>
      </Drawer>

      <Drawer open={!!selectedTestCase} onOpenChange={(open) => !open && setSelectedTestCase(null)}>
        <DrawerContent size="xl">
        {selectedTestCase && (
          <div className="flex h-full flex-col">
            <div className="border-b border-slate-100 p-5">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <DrawerTitle className="font-mono text-lg font-extrabold text-slate-950">{selectedTestCase.test_case_id}</DrawerTitle>
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
                ["path", "Path to Execution"],
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
              {drawerTab === "path" && selectedProject && (
                <ExecutionPathPanel projectId={selectedProject} testCaseId={selectedTestCase.id} />
              )}

              {drawerTab === "overview" && (
                <>
                  <DrawerCard title="Test Case Details" icon={TestTube2}>
                    <div className="space-y-5">
                      <div>
                        <p className="text-[10px] font-extrabold uppercase tracking-wide text-slate-400">Objective</p>
                        <p className="mt-1 text-xs font-semibold leading-5 text-slate-700">
                          {selectedTestCase.test_case_objective?.trim() || selectedTestCase.title}
                        </p>
                      </div>

                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                        <InfoPair label="Priority" value={selectedTestCase.priority || "Not set"} />
                        <InfoPair label="Severity" value={selectedTestCase.severity || "Not set"} />
                        <InfoPair label="Test Type" value={selectedTestCase.test_type || "Not set"} />
                        <InfoPair label="Automation Candidate" value={selectedTestCase.automation_candidate ? "Yes" : "No"} />
                      </div>

                      <div>
                        <p className="text-[10px] font-extrabold uppercase tracking-wide text-slate-400">Preconditions</p>
                        {(selectedTestCase.preconditions ?? []).length ? (
                          <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs font-semibold leading-5 text-slate-700">
                            {(selectedTestCase.preconditions ?? []).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
                          </ol>
                        ) : (
                          <p className="mt-2 text-xs font-semibold text-amber-700">No preconditions recorded.</p>
                        )}
                      </div>

                      <div>
                        <p className="text-[10px] font-extrabold uppercase tracking-wide text-slate-400">Test Steps</p>
                        {normalizedSteps(selectedTestCase.steps).length ? (
                          <div className="mt-2 overflow-hidden rounded-lg border border-slate-200">
                            <div className="grid grid-cols-[42px_minmax(0,1fr)_minmax(0,1fr)] bg-slate-50 text-[10px] font-extrabold uppercase tracking-wide text-slate-500">
                              <span className="px-3 py-2">#</span>
                              <span className="border-l border-slate-200 px-3 py-2">Action</span>
                              <span className="border-l border-slate-200 px-3 py-2">Expected Result</span>
                            </div>
                            {normalizedSteps(selectedTestCase.steps).map((step, index) => (
                              <div key={`${step.step_number}-${index}`} className="grid grid-cols-[42px_minmax(0,1fr)_minmax(0,1fr)] border-t border-slate-200 text-xs font-semibold leading-5 text-slate-700">
                                <span className="px-3 py-2">{step.step_number || index + 1}</span>
                                <span className="border-l border-slate-200 px-3 py-2">{step.action || "Missing action"}</span>
                                <span className="border-l border-slate-200 px-3 py-2">{step.expected_result || "Missing expected result"}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="mt-2 text-xs font-semibold text-amber-700">No test steps recorded.</p>
                        )}
                      </div>

                      <div>
                        <p className="text-[10px] font-extrabold uppercase tracking-wide text-slate-400">Overall Expected Result</p>
                        <p className={cn("mt-1 text-xs font-semibold leading-5", selectedTestCase.expected_result?.trim() ? "text-slate-700" : "text-amber-700")}>
                          {selectedTestCase.expected_result?.trim() || "No overall expected result recorded."}
                        </p>
                      </div>

                      {selectedTestCase.bdd_scenario?.trim() && (
                        <div>
                          <p className="text-[10px] font-extrabold uppercase tracking-wide text-slate-400">BDD Scenario</p>
                          <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">{selectedTestCase.bdd_scenario}</pre>
                        </div>
                      )}
                    </div>
                  </DrawerCard>

                  <DrawerCard title="Review & Approval Readiness" icon={selectedApprovalBlockers.length ? AlertTriangle : CheckCircle}>
                    {selectedIsInApproval ? (
                      <div className="rounded-lg border border-blue-100 bg-blue-50 p-3">
                        <p className="text-xs font-extrabold text-blue-800">
                          {selectedTestCase.status === "approved" || selectedTestCase.approval_status === "approved"
                            ? "This test case is approved."
                            : "This test case is already in Review & Approval."}
                        </p>
                        <p className="mt-1 text-[11px] font-semibold leading-5 text-blue-700">Open the approval queue to view its review status, findings, and decision history.</p>
                      </div>
                    ) : selectedApprovalBlockers.length ? (
                      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                        <p className="text-xs font-extrabold text-amber-900">Complete these items before sending:</p>
                        <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] font-semibold leading-5 text-amber-800">
                          {selectedApprovalBlockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
                        </ul>
                        <p className="mt-2 text-[10px] font-semibold text-amber-700">Automation classification and execution evidence happen later and do not block this handoff.</p>
                      </div>
                    ) : (
                      <div className="rounded-lg border border-emerald-100 bg-emerald-50 p-3">
                        <p className="text-xs font-extrabold text-emerald-800">Ready for Review & Approval</p>
                        <p className="mt-1 text-[11px] font-semibold leading-5 text-emerald-700">The required test content is complete. Automation classification and execution evidence are later-stage activities.</p>
                      </div>
                    )}
                  </DrawerCard>

                  <DrawerCard title="Automation Handoff" icon={Radar}>
                    <AutomationHandoffPanel
                      testCase={selectedTestCase}
                      applications={applications}
                      busy={applicationSaveBusy}
                      classification={classificationsEnabled ? selectedClassification : null}
                      onSaveApplication={(applicationId) => saveApplicationMapping(selectedTestCase.id, applicationId)}
                      onStartDiscovery={(applicationId) => {
                        router.push(
                          `/applications?view=discovery&project=${selectedTestCase.project_id}&application=${applicationId}`,
                        );
                      }}
                    />
                  </DrawerCard>

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
                            <span>Scenario test-case set review</span>
                            <span>{typeof selectedReview.overall_score === "number" ? reviewScoreLabel(selectedReview.overall_score) : selectedReview.verdict.replace(/_/g, " ")}</span>
                          </div>
                          {typeof selectedReview.overall_score === "number" && <MiniProgress value={reviewScorePercent(selectedReview.overall_score)} />}
                          <p className="text-[10px] font-semibold text-slate-500">
                            {selectedReview.review_mode === "gating"
                              ? "Gating review — unresolved findings can block approval."
                              : "Advisory review — findings are improvement suggestions and do not block approval."}
                          </p>
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
                <>
                  <DrawerCard title="AI Info" icon={Bot}>
                    <div className="grid grid-cols-2 gap-4 text-xs">
                      <InfoPair label="Generation Run" value={selectedTestCase.agent_run_id ? `#${selectedTestCase.agent_run_id}` : "—"} />
                      <InfoPair label="Generated At" value={displayDateTime(selectedTestCase.created_at)} />
                    </div>
                  </DrawerCard>

                  <DrawerCard title="Automation Classification" icon={ShieldCheck}>
                    {!selectedTestCase.automation_candidate ? (
                      <p className="text-xs font-semibold text-slate-400">Not marked as an automation candidate.</p>
                    ) : !selectedClassification ? (
                      <div className="space-y-3">
                        <p className="text-xs font-semibold text-slate-400">Not yet classified.</p>
                        <Button size="sm" onClick={() => void classifyTestCase(selectedTestCase.id)} disabled={classifyBusyId === selectedTestCase.id} className="h-8 text-xs font-bold">Classify Now</Button>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4 text-xs">
                          <InfoPair label="Candidate status" value={selectedClassification.candidate_status.replace(/_/g, " ")} />
                          <InfoPair label="Review status" value={selectedClassification.review_status.replace(/_/g, " ")} />
                          <InfoPair label="Primary adapter" value={selectedClassification.primary_adapter || "Not resolved"} />
                          <InfoPair label="Discovery required" value={selectedClassification.discovery_required ? (selectedClassification.recommended_discovery_mode || "Yes") : "No"} />
                          <InfoPair label="Complexity score" value={selectedClassification.complexity_score != null ? String(selectedClassification.complexity_score) : "—"} />
                          <InfoPair label="Automation value score" value={selectedClassification.automation_value_score != null ? String(selectedClassification.automation_value_score) : "—"} />
                          <InfoPair label="Policy version" value={selectedClassification.policy_version ? `v${selectedClassification.policy_version}` : "—"} />
                          <InfoPair label="Last classified" value={displayDateTime(selectedClassification.updated_at)} />
                        </div>
                        <div>
                          <p className="mb-1 text-xs font-bold text-slate-700">Supporting adapters / validators</p>
                          <div className="flex flex-wrap gap-1">
                            {[...selectedClassification.supporting_adapters, ...selectedClassification.mandatory_validators, ...selectedClassification.optional_validators].length ? (
                              <>
                                {selectedClassification.mandatory_validators.map((item) => <span key={`m-${item}`} className={badgeClass("red")}>{item}</span>)}
                                {selectedClassification.optional_validators.map((item) => <span key={`o-${item}`} className={badgeClass("blue")}>{item}</span>)}
                                {selectedClassification.supporting_adapters.map((item) => <span key={`s-${item}`} className={badgeClass("slate")}>{item}</span>)}
                              </>
                            ) : <span className={badgeClass("slate")}>None declared</span>}
                          </div>
                        </div>
                        {selectedClassification.deterministic_blockers.length > 0 && (
                          <div>
                            <p className="mb-1 text-xs font-bold text-red-700">Deterministic blockers</p>
                            <ul className="list-disc space-y-1 pl-4 text-xs font-semibold text-red-600">
                              {selectedClassification.deterministic_blockers.map((item, index) => <li key={`${item.code}-${index}`}>{item.label}: {item.detail}</li>)}
                            </ul>
                          </div>
                        )}
                        {selectedClassification.matched_rules.length > 0 && (
                          <div>
                            <p className="mb-1 text-xs font-bold text-slate-700">Matched rules</p>
                            <pre className="max-h-24 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-[10px] text-slate-700">{JSON.stringify(selectedClassification.matched_rules, null, 2)}</pre>
                          </div>
                        )}
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" onClick={() => void reclassifyTestCase(selectedClassification.id)} disabled={classifyBusyId === selectedClassification.id} className="h-8 text-xs font-bold">Reclassify</Button>
                          <Button size="sm" variant="outline" onClick={() => setPolicyDrawerTestCase(selectedTestCase)} className="h-8 text-xs font-bold">View Policy</Button>
                        </div>
                      </div>
                    )}
                  </DrawerCard>

                  {selectedEligibility?.verdict && (
                    <DrawerCard title="Legacy AI Automation Note" icon={Sparkles}>
                      <p className="text-xs font-semibold text-slate-500">Superseded by the Automation Classification above once this test case is classified.</p>
                      <div className="mt-2 grid grid-cols-2 gap-4 text-xs">
                        <InfoPair label="Automation Eligibility" value={selectedEligibility.verdict} />
                        <InfoPair label="Automation Style" value={selectedEligibility.automation_style || "—"} />
                      </div>
                      {selectedEligibility.reason && <p className="mt-3 text-xs font-semibold text-slate-500">{selectedEligibility.reason}</p>}
                    </DrawerCard>
                  )}
                </>
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
                {selectedIsInApproval ? (
                  <Button variant="outline" size="sm" onClick={() => openInApproval(selectedTestCase.id)} className="h-9 border-blue-200 text-xs font-bold text-[#1b59f8]">Open Review &amp; Approval</Button>
                ) : (
                  <Button variant="outline" size="sm" onClick={() => void sendCaseToApproval(selectedTestCase.id)} disabled={selectedApprovalBlockers.length > 0} title={selectedApprovalBlockers.join(" ")} className="h-9 border-blue-200 text-xs font-bold text-[#1b59f8]">Send to Review &amp; Approval</Button>
                )}
                <Button variant="outline" size="sm" onClick={() => exportToCSV([selectedTestCase], requirementsByKey, requirementsById)} className="col-span-2 h-9 gap-2 border-blue-200 text-xs font-bold text-[#1b59f8]">
                  <Download className="h-3.5 w-3.5" />
                  Export Test Case
                </Button>
              </div>
            </div>
          </div>
        )}
        </DrawerContent>
      </Drawer>

      <ClassificationPolicyDrawer testCase={policyDrawerTestCase} onClose={() => setPolicyDrawerTestCase(null)} />
    </div>
  );
}

function ClassificationPolicyDrawer({ testCase, onClose }: { testCase: TestCase | null; onClose: () => void }) {
  const [policy, setPolicy] = useState<AutomationClassificationPolicy | null>(null);
  const [simulation, setSimulation] = useState<ClassificationPolicySimulateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!testCase || !testCase.project_id) { setPolicy(null); setSimulation(null); return; }
    setLoading(true); setError("");
    Promise.all([
      automationClassificationApi.effectivePolicy(testCase.project_id, testCase.application_id ?? undefined),
      automationClassificationApi.simulatePolicy(testCase.project_id, testCase.id),
    ])
      .then(([policyRes, simRes]) => { setPolicy(policyRes.data); setSimulation(simRes.data); })
      .catch((loadError) => setError(messageFromError(loadError, "Could not load the effective classification policy.")))
      .finally(() => setLoading(false));
  }, [testCase]);

  return (
    <Drawer open={!!testCase} onOpenChange={(open) => !open && onClose()}>
      <DrawerContent size="lg">
        {testCase && (
          <div className="flex h-full flex-col">
            <DrawerHeader>
              <DrawerTitle className="text-sm text-slate-900">Classification Policy — {testCase.test_case_id}</DrawerTitle>
            </DrawerHeader>
            <DrawerBody>
              {loading ? (
                <div className="flex items-center justify-center py-16 text-xs font-bold text-slate-500"><Loader2 className="mr-2 h-4 w-4 animate-spin text-[#1b59f8]" />Loading policy...</div>
              ) : error ? (
                <p className="text-xs font-semibold text-red-600">{error}</p>
              ) : !policy ? (
                <p className="text-xs font-semibold text-slate-400">No published policy resolved for this project.</p>
              ) : (
                <div className="space-y-4">
                  <DrawerCard title="Effective Policy" icon={ShieldCheck}>
                    <div className="grid grid-cols-2 gap-4 text-xs">
                      <InfoPair label="Code" value={policy.code} />
                      <InfoPair label="Version" value={`v${policy.version}`} />
                      <InfoPair label="Status" value={policy.status} />
                      <InfoPair label="Scope" value={policy.application_id ? "Application" : policy.project_id ? "Project" : "Enterprise"} />
                    </div>
                  </DrawerCard>
                  {simulation && (
                    <DrawerCard title="Simulation Result For This Test Case" icon={Bot}>
                      <div className="space-y-3 text-xs">
                        <InfoPair label="Routing default adapter" value={simulation.routing_default_adapter || "Not resolved"} />
                        <div>
                          <p className="mb-1 font-bold text-slate-700">Default mandatory / optional validators</p>
                          <div className="flex flex-wrap gap-1">
                            {simulation.routing_default_mandatory_validators.map((item) => <span key={`m-${item}`} className={badgeClass("red")}>{item}</span>)}
                            {simulation.routing_default_optional_validators.map((item) => <span key={`o-${item}`} className={badgeClass("blue")}>{item}</span>)}
                            {!simulation.routing_default_mandatory_validators.length && !simulation.routing_default_optional_validators.length && <span className={badgeClass("slate")}>None declared</span>}
                          </div>
                        </div>
                        {simulation.deterministic_blockers.length > 0 && (
                          <div>
                            <p className="mb-1 font-bold text-red-700">Would block</p>
                            <ul className="list-disc space-y-1 pl-4 font-semibold text-red-600">{simulation.deterministic_blockers.map((item, index) => <li key={`${item.code}-${index}`}>{item.label}: {item.detail}</li>)}</ul>
                          </div>
                        )}
                        {simulation.deterministic_warnings.length > 0 && (
                          <div>
                            <p className="mb-1 font-bold text-amber-700">Advisory warnings</p>
                            <ul className="list-disc space-y-1 pl-4 font-semibold text-amber-600">{simulation.deterministic_warnings.map((item, index) => <li key={`${item.code}-${index}`}>{item.label}: {item.detail}</li>)}</ul>
                          </div>
                        )}
                      </div>
                    </DrawerCard>
                  )}
                  <DrawerCard title="Routing Matrix (Raw Policy Rules)" icon={FileText}>
                    <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-[10px] text-slate-700">{JSON.stringify(policy.rules, null, 2)}</pre>
                  </DrawerCard>
                </div>
              )}
            </DrawerBody>
          </div>
        )}
      </DrawerContent>
    </Drawer>
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
      className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-xs font-medium text-slate-600 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
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
  selectedProject,
  classifications,
  classificationsEnabled,
  onClassificationsChanged,
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
  selectedProject: number | null;
  classifications: TestCaseAutomationClassification[];
  classificationsEnabled: boolean;
  onClassificationsChanged: () => void | Promise<void>;
}) {
  const tc = selectedTestCase || testCases[0] || null;
  const req = tc ? findRequirementForCase(tc, requirementsByKey, requirementsById) || selectedRequirement : selectedRequirement;
  const steps = tc?.steps ?? [];
  const preconditions = tc?.preconditions ?? [];
  const scenario = scenarioForCase(tc, scenariosById);
  const review = reviewForCase(tc, scenarioReviews);
  const classification = tc ? classifications.find((item) => item.test_case_id === tc.id) : undefined;
  const [canReviewClassification, setCanReviewClassification] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  useEffect(() => {
    if (!selectedProject) { setCanReviewClassification(false); return; }
    let cancelled = false;
    Promise.all([usersApi.me(), projectsApi.memberships(selectedProject), projectsApi.roles()])
      .then(([meRes, membershipRes, roleRes]) => {
        if (cancelled) return;
        const membership = membershipRes.data.find((item) => item.is_active && item.user_id === meRes.data.id);
        const role = roleRes.data.find((item) => item.role === (membership?.role || meRes.data.role));
        setCanReviewClassification(Boolean(meRes.data.is_superuser || role?.permissions.includes("automation_classification.review")));
      })
      .catch(() => setCanReviewClassification(false));
    return () => { cancelled = true; };
  }, [selectedProject]);

  // Query each governed master table directly. The previous nested,
  // active-only tree could hide table rows when a parent was inactive and
  // did not express the required "all values in the table" fallback.
  const [domainOptions, setDomainOptions] = useState<TaxonomyEntry[]>([]);
  const [channelOptions, setChannelOptions] = useState<TaxonomyEntry[]>([]);
  const [productGroupOptions, setProductGroupOptions] = useState<TaxonomyEntry[]>([]);
  const [productOptions, setProductOptions] = useState<TaxonomyEntry[]>([]);
  const [subRequestTypeOptions, setSubRequestTypeOptions] = useState<TaxonomyEntry[]>([]);
  const [testCaseTypeOptions, setTestCaseTypeOptions] = useState<TaxonomyEntry[]>([]);
  const [testCaseComplexityOptions, setTestCaseComplexityOptions] = useState<TaxonomyEntry[]>([]);
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      taxonomyApi.qaDomains(false),
      taxonomyApi.systems(false),
      taxonomyApi.productGroups(false),
      taxonomyApi.products(false),
      taxonomyApi.subRequestTypes(false),
      taxonomyApi.testCaseTypes(false),
      taxonomyApi.testCaseComplexities(false),
    ])
      .then(([domains, channels, productGroups, products, subRequestTypes, testCaseTypes, complexities]) => {
        if (cancelled) return;
        setDomainOptions(domains.data);
        setChannelOptions(channels.data);
        setProductGroupOptions(productGroups.data);
        setProductOptions(products.data);
        setSubRequestTypeOptions(subRequestTypes.data);
        setTestCaseTypeOptions(testCaseTypes.data);
        setTestCaseComplexityOptions(complexities.data);
      })
      .catch(() => {
        if (cancelled) return;
        setDomainOptions([]);
        setChannelOptions([]);
        setProductGroupOptions([]);
        setProductOptions([]);
        setSubRequestTypeOptions([]);
        setTestCaseTypeOptions([]);
        setTestCaseComplexityOptions([]);
      });
    return () => { cancelled = true; };
  }, []);

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
  const typeFilterOptions = useMemo(
    () => availableFilterOptions(testCases.map(testType)),
    [testCases],
  );
  const classFilterOptions = useMemo(
    () => availableFilterOptions(testCases.map(scenarioClass)),
    [testCases],
  );
  const priorityFilterOptions = useMemo(
    () => availableFilterOptions(testCases.map((testCase) => testCase.priority)),
    [testCases],
  );
  const reviewFilterOptions = useMemo(
    () => availableFilterOptions(testCases.map(reviewStatus)),
    [testCases],
  );
  const activeFilterCount = [typeFilter, classFilter, priorityFilter, reviewFilter]
    .filter((filter) => filter !== "all").length;
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
      const typeOk = typeFilter === "all" || normalize(testType(row)) === normalize(typeFilter);
      const classOk = classFilter === "all" || normalize(scenarioClass(row)) === normalize(classFilter);
      const priorityOk = priorityFilter === "all" || normalize(row.priority) === normalize(priorityFilter);
      const reviewOk = reviewFilter === "all" || normalize(reviewStatus(row)) === normalize(reviewFilter);
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
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const editorSearchParams = useSearchParams();
  const [editorDrawerOpen, setEditorDrawerOpen] = useState(Boolean(editorSearchParams.get("case")));
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
      if (draft.domainId !== savedDraft.domainId) payload.domain_id = draft.domainId;
      if (draft.channelId !== savedDraft.channelId) payload.channel_id = draft.channelId;
      if (draft.productId !== savedDraft.productId) payload.product_id = draft.productId;
      if (draft.areaOfTestId !== savedDraft.areaOfTestId) payload.area_of_test_id = draft.areaOfTestId;
      if (draft.subRequestTypeId !== savedDraft.subRequestTypeId) payload.sub_request_type_id = draft.subRequestTypeId;
      if (draft.testCaseTypeId !== savedDraft.testCaseTypeId) payload.test_case_type_id = draft.testCaseTypeId;
      if (draft.testCaseComplexityId !== savedDraft.testCaseComplexityId) payload.test_case_complexity_id = draft.testCaseComplexityId;
      if (draft.testCaseObjective !== savedDraft.testCaseObjective) payload.test_case_objective = draft.testCaseObjective;
      if (draft.atcTestCase !== savedDraft.atcTestCase) payload.atc_test_case = draft.atcTestCase;
      if (draft.isCritical !== savedDraft.isCritical) payload.is_critical = draft.isCritical;
      if (draft.ppmId !== savedDraft.ppmId) payload.ppm_id = draft.ppmId;

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
    const score = typeof review.overall_score === "number" ? `, overall score ${reviewScoreLabel(review.overall_score)}` : "";
    const mode = review.review_mode === "gating" ? "gating" : "advisory";
    notify(`Latest scenario test-case set review for ${tc.test_case_id}: ${review.verdict.replace(/_/g, " ")}${score} (${mode}).`);
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
    <div className="min-h-full pb-3">
      <section className="space-y-4">
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
              <p className="mt-1 text-sm font-normal leading-5 text-slate-500">Review and refine generated test cases before approval.</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {tc && dirty && (
              <Button variant="outline" size="sm" onClick={revertChanges} disabled={busyAction !== null} className="h-9 gap-2 border-slate-200 text-xs font-bold text-slate-600">
                Revert
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={saveDraft} disabled={!tc || busyAction !== null || !dirty} className="h-9 gap-2 border-blue-200 text-xs font-medium text-[#1b59f8]">
              {busyAction === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
              Save Draft
              {tc && dirty && <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />}
            </Button>
            <Button variant="outline" size="sm" onClick={validateCase} disabled={!tc || busyAction !== null} className="h-9 gap-2 border-blue-200 text-xs font-medium text-[#1b59f8]">
              {busyAction === "validate" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              Validate
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={sendToApproval}
              disabled={!tc || busyAction !== null || approvalBlockers.length > 0}
              title={approvalBlockers.length ? approvalBlockers.join(" ") : undefined}
              className="h-9 gap-2 bg-[#1b59f8] text-xs font-medium text-white hover:bg-[#1546c2]"
            >
              {busyAction === "approval" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ChevronRight className="h-4 w-4" />}
              Send to Approval
            </Button>
            <div className="relative">
            <Button variant="outline" size="sm" onClick={() => setShowMore((value) => !value)} className="h-9 gap-2 border-slate-200 text-xs font-medium">
              More
              <ChevronDown className="h-3.5 w-3.5" />
            </Button>
            {showMore && (
              <div className="absolute right-0 top-11 z-20 w-44 rounded-lg border border-slate-200 bg-white p-2 text-xs font-bold shadow-lg">
                <button onClick={() => { setShowMore(false); exportToCSV(tc ? [tc] : testCases, requirementsByKey, requirementsById); }} className="w-full rounded-md px-3 py-2 text-left text-slate-700 hover:bg-slate-50">Export selected</button>
              </div>
            )}
            </div>
            <Button variant="outline" size="sm" onClick={() => setInspectorOpen(true)} disabled={!tc} className="h-9 gap-2 border-slate-200 text-xs font-medium">
              <ShieldCheck className="h-4 w-4" />
              Inspector
            </Button>
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
            <p className="mb-4 text-sm font-semibold text-slate-800">Editing Readiness Check</p>
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
            <p className="text-sm font-semibold text-slate-800">Scenario Test-Case Set Review</p>
            {review ? (
              <>
                <p className="mt-5 text-xl font-extrabold text-slate-950">
                  {typeof review.overall_score === "number" ? reviewScoreLabel(review.overall_score) : "—"}
                </p>
                <span className={badgeClass(review.verdict === "pass" ? "emerald" : review.verdict === "fail" ? "red" : "amber")}>
                  {review.verdict.replace(/_/g, " ")} · {review.review_mode === "gating" ? "gating" : "advisory"}
                </span>
                <p className="mt-3 text-[10px] font-semibold leading-5 text-slate-500">
                  This score reviews the complete set of test cases linked to the parent scenario, not this test case in isolation.
                </p>
              </>
            ) : (
              <p className="mt-5 text-xs font-normal leading-5 text-slate-500">No automated coverage review recorded yet.</p>
            )}
          </div>
        </div>

        <div className="min-w-0">
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
                    "inline-flex h-8 items-center gap-2 rounded-md px-3 text-xs font-semibold transition",
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
                  className="h-9 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-xs font-normal text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                />
              </div>
              <Button
                variant="outline"
                size="sm"
                className={cn(
                  "h-9 gap-2 border-slate-200 px-3 text-xs font-bold",
                  (filtersOpen || activeFilterCount > 0) && "border-blue-300 bg-blue-50 text-[#1b59f8]",
                )}
                onClick={() => setFiltersOpen((open) => !open)}
                aria-expanded={filtersOpen}
                aria-controls="editor-test-case-filters"
              >
                <Filter className="h-4 w-4" />
                Filters
                {activeFilterCount > 0 && (
                  <span className="rounded-full bg-[#1b59f8] px-1.5 py-0.5 text-[10px] text-white">
                    {activeFilterCount}
                  </span>
                )}
              </Button>
            </div>
            {filtersOpen && (
              <div
                id="editor-test-case-filters"
                aria-label="Editor test case filters"
                className="flex flex-wrap items-center gap-2 rounded-lg border border-blue-100 bg-blue-50/40 p-3"
              >
                <FilterSelect value={typeFilter} onChange={setTypeFilter} options={typeFilterOptions} label="Test Type" />
                <FilterSelect value={classFilter} onChange={setClassFilter} options={classFilterOptions} label="Scenario Class" />
                <FilterSelect value={priorityFilter} onChange={setPriorityFilter} options={priorityFilterOptions} label="Priority" />
                <FilterSelect value={reviewFilter} onChange={setReviewFilter} options={reviewFilterOptions} label="Review Status" />
                {activeFilterCount > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-10 gap-2 text-xs font-bold text-slate-600"
                    onClick={() => {
                      setTypeFilter("all");
                      setClassFilter("all");
                      setPriorityFilter("all");
                      setReviewFilter("all");
                    }}
                  >
                    <X className="h-4 w-4" />
                    Clear filters
                  </Button>
                )}
              </div>
            )}
            <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
              <div className="grid min-w-max border-b border-slate-200 bg-slate-50/70 px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500" style={{ gridTemplateColumns: EDITOR_TABLE_GRID }}>
                <span>TC ID</span><span>Req ID / PPM ID</span><span>Title</span><span>Test Type</span><span>Scenario Class</span><span>Priority</span><span>Domain</span><span>Channel</span><span>Complexity</span><span>Critical</span><span>Edit Status</span><span>Validation Status</span><span>Actions</span>
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
                    const selected = editorDrawerOpen && selectedTestCase?.id === row.id;
                    const issue = traceabilityHealth(row) !== "Good" || reviewStatus(row) === "Needs Review";
                    return (
                      <button
                        key={row.id}
                        onClick={() => {
                          setSelectedTestCase(row);
                          setEditorDrawerOpen(true);
                        }}
                        className={cn("grid w-full min-w-max items-center px-3 py-3 text-left text-[11px] font-medium transition hover:bg-slate-50", selected && "border-l-2 border-[#1b59f8] bg-blue-50/30")}
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
                        <span className="truncate text-slate-600">{row.domain_name || "—"}</span>
                        <span className="truncate text-slate-600">{row.channel_name || "—"}</span>
                        <span className="truncate text-slate-600">{row.test_case_complexity_name || "—"}</span>
                        <span>{row.is_critical && <span className={badgeClass("red")}>Critical</span>}</span>
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

          <Drawer
            open={editorDrawerOpen && !!selectedTestCase}
            onOpenChange={(open) => {
              setEditorDrawerOpen(open);
              if (!open) setSelectedTestCase(null);
            }}
          >
            <DrawerContent size="2xl">
              <DrawerBody className="space-y-0 p-4">
                <div className="min-w-0 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            {tc ? (
              <>
                <div className="mb-4 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <DrawerTitle className="text-sm font-extrabold text-slate-950">{tc.test_case_id}</DrawerTitle>
                    <span className={badgeClass(dirty ? "purple" : "slate")}>{dirty ? "Editing" : tc.status.replace(/_/g, " ")}</span>
                    {dirty ? (
                      <span className="text-[10px] font-bold text-amber-600">Unsaved changes</span>
                    ) : tc.updated_at && (
                      <span className="text-[10px] font-bold text-slate-400">Updated {relativeTime(tc.updated_at)}</span>
                    )}
                  </div>
                  <div className="flex gap-2 text-slate-500">
                    <button
                      aria-label="Close"
                      onClick={() => {
                        setEditorDrawerOpen(false);
                        setSelectedTestCase(null);
                      }}
                    >
                      <X className="h-4 w-4" />
                    </button>
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
                <EditorField
                  label="Test Case Objective"
                  value={draft.testCaseObjective}
                  onChange={(v) => updateDraft("testCaseObjective", v)}
                />
                <EditorSection title="UAT Template Fields">
                  <div className="grid grid-cols-4 gap-3">
                    <EditorIdSelect label="Domain" value={draft.domainId} onChange={(v) => updateDraft("domainId", v)} options={domainOptions} />
                    <EditorIdSelect label="Channel" value={draft.channelId} onChange={(v) => updateDraft("channelId", v)} options={channelOptions} />
                    <EditorIdSelect label="Product" value={draft.productId} onChange={(v) => updateDraft("productId", v)} options={productOptions} />
                    <EditorIdSelect label="Area of Test" value={draft.areaOfTestId} onChange={(v) => updateDraft("areaOfTestId", v)} options={productGroupOptions} />
                  </div>
                  <div className="mt-3 grid grid-cols-4 gap-3">
                    <EditorIdSelect label="Sub Request Type" value={draft.subRequestTypeId} onChange={(v) => updateDraft("subRequestTypeId", v)} options={subRequestTypeOptions} />
                    <EditorIdSelect label="Test Case Type" value={draft.testCaseTypeId} onChange={(v) => updateDraft("testCaseTypeId", v)} options={testCaseTypeOptions} />
                    <EditorIdSelect label="Test Case Complexity" value={draft.testCaseComplexityId} onChange={(v) => updateDraft("testCaseComplexityId", v)} options={testCaseComplexityOptions} />
                    <EditorField label="Critical TC Mapping" value={draft.isCritical ? "Yes" : "No"} onChange={(v) => updateDraft("isCritical", v === "Yes")} select options={["Yes", "No"]} />
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-3">
                    <EditorField label="ATC Test Case" value={draft.atcTestCase} onChange={(v) => updateDraft("atcTestCase", v)} />
                    <EditorField label="PPM ID" value={draft.ppmId} onChange={(v) => updateDraft("ppmId", v)} />
                    <EditorField label="JIRA Issue Key" value={tc.jira_issue_key || ""} muted />
                  </div>
                </EditorSection>
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
              </DrawerBody>
              <DrawerFooter className="flex-col items-stretch bg-white">
                {(uiNotice || uiError) && (
                  <div className={cn(
                    "flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-bold",
                    uiError ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700",
                  )}>
                    {uiError ? <AlertTriangle className="h-4 w-4 shrink-0" /> : <CheckCircle className="h-4 w-4 shrink-0" />}
                    <span className="flex-1">{uiError || uiNotice}</span>
                    <button onClick={() => { setUiNotice(""); setUiError(""); }} aria-label="Dismiss message">
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                )}
                <div className="flex items-center justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={saveDraft}
                    disabled={!tc || busyAction !== null || !dirty}
                    className="h-9 gap-2 border-blue-200 text-xs font-bold text-[#1b59f8]"
                  >
                    {busyAction === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                    Save Draft
                    {tc && dirty && <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={validateCase}
                    disabled={!tc || busyAction !== null}
                    className="h-9 gap-2 border-blue-200 text-xs font-bold text-[#1b59f8]"
                  >
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
                </div>
              </DrawerFooter>
            </DrawerContent>
          </Drawer>
        </div>
      </section>

      <Drawer open={inspectorOpen} onOpenChange={setInspectorOpen}>
      <DrawerContent size="lg">
      <DrawerHeader>
        <DrawerTitle>Test Case Inspector</DrawerTitle>
        <button aria-label="Close" onClick={() => setInspectorOpen(false)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-50"><X className="h-4 w-4" /></button>
      </DrawerHeader>
      <DrawerBody>
        <InspectorCard title="Traceability">
          <div className="grid grid-cols-[1fr_18px_1fr_18px_1fr] items-center gap-2 text-center text-[10px] font-bold">
            <TraceBox label="Requirement" value={`${tc?.linked_requirement_key || req?.requirement_id || "—"}\n${ppmFromRequirement(req)}`} />
            <ChevronRight className="h-4 w-4 text-slate-400" />
            <TraceBox label="Scenario" value={scenario?.scenario_id || "—"} />
            <ChevronRight className="h-4 w-4 text-slate-400" />
            <TraceBox label="Test Case" value={tc?.test_case_id || "—"} />
          </div>
        </InspectorCard>
        <AutomationReadinessCard
          classification={classification}
          enabled={classificationsEnabled}
          canReview={canReviewClassification}
          automationCandidate={Boolean(tc?.automation_candidate)}
          onSaved={onClassificationsChanged}
        />
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
      </DrawerBody>
      </DrawerContent>
      </Drawer>
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

// Taxonomy-backed select: stores an id, displays the resolved name. Options
// come from taxonomyApi (see `taxonomy` state in TestCaseEditorView) — never
// a hardcoded list.
function EditorIdSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  options: Array<{ id: number; name: string }>;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[10px] font-extrabold text-slate-500">{label}</span>
      <select
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value ? Number(event.target.value) : null)}
        className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
      >
        <option value="">—</option>
        {options.map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}
      </select>
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

function AutomationReadinessCard({
  classification,
  enabled,
  canReview,
  automationCandidate,
  onSaved,
}: {
  classification: TestCaseAutomationClassification | undefined;
  enabled: boolean;
  canReview: boolean;
  automationCandidate: boolean;
  onSaved: () => void | Promise<void>;
}) {
  const [primaryAdapter, setPrimaryAdapter] = useState("");
  const [mandatoryText, setMandatoryText] = useState("");
  const [optionalText, setOptionalText] = useState("");
  const [discoveryRequired, setDiscoveryRequired] = useState(false);
  const [discoveryMode, setDiscoveryMode] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setPrimaryAdapter(classification?.primary_adapter || "");
    setMandatoryText(classification?.mandatory_validators.join(", ") || "");
    setOptionalText(classification?.optional_validators.join(", ") || "");
    setDiscoveryRequired(classification?.discovery_required || false);
    setDiscoveryMode(classification?.recommended_discovery_mode || "");
    setReason("");
    setError("");
  }, [classification?.id]);

  if (!enabled || !automationCandidate) return null;
  if (!classification) {
    return (
      <InspectorCard title="Automation Readiness">
        <p className="text-xs font-semibold text-slate-400">This test case has not been classified yet. Run classification from Generated Test Cases first.</p>
      </InspectorCard>
    );
  }

  const locked = classification.review_status === "APPROVED";
  const dirty =
    primaryAdapter !== (classification.primary_adapter || "") ||
    mandatoryText !== classification.mandatory_validators.join(", ") ||
    optionalText !== classification.optional_validators.join(", ") ||
    discoveryRequired !== classification.discovery_required ||
    discoveryMode !== (classification.recommended_discovery_mode || "");

  async function save() {
    if (!classification) return;
    setBusy(true);
    setError("");
    try {
      const corrections: Record<string, unknown> = {};
      if (primaryAdapter !== (classification.primary_adapter || "")) corrections.primary_adapter = primaryAdapter || null;
      const mandatory = splitLines(mandatoryText.replace(/,/g, "\n"));
      if (mandatory.join(", ") !== classification.mandatory_validators.join(", ")) corrections.mandatory_validators = mandatory;
      const optional = splitLines(optionalText.replace(/,/g, "\n"));
      if (optional.join(", ") !== classification.optional_validators.join(", ")) corrections.optional_validators = optional;
      if (discoveryRequired !== classification.discovery_required) corrections.discovery_required = discoveryRequired;
      if (discoveryMode !== (classification.recommended_discovery_mode || "")) corrections.recommended_discovery_mode = discoveryMode || null;
      await automationClassificationApi.review(classification.id, corrections, reason.trim() || undefined);
      await onSaved();
    } catch (saveError) {
      setError(messageFromError(saveError, "Could not save the automation-readiness correction."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <InspectorCard title="Automation Readiness" badge={classification.candidate_status.replace(/_/g, " ")}>
      <div className="space-y-3 text-xs">
        <div className="grid grid-cols-2 gap-4">
          <InfoPair label="Candidate status" value={classification.candidate_status.replace(/_/g, " ")} />
          <InfoPair label="Review status" value={classification.review_status.replace(/_/g, " ")} />
        </div>
        {locked && <p className="text-[11px] font-semibold text-amber-600">This classification is already approved and immutable — reclassify from Generated Test Cases to make further changes.</p>}
        {error && <p className="text-[11px] font-semibold text-red-600">{error}</p>}

        <label className="block">
          <span className="mb-1 block text-[10px] font-bold text-slate-500">Primary adapter</span>
          <input value={primaryAdapter} onChange={(e) => setPrimaryAdapter(e.target.value)} disabled={!canReview || locked} className="h-8 w-full rounded border border-slate-200 px-2 text-xs disabled:bg-slate-50" />
        </label>
        <label className="block">
          <span className="mb-1 block text-[10px] font-bold text-slate-500">Mandatory validators (comma-separated)</span>
          <input value={mandatoryText} onChange={(e) => setMandatoryText(e.target.value)} disabled={!canReview || locked} className="h-8 w-full rounded border border-slate-200 px-2 text-xs disabled:bg-slate-50" />
        </label>
        <label className="block">
          <span className="mb-1 block text-[10px] font-bold text-slate-500">Optional validators (comma-separated)</span>
          <input value={optionalText} onChange={(e) => setOptionalText(e.target.value)} disabled={!canReview || locked} className="h-8 w-full rounded border border-slate-200 px-2 text-xs disabled:bg-slate-50" />
        </label>
        <div className="flex items-center gap-2">
          <input id="discovery-required" type="checkbox" checked={discoveryRequired} onChange={(e) => setDiscoveryRequired(e.target.checked)} disabled={!canReview || locked} />
          <label htmlFor="discovery-required" className="text-[10px] font-bold text-slate-500">Discovery required</label>
        </div>
        {discoveryRequired && (
          <label className="block">
            <span className="mb-1 block text-[10px] font-bold text-slate-500">Discovery mode</span>
            <select value={discoveryMode} onChange={(e) => setDiscoveryMode(e.target.value)} disabled={!canReview || locked} className="h-8 w-full rounded border border-slate-200 px-2 text-xs disabled:bg-slate-50">
              <option value="">Select mode</option>
              <option value="GUIDED_USER">Guided User Recording</option>
              <option value="FREE_USER_ACTION">Free User Action</option>
              <option value="SUPERVISED_AGENT">Supervised Agent</option>
            </select>
          </label>
        )}

        {classification.deterministic_blockers.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-bold text-red-600">Known blockers</p>
            <ul className="list-disc space-y-1 pl-4 text-[11px] font-semibold text-red-600">
              {classification.deterministic_blockers.map((item, index) => <li key={`${item.code}-${index}`}>{item.label}: {item.detail}</li>)}
            </ul>
          </div>
        )}

        {canReview && !locked && dirty && (
          <>
            <label className="block">
              <span className="mb-1 block text-[10px] font-bold text-slate-500">Reason for correction</span>
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} className="h-16 w-full resize-none rounded border border-slate-200 p-2 text-xs" />
            </label>
            <Button size="sm" onClick={() => void save()} disabled={busy} className="h-8 text-xs font-bold">Save Correction</Button>
          </>
        )}
        {!canReview && <p className="text-[10px] font-semibold text-slate-400">You do not have permission to correct the automation classification.</p>}
      </div>
    </InspectorCard>
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
