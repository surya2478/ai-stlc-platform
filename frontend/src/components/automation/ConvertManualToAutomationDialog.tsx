"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowRightLeft,
  Loader2,
  Search,
  ShieldCheck,
  AlertTriangle,
  ListChecks,
} from "lucide-react";
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerDescription,
  DrawerBody,
  DrawerFooter,
} from "@/components/ui/drawer";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { automationApi, testCasesApi, type TestCase } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAIAction } from "@/hooks/useAIAction";
import { AI_PROCESSING_STAGES } from "@/lib/ai-processing-stages";

type Framework = "playwright" | "pytest";

type Props = {
  open: boolean;
  onClose: () => void;
  projectId: number | null;
  onConverted?: (count: number) => void;
};

function messageFromError(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function ConvertManualToAutomationDialog({
  open,
  onClose,
  projectId,
  onConverted,
}: Props) {
  const { runAIAction } = useAIAction();
  const [manualCases, setManualCases] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(false);
  const [framework, setFramework] = useState<Framework>("playwright");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    if (!open || !projectId) return;
    setLoading(true);
    setError("");
    setSelected(new Set());
    setConfirmed(false);
    testCasesApi
      .list(projectId, { status: "approved" })
      .then((res) => {
        const manuals = (res.data ?? []).filter(
          (tc) => (tc.execution_mode ?? "").toLowerCase() === "manual",
        );
        setManualCases(manuals);
      })
      .catch((e) => setError(messageFromError(e, "Could not load approved manual test cases.")))
      .finally(() => setLoading(false));
  }, [open, projectId]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return manualCases;
    return manualCases.filter(
      (tc) =>
        tc.test_case_id.toLowerCase().includes(q) || tc.title.toLowerCase().includes(q),
    );
  }, [manualCases, search]);

  const selectedCases = useMemo(
    () => manualCases.filter((tc) => selected.has(tc.id)),
    [manualCases, selected],
  );

  const ambiguousCount = useMemo(() => {
    let count = 0;
    for (const tc of selectedCases) {
      for (const step of tc.steps ?? []) {
        const action = (step.action ?? "").trim();
        if (action.length < 6 || /click|press|do/i.test(action) && action.split(/\s+/).length < 3) {
          count += 1;
        }
      }
    }
    return count;
  }, [selectedCases]);

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!projectId) {
      setError("No project selected.");
      return;
    }
    if (selected.size === 0) {
      setError("Pick at least one approved manual test case to convert.");
      return;
    }
    if (!confirmed) {
      setError("Confirm that converted scripts will start as AI Draft for review.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await runAIAction({
        actionName: "convert_manual_to_automation",
        title: "Converting Manual Flow to Automation",
        module: "Automation Studio",
        artifactType: "Automation Scripts",
        projectId,
        stages: AI_PROCESSING_STAGES.scriptGeneration,
        successMessage: "Manual-to-automation conversion started successfully.",
        execute: () => automationApi.generateScripts(
          projectId,
          Array.from(selected),
          framework,
          "manual_conversion",
        ),
      });
      onConverted?.(selected.size);
      onClose();
    } catch (e) {
      setError(messageFromError(e, "Could not start manual-to-automation conversion."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DrawerContent size="lg">
        <DrawerHeader>
          <div>
            <DrawerTitle className="flex items-center gap-2">
              <ArrowRightLeft className="h-4 w-4 text-violet-600" />
              Convert manual flow to automation
            </DrawerTitle>
            <DrawerDescription>
              Use approved manual test steps as the source. The AI produces draft Playwright or Pytest
              scripts mapped to your steps, then routes them through the standard review and approval
              lifecycle. Nothing auto-approves.
            </DrawerDescription>
          </div>
        </DrawerHeader>

        <DrawerBody>
          <div className="space-y-5">
            <Section title="Target framework">
              <div className="grid grid-cols-2 gap-2">
                <FrameworkChoice
                  active={framework === "playwright"}
                  label="Playwright"
                  hint="UI-driven manual flows"
                  onClick={() => setFramework("playwright")}
                />
                <FrameworkChoice
                  active={framework === "pytest"}
                  label="Pytest"
                  hint="API / backend manual checks"
                  onClick={() => setFramework("pytest")}
                />
              </div>
            </Section>

            <Section title="Approved manual test cases" description={`${selected.size} of ${manualCases.length} selected`}>
              <div className="rounded-lg border border-slate-200">
                <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2">
                  <Search className="h-3.5 w-3.5 text-slate-400" />
                  <input
                    type="search"
                    placeholder="Search manual test cases…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="flex-1 bg-transparent text-xs focus:outline-none"
                  />
                </div>
                <div className="max-h-60 overflow-y-auto">
                  {loading ? (
                    <div className="flex items-center justify-center gap-2 px-4 py-6 text-xs text-slate-400">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Loading approved manual test cases…
                    </div>
                  ) : filtered.length === 0 ? (
                    <div className="px-4 py-6 text-center text-xs text-slate-400">
                      {manualCases.length === 0
                        ? "No approved manual test cases in this project."
                        : "No manual test cases match your search."}
                    </div>
                  ) : (
                    filtered.map((tc) => {
                      const checked = selected.has(tc.id);
                      const stepCount = (tc.steps ?? []).length;
                      return (
                        <button
                          key={tc.id}
                          type="button"
                          onClick={() => toggle(tc.id)}
                          className={cn(
                            "flex w-full items-start gap-2 border-b border-slate-50 px-3 py-2 text-left text-xs transition hover:bg-slate-50",
                            checked && "bg-violet-50/50",
                          )}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            readOnly
                            className="mt-0.5 h-3.5 w-3.5 accent-violet-600"
                          />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-[#1b59f8]">{tc.test_case_id}</span>
                              <Badge variant="secondary" className="text-[10px]">{tc.priority}</Badge>
                              <span className="text-[10px] text-slate-400">
                                <ListChecks className="inline h-3 w-3 mr-0.5" />
                                {stepCount} step{stepCount === 1 ? "" : "s"}
                              </span>
                            </div>
                            <p className="mt-0.5 truncate text-slate-700">{tc.title}</p>
                          </div>
                        </button>
                      );
                    })
                  )}
                </div>
              </div>
            </Section>

            {selectedCases.length > 0 && (
              <Section title="Source manual steps" description="Preview of the first selected test case">
                <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-3">
                  <p className="mb-2 text-[11px] font-semibold text-slate-700">
                    {selectedCases[0].test_case_id} · {selectedCases[0].title}
                  </p>
                  <ol className="space-y-1.5 text-[11px]">
                    {(selectedCases[0].steps ?? []).slice(0, 6).map((step, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <span className="font-mono text-slate-400">{step.step_number}.</span>
                        <div className="min-w-0 flex-1">
                          <p className="text-slate-700">{step.action}</p>
                          {step.expected_result && (
                            <p className="text-slate-400">→ {step.expected_result}</p>
                          )}
                        </div>
                      </li>
                    ))}
                    {(selectedCases[0].steps ?? []).length > 6 && (
                      <li className="text-[10px] text-slate-400">
                        + {(selectedCases[0].steps ?? []).length - 6} more steps…
                      </li>
                    )}
                  </ol>
                  {selectedCases.length > 1 && (
                    <p className="mt-2 text-[10px] text-slate-400">
                      + {selectedCases.length - 1} more selected test case(s) will be converted too.
                    </p>
                  )}
                </div>
              </Section>
            )}

            {ambiguousCount > 0 && (
              <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  Detected {ambiguousCount} potentially ambiguous step{ambiguousCount === 1 ? "" : "s"} (very
                  short or generic action text). The AI will flag these in the draft for you to clarify.
                </span>
              </div>
            )}

            <div className="rounded-lg border border-violet-100 bg-violet-50/50 p-3">
              <p className="flex items-center gap-2 text-[11px] font-semibold text-violet-800">
                <ShieldCheck className="h-3.5 w-3.5" />
                Draft-only conversion
              </p>
              <p className="mt-1 text-[11px] text-violet-700">
                Manual steps stay the source of truth. Converted scripts land as
                <span className="mx-1 font-mono">AI Draft</span> and follow the standard
                AI Draft → Draft → In Review → Approved workflow.
              </p>
              <label className="mt-2 flex items-start gap-2 text-[11px] text-violet-800">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                  className="mt-0.5 h-3.5 w-3.5 accent-violet-600"
                />
                <span>I understand that converted scripts require human review before they can be executed.</span>
              </label>
            </div>

            {error && (
              <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}
          </div>
        </DrawerBody>

        <DrawerFooter>
          <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={busy || selected.size === 0 || !confirmed}
            className="gap-1.5"
          >
            {busy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <ArrowRightLeft className="h-3.5 w-3.5" />
            )}
            Convert as Draft ({selected.size})
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <p className="text-xs font-semibold text-slate-800">{title}</p>
        {description && <p className="text-[11px] text-slate-400">{description}</p>}
      </div>
      {children}
    </div>
  );
}

function FrameworkChoice({
  active,
  label,
  hint,
  onClick,
}: {
  active: boolean;
  label: string;
  hint: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-col items-start gap-0.5 rounded-lg border px-3 py-2 text-left text-xs transition",
        active
          ? "border-violet-300 bg-violet-50 text-violet-800"
          : "border-slate-200 text-slate-700 hover:bg-slate-50",
      )}
    >
      <span className="font-semibold">{label}</span>
      <span className="text-[10px] text-slate-500">{hint}</span>
    </button>
  );
}
