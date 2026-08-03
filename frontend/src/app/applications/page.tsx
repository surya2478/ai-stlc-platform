"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle, Boxes, ChevronRight, CircleDot, Download, HeartPulse,
  Layers3, Loader2, Plug, Plus, RefreshCw, Search, ShieldCheck, X,
} from "lucide-react";
import {
  applicationsApi,
  projectsApi,
  usersApi,
  type ProjectApplication,
  type ProjectApplicationsSummary,
  type ProjectExternalDependency,
  type ProjectMembership,
  type ProjectRole,
  type ProjectSettingAuditLogEntry,
  type UserAccount,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ApplicationInspector } from "@/components/applications/ApplicationInspector";
import { ApplicationDrawer } from "@/components/applications/ApplicationDrawer";
import { ApplicationModelView } from "@/components/applications/ApplicationModelView";
import { NetworkExplorerView } from "@/components/applications/NetworkExplorerView";
import { ApplicationsTabs } from "@/components/applications/ApplicationsTabs";
import { DiscoverySessionView } from "@/components/discovery/DiscoverySessionView";
import {
  applicationHasEnvironment,
  applicationHasProductMapping,
  badgeVariant,
  getQueueTab,
  lifecycleBadgeTone,
  messageFromError,
  resolveUserName,
  type QueueTab,
  type Tone,
} from "@/components/applications/shared";

function StatCard({
  title, value, subtitle, icon: Icon, tone,
}: {
  title: string; value: string | number; subtitle: string; icon: typeof Boxes; tone: Tone;
}) {
  const toneMap: Record<Tone, string> = {
    blue: "bg-blue-50 border-blue-100 text-blue-600",
    emerald: "bg-emerald-50 border-emerald-100 text-emerald-600",
    red: "bg-red-50 border-red-100 text-red-600",
    purple: "bg-purple-50 border-purple-100 text-purple-600",
    amber: "bg-amber-50 border-amber-100 text-amber-600",
    slate: "bg-slate-50 border-slate-100 text-slate-600",
  };
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2.5">
        <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg border", toneMap[tone])}>
          <Icon className="h-4 w-4" />
        </div>
        <p className="min-w-0 truncate text-xs font-bold text-slate-700">{title}</p>
      </div>
      <p className="mt-3 text-2xl font-extrabold leading-none text-slate-950">{value}</p>
      <p className="mt-1.5 text-[11px] font-semibold text-slate-500">{subtitle}</p>
    </div>
  );
}

function ReadinessRing({ percent }: { percent: number }) {
  const radius = 36;
  const stroke = 6;
  const r = radius - stroke;
  const circ = r * 2 * Math.PI;
  const offset = circ - (Math.min(Math.max(percent, 0), 100) / 100) * circ;
  const label = percent >= 80 ? "Good" : percent >= 50 ? "Fair" : "Needs Work";
  const color = percent >= 80 ? "#10b981" : percent >= 50 ? "#f59e0b" : "#ef4444";
  return (
    <div className="relative flex h-[76px] w-[76px] items-center justify-center">
      <svg height={radius * 2} width={radius * 2} className="-rotate-90">
        <circle stroke="#f1f5f9" fill="transparent" strokeWidth={stroke} r={r} cx={radius} cy={radius} />
        <circle
          stroke={color} fill="transparent" strokeWidth={stroke}
          strokeDasharray={`${circ} ${circ}`} style={{ strokeDashoffset: offset }}
          strokeLinecap="round" r={r} cx={radius} cy={radius}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-base font-extrabold text-slate-900">{Math.round(percent)}%</span>
        <span className="text-[9px] font-bold uppercase text-slate-400">{label}</span>
      </div>
    </div>
  );
}

function ReadinessItem({ label, value, tone = "emerald" }: { label: string; value: string; tone?: Tone }) {
  const iconTone = tone === "amber" ? "bg-amber-50 text-amber-600 border-amber-100"
    : tone === "slate" ? "bg-slate-50 text-slate-400 border-slate-100"
    : "bg-emerald-50 text-emerald-600 border-emerald-100";
  return (
    <div className="flex items-center gap-2.5">
      <span className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-full border", iconTone)}>
        {tone === "slate" ? <CircleDot className="h-3.5 w-3.5" /> : tone === "amber" ? <AlertTriangle className="h-3.5 w-3.5" /> : <ShieldCheck className="h-3.5 w-3.5" />}
      </span>
      <div className="min-w-0">
        <p className="truncate text-[10px] font-bold text-slate-500">{label}</p>
        <p className="text-xs font-extrabold text-slate-900">{value}</p>
      </div>
    </div>
  );
}

const QUEUE_TABS: { key: QueueTab; label: string }[] = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "draft", label: "Draft" },
  { key: "needs_review", label: "Needs Review" },
  { key: "discovery_ready", label: "Discovery Ready" },
  { key: "health_issues", label: "Health Issues" },
  { key: "deprecated_retired", label: "Deprecated / Retired" },
];

const TABLE_GRID = "80px 110px minmax(160px,1fr) 90px 150px 130px 90px 100px 90px 100px 90px 110px 100px 70px";

function ApplicationsContent() {
  const searchParams = useSearchParams();
  const selectedProject = Number(searchParams.get("project")) || null;

  const [applications, setApplications] = useState<ProjectApplication[]>([]);
  const [dependencies, setDependencies] = useState<ProjectExternalDependency[]>([]);
  const [availableEnvironments, setAvailableEnvironments] = useState<string[]>([]);
  const [summary, setSummary] = useState<ProjectApplicationsSummary | null>(null);
  const [auditLog, setAuditLog] = useState<ProjectSettingAuditLogEntry[]>([]);
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [memberships, setMemberships] = useState<ProjectMembership[]>([]);
  const [roles, setRoles] = useState<ProjectRole[]>([]);
  const [me, setMe] = useState<UserAccount | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [seeding, setSeeding] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  const [queueTab, setQueueTab] = useState<QueueTab>("all");
  const [query, setQuery] = useState("");
  const [lifecycleFilter, setLifecycleFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [domainFilter, setDomainFilter] = useState("all");
  const [ownerFilter, setOwnerFilter] = useState("all");
  const [environmentFilter, setEnvironmentFilter] = useState("all");

  const [selectedApp, setSelectedApp] = useState<ProjectApplication | null>(null);
  const [drawerMode, setDrawerMode] = useState<"add" | "edit" | null>(null);

  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    setError("");
    try {
      const [appsRes, summaryRes, usersRes, membershipsRes, rolesRes, meRes, auditRes] = await Promise.all([
        applicationsApi.getForProject(selectedProject),
        applicationsApi.summary(selectedProject).catch(() => null),
        usersApi.list({ project_id: selectedProject }).catch(() => ({ data: [] as UserAccount[] })),
        projectsApi.memberships(selectedProject).catch(() => ({ data: [] as ProjectMembership[] })),
        projectsApi.roles().catch(() => ({ data: [] as ProjectRole[] })),
        usersApi.me().catch(() => ({ data: null as unknown as UserAccount })),
        applicationsApi.auditLog(selectedProject).catch(() => ({ data: [] as ProjectSettingAuditLogEntry[] })),
      ]);
      setApplications(appsRes.data.applications);
      setDependencies(appsRes.data.external_dependencies);
      setAvailableEnvironments(appsRes.data.available_environments);
      setSummary(summaryRes?.data ?? null);
      setUsers(usersRes.data);
      setMemberships(membershipsRes.data);
      setRoles(rolesRes.data);
      setMe(meRes.data);
      setAuditLog(auditRes.data);
      setSelectedApp((prev) => prev ? appsRes.data.applications.find((a) => a.id === prev.id) || null : null);
      setLastRefreshed(new Date());
    } catch (loadError) {
      setError(messageFromError(loadError, "Could not load the application registry."));
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => { loadData(); }, [loadData]);

  const userNames = useMemo(() => new Map(users.map((u) => [u.id, u.full_name])), [users]);
  const roleByName = useMemo(() => new Map(roles.map((r) => [r.role, r])), [roles]);
  const activeMembershipByUser = useMemo(
    () => new Map(memberships.filter((m) => m.is_active).map((m) => [m.user_id, m])),
    [memberships]
  );
  const myMembership = me ? activeMembershipByUser.get(me.id) : undefined;
  const myRole = myMembership ? roleByName.get(myMembership.role) : me ? roleByName.get(me.role) : undefined;
  const canManage = Boolean(me?.is_superuser || myRole?.permissions.includes("manage_project"));

  const authorizedOwnerIds = useMemo(() => new Set(memberships.filter((m) => m.is_active).map((m) => m.user_id)), [memberships]);

  const dependenciesByApp = useMemo(() => {
    const map = new Map<number, ProjectExternalDependency[]>();
    dependencies.forEach((dep) => {
      if (dep.application_id == null) return;
      const list = map.get(dep.application_id) || [];
      list.push(dep);
      map.set(dep.application_id, list);
    });
    return map;
  }, [dependencies]);

  const readiness = useMemo(() => {
    const n = applications.length;
    const stableKeyCount = applications.filter((a) => a.key).length;
    const ownerCount = applications.filter((a) => a.business_owner_id || a.technical_owner_id).length;
    const envCount = applications.filter(applicationHasEnvironment).length;
    const mappedCount = applications.filter(applicationHasProductMapping).length;
    const lifecycleValidCount = applications.filter((a) => a.lifecycle_status).length;
    const pct = (num: number) => n === 0 ? 0 : Math.round((num / n) * 100);
    const factors = n === 0 ? [] : [pct(ownerCount), pct(envCount), pct(mappedCount)];
    const overall = factors.length ? Math.round(factors.reduce((s, v) => s + v, 0) / factors.length) : 0;
    return {
      n, stableKeyCount, ownerCount, envCount, mappedCount, lifecycleValidCount, envAppCount: envCount, overall,
    };
  }, [applications]);

  const filteredApplications = useMemo(() => {
    const q = query.trim().toLowerCase();
    return applications.filter((app) => {
      const bucket = getQueueTab(app);
      const queueOk =
        queueTab === "all" ||
        (queueTab === "health_issues" ? false : bucket === queueTab);
      if (!queueOk) return false;
      if (lifecycleFilter !== "all" && app.lifecycle_status !== lifecycleFilter) return false;
      if (typeFilter !== "all" && (app.application_type || "") !== typeFilter) return false;
      if (domainFilter !== "all" && (app.domain || "") !== domainFilter) return false;
      if (ownerFilter !== "all" && String(app.business_owner_id ?? app.technical_owner_id ?? "") !== ownerFilter) return false;
      if (environmentFilter !== "all" && !(app.environment_urls || {})[environmentFilter]) return false;
      if (!q) return true;
      const haystack = [
        app.key, app.name, ...(app.aliases || []), resolveUserName(userNames, app.business_owner_id),
        resolveUserName(userNames, app.technical_owner_id), app.product, app.channel,
        ...Object.values(app.environment_urls || {}),
      ].filter(Boolean).join(" ").toLowerCase();
      return haystack.includes(q);
    });
  }, [applications, queueTab, lifecycleFilter, typeFilter, domainFilter, ownerFilter, environmentFilter, query, userNames]);

  const typeOptions = useMemo(() => Array.from(new Set(applications.map((a) => a.application_type).filter(Boolean))) as string[], [applications]);
  const domainOptions = useMemo(() => Array.from(new Set(applications.map((a) => a.domain).filter(Boolean))) as string[], [applications]);
  const ownerOptions = useMemo(() => {
    const ids = new Set(applications.map((a) => a.business_owner_id ?? a.technical_owner_id).filter((id): id is number => id != null));
    return Array.from(ids).map((id) => ({ id, name: resolveUserName(userNames, id) }));
  }, [applications, userNames]);

  const queueCounts = useMemo(() => {
    const counts: Record<QueueTab, number> = { all: applications.length, active: 0, draft: 0, needs_review: 0, discovery_ready: 0, health_issues: 0, deprecated_retired: 0 };
    applications.forEach((app) => {
      const bucket = getQueueTab(app);
      if (bucket !== "other") counts[bucket] += 1;
    });
    return counts;
  }, [applications]);

  async function handleSeedCanonical() {
    if (!selectedProject) return;
    setSeeding(true);
    setError("");
    try {
      const res = await applicationsApi.seedCanonical(selectedProject);
      setNotice(`Registry now has ${res.data.applications.length} applications.`);
      await loadData();
    } catch (seedError) {
      setError(messageFromError(seedError, "Could not seed canonical applications."));
    } finally {
      setSeeding(false);
    }
  }

  function exportRegistry() {
    const header = ["App ID", "Stable Key", "Name", "Type", "Domain", "Product", "Channel", "Lifecycle", "Environments", "Default", "Updated At"];
    const rows = filteredApplications.map((a) => [
      a.id, a.key, a.name, a.application_type || "", a.domain || "", a.product || "", a.channel || "",
      a.lifecycle_status, Object.keys(a.environment_urls || {}).length, a.is_default ? "Yes" : "No", a.updated_at || "",
    ]);
    const csv = [header, ...rows].map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `application_registry_project_${selectedProject}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const view = searchParams.get("view");
  const applicationParam = Number(searchParams.get("application")) || null;

  if (view === "discovery") {
    if (!selectedProject) {
      return <div className="p-8 text-sm font-semibold text-slate-400">Select a project to open Live Discovery Session.</div>;
    }
    return (
      <div className="min-h-full space-y-4 pb-8">
        <ApplicationsTabs active="discovery" projectId={selectedProject} />
        <DiscoverySessionView projectId={selectedProject} />
      </div>
    );
  }

  if (view === "model") {
    if (!selectedProject) {
      return <div className="p-8 text-sm font-semibold text-slate-400">Select a project to open Application Model.</div>;
    }
    const modelParam = Number(searchParams.get("model")) || null;
    return (
      <div className="min-h-full space-y-4 pb-8">
        <ApplicationsTabs active="model" projectId={selectedProject} />
        <ApplicationModelView projectId={selectedProject} applicationId={applicationParam} modelId={modelParam} />
      </div>
    );
  }

  if (view === "api-network") {
    if (!selectedProject) {
      return <div className="p-8 text-sm font-semibold text-slate-400">Select a project to open API &amp; Network Explorer.</div>;
    }
    return (
      <div className="min-h-full space-y-4 pb-8">
        <ApplicationsTabs active="api-network" projectId={selectedProject} />
        <NetworkExplorerView projectId={selectedProject} applicationId={applicationParam} />
      </div>
    );
  }

  return (
    <div className="min-h-full">
      <section className="space-y-4 pb-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
          <span>e&amp; STLC</span>
          <ChevronRight className="h-3 w-3 text-slate-300" />
          <span>Applications</span>
          <ChevronRight className="h-3 w-3 text-slate-300" />
          <span className="text-[#1b59f8]">Application Registry</span>
        </div>

        <ApplicationsTabs active="registry" projectId={selectedProject} />

        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="mt-1 flex h-9 w-9 items-center justify-center rounded-lg border border-purple-100 bg-purple-50 text-purple-600">
              <Boxes className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-extrabold tracking-tight text-slate-950">Application Registry</h1>
                <Badge variant="purple">P1-S4 UI-014</Badge>
              </div>
              <p className="mt-1 text-xs font-semibold text-slate-500">
                Govern applications, environments, ownership and discovery readiness across the enterprise.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {lastRefreshed && (
              <span className="text-[11px] font-semibold text-slate-500">
                Last refreshed: {lastRefreshed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
            <Button variant="outline" size="sm" onClick={loadData} disabled={loading} className="h-9 gap-2 border-slate-200 text-xs font-bold">
              <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
              Refresh
            </Button>
            <Button variant="outline" size="sm" onClick={exportRegistry} disabled={!filteredApplications.length} className="h-9 gap-2 border-slate-200 text-xs font-bold">
              <Download className="h-4 w-4" />
              Export Registry
            </Button>
            <Button
              size="sm"
              disabled={!canManage}
              title={canManage ? undefined : "Requires application-registry management permission."}
              onClick={() => { setSelectedApp(null); setDrawerMode("add"); }}
              className="h-9 gap-2 bg-[#1b59f8] text-xs font-bold text-white hover:bg-blue-700"
            >
              <Plus className="h-4 w-4" />
              Add Application
            </Button>
          </div>
        </div>

        {(error || notice) && (
          <div className={cn(
            "flex items-center gap-2 rounded-lg border px-4 py-3 text-xs font-semibold",
            error ? "border-red-200 bg-red-50 text-red-700" : "border-blue-200 bg-blue-50 text-blue-700",
          )}>
            {error ? <AlertTriangle className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
            <span className="flex-1">{error || notice}</span>
            <button onClick={() => { setError(""); setNotice(""); }} className="text-current/60 hover:text-current">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 xl:grid-cols-6">
          <StatCard title="Total Applications" value={summary?.total_applications ?? applications.length} subtitle="Across all environments" icon={Boxes} tone="blue" />
          <StatCard title="Active" value={summary?.active_applications ?? "—"} subtitle={summary ? `${Math.round((summary.active_applications / Math.max(summary.total_applications, 1)) * 100)}% of total` : "—"} icon={ShieldCheck} tone="emerald" />
          <StatCard title="Discovery Ready" value={summary?.discovery_ready ?? "—"} subtitle="Proxy: active + environment URL" icon={Layers3} tone="purple" />
          <StatCard title="Environment Gaps" value={summary?.environment_gaps ?? "—"} subtitle={summary ? `${Math.round((summary.environment_gaps / Math.max(summary.active_applications, 1)) * 100)}% of active` : "—"} icon={CircleDot} tone="amber" />
          <StatCard title="Health Issues" value="Not tracked" subtitle="No health-check subsystem yet" icon={HeartPulse} tone="slate" />
          <StatCard title="Mapping Conflicts" value={summary?.mapping_conflicts.length ?? "—"} subtitle={summary?.mapping_conflicts.length ? "have overlapping mappings" : "No overlaps found"} icon={Plug} tone="red" />
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between gap-4">
            <p className="text-[11px] font-extrabold uppercase tracking-wide text-slate-800">Registry Readiness Overview</p>
            {!loading && (
              <Button
                size="sm"
                variant="outline"
                disabled={!canManage || seeding}
                title={canManage ? "Adds any of the 8 canonical applications not already registered for this project. Never overwrites existing rows." : "Requires application-registry management permission."}
                onClick={handleSeedCanonical}
                className="h-8 gap-2 border-slate-200 text-[11px] font-bold"
              >
                {seeding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                Seed Canonical Applications
              </Button>
            )}
          </div>
          <div className="mt-3 grid grid-cols-[1fr_auto] items-center gap-6">
            <div className="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-5">
              <ReadinessItem label="Stable Key" value={`${readiness.stableKeyCount} / ${readiness.n}`} />
              <ReadinessItem label="Owner Assigned" value={`${readiness.ownerCount} / ${readiness.n}`} tone={readiness.ownerCount < readiness.n ? "amber" : "emerald"} />
              <ReadinessItem label="Environments Configured" value={`${readiness.envCount} / ${readiness.n}`} tone={readiness.envCount < readiness.n ? "amber" : "emerald"} />
              <ReadinessItem label="URL Validation" value={`${readiness.envAppCount} / ${readiness.envAppCount}`} />
              <ReadinessItem label="Auth Profile" value="Not configured" tone="slate" />
              <ReadinessItem label="Products & Channels" value={`${readiness.mappedCount} / ${readiness.n}`} tone={readiness.mappedCount < readiness.n ? "amber" : "emerald"} />
              <ReadinessItem label="Discovery Capability" value="Not configured" tone="slate" />
              <ReadinessItem label="Health Check" value="Not configured" tone="slate" />
              <ReadinessItem label="Dependencies Reviewed" value="Not configured" tone="slate" />
              <ReadinessItem label="Lifecycle Valid" value={`${readiness.lifecycleValidCount} / ${readiness.n}`} />
            </div>
            <div className="flex flex-col items-center gap-1" title="Average of Owner Assigned, Environments Configured and Products/Channels Mapped. Checks with no persisted data (auth profile, discovery, health, dependency review) are excluded, not counted as failures.">
              <span className="text-[9px] font-bold uppercase text-slate-400">Registry Readiness</span>
              <ReadinessRing percent={readiness.overall} />
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1 rounded-lg bg-slate-50 p-1">
            {QUEUE_TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setQueueTab(tab.key)}
                className={cn(
                  "inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-bold transition",
                  queueTab === tab.key ? "bg-[#07142d] text-white" : "text-slate-600 hover:bg-white",
                )}
              >
                {tab.label}
                <span className={cn("rounded-full px-1.5 py-0.5 text-[10px]", queueTab === tab.key ? "bg-white/15 text-white" : "bg-slate-200 text-slate-500")}>
                  {tab.key === "health_issues" ? 0 : queueCounts[tab.key]}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-64 flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by app ID, name, key, owner, domain..."
              className="h-9 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-xs font-semibold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
            />
          </div>
          <select value={lifecycleFilter} onChange={(e) => setLifecycleFilter(e.target.value)} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600 outline-none">
            <option value="all">Lifecycle: All</option>
            <option value="draft">Draft</option>
            <option value="active">Active</option>
            <option value="deprecated">Deprecated</option>
            <option value="retired">Retired</option>
          </select>
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600 outline-none">
            <option value="all">Type: All</option>
            {typeOptions.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select value={domainFilter} onChange={(e) => setDomainFilter(e.target.value)} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600 outline-none">
            <option value="all">Domain: All</option>
            {domainOptions.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
          <select value={ownerFilter} onChange={(e) => setOwnerFilter(e.target.value)} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600 outline-none">
            <option value="all">Owner: All</option>
            {ownerOptions.map((o) => <option key={o.id} value={String(o.id)}>{o.name}</option>)}
          </select>
          <select value={environmentFilter} onChange={(e) => setEnvironmentFilter(e.target.value)} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600 outline-none">
            <option value="all">Environment: All</option>
            {availableEnvironments.map((env) => <option key={env} value={env}>{env}</option>)}
          </select>
          {(lifecycleFilter !== "all" || typeFilter !== "all" || domainFilter !== "all" || ownerFilter !== "all" || environmentFilter !== "all" || query) && (
            <button
              onClick={() => { setLifecycleFilter("all"); setTypeFilter("all"); setDomainFilter("all"); setOwnerFilter("all"); setEnvironmentFilter("all"); setQuery(""); }}
              className="text-xs font-bold text-[#1b59f8]"
            >
              Clear Filters
            </button>
          )}
        </div>

        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="grid min-w-[1400px] border-b border-slate-200 bg-slate-50/70 px-3 py-2.5 text-[9px] font-extrabold uppercase tracking-wide text-slate-500" style={{ gridTemplateColumns: TABLE_GRID }}>
            <span>App ID</span><span>Stable Key</span><span>Name</span><span>Type</span><span>Domain / Product</span>
            <span>Channels</span><span>Owner</span><span>Environments</span><span>Default</span><span>Discovery</span>
            <span>Health</span><span>Mapping Usage</span><span>Lifecycle</span><span>Updated</span>
          </div>
          {loading ? (
            <div className="flex items-center justify-center py-16 text-xs font-bold text-slate-500">
              <Loader2 className="mr-2 h-4 w-4 animate-spin text-[#1b59f8]" />
              Loading application registry...
            </div>
          ) : filteredApplications.length === 0 ? (
            <div className="py-16 text-center text-xs font-semibold text-slate-400">
              {applications.length === 0
                ? canManage
                  ? "No applications registered yet. Seed the canonical applications above or use Add Application."
                  : "No applications registered yet."
                : "No applications match the selected filters."}
            </div>
          ) : (
            <div className="min-w-[1400px] divide-y divide-slate-100">
              {filteredApplications.map((app) => {
                const envCount = Object.keys(app.environment_urls || {}).length;
                const discoveryReady = app.is_active && envCount > 0;
                const usage = summary?.mapping_usage[app.id ?? -1] ?? 0;
                const selected = selectedApp?.id === app.id;
                return (
                  <button
                    key={app.id}
                    onClick={() => setSelectedApp(app)}
                    className={cn("grid w-full items-center px-3 py-2.5 text-left text-[10px] transition hover:bg-slate-50", selected && "border-l-2 border-[#1b59f8] bg-blue-50/30")}
                    style={{ gridTemplateColumns: TABLE_GRID }}
                  >
                    <span className="font-mono font-extrabold text-[#1b59f8]">APP-{app.id}</span>
                    <span className="truncate font-bold text-slate-700">{app.key}</span>
                    <span className="truncate font-bold text-slate-900">{app.name}</span>
                    <span className="truncate text-slate-600">{app.application_type || "—"}</span>
                    <span className="truncate text-slate-600">{[app.domain, app.product].filter(Boolean).join(" / ") || "—"}</span>
                    <span className="truncate text-slate-600">{app.channel || "—"}</span>
                    <span className="truncate text-slate-600">{resolveUserName(userNames, app.business_owner_id ?? app.technical_owner_id)}</span>
                    <span className="text-slate-600">{envCount}</span>
                    <span>{app.is_default ? <Badge variant="info">Default</Badge> : "—"}</span>
                    <span><Badge variant={discoveryReady ? "success" : "secondary"}>{discoveryReady ? "Ready" : "Gap"}</Badge></span>
                    <span className="text-slate-400">Not tracked</span>
                    <span className="text-slate-600">{usage} TC</span>
                    <span><Badge variant={badgeVariant(lifecycleBadgeTone(app.lifecycle_status))}>{app.lifecycle_status}</Badge></span>
                    <span className="truncate text-slate-500">{app.updated_at ? new Date(app.updated_at).toLocaleDateString() : "—"}</span>
                  </button>
                );
              })}
            </div>
          )}
          <div className="flex items-center justify-between border-t border-slate-100 px-3 py-2.5">
            <span className="text-xs font-semibold text-slate-500">Showing {filteredApplications.length} of {applications.length} applications</span>
          </div>
        </div>
      </section>

      <ApplicationInspector
        app={selectedApp}
        onClose={() => setSelectedApp(null)}
        dependencies={selectedApp?.id ? dependenciesByApp.get(selectedApp.id) || [] : []}
        userNames={userNames}
        canManage={canManage}
        summary={summary}
        auditLog={auditLog}
        onEdit={() => setDrawerMode("edit")}
      />

      {drawerMode && (
        <ApplicationDrawer
          mode={drawerMode}
          application={drawerMode === "edit" ? selectedApp : null}
          projectId={selectedProject}
          existingApplications={applications}
          availableEnvironments={availableEnvironments}
          users={users}
          authorizedOwnerIds={authorizedOwnerIds}
          userNames={userNames}
          onClose={() => setDrawerMode(null)}
          onSaved={async (savedId) => {
            setDrawerMode(null);
            await loadData();
            if (savedId) {
              setNotice("Application saved.");
            }
          }}
        />
      )}
    </div>
  );
}

export default function ApplicationsPage() {
  return (
    <Suspense fallback={<div className="flex h-full items-center justify-center text-xs font-semibold text-slate-500"><Loader2 className="mr-2 h-4 w-4 animate-spin" />Loading Application Registry...</div>}>
      <ApplicationsContent />
    </Suspense>
  );
}
