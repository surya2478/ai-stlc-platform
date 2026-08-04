"use client";

import { useMemo, useState } from "react";
import { Search, Filter, ChevronRight, Sparkles, ShieldCheck, Radar, AlertTriangle, Crosshair } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ScriptQualitySignals } from "@/lib/api";

export type InventoryItem = {
  id: number;
  testCaseKey: string;
  title: string;
  module?: string | null;
  testSuiteId?: number | null;
  testSuiteName?: string | null;
  priority?: string | null;
  framework?: string | null;
  automationKind: "internal" | "external";
  externalTool?: string | null;
  scriptId?: number | null;
  scriptStatus?: string | null;
  externalStatus?: string | null;
  automationReady: boolean;
  lastUpdated?: string | null;
  quality?: ScriptQualitySignals | null;
  /** True when scriptStatus is "generated" and the Static Quality Gate
   * blocked it — that script will never reach dry run on its own (see
   * agent_tasks._build_dry_run_input, which only picks up "static_passed"
   * scripts) and needs a human to regenerate it. */
  staticGateFailed?: boolean;
  /** The registered application this test case targets, if it has been mapped
   * in Test Case Approval. Null means unmapped — generation still works and
   * falls back to the project's default application, but the test case cannot
   * be taken through Live Discovery Session at all. */
  applicationName?: string | null;
  /** Whether a published Application Model is what this test case's scripts
   * would actually be generated from:
   *   "published" — the published model is the locator source; intended path
   *   "none"      — it is not. Either no model is published, or one is but
   *                 grounds nothing, so generation falls back to the raw
   *                 locator_map. The strip above says which; the row only
   *                 needs to say it is not model-grounded.
   *   "unmapped"  — no application mapped, so there is nothing to ground against
   * Advisory only: nothing here blocks generation. */
  modelState?: "published" | "none" | "unmapped";
};

/** A short, specific reason this script's quality is in question despite its
 * lifecycle status — or null when there's nothing to flag. "Needs
 * regeneration" already gets its own status badge, so this only surfaces
 * the cases an "Approved" badge would otherwise hide: a script can be
 * approved and still carry an ungrounded locator or a known-failed dry run
 * the approval step never checked. */
function qualityFlag(item: InventoryItem): string | null {
  const q = item.quality;
  if (!q || q.needsRegeneration) return null;
  if (q.ungroundedElements.length > 0) return `${q.ungroundedElements.length} locator${q.ungroundedElements.length > 1 ? "s" : ""} ungrounded`;
  if (q.lastDryRunPassed === false) return "Last dry run failed";
  return null;
}

export type LifecycleFilter =
  | "all"
  | "not_created"
  | "ai_draft"
  | "draft"
  | "in_review"
  | "approved"
  | "verified"
  | "blocked"
  // Phase 2-4 grounded generation pipeline (ADR-001) statuses — see
  // LifecycleStepper's GROUNDED_STEPS for the same vocabulary.
  | "generated"
  | "static_gate_failed"
  | "static_gate_passed"
  | "dry_run_passed"
  | "reviewer_approved"
  | "lead_approved"
  | "ci_ready";

export type FrameworkFilter = "all" | "playwright" | "pytest" | "external";

type Props = {
  items: InventoryItem[];
  selectedId: number | null;
  onSelect: (item: InventoryItem) => void;
  selectedIds: Set<number>;
  onToggleSelect: (id: number) => void;
  onSelectMany: (ids: number[], checked: boolean) => void;
  onBulkGenerate: (ids: number[]) => void;
  onBulkApprove: (ids: number[]) => void;
  onBulkDiscover?: (ids: number[]) => void;
  bulkBusy?: boolean;
  bulkDiscoverBusy?: boolean;
};

function statusBadge(item: InventoryItem) {
  if (item.automationKind === "external") {
    if (item.automationReady) return { label: "Verified", variant: "success" as const };
    if (item.externalStatus === "automated") return { label: "Linked", variant: "info" as const };
    return { label: "Not linked", variant: "outline" as const };
  }
  const s = (item.scriptStatus ?? "").toLowerCase();
  if (s === "needs_regeneration") return { label: "Needs regeneration", variant: "destructive" as const };
  if (s === "approved") return { label: "Approved", variant: "success" as const };
  if (s === "in_review" || s === "pending_approval" || s === "under_review")
    return { label: "In review", variant: "warning" as const };
  if (s === "ai_draft") return { label: "AI Draft", variant: "purple" as const };
  if (s === "draft") return { label: "Draft", variant: "outline" as const };
  if (s === "rejected") return { label: "Rejected", variant: "destructive" as const };
  if (s === "deprecated") return { label: "Deprecated", variant: "secondary" as const };
  // Phase 2-4 grounded generation pipeline (ADR-001: contract -> compiler ->
  // static gate -> dry run -> staged human approval) — previously fell
  // through to "Not created" below, hiding real progress on scripts that
  // had actually compiled and run through the gate.
  if (s === "generated") {
    if (item.staticGateFailed) return { label: "Static gate failed", variant: "destructive" as const };
    return { label: "Generated", variant: "purple" as const };
  }
  if (s === "static_passed") return { label: "Static gate passed", variant: "purple" as const };
  if (s === "dry_run_passed") return { label: "Dry run passed", variant: "warning" as const };
  if (s === "reviewer_approved") return { label: "Reviewer approved", variant: "warning" as const };
  if (s === "lead_approved") return { label: "Lead approved", variant: "warning" as const };
  if (s === "ci_ready") return { label: "CI ready", variant: "success" as const };
  return { label: "Not created", variant: "outline" as const };
}

function frameworkLabel(item: InventoryItem): string {
  if (item.automationKind === "external") return item.externalTool ?? "External";
  return (item.framework ?? "—").replace(/^\w/, (c) => c.toUpperCase());
}

export function AutomationInventoryPanel({
  items,
  selectedId,
  onSelect,
  selectedIds,
  onToggleSelect,
  onSelectMany,
  onBulkGenerate,
  onBulkApprove,
  onBulkDiscover,
  bulkBusy,
  bulkDiscoverBusy,
}: Props) {
  const [search, setSearch] = useState("");
  const [framework, setFramework] = useState<FrameworkFilter>("all");
  const [lifecycle, setLifecycle] = useState<LifecycleFilter>("all");
  const [priority, setPriority] = useState<string>("all");
  const [expandedSuites, setExpandedSuites] = useState<Set<string>>(new Set());

  function toggleSuite(key: string) {
    setExpandedSuites((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const modules = useMemo(() => {
    const set = new Set<string>();
    items.forEach((i) => { if (i.module) set.add(i.module); });
    return Array.from(set).sort();
  }, [items]);
  const [module, setModule] = useState<string>("all");

  const priorities = useMemo(() => {
    const set = new Set<string>();
    items.forEach((i) => { if (i.priority) set.add(i.priority); });
    return Array.from(set);
  }, [items]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((item) => {
      if (q && !item.testCaseKey.toLowerCase().includes(q) && !item.title.toLowerCase().includes(q)) return false;
      if (framework !== "all") {
        if (framework === "external") {
          if (item.automationKind !== "external") return false;
        } else {
          if (item.automationKind === "external") return false;
          if ((item.framework ?? "").toLowerCase() !== framework) return false;
        }
      }
      if (module !== "all" && item.module !== module) return false;
      if (priority !== "all" && item.priority !== priority) return false;
      if (lifecycle !== "all") {
        const b = statusBadge(item).label.toLowerCase().replace(/\s+/g, "_");
        if (b !== lifecycle) return false;
      }
      return true;
    });
  }, [items, search, framework, module, priority, lifecycle]);

  const { suiteGroups, ungrouped } = useMemo(() => {
    const groups = new Map<string, { key: string; name: string; items: InventoryItem[] }>();
    const ungroupedItems: InventoryItem[] = [];
    for (const item of filtered) {
      if (item.testSuiteId != null) {
        const key = String(item.testSuiteId);
        const existing = groups.get(key);
        if (existing) existing.items.push(item);
        else groups.set(key, { key, name: item.testSuiteName || `Suite #${item.testSuiteId}`, items: [item] });
      } else {
        ungroupedItems.push(item);
      }
    }
    return {
      suiteGroups: Array.from(groups.values()).sort((a, b) => a.name.localeCompare(b.name)),
      ungrouped: ungroupedItems,
    };
  }, [filtered]);

  function renderRow(item: InventoryItem) {
    const badge = statusBadge(item);
    const flag = qualityFlag(item);
    const selected = item.id === selectedId;
    const checked = selectedIds.has(item.id);
    return (
      <div
        key={item.id}
        className={cn(
          "flex w-full items-start gap-2 border-b border-slate-50 px-3 py-2.5 text-left transition",
          selected ? "bg-violet-50/70" : "hover:bg-slate-50",
        )}
      >
        <input
          type="checkbox"
          checked={checked}
          onChange={() => onToggleSelect(item.id)}
          onClick={(e) => e.stopPropagation()}
          className="mt-1 h-3.5 w-3.5 shrink-0 accent-violet-600"
        />
        <button type="button" onClick={() => onSelect(item)} className="min-w-0 flex-1 text-left">
          <div className="flex items-center justify-between gap-2">
            <span className={cn("font-mono text-xs", selected ? "text-violet-700" : "text-[#1b59f8]")}>
              {item.testCaseKey}
            </span>
            <Badge variant={badge.variant} className="text-[10px]">{badge.label}</Badge>
          </div>
          <p className="mt-0.5 text-xs text-slate-700 line-clamp-1">{item.title}</p>
          <div className="mt-1 flex items-center gap-2 text-[10px] text-slate-400">
            <span>{frameworkLabel(item)}</span>
            {item.module && <><span>·</span><span>{item.module}</span></>}
            {item.priority && <><span>·</span><span>{item.priority}</span></>}
          </div>
          {flag && (
            <div className="mt-1 inline-flex items-center gap-1 rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
              <AlertTriangle className="h-2.5 w-2.5" />
              {flag}
            </div>
          )}
          {(item.modelState === "none" || item.modelState === "unmapped") && (
            <div className="mt-1 inline-flex items-center gap-1 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
              <Crosshair className="h-2.5 w-2.5" />
              {item.modelState === "unmapped" ? "No application mapped" : "Not model-grounded"}
            </div>
          )}
          {item.quality?.grounded && item.quality.ungroundedElements.length === 0 && (badge.label === "Approved") && (
            <div className="mt-1 inline-flex items-center gap-1 rounded-full bg-teal-50 px-1.5 py-0.5 text-[10px] font-medium text-teal-700">
              <Crosshair className="h-2.5 w-2.5" />
              Grounded
            </div>
          )}
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-100 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-bold text-slate-800">Automation inventory</p>
          <span className="text-[10px] text-slate-400">{filtered.length} / {items.length}</span>
        </div>

        {filtered.length > 0 && (
          <label className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <input
              type="checkbox"
              checked={filtered.length > 0 && filtered.every((i) => selectedIds.has(i.id))}
              onChange={(e) => onSelectMany(filtered.map((i) => i.id), e.target.checked)}
              className="h-3.5 w-3.5 accent-violet-600"
            />
            Select all filtered ({filtered.length})
          </label>
        )}

        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by ID or title…"
            className="w-full rounded-md border border-slate-200 bg-white py-1.5 pl-7 pr-2 text-xs focus:outline-none focus:ring-2 focus:ring-violet-500"
          />
        </div>

        <div className="flex gap-1.5 overflow-x-auto">
          {(["all", "playwright", "pytest", "external"] as FrameworkFilter[]).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFramework(f)}
              className={cn(
                "shrink-0 rounded-md px-2 py-1 text-[10px] font-semibold uppercase tracking-wider transition",
                framework === f
                  ? "bg-violet-100 text-violet-800"
                  : "bg-slate-50 text-slate-500 hover:bg-slate-100",
              )}
            >
              {f === "all" ? "All" : f}
            </button>
          ))}
        </div>

        <details className="text-[11px]">
          <summary className="flex cursor-pointer items-center gap-1 text-slate-500 hover:text-slate-800">
            <Filter className="h-3 w-3" />
            More filters
          </summary>
          <div className="mt-2 space-y-2">
            <FilterSelect
              label="Lifecycle"
              value={lifecycle}
              onChange={(v) => setLifecycle(v as LifecycleFilter)}
              options={[
                ["all", "All"],
                ["not_created", "Not created"],
                ["ai_draft", "AI Draft"],
                ["draft", "Draft"],
                ["in_review", "In review"],
                ["approved", "Approved"],
                ["verified", "Verified"],
                ["generated", "Generated"],
                ["static_gate_failed", "Static gate failed"],
                ["static_gate_passed", "Static gate passed"],
                ["dry_run_passed", "Dry run passed"],
                ["reviewer_approved", "Reviewer approved"],
                ["lead_approved", "Lead approved"],
                ["ci_ready", "CI ready"],
              ]}
            />
            <FilterSelect
              label="Module"
              value={module}
              onChange={setModule}
              options={[["all", "All"], ...modules.map((m) => [m, m] as [string, string])]}
            />
            <FilterSelect
              label="Priority"
              value={priority}
              onChange={setPriority}
              options={[["all", "All"], ...priorities.map((p) => [p, p] as [string, string])]}
            />
          </div>
        </details>
      </div>

      {selectedIds.size > 0 && (
        <div className="flex items-center justify-between gap-2 border-b border-violet-100 bg-violet-50/60 px-3 py-2">
          <span className="text-[11px] font-semibold text-violet-800">{selectedIds.size} selected</span>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => onSelectMany(Array.from(selectedIds), false)}
              className="text-[11px] text-slate-500 hover:text-slate-800"
            >
              Clear
            </button>
            {onBulkDiscover && (
              <button
                type="button"
                disabled={bulkDiscoverBusy}
                onClick={() => onBulkDiscover(Array.from(selectedIds))}
                title="Ground automation in the real page: opens a live browser session and captures real locators before you generate scripts."
                className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-2 py-1 text-[11px] font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
              >
                <Radar className="h-3 w-3" />
                Discover UI
              </button>
            )}
            <button
              type="button"
              disabled={bulkBusy}
              onClick={() => onBulkGenerate(Array.from(selectedIds))}
              className="inline-flex items-center gap-1 rounded-md bg-violet-600 px-2 py-1 text-[11px] font-semibold text-white transition hover:bg-violet-700 disabled:opacity-50"
            >
              <Sparkles className="h-3 w-3" />
              Generate
            </button>
            <button
              type="button"
              disabled={bulkBusy}
              onClick={() => onBulkApprove(Array.from(selectedIds))}
              className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2 py-1 text-[11px] font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-50"
            >
              <ShieldCheck className="h-3 w-3" />
              Approve
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="flex h-32 items-center justify-center px-4 text-center text-[11px] text-slate-400">
            No items match the current filters.
          </div>
        ) : (
          <>
            {suiteGroups.map((group) => {
              const collapsed = !expandedSuites.has(group.key);
              return (
                <div key={group.key} className="border-b border-slate-100">
                  <div className="flex w-full items-center gap-2 bg-slate-50 px-3 py-2 hover:bg-slate-100">
                    <input
                      type="checkbox"
                      checked={group.items.every((i) => selectedIds.has(i.id))}
                      onChange={(e) => onSelectMany(group.items.map((i) => i.id), e.target.checked)}
                      className="h-3.5 w-3.5 shrink-0 accent-violet-600"
                    />
                    <button
                      type="button"
                      onClick={() => toggleSuite(group.key)}
                      className="flex flex-1 items-center justify-between gap-2 text-left"
                    >
                      <span className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-600">
                        <ChevronRight className={cn("h-3 w-3 shrink-0 transition-transform", !collapsed && "rotate-90")} />
                        <span className="line-clamp-1">{group.name}</span>
                      </span>
                      <span className="shrink-0 text-[10px] text-slate-400">{group.items.length}</span>
                    </button>
                  </div>
                  {!collapsed && group.items.map((item) => renderRow(item))}
                </div>
              );
            })}
            {ungrouped.map((item) => renderRow(item))}
          </>
        )}
      </div>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="flex items-center justify-between gap-2 text-[11px] text-slate-600">
      <span className="font-semibold">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="flex-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] focus:outline-none focus:ring-2 focus:ring-violet-500"
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>{l}</option>
        ))}
      </select>
    </label>
  );
}
