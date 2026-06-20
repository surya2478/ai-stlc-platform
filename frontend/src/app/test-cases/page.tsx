"use client";

import { useCallback, useEffect, useMemo, useState, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  AlertTriangle, Bot, CheckCircle, ChevronDown, ChevronUp, Columns3, Download, ExternalLink,
  History, Loader2, RefreshCw, RotateCcw, Save, ShieldCheck, TestTube2, XCircle, ChevronRight, X, Play, Info, Sparkles,
  FileText, Layers, Zap, LayoutDashboard, Clock
} from "lucide-react";
import { AuditStamp } from "@/components/ui/AuditStamp";
import { useUserDirectory } from "@/hooks/useUserDirectory";
import {
  agentRunsApi, projectsApi, requirementsApi, scenariosApi, testCasesApi,
  type Project, type Requirement, type TestCase, type TestCaseHistory, type TestCaseSummary, type TestScenario
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerBody, DrawerFooter, DrawerClose
} from "@/components/ui/drawer";

// ── Dropdown and Form Options ──────────────────────────────────────────────────
const STATUS_OPTIONS = ["draft", "pending_approval", "approved", "rejected", "automated"];
const MODE_OPTIONS = ["manual", "automated", "hybrid", "ai"];
const ELIGIBLE_OPTIONS = ["yes", "no"];
const AUTOMATION_STATUS_OPTIONS = [
  "not_required",
  "mapping_required",
  "ready_for_automation",
  "automated",
  "automation_failed",
  "maintenance_required",
];
const TOOL_OPTIONS = ["", "Mock", "Playwright", "Pytest", "Katalon", "Selenium", "Other"];
const JIRA_STATUS_OPTIONS = ["", "pending", "passed", "failed", "skipped", "blocked", "not_run"];
const PHASE_OPTIONS = ["", "SIT", "UAT", "Regression", "NFT", "Production_Validation"];
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
  { key: "testPhase", label: "Test Phase", group: "advanced", width: "150px", draftFields: ["test_phase"] },
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
  product_group: string;
  product: string;
  sub_request_type: string;
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
    product_group: tc.product_group ?? "",
    product: tc.product ?? "",
    sub_request_type: tc.sub_request_type ?? "",
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

  const [projects, setProjects] = useState<Project[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [summary, setSummary] = useState<TestCaseSummary | null>(null);
  const [scenarios, setScenarios] = useState<TestScenario[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  
  // Drawer States
  const [selectedTestCase, setSelectedTestCase] = useState<TestCase | null>(null);
  const [drawerTab, setDrawerTab] = useState<"attributes" | "steps" | "history">("attributes");

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

  // Sync parameters
  useEffect(() => {
    projectsApi.list().then((res) => {
      setProjects(res.data);
      if (res.data.length > 0 && !searchParams.get("project")) {
        const params = new URLSearchParams(searchParams.toString());
        params.set("project", String(res.data[0].id));
        router.push(`${pathname}?${params.toString()}`);
      }
    }).catch(() => setError("Could not load projects."));
  }, [searchParams, pathname, router]);

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
      const [tcRes, summaryRes, scRes, reqRes] = await Promise.all([
        testCasesApi.list(selectedProject),
        testCasesApi.summary(selectedProject),
        scenariosApi.list(selectedProject),
        requirementsApi.list(selectedProject, { status: "approved" }),
      ]);
      const approvedScenarios = scRes.data.filter((s) => s.status === "approved");
      setTestCases(tcRes.data);
      setSummary(summaryRes.data);
      setScenarios(approvedScenarios);
      setRequirements(reqRes.data);
      setSelectedScenarioIds(approvedScenarios.map((s) => s.id));
      setDrafts(Object.fromEntries(tcRes.data.map((tc) => [tc.id, toDraft(tc)])));
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
      "telecom_domain", "test_phase", "product_group", "product", "sub_request_type"
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

  function toggleColumn(column: ColumnConfig) {
    if (column.required) return;
    const isVisible = visibleColumns.includes(column.key);
    setVisibleColumns(isVisible ? visibleColumns.filter((key) => key !== column.key) : [...visibleColumns, column.key]);
  }

  async function saveTestCase(tc: TestCase) {
    const draft = drafts[tc.id];
    if (!draft) return;
    if (draft.status === "rejected" && !draft.comment.trim()) {
      setError("Rejected test cases require a comment.");
      return;
    }
    if (draft.automation_status === "automated" && !draft.external_tc_id.trim() && !tc.automation_script_id) {
      setError("Automated status requires an external TC ID or automation script.");
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
      await testCasesApi.update(tc.id, {
        ...changedPayload(tc),
      });
      setNoticeTone("success");
      setNotice(`${tc.test_case_id} saved.`);
      await loadData();
    } catch (saveError) {
      setError(messageFromError(saveError, "Could not save test case."));
    } finally {
      setSavingId(null);
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
        const modeOk =
          filterMode === "all" ||
          (filterMode === "automation_ready" ? tc.automation_ready : filterMode === "pending_jira" ? tc.jira_sync_status === "pending" : tc.execution_mode === filterMode);
        return statusOk && modeOk;
      }),
    [testCases, filterStatus, filterMode]
  );

  const total = summary?.total ?? testCases.length;
  const approved = summary?.by_status?.approved ?? 0;
  const draft = summary?.by_status?.draft ?? 0;
  const rejected = summary?.by_status?.rejected ?? 0;
  const blocked = summary?.by_status?.blocked ?? 0;
  const pending = summary?.by_status?.pending_approval ?? 0;
  const readyForAutomation = summary?.by_automation_status?.ready_for_automation ?? 0;
  const automated = summary?.by_mode?.automated ?? 0;
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
  const gridTemplateColumns = visibleColumnConfigs.map((col) => col.width).join(" ");
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
        return <span className="text-xs font-semibold text-slate-700 capitalize">{draft.mode}</span>;
      case "automation":
        return (
          <Badge variant={
            draft.automation_status === "automated" ? "success" :
            draft.automation_status === "ready_for_automation" ? "info" :
            draft.automation_status === "mapping_required" || draft.automation_status === "maintenance_required" ? "warning" :
            draft.automation_status === "automation_failed" ? "destructive" : "secondary"
          } className="capitalize truncate max-w-full">
            {draft.automation_status}
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
          <select 
            className="appearance-none bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 rounded-lg text-xs font-semibold px-3 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-[#1b59f8] transition-colors cursor-pointer"
            value={selectedProject ?? ""} 
            onChange={(e) => {
              const val = e.target.value;
              const params = new URLSearchParams(searchParams.toString());
              params.set("project", val);
              router.push(`${pathname}?${params.toString()}`);
            }}
            style={{
              backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
              backgroundPosition: 'right 0.5rem center',
              backgroundSize: '1.25rem 1.25rem',
              backgroundRepeat: 'no-repeat',
            }}
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
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
          <div className="border-t border-slate-100 p-4 max-h-52 overflow-y-auto bg-slate-50/50">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {scenarios.map((sc) => (
                <label key={sc.id} className="flex cursor-pointer items-center gap-3 bg-white border border-slate-200 rounded-lg p-2.5 text-xs hover:bg-slate-50 transition-colors">
                  <input
                    type="checkbox"
                    checked={selectedScenarioIds.includes(sc.id)}
                    className="rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8] h-3.5 w-3.5"
                    onChange={() => setSelectedScenarioIds((prev) => prev.includes(sc.id) ? prev.filter((id) => id !== sc.id) : [...prev, sc.id])}
                  />
                  <span className="shrink-0 font-mono text-[10px] font-bold text-slate-500">{sc.scenario_id}</span>
                  <span className="truncate flex-1 font-semibold text-slate-700">{sc.title}</span>
                </label>
              ))}
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

          {/* Mode Filters */}
          <div className="flex gap-1 rounded-lg border border-slate-200 bg-white p-1 shrink-0">
            {["all", "manual", "automated", "hybrid", "automation_ready", "pending_jira"].map((mode) => (
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
                {mode.replace(/_/g, " ")}
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
                return (
                  <div 
                    key={tc.id} 
                    onClick={() => setSelectedTestCase(tc)}
                    className={cn(
                      "grid items-center gap-2 px-4 transition-colors hover:bg-slate-50/50 cursor-pointer select-none",
                      compactView ? "py-1.5" : "py-2.5",
                      selectedTestCase?.id === tc.id && "bg-[#1b59f8]/5 hover:bg-[#1b59f8]/5",
                      hasEdits && "bg-amber-50/30 hover:bg-amber-50/40"
                    )}
                    style={{ gridTemplateColumns }}
                  >
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
                    Configure specifications, automation ready marks, and synchronize parameters
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
                {(["attributes", "steps", "history"] as const).map((tab) => (
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
                {/* TAB 1: ATTRIBUTES FORM */}
                {drawerTab === "attributes" && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Status */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Status
                      </label>
                      <select
                        value={activeDraft.status}
                        onChange={(e) => updateDraft(selectedTestCase.id, { status: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                      >
                        {STATUS_OPTIONS.map(opt => <option key={opt} value={opt}>{opt.replace(/_/g, " ")}</option>)}
                      </select>
                    </div>

                    {/* Priority */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Priority
                      </label>
                      <select
                        value={activeDraft.priority}
                        onChange={(e) => updateDraft(selectedTestCase.id, { priority: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                      >
                        {PRIORITY_OPTIONS.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                      </select>
                    </div>

                    {/* Execution Mode */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Execution Mode
                      </label>
                      <select
                        value={activeDraft.mode}
                        onChange={(e) => {
                          const val = e.target.value;
                          updateDraft(selectedTestCase.id, {
                            mode: val,
                            automation_eligible: val === "manual" ? "no" : val === "automated" ? "yes" : activeDraft.automation_eligible,
                            automation_status: val === "manual" ? "not_required" : val === "automated" && activeDraft.automation_status === "not_required" ? "mapping_required" : activeDraft.automation_status,
                            automation_ready: val === "manual" ? false : activeDraft.automation_ready
                          });
                        }}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                      >
                        {MODE_OPTIONS.map(opt => <option key={opt} value={opt}>{opt.replace(/_/g, " ")}</option>)}
                      </select>
                    </div>

                    {/* Automation Eligible */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Automation Eligible
                      </label>
                      <select
                        value={activeDraft.automation_eligible}
                        onChange={(e) => {
                          const val = e.target.value;
                          updateDraft(selectedTestCase.id, {
                            automation_eligible: val,
                            automation_status: val === "no" ? "not_required" : activeDraft.mode === "automated" && activeDraft.automation_status === "not_required" ? "mapping_required" : activeDraft.automation_status,
                            automation_ready: val === "no" ? false : activeDraft.automation_ready
                          });
                        }}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                      >
                        {ELIGIBLE_OPTIONS.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                      </select>
                    </div>

                    {/* Automation Status */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Automation Status
                      </label>
                      <select
                        value={activeDraft.automation_status}
                        disabled={activeDraft.mode === "manual" || activeDraft.automation_eligible === "no"}
                        onChange={(e) => updateDraft(selectedTestCase.id, { automation_status: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] disabled:opacity-50"
                      >
                        {AUTOMATION_STATUS_OPTIONS.map(opt => <option key={opt} value={opt}>{opt.replace(/_/g, " ")}</option>)}
                      </select>
                    </div>

                    {/* Automation Ready Checkbox */}
                    <div className="flex flex-col gap-1.5 justify-end pl-1 pb-2">
                      <label className="flex items-center gap-2.5 text-xs font-semibold text-slate-700 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={activeDraft.automation_ready}
                          disabled={activeDraft.mode === "manual" || activeDraft.automation_eligible === "no"}
                          className="rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8] h-4 w-4 disabled:opacity-50"
                          onChange={(e) => updateDraft(selectedTestCase.id, { automation_ready: e.target.checked })}
                        />
                        Automation Execution Ready
                      </label>
                    </div>

                    <div className="border-t border-slate-100 col-span-1 md:col-span-2 my-1" />

                    {/* External Tool */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        External Tool
                      </label>
                      <select
                        value={activeDraft.external_tool}
                        disabled={activeDraft.mode === "manual"}
                        onChange={(e) => updateDraft(selectedTestCase.id, { external_tool: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] disabled:opacity-50"
                      >
                        {TOOL_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                      </select>
                    </div>

                    {/* Suite ID */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Suite ID
                      </label>
                      <input
                        type="text"
                        value={activeDraft.suite_id}
                        disabled={activeDraft.mode === "manual"}
                        onChange={(e) => updateDraft(selectedTestCase.id, { suite_id: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] disabled:opacity-50"
                        placeholder="e.g. suite_102"
                      />
                    </div>

                    {/* External TC ID */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        External TC ID
                      </label>
                      <input
                        type="text"
                        value={activeDraft.external_tc_id}
                        disabled={activeDraft.mode === "manual"}
                        onChange={(e) => updateDraft(selectedTestCase.id, { external_tc_id: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] disabled:opacity-50"
                        placeholder="e.g. tc_5021"
                      />
                    </div>

                    {/* External TC URL */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        External TC URL
                      </label>
                      <input
                        type="text"
                        value={activeDraft.external_tc_url}
                        disabled={activeDraft.mode === "manual"}
                        onChange={(e) => updateDraft(selectedTestCase.id, { external_tc_url: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] disabled:opacity-50"
                        placeholder="https://testrail.example.com/tc/5021"
                      />
                    </div>

                    <div className="border-t border-slate-100 col-span-1 md:col-span-2 my-1" />

                    {/* Telecom Domain */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Telecom Domain
                      </label>
                      <select
                        value={activeDraft.telecom_domain}
                        onChange={(e) => updateDraft(selectedTestCase.id, { telecom_domain: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                      >
                        {DOMAIN_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                      </select>
                    </div>

                    {/* Test Phase */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Test Phase
                      </label>
                      <select
                        value={activeDraft.test_phase}
                        onChange={(e) => updateDraft(selectedTestCase.id, { test_phase: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                      >
                        {PHASE_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                      </select>
                    </div>

                    {/* Product Group */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Product Group
                      </label>
                      <select
                        value={activeDraft.product_group || ""}
                        onChange={(e) => updateDraft(selectedTestCase.id, { product_group: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                      >
                        {PRODUCT_GROUP_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                      </select>
                    </div>

                    {/* Product */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Product
                      </label>
                      <select
                        value={activeDraft.product || ""}
                        onChange={(e) => updateDraft(selectedTestCase.id, { product: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                      >
                        {PRODUCT_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                      </select>
                    </div>

                    {/* Sub Request Type */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Sub Request Type
                      </label>
                      <select
                        value={activeDraft.sub_request_type || ""}
                        onChange={(e) => updateDraft(selectedTestCase.id, { sub_request_type: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                      >
                        {SUB_REQUEST_TYPE_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                      </select>
                    </div>

                    {/* Jira Final Status */}
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Jira Final Status
                      </label>
                      <select
                        value={activeDraft.jira_final_status}
                        onChange={(e) => updateDraft(selectedTestCase.id, { jira_final_status: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8]"
                      >
                        {JIRA_STATUS_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || "None"}</option>)}
                      </select>
                    </div>

                    {/* Comment */}
                    <div className="flex flex-col gap-1 col-span-1 md:col-span-2">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Comment {activeDraft.status === "rejected" && <span className="text-red-500 font-bold">*</span>}
                      </label>
                      <textarea
                        value={activeDraft.comment}
                        onChange={(e) => updateDraft(selectedTestCase.id, { comment: e.target.value })}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#1b59f8] min-h-16"
                        placeholder="Provide details for quality logs or reasons for rejection..."
                      />
                    </div>

                    <div className="border-t border-slate-100 col-span-1 md:col-span-2 my-1" />

                    <div className="flex flex-col gap-1.5 col-span-1 md:col-span-2">
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

                    {/* Preconditions */}
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

                    {/* Steps Table */}
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
              </DrawerFooter>
            </>
          )}
        </DrawerContent>
      </Drawer>
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
