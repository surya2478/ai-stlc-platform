"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import {
  testAutomationStudioApi,
  type TasDiscoveredElement,
  type TasDiscoveryRun,
} from "@/lib/api";
import { EmptyState, SideDrawer } from "./shared";

/** What the crawl found, and — when it found nothing useful — why.
 *
 *  This is the answer to "my test case says it can't find the Login button".
 *  It shows the real accessible names on the real pages, so a mismatch between
 *  what the document called a control and what the application calls it stops
 *  being a mystery.
 */
export function DiscoveryDrawer({
  batchId,
  run,
  onClose,
}: {
  batchId: number;
  run: TasDiscoveryRun;
  onClose: () => void;
}) {
  const { toast } = useToast();
  const [elements, setElements] = useState<TasDiscoveredElement[] | null>(null);
  const [pageFilter, setPageFilter] = useState<string>("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    testAutomationStudioApi
      .listDiscoveredElements(batchId)
      .then((response) => {
        if (!cancelled) setElements(response.data);
      })
      .catch((error) => {
        if (cancelled) return;
        setElements([]);
        toast({
          title: "Could not load the discovered elements",
          description:
            (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
            "Please try again.",
          variant: "error",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [batchId, toast]);

  const pages = useMemo(() => {
    const seen = new Map<string, number>();
    for (const element of elements ?? []) {
      seen.set(element.page_url, (seen.get(element.page_url) ?? 0) + 1);
    }
    return [...seen.entries()];
  }, [elements]);

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (elements ?? []).filter((element) => {
      if (pageFilter && element.page_url !== pageFilter) return false;
      if (!needle) return true;
      return (
        element.element_name.toLowerCase().includes(needle) ||
        (element.accessible_name ?? "").toLowerCase().includes(needle) ||
        (element.business_meaning ?? "").toLowerCase().includes(needle) ||
        (element.role ?? "").toLowerCase().includes(needle)
      );
    });
  }, [elements, pageFilter, search]);

  return (
    <SideDrawer
      title="Application discovery"
      subtitle={run.application_url ?? undefined}
      onClose={onClose}
      footer={
        <Button size="sm" variant="outline" onClick={onClose}>
          Close
        </Button>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Status" value={run.status} />
          <Stat label="Pages" value={String(run.pages_discovered)} />
          <Stat label="Elements" value={String(run.elements_discovered)} />
          <Stat label="Run" value={`v${run.version}`} />
        </div>

        {/* Sign-in is called out separately from the run status on purpose: a
            crawl that never got past the login page reports "completed" and a
            healthy-looking element count, all of it from the wrong page. */}
        {run.auth_mode === "form" && (
          <div
            className={
              run.auth_status === "succeeded"
                ? "flex gap-2 rounded-lg border border-emerald-200 bg-emerald-50/70 px-3 py-2"
                : "flex gap-2 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2"
            }
          >
            {run.auth_status === "succeeded" ? (
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
            ) : (
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            )}
            <div className="min-w-0 text-xs">
              <p className="font-semibold text-gray-900">
                {run.auth_status === "succeeded" ? "Signed in" : "Sign-in did not complete"}
              </p>
              {run.auth_detail && <p className="mt-0.5 text-gray-600">{run.auth_detail}</p>}
              {run.auth_status !== "succeeded" && (
                <p className="mt-1 text-gray-600">
                  Everything below was captured without signing in, so it is most likely the login
                  page rather than the application.
                </p>
              )}
            </div>
          </div>
        )}

        {run.error && (
          <div className="flex gap-2 rounded-lg border border-red-200 bg-red-50/70 px-3 py-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
            <p className="min-w-0 break-words text-xs text-red-800">{run.error}</p>
          </div>
        )}

        {run.blockers.length > 0 && (
          <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2">
            <p className="text-xs font-semibold text-amber-900">
              The environment was not ready, so no browser was opened
            </p>
            <ul className="mt-1 space-y-1">
              {run.blockers.map((blocker, index) => (
                <li key={`${blocker.name}-${index}`} className="text-[11px] text-amber-800">
                  <span className="font-medium">{blocker.name}</span>
                  {blocker.detail ? ` — ${blocker.detail}` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}

        {run.explored_pages.length > 0 && (
          <div>
            <p className="mb-1.5 text-xs font-semibold text-gray-900">Pages crawled</p>
            <ul className="space-y-1">
              {run.explored_pages.map((page, index) => (
                <li
                  key={`${page.url}-${index}`}
                  className="flex items-baseline justify-between gap-3 rounded border border-gray-100 px-2 py-1"
                >
                  <span className="min-w-0 truncate text-[11px] text-gray-700" title={page.url}>
                    {page.title || page.url}
                  </span>
                  <span className="shrink-0 text-[11px] tabular-nums text-gray-500">
                    {page.element_count ?? 0} elements
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <p className="text-xs font-semibold text-gray-900">Discovered elements</p>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter by name, role or meaning"
              className="h-7 flex-1 min-w-[12rem] rounded-lg border border-gray-200 px-2 text-xs"
            />
            {pages.length > 1 && (
              <select
                value={pageFilter}
                onChange={(event) => setPageFilter(event.target.value)}
                className="h-7 max-w-[14rem] rounded-lg border border-gray-200 bg-white px-2 text-xs"
              >
                <option value="">All pages</option>
                {pages.map(([url, count]) => (
                  <option key={url} value={url}>
                    {url} ({count})
                  </option>
                ))}
              </select>
            )}
          </div>

          {elements === null ? (
            <div className="flex items-center gap-2 py-8 text-xs text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading elements...
            </div>
          ) : visible.length === 0 ? (
            <EmptyState
              title="No elements to show"
              description={
                (elements?.length ?? 0) === 0
                  ? "This run captured no interactive elements. The page may require sign-in, or it may render its controls without accessible names."
                  : "No discovered element matches this filter."
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[11px]">
                <thead className="border-b border-gray-200 text-gray-500">
                  <tr>
                    <th className="py-1.5 pr-3 font-medium">Element</th>
                    <th className="py-1.5 pr-3 font-medium">Role</th>
                    <th className="py-1.5 pr-3 font-medium">Locator</th>
                    <th className="py-1.5 pr-3 text-right font-medium">Conf.</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {visible.map((element) => (
                    <tr key={element.id} className="align-top">
                      <td className="py-1.5 pr-3">
                        <p className="font-medium text-gray-900">{element.element_name}</p>
                        {element.accessible_name && (
                          <p className="text-gray-600">&ldquo;{element.accessible_name}&rdquo;</p>
                        )}
                        {element.business_meaning && (
                          <p className="text-gray-500">{element.business_meaning}</p>
                        )}
                      </td>
                      <td className="py-1.5 pr-3">
                        <Badge variant="outline">{element.role ?? "—"}</Badge>
                      </td>
                      <td className="py-1.5 pr-3">
                        <code className="break-all font-mono text-[10px] text-gray-700">
                          {element.recommended_locator}
                        </code>
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums text-gray-600">
                        {element.confidence_score}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </SideDrawer>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-200 px-2.5 py-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-0.5 truncate text-sm font-bold capitalize text-gray-900">{value}</p>
    </div>
  );
}
