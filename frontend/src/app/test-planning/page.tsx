"use client";

import { useState, useEffect, useCallback, useMemo, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  testPlansApi,
  requirementsApi,
  projectsApi,
  scenariosApi,
  agentRunsApi,
  type TestPlan,
  type Requirement,
  type Project,
  type TestScenario,
} from "@/lib/api";
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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { AuditStamp } from "@/components/ui/AuditStamp";
import { useUserDirectory } from "@/hooks/useUserDirectory";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

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
      <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{title}</h4>
      <ul className="text-xs space-y-1.5 font-semibold text-slate-700 bg-white border rounded-lg p-3">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="text-[#1b59f8] font-bold select-none mt-0.5">•</span>
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

function PlanCard({
  plan,
  onApprove,
  onReject,
  resolveUser,
  requirementLabelById,
}: {
  plan: TestPlan;
  onApprove: (id: number) => void;
  onReject: (id: number, notes: string) => void;
  resolveUser: (id?: number) => string;
  requirementLabelById?: Map<number, string>;
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
    const content = `# Test Plan: ${p.title} (${p.test_plan_id})

**Status:** ${p.status.toUpperCase()}
**Estimated Effort:** ${p.estimated_effort || "N/A"}
**Resource Recommendation:** ${p.resource_recommendation || "N/A"}
**Created At:** ${new Date(p.created_at).toLocaleString()}

## Scope
${p.scope?.map((item) => `- ${item}`).join("\n") || "N/A"}

## Out of Scope
${p.out_of_scope?.map((item) => `- ${item}`).join("\n") || "N/A"}

## Test Types
${p.test_types?.map((item) => `- ${item}`).join("\n") || "N/A"}

## Entry Criteria
${p.entry_criteria?.map((item) => `- ${item}`).join("\n") || "N/A"}

## Exit Criteria
${p.exit_criteria?.map((item) => `- ${item}`).join("\n") || "N/A"}

## Risks
${p.risks?.map((item) => `- ${item}`).join("\n") || "N/A"}

## Mitigations
${p.mitigations?.map((item) => `- ${item}`).join("\n") || "N/A"}

## Automation Candidates
${p.automation_candidates?.map((item) => `- ${item}`).join("\n") || "N/A"}
`;
    downloadBlob(new Blob([content], { type: "text/markdown" }), `test_plan_${p.test_plan_id}.md`);
  };

  const exportPlanAsJson = (p: TestPlan) => {
    const content = JSON.stringify(p, null, 2);
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
      "border-slate-200 overflow-hidden hover:shadow-sm transition-all",
      expanded && "border-slate-350 shadow-sm"
    )}>
      {/* Header row */}
      <div
        className="flex items-center justify-between gap-4 px-4 py-3.5 cursor-pointer hover:bg-slate-50/50 transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="rounded-lg bg-blue-50 border border-blue-100 p-2 shrink-0">
            <ClipboardList className="h-4 w-4 text-[#1b59f8]" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] font-mono font-bold text-[#1b59f8] bg-blue-50 border border-blue-100 px-1.5 py-0.5 rounded">
                {plan.test_plan_id}
              </span>
              <span className="font-bold text-slate-800 text-sm truncate">{plan.title}</span>
            </div>
            <div className="flex items-center gap-2.5 mt-1 flex-wrap">
              <Badge variant={getStatusVariant(plan.status)} className="capitalize">
                {plan.status.replace(/_/g, " ")}
              </Badge>
              {plan.estimated_effort && (
                <span className="text-[10px] text-slate-400 font-bold flex items-center gap-1">
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

          {/* Export Dropdown */}
          <div className="relative">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowExportMenu((v) => !v)}
              className="h-8 border-slate-200 text-slate-700 hover:bg-slate-50 bg-white text-xs font-semibold"
            >
              <Download className="h-3.5 w-3.5 mr-1" />
              Export
            </Button>
            {showExportMenu && (
              <>
                <div className="fixed inset-0 z-30" onClick={() => setShowExportMenu(false)} />
                <div className="absolute right-0 mt-1.5 w-40 bg-white border border-slate-200 rounded-xl shadow-lg py-1.5 z-40 animate-in fade-in slide-in-from-top-2 duration-100">
                  <button
                    onClick={() => {
                      exportPlanAsMarkdown(plan);
                      setShowExportMenu(false);
                    }}
                    className="w-full text-left px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 font-semibold flex items-center gap-1.5"
                  >
                    <FileText className="h-3.5 w-3.5 text-blue-500" />
                    As Markdown
                  </button>
                  <button
                    onClick={() => {
                      exportPlanAsJson(plan);
                      setShowExportMenu(false);
                    }}
                    className="w-full text-left px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 font-semibold flex items-center gap-1.5"
                  >
                    <FileText className="h-3.5 w-3.5 text-amber-500" />
                    As JSON
                  </button>
                  <button
                    onClick={() => {
                      exportPlanAsDocx(plan.id, plan.test_plan_id);
                      setShowExportMenu(false);
                    }}
                    className="w-full text-left px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 font-semibold flex items-center gap-1.5"
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
            className="rounded-md p-1.5 hover:bg-slate-100 text-slate-400 shrink-0"
          >
            {expanded ? (
              <ChevronUp className="h-4.5 w-4.5 text-slate-500" />
            ) : (
              <ChevronDown className="h-4.5 w-4.5 text-slate-500" />
            )}
          </button>
        </div>
      </div>

      {/* Approve/Reject panel */}
      {(approving || rejecting) && (
        <div className="px-4 py-3 border-t border-slate-100 bg-slate-50/50 space-y-2.5 animate-in fade-in duration-100">
          <textarea
            placeholder={approving ? "Add optional review comments/notes..." : "Explain the reason for rejecting this test plan (required)..."}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full text-xs border border-slate-200 rounded-lg p-2.5 resize-none focus:outline-none focus:ring-2 focus:ring-[#1b59f8] bg-white font-semibold text-slate-700"
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
              className="h-8 text-xs font-semibold bg-white border-slate-200 text-slate-505"
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-slate-100 px-5 py-4 bg-slate-50/10 space-y-4 animate-in fade-in duration-150">
          {/* Covered Requirements and High Level Metadata */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
            <div className="space-y-2.5">
              <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                <ClipboardList className="h-4 w-4 text-[#1b59f8]" />
                High-Level Details
              </h4>
              <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                <div>
                  <span className="text-slate-400 font-bold block">Estimated Effort</span>
                  <span className="font-semibold text-slate-700">{plan.estimated_effort || "Not Specified"}</span>
                </div>
                <div>
                  <span className="text-slate-400 font-bold block">Resource Recommendation</span>
                  <span className="font-semibold text-slate-700">{plan.resource_recommendation || "Not Specified"}</span>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                <Layers className="h-4 w-4 text-[#1b59f8]" />
                Covered Requirements
              </h4>
              {plan.metadata_?.source_requirement_ids && plan.metadata_.source_requirement_ids.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {plan.metadata_.source_requirement_ids.map((reqId: number) => {
                    const label = requirementLabelById?.get(reqId);
                    return (
                      <span key={reqId} className="text-[10px] font-mono font-bold text-[#1b59f8] bg-blue-50 border border-blue-100 px-2 py-0.5 rounded-md">
                        {label || `REQ-${reqId}`}
                      </span>
                    );
                  })}
                </div>
              ) : (
                <span className="text-xs text-slate-400 font-medium">No linked requirements</span>
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
}: {
  scenario: TestScenario;
  requirementLabelById: Map<number, string>;
  getStatusVariant: (status: string) => string;
  onApprove: (id: number) => void;
  onReject: (id: number, notes: string) => void;
  resolveUser: (id?: number) => string;
}) {
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [notes, setNotes] = useState("");

  return (
    <div className="px-4 py-3.5 hover:bg-slate-50/30 transition-colors font-medium">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <div className="rounded-lg bg-purple-50 border border-purple-100 p-2 shrink-0">
            <Layers className="h-4 w-4 text-purple-600" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="font-mono text-[10px] font-bold text-slate-450">{scenario.scenario_id}</span>
              {scenario.requirement_id && (
                <span className="text-[10px] font-mono font-bold text-[#1b59f8] bg-[#1b59f8]/5 border border-[#1b59f8]/10 px-1.5 py-0.5 rounded shrink-0">
                  {requirementLabelById.get(scenario.requirement_id) ?? `REQ-${scenario.requirement_id}`}
                </span>
              )}
              <Badge variant={getStatusVariant(scenario.status) as any} className="capitalize">
                {scenario.status.replace(/_/g, " ")}
              </Badge>
              {scenario.scenario_type && (
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider bg-slate-50 border px-1.5 py-0.5 rounded shrink-0">
                  {scenario.scenario_type}
                </span>
              )}
              {scenario.priority && (
                <span className={cn(
                  "text-[10px] font-bold uppercase tracking-wider border px-1.5 py-0.5 rounded shrink-0",
                  scenario.priority.toLowerCase() === "high" ? "border-rose-100 bg-rose-50 text-rose-600" :
                  scenario.priority.toLowerCase() === "medium" ? "border-amber-100 bg-amber-50 text-amber-600" :
                  "border-slate-100 bg-slate-50 text-slate-600"
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
            <h3 className="font-bold text-slate-800 text-sm mt-1.5">{scenario.title}</h3>
            {scenario.description && (
              <p className="text-xs text-slate-500 mt-1 leading-relaxed font-semibold">{scenario.description}</p>
            )}
            
            {/* Show review notes if present in metadata */}
            {scenario.metadata_?.review_notes && (
              <div className="mt-2 text-[10px] font-semibold bg-slate-50 border rounded p-2 text-slate-550 leading-normal">
                <span className="font-bold text-slate-700 block mb-0.5">Review Notes:</span>
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
        <div className="mt-3 py-3 border-t border-slate-100 bg-slate-50/50 space-y-2.5 animate-in fade-in duration-100 rounded-lg px-3">
          <textarea
            placeholder={approving ? "Add optional review comments/notes..." : "Explain the reason for rejecting this test scenario (required)..."}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full text-xs border border-slate-200 rounded-lg p-2.5 resize-none focus:outline-none focus:ring-2 focus:ring-[#1b59f8] bg-white font-semibold text-slate-700"
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
              className="h-8 text-xs font-semibold bg-white border-slate-200 text-slate-505"
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
  const { resolveUser } = useUserDirectory();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProject = Number(searchParams.get("project")) || null;

  const [projects, setProjects] = useState<Project[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [plans, setPlans] = useState<TestPlan[]>([]);
  const [scenarios, setScenarios] = useState<TestScenario[]>([]);
  const [loading, setLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState<string | null>(null);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [selectedReqIds, setSelectedReqIds] = useState<number[]>([]);
  const [showAgentPanel, setShowAgentPanel] = useState(false);

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
      const [plansRes, reqsRes, scenariosRes] = await Promise.all([
        testPlansApi.list(selectedProject),
        requirementsApi.list(selectedProject, { status: "approved" }),
        scenariosApi.list(selectedProject),
      ]);
      setPlans(plansRes.data);
      setRequirements(reqsRes.data);
      setScenarios(scenariosRes.data);
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
    for (let attempt = 0; attempt < 100; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      const run = (await agentRunsApi.get(runId)).data;

      if (run.progress_message) {
        setAgentStatus(`${run.progress_message} (${run.progress_percent ?? 0}%)`);
      }

      if (run.status === "completed") {
        setAgentStatus(completedMessage);
        await loadData();
        return;
      }

      if (run.status === "failed") {
        setAgentError(run.error_message || failedFallback);
        setAgentStatus(null);
        return;
      }
    }

    setAgentStatus("Still running. Check Agent Logs for progress.");
  };

  const handleGeneratePlan = async () => {
    if (!selectedProject || selectedReqIds.length === 0) return;
    setAgentStatus("Generating test plan...");
    setAgentError(null);
    try {
      const res = await testPlansApi.generatePlan(selectedProject, selectedReqIds);
      const data = res.data as AgentTriggerResponse;
      if (data.agent_run_id) {
        setAgentStatus(data.message ?? "Test plan generation queued.");
        await pollAgentRun(data.agent_run_id, "Test plan generated successfully.", "Test plan generation failed.");
      } else {
        setAgentStatus(`Test plan ${data.test_plan_id ?? ""} created successfully.`.trim());
        await loadData();
      }
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
      const res = await testPlansApi.generateScenarios(selectedProject, selectedReqIds, overrideQualityGate);
      const data = res.data as AgentTriggerResponse;
      if (data.agent_run_id) {
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
        iconBg: "bg-blue-50 border-blue-100",
        iconColor: "text-blue-500",
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

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Global Controls ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-blue-50 border border-blue-100 p-2.5">
            <ClipboardList className="h-6 w-6 text-[#1b59f8]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Test Planning</h1>
            <p className="text-xs text-slate-500 mt-1">Generate and manage comprehensive test plans and scenarios from approved requirements</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedProject ?? ""}
            onChange={(e) => {
              const val = e.target.value;
              const params = new URLSearchParams(searchParams.toString());
              params.set("project", val);
              router.push(`${pathname}?${params.toString()}`);
            }}
            className="appearance-none bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 rounded-lg text-xs font-semibold px-3 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-[#1b59f8] transition-colors cursor-pointer"
            style={{
              backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
              backgroundPosition: 'right 0.5rem center',
              backgroundSize: '1.25rem 1.25rem',
              backgroundRepeat: 'no-repeat',
            }}
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>

          <Button variant="outline" size="sm" onClick={loadData} className="h-8 w-8 p-0 border-slate-200">
            <RefreshCw className={cn("h-3.5 w-3.5 text-slate-500", loading && "animate-spin")} />
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
          {(agentStatus || agentError) && (
            <div className={cn(
              "flex items-center gap-3 rounded-xl border px-4 py-3 text-xs font-semibold animate-pulse",
              agentError
                ? "border-red-200 bg-red-50 text-red-700"
                : "border-blue-200 bg-blue-50 text-blue-700"
            )}>
              {agentError ? (
                <AlertTriangle className="h-4 w-4 text-red-500 shrink-0" />
              ) : (
                <Bot className="h-4 w-4 text-[#1b59f8] shrink-0" />
              )}
              <span className="flex-1">{agentError ?? agentStatus}</span>
              <button 
                onClick={() => {
                  setAgentStatus(null);
                  setAgentError(null);
                }} 
                className="text-slate-400 hover:text-slate-700 font-bold"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* ── Agent Panel Card ─────────────────────────────────────────────────── */}
          <Card className="border-slate-200 overflow-hidden shadow-sm">
            <button
              onClick={() => setShowAgentPanel((v) => !v)}
              className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-slate-50 transition-colors text-left border-b border-slate-100"
            >
              <div className="rounded-lg bg-blue-50 border border-blue-100 p-1.5 shrink-0">
                <Bot className="h-4 w-4 text-[#1b59f8]" />
              </div>
              <div className="flex-1 min-w-0">
                <span className="font-bold text-sm text-slate-800">AI Agent Test Planning Copilot</span>
                <p className="text-[11px] text-slate-400 font-semibold mt-0.5">
                  {requirements.length} approved requirements available for plan generation
                </p>
              </div>
              <div className="ml-auto flex items-center gap-2">
                {showAgentPanel ? (
                  <ChevronUp className="h-4.5 w-4.5 text-slate-500" />
                ) : (
                  <ChevronDown className="h-4.5 w-4.5 text-slate-500" />
                )}
              </div>
            </button>

            {showAgentPanel && (
              <div className="p-4 bg-slate-50/20 space-y-4">
                {requirements.length === 0 ? (
                  <div className="flex flex-col items-center justify-center p-6 text-center rounded-xl border border-dashed bg-white border-slate-200">
                    <AlertTriangle className="h-8 w-8 text-amber-500 mb-2" />
                    <p className="text-xs font-bold text-slate-700">No Approved Requirements Found</p>
                    <p className="text-[10px] text-slate-400 font-semibold max-w-xs mt-1">
                      Please approve requirements in the Requirements Library first before generating test plans.
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center justify-between border-b pb-2 border-slate-100">
                      <span className="text-xs font-bold text-slate-700">Select requirements to cover:</span>
                      <button
                        onClick={() => {
                          if (selectedReqIds.length === requirements.length) {
                            setSelectedReqIds([]);
                          } else {
                            setSelectedReqIds(requirements.map((r) => r.id));
                          }
                        }}
                        className="text-[11px] font-bold text-[#1b59f8] hover:underline"
                      >
                        {selectedReqIds.length === requirements.length ? "Deselect All" : "Select All"}
                      </button>
                    </div>
                    
                    <div className="max-h-56 overflow-y-auto space-y-1.5 pr-1 font-semibold text-xs text-slate-655">
                      {requirements.map((req) => {
                        const isSelected = selectedReqIds.includes(req.id);
                        return (
                          <div
                            key={req.id}
                            onClick={() => toggleReq(req.id)}
                            className={cn(
                              "flex items-center gap-3 px-3 py-2 rounded-xl border bg-white cursor-pointer transition-all hover:bg-slate-50",
                              isSelected ? "border-[#1b59f8] bg-[#1b59f8]/5 shadow-sm" : "border-slate-200"
                            )}
                          >
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => {}} // handled by parent onClick
                              className="rounded border-slate-350 text-[#1b59f8] focus:ring-[#1b59f8]"
                            />
                            <span className="font-mono text-[10px] font-bold text-[#1b59f8] bg-[#1b59f8]/10 px-1.5 py-0.5 rounded shrink-0">
                              {req.requirement_id || `REQ-${req.id}`}
                            </span>
                            <span className="truncate flex-1 text-slate-800">{req.title}</span>
                          </div>
                        );
                      })}
                    </div>

                    <div className="flex gap-2 pt-2">
                      <Button
                        onClick={handleGeneratePlan}
                        disabled={selectedReqIds.length === 0 || agentStatus !== null}
                        variant="default"
                        className="flex-1 text-xs font-semibold bg-[#1b59f8] hover:bg-[#1546c7] text-white h-9"
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
            <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <ClipboardList className="h-4.5 w-4.5 text-slate-400" />
              Test Plans
              {loading && <RefreshCw className="h-3.5 w-3.5 animate-spin text-slate-400" />}
            </h2>

            {!loading && plans.length === 0 ? (
              <div className="bg-white border border-dashed border-slate-200 rounded-xl p-8 text-center shadow-sm">
                <ClipboardList className="h-8 w-8 text-slate-350 mx-auto mb-2" />
                <p className="text-xs font-bold text-slate-500">No test plans created yet.</p>
                <p className="text-[10px] text-slate-400 font-semibold mt-1">
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
                    resolveUser={resolveUser}
                    requirementLabelById={requirementLabelById}
                  />
                ))}
              </div>
            )}
          </div>

          {/* ── Test Scenarios Catalog ─────────────────────────────────────────────── */}
          <div className="space-y-3.5">
            <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <Layers className="h-4.5 w-4.5 text-slate-400" />
              Test Scenarios Catalog
              {loading && <RefreshCw className="h-3.5 w-3.5 animate-spin text-slate-400" />}
            </h2>

            {!loading && scenarios.length === 0 ? (
              <div className="bg-white border border-dashed border-slate-200 rounded-xl p-8 text-center shadow-sm">
                <Layers className="h-8 w-8 text-slate-350 mx-auto mb-2" />
                <p className="text-xs font-bold text-slate-500">No scenarios generated yet.</p>
                <p className="text-[10px] text-slate-400 font-semibold mt-1">
                  Select approved requirements above and click &quot;Generate Scenarios&quot; to begin.
                </p>
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-slate-200 divide-y divide-slate-100 overflow-hidden shadow-sm">
                {scenarios.map((scenario) => (
                  <ScenarioCard
                    key={scenario.id}
                    scenario={scenario}
                    requirementLabelById={requirementLabelById}
                    getStatusVariant={getStatusVariant}
                    onApprove={handleApproveScenario}
                    onReject={handleRejectScenario}
                    resolveUser={resolveUser}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function TestPlanningPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-slate-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-[#1b59f8] mr-2" />
        Loading Test Planning...
      </div>
    }>
      <TestPlanningContent />
    </Suspense>
  );
}
