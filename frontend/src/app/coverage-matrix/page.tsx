"use client";

import { useState, useEffect, useCallback, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { Table2, Loader2, ShieldCheck, ShieldAlert, RefreshCw } from "lucide-react";
import { projectsApi, reviewsApi, type CoverageMatrixEntry } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

function caseClassVariant(caseClass: string | undefined): "success" | "warning" | "destructive" | "outline" {
  switch (caseClass) {
    case "positive": return "success";
    case "negative": return "warning";
    case "boundary": return "outline";
    case "exception": return "destructive";
    default: return "outline";
  }
}

function executionStatusVariant(status: string | undefined): "success" | "warning" | "destructive" | "outline" {
  if (!status) return "outline";
  const s = status.toLowerCase();
  if (s === "passed" || s === "pass") return "success";
  if (s === "failed" || s === "fail") return "destructive";
  return "warning";
}

function CoverageMatrixContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProject = Number(searchParams.get("project")) || null;

  const [rows, setRows] = useState<CoverageMatrixEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    projectsApi.list().then((res) => {
      if (res.data.length > 0 && !searchParams.get("project")) {
        const params = new URLSearchParams(searchParams.toString());
        params.set("project", String(res.data[0].id));
        router.push(`${pathname}?${params.toString()}`);
      }
    }).catch(() => console.error("Could not load projects."));
  }, [searchParams, router, pathname]);

  const loadMatrix = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const res = await reviewsApi.coverageMatrix(selectedProject);
      setRows(res.data);
    } catch (err) {
      console.error("Could not load coverage matrix:", err);
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadMatrix();
  }, [loadMatrix]);

  const covered = rows.filter((r) => r.script_id != null).length;
  const executed = rows.filter((r) => r.execution_status != null).length;
  const withDefects = rows.filter((r) => r.defect_linked).length;

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-blue-50 border border-blue-100 p-2.5">
            <Table2 className="h-6 w-6 text-[#1b59f8]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Coverage Matrix</h1>
            <p className="text-xs text-slate-500 mt-1">
              Requirement → Scenario → Test Case → Script → Execution → Defect rollup, one row per test case.
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={loadMatrix} disabled={loading} className="h-8 text-xs font-semibold">
          <RefreshCw className={cn("h-3.5 w-3.5 mr-1.5", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Test Cases Tracked", value: rows.length },
          { label: "Automation Linked", value: covered },
          { label: "Executed At Least Once", value: executed },
          { label: "With a Linked Defect", value: withDefects },
        ].map((stat) => (
          <div key={stat.label} className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
            <div className="text-xl font-bold text-slate-900">{stat.value}</div>
            <div className="text-[10px] font-bold text-slate-400 mt-1 uppercase tracking-wider">{stat.label}</div>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-16 text-slate-400 text-xs font-semibold">
          <Loader2 className="h-6 w-6 animate-spin text-[#1b59f8] mb-2" />
          Loading coverage matrix...
        </div>
      ) : rows.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-dashed border-slate-250">
          <Table2 className="h-10 w-10 text-slate-300 mx-auto mb-2" />
          <p className="text-xs text-slate-500 font-bold">No coverage matrix rows yet</p>
          <p className="text-[10px] text-slate-400 font-semibold mt-1">
            Rows are seeded once a test case&apos;s scenario has been reviewed by the test_case_review agent.
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-100 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                <th className="text-left px-4 py-2.5">Requirement</th>
                <th className="text-left px-4 py-2.5">Scenario</th>
                <th className="text-left px-4 py-2.5">Test Case</th>
                <th className="text-left px-4 py-2.5">Type</th>
                <th className="text-left px-4 py-2.5">Class</th>
                <th className="text-left px-4 py-2.5">Automation</th>
                <th className="text-left px-4 py-2.5">Execution</th>
                <th className="text-left px-4 py-2.5">Defect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {rows.map((row) => (
                <tr key={row.id} className="hover:bg-slate-50/50">
                  <td className="px-4 py-2.5 font-mono text-slate-500">
                    {row.requirement_id ? `REQ-${row.requirement_id}` : "—"}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-slate-500">
                    {row.scenario_id ? `TS-${row.scenario_id}` : "—"}
                  </td>
                  <td className="px-4 py-2.5 font-mono font-bold text-slate-700">
                    {row.test_case_id ? `TC-${row.test_case_id}` : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-slate-600">{row.test_type ?? "—"}</td>
                  <td className="px-4 py-2.5">
                    {row.case_class ? (
                      <Badge variant={caseClassVariant(row.case_class)} className="capitalize">{row.case_class}</Badge>
                    ) : "—"}
                  </td>
                  <td className="px-4 py-2.5">
                    {row.script_id ? (
                      <span className="inline-flex items-center gap-1 text-emerald-600 font-bold">
                        <ShieldCheck className="h-3.5 w-3.5" /> Linked
                      </span>
                    ) : (
                      <span className="text-slate-400">Not linked</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {row.execution_status ? (
                      <Badge variant={executionStatusVariant(row.execution_status)} className="capitalize">
                        {row.execution_status}
                      </Badge>
                    ) : (
                      <span className="text-slate-400">Not run</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {row.defect_linked ? (
                      <span className="inline-flex items-center gap-1 text-rose-600 font-bold">
                        <ShieldAlert className="h-3.5 w-3.5" /> Yes
                      </span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function CoverageMatrixPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-slate-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-[#1b59f8] mr-2" />
        Loading Coverage Matrix...
      </div>
    }>
      <CoverageMatrixContent />
    </Suspense>
  );
}
