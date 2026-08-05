"use client";

/**
 * UI-016 Application Model.
 *
 * Rebuilt on the Test Case module's list-and-drawer pattern. The previous
 * layout had three tab strips (canvas, grid, inspector), most of whose tabs
 * were permanently locked, a 220px navigator tree at 9-10px type, and an
 * inspector reached through a `<select>`. Governance decisions — request
 * changes, reject, rename, mark a locator unstable — all went through
 * `window.prompt()`.
 *
 * Now: one list of what the model contains, one drawer per node with its
 * structure, locator evidence and gaps on labelled tabs, and a governance
 * panel that says in words which transition is available and what is
 * blocking the ones that are not.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Boxes, CheckCircle2, Component, Download, ExternalLink, Layers3,
  Loader2, MousePointerClick, Radar, RefreshCw, Search, ShieldCheck, Sparkles, Target, X,
} from "lucide-react";
import {
  applicationModelsApi, applicationsApi, discoveryApi, projectsApi, usersApi,
  type ApplicationModelActivityEntry, type ApplicationModelDetail, type ApplicationModelGap,
  type ApplicationModelNode, type ApplicationModelStatus, type DiscoverySession,
  type LocatorEvidenceEntry, type ProjectApplication,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Drawer, DrawerContent } from "@/components/ui/drawer";
import { cn } from "@/lib/utils";
import { messageFromError } from "./shared";
import {
  Breadcrumb, ChecklistRow, DrawerCard, DrawerTabBar, EmptyState, FilterSelect, GuidanceCard,
  InfoPair, ListRow, ListShell, Notices, QueueTabs, ReasonDrawer, StatCard, WorkspaceHeader,
  type DrawerTabSpec, type ReasonRequest,
} from "./workspace";

type Props = { projectId: number; applicationId: number | null; modelId: number | null };

type DrawerTab = "overview" | "structure" | "locators" | "gaps" | "journeys" | "apis" | "evidence" | "activity";
type QueueKey = "all" | "screens" | "components" | "elements" | "gaps";

const DRAWER_TABS: DrawerTabSpec<DrawerTab>[] = [
  { key: "overview", label: "Overview" },
  { key: "structure", label: "Structure" },
  { key: "locators", label: "Locators" },
  { key: "gaps", label: "Gaps" },
  { key: "activity", label: "Activity" },
  { key: "journeys", label: "Journeys", available: false, reason: "Requires journey/test-case linking, which is not built yet" },
  { key: "apis", label: "APIs & Systems", available: false, reason: "Requires API/network relationships to be published from UI-017" },
  { key: "evidence", label: "Evidence", available: false, reason: "Screenshot viewing is not available yet" },
];

const QUEUE_TABS: { key: QueueKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "screens", label: "Screens" },
  { key: "components", label: "Components" },
  { key: "elements", label: "Elements" },
  { key: "gaps", label: "Gaps" },
];

const NODE_GRID = "minmax(200px,1fr) 110px minmax(180px,1fr) 130px 110px 90px";
const GAP_GRID = "110px minmax(200px,1fr) minmax(220px,1.4fr) 130px 110px";

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

const NODE_ICON = { screen: Layers3, component: Component, element: MousePointerClick } as const;

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
  /** Once the user picks a rebuild source, model reloads stop overriding it. */
  const [sessionPickedByUser, setSessionPickedByUser] = useState(false);
  const [canApprove, setCanApprove] = useState(false);
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);

  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("overview");
  const [queueTab, setQueueTab] = useState<QueueKey>("all");
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState("");

  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reasonRequest, setReasonRequest] = useState<ReasonRequest | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");

  useEffect(() => {
    applicationsApi.getForProject(projectId)
      .then((res) => setApplications(res.data.applications))
      .catch(() => setApplications([]));
    Promise.all([usersApi.me(), projectsApi.memberships(projectId), projectsApi.roles()])
      .then(([meRes, membershipRes, roleRes]) => {
        setCurrentUserId(meRes.data.id);
        const membership = membershipRes.data.find((item) => item.is_active && item.user_id === meRes.data.id);
        const role = roleRes.data.find((item) => item.role === (membership?.role || meRes.data.role));
        setCanApprove(Boolean(meRes.data.is_superuser || role?.permissions.includes("application_model.approve")));
      })
      .catch(() => setCanApprove(false));
  }, [projectId]);

  useEffect(() => {
    if (!selectedApplicationId) return;
    discoveryApi.listSessions(projectId, { application_id: selectedApplicationId, status: "COMPLETED" })
      .then((res) => {
        setEligibleSessions(res.data);
        setSelectedSessionId((current) => current ?? res.data[0]?.id ?? null);
      })
      .catch(() => setEligibleSessions([]));
  }, [projectId, selectedApplicationId]);

  const loadModel = useCallback(async (id: number, applicationScope: number | null) => {
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
      // Seed the rebuild picker from this model's provenance, but never over
      // a choice the user made. This used to assign unconditionally, so every
      // action that reloaded the model silently discarded a deliberate
      // rebuild selection and snapped the picker back to the built-from
      // session — which then looked like the picker was ignoring input.
      if (modelRes.data.source_session_id && !sessionPickedByUser) {
        setSelectedSessionId(modelRes.data.source_session_id);
      }
      setNodes(nodesRes.data);
      setGaps(gapsRes.data);
      setActivity(activityRes.data);
      if (applicationScope) {
        const versionsRes = await applicationModelsApi.list(projectId, applicationScope);
        const detailed = await Promise.all(versionsRes.data.map((v) => applicationModelsApi.get(v.id)));
        setVersions(detailed.map((r) => r.data));
      }
    } catch (loadError) {
      setError(messageFromError(loadError, "Could not load the application model."));
    } finally {
      setLoading(false);
    }
  }, [projectId, sessionPickedByUser]);

  useEffect(() => {
    if (modelId) {
      loadModel(modelId, selectedApplicationId);
      return;
    }
    if (!selectedApplicationId) return;
    applicationModelsApi.list(projectId, selectedApplicationId)
      .then((res) => {
        const current = res.data.find((m) => m.is_current);
        if (current) loadModel(current.id, selectedApplicationId);
        else { setModel(null); setNodes([]); setGaps([]); setActivity([]); setVersions([]); }
      })
      .catch(() => setModel(null));
    // selectedApplicationId is the scope argument; re-running on loadModel identity is intended.
  }, [projectId, selectedApplicationId, modelId, loadModel]);

  const screens = useMemo(() => nodes.filter((n) => n.node_type === "screen"), [nodes]);
  const components = useMemo(() => nodes.filter((n) => n.node_type === "component"), [nodes]);
  const elements = useMemo(() => nodes.filter((n) => n.node_type === "element"), [nodes]);
  const selectedNode = useMemo(() => nodes.find((n) => n.id === selectedNodeId) ?? null, [nodes, selectedNodeId]);
  const openGaps = useMemo(() => gaps.filter((g) => g.status === "open"), [gaps]);
  const criticalOpenGaps = useMemo(() => openGaps.filter((g) => g.severity === "critical"), [openGaps]);
  const gapsByNode = useMemo(() => {
    const map = new Map<number, ApplicationModelGap[]>();
    gaps.forEach((gap) => {
      if (gap.node_id == null) return;
      map.set(gap.node_id, [...(map.get(gap.node_id) ?? []), gap]);
    });
    return map;
  }, [gaps]);

  const isBuilder = model?.built_by != null && currentUserId != null && model.built_by === currentUserId;
  const requiresSeparateApprover = model?.requires_separate_approver ?? true;
  const isMutable = model ? ["draft", "pending_review", "changes_requested"].includes(model.status) : false;
  // The picker targets the next build; the model records what it was built
  // from. When those disagree, say so rather than showing two numbers.
  const rebuildSourceDiffers = Boolean(
    model?.source_session_id && selectedSessionId && selectedSessionId !== model.source_session_id,
  );
  const selectedApplication = applications.find((a) => a.id === selectedApplicationId) ?? null;

  const queueCounts = useMemo(() => ({
    all: nodes.length, screens: screens.length, components: components.length,
    elements: elements.length, gaps: gaps.length,
  }), [nodes, screens, components, elements, gaps]);

  const visibleNodes = useMemo(() => {
    const pool = queueTab === "screens" ? screens
      : queueTab === "components" ? components
      : queueTab === "elements" ? elements
      : nodes.filter((n) => ["screen", "component", "element"].includes(n.node_type));
    const q = search.trim().toLowerCase();
    return pool.filter((node) => {
      if (stateFilter && node.state !== stateFilter) return false;
      if (!q) return true;
      return [node.display_name, node.external_ref, node.description].filter(Boolean).join(" ").toLowerCase().includes(q);
    });
  }, [queueTab, nodes, screens, components, elements, search, stateFilter]);

  const visibleGaps = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return gaps;
    return gaps.filter((gap) => [gap.gap_type, gap.remediation].filter(Boolean).join(" ").toLowerCase().includes(q));
  }, [gaps, search]);

  const stateOptions = useMemo(
    () => Array.from(new Set(nodes.map((n) => n.state).filter(Boolean))).sort(),
    [nodes],
  );

  async function act(action: () => Promise<unknown>, successMessage: string) {
    setBusy(true);
    setError("");
    try {
      await action();
      setNotice(successMessage);
      if (model) await loadModel(model.id, selectedApplicationId);
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
      await loadModel(res.data.id, selectedApplicationId);
    } catch (buildError) {
      setError(messageFromError(buildError, "Could not build the model."));
    } finally {
      setBusy(false);
    }
  }

  /** Unlock a locked version for structural edits. Offered both here (beside
   *  the disabled picker, where the need for it is discovered) and in the
   *  governance action row (where the rest of the lifecycle lives). */
  async function handleCreateDraft() {
    if (!model) return;
    setBusy(true);
    setError("");
    try {
      const res = await applicationModelsApi.newDraft(model.id);
      setNotice("New draft created.");
      await loadModel(res.data.id, selectedApplicationId);
    } catch (draftError) {
      setError(messageFromError(draftError, "Could not create a new draft."));
    } finally {
      setBusy(false);
    }
  }

  const discoveryHref = `/applications?view=discovery&project=${projectId}${selectedApplicationId ? `&application=${selectedApplicationId}` : ""}`;

  /* ── governance: which transition is available, and what blocks it ── */
  const approveBlocker = !canApprove
    ? "You do not have the application_model.approve permission."
    : requiresSeparateApprover && isBuilder
      ? "You built this draft — this deployment requires a different person to approve it."
      : criticalOpenGaps.length > 0
        ? `${criticalOpenGaps.length} critical gap${criticalOpenGaps.length === 1 ? "" : "s"} must be resolved first.`
        : "";

  const guidance = (() => {
    if (!selectedApplicationId) {
      return { tone: "blue" as const, title: "Start by choosing an application", detail: "An Application Model is the reviewed structure of one registered application. Pick one above." };
    }
    if (!model) {
      return {
        tone: eligibleSessions.length === 0 ? "amber" as const : "blue" as const,
        title: eligibleSessions.length === 0 ? "No completed discovery session to build from" : "No model built yet",
        detail: eligibleSessions.length === 0
          ? "A model is built from the evidence of a completed discovery session. Record one and complete it, then return here."
          : "Choose a completed session below and build the first version. Building never overwrites — each build is a new version.",
        action: eligibleSessions.length === 0
          ? <Button size="sm" onClick={() => { window.location.href = discoveryHref; }}><Radar className="h-3.5 w-3.5" /> Open Live Discovery Session</Button>
          : <Button size="sm" onClick={handleBuild} disabled={busy || !selectedSessionId}>{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Build Model</Button>,
      };
    }
    if (screens.length === 0) {
      return { tone: "red" as const, title: "This model contains no screens", detail: "Nothing was discovered to ground tests against. Re-record the source session so each step names the screen it acted on, then rebuild." };
    }
    if (criticalOpenGaps.length > 0) {
      return {
        tone: "red" as const,
        title: `${criticalOpenGaps.length} critical gap${criticalOpenGaps.length === 1 ? "" : "s"} must be resolved`,
        detail: "A model cannot be approved while a critical gap is open. Open the Gaps queue to see each one and what resolves it.",
        action: <Button size="sm" variant="outline" onClick={() => setQueueTab("gaps")}>Show gaps</Button>,
      };
    }
    if (model.status === "draft" || model.status === "changes_requested") {
      return {
        tone: "blue" as const,
        title: model.status === "changes_requested" ? "Changes were requested on this version" : "Draft ready to submit",
        detail: model.status === "changes_requested"
          ? `Reviewer note: ${model.decision_reason || "no reason recorded"}. Address it, then submit again.`
          : "Review the screens, components and locators below, then submit this version for approval.",
        action: <Button size="sm" disabled={busy} onClick={() => act(() => applicationModelsApi.submitReview(model.id), "Submitted for review.")}>Submit for Review</Button>,
      };
    }
    if (model.status === "pending_review") {
      return {
        tone: approveBlocker ? "amber" as const : "blue" as const,
        title: "Waiting for an approval decision",
        detail: approveBlocker || "Approve to lock this version, or request changes with a reason for the builder to act on.",
      };
    }
    if (model.status === "approved") {
      return {
        tone: "blue" as const,
        title: "Approved — publish to make it usable downstream",
        detail: "Publishing marks this the current model. Automation suites gate on a published model.",
        action: <Button size="sm" disabled={busy} onClick={() => act(() => applicationModelsApi.publish(model.id), "Model published.")}>Publish Model</Button>,
      };
    }
    if (model.status === "published") {
      // Publishing is the end of the Applications track and the start of the
      // automation one. Until this link existed, publishing a model told you
      // nothing about where the work continues, and the studio was three
      // sections away in the sidebar.
      return {
        tone: "emerald" as const,
        title: "Published",
        detail: `Version ${model.version} is the current model for this application. Approved test cases mapped to it can now be scripted against this structure.`,
        action: (
          <Button
            size="sm"
            onClick={() => {
              window.location.href = `/automation?project=${projectId}&application=${model.application_id}`;
            }}
          >
            <Sparkles className="h-3.5 w-3.5" /> Continue to AI Automation Studio
          </Button>
        ),
      };
    }
    return { tone: "amber" as const, title: `This version is ${STATUS_TONE[model.status].label.toLowerCase()}`, detail: model.decision_reason || "Create a new draft to continue work on this application." };
  })();

  return (
    <div className="space-y-4 pb-8">
      <Breadcrumb trail={["QAI Command Center","Applications", "Application Model"]} />

      <WorkspaceHeader
        icon={Layers3}
        tone="purple"
        title="Application Model"
        badge="P1-S4 UI-016"
        description="Review, validate and publish the grounded application structure built from discovery evidence."
        actions={
          <>
            <Button variant="outline" size="sm" className="h-9" disabled={!model || loading || busy} onClick={() => model && loadModel(model.id, selectedApplicationId)}>
              <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} /> Refresh
            </Button>
            <Button
              variant="outline" size="sm" className="h-9" disabled={!model}
              title={model ? undefined : "Build a model before exporting."}
              onClick={() => model && window.open(applicationModelsApi.exportUrl(model.id), "_blank")}
            >
              <Download className="h-4 w-4" /> Export Model
            </Button>
          </>
        }
      />

      <Notices error={error} notice={notice} onDismiss={() => { setError(""); setNotice(""); }} />

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-extrabold uppercase tracking-wide text-gray-500">Application</span>
          <select
            value={selectedApplicationId ?? ""}
            onChange={(e) => {
              setSelectedApplicationId(Number(e.target.value) || null);
              setModel(null); setNodes([]); setGaps([]); setSelectedNodeId(null); setSelectedSessionId(null);
            }}
            className="h-9 w-60 rounded-lg border border-gray-200 px-3 text-xs font-bold text-gray-700 outline-none focus:border-app-brand-300 focus:ring-2 focus:ring-app-brand-100"
          >
            <option value="">Select application…</option>
            {applications.map((a) => <option key={a.id ?? a.key} value={a.id ?? ""}>{a.name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-extrabold uppercase tracking-wide text-gray-500">Version</span>
          <select
            value={model?.id ?? ""}
            disabled={versions.length === 0}
            onChange={(e) => loadModel(Number(e.target.value), selectedApplicationId)}
            className="h-9 w-64 rounded-lg border border-gray-200 px-3 text-xs font-bold text-gray-700 outline-none focus:border-app-brand-300 focus:ring-2 focus:ring-app-brand-100 disabled:bg-gray-50 disabled:text-gray-400"
          >
            {versions.length === 0 && <option value="">No versions yet</option>}
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                Version {v.version} · {STATUS_TONE[v.status].label}{v.is_current ? " · current" : ""}
              </option>
            ))}
          </select>
        </label>
        {/* Deliberately NOT called "Source session": that name belongs to the
            session this version was built from, which is a fact about the
            model and is shown beside it. This picker is an input to the next
            build. Both were labelled "Session" before, so a rebuild choice of
            #28 sitting next to a provenance of #24 read as one value
            disagreeing with itself. */}
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-extrabold uppercase tracking-wide text-gray-500">
            {model ? "Rebuild from" : "Build from"}
          </span>
          <select
            value={selectedSessionId ?? ""}
            disabled={eligibleSessions.length === 0 || (Boolean(model) && !isMutable)}
            title={model && !isMutable
              ? `This version is ${STATUS_TONE[model.status].label.toLowerCase()} and cannot be rebuilt. Create a new draft first.`
              : "The completed discovery session the next build will read its evidence from."}
            onChange={(e) => { setSelectedSessionId(Number(e.target.value) || null); setSessionPickedByUser(true); }}
            className="h-9 w-64 rounded-lg border border-gray-200 px-3 text-xs font-bold text-gray-700 outline-none focus:border-app-brand-300 focus:ring-2 focus:ring-app-brand-100 disabled:bg-gray-50 disabled:text-gray-400"
          >
            {eligibleSessions.length === 0 && <option value="">No completed sessions</option>}
            {eligibleSessions.map((s) => (
              <option key={s.id} value={s.id}>
                Session #{s.id} · {s.environment}{s.id === model?.source_session_id ? " · built from" : ""}
              </option>
            ))}
          </select>
          {/* A disabled picker pinned to one session, with the reason living
              further down the card and in a hover title, reads as a hardcoded
              value rather than a locked control — reported as exactly that.
              Say it where the control is. */}
          {model && !isMutable && (
            <span className="flex max-w-64 flex-wrap items-center gap-1.5 text-[11px] font-semibold leading-snug text-gray-500">
              {STATUS_TONE[model.status].label} —
              {["approved", "published", "rejected"].includes(model.status) ? (
                // The unlock lives here as well as in the governance row. Being
                // told to "create a draft" beside a greyed-out control, while
                // the only button that does it sits a screen further down, is
                // how a locked picker reads as a hardcoded value.
                <button
                  type="button" disabled={busy} onClick={handleCreateDraft}
                  className="font-bold text-[#B71920] underline underline-offset-2 disabled:text-gray-400"
                >
                  create a draft to rebuild
                </button>
              ) : (
                <span>this version cannot be rebuilt</span>
              )}
            </span>
          )}
        </label>
        {selectedApplication && (
          <div className="ml-auto flex items-center gap-2 text-[11px] font-semibold text-gray-500">
            <Boxes className="h-3.5 w-3.5 text-gray-400" />
            <span className="font-mono font-bold text-[#B71920]">APP-{selectedApplication.id}</span>
            {model?.source_session_id && (
              <a href={discoveryHref} className="ml-2 inline-flex items-center gap-1 font-bold text-[#B71920]" title="Open the discovery session this version was built from">
                <Radar className="h-3.5 w-3.5" /> Built from session #{model.source_session_id} <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        )}
      </div>

      <GuidanceCard {...guidance} />

      {loading && (
        <div className="rounded-lg border border-gray-200 bg-white p-10 text-center text-xs font-bold text-gray-500">
          <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin text-[#B71920]" /> Loading model…
        </div>
      )}

      {model && !loading && (
        <>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-6">
            <StatCard title="Screens" value={model.kpis.screens} subtitle="Distinct screens discovered" icon={Layers3} tone={screens.length === 0 ? "red" : "blue"} />
            <StatCard title="Components" value={model.kpis.components} subtitle="Grouped within screens" icon={Component} tone="purple" />
            <StatCard title="Elements" value={model.kpis.elements} subtitle="Individually locatable" icon={MousePointerClick} tone="blue" />
            <StatCard title="Open Gaps" value={model.kpis.gaps_open} subtitle={`${model.kpis.gaps_critical_open} critical`} icon={AlertTriangle} tone={model.kpis.gaps_critical_open > 0 ? "red" : model.kpis.gaps_open > 0 ? "amber" : "emerald"} />
            <StatCard title="Journeys" value={model.kpis.journeys} subtitle="Not mapped in this phase" icon={Target} tone="slate" />
            <StatCard title="Version" value={`v${model.version}`} subtitle={`${STATUS_TONE[model.status].label}${model.stale ? " · stale" : ""}`} icon={ShieldCheck} tone={model.status === "published" ? "emerald" : "slate"} />
          </div>

          {/* ── governance ─────────────────────────────────────────── */}
          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[11px] font-extrabold uppercase tracking-wide text-gray-800">Readiness &amp; Governance</p>
                <p className="mt-1 text-[11px] font-semibold text-gray-500">
                  Version {model.version} · built {model.built_at ? new Date(model.built_at).toLocaleString() : "—"}
                  {" · "}{model.built_from_action_count} action{model.built_from_action_count === 1 ? "" : "s"} used
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={STATUS_TONE[model.status].variant}>{STATUS_TONE[model.status].label}</Badge>
                {model.stale && <Badge variant="warning">Stale — source session changed since build</Badge>}
              </div>
            </div>

            <div className="mt-3 grid grid-cols-1 gap-x-8 border-t border-gray-100 pt-3 md:grid-cols-2">
              <ChecklistRow label="Registered application valid" state="pass" detail="Stable application identity resolved from the registry" />
              <ChecklistRow
                label="Source discovery session completed"
                state={model.source_session_id ? "pass" : "blocked"}
                detail={model.source_session_id
                  ? `This version was built from session #${model.source_session_id}${rebuildSourceDiffers ? ` — the picker above targets #${selectedSessionId} for the next rebuild` : ""}`
                  : "No source session recorded"}
              />
              <ChecklistRow
                label="Screen and component structure"
                state={screens.length === 0 || gaps.some((g) => g.status === "open" && g.severity === "critical" && ["MISSING_SCREEN", "MISSING_COMPONENT"].includes(g.gap_type))
                  ? "blocked"
                  : gaps.some((g) => g.status === "open" && ["MISSING_SCREEN", "MISSING_COMPONENT"].includes(g.gap_type)) ? "warning" : "pass"}
                detail={screens.length === 0
                  ? "No screens discovered — there is nothing to ground tests against"
                  : `${screens.length} screen${screens.length === 1 ? "" : "s"} and ${components.length} component${components.length === 1 ? "" : "s"}`}
              />
              <ChecklistRow
                label="Element semantics and locators"
                state={gaps.some((g) => g.status === "open" && g.severity === "critical" && g.gap_type === "MISSING_ELEMENT")
                  ? "blocked"
                  : elements.length === 0 || gaps.some((g) => g.status === "open" && ["AMBIGUOUS_ELEMENT", "UNSTABLE_LOCATOR"].includes(g.gap_type)) ? "warning" : "pass"}
                detail={elements.length === 0 ? "No elements discovered — no locators to validate" : `${elements.length} element${elements.length === 1 ? "" : "s"} with locator evidence`}
              />
              <ChecklistRow
                label="Separation of duties"
                state={requiresSeparateApprover && isBuilder && model.status === "pending_review" ? "warning" : "pass"}
                detail={!requiresSeparateApprover
                  ? "Not required in this deployment — the approver is still recorded"
                  : isBuilder ? "You built this draft, so a different reviewer must approve it" : "Builder and approver differ"}
              />
              <ChecklistRow
                label="No unresolved critical blocker"
                state={criticalOpenGaps.length > 0 ? "blocked" : "pass"}
                detail={`${criticalOpenGaps.length} open critical gap${criticalOpenGaps.length === 1 ? "" : "s"}`}
              />
              <ChecklistRow label="Journey and test-case relationships" state="not_evaluated" detail="Journey linking is not built in this phase" />
              <ChecklistRow label="API and network relationships" state="not_evaluated" detail="Publishing UI-017 relationships into the model is not built yet" />
            </div>

            {rebuildSourceDiffers && (
              <p className="mt-3 flex items-start gap-1.5 rounded-lg border border-app-brand-200 bg-app-brand-75 p-2.5 text-[11px] font-semibold text-app-brand-900">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  Version {model.version} was built from <b>session #{model.source_session_id}</b>. Rebuilding now would
                  use <b>session #{selectedSessionId}</b> instead and create a new version — the current one is not
                  changed until you do.
                </span>
              </p>
            )}

            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-3">
              {isMutable && (
                <Button
                  size="sm" variant="outline" disabled={busy || !selectedSessionId}
                  title={selectedSessionId ? "Rebuild this model from the selected completed session as a new version." : "Select a completed session first."}
                  onClick={handleBuild}
                >
                  <Sparkles className="h-3.5 w-3.5" /> Rebuild from session
                </Button>
              )}
              {(model.status === "draft" || model.status === "changes_requested") && (
                <Button size="sm" disabled={busy} onClick={() => act(() => applicationModelsApi.submitReview(model.id), "Submitted for review.")}>
                  Submit for Review
                </Button>
              )}
              {model.status === "pending_review" && (
                <>
                  <Button
                    size="sm" variant="outline" disabled={busy}
                    onClick={() => setReasonRequest({
                      title: "Request changes",
                      description: `Version ${model.version} goes back to the builder with your note attached.`,
                      label: "What needs to change",
                      placeholder: "e.g. The checkout screen is missing its payment component — re-record with that step included.",
                      confirmLabel: "Request Changes",
                      onConfirm: async (reason) => {
                        await act(() => applicationModelsApi.requestChanges(model.id, reason), "Changes requested.");
                      },
                    })}
                  >
                    Request Changes
                  </Button>
                  <Button
                    size="sm" variant="destructive" disabled={busy}
                    onClick={() => setReasonRequest({
                      title: "Reject this model version",
                      description: "Rejection is terminal for this version. A new draft has to be created to continue.",
                      label: "Reason for rejection",
                      placeholder: "e.g. Recorded against the wrong environment — the SIT run is not representative.",
                      confirmLabel: "Reject Version",
                      destructive: true,
                      onConfirm: async (reason) => {
                        await act(() => applicationModelsApi.reject(model.id, reason), "Model rejected.");
                      },
                    })}
                  >
                    Reject
                  </Button>
                  <Button size="sm" disabled={busy || Boolean(approveBlocker)} title={approveBlocker || undefined} onClick={() => act(() => applicationModelsApi.approve(model.id, null), "Model approved.")}>
                    <ShieldCheck className="h-3.5 w-3.5" /> Approve
                  </Button>
                  {approveBlocker && <span className="text-[11px] font-semibold text-amber-700">{approveBlocker}</span>}
                </>
              )}
              {model.status === "approved" && (
                <Button size="sm" disabled={busy} onClick={() => act(() => applicationModelsApi.publish(model.id), "Model published.")}>
                  Publish Model
                </Button>
              )}
              {["approved", "published", "rejected"].includes(model.status) && (
                <Button size="sm" variant="outline" disabled={busy} onClick={handleCreateDraft}>
                  Create New Draft
                </Button>
              )}
              {!isMutable && model.status !== "pending_review" && (
                <span className="text-[11px] font-semibold text-gray-500">
                  This version is locked. Structural edits require a new draft.
                </span>
              )}
            </div>
          </div>

          <QueueTabs tabs={QUEUE_TABS} active={queueTab} counts={queueCounts} onChange={setQueueTab} />

          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-64 flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={queueTab === "gaps" ? "Search gaps by type or remediation…" : "Search by name or external reference…"}
                className="h-9 w-full rounded-lg border border-gray-200 bg-white pl-9 pr-3 text-xs font-semibold text-gray-700 outline-none focus:border-app-brand-300 focus:ring-2 focus:ring-app-brand-100"
              />
            </div>
            {queueTab !== "gaps" && (
              <FilterSelect
                label="State" value={stateFilter} onChange={setStateFilter}
                options={[{ value: "", label: "State: All" }, ...stateOptions.map((s) => ({ value: s, label: s }))]}
              />
            )}
            {(search || stateFilter) && (
              <button onClick={() => { setSearch(""); setStateFilter(""); }} className="text-xs font-bold text-[#B71920]">Clear Filters</button>
            )}
          </div>

          {queueTab === "gaps" ? (
            <ListShell
              gridTemplate={GAP_GRID}
              minWidth={900}
              columns={["Severity", "Gap", "How to resolve it", "Affected node", "Status"]}
              empty={visibleGaps.length === 0 ? (
                <EmptyState
                  title="No gaps recorded"
                  detail="The build found nothing missing or ambiguous in this model. Gaps appear here when a screen, component or element could not be grounded in the captured evidence."
                />
              ) : undefined}
              footer={<span className="text-xs font-semibold text-gray-500">{openGaps.length} open · {gaps.length - openGaps.length} resolved</span>}
            >
              {visibleGaps.map((gap) => {
                const node = gap.node_id != null ? nodes.find((n) => n.id === gap.node_id) : undefined;
                return (
                  <div key={gap.id} className="grid items-center gap-2 px-3 py-2.5 text-[11px]" style={{ gridTemplateColumns: GAP_GRID }}>
                    <span><Badge variant={gap.severity === "critical" ? "destructive" : "warning"}>{gap.severity}</Badge></span>
                    <span className="font-bold text-gray-800">{gap.gap_type.replace(/_/g, " ")}</span>
                    <span className="font-semibold text-gray-600">{gap.remediation || "No remediation recorded."}</span>
                    <span className="truncate font-semibold text-gray-500">{node?.display_name || "Model-wide"}</span>
                    <span className="flex items-center gap-2">
                      {gap.status === "open" ? (
                        <Button
                          size="sm" variant="outline" className="h-7" disabled={busy || !isMutable}
                          title={isMutable ? "Record that this gap has been dealt with." : "This version is locked — create a new draft to resolve gaps."}
                          onClick={() => setReasonRequest({
                            title: `Resolve ${gap.gap_type.replace(/_/g, " ")}`,
                            description: gap.remediation || "Record how this gap was addressed.",
                            label: "Reviewer notes",
                            placeholder: "e.g. Element is present but rendered late — confirmed manually against SIT.",
                            confirmLabel: "Resolve Gap",
                            onConfirm: async (reason) => {
                              await act(() => applicationModelsApi.resolveGap(model.id, gap.id, reason), "Gap resolved.");
                            },
                          })}
                        >
                          Resolve
                        </Button>
                      ) : <Badge variant="success">Resolved</Badge>}
                    </span>
                  </div>
                );
              })}
            </ListShell>
          ) : (
            <ListShell
              gridTemplate={NODE_GRID}
              minWidth={950}
              columns={["Name", "Type", "External Reference", "Parent", "State", "Gaps"]}
              empty={visibleNodes.length === 0 ? (
                <EmptyState
                  title={nodes.length === 0 ? "This model is empty" : "Nothing matches these filters"}
                  detail={nodes.length === 0
                    ? "The source session did not record any screen it acted on, so there was nothing to build a structure from. Re-record it so each step names a screen, then rebuild."
                    : "Try clearing the search box or switching queue."}
                />
              ) : undefined}
              footer={<span className="text-xs font-semibold text-gray-500">Showing {visibleNodes.length} of {nodes.length} nodes</span>}
            >
              {visibleNodes.map((node) => {
                const Icon = NODE_ICON[node.node_type as keyof typeof NODE_ICON] ?? Component;
                const parent = node.parent_node_id != null ? nodes.find((n) => n.id === node.parent_node_id) : undefined;
                const nodeGaps = gapsByNode.get(node.id) ?? [];
                const openNodeGaps = nodeGaps.filter((g) => g.status === "open");
                return (
                  <ListRow
                    key={node.id}
                    gridTemplate={NODE_GRID}
                    selected={selectedNodeId === node.id}
                    onClick={() => { setSelectedNodeId(node.id); setDrawerTab("overview"); setRenaming(false); }}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <Icon className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                      <span className="truncate font-bold text-gray-900">{node.display_name}</span>
                    </span>
                    <span className="font-semibold capitalize text-gray-600">{node.node_type}</span>
                    <span className="truncate font-mono font-semibold text-gray-500" title={node.external_ref}>{node.external_ref}</span>
                    <span className="truncate font-semibold text-gray-500">{parent?.display_name || "—"}</span>
                    <span><Badge variant={node.state === "DISCOVERED" ? "info" : "secondary"}>{node.state}</Badge></span>
                    <span>
                      {openNodeGaps.length > 0
                        ? <Badge variant={openNodeGaps.some((g) => g.severity === "critical") ? "destructive" : "warning"}>{openNodeGaps.length}</Badge>
                        : <span className="font-semibold text-gray-300">None</span>}
                    </span>
                  </ListRow>
                );
              })}
            </ListShell>
          )}
        </>
      )}

      {/* ── node drawer ─────────────────────────────────────────────── */}
      <Drawer open={!!selectedNode} onOpenChange={(open) => !open && setSelectedNodeId(null)}>
        <DrawerContent size="xl">
          {selectedNode && model && (
            <div className="flex h-full flex-col">
              <div className="border-b border-gray-100 p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="info" className="capitalize">{selectedNode.node_type}</Badge>
                    <Badge variant={selectedNode.state === "DISCOVERED" ? "info" : "secondary"}>{selectedNode.state}</Badge>
                    {(gapsByNode.get(selectedNode.id) ?? []).some((g) => g.status === "open") && (
                      <Badge variant="warning">Has open gaps</Badge>
                    )}
                  </div>
                  <button onClick={() => setSelectedNodeId(null)} aria-label="Close" className="rounded-md p-1 text-gray-500 hover:bg-gray-50">
                    <X className="h-4 w-4" />
                  </button>
                </div>
                {renaming ? (
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <input
                      autoFocus
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      className="h-9 min-w-[16rem] flex-1 rounded-lg border border-gray-200 px-3 text-sm font-bold outline-none focus:ring-2 focus:ring-app-brand-100"
                    />
                    <Button
                      size="sm"
                      disabled={busy || !renameValue.trim() || renameValue.trim() === selectedNode.display_name}
                      title={!renameValue.trim() ? "A semantic name cannot be empty." : undefined}
                      onClick={async () => {
                        await act(() => applicationModelsApi.renameNode(model.id, selectedNode.id, renameValue.trim()), "Semantic name updated.");
                        setRenaming(false);
                      }}
                    >
                      Save
                    </Button>
                    <Button size="sm" variant="outline" disabled={busy} onClick={() => setRenaming(false)}>Cancel</Button>
                  </div>
                ) : (
                  <h2 className="mt-4 text-base font-extrabold text-gray-950">{selectedNode.display_name}</h2>
                )}
                <p className="mt-2 break-all font-mono text-xs font-semibold text-gray-500">{selectedNode.external_ref}</p>
              </div>

              <DrawerTabBar tabs={DRAWER_TABS} active={drawerTab} onChange={setDrawerTab} />

              <div className="flex-1 space-y-4 overflow-y-auto bg-gray-50/50 p-4">
                {drawerTab === "overview" && (
                  <DrawerCard
                    title="Node details"
                    icon={Component}
                    action={isMutable ? (
                      <Button size="sm" variant="outline" className="h-7" onClick={() => { setRenameValue(selectedNode.display_name); setRenaming(true); }}>
                        Edit semantic name
                      </Button>
                    ) : undefined}
                  >
                    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                      <InfoPair label="Type" value={<span className="capitalize">{selectedNode.node_type}</span>} />
                      <InfoPair label="State" value={selectedNode.state} />
                      <InfoPair label="Model version" value={`v${model.version}`} />
                    </div>
                    <div className="mt-4">
                      <p className="text-[10px] font-extrabold uppercase tracking-wide text-gray-400">External reference</p>
                      <p className="mt-1 break-all font-mono text-xs font-semibold text-gray-700">{selectedNode.external_ref}</p>
                    </div>
                    <div className="mt-4">
                      <p className="text-[10px] font-extrabold uppercase tracking-wide text-gray-400">Description</p>
                      <p className={cn("mt-1 text-xs font-semibold leading-5", selectedNode.description ? "text-gray-700" : "text-gray-400")}>
                        {selectedNode.description || "No description recorded by the build."}
                      </p>
                    </div>
                    {!isMutable && (
                      <p className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-2.5 text-[11px] font-semibold text-gray-500">
                        This model version is {STATUS_TONE[model.status].label.toLowerCase()}, so nodes cannot be edited.
                        Create a new draft from the governance panel to make changes.
                      </p>
                    )}
                  </DrawerCard>
                )}

                {drawerTab === "structure" && (
                  <DrawerCard title="Position in the model" icon={Layers3}>
                    <InfoPair
                      label="Parent"
                      value={nodes.find((n) => n.id === selectedNode.parent_node_id)?.display_name || "None — this is a top-level node"}
                    />
                    <div className="mt-4">
                      <p className="text-[10px] font-extrabold uppercase tracking-wide text-gray-400">
                        Children ({nodes.filter((n) => n.parent_node_id === selectedNode.id).length})
                      </p>
                      <div className="mt-2 space-y-1">
                        {nodes.filter((n) => n.parent_node_id === selectedNode.id).map((child) => (
                          <button
                            key={child.id}
                            onClick={() => { setSelectedNodeId(child.id); setDrawerTab("overview"); }}
                            className="flex w-full items-center justify-between rounded-lg border border-gray-200 bg-white px-3 py-2 text-left text-xs font-bold text-gray-700 hover:border-app-brand-200 hover:bg-app-brand-75/40"
                          >
                            <span className="truncate">{child.display_name}</span>
                            <span className="ml-2 shrink-0 font-semibold capitalize text-gray-400">{child.node_type}</span>
                          </button>
                        ))}
                        {nodes.filter((n) => n.parent_node_id === selectedNode.id).length === 0 && (
                          <p className="text-xs font-semibold text-gray-400">Nothing is nested under this node.</p>
                        )}
                      </div>
                    </div>
                  </DrawerCard>
                )}

                {drawerTab === "locators" && (
                  selectedNode.node_type === "element" ? (
                    <NodeLocatorPanel
                      modelId={model.id}
                      node={selectedNode}
                      isMutable={isMutable}
                      busy={busy}
                      onRequestReason={setReasonRequest}
                      onChanged={() => loadModel(model.id, selectedApplicationId)}
                    />
                  ) : (
                    <DrawerCard title="Locators" icon={Target}>
                      <p className="text-xs font-semibold text-gray-500">
                        Only elements carry locator evidence. This node is a {selectedNode.node_type} — open one of its
                        child elements to review and confirm its locators.
                      </p>
                    </DrawerCard>
                  )
                )}

                {drawerTab === "gaps" && (
                  <DrawerCard title="Gaps on this node" icon={AlertTriangle}>
                    {(gapsByNode.get(selectedNode.id) ?? []).length === 0 ? (
                      <p className="text-xs font-semibold text-gray-500">No gaps were recorded against this node.</p>
                    ) : (
                      <div className="space-y-2">
                        {(gapsByNode.get(selectedNode.id) ?? []).map((gap) => (
                          <div key={gap.id} className="rounded-lg border border-gray-200 p-3">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div className="flex items-center gap-2">
                                <Badge variant={gap.severity === "critical" ? "destructive" : "warning"}>{gap.severity}</Badge>
                                <span className="text-xs font-extrabold text-gray-800">{gap.gap_type.replace(/_/g, " ")}</span>
                              </div>
                              {gap.status === "open" ? (
                                <Button
                                  size="sm" variant="outline" className="h-7" disabled={busy || !isMutable}
                                  title={isMutable ? undefined : "This version is locked — create a new draft to resolve gaps."}
                                  onClick={() => setReasonRequest({
                                    title: `Resolve ${gap.gap_type.replace(/_/g, " ")}`,
                                    description: gap.remediation || "Record how this gap was addressed.",
                                    label: "Reviewer notes",
                                    placeholder: "e.g. Confirmed manually against SIT — the element renders after the spinner clears.",
                                    confirmLabel: "Resolve Gap",
                                    onConfirm: async (reason) => {
                                      await act(() => applicationModelsApi.resolveGap(model.id, gap.id, reason), "Gap resolved.");
                                    },
                                  })}
                                >
                                  Resolve
                                </Button>
                              ) : <Badge variant="success">Resolved</Badge>}
                            </div>
                            {gap.remediation && <p className="mt-2 text-[11px] font-semibold leading-5 text-gray-600">{gap.remediation}</p>}
                            {gap.reviewer_notes && (
                              <p className="mt-2 rounded-lg bg-gray-50 p-2 text-[11px] font-semibold text-gray-500">
                                Reviewer: {gap.reviewer_notes}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </DrawerCard>
                )}

                {drawerTab === "activity" && (
                  <DrawerCard title="Model activity" icon={ShieldCheck}>
                    {activity.length === 0 ? (
                      <p className="text-xs font-semibold text-gray-400">No activity recorded for this model yet.</p>
                    ) : (
                      <div className="space-y-2">
                        {activity
                          .filter((entry) => entry.node_id == null || entry.node_id === selectedNode.id)
                          .map((entry) => (
                            <div key={entry.id} className="rounded-lg border border-gray-200 p-2.5">
                              <p className="text-xs font-bold text-gray-800">{entry.event_type.replace(/_/g, " ")}</p>
                              <p className="mt-0.5 text-[11px] font-semibold text-gray-400">{new Date(entry.at).toLocaleString()}</p>
                              {entry.reason && <p className="mt-1 text-[11px] font-semibold text-gray-600">{entry.reason}</p>}
                            </div>
                          ))}
                      </div>
                    )}
                  </DrawerCard>
                )}
              </div>
            </div>
          )}
        </DrawerContent>
      </Drawer>

      <ReasonDrawer
        open={!!reasonRequest}
        title={reasonRequest?.title ?? ""}
        description={reasonRequest?.description ?? ""}
        label={reasonRequest?.label ?? "Reason"}
        placeholder={reasonRequest?.placeholder ?? ""}
        confirmLabel={reasonRequest?.confirmLabel ?? "Confirm"}
        required={reasonRequest?.required}
        minLength={reasonRequest?.minLength}
        destructive={reasonRequest?.destructive}
        busy={busy}
        onCancel={() => setReasonRequest(null)}
        onConfirm={(reason) => {
          // Close before running so the drawer never sits open over a
          // half-applied action, and so `busy` drives the list, not this.
          const request = reasonRequest;
          setReasonRequest(null);
          void request?.onConfirm(reason);
        }}
      />
    </div>
  );
}

function NodeLocatorPanel({
  modelId, node, isMutable, busy, onRequestReason, onChanged,
}: {
  modelId: number;
  node: ApplicationModelNode;
  isMutable: boolean;
  busy: boolean;
  onRequestReason: (request: ReasonRequest) => void;
  onChanged: () => void;
}) {
  const [history, setHistory] = useState<LocatorEvidenceEntry[]>([]);
  const [working, setWorking] = useState(false);

  const reload = useCallback(() => {
    applicationModelsApi.locatorHistory(modelId, node.id)
      .then((res) => setHistory(res.data))
      .catch(() => setHistory([]));
  }, [modelId, node.id]);

  useEffect(reload, [reload]);

  async function run(fn: () => Promise<unknown>) {
    setWorking(true);
    try {
      await fn();
      reload();
      onChanged();
    } finally {
      setWorking(false);
    }
  }

  const latest = history[0];
  const disabled = busy || working || !isMutable;

  return (
    <>
      <DrawerCard title="Current locator" icon={Target}>
        {latest ? (
          <>
            <p className="break-all rounded-lg border border-gray-200 bg-gray-50 p-3 font-mono text-xs font-bold text-gray-800">
              {latest.locator_value || "No locator value recorded"}
            </p>
            <div className="mt-3 grid grid-cols-3 gap-4">
              <InfoPair label="Strategy" value={latest.locator_type || "—"} />
              <InfoPair label="Confidence" value={latest.confidence != null ? `${latest.confidence}%` : "Not scored"} />
              <InfoPair label="Status" value={<span className="capitalize">{latest.status}</span>} />
            </div>
            {latest.reason && (
              <p className="mt-3 rounded-lg bg-amber-50 p-2.5 text-[11px] font-semibold text-amber-800">{latest.reason}</p>
            )}
          </>
        ) : (
          <p className="text-xs font-semibold text-gray-500">
            No locator evidence was captured for this element. It cannot be targeted by generated automation until
            one is recorded — re-record the source session with this element in a performed step.
          </p>
        )}

        <div className="mt-4 flex flex-wrap gap-2 border-t border-gray-100 pt-3">
          <Button
            size="sm" variant="outline" disabled={disabled || !latest}
            title={!isMutable ? "This model version is locked." : !latest ? "There is no locator to confirm." : "Mark this locator as verified against the real application."}
            onClick={() => run(() => applicationModelsApi.confirmLocator(modelId, node.id))}
          >
            <CheckCircle2 className="h-3.5 w-3.5" /> Confirm
          </Button>
          <Button
            size="sm" variant="outline" disabled={disabled || !latest}
            title={!isMutable ? "This model version is locked." : undefined}
            onClick={() => onRequestReason({
              title: "Mark locator unstable",
              description: `${node.display_name} — this is recorded as a warning gap against the model.`,
              label: "Why is it unstable",
              placeholder: "e.g. The id is regenerated on every deploy — matches nothing after a release.",
              confirmLabel: "Mark Unstable",
              onConfirm: async (reason) => {
                await run(() => applicationModelsApi.markLocatorUnstable(modelId, node.id, reason));
              },
            })}
          >
            Mark Unstable
          </Button>
          <Button
            size="sm" variant="outline" disabled={disabled}
            title={!isMutable ? "This model version is locked." : "Add a second locator to try when the primary one fails."}
            onClick={() => onRequestReason({
              title: "Add fallback locator",
              description: `A fallback is attempted for ${node.display_name} when the primary locator does not match.`,
              label: "Fallback locator",
              placeholder: "e.g. //button[normalize-space()='Continue']",
              confirmLabel: "Add Fallback",
              minLength: 3,
              onConfirm: async (value) => {
                await run(() => applicationModelsApi.addFallbackLocator(modelId, node.id, value));
              },
            })}
          >
            Add Fallback
          </Button>
        </div>
        {!isMutable && (
          <p className="mt-3 text-[11px] font-semibold text-gray-500">
            Locator decisions are only editable while the model version is a draft or in review.
          </p>
        )}
      </DrawerCard>

      <DrawerCard title={`Locator history (${Math.max(history.length - 1, 0)})`} icon={Search}>
        {history.length <= 1 ? (
          <p className="text-xs font-semibold text-gray-400">No earlier locator revisions.</p>
        ) : (
          <div className="space-y-2">
            {history.slice(1).map((entry) => (
              <div key={entry.id} className="rounded-lg border border-gray-200 p-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-[11px] font-bold text-gray-700">{entry.locator_value || "—"}</span>
                  <Badge variant="secondary" className="capitalize">{entry.status}</Badge>
                </div>
                <p className="mt-1 text-[11px] font-semibold text-gray-400">{new Date(entry.created_at).toLocaleString()}</p>
                {entry.reason && <p className="mt-1 text-[11px] font-semibold text-gray-600">{entry.reason}</p>}
              </div>
            ))}
          </div>
        )}
      </DrawerCard>
    </>
  );
}
