"use client";

/**
 * UI-017 API & Network Explorer.
 *
 * Rebuilt on the Test Case module's list-and-drawer pattern. The previous
 * layout put a 220px filter rail, a table and an inspector side by side at
 * 9-10px type, so the URL column truncated at ~220px and every detail lived
 * in a panel reached through a `<select>`. Reasons for governed actions were
 * collected with `window.prompt()`.
 *
 * Now: pick an application and a session at the top, see what the session
 * captured, filter the requests, then click one to open a full-height drawer
 * with its evidence and correlation on labelled tabs.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Boxes, CheckCircle2, Download, ExternalLink, Globe, Link2,
  Loader2, Network, Radar, RefreshCw, Search, ShieldCheck, Sparkles, X,
} from "lucide-react";
import {
  applicationsApi, discoveryApi, networkExplorerApi,
  type DiscoveryAction, type DiscoverySession, type NetworkEvent, type NetworkEventActivityEntry,
  type NetworkEventKpis, type ProjectApplication,
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

type Props = { projectId: number; applicationId: number | null };

type DrawerTab = "overview" | "correlation" | "evidence" | "headers" | "timing" | "validation";
type QueueKey = "all" | "unreviewed" | "reviewed" | "ignored" | "external" | "unmapped";

const DRAWER_TABS: DrawerTabSpec<DrawerTab>[] = [
  { key: "overview", label: "Overview" },
  { key: "correlation", label: "Correlation" },
  { key: "evidence", label: "Evidence" },
  { key: "headers", label: "Headers", available: false, reason: "Not captured by this discovery pipeline — method, URL and status only" },
  { key: "timing", label: "Timing", available: false, reason: "No timing data is captured by this pipeline" },
  { key: "validation", label: "Validation", available: false, reason: "No API/DB validator is configured for this project" },
];

const QUEUE_TABS: { key: QueueKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "unreviewed", label: "Unreviewed" },
  { key: "reviewed", label: "Reviewed" },
  { key: "ignored", label: "Ignored" },
  { key: "external", label: "External" },
  { key: "unmapped", label: "Unmapped" },
];

const GRID = "70px 90px minmax(240px,1fr) 90px 170px 120px 110px";

function statusTone(status: number | null): "success" | "warning" | "destructive" | "secondary" {
  if (status == null) return "secondary";
  if (status >= 500) return "destructive";
  if (status >= 400) return "warning";
  if (status >= 200 && status < 400) return "success";
  return "secondary";
}

function reviewBadge(state: NetworkEvent["review_state"]) {
  if (state === "reviewed") return <Badge variant="success">Reviewed</Badge>;
  if (state === "ignored") return <Badge variant="secondary">Ignored</Badge>;
  return <Badge variant="warning">Unreviewed</Badge>;
}

export function NetworkExplorerView({ projectId, applicationId }: Props) {
  const [applications, setApplications] = useState<ProjectApplication[]>([]);
  const [selectedApplicationId, setSelectedApplicationId] = useState<number | null>(applicationId);
  const [sessions, setSessions] = useState<DiscoverySession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [actions, setActions] = useState<DiscoveryAction[]>([]);
  const [events, setEvents] = useState<NetworkEvent[]>([]);
  const [kpis, setKpis] = useState<NetworkEventKpis | null>(null);
  const [activity, setActivity] = useState<NetworkEventActivityEntry[]>([]);

  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("overview");
  const [evidenceText, setEvidenceText] = useState("");

  const [queueTab, setQueueTab] = useState<QueueKey>("all");
  const [methodFilter, setMethodFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");

  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reasonRequest, setReasonRequest] = useState<ReasonRequest | null>(null);

  useEffect(() => {
    applicationsApi.getForProject(projectId)
      .then((res) => setApplications(res.data.applications))
      .catch(() => setApplications([]));
  }, [projectId]);

  useEffect(() => {
    if (!selectedApplicationId) return;
    discoveryApi.listSessions(projectId, { application_id: selectedApplicationId })
      .then((res) => {
        setSessions(res.data);
        // Land on the session most likely to have captures rather than making
        // the user guess: the newest one that actually reached a terminal state.
        setSelectedSessionId((current) => {
          if (current && res.data.some((s) => s.id === current)) return current;
          const finished = res.data.filter((s) => ["COMPLETED", "STOPPED"].includes(s.status));
          return (finished[0] ?? res.data[0])?.id ?? null;
        });
      })
      .catch(() => setSessions([]));
  }, [projectId, selectedApplicationId]);

  const loadEvents = useCallback(async (sessionId: number) => {
    setLoading(true);
    setError("");
    try {
      const [kpisRes, eventsRes, activityRes, actionsRes] = await Promise.all([
        networkExplorerApi.kpis(sessionId),
        networkExplorerApi.events(sessionId, {}),
        networkExplorerApi.activity(sessionId),
        discoveryApi.listActions(sessionId),
      ]);
      setKpis(kpisRes.data);
      setEvents(eventsRes.data);
      setActivity(activityRes.data);
      setActions(actionsRes.data);
    } catch (loadError) {
      setError(messageFromError(loadError, "Could not load network events."));
    } finally {
      setLoading(false);
    }
  }, []);

  // Filtering is done in the browser over the session's full event list, so
  // changing a filter no longer costs four network round trips per keystroke.
  useEffect(() => {
    if (selectedSessionId) loadEvents(selectedSessionId);
  }, [selectedSessionId, loadEvents]);

  const actionById = useMemo(() => new Map(actions.map((a) => [a.id, a])), [actions]);
  const selectedEvent = useMemo(() => events.find((e) => e.id === selectedEventId) ?? null, [events, selectedEventId]);
  const selectedAction = selectedEvent?.action_id != null ? actionById.get(selectedEvent.action_id) : undefined;
  const selectedApplication = applications.find((a) => a.id === selectedApplicationId) ?? null;
  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;

  useEffect(() => {
    setEvidenceText("");
    if (!selectedSessionId || !selectedEvent || drawerTab !== "evidence") return;
    discoveryApi.getCaptureContent(selectedSessionId, selectedEvent.capture_id)
      .then((res) => setEvidenceText(String(res.data)))
      .catch(() => setEvidenceText("Capture content is no longer available on disk."));
  }, [selectedSessionId, selectedEvent, drawerTab]);

  const queueCounts = useMemo(() => ({
    all: events.length,
    unreviewed: events.filter((e) => e.review_state === "unreviewed").length,
    reviewed: events.filter((e) => e.review_state === "reviewed").length,
    ignored: events.filter((e) => e.review_state === "ignored").length,
    external: events.filter((e) => e.is_external === true).length,
    unmapped: events.filter((e) => e.action_id == null).length,
  }), [events]);

  const filteredEvents = useMemo(() => {
    const q = search.trim().toLowerCase();
    return events.filter((event) => {
      if (queueTab === "unreviewed" && event.review_state !== "unreviewed") return false;
      if (queueTab === "reviewed" && event.review_state !== "reviewed") return false;
      if (queueTab === "ignored" && event.review_state !== "ignored") return false;
      if (queueTab === "external" && event.is_external !== true) return false;
      if (queueTab === "unmapped" && event.action_id != null) return false;
      if (methodFilter && event.method !== methodFilter) return false;
      if (statusFilter) {
        const bucket = event.status_code == null ? "" : `${Math.floor(event.status_code / 100)}xx`;
        if (bucket !== statusFilter) return false;
      }
      if (!q) return true;
      return [event.url, event.host, event.path, event.raw_line, event.method]
        .filter(Boolean).join(" ").toLowerCase().includes(q);
    });
  }, [events, queueTab, methodFilter, statusFilter, search]);

  const methodOptions = useMemo(
    () => Array.from(new Set(events.map((e) => e.method).filter((m): m is string => Boolean(m)))).sort(),
    [events],
  );

  async function act(fn: () => Promise<unknown>, successMessage: string) {
    setBusy(true);
    setError("");
    try {
      await fn();
      setNotice(successMessage);
      if (selectedSessionId) await loadEvents(selectedSessionId);
    } catch (actionError) {
      setError(messageFromError(actionError, "Could not update this request."));
    } finally {
      setBusy(false);
    }
  }

  function askReview(event: NetworkEvent) {
    setReasonRequest({
      title: `Mark ${event.method || "request"} as reviewed`,
      description: `${event.url || event.raw_line}`.slice(0, 200),
      label: "Review note",
      placeholder: "e.g. Confirmed this is the catalogue lookup behind the Services screen.",
      confirmLabel: "Mark Reviewed",
      required: false,
      onConfirm: async (reason) => {
        await act(() => networkExplorerApi.review(event.id, reason || undefined), "Request marked reviewed.");
      },
    });
  }

  function askIgnore(event: NetworkEvent) {
    setReasonRequest({
      title: `Ignore ${event.method || "request"}`,
      description: "Ignored requests stay in the evidence trail but are excluded from mapping readiness.",
      label: "Reason for ignoring",
      placeholder: "e.g. Analytics beacon — not part of the application under test.",
      confirmLabel: "Ignore Request",
      onConfirm: async (reason) => {
        await act(() => networkExplorerApi.ignore(event.id, reason), "Request marked ignored.");
      },
    });
  }

  async function handleParse() {
    if (!selectedSessionId) return;
    setBusy(true);
    setError("");
    try {
      await networkExplorerApi.build({ project_id: projectId, session_id: selectedSessionId });
      setNotice("Network events parsed from this session's captures.");
      await loadEvents(selectedSessionId);
    } catch (parseError) {
      setError(messageFromError(parseError, "Could not parse network events for this session."));
    } finally {
      setBusy(false);
    }
  }

  const hasCaptures = events.length > 0 || (kpis?.requests_captured ?? 0) > 0;
  const discoveryHref = `/applications?view=discovery&project=${projectId}${selectedApplicationId ? `&application=${selectedApplicationId}` : ""}`;

  /* ── guidance: the single next action, stated in words ─────────────── */
  const guidance = (() => {
    if (!selectedApplicationId) {
      return { tone: "blue" as const, title: "Start by choosing an application", detail: "Network activity is captured per application, per discovery session. Pick one above to continue." };
    }
    if (sessions.length === 0) {
      return {
        tone: "amber" as const,
        title: "This application has no discovery sessions yet",
        detail: "API and network evidence only exists inside a recorded discovery session. Record one first, then come back here.",
        action: <Button size="sm" onClick={() => { window.location.href = discoveryHref; }}>Open Live Discovery Session</Button>,
      };
    }
    if (!selectedSessionId) {
      return { tone: "blue" as const, title: "Choose a discovery session", detail: "Pick the session whose traffic you want to inspect." };
    }
    if (!hasCaptures) {
      return {
        tone: "amber" as const,
        title: "No requests parsed from this session yet",
        detail: "Parsing reads the session's network-log captures and turns each line into a reviewable request. It is safe to run more than once.",
        action: <Button size="sm" onClick={handleParse} disabled={busy}>{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Parse Captures</Button>,
      };
    }
    if (queueCounts.unreviewed > 0) {
      return {
        tone: "blue" as const,
        title: `${queueCounts.unreviewed} request${queueCounts.unreviewed === 1 ? "" : "s"} still need review`,
        detail: "Open a request to see what it was doing and which step triggered it, then mark it reviewed or ignore it with a reason.",
        action: <Button size="sm" variant="outline" onClick={() => setQueueTab("unreviewed")}>Show unreviewed</Button>,
      };
    }
    return {
      tone: "emerald" as const,
      title: "Every captured request has been reviewed",
      detail: `${kpis?.mapping_readiness_pct ?? 0}% of requests are linked to a discovery action. Export the evidence for the record.`,
    };
  })();

  return (
    <div className="space-y-4 pb-8">
      <Breadcrumb trail={["e& STLC", "Applications", "API & Network Explorer"]} />

      <WorkspaceHeader
        icon={Network}
        tone="blue"
        title="API & Network Explorer"
        badge="P1-S4 UI-017"
        description="Correlate API and network activity captured during governed discovery sessions to screens and test steps."
        actions={
          <>
            <Button variant="outline" size="sm" className="h-9" disabled={!selectedSessionId || loading || busy} onClick={() => selectedSessionId && loadEvents(selectedSessionId)}>
              <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} /> Refresh
            </Button>
            <Button variant="outline" size="sm" className="h-9" disabled={!selectedSessionId || busy} onClick={handleParse}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Parse Captures
            </Button>
            <Button
              variant="outline" size="sm" className="h-9"
              disabled={!selectedSessionId || !hasCaptures}
              title={hasCaptures ? undefined : "Nothing to export until this session's captures are parsed."}
              onClick={() => selectedSessionId && window.open(networkExplorerApi.exportUrl(selectedSessionId), "_blank")}
            >
              <Download className="h-4 w-4" /> Export Evidence
            </Button>
          </>
        }
      />

      <Notices error={error} notice={notice} onDismiss={() => { setError(""); setNotice(""); }} />

      {/* Context bar — the two choices everything below depends on. */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-extrabold uppercase tracking-wide text-slate-500">Application</span>
          <select
            value={selectedApplicationId ?? ""}
            onChange={(e) => {
              setSelectedApplicationId(Number(e.target.value) || null);
              setSelectedSessionId(null); setEvents([]); setKpis(null); setSelectedEventId(null);
            }}
            className="h-9 w-60 rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
          >
            <option value="">Select application…</option>
            {applications.map((a) => <option key={a.id ?? a.key} value={a.id ?? ""}>{a.name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-extrabold uppercase tracking-wide text-slate-500">Discovery session</span>
          <select
            value={selectedSessionId ?? ""}
            disabled={!selectedApplicationId || sessions.length === 0}
            onChange={(e) => { setSelectedSessionId(Number(e.target.value) || null); setSelectedEventId(null); }}
            className="h-9 w-72 rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100 disabled:bg-slate-50 disabled:text-slate-400"
          >
            <option value="">{sessions.length === 0 ? "No sessions recorded" : "Select a session…"}</option>
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>Session #{s.id} · {s.environment} · {s.status}</option>
            ))}
          </select>
        </label>
        {selectedApplication && (
          <div className="ml-auto flex items-center gap-2 text-[11px] font-semibold text-slate-500">
            <Boxes className="h-3.5 w-3.5 text-slate-400" />
            <span className="font-mono font-bold text-[#1b59f8]">APP-{selectedApplication.id}</span>
            <span>{selectedApplication.key}</span>
            {selectedSession && (
              <a href={discoveryHref} className="ml-2 inline-flex items-center gap-1 font-bold text-[#1b59f8]">
                <Radar className="h-3.5 w-3.5" /> Open session <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        )}
      </div>

      <GuidanceCard {...guidance} />

      {selectedSessionId && kpis && (
        <>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-6">
            <StatCard title="Requests Captured" value={kpis.requests_captured} subtitle={`${kpis.requests_unparsed} could not be parsed`} icon={Network} tone="blue" />
            <StatCard title="APIs Identified" value={kpis.apis_identified} subtitle="Distinct method + path" icon={Link2} tone="purple" />
            <StatCard title="External Systems" value={kpis.external_systems} subtitle="Hosts outside the app under test" icon={Globe} tone="amber" />
            <StatCard title="Mapping Readiness" value={`${kpis.mapping_readiness_pct}%`} subtitle="Linked to a discovery action" icon={ShieldCheck} tone="emerald" />
            <StatCard title="Awaiting Review" value={queueCounts.unreviewed} subtitle={`${queueCounts.reviewed} reviewed, ${kpis.ignored} ignored`} icon={AlertTriangle} tone={queueCounts.unreviewed > 0 ? "amber" : "emerald"} />
            <StatCard title="Validation" value="Not configured" subtitle="No API/DB validator for this project" icon={CheckCircle2} tone="slate" />
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="mb-2 text-[11px] font-extrabold uppercase tracking-wide text-slate-800">Governance &amp; Evidence Integrity</p>
            <div className="grid grid-cols-1 gap-x-8 md:grid-cols-2">
              <ChecklistRow label="Discovery session authorized" state="pass" detail={`Session #${selectedSessionId} in ${selectedSession?.environment ?? "—"}`} />
              <ChecklistRow
                label="Network capture available"
                state={hasCaptures ? "pass" : "blocked"}
                detail={hasCaptures ? `${kpis.requests_captured} request(s) parsed from this session` : "No network-log captures found — enable network capture on the session and re-record"}
              />
              <ChecklistRow label="Sanitization completed" state="pass" detail="Captured text is masked before it is written to disk" />
              <ChecklistRow label="Secrets and prohibited headers removed" state="pass" detail="Headers, bodies and cookies are never captured by this pipeline" />
              <ChecklistRow
                label="Request-to-action correlation"
                state={kpis.mapping_readiness_pct >= 80 ? "pass" : kpis.mapping_readiness_pct > 0 ? "warning" : "blocked"}
                detail={`${kpis.mapping_readiness_pct}% of requests are linked to a discovery action`}
              />
              <ChecklistRow label="API validator configured" state="not_evaluated" detail="No API/DB validator connection exists for this project" />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <QueueTabs tabs={QUEUE_TABS} active={queueTab} counts={queueCounts} onChange={setQueueTab} />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-64 flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by URL, host or path…"
                className="h-9 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-xs font-semibold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
              />
            </div>
            <FilterSelect
              label="Method" value={methodFilter} onChange={setMethodFilter}
              options={[{ value: "", label: "Method: All" }, ...methodOptions.map((m) => ({ value: m, label: m }))]}
            />
            <FilterSelect
              label="Status" value={statusFilter} onChange={setStatusFilter}
              options={[
                { value: "", label: "Status: All" }, { value: "2xx", label: "2xx Success" },
                { value: "3xx", label: "3xx Redirect" }, { value: "4xx", label: "4xx Client error" },
                { value: "5xx", label: "5xx Server error" },
              ]}
            />
            {(search || methodFilter || statusFilter || queueTab !== "all") && (
              <button
                onClick={() => { setSearch(""); setMethodFilter(""); setStatusFilter(""); setQueueTab("all"); }}
                className="text-xs font-bold text-[#1b59f8]"
              >
                Clear Filters
              </button>
            )}
          </div>

          <ListShell
            gridTemplate={GRID}
            minWidth={1000}
            columns={["Seq", "Method", "URL", "Status", "Screen / Step", "Review", "Host"]}
            loading={loading}
            empty={filteredEvents.length === 0 ? (
              <EmptyState
                title={events.length === 0 ? "No requests parsed yet" : "No requests match these filters"}
                detail={events.length === 0
                  ? "Parse Captures reads this session's network logs and turns each recorded line into a request you can review."
                  : "Try clearing the search box or switching back to the All queue."}
                action={events.length === 0
                  ? <Button size="sm" onClick={handleParse} disabled={busy}><Sparkles className="h-3.5 w-3.5" /> Parse Captures</Button>
                  : <Button size="sm" variant="outline" onClick={() => { setSearch(""); setMethodFilter(""); setStatusFilter(""); setQueueTab("all"); }}>Clear Filters</Button>}
              />
            ) : undefined}
            footer={<span className="text-xs font-semibold text-slate-500">Showing {filteredEvents.length} of {events.length} requests</span>}
          >
            {filteredEvents.map((event) => {
              const action = event.action_id != null ? actionById.get(event.action_id) : undefined;
              return (
                <ListRow
                  key={event.id}
                  gridTemplate={GRID}
                  selected={selectedEventId === event.id}
                  onClick={() => { setSelectedEventId(event.id); setDrawerTab("overview"); }}
                >
                  <span className="font-mono font-bold text-slate-400">#{event.sequence}</span>
                  <span className="font-mono font-extrabold text-slate-800">
                    {event.method || <span className="font-sans font-semibold text-slate-300">unparsed</span>}
                  </span>
                  <span className="truncate font-semibold text-slate-600" title={event.url || event.raw_line}>
                    {event.path || event.url || event.raw_line}
                  </span>
                  <span><Badge variant={statusTone(event.status_code)}>{event.status_code ?? "—"}</Badge></span>
                  <span className="truncate font-semibold text-slate-600">
                    {action?.target_screen_ref || <span className="font-normal text-slate-300">Unmapped</span>}
                  </span>
                  <span>{reviewBadge(event.review_state)}</span>
                  <span className="truncate font-semibold text-slate-500">
                    {event.host || "—"}{event.is_external ? " ↗" : ""}
                  </span>
                </ListRow>
              );
            })}
          </ListShell>

          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="mb-2 text-[11px] font-extrabold uppercase tracking-wide text-slate-800">Session Activity</p>
            {activity.length === 0 ? (
              <p className="text-xs font-semibold text-slate-400">No review activity recorded for this session yet.</p>
            ) : (
              <div className="space-y-2">
                {activity.map((entry) => (
                  <div key={entry.id} className="flex flex-wrap items-baseline gap-2 text-xs">
                    <span className="font-bold text-slate-700">{entry.event_type.replace(/_/g, " ")}</span>
                    <span className="font-semibold text-slate-400">{new Date(entry.created_at).toLocaleString()}</span>
                    {entry.reason && <span className="font-semibold text-slate-500">— {entry.reason}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {/* ── request drawer ──────────────────────────────────────────── */}
      <Drawer open={!!selectedEvent} onOpenChange={(open) => !open && setSelectedEventId(null)}>
        <DrawerContent size="xl">
          {selectedEvent && (
            <div className="flex h-full flex-col">
              <div className="border-b border-slate-100 p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-lg font-extrabold text-slate-950">
                      {selectedEvent.method || "UNPARSED"}
                    </span>
                    <Badge variant={statusTone(selectedEvent.status_code)}>
                      {selectedEvent.status_code ?? "no status"} {selectedEvent.status_text || ""}
                    </Badge>
                    {reviewBadge(selectedEvent.review_state)}
                    {selectedEvent.is_external && <Badge variant="warning">External host</Badge>}
                  </div>
                  <button onClick={() => setSelectedEventId(null)} aria-label="Close" className="rounded-md p-1 text-slate-500 hover:bg-slate-50">
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <p className="mt-4 break-all text-sm font-bold text-slate-900">
                  {selectedEvent.url || selectedEvent.raw_line}
                </p>
                <p className="mt-2 text-xs font-semibold text-slate-500">
                  Request #{selectedEvent.sequence} of session #{selectedEvent.session_id}
                  {selectedAction
                    ? <> · captured during <span className="text-[#1b59f8]">step {selectedAction.sequence} — {selectedAction.target_semantic || selectedAction.action_family}</span></>
                    : <> · <span className="text-amber-700">not linked to any discovery action</span></>}
                </p>
              </div>

              <DrawerTabBar tabs={DRAWER_TABS} active={drawerTab} onChange={setDrawerTab} />

              <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50/50 p-4">
                {drawerTab === "overview" && (
                  <>
                    <DrawerCard title="Request" icon={Network}>
                      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                        <InfoPair label="Method" value={selectedEvent.method || "Not parsed"} mono />
                        <InfoPair label="Status" value={selectedEvent.status_code != null ? `${selectedEvent.status_code} ${selectedEvent.status_text || ""}`.trim() : "Not parsed"} />
                        <InfoPair label="Host" value={selectedEvent.host || "Not parsed"} mono />
                        <InfoPair label="Path" value={selectedEvent.path || "Not parsed"} mono />
                        <InfoPair label="Scope" value={selectedEvent.is_external === true ? "External system" : selectedEvent.is_external === false ? "Application under test" : "Unknown"} />
                        <InfoPair label="Parse state" value={selectedEvent.parse_state === "parsed" ? "Parsed" : "Raw line only"} />
                      </div>
                      {selectedEvent.parse_state !== "parsed" && (
                        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-[11px] font-semibold text-amber-800">
                          This capture line did not match the expected log format, so only the raw text is available.
                          It still counts toward the captured total but cannot be correlated or classified.
                        </p>
                      )}
                    </DrawerCard>

                    <DrawerCard title="Review" icon={ShieldCheck}>
                      <div className="grid grid-cols-2 gap-4">
                        <InfoPair label="State" value={selectedEvent.review_state} />
                        <InfoPair label="Reviewed at" value={selectedEvent.reviewed_at ? new Date(selectedEvent.reviewed_at).toLocaleString() : "—"} />
                      </div>
                      {selectedEvent.review_reason && (
                        <p className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-[11px] font-semibold text-slate-600">
                          {selectedEvent.review_reason}
                        </p>
                      )}
                      <p className="mt-3 text-[11px] font-semibold text-slate-400">
                        Reviewing records that a human looked at this request. Ignoring removes it from mapping
                        readiness without deleting it from the evidence trail. Both are audited.
                      </p>
                    </DrawerCard>

                    <DrawerCard title="Raw capture line" icon={Search}>
                      <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-3 text-[11px] leading-5 text-slate-600">
                        {selectedEvent.raw_line}
                      </pre>
                    </DrawerCard>
                  </>
                )}

                {drawerTab === "correlation" && (
                  <DrawerCard title="Correlated discovery action" icon={Link2}>
                    {selectedAction ? (
                      <>
                        <div className="grid grid-cols-2 gap-4">
                          <InfoPair label="Step" value={`#${selectedAction.sequence}`} />
                          <InfoPair label="Action" value={selectedAction.action_family} />
                          <InfoPair label="Screen" value={selectedAction.target_screen_ref || "Not recorded"} mono />
                          <InfoPair label="Test step" value={selectedAction.test_step_ref || "Not mapped"} mono />
                        </div>
                        {selectedAction.target_semantic && (
                          <p className="mt-3 text-xs font-semibold leading-5 text-slate-600">{selectedAction.target_semantic}</p>
                        )}
                      </>
                    ) : (
                      <div className="space-y-2">
                        <p className="text-xs font-semibold text-amber-700">This request is not linked to any discovery action.</p>
                        <p className="text-[11px] font-semibold leading-5 text-slate-500">
                          Requests are correlated by the capture they came from. An uncorrelated request usually means
                          the traffic happened between recorded steps — background polling, telemetry, or a redirect
                          chain. It is normal to ignore these with a reason rather than to chase a mapping.
                        </p>
                      </div>
                    )}
                  </DrawerCard>
                )}

                {drawerTab === "evidence" && (
                  <DrawerCard title="Capture content" icon={Download}>
                    <p className="mb-2 text-[11px] font-semibold text-slate-500">
                      The sanitized network-log capture this request was parsed from, as stored on disk.
                    </p>
                    <pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-3 text-[11px] leading-5 text-slate-600">
                      {evidenceText || "Loading…"}
                    </pre>
                  </DrawerCard>
                )}
              </div>

              <div className="flex items-center justify-between gap-2 border-t border-slate-100 bg-slate-50 p-4">
                <p className="text-[11px] font-semibold text-slate-500">
                  {selectedEvent.review_state === "unreviewed"
                    ? "Not yet reviewed — both actions below ask for a note first."
                    : `Already ${selectedEvent.review_state}. Re-reviewing overwrites the previous note.`}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm" variant="outline" disabled={busy || selectedEvent.review_state === "ignored"}
                    title={selectedEvent.review_state === "ignored" ? "This request is already ignored." : undefined}
                    onClick={() => askIgnore(selectedEvent)}
                  >
                    Ignore
                  </Button>
                  <Button size="sm" disabled={busy} onClick={() => askReview(selectedEvent)}>
                    <CheckCircle2 className="h-3.5 w-3.5" /> Mark Reviewed
                  </Button>
                </div>
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
