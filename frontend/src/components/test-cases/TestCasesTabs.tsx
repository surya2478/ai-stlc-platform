"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";

/**
 * One tab bar across the four Test Design screens.
 *
 * These were four separate sidebar entries pointing at four `view` values of
 * the same `/test-cases` page, with no in-page navigation between them — so
 * moving from a generated case to its approval meant going back to the sidebar.
 *
 * Mirrors ApplicationsTabs and the Requirements workspace tabs, so the three
 * governed workspaces navigate identically.
 */

export type TestCasesView = "generated" | "editor" | "approval" | "journey-graph";

const TABS: { view: TestCasesView; label: string; ui: string }[] = [
  { view: "generated", label: "Test Cases", ui: "UI-010" },
  { view: "editor", label: "Test Editor", ui: "UI-011" },
  { view: "approval", label: "Test Case Approval", ui: "UI-012" },
  { view: "journey-graph", label: "Journey Graph", ui: "UI-013" },
];

export function testCasesHref(view: TestCasesView, projectId: number | string | null): string {
  const params = new URLSearchParams();
  // "generated" is the default the page falls back to, so it is expressed by
  // the absence of the parameter — keeps the canonical URL short.
  if (view !== "generated") params.set("view", view);
  if (projectId) params.set("project", String(projectId));
  const query = params.toString();
  return query ? `/test-cases?${query}` : "/test-cases";
}

export function TestCasesTabs({
  active,
  projectId,
}: {
  active: TestCasesView;
  projectId: number | string | null;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-1 rounded-xl border border-slate-200 bg-white p-1.5 shadow-sm">
      {TABS.map((tab) => (
        <Link
          key={tab.view}
          href={testCasesHref(tab.view, projectId)}
          className={cn(
            "rounded-lg px-4 py-2 text-xs font-bold shadow-sm transition-all",
            active === tab.view ? "bg-[#1b59f8] text-white" : "text-slate-500 hover:text-slate-900",
          )}
        >
          {tab.label} <span className="ml-1 text-[9px] opacity-75">{tab.ui}</span>
        </Link>
      ))}
    </div>
  );
}
