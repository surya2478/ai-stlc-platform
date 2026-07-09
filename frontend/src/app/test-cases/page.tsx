"use client";

import { useCallback, useEffect, useMemo, useState, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  AlertTriangle, Bot, CheckCircle, ChevronDown, ChevronUp, Columns3, Download, ExternalLink,
  History, Loader2, RefreshCw, RotateCcw, Save, ShieldCheck, TestTube2, XCircle, ChevronRight, X, Play, Info, Sparkles,
  FileText, Layers, Zap, LayoutDashboard, Clock, Pencil, Plus, Trash2
} from "lucide-react";
import { AuditStamp } from "@/components/ui/AuditStamp";
import { useUserDirectory } from "@/hooks/useUserDirectory";
import {
  agentRunsApi, api, projectsApi, requirementsApi, reviewsApi, scenariosApi, testCasesApi, testSuitesApi,
  type ArtifactReview, type Requirement, type TestCase, type TestCaseBulkUpdateResult,
  type TestCaseHistory, type TestCaseSummary, type TestScenario, type TestSuite,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerBody, DrawerFooter, DrawerClose
} from "@/components/ui/drawer";
import { ReviewBadge } from "@/components/reviews/ReviewBadge";

// ── Dropdown and Form Options ──────────────────────────────────────────────────

type Option = { value: string; label: string };

// Execution mode: shown in the test-case form. New canonical values use snake_case
// identifiers ("automation" not "automated") so backend filters and the existing
// `automation_status` cross-field rules continue to work.
const MODE_OPTIONS: Option[] = [
  { value: "automation", label: "Automation" },
  { value: "manual", label: "Manual" },
  { value: "ai", label: "AI" },
];

// Map any *legacy* stored mode value to a user-friendly display label so old
// test cases keep rendering correctly even though the option is no longer
// offered for new selections.
const LEGACY_MODE_LABELS: Record<string, string> = {
  automated: "Automation",   // historical alias — UI now uses "automation"
  hybrid: "Hybrid (legacy)",
};

function modeDisplayLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const known = MODE_OPTIONS.find((o) => o.value === value);
  if (known) return known.label;
  return LEGACY_MODE_LABELS[value] ?? value.replace(/_/g, " ");
}

// Note: automation_eligible used to be a separate "yes"/"no" dropdown — it's
// now auto-derived from execution_mode on every save (manual → no, automation/ai → yes)
// so the field stays consistent with the chosen mode and no longer needs a UI.

// Automation status: same approach. Sentinel "not_required" is preserved for
// manual-mode rows where the field is disabled — it never appears in the
// dropdown but is rendered with a friendly label if stored.
const AUTOMATION_STATUS_OPTIONS: Option[] = [
  { value: "planned_for_automation", label: "Planned for Automation" },
  { value: "ready_for_automation", label: "Ready for Automation" },
  { value: "automated", label: "Automated" },
  { value: "awaiting_qa_approval", label: "Awaiting QA Approval" },
];

const LEGACY_AUTOMATION_STATUS_LABELS: Record<string, string> = {
  not_required: "Not Required",
  mapping_required: "Mapping Required (legacy)",
  automation_failed: "Automation Failed",
  maintenance_required: "Maintenance Required",
  not_automated: "Not Automated",
  automation_candidate: "Automation Candidate",
};

function automationStatusDisplayLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const known = AUTOMATION_STATUS_OPTIONS.find((o) => o.value === value);
  if (known) return known.label;
  return LEGACY_AUTOMATION_STATUS_LABELS[value] ?? value.replace(/_/g, " ");
}
const TOOL_OPTIONS = ["", "Mock", "Playwright", "Pytest", "Katalon", "Selenium", "Other"];
const JIRA_STATUS_OPTIONS = ["", "pending", "passed", "failed", "skipped", "blocked", "not_run"];
const PHASE_OPTIONS = ["", "SIT", "QA", "UAT", "Regression", "Production Smoke Test"];
const DOMAIN_OPTIONS = ["", "Mobile", "Fixed", "Digital", "Billing", "Charging", "CRM", "OSS", "BSS", "Middleware", "Integration", "Network", "Data"];
const PRODUCT_GROUP_OPTIONS = [
  "",
  "BusinessLite",
  "Figital Services",
  "MOBILE Products",
  "eLife Product Group",
  "Internet - Broad Band Services",
  "Data",
  "PSTN",
  "eCompany Application Based Services",
  "Cloud Communications",
  "Product Group Code for EES and FMS",
  "Multi Play"
];
const PRODUCT_OPTIONS = [
  "",
  "GSM Prepaid",
  "GSM Post Paid",
  "iShare",
  "Global IPVPN",
  "eLife TV",
  "Triple Play Products",
  "PABX Lines",
  "Dual Play Products",
  "Bit Stream"
];
const SUB_REQUEST_TYPE_OPTIONS = [
  "",
  "Add Service",
  "Delete Service",
  "New Account",
  "Number Change",
  "Reconnection",
  "Technician Visit",
  "Migration Request",
  "External Shift"
];
const PRIORITY_OPTIONS = ["Low", "Medium", "High", "Critical"];

type ColumnKey =
  | "id"
  | "title"
  | "status"
  | "priority"
  | "mode"
  | "automation"
  | "jiraLink"
  | "actions"
  | "approvalStatus"
  | "eligible"
  | "automationReady"
  | "tool"
  | "suiteId"
  | "externalTc"
  | "externalTcUrl"
  | "jiraFinal"
  | "jiraSyncStatus"
  | "testPhase"
  | "testSuite"
  | "telecomDomain"
  | "linkedRequirement"
  | "lastAutomation"
  | "evidence"
  | "createdBy"
  | "createdAt"
  | "updatedBy"
  | "updatedAt";

type ColumnConfig = {
  key: ColumnKey;
  label: string;
  defaultVisible?: boolean;
  required?: boolean;
  group: "core" | "advanced";
  width: string;
  draftFields?: Array<keyof Draft>;
};

const TEST_CASE_COLUMNS: ColumnConfig[] = [
  { key: "id", label: "ID", defaultVisible: true, required: true, group: "core", width: "110px" },
  { key: "title", label: "Title", defaultVisible: true, required: true, group: "core", width: "minmax(280px, 1.8fr)" },
  { key: "status", label: "Status", defaultVisible: true, group: "core", width: "128px", draftFields: ["status"] },
  { key: "priority", label: "Priority", defaultVisible: true, group: "core", width: "110px", draftFields: ["priority"] },
  { key: "mode", label: "Mode", defaultVisible: true, group: "core", width: "110px", draftFields: ["mode"] },
  { key: "automation", label: "Automation", defaultVisible: true, group: "core", width: "148px", draftFields: ["automation_status"] },
  { key: "jiraLink", label: "Jira Link", defaultVisible: true, group: "core", width: "110px" },
  { key: "actions", label: "Actions", defaultVisible: true, required: true, group: "core", width: "110px" },
  { key: "approvalStatus", label: "Approval Status", group: "advanced", width: "140px" },
  { key: "eligible", label: "Eligible", group: "advanced", width: "110px", draftFields: ["automation_eligible"] },
  { key: "automationReady", label: "Automation Ready", group: "advanced", width: "132px", draftFields: ["automation_ready"] },
  { key: "tool", label: "Tool", group: "advanced", width: "140px", draftFields: ["external_tool"] },
  { key: "suiteId", label: "Suite ID", group: "advanced", width: "150px", draftFields: ["suite_id"] },
  { key: "externalTc", label: "External TC", group: "advanced", width: "160px", draftFields: ["external_tc_id"] },
  { key: "externalTcUrl", label: "External TC URL", group: "advanced", width: "190px", draftFields: ["external_tc_url"] },
  { key: "jiraFinal", label: "Jira Final", group: "advanced", width: "128px", draftFields: ["jira_final_status"] },
  { key: "jiraSyncStatus", label: "Jira Sync", group: "advanced", width: "130px" },
  { key: "testPhase", label: "Test Environment", group: "advanced", width: "150px", draftFields: ["test_phase"] },
  { key: "testSuite", label: "Test Suite", group: "advanced", width: "170px", draftFields: ["test_suite_name"] },
  { key: "telecomDomain", label: "Telecom Domain", group: "advanced", width: "150px", draftFields: ["telecom_domain"] },
  { key: "linkedRequirement", label: "Linked Requirement", group: "advanced", width: "160px" },
  { key: "lastAutomation", label: "Last Automation", group: "advanced", width: "142px" },
  { key: "evidence", label: "Evidence", group: "advanced", width: "128px" },
  { key: "createdBy", label: "Created By", group: "advanced", width: "140px" },
  { key: "createdAt", label: "Created At", group: "advanced", width: "185px" },
  { key: "updatedBy", label: "Modified By", group: "advanced", width: "140px" },
  { key: "updatedAt", label: "Modified At", group: "advanced", width: "185px" },
];

const DEFAULT_COLUMN_KEYS = TEST_CASE_COLUMNS.filter((c) => c.defaultVisible).map((c) => c.key);
const REQUIRED_COLUMN_KEYS = TEST_CASE_COLUMNS.filter((c) => c.required).map((c) => c.key);
const VALID_COLUMN_KEYS = new Set(TEST_CASE_COLUMNS.map((c) => c.key));

const VIEW_PRESETS: Record<string, { label: string; columns: ColumnKey[] }> = {
  default: {
    label: "Default View",
    columns: ["id", "title", "status", "priority", "mode", "automation", "jiraLink", "actions"],
  },
  automation: {
    label: "Automation View",
    columns: ["id", "title", "mode", "eligible", "automation", "tool", "suiteId", "externalTc", "evidence", "actions"],
  },
  jira: {
    label: "Jira View",
    columns: ["id", "title", "jiraLink", "jiraFinal", "jiraSyncStatus", "linkedRequirement", "actions"],
  },
  telecom: {
    label: "Telecom View",
    columns: ["id", "title", "telecomDomain", "testPhase", "priority", "status", "linkedRequirement", "actions"],
  },
};

type Draft = {
  status: string;
  priority: string;
  mode: string;
  automation_eligible: string;
  automation_status: string;
  automation_ready: boolean;
  external_tool: string;
  suite_id: string;
  external_tc_id: string;
  external_tc_url: string;
  jira_final_status: string;
  telecom_domain: string;
  test_phase: string;
  // Editable as free text (with existing-suite suggestions) — resolved to
  // test_suite_id on save, creating a new suite if the name doesn't match one.
  test_suite_name: string;
  product_group: string;
  product: string;
  sub_request_type: string;
  application_id: number | null;
  comment: string;
};

// ── Helper functions ─────────────────────────────────────────────────────────
function messageFromError(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => item?.msg ?? String(item)).join("; ");
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

function toDraft(tc: TestCase): Draft {
  return {
    status: tc.status,
    priority: tc.priority,
    mode: tc.mode ?? tc.execution_mode,
    automation_eligible: tc.automation_eligible,
    automation_status: tc.automation_status,
    automation_ready: Boolean(tc.automation_ready),
    external_tool: tc.external_tool ?? "",
    suite_id: tc.suite_id ?? "",
    external_tc_id: tc.external_tc_id ?? "",
    external_tc_url: tc.external_tc_url ?? "",
    jira_final_status: tc.jira_final_status ?? "",
    telecom_domain: tc.telecom_domain ?? "",
    test_phase: tc.test_phase ?? "",
    test_suite_name: tc.test_suite_name ?? "",
    product_group: tc.product_group ?? "",
    product: tc.product ?? "",
    sub_request_type: tc.sub_request_type ?? "",
    application_id: tc.application_id ?? null,
    comment: "",
  };
}

function sanitizeColumns(input: unknown): ColumnKey[] {
  const raw = Array.isArray(input) ? input : DEFAULT_COLUMN_KEYS;
  const selected = raw.filter((key): key is ColumnKey => typeof key === "string" && VALID_COLUMN_KEYS.has(key as ColumnKey));
  const withRequired = Array.from(new Set([...selected, ...REQUIRED_COLUMN_KEYS]));
  if (withRequired.length <= REQUIRED_COLUMN_KEYS.length) return DEFAULT_COLUMN_KEYS;
  return TEST_CASE_COLUMNS.filter((col) => withRequired.includes(col.key)).map((col) => col.key);
}

function visibleStorageKey(projectId: number | null) {
  return `testCases.visibleColumns.${projectId ?? "default"}`;
}

function compactStorageKey(projectId: number | null) {
  return `testCases.compactView.${projectId ?? "default"}`;
}

function displayValue(value: string | number | boolean | null | undefined, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ── Content Component ─────────────────────────────────────────────────────────
function TestCasesContent() {
  const { resolveUser } = useUserDirectory();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProject = Number(searchParams.get("project")) || null;

  const [applications, setApplications] = useState<{ id: number; name: string; is_default: boolean }[]>([]);
  const [suites, setSuites] = useState<TestSuite[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [summary, setSummary] = useState<TestCaseSummary | null>(null);
  const [scenarios, setScenarios] = useState<TestScenario[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [testCaseReviews, setTestCaseReviews] = useState<ArtifactReview[]>([]);
  
  // Drawer States
  const [selectedTestCase, setSelectedTestCase] = useState<TestCase | null>(null);
  const [drawerTab, setDrawerTab] = useState<"approval" | "steps" | "details" | "history">("approval");

  // Steps tab editing state — separate from the Details-tab `drafts` mechanism
  // since preconditions/steps/expected_result are structured arrays, not the
  // flat scalar fields `Draft` covers.
  type StepsDraft = {
    preconditions: string[];
    steps: { step_number: number; action: string; expected_result: string }[];
    expected_result: string;
  };
  const [editingStepsId, setEditingStepsId] = useState<number | null>(null);
  const [stepsDraft, setStepsDraft] = useState<StepsDraft | null>(null);
  const [savingSteps, setSavingSteps] = useState(false);

  // Approval action state (Approval tab)
  const [approvalChoice, setApprovalChoice] = useState<"approve" | "reject" | null>(null);
  const [approvalNotes, setApprovalNotes] = useState("");
  const [approvalSubmitting, setApprovalSubmitting] = useState(false);

  // Draft editing states
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [historyRows, setHistoryRows] = useState<TestCaseHistory[]>([]);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [agentRunning, setAgentRunning] = useState(false);
  const [notice, setNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState<"success" | "info">("success");
  const [error, setError] = useState("");
  const [filterStatus, setFilterStatus] = useState("all");
  const [filterMode, setFilterMode] = useState("all");
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<number[]>([]);
  const [showSelector, setShowSelector] = useState(false);
  const [showColumns, setShowColumns] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState<ColumnKey[]>(DEFAULT_COLUMN_KEYS);
  const [compactView, setCompactView] = useState(false);

  // ── Bulk selection state ──────────────────────────────────────────────────
  // Selected test case IDs across the visible (filtered) list. Persists across
  // filter changes but is cleared when the project switches or after a bulk
  // commit. The Bulk Edit action surfaces only when this set is non-empty.
  const [selectedTcIds, setSelectedTcIds] = useState<Set<number>>(new Set());
  const [bulkEditOpen, setBulkEditOpen] = useState(false);

  // Sync parameters
  useEffect(() => {
    projectsApi.list().then((res) => {
      if (res.data.length > 0 && !searchParams.get("project")) {
        const params = new URLSearchParams(searchParams.toString());
        params.set("project", String(res.data[0].id));
        router.push(`${pathname}?${params.toString()}`);
      }
    }).catch(() => setError("Could not load projects."));
  }, [searchParams, pathname, router]);

  useEffect(() => {
    if (!selectedProject) {
      setApplications([]);
      return;
    }
    api.get<{ applications: { id: number; name: string; is_default: boolean; is_active: boolean }[] }>(
      `/projects/${selectedProject}/applications`
    )
      .then((res) => setApplications(res.data.applications.filter((a) => a.is_active)))
      .catch(() => setApplications([]));
  }, [selectedProject]);

  const loadSuites = useCallback(() => {
    if (!selectedProject) {
      setSuites([]);
      return;
    }
    testSuitesApi.list(selectedProject)
      .then((res) => setSuites(res.data))
      .catch(() => setSuites([]));
  }, [selectedProject]);

  useEffect(() => { loadSuites(); }, [loadSuites]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(visibleStorageKey(selectedProject));
    let parsed: unknown = DEFAULT_COLUMN_KEYS;
    try {
      parsed = saved ? JSON.parse(saved) : DEFAULT_COLUMN_KEYS;
    } catch {
      parsed = DEFAULT_COLUMN_KEYS;
    }
    setVisibleColumns(sanitizeColumns(parsed));
    setCompactView(window.localStorage.getItem(compactStorageKey(selectedProject)) === "true");
    // Clear bulk-selection when the user changes projects — IDs are scoped to a project,
    // and carrying them across would either silently target the wrong rows or get rejected
    // by the backend's project-scope check.
    setSelectedTcIds(new Set());
    setBulkEditOpen(false);
  }, [selectedProject]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(visibleStorageKey(selectedProject), JSON.stringify(sanitizeColumns(visibleColumns)));
  }, [selectedProject, visibleColumns]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(compactStorageKey(selectedProject), String(compactView));
  }, [selectedProject, compactView]);

  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    setError("");
    try {
      const [tcRes, summaryRes, scRes, reqRes, reviewsRes] = await Promise.all([
        testCasesApi.list(selectedProject),
        testCasesApi.summary(selectedProject),
        scenariosApi.list(selectedProject),
        requirementsApi.list(selectedProject, { status: "approved" }),
        reviewsApi.listForProject(selectedProject, "scenario_test_case_coverage"),
      ]);
      const approvedScenarios = scRes.data.filter((s) => s.status === "approved");
      setTestCases(tcRes.data);
      setSummary(summaryRes.data);
      setScenarios(approvedScenarios);
      setRequirements(reqRes.data);
      setSelectedScenarioIds(approvedScenarios.map((s) => s.id));
      setDrafts(Object.fromEntries(tcRes.data.map((tc) => [tc.id, toDraft(tc)])));
      setTestCaseReviews(reviewsRes.data);
    } catch (loadError) {
      setError(messageFromError(loadError, "Could not load test case data."));
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadData();
  }, [selectedProject, loadData]);

  // Reset selectedTestCase when project changes
  useEffect(() => {
    setSelectedTestCase(null);
  }, [selectedProject]);

  // Reset approval scratch state and default tab whenever the drawer target changes
  useEffect(() => {
    setApprovalChoice(null);
    setApprovalNotes("");
    setDrawerTab("approval");
  }, [selectedTestCase?.id]);

  // Keep selectedTestCase synced with the latest item from testCases list
  useEffect(() => {
    if (selectedTestCase) {
      const fresh = testCases.find((t) => t.id === selectedTestCase.id);
      if (!fresh) {
        setSelectedTestCase(null);
      } else if (fresh !== selectedTestCase) {
        setSelectedTestCase(fresh);
      }
    }
  }, [testCases, selectedTestCase]);

  // Exit Steps edit mode whenever the selected test case changes (or the
  // drawer closes) so a stale draft never gets applied to the wrong row.
  useEffect(() => {
    setEditingStepsId(null);
    setStepsDraft(null);
  }, [selectedTestCase?.id]);

  // Load history whenever tab changes to history
  useEffect(() => {
    if (selectedTestCase && drawerTab === "history") {
      setHistoryLoading(true);
      testCasesApi.history(selectedTestCase.id)
        .then(res => setHistoryRows(res.data))
        .catch(() => setError("Could not load test case history."))
        .finally(() => setHistoryLoading(false));
    }
  }, [selectedTestCase, drawerTab]);

  function updateDraft(id: number, patch: Partial<Draft>) {
    setDrafts((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }

  function hasChanges(tc: TestCase) {
    const draft = drafts[tc.id];
    if (!draft) return false;
    const original = toDraft(tc);
    return Object.entries(draft).some(([key, value]) => key !== "comment" && original[key as keyof Draft] !== value);
  }

  function changedPayload(tc: TestCase) {
    const draft = drafts[tc.id];
    if (!draft) return {};
    const original = toDraft(tc);
    const editableKeys: Array<keyof Draft> = [
      "status", "priority", "mode", "automation_eligible", "automation_status", "automation_ready",
      "external_tool", "suite_id", "external_tc_id", "external_tc_url", "jira_final_status",
      "telecom_domain", "test_phase", "product_group", "product", "sub_request_type", "application_id"
    ];
    const payload: Partial<TestCase> & { comment?: string; mode?: string } = {};
    const mutablePayload = payload as Record<string, unknown>;
    editableKeys.forEach((key) => {
      if (draft[key] === original[key]) return;
      const value = draft[key];
      if (typeof value === "string") {
        mutablePayload[key] = value || undefined;
      } else {
        mutablePayload[key] = value;
      }
    });
    if (draft.comment.trim()) payload.comment = draft.comment.trim();
    return payload;
  }

  /** Resolves a typed suite name to its id, creating a new suite inline if no
   * existing suite in this project matches (case-insensitive). Empty name clears
   * the assignment. */
  async function resolveSuiteId(name: string): Promise<number | null> {
    const trimmed = name.trim();
    if (!trimmed) return null;
    const existing = suites.find((s) => s.name.toLowerCase() === trimmed.toLowerCase());
    if (existing) return existing.id;
    if (!selectedProject) return null;
    const res = await testSuitesApi.create({ project_id: selectedProject, name: trimmed });
    setSuites((prev) => [...prev, res.data]);
    return res.data.id;
  }

  function toggleColumn(column: ColumnConfig) {
    if (column.required) return;
    const isVisible = visibleColumns.includes(column.key);
    setVisibleColumns(isVisible ? visibleColumns.filter((key) => key !== column.key) : [...visibleColumns, column.key]);
  }

  async function saveTestCase(tc: TestCase) {
    const draft = drafts[tc.id];
    if (!draft) return;
    // External TC ID requirement only applies to *external* tools (Katalon, Selenium, etc.)
    // where the test case lives in another system. For internal tools (Playwright / Pytest)
    // the script is platform-managed and the linkage is filled in by the script generator,
    // so the user can flag the row as Automated before that link exists.
    const isInternalTool = draft.external_tool === "Playwright" || draft.external_tool === "Pytest";
    if (
      draft.automation_status === "automated"
      && !isInternalTool
      && !draft.external_tc_id.trim()
      && !tc.automation_script_id
    ) {
      setError("Automated status needs an External TC ID, a linked automation script, or an internal tool (Playwright / Pytest).");
      return;
    }
    if (draft.mode === "manual" && draft.automation_status === "automated") {
      setError("Manual test cases cannot be marked automated.");
      return;
    }
    setSavingId(tc.id);
    setError("");
    setNotice("");
    try {
      const payload: Record<string, unknown> = { ...changedPayload(tc) };
      if (draft.test_suite_name !== toDraft(tc).test_suite_name) {
        payload.test_suite_id = await resolveSuiteId(draft.test_suite_name);
      }
      await testCasesApi.update(tc.id, payload);
      setNoticeTone("success");
      setNotice(`${tc.test_case_id} saved.`);
      await loadData();
    } catch (saveError) {
      setError(messageFromError(saveError, "Could not save test case."));
    } finally {
      setSavingId(null);
    }
  }

  function enterStepsEdit(tc: TestCase) {
    setEditingStepsId(tc.id);
    setStepsDraft({
      preconditions: [...(tc.preconditions ?? [])],
      steps: (tc.steps ?? []).map((s) => ({ ...s })),
      expected_result: tc.expected_result ?? "",
    });
  }

  function cancelStepsEdit() {
    setEditingStepsId(null);
    setStepsDraft(null);
  }

  function renumberSteps(steps: StepsDraft["steps"]): StepsDraft["steps"] {
    return steps.map((s, i) => ({ ...s, step_number: i + 1 }));
  }

  function addPrecondition() {
    setStepsDraft((prev) => (prev ? { ...prev, preconditions: [...prev.preconditions, ""] } : prev));
  }

  function updatePrecondition(index: number, value: string) {
    setStepsDraft((prev) => {
      if (!prev) return prev;
      const preconditions = [...prev.preconditions];
      preconditions[index] = value;
      return { ...prev, preconditions };
    });
  }

  function removePrecondition(index: number) {
    setStepsDraft((prev) => (prev ? { ...prev, preconditions: prev.preconditions.filter((_, i) => i !== index) } : prev));
  }

  function addStep() {
    setStepsDraft((prev) =>
      prev ? { ...prev, steps: renumberSteps([...prev.steps, { step_number: 0, action: "", expected_result: "" }]) } : prev
    );
  }

  function updateStep(index: number, field: "action" | "expected_result", value: string) {
    setStepsDraft((prev) => {
      if (!prev) return prev;
      const steps = [...prev.steps];
      steps[index] = { ...steps[index], [field]: value };
      return { ...prev, steps };
    });
  }

  function removeStep(index: number) {
    setStepsDraft((prev) => (prev ? { ...prev, steps: renumberSteps(prev.steps.filter((_, i) => i !== index)) } : prev));
  }

  async function saveSteps(tc: TestCase) {
    if (!stepsDraft) return;
    setSavingSteps(true);
    setError("");
    setNotice("");
    try {
      await testCasesApi.update(tc.id, {
        preconditions: stepsDraft.preconditions.filter((p) => p.trim().length > 0),
        steps: stepsDraft.steps,
        expected_result: stepsDraft.expected_result,
      });
      setNoticeTone("success");
      setNotice(`${tc.test_case_id} steps saved.`);
      cancelStepsEdit();
      await loadData();
    } catch (saveError) {
      setError(messageFromError(saveError, "Could not save test case steps."));
    } finally {
      setSavingSteps(false);
    }
  }

  async function submitApproval(tc: TestCase) {
    if (!approvalChoice) return;
    if (approvalChoice === "reject" && !approvalNotes.trim()) {
      setError("Rejection requires a comment.");
      return;
    }
    setApprovalSubmitting(true);
    setError("");
    setNotice("");
    try {
      await testCasesApi.approve(tc.id, approvalChoice, approvalNotes.trim() || undefined);
      setNoticeTone("success");
      setNotice(`${tc.test_case_id} ${approvalChoice === "approve" ? "approved" : "rejected"}.`);
      setApprovalChoice(null);
      setApprovalNotes("");
      await loadData();
    } catch (approvalError) {
      setError(messageFromError(approvalError, "Could not submit approval."));
    } finally {
      setApprovalSubmitting(false);
    }
  }

  // GAP-4c: detect quality-gate blocks and let the user consciously override
  function qualityGateBlockMessage(err: unknown): string | null {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
    if (detail && typeof detail === "object" && (detail as { code?: string }).code === "quality_gate_blocked") {
      const d = detail as { message?: string; blocked_requirements?: Array<{ requirement_id?: string; title?: string; reasons?: string[] }> };
      const lines = (d.blocked_requirements ?? [])
        .map((b) => `• ${b.requirement_id ?? ""} ${b.title ?? ""}: ${(b.reasons ?? []).join(", ")}`)
        .join("\n");
      return `${d.message ?? "Some requirements failed the quality gate."}\n\n${lines}`;
    }
    return null;
  }

  async function generateCases(overrideQualityGate = false) {
    if (!selectedProject) return;
    setAgentRunning(true);
    setNotice("");
    setError("");
    try {
      const scenarioIds = selectedScenarioIds.length > 0 ? selectedScenarioIds : undefined;
      const reqIds = requirements.map((r) => r.id);
      const res = await testCasesApi.generateCases(selectedProject, scenarioIds, scenarioIds ? undefined : reqIds, overrideQualityGate);
      const data = res.data as Record<string, unknown>;
      const agentRunId = typeof data.agent_run_id === "number" ? data.agent_run_id : null;
      if (agentRunId) {
        setNoticeTone("info");
        setNotice("Test case generation is running...");
        for (let attempt = 0; attempt < 80; attempt += 1) {
          await sleep(attempt === 0 ? 1000 : 2000);
          const runRes = await agentRunsApi.get(agentRunId);
          const run = runRes.data;
          if (run.status === "failed") {
            setNotice("");
            setError(run.error_message || "Test case generation failed.");
            await loadData();
            return;
          }
          if (run.status === "completed") {
            const count = Number(run.output_data?.count ?? 0);
            await loadData();
            if (count > 0) {
              setNoticeTone("success");
              setNotice(`Generated ${count} test case${count === 1 ? "" : "s"}.`);
            } else {
              setNotice("");
              setError("Test case generation completed but produced 0 test cases. Check agent logs for provider errors or empty model output.");
            }
            return;
          }
          setNotice(run.progress_message ? `Test case generation: ${run.progress_message}` : "Test case generation is running...");
        }
        setNotice("");
        setError("Test case generation is still running. Check Agent Logs for the latest status.");
      } else {
        setNoticeTone("success");
        setNotice(String(data.message ?? "Test cases generated."));
      }
      await loadData();
    } catch (agentError) {
      const gateMessage = qualityGateBlockMessage(agentError);
      if (gateMessage && !overrideQualityGate) {
        setAgentRunning(false);
        const proceed = window.confirm(
          `${gateMessage}\n\nGenerate anyway? Test cases from low-quality requirements may be generic or incomplete.`
        );
        if (proceed) {
          await generateCases(true);
        } else {
          setError("Generation blocked by quality gate. Improve the requirement(s) and re-run the AI quality review.");
        }
        return;
      }
      setError(messageFromError(agentError, "Could not generate test cases."));
    } finally {
      setAgentRunning(false);
    }
  }

  async function syncJira(tc: TestCase) {
    setSavingId(tc.id);
    setError("");
    setNotice("");
    try {
      const res = await testCasesApi.syncJira(tc.id);
      setNoticeTone("info");
      setNotice(`Jira sync queued${res.data.sync_job_id ? `: ${res.data.sync_job_id}` : ""}.`);
      await loadData();
    } catch (syncError) {
      setError(messageFromError(syncError, "Could not queue Jira sync."));
    } finally {
      setSavingId(null);
    }
  }

  const filtered = useMemo(
    () =>
      testCases.filter((tc) => {
        const statusOk = filterStatus === "all" || tc.status === filterStatus;
        let modeOk: boolean;
        if (filterMode === "all") {
          modeOk = true;
        } else if (filterMode === "automation_ready") {
          modeOk = !!tc.automation_ready;
        } else if (filterMode === "pending_jira") {
          modeOk = tc.jira_sync_status === "pending";
        } else if (filterMode === "automation") {
          // "Automation" filter matches both the new canonical value and the legacy
          // "automated" rows so existing data still shows up under the new chip.
          modeOk = tc.execution_mode === "automation" || tc.execution_mode === "automated" || tc.execution_mode === "hybrid";
        } else {
          modeOk = tc.execution_mode === filterMode;
        }
        return statusOk && modeOk;
      }),
    [testCases, filterStatus, filterMode]
  );

  const scenarioCoveredByCases = useMemo(() => {
    const set = new Set<number>();
    testCases.forEach((tc) => {
      if (tc.linked_scenario_id != null) set.add(tc.linked_scenario_id);
      if (tc.scenario_id != null) set.add(tc.scenario_id);
    });
    return set;
  }, [testCases]);

  const testCaseReviewByScenarioId = useMemo(() => new Map(
    testCaseReviews.map((r) => [r.artifact_id, r])
  ), [testCaseReviews]);

  const total = summary?.total ?? testCases.length;
  const approved = summary?.by_status?.approved ?? 0;
  const draft = summary?.by_status?.draft ?? 0;
  const rejected = summary?.by_status?.rejected ?? 0;
  const blocked = summary?.by_status?.blocked ?? 0;
  const pending = summary?.by_status?.pending_approval ?? 0;
  const readyForAutomation =
    (summary?.by_automation_status?.ready_for_automation ?? 0)
    + (summary?.by_automation_status?.planned_for_automation ?? 0);
  // Backend's by_mode buckets are keyed by the stored value, so legacy rows live
  // under "automated"/"hybrid" while new rows live under "automation". Sum them
  // so the KPI reflects every automation-flavoured test case in one number.
  const automated =
    (summary?.by_mode?.automation ?? 0)
    + (summary?.by_mode?.automated ?? 0)
    + (summary?.by_mode?.hybrid ?? 0);
  const manual = summary?.by_mode?.manual ?? 0;

  const approvedPct = total > 0 ? ((approved / total) * 100).toFixed(1) : "0.0";
  const readyPct = total > 0 ? ((readyForAutomation / total) * 100).toFixed(1) : "0.0";
  const draftPct = total > 0 ? ((draft / total) * 100).toFixed(1) : "0.0";
  const manualPct = total > 0 ? ((manual / total) * 100).toFixed(1) : "0.0";
  const automatedPct = total > 0 ? ((automated / total) * 100).toFixed(1) : "0.0";
  const rejectedPct = total > 0 ? ((rejected / total) * 100).toFixed(1) : "0.0";
  const blockedPct = total > 0 ? ((blocked / total) * 100).toFixed(1) : "0.0";
  const mappingRequired = Math.max(0, readyForAutomation - automated);

  const cards = [
    {
      title: "Total Test Cases",
      icon: FileText,
      iconBg: "bg-blue-50 border-blue-100",
      iconColor: "text-blue-500",
      value: total.toLocaleString(),
      sublabel: "Total",
      footer: "100% of all test cases",
    },
    {
      title: "Approved",
      icon: ShieldCheck,
      iconBg: "bg-emerald-50 border-emerald-100",
      iconColor: "text-emerald-500",
      value: approved.toLocaleString(),
      sublabel: "Approved",
      footer: `${pending} Pending • ${approvedPct}% of total`,
    },
    {
      title: "Automation Ready",
      icon: Bot,
      iconBg: "bg-purple-50 border-purple-100",
      iconColor: "text-purple-500",
      value: readyForAutomation.toLocaleString(),
      sublabel: "Ready",
      footer: `${mappingRequired} Mapping Required • ${readyPct}%`,
    },
    {
      title: "Draft",
      icon: FileText,
      iconBg: "bg-amber-50 border-amber-100",
      iconColor: "text-amber-500",
      value: draft.toLocaleString(),
      sublabel: "Draft",
      footer: `${draftPct}% of total`,
    },
    {
      title: "Manual vs Automated",
      icon: Layers,
      iconBg: "bg-cyan-50 border-cyan-100",
      iconColor: "text-cyan-500",
      value: `${manual} / ${automated}`,
      sublabel: "",
      footer: `${manualPct}% Manual • ${automatedPct}% Automated`,
    },
    {
      title: "Rejected / Blocked",
      icon: AlertTriangle,
      iconBg: "bg-red-50 border-red-100",
      iconColor: "text-red-500",
      value: `${rejected} / ${blocked}`,
      sublabel: "",
      footer: `${rejectedPct}% Rejected • ${blockedPct}% Blocked`,
    },
  ];

  const visibleColumnConfigs = TEST_CASE_COLUMNS.filter((col) => visibleColumns.includes(col.key));
  // Prepend a fixed-width checkbox column for bulk selection. Width chosen to
  // line up with the column boundary the eye expects in the data rows below.
  const gridTemplateColumns = `28px ${visibleColumnConfigs.map((col) => col.width).join(" ")}`;
  const selectedPreset =
    Object.entries(VIEW_PRESETS).find(([, preset]) => preset.columns.length === visibleColumns.length && preset.columns.every((key) => visibleColumns.includes(key)))?.[0] ??
    "custom";

  function renderCell(column: ColumnConfig, tc: TestCase, draft: Draft) {
    switch (column.key) {
      case "id":
        return <span className="font-mono text-xs font-semibold text-[#1b59f8]" title={tc.test_case_id}>{tc.test_case_id}</span>;
      case "title":
        return (
          <div className="min-w-0 pr-2">
            <p className="truncate font-bold text-slate-800 text-xs" title={tc.title}>{tc.title}</p>
            <p className="truncate text-[10px] text-slate-400 mt-0.5" title={`${tc.linked_requirement_key || "Not linked"} / ${tc.test_type || "-"}`}>
              {tc.linked_requirement_key || "Not linked"} / {tc.test_type || "-"}
            </p>
          </div>
        );
      case "status":
        return (
          <Badge variant={
            draft.status === "approved" ? "success" :
            draft.status === "rejected" ? "destructive" :
            draft.status === "pending_approval" ? "warning" :
            draft.status === "automated" ? "purple" : "secondary"
          } className="capitalize">
            {draft.status}
          </Badge>
        );
      case "priority":
        return (
          <span className={cn(
            "inline-flex items-center text-[10px] font-bold px-2 py-0.5 rounded-full border shrink-0",
            draft.priority === "Critical" ? "text-red-700 bg-red-50 border-red-100" :
            draft.priority === "High" ? "text-orange-700 bg-orange-50 border-orange-100" :
            draft.priority === "Medium" ? "text-amber-700 bg-amber-50 border-amber-100" :
            "text-blue-700 bg-blue-50 border-blue-100"
          )}>
            {draft.priority}
          </span>
        );
      case "mode":
        return <span className="text-xs font-semibold text-slate-700">{modeDisplayLabel(draft.mode)}</span>;
      case "automation":
        return (
          <Badge variant={
            draft.automation_status === "automated" ? "success" :
            draft.automation_status === "ready_for_automation" ? "info" :
            draft.automation_status === "planned_for_automation" ? "info" :
            draft.automation_status === "awaiting_qa_approval" ? "warning" :
            draft.automation_status === "mapping_required" || draft.automation_status === "maintenance_required" ? "warning" :
            draft.automation_status === "automation_failed" ? "destructive" : "secondary"
          } className="truncate max-w-full">
            {automationStatusDisplayLabel(draft.automation_status)}
          </Badge>
        );
      case "jiraLink":
        return tc.jira_url ? (
          <a onClick={(e) => e.stopPropagation()} href={tc.jira_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs font-semibold text-[#1b59f8] hover:underline">
            {tc.jira_issue_key || "View"} <ExternalLink className="h-3 w-3" />
          </a>
        ) : <span className="text-xs text-slate-400">-</span>;
      case "actions":
        return (
          <Button 
            variant="outline" 
            size="sm" 
            onClick={(e) => { e.stopPropagation(); setSelectedTestCase(tc); }} 
            className="h-7 px-3 text-xs border-slate-200"
          >
            Details
            <ChevronRight className="h-3 w-3 text-slate-400" />
          </Button>
        );
      case "approvalStatus":
        return <Badge variant={tc.approval_status === "approved" ? "success" : "secondary"} className="capitalize">{tc.approval_status || "-"}</Badge>;
      case "eligible":
        return <span className="text-xs text-slate-600 capitalize font-medium">{draft.automation_eligible}</span>;
      case "automationReady":
        return (
          <Badge variant={draft.automation_ready ? "success" : "secondary"} className="capitalize">
            {draft.automation_ready ? "Ready" : "Not Ready"}
          </Badge>
        );
      case "tool":
        return <span className="text-xs text-slate-600 font-medium">{draft.external_tool || "-"}</span>;
      case "suiteId":
        return <span className="text-xs font-mono text-slate-500">{draft.suite_id || "-"}</span>;
      case "externalTc":
        return <span className="text-xs font-mono text-slate-500">{draft.external_tc_id || "-"}</span>;
      case "externalTcUrl":
        return draft.external_tc_url ? (
          <a onClick={(e) => e.stopPropagation()} href={draft.external_tc_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-[#1b59f8] hover:underline">
            Open Link <ExternalLink className="h-3 w-3" />
          </a>
        ) : <span className="text-xs text-slate-400">-</span>;
      case "jiraFinal":
        return <Badge variant={draft.jira_final_status === "passed" ? "success" : draft.jira_final_status === "failed" ? "destructive" : "secondary"}>{draft.jira_final_status || "-"}</Badge>;
      case "jiraSyncStatus":
        return (
          <Badge variant={
            tc.jira_sync_status === "synced" ? "success" :
            tc.jira_sync_status === "pending" || tc.jira_sync_status === "conflict" ? "warning" : "secondary"
          } className="capitalize">
            {tc.jira_sync_status}
          </Badge>
        );
      case "testPhase":
        return <span className="text-xs text-slate-600 font-medium">{draft.test_phase || "-"}</span>;
      case "testSuite":
        return <span className="text-xs text-slate-600 font-medium">{draft.test_suite_name || "-"}</span>;
      case "telecomDomain":
        return <span className="text-xs text-slate-600 font-medium">{draft.telecom_domain || "-"}</span>;
      case "linkedRequirement":
        return <span className="text-xs text-slate-500 truncate" title={tc.linked_requirement_key || "-"}>{tc.linked_requirement_key || "-"}</span>;
      case "lastAutomation":
        return <Badge variant={tc.last_automation_status === "passed" ? "success" : tc.last_automation_status === "failed" ? "destructive" : "secondary"}>{tc.last_automation_status || "not_run"}</Badge>;
      case "evidence":
        return tc.evidence_url ? (
          <a onClick={(e) => e.stopPropagation()} href={tc.evidence_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-[#1b59f8] hover:underline">
            Evidence <ExternalLink className="h-3 w-3" />
          </a>
        ) : <span className="text-xs text-slate-400">-</span>;
      case "createdBy":
        return (
          <span className="text-xs text-slate-700 font-semibold whitespace-nowrap">
            {tc.created_by ? resolveUser(tc.created_by) : "-"}
          </span>
        );
      case "updatedBy":
        return (
          <span className="text-xs text-slate-700 font-semibold whitespace-nowrap">
            {tc.updated_by ? resolveUser(tc.updated_by) : "-"}
          </span>
        );
      case "createdAt":
        return (
          <span className="text-xs text-slate-500 font-medium whitespace-nowrap">
            {tc.created_at
              ? new Date(tc.created_at).toLocaleString("en-US", {
                  year: "numeric",
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })
              : "-"}
          </span>
        );
      case "updatedAt":
        return (
          <span className="text-xs text-slate-500 font-medium whitespace-nowrap">
            {tc.updated_at
              ? new Date(tc.updated_at).toLocaleString("en-US", {
                  year: "numeric",
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })
              : "-"}
          </span>
        );
      default:
        return <span className="text-xs text-slate-400">-</span>;
    }
  }

  // Get current active draft for drawer
  const activeDraft = selectedTestCase ? drafts[selectedTestCase.id] : null;
  const busy = selectedTestCase ? savingId === selectedTestCase.id : false;
  const changed = selectedTestCase ? hasChanges(selectedTestCase) : false;

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Filter Headers ─────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
            <TestTube2 className="h-5 w-5 text-[#1b59f8]" />
            Test Case Library
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Manage test case metadata, automation eligible targets, and real-time Jira synchronizations
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadData} className="h-8 w-8 p-0 border-slate-200" title="Refresh">
            <RefreshCw className={cn("h-3.5 w-3.5 text-slate-500", loading && "animate-spin")} />
          </Button>
        </div>
      </div>

      {/* ── Status Counts Cards ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {cards.map((card) => {
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

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="flex-1 font-semibold">{error}</span>
          <button onClick={() => setError("")}><X className="h-4 w-4 text-red-400 hover:text-red-700" /></button>
        </div>
      )}
      {notice && (
        <div className={cn(
          "flex items-center gap-2 rounded-lg border px-4 py-3 text-xs",
          noticeTone === "success"
            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
            : "border-blue-200 bg-blue-50 text-blue-700"
        )}>
          {noticeTone === "success" ? <CheckCircle className="h-4 w-4 shrink-0" /> : <Loader2 className="h-4 w-4 shrink-0 animate-spin" />}
          <span className="flex-1 font-semibold">{notice}</span>
          <button onClick={() => setNotice("")}>
            <X className={cn("h-4 w-4", noticeTone === "success" ? "text-emerald-400 hover:text-emerald-700" : "text-blue-400 hover:text-blue-700")} />
          </button>
        </div>
      )}

      {/* ── AI Case Generator Action Card ─────────────────────────────────────── */}
      <Card className="border-slate-200 bg-white">
        <CardContent className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="h-9 w-9 shrink-0 flex items-center justify-center rounded-lg bg-indigo-50 border border-indigo-100">
              <Bot className="h-5 w-5 text-indigo-500" />
            </div>
            <div>
              <h3 className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                AI Agent Test Case Generator
              </h3>
              <p className="text-[10px] text-slate-400 mt-1 leading-relaxed">
                Scan requirement specifications to generate trace-mapped telecom scenarios automatically
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 self-end md:self-auto shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push(`/test-cases/command-center?project=${selectedProject}`)}
              className="h-8 text-xs border-slate-200 text-slate-700 bg-white"
            >
              <LayoutDashboard className="h-3.5 w-3.5 mr-1.5" />
              Command Center
            </Button>
            {scenarios.length > 0 && (
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => setShowSelector((v) => !v)}
                className="h-8 text-xs border-slate-200"
              >
                {selectedScenarioIds.length} scenario{selectedScenarioIds.length !== 1 && "s"}
                {showSelector ? <ChevronUp className="h-3.5 w-3.5 ml-1" /> : <ChevronDown className="h-3.5 w-3.5 ml-1" />}
              </Button>
            )}
            <Button
              variant="ai"
              size="sm"
              onClick={() => generateCases()}
              disabled={agentRunning || scenarios.length === 0}
              className="h-8 text-xs"
            >
              {agentRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              Generate Test Cases
            </Button>
            {filtered.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => exportToCSV(filtered)}
                className="h-8 text-xs border-slate-200"
              >
                <Download className="h-3.5 w-3.5" />
                Export CSV
              </Button>
            )}
          </div>
        </CardContent>
        {showSelector && (
          <div className="border-t border-slate-100 bg-slate-50/50">
            <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-2.5 bg-white">
              <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-slate-700">
                <input
                  type="checkbox"
                  className="rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8] h-3.5 w-3.5"
                  checked={scenarios.length > 0 && selectedScenarioIds.length === scenarios.length}
                  ref={(el) => {
                    if (el) el.indeterminate = selectedScenarioIds.length > 0 && selectedScenarioIds.length < scenarios.length;
                  }}
                  onChange={(e) => {
                    setSelectedScenarioIds(e.target.checked ? scenarios.map((s) => s.id) : []);
                  }}
                />
                {selectedScenarioIds.length === scenarios.length ? "Deselect All" : "Select All"}
              </label>
              <span className="text-[10px] font-bold text-slate-400">
                {selectedScenarioIds.length} of {scenarios.length} selected
              </span>
            </div>
            <div className="p-4 max-h-52 overflow-y-auto">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {scenarios.map((sc) => {
                const hasCases = scenarioCoveredByCases.has(sc.id);
                return (
                  <label key={sc.id} className="flex flex-col cursor-pointer gap-1.5 bg-white border border-slate-200 rounded-lg p-2.5 text-xs hover:bg-slate-50 transition-colors">
                    <div className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        checked={selectedScenarioIds.includes(sc.id)}
                        className="rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8] h-3.5 w-3.5"
                        onChange={() => setSelectedScenarioIds((prev) => prev.includes(sc.id) ? prev.filter((id) => id !== sc.id) : [...prev, sc.id])}
                      />
                      <span className="shrink-0 font-mono text-[10px] font-bold text-slate-500">{sc.scenario_id}</span>
                      <span className="truncate flex-1 font-semibold text-slate-700">{sc.title}</span>
                    </div>
                    <div className="flex items-center flex-wrap gap-2 pl-7">
                      <AuditStamp
                        createdAt={sc.created_at}
                        createdByName={resolveUser(sc.created_by ?? undefined)}
                        compact
                      />
                      <span className="text-slate-300">·</span>
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-bold",
                          hasCases
                            ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                            : "bg-slate-50 border-slate-200 text-slate-500"
                        )}
                        title={hasCases ? "Test cases have been generated for this scenario" : "No test cases generated yet"}
                      >
                        {hasCases ? (
                          <CheckCircle className="h-3 w-3" />
                        ) : (
                          <XCircle className="h-3 w-3" />
                        )}
                        Test Cases: {hasCases ? "Y" : "N"}
                      </span>
                    </div>
                  </label>
                );
              })}
            </div>
            </div>
          </div>
        )}
      </Card>

      {/* ── Table Filters, Presets, and Column Toggles ───────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          {/* Status Filters */}
          <div className="flex gap-1 rounded-lg border border-slate-200 bg-white p-1 shrink-0">
            {["all", "draft", "pending_approval", "approved", "rejected"].map((status) => (
              <button 
                key={status} 
                onClick={() => setFilterStatus(status)} 
                className={cn(
                  "rounded-md px-3 py-1 text-xs font-semibold capitalize transition-all",
                  filterStatus === status 
                    ? "bg-[#1b59f8] text-white shadow-sm" 
                    : "text-slate-500 hover:text-slate-900"
                )}
              >
                {status.replace(/_/g, " ")}
              </button>
            ))}
          </div>

          {/* Mode Filters — chip values stay snake_case so the URL/state remains stable;
              the filter predicate (above) also matches legacy "automated" rows when
              "automation" is selected so old data keeps showing up. */}
          <div className="flex gap-1 rounded-lg border border-slate-200 bg-white p-1 shrink-0">
            {["all", "manual", "automation", "ai", "automation_ready", "pending_jira"].map((mode) => (
              <button
                key={mode}
                onClick={() => setFilterMode(mode)}
                className={cn(
                  "rounded-md px-3 py-1 text-xs font-semibold capitalize transition-all",
                  filterMode === mode
                    ? "bg-[#1b59f8] text-white shadow-sm"
                    : "text-slate-500 hover:text-slate-900"
                )}
              >
                {mode === "ai" ? "AI" : mode.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </div>

        {/* View Presets & Column Controls */}
        <div className="relative flex flex-wrap items-center gap-2 self-start lg:self-auto shrink-0">
          <select
            value={selectedPreset}
            onChange={(e) => {
              const preset = VIEW_PRESETS[e.target.value];
              if (preset) {
                setVisibleColumns(preset.columns);
                setNoticeTone("success");
                setNotice(`${preset.label} applied.`);
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
            {Object.entries(VIEW_PRESETS).map(([key, preset]) => (
              <option key={key} value={key}>{preset.label}</option>
            ))}
          </select>

          <Button 
            variant="outline" 
            size="sm" 
            onClick={() => setShowColumns((v) => !v)} 
            className="h-8 text-xs border-slate-200 bg-white"
          >
            <Columns3 className="h-4 w-4 text-slate-500" />
            Columns
            <Badge variant="secondary" className="px-1.5 py-0 bg-slate-100 ml-1">{visibleColumns.length}</Badge>
          </Button>

          <span className="text-xs text-slate-400 font-semibold ml-2">
            {filtered.length} item{filtered.length !== 1 && "s"}
          </span>

          {/* Column Toggle Dropdown Popover */}
          {showColumns && (
            <>
              <div className="fixed inset-0 z-20" onClick={() => setShowColumns(false)} />
              <div className="absolute right-0 top-10 z-30 w-72 rounded-xl border border-slate-200 bg-white p-4 shadow-xl animate-fade-in select-none">
                <div className="mb-3.5 flex items-center justify-between">
                  <p className="text-xs font-bold text-slate-800">Column Configuration</p>
                  <button onClick={() => setShowColumns(false)} className="rounded p-1 text-slate-400 hover:bg-slate-50 hover:text-slate-600">
                    <XCircle className="h-4 w-4" />
                  </button>
                </div>
                
                <div className="mb-3.5 grid grid-cols-2 gap-2">
                  <button 
                    onClick={() => setVisibleColumns(TEST_CASE_COLUMNS.map((col) => col.key))} 
                    className="rounded-lg border border-slate-200 px-2 py-1.5 text-[10px] font-bold text-slate-600 hover:bg-slate-50"
                  >
                    Select All
                  </button>
                  <button 
                    onClick={() => setVisibleColumns(DEFAULT_COLUMN_KEYS)} 
                    className="inline-flex items-center justify-center gap-1 rounded-lg border border-slate-200 px-2 py-1.5 text-[10px] font-bold text-slate-600 hover:bg-slate-50"
                  >
                    <RotateCcw className="h-3 w-3" />Reset Defaults
                  </button>
                </div>

                <label className="mb-3.5 flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 bg-slate-50 cursor-pointer">
                  Compact Padding Layout
                  <input 
                    type="checkbox" 
                    checked={compactView} 
                    className="rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8]" 
                    onChange={(e) => setCompactView(e.target.checked)} 
                  />
                </label>

                <div className="max-h-60 space-y-3.5 overflow-y-auto pr-1">
                  {(["core", "advanced"] as const).map((group) => (
                    <div key={group}>
                      <p className="mb-1.5 text-[9px] font-bold uppercase tracking-wider text-slate-400">
                        {group === "core" ? "Recommended Fields" : "Advanced Details"}
                      </p>
                      <div className="space-y-1">
                        {TEST_CASE_COLUMNS.filter((col) => col.group === group).map((col) => (
                          <label key={col.key} className="flex cursor-pointer items-center justify-between rounded-lg px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition-colors">
                            <span className="font-medium">{col.label}</span>
                            <input
                              type="checkbox"
                              checked={visibleColumns.includes(col.key)}
                              disabled={col.required}
                              className="rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8]"
                              onChange={() => toggleColumn(col)}
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

      {/* ── Test Cases Compact Table View ────────────────────────────────────────── */}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <div style={{ minWidth: visibleColumns.length > DEFAULT_COLUMN_KEYS.length ? `${visibleColumnConfigs.length * 115 + 400}px` : "980px" }}>
          {/* Header Row */}
          <div
            className="grid gap-2 border-b border-slate-200 bg-slate-50/70 px-4 py-2.5 text-[10px] font-bold uppercase tracking-wider text-slate-400"
            style={{ gridTemplateColumns }}
          >
            <span className="flex items-center" title="Select all rows currently visible">
              <input
                type="checkbox"
                ref={(node) => {
                  if (!node) return;
                  // Show the indeterminate dash when *some but not all* visible rows are selected.
                  const visibleIds = filtered.map((tc) => tc.id);
                  const selectedHere = visibleIds.filter((id) => selectedTcIds.has(id)).length;
                  node.indeterminate = selectedHere > 0 && selectedHere < visibleIds.length;
                }}
                checked={filtered.length > 0 && filtered.every((tc) => selectedTcIds.has(tc.id))}
                onChange={(e) => {
                  const next = new Set(selectedTcIds);
                  if (e.target.checked) filtered.forEach((tc) => next.add(tc.id));
                  else filtered.forEach((tc) => next.delete(tc.id));
                  setSelectedTcIds(next);
                }}
                className="h-3.5 w-3.5 rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8] cursor-pointer"
              />
            </span>
            {visibleColumnConfigs.map((col) => (
              <span key={col.key} className="truncate" title={col.label}>{col.label}</span>
            ))}
          </div>

          {/* Table Body */}
          {loading ? (
            <div className="flex items-center justify-center py-20 text-xs font-semibold text-slate-400">
              <Loader2 className="mr-2 h-4 w-4 animate-spin text-[#1b59f8]" />
              Fetching test case library datasets...
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-20 text-center text-xs font-semibold text-slate-400">
              No test cases found matching selected project or filter query.
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {filtered.map((tc) => {
                const draft = drafts[tc.id] ?? toDraft(tc);
                const hasEdits = hasChanges(tc);
                const isChecked = selectedTcIds.has(tc.id);
                return (
                  <div
                    key={tc.id}
                    onClick={() => setSelectedTestCase(tc)}
                    className={cn(
                      "grid items-center gap-2 px-4 transition-colors hover:bg-slate-50/50 cursor-pointer select-none",
                      compactView ? "py-1.5" : "py-2.5",
                      selectedTestCase?.id === tc.id && "bg-[#1b59f8]/5 hover:bg-[#1b59f8]/5",
                      isChecked && "bg-[#1b59f8]/5",
                      hasEdits && "bg-amber-50/30 hover:bg-amber-50/40"
                    )}
                    style={{ gridTemplateColumns }}
                  >
                    <span
                      className="flex items-center"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={(e) => {
                          const next = new Set(selectedTcIds);
                          if (e.target.checked) next.add(tc.id); else next.delete(tc.id);
                          setSelectedTcIds(next);
                        }}
                        className="h-3.5 w-3.5 rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8] cursor-pointer"
                        title={`Select ${tc.test_case_id}`}
                      />
                    </span>
                    {visibleColumnConfigs.map((col) => (
                      <div key={col.key} className="min-w-0 overflow-hidden text-xs text-slate-600 font-medium">
                        {renderCell(col, tc, draft)}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Right-Side Detail Drawer (Sliding attributes form) ─────────────────── */}
      <Drawer open={selectedTestCase !== null} onOpenChange={(open) => { if (!open) setSelectedTestCase(null); }}>
        <DrawerContent size="lg">
          {selectedTestCase && activeDraft && (
            <>
              <DrawerHeader>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-[#1b59f8]">
                      {selectedTestCase.test_case_id}
                    </span>
                    {(selectedTestCase.scenario_id ?? selectedTestCase.linked_scenario_id) != null && selectedProject && (
                      <ReviewBadge
                        review={testCaseReviewByScenarioId.get(
                          (selectedTestCase.scenario_id ?? selectedTestCase.linked_scenario_id) as number
                        )}
                        artifactType="scenario_test_case_coverage"
                        artifactId={(selectedTestCase.scenario_id ?? selectedTestCase.linked_scenario_id) as number}
                        projectId={selectedProject}
                      />
                    )}
                    {hasChanges(selectedTestCase) && (
                      <span className="inline-flex items-center rounded bg-amber-50 border border-amber-200 px-1.5 py-0.5 text-[9px] font-bold text-amber-700 uppercase tracking-wider">
                        Unsaved Edits
                      </span>
                    )}
                  </div>
                  <DrawerTitle className="mt-1.5 truncate text-slate-800" title={selectedTestCase.title}>
                    {selectedTestCase.title}
                  </DrawerTitle>
                  <DrawerDescription>
                    Approve or reject the case here. Use Details to edit metadata anytime.
                  </DrawerDescription>
                </div>
                <DrawerClose asChild>
                  <button 
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-50 hover:text-slate-600 focus:outline-none"
                  >
                    <X className="h-4.5 w-4.5" />
                  </button>
                </DrawerClose>
              </DrawerHeader>

              {/* Drawer Tabs */}
              <div className="flex border-b border-slate-100 px-4 shrink-0 bg-slate-50/50">
                {(["approval", "steps", "details", "history"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setDrawerTab(tab)}
                    className={cn(
                      "px-4 py-2.5 text-xs font-semibold capitalize border-b-2 -mb-px transition-colors focus:outline-none",
                      drawerTab === tab
                        ? "border-[#1b59f8] text-[#1b59f8]"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    )}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              {/* Drawer Content Body */}
              <DrawerBody className="p-5">
                {/* TAB 1: APPROVAL (mirrors Test Plan / Scenario simplicity) */}
                {drawerTab === "approval" && (
                  <div className="space-y-5">
                    {/* Current status summary — read-only chips */}
                    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                          Current State
                        </span>
                        <Badge
                          variant={
                            selectedTestCase.status === "approved" ? "success" :
                            selectedTestCase.status === "rejected" ? "destructive" :
                            selectedTestCase.status === "pending_approval" ? "warning" :
                            selectedTestCase.status === "automated" ? "purple" : "secondary"
                          }
                          className="capitalize"
                        >
                          {selectedTestCase.status.replace(/_/g, " ")}
                        </Badge>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-600 font-medium">
                        <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5">
                          Priority: <span className="font-bold capitalize text-slate-800">{selectedTestCase.priority}</span>
                        </span>
                        <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5">
                          Mode: <span className="font-bold text-slate-800">{modeDisplayLabel(selectedTestCase.execution_mode || selectedTestCase.mode)}</span>
                        </span>
                        <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5">
                          Automation: <span className="font-bold text-slate-800">{automationStatusDisplayLabel(selectedTestCase.automation_status || "not_required")}</span>
                        </span>
                      </div>
                      {(() => {
                        const meta = (selectedTestCase as unknown as { metadata_?: Record<string, unknown> | null }).metadata_;
                        const lastNote = meta && typeof meta === "object" ? meta.review_notes : null;
                        if (!lastNote) return null;
                        return (
                          <div className="rounded-lg border border-slate-100 bg-slate-50/70 p-2.5 text-[11px] text-slate-600 leading-relaxed">
                            <span className="font-bold text-slate-500 uppercase text-[9px] tracking-wider block mb-1">Last Review Note</span>
                            {String(lastNote)}
                          </div>
                        );
                      })()}
                    </div>

                    {/* Decision panel — only shown while the case is awaiting a decision */}
                    {(selectedTestCase.status === "draft" || selectedTestCase.status === "pending_approval") ? (
                      <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                          Approval Decision
                        </span>
                        <div className="grid grid-cols-2 gap-2">
                          <button
                            type="button"
                            onClick={() => setApprovalChoice(approvalChoice === "approve" ? null : "approve")}
                            className={cn(
                              "flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-bold transition-colors",
                              approvalChoice === "approve"
                                ? "border-emerald-400 bg-emerald-50 text-emerald-700"
                                : "border-slate-200 bg-white text-slate-600 hover:bg-emerald-50 hover:text-emerald-700 hover:border-emerald-200"
                            )}
                          >
                            <CheckCircle className="h-4 w-4" />
                            Approve
                          </button>
                          <button
                            type="button"
                            onClick={() => setApprovalChoice(approvalChoice === "reject" ? null : "reject")}
                            className={cn(
                              "flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-bold transition-colors",
                              approvalChoice === "reject"
                                ? "border-rose-400 bg-rose-50 text-rose-700"
                                : "border-slate-200 bg-white text-slate-600 hover:bg-rose-50 hover:text-rose-700 hover:border-rose-200"
                            )}
                          >
                            <XCircle className="h-4 w-4" />
                            Reject
                          </button>
                        </div>

                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                            Notes {approvalChoice === "reject" && <span className="text-red-500 font-bold">*</span>}
                          </label>
                          <textarea
                            value={approvalNotes}
                            onChange={(e) => setApprovalNotes(e.target.value)}
                            className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] min-h-16"
                            placeholder={
                              approvalChoice === "reject"
                                ? "Explain why this test case is being rejected..."
                                : "Optional review comments..."
                            }
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-xl border border-slate-200 bg-slate-50/40 p-4 space-y-2 text-xs text-slate-600">
                        <p className="font-semibold text-slate-700">
                          This test case is already <span className="capitalize">{selectedTestCase.status.replace(/_/g, " ")}</span>.
                        </p>
                        <p className="text-[11px] text-slate-500 leading-relaxed">
                          Switch to the <span className="font-bold text-slate-700">Details</span> tab to edit
                          execution mode, automation setup, classification, or Jira fields. The status can only
                          be changed through a new approval action.
                        </p>
                      </div>
                    )}

                    {/* Audit trail */}
                    <div className="flex flex-col gap-1.5">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        Audit Trail
                      </label>
                      <AuditStamp
                        createdAt={selectedTestCase.created_at}
                        updatedAt={selectedTestCase.updated_at}
                        createdByName={resolveUser(selectedTestCase.created_by ?? undefined)}
                        updatedByName={resolveUser(selectedTestCase.updated_by ?? undefined)}
                      />
                    </div>
                  </div>
                )}

                {/* TAB: DETAILS — full attribute editor, grouped */}
                {drawerTab === "details" && (
                  <div className="space-y-6">
                    {/* Classification */}
                    <section className="space-y-3">
                      <h4 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                        <Layers className="h-3 w-3" />
                        Classification
                      </h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Priority</label>
                          <select
                            value={activeDraft.priority}
                            onChange={(e) => updateDraft(selectedTestCase.id, { priority: e.target.value })}
                            className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                          >
                            {PRIORITY_OPTIONS.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                          </select>
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Execution Mode</label>
                          <select
                            value={MODE_OPTIONS.some((o) => o.value === activeDraft.mode) ? activeDraft.mode : ""}
                            onChange={(e) => {
                              const val = e.target.value;
                              // Anything other than "manual" means "this test case is in scope for some
                              // form of automation" — Automation and AI both flip eligible→yes.
                              const isAutoFlavour = val === "automation" || val === "ai";
                              const wasIneligibleSentinel = activeDraft.automation_status === "not_required" || activeDraft.automation_status === "mapping_required" || activeDraft.automation_status === "not_automated";
                              updateDraft(selectedTestCase.id, {
                                mode: val,
                                automation_eligible: val === "manual" ? "no" : isAutoFlavour ? "yes" : activeDraft.automation_eligible,
                                automation_status: val === "manual"
                                  ? "not_required"
                                  : isAutoFlavour && wasIneligibleSentinel
                                    ? "planned_for_automation"
                                    : activeDraft.automation_status,
                                automation_ready: val === "manual" ? false : activeDraft.automation_ready,
                              });
                            }}
                            className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                          >
                            {/* Render a disabled "legacy" placeholder so a TC stored with an older value
                                ("automated" / "hybrid") still shows a meaningful label and the select
                                doesn't fall back to the first option. */}
                            {!MODE_OPTIONS.some((o) => o.value === activeDraft.mode) && activeDraft.mode && (
                              <option value="" disabled>{modeDisplayLabel(activeDraft.mode)}</option>
                            )}
                            {MODE_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                          </select>
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Telecom Domain</label>
                          <select
                            value={activeDraft.telecom_domain}
                            onChange={(e) => updateDraft(selectedTestCase.id, { telecom_domain: e.target.value })}
                            className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                          >
                            {DOMAIN_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                          </select>
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Test Environment</label>
                          <select
                            value={activeDraft.test_phase}
                            onChange={(e) => updateDraft(selectedTestCase.id, { test_phase: e.target.value })}
                            className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                          >
                            {PHASE_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                          </select>
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Test Suite</label>
                          <input
                            list="test-suite-options"
                            value={activeDraft.test_suite_name}
                            onChange={(e) => updateDraft(selectedTestCase.id, { test_suite_name: e.target.value })}
                            placeholder="Type to select or create…"
                            className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                          />
                          <datalist id="test-suite-options">
                            {suites.map((s) => <option key={s.id} value={s.name} />)}
                          </datalist>
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Product Group</label>
                          <select
                            value={activeDraft.product_group || ""}
                            onChange={(e) => updateDraft(selectedTestCase.id, { product_group: e.target.value })}
                            className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                          >
                            {PRODUCT_GROUP_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                          </select>
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Product</label>
                          <select
                            value={activeDraft.product || ""}
                            onChange={(e) => updateDraft(selectedTestCase.id, { product: e.target.value })}
                            className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                          >
                            {PRODUCT_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                          </select>
                        </div>
                        <div className="flex flex-col gap-1 md:col-span-2">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Sub Request Type</label>
                          <select
                            value={activeDraft.sub_request_type || ""}
                            onChange={(e) => updateDraft(selectedTestCase.id, { sub_request_type: e.target.value })}
                            className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                          >
                            {SUB_REQUEST_TYPE_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                          </select>
                        </div>
                      </div>
                    </section>

                    {/* Automation Setup */}
                    {(() => {
                      // "Internal" tools — scripts live inside the platform, so the external
                      // identifiers (suite_id / external_tc_id / external_tc_url) are managed
                      // by the script generator and should not be hand-edited.
                      const isInternalTool = activeDraft.external_tool === "Playwright" || activeDraft.external_tool === "Pytest";
                      // automation_eligible is auto-derived from mode on the mode-change handler
                      // and on save — the UI no longer surfaces it as a separate dropdown.
                      const automationDisabled = activeDraft.mode === "manual";
                      return (
                        <section className="space-y-3">
                          <h4 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                            <Bot className="h-3 w-3" />
                            Automation Setup
                          </h4>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div className="flex flex-col gap-1">
                              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Automation Status</label>
                              <select
                                value={AUTOMATION_STATUS_OPTIONS.some((o) => o.value === activeDraft.automation_status) ? activeDraft.automation_status : ""}
                                disabled={automationDisabled}
                                onChange={(e) => updateDraft(selectedTestCase.id, { automation_status: e.target.value })}
                                className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] disabled:opacity-50"
                              >
                                {/* Legacy stored values shown as a disabled placeholder so the
                                    historical state stays visible until the user picks a new option. */}
                                {!AUTOMATION_STATUS_OPTIONS.some((o) => o.value === activeDraft.automation_status) && activeDraft.automation_status && (
                                  <option value="" disabled>{automationStatusDisplayLabel(activeDraft.automation_status)}</option>
                                )}
                                {AUTOMATION_STATUS_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                              </select>
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                Application
                              </label>
                              <select
                                value={activeDraft.application_id ?? ""}
                                onChange={(e) => updateDraft(selectedTestCase.id, { application_id: e.target.value ? Number(e.target.value) : null })}
                                className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                              >
                                <option value="">
                                  {applications.find((a) => a.is_default)?.name
                                    ? `Default (${applications.find((a) => a.is_default)!.name})`
                                    : "Default"}
                                </option>
                                {applications.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                              </select>
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External Tool</label>
                              <select
                                value={activeDraft.external_tool}
                                disabled={automationDisabled}
                                onChange={(e) => {
                                  const val = e.target.value;
                                  // When switching to an internal tool, clear external identifiers
                                  // (they'll be populated by the script generator). When switching
                                  // FROM an internal tool to an external one, keep whatever is there
                                  // so users can paste in mappings.
                                  const becameInternal = val === "Playwright" || val === "Pytest";
                                  updateDraft(selectedTestCase.id, {
                                    external_tool: val,
                                    suite_id: becameInternal ? "" : activeDraft.suite_id,
                                    external_tc_id: becameInternal ? "" : activeDraft.external_tc_id,
                                    external_tc_url: becameInternal ? "" : activeDraft.external_tc_url,
                                  });
                                }}
                                className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] disabled:opacity-50"
                              >
                                {TOOL_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                              </select>
                            </div>

                            {/* Internal-tool helper banner. Shown above the three identifier
                                inputs when External Tool is Playwright/Pytest. Inputs below
                                stay rendered (so the values are still visible) but become
                                read-only with a muted look. */}
                            {isInternalTool && (
                              <div className="md:col-span-2 flex items-start gap-2 rounded-md border border-blue-100 bg-blue-50/60 px-3 py-2 text-[11px] text-blue-800">
                                <Bot className="h-3.5 w-3.5 mt-0.5 shrink-0 text-blue-500" />
                                <span>
                                  Suite ID, External TC ID and URL are managed internally for {activeDraft.external_tool} scripts —
                                  they&apos;re auto-populated by the script generator and can&apos;t be edited here.
                                </span>
                              </div>
                            )}

                            <div className="flex flex-col gap-1">
                              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Suite ID</label>
                              <input
                                type="text"
                                value={activeDraft.suite_id}
                                disabled={automationDisabled || isInternalTool}
                                readOnly={isInternalTool}
                                onChange={(e) => updateDraft(selectedTestCase.id, { suite_id: e.target.value })}
                                className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] disabled:opacity-50 disabled:cursor-not-allowed"
                                placeholder={isInternalTool ? "Managed internally" : "e.g. suite_102"}
                              />
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External TC ID</label>
                              <input
                                type="text"
                                value={activeDraft.external_tc_id}
                                disabled={automationDisabled || isInternalTool}
                                readOnly={isInternalTool}
                                onChange={(e) => updateDraft(selectedTestCase.id, { external_tc_id: e.target.value })}
                                className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] disabled:opacity-50 disabled:cursor-not-allowed"
                                placeholder={isInternalTool ? "Managed internally" : "e.g. tc_5021"}
                              />
                            </div>
                            <div className="md:col-span-2 flex flex-col gap-1">
                              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External TC URL</label>
                              <input
                                type="text"
                                value={activeDraft.external_tc_url}
                                disabled={automationDisabled || isInternalTool}
                                readOnly={isInternalTool}
                                onChange={(e) => updateDraft(selectedTestCase.id, { external_tc_url: e.target.value })}
                                className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] disabled:opacity-50 disabled:cursor-not-allowed"
                                placeholder={isInternalTool ? "Managed internally" : "https://testrail.example.com/tc/5021"}
                              />
                            </div>

                            <div className="md:col-span-2 flex items-center pt-1">
                              <label className="flex items-center gap-2.5 text-xs font-semibold text-slate-700 cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={activeDraft.automation_ready}
                                  disabled={automationDisabled}
                                  className="rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8] h-4 w-4 disabled:opacity-50"
                                  onChange={(e) => updateDraft(selectedTestCase.id, { automation_ready: e.target.checked })}
                                />
                                <span>
                                  Automation Execution Ready
                                  <span className="ml-1.5 text-[10px] font-normal text-slate-400">— gates whether CI is allowed to run this test unattended</span>
                                </span>
                              </label>
                            </div>
                          </div>
                        </section>
                      );
                    })()}

                    {/* Jira */}
                    <section className="space-y-3">
                      <h4 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                        <ShieldCheck className="h-3 w-3" />
                        Jira
                      </h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Jira Final Status</label>
                          <select
                            value={activeDraft.jira_final_status}
                            onChange={(e) => updateDraft(selectedTestCase.id, { jira_final_status: e.target.value })}
                            className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                          >
                            {JIRA_STATUS_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                          </select>
                        </div>
                      </div>
                    </section>

                    {/* Internal comment */}
                    <section className="space-y-2">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Internal Comment
                      </label>
                      <textarea
                        value={activeDraft.comment}
                        onChange={(e) => updateDraft(selectedTestCase.id, { comment: e.target.value })}
                        className="w-full rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] min-h-16"
                        placeholder="Optional context for this metadata change..."
                      />
                    </section>
                  </div>
                )}

                {/* TAB 2: TEST STEPS */}
                {drawerTab === "steps" && (
                  <div className="space-y-4">
                    {/* Linked Requirement Info */}
                    <div className="bg-slate-50 rounded-xl p-3 border border-slate-100 flex items-start gap-2 text-xs">
                      <Info className="h-4.5 w-4.5 text-slate-500 shrink-0 mt-0.5" />
                      <div>
                        <p className="font-bold text-slate-800">Linked Requirement</p>
                        <p className="text-slate-500 mt-1 font-medium">
                          {selectedTestCase.linked_requirement_key ? `${selectedTestCase.linked_requirement_key} - Associated spec verified` : "No requirement link mapped for this test case"}
                        </p>
                      </div>
                    </div>

                    {editingStepsId === selectedTestCase.id && stepsDraft ? (
                      <>
                        {/* Preconditions — edit mode */}
                        <div className="space-y-1.5">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Preconditions</label>
                          <div className="space-y-1.5">
                            {stepsDraft.preconditions.map((prec, i) => (
                              <div key={i} className="flex items-center gap-1.5">
                                <input
                                  type="text"
                                  value={prec}
                                  onChange={(e) => updatePrecondition(i, e.target.value)}
                                  className="flex-1 rounded-lg border border-slate-200 bg-white p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                                  placeholder="Precondition text..."
                                />
                                <button
                                  type="button"
                                  onClick={() => removePrecondition(i)}
                                  className="shrink-0 rounded-lg border border-slate-200 p-2 text-slate-400 hover:text-red-600 hover:border-red-200"
                                  title="Remove precondition"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              </div>
                            ))}
                            <button
                              type="button"
                              onClick={addPrecondition}
                              className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#1b59f8] hover:underline"
                            >
                              <Plus className="h-3.5 w-3.5" /> Add precondition
                            </button>
                          </div>
                        </div>

                        {/* Steps — edit mode */}
                        <div className="space-y-1.5">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Steps</label>
                          <div className="space-y-2">
                            {stepsDraft.steps.map((step, i) => (
                              <div key={i} className="rounded-xl border border-slate-200 p-2.5 space-y-1.5">
                                <div className="flex items-center justify-between">
                                  <span className="text-[10px] font-bold text-slate-400">Step {step.step_number}</span>
                                  <button
                                    type="button"
                                    onClick={() => removeStep(i)}
                                    className="text-slate-400 hover:text-red-600"
                                    title="Remove step"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </button>
                                </div>
                                <textarea
                                  value={step.action}
                                  onChange={(e) => updateStep(i, "action", e.target.value)}
                                  className="w-full rounded-lg border border-slate-200 bg-white p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] min-h-14"
                                  placeholder="Action..."
                                />
                                <textarea
                                  value={step.expected_result}
                                  onChange={(e) => updateStep(i, "expected_result", e.target.value)}
                                  className="w-full rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-600 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] min-h-14"
                                  placeholder="Expected result..."
                                />
                              </div>
                            ))}
                            <button
                              type="button"
                              onClick={addStep}
                              className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#1b59f8] hover:underline"
                            >
                              <Plus className="h-3.5 w-3.5" /> Add step
                            </button>
                          </div>
                        </div>

                        {/* Overall expected result — edit mode */}
                        <div className="space-y-1.5">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Overall Expected Result</label>
                          <textarea
                            value={stepsDraft.expected_result}
                            onChange={(e) => setStepsDraft((prev) => (prev ? { ...prev, expected_result: e.target.value } : prev))}
                            className="w-full rounded-lg border border-slate-200 bg-white p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] min-h-16"
                          />
                        </div>
                      </>
                    ) : (
                      <>
                        {/* Preconditions — read only */}
                        {selectedTestCase.preconditions && selectedTestCase.preconditions.length > 0 && (
                          <div className="space-y-1.5">
                            <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Preconditions</label>
                            <ul className="list-disc list-inside space-y-1 bg-slate-50/30 p-2.5 rounded-lg border border-slate-100 text-xs text-slate-600 font-medium">
                              {selectedTestCase.preconditions.map((prec, i) => (
                                <li key={i}>{prec}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Steps Table — read only */}
                        <div className="space-y-1.5">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Steps</label>
                          {selectedTestCase.steps && selectedTestCase.steps.length > 0 ? (
                            <div className="overflow-hidden rounded-xl border border-slate-200">
                              <div className="grid grid-cols-[50px_1fr_1fr] bg-slate-50 border-b border-slate-200 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                <span>Step</span>
                                <span>Action</span>
                                <span>Expected Result</span>
                              </div>
                              <div className="divide-y divide-slate-100 bg-white">
                                {selectedTestCase.steps.map((step, idx) => (
                                  <div key={`${step.step_number}-${idx}`} className="grid grid-cols-[50px_1fr_1fr] px-3 py-2.5 text-xs text-slate-600 font-medium">
                                    <span className="text-slate-400 font-bold">{step.step_number}</span>
                                    <span className="pr-3 break-words leading-relaxed">{step.action}</span>
                                    <span className="break-words text-slate-500 leading-relaxed">{step.expected_result}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : (
                            <p className="text-xs text-slate-400 font-medium italic p-2 bg-slate-50/50 rounded border">No structured steps provided for this test case.</p>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                )}

                {/* TAB 3: AUDIT & JIRA HISTORY */}
                {drawerTab === "history" && (
                  <div className="space-y-4">
                    {/* Integration status */}
                    <div className="bg-slate-50 rounded-xl p-3 border border-slate-100 space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-700">Jira Sync Status:</span>
                        <Badge variant={selectedTestCase.jira_sync_status === "synced" ? "success" : "warning"} className="capitalize">
                          {selectedTestCase.jira_sync_status}
                        </Badge>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-700">Last Synced:</span>
                        <span className="text-slate-500 font-medium">
                          {selectedTestCase.jira_last_synced_at ? new Date(selectedTestCase.jira_last_synced_at).toLocaleString() : "Never"}
                        </span>
                      </div>
                      {selectedTestCase.jira_sync_error && (
                        <div className="rounded border border-red-200 bg-red-50 p-2.5 text-[11px] text-red-700 font-medium break-words mt-2">
                          {selectedTestCase.jira_sync_error}
                        </div>
                      )}
                    </div>

                    {/* Timeline */}
                    <div className="space-y-2">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Change Log Timeline</label>
                      {historyLoading ? (
                        <div className="flex items-center justify-center py-8 text-xs text-slate-400">
                          <Loader2 className="mr-2 h-4 w-4 animate-spin text-[#1b59f8]" />
                          Retrieving change logs...
                        </div>
                      ) : historyRows.length === 0 ? (
                        <p className="text-xs text-slate-400 font-medium italic p-2 bg-slate-50/50 rounded border">No changes recorded for this test case.</p>
                      ) : (
                        <div className="space-y-2">
                          {historyRows.map((row) => (
                            <div key={row.id} className="rounded-lg border border-slate-200 p-3 text-xs bg-white space-y-1.5 shadow-sm">
                              <div className="flex flex-wrap items-center justify-between gap-1">
                                <Badge variant="info" className="text-[10px] font-semibold">{row.field_name}</Badge>
                                <span className="text-[10px] text-slate-400 font-medium">{new Date(row.created_at).toLocaleString()}</span>
                              </div>
                              <p className="text-[11px] text-slate-500 font-medium break-all">
                                {row.old_value || "-"} → <span className="font-bold text-slate-800">{row.new_value || "-"}</span>
                              </p>
                              {row.comment && (
                                <p className="text-[10px] text-slate-400 border-t border-slate-50 pt-1 mt-1 font-semibold italic">
                                  Comment: {row.comment}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </DrawerBody>

              <DrawerFooter>
                <DrawerClose asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 px-4 text-xs border-slate-200"
                  >
                    Close
                  </Button>
                </DrawerClose>

                {drawerTab === "approval" && (selectedTestCase.status === "draft" || selectedTestCase.status === "pending_approval") && (
                  <Button
                    variant="default"
                    size="sm"
                    disabled={
                      approvalSubmitting ||
                      !approvalChoice ||
                      (approvalChoice === "reject" && !approvalNotes.trim())
                    }
                    onClick={() => submitApproval(selectedTestCase)}
                    className="h-9 px-4 text-xs gap-1 font-semibold"
                  >
                    {approvalSubmitting
                      ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      : approvalChoice === "reject"
                        ? <XCircle className="h-3.5 w-3.5" />
                        : <CheckCircle className="h-3.5 w-3.5" />}
                    {approvalChoice === "reject" ? "Submit Rejection" : "Submit Approval"}
                  </Button>
                )}

                {drawerTab === "approval" && !(selectedTestCase.status === "draft" || selectedTestCase.status === "pending_approval") && (
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() => setDrawerTab("details")}
                    className="h-9 px-4 text-xs gap-1 font-semibold"
                  >
                    <FileText className="h-3.5 w-3.5" />
                    Edit Details
                  </Button>
                )}

                {drawerTab === "details" && (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy || !selectedTestCase.jira_issue_key}
                      onClick={() => syncJira(selectedTestCase)}
                      className="h-9 px-4 text-xs gap-1 border-slate-200 font-semibold"
                    >
                      <ShieldCheck className="h-3.5 w-3.5" />
                      Sync Jira
                    </Button>
                    <Button
                      variant="default"
                      size="sm"
                      disabled={busy || !changed}
                      onClick={() => saveTestCase(selectedTestCase)}
                      className="h-9 px-4 text-xs gap-1 font-semibold"
                    >
                      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                      Save Changes
                    </Button>
                  </>
                )}

                {drawerTab === "steps" && editingStepsId !== selectedTestCase.id && (
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() => enterStepsEdit(selectedTestCase)}
                    className="h-9 px-4 text-xs gap-1 font-semibold"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                    Edit Steps
                  </Button>
                )}

                {drawerTab === "steps" && editingStepsId === selectedTestCase.id && (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={savingSteps}
                      onClick={cancelStepsEdit}
                      className="h-9 px-4 text-xs gap-1 border-slate-200 font-semibold"
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="default"
                      size="sm"
                      disabled={savingSteps}
                      onClick={() => saveSteps(selectedTestCase)}
                      className="h-9 px-4 text-xs gap-1 font-semibold"
                    >
                      {savingSteps ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                      Save Steps
                    </Button>
                  </>
                )}
              </DrawerFooter>
            </>
          )}
        </DrawerContent>
      </Drawer>

      {/* ── Floating Bulk Edit action bar ─────────────────────────────────────
          Surfaces when at least one test case is selected. Shows the count and
          opens the preview-confirm dialog. */}
      {selectedTcIds.size > 0 && !bulkEditOpen && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-30">
          <div className="flex items-center gap-3 rounded-full border border-slate-200 bg-white px-4 py-2 shadow-xl">
            <span className="text-xs font-semibold text-slate-700">
              {selectedTcIds.size} test case{selectedTcIds.size === 1 ? "" : "s"} selected
            </span>
            <button
              onClick={() => setSelectedTcIds(new Set())}
              className="text-[11px] font-medium text-slate-500 hover:text-slate-800"
            >
              Clear
            </button>
            <span className="h-4 w-px bg-slate-200" />
            <button
              onClick={() => setBulkEditOpen(true)}
              className="rounded-full bg-[#1b59f8] px-3 py-1 text-xs font-semibold text-white hover:bg-[#1546c2]"
            >
              Bulk edit
            </button>
          </div>
        </div>
      )}

      {bulkEditOpen && selectedProject != null && (
        <BulkEditDialog
          projectId={selectedProject}
          selectedIds={Array.from(selectedTcIds)}
          allTestCases={testCases}
          suites={suites}
          resolveSuiteId={resolveSuiteId}
          onClose={() => setBulkEditOpen(false)}
          onApplied={async () => {
            setBulkEditOpen(false);
            setSelectedTcIds(new Set());
            // Reload the test cases list so the table reflects the changes.
            const tcRes = await testCasesApi.list(selectedProject);
            setTestCases(tcRes.data);
            setDrafts(Object.fromEntries(tcRes.data.map((tc) => [tc.id, toDraft(tc)])));
            setNoticeTone("success");
            setNotice("Bulk update applied.");
          }}
        />
      )}
    </div>
  );
}

// ── Bulk Edit Dialog ─────────────────────────────────────────────────────────
//
// Two-step flow:
//   1. "Choose changes" — user picks which fields to update and their new values.
//      Each field has a "change this field" toggle so untouched fields aren't
//      sent to the server (the patch only includes fields the user explicitly
//      flipped on).
//   2. "Preview" — calls bulkUpdate(dry_run=true) and shows per-row diff plus
//      any conflict reasons. User enters the audit reason here.
//   3. On confirm — calls bulkUpdate(dry_run=false, reason).

type BulkPatchKey = "execution_mode" | "automation_status" | "automation_ready" | "external_tool" | "test_suite";

function BulkEditDialog({
  projectId,
  selectedIds,
  allTestCases,
  suites,
  resolveSuiteId,
  onClose,
  onApplied,
}: {
  projectId: number;
  selectedIds: number[];
  allTestCases: TestCase[];
  suites: TestSuite[];
  resolveSuiteId: (name: string) => Promise<number | null>;
  onClose: () => void;
  onApplied: () => void | Promise<void>;
}) {
  // Which fields the user has toggled on to change.
  const [enabledFields, setEnabledFields] = useState<Record<BulkPatchKey, boolean>>({
    execution_mode: false,
    automation_status: false,
    automation_ready: false,
    external_tool: false,
    test_suite: false,
  });
  const [executionMode, setExecutionMode] = useState<string>("automation");
  const [automationStatus, setAutomationStatus] = useState<string>("planned_for_automation");
  const [automationReady, setAutomationReady] = useState<boolean>(true);
  const [externalTool, setExternalTool] = useState<string>("Playwright");
  const [testSuiteName, setTestSuiteName] = useState<string>("");
  const [reason, setReason] = useState<string>("");
  const [step, setStep] = useState<"choose" | "preview">("choose");
  const [preview, setPreview] = useState<TestCaseBulkUpdateResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const selectedTcs = useMemo(
    () => allTestCases.filter((tc) => selectedIds.includes(tc.id)),
    [allTestCases, selectedIds],
  );

  const buildPatch = useCallback(async () => {
    const patch: Record<string, unknown> = {};
    if (enabledFields.execution_mode) patch.execution_mode = executionMode;
    if (enabledFields.automation_status) patch.automation_status = automationStatus;
    if (enabledFields.automation_ready) patch.automation_ready = automationReady;
    if (enabledFields.external_tool) patch.external_tool = externalTool;
    if (enabledFields.test_suite) patch.test_suite_id = await resolveSuiteId(testSuiteName);
    return patch;
  }, [enabledFields, executionMode, automationStatus, automationReady, externalTool, testSuiteName, resolveSuiteId]);

  const anyEnabled = Object.values(enabledFields).some(Boolean);

  const runPreview = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await testCasesApi.bulkUpdate(projectId, {
        test_case_ids: selectedIds,
        patch: await buildPatch(),
        reason: reason.trim() || "preview",
        dry_run: true,
      });
      setPreview(res.data);
      setStep("preview");
    } catch (e: unknown) {
      const errObj = e as { response?: { data?: { detail?: string } }; message?: string };
      setErr(errObj?.response?.data?.detail ?? errObj?.message ?? "Preview failed");
    } finally {
      setBusy(false);
    }
  };

  const commit = async () => {
    if (!reason.trim()) { setErr("A reason is required for the audit trail."); return; }
    setBusy(true);
    setErr(null);
    try {
      await testCasesApi.bulkUpdate(projectId, {
        test_case_ids: selectedIds,
        patch: await buildPatch(),
        reason: reason.trim(),
        dry_run: false,
      });
      await onApplied();
    } catch (e: unknown) {
      const errObj = e as { response?: { data?: { detail?: string } }; message?: string };
      setErr(errObj?.response?.data?.detail ?? errObj?.message ?? "Update failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="w-full max-w-2xl rounded-xl bg-white shadow-2xl overflow-hidden" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">Bulk edit · {selectedIds.length} test cases</h3>
            <p className="text-[11px] text-slate-500 mt-0.5">
              {step === "choose" ? "Pick which fields to update. Untouched fields are left alone." : "Review the per-row diff and conflicts before committing."}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-lg leading-none">×</button>
        </div>

        {step === "choose" && (
          <div className="p-5 space-y-3">
            <BulkFieldRow
              label="Execution Mode"
              enabled={enabledFields.execution_mode}
              onToggle={(v) => setEnabledFields((s) => ({ ...s, execution_mode: v }))}
            >
              <select
                value={executionMode}
                onChange={(e) => setExecutionMode(e.target.value)}
                disabled={!enabledFields.execution_mode}
                className="rounded border border-slate-200 px-2 py-1 text-xs bg-white disabled:bg-slate-50 disabled:text-slate-400"
              >
                {MODE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </BulkFieldRow>

            <BulkFieldRow
              label="Automation Status"
              enabled={enabledFields.automation_status}
              onToggle={(v) => setEnabledFields((s) => ({ ...s, automation_status: v }))}
            >
              <select
                value={automationStatus}
                onChange={(e) => setAutomationStatus(e.target.value)}
                disabled={!enabledFields.automation_status}
                className="rounded border border-slate-200 px-2 py-1 text-xs bg-white disabled:bg-slate-50 disabled:text-slate-400"
              >
                {AUTOMATION_STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </BulkFieldRow>

            <BulkFieldRow
              label="External Tool"
              enabled={enabledFields.external_tool}
              onToggle={(v) => setEnabledFields((s) => ({ ...s, external_tool: v }))}
            >
              <select
                value={externalTool}
                onChange={(e) => setExternalTool(e.target.value)}
                disabled={!enabledFields.external_tool}
                className="rounded border border-slate-200 px-2 py-1 text-xs bg-white disabled:bg-slate-50 disabled:text-slate-400"
              >
                {TOOL_OPTIONS.filter((t) => t).map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </BulkFieldRow>

            <BulkFieldRow
              label="Automation Execution Ready"
              enabled={enabledFields.automation_ready}
              onToggle={(v) => setEnabledFields((s) => ({ ...s, automation_ready: v }))}
            >
              <label className="flex items-center gap-1.5 text-xs text-slate-700">
                <input
                  type="checkbox"
                  checked={automationReady}
                  onChange={(e) => setAutomationReady(e.target.checked)}
                  disabled={!enabledFields.automation_ready}
                  className="h-3.5 w-3.5 rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8]"
                />
                {automationReady ? "Ready (CI-eligible)" : "Not ready"}
              </label>
            </BulkFieldRow>

            <BulkFieldRow
              label="Test Suite"
              enabled={enabledFields.test_suite}
              onToggle={(v) => setEnabledFields((s) => ({ ...s, test_suite: v }))}
            >
              <input
                list="bulk-test-suite-options"
                value={testSuiteName}
                onChange={(e) => setTestSuiteName(e.target.value)}
                disabled={!enabledFields.test_suite}
                placeholder="Type to select or create…"
                className="rounded border border-slate-200 px-2 py-1 text-xs bg-white disabled:bg-slate-50 disabled:text-slate-400"
              />
              <datalist id="bulk-test-suite-options">
                {suites.map((s) => <option key={s.id} value={s.name} />)}
              </datalist>
            </BulkFieldRow>

            {err && <p className="text-[11px] text-red-600">{err}</p>}

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
              <button onClick={onClose} className="rounded-md px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">Cancel</button>
              <button
                onClick={runPreview}
                disabled={!anyEnabled || busy}
                className="rounded-md bg-[#1b59f8] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#1546c2] disabled:opacity-50"
              >
                {busy ? "Loading…" : "Preview changes"}
              </button>
            </div>
          </div>
        )}

        {step === "preview" && preview && (
          <div className="p-5 space-y-3">
            <div className="flex flex-wrap gap-2 text-[11px]">
              <span className="rounded-full bg-emerald-50 text-emerald-700 px-2 py-0.5 font-semibold">{preview.updated} will update</span>
              <span className="rounded-full bg-slate-100 text-slate-600 px-2 py-0.5 font-semibold">{preview.skipped} no change</span>
              {preview.conflicts > 0 && (
                <span className="rounded-full bg-red-50 text-red-700 px-2 py-0.5 font-semibold">{preview.conflicts} conflicts (will be skipped)</span>
              )}
              {preview.not_found > 0 && (
                <span className="rounded-full bg-amber-50 text-amber-700 px-2 py-0.5 font-semibold">{preview.not_found} not found</span>
              )}
            </div>

            <div className="max-h-72 overflow-y-auto border border-slate-100 rounded-md">
              <table className="w-full text-[11px]">
                <thead className="bg-slate-50 sticky top-0">
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400">
                    <th className="py-1.5 px-2">TC</th>
                    <th className="py-1.5 px-2">Outcome</th>
                    <th className="py-1.5 px-2">Diff / Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row) => {
                    const tone =
                      row.outcome === "updated" ? "text-emerald-700" :
                      row.outcome === "conflict" ? "text-red-700" :
                      row.outcome === "not_found" || row.outcome === "forbidden" ? "text-amber-700" :
                      "text-slate-500";
                    return (
                      <tr key={row.test_case_id} className="border-t border-slate-100">
                        <td className="py-1.5 px-2 font-mono text-slate-700 whitespace-nowrap">
                          {row.test_case_key ?? `#${row.test_case_id}`}
                        </td>
                        <td className={cn("py-1.5 px-2 font-semibold capitalize", tone)}>{row.outcome.replace(/_/g, " ")}</td>
                        <td className="py-1.5 px-2 text-slate-600">
                          {row.conflict_reason ? row.conflict_reason : (
                            Object.entries(row.changes).map(([field, diff]) => (
                              <div key={field} className="text-[10px]">
                                <span className="font-mono text-slate-500">{field}</span>:{" "}
                                <span className="text-slate-400 line-through">{String(diff.old ?? "—")}</span>{" → "}
                                <span className="text-slate-800 font-semibold">{String(diff.new ?? "—")}</span>
                              </div>
                            ))
                          )}
                          {row.outcome === "updated" && Object.keys(row.changes).length === 0 && <span>(no visible diff)</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div>
              <label className="block text-[10px] uppercase tracking-wider text-slate-400 font-semibold mb-1">Reason (audit trail, required)</label>
              <textarea
                rows={2}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Why are you making this bulk change?"
                className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-[#1b59f8]"
              />
            </div>

            {err && <p className="text-[11px] text-red-600">{err}</p>}

            <div className="flex items-center justify-between pt-2 border-t border-slate-100">
              <button onClick={() => { setStep("choose"); setPreview(null); }} className="text-xs font-medium text-slate-500 hover:text-slate-800">
                ← Back to fields
              </button>
              <div className="flex items-center gap-2">
                <button onClick={onClose} className="rounded-md px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">Cancel</button>
                <button
                  onClick={commit}
                  disabled={busy || preview.updated === 0 || !reason.trim()}
                  className="rounded-md bg-[#1b59f8] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#1546c2] disabled:opacity-50"
                  title={preview.updated === 0 ? "Nothing would change with these settings" : !reason.trim() ? "Reason is required" : ""}
                >
                  {busy ? "Applying…" : `Apply to ${preview.updated} test case${preview.updated === 1 ? "" : "s"}`}
                </button>
              </div>
            </div>
          </div>
        )}
        {/* Used only to keep the imports clean — silences the unused warning on selectedTcs. */}
        <span hidden>{selectedTcs.length}</span>
      </div>
    </div>
  );
}

function BulkFieldRow({
  label, enabled, onToggle, children,
}: {
  label: string;
  enabled: boolean;
  onToggle: (v: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-slate-100 px-3 py-2">
      <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 cursor-pointer">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
          className="h-3.5 w-3.5 rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8]"
        />
        {label}
      </label>
      {children}
    </div>
  );
}

// ── Export CSV Logic Helper ──────────────────────────────────────────────────
function exportToCSV(testCases: TestCase[]) {
  const headers = ["ID", "Title", "Status", "Priority", "Mode", "Automation Eligible", "Automation Status", "External Tool", "Suite ID", "External TC ID", "Jira Final", "Jira Sync"];
  const rows = testCases.map((tc) => [
    tc.test_case_id,
    tc.title,
    tc.status,
    tc.priority,
    tc.execution_mode,
    tc.automation_eligible,
    tc.automation_status,
    tc.external_tool ?? "",
    tc.suite_id ?? "",
    tc.external_tc_id ?? "",
    tc.jira_final_status ?? "",
    tc.jira_sync_status,
  ]);
  const csv = [headers, ...rows].map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "test-cases.csv";
  a.click();
  URL.revokeObjectURL(url);
}

// ── Root Wrapper with Suspense ────────────────────────────────────────────────
export default function TestCasesPage() {
  return (
    <Suspense fallback={
      <div className="p-8 text-center text-xs text-slate-500 font-semibold flex items-center justify-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin text-[#1b59f8]" />
        Loading Test Case Library...
      </div>
    }>
      <TestCasesContent />
    </Suspense>
  );
}
