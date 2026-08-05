"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, Plus, ShieldCheck, X } from "lucide-react";
import {
  applicationsApi,
  type ApplicationLifecycleStatus,
  type ProjectApplication,
  type ProjectApplicationUpdatePayload,
  type UserAccount,
} from "@/lib/api";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerBody, DrawerFooter } from "@/components/ui/drawer";
import { Badge } from "@/components/ui/badge";
import { messageFromError } from "./shared";

type EnvRow = { name: string; url: string };

type Draft = {
  name: string;
  key: string;
  keyManuallyEdited: boolean;
  description: string;
  applicationType: string;
  aliasesText: string;
  lifecycleStatus: ApplicationLifecycleStatus;
  isActive: boolean;
  isDefault: boolean;
  businessOwnerId: number | null;
  technicalOwnerId: number | null;
  domain: string;
  productGroup: string;
  product: string;
  channel: string;
  environments: EnvRow[];
};

function slugify(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function draftFromApplication(app: ProjectApplication | null): Draft {
  return {
    name: app?.name ?? "",
    key: app?.key ?? "",
    keyManuallyEdited: Boolean(app),
    description: app?.description ?? "",
    applicationType: app?.application_type ?? "",
    aliasesText: (app?.aliases ?? []).join("\n"),
    lifecycleStatus: app?.lifecycle_status ?? "draft",
    isActive: app?.is_active ?? false,
    isDefault: app?.is_default ?? false,
    businessOwnerId: app?.business_owner_id ?? null,
    technicalOwnerId: app?.technical_owner_id ?? null,
    domain: app?.domain ?? "",
    productGroup: app?.product_group ?? "",
    product: app?.product ?? "",
    channel: app?.channel ?? "",
    environments: Object.entries(app?.environment_urls ?? {}).map(([name, url]) => ({ name, url })),
  };
}

function isAbsoluteHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function ApplicationDrawer({
  mode,
  application,
  projectId,
  existingApplications,
  availableEnvironments,
  users,
  authorizedOwnerIds,
  userNames,
  onClose,
  onSaved,
}: {
  mode: "add" | "edit";
  application: ProjectApplication | null;
  projectId: number | null;
  existingApplications: ProjectApplication[];
  availableEnvironments: string[];
  users: UserAccount[];
  authorizedOwnerIds: Set<number>;
  userNames: Map<number, string>;
  onClose: () => void;
  onSaved: (savedId?: number) => void | Promise<void>;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftFromApplication(application));
  const [saving, setSaving] = useState(false);
  const [validated, setValidated] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { setDraft(draftFromApplication(application)); }, [application]);

  const ownerOptions = useMemo(
    () => users.filter((u) => authorizedOwnerIds.has(u.id) || u.id === draft.businessOwnerId || u.id === draft.technicalOwnerId),
    [users, authorizedOwnerIds, draft.businessOwnerId, draft.technicalOwnerId]
  );

  const currentDefaultApp = existingApplications.find((a) => a.is_default && a.id !== application?.id);

  function updateDraft<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
    setValidated(false);
  }

  function handleNameChange(value: string) {
    setDraft((prev) => ({
      ...prev,
      name: value,
      key: prev.keyManuallyEdited ? prev.key : slugify(value),
    }));
    setValidated(false);
  }

  function addEnvironment() {
    updateDraft("environments", [...draft.environments, { name: "", url: "" }]);
  }

  function updateEnvironment(index: number, field: "name" | "url", value: string) {
    updateDraft("environments", draft.environments.map((row, i) => i === index ? { ...row, [field]: value } : row));
  }

  function removeEnvironment(index: number) {
    updateDraft("environments", draft.environments.filter((_, i) => i !== index));
  }

  // Client-side gates — the backend remains authoritative; these are a fast
  // pre-submit check plus the drawer's review-summary state per contract §10.1.
  const validationErrors: string[] = [];
  if (!draft.name.trim() || draft.name.trim().length < 2) validationErrors.push("Application Name must be at least 2 characters.");
  if (!draft.key.trim()) validationErrors.push("Stable Key is required.");
  if (mode === "add" && existingApplications.some((a) => a.key === slugify(draft.key))) {
    const conflict = existingApplications.find((a) => a.key === slugify(draft.key));
    validationErrors.push(`Stable Key "${slugify(draft.key)}" is already used by ${conflict?.name}.`);
  }
  const envNames = draft.environments.map((e) => e.name.trim().toLowerCase());
  if (new Set(envNames).size !== envNames.length) validationErrors.push("Environment names must be unique.");
  draft.environments.forEach((env) => {
    if (!env.name.trim()) validationErrors.push("Every environment needs a name.");
    if (env.url.trim() && !isAbsoluteHttpUrl(env.url.trim())) validationErrors.push(`Environment "${env.name || "(unnamed)"}" URL must be an absolute http(s) URL.`);
  });

  const ownerAssigned = Boolean(draft.businessOwnerId || draft.technicalOwnerId);
  const mapped = Boolean(draft.domain || draft.productGroup || draft.product || draft.channel);
  const hasEnvironment = draft.environments.some((e) => e.name.trim() && e.url.trim());
  const readyToActivate = validationErrors.length === 0 && ownerAssigned && mapped;
  const discoveryReady = readyToActivate && draft.isActive && hasEnvironment;

  const reviewState = validationErrors.length > 0
    ? "Blocked"
    : discoveryReady ? "Discovery Ready"
    : readyToActivate ? "Ready to Activate"
    : "Valid Draft";

  function buildPayload(overrides: Partial<Draft> = {}): ProjectApplicationUpdatePayload {
    const merged = { ...draft, ...overrides };
    return {
      key: mode === "edit" ? draft.key : slugify(merged.key),
      name: merged.name.trim(),
      description: merged.description.trim() || null,
      is_default: merged.isDefault,
      environment_urls: Object.fromEntries(
        merged.environments.filter((e) => e.name.trim() && e.url.trim()).map((e) => [e.name.trim(), e.url.trim()])
      ),
      is_active: merged.isActive,
      application_type: merged.applicationType.trim() || null,
      aliases: merged.aliasesText.split("\n").map((a) => a.trim()).filter(Boolean),
      lifecycle_status: merged.lifecycleStatus,
      business_owner_id: merged.businessOwnerId,
      technical_owner_id: merged.technicalOwnerId,
      domain: merged.domain.trim() || null,
      product_group: merged.productGroup.trim() || null,
      product: merged.product.trim() || null,
      channel: merged.channel.trim() || null,
    };
  }

  async function submit(overrides: Partial<Draft>, changeReason: string) {
    if (!projectId) return;
    if (validationErrors.length > 0) {
      setError(validationErrors[0]);
      return;
    }
    setSaving(true);
    setError("");
    try {
      const res = await applicationsApi.update(projectId, [buildPayload(overrides)], changeReason);
      const saved = res.data.applications.find((a) => a.key === (mode === "edit" ? draft.key : slugify(draft.key)));
      await onSaved(saved?.id ?? undefined);
    } catch (submitError) {
      setError(messageFromError(submitError, "Could not save this application."));
    } finally {
      setSaving(false);
    }
  }

  const canActivateNow = mode === "edit" && application?.lifecycle_status !== "active" && draft.lifecycleStatus === "active" && readyToActivate;

  return (
    <Drawer open onOpenChange={(open) => !open && !saving && onClose()}>
      <DrawerContent size="2xl">
        <DrawerHeader>
          <div>
            <DrawerTitle>{mode === "add" ? "Add Application" : "Edit Application"}</DrawerTitle>
            <DrawerDescription>Register a stable application identity and governed discovery context.</DrawerDescription>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={reviewState === "Blocked" ? "destructive" : reviewState === "Discovery Ready" ? "success" : reviewState === "Ready to Activate" ? "info" : "secondary"}>
              {reviewState}
            </Badge>
            <button aria-label="Close" onClick={() => !saving && onClose()} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-50"><X className="h-4 w-4" /></button>
          </div>
        </DrawerHeader>
        <DrawerBody>
          <section className="space-y-3">
            <h4 className="text-xs font-extrabold uppercase tracking-wide text-gray-500">Step 1 · Identity</h4>
            <div className="grid grid-cols-2 gap-3">
              <label className="col-span-2 block">
                <span className="mb-1 block text-[10px] font-bold text-gray-500">Application Name *</span>
                <input value={draft.name} onChange={(e) => handleNameChange(e.target.value)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-xs font-semibold outline-none focus:ring-2 focus:ring-app-brand-100" />
              </label>
              <label className="block">
                <span className="mb-1 block text-[10px] font-bold text-gray-500">Stable Key *</span>
                <input
                  value={draft.key}
                  disabled={mode === "edit"}
                  onChange={(e) => setDraft((p) => ({ ...p, key: e.target.value, keyManuallyEdited: true }))}
                  className="h-10 w-full rounded-lg border border-gray-200 px-3 text-xs font-mono font-semibold outline-none focus:ring-2 focus:ring-app-brand-100 disabled:bg-gray-50 disabled:text-gray-400"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-[10px] font-bold text-gray-500">Application Type</span>
                <input value={draft.applicationType} onChange={(e) => updateDraft("applicationType", e.target.value)} placeholder="Web, API, Mobile, Service..." className="h-10 w-full rounded-lg border border-gray-200 px-3 text-xs font-semibold outline-none focus:ring-2 focus:ring-app-brand-100" />
              </label>
              <label className="col-span-2 block">
                <span className="mb-1 block text-[10px] font-bold text-gray-500">Description</span>
                <textarea value={draft.description} onChange={(e) => updateDraft("description", e.target.value)} rows={2} className="w-full rounded-lg border border-gray-200 px-3 py-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-app-brand-100" />
              </label>
              <label className="col-span-2 block">
                <span className="mb-1 block text-[10px] font-bold text-gray-500">Aliases — one per line</span>
                <textarea value={draft.aliasesText} onChange={(e) => updateDraft("aliasesText", e.target.value)} rows={2} className="w-full rounded-lg border border-gray-200 px-3 py-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-app-brand-100" />
              </label>
              <label className="block">
                <span className="mb-1 block text-[10px] font-bold text-gray-500">Lifecycle State</span>
                <select value={draft.lifecycleStatus} onChange={(e) => updateDraft("lifecycleStatus", e.target.value as ApplicationLifecycleStatus)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-xs font-bold outline-none">
                  <option value="draft">Draft</option>
                  <option value="active">Active</option>
                  <option value="deprecated">Deprecated</option>
                  <option value="retired">Retired</option>
                </select>
              </label>
              <label className="flex items-center gap-2 rounded-lg border border-gray-200 px-3">
                <input type="checkbox" checked={draft.isActive} onChange={(e) => updateDraft("isActive", e.target.checked)} />
                <span className="text-xs font-semibold text-gray-700">Active</span>
              </label>
              <label className="col-span-2 flex items-start gap-2 rounded-lg border border-gray-200 bg-gray-50/60 px-3 py-2">
                <input type="checkbox" checked={draft.isDefault} onChange={(e) => updateDraft("isDefault", e.target.checked)} className="mt-0.5" />
                <span className="text-xs font-semibold text-gray-700">
                  Set as Project Default
                  {draft.isDefault && currentDefaultApp && (
                    <span className="mt-0.5 block text-[10px] font-bold text-amber-600">This replaces &quot;{currentDefaultApp.name}&quot; as the project default.</span>
                  )}
                </span>
              </label>
            </div>
          </section>

          <section className="space-y-3 border-t border-gray-100 pt-4">
            <h4 className="text-xs font-extrabold uppercase tracking-wide text-gray-500">Step 2 · Ownership & Classification</h4>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="mb-1 block text-[10px] font-bold text-gray-500">Business Owner</span>
                <select value={draft.businessOwnerId ?? ""} onChange={(e) => updateDraft("businessOwnerId", e.target.value ? Number(e.target.value) : null)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-xs font-bold outline-none">
                  <option value="">Unassigned</option>
                  {ownerOptions.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-[10px] font-bold text-gray-500">Technical Owner</span>
                <select value={draft.technicalOwnerId ?? ""} onChange={(e) => updateDraft("technicalOwnerId", e.target.value ? Number(e.target.value) : null)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-xs font-bold outline-none">
                  <option value="">Unassigned</option>
                  {ownerOptions.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </select>
              </label>
              {ownerOptions.length === 0 && (
                <p className="col-span-2 flex items-center gap-1.5 text-[10px] font-semibold text-amber-600"><AlertTriangle className="h-3 w-3" />No authorized project members found to assign as owner.</p>
              )}
              <label className="block">
                <span className="mb-1 block text-[10px] font-bold text-gray-500">Domain</span>
                <input value={draft.domain} onChange={(e) => updateDraft("domain", e.target.value)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-xs font-semibold outline-none focus:ring-2 focus:ring-app-brand-100" />
              </label>
              <label className="block">
                <span className="mb-1 block text-[10px] font-bold text-gray-500">Product Group</span>
                <input value={draft.productGroup} onChange={(e) => updateDraft("productGroup", e.target.value)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-xs font-semibold outline-none focus:ring-2 focus:ring-app-brand-100" />
              </label>
              <label className="block">
                <span className="mb-1 block text-[10px] font-bold text-gray-500">Product</span>
                <input value={draft.product} onChange={(e) => updateDraft("product", e.target.value)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-xs font-semibold outline-none focus:ring-2 focus:ring-app-brand-100" />
              </label>
              <label className="block">
                <span className="mb-1 block text-[10px] font-bold text-gray-500">Channel</span>
                <input value={draft.channel} onChange={(e) => updateDraft("channel", e.target.value)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-xs font-semibold outline-none focus:ring-2 focus:ring-app-brand-100" />
              </label>
            </div>
            <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50/60 p-2.5 text-[10px] font-semibold text-gray-400">
              Customer Segment, Customer Type, Request Type, supported journeys and upstream/downstream applications — not configured. No backing subsystem persists these relationships yet.
            </div>
          </section>

          <section className="space-y-3 border-t border-gray-100 pt-4">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-extrabold uppercase tracking-wide text-gray-500">Step 3 · Environments & Access</h4>
              <button onClick={addEnvironment} className="flex items-center gap-1 text-[11px] font-bold text-[#B71920]"><Plus className="h-3.5 w-3.5" />Add Environment</button>
            </div>
            {draft.environments.length === 0 ? (
              <p className="text-xs font-semibold text-gray-400">No environments configured. An application may be saved as Draft without one, but at least one is required for Discovery Ready.</p>
            ) : (
              <div className="space-y-2">
                {draft.environments.map((env, index) => (
                  <div key={index} className="grid grid-cols-[140px_1fr_28px] items-center gap-2">
                    <input
                      value={env.name}
                      onChange={(e) => updateEnvironment(index, "name", e.target.value)}
                      placeholder="SIT, QA, UAT..."
                      list="available-environments"
                      className="h-9 rounded-lg border border-gray-200 px-2 text-xs font-bold outline-none"
                    />
                    <input
                      value={env.url}
                      onChange={(e) => updateEnvironment(index, "url", e.target.value)}
                      placeholder="https://..."
                      className="h-9 rounded-lg border border-gray-200 px-2 text-xs font-semibold outline-none"
                    />
                    <button onClick={() => removeEnvironment(index)} className="text-gray-400 hover:text-red-600"><X className="h-4 w-4" /></button>
                  </div>
                ))}
              </div>
            )}
            <datalist id="available-environments">
              {availableEnvironments.map((env) => <option key={env} value={env} />)}
            </datalist>
            <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50/60 p-2.5 text-[10px] font-semibold text-gray-400">
              Health-check strategy, authentication profile reference, browser/device/AVD compatibility and environment restrictions — not configured. Auth profiles are selector-only when available; credentials are never stored here.
            </div>
          </section>

          <section className="space-y-3 border-t border-gray-100 pt-4">
            <h4 className="text-xs font-extrabold uppercase tracking-wide text-gray-500">Step 4 · Discovery, Dependencies & Review</h4>
            <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50/60 p-3 text-[10px] font-semibold text-gray-400">
              Discovery Enabled, supported modes/surfaces, allowed host list and evidence policy — not configured; this backend extension has not been built yet. External dependency mapping is managed from the application&apos;s Dependencies inspector tab after saving.
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-3">
              <p className="mb-2 text-[10px] font-extrabold uppercase text-gray-500">Review Summary</p>
              <ul className="space-y-1 text-[11px] font-semibold">
                <li className={ownerAssigned ? "text-emerald-700" : "text-amber-600"}>{ownerAssigned ? "✓" : "○"} Owner assigned</li>
                <li className={mapped ? "text-emerald-700" : "text-amber-600"}>{mapped ? "✓" : "○"} Domain/Product/Channel mapped</li>
                <li className={hasEnvironment ? "text-emerald-700" : "text-amber-600"}>{hasEnvironment ? "✓" : "○"} At least one environment configured</li>
                <li className={draft.isActive ? "text-emerald-700" : "text-gray-400"}>{draft.isActive ? "✓" : "○"} Active</li>
              </ul>
              {validationErrors.length > 0 && (
                <div className="mt-2 space-y-1">
                  {validationErrors.map((err) => (
                    <p key={err} className="flex items-start gap-1.5 text-[10px] font-semibold text-red-700"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />{err}</p>
                  ))}
                </div>
              )}
              {validated && validationErrors.length === 0 && (
                <p className="mt-2 flex items-center gap-1.5 text-[10px] font-bold text-emerald-700"><ShieldCheck className="h-3 w-3" />Client-side checks passed. Final validation occurs on save.</p>
              )}
            </div>
          </section>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">{error}</div>
          )}
        </DrawerBody>
        <DrawerFooter>
          <button type="button" disabled={saving} onClick={onClose} className="inline-flex h-9 items-center justify-center rounded-lg border border-gray-200 bg-white px-4 text-xs font-bold text-gray-700 hover:bg-gray-50 disabled:opacity-50">
            Cancel
          </button>
          <button type="button" disabled={saving} onClick={() => setValidated(true)} className="inline-flex h-9 items-center justify-center rounded-lg border border-gray-200 bg-white px-4 text-xs font-bold text-gray-700 hover:bg-gray-50 disabled:opacity-50">
            Validate
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => submit({ lifecycleStatus: "draft", isActive: false }, "Saved as draft")}
            className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-gray-200 bg-white px-4 text-xs font-bold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Save Draft
          </button>
          <button
            type="button"
            disabled={saving || validationErrors.length > 0}
            onClick={() => submit({}, mode === "add" ? "Application registered" : "Application updated")}
            className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-[#B71920] px-4 text-xs font-bold text-white shadow-sm hover:bg-app-brand-700 disabled:opacity-50"
          >
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {mode === "add" ? "Add Application" : canActivateNow ? "Activate Application" : "Save Changes"}
          </button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
