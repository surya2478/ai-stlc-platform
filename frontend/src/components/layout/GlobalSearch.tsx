"use client";

/**
 * Command palette for the header's search button.
 *
 * There is no global search endpoint on the backend — the only server-side
 * search is RAG, which is semantic search over indexed *documents*, not over
 * requirements, test cases and defects. So this queries the list endpoints
 * that already exist for the selected project and filters their results in the
 * browser.
 *
 * That has a real limit worth stating rather than hiding: those endpoints
 * return their first page (100 rows for test cases), so this searches what
 * they return, not the whole project. The footer says so when a result set is
 * capped, because a search box that silently misses rows is worse than one
 * that admits its range.
 *
 * Destinations are matched too, so it doubles as a "jump to page" palette and
 * is useful even with no project selected.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Search, Loader2, FileText, TestTube2, Bug, Compass, CornerDownLeft,
} from "lucide-react";
import {
  requirementsApi, testCasesApi, defectsApi,
  type Requirement, type TestCase, type DefectDraft,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type Hit = {
  id: string;
  kind: "Requirement" | "Test Case" | "Defect" | "Go to";
  code: string;
  title: string;
  href: string;
};

/** Every real route in the app shell, so the palette can navigate as well as
 *  search. Kept in step with the sidebar by hand — there are only a dozen. */
const DESTINATIONS: Array<{ label: string; href: string }> = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Command Centre", href: "/autonomous-lab/missions" },
  { label: "Requirements", href: "/requirements" },
  { label: "Test Planning & Scenarios", href: "/test-planning" },
  { label: "Test Cases", href: "/test-cases" },
  { label: "Applications", href: "/applications" },
  { label: "AI Automation Studio", href: "/automation" },
  { label: "Playwright AI Studio", href: "/playwright-studio" },
  { label: "Manual Execution", href: "/execution/manual" },
  { label: "Automation Execution", href: "/execution/automation" },
  { label: "Execution Dashboard", href: "/execution/dashboard" },
  { label: "Defects", href: "/defects" },
  { label: "Reports", href: "/reports" },
  { label: "Test Data", href: "/test-data" },
  { label: "AI Agents", href: "/agents" },
  { label: "Taxonomy", href: "/taxonomy" },
  { label: "Project Settings", href: "/settings" },
  { label: "Users & Roles", href: "/users" },
];

const ICONS = {
  Requirement: FileText,
  "Test Case": TestTube2,
  Defect: Bug,
  "Go to": Compass,
} as const;

export function GlobalSearch({
  open,
  onClose,
  projectId,
}: {
  open: boolean;
  onClose: () => void;
  projectId: number | null;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [defects, setDefects] = useState<DefectDraft[]>([]);
  const [capped, setCapped] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load once per open, not per keystroke — the list endpoints are not search
  // endpoints and re-fetching on every character would hammer them.
  useEffect(() => {
    if (!open || !projectId) return;
    let cancelled = false;
    setLoading(true);
    Promise.allSettled([
      requirementsApi.list(projectId),
      testCasesApi.list(projectId),
      defectsApi.list(projectId),
    ])
      .then(([r, tc, d]) => {
        if (cancelled) return;
        const reqs = r.status === "fulfilled" ? r.value.data ?? [] : [];
        const cases = tc.status === "fulfilled" ? tc.value.data ?? [] : [];
        const defs = d.status === "fulfilled" ? d.value.data ?? [] : [];
        setRequirements(reqs);
        setTestCases(cases);
        setDefects(defs);
        // The list endpoints page at 100; hitting it exactly means there are
        // almost certainly rows this palette cannot see.
        setCapped(reqs.length >= 100 || cases.length >= 100 || defs.length >= 100);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, projectId]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
      // Autofocus after the overlay paints.
      const t = setTimeout(() => inputRef.current?.focus(), 20);
      return () => clearTimeout(t);
    }
  }, [open]);

  const withProject = useCallback(
    (href: string) => (projectId ? `${href}${href.includes("?") ? "&" : "?"}project=${projectId}` : href),
    [projectId],
  );

  const hits = useMemo<Hit[]>(() => {
    const term = query.trim().toLowerCase();
    if (!term) {
      return DESTINATIONS.slice(0, 8).map((d) => ({
        id: `dest-${d.href}`, kind: "Go to", code: "", title: d.label, href: withProject(d.href),
      }));
    }
    const matches = (...values: Array<string | null | undefined>) =>
      values.some((v) => (v ?? "").toLowerCase().includes(term));

    const out: Hit[] = [];
    for (const d of DESTINATIONS) {
      if (matches(d.label)) {
        out.push({ id: `dest-${d.href}`, kind: "Go to", code: "", title: d.label, href: withProject(d.href) });
      }
    }
    for (const r of requirements) {
      if (matches(r.requirement_id, r.title)) {
        out.push({
          id: `req-${r.id}`, kind: "Requirement", code: r.requirement_id, title: r.title,
          href: withProject(`/requirements?view=intake&requirement=${r.id}`),
        });
      }
    }
    for (const tc of testCases) {
      if (matches(tc.test_case_id, tc.title)) {
        out.push({
          id: `tc-${tc.id}`, kind: "Test Case", code: tc.test_case_id, title: tc.title,
          href: withProject(`/test-cases?view=editor&case=${tc.id}`),
        });
      }
    }
    for (const d of defects) {
      if (matches(d.defect_id, d.summary)) {
        out.push({
          id: `def-${d.id}`, kind: "Defect", code: d.defect_id, title: d.summary,
          href: withProject("/defects"),
        });
      }
    }
    return out.slice(0, 40);
  }, [query, requirements, testCases, defects, withProject]);

  useEffect(() => { setActiveIndex(0); }, [query]);

  const go = useCallback((hit: Hit) => {
    onClose();
    router.push(hit.href);
  }, [onClose, router]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); setActiveIndex((i) => Math.min(i + 1, hits.length - 1)); }
      if (e.key === "ArrowUp") { e.preventDefault(); setActiveIndex((i) => Math.max(i - 1, 0)); }
      if (e.key === "Enter" && hits[activeIndex]) { e.preventDefault(); go(hits[activeIndex]); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, hits, activeIndex, go, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[12vh]" onClick={onClose}>
      <div
        className="w-full max-w-xl overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-slate-100 px-3.5 py-2.5">
          <Search className="h-4 w-4 shrink-0 text-slate-400" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={projectId ? "Search requirements, test cases, defects, or jump to a page…" : "Jump to a page…"}
            aria-label="Search"
            className="flex-1 bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400"
          />
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />}
          <kbd className="rounded border border-slate-200 px-1.5 py-0.5 text-[9px] font-semibold text-slate-400">ESC</kbd>
        </div>

        <div className="max-h-[50vh] overflow-y-auto py-1">
          {hits.length === 0 ? (
            <p className="px-4 py-8 text-center text-xs font-medium text-slate-400">
              No matches for “{query.trim()}”.
            </p>
          ) : (
            hits.map((hit, index) => {
              const Icon = ICONS[hit.kind];
              return (
                <button
                  key={hit.id}
                  type="button"
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => go(hit)}
                  className={cn(
                    "flex w-full items-center gap-2.5 px-4 py-2 text-left transition-colors",
                    index === activeIndex ? "bg-blue-50" : "hover:bg-slate-50",
                  )}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-semibold text-slate-800">
                      {hit.code && <span className="mr-1.5 font-mono text-[10px] text-[#1b59f8]">{hit.code}</span>}
                      {hit.title}
                    </p>
                  </div>
                  <span className="shrink-0 text-[9px] font-bold uppercase tracking-wider text-slate-400">{hit.kind}</span>
                  {index === activeIndex && <CornerDownLeft className="h-3 w-3 shrink-0 text-slate-400" />}
                </button>
              );
            })
          )}
        </div>

        <div className="border-t border-slate-100 px-4 py-2">
          <p className="text-[10px] font-medium text-slate-400">
            {!projectId
              ? "Select a project to search its requirements, test cases and defects."
              : capped
                ? "Searching the most recent 100 of each type — there are more in this project than this palette can reach."
                : `Searching ${requirements.length} requirements · ${testCases.length} test cases · ${defects.length} defects`}
          </p>
        </div>
      </div>
    </div>
  );
}
