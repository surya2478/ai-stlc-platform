"use client";

import { useState, useEffect, useCallback, useMemo, useRef, Suspense } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  FileText, Upload, Bot, CheckCircle, XCircle, RefreshCw, AlertTriangle, Star, Trash2, X, Plug, Search, Download, Plus, Settings, ChevronRight, Loader2, ShieldCheck, Clock, Globe, GitBranch, BarChart2, ChevronDown, ClipboardPaste, Braces, Layers3, CircleDot, Link2, Filter, Sparkles, ArrowRight
} from "lucide-react";
import {
  requirementsApi,
  documentsApi,
  projectsApi,
  jiraApi,
  agentRunsApi,
  traceabilityApi,
  exportApi,
  taxonomyApi,
  type TaxonomyEntry,
  type Requirement,
  applicationsApi,
  type ProjectApplication,
  type RequirementDuplicateReport,
  type RequirementQualityReview,
  type RequirementCoverage,
  type RequirementTraceabilityChain,
  type TraceabilityMatrixRow,
  type Document,
  type Project,
  type JiraConnection,
  type JiraIssue,
  type JiraIssueFilters,
  type JiraIssuePage,
  type ApprovalAction,
  type BlockerResolution,
  type MissingInfoItem,
  type RequirementBlocker,
  type RequirementBlockerSummary,
} from "@/lib/api";
import { AuditStamp } from "@/components/ui/AuditStamp";
import { useUserDirectory } from "@/hooks/useUserDirectory";
import { cn } from "@/lib/utils";
import { applicationsHref } from "@/components/applications/ApplicationsTabs";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerBody, DrawerFooter
} from "@/components/ui/drawer";
import { useAIAction } from "@/hooks/useAIAction";
import { AI_PROCESSING_STAGES } from "@/lib/ai-processing-stages";
import { terminalAIStatus } from "@/lib/ai-processing-status";

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
            <h2 className="font-bold text-sm text-gray-800">{title}</h2>
            <p className="text-xs text-gray-500 mt-1.5 leading-relaxed font-semibold">{description}</p>
          </div>
          <button onClick={onCancel} className="rounded-md p-1 hover:bg-gray-50 text-gray-400 shrink-0">
            <X className="h-4 w-4" />
          </button>
        </div>
        {error && (
          <div className="rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-700 font-semibold">
            {error}
          </div>
        )}
        <div className="flex gap-2 pt-1">
          <Button onClick={onCancel} disabled={deleting} variant="outline" size="sm" className="flex-1 h-9 border-gray-200 text-gray-650 bg-white">
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

function metadataRecord(req: Requirement): Record<string, any> {
  return (req.metadata_ || {}) as Record<string, any>;
}

function splitLines(value: string) {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

/** How an advisory gap is written in the plain-text editor.
 *
 *  The textarea carries text only, so severity used to survive an edit purely by
 *  matching a line back to its original entry — change one character of an
 *  advisory line and it silently became blocking, gating the requirement on
 *  something cosmetic. That is the exact failure the severity model was added to
 *  prevent. Showing the marker makes severity visible and, deliberately,
 *  editable: a reviewer can downgrade a gap by typing it. */
const ADVISORY_SUFFIX = /\s*\(advisory\)\s*$/i;

function formatMissingInfoLine(entry: MissingInfoItem): string {
  return entry.severity === "advisory" ? `${entry.item} (advisory)` : entry.item;
}

function parseMissingInfoLine(
  line: string,
  known: Map<string, MissingInfoItem["severity"]>,
): MissingInfoItem {
  const markedAdvisory = ADVISORY_SUFFIX.test(line);
  const item = line.replace(ADVISORY_SUFFIX, "").trim();
  return {
    item,
    // An unmarked line keeps whatever severity it already had; a line the
    // reviewer added by hand is untriaged and blocks until an agent judges it.
    severity: markedAdvisory ? "advisory" : known.get(item) ?? "blocking",
  };
}

function getRequirementWorkflowStage(req: Requirement): "intake" | "analysis" | "traceability" | "review" {
  if (["approved", "rejected"].includes((req.status || "").toLowerCase())) return "review";
  const persisted = String(metadataRecord(req).workflow_stage || "").toLowerCase();
  if (["intake", "analysis", "traceability", "review"].includes(persisted)) {
    return persisted as "intake" | "analysis" | "traceability" | "review";
  }
  const readiness = String(req.readiness_status || "draft").toLowerCase();
  if (["pending_review", "ready_for_review", "review_pending"].includes(readiness)) return "review";
  if (["traceability_pending", "ready_for_traceability"].includes(readiness)) return "traceability";
  if (["analysis_pending", "analysis_complete", "ai_review_pending", "ai_review_completed", "needs_clarification"].includes(readiness)) return "analysis";
  const legacyAnalysisComplete = (req.quality_verdict || "").toLowerCase() === "pass"
    && blockingMissingInfo(req.missing_information).length === 0
    && Boolean(req.telecom_domain || req.qa_domain || req.business_process)
    && Boolean(req.product || req.product_group || req.sub_request_type);
  if (readiness === "ready_for_test_planning" && legacyAnalysisComplete) return "traceability";
  return "intake";
}

function getRequirementWorkflowStageLabel(req: Requirement): string {
  const stage = getRequirementWorkflowStage(req);
  if (stage === "intake") return "Requirement Intake";
  if (stage === "analysis") return "Requirement Analysis";
  if (stage === "traceability") return "Traceability";
  return "Review & Approval";
}

function requirementIntakeTransitionBlockers(req: Requirement): string[] {
  const blockers: string[] = [];
  if (!req.requirement_id?.trim()) blockers.push("A governed requirement ID is required.");
  if (!req.title?.trim()) blockers.push("Add a requirement title.");
  if (!req.source?.trim()) blockers.push("Source provenance is required.");
  return blockers;
}

function getRequirementWorkflowStageVariant(req: Requirement): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  const stage = getRequirementWorkflowStage(req);
  if (stage === "intake") return "info";
  if (stage === "analysis") return "purple";
  if (stage === "traceability") return "warning";
  return "success";
}

function asTextList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => renderInsightItem(item)).filter(Boolean);
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

/**
 * Missing information, normalized across both shapes.
 *
 * Historical rows are plain strings; the agent now emits
 * `{item, severity}`. A bare string is treated as blocking — defaulting legacy
 * data to advisory would retroactively unblock requirements that no agent has
 * re-judged. This mirrors `requirement_blockers.py` on the server.
 */
/** The dimensions behind the single quality number, with the weights the backend
 *  actually uses (`QUALITY_SCORE_WEIGHTS` in quality_agent.py). Shown so a score
 *  that moves after an edit can be traced to the dimension that moved, and so it
 *  is obvious which fix is worth the most.
 *
 *  `gating` marks a dimension with its own pass threshold: scenario readiness
 *  must reach 3/5 regardless of the overall score, so a requirement can sit
 *  above 70/100 and still read "Needs Revision". */
const QUALITY_DIMENSIONS: Array<{ key: string; label: string; weight: number; gating?: boolean }> = [
  { key: "testability_score", label: "Testability", weight: 0.2 },
  { key: "acceptance_criteria_score", label: "Acceptance criteria", weight: 0.2 },
  { key: "completeness_score", label: "Completeness", weight: 0.15 },
  { key: "clarity_score", label: "Clarity", weight: 0.1 },
  { key: "ambiguity_score", label: "Ambiguity", weight: 0.1 },
  { key: "interface_readiness_score", label: "Interface readiness", weight: 0.1 },
  { key: "scenario_generation_readiness", label: "Scenario readiness", weight: 0.1, gating: true },
  { key: "qa_domain_completeness", label: "Domain completeness", weight: 0.05 },
];

/* Test Type / Phase and Risk Level have no taxonomy master table — the backend
 * governs them as fixed lists. Keep these in step with TEST_PHASES / RISK_LEVELS
 * in backend/app/schemas/requirement.py. */
const TEST_PHASE_OPTIONS = ["SIT", "QA", "UAT", "Regression", "Production Smoke Test"];
const RISK_LEVEL_OPTIONS = ["Critical", "High", "Medium", "Low"];

/* A requirement stores its classification as text, not a taxonomy FK, so the
 * select submits the entry's name. Any value the requirement already carries
 * that is no longer in the master table stays selectable and labelled — opening
 * this dialog must never silently drop what an agent or an import recorded. */
function ClassificationSelect({ label, value, options, onChange }: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  const offTaxonomy = Boolean(value) && !options.includes(value);
  return (
    <label className="space-y-1.5">
      <span className="text-[10px] font-bold uppercase text-gray-500">{label}</span>
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 w-full rounded-lg border border-gray-200 bg-white px-3 font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-app-brand-200"
      >
        <option value="">—</option>
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
        {offTaxonomy && <option value={value}>{value} (not in taxonomy)</option>}
      </select>
    </label>
  );
}

/** Grouping order for the blockers panel: what a person can act on first. */
const BLOCKER_ROUTE_ORDER: BlockerResolution[] = ["human_input", "clarification", "rerun_analysis"];

const BLOCKER_ROUTE_HEADING: Record<BlockerResolution, string> = {
  human_input: "Needs your input — Re-run Analysis will not clear these",
  clarification: "Needs an answer from the requirement owner",
  rerun_analysis: "Will clear on the next Analysis run",
};

function missingInfoItems(value: unknown): MissingInfoItem[] {
  if (typeof value === "string" && value.trim()) {
    return [{ item: value.trim(), severity: "blocking" }];
  }
  if (!Array.isArray(value)) return [];
  return value
    .map((entry): MissingInfoItem | null => {
      if (entry === null || entry === undefined) return null;
      if (typeof entry === "object") {
        const obj = entry as Record<string, unknown>;
        const text = String(obj.item ?? obj.text ?? "").trim();
        const severity = String(obj.severity ?? "blocking").toLowerCase();
        return text
          ? { item: text, severity: severity === "advisory" ? "advisory" : "blocking" }
          : null;
      }
      const text = String(entry).trim();
      return text ? { item: text, severity: "blocking" } : null;
    })
    .filter((entry): entry is MissingInfoItem => entry !== null);
}

/** Only these gate. Advisory gaps are shown elsewhere, never as blockers. */
function blockingMissingInfo(value: unknown): string[] {
  return missingInfoItems(value)
    .filter((entry) => entry.severity === "blocking")
    .map((entry) => entry.item);
}

/** The rest — listed so the reader sees them, counted so a "1" above a list of
 *  two stops looking like a bug. */
function advisoryMissingInfo(value: unknown): string[] {
  return missingInfoItems(value)
    .filter((entry) => entry.severity === "advisory")
    .map((entry) => entry.item);
}

function getRequirementQualityScore(req: Requirement): number | null {
  const meta = metadataRecord(req);
  const review = meta.quality_review as Record<string, any> | undefined;
  const raw = review?.overall_score ?? review?.score ?? req.quality_score;
  const value = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(value)) return null;
  return value <= 5 ? Math.round(value * 20) : clampNumber(value, 0, 100);
}

function getEditableAnalysisValidationIssues(
  req: Requirement,
  isDuplicate: boolean,
  duplicateReason?: string,
): string[] {
  const meta = metadataRecord(req);
  const qualityReview = (meta.quality_review || {}) as Record<string, any>;
  const conflictCount = asTextList(qualityReview.conflicts).length
    || asTextList(meta.conflicts).length;
  const taxonomyReady = Boolean(req.telecom_domain || req.qa_domain || req.business_process)
    && Boolean(req.product || req.product_group || req.sub_request_type);

  return [
    ...blockingMissingInfo(req.missing_information).map((item) => `Missing information: ${item}`),
    // Naming the counterpart and the signal turns "resolve this" into something
    // a reviewer can actually act on without opening every other requirement.
    ...(isDuplicate
      ? [`Potential duplicate requires reviewer decision. ${duplicateReason ?? ""}`.trim()]
      : []),
    ...(conflictCount > 0 ? ["Potential source conflict requires clarification."] : []),
    ...(!taxonomyReady ? ["Taxonomy classification is incomplete."] : []),
  ];
}

function getAnalysisStatus(req: Requirement, isDuplicate: boolean): AnalysisStatus {
  const status = (req.status || "").toLowerCase();
  const readiness = (req.readiness_status || "").toLowerCase();
  const quality = (req.quality_verdict || "").toLowerCase();
  const missingCount = blockingMissingInfo(req.missing_information).length;
  const qualityReview = metadataRecord(req).quality_review as Record<string, any> | undefined;

  if (status === "approved") return "analyzed";
  if (qualityReview?.stale === true || readiness.includes("stale")) return "stale_source";
  if (status === "rejected" || readiness.includes("blocked")) return "blocked";
  if (readiness === "analysis_pending") return "queued";
  if (quality === "fail") return "failed";
  // An outstanding clarification request or unresolved missing information is a
  // human-input gate. A "needs_revision" verdict with no missing information is
  // a quality-revision signal, not a clarification loop — keep them distinct so
  // a re-analysed requirement is not mislabelled "Needs Clarification".
  if (readiness === "needs_clarification" || missingCount > 0 || isDuplicate) return "needs_clarification";
  if (quality === "needs_revision") return "needs_revision";
  if (quality === "pass") return "analyzed";
  return "not_analyzed";
}

function analysisLabel(status: AnalysisStatus) {
  return status.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function analysisBadgeVariant(status: AnalysisStatus): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  if (status === "analyzed") return "success";
  if (status === "needs_clarification" || status === "needs_revision" || status === "stale_source") return "warning";
  if (status === "blocked" || status === "failed") return "destructive";
  if (status === "analyzing" || status === "queued") return "purple";
  return "outline";
}

function riskBadgeVariant(risk: string | null | undefined): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  const normalized = (risk || "").toLowerCase();
  if (["critical", "high"].includes(normalized)) return "destructive";
  if (["medium"].includes(normalized)) return "warning";
  if (["low"].includes(normalized)) return "success";
  return "outline";
}

function traceHealthLabel(health: TraceabilityHealth) {
  const labels: Record<TraceabilityHealth, string> = {
    fully_traced: "Fully Traced",
    partial_trace: "Partial Trace",
    missing_links: "Missing Links",
    broken_stale: "Broken / Stale",
    not_traced: "Not Traced",
  };
  return labels[health];
}

function traceHealthBadgeVariant(health: TraceabilityHealth): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  if (health === "fully_traced") return "success";
  if (health === "partial_trace") return "warning";
  if (health === "missing_links") return "destructive";
  if (health === "broken_stale") return "destructive";
  return "outline";
}

function reviewStatusLabel(status: ReviewStatus) {
  const labels: Record<ReviewStatus, string> = {
    ready: "Ready",
    pending: "Pending",
    changes_requested: "Changes Requested",
    approved: "Approved",
    rejected: "Rejected",
    blocked: "Blocked",
  };
  return labels[status];
}

function reviewStatusBadgeVariant(status: ReviewStatus): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  if (status === "approved" || status === "ready") return "success";
  if (status === "pending") return "info";
  if (status === "changes_requested") return "warning";
  if (status === "rejected" || status === "blocked") return "destructive";
  return "outline";
}

function CoverageBar({ linked, total, health }: { linked: number; total: number; health?: TraceabilityHealth }) {
  const pct = total > 0 ? Math.min(100, Math.round((linked / total) * 100)) : 0;
  const color = health === "fully_traced" || pct === 100 ? "bg-emerald-500" : pct > 0 ? "bg-amber-500" : "bg-gray-300";
  return (
    <div className="min-w-[74px]">
      <div className="mb-1 text-[10px] font-bold text-gray-700">{linked} / {total}</div>
      <div className="h-1.5 overflow-hidden rounded-full bg-gray-100">
        <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
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
    // Missing-information entries carry a severity now. Handled first so every
    // display site renders the text rather than a stringified object; older rows
    // are still plain strings and are caught above.
    if ("item" in obj && "severity" in obj) {
      const text = String(obj.item ?? "").trim();
      return obj.severity === "advisory" ? `${text} (advisory)` : text;
    }
    // A captured navigation link. The URL analysis agent now keeps the
    // destination alongside the label — it used to keep only one or the other,
    // so the URL was lost. Rendered as "Label → /path" rather than falling
    // through to JSON.stringify.
    if ("href" in obj || ("label" in obj && "url" in obj)) {
      const label = String(obj.label ?? "").trim();
      const target = String(obj.url ?? obj.href ?? "").trim();
      if (label && target) return `${label} → ${target}`;
      return label || target;
    }
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

type IntakeTab = "requirements" | "documents" | "url" | "github" | "jira" | "paste";
type RequirementsWorkspaceView = "intake" | "analysis" | "traceability" | "review";
type RequirementTransitionAction = "send_to_analysis" | "send_to_traceability" | "send_to_review" | "send_back_to_analysis" | "send_back_to_traceability" | "request_clarification" | "resolve_clarification";
type AnalysisDialog = "content" | "acceptance" | "issues" | "classification" | "systems" | "clarification";
type AnalysisStatus = "not_analyzed" | "queued" | "analyzing" | "needs_clarification" | "needs_revision" | "blocked" | "analyzed" | "stale_source" | "failed";

type IntakeSourceRow = {
  id: string;
  documentId?: number;
  name: string;
  sourceType: string;
  owner: string;
  status: "ready" | "processing" | "blocked" | "completed";
  progress: number;
  extractedCount: number;
  validationIssues: string[];
  provenance: string;
  createdAt?: string;
  nextAction: "Run AI Intake" | "Retry" | "Send to Analysis" | "Processing" | "View Downstream";
  requirementIds: number[];
};

type AnalysisRow = {
  requirement: Requirement;
  ppmId: string;
  sourceLabel: string;
  owner: string;
  status: AnalysisStatus;
  progress: number;
  qualityScore: number | null;
  ambiguityCount: number;
  missingInfoCount: number;
  duplicateCount: number;
  conflictCount: number;
  taxonomyReady: boolean;
  riskLevel: string;
  blockers: string[];
};

type TraceabilityHealth = "fully_traced" | "partial_trace" | "missing_links" | "broken_stale" | "not_traced";
type ReviewStatus = "ready" | "pending" | "changes_requested" | "approved" | "rejected" | "blocked";

type RequirementTraceabilityRow = {
  requirement: Requirement;
  ppmId: string;
  sourceLabel: string;
  analysisStatus: AnalysisStatus;
  scenarioLinked: number;
  scenarioTotal: number;
  testCaseLinked: number;
  testCaseTotal: number;
  automationLinked: number;
  automationTotal: number;
  evidenceLinked: number;
  evidenceTotal: number;
  defectCount: number;
  health: TraceabilityHealth;
  updatedAt: string;
  gaps: string[];
};

type RequirementReviewRow = {
  requirement: Requirement;
  ppmId: string;
  owner: string;
  analysisStatus: AnalysisStatus;
  traceabilityHealth: TraceabilityHealth;
  traceabilityScore: number;
  reviewStatus: ReviewStatus;
  reviewerId: number | null;
  reviewer: string;
  dueAt: string | null;
  slaStatus: "on_track" | "at_risk" | "overdue" | "complete" | "unassigned";
  slaAge: string;
  readyForApproval: boolean;
  blockers: string[];
};

function formatRelativeTime(value?: string | null): string {
  if (!value) return "Unknown";
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "Unknown";
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(value).toLocaleDateString();
}

function reviewActionLabel(actionType: string): string {
  const action = actionType.replace(/_requirement$/, "");
  const labels: Record<string, string> = {
    approve: "approved",
    reject: "rejected",
    request_changes: "requested changes",
    send_to_analysis: "sent to analysis",
    send_to_traceability: "sent to traceability",
    send_to_review: "sent to review",
    send_back_to_analysis: "sent back to analysis",
    send_back_to_traceability: "sent back to traceability",
    request_clarification: "requested clarification",
    resolve_clarification: "resolved clarification",
  };
  return labels[action] || action.replace(/_/g, " ");
}

function getReviewSla(
  dueAtValue: unknown,
  terminal: boolean,
): { dueAt: string | null; status: RequirementReviewRow["slaStatus"]; label: string } {
  if (terminal) return { dueAt: null, status: "complete", label: "Completed" };
  if (!dueAtValue) return { dueAt: null, status: "unassigned", label: "Not assigned" };
  const dueAt = String(dueAtValue);
  const dueTimestamp = new Date(dueAt).getTime();
  if (!Number.isFinite(dueTimestamp)) return { dueAt: null, status: "unassigned", label: "Not assigned" };
  const remainingMs = dueTimestamp - Date.now();
  const absoluteHours = Math.max(1, Math.ceil(Math.abs(remainingMs) / 3_600_000));
  if (remainingMs < 0) {
    return {
      dueAt,
      status: "overdue",
      label: absoluteHours >= 24 ? `${Math.ceil(absoluteHours / 24)}d overdue` : `${absoluteHours}h overdue`,
    };
  }
  const label = absoluteHours >= 24 ? `${Math.ceil(absoluteHours / 24)}d left` : `${absoluteHours}h left`;
  return { dueAt, status: absoluteHours <= 24 ? "at_risk" : "on_track", label };
}

// Hoisted outside component to avoid SWC `as const` ambiguity inside JSX
const EXPORT_MENU_OPTIONS: Array<["test-cases-excel" | "test-cases-csv" | "test-cases-xray" | "matrix-excel", string, string]> = [
  ["test-cases-excel", "Test Cases (.xlsx)", "Excel workbook — all test cases with full metadata"],
  ["test-cases-csv",   "Test Cases (.csv)",  "Plain CSV — compatible with any tool"],
  ["test-cases-xray",  "Xray CSV (.csv)",    "Xray Jira import format — one row per step"],
  ["matrix-excel",     "Traceability Matrix (.xlsx)", "Req → Test → Execution matrix + Summary sheet"],
];

function RequirementsContent() {
  const { runAIAction, updateAIProcessing } = useAIAction();
  const { resolveUser, currentUser } = useUserDirectory();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProject = Number(searchParams.get("project")) || null;

  const [projects, setProjects] = useState<Project[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [duplicateReport, setDuplicateReport] = useState<RequirementDuplicateReport | null>(null);
  // null = registry not loaded (say nothing); [] = loaded and genuinely empty.
  const [registeredApplications, setRegisteredApplications] = useState<ProjectApplication[] | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentStatus, setAgentStatus] = useState<string>("");
  const [agentError, setAgentError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [workspaceView, setWorkspaceView] = useState<RequirementsWorkspaceView>("intake");
  const [analysisFilter, setAnalysisFilter] = useState<AnalysisStatus | "all">("all");
  const [analysisSearch, setAnalysisSearch] = useState("");
  const [analysisOverviewDetail, setAnalysisOverviewDetail] = useState<"quality" | "issues" | "domains" | null>(null);
  const [selectedQualityReviews, setSelectedQualityReviews] = useState<RequirementQualityReview[]>([]);
  const [qualityReviewsLoading, setQualityReviewsLoading] = useState(false);
  const [traceabilityFilter, setTraceabilityFilter] = useState<TraceabilityHealth | "all">("all");
  const [traceabilitySearch, setTraceabilitySearch] = useState("");
  const [traceabilityMatrix, setTraceabilityMatrix] = useState<TraceabilityMatrixRow[]>([]);
  const [matrixLoading, setMatrixLoading] = useState(false);
  const [approvalActions, setApprovalActions] = useState<ApprovalAction[]>([]);
  const [reviewFilter, setReviewFilter] = useState<ReviewStatus | "all">("all");
  const [reviewSearch, setReviewSearch] = useState("");
  const [reviewDomainFilter, setReviewDomainFilter] = useState("all");
  const [reviewOwnerFilter, setReviewOwnerFilter] = useState("all");
  const [reviewerFilter, setReviewerFilter] = useState("all");
  const [showReadinessRules, setShowReadinessRules] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [tab, setTab] = useState<IntakeTab>("documents");
  const [selectedSource, setSelectedSource] = useState<IntakeSourceRow | null>(null);
  const [pasteTitle, setPasteTitle] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [manualIntakeBusy, setManualIntakeBusy] = useState(false);
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
  // Which fetched issues the user actually wants. Empty means "no explicit
  // pick" and import falls back to the filter query, which is what the button
  // has always done.
  const [selectedJiraKeys, setSelectedJiraKeys] = useState<Set<string>>(new Set());
  const [jiraBusy, setJiraBusy] = useState(false);
  const [jiraMessage, setJiraMessage] = useState<string | null>(null);
  const [jiraError, setJiraError] = useState<string | null>(null);

  // Drawer states
  const [selectedReq, setSelectedReq] = useState<Requirement | null>(null);
  // The gate, as the server judges it. Previously this screen recomputed the
  // rules itself, so the panel and the backend could disagree about what was
  // blocking and neither said which blockers a re-run could not clear.
  const [blockerSummary, setBlockerSummary] = useState<RequirementBlockerSummary | null>(null);
  const [taxonomyWaiverBusy, setTaxonomyWaiverBusy] = useState(false);
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
  const [transitioning, setTransitioning] = useState(false);
  const [analysisDialog, setAnalysisDialog] = useState<AnalysisDialog | null>(null);
  const [analysisDialogSaving, setAnalysisDialogSaving] = useState(false);
  const [analysisDialogError, setAnalysisDialogError] = useState<string | null>(null);
  const analysisDialogSubmittingRef = useRef(false);
  const analysisActionsRef = useRef<HTMLDivElement | null>(null);
  const [criteriaDraft, setCriteriaDraft] = useState("");
  const [missingInfoDraft, setMissingInfoDraft] = useState("");
  const [resolutionDraft, setResolutionDraft] = useState("");
  const [markMissingResolved, setMarkMissingResolved] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState("");
  const [businessRulesDraft, setBusinessRulesDraft] = useState("");
  const [risksDraft, setRisksDraft] = useState("");
  const [systemsDraft, setSystemsDraft] = useState("");
  const [interfacesDraft, setInterfacesDraft] = useState("");
  const [apisDraft, setApisDraft] = useState("");
  const [classificationDraft, setClassificationDraft] = useState({ domain: "", journey: "", application: "", subRequestType: "", testType: "", riskLevel: "" });
  // Classification values come from the same governed master tables the Test
  // Case editor reads, queried directly with active_only=false so an inactive
  // parent cannot hide a row the requirement may already be carrying.
  const [domainOptions, setDomainOptions] = useState<TaxonomyEntry[]>([]);
  const [productOptions, setProductOptions] = useState<TaxonomyEntry[]>([]);
  const [subRequestTypeOptions, setSubRequestTypeOptions] = useState<TaxonomyEntry[]>([]);
  const [businessProcessOptions, setBusinessProcessOptions] = useState<TaxonomyEntry[]>([]);
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      taxonomyApi.qaDomains(false),
      taxonomyApi.products({ active_only: false }),
      taxonomyApi.subRequestTypes(false),
      taxonomyApi.businessProcesses(false),
    ])
      .then(([domains, products, subRequestTypes, businessProcesses]) => {
        if (cancelled) return;
        setDomainOptions(domains.data);
        setProductOptions(products.data);
        setSubRequestTypeOptions(subRequestTypes.data);
        setBusinessProcessOptions(businessProcesses.data);
      })
      .catch(() => {
        if (cancelled) return;
        setDomainOptions([]);
        setProductOptions([]);
        setSubRequestTypeOptions([]);
        setBusinessProcessOptions([]);
      });
    return () => { cancelled = true; };
  }, []);
  // Test Environment + Generation Notes — tester-set context for AI test-case
  // generation, editable per requirement in the Details tab.
  const [genEnvDraft, setGenEnvDraft] = useState("");
  const [genNotesDraft, setGenNotesDraft] = useState("");
  const [savingGenContext, setSavingGenContext] = useState(false);
  const [genContextSaved, setGenContextSaved] = useState(false);

  const handleWorkspaceViewChange = (view: RequirementsWorkspaceView) => {
    setWorkspaceView(view);
    const params = new URLSearchParams(searchParams.toString());
    if (view === "intake") {
      params.delete("view");
    } else {
      params.set("view", view);
    }
    router.push(`${pathname}?${params.toString()}`);
  };

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
      .catch((e: any) => setLoadError(e?.response?.data?.detail || e?.message || "Failed to load projects."));
  }, [searchParams]);

  useEffect(() => {
    const view = searchParams.get("view");
    if (view === "analysis" || view === "traceability" || view === "review") {
      setWorkspaceView(view);
    } else {
      setWorkspaceView("intake");
    }
  }, [searchParams]);

  // Load Requirements and Documents
  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoadError(null);
    setLoading(true);
    try {
      const [reqRes, docRes, dupRes, appsRes] = await Promise.all([
        requirementsApi.list(selectedProject),
        documentsApi.list(selectedProject),
        // Detection is server-side and project-wide. A failure here must not
        // blank the workspace, so it degrades to "no candidates known" rather
        // than taking the whole load down with it.
        requirementsApi.duplicates(selectedProject).catch(() => null),
        // Only to tell the user when portal URL analysis has no registered
        // application to resolve a base URL against. Same degrade-quietly rule:
        // an unreachable registry must not stop requirements loading.
        applicationsApi.getForProject(selectedProject).catch(() => null),
      ]);
      setRequirements(reqRes.data);
      setDocuments(docRes.data);
      setDuplicateReport(dupRes?.data ?? null);
      setRegisteredApplications(appsRes?.data.applications ?? null);
    } catch (e: any) {
      setLoadError(e?.response?.data?.detail || e?.message || "Failed to load requirements data.");
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  const refreshRequirementDrawer = useCallback(async (requirementId: number) => {
    const [requirementResult, reviewsResult] = await Promise.all([
      requirementsApi.get(requirementId),
      requirementsApi.qualityReviews(requirementId),
    ]);
    const refreshed = requirementResult.data;
    setRequirements((current) => current.map((item) => item.id === refreshed.id ? refreshed : item));
    setSelectedReq((current) => current?.id === refreshed.id ? refreshed : current);
    setSelectedQualityReviews(reviewsResult.data);
    return refreshed;
  }, []);

  const focusAnalysisActions = () => {
    window.setTimeout(() => {
      analysisActionsRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 80);
  };

  useEffect(() => {
    loadData();
  }, [loadData]);

  const loadTraceabilityMatrix = useCallback(async () => {
    if (!selectedProject) return;
    setMatrixLoading(true);
    try {
      // Backend caps page_size at 200 (le=200 in the query validator).
      const res = await traceabilityApi.matrix(selectedProject, { page: 1, page_size: 200, include_drafts: true });
      setTraceabilityMatrix(res.data.items);
    } catch (err) {
      console.error("Failed to load traceability matrix:", err);
      setTraceabilityMatrix([]);
    } finally {
      setMatrixLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadTraceabilityMatrix();
  }, [loadTraceabilityMatrix]);

  const loadApprovalActions = useCallback(async () => {
    if (!selectedProject) return;
    try {
      const res = await traceabilityApi.approvals(selectedProject, {
        entity_type: "requirement",
        page: 1,
        page_size: 200,
      });
      setApprovalActions(res.data);
    } catch (err) {
      console.error("Failed to load requirement approval history:", err);
      setApprovalActions([]);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadApprovalActions();
  }, [loadApprovalActions]);

  const loadBlockerSummary = useCallback(async (requirementId: number | null) => {
    if (requirementId == null) {
      setBlockerSummary(null);
      return;
    }
    try {
      const { data } = await requirementsApi.blockers(requirementId);
      setBlockerSummary(data);
    } catch {
      // The panel falls back to the locally derived list rather than showing
      // nothing; a failed read must not make a blocked requirement look clear.
      setBlockerSummary(null);
    }
  }, []);

  useEffect(() => {
    void loadBlockerSummary(selectedReq?.id ?? null);
  }, [selectedReq?.id, selectedReq?.updated_at, loadBlockerSummary]);

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
    setReviewFilter("all");
    setReviewSearch("");
    setReviewDomainFilter("all");
    setReviewOwnerFilter("all");
    setReviewerFilter("all");
    setAnalysisOverviewDetail(null);
    setSelectedQualityReviews([]);
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

  const handleManualIntake = async () => {
    if (!selectedProject) return;
    const title = pasteTitle.trim();
    const content = pasteText.trim();
    if (!title || !content) {
      setAgentError("A source title and source content are required before intake.");
      return;
    }

    setManualIntakeBusy(true);
    setAgentError(null);
    try {
      await requirementsApi.create({
        project_id: selectedProject,
        title,
        summary: content,
        source: "pasted_text",
      });
      await loadData();
      setPasteTitle("");
      setPasteText("");
      setAgentStatus("Pasted text accepted into the governed intake queue.");
      setTab("requirements");
    } catch (e: any) {
      setAgentError(e?.response?.data?.detail || "The source could not be added to requirement intake.");
    } finally {
      setManualIntakeBusy(false);
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
    while (true) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      try {
        const res = await agentRunsApi.get(runId);
        const run = res.data;
        const terminalStatus = terminalAIStatus(run.status);
        if (terminalStatus) {
          const message = run.error_message || failedFallback;
          setAgentStatus("");
          updateAIProcessing({ status: terminalStatus, currentStage: run.status, errorCategory: "AI processing failed", errorMessage: message });
          throw new Error(message);
        }
        if (run.progress_message) {
          setAgentStatus(`${run.progress_message} (${run.progress_percent ?? 0}%)`);
          updateAIProcessing({ status: "processing", currentStage: run.progress_message });
        }
        if (run.status === "completed") {
          const count = typeof run.output_data?.count === "number" ? run.output_data.count : null;
          if (options?.zeroCountError && count === 0) {
            setAgentStatus("");
            await loadData();
            throw new Error(options.zeroCountError);
          }
          setAgentStatus(completedMessage);
          await loadData();
          return;
        }
      } catch (err) {
        console.error("Error polling agent run:", err);
        throw err;
      }
    }
  };

  const runIntakeAgent = async (docId: number) => {
    if (!selectedProject) return;
    setAgentRunning(true);
    setAgentStatus("Agent 1 running -- extracting requirements from document...");
    setAgentError(null);
    try {
      await runAIAction({
        actionName: "requirement_intake",
        title: "Analyzing Requirement Source",
        module: "Requirement Intelligence",
        artifactType: "Requirements",
        projectId: selectedProject,
        stages: AI_PROCESSING_STAGES.requirementAnalysis,
        successMessage: "Requirements extracted successfully.",
        execute: async () => {
      const res = await requirementsApi.triggerIntake(selectedProject, docId);
      const data = res.data as { message?: string; agent_run_id?: number };
      if (data.agent_run_id) {
        updateAIProcessing({ status: "waiting", agentRunId: String(data.agent_run_id), currentStage: data.message ?? "Waiting for the requirement-intake agent" });
        setAgentStatus(data.message ?? "Requirement intake queued.");
        await pollAgentRun(data.agent_run_id, "Requirements extracted successfully.", "Requirement extraction failed.");
      } else {
        setAgentStatus(`Done: ${data.message || "Extraction completed successfully"}`);
        await loadData();
      }
      return res;
        },
      });
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
      await runAIAction({
        actionName: "analyze_portal_url",
        title: "Analyzing Portal URL",
        module: "Requirement Intelligence",
        artifactType: "Portal Requirements",
        projectId: selectedProject,
        stages: AI_PROCESSING_STAGES.requirementAnalysis,
        successMessage: "Portal requirements generated successfully.",
        execute: async () => {
      const res = await requirementsApi.triggerUrlAnalysis(selectedProject, portalUrl.trim(), urlCrawlDepth);
      const data = res.data as { message?: string; agent_run_id?: number };
      if (data.agent_run_id) {
        updateAIProcessing({ status: "waiting", agentRunId: String(data.agent_run_id), currentStage: data.message ?? "Waiting for the portal-analysis agent" });
        setAgentStatus(data.message ?? "Portal URL analysis queued.");
        await pollAgentRun(data.agent_run_id, "Portal requirements generated successfully.", "Portal URL analysis failed.");
        setPortalUrl("");
      } else {
        setAgentStatus(`Done: ${data.message || "URL analysis completed successfully"}`);
        await loadData();
      }
      return res;
        },
      });
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
      await runAIAction({
        actionName: "analyze_repository",
        title: source === "github" ? "Analyzing GitHub Repository" : "Analyzing Local Repository",
        module: "Requirement Intelligence",
        artifactType: "Code-derived Requirements",
        projectId: selectedProject,
        stages: AI_PROCESSING_STAGES.requirementAnalysis,
        successMessage: "Code requirements generated successfully.",
        execute: async () => {
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
        updateAIProcessing({ status: "waiting", agentRunId: String(data.agent_run_id), currentStage: data.message ?? "Waiting for the code-analysis agent" });
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
      return res;
        },
      });
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
      await runAIAction({
        actionName: "analyze_ui_screenshot",
        title: "Analyzing UI Screenshot",
        module: "Requirement Intelligence",
        artifactType: "UI Requirements",
        projectId: selectedProject,
        stages: AI_PROCESSING_STAGES.requirementAnalysis,
        successMessage: "UI requirements generated successfully.",
        execute: async () => {
      const res = await requirementsApi.triggerUiAnalysis(selectedProject, docId);
      const data = res.data as { message?: string; agent_run_id?: number };
      if (data.agent_run_id) {
        updateAIProcessing({ status: "waiting", agentRunId: String(data.agent_run_id), currentStage: data.message ?? "Waiting for the vision agent" });
        setAgentStatus(data.message ?? "UI screenshot analysis queued.");
        await pollAgentRun(data.agent_run_id, "UI requirements generated successfully.", "UI screenshot analysis failed.");
      } else {
        setAgentStatus(`Done: ${data.message || "UI analysis completed successfully"}`);
        await loadData();
      }
      return res;
        },
      });
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
    const drawerRequirementId = selectedReq && (!reqIds || reqIds.includes(selectedReq.id))
      ? selectedReq.id
      : null;
    setAgentRunning(true);
    setAgentStatus("Agent 2 running -- reviewing requirement quality...");
    setAgentError(null);
    try {
      await runAIAction({
        actionName: "review_requirement_quality",
        title: "Reviewing Requirement Quality",
        module: "Requirement Intelligence",
        artifactType: "Quality Review",
        projectId: selectedProject,
        stages: AI_PROCESSING_STAGES.requirementAnalysis,
        successMessage: "Requirement quality review completed.",
        execute: async () => {
      const res = await requirementsApi.triggerQuality(selectedProject, reqIds);
      const data = res.data as { message?: string; agent_run_id?: number };
      if (data.agent_run_id) {
        updateAIProcessing({ status: "waiting", agentRunId: String(data.agent_run_id), currentStage: data.message ?? "Waiting for the quality-review agent" });
        setAgentStatus(data.message ?? "Quality review queued.");
        await pollAgentRun(data.agent_run_id, "Quality review completed successfully.", "Quality review failed.");
      } else {
        const summary = (data as any).summary as Record<string, number> | undefined;
        setAgentStatus(`Done. Pass: ${summary?.pass ?? 0}, Needs Revision: ${summary?.needs_revision ?? 0}, Fail: ${summary?.fail ?? 0}`);
        await loadData();
      }
      return res;
        },
      });
      if (drawerRequirementId) {
        await refreshRequirementDrawer(drawerRequirementId);
        focusAnalysisActions();
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setAgentError(detail ? `Quality review failed: ${detail}` : "Quality review failed — check backend logs.");
      setAgentStatus("");
    } finally {
      setAgentRunning(false);
    }
  };

  const handleRequirementTransition = async (req: Requirement, action: RequirementTransitionAction, nextView: RequirementsWorkspaceView) => {
    setTransitioning(true);
    setAgentError(null);
    try {
      await requirementsApi.transition(req.id, action, notes || undefined);
      await loadData();
      setSelectedReq(null);
      setNotes("");
      handleWorkspaceViewChange(nextView);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      const message = typeof detail === "string" ? detail : detail?.message;
      const blockers = Array.isArray(detail?.blockers) ? ` ${detail.blockers.join(" ")}` : "";
      setAgentError(`${message || "Requirement transition failed."}${blockers}`);
    } finally {
      setTransitioning(false);
    }
  };

  const sendSourceToAnalysis = async (source: IntakeSourceRow) => {
    if (!source.requirementIds.length) return;
    setTransitioning(true);
    setAgentError(null);
    try {
      await Promise.all(source.requirementIds.map((id) => requirementsApi.transition(id, "send_to_analysis")));
      await loadData();
      setSelectedSource(null);
      handleWorkspaceViewChange("analysis");
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setAgentError(typeof detail === "string" ? detail : detail?.message || "Source hand-off failed.");
    } finally {
      setTransitioning(false);
    }
  };

  const openAnalysisDialog = (kind: AnalysisDialog) => {
    if (!selectedReq) return;
    setAnalysisDialogError(null);
    setCriteriaDraft((selectedReq.acceptance_criteria || []).join("\n"));
    // Normalized, not `.join("\n")` — entries are objects now and would render
    // as "[object Object]" in the textarea.
    setMissingInfoDraft(
      missingInfoItems(selectedReq.missing_information).map(formatMissingInfoLine).join("\n"),
    );
    setResolutionDraft("");
    setMarkMissingResolved(false);
    setSummaryDraft(selectedReq.summary || "");
    setBusinessRulesDraft((selectedReq.business_rules || []).join("\n"));
    setRisksDraft((selectedReq.risks || []).join("\n"));
    setSystemsDraft((selectedReq.systems_impacted || []).join("\n"));
    setInterfacesDraft((selectedReq.impacted_interfaces || []).join("\n"));
    setApisDraft((selectedReq.apis || []).join("\n"));
    setClassificationDraft({
      domain: selectedReq.telecom_domain || selectedReq.qa_domain || "",
      journey: selectedReq.business_process || "",
      application: selectedReq.product || selectedReq.product_group || "",
      subRequestType: selectedReq.sub_request_type || "",
      testType: selectedReq.test_phase || "",
      riskLevel: selectedReq.risk_level || "",
    });
    setAnalysisDialog(kind);
  };

  const saveAnalysisDialog = async () => {
    if (!selectedReq || !analysisDialog) return;
    if (analysisDialogSubmittingRef.current) return;
    analysisDialogSubmittingRef.current = true;
    setAnalysisDialogSaving(true);
    setAgentError(null);
    setAnalysisDialogError(null);
    try {
      const resolvingClarification = analysisDialog === "issues" && selectedReq.readiness_status === "needs_clarification";
      let updates: Partial<Requirement> = {};
      if (analysisDialog === "content") {
        updates = {
          summary: summaryDraft.trim(),
          business_rules: splitLines(businessRulesDraft),
          risks: splitLines(risksDraft),
        };
      } else if (analysisDialog === "acceptance") {
        updates = { acceptance_criteria: splitLines(criteriaDraft) };
      } else if (analysisDialog === "issues") {
        if ((markMissingResolved || resolvingClarification) && !resolutionDraft.trim()) {
          setAnalysisDialogError("Add resolution details before marking missing information as resolved.");
          return;
        }
        const resolutionNote = resolutionDraft.trim()
          ? `${selectedReq.review_notes ? `${selectedReq.review_notes}\n` : ""}Missing information resolution: ${resolutionDraft.trim()}`
          : selectedReq.review_notes;
        if (markMissingResolved || resolvingClarification) {
          const res = await requirementsApi.transition(selectedReq.id, "resolve_clarification", resolutionDraft.trim());
          setSelectedReq(res.data);
          setRequirements((current) => current.map((item) => item.id === res.data.id ? res.data : item));
          const remainingIssues = getEditableAnalysisValidationIssues(
            res.data,
            duplicateRequirementIds.has(res.data.id),
          );
          setAgentStatus(remainingIssues.length
            ? `Clarification saved. Next validation: ${remainingIssues[0]}`
            : "Clarification saved. All editable validation details are complete; Re-run Analysis is now the required next step.");
          setAnalysisDialog(null);
          focusAnalysisActions();
          return;
        }
        // Severity comes from the "(advisory)" marker the editor shows, falling
        // back to the line's original severity when it is unmarked and
        // unchanged. Matching on text alone could not survive an edit.
        const existingSeverity = new Map(
          missingInfoItems(selectedReq?.missing_information).map((entry) => [
            entry.item,
            entry.severity,
          ]),
        );
        updates = {
          missing_information: markMissingResolved
            ? []
            : splitLines(missingInfoDraft)
                .map((line) => parseMissingInfoLine(line, existingSeverity))
                .filter((entry) => entry.item),
          review_notes: resolutionNote,
        };
      } else if (analysisDialog === "classification") {
        if (!classificationDraft.domain.trim() && !classificationDraft.journey.trim()) {
          setAnalysisDialogError("Complete either Domain or Journey / Business Process.");
          return;
        }
        if (!classificationDraft.application.trim() && !classificationDraft.subRequestType.trim()) {
          setAnalysisDialogError("Complete either Application / Product or Sub Request Type.");
          return;
        }
        updates = {
          telecom_domain: classificationDraft.domain.trim() || undefined,
          business_process: classificationDraft.journey.trim() || undefined,
          product: classificationDraft.application.trim() || undefined,
          sub_request_type: classificationDraft.subRequestType.trim() || undefined,
          test_phase: classificationDraft.testType.trim() || undefined,
          risk_level: classificationDraft.riskLevel.trim() || undefined,
        };
      } else if (analysisDialog === "systems") {
        updates = {
          systems_impacted: splitLines(systemsDraft),
          impacted_interfaces: splitLines(interfacesDraft),
          apis: splitLines(apisDraft),
        };
      } else if (analysisDialog === "clarification") {
        if (!resolutionDraft.trim()) {
          setAnalysisDialogError("Describe the clarification required before submitting the request.");
          return;
        }
        const res = await requirementsApi.transition(selectedReq.id, "request_clarification", resolutionDraft.trim());
        setSelectedReq(res.data);
        setRequirements((current) => current.map((item) => item.id === res.data.id ? res.data : item));
        setAgentStatus("Clarification request recorded and added to the audit trail.");
        setAnalysisDialog(null);
        return;
      }
      const res = await requirementsApi.update(selectedReq.id, updates);
      setSelectedReq(res.data);
      setRequirements((current) => current.map((item) => item.id === res.data.id ? res.data : item));
      const remainingIssues = getEditableAnalysisValidationIssues(
        res.data,
        duplicateRequirementIds.has(res.data.id),
      );
      setAgentStatus(remainingIssues.length
        ? `Changes saved. Next validation: ${remainingIssues[0]}`
        : "Changes saved. All editable validation details are complete; Re-run Analysis is now the required next step.");
      setAnalysisDialog(null);
      focusAnalysisActions();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      const message = typeof detail === "string" ? detail : detail?.message || "Unable to update requirement details.";
      setAnalysisDialogError(message);
      setAgentError(message);
    } finally {
      analysisDialogSubmittingRef.current = false;
      setAnalysisDialogSaving(false);
    }
  };

  const handleApprove = async (action: "approve" | "reject") => {
    if (!selectedReq) return;
    setReviewLoading(true);
    try {
      await requirementsApi.approve(selectedReq.id, action, notes || undefined);
      await Promise.all([loadData(), loadApprovalActions()]);
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
      // A new result set invalidates any prior pick — keeping keys that are no
      // longer on screen would import issues the user can no longer see.
      setSelectedJiraKeys(new Set());
      setJiraMessage(`Fetched ${res.data.items.length} of ${res.data.total} Jira issues. Tick the ones to import, or import all matches.`);
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
    // An explicit pick wins; with nothing ticked this is undefined and the
    // import behaves exactly as it did before selection existed.
    const chosenKeys = selectedJiraKeys.size > 0 ? Array.from(selectedJiraKeys) : undefined;
    setJiraBusy(true);
    setJiraError(null);
    setJiraMessage(null);
    try {
      const res = await jiraApi.importRequirements(selectedJiraConnection, {
        issue_types: splitCsv(jiraFilters.issue_types),
        statuses: splitCsv(jiraFilters.statuses),
        priorities: splitCsv(jiraFilters.priorities),
        labels: splitCsv(jiraFilters.labels),
        issue_keys: chosenKeys,
        assignee: jiraFilters.assignee.trim() || undefined,
        text: jiraFilters.text.trim() || undefined,
        updated_since: jiraFilters.updated_since.trim() || undefined,
        jql: jiraFilters.jql.trim() || undefined,
        batch_size: pageSize,
        max_issues: maxIssues,
      });
      await loadData();
      const scope = chosenKeys ? `${chosenKeys.length} selected issue(s)` : "all matching issues";
      setJiraMessage(`Imported ${res.data.imported} Jira requirements from ${scope}: ${res.data.created} created, ${res.data.updated} updated.`);
    } catch (e: any) {
      setJiraError("Failed to import Jira requirements.");
    } finally {
      setJiraBusy(false);
    }
  };

  const toggleJiraKey = (key: string) => {
    setSelectedJiraKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
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
    setSelectedQualityReviews([]);
    setQualityReviewsLoading(true);
    requirementsApi
      .qualityReviews(req.id)
      .then((res) => setSelectedQualityReviews(res.data))
      .catch(() => setSelectedQualityReviews([]))
      .finally(() => setQualityReviewsLoading(false));
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
  const requirementsByStage = useMemo(() => ({
    intake: requirements.filter((requirement) => getRequirementWorkflowStage(requirement) === "intake"),
    analysis: requirements.filter((requirement) => getRequirementWorkflowStage(requirement) === "analysis"),
    traceability: requirements.filter((requirement) => getRequirementWorkflowStage(requirement) === "traceability"),
    review: requirements.filter((requirement) => getRequirementWorkflowStage(requirement) === "review"),
  }), [requirements]);

  const filteredRequirements = useMemo(() => {
    return requirements.filter((r) => filterStatus === "all" || r.status === filterStatus);
  }, [requirements, filterStatus]);

  const intakeSources = useMemo<IntakeSourceRow[]>(() => {
    const documentRows = documents.map((document) => {
      const sourceRequirements = requirements.filter((requirement) => requirement.source_document_id === document.id);
      const intakeRequirements = sourceRequirements.filter((requirement) => getRequirementWorkflowStage(requirement) === "intake");
      const extractedCount = sourceRequirements.length;
      const normalizedStatus = document.status.toLowerCase();
      const isProcessing = ["uploaded", "processing"].includes(normalizedStatus);
      const isBlocked = ["failed", "error", "blocked"].includes(normalizedStatus);
      const status: IntakeSourceRow["status"] = isBlocked
        ? "blocked"
        : isProcessing
          ? "processing"
          : extractedCount > 0
            ? "completed"
            : "ready";
      const validationIssues = isBlocked
        ? ["Source processing failed. Review the processing job before retrying."]
        : [];
      return {
        id: `document-${document.id}`,
        documentId: document.id,
        name: document.original_filename,
        sourceType: document.file_type?.toUpperCase() || "Document",
        owner: "Project team",
        status,
        progress: status === "processing" ? 55 : status === "blocked" ? 0 : 100,
        extractedCount,
        validationIssues,
        provenance: `Uploaded source #${document.id}`,
        createdAt: document.created_at,
        nextAction: status === "blocked" ? "Retry" : status === "processing" ? "Processing" : intakeRequirements.length > 0 ? "Send to Analysis" : extractedCount > 0 ? "View Downstream" : "Run AI Intake",
        requirementIds: intakeRequirements.map((requirement) => requirement.id),
      } satisfies IntakeSourceRow;
    });

    const nonDocumentRows = requirements
      .filter((requirement) => !requirement.source_document_id)
      .map((requirement) => {
        const source = (requirement.source || "manual").toLowerCase();
        const sourceType = source.includes("jira")
          ? "Jira"
          : source.includes("url") || source.includes("portal")
            ? "URL"
            : source.includes("github") || source.includes("code") || source.includes("repo")
              ? "Repository"
              : source.includes("api")
                ? "API Specification"
                : source.includes("paste")
                  ? "Pasted Text"
                  : "Manual";
        const validationIssues = !requirement.title?.trim() ? ["A source title is required."] : [];
        return {
          id: `requirement-source-${requirement.id}`,
          name: requirement.jira_issue_key || requirement.title,
          sourceType,
          owner: resolveUser(requirement.created_by),
          status: validationIssues.length ? "blocked" : "completed",
          progress: validationIssues.length ? 0 : 100,
          extractedCount: 1,
          validationIssues,
          provenance: requirement.jira_issue_key
            ? `Imported from Jira issue ${requirement.jira_issue_key}`
            : `Created from ${sourceType.toLowerCase()} intake`,
          createdAt: requirement.created_at,
          nextAction: validationIssues.length ? "Retry" : getRequirementWorkflowStage(requirement) === "intake" ? "Send to Analysis" : "View Downstream",
          requirementIds: getRequirementWorkflowStage(requirement) === "intake" ? [requirement.id] : [],
        } satisfies IntakeSourceRow;
      });

    return [...documentRows, ...nonDocumentRows].sort((a, b) =>
      (b.createdAt || "").localeCompare(a.createdAt || "")
    );
  }, [documents, requirements, resolveUser]);

  const selectedProjectRecord = projects.find((project) => project.id === selectedProject);
  const selectedProjectPpmId = selectedProjectRecord?.ppm_id || "Not set";

  // Server-side, scored over requirement content. This was previously exact
  // lowercased title equality computed here in the browser, which found nothing
  // on the case that actually produces duplicates — a portal crawl deriving the
  // same fact from every page, titled differently each time.
  const duplicateRequirementIds = useMemo(
    () => new Set(duplicateReport?.duplicate_requirement_ids ?? []),
    [duplicateReport]
  );

  // Why a given requirement was flagged, so the drawer can say more than "1".
  const duplicateReasonById = useMemo(() => {
    const byId = new Map<number, string>();
    for (const pair of duplicateReport?.pairs ?? []) {
      if (!byId.has(pair.left_id)) byId.set(pair.left_id, `${pair.reason} Similar to ${pair.right_display_id}.`);
      if (!byId.has(pair.right_id)) byId.set(pair.right_id, `${pair.reason} Similar to ${pair.left_display_id}.`);
    }
    return byId;
  }, [duplicateReport]);

  const analysisRows = useMemo<AnalysisRow[]>(() => {
    return requirementsByStage.analysis.map((requirement) => {
      const meta = metadataRecord(requirement);
      const qualityMeta = (meta.quality_review || {}) as Record<string, any>;
      const ambiguityCount = asTextList(qualityMeta.ambiguities).length
        || asTextList(qualityMeta.ambiguity_findings).length
        || (String(requirement.quality_feedback || "").toLowerCase().includes("ambiguous") ? 1 : 0);
      const missingInfoCount = blockingMissingInfo(requirement.missing_information).length
        || asTextList(qualityMeta.missing_information).length;
      const duplicateCount = duplicateRequirementIds.has(requirement.id) ? 1 : 0;
      const conflictCount = asTextList(qualityMeta.conflicts).length
        || asTextList(meta.conflicts).length;
      const taxonomyReady = Boolean(requirement.telecom_domain || requirement.qa_domain || requirement.business_process)
        && Boolean(requirement.product || requirement.product_group || requirement.sub_request_type);
      const riskLevel = requirement.risk_level || "Not assessed";
      const status = getAnalysisStatus(requirement, duplicateCount > 0);
      const qualityScore = getRequirementQualityScore(requirement);
      const qualityVerdict = (requirement.quality_verdict || "").toLowerCase();
      const isQualityStale = qualityMeta.stale === true;
      const completedAnalysisGates = [
        Boolean(requirement.quality_verdict),
        missingInfoCount === 0,
        taxonomyReady,
        qualityVerdict === "pass",
      ].filter(Boolean).length;
      const progress = status === "analyzed" ? 100 : completedAnalysisGates * 25;
      const blockers = [
        ...(isQualityStale
          ? ["Saved changes must be validated. Re-run Analysis before traceability."]
          : []),
        ...(!isQualityStale && ["needs_revision", "fail"].includes((requirement.quality_verdict || "").toLowerCase())
          ? ["Quality analysis must reach a Pass verdict before traceability. Revise the requirement and re-run Analysis."]
          : []),
        ...getEditableAnalysisValidationIssues(
          requirement, duplicateCount > 0, duplicateReasonById.get(requirement.id),
        ),
      ];

      return {
        requirement,
        ppmId: selectedProjectPpmId,
        sourceLabel: requirement.jira_issue_key || requirement.source || "Manual",
        owner: resolveUser(requirement.updated_by || requirement.created_by),
        status,
        progress,
        qualityScore,
        ambiguityCount,
        missingInfoCount,
        duplicateCount,
        conflictCount,
        taxonomyReady,
        riskLevel,
        blockers,
      };
    });
  }, [duplicateReasonById, duplicateRequirementIds, requirementsByStage.analysis, resolveUser, selectedProjectPpmId]);

  const filteredAnalysisRows = useMemo(() => {
    const query = analysisSearch.trim().toLowerCase();
    return analysisRows.filter((row) => {
      const matchesStatus = analysisFilter === "all" || row.status === analysisFilter;
      const matchesQuery = !query
        || row.requirement.requirement_id.toLowerCase().includes(query)
        || row.requirement.title.toLowerCase().includes(query)
        || row.ppmId.toLowerCase().includes(query)
        || row.sourceLabel.toLowerCase().includes(query);
      return matchesStatus && matchesQuery;
    });
  }, [analysisFilter, analysisRows, analysisSearch]);

  const analysisStats = useMemo(() => {
    const count = (status: AnalysisStatus) => analysisRows.filter((row) => row.status === status).length;
    const needsAttention = analysisRows.filter((row) => row.ambiguityCount > 0).length;
    const missingInfo = analysisRows.filter((row) => row.missingInfoCount > 0).length;
    const duplicatesAndConflicts = analysisRows.filter((row) => row.duplicateCount > 0 || row.conflictCount > 0).length;
    const ready = analysisRows.filter((row) => row.status === "analyzed" && row.blockers.length === 0).length;

    return [
      { title: "Total Requirements", icon: FileText, iconBg: "bg-app-brand-75 border-app-brand-100", iconColor: "text-app-brand-500", value: analysisRows.length.toLocaleString(), sublabel: "In analysis", footer: "Current analysis-stage records" },
      { title: "Analysis Ready", icon: ShieldCheck, iconBg: "bg-emerald-50 border-emerald-100", iconColor: "text-emerald-500", value: ready.toLocaleString(), sublabel: "Ready", footer: "No mandatory blockers" },
      { title: "In Progress", icon: RefreshCw, iconBg: "bg-app-brand-75 border-app-brand-100", iconColor: "text-app-brand-500", value: (count("queued") + count("analyzing")).toLocaleString(), sublabel: "Active", footer: "Queued or analyzing" },
      { title: "Ambiguity Detected", icon: AlertTriangle, iconBg: "bg-orange-50 border-orange-100", iconColor: "text-orange-500", value: needsAttention.toLocaleString(), sublabel: "Review", footer: "Needs clarification" },
      { title: "Missing Information", icon: CircleDot, iconBg: "bg-red-50 border-red-100", iconColor: "text-red-500", value: missingInfo.toLocaleString(), sublabel: "Blocked", footer: "Details required" },
      { title: "Duplicates / Conflicts", icon: GitBranch, iconBg: "bg-purple-50 border-purple-100", iconColor: "text-purple-500", value: duplicatesAndConflicts.toLocaleString(), sublabel: "Review", footer: "Resolution required" },
    ];
  }, [analysisRows]);

  const scoredAnalysisRows = useMemo(
    () => analysisRows.filter((row) => row.qualityScore !== null),
    [analysisRows],
  );

  const analysisQualityAverage = useMemo(
    () => scoredAnalysisRows.length
      ? Math.round(scoredAnalysisRows.reduce((sum, row) => sum + (row.qualityScore as number), 0) / scoredAnalysisRows.length)
      : null,
    [scoredAnalysisRows],
  );

  const analysisDomainDistribution = useMemo(() => Object.entries(
    analysisRows.reduce<Record<string, number>>((groups, row) => {
      const key = row.requirement.telecom_domain || row.requirement.qa_domain || row.requirement.business_process || "Unclassified";
      groups[key] = (groups[key] || 0) + 1;
      return groups;
    }, {}),
  ).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])), [analysisRows]);

  const classifiedAnalysisCount = useMemo(
    () => analysisRows.filter((row) => row.requirement.telecom_domain || row.requirement.qa_domain || row.requirement.business_process).length,
    [analysisRows],
  );

  const analysisRowsWithIssues = useMemo(
    () => analysisRows.filter((row) => row.blockers.length > 0 || row.ambiguityCount > 0 || row.missingInfoCount > 0 || row.duplicateCount > 0 || row.conflictCount > 0),
    [analysisRows],
  );

  const traceabilityRows = useMemo<RequirementTraceabilityRow[]>(() => {
    const matrixByRequirementId = new Map(traceabilityMatrix.map((row) => [row.requirement.id, row]));
    return requirementsByStage.traceability.map((requirement) => {
      const matrix = matrixByRequirementId.get(requirement.id);
      const analysis = analysisRows.find((row) => row.requirement.id === requirement.id);
      const testCaseLinked = matrix?.test_cases.length ?? 0;
      const defectCount = matrix?.defects.length ?? 0;
      const evidenceLinked = matrix?.execution_results.length ?? 0;
      const gapCount = matrix?.gaps.length ?? 0;
      const scenarioLinked = testCaseLinked > 0 ? Math.max(1, Math.min(3, Math.ceil(testCaseLinked / 2))) : 0;
      const scenarioTotal = Math.max(scenarioLinked, testCaseLinked > 0 ? 3 : gapCount > 0 ? 1 : 0);
      const testCaseTotal = Math.max(testCaseLinked, scenarioLinked * 2, gapCount > 0 ? 2 : 0);
      const automationLinked = matrix?.test_cases.filter((item) => (item.status || "").toLowerCase().includes("auto")).length
        ?? Math.max(0, Math.min(testCaseLinked, Math.floor(testCaseLinked * 0.6)));
      const automationTotal = Math.max(automationLinked, testCaseTotal > 0 ? Math.max(1, Math.ceil(testCaseTotal * 0.75)) : 0);
      const evidenceTotal = Math.max(evidenceLinked, testCaseTotal > 0 ? testCaseTotal * 2 : 0);
      const hasBroken = defectCount > 0 && evidenceLinked > 0;
      const health: TraceabilityHealth = testCaseLinked === 0 && evidenceLinked === 0
        ? "not_traced"
        : gapCount > 0
          ? "missing_links"
          : hasBroken
            ? "broken_stale"
            : scenarioTotal > 0 && scenarioLinked >= scenarioTotal && testCaseTotal > 0 && testCaseLinked >= testCaseTotal && evidenceTotal > 0 && evidenceLinked >= evidenceTotal
              ? "fully_traced"
              : "partial_trace";

      return {
        requirement,
        ppmId: String(metadataRecord(requirement).ppm_id || selectedProjectPpmId || "Not assigned"),
        sourceLabel: requirement.jira_issue_key || requirement.source || "Source / Evidence",
        analysisStatus: analysis?.status ?? getAnalysisStatus(requirement, duplicateRequirementIds.has(requirement.id)),
        scenarioLinked,
        scenarioTotal,
        testCaseLinked,
        testCaseTotal,
        automationLinked,
        automationTotal,
        evidenceLinked,
        evidenceTotal,
        defectCount,
        health,
        updatedAt: requirement.updated_at,
        gaps: matrix?.gaps ?? [],
      };
    });
  }, [analysisRows, duplicateRequirementIds, requirementsByStage.traceability, selectedProjectPpmId, traceabilityMatrix]);

  const filteredTraceabilityRows = useMemo(() => {
    const query = traceabilitySearch.trim().toLowerCase();
    return traceabilityRows.filter((row) => {
      const matchesHealth = traceabilityFilter === "all" || row.health === traceabilityFilter;
      const matchesQuery = !query
        || row.requirement.requirement_id.toLowerCase().includes(query)
        || row.requirement.title.toLowerCase().includes(query)
        || row.ppmId.toLowerCase().includes(query)
        || row.sourceLabel.toLowerCase().includes(query);
      return matchesHealth && matchesQuery;
    });
  }, [traceabilityFilter, traceabilityRows, traceabilitySearch]);

  const traceabilityStats = useMemo(() => {
    const total = traceabilityRows.length;
    const count = (health: TraceabilityHealth) => traceabilityRows.filter((row) => row.health === health).length;
    const fully = count("fully_traced");
    const partial = count("partial_trace");
    const missingScenario = traceabilityRows.filter((row) => row.scenarioLinked < row.scenarioTotal).length;
    const missingCases = traceabilityRows.filter((row) => row.testCaseLinked < row.testCaseTotal).length;
    const broken = count("broken_stale") + count("missing_links");
    const pct = (value: number) => total > 0 ? `${((value / total) * 100).toFixed(1)}%` : "0.0%";

    return [
      { title: "Total Requirements", icon: FileText, iconBg: "bg-app-brand-75 border-app-brand-100", iconColor: "text-app-brand-500", value: total.toLocaleString(), sublabel: "100%", footer: "100% of analyzed" },
      { title: "Fully Traced", icon: ShieldCheck, iconBg: "bg-emerald-50 border-emerald-100", iconColor: "text-emerald-500", value: fully.toLocaleString(), sublabel: pct(fully), footer: `${pct(fully)} fully traced` },
      { title: "Partial Trace", icon: Link2, iconBg: "bg-app-brand-75 border-app-brand-100", iconColor: "text-app-brand-500", value: partial.toLocaleString(), sublabel: pct(partial), footer: `${pct(partial)} partial` },
      { title: "Missing Scenarios", icon: AlertTriangle, iconBg: "bg-amber-50 border-amber-100", iconColor: "text-amber-500", value: missingScenario.toLocaleString(), sublabel: pct(missingScenario), footer: `${pct(missingScenario)} missing` },
      { title: "Missing Test Cases", icon: Braces, iconBg: "bg-purple-50 border-purple-100", iconColor: "text-purple-500", value: missingCases.toLocaleString(), sublabel: pct(missingCases), footer: `${pct(missingCases)} missing` },
      { title: "Broken / Stale Links", icon: XCircle, iconBg: "bg-red-50 border-red-100", iconColor: "text-red-500", value: broken.toLocaleString(), sublabel: pct(broken), footer: `${pct(broken)} need attention` },
    ];
  }, [traceabilityRows]);

  const reviewRows = useMemo<RequirementReviewRow[]>(() => {
    const decisionsByRequirement = new Map<number, ApprovalAction>();
    approvalActions.forEach((action) => {
      if (!decisionsByRequirement.has(action.entity_id) && ["approved", "rejected"].includes(action.decision)) {
        decisionsByRequirement.set(action.entity_id, action);
      }
    });
    return requirementsByStage.review.map((requirement) => {
      const meta = metadataRecord(requirement);
      const terminal = ["approved", "rejected"].includes((requirement.status || "").toLowerCase());
      const decision = decisionsByRequirement.get(requirement.id);
      const analysisStatus = getAnalysisStatus(requirement, duplicateRequirementIds.has(requirement.id));
      const traceValidated = meta.traceability_validated === true || requirement.readiness_status === "pending_review" || ["approved", "rejected"].includes(requirement.status);
      const traceScore = traceValidated ? 100 : 0;
      const taxonomyReady = Boolean(requirement.telecom_domain || requirement.qa_domain || requirement.business_process)
        && Boolean(requirement.product || requirement.product_group || requirement.sub_request_type);
      const applicationMapped = Boolean(requirement.systems_impacted?.length || requirement.impacted_interfaces?.length || requirement.upstream_systems?.length || requirement.downstream_systems?.length || requirement.product || requirement.product_group);
      const blockers = [
        ...(analysisStatus !== "analyzed" ? ["Requirement analysis has not passed."] : []),
        ...(blockingMissingInfo(requirement.missing_information).length ? ["Missing information must be resolved."] : []),
        ...(duplicateRequirementIds.has(requirement.id) ? ["Potential duplicate requires resolution."] : []),
        ...(!taxonomyReady ? ["Taxonomy classification is incomplete."] : []),
        ...(!applicationMapped ? ["Application or system mapping is incomplete."] : []),
        ...(!traceValidated ? ["Traceability gate has not been validated."] : []),
        ...((requirement.status || "").toLowerCase() === "rejected" ? ["Requirement was rejected."] : []),
      ];
      const readyForApproval = blockers.length === 0 && !["approved", "rejected"].includes(requirement.status);
      const reviewStatus: ReviewStatus = requirement.status === "approved"
        ? "approved"
        : requirement.status === "rejected"
          ? "rejected"
          : blockers.length > 0
            ? (analysisStatus === "needs_clarification" || analysisStatus === "needs_revision" ? "changes_requested" : "blocked")
            : readyForApproval
              ? "ready"
              : "pending";
      const assignedReviewerId = Number(meta.assigned_reviewer_id || 0) || null;
      const reviewerId = assignedReviewerId ?? (terminal ? decision?.user_id ?? null : null);
      const sla = getReviewSla(meta.review_due_at, terminal);

      return {
        requirement,
        ppmId: String(meta.ppm_id || selectedProjectPpmId || "Not assigned"),
        owner: resolveUser(requirement.updated_by || requirement.created_by),
        analysisStatus,
        traceabilityHealth: traceValidated ? "fully_traced" : "not_traced",
        traceabilityScore: traceScore,
        reviewStatus,
        reviewerId,
        reviewer: reviewerId ? resolveUser(reviewerId) : "Unassigned",
        dueAt: sla.dueAt,
        slaStatus: sla.status,
        slaAge: sla.label,
        readyForApproval,
        blockers,
      };
    });
  }, [approvalActions, duplicateRequirementIds, requirementsByStage.review, resolveUser, selectedProjectPpmId]);

  const reviewDomains = useMemo(() => Array.from(new Set(
    reviewRows.map((row) => row.requirement.telecom_domain || row.requirement.qa_domain || row.requirement.business_process).filter(Boolean) as string[],
  )).sort(), [reviewRows]);

  const reviewOwners = useMemo(() => Array.from(new Set(reviewRows.map((row) => row.owner))).sort(), [reviewRows]);
  const reviewReviewers = useMemo(() => Array.from(new Set(reviewRows.map((row) => row.reviewer))).sort(), [reviewRows]);

  const filteredReviewRows = useMemo(() => {
    const query = reviewSearch.trim().toLowerCase();
    return reviewRows.filter((row) => {
      const domain = row.requirement.telecom_domain || row.requirement.qa_domain || row.requirement.business_process || "";
      return (reviewFilter === "all" || row.reviewStatus === reviewFilter)
        && (reviewDomainFilter === "all" || domain === reviewDomainFilter)
        && (reviewOwnerFilter === "all" || row.owner === reviewOwnerFilter)
        && (reviewerFilter === "all" || row.reviewer === reviewerFilter)
        && (!query
          || row.requirement.requirement_id.toLowerCase().includes(query)
          || row.requirement.title.toLowerCase().includes(query)
          || row.ppmId.toLowerCase().includes(query)
          || row.owner.toLowerCase().includes(query)
          || row.reviewer.toLowerCase().includes(query));
    });
  }, [reviewDomainFilter, reviewFilter, reviewOwnerFilter, reviewRows, reviewSearch, reviewerFilter]);

  const reviewerWorkload = useMemo(() => {
    const activeRows = reviewRows.filter((row) => !["approved", "rejected"].includes(row.reviewStatus));
    const counts = activeRows.reduce<Map<string, number>>((result, row) => {
      result.set(row.reviewer, (result.get(row.reviewer) || 0) + 1);
      return result;
    }, new Map());
    return Array.from(counts, ([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }, [reviewRows]);

  const reviewSlaStats = useMemo(() => {
    const activeRows = reviewRows.filter((row) => !["approved", "rejected"].includes(row.reviewStatus) && row.slaStatus !== "unassigned");
    const total = activeRows.length;
    return ([
      ["On Track", "on_track", "bg-emerald-500"],
      ["At Risk", "at_risk", "bg-amber-500"],
      ["Overdue", "overdue", "bg-red-500"],
    ] as const).map(([label, status, color]) => {
      const count = activeRows.filter((row) => row.slaStatus === status).length;
      return { label, count, color, percentage: total ? Math.round((count / total) * 100) : 0 };
    });
  }, [reviewRows]);

  const recentReviewActivity = useMemo(() => approvalActions
    .filter((action) => requirementsByStage.review.some((requirement) => requirement.id === action.entity_id))
    .slice(0, 5)
    .map((action) => {
      const requirement = requirementsByStage.review.find((item) => item.id === action.entity_id);
      return {
        id: action.id,
        text: `${requirement?.requirement_id || `Requirement #${action.entity_id}`} ${reviewActionLabel(action.action_type)} by ${resolveUser(action.user_id)}`,
        when: formatRelativeTime(action.created_at),
      };
    }), [approvalActions, requirementsByStage.review, resolveUser]);

  const reviewStats = useMemo(() => {
    const total = reviewRows.length;
    const count = (status: ReviewStatus) => reviewRows.filter((row) => row.reviewStatus === status).length;
    const ready = count("ready");
    const pending = count("pending");
    const changes = count("changes_requested");
    const approved = count("approved");
    const rejectedBlocked = count("rejected") + count("blocked");
    const pct = (value: number) => total > 0 ? `${((value / total) * 100).toFixed(1)}%` : "0.0%";
    return [
      { title: "Total for Review", icon: FileText, iconBg: "bg-app-brand-75 border-app-brand-100", iconColor: "text-app-brand-500", value: total.toLocaleString(), sublabel: "Review", footer: "100% of analyzed reqs" },
      { title: "Ready for Approval", icon: ShieldCheck, iconBg: "bg-emerald-50 border-emerald-100", iconColor: "text-emerald-500", value: ready.toLocaleString(), sublabel: pct(ready), footer: `${pct(ready)} ready` },
      { title: "Pending Review", icon: Clock, iconBg: "bg-amber-50 border-amber-100", iconColor: "text-amber-500", value: pending.toLocaleString(), sublabel: pct(pending), footer: `${pct(pending)} pending` },
      { title: "Changes Requested", icon: AlertTriangle, iconBg: "bg-purple-50 border-purple-100", iconColor: "text-purple-500", value: changes.toLocaleString(), sublabel: pct(changes), footer: `${pct(changes)} need updates` },
      { title: "Approved", icon: CheckCircle, iconBg: "bg-emerald-50 border-emerald-100", iconColor: "text-emerald-500", value: approved.toLocaleString(), sublabel: pct(approved), footer: `${pct(approved)} approved` },
      { title: "Rejected / Blocked", icon: XCircle, iconBg: "bg-red-50 border-red-100", iconColor: "text-red-500", value: rejectedBlocked.toLocaleString(), sublabel: pct(rejectedBlocked), footer: `${pct(rejectedBlocked)} not approved` },
    ];
  }, [reviewRows]);

  // UI-006 intake-governance metrics. Values are derived from persisted sources and
  // requirements so their ownership stays deterministic and auditable.
  const stats = useMemo(() => {
    // Requirements involved in at least one candidate pair. Counting
    // requirements rather than pairs matches what the reviewer acts on: five
    // restatements of one fact are five records to settle, not ten pairings.
    const duplicateCandidates = duplicateReport?.duplicate_requirement_ids.length ?? 0;
    const duplicateGroups = duplicateReport?.groups.length ?? 0;
    const ready = intakeSources.filter((source) => source.status === "completed" && source.validationIssues.length === 0 && source.requirementIds.length > 0).length;
    const processing = intakeSources.filter((source) => source.status === "processing").length;
    const blocked = intakeSources.filter((source) => source.status === "blocked").length;

    return [
      { title: "Total Sources", icon: Layers3, iconBg: "bg-app-brand-75 border-app-brand-100", iconColor: "text-app-brand-500", value: intakeSources.length.toLocaleString(), sublabel: "Sources", footer: "All governed intake records" },
      { title: "Ready for Analysis", icon: CheckCircle, iconBg: "bg-emerald-50 border-emerald-100", iconColor: "text-emerald-500", value: ready.toLocaleString(), sublabel: "Ready", footer: "Validated with extracted content" },
      { title: "Processing", icon: RefreshCw, iconBg: "bg-purple-50 border-purple-100", iconColor: "text-purple-500", value: processing.toLocaleString(), sublabel: "Active", footer: "AI intake jobs in progress" },
      { title: "Blocked", icon: AlertTriangle, iconBg: "bg-red-50 border-red-100", iconColor: "text-red-500", value: blocked.toLocaleString(), sublabel: "Sources", footer: "Validation or processing issues" },
      { title: "Duplicate Candidates", icon: CircleDot, iconBg: "bg-amber-50 border-amber-100", iconColor: "text-amber-500", value: duplicateCandidates.toLocaleString(), sublabel: "Review", footer: duplicateReport ? `${duplicateGroups} subject${duplicateGroups === 1 ? "" : "s"} · matched on title and acceptance criteria` : "Candidate matching unavailable" },
      { title: "Requirements Extracted", icon: FileText, iconBg: "bg-cyan-50 border-cyan-100", iconColor: "text-cyan-600", value: requirements.length.toLocaleString(), sublabel: "Records", footer: "All extracted requirement records" },
    ];
  }, [duplicateReport, intakeSources, requirements]);

  const selectedJiraConnectionRecord = jiraConnections.find((c) => c.id === selectedJiraConnection);

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Global Controls ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-app-brand-75 border border-app-brand-100 p-2.5">
            {workspaceView === "traceability" ? <Link2 className="h-6 w-6 text-[#B71920]" /> : workspaceView === "review" ? <ShieldCheck className="h-6 w-6 text-[#B71920]" /> : <FileText className="h-6 w-6 text-[#B71920]" />}
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">{workspaceView === "review" ? "Requirement Review & Approval" : workspaceView === "traceability" ? "Requirement Traceability" : workspaceView === "analysis" ? "Requirement Analysis" : "Requirements Workspace"}</h1>
            <p className="text-xs text-gray-500 mt-1">
              {workspaceView === "review"
                ? "Final review and approval before requirements move to test design and execution."
                : workspaceView === "traceability"
                ? "End-to-end visibility from business requirement to test execution, defects and evidence."
                : workspaceView === "analysis"
                  ? "AI-powered analysis to identify ambiguity, gaps, duplicates, conflicts, risks and classify requirements."
                  : "Govern requirement sources from intake through analysis, traceability, review and approval"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadData} className="h-8 w-8 p-0 border-gray-200">
            <RefreshCw className={cn("h-3.5 w-3.5 text-gray-500", loading && "animate-spin")} />
          </Button>

          {/* GAP-5: Export dropdown */}
          <div className="relative">
            <Button
              variant="outline"
              size="sm"
              disabled={!selectedProject || requirements.length === 0 || exportBusy}
              onClick={() => setShowExportMenu((v) => !v)}
              className="h-8 px-3 border-gray-200 text-gray-600 bg-white font-semibold text-xs"
            >
              {exportBusy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
              ) : (
                <Download className="h-3.5 w-3.5 mr-1" />
              )}
              Export
              <ChevronDown className="h-3 w-3 ml-1 text-gray-400" />
            </Button>
            {showExportMenu && (
              <div
                className="absolute right-0 top-full mt-1 z-50 w-52 rounded-xl border border-gray-200 bg-white shadow-lg py-1 animate-in fade-in zoom-in-95 duration-100"
                onMouseLeave={() => setShowExportMenu(false)}
              >
                {EXPORT_MENU_OPTIONS.map(([type, label, desc]) => (
                  <button
                    key={type}
                    onClick={() => handleExport(type)}
                    className="w-full text-left px-3 py-2.5 hover:bg-gray-50 transition-colors group"
                  >
                    <span className="block text-xs font-bold text-gray-800 group-hover:text-[#B71920]">{label}</span>
                    <span className="block text-[10px] text-gray-400 mt-0.5">{desc}</span>
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
          <div className="flex flex-wrap items-center gap-1 rounded-xl border border-gray-200 bg-white p-1.5 shadow-sm">
            <button
              onClick={() => handleWorkspaceViewChange("intake")}
              className={cn(
                "rounded-lg px-4 py-2 text-xs font-bold shadow-sm transition-all",
                workspaceView === "intake" ? "bg-[#B71920] text-white" : "text-gray-500 hover:text-gray-900"
              )}
            >
              Requirement Intake <span className="ml-1 text-[9px] opacity-75">UI-006</span>
            </button>
            <button
              onClick={() => handleWorkspaceViewChange("analysis")}
              className={cn(
                "rounded-lg px-4 py-2 text-xs font-bold shadow-sm transition-all",
                workspaceView === "analysis" ? "bg-[#B71920] text-white" : "text-gray-500 hover:text-gray-900"
              )}
            >
              Requirement Analysis <span className="ml-1 text-[9px] opacity-75">UI-007</span>
            </button>
            <button
              onClick={() => handleWorkspaceViewChange("traceability")}
              className={cn(
                "rounded-lg px-4 py-2 text-xs font-bold shadow-sm transition-all",
                workspaceView === "traceability" ? "bg-[#B71920] text-white" : "text-gray-500 hover:text-gray-900"
              )}
            >
              Traceability <span className="ml-1 text-[9px] opacity-75">UI-008</span>
            </button>
            <button
              onClick={() => handleWorkspaceViewChange("review")}
              className={cn(
                "rounded-lg px-4 py-2 text-xs font-bold shadow-sm transition-all",
                workspaceView === "review" ? "bg-[#B71920] text-white" : "text-gray-500 hover:text-gray-900"
              )}
            >
              Review & Approval <span className="ml-1 text-[9px] opacity-75">UI-009</span>
            </button>
            {["Requirement Analysis · UI-007", "Traceability · UI-008", "Review & Approval · UI-009"].map((view) => (
              <button key={view} disabled title="Available after its visual design gate is approved" className={cn("cursor-not-allowed rounded-lg px-4 py-2 text-xs font-bold text-gray-400", (view.startsWith("Requirement Analysis") || view.startsWith("Traceability") || view.startsWith("Review")) && "hidden")}>
                {view}
              </button>
            ))}
            <Badge variant="outline" className="ml-auto border-app-brand-100 bg-app-brand-75 text-app-brand-600">Phase 1 · P1-S2</Badge>
          </div>

          {/* ── Status Counts Cards ─────────────────────────────────────────────────── */}
          <div className={cn("grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6", workspaceView !== "intake" ? "gap-2" : "gap-3")}>
            {(workspaceView === "review" ? reviewStats : workspaceView === "traceability" ? traceabilityStats : workspaceView === "analysis" ? analysisStats : stats).map((card) => {
              const Icon = card.icon;
              return (
                <Card key={card.title} className="border-gray-200 hover:-translate-y-0.5 transition-all">
                  <CardContent className={cn("flex h-full flex-col justify-between", workspaceView !== "intake" ? "space-y-2 p-3" : "space-y-3 p-4")}>
                    <div className="flex items-center gap-2">
                      <div className={cn("flex shrink-0 items-center justify-center rounded-lg border", workspaceView !== "intake" ? "p-1" : "p-1.5", card.iconBg)}>
                        <Icon className={cn(workspaceView !== "intake" ? "h-3.5 w-3.5" : "h-4 w-4", card.iconColor)} />
                      </div>
                      <span className={cn("truncate font-bold text-gray-700", workspaceView !== "intake" ? "text-[11px]" : "text-xs")}>{card.title}</span>
                    </div>
                    <div className="flex items-baseline gap-1.5">
                      <span className={cn("font-bold text-gray-900", workspaceView !== "intake" ? "text-lg" : "text-xl")}>{card.value}</span>
                      {card.sublabel && (
                        <span className="text-[10px] font-bold text-gray-400">{card.sublabel}</span>
                      )}
                    </div>
                    <div className={cn("border-t border-gray-50 text-[10px] font-semibold text-gray-400", workspaceView !== "intake" ? "pt-1" : "pt-2")}>
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
                ? "border-app-brand-200 bg-app-brand-75 text-app-brand-700 animate-pulse"
                : agentError
                ? "border-red-200 bg-red-50 text-red-700"
                : "border-emerald-200 bg-emerald-50 text-emerald-700"
            )}>
              {agentRunning ? (
                <Loader2 className="h-4 w-4 animate-spin text-[#B71920] shrink-0" />
              ) : agentError ? (
                <AlertTriangle className="h-4 w-4 text-red-500 shrink-0" />
              ) : (
                <CheckCircle className="h-4 w-4 text-emerald-600 shrink-0" />
              )}
              <span className="flex-1">{agentError ?? agentStatus}</span>
              {!agentRunning && (
                <button onClick={() => { setAgentStatus(""); setAgentError(null); }} className="text-gray-400 hover:text-gray-700">
                  <XCircle className="h-4.5 w-4.5" />
                </button>
              )}
            </div>
          )}

          {/* ── Sub Navigation Tabs ────────────────────────────────────────────────── */}
          {workspaceView === "review" && (
            <div className="space-y-4">
              <Card className="border-gray-200 shadow-sm">
                <CardContent className="p-3">
                  <h2 className="mb-3 text-xs font-bold text-gray-900">Approval Readiness Overview</h2>
                  <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
                    {([
                      ["Analysis Complete", `${reviewRows.length ? Math.round((reviewRows.filter((row) => row.analysisStatus === "analyzed").length / reviewRows.length) * 100) : 0}%`, CheckCircle, "text-emerald-600"],
                      ["Traceability Health", `${reviewRows.length ? Math.round(reviewRows.reduce((sum, row) => sum + row.traceabilityScore, 0) / reviewRows.length) : 0}%`, ShieldCheck, "text-emerald-600"],
                      ["Missing Information", reviewRows.filter((row) => row.blockers.some((blocker) => blocker.toLowerCase().includes("missing"))).length.toString(), AlertTriangle, "text-amber-600"],
                      ["Duplicates Resolved", `${reviewRows.length ? Math.round((reviewRows.filter((row) => !row.blockers.some((blocker) => blocker.toLowerCase().includes("duplicate"))).length / reviewRows.length) * 100) : 0}%`, CheckCircle, "text-emerald-600"],
                      ["Mandatory Evidence", `${reviewRows.filter((row) => row.traceabilityHealth === "fully_traced").length} / ${reviewRows.length}`, ShieldCheck, "text-emerald-600"],
                      ["Policy & Permissions", currentUser ? (currentUser.is_superuser ? "Platform admin" : currentUser.role) : "Checking…", CheckCircle, "text-emerald-600"],
                    ] as const).map(([label, value, Icon, tone]) => (
                      <div key={label} className="flex items-start gap-2">
                        <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", tone)} />
                        <div>
                          <div className="text-[11px] font-bold text-gray-700">{label}</div>
                          <div className="mt-1 text-xs font-bold text-gray-900">{value}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-3 flex items-center justify-between rounded-lg border border-app-brand-100 bg-app-brand-75/40 px-3 py-2 text-[11px] font-semibold text-app-brand-700">
                    <span>Requirements must pass all readiness checks to be eligible for approval.</span>
                    <button onClick={() => setShowReadinessRules((value) => !value)} className="font-bold">
                      {showReadinessRules ? "Hide readiness rules" : "View readiness rules"} <ChevronRight className={cn("inline h-3 w-3 transition-transform", showReadinessRules && "rotate-90")} />
                    </button>
                  </div>
                  {showReadinessRules && (
                    <div className="mt-2 grid gap-2 rounded-lg border border-gray-200 bg-gray-50 p-3 text-[10px] font-semibold text-gray-600 md:grid-cols-2">
                      <span>• Requirement analysis must pass without unresolved missing information.</span>
                      <span>• Duplicate candidates and classification gaps must be resolved.</span>
                      <span>• Application/system mapping and traceability validation are mandatory.</span>
                      <span>• Approval and rejection are permission-checked and recorded in the audit history.</span>
                    </div>
                  )}
                </CardContent>
              </Card>

              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex flex-wrap gap-1 rounded-xl border border-gray-200 bg-white p-1 shadow-sm">
                  {([
                    ["all", "All"],
                    ["ready", "Ready"],
                    ["pending", "Pending"],
                    ["changes_requested", "Changes Requested"],
                    ["approved", "Approved"],
                    ["rejected", "Rejected"],
                    ["blocked", "Blocked"],
                  ] as Array<[ReviewStatus | "all", string]>).map(([status, label]) => (
                    <button
                      key={status}
                      onClick={() => setReviewFilter(status)}
                      className={cn(
                        "rounded-lg px-3 py-1.5 text-[11px] font-bold transition-colors",
                        reviewFilter === status ? "bg-[#B71920] text-white" : "text-gray-500 hover:bg-gray-50 hover:text-gray-900",
                      )}
                    >
                      {label}
                      <span className={cn("ml-1 rounded-full px-1.5 py-0.5 text-[9px]", reviewFilter === status ? "bg-white/20 text-white" : "bg-gray-100 text-gray-600")}>{status === "all" ? reviewRows.length : reviewRows.filter((row) => row.reviewStatus === status).length}</span>
                    </button>
                  ))}
                </div>
                <Button variant="outline" size="sm" onClick={() => selectedProject && handleExport("matrix-excel")} className="h-8 bg-white text-xs font-bold">
                  <Download className="mr-1 h-3.5 w-3.5" />Export
                </Button>
              </div>

              <div className="flex flex-col gap-2 rounded-xl border border-gray-200 bg-white p-3 shadow-sm xl:flex-row xl:items-center">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                  <input value={reviewSearch} onChange={(event) => setReviewSearch(event.target.value)} placeholder="Search by REQ ID, PPM ID, title, owner..." className="h-9 w-full rounded-lg border border-gray-200 bg-white pl-9 pr-3 text-xs font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-app-brand-200" />
                </div>
                <select aria-label="Review Status" value={reviewFilter} onChange={(event) => setReviewFilter(event.target.value as ReviewStatus | "all")} className="h-9 min-w-[140px] rounded-lg border border-gray-200 bg-white px-3 text-xs font-bold text-gray-500">
                  <option value="all">All review statuses</option>
                  <option value="ready">Ready</option><option value="pending">Pending</option><option value="changes_requested">Changes Requested</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="blocked">Blocked</option>
                </select>
                <select aria-label="Domain" value={reviewDomainFilter} onChange={(event) => setReviewDomainFilter(event.target.value)} className="h-9 min-w-[120px] rounded-lg border border-gray-200 bg-white px-3 text-xs font-bold text-gray-500">
                  <option value="all">All domains</option>
                  {reviewDomains.map((domain) => <option key={domain} value={domain}>{domain}</option>)}
                </select>
                <select aria-label="Owner" value={reviewOwnerFilter} onChange={(event) => setReviewOwnerFilter(event.target.value)} className="h-9 min-w-[120px] rounded-lg border border-gray-200 bg-white px-3 text-xs font-bold text-gray-500">
                  <option value="all">All owners</option>
                  {reviewOwners.map((owner) => <option key={owner} value={owner}>{owner}</option>)}
                </select>
                <select aria-label="Reviewer" value={reviewerFilter} onChange={(event) => setReviewerFilter(event.target.value)} className="h-9 min-w-[130px] rounded-lg border border-gray-200 bg-white px-3 text-xs font-bold text-gray-500">
                  <option value="all">All reviewers</option>
                  {reviewReviewers.map((reviewer) => <option key={reviewer} value={reviewer}>{reviewer}</option>)}
                </select>
              </div>

              <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
                <table className="min-w-[1220px] w-full border-collapse text-left text-xs">
                  <thead className="border-b border-gray-200 bg-gray-50/70 text-[10px] font-bold uppercase tracking-wider text-gray-400">
                    <tr>
                      <th className="px-3 py-2.5">Req ID</th><th className="px-3 py-2.5">PPM ID</th><th className="px-3 py-2.5">Title</th><th className="px-3 py-2.5">Analysis Status</th><th className="px-3 py-2.5">Traceability Health</th><th className="px-3 py-2.5">Review Status</th><th className="px-3 py-2.5">Assigned Reviewer</th><th className="px-3 py-2.5">SLA / Age</th><th className="px-3 py-2.5">Updated At</th><th className="px-3 py-2.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 font-medium text-gray-600">
                    {filteredReviewRows.map((row) => (
                      <tr key={row.requirement.id} onClick={() => { handleOpenReqDetail(row.requirement); setDrawerTab("details"); }} className="cursor-pointer transition-colors hover:bg-gray-50/70">
                        <td className="whitespace-nowrap px-3 py-3 font-mono text-[11px] font-bold text-[#B71920]">{row.requirement.requirement_id}</td>
                        <td className="whitespace-nowrap px-3 py-3 font-mono text-[11px] font-bold text-gray-600">{row.ppmId}</td>
                        <td className="max-w-[260px] px-3 py-3 font-bold text-gray-800"><div className="line-clamp-2">{row.requirement.title}</div></td>
                        <td className="px-3 py-3"><Badge variant={analysisBadgeVariant(row.analysisStatus)}>{analysisLabel(row.analysisStatus)}</Badge></td>
                        <td className="px-3 py-3"><div className="min-w-[100px]"><div className="mb-1 flex justify-between text-[10px] font-bold"><span>{traceHealthLabel(row.traceabilityHealth)}</span><span>{row.traceabilityScore}/100</span></div><div className="h-1.5 overflow-hidden rounded-full bg-gray-100"><div className={cn("h-full rounded-full", row.traceabilityScore >= 80 ? "bg-emerald-500" : row.traceabilityScore >= 50 ? "bg-amber-500" : "bg-red-500")} style={{ width: `${row.traceabilityScore}%` }} /></div></div></td>
                        <td className="px-3 py-3"><Badge variant={reviewStatusBadgeVariant(row.reviewStatus)}>{reviewStatusLabel(row.reviewStatus)}</Badge></td>
                        <td className="px-3 py-3"><span className="inline-flex items-center gap-2"><span className="flex h-6 w-6 items-center justify-center rounded-full bg-violet-100 text-[10px] font-bold text-violet-700">{row.reviewer.slice(0, 2).toUpperCase()}</span>{row.reviewer}</span></td>
                        <td className={cn("px-3 py-3 font-bold", row.slaStatus === "overdue" ? "text-red-600" : row.slaStatus === "at_risk" ? "text-amber-600" : row.slaStatus === "on_track" ? "text-emerald-600" : "text-gray-400")}>{row.slaAge}</td>
                        <td className="whitespace-nowrap px-3 py-3 text-gray-500">{row.requirement.updated_at ? new Date(row.requirement.updated_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "-"}</td>
                        <td className="px-3 py-3 text-right"><Button variant="outline" size="sm" className="h-7 px-2 text-[10px] font-bold">...</Button></td>
                      </tr>
                    ))}
                    {filteredReviewRows.length === 0 && (
                      <tr><td colSpan={10} className="px-4 py-8 text-center text-xs font-semibold text-gray-400">No requirements match the selected review filters.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div className="grid gap-3 xl:grid-cols-3">
                <Card className="border-gray-200 shadow-sm">
                  <CardContent className="p-3">
                    <h3 className="mb-2 text-xs font-bold text-gray-900">Review Workload</h3>
                    <div className="flex items-center gap-4">
                      <div
                        className="flex h-24 w-24 items-center justify-center rounded-full p-3"
                        style={{ background: `conic-gradient(#2563eb 0 ${reviewRows.length ? Math.round((reviewRows.filter((row) => !["approved", "rejected"].includes(row.reviewStatus)).length / reviewRows.length) * 100) : 0}%, #E8EAEE 0 100%)` }}
                      >
                        <div className="flex h-full w-full flex-col items-center justify-center rounded-full bg-white">
                          <span className="text-xl font-bold text-gray-900">{reviewRows.filter((row) => !["approved", "rejected"].includes(row.reviewStatus)).length}</span>
                          <span className="text-[9px] font-bold text-gray-400">Open reviews</span>
                        </div>
                      </div>
                      <div className="flex-1 space-y-1.5 text-[11px] font-semibold text-gray-600">
                        {reviewerWorkload.map(({ name, count }) => <div key={name} className="flex justify-between"><span>{name}</span><span>{count}</span></div>)}
                        {reviewerWorkload.length === 0 && <div className="text-gray-400">No open reviewer assignments.</div>}
                      </div>
                    </div>
                  </CardContent>
                </Card>
                <Card className="border-gray-200 shadow-sm">
                  <CardContent className="p-3">
                    <h3 className="mb-2 text-xs font-bold text-gray-900">Review SLA Status</h3>
                    <div className="space-y-3 text-[11px] font-semibold text-gray-600">
                      {reviewSlaStats.map(({ label, count, color, percentage }) => <div key={label}><div className="mb-1 flex justify-between"><span>{label}</span><span>{count}</span></div><div className="h-1.5 rounded-full bg-gray-100"><div className={cn("h-full rounded-full", color)} style={{ width: `${percentage}%` }} /></div></div>)}
                      {reviewRows.some((row) => row.slaStatus === "unassigned" && !["approved", "rejected"].includes(row.reviewStatus)) && (
                        <div className="flex justify-between text-gray-400"><span>Due date not assigned</span><span>{reviewRows.filter((row) => row.slaStatus === "unassigned" && !["approved", "rejected"].includes(row.reviewStatus)).length}</span></div>
                      )}
                    </div>
                  </CardContent>
                </Card>
                <Card className="border-gray-200 shadow-sm">
                  <CardContent className="p-3">
                    <h3 className="mb-2 text-xs font-bold text-gray-900">Recent Review Activity</h3>
                    <div className="space-y-2 text-[11px] font-semibold text-gray-600">
                      {recentReviewActivity.map((activity) => <div key={activity.id} className="flex justify-between gap-2"><span className="truncate">{activity.text}</span><span className="shrink-0 text-gray-400">{activity.when}</span></div>)}
                      {recentReviewActivity.length === 0 && <div className="text-gray-400">No requirement governance activity recorded.</div>}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          )}

          {workspaceView === "traceability" && (
            <div className="space-y-4">
              <Card className="border-gray-200 shadow-sm">
                <CardContent className="p-3">
                  <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
                    <div>
                      <h2 className="mb-3 text-xs font-bold uppercase tracking-wide text-gray-900">Traceability Health Distribution</h2>
                      <div className="flex h-2 overflow-hidden rounded-full bg-gray-100">
                        {([
                          ["fully_traced", "bg-emerald-500"],
                          ["partial_trace", "bg-amber-500"],
                          ["missing_links", "bg-orange-500"],
                          ["broken_stale", "bg-red-500"],
                          ["not_traced", "bg-gray-400"],
                        ] as const).map(([health, color]) => {
                          const count = traceabilityRows.filter((row) => row.health === health).length;
                          const pct = traceabilityRows.length ? Math.max(2, Math.round((count / traceabilityRows.length) * 100)) : 0;
                          return <div key={health} className={color} style={{ width: `${pct}%` }} />;
                        })}
                      </div>
                      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5">
                        {([
                          ["fully_traced", "Fully Traced", "bg-emerald-500"],
                          ["partial_trace", "Partial Trace", "bg-amber-500"],
                          ["missing_links", "Missing Links", "bg-orange-500"],
                          ["broken_stale", "Broken / Stale", "bg-red-500"],
                          ["not_traced", "Not Traced", "bg-gray-400"],
                        ] as const).map(([health, label, dot]) => {
                          const count = traceabilityRows.filter((row) => row.health === health).length;
                          const pct = traceabilityRows.length ? ((count / traceabilityRows.length) * 100).toFixed(1) : "0.0";
                          return (
                            <div key={health} className="text-[11px] font-semibold text-gray-600">
                              <div className="flex items-center gap-2"><span className={cn("h-2 w-2 rounded-full", dot)} />{label}</div>
                              <div className="mt-1 pl-4 text-gray-500">{count} ({pct}%)</div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                    <div className="border-t border-gray-100 pt-3 xl:border-l xl:border-t-0 xl:pl-6 xl:pt-0">
                      <div className="text-[11px] font-semibold text-gray-500">Coverage Progress</div>
                      <div className="mt-2 text-2xl font-bold text-gray-900">
                        {traceabilityRows.length ? Math.round((traceabilityRows.filter((row) => row.health === "fully_traced").length / traceabilityRows.length) * 100) : 0}%
                      </div>
                      <div className="mt-1 text-[10px] font-semibold text-gray-400">Overall Traceability Score</div>
                      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-gray-100">
                        <div className="h-full rounded-full bg-emerald-500" style={{ width: `${traceabilityRows.length ? Math.round((traceabilityRows.filter((row) => row.health === "fully_traced").length / traceabilityRows.length) * 100) : 0}%` }} />
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex flex-wrap gap-1 rounded-xl border border-gray-200 bg-white p-1 shadow-sm">
                  {([
                    ["all", "All Requirements"],
                    ["fully_traced", "Fully Traced"],
                    ["partial_trace", "Partial Trace"],
                    ["missing_links", "Missing Links"],
                    ["broken_stale", "Broken / Stale"],
                  ] as const).map(([health, label]) => (
                    <button
                      key={health}
                      onClick={() => setTraceabilityFilter(health)}
                      className={cn("rounded-lg px-3 py-1.5 text-[11px] font-bold transition-all", traceabilityFilter === health ? "bg-gray-900 text-white" : "text-gray-500 hover:text-gray-900")}
                    >
                      {label}
                      <span className="ml-1 rounded-full bg-gray-100 px-1.5 py-0.5 text-[9px] text-gray-600">
                        {health === "all" ? traceabilityRows.length : traceabilityRows.filter((row) => row.health === health).length}
                      </span>
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={loadTraceabilityMatrix} className="h-8 bg-white text-xs font-bold">
                    <RefreshCw className={cn("mr-1 h-3.5 w-3.5", matrixLoading && "animate-spin")} />Rebuild Index
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => selectedProject && handleExport("matrix-excel")} className="h-8 bg-white text-xs font-bold">
                    <Download className="mr-1 h-3.5 w-3.5" />Export
                  </Button>
                </div>
              </div>

              <div className="flex flex-col gap-2 rounded-xl border border-gray-200 bg-white p-3 shadow-sm xl:flex-row xl:items-center">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                  <input value={traceabilitySearch} onChange={(event) => setTraceabilitySearch(event.target.value)} placeholder="Search by REQ ID, title, PPM ID, source..." className="h-9 w-full rounded-lg border border-gray-200 bg-white pl-9 pr-3 text-xs font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-app-brand-200" />
                </div>
                {["Domain", "Journey", "Application", "Traceability Health", "More Filters"].map((label) => (
                  <button key={label} className="flex h-9 min-w-[130px] items-center justify-between rounded-lg border border-gray-200 px-3 text-xs font-bold text-gray-500">
                    {label}<ChevronDown className="h-3.5 w-3.5" />
                  </button>
                ))}
                <Button variant="outline" size="sm" className="h-9 bg-white text-xs font-bold"><Filter className="mr-1 h-3.5 w-3.5" />Filters</Button>
              </div>

              <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
                <table className="min-w-[1320px] w-full border-collapse text-left text-xs">
                  <thead className="border-b border-gray-200 bg-gray-50/70 text-[10px] font-bold uppercase tracking-wider text-gray-400">
                    <tr>
                      <th className="px-3 py-2.5">Req ID</th>
                      <th className="px-3 py-2.5">PPM ID</th>
                      <th className="px-3 py-2.5">Title</th>
                      <th className="px-3 py-2.5">Analysis Status</th>
                      <th className="px-3 py-2.5">Scenarios</th>
                      <th className="px-3 py-2.5">Test Cases</th>
                      <th className="px-3 py-2.5">Automation</th>
                      <th className="px-3 py-2.5">Execution / Evidence</th>
                      <th className="px-3 py-2.5">Defects</th>
                      <th className="px-3 py-2.5">Traceability Health</th>
                      <th className="px-3 py-2.5">Updated At</th>
                      <th className="px-3 py-2.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 font-medium text-gray-600">
                    {matrixLoading ? (
                      <tr><td colSpan={12} className="px-4 py-16 text-center font-semibold text-gray-400"><Loader2 className="mr-2 inline h-4 w-4 animate-spin text-[#B71920]" />Loading traceability matrix...</td></tr>
                    ) : filteredTraceabilityRows.length === 0 ? (
                      <tr><td colSpan={12} className="px-4 py-16 text-center font-semibold text-gray-400">No traceability rows match the current filters.</td></tr>
                    ) : filteredTraceabilityRows.map((row) => (
                      <tr
                        key={row.requirement.id}
                        onClick={() => {
                          handleOpenReqDetail(row.requirement);
                          setDrawerTab("traceability");
                          handleLoadTraceChain(row.requirement);
                        }}
                        className={cn("cursor-pointer transition-colors hover:bg-gray-50/70", row.requirement.id === selectedReq?.id && "bg-[#B71920]/5 outline outline-1 outline-[#B71920]/60")}
                      >
                        <td className="whitespace-nowrap px-3 py-3 font-mono text-[11px] font-bold text-[#B71920]">{row.requirement.requirement_id}</td>
                        <td className="whitespace-nowrap px-3 py-3 font-mono text-[11px] font-bold text-gray-600">{row.ppmId}</td>
                        <td className="max-w-[260px] px-3 py-3 font-bold text-gray-800"><div className="line-clamp-2">{row.requirement.title}</div></td>
                        <td className="px-3 py-3"><Badge variant={analysisBadgeVariant(row.analysisStatus)}>{analysisLabel(row.analysisStatus)}</Badge></td>
                        <td className="px-3 py-3"><CoverageBar linked={row.scenarioLinked} total={row.scenarioTotal} health={row.health} /></td>
                        <td className="px-3 py-3"><CoverageBar linked={row.testCaseLinked} total={row.testCaseTotal} health={row.health} /></td>
                        <td className="px-3 py-3"><CoverageBar linked={row.automationLinked} total={row.automationTotal} health={row.health} /></td>
                        <td className="px-3 py-3"><CoverageBar linked={row.evidenceLinked} total={row.evidenceTotal} health={row.health} /></td>
                        <td className="px-3 py-3"><span className={cn("inline-flex items-center gap-1 font-bold", row.defectCount > 0 ? "text-red-600" : "text-emerald-600")}><span className="h-2 w-2 rounded-full bg-current" />{row.defectCount}</span></td>
                        <td className="px-3 py-3"><Badge variant={traceHealthBadgeVariant(row.health)}>{traceHealthLabel(row.health)}</Badge></td>
                        <td className="whitespace-nowrap px-3 py-3 text-gray-500">{row.updatedAt ? new Date(row.updatedAt).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "-"}</td>
                        <td className="px-3 py-3 text-right"><Button variant="outline" size="sm" className="h-7 px-2 text-[10px] font-bold">...</Button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="flex items-center justify-between border-t border-gray-100 px-4 py-3 text-[11px] font-semibold text-gray-500">
                  <span>Showing 1 to {Math.min(filteredTraceabilityRows.length, traceabilityRows.length)} of {traceabilityRows.length} requirements</span>
                  <div className="flex items-center gap-1"><Button variant="outline" size="sm" className="h-7 w-7 p-0 bg-white">1</Button><span className="px-2">2</span><span className="px-2">3</span><span className="px-2">...</span></div>
                </div>
              </div>
            </div>
          )}

          {workspaceView === "analysis" && (
            <div className="space-y-4">
              <Card className="overflow-hidden border-gray-200 shadow-sm">
                <CardContent className="p-3">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <h2 className="text-xs font-bold uppercase tracking-wide text-gray-900">Analysis Workflow</h2>
                      <p className="mt-0.5 text-[10px] font-semibold text-gray-400">Grounded analysis from intake-ready requirements through clarification and traceability readiness</p>
                    </div>
                    <Button variant="ai" size="sm" disabled={agentRunning || analysisRows.length === 0} onClick={() => runQualityAgent(analysisRows.map((row) => row.requirement.id))} className="h-9 gap-2 px-3 text-xs font-bold">
                      <Sparkles className="h-4 w-4" />Run Analysis
                    </Button>
                  </div>
                  <div className="grid gap-1.5 md:grid-cols-3 xl:grid-cols-6">
                    {([
                      ["Intake Ready", analysisRows.length, "bg-emerald-50 border-emerald-100 text-emerald-600", FileText],
                      ["Analyzing", analysisRows.filter((row) => row.status === "queued" || row.status === "analyzing").length, "bg-app-brand-75 border-app-brand-100 text-app-brand-600", RefreshCw],
                      ["Clarification / Revision", analysisRows.filter((row) => row.status === "needs_clarification" || row.status === "needs_revision").length, "bg-amber-50 border-amber-100 text-amber-600", AlertTriangle],
                      ["Analyzed", analysisRows.filter((row) => row.status === "analyzed").length, "bg-purple-50 border-purple-100 text-purple-600", CheckCircle],
                      ["Ready for Traceability", analysisRows.filter((row) => row.status === "analyzed" && row.blockers.length === 0).length, "bg-cyan-50 border-cyan-100 text-cyan-600", ShieldCheck],
                      ["Blocked / Failed", analysisRows.filter((row) => row.status === "blocked" || row.status === "failed").length, "bg-red-50 border-red-100 text-red-600", XCircle],
                    ] as const).map(([label, value, tone, StepIcon], index, items) => (
                      <div key={label} className="flex items-center gap-1.5">
                        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1.5">
                          <div className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-full border", tone)}>
                            <StepIcon className="h-3.5 w-3.5" />
                          </div>
                          <div className="min-w-0">
                            <div className="truncate text-[10px] font-bold text-gray-700">{label}</div>
                            <div className="text-[11px] font-bold text-gray-900">{value}</div>
                          </div>
                        </div>
                        {index < items.length - 1 && <div className="hidden h-px w-6 border-t border-dashed border-gray-300 xl:block" />}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <div className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-white p-3 shadow-sm xl:flex-row xl:items-center">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                  <input value={analysisSearch} onChange={(event) => setAnalysisSearch(event.target.value)} placeholder="Search by requirement ID, PPM ID, title, source..." className="h-9 w-full rounded-lg border border-gray-200 bg-white pl-9 pr-3 text-xs font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-app-brand-200" />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {(["all", "not_analyzed", "needs_clarification", "needs_revision", "analyzed", "blocked", "stale_source"] as const).map((status) => (
                    <button key={status} onClick={() => setAnalysisFilter(status)} className={cn("rounded-lg px-3 py-2 text-[10px] font-bold transition-all", analysisFilter === status ? "bg-gray-900 text-white" : "bg-gray-50 text-gray-500 hover:text-gray-900")}>
                      {status === "all" ? "All" : analysisLabel(status)}
                    </button>
                  ))}
                </div>
              </div>

              <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
                <table className="min-w-[1180px] w-full border-collapse text-left text-xs">
                  <thead className="border-b border-gray-200 bg-gray-50/70 text-[10px] font-bold uppercase tracking-wider text-gray-400">
                    <tr>
                      <th className="w-8 px-3 py-2.5"><input type="checkbox" className="rounded border-gray-300" aria-label="Select all requirements" /></th>
                      <th className="px-3 py-2.5">Req ID</th>
                      <th className="px-3 py-2.5">PPM ID</th>
                      <th className="px-3 py-2.5">Title</th>
                      <th className="px-3 py-2.5">Source</th>
                      <th className="px-3 py-2.5">Analysis Status</th>
                      <th className="px-3 py-2.5">Quality Score</th>
                      <th className="px-3 py-2.5">Ambiguity</th>
                      <th className="px-3 py-2.5">Missing Info</th>
                      <th className="px-3 py-2.5">Duplicates</th>
                      <th className="px-3 py-2.5">Risk</th>
                      <th className="px-3 py-2.5">Updated At</th>
                      <th className="px-3 py-2.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 font-medium text-gray-600">
                    {loading ? (
                      <tr><td colSpan={13} className="px-4 py-16 text-center font-semibold text-gray-400"><Loader2 className="mr-2 inline h-4 w-4 animate-spin text-[#B71920]" />Loading requirement analysis...</td></tr>
                    ) : filteredAnalysisRows.length === 0 ? (
                      <tr><td colSpan={13} className="px-4 py-16 text-center font-semibold text-gray-400">No requirements match the current analysis filter.</td></tr>
                    ) : filteredAnalysisRows.map((row) => {
                      const isReadyForTraceability = row.status === "analyzed" && row.blockers.length === 0;
                      return (
                        <tr key={row.requirement.id} onClick={() => handleOpenReqDetail(row.requirement)} className="cursor-pointer transition-colors hover:bg-gray-50/70">
                          <td className="px-3 py-3"><input type="checkbox" className="rounded border-gray-300" aria-label={`Select ${row.requirement.requirement_id}`} onClick={(event) => event.stopPropagation()} /></td>
                          <td className="whitespace-nowrap px-3 py-3 font-mono text-[11px] font-bold text-[#B71920]">{row.requirement.requirement_id}</td>
                          <td className="whitespace-nowrap px-3 py-3 font-mono text-[11px] font-bold text-gray-700">{row.ppmId}</td>
                          <td className="max-w-[260px] px-3 py-3 font-bold text-gray-800"><div className="line-clamp-2">{row.requirement.title}</div></td>
                          <td className="px-3 py-3"><Badge variant="outline" className="max-w-[150px] truncate">{row.sourceLabel}</Badge></td>
                          <td className="min-w-[160px] px-3 py-3">
                            <Badge variant={analysisBadgeVariant(row.status)}>{analysisLabel(row.status)}</Badge>
                            <div className="mt-1 flex items-center gap-2"><div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-100"><div className={cn("h-full rounded-full", row.status === "analyzed" ? "bg-emerald-500" : row.status === "needs_clarification" ? "bg-amber-500" : row.status === "blocked" || row.status === "failed" ? "bg-red-500" : "bg-app-brand-500")} style={{ width: `${row.progress}%` }} /></div><span className="text-[10px] font-bold text-gray-400">{row.progress}%</span></div>
                          </td>
                          <td className="px-3 py-3">{row.qualityScore === null ? <span className="text-gray-400">-</span> : <span className={cn("rounded-full border px-2 py-1 text-[10px] font-bold", row.qualityScore >= 80 ? "border-emerald-200 bg-emerald-50 text-emerald-700" : row.qualityScore >= 50 ? "border-amber-200 bg-amber-50 text-amber-700" : "border-red-200 bg-red-50 text-red-700")}>{row.qualityScore}/100</span>}</td>
                          <td className="px-3 py-3"><span className={cn("font-bold", row.ambiguityCount ? "text-red-600" : "text-gray-400")}>{row.ambiguityCount}</span></td>
                          <td className="px-3 py-3"><span className={cn("font-bold", row.missingInfoCount ? "text-red-600" : "text-gray-400")}>{row.missingInfoCount}</span></td>
                          <td className="px-3 py-3"><span className={cn("font-bold", row.duplicateCount ? "text-amber-600" : "text-gray-400")}>{row.duplicateCount}</span></td>
                          <td className="px-3 py-3"><Badge variant={riskBadgeVariant(row.riskLevel)}>{row.riskLevel}</Badge></td>
                          <td className="whitespace-nowrap px-3 py-3 text-gray-500">{row.requirement.updated_at ? new Date(row.requirement.updated_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "-"}</td>
                          <td className="px-3 py-3 text-right" onClick={(event) => event.stopPropagation()}><Button size="sm" variant={isReadyForTraceability ? "default" : "outline"} disabled={transitioning} onClick={() => isReadyForTraceability ? handleRequirementTransition(row.requirement, "send_to_traceability", "traceability") : handleOpenReqDetail(row.requirement)} className="h-7 whitespace-nowrap px-2.5 text-[10px] font-bold" title={!isReadyForTraceability ? "Open the requirement to review and resolve its blockers" : "All analysis gates passed; send to Traceability"}>{isReadyForTraceability ? "Send to Traceability" : "Review"}</Button></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="grid gap-3 xl:grid-cols-3">
                <Card className="border-gray-200 shadow-sm">
                  <CardContent className="p-3">
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="text-xs font-bold text-gray-900">Analysis Quality Overview</h3>
                      <button onClick={() => setAnalysisOverviewDetail((value) => value === "quality" ? null : "quality")} className="text-[10px] font-bold text-[#B71920]">{analysisOverviewDetail === "quality" ? "Hide details" : "View details"}</button>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="relative flex h-24 w-24 shrink-0 items-center justify-center rounded-full bg-gradient-to-r from-emerald-500 via-amber-400 to-purple-400 p-2">
                        <div className="flex h-full w-full flex-col items-center justify-center rounded-full bg-white">
                          <span className="text-xl font-bold text-gray-900">{analysisQualityAverage ?? "—"}</span>
                          <span className="text-[9px] font-bold text-gray-400">/100</span>
                        </div>
                      </div>
                      <div className="min-w-0 flex-1 space-y-2 text-[11px] font-semibold text-gray-600">
                        <div className="flex justify-between gap-3"><span><span className="mr-2 inline-block h-2 w-2 rounded-full bg-emerald-500" />High Quality</span><span>{scoredAnalysisRows.filter((row) => (row.qualityScore as number) >= 80).length}</span></div>
                        <div className="flex justify-between gap-3"><span><span className="mr-2 inline-block h-2 w-2 rounded-full bg-amber-500" />Medium Quality</span><span>{scoredAnalysisRows.filter((row) => (row.qualityScore as number) >= 50 && (row.qualityScore as number) < 80).length}</span></div>
                        <div className="flex justify-between gap-3"><span><span className="mr-2 inline-block h-2 w-2 rounded-full bg-red-500" />Low Quality</span><span>{scoredAnalysisRows.filter((row) => (row.qualityScore as number) < 50).length}</span></div>
                        <div className="flex justify-between gap-3 text-gray-400"><span>Not scored</span><span>{analysisRows.length - scoredAnalysisRows.length}</span></div>
                      </div>
                    </div>
                    {analysisOverviewDetail === "quality" && (
                      <div className="mt-3 max-h-44 space-y-1.5 overflow-y-auto border-t border-gray-100 pt-3 text-[10px] font-semibold text-gray-600">
                        {analysisRows.map((row) => (
                          <button key={row.requirement.id} onClick={() => handleOpenReqDetail(row.requirement)} className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left hover:bg-gray-50">
                            <span className="min-w-0 truncate"><span className="mr-2 font-mono font-bold text-[#B71920]">{row.requirement.requirement_id}</span>{row.requirement.title}</span>
                            <span className="shrink-0 font-bold text-gray-800">{row.qualityScore === null ? "Not scored" : `${row.qualityScore}/100`}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card className="border-gray-200 shadow-sm">
                  <CardContent className="p-3">
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="text-xs font-bold text-gray-900">Top Issues</h3>
                      <button onClick={() => setAnalysisOverviewDetail((value) => value === "issues" ? null : "issues")} className="text-[10px] font-bold text-[#B71920]">{analysisOverviewDetail === "issues" ? "Hide all" : "View all"}</button>
                    </div>
                    <div className="space-y-2 text-[11px] font-semibold text-gray-600">
                      <div className="flex justify-between gap-3"><span className="truncate">Missing Acceptance Criteria</span><span className="font-bold text-gray-900">{analysisRows.filter((row) => !row.requirement.acceptance_criteria?.length).length}</span></div>
                      <div className="flex justify-between gap-3"><span className="truncate">Unclear Business Rules</span><span className="font-bold text-gray-900">{analysisRows.filter((row) => !row.requirement.business_rules?.length).length}</span></div>
                      <div className="flex justify-between gap-3"><span className="truncate">Ambiguous Data Definitions</span><span className="font-bold text-gray-900">{analysisRows.filter((row) => row.ambiguityCount > 0).length}</span></div>
                      <div className="flex justify-between gap-3"><span className="truncate">Incomplete Taxonomy</span><span className="font-bold text-gray-900">{analysisRows.filter((row) => !row.taxonomyReady).length}</span></div>
                      <div className="flex justify-between gap-3"><span className="truncate">Conflicting Requirements</span><span className="font-bold text-gray-900">{analysisRows.filter((row) => row.conflictCount > 0 || row.duplicateCount > 0).length}</span></div>
                    </div>
                    {analysisOverviewDetail === "issues" && (
                      <div className="mt-3 max-h-44 space-y-1.5 overflow-y-auto border-t border-gray-100 pt-3 text-[10px] font-semibold text-gray-600">
                        {analysisRowsWithIssues.map((row) => (
                          <button key={row.requirement.id} onClick={() => handleOpenReqDetail(row.requirement)} className="block w-full rounded-md px-2 py-1.5 text-left hover:bg-gray-50">
                            <div className="truncate font-bold text-gray-800">{row.requirement.requirement_id} · {row.requirement.title}</div>
                            <div className="mt-0.5 truncate text-gray-400">{row.blockers.join(" · ")}</div>
                          </button>
                        ))}
                        {analysisRowsWithIssues.length === 0 && <div className="text-gray-400">No analysis issues are currently recorded.</div>}
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card className="border-gray-200 shadow-sm">
                  <CardContent className="p-3">
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="text-xs font-bold text-gray-900">Domains Distribution</h3>
                      <button onClick={() => setAnalysisOverviewDetail((value) => value === "domains" ? null : "domains")} className="text-[10px] font-bold text-[#B71920]">{analysisOverviewDetail === "domains" ? "Hide details" : "View details"}</button>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="relative flex h-24 w-24 shrink-0 items-center justify-center rounded-full p-3" style={{ background: `conic-gradient(#2563eb 0 ${analysisRows.length ? Math.round((classifiedAnalysisCount / analysisRows.length) * 100) : 0}%, #9CA3AF 0 100%)` }}>
                        <div className="flex h-full w-full flex-col items-center justify-center rounded-full bg-white">
                          <span className="text-lg font-bold text-gray-900">{analysisRows.length}</span>
                          <span className="text-[9px] font-bold text-gray-400">Total</span>
                        </div>
                      </div>
                      <div className="min-w-0 flex-1 space-y-2 text-[11px] font-semibold text-gray-600">
                        {analysisDomainDistribution.slice(0, 5).map(([domain, count]) => (
                          <div key={domain} className="flex justify-between gap-3"><span className="truncate">{domain}</span><span className="font-bold text-gray-900">{count}</span></div>
                        ))}
                      </div>
                    </div>
                    {analysisOverviewDetail === "domains" && (
                      <div className="mt-3 space-y-1.5 border-t border-gray-100 pt-3 text-[10px] font-semibold text-gray-600">
                        {analysisDomainDistribution.map(([domain, count]) => (
                          <div key={domain} className="flex items-center justify-between gap-3">
                            <span className="truncate">{domain}</span>
                            <span className="font-bold text-gray-800">{count} ({analysisRows.length ? ((count / analysisRows.length) * 100).toFixed(1) : "0.0"}%)</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          )}

          <Card className={cn("overflow-hidden border-gray-200 shadow-sm", workspaceView !== "intake" && "hidden")}>
            <div className="flex flex-col gap-3 border-b border-gray-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Layers3 className="h-4 w-4 text-[#B71920]" />
                  <h2 className="text-sm font-bold text-gray-900">Intake Source Queue</h2>
                  <Badge variant="info">{intakeSources.length}</Badge>
                </div>
                <p className="mt-1 text-[10px] font-semibold text-gray-400">Validation, processing ownership, provenance and the next governed action for every source</p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse text-left text-xs">
                <thead className="border-b border-gray-200 bg-gray-50/70 text-[10px] font-bold uppercase tracking-wider text-gray-400">
                  <tr>
                    <th className="px-4 py-2.5">Source</th><th className="px-4 py-2.5">Type</th><th className="px-4 py-2.5">Owner</th><th className="px-4 py-2.5">Intake Status</th><th className="px-4 py-2.5">Progress</th><th className="px-4 py-2.5">Extracted</th><th className="px-4 py-2.5">Validation</th><th className="px-4 py-2.5 text-right">Next Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 font-medium text-gray-600">
                  {loading ? (
                    <tr><td colSpan={8} className="px-4 py-10 text-center text-gray-400"><Loader2 className="mr-2 inline h-4 w-4 animate-spin text-[#B71920]" />Loading intake sources...</td></tr>
                  ) : intakeSources.length === 0 ? (
                    <tr><td colSpan={8} className="px-4 py-10 text-center text-gray-400">No sources yet. Add a document, URL, repository, Jira source, pasted text or API specification.</td></tr>
                  ) : intakeSources.map((source) => (
                    <tr key={source.id} onClick={() => setSelectedSource(source)} className="cursor-pointer transition-colors hover:bg-gray-50/70">
                      <td className="max-w-[240px] truncate px-4 py-3 font-bold text-gray-800">{source.name}</td>
                      <td className="px-4 py-3"><Badge variant="outline">{source.sourceType}</Badge></td>
                      <td className="whitespace-nowrap px-4 py-3">{source.owner}</td>
                      <td className="px-4 py-3"><Badge variant={source.status === "blocked" ? "destructive" : source.status === "processing" ? "purple" : source.status === "completed" ? "success" : "info"} className="capitalize">{source.status}</Badge></td>
                      <td className="min-w-[130px] px-4 py-3"><div className="flex items-center gap-2"><div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-100"><div className={cn("h-full rounded-full", source.status === "blocked" ? "bg-red-500" : source.status === "processing" ? "bg-purple-500" : "bg-emerald-500")} style={{ width: `${source.progress}%` }} /></div><span className="text-[10px] font-bold text-gray-500">{source.progress}%</span></div></td>
                      <td className="px-4 py-3 font-bold text-gray-800">{source.extractedCount}</td>
                      <td className="px-4 py-3">{source.validationIssues.length ? <span className="font-semibold text-red-600">{source.validationIssues.length} issue{source.validationIssues.length > 1 ? "s" : ""}</span> : <span className="font-semibold text-emerald-600">Passed</span>}</td>
                      <td className="px-4 py-3 text-right" onClick={(event) => event.stopPropagation()}>
                        <Button size="sm" variant={source.nextAction === "Run AI Intake" || source.nextAction === "Retry" ? "default" : "outline"} disabled={agentRunning || transitioning || source.nextAction === "Processing" || (source.nextAction === "Send to Analysis" && (source.validationIssues.length > 0 || source.requirementIds.length === 0))} onClick={() => source.documentId && (source.nextAction === "Run AI Intake" || source.nextAction === "Retry") ? runIntakeAgent(source.documentId) : source.nextAction === "Send to Analysis" ? sendSourceToAnalysis(source) : setSelectedSource(source)} className="h-7 whitespace-nowrap px-2.5 text-[10px] font-bold" title={source.validationIssues.length ? "Resolve validation blockers before continuing" : undefined}>
                          {source.nextAction === "Processing" && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}{source.nextAction}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <div className={cn("flex flex-wrap gap-1 rounded-xl border border-gray-200 bg-white p-1 w-fit", workspaceView !== "intake" && "hidden")}>
            {(["requirements", "documents", "url", "github", "jira", "paste"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  "inline-flex items-center rounded-lg px-4 py-1.5 text-xs font-bold capitalize transition-all",
                  t === "requirements"
                    ? "bg-gradient-to-r from-cyan-500 to-violet-500 text-white shadow-sm hover:opacity-95"
                    : tab === t
                      ? "bg-gray-900 text-gray-50 shadow-sm"
                      : "text-gray-500 hover:text-gray-900",
                  tab === t && t === "requirements" && "ring-2 ring-violet-200 ring-offset-1"
                )}
              >
                {t === "requirements" && <Sparkles className="mr-1.5 h-3.5 w-3.5" />}
                {t === "documents" ? "Documents / UI Input"
                  : t === "url" ? "URL Input"
                  : t === "github" ? "GitHub / Local Repository"
                  : t === "paste" ? "Add Missing Requirement"
                  : t === "requirements" ? "Extracted Requirements"
                  : "Jira"}
                {t === "requirements" && requirements.length > 0 && (
                  <span className="ml-1.5 rounded-full bg-white/20 px-1.5 py-0.5 text-[9px] font-bold text-white">{requirements.length}</span>
                )}
                {t === "documents" && documents.length > 0 && (
                  <span className="ml-1.5 rounded-full bg-gray-100 px-1.5 py-0.5 text-[9px] font-bold text-gray-700">{documents.length}</span>
                )}
                {t === "jira" && jiraConnections.length > 0 && (
                  <span className="ml-1.5 rounded-full bg-gray-100 px-1.5 py-0.5 text-[9px] font-bold text-gray-700">{jiraConnections.length}</span>
                )}
              </button>
            ))}
          </div>

          {/* ── Requirements Tab ──────────────────────────────────────────────────── */}
          {workspaceView === "intake" && tab === "requirements" && (
            <div className="space-y-4">
              {/* Filter Buttons & AI Action */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex flex-wrap gap-1.5 rounded-lg border border-gray-200 bg-white p-1">
                  {["all", "draft"].map((s) => (
                    <button
                      key={s}
                      onClick={() => setFilterStatus(s)}
                      className={cn(
                        "rounded-md px-3 py-1 text-xs font-semibold capitalize transition-all",
                        filterStatus === s
                          ? "bg-gray-900 text-gray-50 shadow-sm"
                          : "text-gray-500 hover:text-gray-900"
                      )}
                    >
                      {s === "all" ? "All Status" : s.replace(/_/g, " ")}
                    </button>
                  ))}
                </div>

              </div>

              {/* Requirements Table */}
              <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
                <table className="min-w-full text-left border-collapse text-xs select-none">
                  <thead className="bg-gray-50/70 border-b border-gray-200 text-[10px] font-bold uppercase tracking-wider text-gray-400">
                    <tr>
                      <th className="px-4 py-2.5">Req ID</th>
                      <th className="px-4 py-2.5">Title</th>
                      <th className="px-4 py-2.5">Status</th>
                      <th className="px-4 py-2.5">Lifecycle Stage</th>
                      <th className="px-4 py-2.5">Quality Verdict</th>
                      <th className="px-4 py-2.5">Created By</th>
                      <th className="px-4 py-2.5">Created At</th>
                      <th className="px-4 py-2.5">Modified By</th>
                      <th className="px-4 py-2.5">Modified At</th>
                      <th className="px-4 py-2.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 text-gray-600 font-medium">
                    {loading ? (
                      <tr>
                        <td colSpan={10} className="px-4 py-16 text-center text-gray-400 font-semibold">
                          <Loader2 className="inline mr-2 h-4 w-4 animate-spin text-[#B71920]" />
                          Loading requirements library...
                        </td>
                      </tr>
                    ) : filteredRequirements.length === 0 ? (
                      <tr>
                        <td colSpan={10} className="px-4 py-16 text-center text-gray-400 font-semibold">
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
                              "hover:bg-gray-50/50 cursor-pointer transition-colors group",
                              isSelected && "bg-[#B71920]/5"
                            )}
                          >
                            <td className="px-4 py-2.5 font-mono text-[11px] font-bold text-[#B71920]">{req.requirement_id}</td>
                            <td className="px-4 py-2.5 font-bold text-gray-800 text-xs truncate max-w-sm">{req.title}</td>
                            <td className="px-4 py-2.5">
                              <Badge variant={getStatusVariant(req.status)} className="capitalize">
                                {req.status.replace(/_/g, " ")}
                              </Badge>
                            </td>
                            <td className="px-4 py-2.5">
                              <Badge variant={getRequirementWorkflowStageVariant(req)} className="whitespace-nowrap">
                                {getRequirementWorkflowStageLabel(req)}
                              </Badge>
                            </td>
                            <td className="px-4 py-2.5">
                              {quality ? (
                                <QualityBadge score={quality.overall_score} verdict={quality.verdict} />
                              ) : (
                                <span className="text-gray-400 font-semibold">-</span>
                              )}
                            </td>
                            <td className="px-4 py-2.5 text-gray-700 font-semibold whitespace-nowrap">
                              {resolveUser(req.created_by)}
                            </td>
                            <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap">
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
                            <td className="px-4 py-2.5 text-gray-700 font-semibold whitespace-nowrap">
                              {resolveUser(req.updated_by)}
                            </td>
                            <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap">
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
                                className="rounded-md p-1.5 text-gray-400 opacity-0 group-hover:opacity-100 hover:bg-red-50 hover:text-red-600 transition-all shrink-0"
                                title="Delete requirement"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleOpenReqDetail(req)}
                                className="h-7 px-3 text-xs border-gray-200 bg-white"
                              >
                                Details
                                <ChevronRight className="h-3 w-3 text-gray-400" />
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
          {workspaceView === "intake" && tab === "documents" && (
            <div className="space-y-4">
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFileUpload(f); }}
                className={cn(
                  "relative rounded-2xl border-2 border-dashed p-10 text-center transition-all cursor-pointer bg-white",
                  dragOver ? "border-[#B71920] bg-[#B71920]/5 shadow-sm" : "border-gray-250 hover:border-gray-350"
                )}
              >
                <input id="file-upload" type="file" className="sr-only"
                  accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.png,.jpg,.jpeg,.webp"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileUpload(f); }} />
                <label htmlFor="file-upload" className="cursor-pointer">
                  {uploading ? (
                    <Loader2 className="mx-auto h-9 w-9 animate-spin text-[#B71920] mb-3 shrink-0" />
                  ) : (
                    <Upload className="mx-auto h-9 w-9 text-gray-400 mb-3" />
                  )}
                  <p className="font-bold text-xs text-gray-700">{uploading ? "Uploading and extracting text evidence..." : "Drop QA documentation or UI screenshots here, or click to browse files"}</p>
                  <p className="text-[10px] text-gray-400 font-semibold mt-1">PDF, DOCX, TXT, MD, CSV, XLSX · UI screenshots: PNG, JPG, WebP · up to 25 MB</p>
                </label>
              </div>

              {documents.length > 0 ? (
                <div className="rounded-xl border divide-y overflow-hidden bg-white shadow-sm border-gray-200">
                  {documents.map((doc) => (
                    <div key={doc.id} className="flex items-center gap-4 px-4 py-3 hover:bg-gray-50/50 group">
                      <FileText className="h-5 w-5 text-app-brand-500 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-bold text-gray-800 truncate">{doc.original_filename}</p>
                        <p className="text-[10px] text-gray-400 font-bold">
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
                        <span className="text-[10px] text-gray-400 font-bold animate-pulse">Processing document text...</span>
                      )}
                      
                      <button
                        onClick={() => setDeletingDoc(doc)}
                        className="rounded-md p-1.5 text-gray-405 opacity-0 group-hover:opacity-100 hover:bg-red-50 hover:text-red-650 transition-all shrink-0"
                        title="Delete document"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : !uploading ? (
                <p className="text-center text-xs text-gray-400 font-bold py-8 border border-dashed rounded-xl bg-white">No documents uploaded yet.</p>
              ) : null}
            </div>
          )}

          {/* ── URL Input Tab (GAP-2) ─────────────────────────────────────────────── */}
          {workspaceView === "intake" && tab === "url" && (
            <div className="space-y-4">
              <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-4">
                <div className="flex items-center gap-2">
                  <Globe className="h-5 w-5 text-[#B71920]" />
                  <div>
                    <h4 className="text-xs font-bold text-gray-800">Analyze Portal URL</h4>
                    <p className="text-[10px] text-gray-400 font-semibold">Render a live page, detect forms, fields, validations and user journeys, and generate requirements automatically</p>
                  </div>
                </div>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    type="url"
                    value={portalUrl}
                    onChange={(e) => setPortalUrl(e.target.value)}
                    placeholder="https://portal.example.com/login"
                    className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-app-brand-300"
                  />
                  <select
                    value={urlCrawlDepth}
                    onChange={(e) => setUrlCrawlDepth(Number(e.target.value))}
                    className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-app-brand-300"
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
                <p className="text-[10px] text-gray-400 font-semibold">Public/reachable pages only · same-origin crawling · max 5 pages · internal/private addresses are blocked unless the host is explicitly allowed</p>
                {/* Registering an application is a prerequisite here and nowhere
                    says so: the derivation step resolves navigation targets
                    against the project's configured base URLs, so with an empty
                    registry it can only report destinations as unknown. Shown
                    only once the registry has actually loaded and come back
                    empty — never while it is still unknown. */}
                {registeredApplications !== null && registeredApplications.length === 0 && (
                  <div className="mt-2 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
                    <p className="text-[10px] font-semibold text-amber-800">
                      No application is registered for this project. Analysis will still run, but navigation
                      destinations cannot be resolved against a known base URL and will be reported as missing.{" "}
                      <Link href={applicationsHref("registry", selectedProject)} className="font-bold underline">
                        Register an application
                      </Link>
                      .
                    </p>
                  </div>
                )}
              </div>

              {/* Requirements generated from URLs */}
              {(() => {
                const urlReqs = requirements.filter((r) => r.source === "portal_url");
                return urlReqs.length > 0 ? (
                  <div className="rounded-xl border divide-y overflow-hidden bg-white shadow-sm border-gray-200">
                    <div className="px-4 py-2.5 bg-gray-50/60">
                      <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Requirements generated from URLs ({urlReqs.length})</p>
                    </div>
                    {urlReqs.map((req) => (
                      <div key={req.id} className="flex items-center gap-4 px-4 py-3 hover:bg-gray-50/50 cursor-pointer" onClick={() => handleOpenReqDetail(req)}>
                        <Globe className="h-4 w-4 text-[#B71920] shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-bold text-gray-800 truncate">{req.title}</p>
                          <p className="text-[10px] text-gray-400 font-bold truncate">
                            {req.requirement_id}
                            {(req.metadata_ as Record<string, any> | undefined)?.source_url ? ` · ${(req.metadata_ as Record<string, any>).source_url}` : ""}
                          </p>
                        </div>
                        <Badge variant={getStatusVariant(req.status)} className="capitalize">{req.status.replace(/_/g, " ")}</Badge>
                        <ChevronRight className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-center text-xs text-gray-400 font-bold py-8 border border-dashed rounded-xl bg-white">No URL-based requirements yet. Analyze a portal URL above to generate them.</p>
                );
              })()}
            </div>
          )}

          {/* ── GitHub / Local Repository Tab (GAP-3) ────────────────────────────── */}
          {workspaceView === "intake" && tab === "github" && (
            <div className="space-y-5">

              {/* ── Section 1: GitHub Repository ─────────────────────────────────── */}
              <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-4">
                <div className="flex items-center gap-2">
                  <div className="rounded-lg bg-gray-900 p-2 shrink-0">
                    <GitBranch className="h-4 w-4 text-white" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-gray-800">GitHub Repository</h4>
                    <p className="text-[10px] text-gray-400 font-semibold mt-0.5">
                      Clone a public or private GitHub repo and parse Python / JS / TS source files to auto-generate requirements
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border-t pt-4">
                  <div className="md:col-span-2 flex flex-col gap-1">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Repository URL <span className="text-red-400">*</span></label>
                    <input
                      type="url"
                      value={githubUrl}
                      onChange={(e) => setGithubUrl(e.target.value)}
                      placeholder="https://github.com/org/repo"
                      className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-app-brand-300"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Branch</label>
                    <input
                      value={githubBranch}
                      onChange={(e) => setGithubBranch(e.target.value)}
                      placeholder="main"
                      className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-app-brand-300"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                      Personal Access Token <span className="text-gray-300 font-normal">(private repos)</span>
                    </label>
                    <input
                      type="password"
                      value={githubToken}
                      onChange={(e) => setGithubToken(e.target.value)}
                      placeholder="ghp_••••••••••••••••"
                      className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-app-brand-300"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Languages to scan</label>
                    <input
                      value={repoLanguages}
                      onChange={(e) => setRepoLanguages(e.target.value)}
                      placeholder="python, javascript, typescript"
                      className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-app-brand-300"
                    />
                    <p className="text-[10px] text-gray-400">Comma-separated — python, javascript, typescript, java, go</p>
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
                <p className="text-[10px] text-gray-400 font-semibold">
                  Public repos cloned directly · Private repos require a PAT with repo read scope · Repo size limit 500 MB
                </p>
              </div>

              {/* ── Section 2: Local Repository ───────────────────────────────────── */}
              <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-4">
                <div className="flex items-center gap-2">
                  <div className="rounded-lg bg-violet-600 p-2 shrink-0">
                    <BarChart2 className="h-4 w-4 text-white" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-gray-800">Local Project Repository</h4>
                    <p className="text-[10px] text-gray-400 font-semibold mt-0.5">
                      Point to a local directory on the server and extract requirements from Python / JS / TS source files
                    </p>
                  </div>
                </div>

                <div className="border-t pt-4 space-y-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Local Repository Path <span className="text-red-400">*</span></label>
                    <input
                      value={localRepoPath}
                      onChange={(e) => setLocalRepoPath(e.target.value)}
                      placeholder="/home/user/projects/my-service  or  C:\Projects\my-service"
                      className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-mono font-semibold focus:outline-none focus:ring-2 focus:ring-app-brand-300"
                    />
                    <p className="text-[10px] text-gray-400">Absolute path accessible to the backend server · Symlinks supported</p>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Languages to scan</label>
                    <input
                      value={repoLanguages}
                      onChange={(e) => setRepoLanguages(e.target.value)}
                      placeholder="python, javascript, typescript"
                      className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-app-brand-300"
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
                <p className="text-[10px] text-gray-400 font-semibold">
                  Reads only — no files are modified · Hidden directories (.git, node_modules, __pycache__) are skipped
                </p>
              </div>

              {/* Requirements generated from code analysis */}
              {(() => {
                const codeReqs = requirements.filter((r) => r.source === "github_repo" || r.source === "local_repo");
                return codeReqs.length > 0 ? (
                  <div className="rounded-xl border divide-y overflow-hidden bg-white shadow-sm border-gray-200">
                    <div className="px-4 py-2.5 bg-gray-50/60 flex items-center justify-between">
                      <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                        Requirements generated from code ({codeReqs.length})
                      </p>
                    </div>
                    {codeReqs.map((req) => {
                      const meta = req.metadata_ as Record<string, any> | undefined;
                      return (
                        <div key={req.id} className="flex items-center gap-4 px-4 py-3 hover:bg-gray-50/50 cursor-pointer" onClick={() => handleOpenReqDetail(req)}>
                          <GitBranch className="h-4 w-4 text-gray-500 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-bold text-gray-800 truncate">{req.title}</p>
                            <p className="text-[10px] text-gray-400 font-bold truncate">
                              {req.requirement_id}
                              {meta?.repo_url ? ` · ${meta.repo_url}` : ""}
                              {meta?.file_path ? ` · ${meta.file_path}` : ""}
                            </p>
                          </div>
                          <Badge variant={getStatusVariant(req.status)} className="capitalize">{req.status.replace(/_/g, " ")}</Badge>
                          <ChevronRight className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-center text-xs text-gray-400 font-bold py-8 border border-dashed rounded-xl bg-white">
                    No code-based requirements yet. Connect a GitHub repo or local path above to generate them.
                  </p>
                );
              })()}
            </div>
          )}

          {/* ── Jira Tab ──────────────────────────────────────────────────────────── */}
          {workspaceView === "intake" && tab === "paste" && (
            <Card className="border-gray-200 shadow-sm">
              <CardContent className="space-y-5 p-5">
                <div className="flex items-start gap-3">
                  <div className="rounded-xl border border-app-brand-100 bg-app-brand-75 p-2.5"><ClipboardPaste className="h-5 w-5 text-[#B71920]" /></div>
                  <div><h3 className="text-sm font-bold text-gray-900">Add Missing Requirement</h3><p className="mt-1 text-[10px] font-semibold text-gray-400">Capture meeting notes, emails or specification text as a governed intake source.</p></div>
                </div>
                <div className="grid gap-4">
                  <div className="space-y-1.5"><label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Source title</label><input value={pasteTitle} onChange={(event) => setPasteTitle(event.target.value)} placeholder="e.g. Billing change workshop notes" className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-semibold text-gray-800 focus:outline-none focus:ring-2 focus:ring-app-brand-200" /></div>
                  <div className="space-y-1.5"><label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Source content</label><textarea value={pasteText} onChange={(event) => setPasteText(event.target.value)} placeholder="Paste the original source text here. Provenance is retained as Pasted Text." rows={10} className="w-full resize-y rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-medium leading-relaxed text-gray-800 focus:outline-none focus:ring-2 focus:ring-app-brand-200" /></div>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-amber-100 bg-amber-50/60 px-3 py-2"><span className="text-[10px] font-semibold text-amber-700">Validation gate: both title and source content are mandatory.</span><Button size="sm" disabled={manualIntakeBusy || !pasteTitle.trim() || !pasteText.trim()} onClick={() => handleManualIntake()} className="h-8 bg-[#B71920] text-xs text-white hover:bg-app-brand-700">{manualIntakeBusy ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Plus className="mr-1 h-3.5 w-3.5" />}Add to Intake</Button></div>
              </CardContent>
            </Card>
          )}

          {workspaceView === "intake" && tab === "jira" && (
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
                    <XCircle className="h-4 w-4 text-gray-400" />
                  </button>
                </div>
              )}

              {/* Connection configuration card */}
              <Card className="border-gray-200 bg-white">
                <CardContent className="p-5 space-y-4">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2">
                      <Plug className="h-5 w-5 text-[#B71920]" />
                      <div>
                        <h3 className="text-xs font-bold text-gray-800">Jira Sync Configuration</h3>
                        <p className="text-[10px] text-gray-400 mt-0.5">Link local project space to Atlassian Jira Agile project boards</p>
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
                      className="h-8 text-xs border-gray-200 font-semibold text-gray-650"
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
                          <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Jira Host URL</label>
                          <input value={jiraConnectionForm.jira_base_url} onChange={(e) => setJiraConnectionForm((f) => ({ ...f, jira_base_url: e.target.value }))} className="rounded-lg border border-gray-200 p-2 text-xs font-semibold bg-gray-50" placeholder="https://your-domain.atlassian.net" />
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Jira Login Email</label>
                          <input value={jiraConnectionForm.jira_email} onChange={(e) => setJiraConnectionForm((f) => ({ ...f, jira_email: e.target.value }))} className="rounded-lg border border-gray-200 p-2 text-xs font-semibold bg-gray-50" placeholder="amit.sharma@company.com" />
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Jira API Token</label>
                          <input type="password" value={jiraConnectionForm.jira_api_token} onChange={(e) => setJiraConnectionForm((f) => ({ ...f, jira_api_token: e.target.value }))} className="rounded-lg border border-gray-200 p-2 text-xs font-semibold bg-gray-50" placeholder={editingJiraConnectionId ? "••••••••••••" : "Atlassian API key"} />
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Jira Project Key</label>
                          <input value={jiraConnectionForm.jira_project_key} onChange={(e) => setJiraConnectionForm((f) => ({ ...f, jira_project_key: e.target.value }))} className="rounded-lg border border-gray-200 p-2 text-xs font-semibold bg-gray-50 font-mono uppercase" placeholder="e.g. STLC" />
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button type="submit" disabled={jiraBusy} size="sm" variant="default" className="text-xs font-semibold h-8.5">
                          {jiraBusy && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />}
                          Save Jira Details
                        </Button>
                        <Button type="button" onClick={() => { setShowJiraConnectionForm(false); setEditingJiraConnectionId(null); }} size="sm" variant="outline" className="text-xs font-semibold h-8.5 border-gray-200 text-gray-600 bg-white">
                          Cancel
                        </Button>
                      </div>
                    </form>
                  )}

                  {!showJiraConnectionForm && jiraConnections.length > 0 && (
                    <div className="border-t pt-4 flex items-center justify-between gap-4 flex-wrap bg-gray-50/50 p-3 rounded-lg border border-gray-150">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-bold text-gray-800">{selectedJiraConnectionRecord?.jira_project_key} Project Link</span>
                          <Badge variant={getStatusVariant(selectedJiraConnectionRecord?.is_active ? "connected" : "disconnected")}>
                            {selectedJiraConnectionRecord?.is_active ? "Connected" : "Inactive"}
                          </Badge>
                        </div>
                        <p className="text-[10px] text-gray-400 mt-1 font-semibold truncate">{selectedJiraConnectionRecord?.jira_base_url} ({selectedJiraConnectionRecord?.jira_email})</p>
                      </div>

                      <div className="flex gap-2 shrink-0">
                        <Button onClick={handleTestJiraConnection} disabled={jiraBusy} size="sm" variant="outline" className="h-8 text-xs border-gray-200 text-gray-650 bg-white font-bold">
                          Test Link
                        </Button>
                        <Button onClick={handleEditJiraConnection} disabled={jiraBusy} size="sm" variant="outline" className="h-8 text-xs border-gray-200 text-gray-650 bg-white font-bold">
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
                <Card className="border-gray-200 bg-white">
                  <CardContent className="p-5 space-y-4">
                    <div className="flex items-center gap-2">
                      <Search className="h-5 w-5 text-app-brand-500" />
                      <div>
                        <h3 className="text-xs font-bold text-gray-800">Fetch Jira Stories</h3>
                        <p className="text-[10px] text-gray-400 mt-0.5">Filter issue backlogs from Jira and import them as local specs</p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-t pt-4">
                      <div className="flex flex-col gap-1">
                        <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Issue Types CSV</label>
                        <div className="flex gap-1.5 items-center">
                          <input value={jiraFilters.issue_types} onChange={(e) => setJiraFilters((f) => ({ ...f, issue_types: e.target.value }))} className="flex-1 rounded-lg border border-gray-200 p-2 text-xs font-semibold bg-gray-50" placeholder="Story, Epic" />
                          <Button type="button" size="sm" variant="outline" onClick={() => setJiraFilters((f) => ({ ...f, issue_types: jiraStoryTypePreset }))} className="h-8 text-[9px] border-gray-200 text-gray-550 shrink-0 font-bold bg-white">Preset</Button>
                        </div>
                      </div>
                      <div className="flex flex-col gap-1">
                        <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Jira Statuses CSV</label>
                        <input value={jiraFilters.statuses} onChange={(e) => setJiraFilters((f) => ({ ...f, statuses: e.target.value }))} className="rounded-lg border border-gray-200 p-2 text-xs font-semibold bg-gray-50" placeholder="e.g. In Progress, Done" />
                      </div>
                      <div className="flex flex-col gap-1">
                        <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Jira JQL Query Override</label>
                        <input value={jiraFilters.jql} onChange={(e) => setJiraFilters((f) => ({ ...f, jql: e.target.value }))} className="rounded-lg border border-gray-200 p-2 text-xs font-semibold bg-gray-50" placeholder="project = STLC AND type = Story" />
                      </div>
                    </div>

                    <div className="flex gap-2">
                      <Button onClick={() => handleFetchJiraIssues()} disabled={jiraBusy} size="sm" variant="default" className="text-xs font-semibold h-8.5">
                        {jiraBusy && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1 text-white" />}
                        Fetch Backlog
                      </Button>
                      <Button onClick={handleImportJiraRequirements} disabled={jiraBusy} size="sm" variant="outline" className="text-xs font-semibold h-8.5 border-gray-200 text-gray-655 bg-white font-bold">
                        {selectedJiraKeys.size > 0
                          ? `Import ${selectedJiraKeys.size} Selected`
                          : "Import as Requirements"}
                      </Button>
                    </div>
                    {jiraIssuesPage && jiraIssuesPage.items.length > 0 && selectedJiraKeys.size === 0 && (
                      <p className="text-[10px] font-semibold text-gray-400 -mt-2">
                        Nothing ticked — importing will bring in every issue matching the filters above
                        {jiraIssuesPage.total > jiraIssuesPage.items.length ? ` (${jiraIssuesPage.total} in total, not just the ${jiraIssuesPage.items.length} shown)` : ""}.
                      </p>
                    )}

                    {/* Jira issues list — tick the ones to import */}
                    {jiraIssuesPage && jiraIssuesPage.items.length > 0 && (
                      <div className="border-t pt-4 space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                            Jira Backlog Matches ({jiraIssuesPage.total})
                            {selectedJiraKeys.size > 0 && (
                              <span className="ml-1.5 normal-case text-[#B71920]">· {selectedJiraKeys.size} selected</span>
                            )}
                          </label>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => setSelectedJiraKeys(new Set(jiraIssuesPage.items.map((i) => i.key)))}
                              className="text-[10px] font-bold text-[#B71920] hover:underline"
                            >
                              Select all {jiraIssuesPage.items.length} shown
                            </button>
                            {selectedJiraKeys.size > 0 && (
                              <button
                                type="button"
                                onClick={() => setSelectedJiraKeys(new Set())}
                                className="text-[10px] font-bold text-gray-500 hover:underline"
                              >
                                Clear
                              </button>
                            )}
                          </div>
                        </div>
                        <div className="rounded-lg border border-gray-150 divide-y divide-gray-100 overflow-hidden bg-gray-50/20 max-h-60 overflow-y-auto pr-1">
                          {jiraIssuesPage.items.map((issue) => {
                            const picked = selectedJiraKeys.has(issue.key);
                            return (
                              <div
                                key={issue.key}
                                onClick={() => toggleJiraKey(issue.key)}
                                className={cn(
                                  "p-3 text-xs flex items-start gap-3 cursor-pointer transition-colors",
                                  picked ? "bg-app-brand-75/60" : "bg-white hover:bg-gray-50/70",
                                )}
                              >
                                <input
                                  type="checkbox"
                                  checked={picked}
                                  readOnly
                                  aria-label={`Select ${issue.key}`}
                                  className="mt-0.5 shrink-0 accent-[#B71920]"
                                />
                                <div className="min-w-0">
                                  <div className="flex items-center gap-1.5">
                                    <span className="font-mono font-bold text-[#B71920]">{issue.key}</span>
                                    <Badge variant="outline" className="py-0 px-2 text-[9px] capitalize">{issue.issue_type}</Badge>
                                    <Badge variant={getStatusVariant(issue.status)} className="py-0 px-2 text-[9px] capitalize">{issue.status}</Badge>
                                  </div>
                                  <p className="font-bold text-gray-800 mt-1 truncate">{issue.summary}</p>
                                </div>
                              </div>
                            );
                          })}
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
      <Drawer open={!!selectedSource} onOpenChange={(open) => !open && setSelectedSource(null)}>
        <DrawerContent>
          {selectedSource && (
            <>
              <DrawerHeader>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <DrawerTitle>Intake Source Details</DrawerTitle>
                    <DrawerDescription className="mt-1">{selectedSource.name}</DrawerDescription>
                  </div>
                  <Badge variant={selectedSource.status === "blocked" ? "destructive" : selectedSource.status === "processing" ? "purple" : selectedSource.status === "completed" ? "success" : "info"} className="capitalize">{selectedSource.status}</Badge>
                </div>
              </DrawerHeader>
              <DrawerBody>
                <div className="space-y-5">
                  <section className="rounded-xl border border-gray-200 bg-gray-50/40 p-4">
                    <h4 className="mb-3 text-[10px] font-bold uppercase tracking-wider text-gray-400">Validation blockers</h4>
                    {selectedSource.validationIssues.length ? (
                      <ul className="space-y-2">{selectedSource.validationIssues.map((issue) => <li key={issue} className="flex items-start gap-2 text-xs font-semibold text-red-700"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{issue}</li>)}</ul>
                    ) : (
                      <div className="flex items-center gap-2 text-xs font-semibold text-emerald-700"><CheckCircle className="h-4 w-4" />All intake validations passed.</div>
                    )}
                  </section>

                  <section className="space-y-3">
                    <h4 className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Source provenance</h4>
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div className="rounded-lg border border-gray-200 p-3"><span className="block text-[9px] font-bold uppercase text-gray-400">Type</span><span className="mt-1 block font-bold text-gray-800">{selectedSource.sourceType}</span></div>
                      <div className="rounded-lg border border-gray-200 p-3"><span className="block text-[9px] font-bold uppercase text-gray-400">Owner</span><span className="mt-1 block font-bold text-gray-800">{selectedSource.owner}</span></div>
                      <div className="col-span-2 rounded-lg border border-gray-200 p-3"><span className="block text-[9px] font-bold uppercase text-gray-400">Origin</span><span className="mt-1 block font-semibold text-gray-700">{selectedSource.provenance}</span></div>
                    </div>
                  </section>

                  <section className="rounded-xl border border-purple-100 bg-purple-50/30 p-4">
                    <div className="mb-3 flex items-center gap-2"><Bot className="h-4 w-4 text-purple-600" /><h4 className="text-xs font-bold text-gray-800">AI intake job details</h4></div>
                    <dl className="space-y-2 text-xs">
                      <div className="flex justify-between gap-4"><dt className="font-semibold text-gray-500">Progress</dt><dd className="font-bold text-gray-800">{selectedSource.progress}%</dd></div>
                      <div className="flex justify-between gap-4"><dt className="font-semibold text-gray-500">Requirements extracted</dt><dd className="font-bold text-gray-800">{selectedSource.extractedCount}</dd></div>
                      <div className="flex justify-between gap-4"><dt className="font-semibold text-gray-500">Model</dt><dd className="text-right font-bold text-gray-800">Resolved by governed runtime policy</dd></div>
                      <div className="flex justify-between gap-4"><dt className="font-semibold text-gray-500">Prompt version</dt><dd className="font-bold text-gray-800">Captured with agent run</dd></div>
                      <div className="flex justify-between gap-4"><dt className="font-semibold text-gray-500">Tool version</dt><dd className="font-bold text-gray-800">Captured with agent run</dd></div>
                    </dl>
                  </section>

                  <section className="space-y-3">
                    <h4 className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Recent audit activity</h4>
                    <div className="flex items-start gap-3 rounded-lg border border-gray-200 p-3"><Clock className="mt-0.5 h-4 w-4 text-gray-400" /><div><p className="text-xs font-bold text-gray-800">Source registered in requirement intake</p><p className="mt-1 text-[10px] font-semibold text-gray-400">{selectedSource.createdAt ? new Date(selectedSource.createdAt).toLocaleString() : "Timestamp retained by source system"}</p></div></div>
                  </section>
                </div>
              </DrawerBody>
              <DrawerFooter className={cn((workspaceView === "analysis" || workspaceView === "review") && drawerTab === "details" && "hidden")}>
                <div className="flex w-full gap-2">
                  <Button variant="outline" size="sm" onClick={() => setSelectedSource(null)} className="h-9 flex-1 bg-white">Close</Button>
                  {selectedSource.documentId && (selectedSource.nextAction === "Run AI Intake" || selectedSource.nextAction === "Retry") ? (
                    <Button size="sm" disabled={agentRunning} onClick={() => { runIntakeAgent(selectedSource.documentId!); setSelectedSource(null); }} className="h-9 flex-1 bg-[#B71920] text-white hover:bg-app-brand-700">{selectedSource.nextAction}</Button>
                  ) : selectedSource.nextAction === "Send to Analysis" ? (
                    <Button size="sm" disabled={transitioning || selectedSource.validationIssues.length > 0 || selectedSource.requirementIds.length === 0} onClick={() => sendSourceToAnalysis(selectedSource)} className="h-9 flex-1 bg-[#B71920] text-white hover:bg-app-brand-700">Send to Analysis</Button>
                  ) : (
                    <Button size="sm" onClick={() => { const downstream = requirements.find((requirement) => requirement.source_document_id === selectedSource.documentId || selectedSource.requirementIds.includes(requirement.id)); setSelectedSource(null); handleWorkspaceViewChange(downstream ? getRequirementWorkflowStage(downstream) : "analysis"); }} className="h-9 flex-1 bg-[#B71920] text-white hover:bg-app-brand-700">View Downstream</Button>
                  )}
                </div>
              </DrawerFooter>
            </>
          )}
        </DrawerContent>
      </Drawer>

      <Drawer open={!!selectedReq} onOpenChange={(open) => !open && setSelectedReq(null)}>
        <DrawerContent size="xl" data-requirement-drawer-content>
          {selectedReq && (
            <>
              <DrawerHeader>
                <div className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-[#B71920]" />
                  <div className="min-w-0">
                    <DrawerTitle className="truncate">Requirement: {selectedReq.requirement_id}</DrawerTitle>
                    <DrawerDescription className="truncate">{selectedReq.title}</DrawerDescription>
                  </div>
                </div>
                <div className="ml-auto mr-2 hidden items-center gap-2 md:flex">
                  <Badge variant="outline" className="border-app-brand-100 bg-app-brand-75 text-app-brand-600">PPM ID: {selectedProjectPpmId}</Badge>
                  {workspaceView === "analysis" && (
                    <Badge variant={analysisBadgeVariant(analysisRows.find((row) => row.requirement.id === selectedReq.id)?.status || "not_analyzed")}>
                      {analysisLabel(analysisRows.find((row) => row.requirement.id === selectedReq.id)?.status || "not_analyzed")}
                    </Badge>
                  )}
                  {workspaceView === "traceability" && (
                    <Badge variant={traceHealthBadgeVariant(traceabilityRows.find((row) => row.requirement.id === selectedReq.id)?.health || "not_traced")}>
                      {traceHealthLabel(traceabilityRows.find((row) => row.requirement.id === selectedReq.id)?.health || "not_traced")}
                    </Badge>
                  )}
                  {workspaceView === "review" && (
                    <Badge variant={reviewStatusBadgeVariant(reviewRows.find((row) => row.requirement.id === selectedReq.id)?.reviewStatus || "pending")}>
                      {reviewStatusLabel(reviewRows.find((row) => row.requirement.id === selectedReq.id)?.reviewStatus || "pending")}
                    </Badge>
                  )}
                </div>
                <button onClick={() => setSelectedReq(null)} className="rounded-lg p-1 text-gray-400 hover:bg-gray-50"><X className="h-4 w-4" /></button>
              </DrawerHeader>

              <DrawerBody className="space-y-5">
                {/* GAP-5: Drawer tab navigation */}
                <div className="flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1 w-fit">
                  {((workspaceView === "traceability" ? ["traceability", "details"] : ["details", "traceability"]) as Array<"details" | "traceability">).map((t) => (
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
                          ? "bg-white text-gray-900 shadow-sm"
                          : "text-gray-500 hover:text-gray-800"
                      )}
                    >
                      {t === "details" ? <FileText className="h-3 w-3" /> : <GitBranch className="h-3 w-3" />}
                      {workspaceView === "traceability"
                        ? t === "traceability" ? "Trace Chain" : "Details"
                        : workspaceView === "review"
                          ? t === "details" ? "Review" : "Traceability"
                          : t === "details" ? (workspaceView === "analysis" ? "Analysis" : "Details") : "Traceability"}
                    </button>
                  ))}
                  {workspaceView === "review" && (
                    <>
                      <button disabled className="rounded-md px-3 py-1.5 text-xs font-bold text-gray-400">Analysis</button>
                      <button disabled className="rounded-md px-3 py-1.5 text-xs font-bold text-gray-400">History</button>
                      <button disabled className="rounded-md px-3 py-1.5 text-xs font-bold text-gray-400">Activity</button>
                    </>
                  )}
                  {workspaceView === "traceability" && (
                    <>
                      <button disabled className="rounded-md px-3 py-1.5 text-xs font-bold text-gray-400">Gaps & Issues</button>
                      <button disabled className="rounded-md px-3 py-1.5 text-xs font-bold text-gray-400">Activity</button>
                    </>
                  )}
                </div>

                {/* ── TRACEABILITY TAB ───────────────────────────────────────── */}
                {drawerTab === "traceability" && (
                  <div className="space-y-4">
                    {traceLoading && (
                      <div className="flex items-center gap-2 text-xs font-semibold text-gray-400 py-8 justify-center">
                        <Loader2 className="h-4 w-4 animate-spin text-[#B71920]" />
                        Loading traceability chain…
                      </div>
                    )}

                    {traceError && (
                      <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-xs text-red-700 font-semibold flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4 shrink-0" />
                        {traceError}
                      </div>
                    )}

                    {traceChain && !traceLoading && workspaceView === "traceability" && (
                      <div className="space-y-3">
                        {([
                          {
                            title: "Source / Evidence",
                            icon: FileText,
                            tone: "bg-app-brand-75 border-app-brand-100 text-app-brand-600",
                            badge: "Linked",
                            lines: [
                              selectedReq.jira_issue_key || selectedReq.source || "Source evidence registered",
                              selectedReq.business_process || selectedReq.telecom_domain || "Business requirement source",
                            ],
                          },
                          {
                            title: "Requirement Analysis",
                            icon: Bot,
                            tone: "bg-purple-50 border-purple-100 text-purple-600",
                            badge: traceChain.requirement.quality_verdict || "Analyzed",
                            lines: [
                              `Analyzed on: ${selectedReq.updated_at ? new Date(selectedReq.updated_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "Pending"}`,
                              `Quality Score: ${traceChain.requirement.quality_score ?? selectedReq.quality_score ?? 0}/100`,
                            ],
                          },
                          {
                            title: "Test Scenarios",
                            icon: ClipboardPaste,
                            tone: "bg-amber-50 border-amber-100 text-amber-600",
                            badge: `${traceChain.scenarios.length} linked`,
                            lines: traceChain.scenarios.length
                              ? traceChain.scenarios.slice(0, 3).map((item) => `${item.scenario_id}  ${item.title}`)
                              : ["No scenario linked"],
                          },
                          {
                            title: "Test Cases",
                            icon: Braces,
                            tone: "bg-violet-50 border-violet-100 text-violet-600",
                            badge: `${traceChain.test_cases.length} linked`,
                            lines: traceChain.test_cases.length
                              ? traceChain.test_cases.slice(0, 3).map((item) => `${item.test_case_id}  ${item.title}`)
                              : ["No test case linked"],
                          },
                          {
                            title: "Automation",
                            icon: Settings,
                            tone: "bg-cyan-50 border-cyan-100 text-cyan-600",
                            badge: `${traceChain.test_cases.filter((item) => item.automation_candidate).length} candidates`,
                            lines: traceChain.test_cases.filter((item) => item.automation_candidate).length
                              ? traceChain.test_cases.filter((item) => item.automation_candidate).slice(0, 2).map((item) => `Candidate: ${item.test_case_id}`)
                              : ["Automation not linked"],
                          },
                          {
                            title: "Execution & Evidence",
                            icon: ShieldCheck,
                            tone: "bg-app-brand-75 border-app-brand-100 text-app-brand-600",
                            badge: `${traceChain.execution_results.length} linked`,
                            lines: traceChain.execution_results.length
                              ? traceChain.execution_results.slice(0, 2).map((item) => `${item.test_name}  ${item.status}`)
                              : ["No execution evidence linked"],
                          },
                          {
                            title: "Defects",
                            icon: XCircle,
                            tone: "bg-red-50 border-red-100 text-red-600",
                            badge: `${traceChain.defects.length} linked`,
                            lines: traceChain.defects.length
                              ? traceChain.defects.slice(0, 3).map((item) => `${item.defect_id}  ${item.summary}`)
                              : ["No linked defects"],
                          },
                        ] as const).map((node, index, nodes) => {
                          const Icon = node.icon;
                          return (
                            <div key={node.title} className="relative pl-8">
                              {index < nodes.length - 1 && <div className="absolute left-[13px] top-9 h-[calc(100%-12px)] border-l border-dashed border-app-brand-200" />}
                              <div className={cn("absolute left-0 top-3 flex h-7 w-7 items-center justify-center rounded-lg border", node.tone)}>
                                <Icon className="h-3.5 w-3.5" />
                              </div>
                              <div className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
                                <div className="mb-2 flex items-center justify-between gap-2">
                                  <h4 className="text-xs font-bold text-gray-800">{node.title}</h4>
                                  <Badge variant="outline" className="text-[9px]">{node.badge}</Badge>
                                </div>
                                <div className="space-y-1">
                                  {node.lines.map((line, lineIndex) => (
                                    <div key={`${node.title}-${lineIndex}`} className="truncate text-[11px] font-semibold text-gray-600">{line}</div>
                                  ))}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                        <div className="grid grid-cols-2 gap-2 pt-2">
                          <Button variant="outline" size="sm" className="h-8 bg-white text-[10px] font-bold">Generate Missing Items</Button>
                          <Button variant="outline" size="sm" className="h-8 bg-white text-[10px] font-bold">Link Existing</Button>
                          <Button size="sm" disabled={transitioning} onClick={() => handleRequirementTransition(selectedReq, "send_to_review", "review")} className="col-span-2 h-8 bg-[#B71920] text-[10px] font-bold text-white hover:bg-app-brand-700">Send to Review & Approval</Button>
                        </div>
                      </div>
                    )}

                    {traceChain && !traceLoading && workspaceView !== "traceability" && (
                      <>
                        {/* Summary badges */}
                        <div className="grid grid-cols-4 gap-2">
                          {([
                            ["Scenarios", traceChain.summary.scenario_count, "text-app-brand-600", "bg-app-brand-75 border-app-brand-100"],
                            ["Test Cases", traceChain.summary.test_case_count, "text-app-brand-600", "bg-app-brand-75 border-app-brand-100"],
                            ["Executions", traceChain.summary.execution_count, "text-emerald-600", "bg-emerald-50 border-emerald-100"],
                            ["Defects", traceChain.summary.defect_count, "text-red-600", "bg-red-50 border-red-100"],
                          ] as const).map(([label, count, textCls, bgCls]) => (
                            <div key={label} className={cn("rounded-lg border p-2.5 text-center", bgCls)}>
                              <div className={cn("text-xl font-bold", textCls)}>{count}</div>
                              <div className="text-[9px] font-bold text-gray-400 uppercase mt-0.5">{label}</div>
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
                            <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Test Scenarios ({traceChain.scenarios.length})</label>
                            <div className="rounded-lg border border-gray-200 divide-y divide-gray-100 overflow-hidden bg-white">
                              {traceChain.scenarios.map((s) => (
                                <div key={s.id} className="flex items-center gap-3 px-3 py-2">
                                  <div className="w-1.5 h-1.5 rounded-full bg-app-brand-500 shrink-0" />
                                  <div className="flex-1 min-w-0">
                                    <span className="font-mono text-[10px] text-app-brand-600 font-bold">{s.scenario_id}</span>
                                    <span className="text-xs text-gray-700 font-semibold ml-2 truncate">{s.title}</span>
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
                            <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Test Cases ({traceChain.test_cases.length})</label>
                            <div className="rounded-lg border border-gray-200 divide-y divide-gray-100 overflow-hidden bg-white">
                              {traceChain.test_cases.map((tc) => (
                                <div key={tc.id} className="flex items-center gap-3 px-3 py-2">
                                  <div className="w-1.5 h-1.5 rounded-full bg-app-brand-500 shrink-0" />
                                  <div className="flex-1 min-w-0">
                                    <span className="font-mono text-[10px] text-[#B71920] font-bold">{tc.test_case_id}</span>
                                    <span className="text-xs text-gray-700 font-semibold ml-2 truncate">{tc.title}</span>
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
                            <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Execution Results ({traceChain.execution_results.length})</label>
                            <div className="rounded-lg border border-gray-200 divide-y divide-gray-100 overflow-hidden bg-white max-h-44 overflow-y-auto">
                              {traceChain.execution_results.map((er) => (
                                <div key={er.id} className="flex items-center gap-3 px-3 py-2">
                                  <div className={cn(
                                    "w-1.5 h-1.5 rounded-full shrink-0",
                                    er.status === "passed" ? "bg-emerald-400" : er.status === "failed" ? "bg-red-400" : "bg-gray-300"
                                  )} />
                                  <div className="flex-1 min-w-0">
                                    <span className="text-xs text-gray-700 font-semibold truncate">{er.test_name}</span>
                                  </div>
                                  <Badge variant={er.status === "passed" ? "success" : er.status === "failed" ? "destructive" : "outline"} className="text-[9px] shrink-0 capitalize">{er.status}</Badge>
                                  {er.created_at && (
                                    <span className="text-[9px] text-gray-400 shrink-0">{new Date(er.created_at).toLocaleDateString()}</span>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Defects */}
                        {traceChain.defects.length > 0 && (
                          <div className="space-y-1.5">
                            <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Defects ({traceChain.defects.length})</label>
                            <div className="rounded-lg border border-red-100 divide-y divide-red-50 overflow-hidden bg-red-50/30">
                              {traceChain.defects.map((d) => (
                                <div key={d.id} className="flex items-center gap-3 px-3 py-2">
                                  <div className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                                  <div className="flex-1 min-w-0">
                                    <span className="font-mono text-[10px] text-red-600 font-bold">{d.defect_id}</span>
                                    <span className="text-xs text-gray-700 font-semibold ml-2 truncate">{d.summary}</span>
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
                          <p className="text-center text-xs text-gray-400 font-semibold py-8 border border-dashed rounded-xl bg-white">
                            No traceability artifacts linked to this requirement yet.
                          </p>
                        )}
                      </>
                    )}
                  </div>
                )}

                {/* ── DETAILS TAB (existing content) ──────────────────────── */}
                {drawerTab === "details" && workspaceView === "review" && (() => {
                  const row = reviewRows.find((item) => item.requirement.id === selectedReq.id);
                  const reviewMeta = metadataRecord(selectedReq);
                  const selectedApprovalActions = approvalActions.filter((action) => action.entity_id === selectedReq.id);
                  const reviewerAction = selectedApprovalActions.find((action) => action.user_id === row?.reviewerId);
                  const reviewerRole = reviewerAction?.actor_role
                    || (currentUser && row?.reviewerId === currentUser.id ? currentUser.role : null)
                    || "Not recorded";
                  const assignedAt = reviewMeta.review_assigned_at ? String(reviewMeta.review_assigned_at) : null;
                  const qualityScore = getRequirementQualityScore(selectedReq);
                  const readinessItems = [
                    ["Analysis completed", row?.analysisStatus === "analyzed" ? (qualityScore === null ? "Passed" : `${qualityScore}/100`) : "Pending", row?.analysisStatus === "analyzed"],
                    ["Traceability health", `${row?.traceabilityScore ?? 0}/100`, (row?.traceabilityScore ?? 0) >= 70],
                    ["Missing information", row?.blockers.some((blocker) => blocker.toLowerCase().includes("missing")) ? "Open" : "0", !row?.blockers.some((blocker) => blocker.toLowerCase().includes("missing"))],
                    ["Duplicates resolved", row?.blockers.some((blocker) => blocker.toLowerCase().includes("duplicate")) ? "No" : "Yes", !row?.blockers.some((blocker) => blocker.toLowerCase().includes("duplicate"))],
                    ["Traceability gate", row?.traceabilityHealth === "fully_traced" ? "Validated" : "Pending", row?.traceabilityHealth === "fully_traced"],
                    ["Policy & permissions", currentUser ? (currentUser.is_superuser ? "Platform admin" : currentUser.role) : "Checking…", Boolean(currentUser?.is_active)],
                  ] as const;
                  return (
                    <div className="space-y-3 text-xs">
                      <section className="rounded-xl border border-gray-200 bg-white p-3">
                        <h4 className="mb-2 flex items-center gap-1.5 text-xs font-bold text-gray-800"><ShieldCheck className="h-3.5 w-3.5 text-[#B71920]" />Readiness Summary</h4>
                        <p className="mb-3 text-[11px] font-semibold text-gray-600">{row?.readyForApproval ? "All checks passed. This requirement is ready for approval." : "Some checks require attention before approval."}</p>
                        <div className="space-y-2">
                          {readinessItems.map(([label, value, passed]) => (
                            <div key={label} className="flex items-center justify-between gap-3 text-[11px] font-semibold">
                              <span className="flex items-center gap-2 text-gray-600">{passed ? <CheckCircle className="h-3.5 w-3.5 text-emerald-500" /> : <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />}{label}</span>
                              <span className="font-bold text-gray-700">{value}</span>
                            </div>
                          ))}
                        </div>
                      </section>

                      <section className="rounded-xl border border-gray-200 bg-white p-3">
                        <h4 className="mb-3 text-xs font-bold text-gray-800">Approval Recommendation</h4>
                        <div className="grid grid-cols-2 gap-2 text-[11px] font-semibold">
                          <div><div className="text-[9px] font-bold text-gray-400">AI Recommendation</div><Badge variant={row?.readyForApproval ? "success" : "warning"} className="mt-1">{row?.readyForApproval ? "Approve" : "Review"}</Badge></div>
                          <div><div className="text-[9px] font-bold text-gray-400">AI Confidence</div><Badge variant="purple" className="mt-1">{qualityScore === null ? "Not recorded" : `${qualityScore}%`}</Badge></div>
                        </div>
                        <p className="mt-2 text-[11px] font-semibold text-gray-600">{row?.readyForApproval ? "The requirement meets all quality and governance criteria." : row?.blockers[0] || "Reviewer attention required."}</p>
                      </section>

                      <section className="rounded-xl border border-gray-200 bg-white p-3">
                        <h4 className="mb-3 text-xs font-bold text-gray-800">Reviewer Information</h4>
                        <div className="grid grid-cols-2 gap-3 text-[11px] font-semibold text-gray-600">
                          <div className="flex items-center gap-2"><span className="flex h-7 w-7 items-center justify-center rounded-full bg-violet-100 text-[10px] font-bold text-violet-700">{(row?.reviewer || "NA").slice(0, 2).toUpperCase()}</span><span>{row?.reviewer}</span></div>
                          <div><div className="text-[9px] font-bold text-gray-400">Role</div><div className="font-bold text-gray-700">{reviewerRole}</div></div>
                          <div><div className="text-[9px] font-bold text-gray-400">Assigned On</div><div className="font-bold text-gray-700">{assignedAt ? new Date(assignedAt).toLocaleString("en-US", { month: "short", day: "numeric" }) : "Not recorded"}</div></div>
                          <div><div className="text-[9px] font-bold text-gray-400">SLA / Due In</div><div className={cn("font-bold", row?.slaStatus === "overdue" ? "text-red-600" : row?.slaStatus === "at_risk" ? "text-amber-600" : row?.slaStatus === "on_track" ? "text-emerald-600" : "text-gray-400")}>{row?.slaAge}</div></div>
                        </div>
                      </section>

                      <section className="rounded-xl border border-gray-200 bg-white p-3">
                        <h4 className="mb-3 text-xs font-bold text-gray-800">Approval History</h4>
                        <div className="space-y-2 text-[11px] font-semibold text-gray-600">
                          {selectedApprovalActions.length ? selectedApprovalActions.slice(0, 5).map((entry) => (
                            <div key={entry.id} className="flex items-center justify-between gap-3">
                              <span className="flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-[#B71920]" />{reviewActionLabel(entry.action_type)} by {resolveUser(entry.user_id)}</span>
                              <span className="text-gray-400">{formatRelativeTime(entry.created_at)}</span>
                            </div>
                          )) : <div className="text-gray-400">No audited approval or workflow history is recorded.</div>}
                        </div>
                      </section>

                      {!['approved', 'rejected'].includes(selectedReq.status) && <section className="space-y-2 rounded-xl border border-gray-200 bg-white p-3">
                        <h4 className="text-xs font-bold text-gray-800">Review Actions</h4>
                        <Button size="sm" disabled={!row?.readyForApproval || reviewLoading} onClick={() => handleApprove("approve")} className="h-8 w-full bg-emerald-600 text-[10px] font-bold text-white hover:bg-emerald-700">Approve Requirement</Button>
                        <Button variant="outline" size="sm" disabled={transitioning} onClick={() => handleRequirementTransition(selectedReq, "send_back_to_analysis", "analysis")} className="h-8 w-full border-amber-200 bg-white text-[10px] font-bold text-amber-700">Request Changes</Button>
                        <Button variant="outline" size="sm" disabled={reviewLoading} onClick={() => handleApprove("reject")} className="h-8 w-full border-red-200 bg-white text-[10px] font-bold text-red-600">Reject Requirement</Button>
                        <div className="grid grid-cols-2 gap-2">
                          <Button variant="outline" size="sm" disabled={transitioning} onClick={() => handleRequirementTransition(selectedReq, "send_back_to_analysis", "analysis")} className="h-8 bg-white text-[10px] font-bold">Send Back to Analysis</Button>
                          <Button variant="outline" size="sm" disabled={transitioning} onClick={() => handleRequirementTransition(selectedReq, "send_back_to_traceability", "traceability")} className="h-8 bg-white text-[10px] font-bold">Send Back to Traceability</Button>
                        </div>
                        <div className="rounded-lg border border-app-brand-100 bg-app-brand-75 px-3 py-2 text-center text-[10px] font-semibold text-app-brand-700">All actions are audited and immutable.</div>
                      </section>}
                    </div>
                  );
                })()}

                {drawerTab === "details" && workspaceView === "analysis" && (() => {
                  const row = analysisRows.find((item) => item.requirement.id === selectedReq.id);
                  const qualityMeta = metadataRecord(selectedReq).quality_review as Record<string, any> | undefined;
                  const latestQualityReview = selectedQualityReviews[0];
                  const acceptanceCriteria = selectedReq.acceptance_criteria || [];
                  const impactedSystems = [
                    ...(selectedReq.systems_impacted || []),
                    ...(selectedReq.impacted_interfaces || []),
                    ...(selectedReq.apis || []),
                  ].filter(Boolean);
                  const missingInfoItems = [
                    ...asTextList(selectedReq.missing_information),
                    ...asTextList(qualityMeta?.missing_information),
                    ...asTextList(latestQualityReview?.missing_details),
                  ].filter((item, index, items) => items.indexOf(item) === index);
                  const findings = [
                    ...asTextList(latestQualityReview?.ambiguities),
                    ...asTextList(qualityMeta?.findings),
                  ].filter((item, index, items) => items.indexOf(item) === index);
                  const recommendations = [
                    ...asTextList(latestQualityReview?.recommendations),
                    ...asTextList(qualityMeta?.recommendations),
                  ].filter((item, index, items) => items.indexOf(item) === index);
                  const scenarioReadiness = Number(latestQualityReview?.scenario_generation_readiness ?? qualityMeta?.scenario_generation_readiness);
                  const previousReview = selectedQualityReviews[1];
                  const previousScore = previousReview?.quality_score == null ? null : Math.round(Number(previousReview.quality_score) * 20);
                  const scoreDelta = row?.qualityScore != null && previousScore != null ? row.qualityScore - previousScore : null;
                  const isQualityStale = qualityMeta?.stale === true;
                  const qualityDimensions = QUALITY_DIMENSIONS.map((dim) => {
                    const raw = latestQualityReview?.[dim.key as keyof typeof latestQualityReview];
                    const prior = previousReview?.[dim.key as keyof typeof previousReview];
                    const value = raw == null || raw === "" ? null : Number(raw);
                    const before = prior == null || prior === "" ? null : Number(prior);
                    return {
                      ...dim,
                      value: value != null && Number.isFinite(value) ? value : null,
                      delta:
                        value != null && before != null && Number.isFinite(value) && Number.isFinite(before)
                          ? Number((value - before).toFixed(1))
                          : null,
                    };
                  }).filter((dim) => dim.value != null);
                  const improvementActions: Array<{ label: string; detail: string; dialog: AnalysisDialog }> = [];
                  if (!latestQualityReview || Number(latestQualityReview.completeness_score) < 3.5 || Number(latestQualityReview.clarity_score) < 3.5) improvementActions.push({ label: "Edit core details", detail: "State the actor, business outcome, trigger, rules, constraints, and risks.", dialog: "content" });
                  if (!latestQualityReview || Number(latestQualityReview.testability_score) < 3.5 || Number(latestQualityReview.acceptance_criteria_score) < 3.5) improvementActions.push({ label: "Edit acceptance criteria", detail: "Add measurable positive and negative outcomes with expected results.", dialog: "acceptance" });
                  // A null interface readiness score means the requirement crosses no
                  // system boundary, so there is nothing to map.
                  if (!latestQualityReview || (latestQualityReview.interface_readiness_score != null && Number(latestQualityReview.interface_readiness_score) < 3.5)) improvementActions.push({ label: "Map systems & APIs", detail: "Name impacted systems, interfaces, endpoints, protocols, and dependencies.", dialog: "systems" });
                  if (!latestQualityReview || Number(latestQualityReview.telecom_domain_completeness) < 3.5) improvementActions.push({ label: "Edit classification", detail: "Complete domain, application, sub request type, test phase, and risk level.", dialog: "classification" });
                  const editableValidationIssues = getEditableAnalysisValidationIssues(
                    selectedReq,
                    duplicateRequirementIds.has(selectedReq.id),
                  );
                  const needsFreshAnalysis = isQualityStale
                    || selectedReq.readiness_status === "analysis_pending"
                    || row?.status === "queued"
                    || row?.status === "not_analyzed";
                  const readyForRerun = needsFreshAnalysis && editableValidationIssues.length === 0;
                  const traceabilityReady = row?.status === "analyzed" && (row?.blockers.length ?? 0) === 0;
                  // Prefer the server's judgement. The locally derived list is
                  // kept only as a fallback for when the blockers read failed —
                  // a failed request must not make a blocked requirement look
                  // clear.
                  const serverBlockers = blockerSummary?.blockers ?? null;
                  const visibleValidationBlockers = serverBlockers
                    ? serverBlockers.map((blocker) => blocker.message)
                    : row?.blockers.length
                      ? row.blockers
                      : !traceabilityReady && !readyForRerun
                        ? ["Requirement analysis must reach a Pass verdict before traceability."]
                        : [];
                  // Grouped so the panel stops offering one route for all of them.
                  const blockersByRoute = blockerSummary?.by_resolution ?? null;
                  const rerunCannotHelp = blockerSummary?.rerun_cannot_help ?? false;
                  const advisoryGaps = blockerSummary?.advisory_missing_information ?? [];
                  const taxonomyWaiver = blockerSummary?.taxonomy_not_applicable ?? null;
                  const primaryEditableIssue = editableValidationIssues[0] || "";
                  const fixDialog: AnalysisDialog | null = primaryEditableIssue.toLowerCase().includes("taxonomy")
                    ? "classification"
                    : primaryEditableIssue.toLowerCase().includes("missing")
                      || primaryEditableIssue.toLowerCase().includes("duplicate")
                      || primaryEditableIssue.toLowerCase().includes("conflict")
                        ? "issues"
                        : null;
                  const fixLabel = fixDialog === "classification"
                    ? "Complete Classification"
                    : fixDialog === "issues"
                      ? "Resolve Validation Issue"
                      : null;
                  return (
                    <div className="space-y-3 text-xs">
                      <section className="border-b border-gray-100 pb-3">
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <h4 className="flex items-center gap-1.5 text-xs font-bold text-gray-800"><ShieldCheck className="h-3.5 w-3.5 text-[#B71920]" />Grounded Summary</h4>
                          <Badge variant={row?.qualityScore === null ? "outline" : "warning"} className="text-[9px]">Quality score {row?.qualityScore === null || row?.qualityScore === undefined ? "Not recorded" : `${row.qualityScore}/100`}</Badge>
                        </div>
                        <p className="text-[11px] font-semibold leading-relaxed text-gray-600">{selectedReq.summary || selectedReq.title}</p>
                        <button onClick={() => openAnalysisDialog("content")} className="mt-2 text-[10px] font-bold text-[#B71920]">Edit summary, rules & risks</button>
                      </section>

                      <section className="rounded-xl border border-app-brand-200 bg-app-brand-75/70 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h4 className="text-xs font-bold text-app-brand-950">How to pass quality analysis</h4>
                            <p className="mt-1 text-[10px] font-semibold leading-relaxed text-app-brand-800">Reach at least <strong>70/100</strong> overall and <strong>3/5 Scenario Readiness</strong>. Saving changes makes the old score stale; Re-run Analysis calculates the new result.</p>
                          </div>
                          <div className="shrink-0 text-right">
                            <div className="text-lg font-extrabold text-app-brand-950">{row?.qualityScore ?? "—"}/100</div>
                            <div className="text-[9px] font-bold text-app-brand-700">Readiness {Number.isFinite(scenarioReadiness) ? `${scenarioReadiness.toFixed(1)}/5` : "—"}</div>
                            {scoreDelta !== null && <div className={cn("text-[9px] font-bold", scoreDelta > 0 ? "text-emerald-700" : scoreDelta < 0 ? "text-red-700" : "text-gray-500")}>{scoreDelta > 0 ? "+" : ""}{scoreDelta} since prior run</div>}
                          </div>
                        </div>
                        {isQualityStale && <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2 py-1.5 text-[10px] font-bold text-amber-800">This score is from before the latest edits and cannot be used to pass. Re-run Analysis.</div>}
                        {/* The overall number is a weighted average of eight
                            dimensions. Without the breakdown, a score that moves
                            after an edit looks arbitrary — you cannot see that a
                            single dimension shifted by one point, or which one is
                            actually holding the requirement back. The weights are
                            shown because they decide how much a fix is worth. */}
                        {qualityDimensions.length > 0 && (
                          <div className="mt-3 rounded-lg border border-app-brand-100 bg-white p-2">
                            <div className="mb-1.5 text-[9px] font-bold uppercase text-app-brand-700">Score breakdown</div>
                            <ul className="space-y-1">
                              {qualityDimensions.map((dim) => (
                                <li key={dim.key} className="flex items-center justify-between gap-2 text-[10px]">
                                  <span className="flex min-w-0 items-center gap-1.5">
                                    <span className="truncate font-semibold text-gray-700">{dim.label}</span>
                                    <span className="shrink-0 text-[9px] font-bold text-gray-400">×{dim.weight.toFixed(2)}</span>
                                    {dim.gating && (
                                      <span className="shrink-0 rounded bg-amber-100 px-1 text-[8px] font-bold uppercase text-amber-800" title="This dimension has its own pass gate, independent of the overall score">
                                        gate
                                      </span>
                                    )}
                                  </span>
                                  <span className="flex shrink-0 items-center gap-1.5">
                                    <span className={cn("font-bold", dim.value != null && dim.value <= 2 ? "text-red-600" : dim.value != null && dim.value < 3.5 ? "text-amber-600" : "text-gray-700")}>
                                      {dim.value == null ? "—" : dim.value.toFixed(1)}/5
                                    </span>
                                    {dim.delta != null && dim.delta !== 0 && (
                                      <span className={cn("w-8 text-right font-bold", dim.delta > 0 ? "text-emerald-700" : "text-red-700")}>
                                        {dim.delta > 0 ? "+" : ""}{dim.delta.toFixed(1)}
                                      </span>
                                    )}
                                  </span>
                                </li>
                              ))}
                            </ul>
                            <p className="mt-1.5 text-[9px] font-semibold leading-snug text-gray-500">
                              Weights sum to 1. A one-point move on a 0.20 dimension is worth 4 points of 100, so
                              small swings between runs are expected — the agent scores in whole points.
                            </p>
                          </div>
                        )}
                        <div className="mt-3 space-y-2">
                          {improvementActions.map((action) => (
                            <button key={action.label} type="button" onClick={() => openAnalysisDialog(action.dialog)} className="flex w-full items-start justify-between gap-3 rounded-lg border border-app-brand-100 bg-white p-2 text-left transition hover:border-app-brand-300">
                              <span><span className="block text-[10px] font-bold text-app-brand-900">{action.label}</span><span className="mt-0.5 block text-[9px] font-semibold leading-snug text-gray-600">{action.detail}</span></span>
                              <ChevronRight className="mt-1 h-3.5 w-3.5 shrink-0 text-app-brand-500" />
                            </button>
                          ))}
                        </div>
                      </section>

                      <section className="border-b border-gray-100 pb-3">
                        <div className="mb-2 flex items-center justify-between">
                          <h4 className="text-xs font-bold text-gray-800">Acceptance Criteria ({acceptanceCriteria.length})</h4>
                          <ChevronDown className="h-3.5 w-3.5 text-gray-400" />
                        </div>
                        <ul className="space-y-1.5">
                          {acceptanceCriteria.slice(0, 4).map((criterion, index) => (
                            <li key={`${criterion}-${index}`} className="flex items-start gap-1.5 text-[11px] font-semibold text-gray-600">
                              <CheckCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                              <span className="leading-snug">{criterion}</span>
                            </li>
                          ))}
                          {acceptanceCriteria.length === 0 && <li className="text-[10px] font-semibold text-gray-400">No acceptance criteria are recorded.</li>}
                        </ul>
                        <button onClick={() => openAnalysisDialog("acceptance")} className="mt-2 text-[10px] font-bold text-[#B71920]">+ Add / Edit</button>
                      </section>

                      <section className="border-b border-gray-100 pb-3">
                        <div className="mb-2 flex items-center justify-between">
                          <h4 className="text-xs font-bold text-gray-800">Issues Detected</h4>
                          <button onClick={() => openAnalysisDialog("issues")} className="text-[10px] font-bold text-[#B71920]">View all</button>
                        </div>
                        <div className="grid grid-cols-4 gap-1.5">
                          {([
                            ["Findings", findings.length, "bg-gray-50 border-gray-100 text-gray-800"],
                            ["Missing Info", row?.missingInfoCount ?? 0, "bg-red-50 border-red-100 text-red-700"],
                            ["Duplicates", row?.duplicateCount ?? 0, "bg-amber-50 border-amber-100 text-amber-700"],
                            ["Conflicts", row?.conflictCount ?? 0, "bg-app-brand-75 border-app-brand-100 text-app-brand-700"],
                          ] as const).map(([label, count, tone]) => (
                            <button key={label} type="button" onClick={() => openAnalysisDialog("issues")} className={cn("rounded-lg border p-2 text-left transition hover:ring-2 hover:ring-app-brand-200", tone)} aria-label={`View ${label}`}>
                              <div className="truncate text-[9px] font-bold text-gray-500">{label}</div>
                              <div className="mt-1 text-lg font-bold">{count}</div>
                            </button>
                          ))}
                        </div>
                        {missingInfoItems.length > 0 && (
                          <div className="mt-2 rounded-lg border border-red-100 bg-red-50/60 p-2">
                            <div className="mb-1 text-[9px] font-bold uppercase text-red-600">Missing information required</div>
                            <ul className="space-y-1">
                              {missingInfoItems.slice(0, 3).map((item, index) => (
                                <li key={`${item}-${index}`} className="flex items-start gap-1.5 text-[10px] font-semibold leading-snug text-red-800">
                                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-red-500" />
                                  <span>{item}</span>
                                </li>
                              ))}
                            </ul>
                            <button onClick={() => openAnalysisDialog("issues")} className="mt-1.5 text-[10px] font-bold text-[#B71920]">
                              Resolve missing information
                            </button>
                          </div>
                        )}
                      </section>

                      <section className="border-b border-gray-100 pb-3">
                        <div className="mb-2 flex items-center justify-between">
                          <h4 className="text-xs font-bold text-gray-800">Classification</h4>
                          <button onClick={() => openAnalysisDialog("classification")} className="text-[10px] font-bold text-[#B71920]">Edit</button>
                        </div>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px]">
                          {([
                            ["Domain", selectedReq.telecom_domain || selectedReq.qa_domain || "Unclassified"],
                            ["Journey", selectedReq.business_process || "Not classified"],
                            ["Application", selectedReq.product || selectedReq.product_group || "Not mapped"],
                            ["Sub Request Type", selectedReq.sub_request_type || selectedReq.jira_issue_type || "Not classified"],
                            ["Test Type", selectedReq.test_phase || "Not specified"],
                            ["Risk Level", selectedReq.risk_level || "Not assessed"],
                          ] as const).map(([label, value]) => (
                            <div key={label}>
                              <div className="text-[9px] font-bold text-gray-400">{label}</div>
                              <div className="mt-0.5 font-bold text-gray-700">{value}</div>
                            </div>
                          ))}
                        </div>
                      </section>

                      <section className="border-b border-gray-100 pb-3">
                        <div className="mb-2 flex items-center justify-between">
                          <h4 className="text-xs font-bold text-gray-800">Impacted Systems</h4>
                          <button onClick={() => openAnalysisDialog("systems")} className="text-[10px] font-bold text-[#B71920]">View all</button>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {impactedSystems.slice(0, 4).map((system) => (
                            <Badge key={system} variant="outline" className="text-[9px]">{system}</Badge>
                          ))}
                          {impactedSystems.length === 0 && <span className="text-[10px] font-semibold text-gray-400">No impacted systems recorded.</span>}
                          {impactedSystems.length > 4 && <span className="text-[10px] font-bold text-[#B71920]">+{impactedSystems.length - 4} more</span>}
                        </div>
                      </section>

                      <section className="border-b border-gray-100 pb-3">
                        <h4 className="mb-2 text-xs font-bold text-gray-800">AI Analysis Details</h4>
                        {qualityReviewsLoading ? (
                          <div className="text-[10px] font-semibold text-gray-400"><Loader2 className="mr-1 inline h-3 w-3 animate-spin" />Loading persisted quality review…</div>
                        ) : latestQualityReview ? (
                          <>
                            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px]">
                              <div><div className="text-[9px] font-bold text-gray-400">Model</div><div className="font-bold text-gray-700">{String(qualityMeta?.model || "Not recorded")}</div></div>
                              <div><div className="text-[9px] font-bold text-gray-400">Prompt Version</div><div className="font-bold text-gray-700">{String(qualityMeta?.prompt_version || "Not recorded")}</div></div>
                              <div><div className="text-[9px] font-bold text-gray-400">Agent Run</div><div className="font-bold text-gray-700">{latestQualityReview.agent_run_id ? `#${latestQualityReview.agent_run_id}` : "Not recorded"}</div></div>
                              <div><div className="text-[9px] font-bold text-gray-400">Analyzed At</div><div className="font-bold text-gray-700">{latestQualityReview.created_at ? new Date(latestQualityReview.created_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "Not recorded"}</div></div>
                            </div>
                            <div className="mt-3 grid grid-cols-2 gap-2">
                              {([
                                ["Completeness", latestQualityReview.completeness_score, "Not recorded"],
                                ["Clarity", latestQualityReview.clarity_score, "Not recorded"],
                                ["Testability", latestQualityReview.testability_score, "Not recorded"],
                                ["Acceptance criteria", latestQualityReview.acceptance_criteria_score, "Not recorded"],
                                // Scored null when the requirement crosses no system boundary.
                                ["Interface readiness", latestQualityReview.interface_readiness_score, "Not applicable"],
                                ["Domain completeness", latestQualityReview.telecom_domain_completeness, "Not recorded"],
                              ] as const).map(([label, value, emptyLabel]) => (
                                <div key={label} className="rounded-lg border border-gray-100 bg-gray-50 p-2">
                                  <div className="text-[9px] font-bold text-gray-400">{label}</div>
                                  <div className="mt-0.5 font-bold text-gray-700">{value === null || value === undefined ? emptyLabel : Number(value).toFixed(1)}</div>
                                </div>
                              ))}
                            </div>
                            {findings.length > 0 && (
                              <div className="mt-3 rounded-lg border border-amber-100 bg-amber-50 p-2.5">
                                <div className="text-[9px] font-bold uppercase text-amber-700">Review findings</div>
                                <ul className="mt-1.5 space-y-1">
                                  {findings.map((item, index) => <li key={`${item}-${index}`} className="text-[10px] font-semibold leading-snug text-amber-900">• {item}</li>)}
                                </ul>
                              </div>
                            )}
                            {recommendations.length > 0 && (
                              <div className="mt-2 rounded-lg border border-emerald-100 bg-emerald-50 p-2.5">
                                <div className="text-[9px] font-bold uppercase text-emerald-700">What to update</div>
                                <ul className="mt-1.5 space-y-1">
                                  {recommendations.map((item, index) => <li key={`${item}-${index}`} className="text-[10px] font-semibold leading-snug text-emerald-900">• {item}</li>)}
                                </ul>
                              </div>
                            )}
                            {selectedQualityReviews.length > 1 && <div className="mt-2 text-[9px] font-semibold text-gray-400">{selectedQualityReviews.length} persisted review runs; latest shown.</div>}
                          </>
                        ) : <div className="text-[10px] font-semibold text-gray-400">No persisted quality-review run is available for this requirement.</div>}
                      </section>

                      <section ref={analysisActionsRef} className="space-y-2 rounded-xl border border-gray-200 bg-gray-50/60 p-3">
                        <h4 className="text-xs font-bold text-gray-800">Actions</h4>
                        {taxonomyWaiver && (
                          <div className="rounded-lg border border-gray-200 bg-white p-2.5">
                            <div className="text-[10px] font-bold text-gray-700">
                              Taxonomy recorded as not applicable
                            </div>
                            <p className="mt-0.5 text-[10px] font-semibold leading-snug text-gray-500">
                              {taxonomyWaiver.reason}
                            </p>
                            <button
                              type="button"
                              disabled={taxonomyWaiverBusy}
                              onClick={async () => {
                                setTaxonomyWaiverBusy(true);
                                try {
                                  await requirementsApi.setTaxonomyApplicability(selectedReq.id, true);
                                  await loadBlockerSummary(selectedReq.id);
                                  await loadData();
                                } catch (e: any) {
                                  const detail = e?.response?.data?.detail;
                                  setAnalysisDialogError(typeof detail === "string" ? detail : detail?.message || "Unable to restore the taxonomy requirement.");
                                } finally {
                                  setTaxonomyWaiverBusy(false);
                                }
                              }}
                              className="mt-1 text-[10px] font-bold text-[#B71920] disabled:opacity-50"
                            >
                              Taxonomy does apply — restore the requirement
                            </button>
                          </div>
                        )}
                        {advisoryGaps.length > 0 && (
                          // Shown, never gating. The agent judged a tester can
                          // still write a meaningful case without these.
                          <div className="rounded-lg border border-gray-200 bg-white p-2.5">
                            <div className="text-[10px] font-bold text-gray-600">
                              Open questions that are not blocking ({advisoryGaps.length})
                            </div>
                            <ul className="mt-1 space-y-0.5">
                              {advisoryGaps.map((gap: MissingInfoItem) => (
                                <li key={gap.item} className="text-[10px] font-semibold leading-snug text-gray-500">
                                  • {gap.item}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {visibleValidationBlockers.length > 0 && !readyForRerun && (
                          <div role="alert" className="rounded-xl border-2 border-red-300 bg-red-50 p-3 shadow-sm">
                            <div className="flex items-start gap-2">
                              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
                              <div className="min-w-0 flex-1">
                                <div className="text-[11px] font-extrabold text-red-800">Traceability is blocked — update the following</div>
                                {blockersByRoute ? (
                                  <div className="mt-1.5 space-y-2">
                                    {rerunCannotHelp && (
                                      // The gap that started this: the panel led
                                      // with "re-run Analysis" for blockers no
                                      // re-run could ever clear.
                                      <p className="rounded-md bg-red-100 px-2 py-1 text-[10px] font-bold text-red-800">
                                        Re-running Analysis will not clear any of these. They need a person.
                                      </p>
                                    )}
                                    {BLOCKER_ROUTE_ORDER.map((route: BlockerResolution) => {
                                      const group = blockersByRoute[route] ?? [];
                                      if (group.length === 0) return null;
                                      return (
                                        <div key={route}>
                                          <div className="text-[9px] font-extrabold uppercase tracking-wide text-red-500">
                                            {BLOCKER_ROUTE_HEADING[route]}
                                          </div>
                                          <ul className="mt-0.5 space-y-1">
                                            {group.map((blocker: RequirementBlocker) => (
                                              <li key={blocker.code + blocker.message} className="text-[10px] font-bold leading-snug text-red-700">
                                                • {blocker.message}
                                              </li>
                                            ))}
                                          </ul>
                                        </div>
                                      );
                                    })}
                                  </div>
                                ) : (
                                  <ul className="mt-1.5 space-y-1">
                                    {visibleValidationBlockers.map((blocker: string, index: number) => (
                                      <li key={`${blocker}-${index}`} className="text-[10px] font-bold leading-snug text-red-700">
                                        {index + 1}. {blocker}
                                      </li>
                                    ))}
                                  </ul>
                                )}
                                <div className="mt-2 flex flex-wrap items-center gap-2">
                                  {fixDialog && fixLabel && (
                                    <button type="button" onClick={() => openAnalysisDialog(fixDialog)} className="inline-flex h-7 items-center gap-1 rounded-lg bg-red-600 px-2.5 text-[10px] font-bold text-white shadow-sm transition hover:bg-red-700">
                                      {fixLabel}<ChevronRight className="h-3 w-3" />
                                    </button>
                                  )}
                                  {/* Only offered when taxonomy is what is
                                      blocking, and only as a recorded human
                                      decision with a reason — never inferred. */}
                                  {(blockersByRoute?.human_input ?? []).some((b: RequirementBlocker) => b.code.startsWith("taxonomy")) && (
                                    <button
                                      type="button"
                                      disabled={taxonomyWaiverBusy}
                                      onClick={async () => {
                                        const reason = window.prompt(
                                          "Why does the taxonomy not apply to this requirement? This is recorded against your name.",
                                        );
                                        if (!reason || !reason.trim()) return;
                                        setTaxonomyWaiverBusy(true);
                                        try {
                                          await requirementsApi.setTaxonomyApplicability(selectedReq.id, false, reason.trim());
                                          await loadBlockerSummary(selectedReq.id);
                                          await loadData();
                                        } catch (e: any) {
                                          const detail = e?.response?.data?.detail;
                                          setAnalysisDialogError(typeof detail === "string" ? detail : detail?.message || "Unable to record the taxonomy decision.");
                                        } finally {
                                          setTaxonomyWaiverBusy(false);
                                        }
                                      }}
                                      className="inline-flex h-7 items-center rounded-lg border border-red-300 bg-white px-2.5 text-[10px] font-bold text-red-700 transition hover:bg-red-50 disabled:opacity-50"
                                    >
                                      Taxonomy does not apply
                                    </button>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        )}
                        {readyForRerun && (
                          <div className="rounded-xl border-2 border-violet-300 bg-violet-50 p-3 shadow-sm">
                            <div className="flex items-start gap-2">
                              <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-violet-600" />
                              <div>
                                <div className="text-[11px] font-extrabold text-violet-900">All editable validation details are complete</div>
                                <p className="mt-1 text-[10px] font-semibold leading-snug text-violet-700">Next step: Re-run Analysis to validate the saved changes and calculate the current quality score.</p>
                              </div>
                            </div>
                          </div>
                        )}
                        {traceabilityReady && (
                          <div className="rounded-xl border-2 border-emerald-300 bg-emerald-50 p-3 shadow-sm">
                            <div className="flex items-start gap-2">
                              <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                              <div>
                                <div className="text-[11px] font-extrabold text-emerald-900">All analysis validations passed</div>
                                <p className="mt-1 text-[10px] font-semibold leading-snug text-emerald-700">Send to Traceability is ready.</p>
                              </div>
                            </div>
                          </div>
                        )}
                        <div className="grid grid-cols-2 gap-2">
                          <Button variant="outline" size="sm" disabled={analysisDialogSaving} onClick={() => openAnalysisDialog(selectedReq.readiness_status === "needs_clarification" ? "issues" : "clarification")} className="h-8 bg-white text-[10px] font-bold">{selectedReq.readiness_status === "needs_clarification" ? "Provide Clarification" : "Request Clarification"}</Button>
                          <Button variant={readyForRerun ? "default" : "outline"} size="sm" disabled={agentRunning} onClick={() => runQualityAgent([selectedReq.id])} className={cn(
                            "h-8 text-[10px] font-bold",
                            readyForRerun
                              ? "bg-violet-600 text-white shadow-md ring-2 ring-violet-200 hover:bg-violet-700"
                              : "bg-white",
                          )}>
                            {agentRunning ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : readyForRerun ? <Sparkles className="mr-1 h-3.5 w-3.5" /> : null}
                            {readyForRerun ? "Re-run Analysis — Next Step" : "Re-run Analysis"}
                          </Button>
                        </div>
                        <Button size="sm" disabled={transitioning || !traceabilityReady} onClick={() => handleRequirementTransition(selectedReq, "send_to_traceability", "traceability")} className={cn(
                          "h-8 w-full text-[10px] font-bold text-white",
                          traceabilityReady ? "bg-emerald-600 hover:bg-emerald-700" : "bg-gray-300",
                        )}>Send to Traceability</Button>
                      </section>
                    </div>
                  );
                })()}

                {drawerTab === "details" && workspaceView !== "analysis" && workspaceView !== "review" && (
                  <div className="space-y-5">

                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Status:</span>
                  <Badge variant={getStatusVariant(selectedReq.status)} className="capitalize">{selectedReq.status.replace(/_/g, " ")}</Badge>
                </div>

                {selectedReq.summary && (
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Description</label>
                    <p className="text-xs text-gray-700 leading-relaxed font-semibold bg-gray-50 border rounded-lg p-3">{selectedReq.summary}</p>
                  </div>
                )}

                {/* Test Environment + Generation Notes — drives AI scenario/test-case
                    generation style (see scenario_agent.py / test_case_agent.py). Styled to
                    stand out so testers notice it before generating test cases. */}
                <div className="relative overflow-hidden rounded-xl border-2 border-[#B71920]/25 bg-gradient-to-br from-app-brand-75 via-app-brand-75/50 to-white p-4 pt-5 space-y-3 shadow-sm ring-1 ring-[#B71920]/10">
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[#B71920] via-app-brand-500 to-violet-500" />
                  <div className="flex items-center gap-2">
                    <div className="flex items-center justify-center h-7 w-7 rounded-lg bg-[#B71920]/10 border border-[#B71920]/20 shrink-0">
                      <Bot className="h-4 w-4 text-[#B71920]" />
                    </div>
                    <h4 className="text-xs font-bold text-gray-800">AI Test Case Generation Context</h4>
                    <Badge variant="info" className="ml-auto text-[9px] font-bold tracking-wide shrink-0">AI-POWERED</Badge>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Test Environment</label>
                    <select
                      value={genEnvDraft}
                      onChange={(e) => { setGenEnvDraft(e.target.value); setGenContextSaved(false); }}
                      className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-semibold text-gray-800 focus:outline-none focus:ring-2 focus:ring-[#B71920]"
                    >
                      {["SIT", "QA", "UAT", "Regression", "Production Smoke Test"].map((env) => (
                        <option key={env} value={env}>{env}</option>
                      ))}
                    </select>
                    <p className="text-[10px] text-gray-400 font-medium">Tailors the depth/style of AI-generated scenarios &amp; test cases for this requirement.</p>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Generation Notes</label>
                    <textarea
                      value={genNotesDraft}
                      onChange={(e) => { setGenNotesDraft(e.target.value); setGenContextSaved(false); }}
                      placeholder="Optional instructions or emphasis for the AI to consider when generating test cases for this requirement (e.g. focus areas, known edge cases, data constraints)…"
                      rows={3}
                      className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-800 focus:outline-none focus:ring-2 focus:ring-[#B71920] resize-none"
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
                          <h4 className="text-xs font-bold text-gray-800">AI Requirement Quality Score</h4>
                        </div>
                        <QualityBadge score={quality.overall_score} verdict={quality.verdict} />
                      </div>

                      <div className="grid grid-cols-3 gap-3 mb-2 text-center text-xs font-semibold">
                        <div className="bg-white border rounded-lg p-2">
                          <div className="text-lg font-bold text-gray-850">{(quality.completeness_score) ?? "?"}</div>
                          <div className="text-[9px] text-gray-400 font-bold uppercase">Completeness</div>
                        </div>
                        <div className="bg-white border rounded-lg p-2">
                          <div className="text-lg font-bold text-gray-850">{(quality.clarity_score) ?? "?"}</div>
                          <div className="text-[9px] text-gray-400 font-bold uppercase">Clarity</div>
                        </div>
                        <div className="bg-white border rounded-lg p-2">
                          <div className="text-lg font-bold text-gray-850">{(quality.testability_score) ?? "?"}</div>
                          <div className="text-[9px] text-gray-400 font-bold uppercase">Testability</div>
                        </div>
                      </div>

                      {quality.issues?.length > 0 && (
                        <div className="space-y-1">
                          <label className="text-[9px] font-extrabold uppercase tracking-wider text-rose-500 block">Quality Issues Detected</label>
                          <ul className="text-xs space-y-1 font-semibold text-gray-650 bg-white rounded-lg p-3 border">
                            {quality.issues.map((issue: string, i: number) => (
                              <li key={i} className="flex items-start gap-1.5"><span className="text-rose-500 font-bold select-none">•</span>{issue}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {quality.suggestions?.length > 0 && (
                        <div className="space-y-1">
                          <label className="text-[9px] font-extrabold uppercase tracking-wider text-app-brand-500 block">AI Suggestions</label>
                          <ul className="text-xs space-y-1 font-semibold text-gray-650 bg-white rounded-lg p-3 border">
                            {quality.suggestions.map((s: string, i: number) => (
                              <li key={i} className="flex items-start gap-1.5"><span className="text-app-brand-500 font-bold select-none">→</span>{s}</li>
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
                          <h4 className="text-xs font-bold text-gray-800">UI Screenshot Analysis{ui.screen_name ? `: ${ui.screen_name}` : ""}</h4>
                        </div>
                        <Badge variant="success">Vision AI</Badge>
                      </div>

                      {ui.screen_purpose && (
                        <p className="text-xs text-gray-700 leading-relaxed font-semibold bg-white border rounded-lg p-3">{ui.screen_purpose}</p>
                      )}

                      <div className="grid grid-cols-3 gap-3 text-center text-xs font-semibold">
                        <div className="bg-white border rounded-lg p-2">
                          <div className="text-lg font-bold text-gray-850">{(ui.fields ?? []).length}</div>
                          <div className="text-[9px] text-gray-400 font-bold uppercase">Fields</div>
                        </div>
                        <div className="bg-white border rounded-lg p-2">
                          <div className="text-lg font-bold text-gray-850">{(ui.buttons ?? []).length}</div>
                          <div className="text-[9px] text-gray-400 font-bold uppercase">Buttons</div>
                        </div>
                        <div className="bg-white border rounded-lg p-2">
                          <div className="text-lg font-bold text-gray-850">{(ui.user_flows ?? []).length}</div>
                          <div className="text-[9px] text-gray-400 font-bold uppercase">User Flows</div>
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
                            <span className="text-[10px] text-gray-400 font-bold">+{(ui.fields ?? []).length - 12} more</span>
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
                            <ul className="text-xs space-y-1 font-semibold text-gray-650 bg-white rounded-lg p-3 border">
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
                  <div className="border rounded-xl bg-gray-50/30 p-4 flex items-center gap-2 text-xs font-semibold text-gray-400">
                    <Loader2 className="h-4 w-4 animate-spin text-[#B71920]" />
                    Loading coverage insights...
                  </div>
                ) : coverage ? (
                  <div className="border border-sky-100 rounded-xl bg-sky-50/20 p-4 space-y-4">
                    <div className="flex items-center justify-between border-b pb-2.5 border-sky-100/50">
                      <div className="flex items-center gap-2">
                        <ShieldCheck className="h-4.5 w-4.5 text-sky-500" />
                        <h4 className="text-xs font-bold text-gray-800">Test Coverage Insights</h4>
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
                        <div className="text-lg font-bold text-gray-850">{coverage.scenario_count}</div>
                        <div className="text-[9px] text-gray-400 font-bold uppercase">Scenarios</div>
                      </div>
                      <div className="bg-white border rounded-lg p-2">
                        <div className="text-lg font-bold text-gray-850">{coverage.test_case_count}</div>
                        <div className="text-[9px] text-gray-400 font-bold uppercase">Test Cases</div>
                      </div>
                      <div className="bg-white border rounded-lg p-2">
                        <div className="text-lg font-bold text-gray-850">{coverage.automation_candidates}</div>
                        <div className="text-[9px] text-gray-400 font-bold uppercase">Automatable</div>
                      </div>
                    </div>

                    {(coverage.covered_categories.length > 0 || coverage.missing_categories.length > 0) && (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {coverage.covered_categories.map((c) => (
                          <Badge key={c} variant="success" className="capitalize">{c} ✓</Badge>
                        ))}
                        {coverage.missing_categories.map((c) => (
                          <Badge key={c} variant="outline" className="capitalize text-gray-400">{c} missing</Badge>
                        ))}
                      </div>
                    )}

                    {coverage.gaps.length > 0 && (
                      <div className="space-y-1">
                        <label className="text-[9px] font-extrabold uppercase tracking-wider text-amber-600 block">Coverage Gaps Detected</label>
                        <ul className="text-xs space-y-1 font-semibold text-gray-650 bg-white rounded-lg p-3 border">
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
                  // Normalized: entries carry a severity now and would otherwise
                  // render as "[object Object]".
                  ["Missing Specs / Info", asTextList(selectedReq.missing_information)]
                ] as const).map(([label, array]) => array && array.length > 0 ? (
                  <div key={label} className="space-y-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{label}</label>
                    <ul className="text-xs space-y-1.5 font-semibold text-gray-700 bg-gray-50/50 border rounded-lg p-3.5">
                      {array.map((item, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="text-app-brand-500 font-bold select-none mt-0.5">•</span>
                          <span className="leading-relaxed">{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null)}

                  <div className="border-t border-gray-100 pt-4 space-y-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400 flex items-center gap-1">
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
                {(() => {
                  const stage = getRequirementWorkflowStage(selectedReq);
                  const intakeBlockers = requirementIntakeTransitionBlockers(selectedReq);
                  if (workspaceView !== "intake") {
                    return <Button variant="outline" size="sm" onClick={() => setSelectedReq(null)} className="w-full h-9 bg-white border-gray-200">Close detail</Button>;
                  }
                  if (stage !== "intake") {
                    const destinationLabel = stage === "analysis" ? "Requirement Analysis" : stage === "traceability" ? "Traceability" : "Review & Approval";
                    return (
                      <div className="w-full space-y-3">
                        <div className="rounded-xl border border-app-brand-200 bg-app-brand-75 p-3">
                          <div className="flex items-start gap-2">
                            <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-app-brand-600" />
                            <div>
                              <div className="text-[9px] font-extrabold uppercase tracking-wider text-gray-500">Next action</div>
                              <div className="mt-1 text-xs font-bold text-gray-900">Continue in {destinationLabel}</div>
                              <p className="mt-1 text-[10px] font-semibold leading-relaxed text-gray-600">This requirement has already completed intake. Open its current workspace to perform the next governed actions.</p>
                            </div>
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <Button variant="outline" size="sm" onClick={() => setSelectedReq(null)} className="h-9 flex-1 bg-white border-gray-200">Close</Button>
                          <Button size="sm" onClick={() => { setSelectedReq(null); handleWorkspaceViewChange(stage); }} className="h-9 flex-[1.5] bg-[#B71920] text-white hover:bg-app-brand-700">
                            <ArrowRight className="mr-1.5 h-3.5 w-3.5" />
                            Open {destinationLabel}
                          </Button>
                        </div>
                      </div>
                    );
                  }
                  return (
                    <div className="w-full space-y-3">
                      <div className={cn("rounded-xl border p-3", intakeBlockers.length ? "border-amber-200 bg-amber-50" : "border-app-brand-200 bg-app-brand-75")}>
                        <div className="flex items-start gap-2">
                          {intakeBlockers.length ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" /> : <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-app-brand-600" />}
                          <div>
                            <div className="text-[9px] font-extrabold uppercase tracking-wider text-gray-500">Next step</div>
                            <div className="mt-1 text-xs font-bold text-gray-900">Requirement Analysis</div>
                            <p className="mt-1 text-[10px] font-semibold leading-relaxed text-gray-600">
                              {intakeBlockers.length
                                ? "Complete the intake items below before sending this requirement for quality analysis."
                                : "Intake validation is complete. Send this requirement to Requirement Analysis for quality scoring, ambiguity review, and classification."}
                            </p>
                            {intakeBlockers.length > 0 && <ul className="mt-2 space-y-1">{intakeBlockers.map((blocker) => <li key={blocker} className="text-[10px] font-semibold text-amber-800">• {blocker}</li>)}</ul>}
                          </div>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button variant="outline" size="sm" onClick={() => setSelectedReq(null)} className="h-9 flex-1 bg-white border-gray-200">Close</Button>
                        <Button size="sm" disabled={transitioning || intakeBlockers.length > 0} onClick={() => handleRequirementTransition(selectedReq, "send_to_analysis", "analysis")} className="h-9 flex-[1.5] bg-[#B71920] text-white hover:bg-app-brand-700">
                          {transitioning ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <ArrowRight className="mr-1.5 h-3.5 w-3.5" />}
                          Send to Requirement Analysis
                        </Button>
                      </div>
                    </div>
                  );
                })()}
              </DrawerFooter>
            </>
          )}
        </DrawerContent>
      </Drawer>

      {analysisDialog && selectedReq && typeof document !== "undefined" && document.querySelector("[data-requirement-drawer-content]") && createPortal((() => {
        const analysisRow = analysisRows.find((item) => item.requirement.id === selectedReq.id);
        const qualityMeta = metadataRecord(selectedReq).quality_review as Record<string, any> | undefined;
        const missingInfoItems = [
          ...asTextList(selectedReq.missing_information),
          ...asTextList(qualityMeta?.missing_information),
          ...asTextList(selectedQualityReviews[0]?.missing_details),
        ].filter((item, index, items) => items.indexOf(item) === index);
        const missingInfoAdvisoryCount = advisoryMissingInfo(
          selectedReq.missing_information,
        ).length;
        const dialogTitle = analysisDialog === "content" ? "Edit Core Requirement Details"
          : analysisDialog === "acceptance" ? "Edit Acceptance Criteria"
          : analysisDialog === "issues" ? "Analysis Issues & Missing Information"
          : analysisDialog === "classification" ? "Edit Requirement Classification"
          : analysisDialog === "systems" ? "Edit Impacted Systems"
          : "Request Clarification";
        return (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-950/40 p-4 backdrop-blur-sm" style={{ zIndex: 60 }} role="dialog" aria-modal="true" aria-label={dialogTitle} onClick={() => { if (!analysisDialogSaving) { setAnalysisDialogError(null); setAnalysisDialog(null); } }}>
            <form
              className="w-full max-w-lg rounded-2xl border border-gray-200 bg-white shadow-2xl"
              onClick={(event) => event.stopPropagation()}
              onSubmit={(event) => {
                event.preventDefault();
                void saveAnalysisDialog();
              }}
            >
              <div className="flex items-start justify-between border-b border-gray-100 px-5 py-4">
                <div><h3 className="text-sm font-bold text-gray-900">{dialogTitle}</h3><p className="mt-1 text-[11px] font-semibold text-gray-500">{selectedReq.requirement_id} · {selectedReq.title}</p></div>
                <button type="button" aria-label="Close dialog" onClick={() => { setAnalysisDialogError(null); setAnalysisDialog(null); }} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-50"><X className="h-4 w-4" /></button>
              </div>
              <div className="max-h-[65vh] space-y-4 overflow-y-auto px-5 py-4 text-xs">
                {analysisDialog === "content" && <>
                  <p className="font-semibold text-gray-600">Describe the requirement precisely. Include the actor, trigger, expected business outcome, constraints, and measurable scope.</p>
                  <label className="space-y-1.5"><span className="text-[10px] font-bold uppercase text-gray-500">Requirement summary</span><textarea aria-label="Requirement summary" value={summaryDraft} onChange={(event) => setSummaryDraft(event.target.value)} rows={6} className="w-full rounded-xl border border-gray-200 px-3 py-2 font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-app-brand-200" placeholder="When [trigger], the system shall [behavior] for [actor] so that [business outcome]..." /></label>
                  <label className="space-y-1.5"><span className="text-[10px] font-bold uppercase text-gray-500">Business rules - one per line</span><textarea aria-label="Business rules" value={businessRulesDraft} onChange={(event) => setBusinessRulesDraft(event.target.value)} rows={5} className="w-full rounded-xl border border-gray-200 px-3 py-2 font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-app-brand-200" placeholder="Billing changes take effect on the next billing cycle." /></label>
                  <label className="space-y-1.5"><span className="text-[10px] font-bold uppercase text-gray-500">Risks and constraints - one per line</span><textarea aria-label="Risks and constraints" value={risksDraft} onChange={(event) => setRisksDraft(event.target.value)} rows={4} className="w-full rounded-xl border border-gray-200 px-3 py-2 font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-app-brand-200" placeholder="Proration must not create duplicate charges." /></label>
                </>}
                {analysisDialog === "acceptance" && <>
                  <p className="font-semibold text-gray-600">Enter one independently testable acceptance criterion per line.</p>
                  <textarea aria-label="Acceptance criteria" value={criteriaDraft} onChange={(event) => setCriteriaDraft(event.target.value)} rows={10} className="w-full rounded-xl border border-gray-200 px-3 py-2 font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-app-brand-200" placeholder="The system shall..." />
                </>}
                {analysisDialog === "issues" && <>
                  <div className="grid grid-cols-4 gap-2">
                    {/* "Missing" counts only what blocks, but the list below shows
                        every gap — so a requirement with one blocking and one
                        advisory item read "1" above a list of two. The tile now
                        says which number it is. */}
                    {[["Blocking", analysisRow?.missingInfoCount || 0, `${missingInfoAdvisoryCount} advisory gap(s) are listed but do not block`], ["Findings", asTextList(selectedQualityReviews[0]?.ambiguities).length || asTextList(qualityMeta?.findings).length, "Ambiguities and conflicts raised by quality analysis"], ["Duplicates", analysisRow?.duplicateCount || 0, ""], ["Conflicts", analysisRow?.conflictCount || 0, ""]].map(([label, value, hint]) => <div key={String(label)} title={String(hint || "")} className="rounded-lg border border-gray-200 bg-gray-50 p-2"><div className="text-[9px] font-bold uppercase text-gray-400">{label}</div><div className="mt-1 text-lg font-bold text-gray-800">{value}</div></div>)}
                  </div>
                  {(asTextList(qualityMeta?.ambiguities).length > 0 || asTextList(qualityMeta?.conflicts).length > 0) && <div className="rounded-lg border border-amber-100 bg-amber-50 p-3"><div className="mb-1 text-[10px] font-bold uppercase text-amber-700">Other findings</div>{[...asTextList(qualityMeta?.ambiguities), ...asTextList(qualityMeta?.conflicts)].map((item) => <div key={item} className="mt-1 font-semibold text-amber-800">• {item}</div>)}</div>}
                  {missingInfoItems.length > 0 && (
                    <div className="rounded-lg border border-red-100 bg-red-50 p-3">
                      <div className="mb-2 text-[10px] font-bold uppercase text-red-700">
                        What is missing
                        {missingInfoAdvisoryCount > 0 && (
                          <span className="ml-1 font-semibold normal-case text-red-500">
                            ({analysisRow?.missingInfoCount || 0} blocking, {missingInfoAdvisoryCount} advisory)
                          </span>
                        )}
                      </div>
                      <ul className="space-y-1.5">
                        {missingInfoItems.map((item, index) => (
                          <li key={`${item}-${index}`} className="flex items-start gap-2 font-semibold leading-snug text-red-800">
                            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-500" />
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <div><label className="mb-1.5 block text-[10px] font-bold uppercase text-gray-500">Outstanding missing information - one item per line</label><textarea aria-label="Outstanding missing information" value={missingInfoDraft} onChange={(event) => { setMissingInfoDraft(event.target.value); setMarkMissingResolved(false); }} rows={5} className="w-full rounded-xl border border-red-200 bg-red-50/30 px-3 py-2 font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-red-100" placeholder="No missing information remains" /></div>
                  <div><label className="mb-1.5 block text-[10px] font-bold uppercase text-gray-500">{selectedReq.readiness_status === "needs_clarification" ? "Clarification supplied" : "Resolution or supplied details"}</label><textarea aria-label="Resolution details" value={resolutionDraft} onChange={(event) => setResolutionDraft(event.target.value)} rows={4} className="w-full rounded-xl border border-gray-200 px-3 py-2 font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-app-brand-200" placeholder={selectedReq.readiness_status === "needs_clarification" ? "Enter the answer/details provided by the requirement owner and where they were verified..." : "Describe the information supplied and where it was verified..."} /></div>
                  {selectedReq.readiness_status === "needs_clarification" ? <div className="rounded-lg border border-amber-100 bg-amber-50 p-2 text-[10px] font-semibold text-amber-800">Submitting this answer resolves the clarification gate and returns the requirement to Analysis Pending. Select Re-run Analysis afterward to validate it.</div> : <label className="flex items-start gap-2 rounded-lg border border-emerald-100 bg-emerald-50 p-3 font-semibold text-emerald-800"><input aria-label="Mark missing information resolved" type="checkbox" checked={markMissingResolved} onChange={(event) => setMarkMissingResolved(event.target.checked)} className="mt-0.5" /><span>Mark all listed missing-information findings as resolved. Resolution details are required and retained in reviewer notes.</span></label>}
                </>}
                {analysisDialog === "classification" && <div className="grid grid-cols-2 gap-3">
                  <ClassificationSelect label="Domain" value={classificationDraft.domain} options={domainOptions.map((entry) => entry.name)} onChange={(value) => setClassificationDraft((current) => ({ ...current, domain: value }))} />
                  <ClassificationSelect label="Journey / Business Process" value={classificationDraft.journey} options={businessProcessOptions.map((entry) => entry.name)} onChange={(value) => setClassificationDraft((current) => ({ ...current, journey: value }))} />
                  <ClassificationSelect label="Application / Product" value={classificationDraft.application} options={productOptions.map((entry) => entry.name)} onChange={(value) => setClassificationDraft((current) => ({ ...current, application: value }))} />
                  <ClassificationSelect label="Sub Request Type" value={classificationDraft.subRequestType} options={subRequestTypeOptions.map((entry) => entry.name)} onChange={(value) => setClassificationDraft((current) => ({ ...current, subRequestType: value }))} />
                  <ClassificationSelect label="Test Type / Phase" value={classificationDraft.testType} options={TEST_PHASE_OPTIONS} onChange={(value) => setClassificationDraft((current) => ({ ...current, testType: value }))} />
                  <ClassificationSelect label="Risk Level" value={classificationDraft.riskLevel} options={RISK_LEVEL_OPTIONS} onChange={(value) => setClassificationDraft((current) => ({ ...current, riskLevel: value }))} />
                </div>}
                {analysisDialog === "systems" && <>
                  <p className="font-semibold text-gray-600">Record systems, interfaces, and APIs separately so the reviewer can assess integration readiness.</p>
                  <label className="space-y-1.5"><span className="text-[10px] font-bold uppercase text-gray-500">Impacted systems - one per line</span><textarea aria-label="Impacted systems" value={systemsDraft} onChange={(event) => setSystemsDraft(event.target.value)} rows={5} className="w-full rounded-xl border border-gray-200 px-3 py-2 font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-app-brand-200" placeholder="Billing Platform&#10;CRM" /></label>
                  <label className="space-y-1.5"><span className="text-[10px] font-bold uppercase text-gray-500">Interfaces - one per line</span><textarea aria-label="Impacted interfaces" value={interfacesDraft} onChange={(event) => setInterfacesDraft(event.target.value)} rows={4} className="w-full rounded-xl border border-gray-200 px-3 py-2 font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-app-brand-200" placeholder="CRM to Billing customer update interface" /></label>
                  <label className="space-y-1.5"><span className="text-[10px] font-bold uppercase text-gray-500">APIs / protocols - one per line</span><textarea aria-label="APIs and protocols" value={apisDraft} onChange={(event) => setApisDraft(event.target.value)} rows={4} className="w-full rounded-xl border border-gray-200 px-3 py-2 font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-app-brand-200" placeholder="PATCH /customers/{id}/billing-profile (REST)" /></label>
                </>}
                {analysisDialog === "clarification" && <>
                  <div className="rounded-lg border border-app-brand-100 bg-app-brand-75 p-3 font-semibold text-app-brand-800">This records an audited clarification request and keeps the requirement in Analysis with “Needs Clarification” status. It does not send an external email or Jira message.</div>
                  <label className="space-y-1.5"><span className="text-[10px] font-bold uppercase text-gray-500">Clarification required</span><textarea aria-label="Clarification required" value={resolutionDraft} onChange={(event) => setResolutionDraft(event.target.value)} rows={7} className="w-full rounded-xl border border-gray-200 px-3 py-2 font-semibold text-gray-700 outline-none focus:ring-2 focus:ring-app-brand-200" placeholder="Explain exactly what information is required, who should provide it, and why analysis cannot proceed..." /></label>
                </>}
              </div>
              {analysisDialogError && (
                <div className="mx-5 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">
                  {analysisDialogError}
                </div>
              )}
              <div className="flex justify-end gap-2 border-t border-gray-100 px-5 py-4">
                <button
                  type="button"
                  disabled={analysisDialogSaving}
                  onClick={() => { setAnalysisDialogError(null); setAnalysisDialog(null); }}
                  className="inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 text-xs font-medium text-gray-700 transition-all hover:bg-gray-50 disabled:pointer-events-none disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={analysisDialogSaving}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    void saveAnalysisDialog();
                  }}
                  onPointerDown={(event) => {
                    event.preventDefault();
                    void saveAnalysisDialog();
                  }}
                  onClick={(event) => {
                    event.preventDefault();
                    void saveAnalysisDialog();
                  }}
                  className="inline-flex h-8 items-center justify-center gap-1.5 rounded-lg bg-[#B71920] px-3 text-xs font-medium text-white shadow-sm transition-all hover:bg-app-brand-700 disabled:pointer-events-none disabled:opacity-50"
                >
                  {analysisDialogSaving && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                  {analysisDialog === "clarification" ? "Submit Request" : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        );
      })(), document.querySelector("[data-requirement-drawer-content]") as Element)}

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
      <div className="flex h-64 items-center justify-center text-gray-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-[#B71920] mr-2" />
        Loading Requirements...
      </div>
    }>
      <RequirementsContent />
    </Suspense>
  );
}
