// UI-020/021/023 — the Automation Asset Workspace landing page.
//
// The workspace itself opens on one suite member, so a navigation entry needs
// somewhere to land. This is that list. It also serves as the aging queue from
// contract Section 16: deferred human review is only safe when the backlog of
// AI-approved-but-unreviewed assets is a visible number rather than an
// invisible pile.

"use client";

import { useCallback, useEffect, useState } from "react";
import { Layers3, Loader2, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  automationAssetListApi,
  type AutomationAssetListing,
  type AutomationAssetRow,
} from "@/lib/api";

import { EmptyRow, messageFromError, Panel, SuiteStatusBadge } from "./suite-shared";

function AutonomyCell({ row }: { row: AutomationAssetRow }) {
  if (row.approval_state === "FINAL_APPROVED") {
    return <Badge variant="success" className="text-[9px]">Final Approved</Badge>;
  }
  if (row.approval_state === "REJECTED") {
    return <Badge variant="destructive" className="text-[9px]">Rejected</Badge>;
  }
  if (row.autonomy_state === "AI_APPROVED") {
    return <Badge variant="info" className="text-[9px]">AI Approved · awaiting review</Badge>;
  }
  if (row.autonomy_state === "AI_HELD") {
    return <Badge variant="warning" className="text-[9px]">AI Held</Badge>;
  }
  return <Badge variant="secondary" className="text-[9px]">Not evaluated</Badge>;
}

function Count({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className={cn("rounded-lg border p-2.5", tone)}>
      <p className="text-[9px] font-semibold uppercase tracking-wide opacity-70">{label}</p>
      <p className="text-[18px] font-bold">{value}</p>
    </div>
  );
}

export function AutomationAssetPicker({
  projectId,
  onOpen,
}: {
  projectId: number;
  onOpen: (memberId: number) => void;
}) {
  const [data, setData] = useState<AutomationAssetListing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await automationAssetListApi.list(projectId);
      setData(res.data);
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !data) {
    return (
      <div className="flex items-center gap-2 p-6 text-[12px] text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading automation assets…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-[12px] text-red-800">
        {error}
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center gap-3">
        <div className="rounded-xl border border-blue-100 bg-blue-50 p-2.5">
          <Layers3 className="h-6 w-6 text-[#1b59f8]" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-slate-900">Automation Assets</h1>
          <p className="mt-1 text-xs text-slate-500">
            Behaviour, code and review for one test case. Open an asset to work on it.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Count label="Total assets" value={data.counts.total} tone="border-slate-200 bg-white text-slate-800" />
        <Count label="AI Held" value={data.counts.ai_held} tone="border-amber-200 bg-amber-50 text-amber-900" />
        <Count
          label="Awaiting final approval"
          value={data.counts.pending_final_approval}
          tone="border-blue-200 bg-blue-50 text-blue-800"
        />
        <Count
          label="Final approved"
          value={data.counts.final_approved}
          tone="border-emerald-200 bg-emerald-50 text-emerald-800"
        />
      </div>

      {data.counts.pending_final_approval > 0 ? (
        <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 p-2.5 text-[11px] text-blue-900">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            {data.counts.pending_final_approval} asset
            {data.counts.pending_final_approval === 1 ? " has" : "s have"} been AI-approved and
            {data.counts.pending_final_approval === 1 ? " is" : " are"} awaiting a human final
            approval. None of them can be published until that is recorded.
          </span>
        </div>
      ) : null}

      <Panel title={`Assets (${data.assets.length})`}>
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-left text-[9px] uppercase text-slate-400">
              <th className="py-1">Test case</th>
              <th>Suite</th>
              <th>Framework</th>
              <th>Compiled</th>
              <th>State</th>
              <th className="text-right">Open</th>
            </tr>
          </thead>
          <tbody>
            {data.assets.map((row) => (
              <tr
                key={row.member_id}
                className={cn(
                  "border-b border-slate-50 hover:bg-slate-50",
                  row.inclusion_status === "excluded" && "opacity-50",
                )}
              >
                <td className="py-1.5">
                  <span className="font-medium text-slate-800">
                    {row.test_case_display_id ?? `TC-${row.test_case_id}`}
                  </span>
                  <span className="ml-1 text-slate-500">{row.test_case_title}</span>
                </td>
                <td className="text-slate-600">
                  {row.suite_name} <SuiteStatusBadge status={row.suite_status} />
                </td>
                {/* Absent values render as an explained dash, never a zero. */}
                <td className="text-slate-600" title={row.framework ? undefined : "No linked script, so no framework resolves."}>
                  {row.framework ?? "—"}
                </td>
                <td className="text-slate-600">{row.has_script ? "Yes" : "No"}</td>
                <td>
                  <AutonomyCell row={row} />
                </td>
                <td className="text-right">
                  <button
                    type="button"
                    onClick={() => onOpen(row.member_id)}
                    className="text-[10px] font-bold text-[#1b59f8] hover:underline"
                  >
                    Open asset
                  </button>
                </td>
              </tr>
            ))}
            {data.assets.length === 0 ? (
              <EmptyRow
                colSpan={6}
                message="No automation assets yet. Create an Automation Test Suite and add test cases to it."
              />
            ) : null}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
