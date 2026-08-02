"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, CheckCircle2, ChevronRight, Download, ExternalLink, FileWarning,
  Loader2, Lock, RefreshCw, ShieldCheck, Sparkles, XCircle,
} from "lucide-react";
import {
  applicationModelsApi, applicationsApi, discoveryApi, projectsApi, usersApi,
  type ApplicationModelActivityEntry, type ApplicationModelDetail, type ApplicationModelGap,
  type ApplicationModelNode, type ApplicationModelStatus, type DiscoverySession,
  type ProjectApplication,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type Props = { projectId: number; applicationId: number | null; modelId: number | null };

type CanvasTab = "screen_map" | "component_map" | "element_map" | "journey_overlay" | "api_map" | "evidence_overlay" | "change_comparison";
type GridTab = "screens" | "components" | "elements" | "gaps" | "journeys" | "apis" | "external_systems" | "evidence" | "version_changes";
type InspectorTab = "overview" | "structure" | "locators" | "journeys" | "apis_systems" | "evidence" | "gaps" | "history" | "activity";

const CANVAS_TABS: { key: CanvasTab; label: string; available: boolean; reason?: string }[] = [
  { key: "screen_map", label: "Screen Map", available: true },
  { key: "component_map", label: "Component Map", available: false, reason: "Planned for a later phase" },
  { key: "element_map", label: "Element Map", available: false, reason: "Planned for a later phase" },
  { key: "journey_overlay", label: "Journey Overlay", available: false, reason: "Requires journey/test-case linking (not yet built)" },
  { key: "api_map", label: "API & System Map", available: false, reason: "Requires API/network capture parsing (not yet built)" },
  { key: "evidence_overlay", label: "Evidence Overlay", available: false, reason: "Screenshot viewing is not yet available" },
  { key: "change_comparison", label: "Change Comparison", available: false, reason: "Planned for a later phase" },
];

const GRID_TABS: { key: GridTab; label: string; available: boolean; reason?: string }[] = [
  { key: "screens", label: "Screens", available: true },
  { key: "components", label: "Components", available: true },
  { key: "elements", label: "Elements", available: true },
  { key: "gaps", label: "Gaps", available: true },
  { key: "journeys", label: "Journeys & Test Cases", available: false, reason: "Requires journey/test-case linking (not yet built)" },
  { key: "apis", label: "APIs", available: false, reason: "Requires API/network capture parsing (not yet built)" },
  { key: "external_systems", label: "External Systems & MCPs", available: false, reason: "Requires API/network capture parsing (not yet built)" },
  { key: "evidence", label: "Evidence", available: false, reason: "Screenshot viewing is not yet available" },
  { key: "version_changes", label: "Version Changes", available: false, reason: "Planned for a later phase" },
];

const INSPECTOR_TABS: { key: InspectorTab; label: string; available: boolean; reason?: string }[] = [
  { key: "overview", label: "Overview", available: true },
  { key: "structure", label: "Structure", available: true },
  { key: "locators", label: "Locators", available: true },
  { key: "journeys", label: "Journeys", available: false, reason: "Requires journey/test-case linking (not yet built)" },
  { key: "apis_systems", label: "APIs & Systems", available: false, reason: "Requires API/network capture parsing (not yet built)" },
  { key: "evidence", label: "Evidence", available: false, reason: "Screenshot viewing is not yet available" },
  { key: "gaps", label: "Gaps", available: true },
  { key: "history", label: "History", available: true },
  { key: "activity", label: "Activity", available: true },
];

const STATUS_TONE: Record<ApplicationModelStatus, { label: string; variant: "success" | "info" | "warning" | "destructive" | "secondary" | "purple" }> = {
  draft: { label: "Draft", variant: "secondary" },
  pending_review: { label: "Pending Review", variant: "info" },
  changes_requested: { label: "Changes Requested", variant: "warning" },
  approved: { label: "Approved", variant: "purple" },
  published: { label: "Published", variant: "success" },
  superseded: { label: "Superseded", variant: "secondary" },
  rejected: { label: "Rejected", variant: "destructive" },
  stale: { label: "Stale", variant: "warning" },
  archived: { label: "Archived", variant: "secondary" },
};

function messageFromError(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  return fallback;
}

function Kpi({ label, value, subtitle, tone }: { label: string; value: string | number; subtitle?: string; tone?: "amber" | "red" }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-[9px] font-extrabold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={cn("mt-1 text-xl font-black", tone === "red" ? "text-red-600" : tone === "amber" ? "text-amber-600" : "text-slate-900")}>{value}</p>
      {subtitle && <p className="mt-0.5 text-[9px] font-semibold text-slate-400">{subtitle}</p>}
    </div>
  );
}

function Panel({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-[10px] font-extrabold text-slate-800">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function DisabledTabButton({ label, reason }: { label: string; reason?: string }) {
  return (
    <button
      disabled
      title={reason}
      className="inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-[10px] font-bold text-slate-300 cursor-not-allowed"
    >
      <Lock className="h-2.5 w-2.5" />
      {label}
    </button>
  );
}

function ReadinessRow({ label, state, detail }: { label: string; state: "pass" | "warning" | "blocked" | "not_evaluated"; detail: string }) {
  const icon = state === "pass" ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
    : state === "warning" ? <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
    : state === "blocked" ? <XCircle className="h-3.5 w-3.5 text-red-500" />
    : <FileWarning className="h-3.5 w-3.5 text-slate-300" />;
  return (
    <div className="flex items-start gap-2 py-1">
      {icon}
      <div className="min-w-0">
        <p className="text-[10px] font-bold text-slate-800">{label}</p>
        <p className="truncate text-[9px] font-semibold text-slate-500">{detail}</p>
      </div>
    </div>
  );
}

export function ApplicationModelView({ projectId, applicationId, modelId }: Props) {
  const [applications, setApplications] = useState<ProjectApplication[]>([]);
  const [selectedApplicationId, setSelectedApplicationId] = useState<number | null>(applicationId);
  const [model, setModel] = useState<ApplicationModelDetail | null>(null);
  const [versions, setVersions] = useState<ApplicationModelDetail[]>([]);
  const [nodes, setNodes] = useState<ApplicationModelNode[]>([]);
  const [gaps, setGaps] = useState<ApplicationModelGap[]>([]);
  const [activity, setActivity] = useState<ApplicationModelActivityEntry[]>([]);
  const [eligibleSessions, setEligibleSessions] = useState<DiscoverySession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);
  const [canApprove, setCanApprove] = useState(false);
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);

  const [canvasTab, setCanvasTab] = useState<CanvasTab>("screen_map");
  const [gridTab, setGridTab] = useState<GridTab>("screens");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("overview");

  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    applicationsApi.getForProject(projectId).then((res) => setApplications(res.data.applications)).catch(() => setApplications([]));
    Promise.all([usersApi.me(), projectsApi.memberships(projectId), projectsApi.roles()])
      .then(([meRes, membershipRes, roleRes]) => {
        setCurrentUserId(meRes.data.id);
        const membership = membershipRes.data.find((item) => item.is_active && item.user_id === meRes.data.id);
        const role = roleRes.data.find((item) => item.role === (membership?.role || meRes.data.role));
        setCanApprove(Boolean(meRes.data.is_superuser || role?.permissions.includes("application_model.approve")));
      })
      .catch(() => { setCanApprove(false); });
  }, [projectId]);

  useEffect(() => {
    if (!selectedApplicationId) return;
    discoveryApi.listSessions(projectId, { application_id: selectedApplicationId, status: "COMPLETED" })
      .then((res) => setEligibleSessions(res.data))
      .catch(() => setEligibleSessions([]));
  }, [projectId, selectedApplicationId]);

  async function loadModel(id: number) {
    setLoading(true);
    setError("");
    try {
      const [modelRes, nodesRes, gapsRes, activityRes] = await Promise.all([
        applicationModelsApi.get(id),
        applicationModelsApi.nodes(id),
        applicationModelsApi.gaps(id),
        applicationModelsApi.activity(id),
      ]);
      setModel(modelRes.data);
      if (modelRes.data.source_session_id) setSelectedSessionId(modelRes.data.source_session_id);
      setNodes(nodesRes.data);
      setGaps(gapsRes.data);
      setActivity(activityRes.data);
      if (selectedApplicationId) {
        const versionsRes = await applicationModelsApi.list(projectId, selectedApplicationId);
        const detailed = await Promise.all(versionsRes.data.map((v) => applicationModelsApi.get(v.id)));
        setVersions(detailed.map((r) => r.data));
      }
    } catch (loadError) {
      setError(messageFromError(loadError, "Could not load the application model."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (modelId) {
      loadModel(modelId);
      return;
    }
    if (!selectedApplicationId) return;
    applicationModelsApi.list(projectId, selectedApplicationId).then((res) => {
      const current = res.data.find((m) => m.is_current);
      if (current) loadModel(current.id);
      else setModel(null);
    }).catch(() => setModel(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, selectedApplicationId, modelId]);

  const screens = useMemo(() => nodes.filter((n) => n.node_type === "screen"), [nodes]);
  const components = useMemo(() => nodes.filter((n) => n.node_type === "component"), [nodes]);
  const elements = useMemo(() => nodes.filter((n) => n.node_type === "element"), [nodes]);
  const selectedNode = useMemo(() => nodes.find((n) => n.id === selectedNodeId) || null, [nodes, selectedNodeId]);
  const openGaps = useMemo(() => gaps.filter((g) => g.status === "open"), [gaps]);
  const criticalOpenGaps = useMemo(() => openGaps.filter((g) => g.severity === "critical"), [openGaps]);
  const isBuilder = model?.built_by != null && currentUserId != null && model.built_by === currentUserId;
  // Defaults to the strict rule while the detail is still loading, so the
  // Approve button is never briefly enabled on a deployment that forbids it.
  const requiresSeparateApprover = model?.requires_separate_approver ?? true;
  const isMutable = model ? ["draft", "pending_review", "changes_requested"].includes(model.status) : false;

  async function run(action: () => Promise<unknown>, successMessage: string) {
    setBusy(true);
    setError("");
    try {
      await action();
      setNotice(successMessage);
      if (model) await loadModel(model.id);
    } catch (actionError) {
      setError(messageFromError(actionError, "Action failed."));
    } finally {
      setBusy(false);
    }
  }

  async function handleBuild() {
    if (!selectedApplicationId || !selectedSessionId) {
      setError("Select a completed discovery session to build from.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await applicationModelsApi.build({
        project_id: projectId, application_id: selectedApplicationId, session_id: selectedSessionId,
      });
      setNotice("Model built from the selected discovery session.");
      await loadModel(res.data.id);
    } catch (buildError) {
      setError(messageFromError(buildError, "Could not build the model."));
    } finally {
      setBusy(false);
    }
  }

  if (!selectedApplicationId) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-8 text-center">
        <p className="text-sm font-bold text-slate-700">Select an application</p>
        <p className="mt-1 text-xs font-semibold text-slate-500">Choose an application below to view or build its Application Model.</p>
        <select
          className="mx-auto mt-4 block h-9 rounded-lg border border-slate-200 px-3 text-xs font-semibold"
          value=""
          onChange={(e) => setSelectedApplicationId(Number(e.target.value) || null)}
        >
          <option value="">Select application…</option>
          {applications.map((a) => <option key={a.id ?? a.key} value={a.id ?? ""}>{a.name}</option>)}
        </select>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
        <span>e&amp; STLC</span>
        <ChevronRight className="h-3 w-3 text-slate-300" />
        <span>Application Discovery</span>
        <ChevronRight className="h-3 w-3 text-slate-300" />
        <span className="text-slate-800">Application Model</span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900">Application Model</h1>
            <Badge variant="info">P1-S4 UI-016</Badge>
            {model && <Badge variant={STATUS_TONE[model.status].variant}>{STATUS_TONE[model.status].label}</Badge>}
            {model?.stale && <Badge variant="warning">Stale — source session has new activity</Badge>}
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Review, validate and publish the grounded application structure created from discovery evidence.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="h-9 rounded-lg border border-slate-200 px-3 text-xs font-semibold"
            value={selectedApplicationId}
            onChange={(e) => { setSelectedApplicationId(Number(e.target.value) || null); setModel(null); }}
          >
            {applications.map((a) => <option key={a.id ?? a.key} value={a.id ?? ""}>{a.name}</option>)}
          </select>
          {versions.length > 1 && model && (
            <select
              className="h-9 rounded-lg border border-slate-200 px-3 text-xs font-semibold"
              value={model.id}
              onChange={(e) => loadModel(Number(e.target.value))}
            >
              {versions.map((v) => <option key={v.id} value={v.id}>Version {v.version} ({v.status})</option>)}
            </select>
          )}
          <Button variant="outline" size="sm" onClick={() => model && loadModel(model.id)} disabled={loading || busy}>
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} /> Refresh
          </Button>
          {model && (
            <Button variant="outline" size="sm" onClick={() => window.open(applicationModelsApi.exportUrl(model.id), "_blank")}>
              <Download className="h-3.5 w-3.5" /> Export Model
            </Button>
          )}
        </div>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div>}
      {notice && <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-700">{notice}</div>}

      {!model && !loading && (
        <Panel title="No model yet">
          <p className="text-xs font-semibold text-slate-500">
            No Application Model exists yet for this application. Build one from a completed Live Discovery Session.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <select
              className="h-9 rounded-lg border border-slate-200 px-3 text-xs font-semibold"
              value={selectedSessionId ?? ""}
              onChange={(e) => setSelectedSessionId(Number(e.target.value) || null)}
            >
              <option value="">Select a completed discovery session…</option>
              {eligibleSessions.map((s) => <option key={s.id} value={s.id}>Session #{s.id} — {s.environment}</option>)}
            </select>
            <Button size="sm" onClick={handleBuild} disabled={busy || !selectedSessionId}>
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Build Model
            </Button>
            {eligibleSessions.length === 0 && (
              <a href={`/automation?view=discovery&project=${projectId}&application=${selectedApplicationId}`} className="text-[10px] font-bold text-[#1b59f8]">
                No completed sessions yet — open Live Discovery Session →
              </a>
            )}
          </div>
        </Panel>
      )}

      {loading && <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-xs font-semibold text-slate-400">Loading…</div>}

      {model && !loading && (
        <>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-6">
            <Kpi label="Screens" value={model.kpis.screens} />
            <Kpi label="Components" value={model.kpis.components} />
            <Kpi label="Elements" value={model.kpis.elements} />
            <Kpi label="Journeys" value={model.kpis.journeys} subtitle="Not yet mapped — requires UI-017" />
            <Kpi label="APIs" value={model.kpis.apis} subtitle="Not yet mapped — requires UI-017" />
            <Kpi
              label="Gaps"
              value={model.kpis.gaps_open}
              subtitle={`${model.kpis.gaps_critical_open} critical`}
              tone={model.kpis.gaps_critical_open > 0 ? "red" : model.kpis.gaps_open > 0 ? "amber" : undefined}
            />
          </div>

          <Panel title="Readiness & Governance">
            <div className="grid grid-cols-1 gap-x-6 gap-y-1 md:grid-cols-2">
              <ReadinessRow label="Registered application valid" state="pass" detail="Stable application ID resolved" />
              <ReadinessRow
                label="Source discovery session completed"
                state={model.source_session_id ? "pass" : "blocked"}
                detail={model.source_session_id ? `Session #${model.source_session_id}` : "No source session"}
              />
              {/* These rows are phrased as the absence of a gap, which made an
                  empty model pass every one of them: nothing discovered means
                  nothing to find fault with. Zero is now reported as a failure
                  in its own right, so "grounded" and "empty" stop looking
                  identical. */}
              <ReadinessRow
                label="Screen/component mappings reviewed"
                state={
                  screens.length === 0
                    // Severity, not type: a warning-level MISSING_COMPONENT is
                    // something a reviewer accepted, and showing it as blocked
                    // contradicted this model's own "0 critical" gap count.
                    || gaps.some((g) => g.status === "open" && g.severity === "critical"
                      && ["MISSING_SCREEN", "MISSING_COMPONENT"].includes(g.gap_type))
                    ? "blocked"
                    : gaps.some((g) => g.status === "open" && ["MISSING_SCREEN", "MISSING_COMPONENT"].includes(g.gap_type))
                      ? "warning"
                      : "pass"
                }
                detail={
                  screens.length === 0
                    ? "No screens discovered — nothing to ground tests against"
                    : `${screens.length} screens, ${components.length} components discovered`
                }
              />
              <ReadinessRow
                label="Element semantics and locators validated"
                state={
                  gaps.some((g) => g.status === "open" && g.severity === "critical" && g.gap_type === "MISSING_ELEMENT")
                    ? "blocked"
                    : elements.length === 0
                      || gaps.some((g) => g.status === "open" && ["AMBIGUOUS_ELEMENT", "UNSTABLE_LOCATOR"].includes(g.gap_type))
                      ? "warning"
                      : "pass"
                }
                detail={
                  elements.length === 0
                    ? "No elements discovered — no locators to validate"
                    : `${elements.length} elements discovered`
                }
              />
              <ReadinessRow label="Journey/test-case relationships valid" state="not_evaluated" detail="Not evaluated in this phase" />
              <ReadinessRow label="API/network relationships reviewed" state="not_evaluated" detail="Not evaluated in this phase" />
              {/* States the rule this deployment actually enforces. A
                  single-operator deployment turns it off, and claiming a
                  separate reviewer is required there would be false. */}
              <ReadinessRow
                label="Separation of duties valid"
                state={requiresSeparateApprover && isBuilder && model.status === "pending_review" ? "warning" : "pass"}
                detail={
                  !requiresSeparateApprover
                    ? "Not required in this deployment — the approver is still recorded"
                    : isBuilder
                      ? "You built this draft — a different reviewer must approve it"
                      : "Builder and approver can differ"
                }
              />
              <ReadinessRow
                label="No unresolved critical blocker"
                state={criticalOpenGaps.length > 0 ? "blocked" : "pass"}
                detail={`${criticalOpenGaps.length} open critical gap${criticalOpenGaps.length === 1 ? "" : "s"}`}
              />
            </div>
          </Panel>

          <Panel
            title="Model Actions"
            action={
              <div className="flex flex-wrap items-center gap-2">
                {isMutable && (
                  <>
                    {eligibleSessions.length > 1 && (
                      <select
                        className="h-8 rounded-md border border-slate-200 px-2 text-[10px] font-semibold"
                        value={selectedSessionId ?? ""}
                        onChange={(e) => setSelectedSessionId(Number(e.target.value) || null)}
                      >
                        {eligibleSessions.map((s) => <option key={s.id} value={s.id}>Session #{s.id} — {s.environment}</option>)}
                      </select>
                    )}
                    <Button size="sm" variant="outline" onClick={handleBuild} disabled={busy || !selectedSessionId} title="Rebuild from the selected completed session">
                      Rebuild
                    </Button>
                  </>
                )}
                {(model.status === "draft" || model.status === "changes_requested") && (
                  <Button size="sm" onClick={() => run(() => applicationModelsApi.submitReview(model.id), "Submitted for review.")} disabled={busy}>
                    Submit for Review
                  </Button>
                )}
                {model.status === "pending_review" && (
                  <>
                    <Button size="sm" variant="outline" onClick={() => {
                      const reason = window.prompt("Reason for requesting changes:");
                      if (reason) run(() => applicationModelsApi.requestChanges(model.id, reason), "Changes requested.");
                    }} disabled={busy}>Request Changes</Button>
                    <Button size="sm" variant="destructive" onClick={() => {
                      const reason = window.prompt("Reason for rejecting:");
                      if (reason) run(() => applicationModelsApi.reject(model.id, reason), "Model rejected.");
                    }} disabled={busy}>Reject</Button>
                    <Button
                      size="sm"
                      onClick={() => run(() => applicationModelsApi.approve(model.id, null), "Model approved.")}
                      disabled={busy || !canApprove || (requiresSeparateApprover && isBuilder) || criticalOpenGaps.length > 0}
                      title={
                        requiresSeparateApprover && isBuilder
                          ? "The user who built this draft cannot approve it"
                          : criticalOpenGaps.length > 0 ? "Resolve critical gaps first" : undefined
                      }
                    >
                      <ShieldCheck className="h-3.5 w-3.5" /> Approve
                    </Button>
                  </>
                )}
                {model.status === "approved" && (
                  <Button size="sm" onClick={() => run(() => applicationModelsApi.publish(model.id), "Model published.")} disabled={busy}>
                    Publish Model
                  </Button>
                )}
                {["approved", "published", "rejected"].includes(model.status) && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      setError("");
                      try {
                        const res = await applicationModelsApi.newDraft(model.id);
                        setNotice("New draft created.");
                        await loadModel(res.data.id);
                      } catch (draftError) {
                        setError(messageFromError(draftError, "Could not create a new draft."));
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Create New Draft
                  </Button>
                )}
              </div>
            }
          >
            <p className="text-[10px] font-semibold text-slate-500">
              Version {model.version} · Built {model.built_at ? new Date(model.built_at).toLocaleString() : "—"}
              {model.source_session_id && (
                <> · Source <a className="font-bold text-[#1b59f8]" href={`/automation?view=discovery&project=${projectId}&application=${selectedApplicationId}`}>Session #{model.source_session_id} <ExternalLink className="inline h-2.5 w-2.5" /></a></>
              )}
            </p>
          </Panel>

          <div className="grid grid-cols-1 gap-3 xl:grid-cols-[220px_1fr_320px]">
            <Panel title="Model Navigator">
              <div className="space-y-3 text-[10px]">
                <div>
                  <p className="mb-1 font-extrabold text-slate-700">Screens ({screens.length})</p>
                  <ul className="space-y-0.5">
                    {screens.map((s) => (
                      <li key={s.id}>
                        <button
                          onClick={() => setSelectedNodeId(s.id)}
                          className={cn("w-full truncate rounded px-1.5 py-0.5 text-left font-semibold hover:bg-slate-50", selectedNodeId === s.id && "bg-blue-50 text-[#1b59f8]")}
                        >
                          {s.display_name}
                        </button>
                        <ul className="ml-3 space-y-0.5">
                          {components.filter((c) => c.parent_node_id === s.id).map((c) => (
                            <li key={c.id}>
                              <button
                                onClick={() => setSelectedNodeId(c.id)}
                                className={cn("w-full truncate rounded px-1.5 py-0.5 text-left font-semibold text-slate-500 hover:bg-slate-50", selectedNodeId === c.id && "bg-blue-50 text-[#1b59f8]")}
                              >
                                {c.display_name}
                              </button>
                            </li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="mb-1 font-extrabold text-slate-700">Gaps ({openGaps.length})</p>
                  <p className="text-[9px] font-semibold text-slate-400">{criticalOpenGaps.length} critical, {openGaps.length - criticalOpenGaps.length} warning</p>
                </div>
                <div className="border-t border-slate-100 pt-2 opacity-40">
                  <p className="text-[9px] font-bold" title="Requires journey/test-case linking (not yet built)">Journeys</p>
                  <p className="text-[9px] font-bold" title="Requires API/network capture parsing (not yet built)">APIs & Network</p>
                  <p className="text-[9px] font-bold" title="Requires API/network capture parsing (not yet built)">External Systems & MCPs</p>
                  <p className="text-[9px] font-bold" title="Screenshot viewing is not yet available">Evidence</p>
                </div>
              </div>
            </Panel>

            <Panel
              title="Model Canvas"
              action={
                <div className="flex flex-wrap items-center gap-1">
                  {CANVAS_TABS.map((tab) =>
                    tab.available ? (
                      <button
                        key={tab.key}
                        onClick={() => setCanvasTab(tab.key)}
                        className={cn("rounded-md px-3 py-1.5 text-[10px] font-bold", canvasTab === tab.key ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-slate-100")}
                      >
                        {tab.label}
                      </button>
                    ) : <DisabledTabButton key={tab.key} label={tab.label} reason={tab.reason} />
                  )}
                </div>
              }
            >
              {canvasTab === "screen_map" && (
                <div className="overflow-x-auto py-2">
                  {screens.length === 0 ? (
                    <p className="p-6 text-center text-xs font-semibold text-slate-400">No screens discovered yet.</p>
                  ) : (
                    <div className="flex items-start gap-8">
                      {screens.map((s) => (
                        <button
                          key={s.id}
                          onClick={() => setSelectedNodeId(s.id)}
                          className={cn(
                            "flex min-w-[140px] flex-col items-start gap-1 rounded-lg border-2 bg-white p-3 text-left shadow-sm",
                            selectedNodeId === s.id ? "border-[#1b59f8]" : "border-slate-200",
                          )}
                        >
                          <span className="text-[10px] font-extrabold text-slate-900">{s.display_name}</span>
                          <span className="text-[9px] font-semibold text-slate-400">{components.filter((c) => c.parent_node_id === s.id).length} components</span>
                          <Badge variant={s.state === "DISCOVERED" ? "info" : "secondary"} className="text-[8px]">{s.state}</Badge>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </Panel>

            <Panel
              title="Inspector"
              action={
                <select
                  className="h-7 rounded-md border border-slate-200 px-1.5 text-[9px] font-bold"
                  value={inspectorTab}
                  onChange={(e) => setInspectorTab(e.target.value as InspectorTab)}
                >
                  {INSPECTOR_TABS.map((tab) => (
                    <option key={tab.key} value={tab.key} disabled={!tab.available}>{tab.label}{!tab.available ? " (unavailable)" : ""}</option>
                  ))}
                </select>
              }
            >
              {inspectorTab === "overview" && (
                selectedNode ? (
                  <div className="space-y-1 text-[10px]">
                    <p className="font-extrabold text-slate-900">{selectedNode.display_name}</p>
                    <p className="font-semibold text-slate-500">Type: {selectedNode.node_type}</p>
                    <p className="font-semibold text-slate-500">External ref: {selectedNode.external_ref}</p>
                    <p className="font-semibold text-slate-500">State: {selectedNode.state}</p>
                    {isMutable && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="mt-2"
                        onClick={() => {
                          const name = window.prompt("New semantic name:", selectedNode.display_name);
                          if (name && name.trim()) run(() => applicationModelsApi.renameNode(model.id, selectedNode.id, name.trim()), "Node renamed.");
                        }}
                      >
                        Edit semantic name
                      </Button>
                    )}
                  </div>
                ) : <p className="text-[10px] font-semibold text-slate-400">Select a node to inspect it.</p>
              )}
              {inspectorTab === "structure" && (
                selectedNode ? (
                  <div className="space-y-1 text-[10px]">
                    <p className="font-bold text-slate-700">Parent: {nodes.find((n) => n.id === selectedNode.parent_node_id)?.display_name || "—"}</p>
                    <p className="font-bold text-slate-700">Children: {nodes.filter((n) => n.parent_node_id === selectedNode.id).map((n) => n.display_name).join(", ") || "None"}</p>
                  </div>
                ) : <p className="text-[10px] font-semibold text-slate-400">Select a node to inspect its structure.</p>
              )}
              {inspectorTab === "locators" && (
                selectedNode?.node_type === "element" ? (
                  <NodeLocatorInspector modelId={model.id} node={selectedNode} isMutable={isMutable} onChanged={() => loadModel(model.id)} />
                ) : <p className="text-[10px] font-semibold text-slate-400">Select an element to view its locator evidence.</p>
              )}
              {inspectorTab === "gaps" && (
                <div className="space-y-2">
                  {(selectedNode ? gaps.filter((g) => g.node_id === selectedNode.id) : gaps).map((g) => (
                    <GapRow key={g.id} gap={g} modelId={model.id} isMutable={isMutable} onChanged={() => loadModel(model.id)} />
                  ))}
                  {gaps.length === 0 && <p className="text-[10px] font-semibold text-slate-400">No gaps recorded.</p>}
                </div>
              )}
              {inspectorTab === "history" && (
                <div className="space-y-1.5">
                  {activity.map((a) => (
                    <div key={a.id} className="text-[9px]">
                      <p className="font-bold text-slate-700">{new Date(a.at).toLocaleString()}</p>
                      <p className="font-semibold text-slate-500">{a.event_type}{a.reason ? ` — ${a.reason}` : ""}</p>
                    </div>
                  ))}
                  {activity.length === 0 && <p className="text-[10px] font-semibold text-slate-400">No history yet.</p>}
                </div>
              )}
              {inspectorTab === "activity" && (
                <div className="space-y-1.5">
                  {activity.map((a) => (
                    <div key={a.id} className="text-[9px]">
                      <p className="font-bold text-slate-700">{a.event_type}</p>
                      <p className="font-semibold text-slate-500">{new Date(a.at).toLocaleString()}</p>
                    </div>
                  ))}
                  {activity.length === 0 && <p className="text-[10px] font-semibold text-slate-400">No activity yet.</p>}
                </div>
              )}
            </Panel>
          </div>

          <Panel
            title="Relationships"
            action={
              <div className="flex flex-wrap items-center gap-1">
                {GRID_TABS.map((tab) =>
                  tab.available ? (
                    <button
                      key={tab.key}
                      onClick={() => setGridTab(tab.key)}
                      className={cn("rounded-md px-2.5 py-1 text-[9px] font-bold", gridTab === tab.key ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-slate-100")}
                    >
                      {tab.label}
                    </button>
                  ) : <DisabledTabButton key={tab.key} label={tab.label} reason={tab.reason} />
                )}
              </div>
            }
          >
            {gridTab === "screens" && <NodeTable nodes={screens} onSelect={setSelectedNodeId} selectedId={selectedNodeId} />}
            {gridTab === "components" && <NodeTable nodes={components} onSelect={setSelectedNodeId} selectedId={selectedNodeId} />}
            {gridTab === "elements" && <NodeTable nodes={elements} onSelect={setSelectedNodeId} selectedId={selectedNodeId} />}
            {gridTab === "gaps" && (
              <div className="space-y-2">
                {gaps.map((g) => <GapRow key={g.id} gap={g} modelId={model.id} isMutable={isMutable} onChanged={() => loadModel(model.id)} />)}
                {gaps.length === 0 && <p className="text-[10px] font-semibold text-slate-400">No gaps recorded.</p>}
              </div>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}

function NodeTable({ nodes, onSelect, selectedId }: { nodes: ApplicationModelNode[]; onSelect: (id: number) => void; selectedId: number | null }) {
  if (nodes.length === 0) return <p className="p-4 text-center text-[10px] font-semibold text-slate-400">None discovered yet.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[10px]">
        <thead>
          <tr className="border-b border-slate-100 text-[9px] font-extrabold uppercase text-slate-400">
            <th className="py-1.5">Name</th><th>External Ref</th><th>State</th>
          </tr>
        </thead>
        <tbody>
          {nodes.map((n) => (
            <tr key={n.id} onClick={() => onSelect(n.id)} className={cn("cursor-pointer border-b border-slate-50 hover:bg-slate-50", selectedId === n.id && "bg-blue-50/40")}>
              <td className="py-1.5 font-bold text-slate-800">{n.display_name}</td>
              <td className="font-semibold text-slate-500">{n.external_ref}</td>
              <td><Badge variant={n.state === "DISCOVERED" ? "info" : "secondary"} className="text-[8px]">{n.state}</Badge></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GapRow({ gap, modelId, isMutable, onChanged }: { gap: ApplicationModelGap; modelId: number; isMutable: boolean; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  async function resolve() {
    setBusy(true);
    try {
      await applicationModelsApi.resolveGap(modelId, gap.id);
      onChanged();
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex items-start justify-between gap-2 rounded-md border border-slate-100 p-2">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <Badge variant={gap.severity === "critical" ? "destructive" : "warning"} className="text-[8px]">{gap.severity}</Badge>
          <p className="text-[10px] font-extrabold text-slate-800">{gap.gap_type.replace(/_/g, " ")}</p>
        </div>
        {gap.remediation && <p className="mt-0.5 text-[9px] font-semibold text-slate-500">{gap.remediation}</p>}
      </div>
      {gap.status === "open" && isMutable && (
        <Button size="sm" variant="outline" onClick={resolve} disabled={busy}>{busy ? <Loader2 className="h-3 w-3 animate-spin" /> : "Resolve"}</Button>
      )}
      {gap.status === "resolved" && <Badge variant="success" className="text-[8px]">Resolved</Badge>}
    </div>
  );
}

function NodeLocatorInspector({ modelId, node, isMutable, onChanged }: { modelId: number; node: ApplicationModelNode; isMutable: boolean; onChanged: () => void }) {
  const [history, setHistory] = useState<Awaited<ReturnType<typeof applicationModelsApi.locatorHistory>>["data"]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    applicationModelsApi.locatorHistory(modelId, node.id).then((res) => setHistory(res.data)).catch(() => setHistory([]));
  }, [modelId, node.id]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      const res = await applicationModelsApi.locatorHistory(modelId, node.id);
      setHistory(res.data);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  const latest = history[0];
  return (
    <div className="space-y-2">
      {latest ? (
        <div className="rounded-md border border-slate-100 p-2 text-[10px]">
          <p className="font-bold text-slate-800">{latest.locator_value || "No locator value"}</p>
          <p className="font-semibold text-slate-500">Confidence: {latest.confidence ?? "—"} · Status: {latest.status}</p>
        </div>
      ) : <p className="text-[10px] font-semibold text-slate-400">No locator evidence captured.</p>}
      {isMutable && (
        <div className="flex flex-wrap gap-1.5">
          <Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => applicationModelsApi.confirmLocator(modelId, node.id))}>Confirm</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => {
            const reason = window.prompt("Reason this locator is unstable:");
            if (reason) act(() => applicationModelsApi.markLocatorUnstable(modelId, node.id, reason));
          }}>Mark Unstable</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => {
            const value = window.prompt("Fallback locator value:");
            if (value) act(() => applicationModelsApi.addFallbackLocator(modelId, node.id, value));
          }}>Add Fallback</Button>
        </div>
      )}
      <div className="space-y-1 border-t border-slate-100 pt-2">
        <p className="text-[9px] font-extrabold text-slate-600">History</p>
        {history.slice(1).map((h) => (
          <p key={h.id} className="text-[9px] font-semibold text-slate-500">{new Date(h.created_at).toLocaleString()} · {h.status} · {h.locator_value || "—"}</p>
        ))}
      </div>
    </div>
  );
}
