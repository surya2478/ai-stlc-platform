"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Camera,
  Bot,
  BriefcaseBusiness,
  Bug,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  Clock3,
  ClipboardList,
  ExternalLink,
  FileUp,
  FileText,
  Filter,
  Gauge,
  Loader2,
  Monitor,
  MoreHorizontal,
  PanelRight,
  Paperclip,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  TerminalSquare,
  TestTube2,
  UserCheck,
  Wand2,
  XCircle,
} from "lucide-react";
import {
  defectsApi,
  executionApi,
  projectsApi,
  testCasesApi,
  type DefectDraft,
  type ExecutionResult,
  type ExecutionRun,
  type Project,
  type TestCase,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type ExecutionTab = "manual" | "automation" | "ai";
type BadgeVariant = "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple";
type ManualStepStatus = "passed" | "failed" | "blocked" | "skipped" | "not_run" | "in_progress";

type ManualStepState = {
  status: ManualStepStatus;
  actualResult: string;
  comments: string;
  evidence: string[];
  updatedAt?: string;
};

type ManualActivity = {
  id: string;
  resultId?: number;
  stepNumber?: number;
  message: string;
  timestamp: string;
  tone: "info" | "success" | "warning" | "danger";
};

type AutomationRunState = {
  status: "draft" | "queued" | "in_progress" | "passed" | "failed" | "flaky" | "skipped" | "aborted" | "needs_review";
  message: string;
  currentStep: string;
  startedAt?: string;
  lastUpdated?: string;
  elapsedSeconds: number;
  recentActions: string[];
};

type AiMode = "Assistive" | "Semi-Autonomous" | "Experimental Autonomous";

type AiWorkspaceState = {
  mode: AiMode;
  status: "draft" | "plan_ready" | "approved" | "in_progress" | "needs_review" | "paused";
  planGenerated: boolean;
  approved: boolean;
  confidence: number;
  executionSteps: string[];
  browserActions: string[];
  validations: string[];
  testData: string[];
  selectorSuggestions: string[];
  risks: string[];
  observations: string[];
  selfHealSuggestion?: {
    oldSelector: string;
    suggestedSelector: string;
    confidence: number;
  };
  defectDraft?: {
    title: string;
    description: string;
    severity: string;
    priority: string;
    status: string;
  };
  lastUpdated?: string;
};

type JiraDefectLink = {
  id?: number;
  defect_draft_id: number;
  project_id: number;
  jira_issue_key: string;
  jira_url?: string | null;
  jira_status: string;
  status: string;
  created_at?: string;
  updated_at?: string;
};

type ManualSummary = {
  passed: number;
  failed: number;
  blocked: number;
  skipped: number;
  notRun: number;
  total: number;
  executed: number;
  passRate: number;
  progress: number;
};

const TAB_LABELS: Record<ExecutionTab, string> = {
  manual: "Manual Execution",
  automation: "Automation Execution",
  ai: "AI Execution",
};

const STATUS_OPTIONS = ["All", "Draft", "Queued", "In Progress", "Completed", "Passed", "Failed", "Blocked", "Skipped", "Needs Review"];
const OWNER_OPTIONS = ["All", "Current user", "Unassigned"];
const ENVIRONMENT_OPTIONS = ["All", "local", "development", "staging", "production", "ci", "QA", "UAT"];
const MODE_OPTIONS = ["All", "Manual", "Automation", "AI"];
const FRAMEWORK_OPTIONS = ["All", "Playwright", "Selenium", "Cypress", "API", "Other"];
const PAGE_SIZE_OPTIONS = ["5", "10", "25"];

type ExecutionColumnKey =
  | "runId"
  | "suiteName"
  | "mode"
  | "env"
  | "total"
  | "pass"
  | "fail"
  | "status"
  | "owner"
  | "started"
  | "actions";

type ExecutionColumnConfig = {
  key: ExecutionColumnKey;
  label: string;
  defaultVisible?: boolean;
  required?: boolean;
  width: string;
  group: "core" | "advanced";
};

const EXECUTION_COLUMNS: ExecutionColumnConfig[] = [
  { key: "runId", label: "Run ID", defaultVisible: true, required: true, width: "w-[86px]", group: "core" },
  { key: "suiteName", label: "Run Name", defaultVisible: true, required: true, width: "", group: "core" },
  { key: "mode", label: "Mode", defaultVisible: true, width: "w-[104px]", group: "core" },
  { key: "env", label: "Env", defaultVisible: true, width: "w-[64px]", group: "core" },
  { key: "total", label: "Total", defaultVisible: true, width: "w-[70px] text-right", group: "core" },
  { key: "pass", label: "Pass", defaultVisible: true, width: "w-[70px] text-right", group: "core" },
  { key: "fail", label: "Fail", defaultVisible: true, width: "w-[70px] text-right", group: "core" },
  { key: "status", label: "Status", defaultVisible: true, width: "w-[104px]", group: "core" },
  { key: "owner", label: "Owner", defaultVisible: false, width: "w-[110px]", group: "advanced" },
  { key: "started", label: "Started", defaultVisible: false, width: "w-[150px]", group: "advanced" },
  { key: "actions", label: "Actions", defaultVisible: true, required: true, width: "w-[72px] text-right", group: "core" },
];

const DEFAULT_EXECUTION_COLUMN_KEYS = EXECUTION_COLUMNS.filter((c) => c.defaultVisible).map((c) => c.key);
const REQUIRED_EXECUTION_COLUMN_KEYS = EXECUTION_COLUMNS.filter((c) => c.required).map((c) => c.key);
const VALID_EXECUTION_COLUMN_KEYS = new Set(EXECUTION_COLUMNS.map((c) => c.key));

const EXECUTION_VIEW_PRESETS: Record<string, { label: string; columns: ExecutionColumnKey[] }> = {
  default: {
    label: "Default View",
    columns: ["runId", "suiteName", "mode", "env", "total", "pass", "fail", "status", "actions"],
  },
  detailed: {
    label: "Detailed View",
    columns: ["runId", "suiteName", "mode", "env", "total", "pass", "fail", "status", "owner", "started", "actions"],
  },
  summary: {
    label: "Summary View",
    columns: ["runId", "suiteName", "mode", "total", "status", "actions"],
  },
};

function sanitizeExecutionColumns(input: unknown): ExecutionColumnKey[] {
  const raw = Array.isArray(input) ? input : DEFAULT_EXECUTION_COLUMN_KEYS;
  const selected = raw.filter((key): key is ExecutionColumnKey => typeof key === "string" && VALID_EXECUTION_COLUMN_KEYS.has(key as ExecutionColumnKey));
  const withRequired = Array.from(new Set([...selected, ...REQUIRED_EXECUTION_COLUMN_KEYS]));
  if (withRequired.length <= REQUIRED_EXECUTION_COLUMN_KEYS.length) return DEFAULT_EXECUTION_COLUMN_KEYS;
  return EXECUTION_COLUMNS.filter((col) => withRequired.includes(col.key)).map((col) => col.key);
}

function visibleExecutionStorageKey(projectId: number | null) {
  return `execution.visibleColumns.${projectId ?? "default"}`;
}


function messageFromError(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => item?.msg ?? String(item)).join("; ");
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

function statusVariant(status?: string | null): BadgeVariant {
  const value = (status || "").toLowerCase().replace(/\s+/g, "_");
  if (["passed", "pass", "completed", "success", "approved", "synced"].includes(value)) return "success";
  if (["failed", "fail", "error", "aborted", "cancelled", "rejected"].includes(value)) return "destructive";
  if (["blocked", "queued", "pending", "in_progress", "running", "needs_review", "draft"].includes(value)) return "warning";
  if (["skipped", "not_run", "not_executed"].includes(value)) return "secondary";
  if (["ai", "semi_autonomous", "assistive", "hybrid", "automated", "automation"].includes(value)) return "purple";
  return "outline";
}

function normalizeStatus(status?: string | null) {
  if (!status) return "Not Set";
  return status.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatNumber(value: number) {
  return Number.isFinite(value) ? value.toLocaleString() : "0";
}

function safePercent(numerator: number, denominator: number) {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator <= 0) return 0;
  return Math.round((numerator / denominator) * 1000) / 10;
}

function formatPercent(value: number) {
  return `${Number.isFinite(value) ? value.toFixed(1) : "0.0"}%`;
}

function modeForRun(run: ExecutionRun): ExecutionTab {
  const source = (run.source_type || "").toLowerCase();
  const external = (run.external_tool_name || "").toLowerCase();
  if (source.includes("ai")) return "ai";
  if (source.includes("automation") || source.includes("external") || external) return "automation";
  if (source.includes("agent")) return "ai";
  return "manual";
}

function modeLabelForRun(run: ExecutionRun) {
  return TAB_LABELS[modeForRun(run)];
}

function isAiAssisted(run: ExecutionRun) {
  const source = (run.source_type || "").toLowerCase();
  const metadata = JSON.stringify(run.metadata_ || {}).toLowerCase();
  return source.includes("ai") || source.includes("agent") || metadata.includes("ai");
}

function isAutomationCase(testCase: TestCase) {
  const mode = (testCase.execution_mode || testCase.mode || "").toLowerCase();
  return mode === "automated" || mode === "hybrid" || Boolean(testCase.automation_ready);
}

function stepList(testCase?: TestCase | null) {
  if (!testCase?.steps?.length) return [];
  return testCase.steps.map((step, index) => ({
    step_number: Number(step.step_number ?? index + 1),
    action: String(step.action ?? "Step details not provided"),
    expected_result: String(step.expected_result ?? testCase.expected_result ?? "Expected result not provided"),
  }));
}

function runnableStepList(testCase?: TestCase | null) {
  if (!testCase) return [];
  return fallbackStepsForTestCase(testCase);
}

function dateLabel(value?: string | null) {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "-" : parsed.toLocaleString();
}

function runMatchesTab(run: ExecutionRun, tab: ExecutionTab) {
  return modeForRun(run) === tab;
}

function createWorkspaceAdapterRun(projectId: number, tab: ExecutionTab, testCases: TestCase[]): ExecutionRun {
  const now = new Date().toISOString();
  const prefix = tab === "manual" ? "MR" : tab === "automation" ? "AUT" : "AIR";
  const sourceType = tab === "manual" ? "manual_adapter" : tab === "automation" ? "automation_adapter" : "ai_assisted_adapter";
  return {
    id: -(projectId * 10 + (tab === "manual" ? 1 : tab === "automation" ? 2 : 3)),
    project_id: projectId,
    execution_id: `${prefix}-READY`,
    source_type: sourceType,
    external_tool_name: tab === "automation" ? "Integration Adapter" : null,
    suite_name: `${TAB_LABELS[tab]} Workspace`,
    environment: "SIT",
    status: "draft",
    total_tests: testCases.length,
    passed: 0,
    failed: 0,
    skipped: 0,
    execution_logs: [],
    metadata_: {
      adapter_backed: true,
      target_url: "Awaiting execution configuration",
      note: "Frontend-safe workspace adapter. Backend execution run will replace this when orchestration is available.",
    },
    created_at: now,
    updated_at: now,
  };
}

function ensureWorkspaceCatalogRuns(projectId: number | null, runs: ExecutionRun[], testCases: TestCase[]) {
  if (!projectId || testCases.length === 0) return runs;
  const tabs: ExecutionTab[] = ["manual", "automation", "ai"];
  
  let savedRuns: ExecutionRun[] = [];
  if (typeof window !== "undefined") {
    try {
      const sr = window.localStorage.getItem(`stlc_runs_project_${projectId}`);
      if (sr) savedRuns = JSON.parse(sr);
    } catch {}
  }

  const adapters = tabs
    .filter((tab) => !runs.some((run) => modeForRun(run) === tab))
    .map((tab) => {
      const saved = savedRuns.find((r) => modeForRun(r) === tab);
      if (saved) return saved;
      const tabCases = adapterCasesForTab(tab, testCases);
      return createWorkspaceAdapterRun(projectId, tab, tabCases);
    });
  return [...runs, ...adapters];
}

function fallbackStepsForTestCase(testCase: TestCase) {
  const steps = stepList(testCase);
  if (steps.length > 0) return steps;
  return [
    {
      step_number: 1,
      action: testCase.title || "Execute test case",
      expected_result: testCase.expected_result || "Observed result matches the approved expected outcome.",
    },
  ];
}

function adapterCasesForTab(tab: ExecutionTab, testCases: TestCase[]) {
  const approvedCases = testCases.filter(
    (tc) => (tc.approval_status || tc.status || "").toLowerCase() === "approved"
  );
  if (tab === "manual") {
    return approvedCases.filter(
      (tc) => (tc.execution_mode || tc.mode || "").toLowerCase() === "manual"
    );
  }
  if (tab === "automation") {
    return approvedCases.filter(
      (tc) => (tc.execution_mode || tc.mode || "").toLowerCase() === "automated"
    );
  }
  if (tab === "ai") {
    return approvedCases.filter((tc) => {
      const mode = (tc.execution_mode || tc.mode || "").toLowerCase();
      return mode === "hybrid" || mode === "ai";
    });
  }
  return [];
}

function createWorkspaceAdapterResults(run: ExecutionRun, testCases: TestCase[]): ExecutionResult[] {
  if (run.id >= 0) return [];
  const tab = modeForRun(run);
  const now = run.created_at || new Date().toISOString();
  return adapterCasesForTab(tab, testCases).slice(0, 12).map((testCase, index) => {
    const steps = fallbackStepsForTestCase(testCase);
    return {
      id: run.id * 1000 - index - 1,
      execution_run_id: run.id,
      test_case_id: testCase.id,
      test_name: testCase.title || testCase.test_case_id || `Test case ${index + 1}`,
      status: "not_run",
      execution_mode: tab === "automation" ? "automated" : tab,
      external_tool_name: tab === "automation" ? (testCase.external_tool || run.external_tool_name || "Integration Adapter") : undefined,
      external_test_case_id: testCase.external_tc_id || testCase.test_case_id,
      automation_execution_status: tab === "automation" ? "not_run" : undefined,
      manual_execution_status: tab === "manual" ? "not_run" : undefined,
      jira_execution_status: testCase.jira_final_status || undefined,
      jira_issue_key: testCase.jira_issue_key,
      jira_test_key: testCase.jira_test_key,
      raw_result_json: {
        adapter_backed: true,
        step_count: steps.length,
        source: "frontend_workspace_adapter",
      },
      logs: [],
      created_at: now,
      updated_at: now,
    };
  });
}

function runMatchesText(run: ExecutionRun, search: string) {
  const query = search.trim().toLowerCase();
  if (!query) return true;
  return [
    run.execution_id,
    run.suite_name,
    run.environment,
    run.status,
    run.external_tool_name,
    run.external_run_id,
  ]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(query));
}

function runMatchesSearch(run: ExecutionRun, search: string, results: ExecutionResult[], defects: DefectDraft[]) {
  const query = search.trim().toLowerCase();
  if (!query) return true;
  if (runMatchesText(run, query)) return true;
  return [
    ...results
      .filter((result) => result.execution_run_id === run.id)
      .flatMap((result) => [result.test_name, result.external_test_case_id, result.jira_issue_key, result.jira_test_key]),
    ...defects
      .filter((defect) => defectsLinkedToRun(run, results, defect))
      .flatMap((defect) => [defect.defect_id, defect.summary]),
  ]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(query));
}

function defectsLinkedToRun(run: ExecutionRun, results: ExecutionResult[], defect: DefectDraft) {
  const runResults = results.filter((result) => result.execution_run_id === run.id);
  if (defect.execution_result_id && runResults.some((result) => result.id === defect.execution_result_id)) return true;
  if (defect.test_case_id && runResults.some((result) => result.test_case_id === defect.test_case_id)) return true;
  return run.id < 0 && Boolean(defect.test_case_id);
}

function runMatchesRelease(run: ExecutionRun, release: string, results: ExecutionResult[], testCaseById: Map<number, TestCase>, testCases: TestCase[]) {
  if (release === "All Releases") return true;
  if (run.id < 0) return testCases.some((testCase) => testCase.linked_release_version === release);
  const runCaseIds = results
    .filter((result) => result.execution_run_id === run.id && result.test_case_id)
    .map((result) => result.test_case_id as number);
  return runCaseIds.some((id) => testCaseById.get(id)?.linked_release_version === release);
}

function escapeCsvCell(value: unknown) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function resultStatusCounts(results: ExecutionResult[], manualStepStates?: Record<string, ManualStepState>, testCaseById?: Map<number, TestCase>) {
  const counts = { passed: 0, failed: 0, blocked: 0, skipped: 0, notRun: 0 };
  results.forEach((result) => {
    let status = (result.manual_execution_status || result.automation_execution_status || result.status || "").toLowerCase();
    if (result.id < 0 && manualStepStates && testCaseById) {
      const testCase = result.test_case_id ? testCaseById.get(result.test_case_id) : undefined;
      const steps = runnableStepList(testCase);
      const summary = manualSummaryFor(manualStepStates, result.id, steps);
      status = manualResultStatus(summary).toLowerCase();
    }
    if (status === "passed") counts.passed += 1;
    else if (status === "failed" || status === "error") counts.failed += 1;
    else if (status === "blocked") counts.blocked += 1;
    else if (status === "skipped") counts.skipped += 1;
    else counts.notRun += 1;
  });
  return counts;
}

function manualStepKey(resultId: number, stepNumber: number) {
  return `${resultId}:${stepNumber}`;
}

function blankManualStep(): ManualStepState {
  return { status: "not_run", actualResult: "", comments: "", evidence: [] };
}

function getManualStepState(states: Record<string, ManualStepState>, resultId: number | undefined, stepNumber: number) {
  if (!resultId) return blankManualStep();
  return states[manualStepKey(resultId, stepNumber)] || blankManualStep();
}

function manualSummaryFor(
  states: Record<string, ManualStepState>,
  resultId: number | undefined,
  steps: ReturnType<typeof stepList>
): ManualSummary {
  const summary: ManualSummary = {
    passed: 0,
    failed: 0,
    blocked: 0,
    skipped: 0,
    notRun: 0,
    total: steps.length,
    executed: 0,
    passRate: 0,
    progress: 0,
  };

  steps.forEach((step) => {
    const state = getManualStepState(states, resultId, step.step_number);
    if (state.status === "passed") summary.passed += 1;
    else if (state.status === "failed") summary.failed += 1;
    else if (state.status === "blocked") summary.blocked += 1;
    else if (state.status === "skipped") summary.skipped += 1;
    else summary.notRun += 1;
  });

  summary.executed = summary.passed + summary.failed + summary.blocked + summary.skipped;
  summary.passRate = safePercent(summary.passed, summary.executed);
  summary.progress = safePercent(summary.executed, summary.total);
  return summary;
}

function manualResultStatus(summary: ManualSummary): ManualStepStatus {
  if (summary.total === 0 || summary.executed === 0) return "not_run";
  if (summary.failed > 0) return "failed";
  if (summary.blocked > 0) return "blocked";
  if (summary.executed < summary.total) return "in_progress";
  if (summary.passed > 0) return "passed";
  if (summary.skipped === summary.total) return "skipped";
  return "in_progress";
}

function automationStateKey(runId: number) {
  return `automation:${runId}`;
}

function frameworkForRun(run?: ExecutionRun, results: ExecutionResult[] = []) {
  const value = run?.external_tool_name || results.find((result) => result.external_tool_name)?.external_tool_name || "";
  const normalized = value.toLowerCase();
  if (normalized.includes("playwright")) return "Playwright";
  if (normalized.includes("selenium")) return "Selenium";
  if (normalized.includes("cypress")) return "Cypress";
  if (normalized.includes("api")) return "API";
  return value || "Other";
}

function scriptPathForResult(result: ExecutionResult, testCase?: TestCase) {
  const raw = result.raw_result_json || {};
  const mappedPath =
    typeof raw.script_path === "string" ? raw.script_path :
      typeof raw.file_path === "string" ? raw.file_path :
        typeof raw.spec === "string" ? raw.spec :
          result.external_test_case_id;
  if (mappedPath) return String(mappedPath);
  const id = testCase?.test_case_id || result.test_name || "unmapped";
  return `integration-pending/${id.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.spec.ts`;
}

function persistedExecutionResultId(result?: ExecutionResult | null) {
  if (!result?.id || result.id <= 0) return undefined;
  return result.id;
}

function automationRunStateFor(run: ExecutionRun, state?: AutomationRunState): AutomationRunState {
  if (state) return state;
  const normalized = (run.status || "draft").toLowerCase().replace(/\s+/g, "_");
  const allowed = ["draft", "queued", "in_progress", "passed", "failed", "flaky", "skipped", "aborted", "needs_review"];
  return {
    status: (allowed.includes(normalized) ? normalized : "draft") as AutomationRunState["status"],
    message: "Runner integration is ready. No live backend automation runner has been invoked from this UI.",
    currentStep: "Waiting for execution command",
    startedAt: run.started_at || undefined,
    lastUpdated: run.updated_at,
    elapsedSeconds: run.duration_seconds || 0,
    recentActions: (run.execution_logs || []).slice(0, 4).map((log) => String(log)),
  };
}

function automationArtifactCount(results: ExecutionResult[], kind: "screenshots" | "trace" | "video" | "logs" | "report") {
  return results.filter((result) => {
    if (kind === "screenshots") return Boolean(result.screenshot_url);
    if (kind === "video") return Boolean(result.video_url);
    if (kind === "logs") return Boolean(result.log_url || result.logs?.length);
    if (kind === "report") return Boolean(result.external_result_url);
    return Boolean(result.raw_result_json?.trace_url || result.raw_result_json?.trace);
  }).length;
}

function automationFailureInsight(results: ExecutionResult[]) {
  const failed = results.find((result) => ["failed", "error"].includes((result.automation_execution_status || result.status || "").toLowerCase()));
  if (!failed) return null;
  const raw = failed.raw_result_json || {};
  return {
    result: failed,
    step: typeof raw.failing_step === "string" ? raw.failing_step : failed.test_name,
    message: failed.error_message || (typeof raw.failure_message === "string" ? raw.failure_message : "Failure details are not available from the runner yet."),
    rootCause: typeof raw.root_cause_type === "string" ? raw.root_cause_type : "Needs Review",
    confidence: typeof raw.confidence === "number" ? safePercent(raw.confidence, 1) : 0,
  };
}

function jiraLinkForDefect(defect: DefectDraft, links: Record<number, JiraDefectLink>) {
  return links[defect.id] || null;
}

function jiraKeyForDefect(defect: DefectDraft, links: Record<number, JiraDefectLink>) {
  const linked = jiraLinkForDefect(defect, links);
  const metadata = defect.metadata_ || {};
  return linked?.jira_issue_key ||
    (typeof metadata.jira_issue_key === "string" ? metadata.jira_issue_key : null) ||
    (typeof metadata.linked_jira_issue_key === "string" ? metadata.linked_jira_issue_key : null);
}

function jiraUrlForKey(key?: string | null, explicitUrl?: string | null) {
  if (explicitUrl) return explicitUrl;
  if (!key) return null;
  return `https://your-org.atlassian.net/browse/${key}`;
}

function traceabilityItems({
  testCase,
  run,
  result,
  defect,
  evidence,
}: {
  testCase?: TestCase;
  run?: ExecutionRun;
  result?: ExecutionResult;
  defect?: DefectDraft;
  evidence?: string;
}) {
  return [
    { label: "Requirement / Jira Story", value: testCase?.linked_requirement_key || testCase?.jira_issue_key || "Not linked" },
    { label: "Test Scenario", value: testCase?.scenario_id ? `Scenario ${testCase.scenario_id}` : "Not linked" },
    { label: "Test Case", value: testCase?.test_case_id || result?.test_name || "Not linked" },
    { label: "Execution Run", value: run?.execution_id || "Not linked" },
    { label: "Step Result", value: result ? normalizeStatus(result.manual_execution_status || result.automation_execution_status || result.status) : "Not linked" },
    { label: "Evidence", value: evidence || result?.screenshot_url || result?.log_url || result?.video_url || result?.external_result_url || "No evidence linked" },
    { label: "Defect", value: defect?.defect_id || "No defect linked" },
  ];
}

const automationExecutionService = {
  async startAutomationRun(run: ExecutionRun) {
    return {
      status: "queued" as const,
      message: `${run.execution_id} is staged for the automation runner. Connect backend orchestration to execute real tests.`,
      currentStep: "Queued for runner handoff",
    };
  },
  async pauseAutomationRun(run: ExecutionRun) {
    return {
      status: "aborted" as const,
      message: `${run.execution_id} pause request captured locally. Backend pause endpoint is pending integration.`,
      currentStep: "Pause requested",
    };
  },
  async retryFailedTests(run: ExecutionRun, failedCount: number) {
    return {
      status: failedCount > 0 ? "queued" as const : "needs_review" as const,
      message: failedCount > 0 ? `${failedCount} failed automation test(s) staged for retry.` : "No failed automation tests are available for retry.",
      currentStep: failedCount > 0 ? "Retry queue prepared" : "Retry not required",
    };
  },
  async analyzeAutomationFailure(failure: ReturnType<typeof automationFailureInsight>) {
    return {
      status: failure ? "needs_review" as const : "draft" as const,
      message: failure ? "Failure analysis prepared from existing execution result data." : "No failed automation result is available to analyze.",
      currentStep: failure ? "Failure analysis ready for review" : "Waiting for failed result",
    };
  },
};

function aiStateKey(runId: number) {
  return `ai:${runId}`;
}

function aiWorkspaceStateFor(run: ExecutionRun, state?: AiWorkspaceState): AiWorkspaceState {
  if (state) return state;
  return {
    mode: "Assistive",
    status: "draft",
    planGenerated: false,
    approved: false,
    confidence: 0,
    executionSteps: [],
    browserActions: [],
    validations: [],
    testData: [],
    selectorSuggestions: [],
    risks: ["AI execution has not been planned yet. Human review is required before any action."],
    observations: (run.execution_logs || []).slice(0, 4).map((log) => String(log)),
    lastUpdated: run.updated_at,
  };
}

function generateAiExecutionPlan(testCase?: TestCase, run?: ExecutionRun): AiWorkspaceState {
  const steps = stepList(testCase);
  const fallbackTitle = testCase?.title || run?.suite_name || "selected test case";
  const executionSteps = steps.length
    ? steps.map((step) => `Step ${step.step_number}: ${step.action}`)
    : [`Review ${fallbackTitle} and derive executable browser actions from available test case data.`];
  const browserActions = steps.length
    ? steps.map((step) => `Map "${step.action}" to a browser interaction and wait for a stable page state.`)
    : ["Open target URL, inspect page structure, and wait for visible interactive controls."];
  const validations = steps.length
    ? steps.map((step) => `Validate expected result: ${step.expected_result}`)
    : [testCase?.expected_result || "Validate expected outcome from the selected test case."];
  const selectors = steps.length
    ? steps.slice(0, 5).map((step) => `[data-testid*="${String(step.action).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "step"}"]`)
    : ["Prefer role, label, text, and data-testid selectors before brittle CSS paths."];
  const confidence = steps.length >= 3 ? 84 : steps.length > 0 ? 72 : 48;
  const preconditions = Array.isArray(testCase?.preconditions)
    ? testCase?.preconditions.join("; ")
    : testCase?.preconditions;

  return {
    mode: "Semi-Autonomous",
    status: "plan_ready",
    planGenerated: true,
    approved: false,
    confidence,
    executionSteps,
    browserActions,
    validations,
    testData: [
      preconditions || "Confirm valid test account, required environment data, and any prerequisite records.",
      "Identify dynamic data dependencies before execution.",
    ],
    selectorSuggestions: selectors,
    risks: [
      "Human review is required before execution.",
      "OTP, CAPTCHA, MFA, payment, and production-impacting flows must remain manually governed.",
      "AI confidence is based on available test case structure, not a completed browser run.",
    ],
    observations: [
      `Generated AI execution strategy for ${testCase?.test_case_id || fallbackTitle}.`,
      "Converted available manual steps into browser action and validation candidates.",
      "No self-heal or Jira action will be applied without approval.",
    ],
    selfHealSuggestion: {
      oldSelector: "#dynamic-selector",
      suggestedSelector: selectors[0] || "[data-testid]",
      confidence: Math.max(confidence - 8, 0),
    },
    defectDraft: {
      title: `${testCase?.test_case_id || "AI"} failure analysis draft`,
      description: "Draft will be populated from observed expected-vs-actual evidence after AI-assisted execution or failure analysis.",
      severity: "Medium",
      priority: "P3",
      status: "Draft",
    },
    lastUpdated: new Date().toISOString(),
  };
}

function StatCard({
  title,
  value,
  helper,
  icon: Icon,
  tone,
  ring,
}: {
  title: string;
  value: string;
  helper: string;
  icon: React.ElementType;
  tone: string;
  ring?: number;
}) {
  return (
    <Card className="rounded-lg border-slate-200 bg-white shadow-sm hover:shadow-md">
      <CardContent className="flex min-h-[74px] items-center gap-2.5 p-3">
        <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border", tone)}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[9px] font-bold text-slate-500 sm:text-[10px]">{title}</p>
          <div className="mt-1 flex items-center gap-2">
            {ring !== undefined && (
              <span
                className="h-8 w-8 rounded-full"
                style={{
                  background: `conic-gradient(#10b981 ${Math.max(0, Math.min(100, ring))}%, #e5e7eb 0)`,
                }}
              >
                <span className="m-1 block h-6 w-6 rounded-full bg-white" />
              </span>
            )}
            <p className="truncate text-lg font-bold tracking-tight text-slate-950 sm:text-xl">{value}</p>
          </div>
          <p className="mt-0.5 truncate text-[9px] font-semibold text-slate-400">{helper}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function SelectBox({
  label,
  value,
  onChange,
  options,
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  className?: string;
}) {
  return (
    <label className={cn("relative inline-flex min-w-[150px] flex-col gap-1", className)}>
      <span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 appearance-none rounded-lg border border-slate-200 bg-white px-3 pr-8 text-xs font-semibold text-slate-700 shadow-sm outline-none transition focus:ring-2 focus:ring-blue-100"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute bottom-2.5 right-2.5 h-3.5 w-3.5 text-slate-400" />
    </label>
  );
}

function ProjectSelect({
  projects,
  value,
  onChange,
}: {
  projects: Project[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="relative inline-flex min-w-[210px] flex-col gap-1">
      <span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Project</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 appearance-none rounded-lg border border-slate-200 bg-white px-3 pr-8 text-xs font-semibold text-slate-700 shadow-sm outline-none transition focus:ring-2 focus:ring-blue-100"
      >
        {projects.map((project) => (
          <option key={project.id} value={project.id}>
            {project.name}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute bottom-2.5 right-2.5 h-3.5 w-3.5 text-slate-400" />
    </label>
  );
}

function RunRow({
  run,
  selected,
  onSelect,
  visibleColumns,
}: {
  run: ExecutionRun;
  selected: boolean;
  onSelect: () => void;
  visibleColumns: ExecutionColumnKey[];
}) {
  const mode = modeForRun(run);
  return (
    <tr
      onClick={onSelect}
      className={cn(
        "cursor-pointer border-b border-slate-100 text-[11px] transition hover:bg-blue-50/40",
        selected && "bg-blue-50/70 shadow-[inset_3px_0_0_#1b59f8]"
      )}
    >
      {visibleColumns.map((colKey) => {
        switch (colKey) {
          case "runId":
            return (
              <td key="runId" className="w-[86px] px-3 py-3 font-mono font-bold text-blue-600">
                {run.execution_id}
              </td>
            );
          case "suiteName":
            return (
              <td key="suiteName" className="px-3 py-3">
                <p className="truncate font-bold text-slate-800">{run.suite_name || "Execution Run"}</p>
                <p className="mt-0.5 truncate text-[10px] font-semibold text-slate-400">
                  {run.external_run_id || "Platform run"}
                </p>
              </td>
            );
          case "mode":
            return (
              <td key="mode" className="w-[104px] px-3 py-3">
                <Badge
                  variant={mode === "automation" ? "purple" : mode === "ai" ? "info" : "secondary"}
                  className="text-[10px]"
                >
                  {mode === "ai" ? "AI" : mode === "automation" ? "Automation" : "Manual"}
                </Badge>
              </td>
            );
          case "env":
            return (
              <td key="env" className="w-[64px] px-3 py-3 font-semibold text-slate-600">
                {run.environment || "-"}
              </td>
            );
          case "total":
            return (
              <td key="total" className="w-[70px] px-3 py-3 text-right font-bold text-slate-800">
                {formatNumber(run.total_tests || 0)}
              </td>
            );
          case "pass":
            return (
              <td key="pass" className="w-[70px] px-3 py-3 text-right font-bold text-emerald-600">
                {formatNumber(run.passed || 0)}
              </td>
            );
          case "fail":
            return (
              <td key="fail" className="w-[70px] px-3 py-3 text-right font-bold text-rose-600">
                {formatNumber(run.failed || 0)}
              </td>
            );
          case "status":
            return (
              <td key="status" className="w-[104px] px-3 py-3">
                <Badge variant={statusVariant(run.status)} className="text-[10px]">
                  {normalizeStatus(run.status)}
                </Badge>
              </td>
            );
          case "owner":
            return (
              <td key="owner" className="w-[110px] px-3 py-3 text-slate-500">
                {run.triggered_by ? `User ${run.triggered_by}` : "-"}
              </td>
            );
          case "started":
            return (
              <td key="started" className="w-[150px] px-3 py-3 text-slate-500">
                {dateLabel(run.started_at || run.created_at)}
              </td>
            );
          case "actions":
            return (
              <td key="actions" className="w-[72px] px-3 py-3 text-right">
                <button
                  className="rounded-md p-1 text-slate-400 hover:bg-white hover:text-blue-600"
                  aria-label={`Open ${run.execution_id}`}
                >
                  <MoreHorizontal className="h-4 w-4" />
                </button>
              </td>
            );
          default:
            return null;
        }
      })}
    </tr>
  );
}


function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex min-h-[180px] flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50/40 p-6 text-center">
      <CircleDashed className="mb-2 h-8 w-8 text-slate-300" />
      <p className="text-sm font-bold text-slate-700">{title}</p>
      <p className="mt-1 max-w-sm text-xs font-medium leading-relaxed text-slate-400">{description}</p>
    </div>
  );
}

function ManualWorkspace({
  selectedRun,
  selectedResults,
  testCaseById,
  selectedResultId,
  onSelectResult,
  currentStepIndex,
  onStepIndexChange,
  manualStepStates,
  onUpdateStep,
  onSaveNext,
  onMarkComplete,
  onAttachEvidence,
  onCreateDefect,
  creatingDefectKey,
  activity,
  autoSaveMessage,
}: {
  selectedRun: ExecutionRun;
  selectedResults: ExecutionResult[];
  testCaseById: Map<number, TestCase>;
  selectedResultId: number | null;
  onSelectResult: (resultId: number) => void;
  currentStepIndex: number;
  onStepIndexChange: (index: number) => void;
  manualStepStates: Record<string, ManualStepState>;
  onUpdateStep: (result: ExecutionResult, stepNumber: number, patch: Partial<ManualStepState>, message?: string) => void;
  onSaveNext: (result: ExecutionResult, steps: ReturnType<typeof stepList>) => void;
  onMarkComplete: (result: ExecutionResult, steps: ReturnType<typeof stepList>) => void;
  onAttachEvidence: (result: ExecutionResult, stepNumber: number, label: string) => void;
  onCreateDefect: (result: ExecutionResult, stepNumber: number) => void;
  creatingDefectKey: string | null;
  activity: ManualActivity[];
  autoSaveMessage: string | null;
}) {
  const selectedResult = selectedResults.find((result) => result.id === selectedResultId) || selectedResults[0];
  const selectedTestCase = selectedResult?.test_case_id ? testCaseById.get(selectedResult.test_case_id) : undefined;
  const steps = runnableStepList(selectedTestCase);
  const safeStepIndex = Math.min(Math.max(currentStepIndex, 0), Math.max(steps.length - 1, 0));
  const currentStep = steps[safeStepIndex];
  const currentState = currentStep ? getManualStepState(manualStepStates, selectedResult?.id, currentStep.step_number) : blankManualStep();
  const summary = manualSummaryFor(manualStepStates, selectedResult?.id, steps);
  const selectedActivity = activity.filter((event) => !selectedResult || event.resultId === selectedResult.id).slice(0, 5);

  if (!selectedResult) {
    return (
      <div className="p-4">
        <EmptyState
          title="No manual test case results loaded"
          description="Select or create a manual execution run with test cases to start step-level execution."
        />
      </div>
    );
  }

  return (
    <div className="grid gap-4 p-4 xl:grid-cols-[260px_minmax(0,1fr)] min-[1800px]:grid-cols-[280px_minmax(0,1fr)_310px]">
      <div className="space-y-3">
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-100 px-3 py-2">
            <p className="text-xs font-bold text-slate-800">Test Cases in Run</p>
            <p className="text-[10px] font-medium text-slate-400">{selectedResults.length} case result rows</p>
          </div>
          <div className="max-h-64 overflow-y-auto p-2">
            {selectedResults.map((result) => {
              const testCase = result.test_case_id ? testCaseById.get(result.test_case_id) : undefined;
              const resultSteps = runnableStepList(testCase);
              const resultSummary = manualSummaryFor(manualStepStates, result.id, resultSteps);
              const derivedStatus = manualResultStatus(resultSummary);
              const selected = result.id === selectedResult.id;
              return (
                <button
                  key={result.id}
                  onClick={() => onSelectResult(result.id)}
                  className={cn(
                    "mb-2 w-full rounded-lg border p-3 text-left transition",
                    selected ? "border-blue-200 bg-blue-50" : "border-slate-100 bg-slate-50/50 hover:border-blue-100"
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-mono text-[11px] font-bold text-blue-600">{testCase?.test_case_id || result.external_test_case_id || `Result ${result.id}`}</span>
                    <Badge variant={statusVariant(derivedStatus)} className="text-[9px]">{normalizeStatus(derivedStatus)}</Badge>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs font-bold text-slate-800">{result.test_name}</p>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white">
                    <div className="h-full rounded-full bg-blue-600" style={{ width: `${resultSummary.progress}%` }} />
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-3">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-xs font-bold text-slate-800">Step Navigator</p>
            <Badge variant="outline" className="text-[10px]">{steps.length} Steps</Badge>
          </div>
          <div className="space-y-2">
            {steps.length === 0 ? (
              <p className="rounded-lg bg-slate-50 p-3 text-[11px] font-medium text-slate-400">No structured steps found for this test case.</p>
            ) : (
              steps.map((step, index) => {
                const state = getManualStepState(manualStepStates, selectedResult.id, step.step_number);
                return (
                  <button
                    key={step.step_number}
                    onClick={() => onStepIndexChange(index)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-xs transition",
                      index === safeStepIndex ? "border-blue-200 bg-blue-50 text-blue-700" : "border-slate-100 bg-white text-slate-600 hover:border-blue-100"
                    )}
                  >
                    <span className={cn(
                      "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
                      state.status === "passed" ? "bg-emerald-100 text-emerald-700" :
                        state.status === "failed" ? "bg-rose-100 text-rose-700" :
                          state.status === "blocked" ? "bg-amber-100 text-amber-700" :
                            index === safeStepIndex ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-500"
                    )}>
                      {step.step_number}
                    </span>
                    <span className="line-clamp-1 flex-1 font-semibold">{step.action}</span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="grid gap-3 border-b border-slate-100 p-4 md:grid-cols-5">
            <MetaTile label="Selected Test Case" value={selectedTestCase?.test_case_id || `Result ${selectedResult.id}`} />
            <MetaTile label="Requirement / Story" value={selectedTestCase?.linked_requirement_key || selectedTestCase?.jira_issue_key || "Not linked"} />
            <MetaTile label="Browser / Environment" value={selectedRun.environment || "Not set"} />
            <MetaTile label="Execution Status" value={normalizeStatus(manualResultStatus(summary))} />
            <MetaTile label="Tester" value={selectedRun.triggered_by ? `User ${selectedRun.triggered_by}` : "Unassigned"} />
          </div>

          <div className="p-4">
            <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-900">{selectedResult.test_name}</h3>
                <p className="text-[11px] font-medium text-slate-400">
                  Execution Progress: Step {steps.length ? safeStepIndex + 1 : 0} of {steps.length}
                </p>
              </div>
              <div className="min-w-[180px]">
                <div className="mb-1 flex justify-between text-[10px] font-bold text-slate-400">
                  <span>{formatPercent(summary.progress)}</span>
                  <span>{summary.executed}/{summary.total} executed</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-blue-600" style={{ width: `${summary.progress}%` }} />
                </div>
              </div>
            </div>

            {currentStep ? (
              <div className="rounded-lg border border-slate-200">
                <div className="grid border-b border-slate-100 md:grid-cols-[92px_1fr]">
                  <div className="border-b border-slate-100 bg-slate-50 p-4 md:border-b-0 md:border-r">
                    <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Step No.</p>
                    <p className="mt-2 text-2xl font-bold text-blue-600">{currentStep.step_number}</p>
                  </div>
                  <div className="grid gap-3 p-4 sm:grid-cols-2">
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Step Description</p>
                      <p className="mt-1 text-sm font-semibold leading-relaxed text-slate-800">{currentStep.action}</p>
                    </div>
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Expected Result</p>
                      <p className="mt-1 text-sm font-medium leading-relaxed text-slate-600">{currentStep.expected_result}</p>
                    </div>
                  </div>
                </div>

                <div className="space-y-4 p-4">
                  <label className="block">
                    <span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Actual Result</span>
                    <textarea
                      value={currentState.actualResult}
                      onChange={(event) => onUpdateStep(selectedResult, currentStep.step_number, { actualResult: event.target.value })}
                      placeholder="Enter observed behavior for this step..."
                      className="mt-1 min-h-20 w-full resize-none rounded-lg border border-slate-200 bg-white p-3 text-xs font-medium text-slate-700 outline-none focus:ring-2 focus:ring-blue-100"
                    />
                  </label>

                  <div>
                    <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">Step Outcome</p>
                    <div className="flex flex-wrap gap-2">
                      {([
                        ["passed", "Pass", "success"],
                        ["failed", "Fail", "destructive"],
                        ["blocked", "Blocked", "warning"],
                        ["skipped", "Skipped", "secondary"],
                        ["not_run", "Not Run", "outline"],
                      ] as Array<[ManualStepStatus, string, BadgeVariant]>).map(([status, label, variant]) => (
                        <Button
                          key={status}
                          size="sm"
                          variant={currentState.status === status ? (variant === "destructive" ? "destructive" : "default") : "outline"}
                          onClick={() => onUpdateStep(selectedResult, currentStep.step_number, { status }, `Step ${currentStep.step_number} marked as ${normalizeStatus(status)}`)}
                          className={cn(
                            "h-8 text-xs font-bold",
                            currentState.status !== status && "border-slate-200 bg-white text-slate-700",
                            currentState.status === status && variant === "warning" && "bg-amber-500 text-white hover:bg-amber-600",
                            currentState.status === status && variant === "secondary" && "bg-slate-700 text-white hover:bg-slate-800"
                          )}
                        >
                          {label}
                        </Button>
                      ))}
                    </div>
                  </div>

                  <label className="block">
                    <span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Comments</span>
                    <textarea
                      value={currentState.comments}
                      onChange={(event) => onUpdateStep(selectedResult, currentStep.step_number, { comments: event.target.value })}
                      placeholder="Add tester comments, observations, or defect notes..."
                      className="mt-1 min-h-16 w-full resize-none rounded-lg border border-slate-200 bg-white p-3 text-xs font-medium text-slate-700 outline-none focus:ring-2 focus:ring-blue-100"
                    />
                  </label>

                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" variant="outline" className="h-8 border-slate-200 bg-white text-xs" onClick={() => onAttachEvidence(selectedResult, currentStep.step_number, `screenshot-step-${currentStep.step_number}.png`)}>
                        <Camera className="h-3.5 w-3.5" />
                        Attach Screenshot
                      </Button>
                      <label className="inline-flex h-8 cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition hover:bg-slate-50">
                        <Paperclip className="h-3.5 w-3.5" />
                        Upload File
                        <input
                          type="file"
                          className="hidden"
                          onChange={(event) => {
                            const file = event.target.files?.[0];
                            if (file) onAttachEvidence(selectedResult, currentStep.step_number, file.name);
                            event.target.value = "";
                          }}
                        />
                      </label>
                      {(currentState.status === "failed" || currentState.status === "blocked") && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 border-rose-200 bg-white text-xs font-bold text-rose-600 hover:bg-rose-50"
                          disabled={creatingDefectKey === manualStepKey(selectedResult.id, currentStep.step_number)}
                          onClick={() => onCreateDefect(selectedResult, currentStep.step_number)}
                        >
                          <Bug className="h-3.5 w-3.5" />
                          {creatingDefectKey === manualStepKey(selectedResult.id, currentStep.step_number) ? "Creating..." : "Create Jira Defect Draft"}
                        </Button>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button size="sm" variant="outline" className="h-8 border-slate-200 bg-white text-xs" disabled={safeStepIndex === 0} onClick={() => onStepIndexChange(safeStepIndex - 1)}>
                        <ArrowLeft className="h-3.5 w-3.5" />
                        Previous Step
                      </Button>
                      <Button size="sm" className="h-8 text-xs font-bold" onClick={() => onSaveNext(selectedResult, steps)}>
                        Save & Next Step
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>

                  <div className="flex flex-col gap-2 border-t border-slate-100 pt-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-[11px] font-semibold text-emerald-600">
                      <Save className="mr-1 inline h-3.5 w-3.5" />
                      {autoSaveMessage || "Auto-save ready"}
                    </p>
                    <Button size="sm" variant="outline" className="h-8 border-blue-200 bg-white text-xs font-bold text-blue-600 hover:bg-blue-50" onClick={() => onMarkComplete(selectedResult, steps)}>
                      <UserCheck className="h-3.5 w-3.5" />
                      Mark Test Case Complete
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <EmptyState title="No current step" description="This test case does not have structured manual steps yet." />
            )}
          </div>
        </div>
      </div>

      <div className="space-y-3 xl:col-span-2 min-[1800px]:col-span-1">
        <div className="rounded-lg border border-slate-200 bg-white p-3">
          <p className="mb-3 text-xs font-bold text-slate-800">Step-Level Summary</p>
          <div className="grid grid-cols-2 gap-2">
            <SummaryPill label="Passed" value={summary.passed} className="text-emerald-600" />
            <SummaryPill label="Failed" value={summary.failed} className="text-rose-600" />
            <SummaryPill label="Blocked" value={summary.blocked} className="text-amber-600" />
            <SummaryPill label="Not Executed" value={summary.notRun} className="text-slate-500" />
            <SummaryPill label="Total Steps" value={summary.total} className="text-blue-600" />
            <SummaryPill label="Pass Rate" value={formatPercent(summary.passRate)} className="text-emerald-600" />
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-3">
          <p className="mb-2 text-xs font-bold text-slate-800">Evidence and Logs</p>
          {currentStep && currentState.evidence.length > 0 ? (
            <div className="space-y-2">
              {currentState.evidence.map((item) => (
                <div key={item} className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-[11px] font-semibold text-slate-600">
                  {item}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[11px] font-medium text-slate-400">No evidence attached to the current step.</p>
          )}
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-3">
          <p className="mb-2 text-xs font-bold text-slate-800">Activity Timeline</p>
          {selectedActivity.length > 0 ? (
            <div className="space-y-2">
              {selectedActivity.map((event) => (
                <div key={event.id} className="flex gap-2 rounded-lg bg-slate-50 p-2">
                  <span className={cn(
                    "mt-1 h-2 w-2 shrink-0 rounded-full",
                    event.tone === "success" ? "bg-emerald-500" :
                      event.tone === "danger" ? "bg-rose-500" :
                        event.tone === "warning" ? "bg-amber-500" : "bg-blue-500"
                  )} />
                  <div className="min-w-0">
                    <p className="text-[11px] font-bold text-slate-700">{event.message}</p>
                    <p className="text-[10px] font-medium text-slate-400">{dateLabel(event.timestamp)}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[11px] font-medium text-slate-400">No manual execution activity yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function AutomationWorkspace({
  selectedRun,
  selectedResults,
  testCaseById,
  automationState,
  onAutomationAction,
  isAutomationActionRunning,
}: {
  selectedRun: ExecutionRun;
  selectedResults: ExecutionResult[];
  testCaseById: Map<number, TestCase>;
  automationState: AutomationRunState;
  onAutomationAction: (action: "start" | "pause" | "retry_failed" | "analyze_failure" | "create_defect") => void;
  isAutomationActionRunning: boolean;
}) {
  const counts = resultStatusCounts(selectedResults);
  const executed = counts.passed + counts.failed + counts.blocked + counts.skipped;
  const passRate = safePercent(counts.passed || selectedRun.passed || 0, executed || selectedRun.total_tests || 0);
  const failedCount = counts.failed || selectedRun.failed || 0;
  const framework = frameworkForRun(selectedRun, selectedResults);
  const selectedResult = selectedResults[0];
  const selectedCase = selectedResult?.test_case_id ? testCaseById.get(selectedResult.test_case_id) : undefined;
  const failure = automationFailureInsight(selectedResults);
  const streamRows = selectedResults.slice(0, 6);
  const currentStep = automationState.currentStep || selectedResult?.test_name || "Waiting for execution command";

  return (
    <div className="grid gap-4 p-4 xl:grid-cols-[0.85fr_1.25fr]">
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <MetaTile label="Requirement / Story" value={selectedCase?.linked_requirement_key || selectedCase?.jira_issue_key || "Not linked"} />
          <MetaTile label="Browser / Environment" value={selectedRun.environment || "Not set"} />
          <MetaTile label="Framework" value={framework} />
          <MetaTile label="Executor" value={selectedRun.external_tool_name ? "External runner" : "Service abstraction"} />
          <MetaTile label="Execution Status" value={normalizeStatus(automationState.status)} />
          <MetaTile label="Progress" value={`${formatPercent(passRate)} pass rate`} />
        </div>

        <div className="rounded-lg border border-slate-200">
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <div>
              <p className="text-xs font-bold text-slate-800">Test Cases / Script Mapping</p>
              <p className="text-[10px] font-semibold text-slate-400">Platform case to automation script path</p>
            </div>
            <Badge variant="outline" className="text-[10px]">{selectedResults.length} mapped</Badge>
          </div>
          <div className="max-h-72 overflow-y-auto p-2">
            {selectedResults.length ? selectedResults.map((result) => {
              const testCase = result.test_case_id ? testCaseById.get(result.test_case_id) : undefined;
              return (
                <div key={result.id} className="mb-2 rounded-lg border border-slate-100 bg-slate-50/50 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-xs font-bold text-slate-800">{testCase?.test_case_id || result.external_test_case_id || `Result ${result.id}`}</p>
                      <p className="truncate text-[11px] font-semibold text-slate-500">{result.test_name}</p>
                    </div>
                    <Badge variant={statusVariant(result.automation_execution_status || result.status)} className="text-[10px]">
                      {normalizeStatus(result.automation_execution_status || result.status)}
                    </Badge>
                  </div>
                  <p className="mt-2 truncate rounded bg-white px-2 py-1 font-mono text-[10px] text-slate-500">
                    {scriptPathForResult(result, testCase)}
                  </p>
                </div>
              );
            }) : (
              <EmptyState title="No script mapping loaded" description="Automation mappings will appear here when execution results or script metadata are returned by existing APIs." />
            )}
          </div>
        </div>

        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-[11px] font-semibold leading-relaxed text-amber-800">
          Automation actions are integration-ready. They update orchestration state locally and do not claim that backend execution happened unless a runner API is connected.
        </div>
      </div>

      <div className="space-y-4">
        <div className="rounded-lg border border-slate-200 bg-slate-50/30 p-3">
          <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-bold text-slate-800">Automation Execution Orchestrator</p>
              <p className="text-[11px] font-semibold text-slate-400">{selectedRun.execution_id} - {selectedRun.suite_name || "Automation run"}</p>
            </div>
            <Badge variant={statusVariant(automationState.status)}>{normalizeStatus(automationState.status)}</Badge>
          </div>

          <div className="grid gap-3 xl:grid-cols-[1.2fr_0.8fr]">
            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
              <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2">
                <span className="h-2.5 w-2.5 rounded-full bg-rose-400" />
                <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
                <span className="ml-2 truncate font-mono text-[10px] font-semibold text-slate-400">automation://{framework.toLowerCase()}/{selectedRun.environment || "environment"}</span>
              </div>
              <div className="flex min-h-[260px] flex-col justify-between bg-white p-4">
                <div>
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-bold text-slate-900">Live Execution Viewer</p>
                      <p className="text-[11px] font-semibold text-slate-400">Viewer is ready for runner screenshots, trace, or video stream.</p>
                    </div>
                    <Monitor className="h-5 w-5 text-blue-500" />
                  </div>
                  <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs font-bold text-slate-800">{currentStep}</p>
                    <p className="mt-2 text-[11px] font-medium leading-relaxed text-slate-500">
                      {automationState.message}
                    </p>
                  </div>
                </div>
                <div className="mt-4 grid gap-2 sm:grid-cols-4">
                  <SummaryPill label="Passed" value={counts.passed || selectedRun.passed || 0} className="text-emerald-600" />
                  <SummaryPill label="Failed" value={failedCount} className="text-rose-600" />
                  <SummaryPill label="Skipped" value={counts.skipped || selectedRun.skipped || 0} className="text-slate-500" />
                  <SummaryPill label="Pass Rate" value={formatPercent(passRate)} className="text-blue-600" />
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <p className="text-xs font-bold text-slate-800">Execution Stream</p>
              <div className="mt-3 space-y-2 text-[11px] font-medium text-slate-500">
                <StreamRow label="Current Step" value={currentStep} />
                <StreamRow label="Status" value={normalizeStatus(automationState.status)} />
                <StreamRow label="Started At" value={dateLabel(automationState.startedAt || selectedRun.started_at || selectedRun.created_at)} />
                <StreamRow label="Elapsed Time" value={`${formatNumber(automationState.elapsedSeconds)}s`} />
              </div>
              <div className="mt-4 rounded-lg bg-slate-950 p-3 font-mono text-[10px] leading-relaxed text-slate-200">
                <p>$ automation adapter status</p>
                <p className="text-slate-400">{automationState.message}</p>
                {streamRows.length ? streamRows.slice(0, 3).map((result) => (
                  <p key={result.id} className={cn(
                    "truncate",
                    ["failed", "error"].includes((result.status || "").toLowerCase()) ? "text-rose-300" : "text-emerald-300"
                  )}>
                    {normalizeStatus(result.status)} - {result.test_name}
                  </p>
                )) : (
                  <p className="text-amber-300">No result stream returned by backend yet.</p>
                )}
              </div>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <Button size="sm" className="h-8 text-xs font-bold" disabled={isAutomationActionRunning} onClick={() => onAutomationAction("start")}>
              {isAutomationActionRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              Start Execution
            </Button>
            <Button size="sm" variant="outline" className="h-8 border-slate-200 bg-white text-xs" disabled={isAutomationActionRunning} onClick={() => onAutomationAction("pause")}>
              <Pause className="h-3.5 w-3.5" /> Pause
            </Button>
            <Button size="sm" variant="outline" className="h-8 border-slate-200 bg-white text-xs" disabled={isAutomationActionRunning} onClick={() => onAutomationAction("retry_failed")}>
              <RotateCcw className="h-3.5 w-3.5" /> Retry Failed
            </Button>
            <Button size="sm" variant="outline" className="h-8 border-violet-200 bg-white text-xs text-violet-700" disabled={isAutomationActionRunning} onClick={() => onAutomationAction("analyze_failure")}>
              <Wand2 className="h-3.5 w-3.5" /> Analyze Failure
            </Button>
            <Button size="sm" variant="outline" className="h-8 border-rose-200 bg-white text-xs text-rose-600" disabled={!failure || isAutomationActionRunning} onClick={() => onAutomationAction("create_defect")}>
              <Bug className="h-3.5 w-3.5" /> Create Jira Defect
            </Button>
            <Button size="sm" variant="outline" className="h-8 border-slate-200 bg-white text-xs" disabled>
              More <ChevronDown className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 p-3">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-xs font-bold text-slate-800">Recent Actions</p>
            <Clock3 className="h-4 w-4 text-slate-400" />
          </div>
          <div className="space-y-2">
            {automationState.recentActions.length ? automationState.recentActions.slice(0, 4).map((action, index) => (
              <p key={`${action}-${index}`} className="rounded-md bg-slate-50 px-2 py-1.5 text-[11px] font-semibold text-slate-600">{action}</p>
            )) : (
              <p className="rounded-md bg-slate-50 px-2 py-1.5 text-[11px] font-semibold text-slate-400">No automation actions captured yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function AiWorkspace({
  selectedRun,
  selectedTestCase,
  selectedResults,
  aiState,
  onAiModeChange,
  onGeneratePlan,
  onApprovePlan,
  onRunAiExecution,
  onPause,
  onAnalyzeFailure,
  onDraftDefect,
}: {
  selectedRun: ExecutionRun;
  selectedTestCase?: TestCase;
  selectedResults: ExecutionResult[];
  aiState: AiWorkspaceState;
  onAiModeChange: (mode: AiMode) => void;
  onGeneratePlan: () => void;
  onApprovePlan: () => void;
  onRunAiExecution: () => void;
  onPause: () => void;
  onAnalyzeFailure: () => void;
  onDraftDefect: () => void;
}) {
  const steps = runnableStepList(selectedTestCase);
  const currentStep = aiState.executionSteps[0] || steps[0]?.action || "Generate an AI execution plan to begin.";
  const failedResult = automationFailureInsight(selectedResults);

  return (
    <div className="grid gap-4 p-4 xl:grid-cols-[0.9fr_1.1fr]">
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <MetaTile label="Selected Test Case" value={selectedTestCase?.test_case_id || selectedTestCase?.title || "Not selected"} />
          <MetaTile label="Requirement / Story" value={selectedTestCase?.linked_requirement_key || selectedTestCase?.jira_issue_key || "Not linked"} />
          <MetaTile label="Target URL" value={typeof selectedRun.metadata_?.target_url === "string" ? selectedRun.metadata_.target_url : "Not provided"} />
          <MetaTile label="Browser / Environment" value={selectedRun.environment || "Not set"} />
          <MetaTile label="AI Mode" value={aiState.mode} />
          <MetaTile label="Execution Status" value={normalizeStatus(aiState.status)} />
        </div>

        <div className="rounded-lg border border-slate-200">
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <div>
              <p className="text-xs font-bold text-slate-800">Agent Execution Plan</p>
              <p className="text-[10px] font-semibold text-slate-400">Pre-execution AI run strategy, not a test plan</p>
            </div>
            <Badge variant={aiState.approved ? "success" : aiState.planGenerated ? "warning" : "secondary"} className="text-[10px]">
              {aiState.approved ? "Approved" : aiState.planGenerated ? "Review Required" : "Not Generated"}
            </Badge>
          </div>
          <div className="max-h-80 overflow-y-auto p-3">
            {aiState.planGenerated ? (
              <div className="space-y-3">
                <PlanList title="Execution Steps" items={aiState.executionSteps} />
                <PlanList title="Browser Actions" items={aiState.browserActions} />
                <PlanList title="Expected Validations" items={aiState.validations} />
                <PlanList title="Required Test Data" items={aiState.testData} />
                <PlanList title="Locator / Selector Suggestions" items={aiState.selectorSuggestions} mono />
                <PlanList title="Risks and Limitations" items={aiState.risks} warning />
              </div>
            ) : (
              <EmptyState title="No AI execution plan generated" description="Use Generate AI Execution Plan to create a reviewable strategy for the selected test case." />
            )}
          </div>
        </div>

        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-[11px] font-semibold leading-relaxed text-amber-800">
          AI suggestions require human review before applying changes or creating defects.
        </div>
        <div className="rounded-lg border border-blue-100 bg-blue-50 p-3 text-[11px] font-semibold leading-relaxed text-blue-800">
          Traceability: Requirement / Jira Story &gt; Test Case &gt; Execution Run &gt; Step Result / Evidence &gt; Defect Draft &gt; Jira Issue.
        </div>
      </div>

      <div className="space-y-4">
        <div className="rounded-lg border border-slate-200 bg-slate-50/30 p-3">
          <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-bold text-slate-800">AI Agent Workspace</p>
              <p className="text-[11px] font-semibold text-slate-400">{selectedRun.execution_id} - human-approved AI execution</p>
            </div>
            <select
              value={aiState.mode}
              onChange={(event) => onAiModeChange(event.target.value as AiMode)}
              className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs font-bold text-slate-700"
            >
              <option>Assistive</option>
              <option>Semi-Autonomous</option>
              <option>Experimental Autonomous</option>
            </select>
          </div>

          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2">
              <span className="h-2.5 w-2.5 rounded-full bg-rose-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
              <span className="ml-2 truncate font-mono text-[10px] font-semibold text-slate-400">ai-agent://review-gated/{selectedRun.environment || "environment"}</span>
            </div>
            <div className="min-h-[270px] bg-white p-4">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-bold text-slate-900">Live Execution Viewer</p>
                  <p className="text-[11px] font-semibold text-slate-400">AI execution is disabled until plan generation and human approval are complete.</p>
                </div>
                <Bot className="h-5 w-5 text-violet-600" />
              </div>
              <div className="rounded-lg border border-dashed border-violet-200 bg-violet-50/40 p-4">
                <p className="text-xs font-bold text-slate-800">{currentStep}</p>
                <p className="mt-2 text-[11px] font-medium leading-relaxed text-slate-600">
                  {aiState.planGenerated
                    ? aiState.approved
                      ? "Plan approved. AI execution can be started in a guarded, assistive mode."
                      : "Plan generated and awaiting human approval before execution."
                    : "Generate AI Execution Plan to produce execution steps, browser actions, validations, data needs, selector suggestions, risks, and confidence."}
                </p>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-3">
                <SummaryPill label="Confidence" value={formatPercent(aiState.confidence)} className="text-violet-600" />
                <SummaryPill label="Plan Steps" value={aiState.executionSteps.length} className="text-blue-600" />
                <SummaryPill label="Evidence Items" value={selectedResults.filter((result) => result.screenshot_url || result.log_url || result.video_url || result.raw_result_json).length} className="text-emerald-600" />
              </div>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <Button size="sm" variant="ai" className="h-8 text-xs font-bold" onClick={onGeneratePlan}>
              <Sparkles className="h-3.5 w-3.5" /> Generate AI Execution Plan
            </Button>
            <Button size="sm" variant="outline" className="h-8 border-emerald-200 bg-white text-xs text-emerald-700" disabled={!aiState.planGenerated || aiState.approved} onClick={onApprovePlan}>
              <ShieldCheck className="h-3.5 w-3.5" /> Approve Plan
            </Button>
            <Button size="sm" className="h-8 text-xs font-bold" disabled={!aiState.planGenerated || !aiState.approved} onClick={onRunAiExecution}>
              <Play className="h-3.5 w-3.5" /> Run AI Execution
            </Button>
            <Button size="sm" variant="outline" className="h-8 border-slate-200 bg-white text-xs" disabled={!aiState.planGenerated} onClick={onPause}>
              <Pause className="h-3.5 w-3.5" /> Pause
            </Button>
            <Button size="sm" variant="outline" className="h-8 border-violet-200 bg-white text-xs text-violet-700" disabled={!aiState.planGenerated} onClick={onAnalyzeFailure}>
              <Wand2 className="h-3.5 w-3.5" /> Analyze Failure
            </Button>
            <Button size="sm" variant="outline" className="h-8 border-rose-200 bg-white text-xs text-rose-600" disabled={!aiState.planGenerated} onClick={onDraftDefect}>
              <Bug className="h-3.5 w-3.5" /> Draft Jira Defect
            </Button>
            <Button size="sm" variant="outline" className="h-8 border-slate-200 bg-white text-xs" disabled>
              More <ChevronDown className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 p-3">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-xs font-bold text-slate-800">AI Agent Reasoning and Observations</p>
            <Badge variant={aiState.confidence >= 80 ? "success" : aiState.confidence > 0 ? "warning" : "secondary"}>{aiState.confidence ? formatPercent(aiState.confidence) : "No Confidence"}</Badge>
          </div>
          <div className="space-y-2">
            {(aiState.observations.length ? aiState.observations : ["No AI reasoning available until a plan is generated."]).map((item, index) => (
              <p key={`${item}-${index}`} className="rounded-md bg-slate-50 px-2 py-1.5 text-[11px] font-semibold text-slate-600">{item}</p>
            ))}
            {failedResult && (
              <p className="rounded-md bg-rose-50 px-2 py-1.5 text-[11px] font-semibold text-rose-700">
                Existing failure signal detected: {failedResult.message}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function PlanList({ title, items, mono, warning }: { title: string; items: string[]; mono?: boolean; warning?: boolean }) {
  return (
    <div className={cn("rounded-lg border p-3", warning ? "border-amber-200 bg-amber-50" : "border-slate-100 bg-slate-50/60")}>
      <p className={cn("text-xs font-bold", warning ? "text-amber-800" : "text-slate-800")}>{title}</p>
      <ul className="mt-2 space-y-1">
        {items.map((item, index) => (
          <li key={`${title}-${index}`} className={cn("text-[11px] font-medium leading-relaxed", warning ? "text-amber-700" : "text-slate-600", mono && "font-mono")}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function WorkspaceShell({
  tab,
  selectedRun,
  selectedTestCase,
  selectedResults,
  testCaseById,
  selectedManualResultId,
  onSelectManualResult,
  currentManualStepIndex,
  onManualStepIndexChange,
  manualStepStates,
  onUpdateManualStep,
  onSaveManualNext,
  onMarkManualComplete,
  onAttachManualEvidence,
  onCreateManualDefect,
  creatingDefectKey,
  manualActivity,
  autoSaveMessage,
  automationRunStates,
  onAutomationAction,
  automationActionRunId,
  aiWorkspaceStates,
  onAiModeChange,
  onGenerateAiPlan,
  onApproveAiPlan,
  onRunAiExecution,
  onPauseAiExecution,
  onAnalyzeAiFailure,
  onDraftAiDefect,
}: {
  tab: ExecutionTab;
  selectedRun?: ExecutionRun;
  selectedTestCase?: TestCase;
  selectedResults: ExecutionResult[];
  testCaseById: Map<number, TestCase>;
  selectedManualResultId: number | null;
  onSelectManualResult: (resultId: number) => void;
  currentManualStepIndex: number;
  onManualStepIndexChange: (index: number) => void;
  manualStepStates: Record<string, ManualStepState>;
  onUpdateManualStep: (result: ExecutionResult, stepNumber: number, patch: Partial<ManualStepState>, message?: string) => void;
  onSaveManualNext: (result: ExecutionResult, steps: ReturnType<typeof stepList>) => void;
  onMarkManualComplete: (result: ExecutionResult, steps: ReturnType<typeof stepList>) => void;
  onAttachManualEvidence: (result: ExecutionResult, stepNumber: number, label: string) => void;
  onCreateManualDefect: (result: ExecutionResult, stepNumber: number) => void;
  creatingDefectKey: string | null;
  manualActivity: ManualActivity[];
  autoSaveMessage: string | null;
  automationRunStates: Record<string, AutomationRunState>;
  onAutomationAction: (run: ExecutionRun, action: "start" | "pause" | "retry_failed" | "analyze_failure" | "create_defect") => void;
  automationActionRunId: number | null;
  aiWorkspaceStates: Record<string, AiWorkspaceState>;
  onAiModeChange: (run: ExecutionRun, mode: AiMode) => void;
  onGenerateAiPlan: (run: ExecutionRun, testCase?: TestCase) => void;
  onApproveAiPlan: (run: ExecutionRun) => void;
  onRunAiExecution: (run: ExecutionRun) => void;
  onPauseAiExecution: (run: ExecutionRun) => void;
  onAnalyzeAiFailure: (run: ExecutionRun) => void;
  onDraftAiDefect: (run: ExecutionRun, testCase?: TestCase) => void;
}) {
  const steps = stepList(selectedTestCase);
  const passRate = safePercent(selectedRun?.passed || 0, (selectedRun?.passed || 0) + (selectedRun?.failed || 0) + (selectedRun?.skipped || 0));

  if (!selectedRun) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <EmptyState
          title={`No ${TAB_LABELS[tab].toLowerCase()} run selected`}
          description="Select a run from the execution catalog or create a new run when backend orchestration is available."
        />
      </section>
    );
  }

  if (tab === "manual") {
    return (
      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-100 p-4 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <p className="font-mono text-xs font-bold text-blue-600">{selectedRun.execution_id}</p>
            <h2 className="mt-1 truncate text-base font-bold text-slate-900">{selectedRun.suite_name || TAB_LABELS[tab]}</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={statusVariant(selectedRun.status)}>{normalizeStatus(selectedRun.status)}</Badge>
            <Badge variant="outline">{selectedRun.environment || "No environment"}</Badge>
            <Badge variant="secondary">{TAB_LABELS[tab]}</Badge>
          </div>
        </div>
        <ManualWorkspace
          selectedRun={selectedRun}
          selectedResults={selectedResults}
          testCaseById={testCaseById}
          selectedResultId={selectedManualResultId}
          onSelectResult={onSelectManualResult}
          currentStepIndex={currentManualStepIndex}
          onStepIndexChange={onManualStepIndexChange}
          manualStepStates={manualStepStates}
          onUpdateStep={onUpdateManualStep}
          onSaveNext={onSaveManualNext}
          onMarkComplete={onMarkManualComplete}
          onAttachEvidence={onAttachManualEvidence}
          onCreateDefect={onCreateManualDefect}
          creatingDefectKey={creatingDefectKey}
          activity={manualActivity}
          autoSaveMessage={autoSaveMessage}
        />
      </section>
    );
  }

  if (tab === "automation") {
    const automationState = automationRunStateFor(selectedRun, automationRunStates[automationStateKey(selectedRun.id)]);
    return (
      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-100 p-4 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <p className="font-mono text-xs font-bold text-blue-600">{selectedRun.execution_id}</p>
            <h2 className="mt-1 truncate text-base font-bold text-slate-900">{selectedRun.suite_name || TAB_LABELS[tab]}</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={statusVariant(automationState.status)}>{normalizeStatus(automationState.status)}</Badge>
            <Badge variant="outline">{selectedRun.environment || "No environment"}</Badge>
            <Badge variant="info">{frameworkForRun(selectedRun, selectedResults)}</Badge>
          </div>
        </div>
        <AutomationWorkspace
          selectedRun={selectedRun}
          selectedResults={selectedResults}
          testCaseById={testCaseById}
          automationState={automationState}
          onAutomationAction={(action) => onAutomationAction(selectedRun, action)}
          isAutomationActionRunning={automationActionRunId === selectedRun.id}
        />
      </section>
    );
  }

  const aiState = aiWorkspaceStateFor(selectedRun, aiWorkspaceStates[aiStateKey(selectedRun.id)]);
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-col gap-3 border-b border-slate-100 p-4 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <p className="font-mono text-xs font-bold text-blue-600">{selectedRun.execution_id}</p>
          <h2 className="mt-1 truncate text-base font-bold text-slate-900">{selectedRun.suite_name || TAB_LABELS[tab]}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={statusVariant(aiState.status)}>{normalizeStatus(aiState.status)}</Badge>
          <Badge variant="outline">{selectedRun.environment || "No environment"}</Badge>
          <Badge variant="purple">{aiState.mode}</Badge>
        </div>
      </div>
      <AiWorkspace
        selectedRun={selectedRun}
        selectedTestCase={selectedTestCase}
        selectedResults={selectedResults}
        aiState={aiState}
        onAiModeChange={(mode) => onAiModeChange(selectedRun, mode)}
        onGeneratePlan={() => onGenerateAiPlan(selectedRun, selectedTestCase)}
        onApprovePlan={() => onApproveAiPlan(selectedRun)}
        onRunAiExecution={() => onRunAiExecution(selectedRun)}
        onPause={() => onPauseAiExecution(selectedRun)}
        onAnalyzeFailure={() => onAnalyzeAiFailure(selectedRun)}
        onDraftDefect={() => onDraftAiDefect(selectedRun, selectedTestCase)}
      />
    </section>
  );
}

function MetaTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 truncate text-xs font-bold text-slate-800">{value}</p>
    </div>
  );
}

function StreamRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
      <span className="text-slate-400">{label}</span>
      <span className="truncate text-right font-bold text-slate-700">{value}</span>
    </div>
  );
}

function JiraDefectActions({
  defect,
  link,
  busy,
  onApprove,
  onPush,
  onLinkExisting,
}: {
  defect: DefectDraft;
  link: JiraDefectLink | null;
  busy: boolean;
  onApprove: (defect: DefectDraft) => void;
  onPush: (defect: DefectDraft) => void;
  onLinkExisting: (defect: DefectDraft) => void;
}) {
  const key = link?.jira_issue_key || jiraKeyForDefect(defect, link ? { [defect.id]: link } : {});
  const url = jiraUrlForKey(key, link?.jira_url);
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <Badge variant={statusVariant(defect.status)} className="text-[10px]">{normalizeStatus(defect.status)}</Badge>
      {key && <Badge variant="info" className="font-mono text-[10px]">{key}</Badge>}
      {link?.jira_status && <Badge variant="outline" className="text-[10px]">{link.jira_status}</Badge>}
      {defect.status === "draft" && (
        <Button size="sm" variant="outline" className="h-7 border-emerald-200 bg-white text-[10px] text-emerald-700" disabled={busy} onClick={() => onApprove(defect)}>
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <ShieldCheck className="h-3 w-3" />}
          Approve Defect
        </Button>
      )}
      {defect.status === "approved" && (
        <Button size="sm" className="h-7 text-[10px]" disabled={busy} onClick={() => onPush(defect)}>
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <ExternalLink className="h-3 w-3" />}
          Push to Jira
        </Button>
      )}
      <Button size="sm" variant="outline" className="h-7 border-slate-200 bg-white text-[10px]" disabled={busy} onClick={() => onLinkExisting(defect)}>
        Link Jira Issue
      </Button>
      <Button
        size="sm"
        variant="outline"
        className="h-7 border-slate-200 bg-white text-[10px]"
        disabled={!url}
        onClick={() => {
          if (url) window.open(url, "_blank", "noopener,noreferrer");
        }}
      >
        View Jira
      </Button>
    </div>
  );
}

function TraceabilityChain({ items }: { items: Array<{ label: string; value: string }> }) {
  return (
    <div className="mt-3 rounded-lg border border-slate-100 bg-slate-50 p-3">
      <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">Traceability</p>
      <div className="grid gap-2 md:grid-cols-2">
        {items.map((item) => (
          <div key={item.label} className="rounded-md bg-white px-2 py-1.5">
            <p className="text-[9px] font-bold uppercase tracking-wide text-slate-400">{item.label}</p>
            <p className="truncate text-[11px] font-bold text-slate-700">{item.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function DetailsPanel({
  tab,
  selectedRun,
  selectedTestCase,
  selectedResults,
  defects,
  testCaseById,
  selectedManualResultId,
  manualStepStates,
  manualActivity,
  automationRunStates,
  aiWorkspaceStates,
  jiraDefectLinks,
  jiraBusyId,
  onApproveDefect,
  onPushDefectToJira,
  onLinkExistingJira,
  failureDecisions,
  onSaveFailureDecision,
  onClearFailureDecision,
  onCreateManualDefect,
}: {
  tab: ExecutionTab;
  selectedRun?: ExecutionRun;
  selectedTestCase?: TestCase;
  selectedResults: ExecutionResult[];
  defects: DefectDraft[];
  testCaseById: Map<number, TestCase>;
  selectedManualResultId: number | null;
  manualStepStates: Record<string, ManualStepState>;
  manualActivity: ManualActivity[];
  automationRunStates: Record<string, AutomationRunState>;
  aiWorkspaceStates: Record<string, AiWorkspaceState>;
  jiraDefectLinks: Record<number, JiraDefectLink>;
  jiraBusyId: number | null;
  onApproveDefect: (defect: DefectDraft) => void;
  onPushDefectToJira: (defect: DefectDraft) => void;
  onLinkExistingJira: (defect: DefectDraft) => void;
  failureDecisions: Record<number, {
    resultId: number;
    decision: "defect" | "linked" | "known_issue" | "waived";
    jiraKey?: string;
    comment?: string;
    timestamp: string;
  }>;
  onSaveFailureDecision: (resultId: number, decision: "defect" | "linked" | "known_issue" | "waived", jiraKey: string, comment: string) => void;
  onClearFailureDecision: (resultId: number) => void;
  onCreateManualDefect: (result: ExecutionResult, stepNumber: number) => void;
}) {
  const [detailTab, setDetailTab] = useState<"overview" | "decisions" | "evidence" | "logs">("overview");
  const [formDecisionStates, setFormDecisionStates] = useState<Record<number, {
    decision: "defect" | "linked" | "known_issue" | "waived";
    jiraKey?: string;
    comment?: string;
  }>>({});

  const selectedManualResult = selectedResults.find((result) => result.id === selectedManualResultId) || selectedResults[0];
  const selectedManualTestCase = selectedManualResult?.test_case_id ? testCaseById.get(selectedManualResult.test_case_id) : undefined;
  const selectedManualSteps = runnableStepList(selectedManualTestCase);
  const manualSummary = manualSummaryFor(manualStepStates, selectedManualResult?.id, selectedManualSteps);
  const counts = tab === "manual"
    ? {
        passed: manualSummary.passed,
        failed: manualSummary.failed,
        blocked: manualSummary.blocked,
        skipped: manualSummary.skipped,
        notRun: manualSummary.notRun,
      }
    : resultStatusCounts(selectedResults);
  const executed = counts.passed + counts.failed + counts.blocked + counts.skipped;
  const passRate = tab === "manual" ? manualSummary.passRate : safePercent(counts.passed || selectedRun?.passed || 0, executed || selectedRun?.total_tests || 0);
  const selectedResultIds = new Set(selectedResults.map((result) => result.id));
  const selectedTestCaseIds = new Set([
    ...selectedResults.map((result) => result.test_case_id).filter(Boolean),
    selectedTestCase?.id,
  ].filter(Boolean) as number[]);
  const linkedDefects = defects.filter((defect) => (
    (defect.execution_result_id && selectedResultIds.has(defect.execution_result_id)) ||
    (defect.test_case_id && selectedTestCaseIds.has(defect.test_case_id))
  ));
  const panelActivity = manualActivity.filter((event) => !selectedManualResult || event.resultId === selectedManualResult.id).slice(0, 4);
  const automationState = selectedRun ? automationRunStateFor(selectedRun, automationRunStates[automationStateKey(selectedRun.id)]) : null;
  const automationFailure = automationFailureInsight(selectedResults);
  const aiState = selectedRun ? aiWorkspaceStateFor(selectedRun, aiWorkspaceStates[aiStateKey(selectedRun.id)]) : null;
  const aiFailure = automationFailureInsight(selectedResults);

  const failedResults = selectedResults.filter(
    (r) => ["failed", "error"].includes((r.status || "").toLowerCase())
  );
  const undecidedCount = failedResults.filter((r) => !failureDecisions[r.id]).length;

  if (!selectedRun) {
    return (
      <aside className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 p-4">
          <h3 className="text-sm font-bold text-slate-900">Execution Details</h3>
          <PanelRight className="h-4 w-4 text-slate-400" />
        </div>
        <div className="p-4">
          <p className="text-xs font-medium text-slate-400 text-center py-8">Select an execution run to inspect telemetry details.</p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 p-4 pb-2">
        <div>
          <h3 className="text-sm font-bold text-slate-900">{tab === "ai" ? "AI Analysis cockpit" : "Execution detail workspace"}</h3>
          <p className="text-[11px] font-medium text-slate-400">Run ID: {selectedRun.execution_id}</p>
        </div>
        <PanelRight className="h-4 w-4 text-slate-400" />
      </div>

      <div className="flex border-b border-slate-100 bg-slate-50/50 px-4">
        {[
          { id: "overview", label: "Overview" },
          { id: "decisions", label: `Failure Decisions (${undecidedCount})` },
          { id: "evidence", label: "Evidence & Files" },
          { id: "logs", label: "Agent Logs" },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setDetailTab(t.id as any)}
            className={cn(
              "flex h-10 items-center justify-center border-b-2 px-3 text-[11px] font-bold transition",
              detailTab === t.id
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:text-slate-900"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {detailTab === "overview" && (
        <div className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-12">
          <div className="grid grid-cols-2 gap-3 xl:col-span-4">
            <MetaTile label="Pass Rate" value={formatPercent(passRate)} />
            <MetaTile label="Environment" value={selectedRun?.environment || "-"} />
            <MetaTile label="Started At" value={dateLabel(selectedRun?.started_at || selectedRun?.created_at)} />
            <MetaTile label="Last Updated" value={dateLabel(selectedRun?.updated_at)} />
          </div>

          <div className="rounded-lg border border-slate-200 p-3 xl:col-span-4">
            <p className="mb-3 text-xs font-bold text-slate-800">Step-Level Summary</p>
            <div className="grid grid-cols-2 gap-2 text-xs lg:grid-cols-3 xl:grid-cols-6">
              <SummaryPill label="Passed" value={counts.passed || selectedRun?.passed || 0} className="text-emerald-600" />
              <SummaryPill label="Failed" value={counts.failed || selectedRun?.failed || 0} className="text-rose-600" />
              <SummaryPill label={tab === "automation" ? "Flaky" : "Blocked"} value={tab === "automation" ? 0 : counts.blocked} className="text-amber-600" />
              <SummaryPill label="Skipped" value={counts.skipped || selectedRun?.skipped || 0} className="text-slate-500" />
              <SummaryPill label="Total Steps" value={tab === "manual" ? manualSummary.total : selectedResults.length || selectedRun?.total_tests || 0} className="text-blue-600" />
              <SummaryPill label="Not Executed" value={counts.notRun} className="text-slate-500" />
            </div>
          </div>

          {tab === "ai" && (
            <div className="xl:col-span-4">
              <TraceabilityChain
                items={traceabilityItems({
                  testCase: linkedDefects[0]?.test_case_id ? testCaseById.get(linkedDefects[0].test_case_id) : selectedTestCase,
                  run: selectedRun,
                  result: selectedResults.find((result) => result.id === linkedDefects[0]?.execution_result_id),
                  defect: linkedDefects[0],
                })}
              />
            </div>
          )}

          <div className="rounded-lg border border-slate-200 p-3 xl:col-span-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-bold text-slate-800">Linked Defects</p>
              <Badge variant={linkedDefects.length ? "destructive" : "secondary"} className="text-[10px]">{linkedDefects.length}</Badge>
            </div>
            {linkedDefects.length ? (
              linkedDefects.slice(0, 3).map((defect) => (
                <div key={defect.id} className="mb-2 rounded-lg bg-rose-50 px-3 py-2">
                  <p className="font-mono text-[11px] font-bold text-rose-600">{defect.defect_id}</p>
                  <p className="truncate text-[11px] font-semibold text-slate-700">{defect.summary}</p>
                  <JiraDefectActions
                    defect={defect}
                    link={jiraLinkForDefect(defect, jiraDefectLinks)}
                    busy={jiraBusyId === defect.id}
                    onApprove={onApproveDefect}
                    onPush={onPushDefectToJira}
                    onLinkExisting={onLinkExistingJira}
                  />
                  <TraceabilityChain
                    items={traceabilityItems({
                      testCase: defect.test_case_id ? testCaseById.get(defect.test_case_id) : undefined,
                      run: selectedRun,
                      result: selectedResults.find((result) => result.id === defect.execution_result_id),
                      defect,
                    })}
                  />
                </div>
              ))
            ) : (
              <p className="text-[11px] font-medium text-slate-400">No defect draft linked to the selected run results.</p>
            )}
          </div>

          <div className="rounded-lg border border-slate-200 p-3 xl:col-span-4">
            <p className="mb-2 text-xs font-bold text-slate-800">{tab === "automation" ? "Evidence and Artifacts" : "Evidence and Logs"}</p>
            <div className="grid grid-cols-2 gap-2 lg:grid-cols-4 xl:grid-cols-5">
              {["Screenshots", "Logs", "Trace", "Video"].map((label) => (
                <div key={label} className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-[11px] font-bold text-slate-600">
                  {label}
                  <span className="ml-1 text-slate-400">
                    {label === "Screenshots" ? automationArtifactCount(selectedResults, "screenshots") :
                      label === "Video" ? automationArtifactCount(selectedResults, "video") :
                        label === "Logs" ? automationArtifactCount(selectedResults, "logs") :
                          automationArtifactCount(selectedResults, "trace")}
                  </span>
                </div>
              ))}
              {tab === "automation" && (
                <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-[11px] font-bold text-slate-600">
                  Report
                  <span className="ml-1 text-slate-400">{automationArtifactCount(selectedResults, "report")}</span>
                </div>
              )}
            </div>
          </div>

          {tab === "automation" && (
            <div className="rounded-lg border border-slate-200 p-3 xl:col-span-4">
              <p className="mb-2 text-xs font-bold text-slate-800">Failure Details</p>
              {automationFailure ? (
                <div className="space-y-2 text-[11px] font-semibold text-slate-600">
                  <StreamRow label="Failing Step" value={automationFailure.step} />
                  <StreamRow label="Failure Message" value={automationFailure.message} />
                  <StreamRow label="Root Cause Type" value={automationFailure.rootCause} />
                  <StreamRow label="Confidence" value={automationFailure.confidence ? formatPercent(automationFailure.confidence) : "Needs analysis"} />
                </div>
              ) : (
                <p className="text-[11px] font-medium text-slate-400">No failed automation result is available for analysis.</p>
              )}
            </div>
          )}

          {tab === "ai" && aiState && (
            <>
              <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 xl:col-span-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-bold text-violet-900">Confidence Score</p>
                    <p className="mt-1 text-[11px] font-semibold text-violet-700">
                      {aiState.confidence ? "Based on available test steps, selector hints, and execution context." : "Generate an AI execution plan to calculate confidence."}
                    </p>
                  </div>
                  <p className="text-2xl font-bold text-violet-700">{formatPercent(aiState.confidence)}</p>
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 p-3 xl:col-span-4">
                <p className="mb-2 text-xs font-bold text-slate-800">Root Cause Analysis</p>
                <div className="flex flex-wrap gap-2">
                  {["Product Bug", "Automation Issue", "Data Issue", "Environment Issue"].map((label) => (
                    <Badge key={label} variant={label === "Product Bug" && aiFailure ? "destructive" : "outline"} className="text-[10px]">
                      {label}
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 p-3 xl:col-span-4">
                <p className="mb-2 text-xs font-bold text-slate-800">Self-Heal Suggestion</p>
                {aiState.selfHealSuggestion ? (
                  <div className="space-y-2 text-[11px] font-semibold text-slate-600">
                    <StreamRow label="Old Selector" value={aiState.selfHealSuggestion.oldSelector} />
                    <StreamRow label="Suggested Selector" value={aiState.selfHealSuggestion.suggestedSelector} />
                    <StreamRow label="Confidence" value={formatPercent(aiState.selfHealSuggestion.confidence)} />
                  </div>
                ) : (
                  <p className="text-[11px] font-medium text-slate-400">No self-heal suggestion until plan generation or failure analysis.</p>
                )}
              </div>

              <div className="rounded-lg border border-slate-200 p-3 xl:col-span-4">
                <p className="mb-2 text-xs font-bold text-slate-800">Expected vs Actual</p>
                <div className="grid gap-2 text-[11px] font-semibold text-slate-600">
                  <div className="rounded-lg bg-slate-50 p-2">
                    <p className="text-slate-400 font-bold uppercase text-[9px]">Expected</p>
                    <p>{selectedManualTestCase?.expected_result || aiState.validations[0] || "Expected outcome comes from the linked test case."}</p>
                  </div>
                  <div className="rounded-lg bg-slate-50 p-2">
                    <p className="text-slate-400 font-bold uppercase text-[9px]">Actual</p>
                    <p>{aiFailure?.message || "No observed failure result available yet."}</p>
                  </div>
                </div>
              </div>

              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 xl:col-span-4">
                <p className="text-xs font-bold text-amber-800">Risk / Limitation</p>
                <p className="mt-1 text-[11px] font-medium leading-relaxed text-amber-700">
                  {(aiState.risks[0]) || "AI suggestions require human review before applying changes or creating defects."}
                </p>
              </div>

              <div className="rounded-lg border border-slate-200 p-3 xl:col-span-4">
                <p className="mb-2 text-xs font-bold text-slate-800">Activity Timeline</p>
                <div className="space-y-2">
                  {(aiState.observations.length ? aiState.observations.slice(0, 4) : ["No AI activity captured yet."]).map((event, index) => (
                    <div key={`${event}-${index}`} className="rounded-lg bg-slate-50 px-3 py-2">
                      <p className="text-[11px] font-bold text-slate-700">{event}</p>
                      <p className="text-[10px] font-medium text-slate-400">{dateLabel(aiState.lastUpdated || selectedRun?.updated_at)}</p>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {tab === "manual" && (
            <div className="rounded-lg border border-slate-200 p-3 xl:col-span-4">
              <p className="mb-2 text-xs font-bold text-slate-800">Activity Timeline</p>
              {panelActivity.length ? (
                <div className="space-y-2">
                  {panelActivity.map((event) => (
                    <div key={event.id} className="rounded-lg bg-slate-50 px-3 py-2">
                      <p className="text-[11px] font-bold text-slate-700">{event.message}</p>
                      <p className="text-[10px] font-medium text-slate-400">{dateLabel(event.timestamp)}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] font-medium text-slate-400">No manual activity captured yet.</p>
              )}
            </div>
          )}

          {tab === "automation" && (
            <div className="rounded-lg border border-slate-200 p-3 xl:col-span-4">
              <p className="mb-2 text-xs font-bold text-slate-800">Activity Timeline</p>
              {automationState?.recentActions.length ? (
                <div className="space-y-2">
                  {automationState.recentActions.slice(0, 4).map((event, index) => (
                    <div key={`${event}-${index}`} className="rounded-lg bg-slate-50 px-3 py-2">
                      <p className="text-[11px] font-bold text-slate-700">{event}</p>
                      <p className="text-[10px] font-medium text-slate-400">{dateLabel(automationState.lastUpdated || selectedRun?.updated_at)}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] font-medium text-slate-400">No automation activity captured yet.</p>
              )}
            </div>
          )}
        </div>
      )}

      {detailTab === "decisions" && (
        <div className="p-4 space-y-4">
          <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-3 text-[11px] font-semibold text-blue-800 leading-normal">
            <strong>PRINCIPLE-05 Compliance Gate:</strong> All failed test execution runs require a documented decision verdict before release readiness reporting can be approved.
          </div>
          {failedResults.length === 0 ? (
            <div className="py-12 text-center text-xs font-semibold text-slate-400 bg-slate-50/50 rounded-lg border border-dashed border-slate-200">
              <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-500 mb-2" />
              No failed test results in this run. Release clearance is green!
            </div>
          ) : (
            <div className="space-y-4 max-h-[460px] overflow-y-auto pr-1">
              {failedResults.map((result) => {
                const decision = failureDecisions[result.id];
                const testCase = result.test_case_id ? testCaseById.get(result.test_case_id) : undefined;
                const activeDec = formDecisionStates[result.id]?.decision ?? "defect";
                return (
                  <div key={result.id} className={cn(
                    "rounded-lg border p-4 shadow-sm transition",
                    decision ? "border-slate-200 bg-white" : "border-rose-100 bg-rose-50/10"
                  )}>
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <span className="font-mono text-xs font-bold text-blue-600">
                          {testCase?.test_case_id || result.external_test_case_id || `Result ${result.id}`}
                        </span>
                        <h4 className="text-xs font-bold text-slate-800 mt-0.5">{result.test_name}</h4>
                      </div>
                      {decision ? (
                        <Badge
                          variant={
                            decision.decision === "defect" ? "destructive" :
                            decision.decision === "waived" ? "success" :
                            decision.decision === "known_issue" ? "warning" : "info"
                          }
                          className="text-[9px] uppercase font-bold"
                        >
                          {decision.decision === "defect" ? "Defect Drafted" :
                           decision.decision === "waived" ? "Waived" :
                           decision.decision === "known_issue" ? "Known Issue" : "Linked Issue"}
                        </Badge>
                      ) : (
                        <Badge variant="destructive" className="text-[9px] font-bold animate-pulse">
                          Verdit Required
                        </Badge>
                      )}
                    </div>

                    <div className="mt-2.5 rounded bg-slate-900 p-2.5 font-mono text-[10px] leading-normal text-rose-300 overflow-x-auto max-h-24">
                      <p className="font-bold text-slate-400">Error Output:</p>
                      <p className="break-all">{result.error_message || "AssertionError: Expected status code 200, got 500"}</p>
                    </div>

                    {decision ? (
                      <div className="mt-3 border-t border-slate-100 pt-3 text-[11px] font-semibold text-slate-500">
                        <div className="grid gap-1 sm:grid-cols-2">
                          {decision.jiraKey && (
                            <p>
                              <span className="font-bold text-slate-400">Jira key / Ref:</span>{" "}
                              <span className="font-mono font-bold text-slate-700 bg-slate-100 px-1.5 py-0.5 rounded">{decision.jiraKey}</span>
                            </p>
                          )}
                          <p>
                            <span className="font-bold text-slate-400">Decision On:</span>{" "}
                            {dateLabel(decision.timestamp)}
                          </p>
                        </div>
                        {decision.comment && (
                          <div className="mt-2 rounded bg-slate-50 p-2 text-slate-700 text-[10px]">
                            <span className="font-bold text-slate-400 block mb-0.5 text-[8px] uppercase tracking-wider">Comment Notes</span>
                            {decision.comment}
                          </div>
                        )}
                        <Button
                          size="sm"
                          variant="outline"
                          className="mt-3 h-7 border-slate-200 bg-white text-[10px] font-bold"
                          onClick={() => onClearFailureDecision(result.id)}
                        >
                          Change Decision
                        </Button>
                      </div>
                    ) : (
                      <div className="mt-3 border-t border-slate-100 pt-2.5">
                        <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Log Compliance Decision</p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {(["defect", "linked", "known_issue", "waived"] as const).map((opt) => (
                            <button
                              key={opt}
                              type="button"
                              onClick={() => {
                                setFormDecisionStates(prev => ({
                                  ...prev,
                                  [result.id]: {
                                    ...prev[result.id],
                                    decision: opt
                                  }
                                }));
                              }}
                              className={cn(
                                "rounded-md border px-2.5 py-1 text-xs font-bold transition",
                                activeDec === opt
                                  ? "border-blue-600 bg-blue-50 text-blue-700"
                                  : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
                              )}
                            >
                              {opt === "defect" ? "Create Defect" :
                               opt === "linked" ? "Link Existing" :
                               opt === "known_issue" ? "Known Issue" : "Waive"}
                            </button>
                          ))}
                        </div>

                        <div className="mt-3 grid gap-3 sm:grid-cols-2">
                          <div>
                            <span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
                              {activeDec === "defect" ? "Summary Tag Prefix" : "Jira / Reference Issue Key"}
                            </span>
                            <input
                              type="text"
                              value={formDecisionStates[result.id]?.jiraKey ?? ""}
                              onChange={(e) => setFormDecisionStates(prev => ({
                                ...prev,
                                [result.id]: {
                                  ...prev[result.id],
                                  jiraKey: e.target.value
                                }
                              }))}
                              placeholder={
                                activeDec === "defect"
                                  ? "e.g. BUG (creates defect draft)"
                                  : "e.g. BSS-1847 or release bug key"
                              }
                              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs outline-none focus:ring-2 focus:ring-blue-100 font-semibold text-slate-700"
                            />
                          </div>
                          <div>
                            <span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Justification Comment</span>
                            <input
                              type="text"
                              value={formDecisionStates[result.id]?.comment ?? ""}
                              onChange={(e) => setFormDecisionStates(prev => ({
                                ...prev,
                                [result.id]: {
                                  ...prev[result.id],
                                  comment: e.target.value
                                }
                              }))}
                              placeholder="Explanation notes..."
                              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs outline-none focus:ring-2 focus:ring-blue-100 font-semibold text-slate-700"
                            />
                          </div>
                        </div>

                        <div className="mt-3 flex items-center justify-between gap-4">
                          <p className="text-[10px] font-semibold text-slate-400">
                            {activeDec === "waived" ? "⚠ requires QA manager approval" : activeDec === "defect" ? "✓ Will draft a local Defect Draft" : "✓ Links to existing ticket"}
                          </p>
                          <Button
                            size="sm"
                            className="h-7 text-xs font-bold bg-blue-600 text-white hover:bg-blue-700"
                            onClick={() => {
                              const sDec = formDecisionStates[result.id]?.decision ?? "defect";
                              const sKey = formDecisionStates[result.id]?.jiraKey ?? "";
                              const sComment = formDecisionStates[result.id]?.comment ?? "";
                              onSaveFailureDecision(result.id, sDec, sKey, sComment);
                              if (sDec === "defect") {
                                onCreateManualDefect(result, 1);
                              }
                            }}
                          >
                            Save Decision
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {detailTab === "evidence" && (
        <div className="p-4 space-y-4">
          <div className="rounded-lg border border-slate-200 p-3 bg-white">
            <h4 className="text-xs font-bold text-slate-800 mb-2">Screenshot Attachments</h4>
            {selectedResults.some((r) => r.screenshot_url || (r as any).screenshot_path) ? (
              <div className="grid gap-2 grid-cols-2">
                {selectedResults.filter((r) => r.screenshot_url || (r as any).screenshot_path).map((r) => (
                  <div key={r.id} className="overflow-hidden rounded border border-slate-100 bg-slate-50 p-2">
                    <div className="aspect-[16/10] bg-slate-200 rounded flex items-center justify-center font-bold text-slate-400 text-[10px]">
                      [Screen: {r.test_case_id ? `TC-${r.test_case_id}` : "Test"}]
                    </div>
                    <p className="mt-1 truncate font-mono text-[9px] text-slate-500">{(r as any).screenshot_path || r.screenshot_url || "screenshot.png"}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[11px] font-medium text-slate-400 bg-slate-50/50 p-4 rounded text-center">No visual screenshots captured in this execution run.</p>
            )}
          </div>

          <div className="rounded-lg border border-slate-200 p-3 bg-white">
            <h4 className="text-xs font-bold text-slate-800 mb-2">Logs & Trace Logs</h4>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {selectedResults.map((r) => (
                <div key={r.id} className="p-2 border border-slate-100 bg-slate-50 rounded text-[10px]">
                  <p className="font-bold text-slate-700 truncate">{r.test_name}</p>
                  <div className="flex flex-wrap gap-2 mt-1.5">
                    {r.log_url && <a href={r.log_url} target="_blank" rel="noreferrer" className="font-bold text-blue-600 bg-white border border-blue-100 px-1.5 py-0.5 rounded hover:bg-blue-50">View logs ↗</a>}
                    {((r as any).trace_path || r.raw_result_json?.trace) && (
                      <span className="font-mono text-slate-400 bg-white border border-slate-100 px-1.5 py-0.5 rounded">
                        Trace: {((r as any).trace_path as string) || (r.raw_result_json?.trace as string) || "trace.json"}
                      </span>
                    )}
                    {r.video_url && <a href={r.video_url} target="_blank" rel="noreferrer" className="font-bold text-[#7c3aed] bg-white border border-violet-100 px-1.5 py-0.5 rounded hover:bg-violet-50">Watch Video ↗</a>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {detailTab === "logs" && (
        <div className="p-4">
          <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 shadow-inner">
            <div className="flex items-center justify-between border-b border-slate-900 pb-1.5 mb-2">
              <span className="text-[10px] font-bold text-slate-500 font-mono">STLC_EXECUTION_AGENT_LOGS</span>
            </div>
            {selectedRun.execution_logs && Array.isArray(selectedRun.execution_logs) && selectedRun.execution_logs.length > 0 ? (
              <pre className="font-mono text-[9px] leading-relaxed text-slate-300 overflow-auto max-h-[380px] pr-1">
                {selectedRun.execution_logs.map((log: any, idx) => (
                  <div key={idx} className="border-b border-slate-900/50 py-0.5 hover:bg-slate-900/50">
                    <span className="text-emerald-500">[{new Date(selectedRun.created_at).toLocaleTimeString()}]</span>{" "}
                    {typeof log === "string" ? log : JSON.stringify(log)}
                  </div>
                ))}
              </pre>
            ) : (
              <div className="font-mono text-[10px] text-slate-500 py-6 text-center">
                No telemetry execution agent logs found.
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}

function SummaryPill({ label, value, className }: { label: string; value: number | string; className?: string }) {
  return (
    <div className="rounded-lg bg-slate-50 p-2">
      <p className={cn("text-base font-bold", className)}>{typeof value === "number" ? formatNumber(value) : value}</p>
      <p className="text-[10px] font-semibold text-slate-400">{label}</p>
    </div>
  );
}

function ResultsTable({
  tab,
  selectedResults,
  selectedTestCase,
  testCaseById,
  selectedManualResultId,
  manualStepStates,
  selectedRun,
  aiWorkspaceStates,
  defects,
  jiraDefectLinks,
  jiraBusyId,
  onApproveDefect,
  onPushDefectToJira,
  onLinkExistingJira,
}: {
  tab: ExecutionTab;
  selectedResults: ExecutionResult[];
  selectedTestCase?: TestCase;
  testCaseById: Map<number, TestCase>;
  selectedManualResultId: number | null;
  manualStepStates: Record<string, ManualStepState>;
  selectedRun?: ExecutionRun;
  aiWorkspaceStates: Record<string, AiWorkspaceState>;
  defects: DefectDraft[];
  jiraDefectLinks: Record<number, JiraDefectLink>;
  jiraBusyId: number | null;
  onApproveDefect: (defect: DefectDraft) => void;
  onPushDefectToJira: (defect: DefectDraft) => void;
  onLinkExistingJira: (defect: DefectDraft) => void;
}) {
  const manualResult = selectedResults.find((result) => result.id === selectedManualResultId) || selectedResults[0];
  const manualTestCase = manualResult?.test_case_id ? testCaseById.get(manualResult.test_case_id) : undefined;
  const manualSteps = stepList(manualTestCase);
  const aiState = tab === "ai" && selectedRun ? aiWorkspaceStateFor(selectedRun, aiWorkspaceStates[aiStateKey(selectedRun.id)]) : null;
  const selectedResultIds = new Set(selectedResults.map((result) => result.id));
  const selectedTestCaseIds = new Set([
    ...selectedResults.map((result) => result.test_case_id).filter(Boolean),
    selectedTestCase?.id,
  ].filter(Boolean) as number[]);
  const aiDraftDefect = tab === "ai"
    ? defects.find((defect) => (
        (defect.execution_result_id && selectedResultIds.has(defect.execution_result_id)) ||
        (defect.test_case_id && selectedTestCaseIds.has(defect.test_case_id))
      ))
    : undefined;

  if (tab === "automation") {
    return (
      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-2 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900">Test Case Execution Details</h3>
            <p className="text-[11px] font-medium text-slate-400">Automation result details from existing execution data and script metadata.</p>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" className="h-8 border-slate-200 text-xs" disabled><Filter className="h-3.5 w-3.5" /> Filter</Button>
            <Button size="sm" variant="outline" className="h-8 border-slate-200 text-xs" disabled>Export</Button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[1180px] text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-4 py-3">Test Case ID</th>
                <th className="px-4 py-3">Mapped To Script Path</th>
                <th className="px-4 py-3">Expected Result</th>
                <th className="px-4 py-3">Actual Result</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Duration</th>
                <th className="px-4 py-3">Retry</th>
                <th className="px-4 py-3">Last Result</th>
                <th className="px-4 py-3">Executed At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {selectedResults.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-xs font-semibold text-slate-400">
                    Select an automation run with results to view test case execution details.
                  </td>
                </tr>
              ) : (
                selectedResults.map((result) => {
                  const testCase = result.test_case_id ? testCaseById.get(result.test_case_id) : undefined;
                  const status = result.automation_execution_status || result.status;
                  const retryCount = typeof result.raw_result_json?.retry === "number" ? result.raw_result_json.retry : 0;
                  const lastResult = typeof result.raw_result_json?.last_result === "string" ? result.raw_result_json.last_result : status;
                  return (
                    <tr key={result.id} className="hover:bg-slate-50/70">
                      <td className="px-4 py-3 font-mono text-[11px] font-bold text-blue-600">{testCase?.test_case_id || result.external_test_case_id || "-"}</td>
                      <td className="max-w-[280px] px-4 py-3 font-mono text-[10px] text-slate-500">{scriptPathForResult(result, testCase)}</td>
                      <td className="max-w-[260px] px-4 py-3 text-slate-500">{testCase?.expected_result || "Expected result is maintained on the linked test case."}</td>
                      <td className="max-w-[260px] px-4 py-3 text-slate-500">{result.error_message || (typeof result.raw_result_json?.actual_result === "string" ? result.raw_result_json.actual_result : "-")}</td>
                      <td className="px-4 py-3">
                        <Badge variant={statusVariant(status)} className="text-[10px]">{normalizeStatus(status)}</Badge>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{result.duration_seconds ? `${result.duration_seconds}s` : result.duration_ms ? `${Math.round(result.duration_ms / 1000)}s` : "-"}</td>
                      <td className="px-4 py-3 text-slate-500">{retryCount}</td>
                      <td className="px-4 py-3">
                        <Badge variant={statusVariant(lastResult)} className="text-[10px]">{normalizeStatus(lastResult)}</Badge>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{dateLabel(result.updated_at || result.created_at)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    );
  }

  return (
    <>
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-col gap-2 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-sm font-bold text-slate-900">
            Step-Level Execution
          </h3>
          <p className="text-[11px] font-medium text-slate-400">
            {tab === "manual" ? "Interactive local step execution state for the selected manual test case." : "Read-only AI execution result view backed by existing execution results."}
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="h-8 border-slate-200 text-xs" disabled><Filter className="h-3.5 w-3.5" /> Filter</Button>
          <Button size="sm" variant="outline" className="h-8 border-slate-200 text-xs" disabled>Export</Button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-3">Test Case ID</th>
              <th className="px-4 py-3">Name / Step</th>
              <th className="px-4 py-3">Expected Result</th>
              <th className="px-4 py-3">Actual Result</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Evidence</th>
              <th className="px-4 py-3">Executed At</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {tab === "manual" ? (
              !manualResult || manualSteps.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-xs font-semibold text-slate-400">
                    Select a manual test case with structured steps to view step-level execution.
                  </td>
                </tr>
              ) : (
                manualSteps.map((step) => {
                  const state = getManualStepState(manualStepStates, manualResult.id, step.step_number);
                  return (
                    <tr key={`${manualResult.id}-${step.step_number}`} className="hover:bg-slate-50/70">
                      <td className="px-4 py-3 font-mono text-[11px] font-bold text-blue-600">{manualTestCase?.test_case_id || `Result ${manualResult.id}`}</td>
                      <td className="max-w-[260px] px-4 py-3">
                        <p className="truncate font-bold text-slate-800">Step {step.step_number}</p>
                        <p className="truncate text-[10px] font-medium text-slate-400">{step.action}</p>
                      </td>
                      <td className="max-w-[260px] px-4 py-3 text-slate-500">{step.expected_result}</td>
                      <td className="max-w-[260px] px-4 py-3 text-slate-500">{state.actualResult || "-"}</td>
                      <td className="px-4 py-3">
                        <Badge variant={statusVariant(state.status)} className="text-[10px]">{normalizeStatus(state.status)}</Badge>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{state.evidence.length ? state.evidence.join(", ") : "-"}</td>
                      <td className="px-4 py-3 text-slate-500">{dateLabel(state.updatedAt)}</td>
                    </tr>
                  );
                })
              )
            ) : selectedResults.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-xs font-semibold text-slate-400">
                  Select a run with results to view execution detail rows.
                </td>
              </tr>
            ) : (
              selectedResults.map((result) => {
                const testCase = result.test_case_id ? testCaseById.get(result.test_case_id) : undefined;
                return (
                  <tr key={result.id} className="hover:bg-slate-50/70">
                    <td className="px-4 py-3 font-mono text-[11px] font-bold text-blue-600">{testCase?.test_case_id || result.external_test_case_id || "-"}</td>
                    <td className="max-w-[260px] px-4 py-3">
                      <p className="truncate font-bold text-slate-800">{result.test_name}</p>
                      <p className="truncate text-[10px] font-medium text-slate-400">{modeLabelForResult(tab, result)}</p>
                    </td>
                    <td className="max-w-[260px] px-4 py-3 text-slate-500">{testCase?.expected_result || "Derived from test case steps"}</td>
                    <td className="max-w-[260px] px-4 py-3 text-slate-500">{result.error_message || result.raw_result_json?.actual_result as string || "-"}</td>
                    <td className="px-4 py-3">
                      <Badge variant={statusVariant(result.status)} className="text-[10px]">{normalizeStatus(result.status)}</Badge>
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {result.screenshot_url || result.video_url || result.log_url || result.external_result_url ? "Available" : "-"}
                    </td>
                    <td className="px-4 py-3 text-slate-500">{dateLabel(result.created_at)}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
    {tab === "ai" && aiState?.defectDraft && (
      <section className="rounded-lg border border-rose-200 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Bug className="h-4 w-4 text-rose-600" />
              <h3 className="text-sm font-bold text-slate-900">Defect Draft</h3>
            </div>
            <p className="mt-1 text-[11px] font-medium text-slate-400">AI-generated draft. Human approval is required before Jira creation.</p>
          </div>
          {aiDraftDefect ? (
            <JiraDefectActions
              defect={aiDraftDefect}
              link={jiraLinkForDefect(aiDraftDefect, jiraDefectLinks)}
              busy={jiraBusyId === aiDraftDefect.id}
              onApprove={onApproveDefect}
              onPush={onPushDefectToJira}
              onLinkExisting={onLinkExistingJira}
            />
          ) : (
            <Button size="sm" variant="outline" className="h-8 border-slate-200 bg-white text-xs" disabled>
              View in Jira
            </Button>
          )}
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <MetaTile label="Draft Title" value={aiState.defectDraft.title} />
          <MetaTile label="Severity" value={aiState.defectDraft.severity} />
          <MetaTile label="Priority" value={aiState.defectDraft.priority} />
          <MetaTile label="Status" value={aiState.defectDraft.status} />
        </div>
        <p className="mt-3 rounded-lg bg-rose-50 p-3 text-xs font-semibold leading-relaxed text-rose-800">
          {aiState.defectDraft.description}
        </p>
        <TraceabilityChain
          items={traceabilityItems({
            testCase: aiDraftDefect?.test_case_id ? testCaseById.get(aiDraftDefect.test_case_id) : selectedTestCase,
            run: selectedRun,
            result: selectedResults.find((result) => result.id === aiDraftDefect?.execution_result_id),
            defect: aiDraftDefect,
          })}
        />
      </section>
    )}
    </>
  );
}

function modeLabelForResult(tab: ExecutionTab, result: ExecutionResult) {
  if (tab === "automation") return result.external_test_case_id || result.external_tool_name || "Automation result";
  if (tab === "ai") return "AI-assisted execution result";
  return result.execution_mode || "Manual result";
}

function ExecutionContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const selectedProject = Number(searchParams.get("project")) || null;

  const [projects, setProjects] = useState<Project[]>([]);
  const [runs, setRuns] = useState<ExecutionRun[]>([]);
  const [results, setResults] = useState<ExecutionResult[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [defects, setDefects] = useState<DefectDraft[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<ExecutionTab>("manual");
  const [statusFilter, setStatusFilter] = useState("All");
  const [modeFilter, setModeFilter] = useState("All");
  const [visibleColumns, setVisibleColumns] = useState<ExecutionColumnKey[]>(DEFAULT_EXECUTION_COLUMN_KEYS);
  const [showColumns, setShowColumns] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [loading, setLoading] = useState(false);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedManualResultId, setSelectedManualResultId] = useState<number | null>(null);
  const [currentManualStepIndex, setCurrentManualStepIndex] = useState(0);
  const [manualStepStates, setManualStepStates] = useState<Record<string, ManualStepState>>({});
  const [manualActivity, setManualActivity] = useState<ManualActivity[]>([]);
  const [autoSaveMessage, setAutoSaveMessage] = useState<string | null>(null);
  const [creatingDefectKey, setCreatingDefectKey] = useState<string | null>(null);
  const [automationRunStates, setAutomationRunStates] = useState<Record<string, AutomationRunState>>({});
  const [automationActionRunId, setAutomationActionRunId] = useState<number | null>(null);
  const [aiWorkspaceStates, setAiWorkspaceStates] = useState<Record<string, AiWorkspaceState>>({});
  const [jiraDefectLinks, setJiraDefectLinks] = useState<Record<number, JiraDefectLink>>({});
  const [jiraBusyId, setJiraBusyId] = useState<number | null>(null);
  const [failureDecisions, setFailureDecisions] = useState<Record<number, {
    resultId: number;
    decision: "defect" | "linked" | "known_issue" | "waived";
    jiraKey?: string;
    comment?: string;
    timestamp: string;
  }>>({});

  const handleSaveFailureDecision = useCallback((
    resultId: number,
    decision: "defect" | "linked" | "known_issue" | "waived",
    jiraKey: string,
    comment: string
  ) => {
    const now = new Date().toISOString();
    setFailureDecisions((prev) => ({
      ...prev,
      [resultId]: {
        resultId,
        decision,
        jiraKey,
        comment,
        timestamp: now,
      },
    }));
    setNotice(`Failure decision saved for Result ID ${resultId}.`);
  }, []);

  const handleClearFailureDecision = useCallback((resultId: number) => {
    setFailureDecisions((prev) => {
      const copy = { ...prev };
      delete copy[resultId];
      return copy;
    });
    setNotice(`Failure decision cleared for Result ID ${resultId}.`);
  }, []);

  useEffect(() => {
    projectsApi
      .list()
      .then((response) => {
        setProjects(response.data);
        if (response.data.length > 0 && !searchParams.get("project")) {
          const params = new URLSearchParams(searchParams.toString());
          params.set("project", String(response.data[0].id));
          router.push(`${pathname}?${params.toString()}`);
        }
      })
  }, [pathname, router, searchParams]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(visibleExecutionStorageKey(selectedProject));
    let parsed: unknown = DEFAULT_EXECUTION_COLUMN_KEYS;
    try {
      parsed = saved ? JSON.parse(saved) : DEFAULT_EXECUTION_COLUMN_KEYS;
    } catch {
      parsed = DEFAULT_EXECUTION_COLUMN_KEYS;
    }
    setVisibleColumns(sanitizeExecutionColumns(parsed));
  }, [selectedProject]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(
      visibleExecutionStorageKey(selectedProject),
      JSON.stringify(sanitizeExecutionColumns(visibleColumns))
    );
  }, [selectedProject, visibleColumns]);

  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    setError(null);
    try {
      const [runsRes, casesRes] = await Promise.all([
        executionApi.listRuns(selectedProject),
        testCasesApi.list(selectedProject),
      ]);
      let defectRows: DefectDraft[] = [];
      try {
        defectRows = (await defectsApi.list(selectedProject)).data;
      } catch {
        defectRows = [];
      }

      let localResults: ExecutionResult[] = [];
      let localStepStates: Record<string, ManualStepState> = {};
      let localRuns: ExecutionRun[] = [];
      if (typeof window !== "undefined") {
        try {
          const sr = window.localStorage.getItem(`stlc_results_project_${selectedProject}`);
          if (sr) localResults = JSON.parse(sr);
          const ss = window.localStorage.getItem(`stlc_manual_step_states_project_${selectedProject}`);
          if (ss) localStepStates = JSON.parse(ss);
          const sruns = window.localStorage.getItem(`stlc_runs_project_${selectedProject}`);
          if (sruns) localRuns = JSON.parse(sruns);
        } catch {}
      }

      const backendRuns = runsRes.data;
      const tabs: ExecutionTab[] = ["manual", "automation", "ai"];
      const adapters = tabs
        .filter((tab) => !backendRuns.some((run) => modeForRun(run) === tab))
        .map((tab) => {
          const saved = localRuns.find((r) => modeForRun(r) === tab);
          if (saved) return saved;
          const tabCases = adapterCasesForTab(tab, casesRes.data);
          return createWorkspaceAdapterRun(selectedProject, tab, tabCases);
        });

      const allRuns = [...backendRuns, ...adapters];
      setRuns(allRuns);
      setTestCases(casesRes.data);
      setDefects(defectRows);
      setResults(localResults);
      setManualStepStates(localStepStates);
      setSelectedRunId((current) => current && allRuns.some((run) => run.id === current) ? current : allRuns[0]?.id ?? null);
    } catch (loadError) {
      setError(messageFromError(loadError, "Could not load execution command center data."));
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const catalogRuns = runs;
  const selectedRun = useMemo(() => catalogRuns.find((run) => run.id === selectedRunId), [catalogRuns, selectedRunId]);

  useEffect(() => {
    setSelectedRunId((current) => {
      if (current && catalogRuns.some((run) => run.id === current && runMatchesTab(run, activeTab))) return current;
      return catalogRuns.find((run) => runMatchesTab(run, activeTab))?.id ?? null;
    });
  }, [activeTab, catalogRuns]);

  useEffect(() => {
    if (!selectedRunId) {
      setResults([]);
      return;
    }
    if (selectedRunId < 0) {
      let localResults: ExecutionResult[] = [];
      if (typeof window !== "undefined") {
        try {
          const sr = window.localStorage.getItem(`stlc_results_project_${selectedProject}`);
          if (sr) localResults = JSON.parse(sr);
        } catch {}
      }
      setResults(localResults);
      return;
    }
    setResultsLoading(true);
    executionApi
      .getResults(selectedRunId)
      .then((response) => setResults(response.data))
      .catch((loadError) => setError(messageFromError(loadError, "Could not load execution result details.")))
      .finally(() => setResultsLoading(false));
  }, [selectedRunId, selectedProject]);

  const testCaseById = useMemo(() => new Map(testCases.map((testCase) => [testCase.id, testCase])), [testCases]);

  const visibleRuns = useMemo(() => {
    return catalogRuns.filter((run) => {
      if (!runMatchesTab(run, activeTab)) return false;
      if (statusFilter !== "All" && normalizeStatus(run.status) !== statusFilter) return false;
      if (modeFilter !== "All" && TAB_LABELS[modeForRun(run)].replace(" Execution", "") !== modeFilter) return false;
      return true;
    });
  }, [activeTab, catalogRuns, modeFilter, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(visibleRuns.length / pageSize));
  const pagedRuns = useMemo(() => {
    const safePage = Math.min(Math.max(currentPage, 1), totalPages);
    const start = (safePage - 1) * pageSize;
    return visibleRuns.slice(start, start + pageSize);
  }, [currentPage, pageSize, totalPages, visibleRuns]);

  useEffect(() => {
    setCurrentPage(1);
  }, [activeTab, modeFilter, pageSize, statusFilter]);

  useEffect(() => {
    if (currentPage > totalPages) setCurrentPage(totalPages);
  }, [currentPage, totalPages]);

  const selectedResults = useMemo(() => {
    if (!selectedRun) return [];
    if (selectedRun.id >= 0) {
      return results.filter((result) => result.execution_run_id === selectedRun.id);
    }
    const adapterResults = createWorkspaceAdapterResults(selectedRun, testCases);
    const runResults = results.filter((result) => result.execution_run_id === selectedRun.id);
    return adapterResults.map((adapterRes) => {
      const updated = runResults.find((r) => r.test_case_id === adapterRes.test_case_id);
      return updated || adapterRes;
    });
  }, [results, selectedRun, testCases]);
  const selectedTestCase = useMemo(() => {
    const resultWithCase = selectedResults.find((result) => result.test_case_id);
    if (resultWithCase?.test_case_id) {
      return testCaseById.get(resultWithCase.test_case_id);
    }
    const tabCases = adapterCasesForTab(activeTab, testCases);
    return tabCases[0] || testCases[0];
  }, [selectedResults, testCaseById, testCases, activeTab]);

  useEffect(() => {
    if (activeTab !== "manual") return;
    setSelectedManualResultId((current) => {
      if (current && selectedResults.some((result) => result.id === current)) return current;
      return selectedResults[0]?.id ?? null;
    });
  }, [activeTab, selectedRunId, selectedResults]);

  useEffect(() => {
    setCurrentManualStepIndex(0);
  }, [selectedManualResultId]);

  const resultCounts = useMemo(() => resultStatusCounts(selectedResults, manualStepStates, testCaseById), [selectedResults, manualStepStates, testCaseById]);
  const totalTestCases = testCases.length;
  const planned = testCases.filter((testCase) => ["approved", "automated"].includes((testCase.status || "").toLowerCase())).length;
  const executed = resultCounts.passed + resultCounts.failed + resultCounts.blocked + resultCounts.skipped;
  const automatedCases = testCases.filter(isAutomationCase).length;
  const failedWithDefects = defects.length;

  const undecidedFailuresCount = useMemo(() => {
    return selectedResults.filter(
      (result) =>
        ["failed", "error"].includes((result.status || "").toLowerCase()) &&
        !failureDecisions[result.id]
    ).length;
  }, [selectedResults, failureDecisions]);

  const metrics = [
    {
      title: "Total Test Cases",
      value: formatNumber(totalTestCases),
      helper: "From test case library",
      icon: TestTube2,
      tone: "border-blue-100 bg-blue-50 text-blue-600",
    },
    {
      title: "Planned for Execution",
      value: formatNumber(planned),
      helper: "Approved or automated cases",
      icon: ClipboardList,
      tone: "border-indigo-100 bg-indigo-50 text-indigo-600",
    },
    {
      title: "Executed",
      value: formatNumber(executed),
      helper: "Passed + failed + blocked + skipped",
      icon: Play,
      tone: "border-blue-100 bg-blue-50 text-blue-600",
    },
    {
      title: "Passed",
      value: formatNumber(resultCounts.passed),
      helper: "Execution results",
      icon: CheckCircle2,
      tone: "border-emerald-100 bg-emerald-50 text-emerald-600",
    },
    {
      title: "Failed",
      value: formatNumber(resultCounts.failed),
      helper: "Failed or error results",
      icon: XCircle,
      tone: "border-rose-100 bg-rose-50 text-rose-600",
    },
    {
      title: "Undecided Failures",
      value: formatNumber(undecidedFailuresCount),
      helper: "PRINCIPLE-05 blockers",
      icon: AlertTriangle,
      tone: undecidedFailuresCount > 0 ? "border-amber-100 bg-amber-50 text-amber-600 animate-pulse font-bold" : "border-slate-100 bg-slate-50 text-slate-400",
    },
    {
      title: "Pass Rate",
      value: formatPercent(safePercent(resultCounts.passed, executed)),
      helper: `${formatNumber(resultCounts.passed)} / ${formatNumber(executed)} executed`,
      icon: Gauge,
      tone: "border-emerald-100 bg-emerald-50 text-emerald-600",
      ring: safePercent(resultCounts.passed, executed),
    },
    {
      title: "Automation Coverage",
      value: formatPercent(safePercent(automatedCases, totalTestCases)),
      helper: "Automated or hybrid cases",
      icon: TerminalSquare,
      tone: "border-violet-100 bg-violet-50 text-violet-600",
    },
    {
      title: "AI-Assisted Runs",
      value: formatNumber(runs.filter(isAiAssisted).length),
      helper: "Runs marked with AI source/metadata",
      icon: Bot,
      tone: "border-cyan-100 bg-cyan-50 text-cyan-600",
    },
    {
      title: "Defects Raised",
      value: formatNumber(failedWithDefects),
      helper: "Drafts linked to execution results",
      icon: Bug,
      tone: "border-rose-100 bg-rose-50 text-rose-600",
    },
  ];

  function handleProjectChange(projectId: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("project", projectId);
    router.push(`${pathname}?${params.toString()}`);
  }

  function handleTabChange(tab: ExecutionTab) {
    setActiveTab(tab);
    const firstRun = catalogRuns.find((run) => runMatchesTab(run, tab));
    setSelectedRunId(firstRun?.id ?? null);
  }

  function handleClearFilters() {
    setStatusFilter("All");
    setModeFilter("All");
    setNotice("Execution filters cleared.");
  }

  function handleImportResults() {
    setNotice("Import Results is staged for backend file/API ingestion. No execution data was imported.");
  }

  function handleConfigureExecution() {
    setNotice("Configure Execution is staged for Phase 7 backend configuration. Current settings are read-only.");
  }

  function handleCreateExecutionRun() {
    setNotice("Create Execution Run is ready for backend orchestration. Use existing runs or adapter workspaces until the API is connected.");
  }

  function handleExportReport() {
    const rows = visibleRuns.map((run) => ({
      run_id: run.execution_id,
      run_name: run.suite_name || TAB_LABELS[modeForRun(run)],
      mode: modeLabelForRun(run),
      framework: frameworkForRun(run, results),
      environment: run.environment || "",
      status: normalizeStatus(run.status),
      total_test_cases: run.total_tests || 0,
      passed: run.passed || 0,
      failed: run.failed || 0,
      skipped: run.skipped || 0,
      started_at: dateLabel(run.started_at || run.created_at),
      updated_at: dateLabel(run.updated_at),
    }));
    const header = Object.keys(rows[0] || {
      run_id: "",
      run_name: "",
      mode: "",
      framework: "",
      environment: "",
      status: "",
      total_test_cases: "",
      passed: "",
      failed: "",
      skipped: "",
      started_at: "",
      updated_at: "",
    });
    const csv = [
      header.map(escapeCsvCell).join(","),
      ...rows.map((row) => header.map((key) => escapeCsvCell(row[key as keyof typeof row])).join(",")),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `execution-${activeTab}-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setNotice(`Exported ${formatNumber(rows.length)} ${TAB_LABELS[activeTab].toLowerCase()} row(s).`);
  }

  function pushManualActivity(event: Omit<ManualActivity, "id" | "timestamp">) {
    setManualActivity((previous) => [
      {
        ...event,
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        timestamp: new Date().toISOString(),
      },
      ...previous,
    ].slice(0, 60));
  }

  function projectManualResult(result: ExecutionResult, nextStates: Record<string, ManualStepState>) {
    const testCase = result.test_case_id ? testCaseById.get(result.test_case_id) : undefined;
    const steps = stepList(testCase);
    const summary = manualSummaryFor(nextStates, result.id, steps);
    const status = manualResultStatus(summary);

    const updatedResult = {
      ...result,
      status,
      manual_execution_status: status,
      updated_at: new Date().toISOString(),
    };

    setResults((previous) => {
      const next = previous.some((row) => row.id === result.id)
        ? previous.map((row) => (row.id === result.id ? updatedResult : row))
        : [...previous, updatedResult];
      if (typeof window !== "undefined") {
        window.localStorage.setItem(`stlc_results_project_${selectedProject}`, JSON.stringify(next));
      }
      return next;
    });

    if (!selectedRun) return;
    setRuns((previous) => {
      const next = previous.map((run) => {
        if (run.id !== selectedRun.id) return run;
        const runResults = results.some((row) => row.id === result.id)
          ? results.map((row) => (row.id === result.id ? updatedResult : row))
          : [...results, updatedResult];
        const counts = resultStatusCounts(runResults, nextStates, testCaseById);
        const runExecuted = counts.passed + counts.failed + counts.blocked + counts.skipped;
        return {
          ...run,
          passed: counts.passed,
          failed: counts.failed,
          skipped: counts.skipped,
          status: counts.failed > 0 ? "failed" : runExecuted > 0 && runExecuted < Math.max(run.total_tests, runResults.length) ? "in_progress" : runExecuted > 0 ? "completed" : run.status,
          updated_at: new Date().toISOString(),
        };
      });
      if (typeof window !== "undefined") {
        const adapterRuns = next.filter((r) => r.id < 0);
        window.localStorage.setItem(`stlc_runs_project_${selectedProject}`, JSON.stringify(adapterRuns));
      }
      return next;
    });
  }

  function handleSelectManualResult(resultId: number) {
    setSelectedManualResultId(resultId);
    setCurrentManualStepIndex(0);
  }

  function handleUpdateManualStep(result: ExecutionResult, stepNumber: number, patch: Partial<ManualStepState>, message?: string) {
    const key = manualStepKey(result.id, stepNumber);
    const now = new Date().toISOString();
    setManualStepStates((previous) => {
      const existing = previous[key] || blankManualStep();
      const nextState: ManualStepState = {
        ...existing,
        ...patch,
        evidence: patch.evidence || existing.evidence,
        updatedAt: now,
      };
      const next = { ...previous, [key]: nextState };
      if (typeof window !== "undefined") {
        window.localStorage.setItem(`stlc_manual_step_states_project_${selectedProject}`, JSON.stringify(next));
      }
      projectManualResult(result, next);
      return next;
    });
    setAutoSaveMessage(`Auto-saved ${dateLabel(now)}`);
    if (message) {
      pushManualActivity({
        resultId: result.id,
        stepNumber,
        message,
        tone: patch.status === "passed" ? "success" : patch.status === "failed" ? "danger" : patch.status === "blocked" ? "warning" : "info",
      });
    }
  }

  function handleAttachManualEvidence(result: ExecutionResult, stepNumber: number, label: string) {
    const key = manualStepKey(result.id, stepNumber);
    const existing = manualStepStates[key] || blankManualStep();
    const evidence = Array.from(new Set([...existing.evidence, label]));
    handleUpdateManualStep(result, stepNumber, { evidence }, `Evidence attached for Step ${stepNumber}: ${label}`);
  }

  function handleSaveManualNext(result: ExecutionResult, steps: ReturnType<typeof stepList>) {
    const currentStep = steps[currentManualStepIndex];
    if (currentStep) {
      handleUpdateManualStep(result, currentStep.step_number, {}, `Step ${currentStep.step_number} saved`);
    }
    setCurrentManualStepIndex((current) => Math.min(current + 1, Math.max(steps.length - 1, 0)));
  }

  function handleMarkManualComplete(result: ExecutionResult, steps: ReturnType<typeof stepList>) {
    const nextStates = { ...manualStepStates };
    const now = new Date().toISOString();
    steps.forEach((step) => {
      const key = manualStepKey(result.id, step.step_number);
      const existing = nextStates[key] || blankManualStep();
      if (existing.status === "not_run" || existing.status === "in_progress") {
        nextStates[key] = { ...existing, status: "skipped", updatedAt: now };
      }
    });
    setManualStepStates(nextStates);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(`stlc_manual_step_states_project_${selectedProject}`, JSON.stringify(nextStates));
    }
    projectManualResult(result, nextStates);
    setAutoSaveMessage(`Marked complete ${dateLabel(now)}`);
    pushManualActivity({
      resultId: result.id,
      message: "Manual test case marked complete",
      tone: "success",
    });
  }

  async function handleApproveDefect(defect: DefectDraft) {
    setJiraBusyId(defect.id);
    setError(null);
    try {
      const response = await defectsApi.approve(defect.id, "approve", "Approved from Execution traceability workspace.");
      setDefects((previous) => previous.map((row) => row.id === defect.id ? response.data : row));
    } catch (approveError) {
      setError(messageFromError(approveError, "Could not approve defect draft for Jira push."));
    } finally {
      setJiraBusyId(null);
    }
  }

  async function handlePushDefectToJira(defect: DefectDraft) {
    setJiraBusyId(defect.id);
    setError(null);
    try {
      const response = await defectsApi.pushToJira(defect.id);
      setJiraDefectLinks((previous) => ({
        ...previous,
        [defect.id]: response.data,
      }));
      setDefects((previous) => previous.map((row) => (
        row.id === defect.id
          ? { ...row, status: "pushed_to_jira", jira_ready: true, updated_at: new Date().toISOString() }
          : row
      )));
    } catch (pushError) {
      setError(messageFromError(pushError, "Could not push defect to Jira. Ensure the draft is approved and Jira permissions are configured."));
    } finally {
      setJiraBusyId(null);
    }
  }

  function handleLinkExistingJira(defect: DefectDraft) {
    const key = window.prompt("Enter existing Jira issue key to link, for example BUG-1234");
    if (!key?.trim()) return;
    const normalizedKey = key.trim().toUpperCase();
    const now = new Date().toISOString();
    setJiraDefectLinks((previous) => ({
      ...previous,
      [defect.id]: {
        defect_draft_id: defect.id,
        project_id: defect.project_id,
        jira_issue_key: normalizedKey,
        jira_url: jiraUrlForKey(normalizedKey),
        jira_status: "Linked",
        status: "linked_existing",
        created_at: now,
        updated_at: now,
      },
    }));
  }

  async function handleCreateManualDefect(result: ExecutionResult, stepNumber: number) {
    if (!selectedProject) return;
    const key = manualStepKey(result.id, stepNumber);
    const state = manualStepStates[key] || blankManualStep();
    const testCase = result.test_case_id ? testCaseById.get(result.test_case_id) : undefined;
    const step = stepList(testCase).find((item) => item.step_number === stepNumber);
    setCreatingDefectKey(key);
    setError(null);
    try {
      const response = await defectsApi.create({
        project_id: selectedProject,
        test_case_id: result.test_case_id || undefined,
        execution_result_id: persistedExecutionResultId(result),
        summary: `Manual Step Failure: ${testCase?.test_case_id || result.test_name} - Step ${stepNumber}`,
        description: [
          `Manual execution defect draft created from ${selectedRun?.execution_id || "selected run"}.`,
          `Step: ${step?.action || `Step ${stepNumber}`}`,
          `Expected: ${step?.expected_result || testCase?.expected_result || "-"}`,
          `Actual: ${state.actualResult || "-"}`,
          `Comments: ${state.comments || "-"}`,
        ].join("\n\n"),
        expected_result: step?.expected_result || testCase?.expected_result,
        actual_result: state.actualResult || state.comments || "Manual tester marked this step as failed.",
        severity: "Medium",
        priority: "P3",
        classification: "product_defect",
      });
      setDefects((previous) => [response.data, ...previous]);
      handleUpdateManualStep(result, stepNumber, { comments: state.comments ? `${state.comments}\nLinked defect draft: ${response.data.defect_id}` : `Linked defect draft: ${response.data.defect_id}` });
      pushManualActivity({
        resultId: result.id,
        stepNumber,
        message: `Defect draft ${response.data.defect_id} created for Step ${stepNumber}`,
        tone: "danger",
      });
    } catch (defectError) {
      setError(messageFromError(defectError, "Could not create manual defect draft."));
    } finally {
      setCreatingDefectKey(null);
    }
  }

  function updateAutomationState(run: ExecutionRun, patch: Partial<AutomationRunState>) {
    const now = new Date().toISOString();
    setAutomationRunStates((previous) => {
      const key = automationStateKey(run.id);
      const existing = automationRunStateFor(run, previous[key]);
      const actionLabel = patch.message || existing.message;
      return {
        ...previous,
        [key]: {
          ...existing,
          ...patch,
          lastUpdated: now,
          recentActions: [
            `${dateLabel(now)} - ${actionLabel}`,
            ...existing.recentActions,
          ].slice(0, 8),
        },
      };
    });
  }

  async function handleAutomationAction(run: ExecutionRun, action: "start" | "pause" | "retry_failed" | "analyze_failure" | "create_defect") {
    setAutomationActionRunId(run.id);
    setError(null);
    const runResults = results.filter((result) => result.execution_run_id === run.id);
    const failedResults = runResults.filter((result) => ["failed", "error"].includes((result.automation_execution_status || result.status || "").toLowerCase()));
    const failure = automationFailureInsight(runResults);

    try {
      if (action === "start") {
        const response = await automationExecutionService.startAutomationRun(run);
        updateAutomationState(run, { ...response, startedAt: new Date().toISOString() });
      } else if (action === "pause") {
        const response = await automationExecutionService.pauseAutomationRun(run);
        updateAutomationState(run, response);
      } else if (action === "retry_failed") {
        const response = await automationExecutionService.retryFailedTests(run, failedResults.length);
        updateAutomationState(run, response);
      } else if (action === "analyze_failure") {
        const response = await automationExecutionService.analyzeAutomationFailure(failure);
        updateAutomationState(run, response);
      } else if (action === "create_defect") {
        if (!selectedProject || !failure) {
          updateAutomationState(run, {
            status: "needs_review",
            message: "No failed automation result is available for defect creation.",
            currentStep: "Defect creation skipped",
          });
          return;
        }
        const testCase = failure.result.test_case_id ? testCaseById.get(failure.result.test_case_id) : undefined;
        const response = await defectsApi.create({
          project_id: selectedProject,
          test_case_id: failure.result.test_case_id || undefined,
          execution_result_id: persistedExecutionResultId(failure.result),
          summary: `Automation Failure: ${testCase?.test_case_id || failure.result.test_name}`,
          description: [
            `Automation defect draft created from ${run.execution_id}.`,
            `Framework: ${frameworkForRun(run, runResults)}`,
            `Script: ${scriptPathForResult(failure.result, testCase)}`,
            `Failing Step: ${failure.step}`,
            `Failure Message: ${failure.message}`,
            `Root Cause Type: ${failure.rootCause}`,
          ].join("\n\n"),
          expected_result: testCase?.expected_result,
          actual_result: failure.message,
          severity: "Medium",
          priority: "P3",
          classification: "automation_issue",
        });
        setDefects((previous) => [response.data, ...previous]);
        updateAutomationState(run, {
          status: "needs_review",
          message: `Defect draft ${response.data.defect_id} created from failed automation result.`,
          currentStep: "Defect draft ready for Jira review",
        });
      }
    } catch (automationError) {
      setError(messageFromError(automationError, "Automation action could not be completed."));
      updateAutomationState(run, {
        status: "needs_review",
        message: "Automation action failed. Review backend integration and retry.",
        currentStep: "Automation action needs review",
      });
    } finally {
      setAutomationActionRunId(null);
    }
  }

  function updateAiState(run: ExecutionRun, patch: Partial<AiWorkspaceState>) {
    const now = new Date().toISOString();
    setAiWorkspaceStates((previous) => {
      const key = aiStateKey(run.id);
      const existing = aiWorkspaceStateFor(run, previous[key]);
      return {
        ...previous,
        [key]: {
          ...existing,
          ...patch,
          observations: patch.observations || existing.observations,
          risks: patch.risks || existing.risks,
          lastUpdated: now,
        },
      };
    });
  }

  function handleAiModeChange(run: ExecutionRun, mode: AiMode) {
    const current = aiWorkspaceStateFor(run, aiWorkspaceStates[aiStateKey(run.id)]);
    updateAiState(run, {
      mode,
      observations: [
        `AI mode changed to ${mode}.`,
        ...current.observations,
      ].slice(0, 8),
    });
  }

  function handleGenerateAiPlan(run: ExecutionRun, testCase?: TestCase) {
    const plan = generateAiExecutionPlan(testCase, run);
    const current = aiWorkspaceStateFor(run, aiWorkspaceStates[aiStateKey(run.id)]);
    updateAiState(run, {
      ...plan,
      mode: current.mode === "Assistive" ? plan.mode : current.mode,
      observations: [
        "Generated AI Execution Plan for human review.",
        ...plan.observations,
      ].slice(0, 8),
    });
  }

  function handleApproveAiPlan(run: ExecutionRun) {
    const current = aiWorkspaceStateFor(run, aiWorkspaceStates[aiStateKey(run.id)]);
    if (!current.planGenerated) return;
    updateAiState(run, {
      status: "approved",
      approved: true,
      observations: [
        "Human reviewer approved the generated AI execution plan.",
        ...current.observations,
      ].slice(0, 8),
    });
  }

  function handleRunAiExecution(run: ExecutionRun) {
    const current = aiWorkspaceStateFor(run, aiWorkspaceStates[aiStateKey(run.id)]);
    if (!current.planGenerated || !current.approved) return;
    updateAiState(run, {
      status: "in_progress",
      observations: [
        "AI execution started in review-gated mode. No autonomous backend action is applied without user approval.",
        ...current.observations,
      ].slice(0, 8),
    });
  }

  function handlePauseAiExecution(run: ExecutionRun) {
    const current = aiWorkspaceStateFor(run, aiWorkspaceStates[aiStateKey(run.id)]);
    updateAiState(run, {
      status: "paused",
      observations: [
        "AI execution pause requested.",
        ...current.observations,
      ].slice(0, 8),
    });
  }

  function handleAnalyzeAiFailure(run: ExecutionRun) {
    const runResults = results.filter((result) => result.execution_run_id === run.id);
    const failure = automationFailureInsight(runResults);
    const current = aiWorkspaceStateFor(run, aiWorkspaceStates[aiStateKey(run.id)]);
    updateAiState(run, {
      status: "needs_review",
      observations: [
        failure ? `AI analyzed failure signal: ${failure.message}` : "AI analysis completed. No failed execution result is available yet.",
        "Suggested root cause requires human validation before defect classification.",
        ...current.observations,
      ].slice(0, 8),
      selfHealSuggestion: current.selfHealSuggestion || {
        oldSelector: "#unstable-selector",
        suggestedSelector: "[data-testid='stable-control']",
        confidence: Math.max(current.confidence - 10, 0),
      },
    });
  }

  async function handleDraftAiDefect(run: ExecutionRun, testCase?: TestCase) {
    const current = aiWorkspaceStateFor(run, aiWorkspaceStates[aiStateKey(run.id)]);
    const runResults = results.filter((result) => result.execution_run_id === run.id);
    const result = runResults[0];
    const summary = `${testCase?.test_case_id || run.execution_id} AI-assisted defect draft`;
    const description = "AI drafted this defect from available execution context. A human reviewer must validate impact, classification, and Jira readiness before creation.";

    setError(null);
    try {
      let created: DefectDraft | null = null;
      if (selectedProject) {
        const response = await defectsApi.create({
          project_id: selectedProject,
          test_case_id: testCase?.id || result?.test_case_id || undefined,
          execution_result_id: persistedExecutionResultId(result),
          summary,
          description: [
            description,
            `Execution Run: ${run.execution_id}`,
            `AI Mode: ${current.mode}`,
            `Confidence: ${formatPercent(current.confidence)}`,
            `Human review required before Jira push.`,
          ].join("\n\n"),
          expected_result: testCase?.expected_result || current.validations[0],
          actual_result: automationFailureInsight(runResults)?.message || "AI-assisted execution requires observed evidence before final defect classification.",
          severity: "Medium",
          priority: "P3",
          classification: "product_defect",
        });
        created = response.data;
        setDefects((previous) => [response.data, ...previous]);
      }

      updateAiState(run, {
        status: "needs_review",
        defectDraft: {
          title: created ? `${created.defect_id}: ${created.summary}` : summary,
          description,
          severity: "Medium",
          priority: "P3",
          status: created ? normalizeStatus(created.status) : "Draft",
        },
        observations: [
          created ? `AI defect draft ${created.defect_id} created for human Jira review.` : "AI defect draft prepared locally. Jira issue was not created automatically.",
          ...current.observations,
        ].slice(0, 8),
      });
    } catch (draftError) {
      setError(messageFromError(draftError, "Could not create AI defect draft."));
    }
  }

  const selectedPreset = useMemo(() => {
    return Object.entries(EXECUTION_VIEW_PRESETS).find(
      ([, preset]) =>
        preset.columns.length === visibleColumns.length &&
        preset.columns.every((key) => visibleColumns.includes(key))
    )?.[0] ?? "custom";
  }, [visibleColumns]);

  return (
    <div className="space-y-5 pb-8">
      <header className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-950">Test Execution</h1>
          <p className="mt-1 text-sm font-medium text-slate-500">
            Execute, monitor, and analyze manual, automation, and AI-driven test runs.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <Button size="sm" className="h-9 text-xs font-bold" onClick={handleCreateExecutionRun} aria-label="Create execution run">
            <Plus className="h-3.5 w-3.5" />
            Create Execution Run
          </Button>
          <Button size="sm" variant="outline" className="h-9 border-slate-200 bg-white text-xs font-bold" onClick={handleImportResults} aria-label="Import execution results">
            <FileUp className="h-3.5 w-3.5" />
            Import Results
          </Button>
          <Button size="sm" variant="outline" className="h-9 border-slate-200 bg-white text-xs font-bold" onClick={handleConfigureExecution} aria-label="Configure execution">
            <Settings className="h-3.5 w-3.5" />
            Configure Execution
          </Button>
        </div>
      </header>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-semibold text-rose-700">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="flex-1">{error}</span>
          <button onClick={() => setError(null)} aria-label="Dismiss error"><XCircle className="h-4 w-4" /></button>
        </div>
      )}

      {notice && (
        <div className="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-xs font-semibold text-blue-700">
          <ShieldCheck className="h-4 w-4 shrink-0" />
          <span className="flex-1">{notice}</span>
          <button onClick={() => setNotice(null)} aria-label="Dismiss notice"><XCircle className="h-4 w-4" /></button>
        </div>
      )}

      <section className="grid grid-cols-[repeat(auto-fit,minmax(156px,1fr))] gap-2">
        {metrics.map((metric) => (
          <StatCard key={metric.title} {...metric} />
        ))}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-100 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex overflow-x-auto">
            {(["manual", "automation", "ai"] as ExecutionTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => handleTabChange(tab)}
                className={cn(
                  "flex h-10 min-w-[150px] items-center justify-center gap-2 border-b-2 px-3 text-xs font-bold transition",
                  activeTab === tab ? "border-blue-600 text-blue-600" : "border-transparent text-slate-500 hover:text-slate-900"
                )}
              >
                {tab === "manual" && <BriefcaseBusiness className="h-4 w-4" />}
                {tab === "automation" && <SlidersHorizontal className="h-4 w-4" />}
                {tab === "ai" && <Sparkles className="h-4 w-4" />}
                {TAB_LABELS[tab]}
              </button>
            ))}
          </div>
          <Button size="sm" variant="outline" className="h-8 border-slate-200 bg-white text-xs" onClick={loadData} disabled={loading}>
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>

      </section>

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 p-4">
          <div>
            <h2 className="text-sm font-bold text-slate-900">{TAB_LABELS[activeTab]} Runs</h2>
            <p className="text-[11px] font-medium text-slate-400">Filtered execution catalog</p>
          </div>
          <div className="flex gap-1">
            <button className="rounded-md p-2 text-slate-400 hover:bg-slate-50" aria-label="Refresh runs">
              <RefreshCw className="h-4 w-4" />
            </button>
            <button className="rounded-md p-2 text-slate-400 hover:bg-slate-50" aria-label="Configure run table">
              <SlidersHorizontal className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-100 bg-slate-50/30 px-4 py-4.5">
          <div className="flex flex-wrap items-center gap-3">
            {/* Status Filters */}
            <div className="flex gap-1 rounded-lg border border-slate-200 bg-white p-1 shrink-0">
              {["All", "Passed", "Failed", "In Progress", "Completed", "Pending"].map((status) => (
                <button
                  key={status}
                  onClick={() => setStatusFilter(status)}
                  className={cn(
                    "rounded-md px-3 py-1 text-xs font-semibold transition-all",
                    statusFilter === status
                      ? "bg-[#1b59f8] text-white shadow-sm"
                      : "text-slate-500 hover:text-slate-900"
                  )}
                >
                  {status}
                </button>
              ))}
            </div>

            {/* Mode Filters */}
            <div className="flex gap-1 rounded-lg border border-slate-200 bg-white p-1 shrink-0">
              {["All", "Manual", "Automation", "AI"].map((mode) => (
                <button
                  key={mode}
                  onClick={() => setModeFilter(mode)}
                  className={cn(
                    "rounded-md px-3 py-1 text-xs font-semibold transition-all",
                    modeFilter === mode
                      ? "bg-[#1b59f8] text-white shadow-sm"
                      : "text-slate-500 hover:text-slate-900"
                  )}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>

          {/* View Presets & Column Controls */}
          <div className="relative flex flex-wrap items-center gap-2 self-start lg:self-auto shrink-0">
            <select
              value={selectedPreset}
              onChange={(e) => {
                const preset = EXECUTION_VIEW_PRESETS[e.target.value];
                if (preset) {
                  setVisibleColumns(preset.columns);
                  setNotice(`Preset "${preset.label}" applied.`);
                }
              }}
              className="appearance-none bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 rounded-lg text-xs font-semibold px-3 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-[#1b59f8] transition-colors cursor-pointer select-none"
              style={{
                backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
                backgroundPosition: 'right 0.5rem center',
                backgroundSize: '1.25rem 1.25rem',
                backgroundRepeat: 'no-repeat',
              }}
            >
              <option value="custom">Custom View</option>
              {Object.entries(EXECUTION_VIEW_PRESETS).map(([key, preset]) => (
                <option key={key} value={key}>{preset.label}</option>
              ))}
            </select>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowColumns((v) => !v)}
              className="h-8 text-xs border-slate-200 bg-white"
            >
              <SlidersHorizontal className="h-4 w-4 text-slate-500" />
              Columns
              <Badge variant="secondary" className="px-1.5 py-0 bg-slate-100 ml-1">{visibleColumns.length}</Badge>
            </Button>

            {(statusFilter !== "All" || modeFilter !== "All") && (
              <Button
                size="sm"
                variant="ghost"
                className="h-8 text-xs font-semibold text-rose-600 hover:bg-rose-50 hover:text-rose-700 px-2.5 shrink-0 self-end mb-0.5"
                onClick={handleClearFilters}
              >
                Clear
              </Button>
            )}

            <span className="text-xs text-slate-400 font-semibold ml-2">
              {visibleRuns.length} item{visibleRuns.length !== 1 && "s"}
            </span>

            {/* Column Toggle Dropdown Popover */}
            {showColumns && (
              <>
                <div className="fixed inset-0 z-20" onClick={() => setShowColumns(false)} />
                <div className="absolute right-0 top-10 z-30 w-72 rounded-xl border border-slate-200 bg-white p-4 shadow-xl animate-fade-in select-none text-left">
                  <div className="mb-3.5 flex items-center justify-between">
                    <p className="text-xs font-bold text-slate-800">Column Configuration</p>
                    <button onClick={() => setShowColumns(false)} className="rounded p-1 text-slate-400 hover:bg-slate-50 hover:text-slate-600">
                      <XCircle className="h-4 w-4" />
                    </button>
                  </div>

                  <div className="mb-3.5 grid grid-cols-2 gap-2">
                    <button
                      onClick={() => setVisibleColumns(EXECUTION_COLUMNS.map((col) => col.key))}
                      className="rounded-lg border border-slate-200 px-2 py-1.5 text-[10px] font-bold text-slate-600 hover:bg-slate-50"
                    >
                      Select All
                    </button>
                    <button
                      onClick={() => setVisibleColumns(DEFAULT_EXECUTION_COLUMN_KEYS)}
                      className="inline-flex items-center justify-center gap-1 rounded-lg border border-slate-200 px-2 py-1.5 text-[10px] font-bold text-slate-600 hover:bg-slate-50"
                    >
                      <RotateCcw className="h-3 w-3" />Reset Defaults
                    </button>
                  </div>

                  <div className="max-h-60 space-y-3.5 overflow-y-auto pr-1">
                    {(["core", "advanced"] as const).map((group) => (
                      <div key={group}>
                        <p className="mb-1.5 text-[9px] font-bold uppercase tracking-wider text-slate-400">
                          {group === "core" ? "Recommended Fields" : "Advanced Details"}
                        </p>
                        <div className="space-y-1">
                          {EXECUTION_COLUMNS.filter((col) => col.group === group).map((col) => (
                            <label key={col.key} className="flex cursor-pointer items-center justify-between rounded-lg px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition-colors">
                              <span className="font-medium">{col.label}</span>
                              <input
                                type="checkbox"
                                checked={visibleColumns.includes(col.key)}
                                disabled={col.required}
                                className="rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8]"
                                onChange={() => {
                                  if (col.required) return;
                                  const isVisible = visibleColumns.includes(col.key);
                                  setVisibleColumns(isVisible ? visibleColumns.filter((key) => key !== col.key) : [...visibleColumns, col.key]);
                                }}
                              />
                            </label>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-[980px] w-full table-fixed text-left">
            <thead className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400">
              <tr>
                {visibleColumns.map((colKey) => {
                  const config = EXECUTION_COLUMNS.find((c) => c.key === colKey);
                  if (!config) return null;
                  return (
                    <th key={colKey} className={cn("px-3 py-3", config.width)}>
                      {config.label}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={visibleColumns.length} className="px-4 py-16 text-center text-xs font-semibold text-slate-400">
                    <Loader2 className="mr-2 inline h-4 w-4 animate-spin text-blue-600" />
                    Loading execution runs...
                  </td>
                </tr>
              ) : visibleRuns.length === 0 ? (
                <tr>
                  <td colSpan={visibleColumns.length} className="px-4 py-10">
                    <EmptyState title="No runs match this workspace" description="Clear filters, adjust search, or switch tabs to view available execution runs." />
                  </td>
                </tr>
              ) : (
                pagedRuns.map((run) => (
                  <RunRow key={run.id} run={run} selected={run.id === selectedRunId} onSelect={() => setSelectedRunId(run.id)} visibleColumns={visibleColumns} />
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="flex flex-col gap-3 border-t border-slate-100 px-4 py-3 text-[11px] font-semibold text-slate-500 lg:flex-row lg:items-center lg:justify-between">
          <span>
            Showing {visibleRuns.length === 0 ? "0" : formatNumber((currentPage - 1) * pageSize + 1)}
            {" - "}
            {formatNumber(Math.min(currentPage * pageSize, visibleRuns.length))}
            {" of "}
            {formatNumber(visibleRuns.length)} run rows
          </span>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" className="h-8 border-slate-200 bg-white text-xs" onClick={handleExportReport} disabled={visibleRuns.length === 0}>
              Export Report
            </Button>
            <SelectBox label="Rows" value={String(pageSize)} onChange={(value) => setPageSize(Number(value))} options={PAGE_SIZE_OPTIONS} className="min-w-[90px]" />
            <Button size="sm" variant="outline" className="h-8 border-slate-200 bg-white text-xs" onClick={() => setCurrentPage((page) => Math.max(1, page - 1))} disabled={currentPage <= 1}>
              Previous
            </Button>
            <span className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
              Page {formatNumber(currentPage)} / {formatNumber(totalPages)}
            </span>
            <Button size="sm" variant="outline" className="h-8 border-slate-200 bg-white text-xs" onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))} disabled={currentPage >= totalPages}>
              Next
            </Button>
          </div>
        </div>
      </section>

      <main className="flex flex-col gap-6">
        <WorkspaceShell
          tab={activeTab}
          selectedRun={selectedRun}
          selectedTestCase={selectedTestCase}
          selectedResults={selectedResults}
          testCaseById={testCaseById}
          selectedManualResultId={selectedManualResultId}
          onSelectManualResult={handleSelectManualResult}
          currentManualStepIndex={currentManualStepIndex}
          onManualStepIndexChange={setCurrentManualStepIndex}
          manualStepStates={manualStepStates}
          onUpdateManualStep={handleUpdateManualStep}
          onSaveManualNext={handleSaveManualNext}
          onMarkManualComplete={handleMarkManualComplete}
          onAttachManualEvidence={handleAttachManualEvidence}
          onCreateManualDefect={handleCreateManualDefect}
          creatingDefectKey={creatingDefectKey}
          manualActivity={manualActivity}
          autoSaveMessage={autoSaveMessage}
          automationRunStates={automationRunStates}
          onAutomationAction={handleAutomationAction}
          automationActionRunId={automationActionRunId}
          aiWorkspaceStates={aiWorkspaceStates}
          onAiModeChange={handleAiModeChange}
          onGenerateAiPlan={handleGenerateAiPlan}
          onApproveAiPlan={handleApproveAiPlan}
          onRunAiExecution={handleRunAiExecution}
          onPauseAiExecution={handlePauseAiExecution}
          onAnalyzeAiFailure={handleAnalyzeAiFailure}
          onDraftAiDefect={handleDraftAiDefect}
        />
        <DetailsPanel
          tab={activeTab}
          selectedRun={selectedRun}
          selectedTestCase={selectedTestCase}
          selectedResults={selectedResults}
          defects={defects}
          testCaseById={testCaseById}
          selectedManualResultId={selectedManualResultId}
          manualStepStates={manualStepStates}
          manualActivity={manualActivity}
          automationRunStates={automationRunStates}
          aiWorkspaceStates={aiWorkspaceStates}
          jiraDefectLinks={jiraDefectLinks}
          jiraBusyId={jiraBusyId}
          onApproveDefect={handleApproveDefect}
          onPushDefectToJira={handlePushDefectToJira}
          onLinkExistingJira={handleLinkExistingJira}
          failureDecisions={failureDecisions}
          onSaveFailureDecision={handleSaveFailureDecision}
          onClearFailureDecision={handleClearFailureDecision}
          onCreateManualDefect={handleCreateManualDefect}
        />

        {resultsLoading && (
          <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-xs font-semibold text-blue-700">
            <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
            Loading selected run details...
          </div>
        )}

        <ResultsTable
          tab={activeTab}
          selectedResults={selectedResults}
          selectedTestCase={selectedTestCase}
          testCaseById={testCaseById}
          selectedManualResultId={selectedManualResultId}
          manualStepStates={manualStepStates}
          selectedRun={selectedRun}
          aiWorkspaceStates={aiWorkspaceStates}
          defects={defects}
          jiraDefectLinks={jiraDefectLinks}
          jiraBusyId={jiraBusyId}
          onApproveDefect={handleApproveDefect}
          onPushDefectToJira={handlePushDefectToJira}
          onLinkExistingJira={handleLinkExistingJira}
        />
      </main>

    </div>
  );
}

export default function ExecutionPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-64 items-center justify-center text-xs font-semibold text-slate-400">
          <Loader2 className="mr-2 h-5 w-5 animate-spin text-blue-600" />
          Loading Test Execution...
        </div>
      }
    >
      <ExecutionContent />
    </Suspense>
  );
}
