"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";

/**
 * One tab bar across the four Applications screens.
 *
 * These were four separate sidebar entries, three of which were already
 * `/applications?view=…` while Live Discovery Session sat under `/automation`
 * beside the Automation Studio screens. Splitting them hid the fact that they
 * are one workflow over one subject: register the app, observe it, structure
 * what was observed, inspect its traffic.
 *
 * Matches the tab pattern Requirements and Test Design already use, so the
 * three governed workspaces behave the same way.
 */

export type ApplicationsView = "registry" | "discovery" | "model" | "api-network";

const TABS: { view: ApplicationsView; label: string; ui: string }[] = [
  { view: "registry", label: "Application Registry", ui: "UI-014" },
  { view: "discovery", label: "Live Discovery Session", ui: "UI-015" },
  { view: "model", label: "Application Model", ui: "UI-016" },
  { view: "api-network", label: "API & Network Explorer", ui: "UI-017" },
];

export function applicationsHref(view: ApplicationsView, projectId: number | null): string {
  const params = new URLSearchParams();
  // "registry" is the default view, so it is expressed by the absence of the
  // parameter rather than by `view=registry` — keeps the canonical URL for the
  // section short and matches what the sidebar has always linked to.
  if (view !== "registry") params.set("view", view);
  if (projectId) params.set("project", String(projectId));
  const query = params.toString();
  return query ? `/applications?${query}` : "/applications";
}

export function ApplicationsTabs({
  active,
  projectId,
}: {
  active: ApplicationsView;
  projectId: number | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1 rounded-xl border border-gray-200 bg-white p-1.5 shadow-sm">
      {TABS.map((tab) => (
        <Link
          key={tab.view}
          href={applicationsHref(tab.view, projectId)}
          className={cn(
            "rounded-lg px-4 py-2 text-xs font-bold shadow-sm transition-all",
            active === tab.view ? "bg-[#B71920] text-white" : "text-gray-500 hover:text-gray-900",
          )}
        >
          {tab.label} <span className="ml-1 text-[9px] opacity-75">{tab.ui}</span>
        </Link>
      ))}
    </div>
  );
}
