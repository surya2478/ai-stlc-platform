"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  AlertTriangle,
  Bot,
  Clock,
  ExternalLink,
  FileText,
  History,
  Link2,
  Loader2,
  PlayCircle,
  Radar,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Wrench,
  X,
  Terminal,
  Video,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
} from "recharts";
import {
  automationApi,
  getScriptQualitySignals,
  projectsApi,
  testCasesApi,
  type AutomationScript,
  type AutomationTestMapping,
  type ExecutionResult,
  type ExecutionRun,
  type LifecycleApprovalAction,
  type TestCase,
} from "@/lib/api";
import { useAutomationMappings, usePlanning, useScripts } from "@/lib/queries/automation";
import { useRuns } from "@/lib/queries/execution";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerDescription,
  DrawerBody,
  DrawerFooter
} from "@/components/ui/drawer";
import { GenerateWithAIDialog } from "@/components/automation/GenerateWithAIDialog";
import { IntelligenceAssistantPanel } from "@/components/automation/IntelligenceAssistantPanel";
import { AutomationInventoryPanel, type InventoryItem } from "@/components/automation/AutomationInventoryPanel";
import { AutomationWorkspace } from "@/components/automation/AutomationWorkspace";
import { ConvertManualToAutomationDialog } from "@/components/automation/ConvertManualToAutomationDialog";
import { DiscoverySessionView } from "@/components/discovery/DiscoverySessionView";
import { AutomationSuiteDashboard } from "@/components/automation/AutomationSuiteDashboard";
import { AutomationSuiteDetail } from "@/components/automation/AutomationSuiteDetail";
import { NewAutomationSuiteWizard } from "@/components/automation/NewAutomationSuiteWizard";
import { AutomationAssetWorkspace } from "@/components/automation/AutomationAssetWorkspace";
import { AutomationAssetPicker } from "@/components/automation/AutomationAssetPicker";
import { LiveRecorderLauncher } from "@/components/automation/LiveRecorderLauncher";
import { LiveRecorderWorkspace } from "@/components/automation/LiveRecorderWorkspace";
import { RunnerStatusChip } from "@/app/execution/_components/RunnerStatusChip";
import { RunTriggerDialog, RunAllEligibleDialog, type RunTarget, type BatchRunCandidate } from "@/app/execution/_components/AutomationBuilderTab";
import { RunDetailDrawer } from "@/app/execution/_components/RunDetailDrawer";
import { TraceabilityDrawer, type TraceTarget } from "@/app/execution/_components/TraceabilityDrawer";
import { RunVerdictBadge, formatDate, formatDuration } from "@/app/execution/_components/run-utils";
import { useAIAction } from "@/hooks/useAIAction";
import { AI_PROCESSING_STAGES } from "@/lib/ai-processing-stages";

// Status Chip Variant Mapping
function getStatusVariant(status: string | null | undefined): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  if (!status) return "outline";
  const s = status.toLowerCase();
  if (["passed", "success", "completed", "synced", "yes"].includes(s)) return "success";
  if (["failed", "error", "rejected", "no"].includes(s)) return "destructive";
  if (["blocked", "in_progress", "running", "queued", "pending", "requested"].includes(s)) return "warning";
  if (["skipped", "deferred", "manual", "kept for later"].includes(s)) return "secondary";
  if (["automated", "hybrid", "active", "visible"].includes(s)) return "purple";
  return "outline";
}

function messageFromError(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => item?.msg ?? String(item)).join("; ");
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

/** Recognizes the backend's "approving this requires an explicit override
 * note" 422 (see automation_service.approval_override_reason) and returns
 * its message — already phrased as a prompt asking the reviewer why — or
 * null for any other error. */
function overrideNoteFromError(error: unknown): string | null {
  if (!error || typeof error !== "object" || !("response" in error)) return null;
  const response = (error as { response?: { status?: number; data?: { detail?: unknown } } }).response;
  if (response?.status !== 422) return null;
  const detail = response.data?.detail;
  if (typeof detail === "string" && detail.includes("requires a note explaining why")) return detail;
  return null;
}

type MappingForm = {
  external_tool_name: string;
  external_project_id: string;
  external_suite_id: string;
  external_test_case_id: string;
  external_script_id: string;
};

const emptyMappingForm: MappingForm = {
  external_tool_name: "Mock",
  external_project_id: "",
  external_suite_id: "",
  external_test_case_id: "",
  external_script_id: "",
};

function AutomationContent() {
  const { runAIAction } = useAIAction();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProject = Number(searchParams.get("project")) || null;
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [latestResults, setLatestResults] = useState<Record<number, ExecutionResult | undefined>>({});

  // Scripts / planning / mappings / runs come from the shared React Query
  // hooks; runs poll automatically while any run is active.
  const scriptsQuery = useScripts(selectedProject);
  const planningQuery = usePlanning(selectedProject);
  const mappingsQuery = useAutomationMappings(selectedProject);
  const runsQuery = useRuns(selectedProject);
  const scripts = useMemo(() => scriptsQuery.data ?? [], [scriptsQuery.data]);
  const mappings = useMemo(() => mappingsQuery.data ?? [], [mappingsQuery.data]);
  const planning = planningQuery.data ?? null;
  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);

  // States
  const [tcLoading, setTcLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [environment, setEnvironment] = useState("staging");
  const [showAiScripts, setShowAiScripts] = useState(false);
  const [reviewBusyId, setReviewBusyId] = useState<number | null>(null);
  const [lifecycleBusyId, setLifecycleBusyId] = useState<number | null>(null);
  const loading = tcLoading || scriptsQuery.isLoading || planningQuery.isLoading || mappingsQuery.isLoading;

  // Drawer States
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedTestCase, setSelectedTestCase] = useState<TestCase | null>(null);
  const [drawerTab, setDrawerTab] = useState<"mapping" | "history">("mapping");
  const [mappingForm, setMappingForm] = useState<MappingForm>(emptyMappingForm);
  const [historyRows, setHistoryRows] = useState<ExecutionResult[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // AI Automation Studio — Phase 2A additions
  const [aiDialogOpen, setAiDialogOpen] = useState(false);
  const [aiDialogPreselect, setAiDialogPreselect] = useState<number[]>([]);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantScript, setAssistantScript] = useState<AutomationScript | null>(null);

  // AI Automation Studio — Phase 2B additions
  const [selectedInventoryId, setSelectedInventoryId] = useState<number | null>(null);
  const [selectedInventoryIds, setSelectedInventoryIds] = useState<Set<number>>(new Set());
  const [bulkApproveBusy, setBulkApproveBusy] = useState(false);
  const [bulkDiscoverBusy, setBulkDiscoverBusy] = useState(false);

  // AI Automation Studio — Phase 2C additions
  const [transitionBusyId, setTransitionBusyId] = useState<number | null>(null);
  const [convertManualOpen, setConvertManualOpen] = useState(false);

  // AI Automation Studio — Phase 2D additions
  const [saveBusyId, setSaveBusyId] = useState<number | null>(null);

  // Sandbox runs — local runner trigger + per-script run history strip.
  const [sandboxTarget, setSandboxTarget] = useState<RunTarget | null>(null);
  const [openRun, setOpenRun] = useState<ExecutionRun | null>(null);
  const [traceTarget, setTraceTarget] = useState<TraceTarget | null>(null);
  const [runAllOpen, setRunAllOpen] = useState(false);

  // Load Projects on mount
  useEffect(() => {
    projectsApi.list().then((res) => {
      if (res.data.length > 0 && !searchParams.get("project")) {
        const params = new URLSearchParams(searchParams.toString());
        params.set("project", String(res.data[0].id));
        router.push(`${pathname}?${params.toString()}`);
      }
    }).catch(() => setError("Could not load projects."));
  }, [pathname, router, searchParams]);

  // Load approved test cases + their latest execution results. Scripts,
  // planning, mappings, and runs are handled by the React Query hooks above.
  const loadTestCases = useCallback(async () => {
    if (!selectedProject) return;
    setTcLoading(true);
    setError("");
    try {
      const casesRes = await testCasesApi.list(selectedProject, { status: "approved", automation_only: true });
      setTestCases(casesRes.data);

      const candidateIds = casesRes.data
        .filter(isAutomationVisible)
        .map((tc) => tc.id);

      const historyPairs = await Promise.all(
        candidateIds.map(async (id) => {
          try {
            const history = await automationApi.getExecutionHistory(id);
            return [id, history.data[0]] as const;
          } catch {
            return [id, undefined] as const;
          }
        })
      );
      setLatestResults(Object.fromEntries(historyPairs));
    } catch (loadError) {
      setError(messageFromError(loadError, "Could not load automation control data."));
    } finally {
      setTcLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadTestCases();
  }, [loadTestCases]);

  const loadData = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["automation"] });
    queryClient.invalidateQueries({ queryKey: ["execution"] });
    loadTestCases();
  }, [queryClient, loadTestCases]);

  // Reset states on project change
  useEffect(() => {
    setDrawerOpen(false);
    setSelectedTestCase(null);
    setHistoryRows([]);
    setError("");
  }, [selectedProject]);

  // Load History when Drawer active tab is history
  useEffect(() => {
    if (selectedTestCase && drawerTab === "history" && drawerOpen) {
      setHistoryLoading(true);
      automationApi.getExecutionHistory(selectedTestCase.id)
        .then((res) => setHistoryRows(res.data))
        .catch(() => setError("Could not load execution history."))
        .finally(() => setHistoryLoading(false));
    }
  }, [selectedTestCase, drawerTab, drawerOpen]);

  const mappingByTestCase = useMemo(() => {
    const result = new Map<number, AutomationTestMapping>();
    mappings.forEach((mapping) => {
      if (mapping.is_active && !result.has(mapping.test_case_id)) {
        result.set(mapping.test_case_id, mapping);
      }
    });
    return result;
  }, [mappings]);

  const rows = useMemo(
    () => testCases.filter(isAutomationVisible),
    [testCases]
  );

  const planningCandidates = useMemo(() => planning?.candidates ?? [], [planning]);

  const scriptsById = useMemo(() => {
    return new Map(scripts.map((script) => [script.id, script]));
  }, [scripts]);

  // Every candidate with an approved (or previously executed) script — feeds
  // the "Run All Eligible" batch dialog.
  const runAllCandidates = useMemo<BatchRunCandidate[]>(
    () =>
      planningCandidates
        .filter((c) => Boolean(c.script_id) && ["approved", "executed"].includes((c.script_status ?? "").toLowerCase()))
        .map((c) => ({
          scriptId: c.script_id as number,
          framework: c.recommended_framework,
          key: c.test_case_key,
          label: `${c.test_case_key} — ${c.title}`,
          testSuiteId: c.test_suite_id,
          testSuiteName: c.test_suite_name,
        })),
    [planningCandidates],
  );

  function handleRowClick(tc: TestCase) {
    const mapping = mappingByTestCase.get(tc.id);
    setSelectedTestCase(tc);
    setDrawerTab(mapping ? "history" : "mapping");
    setMappingForm(
      mapping
        ? {
            external_tool_name: mapping.external_tool_name,
            external_project_id: mapping.external_project_id ?? "",
            external_suite_id: mapping.external_suite_id ?? "",
            external_test_case_id: mapping.external_test_case_id,
            external_script_id: mapping.external_script_id ?? "",
          }
        : {
            ...emptyMappingForm,
            external_project_id: selectedProject ? `PROJECT-${selectedProject}` : "",
            external_suite_id: "REGRESSION",
            external_test_case_id: tc.test_case_id,
          }
    );
    setDrawerOpen(true);
  }

  async function handleSaveMapping(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProject || !selectedTestCase) return;
    if (!mappingForm.external_tool_name.trim() || !mappingForm.external_test_case_id.trim()) {
      setError("External tool and external automated test case ID are required.");
      return;
    }
    setBusyId(selectedTestCase.id);
    setError("");
    try {
      const existing = mappingByTestCase.get(selectedTestCase.id);
      const payload = {
        project_id: selectedProject,
        test_case_id: selectedTestCase.id,
        external_tool_name: mappingForm.external_tool_name.trim(),
        external_project_id: mappingForm.external_project_id.trim() || undefined,
        external_suite_id: mappingForm.external_suite_id.trim() || undefined,
        external_test_case_id: mappingForm.external_test_case_id.trim(),
        external_script_id: mappingForm.external_script_id.trim() || undefined,
        automation_status: "automated",
        is_active: true,
      };
      if (existing) {
        await automationApi.updateAutomationMapping(existing.id, payload);
      } else {
        await automationApi.createAutomationMapping(payload);
      }
      toast({ title: "Automation mapping saved", variant: "success" });
      setDrawerOpen(false);
      loadData();
    } catch (saveError) {
      toast({ title: "Could not save automation mapping", description: messageFromError(saveError, ""), variant: "error" });
    } finally {
      setBusyId(null);
    }
  }

  async function handleRunAutomation(tc: TestCase) {
    if (!selectedProject) return;
    setBusyId(tc.id);
    setError("");
    try {
      const response = await automationApi.runExternalAutomation(selectedProject, [tc.id], environment);
      toast({ title: "External run triggered", description: `${response.data.message} Run ${response.data.external_run_id}`, variant: "success" });
      loadData();
      // If drawer is open, switch to history tab to see new runs
      if (drawerOpen && selectedTestCase?.id === tc.id) {
        setDrawerTab("history");
        // Reload history manually
        setHistoryLoading(true);
        automationApi.getExecutionHistory(tc.id)
          .then((res) => setHistoryRows(res.data))
          .catch(() => setError("Could not load execution history."))
          .finally(() => setHistoryLoading(false));
      }
    } catch (runError) {
      toast({ title: "Could not run external automation", description: messageFromError(runError, ""), variant: "error" });
    } finally {
      setBusyId(null);
    }
  }

  async function handleSyncAutomation(mapping: AutomationTestMapping) {
    setBusyId(mapping.test_case_id);
    setError("");
    try {
      const response = await automationApi.syncExternalAutomationResult(mapping.id, environment);
      toast({ title: "External result synced", description: `${response.data.message} Run ${response.data.external_run_id}`, variant: "success" });
      loadData();
      if (drawerOpen && selectedTestCase?.id === mapping.test_case_id) {
        setDrawerTab("history");
        setHistoryLoading(true);
        automationApi.getExecutionHistory(mapping.test_case_id)
          .then((res) => setHistoryRows(res.data))
          .catch(() => setError("Could not load execution history."))
          .finally(() => setHistoryLoading(false));
      }
    } catch (syncError) {
      toast({ title: "Could not sync automation result", description: messageFromError(syncError, ""), variant: "error" });
    } finally {
      setBusyId(null);
    }
  }

  async function handleSyncJira(tc: TestCase) {
    const status = window.prompt("Enter Jira final execution status", latestResults[tc.id]?.jira_execution_status || "passed");
    if (!status) return;
    setBusyId(tc.id);
    setError("");
    try {
      await automationApi.syncJiraExecutionStatus({
        test_case_id: tc.id,
        jira_execution_status: status,
        jira_issue_key: tc.jira_issue_key,
        jira_test_key: tc.jira_test_key,
      });
      toast({ title: "Jira final execution status synced", variant: "success" });
      loadData();
      if (drawerOpen && selectedTestCase?.id === tc.id) {
        setDrawerTab("history");
        setHistoryLoading(true);
        automationApi.getExecutionHistory(tc.id)
          .then((res) => setHistoryRows(res.data))
          .catch(() => setError("Could not load execution history."))
          .finally(() => setHistoryLoading(false));
      }
    } catch (jiraError) {
      toast({ title: "Could not sync Jira execution status", description: messageFromError(jiraError, ""), variant: "error" });
    } finally {
      setBusyId(null);
    }
  }

  async function handleReviewScript(scriptId: number, action: "approve" | "reject") {
    // Rejections carry a reason into the script's review notes for the audit trail.
    let notes: string | undefined;
    if (action === "reject") {
      const reason = window.prompt("Reason for rejection (recorded in review history):");
      if (reason === null) return; // cancelled
      notes = reason.trim() || undefined;
    }
    setReviewBusyId(scriptId);
    setError("");
    try {
      try {
        await automationApi.approve(scriptId, action, notes);
      } catch (reviewError) {
        // Approving a script with a known quality issue (ungrounded locator,
        // failed dry run) is blocked unless the reviewer explicitly says why
        // — the backend's 422 message names the exact issue. Surface it and
        // let the reviewer supply that reason on the spot rather than
        // bouncing them out to figure out what "approve" silently rejected.
        const overrideReason = overrideNoteFromError(reviewError);
        if (!overrideReason) throw reviewError;
        const note = window.prompt(overrideReason);
        if (note === null || !note.trim()) return;
        await automationApi.approve(scriptId, action, note.trim());
      }
      toast({ title: `Script ${action === "approve" ? "approved" : "rejected"}`, variant: "success" });
      loadData();
    } catch (reviewError) {
      toast({ title: "Could not update script review state", description: messageFromError(reviewError, ""), variant: "error" });
    } finally {
      setReviewBusyId(null);
    }
  }

  async function handleLifecycleApproval(scriptId: number, action: LifecycleApprovalAction) {
    // Rejections carry a reason into the approval audit trail, same as the
    // legacy review flow.
    let notes: string | undefined;
    if (action === "reviewer_reject" || action === "lead_reject") {
      const reason = window.prompt("Reason for rejection (recorded in the approval audit trail):");
      if (reason === null) return; // cancelled
      notes = reason.trim() || undefined;
    }
    setLifecycleBusyId(scriptId);
    setError("");
    try {
      try {
        await automationApi.lifecycleApprove(scriptId, action, notes);
      } catch (lifecycleError) {
        const overrideReason = overrideNoteFromError(lifecycleError);
        if (!overrideReason) throw lifecycleError;
        const note = window.prompt(overrideReason);
        if (note === null || !note.trim()) return;
        await automationApi.lifecycleApprove(scriptId, action, note.trim());
      }
      const labels: Record<LifecycleApprovalAction, string> = {
        reviewer_approve: "approved by reviewer",
        reviewer_reject: "rejected by reviewer",
        lead_approve: "approved by lead",
        lead_reject: "rejected by lead",
        environment_approve: "environment-approved",
        mark_ci_ready: "marked CI ready",
      };
      toast({ title: `Script ${labels[action]}`, variant: "success" });
      loadData();
    } catch (lifecycleError) {
      toast({
        title: "Could not update script approval state",
        description: messageFromError(lifecycleError, ""),
        variant: "error",
      });
    } finally {
      setLifecycleBusyId(null);
    }
  }

  async function handleSaveDraft(scriptId: number, nextCode: string) {
    setSaveBusyId(scriptId);
    setError("");
    try {
      // Saving an in_review script back to draft via update is intentionally
      // blocked by the backend transition rules — author must Request Changes
      // first. Here we only update the code body.
      await automationApi.update(scriptId, { code: nextCode });
      toast({ title: "Draft saved", variant: "success" });
      loadData();
    } catch (saveError) {
      toast({ title: "Could not save draft", description: messageFromError(saveError, ""), variant: "error" });
    } finally {
      setSaveBusyId(null);
    }
  }

  async function handleTransitionScript(
    scriptId: number,
    action: "submit_for_review" | "request_changes" | "restore_draft",
  ) {
    setTransitionBusyId(scriptId);
    setError("");
    try {
      await automationApi.transition(scriptId, action);
      const label =
        action === "submit_for_review" ? "submitted for review"
        : action === "request_changes" ? "sent back for changes"
        : "restored to draft";
      toast({ title: `Script ${label}`, variant: "success" });
      loadData();
    } catch (transitionError) {
      toast({ title: "Could not transition script state", description: messageFromError(transitionError, ""), variant: "error" });
    } finally {
      setTransitionBusyId(null);
    }
  }

  const total = rows.length;

  // Phase 2B: build inventory items from TCs + planning + mappings + scripts.
  const inventoryItems = useMemo<InventoryItem[]>(() => {
    return rows.map((tc) => {
      const candidate = planningCandidates.find((c) => c.test_case_id === tc.id);
      const mapping = mappingByTestCase.get(tc.id);
      const scriptId = candidate?.script_id ?? null;
      const script = scriptId != null ? scriptsById.get(scriptId) ?? null : null;
      const isExternal = Boolean(mapping);
      return {
        id: tc.id,
        testCaseKey: tc.test_case_id,
        title: tc.title,
        module: tc.product ?? tc.product_group ?? null,
        testSuiteId: tc.test_suite_id ?? null,
        testSuiteName: tc.test_suite_name ?? null,
        priority: tc.priority,
        framework: candidate?.recommended_framework ?? script?.framework ?? null,
        automationKind: isExternal ? "external" : "internal",
        externalTool: mapping?.external_tool_name ?? null,
        scriptId: scriptId,
        scriptStatus: script?.status ?? candidate?.script_status ?? null,
        externalStatus: mapping?.automation_status ?? null,
        automationReady: candidate?.automation_ready ?? false,
        lastUpdated: script?.updated_at ?? null,
        quality: script ? getScriptQualitySignals(script) : null,
        staticGateFailed: script?.static_gate_result?.passed === false,
      };
    });
  }, [rows, planningCandidates, mappingByTestCase, scriptsById]);

  // Deep-link support: a "tc" query param (test case id) — set by e.g. the
  // execution page's "Regenerate script" action — pre-selects that item
  // instead of the default first-item selection, so a failure can send the
  // user straight to the script that caused it rather than leaving them to
  // hunt for it in the inventory list.
  useEffect(() => {
    if (selectedInventoryId != null || inventoryItems.length === 0) return;
    const tcParam = Number(searchParams.get("tc"));
    const target = Number.isFinite(tcParam) && inventoryItems.some((i) => i.id === tcParam)
      ? tcParam
      : inventoryItems[0].id;
    setSelectedInventoryId(target);
  }, [inventoryItems, selectedInventoryId, searchParams]);

  function handleToggleInventorySelect(id: number) {
    setSelectedInventoryIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleSelectManyInventory(ids: number[], checked: boolean) {
    setSelectedInventoryIds((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (checked) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }

  function handleBulkGenerate(ids: number[]) {
    setAiDialogPreselect(ids);
    setAiDialogOpen(true);
  }

  async function handleBulkApprove(ids: number[]) {
    const approvableStatuses = new Set(["in_review", "pending_approval", "under_review"]);
    const scriptIds = ids
      .map((id) => inventoryItems.find((i) => i.id === id))
      .filter(
        (item): item is InventoryItem =>
          !!item &&
          item.automationKind === "internal" &&
          item.scriptId != null &&
          approvableStatuses.has((item.scriptStatus ?? "").toLowerCase()),
      )
      .map((item) => item.scriptId as number);

    if (scriptIds.length === 0) {
      toast({
        title: "Nothing to approve",
        description: "Select test cases with a script currently in review.",
        variant: "error",
      });
      return;
    }

    setBulkApproveBusy(true);
    try {
      const res = await automationApi.bulkApprove(scriptIds, "approve");
      const { approved_count, failed_count } = res.data;
      toast({
        title: `${approved_count} script${approved_count === 1 ? "" : "s"} approved`,
        description: failed_count > 0 ? `${failed_count} could not be approved.` : undefined,
        variant: failed_count > 0 ? "error" : "success",
      });
      setSelectedInventoryIds(new Set());
      loadData();
    } catch (bulkError) {
      toast({ title: "Bulk approve failed", description: messageFromError(bulkError, ""), variant: "error" });
    } finally {
      setBulkApproveBusy(false);
    }
  }

  async function handleBulkDiscover(ids: number[]) {
    if (!selectedProject) return;
    // Each test case's own configured environment (test_phase) — not the
    // page's generic "environment" dropdown, which defaults to "staging"
    // and has nothing to do with what's actually configured for these test
    // cases' application. Mirrors the backend auto-chain's own fallback
    // (tc.test_phase or "QA").
    const idsByEnvironment = new Map<string, number[]>();
    for (const id of ids) {
      const env = rows.find((tc) => tc.id === id)?.test_phase || "QA";
      const group = idsByEnvironment.get(env) ?? [];
      group.push(id);
      idsByEnvironment.set(env, group);
    }

    setBulkDiscoverBusy(true);
    try {
      const results = await runAIAction({
        actionName: "discover_automation_ui",
        title: "Preparing Application Discovery",
        module: "Automation Studio",
        artifactType: "Discovery Sessions",
        projectId: selectedProject,
        stages: AI_PROCESSING_STAGES.applicationDiscovery,
        successMessage: "Application discovery requests were queued.",
        execute: () => Promise.allSettled(
          Array.from(idsByEnvironment.entries()).map(([env, groupIds]) =>
            automationApi.discoverUi(selectedProject, groupIds, env),
          ),
        ),
      });
      const failed = results.filter((r) => r.status === "rejected");
      if (failed.length === 0) {
        toast({
          title: "Discovery queued",
          description: "Opening a live browser session to ground automation in the real page. This can take a minute — locators will appear once it completes.",
          variant: "success",
        });
      } else {
        const firstError = (failed[0] as PromiseRejectedResult).reason;
        toast({
          title: failed.length === results.length ? "Could not start discovery" : "Some discovery runs could not start",
          description: messageFromError(firstError, ""),
          variant: "error",
        });
      }
      setSelectedInventoryIds(new Set());
    } finally {
      setBulkDiscoverBusy(false);
    }
  }

  const selectedItem = useMemo(
    () => inventoryItems.find((i) => i.id === selectedInventoryId) ?? null,
    [inventoryItems, selectedInventoryId],
  );

  const selectedScript = useMemo(() => {
    if (selectedInventoryId == null) return null;
    const candidate = planningCandidates.find((c) => c.test_case_id === selectedInventoryId);
    if (candidate?.script_id != null) {
      const direct = scriptsById.get(candidate.script_id);
      if (direct) return direct;
    }
    // Fallback: most recent script for this TC.
    return scripts
      .filter((s) => s.test_case_id === selectedInventoryId)
      .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))[0] ?? null;
  }, [selectedInventoryId, planningCandidates, scriptsById, scripts]);

  const selectedMapping = useMemo(
    () => (selectedInventoryId != null ? mappingByTestCase.get(selectedInventoryId) ?? null : null),
    [selectedInventoryId, mappingByTestCase],
  );

  // Phase 2B metric counts.
  const scriptsUnderReview = scripts.filter((s) => {
    const st = s.status.toLowerCase();
    return st === "in_review" || st === "pending_approval" || st === "under_review";
  }).length;
  const scriptsApproved = scripts.filter((s) => s.status.toLowerCase() === "approved").length;
  const externalsVerified = inventoryItems.filter(
    (i) => i.automationKind === "external" && i.automationReady,
  ).length;
  const readyForExecution = scriptsApproved + externalsVerified;
  const coveragePct = total > 0 ? ((readyForExecution / total) * 100).toFixed(0) : "0";

  const metrics = [
    {
      title: "Eligible for automation",
      icon: Wrench,
      iconBg: "bg-blue-50 border-blue-100",
      iconColor: "text-blue-500",
      value: total.toLocaleString(),
      sublabel: "Test cases",
      footer: "Approved & automation-eligible",
    },
    {
      title: "Scripts generated",
      icon: Sparkles,
      iconBg: "bg-violet-50 border-violet-100",
      iconColor: "text-violet-500",
      value: scripts.length.toLocaleString(),
      sublabel: "Drafts",
      footer: "AI Draft + Draft + In Review",
    },
    {
      title: "Under review",
      icon: Clock,
      iconBg: "bg-amber-50 border-amber-100",
      iconColor: "text-amber-500",
      value: scriptsUnderReview.toLocaleString(),
      sublabel: "Pending",
      footer: "Awaiting reviewer signoff",
    },
    {
      title: "Ready for execution",
      icon: ShieldCheck,
      iconBg: "bg-emerald-50 border-emerald-100",
      iconColor: "text-emerald-500",
      value: readyForExecution.toLocaleString(),
      sublabel: `${coveragePct}%`,
      footer: "Approved internal + verified external",
    },
  ];

  if (searchParams.get("view") === "discovery") {
    if (!selectedProject) {
      return <div className="p-8 text-sm font-semibold text-slate-400">Select a project to open Live Discovery Session.</div>;
    }
    return (
      <div className="space-y-6 select-none pb-8 animate-fade-in">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-blue-50 border border-blue-100 p-2.5">
            <Radar className="h-6 w-6 text-[#1b59f8]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Live Discovery Session</h1>
            <p className="text-xs text-slate-500 mt-1">Observe, record and ground application behaviour with governed evidence.</p>
          </div>
        </div>
        <DiscoverySessionView projectId={selectedProject} />
      </div>
    );
  }

  if (searchParams.get("view") === "workspace") {
    if (!selectedProject) {
      return <div className="p-8 text-sm font-semibold text-slate-400">Select a project to open Automation Workspace.</div>;
    }
    const suiteId = Number(searchParams.get("suite")) || null;
    return (
      <div className="min-h-full pb-8">
        {suiteId ? (
          <AutomationSuiteDetail projectId={selectedProject} suiteId={suiteId} />
        ) : (
          <AutomationSuiteDashboard projectId={selectedProject} />
        )}
      </div>
    );
  }

  if (searchParams.get("view") === "recorder") {
    if (!selectedProject) {
      return <div className="p-8 text-sm font-semibold text-slate-400">Select a project to open the Live Recorder.</div>;
    }
    const recordingId = Number(searchParams.get("recording")) || null;
    return (
      <div className="min-h-full pb-8">
        {recordingId ? (
          <LiveRecorderWorkspace projectId={selectedProject} recordingId={recordingId} />
        ) : (
          <div className="space-y-6 animate-fade-in">
            <div className="flex items-center gap-3">
              <div className="rounded-xl bg-blue-50 border border-blue-100 p-2.5">
                <Video className="h-6 w-6 text-[#1b59f8]" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-slate-900">Live Recorder</h1>
                <p className="text-xs text-slate-500 mt-1">
                  Record real interactions against the mapped application for one Automation Test Suite member.
                </p>
              </div>
            </div>
            <LiveRecorderLauncher projectId={selectedProject} />
          </div>
        )}
      </div>
    );
  }

  // UI-020/021/023 Automation Asset Workspace — one workspace, three tabs, over
  // one suite member. Each tab is its own addressable route so UI-020, UI-021
  // and UI-023 stay separately deep-linkable and acceptance-testable.
  {
    const view = searchParams.get("view");
    if (view === "ir" || view === "script" || view === "validation") {
      const memberId = Number(searchParams.get("member")) || null;
      const setParam = (next: Record<string, string>) => {
        const params = new URLSearchParams(searchParams.toString());
        Object.entries(next).forEach(([k, v]) => params.set(k, v));
        router.push(`/automation?${params.toString()}`);
      };
      // No member selected: land on the picker rather than a dead end. It is
      // also the Section 16 aging queue.
      if (!memberId) {
        if (!selectedProject) {
          return (
            <div className="p-8 text-sm font-semibold text-slate-400">
              Select a project to see its automation assets.
            </div>
          );
        }
        return (
          <div className="min-h-full pb-8">
            <AutomationAssetPicker
              projectId={selectedProject}
              onOpen={(id) => setParam({ view: "ir", member: String(id) })}
            />
          </div>
        );
      }
      return (
        <div className="min-h-full pb-8">
          <AutomationAssetWorkspace
            memberId={memberId}
            tab={view}
            onTabChange={(tab) => setParam({ view: tab })}
            onBackToSuite={(suiteId) =>
              setParam({ view: "workspace", suite: String(suiteId) })
            }
            onOpenRecorder={() => setParam({ view: "recorder" })}
          />
        </div>
      );
    }
  }

  if (searchParams.get("view") === "workspace-new") {
    if (!selectedProject) {
      return <div className="p-8 text-sm font-semibold text-slate-400">Select a project to create an Automation Test Suite.</div>;
    }
    return (
      <div className="min-h-full pb-8">
        <NewAutomationSuiteWizard projectId={selectedProject} />
      </div>
    );
  }

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Global Controls ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-blue-50 border border-blue-100 p-2.5">
            <Wrench className="h-6 w-6 text-[#1b59f8]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">AI Automation Studio</h1>
            <p className="text-xs text-slate-500 mt-1">Design. Generate. Review. Approve automation assets.</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <RunnerStatusChip />
          <select
            value={environment}
            onChange={(e) => setEnvironment(e.target.value)}
            className="appearance-none bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 rounded-lg text-xs font-semibold px-3 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-[#1b59f8] transition-colors cursor-pointer"
            style={{
              backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
              backgroundPosition: 'right 0.5rem center',
              backgroundSize: '1.25rem 1.25rem',
              backgroundRepeat: 'no-repeat',
            }}
          >
            {["development", "staging", "production", "ci"].map((env) => (
              <option key={env} value={env}>
                {env.toUpperCase()}
              </option>
            ))}
          </select>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setConvertManualOpen(true)}
            disabled={!selectedProject}
            className="gap-1.5 border-slate-200 text-slate-700 hover:bg-slate-50"
          >
            Convert manual flow
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setAssistantScript(null);
              setAssistantOpen(true);
            }}
            className="gap-1.5 border-violet-200 text-violet-700 hover:bg-violet-50"
          >
            <Bot className="h-3.5 w-3.5" />
            AI Assistant
          </Button>

          <Button
            size="sm"
            onClick={() => {
              setAiDialogPreselect([]);
              setAiDialogOpen(true);
            }}
            disabled={!selectedProject || testCases.length === 0}
            className="gap-1.5 bg-violet-600 hover:bg-violet-700 text-white"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Generate with AI
          </Button>

          <Button
            size="sm"
            onClick={() => setRunAllOpen(true)}
            disabled={!selectedProject || runAllCandidates.length === 0}
            className="gap-1.5"
            title={runAllCandidates.length === 0 ? "No approved scripts ready to run" : undefined}
          >
            <PlayCircle className="h-3.5 w-3.5" />
            Run All Eligible ({runAllCandidates.length})
          </Button>

          <Button variant="outline" size="sm" onClick={loadData} className="h-8 w-8 p-0 border-slate-200">
            <RefreshCw className={cn("h-3.5 w-3.5 text-slate-500", loading && "animate-spin")} />
          </Button>
        </div>
      </div>

      {/* ── Metric Cards ───────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {metrics.map((card) => {
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
      {/* ── AI Automation Studio workspace (Phase 2B) ─────────────────────────── */}
      <section className="grid gap-4 lg:grid-cols-[300px_1fr]">
        <div className="min-h-[480px]">
          <AutomationInventoryPanel
            items={inventoryItems}
            selectedId={selectedInventoryId}
            onSelect={(item) => setSelectedInventoryId(item.id)}
            selectedIds={selectedInventoryIds}
            onToggleSelect={handleToggleInventorySelect}
            onSelectMany={handleSelectManyInventory}
            onBulkGenerate={handleBulkGenerate}
            onBulkApprove={handleBulkApprove}
            onBulkDiscover={handleBulkDiscover}
            bulkBusy={bulkApproveBusy}
            bulkDiscoverBusy={bulkDiscoverBusy}
          />
        </div>
        <div className="space-y-4">
          <AutomationWorkspace
            item={selectedItem}
            script={selectedScript}
            mapping={selectedMapping}
            busyApprove={reviewBusyId != null}
            busyTransition={transitionBusyId != null}
            busySave={saveBusyId != null}
            busyLifecycle={lifecycleBusyId != null}
            onApprove={async (action) => {
              if (!selectedScript) return;
              await handleReviewScript(selectedScript.id, action);
            }}
            onLifecycleApprove={async (action) => {
              if (!selectedScript) return;
              await handleLifecycleApproval(selectedScript.id, action);
            }}
            onTransition={async (action) => {
              if (!selectedScript) return;
              await handleTransitionScript(selectedScript.id, action);
            }}
            onSaveDraft={async (code) => {
              if (!selectedScript) return;
              await handleSaveDraft(selectedScript.id, code);
            }}
            onConfigureExternal={() => {
              if (!selectedItem) return;
              const tc = testCases.find((t) => t.id === selectedItem.id);
              if (tc) handleRowClick(tc);
            }}
            onRunSandbox={() => {
              if (!selectedScript) return;
              setSandboxTarget({
                scriptId: selectedScript.id,
                framework: selectedScript.framework,
                label: `${selectedScript.script_id}${selectedItem ? ` — ${selectedItem.title}` : ""}`,
              });
            }}
            onOpenAssistant={() => {
              setAssistantScript(selectedScript);
              setAssistantOpen(true);
            }}
            onGenerate={() => {
              if (!selectedItem) return;
              setAiDialogPreselect([selectedItem.id]);
              setAiDialogOpen(true);
            }}
            onTrace={() => {
              if (!selectedScript) return;
              setTraceTarget({
                entityType: "automation_script",
                entityId: selectedScript.id,
                label: selectedScript.script_id,
              });
            }}
          />
          <ScriptRunsStrip
            script={selectedScript}
            runs={runs}
            projectId={selectedProject}
            onOpenRun={setOpenRun}
          />
        </div>
      </section>

      {/* Phase 2D: legacy detail table removed — workspace action bar now owns per-row actions. */}

      {/* ── Details & Control Drawer ───────────────────────────────────────────── */}
      <Drawer open={drawerOpen} onOpenChange={setDrawerOpen}>
        <DrawerContent size="lg">
          {selectedTestCase && (
            <>
              <DrawerHeader>
                <div className="flex items-center gap-2">
                  <Terminal className="h-5 w-5 text-[#1b59f8]" />
                  <div className="min-w-0">
                    <DrawerTitle className="truncate">Automated Case: {selectedTestCase.test_case_id}</DrawerTitle>
                    <DrawerDescription className="truncate">{selectedTestCase.title}</DrawerDescription>
                  </div>
                </div>
                <button onClick={() => setDrawerOpen(false)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-50"><X className="h-4 w-4" /></button>
              </DrawerHeader>

              {/* Action Buttons Hub inside Drawer */}
              <div className="bg-slate-50 border-b border-slate-100 p-4 flex flex-wrap gap-2">
                <Button
                  variant="default"
                  size="sm"
                  disabled={busyId === selectedTestCase.id || !mappingByTestCase.has(selectedTestCase.id)}
                  onClick={() => handleRunAutomation(selectedTestCase)}
                  className="text-xs font-semibold h-8"
                >
                  <PlayCircle className="h-3.5 w-3.5 mr-1" />
                  Run Test
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busyId === selectedTestCase.id || !mappingByTestCase.has(selectedTestCase.id)}
                  onClick={() => {
                    const m = mappingByTestCase.get(selectedTestCase.id);
                    if (m) handleSyncAutomation(m);
                  }}
                  className="text-xs font-semibold h-8 border-slate-200 text-slate-600 bg-white"
                >
                  <RefreshCw className={cn("h-3.5 w-3.5 mr-1", busyId === selectedTestCase.id && "animate-spin")} />
                  Sync Agent Result
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busyId === selectedTestCase.id}
                  onClick={() => handleSyncJira(selectedTestCase)}
                  className="text-xs font-semibold h-8 border-slate-200 text-slate-600 bg-white"
                >
                  <ShieldCheck className="h-3.5 w-3.5 mr-1" />
                  Sync Jira QA Status
                </Button>
              </div>

              {/* Tab Selector */}
              <div className="flex border-b border-slate-100 px-4 bg-white shrink-0">
                <button
                  onClick={() => setDrawerTab("mapping")}
                  className={cn(
                    "px-4 py-2.5 text-xs font-bold border-b-2 transition-colors",
                    drawerTab === "mapping" ? "border-[#1b59f8] text-[#1b59f8]" : "border-transparent text-slate-500 hover:text-slate-900"
                  )}
                >
                  Mapping Configuration
                </button>
                <button
                  onClick={() => setDrawerTab("history")}
                  className={cn(
                    "px-4 py-2.5 text-xs font-bold border-b-2 transition-colors",
                    drawerTab === "history" ? "border-[#1b59f8] text-[#1b59f8]" : "border-transparent text-slate-500 hover:text-slate-900"
                  )}
                >
                  Execution History
                </button>
              </div>

              <DrawerBody className="space-y-5">
                {drawerTab === "mapping" && (
                  <form onSubmit={handleSaveMapping} className="space-y-4">
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External Tool Name</label>
                      <input
                        value={mappingForm.external_tool_name}
                        onChange={(e) => setMappingForm((f) => ({ ...f, external_tool_name: e.target.value }))}
                        className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50"
                        placeholder="e.g. Playwright, Katalon, Pytest, Mock"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External Project ID</label>
                      <input
                        value={mappingForm.external_project_id}
                        onChange={(e) => setMappingForm((f) => ({ ...f, external_project_id: e.target.value }))}
                        className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50"
                        placeholder="e.g. BSS-ACTIVATIONS"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External Suite ID</label>
                      <input
                        value={mappingForm.external_suite_id}
                        onChange={(e) => setMappingForm((f) => ({ ...f, external_suite_id: e.target.value }))}
                        className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50"
                        placeholder="e.g. REGRESSION-SIT"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External automated test case ID</label>
                      <input
                        value={mappingForm.external_test_case_id}
                        onChange={(e) => setMappingForm((f) => ({ ...f, external_test_case_id: e.target.value }))}
                        className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50 font-mono"
                        placeholder="e.g. tc_activate_esim_01"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External Script ID (Optional)</label>
                      <input
                        value={mappingForm.external_script_id}
                        onChange={(e) => setMappingForm((f) => ({ ...f, external_script_id: e.target.value }))}
                        className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50 font-mono"
                        placeholder="e.g. scripts/activate_esim.py"
                      />
                    </div>

                    <div className="pt-2">
                      <Button
                        type="submit"
                        variant="default"
                        size="sm"
                        disabled={busyId === selectedTestCase.id}
                        className="w-full text-xs font-bold"
                      >
                        {busyId === selectedTestCase.id ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Link2 className="h-3.5 w-3.5 mr-1" />}
                        Save Mapping Config
                      </Button>
                    </div>
                  </form>
                )}

                {drawerTab === "history" && (
                  <div className="space-y-4">
                    {historyLoading ? (
                      <div className="flex flex-col items-center justify-center py-12 text-slate-400 text-xs font-semibold">
                        <Loader2 className="h-5 w-5 animate-spin text-[#1b59f8] mb-2" />
                        Loading execution history logs...
                      </div>
                    ) : historyRows.length === 0 ? (
                      <div className="text-center py-12 text-slate-400 font-semibold text-xs">
                        No automated runs recorded for this case.
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {historyRows.map((row) => (
                          <div key={row.id} className="rounded-lg border border-slate-150 p-3 bg-slate-50/50 space-y-2.5">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="text-[10px] font-mono text-slate-400">{new Date(row.created_at).toLocaleString()}</span>
                              <div className="flex gap-1.5">
                                <Badge variant={getStatusVariant(row.automation_execution_status ?? row.status)}>
                                  {row.automation_execution_status ?? row.status}
                                </Badge>
                                <Badge variant={getStatusVariant(row.jira_execution_status)}>
                                  Jira: {row.jira_execution_status ?? "Unsynced"}
                                </Badge>
                              </div>
                            </div>

                            {row.error_message && (
                              <div className="text-[11px] bg-red-50 border border-red-100 rounded p-2 text-red-700 font-semibold">
                                {row.error_message}
                              </div>
                            )}

                            {/* Evidence files */}
                            <div className="flex flex-wrap gap-1.5 pt-1">
                              {row.external_result_url && (
                                <a
                                  href={row.external_result_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="inline-flex items-center gap-1 bg-white hover:bg-slate-50 border border-slate-200 text-slate-600 rounded px-2 py-1 text-[10px] font-bold"
                                >
                                  <ExternalLink className="h-3 w-3" />
                                  External Report
                                </a>
                              )}
                              {row.log_url && (
                                <a
                                  href={row.log_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="inline-flex items-center gap-1 bg-white hover:bg-slate-50 border border-slate-200 text-slate-600 rounded px-2 py-1 text-[10px] font-bold"
                                >
                                  <FileText className="h-3 w-3" />
                                  Evidence logs
                                </a>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </DrawerBody>
              <DrawerFooter>
                <Button variant="outline" size="sm" onClick={() => setDrawerOpen(false)} className="w-full h-9 border-slate-200 bg-white">Close Detail</Button>
              </DrawerFooter>
            </>
          )}
        </DrawerContent>
      </Drawer>

      {/* ── AI Generated Scripts Section ────────────────────────────────────────── */}
      <section className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <button
          onClick={() => setShowAiScripts(!showAiScripts)}
          className="flex w-full items-center justify-between px-5 py-4 text-left hover:bg-slate-50/50 transition-colors"
        >
          <span className="inline-flex items-center gap-2 text-xs font-bold text-slate-800">
            <Bot className="h-4.5 w-4.5 text-violet-600" />
            AI-Generated Automation Scripts Repository
          </span>
          <Badge variant={showAiScripts ? "purple" : "secondary"}>
            {showAiScripts ? "Hide List" : `${scripts.length} Scripts`}
          </Badge>
        </button>
        {showAiScripts && (
          <div className="border-t border-slate-200 p-5 bg-slate-50/30">
            <p className="mb-4 text-xs text-slate-500 leading-relaxed font-semibold">
              Draft generation stays here in Automation. Human review, repository metadata, and approval happen before the Execution module orchestrates a run.
            </p>
            <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
              {scripts.map((script) => (
                <div key={script.id} className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[10px] font-bold text-[#1b59f8]">{script.script_id}</span>
                        <Badge variant={script.framework === "playwright" ? "purple" : "info"}>{frameworkLabel(script.framework)}</Badge>
                        <Badge variant={getStatusVariant(script.status)}>{script.status}</Badge>
                      </div>
                      <p className="mt-2 truncate font-semibold text-slate-700">{script.file_path || "Generated Script"}</p>
                      <p className="mt-1 text-[10px] font-semibold text-slate-400">
                        {scriptRepository(script).repository || "Repository pending"} • {scriptRepository(script).branch || "codex/automation-drafts"}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 border-emerald-200 text-xs text-emerald-700"
                        disabled={reviewBusyId === script.id || script.status === "approved"}
                        onClick={() => handleReviewScript(script.id, "approve")}
                      >
                        {reviewBusyId === script.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Approve"}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 border-rose-200 text-xs text-rose-600"
                        disabled={reviewBusyId === script.id || script.status === "rejected"}
                        onClick={() => handleReviewScript(script.id, "reject")}
                      >
                        Reject
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
              {scripts.length === 0 && (
                <p className="text-xs text-slate-400 font-semibold text-center py-6">No AI-generated scripts found.</p>
              )}
            </div>
          </div>
        )}
      </section>

      {/* ── Studio insights: script status mix + run confidence ─────────────── */}
      <StudioInsightsRow scripts={scripts} runs={runs} projectId={selectedProject} />

      {/* ── AI Automation Studio — Phase 2A ──────────────────────────────────── */}
      <GenerateWithAIDialog
        open={aiDialogOpen}
        onClose={() => setAiDialogOpen(false)}
        projectId={selectedProject}
        approvedTestCases={testCases}
        preselectedIds={aiDialogPreselect}
        onGenerated={(count) => {
          toast({
            title: `AI generation queued for ${count} test case${count === 1 ? "" : "s"}`,
            description: "Drafts will appear once the agent completes.",
            variant: "success",
          });
          loadData();
        }}
      />

      <IntelligenceAssistantPanel
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        script={assistantScript}
      />

      <ConvertManualToAutomationDialog
        open={convertManualOpen}
        onClose={() => setConvertManualOpen(false)}
        projectId={selectedProject}
        onConverted={(count) => {
          toast({
            title: `Manual-to-automation conversion queued for ${count} test case${count === 1 ? "" : "s"}`,
            description: "AI Drafts will appear once the agent completes.",
            variant: "success",
          });
          loadData();
        }}
      />

      {/* ── Sandbox run trigger + run detail ─────────────────────────────────── */}
      {selectedProject && (
        <RunTriggerDialog
          target={sandboxTarget}
          onClose={() => setSandboxTarget(null)}
          projectId={selectedProject}
          defaultEnvironment={environment}
          environments={planning?.summary.available_environments ?? []}
        />
      )}
      {selectedProject && (
        <RunAllEligibleDialog
          open={runAllOpen}
          onClose={() => setRunAllOpen(false)}
          projectId={selectedProject}
          candidates={runAllCandidates}
          defaultEnvironment={environment}
          environments={planning?.summary.available_environments ?? []}
          onStarted={(executionRunId) => router.push(`/execution/automation?project=${selectedProject}&run=${executionRunId}`)}
        />
      )}
      <RunDetailDrawer
        runId={openRun?.id ?? null}
        open={openRun !== null}
        onOpenChange={(o) => { if (!o) setOpenRun(null); }}
        initialRun={openRun}
      />
      <TraceabilityDrawer target={traceTarget} onClose={() => setTraceTarget(null)} />
    </div>
  );
}

const SCRIPT_STATUS_COLORS: Record<string, string> = {
  ai_draft: "#8b5cf6",
  draft: "#94a3b8",
  in_review: "#0ea5e9",
  pending_approval: "#0ea5e9",
  approved: "#10b981",
  rejected: "#ef4444",
  executed: "#059669",
  deprecated: "#cbd5e1",
  blocked: "#f97316",
};

/** Script status distribution donut + average sandbox-run confidence. */
function StudioInsightsRow({
  scripts,
  runs,
  projectId,
}: {
  scripts: AutomationScript[];
  runs: ExecutionRun[];
  projectId: number | null;
}) {
  const distribution = useMemo(() => {
    const counts = new Map<string, number>();
    for (const s of scripts) {
      const key = (s.status ?? "unknown").toLowerCase();
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return Array.from(counts.entries()).map(([status, count]) => ({
      status,
      label: status.replace(/_/g, " "),
      count,
      color: SCRIPT_STATUS_COLORS[status] ?? "#64748b",
    }));
  }, [scripts]);

  const runStats = useMemo(() => {
    const automationRuns = runs.filter((r) => r.execution_type === "automation");
    const confidences = automationRuns
      .map((r) => r.confidence_score)
      .filter((c): c is number => c !== null && c !== undefined);
    const avgConfidence = confidences.length > 0
      ? Math.round(confidences.reduce((a, b) => a + b, 0) / confidences.length)
      : null;
    const terminal = automationRuns.filter((r) => (r.passed ?? 0) + (r.failed ?? 0) > 0);
    const passed = terminal.reduce((a, r) => a + (r.passed ?? 0), 0);
    const failed = terminal.reduce((a, r) => a + (r.failed ?? 0), 0);
    const passRate = passed + failed > 0 ? Math.round((passed / (passed + failed)) * 100) : null;
    return { total: automationRuns.length, avgConfidence, passRate };
  }, [runs]);

  if (scripts.length === 0) return null;

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Card className="border-slate-200">
        <CardContent className="p-4">
          <p className="mb-3 text-xs font-bold text-slate-800">Scripts by status</p>
          <div className="flex items-center gap-4">
            <ResponsiveContainer width={110} height={110}>
              <PieChart>
                <Pie
                  data={distribution}
                  dataKey="count"
                  nameKey="label"
                  innerRadius={32}
                  outerRadius={52}
                  paddingAngle={2}
                >
                  {distribution.map((d) => (
                    <Cell key={d.status} fill={d.color} />
                  ))}
                </Pie>
                <RechartsTooltip
                  formatter={(value: number, name: string) => [value, name]}
                  contentStyle={{ fontSize: 11, borderRadius: 8 }}
                />
              </PieChart>
            </ResponsiveContainer>
            <ul className="min-w-0 flex-1 space-y-1">
              {distribution.map((d) => (
                <li key={d.status} className="flex items-center gap-2 text-[11px]">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: d.color }} />
                  <span className="capitalize text-slate-600">{d.label}</span>
                  <span className="ml-auto font-semibold tabular-nums text-slate-800">{d.count}</span>
                </li>
              ))}
            </ul>
          </div>
        </CardContent>
      </Card>

      <Card className="border-slate-200">
        <CardContent className="p-4">
          <p className="mb-3 text-xs font-bold text-slate-800">Sandbox run health</p>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Runs</p>
              <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900">{runStats.total}</p>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Pass rate</p>
              <p className="mt-1 text-2xl font-bold tabular-nums text-emerald-600">
                {runStats.passRate !== null ? `${runStats.passRate}%` : "—"}
              </p>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Avg confidence</p>
              <p className="mt-1 text-2xl font-bold tabular-nums text-violet-600">
                {runStats.avgConfidence !== null ? `${runStats.avgConfidence}%` : "—"}
              </p>
            </div>
          </div>
          {projectId && (
            <div className="mt-3 border-t border-slate-50 pt-2 text-right">
              <a
                href={`/execution/dashboard?project=${projectId}`}
                className="text-[11px] text-[#1b59f8] hover:underline"
              >
                Full analytics →
              </a>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** Recent local-runner runs for the selected script, newest first. */
function ScriptRunsStrip({
  script,
  runs,
  projectId,
  onOpenRun,
}: {
  script: AutomationScript | null;
  runs: ExecutionRun[];
  projectId: number | null;
  onOpenRun: (run: ExecutionRun) => void;
}) {
  const scriptRuns = useMemo(() => {
    if (!script) return [];
    return runs
      .filter((r) => {
        const meta = (r.metadata_ ?? {}) as { automation_script_id?: number };
        return meta.automation_script_id === script.id;
      })
      .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))
      .slice(0, 5);
  }, [script, runs]);

  if (!script) return null;

  return (
    <Card className="border-slate-200">
      <CardContent className="p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-800">
            <History className="h-3.5 w-3.5 text-slate-400" />
            Recent runs — {script.script_id}
          </span>
          {projectId && (
            <a
              href={`/execution/automation?project=${projectId}&tab=history`}
              className="text-[11px] text-[#1b59f8] hover:underline"
            >
              All runs →
            </a>
          )}
        </div>
        {scriptRuns.length === 0 ? (
          <p className="rounded border border-dashed border-slate-200 px-3 py-3 text-center text-[11px] text-slate-400">
            No sandbox runs yet. Approve the script, then use “Run in sandbox”.
          </p>
        ) : (
          <div className="divide-y divide-slate-50">
            {scriptRuns.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => onOpenRun(r)}
                className="flex w-full items-center gap-3 py-2 text-left text-xs hover:bg-slate-50/60"
              >
                <span className="w-24 shrink-0 font-mono text-[#1b59f8]">{r.execution_id}</span>
                <RunVerdictBadge run={r} />
                <span className="text-slate-500">{r.environment ?? "—"}</span>
                <span className="ml-auto tabular-nums text-slate-400">
                  {formatDate(r.started_at ?? r.created_at)}
                </span>
                <span className="w-16 text-right font-mono tabular-nums text-slate-400">
                  {formatDuration(r.duration_seconds)}
                </span>
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function isAutomationVisible(tc: TestCase) {
  return ["automation", "automated", "hybrid"].includes((tc.execution_mode || "").toLowerCase()) && (tc.automation_eligible || "").toLowerCase() === "yes";
}

function frameworkLabel(framework: string) {
  return framework === "pytest" ? "pytest" : "Playwright";
}

function scriptRepository(script: AutomationScript) {
  const metadata = script.metadata_ && typeof script.metadata_ === "object" ? script.metadata_ : {};
  return {
    repository: typeof metadata.repository === "string" ? metadata.repository : null,
    branch: typeof metadata.branch === "string" ? metadata.branch : null,
  };
}


export default function AutomationPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-slate-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-[#1b59f8] mr-2" />
        Loading AI Automation Studio...
      </div>
    }>
      <AutomationContent />
    </Suspense>
  );
}
