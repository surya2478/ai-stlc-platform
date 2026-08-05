"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle, ChevronRight, Clock, Globe, Plug, Radar, ShieldCheck, X,
} from "lucide-react";
import type { ProjectApplication, ProjectApplicationsSummary, ProjectExternalDependency, ProjectSettingAuditLogEntry } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerBody } from "@/components/ui/drawer";
import { cn } from "@/lib/utils";
import { applicationGaps, badgeVariant, lifecycleBadgeTone, resolveUserName } from "./shared";

type InspectorTab = "overview" | "environments" | "relationships" | "dependencies" | "discovery" | "history" | "activity";

const TABS: { key: InspectorTab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "environments", label: "Environments" },
  { key: "relationships", label: "Relationships" },
  { key: "dependencies", label: "Dependencies" },
  { key: "discovery", label: "Discovery & Health" },
  { key: "history", label: "History" },
  { key: "activity", label: "Activity" },
];

function InspectorCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-4 rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-3 text-xs font-extrabold text-gray-900">{title}</h3>
      {children}
    </section>
  );
}

function InfoPair({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <p className="text-[9px] font-bold uppercase text-gray-400">{label}</p>
      <p className="mt-0.5 text-xs font-bold text-gray-800">{value}</p>
    </div>
  );
}

function NotConfigured({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-dashed border-gray-200 bg-gray-50/60 px-3 py-2 text-[11px] font-semibold text-gray-400">
      <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
      {label} — not configured. No backing subsystem persists this data yet.
    </div>
  );
}

type FieldChange = { field: string; oldValue: unknown; newValue: unknown };
type AppEvent = { entry: ProjectSettingAuditLogEntry; changes: FieldChange[]; isDependency: boolean };

function extractAppEvents(auditLog: ProjectSettingAuditLogEntry[], appId: number | null | undefined): AppEvent[] {
  if (!appId) return [];
  const events: AppEvent[] = [];
  for (const entry of auditLog) {
    if (entry.setting_type === "applications") {
      const oldRows = (entry.old_value?.applications as Array<Record<string, any>> | undefined) || [];
      const newRows = (entry.new_value?.applications as Array<Record<string, any>> | undefined) || [];
      const oldRow = oldRows.find((r) => r.id === appId);
      const newRow = newRows.find((r) => r.id === appId);
      if (!oldRow && !newRow) continue;
      const fields = new Set([...Object.keys(oldRow || {}), ...Object.keys(newRow || {})]);
      const changes: FieldChange[] = [];
      fields.forEach((field) => {
        if (field === "updated_at") return;
        const ov = oldRow?.[field];
        const nv = newRow?.[field];
        if (JSON.stringify(ov) !== JSON.stringify(nv)) changes.push({ field, oldValue: ov ?? null, newValue: nv ?? null });
      });
      if (changes.length) events.push({ entry, changes, isDependency: false });
    } else if (entry.setting_type === "external_dependencies") {
      const oldRows = (entry.old_value?.dependencies as Array<Record<string, any>> | undefined) || [];
      const newRows = (entry.new_value?.dependencies as Array<Record<string, any>> | undefined) || [];
      const touchesApp = [...oldRows, ...newRows].some((r) => r.application_id === appId);
      if (!touchesApp) continue;
      events.push({ entry, changes: [{ field: "external_dependencies", oldValue: null, newValue: null }], isDependency: true });
    }
  }
  return events.sort((a, b) => new Date(b.entry.changed_at).getTime() - new Date(a.entry.changed_at).getTime());
}

function fieldLabel(field: string): string {
  return field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function activitySentence(event: AppEvent, userNames: Map<number, string>): string {
  const actor = resolveUserName(userNames, event.entry.changed_by);
  if (event.isDependency) return `${actor} updated external dependencies referencing this application.`;
  if (event.entry.source === "seed") return `Registered via canonical application seed.`;
  const parts = event.changes.map((c) => {
    if (c.field === "environment_urls") return "environment configuration changed";
    if (c.field === "lifecycle_status") return `lifecycle changed from ${formatValue(c.oldValue)} to ${formatValue(c.newValue)}`;
    if (c.field === "business_owner_id" || c.field === "technical_owner_id") return `${fieldLabel(c.field)} reassigned`;
    if (c.field === "is_active") return c.newValue ? "activated" : "deactivated";
    return `${fieldLabel(c.field)} changed`;
  });
  return `${actor} ${parts.join("; ")}.`;
}

export function ApplicationInspector({
  app,
  onClose,
  dependencies,
  userNames,
  canManage,
  summary,
  auditLog,
  onEdit,
}: {
  app: ProjectApplication | null;
  onClose: () => void;
  dependencies: ProjectExternalDependency[];
  userNames: Map<number, string>;
  canManage: boolean;
  summary: ProjectApplicationsSummary | null;
  auditLog: ProjectSettingAuditLogEntry[];
  onEdit: () => void;
}) {
  const [tab, setTab] = useState<InspectorTab>("overview");
  useEffect(() => { setTab("overview"); }, [app?.id]);
  const router = useRouter();

  function openDiscovery() {
    if (!app?.id) return;
    const firstEnv = Object.keys(app.environment_urls || {})[0];
    const params = new URLSearchParams({
      project: String(app.project_id), view: "discovery", application: String(app.id),
    });
    if (firstEnv) params.set("environment", firstEnv);
    router.push(`/automation?${params.toString()}`);
  }

  const events = useMemo(() => extractAppEvents(auditLog, app?.id), [auditLog, app?.id]);
  const gaps = app ? applicationGaps(app) : [];
  const conflict = app ? summary?.mapping_conflicts.find((c) => c.application_ids.includes(app.id ?? -1)) : undefined;
  const usage = app ? summary?.mapping_usage[app.id ?? -1] ?? 0 : 0;

  return (
    <Drawer open={!!app} onOpenChange={(open) => !open && onClose()}>
      <DrawerContent size="xl">
        {app && (
    <>
      <DrawerHeader>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <DrawerTitle>APP-{app.id}</DrawerTitle>
            <Badge variant={badgeVariant(lifecycleBadgeTone(app.lifecycle_status))}>{app.lifecycle_status}</Badge>
            {app.is_default && <Badge variant="info">Default</Badge>}
          </div>
          <DrawerDescription>{app.name} &middot; {app.key}</DrawerDescription>
        </div>
        <button aria-label="Close" onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-50"><X className="h-4 w-4" /></button>
      </DrawerHeader>
      <DrawerBody>

      <div className="mb-3 flex flex-wrap gap-1 border-b border-gray-100 pb-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "rounded-md px-2 py-1 text-[10px] font-bold transition",
              tab === t.key ? "bg-[#4D0507] text-white" : "text-gray-500 hover:bg-gray-100",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          {gaps.length > 0 && (
            <div className="mb-4 rounded-lg border border-amber-100 bg-amber-50 p-3">
              <div className="mb-1 text-[9px] font-bold uppercase text-amber-700">Missing metadata</div>
              <ul className="space-y-1">
                {gaps.map((g) => (
                  <li key={g} className="flex items-start gap-1.5 text-[10px] font-semibold text-amber-800">
                    <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />{g}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <InspectorCard title="Identity">
            <div className="grid grid-cols-2 gap-3">
              <InfoPair label="Stable Key" value={app.key} />
              <InfoPair label="Application Type" value={app.application_type || "—"} />
              <InfoPair label="Aliases" value={app.aliases.length ? app.aliases.join(", ") : "—"} />
              <InfoPair label="Default Application" value={app.is_default ? "Yes" : "No"} />
            </div>
            {app.description && <p className="mt-3 text-[11px] font-semibold leading-relaxed text-gray-600">{app.description}</p>}
          </InspectorCard>
          <InspectorCard title="Ownership & Classification">
            <div className="grid grid-cols-2 gap-3">
              <InfoPair label="Business Owner" value={resolveUserName(userNames, app.business_owner_id)} />
              <InfoPair label="Technical Owner" value={resolveUserName(userNames, app.technical_owner_id)} />
              <InfoPair label="Domain" value={app.domain || "—"} />
              <InfoPair label="Product Group" value={app.product_group || "—"} />
              <InfoPair label="Product" value={app.product || "—"} />
              <InfoPair label="Channel" value={app.channel || "—"} />
            </div>
          </InspectorCard>
          <InspectorCard title="Governance">
            <div className="grid grid-cols-2 gap-3">
              <InfoPair label="Created By" value={resolveUserName(userNames, app.created_by)} />
              <InfoPair label="Created At" value={app.created_at ? new Date(app.created_at).toLocaleString() : "—"} />
              <InfoPair label="Last Updated By" value={resolveUserName(userNames, app.updated_by)} />
              <InfoPair label="Last Updated At" value={app.updated_at ? new Date(app.updated_at).toLocaleString() : "—"} />
            </div>
          </InspectorCard>
          {canManage && (
            <Button size="sm" onClick={onEdit} className="h-9 w-full bg-[#B71920] text-xs font-bold text-white hover:bg-app-brand-700">
              Edit Application
            </Button>
          )}
        </>
      )}

      {tab === "environments" && (
        <InspectorCard title="Configured Environments">
          {Object.keys(app.environment_urls || {}).length === 0 ? (
            <p className="text-xs font-semibold text-gray-400">No environments configured.</p>
          ) : (
            <div className="space-y-3">
              {Object.entries(app.environment_urls).map(([env, url]) => (
                <div key={env} className="rounded-lg border border-gray-200 p-3">
                  <div className="mb-1 flex items-center justify-between">
                    <Badge variant="secondary">{env}</Badge>
                    <span className="flex items-center gap-1 text-[9px] font-bold text-emerald-600"><ShieldCheck className="h-3 w-3" />Valid URL</span>
                  </div>
                  <p className="flex items-center gap-1 truncate text-[11px] font-semibold text-gray-600"><Globe className="h-3 w-3 shrink-0" />{url}</p>
                </div>
              ))}
            </div>
          )}
          <div className="mt-3 space-y-1.5">
            <NotConfigured label="Browser/device/AVD compatibility" />
            <NotConfigured label="Authentication profile reference" />
            <NotConfigured label="Health-check endpoint/strategy" />
          </div>
        </InspectorCard>
      )}

      {tab === "relationships" && (
        <>
          <InspectorCard title="Products & Channels">
            <div className="grid grid-cols-2 gap-3">
              <InfoPair label="Product Group" value={app.product_group || "—"} />
              <InfoPair label="Product" value={app.product || "—"} />
              <InfoPair label="Channel" value={app.channel || "—"} />
            </div>
          </InspectorCard>
          <InspectorCard title="Usage">
            <div className="flex items-center justify-between rounded-lg border border-gray-200 p-3">
              <span className="text-[11px] font-bold text-gray-600">Targeting test cases</span>
              <Badge variant="info">{usage} TC</Badge>
            </div>
            <div className="mt-2 space-y-1.5">
              <NotConfigured label="Participating journeys" />
              <NotConfigured label="Linked requirements" />
              <NotConfigured label="Automation / execution usage" />
              <NotConfigured label="Upstream / downstream applications" />
            </div>
          </InspectorCard>
          <InspectorCard title="Mapping Conflicts">
            {conflict ? (
              <div className="flex items-start gap-2 rounded-lg border border-red-100 bg-red-50 p-3 text-[11px] font-semibold text-red-700">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>Shares {[conflict.product_group, conflict.product, conflict.channel].filter(Boolean).join(" / ")} with application(s) {conflict.application_ids.filter((id) => id !== app.id).map((id) => `APP-${id}`).join(", ")}.</span>
              </div>
            ) : (
              <p className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-700"><ShieldCheck className="h-3.5 w-3.5" />No mapping conflicts detected.</p>
            )}
          </InspectorCard>
        </>
      )}

      {tab === "dependencies" && (
        <InspectorCard title="External Dependencies">
          {dependencies.length === 0 ? (
            <p className="text-xs font-semibold text-gray-400">No external dependencies recorded for this application.</p>
          ) : (
            <div className="space-y-2">
              {dependencies.map((dep) => (
                <div key={dep.id} className="rounded-lg border border-gray-200 p-3">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-xs font-bold text-gray-800"><Plug className="h-3.5 w-3.5 text-gray-400" />{dep.service_name}</span>
                    <Badge variant={dep.is_active ? "success" : "secondary"}>{dep.is_active ? "Active" : "Inactive"}</Badge>
                  </div>
                  <p className="text-[10px] font-bold uppercase text-gray-400">Mock Strategy: <span className="text-gray-600">{dep.mock_strategy}</span></p>
                  {dep.sandbox_url && <p className="truncate text-[11px] font-semibold text-gray-600">{dep.sandbox_url}</p>}
                  {dep.note && <p className="mt-1 text-[11px] font-semibold text-gray-500">{dep.note}</p>}
                </div>
              ))}
            </div>
          )}
        </InspectorCard>
      )}

      {tab === "discovery" && (
        <>
          <InspectorCard title="Discovery Readiness (Proxy)">
            <div className="flex items-center justify-between rounded-lg border border-gray-200 p-3">
              <span className="text-[11px] font-bold text-gray-600">Active + environment configured</span>
              <Badge variant={app.is_active && Object.keys(app.environment_urls || {}).length > 0 ? "success" : "warning"}>
                {app.is_active && Object.keys(app.environment_urls || {}).length > 0 ? "Ready" : "Gap"}
              </Badge>
            </div>
            <p className="mt-2 text-[10px] font-semibold text-gray-400">Environment-readiness proxy — not real discovery-session telemetry.</p>
          </InspectorCard>
          <InspectorCard title="Discovery & Health">
            <div className="space-y-1.5">
              <NotConfigured label="Discovery capability & supported modes" />
              <NotConfigured label="Application-model status & version" />
              <NotConfigured label="Last discovery session" />
              <NotConfigured label="Health-check configuration & result" />
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={!Object.keys(app.environment_urls || {}).length}
              title={
                Object.keys(app.environment_urls || {}).length
                  ? "Open Live Discovery Session for this application"
                  : "Configure at least one environment URL before starting discovery."
              }
              onClick={openDiscovery}
              className="mt-3 h-9 w-full gap-2 border-gray-200 text-xs font-bold text-gray-600"
            >
              <Radar className="h-4 w-4" />
              Start Discovery
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </InspectorCard>
        </>
      )}

      {tab === "history" && (
        <InspectorCard title="Change History">
          {events.length === 0 ? (
            <p className="text-xs font-semibold text-gray-400">No recorded changes for this application.</p>
          ) : (
            <div className="space-y-3">
              {events.map((event, idx) => (
                <div key={idx} className="rounded-lg border border-gray-100 p-2.5">
                  <div className="mb-1.5 flex items-center justify-between text-[9px] font-bold text-gray-400">
                    <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{new Date(event.entry.changed_at).toLocaleString()}</span>
                    <span className="uppercase">{event.entry.source}</span>
                  </div>
                  <p className="mb-1 text-[10px] font-extrabold text-gray-700">{resolveUserName(userNames, event.entry.changed_by)}</p>
                  {event.isDependency ? (
                    <p className="text-[10px] font-semibold text-gray-600">External dependency configuration changed.</p>
                  ) : (
                    <ul className="space-y-1">
                      {event.changes.map((c, i) => (
                        <li key={i} className="text-[10px] font-semibold text-gray-600">
                          <span className="font-bold text-gray-800">{fieldLabel(c.field)}:</span> {formatValue(c.oldValue)} → {formatValue(c.newValue)}
                        </li>
                      ))}
                    </ul>
                  )}
                  {event.entry.change_reason && <p className="mt-1 text-[10px] italic text-gray-500">&quot;{event.entry.change_reason}&quot;</p>}
                </div>
              ))}
            </div>
          )}
        </InspectorCard>
      )}

      {tab === "activity" && (
        <InspectorCard title="Activity Feed">
          {events.length === 0 ? (
            <p className="text-xs font-semibold text-gray-400">No recorded activity for this application.</p>
          ) : (
            <div className="space-y-3">
              {events.map((event, idx) => (
                <div key={idx} className="relative pl-4">
                  <span className="absolute left-0 top-1.5 h-1.5 w-1.5 rounded-full bg-[#B71920]" />
                  <p className="text-[9px] font-bold text-gray-400">{new Date(event.entry.changed_at).toLocaleString()}</p>
                  <p className="mt-0.5 text-[11px] font-semibold text-gray-700">{activitySentence(event, userNames)}</p>
                </div>
              ))}
            </div>
          )}
          <div className="mt-3 space-y-1.5">
            <NotConfigured label="Health-check events" />
            <NotConfigured label="Discovery sessions" />
            <NotConfigured label="Automation / execution usage events" />
          </div>
        </InspectorCard>
      )}
      </DrawerBody>
    </>
        )}
      </DrawerContent>
    </Drawer>
  );
}
