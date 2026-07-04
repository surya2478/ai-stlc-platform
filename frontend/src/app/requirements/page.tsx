"use client";

import { useState, useEffect, useCallback, useMemo, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  FileText, Upload, Bot, CheckCircle, XCircle, RefreshCw, AlertTriangle, Star, Trash2, X, Plug, Search, Download, Plus, Settings, ChevronRight, Loader2, ShieldCheck, Clock, Globe, GitBranch, BarChart2, ChevronDown
} from "lucide-react";
import {
  requirementsApi,
  documentsApi,
  projectsApi,
  jiraApi,
  agentRunsApi,
  traceabilityApi,
  exportApi,
  type Requirement,
  type RequirementCoverage,
  type RequirementTraceabilityChain,
  type Document,
  type JiraConnection,
  type JiraIssue,
  type JiraIssueFilters,
  type JiraIssuePage,
} from "@/lib/api";
import { AuditStamp } from "@/components/ui/AuditStamp";
import { useUserDirectory } from "@/hooks/useUserDirectory";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerBody, DrawerFooter
} from "@/components/ui/drawer";

// Status Chip Variant Mapping
function getStatusVariant(status: string | null | undefined): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  if (!status) return "outline";
  const s = status.toLowerCase();
  if (["approved", "connected", "processed"].includes(s)) return "success";
  if (["rejected", "failed", "error"].includes(s)) return "destructive";
  if (["pending_review", "uploaded"].includes(s)) return "warning";
  if (["draft", "uploaded", "disconnected"].includes(s)) return "secondary";
  return "outline";
}

function getQualityVariant(verdict: string | null | undefined): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  if (!verdict) return "outline";
  const s = verdict.toLowerCase();
  if (s === "pass") return "success";
  if (s === "needs_revision") return "warning";
  return "destructive";
}

function QualityBadge({ score, verdict }: { score?: number; verdict?: string }) {
  if (!verdict) return null;
  return (
    <div className="flex items-center gap-1">
      <Star className="h-3 w-3 text-amber-500 fill-amber-400 shrink-0" />
      <Badge variant={getQualityVariant(verdict)}>
        {score !== undefined ? `${Number(score).toFixed(1)}/5` : verdict.replace(/_/g, " ")}
      </Badge>
    </div>
  );
}

function ConfirmDeleteModal({
  title,
  description,
  onConfirm,
  onCancel,
}: {
  title: string;
  description: string;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    setDeleting(true);
    setError(null);
    try {
      await onConfirm();
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Delete failed. Please try again.");
      setDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4" onClick={onCancel}>
      <div className="w-full max-w-sm rounded-2xl border bg-white shadow-2xl p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start gap-3">
          <div className="rounded-full bg-red-50 border border-red-100 p-2 shrink-0">
            <AlertTriangle className="h-5 w-5 text-red-500" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="font-bold text-sm text-slate-800">{title}</h2>
            <p className="text-xs text-slate-500 mt-1.5 leading-relaxed font-semibold">{description}</p>
          </div>
          <button onClick={onCancel} className="rounded-md p-1 hover:bg-slate-50 text-slate-400 shrink-0">
            <X className="h-4 w-4" />
          </button>
        </div>
        {error && (
          <div className="rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-700 font-semibold">
            {error}
          </div>
        )}
        <div className="flex gap-2 pt-1">
          <Button onClick={onCancel} disabled={deleting} variant="outline" size="sm" className="flex-1 h-9 border-slate-200 text-slate-650 bg-white">
            Cancel
          </Button>
          <Button onClick={handleConfirm} disabled={deleting} variant="default" size="sm" className="flex-1 h-9 bg-rose-600 hover:bg-rose-700 font-semibold text-white">
            {deleting ? <RefreshCw className="h-4 w-4 animate-spin mr-1" /> : <Trash2 className="h-4 w-4 mr-1" />}
            {deleting ? "Deleting…" : "Delete"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function clampNumber(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, Math.trunc(value)));
}

function splitCsv(value: string) {
  const items = value.split(",").map((item) => item.trim()).filter(Boolean);
  return items.length ? items : undefined;
}

// UI Analysis Agent insight lists (validation_rules, negative_scenarios, edge_cases)
// can come back as plain strings OR as structured objects depending on which
// agent path produced them. Coerce each entry to a readable display string so
// React doesn't blow up trying to render an object as a child.
function renderInsightItem(item: unknown): string {
  if (item === null || item === undefined) return "";
  if (typeof item === "string") return item;
  if (typeof item === "number" || typeof item === "boolean") return String(item);
  if (typeof item === "object") {
    const obj = item as Record<string, unknown>;
    // Common shape from the UI Analysis Agent — a field validation rule
    if ("field_name" in obj) {
      const field = obj.field_name;
      const constraints: string[] = [];
      if (obj.type) constraints.push(`type=${String(obj.type)}`);
      if (obj.required) constraints.push("required");
      if (obj.pattern) constraints.push(`pattern=${String(obj.pattern)}`);
      if (obj.min !== undefined && obj.min !== null) constraints.push(`min=${String(obj.min)}`);
      if (obj.max !== undefined && obj.max !== null) constraints.push(`max=${String(obj.max)}`);
      if (obj.minlength !== undefined && obj.minlength !== null) constraints.push(`minLength=${String(obj.minlength)}`);
      if (obj.maxlength !== undefined && obj.maxlength !== null) constraints.push(`maxLength=${String(obj.maxlength)}`);
      const tail = constraints.length ? ` (${constraints.join(", ")})` : "";
      return `${String(field)}${tail}`;
    }
    // Generic fallback — pick a sensible label field, else stringify briefly
    const label = obj.title ?? obj.name ?? obj.description ?? obj.summary ?? obj.text;
    if (label !== undefined && label !== null) return String(label);
    try {
      return JSON.stringify(item);
    } catch {
      return "[unrenderable]";
    }
  }
  return String(item);
}

const emptyJiraConnectionForm = {
  jira_base_url: "",
  jira_email: "",
  jira_api_token: "",
  jira_project_key: "",
};

const defaultJiraFilters = {
  issue_types: "",
  statuses: "",
  priorities: "",
  labels: "",
  assignee: "",
  text: "",
  updated_since: "",
  jql: "",
  page_size: 25,
  max_issues: 500,
};

const jiraStoryTypePreset = "Story, User Story, Requirement, Epic";

// Hoisted outside component to avoid SWC `as const` ambiguity inside JSX
const EXPORT_MENU_OPTIONS: Array<["test-cases-excel" | "test-cases-csv" | "test-cases-xray" | "matrix-excel", string, string]> = [
  ["test-cases-excel", "Test Cases (.xlsx)", "Excel workbook — all test cases with full metadata"],
  ["test-cases-csv",   "Test Cases (.csv)",  "Plain CSV — compatible with any tool"],
  ["test-cases-xray",  "Xray CSV (.csv)",    "Xray Jira import format — one row per step"],
  ["matrix-excel",     "Traceability Matrix (.xlsx)", "Req → Test → Execution matrix + Summary sheet"],
];

function RequirementsContent() {
  const { resolveUser } = useUserDirectory();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProject = Number(searchParams.get("project")) || null;

  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentStatus, setAgentStatus] = useState<string>("");
  const [agentError, setAgentError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [tab, setTab] = useState<"requirements" | "documents" | "url" | "jira" | "github">("requirements");
  // GAP-3: GitHub / local repo analysis state
  const [githubUrl, setGithubUrl] = useState("");
  const [githubBranch, setGithubBranch] = useState("main");
  const [githubToken, setGithubToken] = useState("");
  const [localRepoPath, setLocalRepoPath] = useState("");
  const [repoLanguages, setRepoLanguages] = useState("python,javascript,typescript");
  const [codeAnalysisBusy, setCodeAnalysisBusy] = useState(false);
  const [codeAnalysisSource, setCodeAnalysisSource] = useState<"github" | "local" | null>(null);
  const [deletingReq, setDeletingReq] = useState<Requirement | null>(null);
  const [deletingDoc, setDeletingDoc] = useState<Document | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Jira Connection states
  const [jiraConnections, setJiraConnections] = useState<JiraConnection[]>([]);
  const [selectedJiraConnection, setSelectedJiraConnection] = useState<number | null>(null);
  const [jiraConnectionForm, setJiraConnectionForm] = useState(emptyJiraConnectionForm);
  const [showJiraConnectionForm, setShowJiraConnectionForm] = useState(false);
  const [editingJiraConnectionId, setEditingJiraConnectionId] = useState<number | null>(null);
  const [jiraFilters, setJiraFilters] = useState(defaultJiraFilters);
  const [jiraIssuesPage, setJiraIssuesPage] = useState<JiraIssuePage | null>(null);
  const [jiraBusy, setJiraBusy] = useState(false);
  const [jiraMessage, setJiraMessage] = useState<string | null>(null);
  const [jiraError, setJiraError] = useState<string | null>(null);

  // Drawer states
  const [selectedReq, setSelectedReq] = useState<Requirement | null>(null);
  // GAP-4d: coverage insights for the selected requirement
  const [coverage, setCoverage] = useState<RequirementCoverage | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(false);
  // GAP-5: drawer tab state (details | traceability)
  const [drawerTab, setDrawerTab] = useState<"details" | "traceability">("details");
  // GAP-5: traceability chain for selected requirement
  const [traceChain, setTraceChain] = useState<RequirementTraceabilityChain | null>(null);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState<string | null>(null);
  // GAP-5: export state
  const [exportBusy, setExportBusy] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [showExportMenu, setShowExportMenu] = useState(false);
  // GAP-2: portal URL analysis input
  const [portalUrl, setPortalUrl] = useState("");
  const [urlCrawlDepth, setUrlCrawlDepth] = useState(0);
  const [notes, setNotes] = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);
  // Test Environment + Generation Notes — tester-set context for AI test-case
  // generation, editable per requirement in the Details tab.
  const [genEnvDraft, setGenEnvDraft] = useState("");
  const [genNotesDraft, setGenNotesDraft] = useState("");
  const [savingGenContext, setSavingGenContext] = useState(false);
  const [genContextSaved, setGenContextSaved] = useState(false);

  // Load Projects on mount
  useEffect(() => {
    projectsApi.list()
      .then((res) => {
        if (res.data.length > 0 && !searchParams.get("project")) {
          const params = new URLSearchParams(searchParams.toString());
          params.set("project", String(res.data[0].id));
          router.push(`${pathname}?${params.toString()}`);
        }
      })
      .catch((e: any) => setLoadError(e?.response?.data?.detail || e?.message || "Failed to load projects."));
  }, [searchParams]);

  // Load Requirements and Documents
  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoadError(null);
    setLoading(true);
    try {
      const [reqRes, docRes] = await Promise.all([
        requirementsApi.list(selectedProject),
        documentsApi.list(selectedProject),
      ]);
      setRequirements(reqRes.data);
      setDocuments(docRes.data);
    } catch (e: any) {
      setLoadError(e?.response?.data?.detail || e?.message || "Failed to load requirements data.");
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Poll documents list if any document is in "uploaded" or "processing" state
  useEffect(() => {
    if (!selectedProject || documents.length === 0) return;
    const hasProcessingDocs = documents.some(
      (d) => d.status === "uploaded" || d.status === "processing"
    );
    if (!hasProcessingDocs) return;

    const interval = setInterval(async () => {
      try {
        const docRes = await documentsApi.list(selectedProject);
        setDocuments(docRes.data);
      } catch (err) {
        console.error("Failed to poll documents list:", err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [selectedProject, documents]);

  // Reset page when project changes
  useEffect(() => {
    setJiraIssuesPage(null);
    setJiraMessage(null);
    setJiraError(null);
    setSelectedReq(null);
    setNotes("");
  }, [selectedProject]);

  const loadJiraConnections = useCallback(async (options?: { preserveFeedback?: boolean }) => {
    if (!selectedProject) return;
    if (!options?.preserveFeedback) setJiraError(null);
    try {
      const res = await jiraApi.listConnections(selectedProject);
      setJiraConnections(res.data);
      setSelectedJiraConnection((current) => {
        if (current && res.data.some((connection) => connection.id === current)) return current;
        return res.data[0]?.id ?? null;
      });
      setShowJiraConnectionForm(res.data.length === 0);
    } catch (e: any) {
      setJiraConnections([]);
      setSelectedJiraConnection(null);
      setShowJiraConnectionForm(false);
      setJiraError(
        e?.response?.status === 453 || e?.response?.status === 403
          ? "You do not have sync_jira permission for this project."
          : "Failed to load Jira connections."
      );
    }
  }, [selectedProject]);

  useEffect(() => {
    loadJiraConnections();
  }, [loadJiraConnections]);

  const handleFileUpload = async (file: File) => {
    if (!selectedProject) return;
    setUploading(true);
    try {
      await documentsApi.upload(selectedProject, file);
      await loadData();
      setTab("documents");
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setAgentStatus(detail ? `Upload failed: ${detail}` : "Upload failed — check backend logs.");
      setTab("documents");
    } finally {
      setUploading(false);
    }
  };

  const pollAgentRun = async (
    runId: number,
    completedMessage: string,
    failedFallback: string,
    options?: {
      zeroCountError?: string;
    },
  ) => {
    for (let attempt = 0; attempt < 100; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      try {
        const res = await agentRunsApi.get(runId);
        const run = res.data;
        if (run.progress_message) {
          setAgentStatus(`${run.progress_message} (${run.progress_percent ?? 0}%)`);
        }
        if (run.status === "completed") {
          const count = typeof run.output_data?.count === "number" ? run.output_data.count : null;
          if (options?.zeroCountError && count === 0) {
            setAgentError(options.zeroCountError);
            setAgentStatus("");
            await loadData();
            return;
          }
          setAgentStatus(completedMessage);
          await loadData();
          return;
        }
        if (run.status === "failed") {
          setAgentError(run.error_message || failedFallback);
          setAgentStatus("");
          return;
        }
      } catch (err) {
        console.error("Error polling agent run:", err);
      }
    }
    setAgentStatus("Still running. Check Agent Logs for progress.");
  };

  const runIntakeAgent = async (docId: number) => {
    if (!selectedProject) return;
    setAgentRunning(true);
    setAgentStatus("Agent 1 running -- extracting requirements from document...");
    setAgentError(null);
    try {
      const res = await requirementsApi.triggerIntake(selectedProject, docId);
      const data = res.data as { message?: string; agent_run_id?: number };
      if (data.agent_run_id) {
        setAgentStatus(data.message ?? "Requirement intake queued.");
        await pollAgentRun(data.agent_run_id, "Requirements extracted successfully.", "Requirement extraction failed.");
      } else {
        setAgentStatus(`Done: ${data.message || "Extraction completed successfully"}`);
        await loadData();
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setAgentError(detail ? `Intake failed: ${detail}` : "Intake failed — check backend logs.");
      setAgentStatus("");
    } finally {
      setAgentRunning(false);
    }
  };

  // GAP-2: Playwright + vision analysis of a live portal URL
  const runUrlAnalysisAgent = async () => {
    if (!selectedProject || !portalUrl.trim()) return;
    setAgentRunning(true);
    setAgentStatus("URL agent running -- rendering and analysing portal page(s)...");
    setAgentError(null);
    try {
      const res = await requirementsApi.triggerUrlAnalysis(selectedProject, portalUrl.trim(), urlCrawlDepth);
      const data = res.data as { message?: string; agent_run_id?: number };
      if (data.agent_run_id) {
        setAgentStatus(data.message ?? "Portal URL analysis queued.");
        await pollAgentRun(data.agent_run_id, "Portal requirements generated successfully.", "Portal URL analysis failed.");
        setPortalUrl("");
      } else {
        setAgentStatus(`Done: ${data.message || "URL analysis completed successfully"}`);
        await loadData();
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setAgentError(detail ? `URL analysis failed: ${typeof detail === "string" ? detail : JSON.stringify(detail)}` : "URL analysis failed — check backend logs.");
      setAgentStatus("");
    } finally {
      setAgentRunning(false);
    }
  };

  // GAP-3: GitHub / local repo code analysis
  const runCodeAnalysisAgent = async (source: "github" | "local") => {
    if (!selectedProject) return;
    if (source === "github" && !githubUrl.trim()) return;
    if (source === "local" && !localRepoPath.trim()) return;
    setAgentRunning(true);
    setCodeAnalysisBusy(true);
    setCodeAnalysisSource(source);
    setAgentError(null);
    setAgentStatus(
      source === "github"
        ? "Code analysis agent running — cloning and parsing GitHub repository..."
        : "Code analysis agent running — reading local repository files..."
    );
    try {
      const res = await requirementsApi.triggerCodeAnalysis(selectedProject, {
        source,
        github_url: source === "github" ? githubUrl.trim() : undefined,
        github_branch: source === "github" ? (githubBranch.trim() || "main") : undefined,
        github_token: source === "github" && githubToken.trim() ? githubToken.trim() : undefined,
        local_path: source === "local" ? localRepoPath.trim() : undefined,
        languages: repoLanguages.split(",").map((l) => l.trim()).filter(Boolean),
      });
      const data = res.data as { message?: string; agent_run_id?: number };
      if (data.agent_run_id) {
        setAgentStatus(data.message ?? "Code analysis queued.");
        await pollAgentRun(
          data.agent_run_id,
          "Code requirements generated successfully.",
          "Code analysis failed.",
          { zeroCountError: "Code analysis completed but produced 0 requirements. Check Agent Logs for model errors or an overly narrow language/path selection." }
        );
      } else {
        setAgentStatus(`Done: ${data.message || "Code analysis completed successfully"}`);
        await loadData();
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setAgentError(detail ? `Code analysis failed: ${typeof detail === "string" ? detail : JSON.stringify(detail)}` : "Code analysis failed — check backend logs.");
      setAgentStatus("");
    } finally {
      setAgentRunning(false);
      setCodeAnalysisBusy(false);
      setCodeAnalysisSource(null);
    }
  };

  // GAP-1: vision analysis of an uploaded UI screenshot
  const runUiAnalysisAgent = async (docId: number) => {
    if (!selectedProject) return;
    setAgentRunning(true);
    setAgentStatus("Vision agent running -- analysing UI screenshot...");
    setAgentError(null);
    try {
      const res = await requirementsApi.triggerUiAnalysis(selectedProject, docId);
      const data = res.data as { message?: string; agent_run_id?: number };
      if (data.agent_run_id) {
        setAgentStatus(data.message ?? "UI screenshot analysis queued.");
        await pollAgentRun(data.agent_run_id, "UI requirements generated successfully.", "UI screenshot analysis failed.");
      } else {
        setAgentStatus(`Done: ${data.message || "UI analysis completed successfully"}`);
        await loadData();
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setAgentError(detail ? `UI analysis failed: ${detail}` : "UI analysis failed — check backend logs.");
      setAgentStatus("");
    } finally {
      setAgentRunning(false);
    }
  };

  const runQualityAgent = async (reqIds?: number[]) => {
    if (!selectedProject) return;
    setAgentRunning(true);
    setAgentStatus("Agent 2 running -- reviewing requirement quality...");
    setAgentError(null);
    try {
      const res = await requirementsApi.triggerQuality(selectedProject, reqIds);
      const data = res.data as { message?: string; agent_run_id?: number };
      if (data.agent_run_id) {
        setAgentStatus(data.message ?? "Quality review queued.");
        await pollAgentRun(data.agent_run_id, "Quality review completed successfully.", "Quality review failed.");
      } else {
        const summary = (data as any).summary as Record<string, number> | undefined;
        setAgentStatus(`Done. Pass: ${summary?.pass ?? 0}, Needs Revision: ${summary?.needs_revision ?? 0}, Fail: ${summary?.fail ?? 0}`);
        await loadData();
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setAgentError(detail ? `Quality review failed: ${detail}` : "Quality review failed — check backend logs.");
      setAgentStatus("");
    } finally {
      setAgentRunning(false);
    }
  };

  const handleApprove = async (action: "approve" | "reject") => {
    if (!selectedReq) return;
    setReviewLoading(true);
    try {
      await requirementsApi.approve(selectedReq.id, action, notes || undefined);
      await loadData();
      setSelectedReq(null);
      setNotes("");
    } finally {
      setReviewLoading(false);
    }
  };

  const handleSaveGenerationContext = async () => {
    if (!selectedReq) return;
    setSavingGenContext(true);
    setGenContextSaved(false);
    try {
      const res = await requirementsApi.update(selectedReq.id, {
        test_phase: genEnvDraft,
        generation_notes: genNotesDraft,
      });
      setSelectedReq(res.data);
      setRequirements((prev) => prev.map((r) => (r.id === res.data.id ? res.data : r)));
      setGenContextSaved(true);
    } finally {
      setSavingGenContext(false);
    }
  };

  const handleDeleteReq = async () => {
    if (!deletingReq) return;
    await requirementsApi.delete(deletingReq.id);
    setRequirements((prev) => prev.filter((r) => r.id !== deletingReq.id));
    setDeletingReq(null);
    if (selectedReq?.id === deletingReq.id) setSelectedReq(null);
  };

  const handleDeleteDoc = async () => {
    if (!deletingDoc) return;
    await documentsApi.delete(deletingDoc.id);
    setDocuments((prev) => prev.filter((d) => d.id !== deletingDoc.id));
    setDeletingDoc(null);
  };

  const handleCreateJiraConnection = async () => {
    if (!selectedProject) return;
    const trimmedForm = {
      jira_base_url: jiraConnectionForm.jira_base_url.trim(),
      jira_email: jiraConnectionForm.jira_email.trim(),
      jira_api_token: jiraConnectionForm.jira_api_token.trim(),
      jira_project_key: jiraConnectionForm.jira_project_key.trim().toUpperCase(),
    };
    if (!trimmedForm.jira_base_url || !trimmedForm.jira_email || !trimmedForm.jira_api_token || !trimmedForm.jira_project_key) {
      setJiraError("Complete all Jira connection fields before saving.");
      return;
    }
    setJiraBusy(true);
    setJiraError(null);
    setJiraMessage(null);
    try {
      const res = editingJiraConnectionId
        ? await jiraApi.updateConnection(editingJiraConnectionId, {
            jira_base_url: trimmedForm.jira_base_url,
            jira_email: trimmedForm.jira_email,
            jira_api_token: trimmedForm.jira_api_token,
            jira_project_key: trimmedForm.jira_project_key,
            is_active: true,
          })
        : await jiraApi.createConnection({
            project_id: selectedProject,
            ...trimmedForm,
            is_active: true,
          });
      setJiraConnections((prev) => editingJiraConnectionId
        ? prev.map((connection) => connection.id === res.data.id ? res.data : connection)
        : [res.data, ...prev]
      );
      setSelectedJiraConnection(res.data.id);
      setJiraConnectionForm(emptyJiraConnectionForm);
      setEditingJiraConnectionId(null);
      setShowJiraConnectionForm(false);
      setJiraMessage(editingJiraConnectionId ? "Jira credentials updated." : "Jira connection saved.");
    } catch (e: any) {
      setJiraError(e?.response?.data?.detail || "Failed to save connection.");
    } finally {
      setJiraBusy(false);
    }
  };

  const handleEditJiraConnection = () => {
    const connection = jiraConnections.find((item) => item.id === selectedJiraConnection);
    if (!connection) return;
    setEditingJiraConnectionId(connection.id);
    setJiraConnectionForm({
      jira_base_url: connection.jira_base_url,
      jira_email: connection.jira_email,
      jira_api_token: "",
      jira_project_key: connection.jira_project_key,
    });
    setShowJiraConnectionForm(true);
    setJiraError(null);
    setJiraMessage(null);
  };

  const handleTestJiraConnection = async () => {
    if (!selectedJiraConnection) return;
    setJiraBusy(true);
    setJiraError(null);
    setJiraMessage(null);
    try {
      const res = await jiraApi.testConnection(selectedJiraConnection);
      await loadJiraConnections({ preserveFeedback: true });
      if (res.data.success) {
        setJiraMessage(res.data.display_name ? `Connected as ${res.data.display_name}.` : res.data.message);
      } else {
        setJiraError(res.data.message);
      }
    } catch (e: any) {
      setJiraError("Jira connection test failed.");
    } finally {
      setJiraBusy(false);
    }
  };

  const handleDeleteJiraConnection = async () => {
    if (!selectedJiraConnection) return;
    setJiraBusy(true);
    setJiraError(null);
    setJiraMessage(null);
    try {
      await jiraApi.deleteConnection(selectedJiraConnection);
      setJiraIssuesPage(null);
      setJiraMessage("Jira connection deleted.");
      await loadJiraConnections();
    } catch (e: any) {
      setJiraError("Failed to delete connection.");
    } finally {
      setJiraBusy(false);
    }
  };

  const handleFetchJiraIssues = async (page = 1) => {
    if (!selectedJiraConnection) return;
    const pageSize = clampNumber(jiraFilters.page_size, 1, 100);
    setJiraBusy(true);
    setJiraError(null);
    setJiraMessage(null);
    try {
      const res = await jiraApi.fetchIssues(selectedJiraConnection, {
        issue_types: splitCsv(jiraFilters.issue_types),
        statuses: splitCsv(jiraFilters.statuses),
        priorities: splitCsv(jiraFilters.priorities),
        labels: splitCsv(jiraFilters.labels),
        assignee: jiraFilters.assignee.trim() || undefined,
        text: jiraFilters.text.trim() || undefined,
        updated_since: jiraFilters.updated_since.trim() || undefined,
        jql: jiraFilters.jql.trim() || undefined,
        page: clampNumber(page, 1, 100000),
        page_size: pageSize,
      });
      setJiraIssuesPage(res.data);
      setJiraMessage(`Fetched ${res.data.items.length} of ${res.data.total} Jira issues.`);
    } catch (e: any) {
      setJiraError("Failed to fetch Jira issues.");
    } finally {
      setJiraBusy(false);
    }
  };

  const handleImportJiraRequirements = async () => {
    if (!selectedJiraConnection) return;
    const pageSize = clampNumber(jiraFilters.page_size, 1, 100);
    const maxIssues = clampNumber(jiraFilters.max_issues, 1, 5000);
    setJiraBusy(true);
    setJiraError(null);
    setJiraMessage(null);
    try {
      const res = await jiraApi.importRequirements(selectedJiraConnection, {
        issue_types: splitCsv(jiraFilters.issue_types),
        statuses: splitCsv(jiraFilters.statuses),
        priorities: splitCsv(jiraFilters.priorities),
        labels: splitCsv(jiraFilters.labels),
        assignee: jiraFilters.assignee.trim() || undefined,
        text: jiraFilters.text.trim() || undefined,
        updated_since: jiraFilters.updated_since.trim() || undefined,
        jql: jiraFilters.jql.trim() || undefined,
        batch_size: pageSize,
        max_issues: maxIssues,
      });
      await loadData();
      setJiraMessage(`Imported ${res.data.imported} Jira requirements: ${res.data.created} created, ${res.data.updated} updated.`);
    } catch (e: any) {
      setJiraError("Failed to import Jira requirements.");
    } finally {
      setJiraBusy(false);
    }
  };

  function handleOpenReqDetail(req: Requirement) {
    setSelectedReq(req);
    setNotes("");
    setGenEnvDraft(req.test_phase || "SIT");
    setGenNotesDraft(req.generation_notes ?? "");
    setGenContextSaved(false);
    setDrawerTab("details");
    // GAP-4d: load coverage insights for the drawer (best-effort)
    setCoverage(null);
    setCoverageLoading(true);
    requirementsApi
      .coverage(req.id)
      .then((res) => setCoverage(res.data))
      .catch(() => setCoverage(null))
      .finally(() => setCoverageLoading(false));
    // GAP-5: reset traceability chain (loaded on tab switch)
    setTraceChain(null);
    setTraceError(null);
  }

  /** Load the traceability chain when the Traceability drawer tab is selected. */
  async function handleLoadTraceChain(req: Requirement) {
    if (traceChain && traceChain.requirement.id === req.id) return; // already loaded
    setTraceLoading(true);
    setTraceError(null);
    try {
      const res = await traceabilityApi.requirementChain(req.id);
      setTraceChain(res.data);
    } catch (e: any) {
      setTraceError(
        e?.response?.status === 404
          ? "Requirement not found in traceability index."
          : e?.response?.data?.detail || "Failed to load traceability chain."
      );
      setTraceChain(null);
    } finally {
      setTraceLoading(false);
    }
  }

  /** GAP-5: Export helpers. */
  async function handleExport(type: "test-cases-excel" | "test-cases-csv" | "test-cases-xray" | "matrix-excel") {
    if (!selectedProject) return;
    setExportBusy(true);
    setExportError(null);
    setShowExportMenu(false);
    try {
      if (type === "test-cases-excel") {
        await exportApi.downloadTestCases(selectedProject, "excel");
      } else if (type === "test-cases-csv") {
        await exportApi.downloadTestCases(selectedProject, "csv");
      } else if (type === "test-cases-xray") {
        await exportApi.downloadTestCases(selectedProject, "xray");
      } else if (type === "matrix-excel") {
        await exportApi.downloadTraceabilityMatrix(selectedProject, "excel");
      }
    } catch (e: any) {
      setExportError(e?.response?.data?.detail || "Export failed. Please try again.");
    } finally {
      setExportBusy(false);
    }
  }

  // Filtered requirements list
  const filteredRequirements = useMemo(() => {
    return requirements.filter((r) => filterStatus === "all" || r.status === filterStatus);
  }, [requirements, filterStatus]);

  // Metric status cards metadata
  const stats = useMemo(() => {
    const total = requirements.length;
    const approved = requirements.filter((r) => r.status === "approved").length;
    const pending = requirements.filter((r) => r.status === "pending_review").length;
    const draft = requirements.filter((r) => r.status === "draft").length;

    const approvedPct = total > 0 ? ((approved / total) * 100).toFixed(1) : "0.0";
    const pendingPct = total > 0 ? ((pending / total) * 100).toFixed(1) : "0.0";
    const draftPct = total > 0 ? ((draft / total) * 100).toFixed(1) : "0.0";

    return [
      {
        title: "Total Requirements",
        icon: FileText,
        iconBg: "bg-blue-50 border-blue-100",
        iconColor: "text-blue-500",
        value: total.toLocaleString(),
        sublabel: "Total",
        footer: "100% of all requirements spec",
      },
      {
        title: "Approved Spec",
        icon: ShieldCheck,
        iconBg: "bg-emerald-50 border-emerald-100",
        iconColor: "text-emerald-500",
        value: approved.toLocaleString(),
        sublabel: "Approved",
        footer: `${approvedPct}% approved status count`,
      },
      {
        title: "Pending Review",
        icon: Clock,
        iconBg: "bg-amber-50 border-amber-100",
        iconColor: "text-amber-500",
        value: pending.toLocaleString(),
        sublabel: "Pending",
        footer: `${pendingPct}% review items remaining`,
      },
      {
        title: "Draft Spec",
        icon: FileText,
        iconBg: "bg-purple-50 border-purple-100",
        iconColor: "text-purple-500",
        value: draft.toLocaleString(),
        sublabel: "Draft",
        footer: `${draftPct}% initial specs`,
      },
    ];
  }, [requirements]);

  const selectedJiraConnectionRecord = jiraConnections.find((c) => c.id === selectedJiraConnection);

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Global Controls ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-blue-50 border border-blue-100 p-2.5">
            <FileText className="h-6 w-6 text-[#1b59f8]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Requirements Library</h1>
            <p className="text-xs text-slate-500 mt-1">Upload QA documents to extract structured user stories, audit AI quality scores, or pull from Jira</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadData} className="h-8 w-8 p-0 border-slate-200">
            <RefreshCw className={cn("h-3.5 w-3.5 text-slate-500", loading && "animate-spin")} />
          </Button>

          {/* GAP-5: Export dropdown */}
          <div className="relative">
            <Button
              variant="outline"
              size="sm"
              disabled={!selectedProject || requirements.length === 0 || exportBusy}
              onClick={() => setShowExportMenu((v) => !v)}
              className="h-8 px-3 border-slate-200 text-slate-600 bg-white font-semibold text-xs"
            >
              {exportBusy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
              ) : (
                <Download className="h-3.5 w-3.5 mr-1" />
              )}
              Export
              <ChevronDown className="h-3 w-3 ml-1 text-slate-400" />
            </Button>
            {showExportMenu && (
              <div
                className="absolute right-0 top-full mt-1 z-50 w-52 rounded-xl border border-slate-200 bg-white shadow-lg py-1 animate-in fade-in zoom-in-95 duration-100"
                onMouseLeave={() => setShowExportMenu(false)}
              >
                {EXPORT_MENU_OPTIONS.map(([type, label, desc]) => (
                  <button
                    key={type}
                    onClick={() => handleExport(type)}
                    className="w-full text-left px-3 py-2.5 hover:bg-slate-50 transition-colors group"
                  >
                    <span className="block text-xs font-bold text-slate-800 group-hover:text-[#1b59f8]">{label}</span>
                    <span className="block text-[10px] text-slate-400 mt-0.5">{desc}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          {exportError && (
            <span className="text-[10px] text-red-600 font-semibold max-w-xs truncate">{exportError}</span>
          )}
        </div>
      </div>

      {loadError && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="flex-1 font-semibold">{loadError}</span>
          <button onClick={() => setLoadError(null)}><XCircle className="h-4 w-4 text-red-400 hover:text-red-700" /></button>
        </div>
      )}

      {selectedProject && (
        <>
          {/* ── Status Counts Cards ─────────────────────────────────────────────────── */}
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

          {/* ── Agent Status Banner ──────────────────────────────────────────────── */}
          {(agentRunning || agentStatus || agentError) && (
            <div className={cn(
              "flex items-center gap-3 rounded-xl border px-4 py-3 text-xs font-semibold",
              agentRunning
                ? "border-blue-200 bg-blue-50 text-blue-700 animate-pulse"
                : agentError
                ? "border-red-200 bg-red-50 text-red-700"
                : "border-emerald-200 bg-emerald-50 text-emerald-700"
            )}>
              {agentRunning ? (
                <Loader2 className="h-4 w-4 animate-spin text-[#1b59f8] shrink-0" />
              ) : agentError ? (
                <AlertTriangle className="h-4 w-4 text-red-500 shrink-0" />
              ) : (
                <CheckCircle className="h-4 w-4 text-emerald-600 shrink-0" />
              )}
              <span className="flex-1">{agentError ?? agentStatus}</span>
              {!agentRunning && (
                <button onClick={() => { setAgentStatus(""); setAgentError(null); }} className="text-slate-400 hover:text-slate-700">
                  <XCircle className="h-4.5 w-4.5" />
                </button>
              )}
            </div>
          )}

          {/* ── Sub Navigation Tabs ────────────────────────────────────────────────── */}
          <div className="flex flex-wrap gap-1 rounded-xl border border-slate-200 bg-white p-1 w-fit">
            {(["requirements", "documents", "url", "github", "jira"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  "rounded-lg px-4 py-1.5 text-xs font-bold capitalize transition-all",
                  tab === t
                    ? "bg-slate-900 text-slate-50 shadow-sm"
                    : "text-slate-500 hover:text-slate-900"
                )}
              >
                {t === "documents" ? "Documents / UI Input"
                  : t === "url" ? "URL Input"
                  : t === "github" ? "GitHub / Local Repository"
                  : t}
                {t === "requirements" && requirements.length > 0 && (
                  <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold text-slate-700">{requirements.length}</span>
                )}
                {t === "documents" && documents.length > 0 && (
                  <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold text-slate-700">{documents.length}</span>
                )}
                {t === "jira" && jiraConnections.length > 0 && (
                  <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold text-slate-700">{jiraConnections.length}</span>
                )}
              </button>
            ))}
          </div>

          {/* ── Requirements Tab ──────────────────────────────────────────────────── */}
          {tab === "requirements" && (
            <div className="space-y-4">
              {/* Filter Buttons & AI Action */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex flex-wrap gap-1.5 rounded-lg border border-slate-200 bg-white p-1">
                  {["all", "draft", "pending_review", "approved", "rejected"].map((s) => (
                    <button
                      key={s}
                      onClick={() => setFilterStatus(s)}
                      className={cn(
                        "rounded-md px-3 py-1 text-xs font-semibold capitalize transition-all",
                        filterStatus === s
                          ? "bg-slate-900 text-slate-50 shadow-sm"
                          : "text-slate-500 hover:text-slate-900"
                      )}
                    >
                      {s === "all" ? "All Status" : s.replace(/_/g, " ")}
                    </button>
                  ))}
                </div>

                <Button
                  variant="default"
                  size="sm"
                  disabled={agentRunning || requirements.length === 0}
                  onClick={() => runQualityAgent()}
                  className="h-8 text-xs font-semibold bg-violet-600 hover:bg-violet-700 text-white"
                >
                  <Bot className="h-3.5 w-3.5 mr-1" />
                  Evaluate Quality (Agent 2)
                </Button>
              </div>

              {/* Requirements Table */}
              <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
                <table className="min-w-full text-left border-collapse text-xs select-none">
                  <thead className="bg-slate-50/70 border-b border-slate-200 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    <tr>
                      <th className="px-4 py-2.5">Req ID</th>
                      <th className="px-4 py-2.5">Title</th>
                      <th className="px-4 py-2.5">Status</th>
                      <th className="px-4 py-2.5">Quality Verdict</th>
                      <th className="px-4 py-2.5">Created By</th>
                      <th className="px-4 py-2.5">Created At</th>
                      <th className="px-4 py-2.5">Modified By</th>
                      <th className="px-4 py-2.5">Modified At</th>
                      <th className="px-4 py-2.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-600 font-medium">
                    {loading ? (
                      <tr>
                        <td colSpan={9} className="px-4 py-16 text-center text-slate-400 font-semibold">
                          <Loader2 className="inline mr-2 h-4 w-4 animate-spin text-[#1b59f8]" />
                          Loading requirements library...
                        </td>
                      </tr>
                    ) : filteredRequirements.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="px-4 py-16 text-center text-slate-400 font-semibold">
                          No requirements found matching selection.
                        </td>
                      </tr>
                    ) : (
                      filteredRequirements.map((req) => {
                        // GAP-4a: prefer metadata summary, fall back to persisted quality columns
                        const qualityMeta = (req.metadata_ as Record<string, any> | undefined)?.quality_review;
                        const quality = qualityMeta ?? (req.quality_verdict
                          ? { overall_score: req.quality_score, verdict: req.quality_verdict }
                          : undefined);
                        const isSelected = selectedReq?.id === req.id;
                        return (
                          <tr
                            key={req.id}
                            onClick={() => handleOpenReqDetail(req)}
                            className={cn(
                              "hover:bg-slate-50/50 cursor-pointer transition-colors group",
                              isSelected && "bg-[#1b59f8]/5"
                            )}
                          >
                            <td className="px-4 py-2.5 font-mono text-[11px] font-bold text-[#1b59f8]">{req.requirement_id}</td>
                            <td className="px-4 py-2.5 font-bold text-slate-800 text-xs truncate max-w-sm">{req.title}</td>
                            <td className="px-4 py-2.5">
                              <Badge variant={getStatusVariant(req.status)} className="capitalize">
                                {req.status.replace(/_/g, " ")}
                              </Badge>
                            </td>
                            <td className="px-4 py-2.5">
                              {quality ? (
                                <QualityBadge score={quality.overall_score} verdict={quality.verdict} />
                              ) : (
                                <span className="text-slate-400 font-semibold">-</span>
                              )}
                            </td>
                            <td className="px-4 py-2.5 text-slate-700 font-semibold whitespace-nowrap">
                              {resolveUser(req.created_by)}
                            </td>
                            <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap">
                              {req.created_at
                                ? new Date(req.created_at).toLocaleString("en-US", {
                                    year: "numeric",
                                    month: "short",
                                    day: "numeric",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  })
                                : "-"}
                            </td>
                            <td className="px-4 py-2.5 text-slate-700 font-semibold whitespace-nowrap">
                              {resolveUser(req.updated_by)}
                            </td>
                            <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap">
                              {req.updated_at
                                ? new Date(req.updated_at).toLocaleString("en-US", {
                                    year: "numeric",
                                    month: "short",
                                    day: "numeric",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  })
                                : "-"}
                            </td>
                            <td className="px-4 py-2.5 text-right flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                              <button
                                onClick={() => setDeletingReq(req)}
                                className="rounded-md p-1.5 text-slate-400 opacity-0 group-hover:opacity-100 hover:bg-red-50 hover:text-red-600 transition-all shrink-0"
                                title="Delete requirement"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleOpenReqDetail(req)}
                                className="h-7 px-3 text-xs border-slate-200 bg-white"
                              >
                                Details
                                <ChevronRight className="h-3 w-3 text-slate-400" />
                              </Button>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── Documents Tab ─────────────────────────────────────────────────────── */}
          {tab === "documents" && (
            <div className="space-y-4">
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFileUpload(f); }}
                className={cn(
                  "relative rounded-2xl border-2 border-dashed p-10 text-center transition-all cursor-pointer bg-white",
                  dragOver ? "border-[#1b59f8] bg-[#1b59f8]/5 shadow-sm" : "border-slate-250 hover:border-slate-350"
                )}
              >
                <input id="file-upload" type="file" className="sr-only"
                  accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.png,.jpg,.jpeg,.webp"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileUpload(f); }} />
                <label htmlFor="file-upload" className="cursor-pointer">
                  {uploading ? (
                    <Loader2 className="mx-auto h-9 w-9 animate-spin text-[#1b59f8] mb-3 shrink-0" />
                  ) : (
                    <Upload className="mx-auto h-9 w-9 text-slate-400 mb-3" />
                  )}
                  <p className="font-bold text-xs text-slate-700">{uploading ? "Uploading and extracting text evidence..." : "Drop QA documentation or UI screenshots here, or click to browse files"}</p>
                  <p className="text-[10px] text-slate-400 font-semibold mt-1">PDF, DOCX, TXT, MD, CSV, XLSX · UI screenshots: PNG, JPG, WebP · up to 25 MB</p>
                </label>
              </div>

              {documents.length > 0 ? (
                <div className="rounded-xl border divide-y overflow-hidden bg-white shadow-sm border-slate-200">
                  {documents.map((doc) => (
                    <div key={doc.id} className="flex items-center gap-4 px-4 py-3 hover:bg-slate-50/50 group">
                      <FileText className="h-5 w-5 text-blue-500 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-bold text-slate-800 truncate">{doc.original_filename}</p>
                        <p className="text-[10px] text-slate-400 font-bold">
                          {doc.file_type.toUpperCase()} · {(doc.file_size_bytes / 1024).toFixed(0)} KB
                          {doc.page_count ? ` · ${doc.page_count} pages` : ""}
                        </p>
                      </div>
                      <Badge variant={getStatusVariant(doc.status)}>{doc.status}</Badge>
                      
                      {doc.status === "processed" && (
                        ["png", "jpg", "webp"].includes(doc.file_type) ? (
                          <Button onClick={() => runUiAnalysisAgent(doc.id)} disabled={agentRunning} size="sm" variant="default" className="h-8 text-[11px] font-bold">
                            <Bot className="h-3.5 w-3.5 mr-1" />Analyze UI
                          </Button>
                        ) : (
                          <Button onClick={() => runIntakeAgent(doc.id)} disabled={agentRunning} size="sm" variant="default" className="h-8 text-[11px] font-bold">
                            <Bot className="h-3.5 w-3.5 mr-1" />Extract Specs
                          </Button>
                        )
                      )}
                      {doc.status === "failed" && (
                        <span className="text-[10px] text-rose-500 font-bold">Extraction failed — check backend logs</span>
                      )}
                      {doc.status === "uploaded" && (
                        <span className="text-[10px] text-slate-400 font-bold animate-pulse">Processing document text...</span>
                      )}
                      
                      <button
                        onClick={() => setDeletingDoc(doc)}
                        className="rounded-md p-1.5 text-slate-405 opacity-0 group-hover:opacity-100 hover:bg-red-50 hover:text-red-650 transition-all shrink-0"
                        title="Delete document"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : !uploading ? (
                <p className="text-center text-xs text-slate-400 font-bold py-8 border border-dashed rounded-xl bg-white">No documents uploaded yet.</p>
              ) : null}
            </div>
          )}

          {/* ── URL Input Tab (GAP-2) ─────────────────────────────────────────────── */}
          {tab === "url" && (
            <div className="space-y-4">
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                <div className="flex items-center gap-2">
                  <Globe className="h-5 w-5 text-[#1b59f8]" />
                  <div>
                    <h4 className="text-xs font-bold text-slate-800">Analyze Portal URL</h4>
                    <p className="text-[10px] text-slate-400 font-semibold">Render a live page, detect forms, fields, validations and user journeys, and generate requirements automatically</p>
                  </div>
                </div>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    type="url"
                    value={portalUrl}
                    onChange={(e) => setPortalUrl(e.target.value)}
                    placeholder="https://portal.example.com/login"
                    className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-blue-300"
                  />
                  <select
                    value={urlCrawlDepth}
                    onChange={(e) => setUrlCrawlDepth(Number(e.target.value))}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-blue-300"
                  >
                    <option value={0}>Single page</option>
                    <option value={1}>+ linked pages (depth 1)</option>
                    <option value={2}>+ linked pages (depth 2)</option>
                  </select>
                  <Button
                    onClick={runUrlAnalysisAgent}
                    disabled={agentRunning || !portalUrl.trim()}
                    size="sm"
                    variant="default"
                    className="h-9 text-[11px] font-bold"
                  >
                    <Bot className="h-3.5 w-3.5 mr-1" />Analyze URL
                  </Button>
                </div>
                <p className="text-[10px] text-slate-400 font-semibold">Public/reachable pages only · same-origin crawling · max 5 pages · internal/private addresses are blocked</p>
              </div>

              {/* Requirements generated from URLs */}
              {(() => {
                const urlReqs = requirements.filter((r) => r.source === "portal_url");
                return urlReqs.length > 0 ? (
                  <div className="rounded-xl border divide-y overflow-hidden bg-white shadow-sm border-slate-200">
                    <div className="px-4 py-2.5 bg-slate-50/60">
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Requirements generated from URLs ({urlReqs.length})</p>
                    </div>
                    {urlReqs.map((req) => (
                      <div key={req.id} className="flex items-center gap-4 px-4 py-3 hover:bg-slate-50/50 cursor-pointer" onClick={() => handleOpenReqDetail(req)}>
                        <Globe className="h-4 w-4 text-[#1b59f8] shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-bold text-slate-800 truncate">{req.title}</p>
                          <p className="text-[10px] text-slate-400 font-bold truncate">
                            {req.requirement_id}
                            {(req.metadata_ as Record<string, any> | undefined)?.source_url ? ` · ${(req.metadata_ as Record<string, any>).source_url}` : ""}
                          </p>
                        </div>
                        <Badge variant={getStatusVariant(req.status)} className="capitalize">{req.status.replace(/_/g, " ")}</Badge>
                        <ChevronRight className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-center text-xs text-slate-400 font-bold py-8 border border-dashed rounded-xl bg-white">No URL-based requirements yet. Analyze a portal URL above to generate them.</p>
                );
              })()}
            </div>
          )}

          {/* ── GitHub / Local Repository Tab (GAP-3) ────────────────────────────── */}
          {tab === "github" && (
            <div className="space-y-5">

              {/* ── Section 1: GitHub Repository ─────────────────────────────────── */}
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                <div className="flex items-center gap-2">
                  <div className="rounded-lg bg-slate-900 p-2 shrink-0">
                    <GitBranch className="h-4 w-4 text-white" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-slate-800">GitHub Repository</h4>
                    <p className="text-[10px] text-slate-400 font-semibold mt-0.5">
                      Clone a public or private GitHub repo and parse Python / JS / TS source files to auto-generate requirements
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border-t pt-4">
                  <div className="md:col-span-2 flex flex-col gap-1">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Repository URL <span className="text-red-400">*</span></label>
                    <input
                      type="url"
                      value={githubUrl}
                      onChange={(e) => setGithubUrl(e.target.value)}
                      placeholder="https://github.com/org/repo"
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-blue-300"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Branch</label>
                    <input
                      value={githubBranch}
                      onChange={(e) => setGithubBranch(e.target.value)}
                      placeholder="main"
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-blue-300"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Personal Access Token <span className="text-slate-300 font-normal">(private repos)</span>
                    </label>
                    <input
                      type="password"
                      value={githubToken}
                      onChange={(e) => setGithubToken(e.target.value)}
                      placeholder="ghp_••••••••••••••••"
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-blue-300"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Languages to scan</label>
                    <input
                      value={repoLanguages}
                      onChange={(e) => setRepoLanguages(e.target.value)}
                      placeholder="python, javascript, typescript"
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-blue-300"
                    />
                    <p className="text-[10px] text-slate-400">Comma-separated — python, javascript, typescript, java, go</p>
                  </div>
                </div>

                <Button
                  onClick={() => runCodeAnalysisAgent("github")}
                  disabled={agentRunning || !githubUrl.trim() || !selectedProject}
                  size="sm"
                  variant="default"
                  className="h-9 text-[11px] font-bold"
                >
                  {codeAnalysisBusy && codeAnalysisSource === "github"
                    ? <><Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />Analysing…</>
                    : <><GitBranch className="h-3.5 w-3.5 mr-1.5" />Analyse GitHub Repo</>
                  }
                </Button>
                <p className="text-[10px] text-slate-400 font-semibold">
                  Public repos cloned directly · Private repos require a PAT with repo read scope · Repo size limit 500 MB
                </p>
              </div>

              {/* ── Section 2: Local Repository ───────────────────────────────────── */}
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                <div className="flex items-center gap-2">
                  <div className="rounded-lg bg-violet-600 p-2 shrink-0">
                    <BarChart2 className="h-4 w-4 text-white" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-slate-800">Local Project Repository</h4>
                    <p className="text-[10px] text-slate-400 font-semibold mt-0.5">
                      Point to a local directory on the server and extract requirements from Python / JS / TS source files
                    </p>
                  </div>
                </div>

                <div className="border-t pt-4 space-y-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Local Repository Path <span className="text-red-400">*</span></label>
                    <input
                      value={localRepoPath}
                      onChange={(e) => setLocalRepoPath(e.target.value)}
                      placeholder="/home/user/projects/my-service  or  C:\Projects\my-service"
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-mono font-semibold focus:outline-none focus:ring-2 focus:ring-blue-300"
                    />
                    <p className="text-[10px] text-slate-400">Absolute path accessible to the backend server · Symlinks supported</p>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Languages to scan</label>
                    <input
                      value={repoLanguages}
                      onChange={(e) => setRepoLanguages(e.target.value)}
                      placeholder="python, javascript, typescript"
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-blue-300"
                    />
                  </div>
                </div>

                <Button
                  onClick={() => runCodeAnalysisAgent("local")}
                  disabled={agentRunning || !localRepoPath.trim() || !selectedProject}
                  size="sm"
                  variant="default"
                  className="h-9 text-[11px] font-bold bg-violet-600 hover:bg-violet-700"
                >
                  {codeAnalysisBusy && codeAnalysisSource === "local"
                    ? <><Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />Analysing…</>
                    : <><BarChart2 className="h-3.5 w-3.5 mr-1.5" />Analyse Local Repo</>
                  }
                </Button>
                <p className="text-[10px] text-slate-400 font-semibold">
                  Reads only — no files are modified · Hidden directories (.git, node_modules, __pycache__) are skipped
                </p>
              </div>

              {/* Requirements generated from code analysis */}
              {(() => {
                const codeReqs = requirements.filter((r) => r.source === "github_repo" || r.source === "local_repo");
                return codeReqs.length > 0 ? (
                  <div className="rounded-xl border divide-y overflow-hidden bg-white shadow-sm border-slate-200">
                    <div className="px-4 py-2.5 bg-slate-50/60 flex items-center justify-between">
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Requirements generated from code ({codeReqs.length})
                      </p>
                    </div>
                    {codeReqs.map((req) => {
                      const meta = req.metadata_ as Record<string, any> | undefined;
                      return (
                        <div key={req.id} className="flex items-center gap-4 px-4 py-3 hover:bg-slate-50/50 cursor-pointer" onClick={() => handleOpenReqDetail(req)}>
                          <GitBranch className="h-4 w-4 text-slate-500 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-bold text-slate-800 truncate">{req.title}</p>
                            <p className="text-[10px] text-slate-400 font-bold truncate">
                              {req.requirement_id}
                              {meta?.repo_url ? ` · ${meta.repo_url}` : ""}
                              {meta?.file_path ? ` · ${meta.file_path}` : ""}
                            </p>
                          </div>
                          <Badge variant={getStatusVariant(req.status)} className="capitalize">{req.status.replace(/_/g, " ")}</Badge>
                          <ChevronRight className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-center text-xs text-slate-400 font-bold py-8 border border-dashed rounded-xl bg-white">
                    No code-based requirements yet. Connect a GitHub repo or local path above to generate them.
                  </p>
                );
              })()}
            </div>
          )}

          {/* ── Jira Tab ──────────────────────────────────────────────────────────── */}
          {tab === "jira" && (
            <div className="space-y-4">
              {(jiraMessage || jiraError) && (
                <div className={cn(
                  "flex items-start gap-3 rounded-xl border px-4 py-3 text-xs font-semibold",
                  jiraError
                    ? "border-red-200 bg-red-50 text-red-700"
                    : "border-emerald-200 bg-emerald-50 text-emerald-700"
                )}>
                  {jiraError ? <AlertTriangle className="h-4.5 w-4.5 shrink-0 mt-0.5 text-red-500" /> : <CheckCircle className="h-4.5 w-4.5 shrink-0 mt-0.5 text-emerald-500" />}
                  <span className="flex-1 leading-relaxed">{jiraError || jiraMessage}</span>
                  <button onClick={() => { setJiraError(null); setJiraMessage(null); }} className="opacity-60 hover:opacity-100">
                    <XCircle className="h-4 w-4 text-slate-400" />
                  </button>
                </div>
              )}

              {/* Connection configuration card */}
              <Card className="border-slate-200 bg-white">
                <CardContent className="p-5 space-y-4">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2">
                      <Plug className="h-5 w-5 text-[#1b59f8]" />
                      <div>
                        <h3 className="text-xs font-bold text-slate-800">Jira Sync Configuration</h3>
                        <p className="text-[10px] text-slate-400 mt-0.5">Link local project space to Atlassian Jira Agile project boards</p>
                      </div>
                    </div>
                    <Button
                      onClick={() => {
                        setEditingJiraConnectionId(null);
                        setJiraConnectionForm(emptyJiraConnectionForm);
                        setShowJiraConnectionForm(!showJiraConnectionForm);
                      }}
                      variant="outline"
                      size="sm"
                      className="h-8 text-xs border-slate-200 font-semibold text-slate-650"
                      disabled={jiraBusy}
                    >
                      <Plus className="h-3.5 w-3.5 mr-1" />
                      Configure Connection
                    </Button>
                  </div>

                  {showJiraConnectionForm && (
                    <form onSubmit={(e) => { e.preventDefault(); handleCreateJiraConnection(); }} className="border-t pt-4 space-y-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Jira Host URL</label>
                          <input value={jiraConnectionForm.jira_base_url} onChange={(e) => setJiraConnectionForm((f) => ({ ...f, jira_base_url: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" placeholder="https://your-domain.atlassian.net" />
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Jira Login Email</label>
                          <input value={jiraConnectionForm.jira_email} onChange={(e) => setJiraConnectionForm((f) => ({ ...f, jira_email: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" placeholder="amit.sharma@company.com" />
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Jira API Token</label>
                          <input type="password" value={jiraConnectionForm.jira_api_token} onChange={(e) => setJiraConnectionForm((f) => ({ ...f, jira_api_token: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" placeholder={editingJiraConnectionId ? "••••••••••••" : "Atlassian API key"} />
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Jira Project Key</label>
                          <input value={jiraConnectionForm.jira_project_key} onChange={(e) => setJiraConnectionForm((f) => ({ ...f, jira_project_key: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50 font-mono uppercase" placeholder="e.g. STLC" />
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button type="submit" disabled={jiraBusy} size="sm" variant="default" className="text-xs font-semibold h-8.5">
                          {jiraBusy && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />}
                          Save Jira Details
                        </Button>
                        <Button type="button" onClick={() => { setShowJiraConnectionForm(false); setEditingJiraConnectionId(null); }} size="sm" variant="outline" className="text-xs font-semibold h-8.5 border-slate-200 text-slate-600 bg-white">
                          Cancel
                        </Button>
                      </div>
                    </form>
                  )}

                  {!showJiraConnectionForm && jiraConnections.length > 0 && (
                    <div className="border-t pt-4 flex items-center justify-between gap-4 flex-wrap bg-slate-50/50 p-3 rounded-lg border border-slate-150">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-bold text-slate-800">{selectedJiraConnectionRecord?.jira_project_key} Project Link</span>
                          <Badge variant={getStatusVariant(selectedJiraConnectionRecord?.is_active ? "connected" : "disconnected")}>
                            {selectedJiraConnectionRecord?.is_active ? "Connected" : "Inactive"}
                          </Badge>
                        </div>
                        <p className="text-[10px] text-slate-400 mt-1 font-semibold truncate">{selectedJiraConnectionRecord?.jira_base_url} ({selectedJiraConnectionRecord?.jira_email})</p>
                      </div>

                      <div className="flex gap-2 shrink-0">
                        <Button onClick={handleTestJiraConnection} disabled={jiraBusy} size="sm" variant="outline" className="h-8 text-xs border-slate-200 text-slate-650 bg-white font-bold">
                          Test Link
                        </Button>
                        <Button onClick={handleEditJiraConnection} disabled={jiraBusy} size="sm" variant="outline" className="h-8 text-xs border-slate-200 text-slate-650 bg-white font-bold">
                          Edit
                        </Button>
                        <Button onClick={handleDeleteJiraConnection} disabled={jiraBusy} size="sm" variant="outline" className="h-8 text-xs border-red-200 hover:bg-rose-50 text-red-600 bg-white font-bold">
                          Delete
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Jira Fetch & Import Hub */}
              {selectedJiraConnection && (
                <Card className="border-slate-200 bg-white">
                  <CardContent className="p-5 space-y-4">
                    <div className="flex items-center gap-2">
                      <Search className="h-5 w-5 text-indigo-500" />
                      <div>
                        <h3 className="text-xs font-bold text-slate-800">Fetch Jira Stories</h3>
                        <p className="text-[10px] text-slate-400 mt-0.5">Filter issue backlogs from Jira and import them as local specs</p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-t pt-4">
                      <div className="flex flex-col gap-1">
                        <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Issue Types CSV</label>
                        <div className="flex gap-1.5 items-center">
                          <input value={jiraFilters.issue_types} onChange={(e) => setJiraFilters((f) => ({ ...f, issue_types: e.target.value }))} className="flex-1 rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" placeholder="Story, Epic" />
                          <Button type="button" size="sm" variant="outline" onClick={() => setJiraFilters((f) => ({ ...f, issue_types: jiraStoryTypePreset }))} className="h-8 text-[9px] border-slate-200 text-slate-550 shrink-0 font-bold bg-white">Preset</Button>
                        </div>
                      </div>
                      <div className="flex flex-col gap-1">
                        <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Jira Statuses CSV</label>
                        <input value={jiraFilters.statuses} onChange={(e) => setJiraFilters((f) => ({ ...f, statuses: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" placeholder="e.g. In Progress, Done" />
                      </div>
                      <div className="flex flex-col gap-1">
                        <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Jira JQL Query Override</label>
                        <input value={jiraFilters.jql} onChange={(e) => setJiraFilters((f) => ({ ...f, jql: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" placeholder="project = STLC AND type = Story" />
                      </div>
                    </div>

                    <div className="flex gap-2">
                      <Button onClick={() => handleFetchJiraIssues()} disabled={jiraBusy} size="sm" variant="default" className="text-xs font-semibold h-8.5">
                        {jiraBusy && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1 text-white" />}
                        Fetch Backlog
                      </Button>
                      <Button onClick={handleImportJiraRequirements} disabled={jiraBusy} size="sm" variant="outline" className="text-xs font-semibold h-8.5 border-slate-200 text-slate-655 bg-white font-bold">
                        Import as Requirements
                      </Button>
                    </div>

                    {/* Jira issues list summary */}
                    {jiraIssuesPage && jiraIssuesPage.items.length > 0 && (
                      <div className="border-t pt-4 space-y-3">
                        <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">Jira Backlog Matches ({jiraIssuesPage.total})</label>
                        <div className="rounded-lg border border-slate-150 divide-y divide-slate-100 overflow-hidden bg-slate-50/20 max-h-60 overflow-y-auto pr-1">
                          {jiraIssuesPage.items.map((issue) => (
                            <div key={issue.key} className="p-3 text-xs flex items-center justify-between gap-4 bg-white">
                              <div className="min-w-0">
                                <div className="flex items-center gap-1.5">
                                  <span className="font-mono font-bold text-[#1b59f8]">{issue.key}</span>
                                  <Badge variant="outline" className="py-0 px-2 text-[9px] capitalize">{issue.issue_type}</Badge>
                                  <Badge variant={getStatusVariant(issue.status)} className="py-0 px-2 text-[9px] capitalize">{issue.status}</Badge>
                                </div>
                                <p className="font-bold text-slate-800 mt-1 truncate">{issue.summary}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </>
      )}

      {/* ── Requirements details Drawer ────────────────────────────────────────── */}
      <Drawer open={!!selectedReq} onOpenChange={(open) => !open && setSelectedReq(null)}>
        <DrawerContent size="xl">
          {selectedReq && (
            <>
              <DrawerHeader>
                <div className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-[#1b59f8]" />
                  <div className="min-w-0">
                    <DrawerTitle className="truncate">Requirement: {selectedReq.requirement_id}</DrawerTitle>
                    <DrawerDescription className="truncate">{selectedReq.title}</DrawerDescription>
                  </div>
                </div>
                <button onClick={() => setSelectedReq(null)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-50"><X className="h-4 w-4" /></button>
              </DrawerHeader>

              <DrawerBody className="space-y-5">
                {/* GAP-5: Drawer tab navigation */}
                <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 w-fit">
                  {(["details", "traceability"] as const).map((t) => (
                    <button
                      key={t}
                      onClick={() => {
                        setDrawerTab(t);
                        if (t === "traceability" && selectedReq) {
                          handleLoadTraceChain(selectedReq);
                        }
                      }}
                      className={cn(
                        "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-bold capitalize transition-all",
                        drawerTab === t
                          ? "bg-white text-slate-900 shadow-sm"
                          : "text-slate-500 hover:text-slate-800"
                      )}
                    >
                      {t === "details" ? <FileText className="h-3 w-3" /> : <GitBranch className="h-3 w-3" />}
                      {t === "details" ? "Details" : "Traceability"}
                    </button>
                  ))}
                </div>

                {/* ── TRACEABILITY TAB ───────────────────────────────────────── */}
                {drawerTab === "traceability" && (
                  <div className="space-y-4">
                    {traceLoading && (
                      <div className="flex items-center gap-2 text-xs font-semibold text-slate-400 py-8 justify-center">
                        <Loader2 className="h-4 w-4 animate-spin text-[#1b59f8]" />
                        Loading traceability chain…
                      </div>
                    )}

                    {traceError && (
                      <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-xs text-red-700 font-semibold flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4 shrink-0" />
                        {traceError}
                      </div>
                    )}

                    {traceChain && !traceLoading && (
                      <>
                        {/* Summary badges */}
                        <div className="grid grid-cols-4 gap-2">
                          {([
                            ["Scenarios", traceChain.summary.scenario_count, "text-indigo-600", "bg-indigo-50 border-indigo-100"],
                            ["Test Cases", traceChain.summary.test_case_count, "text-blue-600", "bg-blue-50 border-blue-100"],
                            ["Executions", traceChain.summary.execution_count, "text-emerald-600", "bg-emerald-50 border-emerald-100"],
                            ["Defects", traceChain.summary.defect_count, "text-red-600", "bg-red-50 border-red-100"],
                          ] as const).map(([label, count, textCls, bgCls]) => (
                            <div key={label} className={cn("rounded-lg border p-2.5 text-center", bgCls)}>
                              <div className={cn("text-xl font-bold", textCls)}>{count}</div>
                              <div className="text-[9px] font-bold text-slate-400 uppercase mt-0.5">{label}</div>
                            </div>
                          ))}
                        </div>

                        {/* Gaps alert */}
                        {traceChain.summary.gaps.length > 0 && (
                          <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs font-semibold text-amber-800 flex items-start gap-2">
                            <AlertTriangle className="h-3.5 w-3.5 text-amber-500 mt-0.5 shrink-0" />
                            <span>Gaps: {traceChain.summary.gaps.map((g) => g.replace(/_/g, " ")).join(" · ")}</span>
                          </div>
                        )}

                        {/* Scenarios */}
                        {traceChain.scenarios.length > 0 && (
                          <div className="space-y-1.5">
                            <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Test Scenarios ({traceChain.scenarios.length})</label>
                            <div className="rounded-lg border border-slate-200 divide-y divide-slate-100 overflow-hidden bg-white">
                              {traceChain.scenarios.map((s) => (
                                <div key={s.id} className="flex items-center gap-3 px-3 py-2">
                                  <div className="w-1.5 h-1.5 rounded-full bg-indigo-400 shrink-0" />
                                  <div className="flex-1 min-w-0">
                                    <span className="font-mono text-[10px] text-indigo-600 font-bold">{s.scenario_id}</span>
                                    <span className="text-xs text-slate-700 font-semibold ml-2 truncate">{s.title}</span>
                                  </div>
                                  <Badge variant="outline" className="text-[9px] capitalize shrink-0">{s.scenario_type}</Badge>
                                  <Badge variant={getStatusVariant(s.status)} className="text-[9px] shrink-0">{s.status}</Badge>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Test Cases */}
                        {traceChain.test_cases.length > 0 && (
                          <div className="space-y-1.5">
                            <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Test Cases ({traceChain.test_cases.length})</label>
                            <div className="rounded-lg border border-slate-200 divide-y divide-slate-100 overflow-hidden bg-white">
                              {traceChain.test_cases.map((tc) => (
                                <div key={tc.id} className="flex items-center gap-3 px-3 py-2">
                                  <div className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
                                  <div className="flex-1 min-w-0">
                                    <span className="font-mono text-[10px] text-[#1b59f8] font-bold">{tc.test_case_id}</span>
                                    <span className="text-xs text-slate-700 font-semibold ml-2 truncate">{tc.title}</span>
                                  </div>
                                  {tc.jira_issue_key && (
                                    <Badge variant="info" className="text-[9px] shrink-0">{tc.jira_issue_key}</Badge>
                                  )}
                                  {tc.automation_candidate && (
                                    <Badge variant="purple" className="text-[9px] shrink-0">Auto</Badge>
                                  )}
                                  <Badge variant={getStatusVariant(tc.status)} className="text-[9px] shrink-0">{tc.status}</Badge>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Execution Results */}
                        {traceChain.execution_results.length > 0 && (
                          <div className="space-y-1.5">
                            <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Execution Results ({traceChain.execution_results.length})</label>
                            <div className="rounded-lg border border-slate-200 divide-y divide-slate-100 overflow-hidden bg-white max-h-44 overflow-y-auto">
                              {traceChain.execution_results.map((er) => (
                                <div key={er.id} className="flex items-center gap-3 px-3 py-2">
                                  <div className={cn(
                                    "w-1.5 h-1.5 rounded-full shrink-0",
                                    er.status === "passed" ? "bg-emerald-400" : er.status === "failed" ? "bg-red-400" : "bg-slate-300"
                                  )} />
                                  <div className="flex-1 min-w-0">
                                    <span className="text-xs text-slate-700 font-semibold truncate">{er.test_name}</span>
                                  </div>
                                  <Badge variant={er.status === "passed" ? "success" : er.status === "failed" ? "destructive" : "outline"} className="text-[9px] shrink-0 capitalize">{er.status}</Badge>
                                  {er.created_at && (
                                    <span className="text-[9px] text-slate-400 shrink-0">{new Date(er.created_at).toLocaleDateString()}</span>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Defects */}
                        {traceChain.defects.length > 0 && (
                          <div className="space-y-1.5">
                            <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Defects ({traceChain.defects.length})</label>
                            <div className="rounded-lg border border-red-100 divide-y divide-red-50 overflow-hidden bg-red-50/30">
                              {traceChain.defects.map((d) => (
                                <div key={d.id} className="flex items-center gap-3 px-3 py-2">
                                  <div className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                                  <div className="flex-1 min-w-0">
                                    <span className="font-mono text-[10px] text-red-600 font-bold">{d.defect_id}</span>
                                    <span className="text-xs text-slate-700 font-semibold ml-2 truncate">{d.summary}</span>
                                  </div>
                                  <Badge variant="destructive" className="text-[9px] shrink-0 capitalize">{d.severity}</Badge>
                                  <Badge variant={getStatusVariant(d.status)} className="text-[9px] shrink-0">{d.status}</Badge>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Nothing linked at all */}
                        {traceChain.scenarios.length === 0 && traceChain.test_cases.length === 0 && (
                          <p className="text-center text-xs text-slate-400 font-semibold py-8 border border-dashed rounded-xl bg-white">
                            No traceability artifacts linked to this requirement yet.
                          </p>
                        )}
                      </>
                    )}
                  </div>
                )}

                {/* ── DETAILS TAB (existing content) ──────────────────────── */}
                {drawerTab === "details" && (
                  <div className="space-y-5">

                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Status:</span>
                  <Badge variant={getStatusVariant(selectedReq.status)} className="capitalize">{selectedReq.status.replace(/_/g, " ")}</Badge>
                </div>

                {selectedReq.summary && (
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Description</label>
                    <p className="text-xs text-slate-700 leading-relaxed font-semibold bg-slate-50 border rounded-lg p-3">{selectedReq.summary}</p>
                  </div>
                )}

                {/* Test Environment + Generation Notes — drives AI scenario/test-case
                    generation style (see scenario_agent.py / test_case_agent.py). Styled to
                    stand out so testers notice it before generating test cases. */}
                <div className="relative overflow-hidden rounded-xl border-2 border-[#1b59f8]/25 bg-gradient-to-br from-blue-50 via-indigo-50/50 to-white p-4 pt-5 space-y-3 shadow-sm ring-1 ring-[#1b59f8]/10">
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[#1b59f8] via-indigo-500 to-violet-500" />
                  <div className="flex items-center gap-2">
                    <div className="flex items-center justify-center h-7 w-7 rounded-lg bg-[#1b59f8]/10 border border-[#1b59f8]/20 shrink-0">
                      <Bot className="h-4 w-4 text-[#1b59f8]" />
                    </div>
                    <h4 className="text-xs font-bold text-slate-800">AI Test Case Generation Context</h4>
                    <Badge variant="info" className="ml-auto text-[9px] font-bold tracking-wide shrink-0">AI-POWERED</Badge>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Test Environment</label>
                    <select
                      value={genEnvDraft}
                      onChange={(e) => { setGenEnvDraft(e.target.value); setGenContextSaved(false); }}
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-[#1b59f8]"
                    >
                      {["SIT", "QA", "UAT", "Regression", "Production Smoke Test"].map((env) => (
                        <option key={env} value={env}>{env}</option>
                      ))}
                    </select>
                    <p className="text-[10px] text-slate-400 font-medium">Tailors the depth/style of AI-generated scenarios &amp; test cases for this requirement.</p>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Generation Notes</label>
                    <textarea
                      value={genNotesDraft}
                      onChange={(e) => { setGenNotesDraft(e.target.value); setGenContextSaved(false); }}
                      placeholder="Optional instructions or emphasis for the AI to consider when generating test cases for this requirement (e.g. focus areas, known edge cases, data constraints)…"
                      rows={3}
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-[#1b59f8] resize-none"
                    />
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      onClick={handleSaveGenerationContext}
                      disabled={savingGenContext}
                      className="h-7 text-[11px] font-semibold"
                    >
                      {savingGenContext ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
                      Save
                    </Button>
                    {genContextSaved && (
                      <span className="text-[10px] text-emerald-600 font-semibold flex items-center gap-1">
                        <CheckCircle className="h-3 w-3" /> Saved
                      </span>
                    )}
                  </div>
                </div>

                {/* AI quality review nested sub-panel */}
                {(() => {
                  // GAP-4a: prefer metadata summary, fall back to persisted quality columns
                  const qualityMeta = (selectedReq.metadata_ as Record<string, any> | undefined)?.quality_review;
                  const quality = qualityMeta ?? (selectedReq.quality_verdict
                    ? {
                        overall_score: selectedReq.quality_score,
                        verdict: selectedReq.quality_verdict,
                        issues: selectedReq.quality_feedback ? [selectedReq.quality_feedback] : undefined,
                      }
                    : undefined);
                  if (!quality) return null;
                  return (
                    <div className="border border-violet-100 rounded-xl bg-violet-50/20 p-4 space-y-4">
                      <div className="flex items-center justify-between border-b pb-2.5 border-violet-100/50">
                        <div className="flex items-center gap-2">
                          <Star className="h-4.5 w-4.5 text-violet-500 fill-violet-400" />
                          <h4 className="text-xs font-bold text-slate-800">AI Requirement Quality Score</h4>
                        </div>
                        <QualityBadge score={quality.overall_score} verdict={quality.verdict} />
                      </div>

                      <div className="grid grid-cols-3 gap-3 mb-2 text-center text-xs font-semibold">
                        <div className="bg-white border rounded-lg p-2">
                          <div className="text-lg font-bold text-slate-850">{(quality.completeness_score) ?? "?"}</div>
                          <div className="text-[9px] text-slate-400 font-bold uppercase">Completeness</div>
                        </div>
                        <div className="bg-white border rounded-lg p-2">
                          <div className="text-lg font-bold text-slate-850">{(quality.clarity_score) ?? "?"}</div>
                          <div className="text-[9px] text-slate-400 font-bold uppercase">Clarity</div>
                        </div>
                        <div className="bg-white border rounded-lg p-2">
                          <div className="text-lg font-bold text-slate-850">{(quality.testability_score) ?? "?"}</div>
                          <div className="text-[9px] text-slate-400 font-bold uppercase">Testability</div>
                        </div>
                      </div>

                      {quality.issues?.length > 0 && (
                        <div className="space-y-1">
                          <label className="text-[9px] font-extrabold uppercase tracking-wider text-rose-500 block">Quality Issues Detected</label>
                          <ul className="text-xs space-y-1 font-semibold text-slate-650 bg-white rounded-lg p-3 border">
                            {quality.issues.map((issue: string, i: number) => (
                              <li key={i} className="flex items-start gap-1.5"><span className="text-rose-500 font-bold select-none">•</span>{issue}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {quality.suggestions?.length > 0 && (
                        <div className="space-y-1">
                          <label className="text-[9px] font-extrabold uppercase tracking-wider text-indigo-500 block">AI Suggestions</label>
                          <ul className="text-xs space-y-1 font-semibold text-slate-650 bg-white rounded-lg p-3 border">
                            {quality.suggestions.map((s: string, i: number) => (
                              <li key={i} className="flex items-start gap-1.5"><span className="text-indigo-400 font-bold select-none">→</span>{s}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  );
                })()}

                {/* GAP-1: UI screenshot analysis sub-panel */}
                {(() => {
                  const ui = (selectedReq.metadata_ as Record<string, any> | undefined)?.ui_analysis;
                  if (!ui) return null;
                  return (
                    <div className="border border-emerald-100 rounded-xl bg-emerald-50/20 p-4 space-y-4">
                      <div className="flex items-center justify-between border-b pb-2.5 border-emerald-100/50">
                        <div className="flex items-center gap-2">
                          <Bot className="h-4.5 w-4.5 text-emerald-500" />
                          <h4 className="text-xs font-bold text-slate-800">UI Screenshot Analysis{ui.screen_name ? `: ${ui.screen_name}` : ""}</h4>
                        </div>
                        <Badge variant="success">Vision AI</Badge>
                      </div>

                      {ui.screen_purpose && (
                        <p className="text-xs text-slate-700 leading-relaxed font-semibold bg-white border rounded-lg p-3">{ui.screen_purpose}</p>
                      )}

                      <div className="grid grid-cols-3 gap-3 text-center text-xs font-semibold">
                        <div className="bg-white border rounded-lg p-2">
                          <div className="text-lg font-bold text-slate-850">{(ui.fields ?? []).length}</div>
                          <div className="text-[9px] text-slate-400 font-bold uppercase">Fields</div>
                        </div>
                        <div className="bg-white border rounded-lg p-2">
                          <div className="text-lg font-bold text-slate-850">{(ui.buttons ?? []).length}</div>
                          <div className="text-[9px] text-slate-400 font-bold uppercase">Buttons</div>
                        </div>
                        <div className="bg-white border rounded-lg p-2">
                          <div className="text-lg font-bold text-slate-850">{(ui.user_flows ?? []).length}</div>
                          <div className="text-[9px] text-slate-400 font-bold uppercase">User Flows</div>
                        </div>
                      </div>

                      {(ui.fields ?? []).length > 0 && (
                        <div className="flex flex-wrap items-center gap-1.5">
                          {(ui.fields as Array<{ name?: string; type?: string; required?: boolean | null }>).slice(0, 12).map((f, i) => (
                            <Badge key={i} variant={f.required ? "warning" : "outline"} className="font-semibold">
                              {f.name ?? "field"}{f.type ? ` · ${f.type}` : ""}{f.required ? " *" : ""}
                            </Badge>
                          ))}
                          {(ui.fields ?? []).length > 12 && (
                            <span className="text-[10px] text-slate-400 font-bold">+{(ui.fields ?? []).length - 12} more</span>
                          )}
                        </div>
                      )}

                      {([
                        ["Detected Validation Rules", ui.validation_rules],
                        ["Negative Scenarios To Test", ui.negative_scenarios],
                        ["Edge Cases", ui.edge_cases],
                      ] as Array<[string, Array<string | Record<string, unknown>> | undefined]>).map(([label, items]) =>
                        items && items.length > 0 ? (
                          <div key={label} className="space-y-1">
                            <label className="text-[9px] font-extrabold uppercase tracking-wider text-emerald-600 block">{label}</label>
                            <ul className="text-xs space-y-1 font-semibold text-slate-650 bg-white rounded-lg p-3 border">
                              {items.slice(0, 8).map((item, i) => (
                                <li key={i} className="flex items-start gap-1.5"><span className="text-emerald-500 font-bold select-none">•</span>{renderInsightItem(item)}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null
                      )}
                    </div>
                  );
                })()}

                {/* GAP-4d: Coverage insights sub-panel */}
                {coverageLoading ? (
                  <div className="border rounded-xl bg-slate-50/30 p-4 flex items-center gap-2 text-xs font-semibold text-slate-400">
                    <Loader2 className="h-4 w-4 animate-spin text-[#1b59f8]" />
                    Loading coverage insights...
                  </div>
                ) : coverage ? (
                  <div className="border border-sky-100 rounded-xl bg-sky-50/20 p-4 space-y-4">
                    <div className="flex items-center justify-between border-b pb-2.5 border-sky-100/50">
                      <div className="flex items-center gap-2">
                        <ShieldCheck className="h-4.5 w-4.5 text-sky-500" />
                        <h4 className="text-xs font-bold text-slate-800">Test Coverage Insights</h4>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={coverage.priority_band === "P1" ? "destructive" : coverage.priority_band === "P2" ? "warning" : "info"}>
                          Priority {coverage.priority_band}
                        </Badge>
                        <Badge variant={coverage.coverage_score >= 75 ? "success" : coverage.coverage_score >= 50 ? "warning" : "destructive"}>
                          {coverage.coverage_score}% coverage
                        </Badge>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-3 text-center text-xs font-semibold">
                      <div className="bg-white border rounded-lg p-2">
                        <div className="text-lg font-bold text-slate-850">{coverage.scenario_count}</div>
                        <div className="text-[9px] text-slate-400 font-bold uppercase">Scenarios</div>
                      </div>
                      <div className="bg-white border rounded-lg p-2">
                        <div className="text-lg font-bold text-slate-850">{coverage.test_case_count}</div>
                        <div className="text-[9px] text-slate-400 font-bold uppercase">Test Cases</div>
                      </div>
                      <div className="bg-white border rounded-lg p-2">
                        <div className="text-lg font-bold text-slate-850">{coverage.automation_candidates}</div>
                        <div className="text-[9px] text-slate-400 font-bold uppercase">Automatable</div>
                      </div>
                    </div>

                    {(coverage.covered_categories.length > 0 || coverage.missing_categories.length > 0) && (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {coverage.covered_categories.map((c) => (
                          <Badge key={c} variant="success" className="capitalize">{c} ✓</Badge>
                        ))}
                        {coverage.missing_categories.map((c) => (
                          <Badge key={c} variant="outline" className="capitalize text-slate-400">{c} missing</Badge>
                        ))}
                      </div>
                    )}

                    {coverage.gaps.length > 0 && (
                      <div className="space-y-1">
                        <label className="text-[9px] font-extrabold uppercase tracking-wider text-amber-600 block">Coverage Gaps Detected</label>
                        <ul className="text-xs space-y-1 font-semibold text-slate-650 bg-white rounded-lg p-3 border">
                          {coverage.gaps.map((gap, i) => (
                            <li key={i} className="flex items-start gap-1.5"><span className="text-amber-500 font-bold select-none">!</span>{gap}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ) : null}

                {/* Acceptance criteria and other arrays */}
                {([
                  ["Acceptance Criteria", selectedReq.acceptance_criteria],
                  ["Business Rules", selectedReq.business_rules],
                  ["User Roles Involved", selectedReq.user_roles],
                  ["Systems Impacted", selectedReq.systems_impacted],
                  ["Risks", selectedReq.risks],
                  ["Missing Specs / Info", selectedReq.missing_information]
                ] as const).map(([label, array]) => array && array.length > 0 ? (
                  <div key={label} className="space-y-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</label>
                    <ul className="text-xs space-y-1.5 font-semibold text-slate-700 bg-slate-50/50 border rounded-lg p-3.5">
                      {array.map((item, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="text-blue-500 font-bold select-none mt-0.5">•</span>
                          <span className="leading-relaxed">{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null)}

                {/* Review Gate */}
                {!["approved", "rejected"].includes(selectedReq.status) && (
                  <div className="border-2 border-dashed rounded-xl p-4 bg-slate-50/20 space-y-3">
                    <h4 className="text-xs font-bold text-slate-800">Review Gate Approval Decision</h4>
                    <textarea
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      rows={3}
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold resize-none focus:outline-none focus:ring-2 focus:ring-blue-300"
                      placeholder="Add reviewer notes/feedback..."
                    />
                    <div className="flex gap-2">
                      <Button
                        onClick={() => handleApprove("approve")}
                        disabled={reviewLoading}
                        variant="default"
                        className="flex-1 text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white h-9"
                      >
                        <CheckCircle className="h-4 w-4 mr-1 text-white" />
                        Approve
                      </Button>
                      <Button
                        onClick={() => handleApprove("reject")}
                        disabled={reviewLoading}
                        variant="outline"
                        className="flex-1 text-xs font-semibold border-rose-200 text-rose-600 hover:bg-rose-50 bg-white h-9"
                      >
                        <XCircle className="h-4 w-4 mr-1 text-rose-600" />
                        Reject
                      </Button>
                    </div>
                  </div>
                )}
                  
                  <div className="border-t border-slate-100 pt-4 space-y-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      Audit Trail
                    </label>
                    <AuditStamp
                      createdAt={selectedReq.created_at}
                      updatedAt={selectedReq.updated_at}
                      createdByName={resolveUser(selectedReq.created_by ?? undefined)}
                      updatedByName={resolveUser(selectedReq.updated_by ?? undefined)}
                    />
                  </div>

                    </div>
                  )} {/* end drawerTab === "details" */}
              </DrawerBody>

              <DrawerFooter>
                <Button variant="outline" size="sm" onClick={() => setSelectedReq(null)} className="w-full h-9 bg-white border-slate-200">Close detail</Button>
              </DrawerFooter>
            </>
          )}
        </DrawerContent>
      </Drawer>

      {/* Delete Confirmation Modals */}
      {deletingReq && (
        <ConfirmDeleteModal
          title="Delete Requirement"
          description={`Are you sure you want to delete requirement ${deletingReq.requirement_id}? This action cannot be undone.`}
          onConfirm={handleDeleteReq}
          onCancel={() => setDeletingReq(null)}
        />
      )}
      {deletingDoc && (
        <ConfirmDeleteModal
          title="Delete Document"
          description={`Are you sure you want to delete document ${deletingDoc.original_filename}? All extracted requirements will remain intact.`}
          onConfirm={handleDeleteDoc}
          onCancel={() => setDeletingDoc(null)}
        />
      )}
    </div>
  );
}

export default function RequirementsPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-slate-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-[#1b59f8] mr-2" />
        Loading Requirements...
      </div>
    }>
      <RequirementsContent />
    </Suspense>
  );
}
