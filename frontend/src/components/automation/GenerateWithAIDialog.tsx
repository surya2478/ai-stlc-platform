"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Sparkles,
  Loader2,
  Search,
  ShieldCheck,
  AlertTriangle,
  CheckSquare,
  Square,
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
import { automationApi, type TestCase } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAIAction } from "@/hooks/useAIAction";
import { AI_PROCESSING_STAGES } from "@/lib/ai-processing-stages";
import { agentRunIdFrom, waitForAgentRun } from "@/lib/agentRunProgress";

type Framework = "playwright" | "pytest";
type AutomationKind = "ui" | "api" | "hybrid";

type Props = {
  open: boolean;
  onClose: () => void;
  projectId: number | null;
  approvedTestCases: TestCase[];
  preselectedIds?: number[];
  onGenerated?: (count: number) => void;
};

function messageFromError(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function GenerateWithAIDialog({
  open,
  onClose,
  projectId,
  approvedTestCases,
  preselectedIds = [],
  onGenerated,
}: Props) {
  const { runAIAction } = useAIAction();
  const [framework, setFramework] = useState<Framework>("playwright");
  const [kind, setKind] = useState<AutomationKind>("ui");
  const [context, setContext] = useState("");
  const [includeApiChecks, setIncludeApiChecks] = useState(true);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    if (open) {
      setSelected(new Set(preselectedIds));
      setError("");
      setConfirmed(false);
    }
  }, [open, preselectedIds]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return approvedTestCases;
    return approvedTestCases.filter(
      (tc) =>
        tc.test_case_id.toLowerCase().includes(q) || tc.title.toLowerCase().includes(q),
    );
  }, [approvedTestCases, search]);

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allFilteredSelected = filtered.length > 0 && filtered.every((tc) => selected.has(tc.id));
  const toggleAll = () => {
    setSelected((prev) => {
      if (allFilteredSelected) {
        const next = new Set(prev);
        filtered.forEach((tc) => next.delete(tc.id));
        return next;
      }
      const next = new Set(prev);
      filtered.forEach((tc) => next.add(tc.id));
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!projectId) {
      setError("No project selected.");
      return;
    }
    if (selected.size === 0) {
      setError("Pick at least one approved test case to generate.");
      return;
    }
    if (!confirmed) {
      setError("Confirm that scripts will start as AI Draft and require review.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await runAIAction({
        actionName: "generate_automation_scripts",
        title: `Generating ${framework === "playwright" ? "Playwright" : "Pytest"} Scripts`,
        module: "Automation Studio",
        artifactType: "Automation Scripts",
        projectId,
        stages: AI_PROCESSING_STAGES.scriptGeneration,
        successMessage: "Automation scripts generated.",
        execute: () => automationApi.generateScripts(
          projectId,
          Array.from(selected),
          framework,
        ),
        // The endpoint queues the work and returns 202 immediately, so the
        // request finishing says nothing about the scripts existing. Watch the
        // run itself, otherwise the modal closes seconds into a job that takes
        // minutes and the user is told it "started successfully" and left with
        // no way to see it land.
        awaitCompletion: async (result, update) => {
          const agentRunId = agentRunIdFrom(result);
          if (agentRunId === null) return;
          return waitForAgentRun(agentRunId, update);
        },
      });
      onGenerated?.(selected.size);
      onClose();
    } catch (e) {
      setError(messageFromError(e, "Could not start script generation."));
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
              <Sparkles className="h-4 w-4 text-violet-600" />
              Generate with AI
            </DrawerTitle>
            <DrawerDescription>
              Produce draft Playwright or Pytest scripts from approved test cases. All output starts as AI Draft and must be reviewed before approval.
            </DrawerDescription>
          </div>
        </DrawerHeader>

        <DrawerBody>
          <div className="space-y-5">
            <Section title="Framework" description="Choose the runtime that will execute these tests.">
              <div className="grid grid-cols-2 gap-2">
                <FrameworkChoice
                  active={framework === "playwright"}
                  label="Playwright"
                  hint="UI automation, cross-browser"
                  onClick={() => setFramework("playwright")}
                />
                <FrameworkChoice
                  active={framework === "pytest"}
                  label="Pytest"
                  hint="API + Python integration"
                  onClick={() => setFramework("pytest")}
                />
              </div>
            </Section>

            <Section title="Automation kind" description="What kind of validation will these scripts perform?">
              <div className="grid grid-cols-3 gap-2">
                <KindChoice active={kind === "ui"} label="UI" onClick={() => setKind("ui")} />
                <KindChoice active={kind === "api"} label="API" onClick={() => setKind("api")} />
                <KindChoice active={kind === "hybrid"} label="Hybrid" onClick={() => setKind("hybrid")} />
              </div>
            </Section>

            <Section title="Approved test cases" description={`${selected.size} of ${approvedTestCases.length} selected`}>
              <div className="rounded-lg border border-gray-200">
                <div className="flex items-center gap-2 border-b border-gray-100 px-3 py-2">
                  <Search className="h-3.5 w-3.5 text-gray-400" />
                  <input
                    type="search"
                    placeholder="Search test cases…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="flex-1 bg-transparent text-xs focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={toggleAll}
                    className="inline-flex shrink-0 items-center gap-1 text-[11px] font-semibold text-violet-700 hover:underline"
                  >
                    {allFilteredSelected ? <CheckSquare className="h-3.5 w-3.5" /> : <Square className="h-3.5 w-3.5" />}
                    {allFilteredSelected ? "Deselect all" : "Select all"}
                  </button>
                  {selected.size > 0 && (
                    <button
                      type="button"
                      onClick={() => setSelected(new Set())}
                      className="text-[11px] text-gray-500 hover:text-gray-800"
                    >
                      Clear
                    </button>
                  )}
                </div>
                <div className="max-h-60 overflow-y-auto">
                  {filtered.length === 0 ? (
                    <div className="px-4 py-6 text-center text-xs text-gray-400">
                      No approved test cases match your search.
                    </div>
                  ) : (
                    filtered.map((tc) => {
                      const checked = selected.has(tc.id);
                      return (
                        <button
                          key={tc.id}
                          type="button"
                          onClick={() => toggle(tc.id)}
                          className={cn(
                            "flex w-full items-start gap-2 border-b border-gray-50 px-3 py-2 text-left text-xs transition hover:bg-gray-50",
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
                              <span className="font-mono text-[#B71920]">{tc.test_case_id}</span>
                              <Badge variant="secondary" className="text-[10px]">{tc.priority}</Badge>
                            </div>
                            <p className="mt-0.5 truncate text-gray-700">{tc.title}</p>
                          </div>
                        </button>
                      );
                    })
                  )}
                </div>
              </div>
            </Section>

            <Section title="Business context" description="Optional. Helps the AI tailor steps, data, and assertions.">
              <textarea
                value={context}
                onChange={(e) => setContext(e.target.value)}
                rows={3}
                placeholder="e.g. Prepaid customer flow. Use telco staging endpoints. Validate balance via /accounts/{id}/balance."
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-[#B71920]"
              />
            </Section>

            <Section title="Validation options" description="Additive checks the AI will propose alongside the script.">
              <label className="flex items-start gap-2 text-xs text-gray-700">
                <input
                  type="checkbox"
                  checked={includeApiChecks}
                  onChange={(e) => setIncludeApiChecks(e.target.checked)}
                  className="mt-0.5 h-3.5 w-3.5 accent-violet-600"
                />
                <span>
                  Suggest API and database assertions where the business action implies a backend
                  side-effect (e.g. order created, balance changed). Suggestions arrive as draft
                  validation steps.
                </span>
              </label>
            </Section>

            <div className="rounded-lg border border-violet-100 bg-violet-50/50 p-3">
              <p className="flex items-center gap-2 text-[11px] font-semibold text-violet-800">
                <ShieldCheck className="h-3.5 w-3.5" />
                Draft-only generation
              </p>
              <p className="mt-1 text-[11px] text-violet-700">
                AI never approves its own output. Generated scripts land as <span className="font-mono">AI Draft</span> and follow the standard Draft → In Review → Approved workflow.
              </p>
              <label className="mt-2 flex items-start gap-2 text-[11px] text-violet-800">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                  className="mt-0.5 h-3.5 w-3.5 accent-violet-600"
                />
                <span>I understand that AI output requires human review before it can be executed.</span>
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
              <Sparkles className="h-3.5 w-3.5" />
            )}
            Generate as Draft ({selected.size})
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
        <p className="text-xs font-semibold text-gray-800">{title}</p>
        {description && <p className="text-[11px] text-gray-400">{description}</p>}
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
          : "border-gray-200 text-gray-700 hover:bg-gray-50",
      )}
    >
      <span className="font-semibold">{label}</span>
      <span className="text-[10px] text-gray-500">{hint}</span>
    </button>
  );
}

function KindChoice({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-lg border px-3 py-2 text-xs font-semibold transition",
        active
          ? "border-violet-300 bg-violet-50 text-violet-800"
          : "border-gray-200 text-gray-700 hover:bg-gray-50",
      )}
    >
      {label}
    </button>
  );
}
