"use client";
import { useState, useEffect, useCallback } from "react";
import {
  automationApi, testCasesApi, projectsApi,
  type AutomationScript, type TestCase, type Project,
} from "@/lib/api";
import {
  Code2, Bot, CheckCircle, XCircle, Clock, ChevronDown, ChevronUp,
  Copy, Check, Layers, AlertTriangle,
} from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    draft: "bg-gray-100 text-gray-700",
    pending_approval: "bg-yellow-100 text-yellow-700",
    approved: "bg-green-100 text-green-700",
    rejected: "bg-red-100 text-red-700",
    executed: "bg-blue-100 text-blue-700",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${map[status] ?? "bg-gray-100 text-gray-600"}`}>
      {status.replace("_", " ")}
    </span>
  );
}

function FrameworkBadge({ framework }: { framework: string }) {
  const map: Record<string, string> = {
    playwright: "bg-violet-100 text-violet-700",
    pytest: "bg-blue-100 text-blue-700",
    httpx: "bg-teal-100 text-teal-700",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${map[framework] ?? "bg-gray-100 text-gray-600"}`}>
      {framework}
    </span>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button onClick={handleCopy} title="Copy" className="text-gray-400 hover:text-gray-700 transition-colors">
      {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
    </button>
  );
}

function ScriptCard({
  script,
  onApprove,
  onReject,
}: {
  script: AutomationScript;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [confirming, setConfirming] = useState<"approve" | "reject" | null>(null);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="p-4 flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="text-xs font-mono text-gray-400">{script.script_id}</span>
            <FrameworkBadge framework={script.framework} />
            <StatusBadge status={script.status} />
          </div>
          <p className="text-sm font-medium text-gray-800 truncate">
            {script.file_path || `script_${script.script_id}.${script.framework === "playwright" ? "spec.ts" : "py"}`}
          </p>
          {script.execution_command && (
            <div className="flex items-center gap-1 mt-1">
              <span className="text-xs text-gray-400 font-mono truncate">{script.execution_command}</span>
              <CopyButton text={script.execution_command} />
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {script.status === "draft" && (
            <>
              {confirming === "approve" ? (
                <div className="flex gap-1">
                  <button onClick={() => { onApprove(script.id); setConfirming(null); }}
                    className="px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700">Confirm</button>
                  <button onClick={() => setConfirming(null)}
                    className="px-2 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300">Cancel</button>
                </div>
              ) : confirming === "reject" ? (
                <div className="flex gap-1">
                  <button onClick={() => { onReject(script.id); setConfirming(null); }}
                    className="px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700">Confirm Reject</button>
                  <button onClick={() => setConfirming(null)}
                    className="px-2 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300">Cancel</button>
                </div>
              ) : (
                <>
                  <button onClick={() => setConfirming("approve")}
                    className="flex items-center gap-1 px-2 py-1 text-xs bg-green-50 text-green-700 border border-green-200 rounded hover:bg-green-100">
                    <CheckCircle size={12} /> Approve
                  </button>
                  <button onClick={() => setConfirming("reject")}
                    className="flex items-center gap-1 px-2 py-1 text-xs bg-red-50 text-red-700 border border-red-200 rounded hover:bg-red-100">
                    <XCircle size={12} /> Reject
                  </button>
                </>
              )}
            </>
          )}
          <button onClick={() => setExpanded(!expanded)} className="text-gray-400 hover:text-gray-600">
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-100 bg-gray-50">
          {/* Setup Commands */}
          {script.setup_required && script.setup_required.length > 0 && (
            <div className="px-4 py-3 border-b border-gray-100">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Setup</p>
              <div className="space-y-1">
                {script.setup_required.map((cmd, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <code className="text-xs bg-gray-800 text-green-300 px-2 py-0.5 rounded font-mono flex-1">{cmd}</code>
                    <CopyButton text={cmd} />
                  </div>
                ))}
              </div>
            </div>
          )}
          {/* Code */}
          <div className="px-4 py-3">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Code</p>
              <CopyButton text={script.code} />
            </div>
            <pre className="text-xs bg-gray-900 text-gray-100 p-3 rounded-lg overflow-x-auto max-h-96 font-mono leading-relaxed whitespace-pre-wrap">
              {script.code}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AutomationPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | null>(null);
  const [scripts, setScripts] = useState<AutomationScript[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [agentError, setAgentError] = useState<string | null>(null);
  const [selectedTcIds, setSelectedTcIds] = useState<Set<number>>(new Set());
  const [framework, setFramework] = useState<"playwright" | "pytest">("playwright");
  const [showAgentPanel, setShowAgentPanel] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>("all");

  useEffect(() => {
    projectsApi.list()
      .then((r) => {
        setProjects(r.data);
        const _urlP = typeof window !== "undefined" ? Number(new URLSearchParams(window.location.search).get("project")) || null : null;
        setSelectedProject(_urlP ?? (r.data[0]?.id ?? null));
      })
      .catch((e) => console.error("[Projects] Failed to load:", e?.response?.status));
  }, []);

  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const [scriptsRes, casesRes] = await Promise.all([
        automationApi.list(selectedProject),
        testCasesApi.list(selectedProject, { status: "approved" }),
      ]);
      setScripts(scriptsRes.data);
      setTestCases(casesRes.data.filter((tc) => tc.automation_candidate));
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => { loadData(); }, [loadData]);

  const toggleTc = (id: number) => {
    setSelectedTcIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleGenerate = async () => {
    if (!selectedProject || selectedTcIds.size === 0) return;
    setAgentStatus("running");
    setAgentError(null);
    try {
      const res = await automationApi.generateScripts(selectedProject, Array.from(selectedTcIds), framework);
      const data = res.data as { script_ids?: number[]; message?: string };
      const count = data.script_ids?.length ?? 0;
      if (count === 0) {
        setAgentStatus("error");
        setAgentError("Agent ran but generated 0 scripts — the LLM may have failed to parse the test cases. Check backend logs.");
      } else {
        setAgentStatus("done");
      }
      setSelectedTcIds(new Set());
      await loadData();
    } catch (e: unknown) {
      setAgentStatus("error");
      const err = e as { response?: { data?: { detail?: string } } };
      setAgentError(err?.response?.data?.detail ?? "Agent failed");
    }
  };

  const handleApprove = async (id: number) => {
    await automationApi.approve(id, "approve");
    await loadData();
  };

  const handleReject = async (id: number) => {
    await automationApi.approve(id, "reject");
    await loadData();
  };

  const filtered = filterStatus === "all" ? scripts : scripts.filter((s) => s.status === filterStatus);
  const stats = {
    total: scripts.length,
    approved: scripts.filter((s) => s.status === "approved").length,
    draft: scripts.filter((s) => s.status === "draft").length,
    playwright: scripts.filter((s) => s.framework === "playwright").length,
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-violet-100 rounded-lg">
            <Code2 size={22} className="text-violet-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Automation Scripts</h1>
            <p className="text-sm text-gray-500">AI-generated Playwright & Pytest scripts — Agent 7</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedProject ?? ""}
            onChange={(e) => setSelectedProject(Number(e.target.value))}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-violet-300"
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button
            onClick={() => setShowAgentPanel(!showAgentPanel)}
            className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700"
          >
            <Bot size={16} /> AI Generate
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Total Scripts", value: stats.total, color: "text-gray-800" },
          { label: "Approved", value: stats.approved, color: "text-green-600" },
          { label: "Draft", value: stats.draft, color: "text-yellow-600" },
          { label: "Playwright", value: stats.playwright, color: "text-violet-600" },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
            <p className="text-xs text-gray-500 mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Agent Panel */}
      {showAgentPanel && (
        <div className="bg-violet-50 border border-violet-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Bot size={18} className="text-violet-600" />
            <h2 className="font-semibold text-violet-900">Generate Automation Scripts</h2>
          </div>

          {/* Framework Selector */}
          <div className="flex gap-3 mb-4">
            {(["playwright", "pytest"] as const).map((fw) => (
              <button
                key={fw}
                onClick={() => setFramework(fw)}
                className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                  framework === fw
                    ? "bg-violet-600 text-white border-violet-600"
                    : "bg-white text-gray-600 border-gray-200 hover:border-violet-300"
                }`}
              >
                {fw === "playwright" ? "🎭 Playwright (TS)" : "🐍 Pytest (Python)"}
              </button>
            ))}
          </div>

          {/* Test Case Selector */}
          {testCases.length === 0 ? (
            <p className="text-sm text-violet-700 bg-violet-100 rounded-lg p-3">
              No approved automation-candidate test cases found. Approve test cases in the Test Cases module first.
            </p>
          ) : (
            <>
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm font-medium text-violet-800">
                  Automation-candidate test cases ({testCases.length})
                </p>
                <button
                  onClick={() =>
                    setSelectedTcIds(
                      selectedTcIds.size === testCases.length
                        ? new Set()
                        : new Set(testCases.map((t) => t.id))
                    )
                  }
                  className="text-xs text-violet-600 hover:underline"
                >
                  {selectedTcIds.size === testCases.length ? "Deselect all" : "Select all"}
                </button>
              </div>
              <div className="max-h-48 overflow-y-auto space-y-1 mb-4">
                {testCases.map((tc) => (
                  <label key={tc.id} className="flex items-center gap-2 p-2 bg-white rounded-lg border border-violet-100 cursor-pointer hover:border-violet-300">
                    <input
                      type="checkbox"
                      checked={selectedTcIds.has(tc.id)}
                      onChange={() => toggleTc(tc.id)}
                      className="accent-violet-600"
                    />
                    <span className="text-xs font-mono text-violet-500 shrink-0">{tc.test_case_id}</span>
                    <span className="text-sm text-gray-700 truncate">{tc.title}</span>
                  </label>
                ))}
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleGenerate}
                  disabled={selectedTcIds.size === 0 || agentStatus === "running"}
                  className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {agentStatus === "running" ? (
                    <><span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" /> Generating...</>
                  ) : (
                    <><Bot size={16} /> Generate {selectedTcIds.size} Script{selectedTcIds.size !== 1 ? "s" : ""}</>
                  )}
                </button>
                {agentStatus === "done" && (
                  <span className="flex items-center gap-1 text-sm text-green-600">
                    <CheckCircle size={16} /> Scripts generated!
                  </span>
                )}
                {agentStatus === "error" && (
                  <span className="flex items-center gap-1 text-sm text-red-600">
                    <AlertTriangle size={16} /> {agentError}
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* Filter Bar */}
      <div className="flex gap-2">
        {["all", "draft", "approved", "rejected"].map((s) => (
          <button
            key={s}
            onClick={() => setFilterStatus(s)}
            className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${
              filterStatus === s ? "bg-gray-800 text-white" : "bg-white text-gray-600 border border-gray-200 hover:border-gray-400"
            }`}
          >
            {s === "all" ? "All" : s.charAt(0).toUpperCase() + s.slice(1).replace("_", " ")}
          </button>
        ))}
      </div>

      {/* Scripts List */}
      {loading ? (
        <div className="flex justify-center py-12">
          <span className="animate-spin w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-xl border border-gray-100">
          <Code2 size={40} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500 font-medium">No automation scripts yet</p>
          <p className="text-sm text-gray-400 mt-1">Use the AI Generate button to create scripts from approved test cases</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((s) => (
            <ScriptCard key={s.id} script={s} onApprove={handleApprove} onReject={handleReject} />
          ))}
        </div>
      )}
    </div>
  );
}
