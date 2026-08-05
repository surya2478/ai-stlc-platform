"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight, Bug, ClipboardList, Code2, Crosshair, FileText, GitBranch,
  ListChecks, Network, Play, Table2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { traceabilityApi, type LineageNode } from "@/lib/api";
import {
  Drawer, DrawerBody, DrawerContent, DrawerDescription, DrawerHeader, DrawerTitle,
} from "@/components/ui/drawer";
import { Badge } from "@/components/ui/badge";
import { buildHref, ExecutionStatusBadge, LoadingSkeleton } from "./execution-shared";

export interface TraceTarget {
  entityType: string;
  entityId: number;
  label?: string;
}

const TYPE_META: Record<string, { label: string; icon: typeof FileText; href?: (projectId: string | null) => string }> = {
  requirement:       { label: "Requirement", icon: FileText, href: (p) => buildHref("/requirements", { project: p }) },
  test_plan:         { label: "Test Plan", icon: ClipboardList, href: (p) => buildHref("/test-planning", { project: p }) },
  test_scenario:     { label: "Scenario", icon: ListChecks, href: (p) => buildHref("/test-planning", { project: p }) },
  test_case:         { label: "Test Case", icon: Table2, href: (p) => buildHref("/test-cases", { project: p }) },
  test_data:         { label: "Test Data", icon: Table2, href: (p) => buildHref("/test-data", { project: p }) },
  automation_script: { label: "Script", icon: Code2, href: (p) => buildHref("/automation", { project: p }) },
  locator_map:       { label: "Discovered Locator", icon: Crosshair },
  execution_run:     { label: "Run", icon: Play, href: (p) => buildHref("/execution/automation", { project: p, tab: "history" }) },
  execution_result:  { label: "Result", icon: Play },
  defect_draft:      { label: "Defect", icon: Bug, href: (p) => buildHref("/defects", { project: p }) },
  report:            { label: "Report", icon: FileText, href: (p) => buildHref("/reports", { project: p }) },
};

function NodeCard({ node, projectId }: { node: LineageNode; projectId: string | null }) {
  const meta = TYPE_META[node.entity_type] ?? { label: node.entity_type.replace(/_/g, " "), icon: GitBranch };
  const Icon = meta.icon;
  const href = meta.href?.(projectId);
  const body = (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-3 py-2.5",
        href && "transition-colors hover:border-app-brand-200 hover:bg-app-brand-75/40",
      )}
    >
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-50 ring-1 ring-gray-100">
        <Icon className="h-4 w-4 text-gray-500" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">{meta.label}</span>
          {node.ref && <span className="truncate font-mono text-[11px] text-[#B71920]">{node.ref}</span>}
        </div>
        <p className="truncate text-xs font-medium text-gray-800">{node.title ?? `#${node.entity_id}`}</p>
      </div>
      {node.status && <ExecutionStatusBadge status={node.status} className="shrink-0 text-[10px]" />}
      {href && <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-gray-300" />}
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

function ChainConnector() {
  return <div className="ml-7 h-3 w-px bg-gray-200" aria-hidden />;
}

/**
 * Vertical Requirement → … → Result chain for any STLC artifact, read from
 * the artifact_lineage table. Each node deep-links to its owning module.
 */
export function TraceabilityDrawer({
  target,
  onClose,
}: {
  target: TraceTarget | null;
  onClose: () => void;
}) {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");

  const query = useQuery({
    queryKey: ["traceability", "lineage", target?.entityType, target?.entityId],
    queryFn: async () =>
      (await traceabilityApi.getLineage(target!.entityType, target!.entityId)).data,
    enabled: target !== null,
  });

  const chain = query.data;
  const selfMeta = target ? TYPE_META[target.entityType] : null;

  const upstream = useMemo(() => chain?.upstream ?? [], [chain]);
  const downstream = useMemo(() => chain?.downstream ?? [], [chain]);

  return (
    <Drawer open={target !== null} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DrawerContent size="lg">
        <DrawerHeader>
          <div>
            <DrawerTitle className="flex items-center gap-2">
              <Network className="h-4 w-4 text-[#B71920]" /> Traceability chain
            </DrawerTitle>
            <DrawerDescription>
              {target?.label ?? `${selfMeta?.label ?? target?.entityType} #${target?.entityId}`} — upstream origins and downstream outcomes
            </DrawerDescription>
          </div>
        </DrawerHeader>
        <DrawerBody>
          {query.isLoading && <LoadingSkeleton rows={5} />}

          {query.isError && (
            <p className="rounded-lg border border-red-100 bg-red-50 p-3 text-xs text-red-600">
              Could not load the lineage chain. The artifact may have been deleted.
            </p>
          )}

          {chain && (
            <>
              <section>
                <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                  Upstream — where this came from
                </h3>
                {upstream.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-gray-200 p-3 text-center text-[11px] text-gray-400">
                    No upstream links recorded. Artifacts created before lineage tracking won&apos;t have them.
                  </p>
                ) : (
                  <div>
                    {upstream.map((node, i) => (
                      <div key={`${node.entity_type}-${node.entity_id}`}>
                        {i > 0 && <ChainConnector />}
                        <NodeCard node={node} projectId={projectId} />
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {/* The artifact itself */}
              <div className="flex items-center gap-2 rounded-lg border-2 border-app-brand-200 bg-app-brand-75/50 px-3 py-2.5">
                <Badge variant="info" className="text-[10px]">This artifact</Badge>
                <span className="truncate text-xs font-semibold text-gray-800">
                  {target?.label ?? `${selfMeta?.label ?? target?.entityType} #${target?.entityId}`}
                </span>
              </div>

              <section>
                <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                  Downstream — what this produced
                </h3>
                {downstream.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-gray-200 p-3 text-center text-[11px] text-gray-400">
                    Nothing downstream yet.
                  </p>
                ) : (
                  <div>
                    {downstream.map((node, i) => (
                      <div key={`${node.entity_type}-${node.entity_id}`}>
                        {i > 0 && <ChainConnector />}
                        <NodeCard node={node} projectId={projectId} />
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
