"use client";

import { useEffect, useMemo, useState } from "react";
import { Database, Loader2, Play } from "lucide-react";
import { testDataApi, type TestCase } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Drawer, DrawerBody, DrawerContent, DrawerDescription, DrawerFooter, DrawerHeader, DrawerTitle,
} from "@/components/ui/drawer";

interface BindableRecord {
  record_id: number;
  record_key: string;
  data_set_id: number;
  data_set_name: string;
  data_set_data_id: string;
  test_case_id: number | null;
  preview_keys: string[];
  approval_status: string;
}

/**
 * Pre-run confirmation: name the suite and optionally bind a test data record
 * per test case. Bound records substitute ${field} placeholders in step text
 * server-side at run start.
 */
export function StartRunDialog({
  open,
  onClose,
  projectId,
  environment,
  selectedTcs,
  busy,
  onStart,
  defaultSuiteName,
}: {
  open: boolean;
  onClose: () => void;
  projectId: number;
  environment: string;
  selectedTcs: TestCase[];
  busy: boolean;
  onStart: (options: { suiteName: string; boundRecords: Record<number, number> }) => void;
  /** Pre-fills the suite name — e.g. the Test Suite tag when the selection
   * came from "Select all in suite" — so Run History reads the suite's real
   * name instead of a generic "Manual Run · <date>". */
  defaultSuiteName?: string;
}) {
  const [records, setRecords] = useState<BindableRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [suiteName, setSuiteName] = useState("");
  const [bindings, setBindings] = useState<Record<number, number>>({});

  useEffect(() => {
    if (!open) return;
    setSuiteName(defaultSuiteName || `Manual Run · ${new Date().toLocaleDateString()}`);
    setBindings({});
  }, [open, defaultSuiteName]);

  useEffect(() => {
    if (!open) return;
    setRecordsLoading(true);
    testDataApi
      .listBindableRecords(projectId, { limit: 500 })
      .then((r) => setRecords(r.data ?? []))
      .catch(() => setRecords([]))
      .finally(() => setRecordsLoading(false));
  }, [open, projectId]);

  const optionsForTc = useMemo(() => {
    const map = new Map<number, BindableRecord[]>();
    for (const tc of selectedTcs) {
      map.set(
        tc.id,
        records.filter((r) => r.test_case_id === tc.id || r.test_case_id === null),
      );
    }
    return map;
  }, [records, selectedTcs]);

  const boundCount = Object.keys(bindings).length;

  return (
    <Drawer open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DrawerContent size="lg">
        <DrawerHeader>
          <div>
            <DrawerTitle className="flex items-center gap-2">
              <Play className="h-4 w-4 text-[#1b59f8]" /> Start manual execution
            </DrawerTitle>
            <DrawerDescription>
              {selectedTcs.length} test case{selectedTcs.length === 1 ? "" : "s"} · environment {environment}
            </DrawerDescription>
          </div>
        </DrawerHeader>
        <DrawerBody>
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              Suite name
            </label>
            <input
              value={suiteName}
              onChange={(e) => setSuiteName(e.target.value)}
              className="w-full rounded-md border border-slate-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          </div>

          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                <Database className="h-3 w-3" /> Test data binding (optional)
              </label>
              {recordsLoading && <Loader2 className="h-3 w-3 animate-spin text-slate-300" />}
            </div>
            <p className="mb-2 text-[11px] text-slate-400">
              Bound records fill <code className="rounded bg-slate-100 px-1">{"${field}"}</code> placeholders
              in step text when the run starts.
            </p>
            <div className="space-y-2">
              {selectedTcs.map((tc) => {
                const options = optionsForTc.get(tc.id) ?? [];
                return (
                  <div key={tc.id} className="flex items-center gap-2 rounded-lg border border-slate-100 px-2.5 py-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-mono text-[11px] text-[#1b59f8]">{tc.test_case_id}</p>
                      <p className="truncate text-[11px] text-slate-600">{tc.title}</p>
                    </div>
                    <select
                      value={bindings[tc.id] ?? ""}
                      onChange={(e) => {
                        const value = e.target.value;
                        setBindings((prev) => {
                          const next = { ...prev };
                          if (value === "") delete next[tc.id];
                          else next[tc.id] = Number(value);
                          return next;
                        });
                      }}
                      disabled={options.length === 0}
                      className="w-52 shrink-0 rounded-md border border-slate-200 bg-white px-2 py-1.5 text-[11px] focus:outline-none focus:ring-2 focus:ring-blue-100 disabled:bg-slate-50 disabled:text-slate-400"
                    >
                      <option value="">
                        {options.length === 0 ? "No records available" : "No binding"}
                      </option>
                      {options.map((r) => (
                        <option key={r.record_id} value={r.record_id}>
                          {r.data_set_name} · {r.record_key}
                        </option>
                      ))}
                    </select>
                  </div>
                );
              })}
            </div>
          </div>
        </DrawerBody>
        <DrawerFooter>
          <span className="mr-auto text-[11px] text-slate-400">
            {boundCount > 0 ? `${boundCount} record(s) bound` : "No data bound"}
          </span>
          <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={() => onStart({ suiteName: suiteName.trim() || `Manual Run · ${new Date().toLocaleDateString()}`, boundRecords: bindings })}
            disabled={busy}
            className="gap-1.5"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            Start run
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
