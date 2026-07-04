"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bug, Loader2 } from "lucide-react";
import { defectsApi } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import { buildHref } from "./execution-shared";

// Values must match backend DefectDraftCreate Literals exactly
// (see backend/app/schemas/defect.py) — the Literal check runs before the
// priority normalizer, so lowercase variants are rejected with a 422.
const SEVERITIES = ["Critical", "High", "Medium", "Low"] as const;
const PRIORITIES = ["P1", "P2", "P3", "P4"] as const;

export interface DefectPrefill {
  summary?: string;
  description?: string;
  steps_to_reproduce?: string[];
  expected_result?: string;
  actual_result?: string;
  severity?: string;
  test_case_id?: number;
  execution_result_id?: number;
}

/**
 * Drawer form for drafting a defect from a failed execution result or manual
 * step. Links the draft back to the test case and execution result so the
 * defect keeps full traceability.
 */
export function CreateDefectDialog({
  open,
  onClose,
  projectId,
  prefill,
}: {
  open: boolean;
  onClose: () => void;
  projectId: number;
  prefill?: DefectPrefill;
}) {
  const { toast } = useToast();
  const router = useRouter();

  const [summary, setSummary] = useState("");
  const [description, setDescription] = useState("");
  const [steps, setSteps] = useState("");
  const [expected, setExpected] = useState("");
  const [actual, setActual] = useState("");
  const [severity, setSeverity] = useState<string>("Medium");
  const [priority, setPriority] = useState<string>("P3");
  const [submitting, setSubmitting] = useState(false);

  // Re-seed the form each time the dialog opens with a (new) prefill.
  useEffect(() => {
    if (!open) return;
    setSummary(prefill?.summary ?? "");
    setDescription(prefill?.description ?? "");
    setSteps((prefill?.steps_to_reproduce ?? []).join("\n"));
    setExpected(prefill?.expected_result ?? "");
    setActual(prefill?.actual_result ?? "");
    setSeverity(prefill?.severity ?? "Medium");
    setPriority("P3");
  }, [open, prefill]);

  const submit = async () => {
    if (!summary.trim()) {
      toast({ title: "Summary is required", variant: "warning" });
      return;
    }
    setSubmitting(true);
    try {
      const res = await defectsApi.create({
        project_id: projectId,
        summary: summary.trim(),
        description: description.trim() || undefined,
        steps_to_reproduce: steps
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
        expected_result: expected.trim() || undefined,
        actual_result: actual.trim() || undefined,
        severity,
        priority,
        test_case_id: prefill?.test_case_id,
        execution_result_id: prefill?.execution_result_id,
      });
      toast({
        title: `Defect ${res.data.defect_id} drafted`,
        description: "Linked to the failing test case and execution result.",
        variant: "success",
        action: {
          label: "Open Defects",
          onClick: () => router.push(buildHref("/defects", { project: String(projectId) })),
        },
      });
      onClose();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast({
        title: "Failed to create defect",
        description: err?.response?.data?.detail ?? err?.message,
        variant: "error",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DrawerContent size="lg">
        <DrawerHeader>
          <div>
            <DrawerTitle className="flex items-center gap-2">
              <Bug className="h-4 w-4 text-red-500" /> Draft defect
            </DrawerTitle>
            <DrawerDescription>
              Creates a defect draft linked to this test case and execution result.
            </DrawerDescription>
          </div>
        </DrawerHeader>
        <DrawerBody>
          <Field label="Summary *">
            <input
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              className="w-full rounded-md border border-slate-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100"
              placeholder="Short description of the failure"
            />
          </Field>
          <Field label="Description">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-slate-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          </Field>
          <Field label="Steps to reproduce (one per line)">
            <textarea
              value={steps}
              onChange={(e) => setSteps(e.target.value)}
              rows={4}
              className="w-full rounded-md border border-slate-200 px-2.5 py-1.5 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Expected result">
              <textarea
                value={expected}
                onChange={(e) => setExpected(e.target.value)}
                rows={2}
                className="w-full rounded-md border border-slate-200 px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </Field>
            <Field label="Actual result">
              <textarea
                value={actual}
                onChange={(e) => setActual(e.target.value)}
                rows={2}
                className="w-full rounded-md border border-slate-200 px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Severity">
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
                className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm capitalize focus:outline-none focus:ring-2 focus:ring-blue-100"
              >
                {SEVERITIES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label="Priority">
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm uppercase focus:outline-none focus:ring-2 focus:ring-blue-100"
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>{p.toUpperCase()}</option>
                ))}
              </select>
            </Field>
          </div>
        </DrawerBody>
        <DrawerFooter>
          <Button variant="outline" size="sm" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button size="sm" onClick={submit} disabled={submitting} className="gap-1.5">
            {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Bug className="h-3.5 w-3.5" />}
            Create defect draft
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
        {label}
      </label>
      {children}
    </div>
  );
}
