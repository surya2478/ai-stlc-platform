"use client";

/**
 * Organization-level taxonomy master data.
 *
 * Deliberately not project-scoped: these tables carry `organization_id`, are
 * referenced by test cases across every project, and are configured once. The
 * screen takes no `?project=` parameter for that reason — `/settings` is the
 * project-scoped surface and this is not part of it.
 *
 * The dependent chain is Product Group → Product → Sub Request Type, and only
 * the first hop is a parent column: `products.parent_id` is NOT NULL, so a
 * Product cannot exist without a Product Group. The selector reflects that —
 * you pick the group before its products can be listed or created.
 *
 * The last hop is not a parent column. Sub Request Type reaches Product
 * through the `taxonomy_relationships` edge table (`subrequest_for_product`),
 * which is many-to-many, so one request type can serve several products. It is
 * maintained as its own list and attached to whichever product is selected.
 *
 * Domain is deliberately outside the chain. `product_groups.parent_id` was
 * NOT NULL until migration 059, which made Domain a mandatory root nobody
 * wanted — every deployment had to invent a domain row to unlock the level
 * below. It is now an independent label, listed alongside Channel.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Layers, Loader2, Plus, Pencil, X, Check, AlertTriangle,
  ChevronRight, Link2, Unlink, ShieldAlert, RotateCcw, Network,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  taxonomyApi, usersApi,
  type TaxonomyEntry, type TaxonomyChildEntry, type TaxonomyGroupEntry,
  type TaxonomyEntryInput, type TaxonomyRelationship,
  type UserAccount,
} from "@/lib/api";
import { cn } from "@/lib/utils";

function messageFromError(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string") return detail;
    // FastAPI validation errors arrive as a list of {loc, msg}.
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string } | undefined;
      if (first?.msg) return first.msg;
    }
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

/** Mirrors `_code_shape` on the backend so the user is told before the round
 *  trip, not after a 422. */
function normalizeCode(raw: string): string {
  return raw.trim().toUpperCase();
}

function codeError(code: string): string | null {
  const value = normalizeCode(code);
  if (!value) return "Code is required.";
  if (!/^[A-Z0-9_-]+$/.test(value)) return "Code may only contain letters, digits, hyphen and underscore.";
  if (value.length > 60) return "Code must be 60 characters or fewer.";
  return null;
}

/* ------------------------------------------------------------------ */
/* Row editor — one form shared by every table                         */
/* ------------------------------------------------------------------ */

type EditorValue = { name: string; code: string; description: string };

const EMPTY_EDITOR: EditorValue = { name: "", code: "", description: "" };

function EntryForm({
  value,
  onChange,
  onSubmit,
  onCancel,
  busy,
  submitLabel,
}: {
  value: EditorValue;
  onChange: (next: EditorValue) => void;
  onSubmit: () => void;
  onCancel: () => void;
  busy: boolean;
  submitLabel: string;
}) {
  const invalidCode = value.code ? codeError(value.code) : null;
  const canSubmit = Boolean(value.name.trim()) && Boolean(value.code.trim()) && !invalidCode && !busy;

  return (
    <div className="rounded-lg border border-[#1b59f8]/30 bg-blue-50/40 p-2.5 space-y-2">
      <input
        autoFocus
        value={value.name}
        onChange={(e) => onChange({ ...value, name: e.target.value })}
        placeholder="Name"
        aria-label="Name"
        className="w-full rounded-md border border-slate-200 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[#1b59f8]"
      />
      <input
        value={value.code}
        onChange={(e) => onChange({ ...value, code: e.target.value })}
        placeholder="CODE"
        aria-label="Code"
        className="w-full rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-[11px] uppercase focus:outline-none focus:ring-2 focus:ring-[#1b59f8]"
      />
      <input
        value={value.description}
        onChange={(e) => onChange({ ...value, description: e.target.value })}
        placeholder="Description (optional)"
        aria-label="Description"
        className="w-full rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] focus:outline-none focus:ring-2 focus:ring-[#1b59f8]"
      />
      {invalidCode && (
        <p className="text-[10px] font-semibold text-rose-600">{invalidCode}</p>
      )}
      <div className="flex items-center gap-1.5">
        <Button size="sm" className="h-7 flex-1 text-[10px]" onClick={onSubmit} disabled={!canSubmit}>
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <><Check className="h-3 w-3 mr-1" />{submitLabel}</>}
        </Button>
        <Button size="sm" variant="outline" className="h-7 text-[10px] border-slate-200" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* List panel — used for both cascade columns and standalone tables    */
/* ------------------------------------------------------------------ */

type ListPanelProps = {
  title: string;
  subtitle?: string;
  entries: TaxonomyEntry[];
  selectedId?: number | null;
  onSelect?: (id: number) => void;
  onCreate: (input: TaxonomyEntryInput) => Promise<void>;
  onUpdate: (id: number, input: Partial<TaxonomyEntryInput>) => Promise<void>;
  onDeactivate: (id: number) => Promise<void>;
  canEdit: boolean;
  /** Set when a parent must be chosen first — the panel explains rather than
   *  offering an Add button that could only fail. */
  blockedReason?: string | null;
  loading?: boolean;
  emptyHint: string;
};

function ListPanel({
  title, subtitle, entries, selectedId, onSelect,
  onCreate, onUpdate, onDeactivate, canEdit, blockedReason, loading, emptyHint,
}: ListPanelProps) {
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<EditorValue>(EMPTY_EDITOR);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A parent change invalidates any half-finished child form.
  useEffect(() => {
    setAdding(false);
    setEditingId(null);
    setError(null);
  }, [blockedReason, entries.length]);

  const startAdd = () => { setDraft(EMPTY_EDITOR); setEditingId(null); setAdding(true); setError(null); };
  const startEdit = (entry: TaxonomyEntry) => {
    setDraft({ name: entry.name, code: entry.code, description: entry.description ?? "" });
    setAdding(false);
    setEditingId(entry.id);
    setError(null);
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const payload: TaxonomyEntryInput = {
        name: draft.name.trim(),
        code: normalizeCode(draft.code),
        description: draft.description.trim() || null,
      };
      if (editingId !== null) await onUpdate(editingId, payload);
      else await onCreate(payload);
      setAdding(false);
      setEditingId(null);
      setDraft(EMPTY_EDITOR);
    } catch (e: unknown) {
      setError(messageFromError(e, editingId !== null ? "Could not save the change." : "Could not create the entry."));
    } finally {
      setBusy(false);
    }
  };

  const deactivate = async (entry: TaxonomyEntry) => {
    setBusy(true);
    setError(null);
    try {
      await onDeactivate(entry.id);
    } catch (e: unknown) {
      setError(messageFromError(e, "Could not deactivate the entry."));
    } finally {
      setBusy(false);
    }
  };

  const reactivate = async (entry: TaxonomyEntry) => {
    setBusy(true);
    setError(null);
    try {
      await onUpdate(entry.id, { is_active: true, status: "active" });
    } catch (e: unknown) {
      setError(messageFromError(e, "Could not reactivate the entry."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col rounded-lg border border-slate-200 bg-white">
      <div className="flex items-start justify-between gap-2 border-b border-slate-100 px-3 py-2">
        <div className="min-w-0">
          <h3 className="text-xs font-bold text-slate-800">{title}</h3>
          <p className="text-[10px] font-semibold text-slate-400">
            {subtitle ?? `${entries.length} value${entries.length === 1 ? "" : "s"}`}
          </p>
        </div>
        {canEdit && !blockedReason && !adding && editingId === null && (
          <button
            type="button"
            onClick={startAdd}
            className="shrink-0 rounded-md p-1 text-[#1b59f8] hover:bg-blue-50"
            aria-label={`Add ${title}`}
            title={`Add ${title}`}
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto p-2">
        {error && (
          <div className="flex items-start gap-1.5 rounded-md border border-rose-200 bg-rose-50 p-2">
            <AlertTriangle className="mt-px h-3 w-3 shrink-0 text-rose-500" />
            <p className="text-[10px] font-semibold leading-relaxed text-rose-700">{error}</p>
          </div>
        )}

        {blockedReason ? (
          <p className="px-1 py-6 text-center text-[10px] font-semibold leading-relaxed text-slate-400">
            {blockedReason}
          </p>
        ) : loading ? (
          <div className="space-y-1">
            {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-7 animate-pulse rounded bg-slate-100" />)}
          </div>
        ) : (
          <>
            {adding && (
              <EntryForm
                value={draft} onChange={setDraft} onSubmit={submit}
                onCancel={() => { setAdding(false); setError(null); }}
                busy={busy} submitLabel="Create"
              />
            )}

            {entries.length === 0 && !adding && (
              <p className="px-1 py-6 text-center text-[10px] font-semibold leading-relaxed text-slate-400">
                {emptyHint}
              </p>
            )}

            {entries.map((entry) =>
              editingId === entry.id ? (
                <EntryForm
                  key={entry.id}
                  value={draft} onChange={setDraft} onSubmit={submit}
                  onCancel={() => { setEditingId(null); setError(null); }}
                  busy={busy} submitLabel="Save"
                />
              ) : (
                <div
                  key={entry.id}
                  onClick={onSelect ? () => onSelect(entry.id) : undefined}
                  className={cn(
                    "group flex items-center gap-2 rounded-md px-2 py-1.5 transition-colors",
                    onSelect && "cursor-pointer",
                    selectedId === entry.id ? "bg-[#1b59f8] text-white" : "hover:bg-slate-50",
                    !entry.is_active && selectedId !== entry.id && "opacity-55",
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <p className={cn("truncate text-[11px] font-bold", selectedId === entry.id ? "text-white" : "text-slate-700")}>
                      {entry.name}
                    </p>
                    <p className={cn("truncate font-mono text-[9px] font-semibold", selectedId === entry.id ? "text-white/70" : "text-slate-400")}>
                      {entry.code}
                    </p>
                  </div>
                  {!entry.is_active && (
                    <Badge variant="secondary" className="shrink-0 text-[8px]">Inactive</Badge>
                  )}
                  {canEdit && (
                    <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); startEdit(entry); }}
                        className={cn("rounded p-1", selectedId === entry.id ? "hover:bg-white/20" : "hover:bg-slate-200")}
                        aria-label={`Edit ${entry.name}`}
                        title="Edit"
                      >
                        <Pencil className="h-3 w-3" />
                      </button>
                      {entry.is_active ? (
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); void deactivate(entry); }}
                          className={cn("rounded p-1", selectedId === entry.id ? "hover:bg-white/20" : "hover:bg-slate-200")}
                          aria-label={`Deactivate ${entry.name}`}
                          title="Deactivate — the value stays resolvable on existing test cases"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); void reactivate(entry); }}
                          className={cn("rounded p-1", selectedId === entry.id ? "hover:bg-white/20" : "hover:bg-slate-200")}
                          aria-label={`Reactivate ${entry.name}`}
                          title="Reactivate"
                        >
                          <RotateCcw className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  )}
                  {onSelect && selectedId === entry.id && <ChevronRight className="h-3 w-3 shrink-0 opacity-70" />}
                </div>
              ),
            )}
          </>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Sub Request Types — manage the vocabulary and link it to a product  */
/* ------------------------------------------------------------------ */

function SubRequestTypePanel({
  entries, linkedIds, selectedProductName, canEdit, loading,
  linkBusyId, linkError, onToggleLink, onCreate, onUpdate, onDeactivate,
}: {
  entries: TaxonomyEntry[];
  linkedIds: Set<number>;
  selectedProductName: string | null;
  canEdit: boolean;
  loading: boolean;
  linkBusyId: number | null;
  linkError: string | null;
  onToggleLink: (id: number) => Promise<void>;
  onCreate: (input: TaxonomyEntryInput) => Promise<void>;
  onUpdate: (id: number, input: Partial<TaxonomyEntryInput>) => Promise<void>;
  onDeactivate: (id: number) => Promise<void>;
}) {
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<EditorValue>(EMPTY_EDITOR);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const payload: TaxonomyEntryInput = {
        name: draft.name.trim(),
        code: normalizeCode(draft.code),
        description: draft.description.trim() || null,
      };
      if (editingId !== null) await onUpdate(editingId, payload);
      else await onCreate(payload);
      setAdding(false);
      setEditingId(null);
      setDraft(EMPTY_EDITOR);
    } catch (e: unknown) {
      setError(messageFromError(e, "Could not save the sub request type."));
    } finally {
      setBusy(false);
    }
  };

  const runRowAction = async (action: () => Promise<void>, fallback: string) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e: unknown) {
      setError(messageFromError(e, fallback));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col rounded-lg border border-slate-200 bg-white">
      <div className="flex items-start justify-between gap-2 border-b border-slate-100 px-3 py-2">
        <div className="min-w-0">
          <h3 className="text-xs font-bold text-slate-800">Sub Request Type</h3>
          <p className="text-[10px] font-semibold text-slate-400">
            {selectedProductName
              ? `${linkedIds.size} of ${entries.length} linked to ${selectedProductName}`
              : `${entries.length} value${entries.length === 1 ? "" : "s"} · select a Product to link`}
          </p>
        </div>
        {canEdit && !adding && editingId === null && (
          <button
            type="button"
            onClick={() => { setDraft(EMPTY_EDITOR); setAdding(true); setError(null); }}
            className="shrink-0 rounded-md p-1 text-[#1b59f8] hover:bg-blue-50"
            aria-label="Add Sub Request Type"
            title="Add Sub Request Type"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto p-2">
        {(error || linkError) && (
          <div className="flex items-start gap-1.5 rounded-md border border-rose-200 bg-rose-50 p-2">
            <AlertTriangle className="mt-px h-3 w-3 shrink-0 text-rose-500" />
            <p className="text-[10px] font-semibold leading-relaxed text-rose-700">{error ?? linkError}</p>
          </div>
        )}

        {loading ? (
          <div className="space-y-1">
            {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-7 animate-pulse rounded bg-slate-100" />)}
          </div>
        ) : (
          <>
            {adding && (
              <EntryForm
                value={draft} onChange={setDraft} onSubmit={submit}
                onCancel={() => { setAdding(false); setError(null); }}
                busy={busy} submitLabel="Create"
              />
            )}

            {entries.length === 0 && !adding && (
              <p className="px-1 py-6 text-center text-[10px] font-semibold leading-relaxed text-slate-400">
                No sub request types yet. Add one, then tick it against a product.
              </p>
            )}

            {entries.map((srt) =>
              editingId === srt.id ? (
                <EntryForm
                  key={srt.id}
                  value={draft} onChange={setDraft} onSubmit={submit}
                  onCancel={() => { setEditingId(null); setError(null); }}
                  busy={busy} submitLabel="Save"
                />
              ) : (
                <div
                  key={srt.id}
                  className={cn(
                    "group flex items-center gap-2 rounded-md border px-2 py-1.5 transition-colors",
                    linkedIds.has(srt.id)
                      ? "border-emerald-200 bg-emerald-50"
                      : "border-transparent hover:bg-slate-50",
                    !srt.is_active && "opacity-55",
                  )}
                >
                  {/* The tick is only meaningful once a product is chosen — it
                      is the product that the link belongs to. */}
                  <button
                    type="button"
                    disabled={!canEdit || !selectedProductName || linkBusyId === srt.id}
                    onClick={() => void onToggleLink(srt.id)}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left disabled:cursor-default"
                    title={
                      !selectedProductName
                        ? "Select a Product to link this sub request type"
                        : linkedIds.has(srt.id)
                          ? `Unlink from ${selectedProductName}`
                          : `Link to ${selectedProductName}`
                    }
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[11px] font-bold text-slate-700">{srt.name}</p>
                      <p className="truncate font-mono text-[9px] font-semibold text-slate-400">{srt.code}</p>
                    </div>
                    {linkBusyId === srt.id ? (
                      <Loader2 className="h-3 w-3 shrink-0 animate-spin text-slate-400" />
                    ) : linkedIds.has(srt.id) ? (
                      <Link2 className="h-3 w-3 shrink-0 text-emerald-600" />
                    ) : selectedProductName && canEdit ? (
                      <Unlink className="h-3 w-3 shrink-0 text-slate-300" />
                    ) : null}
                  </button>

                  {canEdit && (
                    <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                      <button
                        type="button"
                        onClick={() => {
                          setDraft({ name: srt.name, code: srt.code, description: srt.description ?? "" });
                          setAdding(false);
                          setEditingId(srt.id);
                          setError(null);
                        }}
                        className="rounded p-1 hover:bg-slate-200"
                        aria-label={`Edit ${srt.name}`}
                        title="Edit"
                      >
                        <Pencil className="h-3 w-3" />
                      </button>
                      {srt.is_active ? (
                        <button
                          type="button"
                          onClick={() => void runRowAction(() => onDeactivate(srt.id), "Could not deactivate.")}
                          className="rounded p-1 hover:bg-slate-200"
                          aria-label={`Deactivate ${srt.name}`}
                          title="Deactivate — stays resolvable on existing test cases"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void runRowAction(() => onUpdate(srt.id, { is_active: true, status: "active" }), "Could not reactivate.")}
                          className="rounded p-1 hover:bg-slate-200"
                          aria-label={`Reactivate ${srt.name}`}
                          title="Reactivate"
                        >
                          <RotateCcw className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ),
            )}
          </>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function TaxonomyPage() {
  const [me, setMe] = useState<UserAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [domains, setDomains] = useState<TaxonomyEntry[]>([]);
  const [productGroups, setProductGroups] = useState<TaxonomyGroupEntry[]>([]);
  const [products, setProducts] = useState<TaxonomyChildEntry[]>([]);
  const [subRequestTypes, setSubRequestTypes] = useState<TaxonomyEntry[]>([]);
  const [businessProcesses, setBusinessProcesses] = useState<TaxonomyEntry[]>([]);
  const [systems, setSystems] = useState<TaxonomyEntry[]>([]);
  const [testCaseTypes, setTestCaseTypes] = useState<TaxonomyEntry[]>([]);
  const [complexities, setComplexities] = useState<TaxonomyEntry[]>([]);
  const [environments, setEnvironments] = useState<TaxonomyEntry[]>([]);
  const [srtLinks, setSrtLinks] = useState<TaxonomyRelationship[]>([]);

  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null);
  const [linkBusyId, setLinkBusyId] = useState<number | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);

  // Mirrors `require_taxonomy_admin` / `is_platform_admin` on the backend.
  // Everyone may read; only platform admins may write, so the controls are
  // hidden rather than shown and then refused with a 403.
  const canEdit = Boolean(me?.is_superuser || ["admin", "platform_admin", "Platform Admin"].includes(me?.role ?? ""));

  const loadAll = useCallback(async () => {
    setLoadError(null);
    try {
      const [d, pg, p, srt, bp, sys, tct, cx, env, links] = await Promise.all([
        taxonomyApi.qaDomains(false),
        taxonomyApi.productGroups({ active_only: false }),
        taxonomyApi.products({ active_only: false }),
        taxonomyApi.subRequestTypes(false),
        taxonomyApi.businessProcesses(false),
        taxonomyApi.systems(false),
        taxonomyApi.testCaseTypes(false),
        taxonomyApi.testCaseComplexities(false),
        taxonomyApi.environments(false),
        taxonomyApi.relationships({ relation_type: "subrequest_for_product" }),
      ]);
      setDomains(d.data ?? []);
      setProductGroups(pg.data ?? []);
      setProducts(p.data ?? []);
      setSubRequestTypes(srt.data ?? []);
      setBusinessProcesses(bp.data ?? []);
      setSystems(sys.data ?? []);
      setTestCaseTypes(tct.data ?? []);
      setComplexities(cx.data ?? []);
      setEnvironments(env.data ?? []);
      setSrtLinks(links.data ?? []);
    } catch (e: unknown) {
      // Surfaced rather than swallowed: an empty dropdown and a failed fetch
      // look identical to the user otherwise.
      setLoadError(messageFromError(e, "Could not load the taxonomy."));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      usersApi.me().then((r) => { if (!cancelled) setMe(r.data); }).catch(() => undefined),
      loadAll(),
    ]).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [loadAll]);

  const visibleProducts = useMemo(
    () => (selectedGroupId ? products.filter((p) => p.parent_id === selectedGroupId) : []),
    [products, selectedGroupId],
  );

  // Clear a stale product selection when its group changes or disappears.
  useEffect(() => {
    if (selectedProductId && !visibleProducts.some((p) => p.id === selectedProductId)) setSelectedProductId(null);
  }, [visibleProducts, selectedProductId]);

  const linkedSrtIds = useMemo(() => {
    if (!selectedProductId) return new Set<number>();
    return new Set(srtLinks.filter((r) => r.to_id === selectedProductId).map((r) => r.from_id));
  }, [srtLinks, selectedProductId]);

  const toggleSrtLink = async (srtId: number) => {
    if (!selectedProductId) return;
    setLinkBusyId(srtId);
    setLinkError(null);
    try {
      const existing = srtLinks.find((r) => r.from_id === srtId && r.to_id === selectedProductId);
      if (existing) await taxonomyApi.deleteRelationship(existing.id);
      else await taxonomyApi.createRelationship({ relation_type: "subrequest_for_product", from_id: srtId, to_id: selectedProductId });
      const fresh = await taxonomyApi.relationships({ relation_type: "subrequest_for_product" });
      setSrtLinks(fresh.data ?? []);
    } catch (e: unknown) {
      setLinkError(messageFromError(e, "Could not change the link."));
    } finally {
      setLinkBusyId(null);
    }
  };

  const selectedProduct = visibleProducts.find((p) => p.id === selectedProductId) ?? null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-slate-900">
            <Layers className="h-5 w-5 text-[#1b59f8]" />
            Taxonomy
          </h1>
          <p className="mt-0.5 text-xs font-semibold text-slate-500">
            Organization-wide master data. Configured once, available to every project.
          </p>
        </div>
        {!loading && !canEdit && (
          <div className="flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
            <ShieldAlert className="h-3.5 w-3.5 shrink-0 text-amber-600" />
            <p className="text-[11px] font-semibold text-amber-700">
              Read-only — only platform administrators can change the taxonomy.
            </p>
          </div>
        )}
      </div>

      {loadError && (
        <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3">
          <AlertTriangle className="mt-px h-4 w-4 shrink-0 text-rose-500" />
          <div>
            <p className="text-xs font-bold text-rose-700">{loadError}</p>
            <button onClick={() => void loadAll()} className="mt-1 text-[11px] font-semibold text-rose-700 underline">
              Retry
            </button>
          </div>
        </div>
      )}

      {/* ── Cascade ─────────────────────────────────────────────────── */}
      <Card>
        <CardContent className="p-5">
          <div className="mb-3">
            <h2 className="flex items-center gap-1.5 text-sm font-bold text-slate-800">
              <Network className="h-4 w-4 text-slate-400" />
              Product Hierarchy
            </h2>
            <p className="text-[11px] font-semibold text-slate-400">
              Product Group → Product → Sub Request Type. Pick one level to work on the next.
            </p>
          </div>

          <div className="grid gap-3 lg:grid-cols-3">
            <ListPanel
              title="Product Group"
              entries={productGroups}
              selectedId={selectedGroupId}
              onSelect={setSelectedGroupId}
              canEdit={canEdit}
              loading={loading}
              emptyHint="No product groups yet. Add the first one to start the hierarchy."
              onCreate={async (input) => { await taxonomyApi.createProductGroup(input); await loadAll(); }}
              onUpdate={async (id, input) => { await taxonomyApi.updateProductGroup(id, input); await loadAll(); }}
              onDeactivate={async (id) => { await taxonomyApi.deactivateProductGroup(id); await loadAll(); }}
            />

            <ListPanel
              title="Product"
              subtitle={selectedGroupId ? `${visibleProducts.length} under selected group` : undefined}
              entries={visibleProducts}
              selectedId={selectedProductId}
              onSelect={setSelectedProductId}
              canEdit={canEdit}
              loading={loading}
              blockedReason={selectedGroupId ? null : "Select a Product Group first — every Product belongs to one."}
              emptyHint="No products under this product group yet."
              onCreate={async (input) => {
                await taxonomyApi.createProduct({ ...input, parent_id: selectedGroupId! });
                await loadAll();
              }}
              onUpdate={async (id, input) => { await taxonomyApi.updateProduct(id, input); await loadAll(); }}
              onDeactivate={async (id) => { await taxonomyApi.deactivateProduct(id); await loadAll(); }}
            />

            {/* The one place Sub Request Types live. They are a flat table
                (no parent column) reached from Product through a many-to-many
                edge, so this panel does both jobs: maintain the vocabulary,
                and tick which entries apply to the selected product. Listing
                it here *and* under Independent Lists showed the same table
                twice and made it look like two different things. */}
            <SubRequestTypePanel
              entries={subRequestTypes}
              linkedIds={linkedSrtIds}
              selectedProductName={selectedProduct?.name ?? null}
              canEdit={canEdit}
              loading={loading}
              linkBusyId={linkBusyId}
              linkError={linkError}
              onToggleLink={toggleSrtLink}
              onCreate={async (input) => { await taxonomyApi.createSubRequestType(input); await loadAll(); }}
              onUpdate={async (id, input) => { await taxonomyApi.updateSubRequestType(id, input); await loadAll(); }}
              onDeactivate={async (id) => { await taxonomyApi.deactivateSubRequestType(id); await loadAll(); }}
            />
          </div>
        </CardContent>
      </Card>

      {/* ── Independent lists ───────────────────────────────────────── */}
      <Card>
        <CardContent className="p-5">
          <div className="mb-3">
            <h2 className="text-sm font-bold text-slate-800">Independent Lists</h2>
            <p className="text-[11px] font-semibold text-slate-400">
              Flat vocabularies with no parent. Available to every project as soon as they are added.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <ListPanel
              title="Domain"
              entries={domains}
              canEdit={canEdit}
              loading={loading}
              emptyHint="No domains yet."
              onCreate={async (input) => { await taxonomyApi.createQaDomain(input); await loadAll(); }}
              onUpdate={async (id, input) => { await taxonomyApi.updateQaDomain(id, input); await loadAll(); }}
              onDeactivate={async (id) => { await taxonomyApi.deactivateQaDomain(id); await loadAll(); }}
            />
            <ListPanel
              title="Channel"
              subtitle={`${systems.length} value${systems.length === 1 ? "" : "s"} · stored as Systems`}
              entries={systems}
              canEdit={canEdit}
              loading={loading}
              emptyHint="No channels yet."
              onCreate={async (input) => { await taxonomyApi.createSystem(input); await loadAll(); }}
              onUpdate={async (id, input) => { await taxonomyApi.updateSystem(id, input); await loadAll(); }}
              onDeactivate={async (id) => { await taxonomyApi.deactivateSystem(id); await loadAll(); }}
            />
            {/* The journey a requirement belongs to. Flat rather than under
                Product Group — the same journey runs across products. */}
            <ListPanel
              title="Business Process"
              subtitle="Journey on Requirement Analysis"
              entries={businessProcesses}
              canEdit={canEdit}
              loading={loading}
              emptyHint="No business processes yet."
              onCreate={async (input) => { await taxonomyApi.createBusinessProcess(input); await loadAll(); }}
              onUpdate={async (id, input) => { await taxonomyApi.updateBusinessProcess(id, input); await loadAll(); }}
              onDeactivate={async (id) => { await taxonomyApi.deactivateBusinessProcess(id); await loadAll(); }}
            />
            <ListPanel
              title="Test Case Type"
              entries={testCaseTypes}
              canEdit={canEdit}
              loading={loading}
              emptyHint="No test case types yet."
              onCreate={async (input) => { await taxonomyApi.createTestCaseType(input); await loadAll(); }}
              onUpdate={async (id, input) => { await taxonomyApi.updateTestCaseType(id, input); await loadAll(); }}
              onDeactivate={async (id) => { await taxonomyApi.deactivateTestCaseType(id); await loadAll(); }}
            />
            <ListPanel
              title="Test Case Complexity"
              entries={complexities}
              canEdit={canEdit}
              loading={loading}
              emptyHint="No complexity levels yet."
              onCreate={async (input) => { await taxonomyApi.createTestCaseComplexity(input); await loadAll(); }}
              onUpdate={async (id, input) => { await taxonomyApi.updateTestCaseComplexity(id, input); await loadAll(); }}
              onDeactivate={async (id) => { await taxonomyApi.deactivateTestCaseComplexity(id); await loadAll(); }}
            />
            <ListPanel
              title="Environment"
              entries={environments}
              canEdit={canEdit}
              loading={loading}
              emptyHint="No environments yet."
              onCreate={async (input) => { await taxonomyApi.createEnvironment(input); await loadAll(); }}
              onUpdate={async (id, input) => { await taxonomyApi.updateEnvironment(id, input); await loadAll(); }}
              onDeactivate={async (id) => { await taxonomyApi.deactivateEnvironment(id); await loadAll(); }}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
