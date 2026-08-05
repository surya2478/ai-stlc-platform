"use client";

import { useState, useEffect, useCallback, useMemo, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  testPlansApi,
  requirementsApi,
  projectsApi,
  scenariosApi,
  agentRunsApi,
  reviewsApi,
  taxonomyApi,
  testCasesApi,
  usersApi,
  planTestCasesApi,
  type TestPlan,
  type Requirement,
  type Project,
  type TestScenario,
  type ArtifactReview,
  type TaxonomyEntry,
  type TestCase,
  type UserAccount,
  type PlanTestCaseEnrollment,
} from "@/lib/api";
import { ReviewBadge } from "@/components/reviews/ReviewBadge";
import {
  ClipboardList,
  Bot,
  CheckCircle,
  XCircle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Clock,
  AlertTriangle,
  Layers,
  Loader2,
  Download,
  FileText,
  Trash2,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { AuditStamp } from "@/components/ui/AuditStamp";
import { useUserDirectory } from "@/hooks/useUserDirectory";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAIAction } from "@/hooks/useAIAction";
import { AI_PROCESSING_STAGES } from "@/lib/ai-processing-stages";
import { terminalAIStatus } from "@/lib/ai-processing-status";

// ── Helpers ───────────────────────────────────────────────────────────────────

function getStatusVariant(status: string): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" {
  const s = status.toLowerCase();
  if (s === "approved" || s === "passed" || s === "completed") return "success";
  if (s === "rejected" || s === "failed") return "destructive";
  if (s === "pending_review" || s === "in_progress") return "warning";
  if (s === "draft") return "secondary";
  return "outline";
}

function PlanSection({ title, items }: { title: string; items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="space-y-1.5">
      <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{title}</h4>
      <ul className="text-xs space-y-1.5 font-semibold text-gray-700 bg-white border rounded-lg p-3">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="text-[#B71920] font-bold select-none mt-0.5">•</span>
            <span className="leading-relaxed">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

type AgentTriggerResponse = {
  message?: string;
  agent_run_id?: number;
  task_id?: string;
  test_plan_id?: string;
};

function getErrorMessage(err: unknown, fallback: string) {
  if (err instanceof Error && err.message === "Network Error") {
    return "Could not reach the backend API. Please check that http://localhost:8000 is running.";
  }

  if (err && typeof err === "object" && "response" in err) {
    const response = (err as { response?: { data?: { detail?: unknown; message?: unknown }; status?: number } })
      .response;
    const detail = response?.data?.detail ?? response?.data?.message;

    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object" && "msg" in item) {
            return String((item as { msg: unknown }).msg);
          }
          return JSON.stringify(item);
        })
        .join("; ");
    }
    if (detail && typeof detail === "object") return JSON.stringify(detail);
    if (response?.status === 401) return "Your session expired. Please log in again.";
    if (response?.status === 403) {
      return "You do not have permission to generate test planning artifacts for this project.";
    }
  }

  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

// ── PlanCard ──────────────────────────────────────────────────────────────────

function textList(value: unknown): string[] {
  if (!value) return [];
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean);
  return [String(value)].filter(Boolean);
}

function linkedRequirements(plan: TestPlan, requirementById?: Map<number, Requirement>) {
  const ids = textList(plan.metadata_?.source_requirement_ids).map((id) => Number(id)).filter(Number.isFinite);
  return ids.map((id) => requirementById?.get(id)).filter((req): req is Requirement => Boolean(req));
}

function planItems(plan: TestPlan, key: keyof TestPlan, linked: Requirement[]): string[] {
  const existing = textList(plan[key]);
  if (existing.length > 0) return existing;
  if (key === "scope") {
    return linked.map((req) => `${req.requirement_id || `REQ-${req.id}`}: ${req.title}${req.summary ? ` - ${req.summary}` : ""}`);
  }
  if (key === "entry_criteria") {
    return [
      "Approved requirements are baselined and available for test design.",
      ...linked.flatMap((req) =>
        textList(req.acceptance_criteria).map((item) => `${req.requirement_id || `REQ-${req.id}`}: Acceptance criterion available - ${item}`),
      ),
    ];
  }
  if (key === "exit_criteria" && linked.length > 0) {
    return [
      "All planned functional, regression, and risk-based tests are executed.",
      "Critical and high severity defects are resolved or formally accepted.",
      "Traceability from requirements to test scenarios and test cases is complete.",
    ];
  }
  if (key === "test_types" && linked.length > 0) return ["Functional", "Regression", "Integration", "Security", "User Acceptance"];
  if (key === "risks") {
    return linked.flatMap((req) => textList(req.risks).map((risk) => `${req.requirement_id || `REQ-${req.id}`}: ${risk}`));
  }
  if (key === "mitigations" && linked.length > 0) {
    return ["Prioritize high-risk requirements and validate acceptance criteria before execution."];
  }
  if (key === "automation_candidates") {
    return linked.map((req) => `${req.requirement_id || `REQ-${req.id}`}: Regression coverage for ${req.title}`);
  }
  if (key === "out_of_scope" && linked.length > 0) return ["Items not covered by the selected approved requirements."];
  return [];
}

function markdownList(items: string[]) {
  return items.length > 0 ? items.map((item) => `- ${item}`).join("\n") : "N/A";
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
    } catch (err) {
      setError(getErrorMessage(err, "Delete failed. Please try again."));
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
          <button onClick={onCancel} className="rounded-md p-1 hover:bg-gray-50 text-gray-400 shrink-0" title="Close">
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
            {deleting ? "Deleting..." : "Delete"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Plan Test Case Enrollment ────────────────────────────────────────────────
// UAT template's plan-time Environment / Tester / Planned Execution Sequence,
// backed by plan_test_cases (migration 042). Loaded lazily when the plan card
// is expanded.

function PlanEnrollmentPanel({ plan }: { plan: TestPlan }) {
  const [enrollments, setEnrollments] = useState<PlanTestCaseEnrollment[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [environments, setEnvironments] = useState<TaxonomyEntry[]>([]);
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addTestCaseId, setAddTestCaseId] = useState("");
  const [adding, setAdding] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    Promise.all([
      planTestCasesApi.list(plan.id),
      testCasesApi.list(plan.project_id),
      taxonomyApi.environments(true),
      usersApi.list({ project_id: plan.project_id }),
    ])
      .then(([enrollRes, tcRes, envRes, userRes]) => {
        setEnrollments(enrollRes.data);
        setTestCases(tcRes.data);
        setEnvironments(envRes.data);
        setUsers(userRes.data);
      })
      .catch(() => setError("Could not load test case enrollments."))
      .finally(() => setLoading(false));
  }, [plan.id, plan.project_id]);

  useEffect(() => { load(); }, [load]);

  const enrolledIds = new Set(enrollments.map((e) => e.test_case_id));
  const availableTestCases = testCases.filter((tc) => !enrolledIds.has(tc.id));

  async function addEnrollment() {
    if (!addTestCaseId) return;
    setAdding(true);
    setError("");
    try {
      await planTestCasesApi.enroll(plan.id, { test_case_id: Number(addTestCaseId) });
      setAddTestCaseId("");
      load();
    } catch {
      setError("Could not enroll that test case.");
    } finally {
      setAdding(false);
    }
  }

  async function updateEnrollment(enrollmentId: number, patch: { environment_id?: number | null; tester_user_id?: number | null; planned_execution_sequence?: string | null }) {
    try {
      await planTestCasesApi.update(plan.id, enrollmentId, patch);
      load();
    } catch {
      setError("Could not update the enrollment.");
    }
  }

  async function removeEnrollment(enrollmentId: number) {
    try {
      await planTestCasesApi.remove(plan.id, enrollmentId);
      load();
    } catch {
      setError("Could not remove that test case from the plan.");
    }
  }

  return (
    <div className="space-y-2.5">
      <h4 className="text-xs font-bold text-gray-800 uppercase tracking-wider flex items-center gap-1.5">
        <ClipboardList className="h-4 w-4 text-[#B71920]" />
        Enrolled Test Cases ({enrollments.length})
      </h4>
      {error && <p className="text-[11px] font-semibold text-rose-600">{error}</p>}
      {loading ? (
        <p className="text-xs font-medium text-gray-400">Loading enrollments…</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="w-full min-w-[640px] text-[11px]">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/70 text-left text-[9px] font-extrabold uppercase tracking-wide text-gray-500">
                <th className="px-3 py-2">Test Case</th>
                <th className="px-3 py-2">Environment</th>
                <th className="px-3 py-2">Tester</th>
                <th className="px-3 py-2">Planned Execution Sequence</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {enrollments.length === 0 ? (
                <tr><td colSpan={5} className="px-3 py-4 text-center text-gray-400">No test cases enrolled in this plan yet.</td></tr>
              ) : enrollments.map((e) => (
                <tr key={e.id} className="border-b border-gray-50 last:border-0">
                  <td className="px-3 py-2 font-mono font-bold text-[#B71920]">
                    {e.test_case_display_id || e.test_case_id}
                    <span className="ml-1 font-sans font-medium text-gray-500">{e.test_case_title}</span>
                  </td>
                  <td className="px-3 py-2">
                    <select
                      value={e.environment_id ?? ""}
                      onChange={(ev) => updateEnrollment(e.id, { environment_id: ev.target.value ? Number(ev.target.value) : null })}
                      className="h-8 rounded-md border border-gray-200 bg-white px-2 text-[11px] font-semibold text-gray-700"
                    >
                      <option value="">—</option>
                      {environments.map((env) => <option key={env.id} value={env.id}>{env.name}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <select
                      value={e.tester_user_id ?? ""}
                      onChange={(ev) => updateEnrollment(e.id, { tester_user_id: ev.target.value ? Number(ev.target.value) : null })}
                      className="h-8 rounded-md border border-gray-200 bg-white px-2 text-[11px] font-semibold text-gray-700"
                    >
                      <option value="">—</option>
                      {users.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <input
                      defaultValue={e.planned_execution_sequence ?? ""}
                      placeholder="e.g. Day 1"
                      onBlur={(ev) => {
                        if (ev.target.value !== (e.planned_execution_sequence ?? "")) {
                          updateEnrollment(e.id, { planned_execution_sequence: ev.target.value || null });
                        }
                      }}
                      className="h-8 w-32 rounded-md border border-gray-200 bg-white px-2 text-[11px] font-semibold text-gray-700"
                    />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => removeEnrollment(e.id)} className="rounded-md p-1 text-gray-400 hover:bg-rose-50 hover:text-rose-600">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center gap-2 border-t border-gray-100 px-3 py-2">
            <select
              value={addTestCaseId}
              onChange={(ev) => setAddTestCaseId(ev.target.value)}
              className="h-8 flex-1 rounded-md border border-gray-200 bg-white px-2 text-[11px] font-semibold text-gray-700"
            >
              <option value="">Select a test case to enroll…</option>
              {availableTestCases.map((tc) => <option key={tc.id} value={tc.id}>{tc.test_case_id} — {tc.title}</option>)}
            </select>
            <Button
              onClick={addEnrollment}
              disabled={!addTestCaseId || adding}
              size="sm"
              className="h-8 bg-[#B71920] text-xs font-bold text-white hover:bg-[#941216]"
            >
              {adding ? "Adding…" : "Add"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function PlanCard({
  plan,
  onApprove,
  onReject,
  onDelete,
  resolveUser,
  requirementLabelById,
  requirementById,
}: {
  plan: TestPlan;
  onApprove: (id: number) => void;
  onReject: (id: number, notes: string) => void;
  onDelete: (plan: TestPlan) => void;
  resolveUser: (id?: number) => string;
  requirementLabelById?: Map<number, string>;
  requirementById?: Map<number, Requirement>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [notes, setNotes] = useState("");
  const [showExportMenu, setShowExportMenu] = useState(false);

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const exportPlanAsMarkdown = (p: TestPlan) => {
    const linked = linkedRequirements(p, requirementById);
    const coveredRequirements = linked.length > 0
      ? linked.map((req) => {
          const ref = req.requirement_id || `REQ-${req.id}`;
          const lines = [`### ${ref}: ${req.title}`];
          if (req.summary) lines.push(req.summary);
          const acceptance = textList(req.acceptance_criteria);
          if (acceptance.length) lines.push("", "**Acceptance Criteria**", markdownList(acceptance));
          const rules = textList(req.business_rules);
          if (rules.length) lines.push("", "**Business Rules**", markdownList(rules));
          const risks = textList(req.risks);
          if (risks.length) lines.push("", "**Requirement Risks**", markdownList(risks));
          return lines.join("\n");
        }).join("\n\n")
      : "N/A";
    const content = `# Test Plan: ${p.title} (${p.test_plan_id})

**Status:** ${p.status.toUpperCase()}
**Estimated Effort:** ${p.estimated_effort || "N/A"}
**Resource Recommendation:** ${p.resource_recommendation || "N/A"}
**Created At:** ${new Date(p.created_at).toLocaleString()}

## Covered Requirements
${coveredRequirements}

## Scope
${markdownList(planItems(p, "scope", linked))}

## Out of Scope
${markdownList(planItems(p, "out_of_scope", linked))}

## Test Types
${markdownList(planItems(p, "test_types", linked))}

## Entry Criteria
${markdownList(planItems(p, "entry_criteria", linked))}

## Exit Criteria
${markdownList(planItems(p, "exit_criteria", linked))}

## Risks
${markdownList(planItems(p, "risks", linked))}

## Mitigations
${markdownList(planItems(p, "mitigations", linked))}

## Automation Candidates
${markdownList(planItems(p, "automation_candidates", linked))}
`;
    downloadBlob(new Blob([content], { type: "text/markdown" }), `test_plan_${p.test_plan_id}.md`);
  };

  const exportPlanAsJson = (p: TestPlan) => {
    const linked = linkedRequirements(p, requirementById);
    const content = JSON.stringify({
      ...p,
      covered_requirements: linked,
      export_sections: {
        scope: planItems(p, "scope", linked),
        out_of_scope: planItems(p, "out_of_scope", linked),
        test_types: planItems(p, "test_types", linked),
        entry_criteria: planItems(p, "entry_criteria", linked),
        exit_criteria: planItems(p, "exit_criteria", linked),
        risks: planItems(p, "risks", linked),
        mitigations: planItems(p, "mitigations", linked),
        automation_candidates: planItems(p, "automation_candidates", linked),
      },
    }, null, 2);
    downloadBlob(new Blob([content], { type: "application/json" }), `test_plan_${p.test_plan_id}.json`);
  };

  const exportPlanAsDocx = async (planId: number, testPlanId: string) => {
    try {
      const res = await testPlansApi.exportDocx(planId);
      downloadBlob(res.data as unknown as Blob, `test_plan_${testPlanId}.docx`);
    } catch (err) {
      console.error("Failed to export docx:", err);
      alert("Failed to export to DOCX. Please verify you have required permissions.");
    }
  };

  return (
    <Card className={cn(
      "border-gray-200 overflow-hidden hover:shadow-sm transition-all",
      expanded && "border-gray-350 shadow-sm"
    )}>
      {/* Header row */}
      <div
        className="flex items-center justify-between gap-4 px-4 py-3.5 cursor-pointer hover:bg-gray-50/50 transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="rounded-lg bg-app-brand-75 border border-app-brand-100 p-2 shrink-0">
            <ClipboardList className="h-4 w-4 text-[#B71920]" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] font-mono font-bold text-[#B71920] bg-app-brand-75 border border-app-brand-100 px-1.5 py-0.5 rounded">
                {plan.test_plan_id}
              </span>
              <span className="font-bold text-gray-800 text-sm truncate">{plan.title}</span>
            </div>
            <div className="flex items-center gap-2.5 mt-1 flex-wrap">
              <Badge variant={getStatusVariant(plan.status)} className="capitalize">
                {plan.status.replace(/_/g, " ")}
              </Badge>
              {plan.estimated_effort && (
                <span className="text-[10px] text-gray-400 font-bold flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  {plan.estimated_effort}
                </span>
              )}
              <AuditStamp
                createdAt={plan.created_at}
                updatedAt={plan.updated_at}
                createdByName={resolveUser(plan.created_by ?? undefined)}
                compact
              />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          {(plan.status === "draft" || plan.status === "pending_review") && (
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setApproving((v) => !v);
                  setRejecting(false);
                }}
                className={cn(
                  "h-8 px-2 border-emerald-250 text-emerald-600 hover:bg-emerald-50 bg-white",
                  approving && "bg-emerald-50 border-emerald-400"
                )}
                title="Approve"
              >
                <CheckCircle className="h-4 w-4 mr-1 text-emerald-600" />
                Approve
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setRejecting((v) => !v);
                  setApproving(false);
                }}
                className={cn(
                  "h-8 px-2 border-rose-250 text-rose-600 hover:bg-rose-50 bg-white",
                  rejecting && "bg-rose-50 border-rose-400"
                )}
                title="Reject"
              >
                <XCircle className="h-4 w-4 mr-1 text-rose-600" />
                Reject
              </Button>
            </div>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => onDelete(plan)}
            className="h-8 w-8 p-0 border-rose-200 text-rose-600 hover:bg-rose-50 bg-white"
            title="Delete test plan"
            aria-label="Delete test plan"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>

          {/* Export Dropdown */}
          <div className="relative">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowExportMenu((v) => !v)}
              className="h-8 border-gray-200 text-gray-700 hover:bg-gray-50 bg-white text-xs font-semibold"
            >
              <Download className="h-3.5 w-3.5 mr-1" />
              Export
            </Button>
            {showExportMenu && (
              <>
                <div className="fixed inset-0 z-30" onClick={() => setShowExportMenu(false)} />
                <div className="absolute right-0 mt-1.5 w-40 bg-white border border-gray-200 rounded-xl shadow-lg py-1.5 z-40 animate-in fade-in slide-in-from-top-2 duration-100">
                  <button
                    onClick={() => {
                      exportPlanAsMarkdown(plan);
                      setShowExportMenu(false);
                    }}
                    className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 font-semibold flex items-center gap-1.5"
                  >
                    <FileText className="h-3.5 w-3.5 text-app-brand-500" />
                    As Markdown
                  </button>
                  <button
                    onClick={() => {
                      exportPlanAsJson(plan);
                      setShowExportMenu(false);
                    }}
                    className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 font-semibold flex items-center gap-1.5"
                  >
                    <FileText className="h-3.5 w-3.5 text-amber-500" />
                    As JSON
                  </button>
                  <button
                    onClick={() => {
                      exportPlanAsDocx(plan.id, plan.test_plan_id);
                      setShowExportMenu(false);
                    }}
                    className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 font-semibold flex items-center gap-1.5"
                  >
                    <FileText className="h-3.5 w-3.5 text-emerald-500" />
                    As Word (.docx)
                  </button>
                </div>
              </>
            )}
          </div>
          
          <button 
            onClick={() => setExpanded((e) => !e)}
            className="rounded-md p-1.5 hover:bg-gray-100 text-gray-400 shrink-0"
          >
            {expanded ? (
              <ChevronUp className="h-4.5 w-4.5 text-gray-500" />
            ) : (
              <ChevronDown className="h-4.5 w-4.5 text-gray-500" />
            )}
          </button>
        </div>
      </div>

      {/* Approve/Reject panel */}
      {(approving || rejecting) && (
        <div className="px-4 py-3 border-t border-gray-100 bg-gray-50/50 space-y-2.5 animate-in fade-in duration-100">
          <textarea
            placeholder={approving ? "Add optional review comments/notes..." : "Explain the reason for rejecting this test plan (required)..."}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full text-xs border border-gray-200 rounded-lg p-2.5 resize-none focus:outline-none focus:ring-2 focus:ring-[#B71920] bg-white font-semibold text-gray-700"
            rows={2}
          />
          <div className="flex gap-2">
            <Button
              onClick={() => {
                if (approving) onApprove(plan.id);
                else onReject(plan.id, notes);
                setApproving(false);
                setRejecting(false);
                setNotes("");
              }}
              variant="default"
              className={cn(
                "h-8 text-xs font-bold text-white",
                approving ? "bg-emerald-600 hover:bg-emerald-700" : "bg-rose-600 hover:bg-rose-700"
              )}
            >
              {approving ? "Confirm Approval" : "Confirm Rejection"}
            </Button>
            <Button
              onClick={() => {
                setApproving(false);
                setRejecting(false);
                setNotes("");
              }}
              variant="outline"
              className="h-8 text-xs font-semibold bg-white border-gray-200 text-gray-505"
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-gray-100 px-5 py-4 bg-gray-50/10 space-y-4 animate-in fade-in duration-150">
          {/* Covered Requirements and High Level Metadata */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
            <div className="space-y-2.5">
              <h4 className="text-xs font-bold text-gray-800 uppercase tracking-wider flex items-center gap-1.5">
                <ClipboardList className="h-4 w-4 text-[#B71920]" />
                High-Level Details
              </h4>
              <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                <div>
                  <span className="text-gray-400 font-bold block">Estimated Effort</span>
                  <span className="font-semibold text-gray-700">{plan.estimated_effort || "Not Specified"}</span>
                </div>
                <div>
                  <span className="text-gray-400 font-bold block">Resource Recommendation</span>
                  <span className="font-semibold text-gray-700">{plan.resource_recommendation || "Not Specified"}</span>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <h4 className="text-xs font-bold text-gray-800 uppercase tracking-wider flex items-center gap-1.5">
                <Layers className="h-4 w-4 text-[#B71920]" />
                Covered Requirements
              </h4>
              {plan.metadata_?.source_requirement_ids && plan.metadata_.source_requirement_ids.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {plan.metadata_.source_requirement_ids.map((reqId: number) => {
                    const label = requirementLabelById?.get(reqId);
                    return (
                      <span key={reqId} className="text-[10px] font-mono font-bold text-[#B71920] bg-app-brand-75 border border-app-brand-100 px-2 py-0.5 rounded-md">
                        {label || `REQ-${reqId}`}
                      </span>
                    );
                  })}
                </div>
              ) : (
                <span className="text-xs text-gray-400 font-medium">No linked requirements</span>
              )}
            </div>
          </div>

          {/* Standard sections */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
            <div className="space-y-4">
              <PlanSection title="Scope" items={plan.scope} />
              <PlanSection title="Out of Scope" items={plan.out_of_scope} />
              <PlanSection title="Test Types" items={plan.test_types} />
              <PlanSection title="Entry Criteria" items={plan.entry_criteria} />
              <PlanSection title="Exit Criteria" items={plan.exit_criteria} />
            </div>
            <div className="space-y-4">
              <PlanSection title="Risks" items={plan.risks} />
              <PlanSection title="Mitigations" items={plan.mitigations} />
              <PlanSection title="Automation Candidates" items={plan.automation_candidates} />
            </div>
          </div>

          <PlanEnrollmentPanel plan={plan} />
        </div>
      )}
    </Card>
  );
}


function ScenarioCard({
  scenario,
  requirementLabelById,
  getStatusVariant,
  onApprove,
  onReject,
  resolveUser,
  review,
  projectId,
}: {
  scenario: TestScenario;
  requirementLabelById: Map<number, string>;
  getStatusVariant: (status: string) => string;
  onApprove: (id: number) => void;
  onReject: (id: number, notes: string) => void;
  resolveUser: (id?: number) => string;
  review?: ArtifactReview;
  projectId: number;
}) {
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [notes, setNotes] = useState("");

  return (
    <div className="px-4 py-3.5 hover:bg-gray-50/30 transition-colors font-medium">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <div className="rounded-lg bg-purple-50 border border-purple-100 p-2 shrink-0">
            <Layers className="h-4 w-4 text-purple-600" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="font-mono text-[10px] font-bold text-gray-450">{scenario.scenario_id}</span>
              {scenario.requirement_id && (
                <span className="text-[10px] font-mono font-bold text-[#B71920] bg-[#B71920]/5 border border-[#B71920]/10 px-1.5 py-0.5 rounded shrink-0">
                  {requirementLabelById.get(scenario.requirement_id) ?? `REQ-${scenario.requirement_id}`}
                </span>
              )}
              <Badge variant={getStatusVariant(scenario.status) as any} className="capitalize">
                {scenario.status.replace(/_/g, " ")}
              </Badge>
              {scenario.requirement_id && (
                <ReviewBadge
                  review={review}
                  artifactType="requirement_scenario_coverage"
                  artifactId={scenario.requirement_id}
                  projectId={projectId}
                />
              )}
              {scenario.scenario_type && (
                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider bg-gray-50 border px-1.5 py-0.5 rounded shrink-0">
                  {scenario.scenario_type}
                </span>
              )}
              {scenario.priority && (
                <span className={cn(
                  "text-[10px] font-bold uppercase tracking-wider border px-1.5 py-0.5 rounded shrink-0",
                  scenario.priority.toLowerCase() === "high" ? "border-rose-100 bg-rose-50 text-rose-600" :
                  scenario.priority.toLowerCase() === "medium" ? "border-amber-100 bg-amber-50 text-amber-600" :
                  "border-gray-100 bg-gray-50 text-gray-600"
                )}>
                  {scenario.priority}
                </span>
              )}
              <AuditStamp
                createdAt={scenario.created_at}
                updatedAt={scenario.updated_at}
                createdByName={resolveUser(scenario.created_by ?? undefined)}
                compact
              />
            </div>
            <h3 className="font-bold text-gray-800 text-sm mt-1.5">{scenario.title}</h3>
            {scenario.description && (
              <p className="text-xs text-gray-500 mt-1 leading-relaxed font-semibold">{scenario.description}</p>
            )}
            
            {/* Show review notes if present in metadata */}
            {scenario.metadata_?.review_notes && (
              <div className="mt-2 text-[10px] font-semibold bg-gray-50 border rounded p-2 text-gray-550 leading-normal">
                <span className="font-bold text-gray-700 block mb-0.5">Review Notes:</span>
                {scenario.metadata_.review_notes}
              </div>
            )}
          </div>
        </div>

        {/* Approval buttons */}
        {(scenario.status === "draft" || scenario.status === "pending_review") && (
          <div className="flex items-center gap-1 shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setApproving((v) => !v);
                setRejecting(false);
              }}
              className={cn(
                "h-8 px-2 border-emerald-250 text-emerald-600 hover:bg-emerald-50 bg-white",
                approving && "bg-emerald-50 border-emerald-400"
              )}
              title="Approve"
            >
              <CheckCircle className="h-4 w-4 mr-1 text-emerald-600" />
              Approve
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setRejecting((v) => !v);
                setApproving(false);
              }}
              className={cn(
                "h-8 px-2 border-rose-250 text-rose-600 hover:bg-rose-50 bg-white",
                rejecting && "bg-rose-50 border-rose-400"
              )}
              title="Reject"
            >
              <XCircle className="h-4 w-4 mr-1 text-rose-600" />
              Reject
            </Button>
          </div>
        )}
      </div>

      {/* Approve/Reject notes panel */}
      {(approving || rejecting) && (
        <div className="mt-3 py-3 border-t border-gray-100 bg-gray-50/50 space-y-2.5 animate-in fade-in duration-100 rounded-lg px-3">
          <textarea
            placeholder={approving ? "Add optional review comments/notes..." : "Explain the reason for rejecting this test scenario (required)..."}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full text-xs border border-gray-200 rounded-lg p-2.5 resize-none focus:outline-none focus:ring-2 focus:ring-[#B71920] bg-white font-semibold text-gray-700"
            rows={2}
          />
          <div className="flex gap-2">
            <Button
              onClick={() => {
                if (approving) onApprove(scenario.id);
                else {
                  if (!notes.trim()) {
                    alert("Rejection notes are required.");
                    return;
                  }
                  onReject(scenario.id, notes);
                }
                setApproving(false);
                setRejecting(false);
                setNotes("");
              }}
              variant="default"
              className={cn(
                "h-8 text-xs font-bold text-white",
                approving ? "bg-emerald-600 hover:bg-emerald-700" : "bg-rose-600 hover:bg-rose-700"
              )}
            >
              {approving ? "Confirm Approval" : "Confirm Rejection"}
            </Button>
            <Button
              onClick={() => {
                setApproving(false);
                setRejecting(false);
                setNotes("");
              }}
              variant="outline"
              className="h-8 text-xs font-semibold bg-white border-gray-200 text-gray-505"
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Content Component ───────────────────────────────────────────────────

function TestPlanningContent() {
  const { runAIAction, updateAIProcessing } = useAIAction();
  const { resolveUser } = useUserDirectory();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProject = Number(searchParams.get("project")) || null;

  const [projects, setProjects] = useState<Project[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [plans, setPlans] = useState<TestPlan[]>([]);
  const [scenarios, setScenarios] = useState<TestScenario[]>([]);
  const [scenarioReviews, setScenarioReviews] = useState<ArtifactReview[]>([]);
  const [loading, setLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState<string | null>(null);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [selectedReqIds, setSelectedReqIds] = useState<number[]>([]);
  const [showAgentPanel, setShowAgentPanel] = useState(false);
  const [showScenariosExportMenu, setShowScenariosExportMenu] = useState(false);
  const [deletingPlan, setDeletingPlan] = useState<TestPlan | null>(null);

  // Load projects on mount
  useEffect(() => {
    projectsApi.list().then((r) => {
      setProjects(r.data);
      if (r.data.length > 0 && !searchParams.get("project")) {
        const params = new URLSearchParams(searchParams.toString());
        params.set("project", String(r.data[0].id));
        router.push(`${pathname}?${params.toString()}`);
      }
    });
  }, [searchParams, pathname, router]);

  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const [plansRes, reqsRes, scenariosRes, reviewsRes] = await Promise.all([
        testPlansApi.list(selectedProject),
        requirementsApi.list(selectedProject, { status: "approved" }),
        scenariosApi.list(selectedProject),
        reviewsApi.listForProject(selectedProject, "requirement_scenario_coverage"),
      ]);
      setPlans(plansRes.data);
      setRequirements(reqsRes.data);
      setScenarios(scenariosRes.data);
      setScenarioReviews(reviewsRes.data);
    } catch (err) {
      console.error("Could not load test planning details:", err);
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    const availableIds = new Set(requirements.map((req) => req.id));
    setSelectedReqIds((prev) => prev.filter((id) => availableIds.has(id)));
  }, [requirements]);

  const toggleReq = (id: number) => {
    setSelectedReqIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const pollAgentRun = async (
    runId: number,
    completedMessage: string,
    failedFallback: string
  ) => {
    while (true) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      const run = (await agentRunsApi.get(runId)).data;

      const terminalStatus = terminalAIStatus(run.status);
      if (terminalStatus) {
        const message = run.error_message || failedFallback;
        setAgentStatus(null);
        updateAIProcessing({ status: terminalStatus, currentStage: run.status, errorCategory: "AI processing failed", errorMessage: message });
        throw new Error(message);
      }

      if (run.progress_message) {
        setAgentStatus(`${run.progress_message} (${run.progress_percent ?? 0}%)`);
        updateAIProcessing({ status: "processing", currentStage: run.progress_message });
      }

      if (run.status === "completed") {
        setAgentStatus(completedMessage);
        await loadData();
        return;
      }

    }

  };

  const handleGeneratePlan = async () => {
    if (!selectedProject || selectedReqIds.length === 0) return;
    setAgentStatus("Generating test plan...");
    setAgentError(null);
    try {
      await runAIAction({
        actionName: "generate_test_plan",
        title: "Generating Test Plan",
        module: "Test Planning",
        artifactType: "Test Plan",
        projectId: selectedProject,
        stages: AI_PROCESSING_STAGES.testPlanning,
        successMessage: "Test plan generated successfully.",
        execute: async () => {
      const res = await testPlansApi.generatePlan(selectedProject, selectedReqIds);
      const data = res.data as AgentTriggerResponse;
      if (data.agent_run_id) {
        updateAIProcessing({ status: "waiting", agentRunId: String(data.agent_run_id), currentStage: data.message ?? "Waiting for the test-planning agent" });
        setAgentStatus(data.message ?? "Test plan generation queued.");
        await pollAgentRun(data.agent_run_id, "Test plan generated successfully.", "Test plan generation failed.");
      } else {
        setAgentStatus(`Test plan ${data.test_plan_id ?? ""} created successfully.`.trim());
        await loadData();
      }
      return res;
        },
      });
    } catch (err: unknown) {
      setAgentError(getErrorMessage(err, "Failed to generate test plan"));
      setAgentStatus(null);
    }
  };

  // GAP-4c: detect quality-gate blocks and let the user consciously override
  const isQualityGateBlock = (err: unknown): { message: string } | null => {
    const detail = (err as { response?: { status?: number; data?: { detail?: unknown } } })?.response?.data?.detail;
    if (
      detail &&
      typeof detail === "object" &&
      (detail as { code?: string }).code === "quality_gate_blocked"
    ) {
      const d = detail as { message?: string; blocked_requirements?: Array<{ requirement_id?: string; title?: string; reasons?: string[] }> };
      const lines = (d.blocked_requirements ?? [])
        .map((b) => `• ${b.requirement_id ?? ""} ${b.title ?? ""}: ${(b.reasons ?? []).join(", ")}`)
        .join("\n");
      return { message: `${d.message ?? "Some requirements failed the quality gate."}\n\n${lines}` };
    }
    return null;
  };

  const handleGenerateScenarios = async (overrideQualityGate = false) => {
    if (!selectedProject || selectedReqIds.length === 0) return;
    setAgentStatus("Generating test scenarios...");
    setAgentError(null);
    try {
      await runAIAction({
        actionName: "generate_test_scenarios",
        title: "Generating Test Scenarios",
        module: "Test Planning",
        artifactType: "Test Scenarios",
        projectId: selectedProject,
        stages: AI_PROCESSING_STAGES.testCaseGeneration,
        successMessage: "Test scenarios generated successfully.",
        execute: async () => {
      const res = await testPlansApi.generateScenarios(selectedProject, selectedReqIds, overrideQualityGate);
      const data = res.data as AgentTriggerResponse;
      if (data.agent_run_id) {
        updateAIProcessing({ status: "waiting", agentRunId: String(data.agent_run_id), currentStage: data.message ?? "Waiting for the scenario agent" });
        setAgentStatus(data.message ?? "Test scenario generation queued.");
        await pollAgentRun(
          data.agent_run_id,
          "Test scenarios generated successfully.",
          "Test scenario generation failed."
        );
      } else {
        setAgentStatus(data.message ?? "Scenarios generated successfully.");
        await loadData();
      }
      return res;
        },
      });
    } catch (err: unknown) {
      const gateBlock = isQualityGateBlock(err);
      if (gateBlock && !overrideQualityGate) {
        setAgentStatus(null);
        const proceed = window.confirm(
          `${gateBlock.message}\n\nGenerate anyway? Test scenarios from low-quality requirements may be generic or incomplete.`
        );
        if (proceed) {
          await handleGenerateScenarios(true);
        } else {
          setAgentError("Generation blocked by quality gate. Improve the requirement(s) and re-run the AI quality review.");
        }
        return;
      }
      setAgentError(getErrorMessage(err, "Failed to generate scenarios"));
      setAgentStatus(null);
    }
  };

  const handleApprove = async (planId: number) => {
    await testPlansApi.approve(planId, "approve");
    await loadData();
  };

  const handleReject = async (planId: number, notes: string) => {
    await testPlansApi.approve(planId, "reject", notes);
    await loadData();
  };

  const handleDeletePlan = async () => {
    if (!deletingPlan) return;
    await testPlansApi.delete(deletingPlan.id);
    setDeletingPlan(null);
    await loadData();
  };

  const handleApproveScenario = async (scenarioId: number) => {
    try {
      await scenariosApi.approve(scenarioId, "approve");
      await loadData();
    } catch (err) {
      setAgentError(getErrorMessage(err, "Failed to approve scenario"));
    }
  };

  const handleRejectScenario = async (scenarioId: number, notes: string) => {
    try {
      await scenariosApi.approve(scenarioId, "reject", notes);
      await loadData();
    } catch (err) {
      setAgentError(getErrorMessage(err, "Failed to reject scenario"));
    }
  };

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const exportScenariosAsMarkdown = () => {
    const projectName = projects.find((p) => p.id === selectedProject)?.name ?? `Project ${selectedProject}`;
    const lines: string[] = [];
    lines.push(`# Test Scenarios Catalog — ${projectName}`);
    lines.push("");
    lines.push(`**Total Scenarios:** ${scenarios.length}`);
    lines.push(`**Exported At:** ${new Date().toLocaleString()}`);
    lines.push("");

    scenarios.forEach((s) => {
      const reqLabel = s.requirement_id
        ? requirementLabelById.get(s.requirement_id) ?? `REQ-${s.requirement_id}`
        : "Unlinked";
      lines.push(`## ${s.scenario_id} — ${s.title}`);
      lines.push("");
      lines.push(`- **Requirement:** ${reqLabel}`);
      lines.push(`- **Status:** ${s.status.replace(/_/g, " ").toUpperCase()}`);
      if (s.scenario_type) lines.push(`- **Type:** ${s.scenario_type}`);
      if (s.priority) lines.push(`- **Priority:** ${s.priority}`);
      lines.push(`- **Created At:** ${new Date(s.created_at).toLocaleString()}`);
      lines.push(`- **Created By:** ${resolveUser(s.created_by ?? undefined)}`);
      if (s.description) {
        lines.push("");
        lines.push("### Description");
        lines.push(s.description);
      }
      if (s.coverage_mapping && s.coverage_mapping.length > 0) {
        lines.push("");
        lines.push("### Coverage Mapping");
        s.coverage_mapping.forEach((c) => lines.push(`- ${c}`));
      }
      lines.push("");
      lines.push("---");
      lines.push("");
    });

    const filename = `test_scenarios_${projectName.replace(/\s+/g, "_")}_${new Date().toISOString().slice(0, 10)}.md`;
    downloadBlob(new Blob([lines.join("\n")], { type: "text/markdown" }), filename);
  };

  const exportScenariosAsJson = () => {
    const projectName = projects.find((p) => p.id === selectedProject)?.name ?? `Project ${selectedProject}`;
    const payload = {
      project: projectName,
      project_id: selectedProject,
      exported_at: new Date().toISOString(),
      total: scenarios.length,
      scenarios,
    };
    const filename = `test_scenarios_${projectName.replace(/\s+/g, "_")}_${new Date().toISOString().slice(0, 10)}.json`;
    downloadBlob(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }), filename);
  };

  const scenarioExportRows = () =>
    scenarios.map((s) => {
      const reqLabel = s.requirement_id
        ? requirementLabelById.get(s.requirement_id) ?? `REQ-${s.requirement_id}`
        : "Unlinked";
      return {
        scenario_id: s.scenario_id,
        title: s.title,
        requirement: reqLabel,
        status: s.status.replace(/_/g, " "),
        type: s.scenario_type ?? "",
        priority: s.priority ?? "",
        description: s.description ?? "",
        coverage_mapping: (s.coverage_mapping ?? []).join("; "),
        created_at: new Date(s.created_at).toLocaleString(),
        created_by: resolveUser(s.created_by ?? undefined),
      };
    });

  const exportScenariosAsCsv = () => {
    const projectName = projects.find((p) => p.id === selectedProject)?.name ?? `Project ${selectedProject}`;
    const headers = [
      "Scenario ID",
      "Title",
      "Requirement",
      "Status",
      "Type",
      "Priority",
      "Description",
      "Coverage Mapping",
      "Created At",
      "Created By",
    ];
    const escape = (value: unknown) => `"${String(value ?? "").replace(/"/g, '""')}"`;
    const rows = scenarioExportRows().map((r) =>
      [
        r.scenario_id,
        r.title,
        r.requirement,
        r.status,
        r.type,
        r.priority,
        r.description,
        r.coverage_mapping,
        r.created_at,
        r.created_by,
      ]
        .map(escape)
        .join(","),
    );
    const csv = "﻿" + [headers.map(escape).join(","), ...rows].join("\r\n");
    const filename = `test_scenarios_${projectName.replace(/\s+/g, "_")}_${new Date().toISOString().slice(0, 10)}.csv`;
    downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), filename);
  };

  const exportScenariosAsXlsx = async () => {
    const projectName = projects.find((p) => p.id === selectedProject)?.name ?? `Project ${selectedProject}`;
    try {
      const ExcelJS = (await import("exceljs")).default;
      const wb = new ExcelJS.Workbook();
      wb.creator = "AI Quality Assurance Command Center";
      wb.created = new Date();
      const ws = wb.addWorksheet("Test Scenarios");

      ws.columns = [
        { header: "Scenario ID", key: "scenario_id", width: 14 },
        { header: "Title", key: "title", width: 48 },
        { header: "Requirement", key: "requirement", width: 14 },
        { header: "Status", key: "status", width: 16 },
        { header: "Type", key: "type", width: 14 },
        { header: "Priority", key: "priority", width: 12 },
        { header: "Description", key: "description", width: 60 },
        { header: "Coverage Mapping", key: "coverage_mapping", width: 40 },
        { header: "Created At", key: "created_at", width: 22 },
        { header: "Created By", key: "created_by", width: 22 },
      ];

      const headerRow = ws.getRow(1);
      headerRow.font = { bold: true, color: { argb: "FFFFFFFF" } };
      headerRow.fill = {
        type: "pattern",
        pattern: "solid",
        fgColor: { argb: "FF1B59F8" },
      };
      headerRow.alignment = { vertical: "middle", horizontal: "left" };

      scenarioExportRows().forEach((row) => ws.addRow(row));
      ws.eachRow({ includeEmpty: false }, (row) => {
        row.alignment = { vertical: "top", wrapText: true };
      });
      ws.autoFilter = { from: { row: 1, column: 1 }, to: { row: 1, column: ws.columns.length } };

      const buffer = await wb.xlsx.writeBuffer();
      const filename = `test_scenarios_${projectName.replace(/\s+/g, "_")}_${new Date().toISOString().slice(0, 10)}.xlsx`;
      downloadBlob(
        new Blob([buffer], {
          type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }),
        filename,
      );
    } catch (err) {
      console.error("Failed to export XLSX:", err);
      setAgentError(getErrorMessage(err, "Failed to export scenarios to Excel."));
    }
  };

  // Stats computation
  const stats = useMemo(() => {
    const totalPlans = plans.length;
    const approvedPlans = plans.filter((p) => p.status === "approved").length;
    const draftPlans = plans.filter((p) => p.status === "draft").length;
    const scenariosCount = scenarios.length;

    const approvedPlansPct = totalPlans > 0 ? ((approvedPlans / totalPlans) * 100).toFixed(1) : "0.0";
    const draftPlansPct = totalPlans > 0 ? ((draftPlans / totalPlans) * 100).toFixed(1) : "0.0";

    return [
      {
        title: "Total Test Plans",
        icon: ClipboardList,
        iconBg: "bg-app-brand-75 border-app-brand-100",
        iconColor: "text-app-brand-500",
        value: totalPlans.toLocaleString(),
        sublabel: "Plans",
        footer: "Total generated test plans spec",
      },
      {
        title: "Approved Plans",
        icon: CheckCircle,
        iconBg: "bg-emerald-50 border-emerald-100",
        iconColor: "text-emerald-500",
        value: approvedPlans.toLocaleString(),
        sublabel: "Approved",
        footer: `${approvedPlansPct}% of plans approved`,
      },
      {
        title: "Draft Plans",
        icon: Clock,
        iconBg: "bg-amber-50 border-amber-100",
        iconColor: "text-amber-500",
        value: draftPlans.toLocaleString(),
        sublabel: "Draft",
        footer: "Plans pending review & approval",
      },
      {
        title: "Test Scenarios",
        icon: Layers,
        iconBg: "bg-purple-50 border-purple-100",
        iconColor: "text-purple-500",
        value: scenariosCount.toLocaleString(),
        sublabel: "Scenarios",
        footer: "Scenarios derived from requirements",
      },
    ];
  }, [plans, scenarios]);

  const requirementLabelById = useMemo(() => new Map(
    requirements.map((req) => [req.id, req.requirement_id || req.title])
  ), [requirements]);

  const scenarioReviewByReqId = useMemo(() => new Map(
    scenarioReviews.map((r) => [r.artifact_id, r])
  ), [scenarioReviews]);

  const requirementById = useMemo(() => new Map(
    requirements.map((req) => [req.id, req])
  ), [requirements]);

  const planCoveredReqIds = useMemo(() => {
    const set = new Set<number>();
    plans.forEach((plan) => {
      const ids = (plan.metadata_?.source_requirement_ids ?? []) as number[];
      ids.forEach((id) => set.add(id));
    });
    return set;
  }, [plans]);

  const scenarioCoveredReqIds = useMemo(() => {
    const set = new Set<number>();
    scenarios.forEach((s) => {
      if (s.requirement_id != null) set.add(s.requirement_id);
    });
    return set;
  }, [scenarios]);

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Global Controls ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-app-brand-75 border border-app-brand-100 p-2.5">
            <ClipboardList className="h-6 w-6 text-[#B71920]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Test Planning</h1>
            <p className="text-xs text-gray-500 mt-1">Generate and manage comprehensive test plans and scenarios from approved requirements</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadData} className="h-8 w-8 p-0 border-gray-200">
            <RefreshCw className={cn("h-3.5 w-3.5 text-gray-500", loading && "animate-spin")} />
          </Button>
        </div>
      </div>

      {selectedProject && (
        <>
          {/* ── Status Counts Cards ─────────────────────────────────────────────────── */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {stats.map((card) => {
              const Icon = card.icon;
              return (
                <Card key={card.title} className="border-gray-200 hover:-translate-y-0.5 transition-all">
                  <CardContent className="p-4 flex flex-col justify-between h-full space-y-3">
                    <div className="flex items-center gap-2">
                      <div className={cn("rounded-lg p-1.5 flex items-center justify-center shrink-0 border", card.iconBg)}>
                        <Icon className={cn("h-4 w-4", card.iconColor)} />
                      </div>
                      <span className="text-xs font-bold text-gray-700 truncate">{card.title}</span>
                    </div>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-xl font-bold text-gray-900">{card.value}</span>
                      {card.sublabel && (
                        <span className="text-[10px] font-bold text-gray-400">{card.sublabel}</span>
                      )}
                    </div>
                    <div className="text-[10px] text-gray-400 font-semibold border-t border-gray-50 pt-2">
                      {card.footer}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* ── Agent Status Banner ──────────────────────────────────────────────── */}
          {(agentStatus || agentError) && (
            <div className={cn(
              "flex items-center gap-3 rounded-xl border px-4 py-3 text-xs font-semibold animate-pulse",
              agentError
                ? "border-red-200 bg-red-50 text-red-700"
                : "border-app-brand-200 bg-app-brand-75 text-app-brand-700"
            )}>
              {agentError ? (
                <AlertTriangle className="h-4 w-4 text-red-500 shrink-0" />
              ) : (
                <Bot className="h-4 w-4 text-[#B71920] shrink-0" />
              )}
              <span className="flex-1">{agentError ?? agentStatus}</span>
              <button 
                onClick={() => {
                  setAgentStatus(null);
                  setAgentError(null);
                }} 
                className="text-gray-400 hover:text-gray-700 font-bold"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* ── Agent Panel Card ─────────────────────────────────────────────────── */}
          <Card className="border-gray-200 overflow-hidden shadow-sm">
            <button
              onClick={() => setShowAgentPanel((v) => !v)}
              className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-gray-50 transition-colors text-left border-b border-gray-100"
            >
              <div className="rounded-lg bg-app-brand-75 border border-app-brand-100 p-1.5 shrink-0">
                <Bot className="h-4 w-4 text-[#B71920]" />
              </div>
              <div className="flex-1 min-w-0">
                <span className="font-bold text-sm text-gray-800">AI Agent Test Planning Copilot</span>
                <p className="text-[11px] text-gray-400 font-semibold mt-0.5">
                  {requirements.length} approved requirements available for plan generation
                </p>
              </div>
              <div className="ml-auto flex items-center gap-2">
                {showAgentPanel ? (
                  <ChevronUp className="h-4.5 w-4.5 text-gray-500" />
                ) : (
                  <ChevronDown className="h-4.5 w-4.5 text-gray-500" />
                )}
              </div>
            </button>

            {showAgentPanel && (
              <div className="p-4 bg-gray-50/20 space-y-4">
                {requirements.length === 0 ? (
                  <div className="flex flex-col items-center justify-center p-6 text-center rounded-xl border border-dashed bg-white border-gray-200">
                    <AlertTriangle className="h-8 w-8 text-amber-500 mb-2" />
                    <p className="text-xs font-bold text-gray-700">No Approved Requirements Found</p>
                    <p className="text-[10px] text-gray-400 font-semibold max-w-xs mt-1">
                      Please approve requirements in the Requirements Library first before generating test plans.
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center justify-between border-b pb-2 border-gray-100">
                      <span className="text-xs font-bold text-gray-700">Select requirements to cover:</span>
                      <button
                        onClick={() => {
                          if (selectedReqIds.length === requirements.length) {
                            setSelectedReqIds([]);
                          } else {
                            setSelectedReqIds(requirements.map((r) => r.id));
                          }
                        }}
                        className="text-[11px] font-bold text-[#B71920] hover:underline"
                      >
                        {selectedReqIds.length === requirements.length ? "Deselect All" : "Select All"}
                      </button>
                    </div>
                    
                    <div className="max-h-56 overflow-y-auto space-y-1.5 pr-1 font-semibold text-xs text-gray-655">
                      {requirements.map((req) => {
                        const isSelected = selectedReqIds.includes(req.id);
                        const hasPlan = planCoveredReqIds.has(req.id);
                        const hasScenarios = scenarioCoveredReqIds.has(req.id);
                        return (
                          <div
                            key={req.id}
                            onClick={() => toggleReq(req.id)}
                            className={cn(
                              "flex flex-col gap-1.5 px-3 py-2 rounded-xl border bg-white cursor-pointer transition-all hover:bg-gray-50",
                              isSelected ? "border-[#B71920] bg-[#B71920]/5 shadow-sm" : "border-gray-200"
                            )}
                          >
                            <div className="flex items-center gap-3">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => {}} // handled by parent onClick
                                className="rounded border-gray-350 text-[#B71920] focus:ring-[#B71920]"
                              />
                              <span className="font-mono text-[10px] font-bold text-[#B71920] bg-[#B71920]/10 px-1.5 py-0.5 rounded shrink-0">
                                {req.requirement_id || `REQ-${req.id}`}
                              </span>
                              <span className="truncate flex-1 text-gray-800">{req.title}</span>
                            </div>
                            <div className="flex items-center flex-wrap gap-2 pl-7">
                              <AuditStamp
                                createdAt={req.created_at}
                                createdByName={resolveUser(req.created_by ?? undefined)}
                                compact
                              />
                              <span className="text-gray-300">·</span>
                              <span
                                className={cn(
                                  "inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-bold",
                                  hasPlan
                                    ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                                    : "bg-gray-50 border-gray-200 text-gray-500"
                                )}
                                title={hasPlan ? "Test plan has been generated for this requirement" : "No test plan generated yet"}
                              >
                                {hasPlan ? (
                                  <CheckCircle className="h-3 w-3" />
                                ) : (
                                  <XCircle className="h-3 w-3" />
                                )}
                                Plan: {hasPlan ? "Y" : "N"}
                              </span>
                              <span
                                className={cn(
                                  "inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-bold",
                                  hasScenarios
                                    ? "bg-violet-50 border-violet-200 text-violet-700"
                                    : "bg-gray-50 border-gray-200 text-gray-500"
                                )}
                                title={hasScenarios ? "Test scenarios have been generated for this requirement" : "No test scenarios generated yet"}
                              >
                                {hasScenarios ? (
                                  <CheckCircle className="h-3 w-3" />
                                ) : (
                                  <XCircle className="h-3 w-3" />
                                )}
                                Scenarios: {hasScenarios ? "Y" : "N"}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    <div className="flex gap-2 pt-2">
                      <Button
                        onClick={handleGeneratePlan}
                        disabled={selectedReqIds.length === 0 || agentStatus !== null}
                        variant="default"
                        className="flex-1 text-xs font-semibold bg-[#B71920] hover:bg-[#941216] text-white h-9"
                      >
                        <ClipboardList className="h-4 w-4 mr-1.5" />
                        Generate Test Plan
                      </Button>
                      <Button
                        onClick={() => handleGenerateScenarios()}
                        disabled={selectedReqIds.length === 0 || agentStatus !== null}
                        className="flex-1 text-xs font-semibold bg-violet-600 hover:bg-violet-700 text-white h-9"
                      >
                        <Layers className="h-4 w-4 mr-1.5" />
                        Generate Scenarios
                      </Button>
                    </div>
                  </>
                )}
              </div>
            )}
          </Card>

          {/* ── Test Plans Accordions List ─────────────────────────────────────────── */}
          <div className="space-y-3.5">
            <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <ClipboardList className="h-4.5 w-4.5 text-gray-400" />
              Test Plans
              {loading && <RefreshCw className="h-3.5 w-3.5 animate-spin text-gray-400" />}
            </h2>

            {!loading && plans.length === 0 ? (
              <div className="bg-white border border-dashed border-gray-200 rounded-xl p-8 text-center shadow-sm">
                <ClipboardList className="h-8 w-8 text-gray-350 mx-auto mb-2" />
                <p className="text-xs font-bold text-gray-500">No test plans created yet.</p>
                <p className="text-[10px] text-gray-400 font-semibold mt-1">
                  Select approved requirements above and click &quot;Generate Test Plan&quot; to begin.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {plans.map((plan) => (
                  <PlanCard
                    key={plan.id}
                    plan={plan}
                    onApprove={handleApprove}
                    onReject={handleReject}
                    onDelete={setDeletingPlan}
                    resolveUser={resolveUser}
                    requirementLabelById={requirementLabelById}
                    requirementById={requirementById}
                  />
                ))}
              </div>
            )}
          </div>

          {/* ── Test Scenarios Catalog ─────────────────────────────────────────────── */}
          <div className="space-y-3.5">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                <Layers className="h-4.5 w-4.5 text-gray-400" />
                Test Scenarios Catalog
                {loading && <RefreshCw className="h-3.5 w-3.5 animate-spin text-gray-400" />}
              </h2>

              {scenarios.length > 0 && (
                <div className="relative">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowScenariosExportMenu((v) => !v)}
                    className="h-8 border-gray-200 text-gray-700 hover:bg-gray-50 bg-white text-xs font-semibold"
                  >
                    <Download className="h-3.5 w-3.5 mr-1" />
                    Export All
                  </Button>
                  {showScenariosExportMenu && (
                    <>
                      <div className="fixed inset-0 z-30" onClick={() => setShowScenariosExportMenu(false)} />
                      <div className="absolute right-0 mt-1.5 w-44 bg-white border border-gray-200 rounded-xl shadow-lg py-1.5 z-40 animate-in fade-in slide-in-from-top-2 duration-100">
                        <button
                          onClick={() => {
                            exportScenariosAsMarkdown();
                            setShowScenariosExportMenu(false);
                          }}
                          className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 font-semibold flex items-center gap-1.5"
                        >
                          <FileText className="h-3.5 w-3.5 text-app-brand-500" />
                          As Markdown
                        </button>
                        <button
                          onClick={() => {
                            exportScenariosAsJson();
                            setShowScenariosExportMenu(false);
                          }}
                          className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 font-semibold flex items-center gap-1.5"
                        >
                          <FileText className="h-3.5 w-3.5 text-amber-500" />
                          As JSON
                        </button>
                        <button
                          onClick={() => {
                            exportScenariosAsCsv();
                            setShowScenariosExportMenu(false);
                          }}
                          className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 font-semibold flex items-center gap-1.5"
                        >
                          <FileText className="h-3.5 w-3.5 text-gray-500" />
                          As CSV
                        </button>
                        <button
                          onClick={() => {
                            exportScenariosAsXlsx();
                            setShowScenariosExportMenu(false);
                          }}
                          className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 font-semibold flex items-center gap-1.5"
                        >
                          <FileText className="h-3.5 w-3.5 text-emerald-500" />
                          As Excel (.xlsx)
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>

            {!loading && scenarios.length === 0 ? (
              <div className="bg-white border border-dashed border-gray-200 rounded-xl p-8 text-center shadow-sm">
                <Layers className="h-8 w-8 text-gray-350 mx-auto mb-2" />
                <p className="text-xs font-bold text-gray-500">No scenarios generated yet.</p>
                <p className="text-[10px] text-gray-400 font-semibold mt-1">
                  Select approved requirements above and click &quot;Generate Scenarios&quot; to begin.
                </p>
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100 overflow-hidden shadow-sm">
                {scenarios.map((scenario) => (
                  <ScenarioCard
                    key={scenario.id}
                    scenario={scenario}
                    requirementLabelById={requirementLabelById}
                    getStatusVariant={getStatusVariant}
                    onApprove={handleApproveScenario}
                    onReject={handleRejectScenario}
                    resolveUser={resolveUser}
                    review={scenario.requirement_id ? scenarioReviewByReqId.get(scenario.requirement_id) : undefined}
                    projectId={selectedProject!}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
      {deletingPlan && (
        <ConfirmDeleteModal
          title="Delete Test Plan"
          description={`Delete ${deletingPlan.test_plan_id} - ${deletingPlan.title}? Linked requirements, scenarios, and test cases will be kept.`}
          onConfirm={handleDeletePlan}
          onCancel={() => setDeletingPlan(null)}
        />
      )}
    </div>
  );
}

export default function TestPlanningPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-gray-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-[#B71920] mr-2" />
        Loading Test Planning...
      </div>
    }>
      <TestPlanningContent />
    </Suspense>
  );
}
