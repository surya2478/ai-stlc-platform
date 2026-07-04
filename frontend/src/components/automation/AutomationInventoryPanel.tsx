"use client";

import { useMemo, useState } from "react";
import { Search, Filter } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type InventoryItem = {
  id: number;
  testCaseKey: string;
  title: string;
  module?: string | null;
  priority?: string | null;
  framework?: string | null;
  automationKind: "internal" | "external";
  externalTool?: string | null;
  scriptStatus?: string | null;
  externalStatus?: string | null;
  automationReady: boolean;
  lastUpdated?: string | null;
};

export type LifecycleFilter =
  | "all"
  | "not_created"
  | "ai_draft"
  | "draft"
  | "in_review"
  | "approved"
  | "verified"
  | "blocked";

export type FrameworkFilter = "all" | "playwright" | "pytest" | "external";

type Props = {
  items: InventoryItem[];
  selectedId: number | null;
  onSelect: (item: InventoryItem) => void;
};

function statusBadge(item: InventoryItem) {
  if (item.automationKind === "external") {
    if (item.automationReady) return { label: "Verified", variant: "success" as const };
    if (item.externalStatus === "automated") return { label: "Linked", variant: "info" as const };
    return { label: "Not linked", variant: "outline" as const };
  }
  const s = (item.scriptStatus ?? "").toLowerCase();
  if (s === "approved") return { label: "Approved", variant: "success" as const };
  if (s === "in_review" || s === "pending_approval" || s === "under_review")
    return { label: "In review", variant: "warning" as const };
  if (s === "ai_draft") return { label: "AI Draft", variant: "purple" as const };
  if (s === "draft") return { label: "Draft", variant: "outline" as const };
  if (s === "rejected") return { label: "Rejected", variant: "destructive" as const };
  if (s === "deprecated") return { label: "Deprecated", variant: "secondary" as const };
  return { label: "Not created", variant: "outline" as const };
}

function frameworkLabel(item: InventoryItem): string {
  if (item.automationKind === "external") return item.externalTool ?? "External";
  return (item.framework ?? "—").replace(/^\w/, (c) => c.toUpperCase());
}

export function AutomationInventoryPanel({ items, selectedId, onSelect }: Props) {
  const [search, setSearch] = useState("");
  const [framework, setFramework] = useState<FrameworkFilter>("all");
  const [lifecycle, setLifecycle] = useState<LifecycleFilter>("all");
  const [priority, setPriority] = useState<string>("all");

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

  return (
    <div className="flex h-full flex-col rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-100 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-bold text-slate-800">Automation inventory</p>
          <span className="text-[10px] text-slate-400">{filtered.length} / {items.length}</span>
        </div>

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

      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="flex h-32 items-center justify-center px-4 text-center text-[11px] text-slate-400">
            No items match the current filters.
          </div>
        ) : (
          filtered.map((item) => {
            const badge = statusBadge(item);
            const selected = item.id === selectedId;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelect(item)}
                className={cn(
                  "block w-full border-b border-slate-50 px-3 py-2.5 text-left transition",
                  selected ? "bg-violet-50/70" : "hover:bg-slate-50",
                )}
              >
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
              </button>
            );
          })
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
