"use client";

import { useState, useEffect, useCallback } from "react";
import { FileText, Upload, Bot, CheckCircle, XCircle, Clock, RefreshCw, AlertTriangle, Eye, Star, Trash2, X as XIcon } from "lucide-react";
import { requirementsApi, documentsApi, projectsApi, type Requirement, type Document, type Project } from "@/lib/api";

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { color: string; label: string }> = {
    draft: { color: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300", label: "Draft" },
    pending_review: { color: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300", label: "Pending Review" },
    approved: { color: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300", label: "Approved" },
    rejected: { color: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300", label: "Rejected" },
    processed: { color: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300", label: "Processed" },
    uploaded: { color: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300", label: "Uploaded" },
    failed: { color: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300", label: "Failed" },
  };
  const s = map[status] ?? { color: "bg-slate-100 text-slate-600", label: status };
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${s.color}`}>{s.label}</span>;
}

function QualityBadge({ score, verdict }: { score?: number; verdict?: string }) {
  if (!verdict) return null;
  const color = verdict === "pass" ? "text-emerald-600 dark:text-emerald-400"
    : verdict === "needs_revision" ? "text-amber-600 dark:text-amber-400"
    : "text-red-600 dark:text-red-400";
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${color}`}>
      <Star className="h-3 w-3" />{score !== undefined ? `${Number(score).toFixed(1)}/5` : verdict}
    </span>
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={onCancel}>
      <div className="w-full max-w-sm rounded-2xl border bg-card shadow-2xl p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start gap-3">
          <div className="rounded-full bg-red-100 dark:bg-red-900/30 p-2 shrink-0">
            <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="font-semibold text-base">{title}</h2>
            <p className="text-sm text-muted-foreground mt-1">{description}</p>
          </div>
          <button onClick={onCancel} className="rounded-md p-1 hover:bg-muted text-muted-foreground shrink-0">
            <XIcon className="h-4 w-4" />
          </button>
        </div>
        {error && (
          <div className="rounded-lg bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-400">
            {error}
          </div>
        )}
        <div className="flex gap-2 pt-1">
          <button onClick={onCancel} disabled={deleting}
            className="flex-1 rounded-lg border px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50 transition-colors">
            Cancel
          </button>
          <button onClick={handleConfirm} disabled={deleting}
            className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors">
            {deleting ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            {deleting ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

function RequirementDetail({ req, onApprove, onClose }: {
  req: Requirement;
  onApprove: (id: number, action: "approve" | "reject", notes?: string) => Promise<void>;
  onClose: () => void;
}) {
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const quality = (req.metadata_ as Record<string, unknown> | undefined)?.quality_review as Record<string, unknown> | undefined;

  const handleAction = async (action: "approve" | "reject") => {
    setLoading(true);
    try { await onApprove(req.id, action, notes || undefined); } finally { setLoading(false); }
  };

  const fields: [string, string[] | undefined][] = [
    ["Acceptance Criteria", req.acceptance_criteria],
    ["Business Rules", req.business_rules],
    ["User Roles", req.user_roles],
    ["Systems Impacted", req.systems_impacted],
    ["Risks", req.risks],
    ["Missing Information", req.missing_information],
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-end bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <div className="h-full w-full max-w-2xl overflow-y-auto bg-card border-l shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-card border-b px-6 py-4 flex items-start justify-between z-10">
          <div className="flex-1 min-w-0 pr-4">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="text-xs font-mono text-muted-foreground">{req.requirement_id}</span>
              <StatusBadge status={req.status} />
            </div>
            <h2 className="font-semibold text-lg leading-tight">{req.title}</h2>
          </div>
          <button onClick={onClose} className="rounded-md p-1.5 hover:bg-muted text-muted-foreground shrink-0 mt-1">
            <XCircle className="h-5 w-5" />
          </button>
        </div>
        <div className="p-6 space-y-6">
          {req.summary && (
            <section>
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Summary</h3>
              <p className="text-sm leading-relaxed">{req.summary}</p>
            </section>
          )}
          {quality && (
            <section className="rounded-xl border bg-muted/30 p-4">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <Star className="h-4 w-4 text-amber-500" />AI Quality Review
                <QualityBadge score={quality.overall_score as number | undefined} verdict={quality.verdict as string | undefined} />
              </h3>
              <div className="grid grid-cols-3 gap-3 mb-4 text-center">
                {[["Completeness", "completeness_score"], ["Clarity", "clarity_score"], ["Testability", "testability_score"]].map(([label, key]) => (
                  <div key={key}>
                    <div className="text-2xl font-bold">{(quality[key] as number) ?? "?"}</div>
                    <div className="text-xs text-muted-foreground">{label}</div>
                  </div>
                ))}
              </div>
              {(quality.issues as string[] | undefined)?.length ? (
                <div className="mb-3">
                  <p className="text-xs font-medium text-red-600 dark:text-red-400 mb-1">Issues Found</p>
                  <ul className="text-xs space-y-1">
                    {(quality.issues as string[]).map((issue, i) => (
                      <li key={i} className="flex gap-2"><span className="text-red-400 shrink-0">*</span>{issue}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {(quality.suggestions as string[] | undefined)?.length ? (
                <div>
                  <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mb-1">Suggestions</p>
                  <ul className="text-xs space-y-1">
                    {(quality.suggestions as string[]).map((s, i) => (
                      <li key={i} className="flex gap-2"><span className="text-blue-400 shrink-0">-&gt;</span>{s}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>
          )}
          {fields.map(([label, items]) => items?.length ? (
            <section key={label}>
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">{label}</h3>
              <ul className="space-y-1.5">
                {items.map((item, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <span className="text-primary shrink-0 mt-0.5">*</span><span>{item}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null)}
          {req.status === "pending_review" && (
            <section className="rounded-xl border-2 border-dashed p-4 space-y-3">
              <h3 className="text-sm font-semibold">Review Decision</h3>
              <textarea
                className="w-full rounded-lg border bg-background px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/50"
                rows={3}
                placeholder="Optional notes / feedback..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
              <div className="flex gap-2">
                <button
                  onClick={() => handleAction("approve")} disabled={loading}
                  className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  <CheckCircle className="h-4 w-4" />Approve
                </button>
                <button
                  onClick={() => handleAction("reject")} disabled={loading}
                  className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                >
                  <XCircle className="h-4 w-4" />Reject
                </button>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

export default function RequirementsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentStatus, setAgentStatus] = useState<string>("");
  const [selectedReq, setSelectedReq] = useState<Requirement | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [tab, setTab] = useState<"requirements" | "documents">("requirements");
  const [deletingReq, setDeletingReq] = useState<Requirement | null>(null);
  const [deletingDoc, setDeletingDoc] = useState<Document | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    projectsApi.list()
      .then((res) => { setProjects(res.data); const _urlP = typeof window !== "undefined" ? Number(new URLSearchParams(window.location.search).get("project")) || null : null; setSelectedProject(_urlP ?? (res.data[0]?.id ?? null)); })
      .catch((e: any) => setLoadError(e?.response?.data?.detail || e?.message || "Failed to load projects. Is the backend running?"));
  }, []);

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
      setLoadError(e?.response?.data?.detail || e?.message || "Failed to load data. Check that the backend is running at http://localhost:8000");
    }
    finally { setLoading(false); }
  }, [selectedProject]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleFileUpload = async (file: File) => {
    if (!selectedProject) return;
    setUploading(true);
    try {
      await documentsApi.upload(selectedProject, file);
      await loadData();
      setTab("documents"); // auto-switch so user sees the document + Extract button
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setAgentStatus(detail ? `Upload failed: ${detail}` : "Upload failed — check file type and backend logs.");
      setTab("documents");
    } finally { setUploading(false); }
  };

  const runIntakeAgent = async (docId: number) => {
    if (!selectedProject) return;
    setAgentRunning(true);
    setAgentStatus("Agent 1 running -- extracting requirements from document...");
    try {
      const res = await requirementsApi.triggerIntake(selectedProject, docId);
      setAgentStatus(`Done: ${(res.data as Record<string, unknown>).message}`);
      await loadData();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setAgentStatus(detail ? `Agent failed: ${detail}` : "Agent failed. Check backend logs.");
    }
    finally { setAgentRunning(false); }
  };

  const runQualityAgent = async (reqIds?: number[]) => {
    if (!selectedProject) return;
    setAgentRunning(true);
    setAgentStatus("Agent 2 running -- reviewing requirement quality...");
    try {
      const res = await requirementsApi.triggerQuality(selectedProject, reqIds);
      const data = res.data as Record<string, unknown>;
      const summary = data.summary as Record<string, number> | undefined;
      setAgentStatus(`Done. Pass: ${summary?.pass ?? 0}, Needs Revision: ${summary?.needs_revision ?? 0}, Fail: ${summary?.fail ?? 0}`);
      await loadData();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setAgentStatus(detail ? `Quality review failed: ${detail}` : "Quality review failed. Check backend logs.");
    }
    finally { setAgentRunning(false); }
  };

  const handleApprove = async (id: number, action: "approve" | "reject", notes?: string) => {
    await requirementsApi.approve(id, action, notes);
    await loadData();
    setSelectedReq(null);
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

  const filtered = requirements.filter((r) => filterStatus === "all" || r.status === filterStatus);
  const stats = {
    total: requirements.length,
    approved: requirements.filter((r) => r.status === "approved").length,
    pending: requirements.filter((r) => r.status === "pending_review").length,
    draft: requirements.filter((r) => r.status === "draft").length,
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Requirements</h1>
          <p className="text-sm text-muted-foreground mt-1">Upload documents to extract and manage AI-structured requirements</p>
        </div>
        <div className="flex items-center gap-2">
          {projects.length > 0 && (
            <select className="rounded-lg border bg-card px-3 py-2 text-sm focus:outline-none"
              value={selectedProject ?? ""} onChange={(e) => setSelectedProject(Number(e.target.value))}>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          )}
          <button onClick={loadData} className="rounded-lg border p-2 hover:bg-muted" title="Refresh">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {loadError && (
        <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-400">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <span className="flex-1">{loadError}</span>
          <button onClick={() => setLoadError(null)} className="opacity-60 hover:opacity-100"><XCircle className="h-4 w-4" /></button>
        </div>
      )}

      {projects.length === 0 && !loadError && (
        <div className="rounded-xl border border-dashed p-12 text-center text-muted-foreground">
          <FileText className="mx-auto h-10 w-10 mb-3 opacity-40" />
          <p className="font-medium">No projects found</p>
          <p className="text-sm mt-1">Create a project first from the Projects section</p>
        </div>
      )}

      {selectedProject && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: "Total", value: stats.total, color: "" },
              { label: "Approved", value: stats.approved, color: "text-emerald-600 dark:text-emerald-400" },
              { label: "Pending Review", value: stats.pending, color: "text-amber-600 dark:text-amber-400" },
              { label: "Draft", value: stats.draft, color: "text-slate-500" },
            ].map((s) => (
              <div key={s.label} className="rounded-xl border bg-card p-4">
                <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
                <div className="text-xs text-muted-foreground">{s.label}</div>
              </div>
            ))}
          </div>

          {(agentRunning || agentStatus) && (
            <div className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-sm ${
              agentRunning ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300"
              : agentStatus.startsWith("Done") ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
              : "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300"
            }`}>
              {agentRunning ? <RefreshCw className="h-4 w-4 animate-spin shrink-0" /> : <Bot className="h-4 w-4 shrink-0" />}
              <span className="flex-1">{agentStatus}</span>
              {!agentRunning && (
                <button onClick={() => setAgentStatus("")} className="opacity-60 hover:opacity-100">
                  <XCircle className="h-4 w-4" />
                </button>
              )}
            </div>
          )}

          <div className="flex gap-1 rounded-xl border bg-muted/30 p-1 w-fit">
            {(["requirements", "documents"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`rounded-lg px-4 py-1.5 text-sm font-medium capitalize transition-all ${tab === t ? "bg-card shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
                {t}
                {t === "requirements" && requirements.length > 0 && (
                  <span className="ml-1.5 rounded-full bg-primary/10 px-1.5 py-0.5 text-xs text-primary">{requirements.length}</span>
                )}
                {t === "documents" && documents.length > 0 && (
                  <span className="ml-1.5 rounded-full bg-primary/10 px-1.5 py-0.5 text-xs text-primary">{documents.length}</span>
                )}
              </button>
            ))}
          </div>

          {tab === "documents" && (
            <div className="space-y-4">
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFileUpload(f); }}
                className={`relative rounded-xl border-2 border-dashed p-12 text-center transition-all ${dragOver ? "border-primary bg-primary/5" : "hover:border-muted-foreground/50"}`}
              >
                <input id="file-upload" type="file" className="sr-only"
                  accept=".pdf,.docx,.txt,.md,.csv,.xlsx"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileUpload(f); }} />
                <label htmlFor="file-upload" className="cursor-pointer">
                  {uploading
                    ? <RefreshCw className="mx-auto h-10 w-10 animate-spin text-primary mb-3" />
                    : <Upload className="mx-auto h-10 w-10 text-muted-foreground mb-3" />}
                  <p className="font-medium">{uploading ? "Uploading and extracting text..." : "Drop a document here or click to upload"}</p>
                  <p className="text-sm text-muted-foreground mt-1">PDF, DOCX, TXT, MD, CSV, XLSX -- up to 25 MB</p>
                </label>
              </div>
              {documents.length > 0 ? (
                <div className="rounded-xl border divide-y overflow-hidden">
                  {documents.map((doc) => (
                    <div key={doc.id} className="flex items-center gap-4 px-4 py-3 bg-card hover:bg-muted/30 group">
                      <FileText className="h-5 w-5 text-primary shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{doc.original_filename}</p>
                        <p className="text-xs text-muted-foreground">
                          {doc.file_type.toUpperCase()} · {(doc.file_size_bytes / 1024).toFixed(0)} KB
                          {doc.page_count ? ` · ${doc.page_count} pages` : ""}
                        </p>
                      </div>
                      <StatusBadge status={doc.status} />
                      {doc.status === "processed" && (
                        <button onClick={() => runIntakeAgent(doc.id)} disabled={agentRunning}
                          className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 shrink-0">
                          <Bot className="h-3.5 w-3.5" />Extract Requirements
                        </button>
                      )}
                      {doc.status === "failed" && (
                        <span className="text-xs text-destructive shrink-0">Extraction failed — unsupported content?</span>
                      )}
                      {doc.status === "uploaded" && (
                        <span className="text-xs text-muted-foreground shrink-0 animate-pulse">Processing…</span>
                      )}
                      <button
                        onClick={() => setDeletingDoc(doc)}
                        className="rounded-md p-1.5 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400 transition-all shrink-0"
                        title="Delete document"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : !uploading ? (
                <p className="text-center text-sm text-muted-foreground py-6">No documents uploaded yet.</p>
              ) : null}
            </div>
          )}

          {tab === "requirements" && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 flex-wrap">
                <div className="flex gap-1 rounded-lg border bg-card p-1">
                  {["all", "draft", "pending_review", "approved", "rejected"].map((s) => (
                    <button key={s} onClick={() => setFilterStatus(s)}
                      className={`rounded-md px-3 py-1 text-xs font-medium capitalize transition-all ${filterStatus === s ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                      {s.replace(/_/g, " ")}
                      {s === "pending_review" && stats.pending > 0 && (
                        <span className="ml-1 rounded-full bg-amber-100 dark:bg-amber-900/40 px-1 text-amber-700 dark:text-amber-300">{stats.pending}</span>
                      )}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => runQualityAgent()}
                  disabled={agentRunning || requirements.length === 0}
                  className="ml-auto flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium hover:bg-muted disabled:opacity-50 transition-colors"
                >
                  <Bot className="h-3.5 w-3.5" />
                  Run Quality Review
                </button>
              </div>

              {loading ? (
                <div className="flex items-center justify-center py-16 text-muted-foreground">
                  <RefreshCw className="h-5 w-5 animate-spin mr-2" />Loading requirements…
                </div>
              ) : filtered.length > 0 ? (
                <div className="rounded-xl border divide-y overflow-hidden">
                  {filtered.map((req) => (
                    <div
                      key={req.id}
                      className="flex items-center gap-4 px-4 py-3 bg-card hover:bg-muted/30 cursor-pointer group"
                      onClick={() => setSelectedReq(req)}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-0.5">
                          <span className="text-xs font-mono text-muted-foreground">{req.requirement_id}</span>
                          <StatusBadge status={req.status} />
                          <QualityBadge
                            score={(req.metadata_ as Record<string, any>)?.quality_review?.overall_score}
                            verdict={(req.metadata_ as Record<string, any>)?.quality_review?.verdict}
                          />
                        </div>
                        <p className="text-sm font-medium truncate">{req.title}</p>
                        {req.summary && (
                          <p className="text-xs text-muted-foreground truncate mt-0.5">{req.summary}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={(e) => { e.stopPropagation(); setSelectedReq(req); }}
                          className="rounded-md p-1.5 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-muted transition-all"
                          title="View details"
                        >
                          <Eye className="h-4 w-4" />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); setDeletingReq(req); }}
                          className="rounded-md p-1.5 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400 transition-all"
                          title="Delete requirement"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-dashed p-12 text-center text-muted-foreground">
                  <FileText className="mx-auto h-10 w-10 mb-3 opacity-40" />
                  <p className="font-medium">
                    {filterStatus === "all" ? "No requirements yet" : `No ${filterStatus.replace(/_/g, " ")} requirements`}
                  </p>
                  <p className="text-sm mt-1">
                    {filterStatus === "all"
                      ? "Upload a document and run the intake agent to extract requirements"
                      : "Try changing the status filter"}
                  </p>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {selectedReq && (
        <RequirementDetail
          req={selectedReq}
          onApprove={handleApprove}
          onClose={() => setSelectedReq(null)}
        />
      )}

      {deletingReq && (
        <ConfirmDeleteModal
          title="Delete Requirement"
          description={`"${deletingReq.title}" will be permanently deleted. This cannot be undone.`}
          onConfirm={handleDeleteReq}
          onCancel={() => setDeletingReq(null)}
        />
      )}

      {deletingDoc && (
        <ConfirmDeleteModal
          title="Delete Document"
          description={`"${deletingDoc.original_filename}" and any requirements extracted from it will be permanently deleted.`}
          onConfirm={handleDeleteDoc}
          onCancel={() => setDeletingDoc(null)}
        />
      )}
    </div>
  );
}
