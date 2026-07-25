"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, CheckCircle2, ChevronRight, Download, FileWarning, Loader2,
  RefreshCw, Sparkles, XCircle,
} from "lucide-react";
import {
  applicationsApi, discoveryApi, networkExplorerApi,
  type DiscoveryAction, type DiscoverySession, type NetworkEvent, type NetworkEventActivityEntry,
  type NetworkEventKpis, type ProjectApplication,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type Props = { projectId: number; applicationId: number | null };

type InspectorTab = "overview" | "correlation" | "evidence" | "headers" | "timing" | "validation";

const INSPECTOR_TABS: { key: InspectorTab; label: string; available: boolean; reason?: string }[] = [
  { key: "overview", label: "Overview", available: true },
  { key: "correlation", label: "Correlation", available: true },
  { key: "evidence", label: "Evidence", available: true },
  { key: "headers", label: "Headers", available: false, reason: "Not captured by this discovery pipeline (method/URL/status only)" },
  { key: "timing", label: "Timing", available: false, reason: "No timing data is captured by this pipeline" },
  { key: "validation", label: "Validation", available: false, reason: "No API/DB validator is configured for this project" },
];

function messageFromError(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  return fallback;
}

function Kpi({ label, value, subtitle, tone }: { label: string; value: string | number; subtitle?: string; tone?: "amber" | "red" | "muted" }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-[9px] font-extrabold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={cn(
        "mt-1 text-xl font-black",
        tone === "red" ? "text-red-600" : tone === "amber" ? "text-amber-600" : tone === "muted" ? "text-slate-300" : "text-slate-900",
      )}>{value}</p>
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

function statusTone(status: number | null): "success" | "warning" | "destructive" | "secondary" {
  if (status == null) return "secondary";
  if (status >= 500) return "destructive";
  if (status >= 400) return "warning";
  if (status >= 200 && status < 400) return "success";
  return "secondary";
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
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("overview");
  const [evidenceText, setEvidenceText] = useState<string>("");

  const [methodFilter, setMethodFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [externalOnly, setExternalOnly] = useState(false);
  const [unmappedOnly, setUnmappedOnly] = useState(false);
  const [search, setSearch] = useState("");

  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    applicationsApi.getForProject(projectId).then((res) => setApplications(res.data.applications)).catch(() => setApplications([]));
  }, [projectId]);

  useEffect(() => {
    if (!selectedApplicationId) return;
    discoveryApi.listSessions(projectId, { application_id: selectedApplicationId })
      .then((res) => setSessions(res.data))
      .catch(() => setSessions([]));
  }, [projectId, selectedApplicationId]);

  async function loadEvents(sessionId: number) {
    setLoading(true);
    setError("");
    try {
      const [kpisRes, eventsRes, activityRes, actionsRes] = await Promise.all([
        networkExplorerApi.kpis(sessionId),
        networkExplorerApi.events(sessionId, {
          method: methodFilter || undefined,
          status_bucket: (statusFilter || undefined) as never,
          external_only: externalOnly || undefined,
          unmapped_only: unmappedOnly || undefined,
          search: search || undefined,
        }),
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
  }

  useEffect(() => {
    if (selectedSessionId) loadEvents(selectedSessionId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSessionId, methodFilter, statusFilter, externalOnly, unmappedOnly, search]);

  const actionById = useMemo(() => new Map(actions.map((a) => [a.id, a])), [actions]);
  const selectedEvent = useMemo(() => events.find((e) => e.id === selectedEventId) || null, [events, selectedEventId]);
  const selectedAction = selectedEvent?.action_id != null ? actionById.get(selectedEvent.action_id) : undefined;

  useEffect(() => {
    setEvidenceText("");
    if (!selectedSessionId || !selectedEvent) return;
    if (inspectorTab !== "evidence") return;
    discoveryApi.getCaptureContent(selectedSessionId, selectedEvent.capture_id)
      .then((res) => setEvidenceText(String(res.data)))
      .catch(() => setEvidenceText("Capture content is no longer available."));
  }, [selectedSessionId, selectedEvent, inspectorTab]);

  async function handleBuild() {
    if (!selectedSessionId) return;
    setBusy(true);
    setError("");
    try {
      await networkExplorerApi.build({ project_id: projectId, session_id: selectedSessionId });
      setNotice("Network events parsed from this session's captures.");
      await loadEvents(selectedSessionId);
    } catch (buildError) {
      setError(messageFromError(buildError, "Could not parse network events for this session."));
    } finally {
      setBusy(false);
    }
  }

  async function handleIgnore(event: NetworkEvent) {
    const reason = window.prompt("Reason this request should be ignored:");
    if (!reason) return;
    setBusy(true);
    try {
      await networkExplorerApi.ignore(event.id, reason);
      setNotice("Request marked ignored.");
      if (selectedSessionId) await loadEvents(selectedSessionId);
    } catch (ignoreError) {
      setError(messageFromError(ignoreError, "Could not update this request."));
    } finally {
      setBusy(false);
    }
  }

  async function handleReview(event: NetworkEvent) {
    const note = window.prompt("Optional review note:") || undefined;
    setBusy(true);
    try {
      await networkExplorerApi.review(event.id, note);
      setNotice("Request marked reviewed.");
      if (selectedSessionId) await loadEvents(selectedSessionId);
    } catch (reviewError) {
      setError(messageFromError(reviewError, "Could not update this request."));
    } finally {
      setBusy(false);
    }
  }

  if (!selectedApplicationId) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-8 text-center">
        <p className="text-sm font-bold text-slate-700">Select an application</p>
        <p className="mt-1 text-xs font-semibold text-slate-500">Choose an application below to explore its captured API and network activity.</p>
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

  const hasNetworkCaptures = events.length > 0 || (kpis?.requests_captured ?? 0) > 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
        <span>e&amp; STLC</span>
        <ChevronRight className="h-3 w-3 text-slate-300" />
        <span>Application Discovery</span>
        <ChevronRight className="h-3 w-3 text-slate-300" />
        <span className="text-slate-800">API &amp; Network Explorer</span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900">API &amp; Network Explorer</h1>
            <Badge variant="info">P1-S4 UI-017</Badge>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Correlate captured API and network activity from governed discovery sessions to screens and test steps.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="h-9 rounded-lg border border-slate-200 px-3 text-xs font-semibold"
            value={selectedApplicationId}
            onChange={(e) => { setSelectedApplicationId(Number(e.target.value) || null); setSelectedSessionId(null); setEvents([]); setKpis(null); }}
          >
            {applications.map((a) => <option key={a.id ?? a.key} value={a.id ?? ""}>{a.name}</option>)}
          </select>
          <select
            className="h-9 rounded-lg border border-slate-200 px-3 text-xs font-semibold"
            value={selectedSessionId ?? ""}
            onChange={(e) => setSelectedSessionId(Number(e.target.value) || null)}
          >
            <option value="">Select a discovery session…</option>
            {sessions.map((s) => <option key={s.id} value={s.id}>Session #{s.id} — {s.environment} ({s.status})</option>)}
          </select>
          <Button variant="outline" size="sm" onClick={() => selectedSessionId && loadEvents(selectedSessionId)} disabled={!selectedSessionId || loading || busy}>
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} /> Refresh
          </Button>
          <Button size="sm" onClick={handleBuild} disabled={!selectedSessionId || busy}>
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Parse Captures
          </Button>
          {selectedSessionId && kpis && (
            <Button variant="outline" size="sm" onClick={() => window.open(networkExplorerApi.exportUrl(selectedSessionId), "_blank")}>
              <Download className="h-3.5 w-3.5" /> Export Evidence
            </Button>
          )}
        </div>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div>}
      {notice && <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-700">{notice}</div>}

      {!selectedSessionId && (
        <Panel title="Select a discovery session">
          <p className="text-xs font-semibold text-slate-500">
            Choose a discovery session above to review the API and network activity it captured, then click Parse Captures.
          </p>
          {sessions.length === 0 && (
            <a href={`/automation?view=discovery&project=${projectId}&application=${selectedApplicationId}`} className="mt-2 inline-block text-[10px] font-bold text-[#1b59f8]">
              No discovery sessions yet — open Live Discovery Session →
            </a>
          )}
        </Panel>
      )}

      {loading && <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-xs font-semibold text-slate-400">Loading…</div>}

      {selectedSessionId && !loading && kpis && (
        <>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-6">
            <Kpi label="Requests Captured" value={kpis.requests_captured} subtitle={`${kpis.requests_unparsed} unparsed`} />
            <Kpi label="APIs Identified" value={kpis.apis_identified} />
            <Kpi label="Validation Passed" value="—" tone="muted" subtitle="No validator configured" />
            <Kpi label="Failures &amp; Warnings" value="—" tone="muted" subtitle="No validator configured" />
            <Kpi label="External Systems" value={kpis.external_systems} />
            <Kpi label="Mapping Readiness" value={`${kpis.mapping_readiness_pct}%`} subtitle={`${kpis.ignored} ignored`} />
          </div>

          <Panel title="Readiness &amp; Governance">
            <div className="grid grid-cols-1 gap-x-6 gap-y-1 md:grid-cols-2">
              <ReadinessRow label="Discovery session authorized" state="pass" detail={`Session #${selectedSessionId}`} />
              <ReadinessRow
                label="Network capture available"
                state={hasNetworkCaptures ? "pass" : "blocked"}
                detail={hasNetworkCaptures ? `${kpis.requests_captured} request(s) parsed` : "No network-log captures found for this session"}
              />
              <ReadinessRow label="Sanitization completed" state="pass" detail="Captured text is masked before being written to disk" />
              <ReadinessRow label="Secrets and prohibited headers removed" state="pass" detail="Headers, bodies and cookies are never captured by this pipeline" />
              <ReadinessRow label="API validator configured" state="not_evaluated" detail="No API/DB validator connection is configured for this project" />
              <ReadinessRow label="External MCPs available" state="not_evaluated" detail="No external-system MCP mapping exists yet" />
              <ReadinessRow
                label="Request-to-action correlation available"
                state={kpis.mapping_readiness_pct > 0 ? "pass" : "warning"}
                detail={`${kpis.mapping_readiness_pct}% of requests linked to a discovery action`}
              />
              <ReadinessRow label="Application Model mapping available" state="not_evaluated" detail="Publishing relationships to the Application Model is not yet built" />
              <ReadinessRow label="Evidence storage accessible" state={hasNetworkCaptures ? "pass" : "not_evaluated"} detail="Reading from the managed discovery workspace" />
              <ReadinessRow label="No unresolved sensitive-data violation" state="pass" detail="Masking is applied before persistence" />
            </div>
          </Panel>

          <div className="grid grid-cols-1 gap-3 xl:grid-cols-[220px_1fr_320px]">
            <Panel title="Filters">
              <div className="space-y-2 text-[10px]">
                <div>
                  <label className="mb-1 block font-extrabold text-slate-600">Method</label>
                  <select className="h-8 w-full rounded-md border border-slate-200 px-2 font-semibold" value={methodFilter} onChange={(e) => setMethodFilter(e.target.value)}>
                    <option value="">All</option>
                    {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block font-extrabold text-slate-600">Status</label>
                  <select className="h-8 w-full rounded-md border border-slate-200 px-2 font-semibold" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                    <option value="">All</option>
                    <option value="2xx">2xx</option>
                    <option value="3xx">3xx</option>
                    <option value="4xx">4xx</option>
                    <option value="5xx">5xx</option>
                  </select>
                </div>
                <input
                  className="h-8 w-full rounded-md border border-slate-200 px-2 font-semibold"
                  placeholder="Search URL…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <label className="flex items-center gap-1.5 font-semibold text-slate-600">
                  <input type="checkbox" checked={externalOnly} onChange={(e) => setExternalOnly(e.target.checked)} /> External systems only
                </label>
                <label className="flex items-center gap-1.5 font-semibold text-slate-600">
                  <input type="checkbox" checked={unmappedOnly} onChange={(e) => setUnmappedOnly(e.target.checked)} /> Unmapped only
                </label>
                <div className="border-t border-slate-100 pt-2 opacity-40">
                  <p className="text-[9px] font-bold" title="No timing data is captured by this pipeline">Timeline / Waterfall</p>
                  <p className="text-[9px] font-bold" title="No validator infrastructure is configured yet">By Validation Result</p>
                  <p className="text-[9px] font-bold" title="Publishing to the Application Model is not yet built">External System &amp; MCP Map</p>
                </div>
              </div>
            </Panel>

            <Panel title={`Requests (${events.length})`}>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[10px]">
                  <thead>
                    <tr className="border-b border-slate-100 text-[9px] font-extrabold uppercase text-slate-400">
                      <th className="py-1.5">Method</th><th>URL</th><th>Status</th><th>Screen / Step</th><th>Review</th><th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((event) => {
                      const action = event.action_id != null ? actionById.get(event.action_id) : undefined;
                      return (
                        <tr
                          key={event.id}
                          onClick={() => { setSelectedEventId(event.id); setInspectorTab("overview"); }}
                          className={cn("cursor-pointer border-b border-slate-50 hover:bg-slate-50", selectedEventId === event.id && "bg-blue-50/40")}
                        >
                          <td className="py-1.5 font-bold text-slate-800">{event.method || <span className="text-slate-300">unparsed</span>}</td>
                          <td className="max-w-[220px] truncate font-semibold text-slate-600" title={event.url || event.raw_line}>{event.url || event.raw_line}</td>
                          <td><Badge variant={statusTone(event.status_code)} className="text-[8px]">{event.status_code ?? "—"}</Badge></td>
                          <td className="font-semibold text-slate-500">{action?.target_screen_ref || <span className="text-slate-300">Unmapped</span>}</td>
                          <td className="font-semibold text-slate-500">{event.review_state}</td>
                          <td onClick={(e) => e.stopPropagation()}>
                            <div className="flex gap-1">
                              <Button size="sm" variant="outline" className="h-6 px-1.5 text-[9px]" disabled={busy} onClick={() => handleReview(event)}>Review</Button>
                              <Button size="sm" variant="outline" className="h-6 px-1.5 text-[9px]" disabled={busy || event.review_state === "ignored"} onClick={() => handleIgnore(event)}>Ignore</Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                    {events.length === 0 && (
                      <tr><td colSpan={6} className="p-6 text-center text-[10px] font-semibold text-slate-400">
                        No requests parsed yet. Click &quot;Parse Captures&quot; to build events from this session&apos;s network-log captures.
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
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
              {!selectedEvent && <p className="text-[10px] font-semibold text-slate-400">Select a request to inspect it.</p>}
              {selectedEvent && inspectorTab === "overview" && (
                <div className="space-y-1 text-[10px]">
                  <p className="font-extrabold text-slate-900">{selectedEvent.method || "Unparsed"} {selectedEvent.path || ""}</p>
                  <p className="font-semibold text-slate-500 break-all">{selectedEvent.url || selectedEvent.raw_line}</p>
                  <p className="font-semibold text-slate-500">Host: {selectedEvent.host || "—"} {selectedEvent.is_external ? "(external)" : selectedEvent.is_external === false ? "(internal)" : ""}</p>
                  <p className="font-semibold text-slate-500">Status: {selectedEvent.status_code ?? "—"} {selectedEvent.status_text || ""}</p>
                  <p className="font-semibold text-slate-500">Parse state: {selectedEvent.parse_state}</p>
                  <p className="font-semibold text-slate-500">Review: {selectedEvent.review_state}{selectedEvent.review_reason ? ` — ${selectedEvent.review_reason}` : ""}</p>
                </div>
              )}
              {selectedEvent && inspectorTab === "correlation" && (
                <div className="space-y-1 text-[10px]">
                  {selectedAction ? (
                    <>
                      <p className="font-bold text-slate-700">Discovery Action #{selectedAction.id}</p>
                      <p className="font-semibold text-slate-500">Screen: {selectedAction.target_screen_ref || "—"}</p>
                      <p className="font-semibold text-slate-500">Test step: {selectedAction.test_step_ref || "—"}</p>
                    </>
                  ) : <p className="font-semibold text-slate-400">This request is not linked to a discovery action.</p>}
                </div>
              )}
              {selectedEvent && inspectorTab === "evidence" && (
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-slate-50 p-2 text-[9px] text-slate-600">
                  {evidenceText || "Loading…"}
                </pre>
              )}
            </Panel>
          </div>

          <Panel title="Activity">
            <div className="space-y-1.5">
              {activity.map((a) => (
                <div key={a.id} className="text-[9px]">
                  <p className="font-bold text-slate-700">{new Date(a.created_at).toLocaleString()} · {a.event_type}</p>
                  {a.reason && <p className="font-semibold text-slate-500">{a.reason}</p>}
                </div>
              ))}
              {activity.length === 0 && <p className="text-[10px] font-semibold text-slate-400">No activity yet.</p>}
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
