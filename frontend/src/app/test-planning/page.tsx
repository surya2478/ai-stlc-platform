"use client";

import { useState, useEffect, useCallback } from "react";
import {
  testPlansApi,
  requirementsApi,
  projectsApi,
  type TestPlan,
  type Requirement,
  type Project,
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
} from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    draft: "bg-gray-100 text-gray-700",
    pending_review: "bg-yellow-100 text-yellow-800",
    approved: "bg-green-100 text-green-800",
    rejected: "bg-red-100 text-red-800",
  };
  const cls = map[status] ?? "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function Section({ title, items }: { title: string; items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="mb-4">
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">{title}</h4>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="text-sm text-gray-700 flex gap-2">
            <span className="text-gray-400 mt-0.5">•</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── PlanCard ──────────────────────────────────────────────────────────────────

function PlanCard({
  plan,
  onApprove,
  onReject,
}: {
  plan: TestPlan;
  onApprove: (id: number) => void;
  onReject: (id: number, notes: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [notes, setNotes] = useState("");

  return (
    <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
      {/* Header row */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <ClipboardList className="h-4 w-4 text-blue-500 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-mono text-gray-400">{plan.test_plan_id}</span>
            <span className="font-medium text-gray-900 text-sm truncate">{plan.title}</span>
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <StatusBadge status={plan.status} />
            {plan.estimated_effort && (
              <span className="text-xs text-gray-500 flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {plan.estimated_effort}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {plan.status === "draft" || plan.status === "pending_review" ? (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setApproving((v) => !v);
                  setRejecting(false);
                }}
                className="p-1.5 rounded text-green-600 hover:bg-green-50 transition-colors"
                title="Approve"
              >
                <CheckCircle className="h-4 w-4" />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setRejecting((v) => !v);
                  setApproving(false);
                }}
                className="p-1.5 rounded text-red-500 hover:bg-red-50 transition-colors"
                title="Reject"
              >
                <XCircle className="h-4 w-4" />
              </button>
            </>
          ) : null}
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          )}
        </div>
      </div>

      {/* Approve/Reject panel */}
      {(approving || rejecting) && (
        <div className="px-4 pb-3 border-t border-gray-100 bg-gray-50">
          <div className="pt-3 flex flex-col gap-2">
            <textarea
              placeholder={approving ? "Optional notes..." : "Reason for rejection..."}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full text-sm border border-gray-200 rounded-md p-2 resize-none focus:outline-none focus:ring-2 focus:ring-blue-300"
              rows={2}
            />
            <div className="flex gap-2">
              <button
                onClick={() => {
                  if (approving) onApprove(plan.id);
                  else onReject(plan.id, notes);
                  setApproving(false);
                  setRejecting(false);
                  setNotes("");
                }}
                className={`px-3 py-1.5 rounded text-xs font-medium text-white transition-colors ${
                  approving ? "bg-green-600 hover:bg-green-700" : "bg-red-600 hover:bg-red-700"
                }`}
              >
                {approving ? "Confirm Approve" : "Confirm Reject"}
              </button>
              <button
                onClick={() => {
                  setApproving(false);
                  setRejecting(false);
                  setNotes("");
                }}
                className="px-3 py-1.5 rounded text-xs font-medium text-gray-600 bg-white border border-gray-200 hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-gray-100 px-4 py-4 grid grid-cols-1 md:grid-cols-2 gap-x-8">
          <div>
            <Section title="Scope" items={plan.scope} />
            <Section title="Out of Scope" items={plan.out_of_scope} />
            <Section title="Test Types" items={plan.test_types} />
            <Section title="Entry Criteria" items={plan.entry_criteria} />
            <Section title="Exit Criteria" items={plan.exit_criteria} />
          </div>
          <div>
            <Section title="Risks" items={plan.risks} />
            <Section title="Mitigations" items={plan.mitigations} />
            <Section title="Automation Candidates" items={plan.automation_candidates} />
            {plan.resource_recommendation && (
              <div className="mb-4">
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                  Resource Recommendation
                </h4>
                <p className="text-sm text-gray-700">{plan.resource_recommendation}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function TestPlanningPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [plans, setPlans] = useState<TestPlan[]>([]);
  const [loading, setLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState<string | null>(null);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [selectedReqIds, setSelectedReqIds] = useState<number[]>([]);
  const [showAgentPanel, setShowAgentPanel] = useState(false);

  // Load projects on mount
  useEffect(() => {
    projectsApi.list().then((r) => {
      setProjects(r.data);
      const _urlP = typeof window !== "undefined" ? Number(new URLSearchParams(window.location.search).get("project")) || null : null;
      setSelectedProject(_urlP ?? (r.data[0]?.id ?? null));
    });
  }, []);

  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const [plansRes, reqsRes] = await Promise.all([
        testPlansApi.list(selectedProject),
        requirementsApi.list(selectedProject, "approved"),
      ]);
      setPlans(plansRes.data);
      setRequirements(reqsRes.data);
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const toggleReq = (id: number) => {
    setSelectedReqIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleGeneratePlan = async () => {
    if (!selectedProject || selectedReqIds.length === 0) return;
    setAgentStatus("Generating test plan...");
    setAgentError(null);
    try {
      const res = await testPlansApi.generatePlan(selectedProject, selectedReqIds);
      setAgentStatus(
        `Test plan ${res.data.test_plan_id} created successfully.`
      );
      await loadData();
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : "Unknown error";
      setAgentError(msg ?? "Failed to generate test plan");
      setAgentStatus(null);
    }
  };

  const handleGenerateScenarios = async () => {
    if (!selectedProject || selectedReqIds.length === 0) return;
    setAgentStatus("Generating test scenarios...");
    setAgentError(null);
    try {
      const res = await testPlansApi.generateScenarios(selectedProject, selectedReqIds);
      setAgentStatus(res.data.message ?? "Scenarios generated successfully.");
      await loadData();
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : "Unknown error";
      setAgentError(msg ?? "Failed to generate scenarios");
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

  // Stats
  const totalPlans = plans.length;
  const approvedPlans = plans.filter((p) => p.status === "approved").length;
  const draftPlans = plans.filter((p) => p.status === "draft").length;
  const approvedReqs = requirements.length;

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Layers className="h-6 w-6 text-blue-600" />
              Test Planning
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Generate and manage test plans from approved requirements
            </p>
          </div>
          <div className="flex items-center gap-3">
            {projects.length > 0 && (
              <select
                value={selectedProject ?? ""}
                onChange={(e) => setSelectedProject(Number(e.target.value))}
                className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-300 bg-white"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            )}
            <button
              onClick={loadData}
              disabled={loading}
              className="p-2 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 text-gray-600 transition-colors disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: "Total Plans", value: totalPlans, icon: ClipboardList, color: "text-blue-600" },
            { label: "Approved", value: approvedPlans, icon: CheckCircle, color: "text-green-600" },
            { label: "Draft", value: draftPlans, icon: Clock, color: "text-yellow-600" },
            { label: "Approved Reqs", value: approvedReqs, icon: Layers, color: "text-purple-600" },
          ].map(({ label, value, icon: Icon, color }) => (
            <div key={label} className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-3">
              <Icon className={`h-5 w-5 ${color}`} />
              <div>
                <div className="text-2xl font-bold text-gray-900">{value}</div>
                <div className="text-xs text-gray-500">{label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Agent Status Banner */}
        {(agentStatus || agentError) && (
          <div
            className={`rounded-lg px-4 py-3 flex items-start gap-2 text-sm ${
              agentError
                ? "bg-red-50 border border-red-200 text-red-700"
                : "bg-blue-50 border border-blue-200 text-blue-700"
            }`}
          >
            {agentError ? (
              <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" />
            ) : (
              <Bot className="h-4 w-4 mt-0.5 flex-shrink-0" />
            )}
            <span>{agentError ?? agentStatus}</span>
            <button
              onClick={() => {
                setAgentStatus(null);
                setAgentError(null);
              }}
              className="ml-auto text-xs opacity-60 hover:opacity-100"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Agent Panel Toggle */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <button
            onClick={() => setShowAgentPanel((v) => !v)}
            className="w-full flex items-center gap-2 px-4 py-3 hover:bg-gray-50 transition-colors text-left"
          >
            <Bot className="h-4 w-4 text-blue-500" />
            <span className="font-medium text-sm text-gray-800">AI Agent Panel</span>
            <span className="ml-auto text-xs text-gray-400">
              {requirements.length} approved requirements available
            </span>
            {showAgentPanel ? (
              <ChevronUp className="h-4 w-4 text-gray-400" />
            ) : (
              <ChevronDown className="h-4 w-4 text-gray-400" />
            )}
          </button>

          {showAgentPanel && (
            <div className="border-t border-gray-100 px-4 pb-4">
              {requirements.length === 0 ? (
                <p className="text-sm text-gray-500 py-3">
                  No approved requirements found. Approve requirements first before generating a test plan.
                </p>
              ) : (
                <>
                  <p className="text-xs text-gray-500 pt-3 pb-2">
                    Select approved requirements to include in the plan:
                  </p>
                  <div className="max-h-48 overflow-y-auto space-y-1 mb-3">
                    <label className="flex items-center gap-2 text-sm text-gray-600 hover:bg-gray-50 px-2 py-1 rounded cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedReqIds.length === requirements.length && requirements.length > 0}
                        onChange={() => {
                          if (selectedReqIds.length === requirements.length) {
                            setSelectedReqIds([]);
                          } else {
                            setSelectedReqIds(requirements.map((r) => r.id));
                          }
                        }}
                        className="rounded"
                      />
                      <span className="font-medium">Select all ({requirements.length})</span>
                    </label>
                    {requirements.map((req) => (
                      <label
                        key={req.id}
                        className="flex items-center gap-2 text-sm text-gray-700 hover:bg-gray-50 px-2 py-1 rounded cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={selectedReqIds.includes(req.id)}
                          onChange={() => toggleReq(req.id)}
                          className="rounded"
                        />
                        <span className="font-mono text-xs text-gray-400">{req.requirement_id}</span>
                        <span className="truncate">{req.title}</span>
                      </label>
                    ))}
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    <button
                      onClick={handleGeneratePlan}
                      disabled={selectedReqIds.length === 0 || agentStatus !== null}
                      className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <ClipboardList className="h-4 w-4" />
                      Generate Test Plan
                    </button>
                    <button
                      onClick={handleGenerateScenarios}
                      disabled={selectedReqIds.length === 0 || agentStatus !== null}
                      className="flex items-center gap-1.5 px-3 py-2 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Layers className="h-4 w-4" />
                      Generate Scenarios
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* Plans List */}
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <ClipboardList className="h-4 w-4 text-gray-400" />
            Test Plans
            {loading && <RefreshCw className="h-3 w-3 animate-spin text-gray-400" />}
          </h2>

          {!loading && plans.length === 0 ? (
            <div className="bg-white border border-dashed border-gray-200 rounded-xl p-8 text-center">
              <ClipboardList className="h-8 w-8 text-gray-300 mx-auto mb-2" />
              <p className="text-sm text-gray-500">No test plans yet.</p>
              <p className="text-xs text-gray-400 mt-1">
                Select approved requirements above and click &quot;Generate Test Plan&quot; to get started.
              </p>
            </div>
          ) : (
            plans.map((plan) => (
              <PlanCard
                key={plan.id}
                plan={plan}
                onApprove={handleApprove}
                onReject={handleReject}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
