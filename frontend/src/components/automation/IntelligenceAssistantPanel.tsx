"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Sparkles,
  Crosshair,
  CheckSquare,
  Database as DatabaseIcon,
  Activity,
  Gauge,
  AlertTriangle,
  Clock,
  Lock,
  Code2,
  ShieldCheck,
  X,
  ChevronRight,
  Loader2,
} from "lucide-react";
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerDescription,
  DrawerBody,
} from "@/components/ui/drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  automationApi,
  type AutomationScript,
  type IntelligenceAssertion,
  type IntelligenceCheck,
  type IntelligenceDataIssue,
  type IntelligenceDecision,
  type IntelligenceHealth,
  type IntelligenceLocator,
  type IntelligenceRecommendation,
  type IntelligenceReport,
  type RecommendationSeverity,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type TabKey =
  | "recommendations"
  | "locators"
  | "assertions"
  | "test_data"
  | "api_db"
  | "health";

type ActionState = "open" | "applied" | "dismissed";

type Props = {
  open: boolean;
  onClose: () => void;
  script?: AutomationScript | null;
};

const TABS: { key: TabKey; label: string; icon: typeof Sparkles }[] = [
  { key: "recommendations", label: "AI Recommendations", icon: Sparkles },
  { key: "locators", label: "Locator Intelligence", icon: Crosshair },
  { key: "assertions", label: "Assertions", icon: CheckSquare },
  { key: "test_data", label: "Test Data", icon: DatabaseIcon },
  { key: "api_db", label: "API / DB Checks", icon: Activity },
  { key: "health", label: "Script Health", icon: Gauge },
];

function messageFromError(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function decisionsToState(decisions: IntelligenceDecision[]): Record<string, ActionState> {
  const out: Record<string, ActionState> = {};
  for (const d of decisions) {
    out[d.recommendation_id] = d.action === "apply" ? "applied" : "dismissed";
  }
  return out;
}

export function IntelligenceAssistantPanel({ open, onClose, script }: Props) {
  const [tab, setTab] = useState<TabKey>("recommendations");
  const [report, setReport] = useState<IntelligenceReport | null>(null);
  const [actionStates, setActionStates] = useState<Record<string, ActionState>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const loadReport = useCallback(() => {
    if (!script) {
      setReport(null);
      setActionStates({});
      return;
    }
    setLoading(true);
    setError("");
    automationApi
      .getIntelligence(script.id)
      .then((res) => {
        setReport(res.data);
        setActionStates(decisionsToState(res.data.decisions ?? []));
      })
      .catch((e) => setError(messageFromError(e, "Could not load script intelligence.")))
      .finally(() => setLoading(false));
  }, [script]);

  useEffect(() => {
    if (open) {
      loadReport();
    }
  }, [open, loadReport]);

  const onAction = async (recommendationId: string, action: ActionState) => {
    if (action === "open") {
      setActionStates((prev) => {
        const next = { ...prev };
        delete next[recommendationId];
        return next;
      });
      return;
    }
    if (!script) {
      setActionStates((prev) => ({ ...prev, [recommendationId]: action }));
      return;
    }
    setBusyId(recommendationId);
    setError("");
    try {
      await automationApi.recommendationDecision(
        script.id,
        recommendationId,
        action === "applied" ? "apply" : "dismiss",
      );
      setActionStates((prev) => ({ ...prev, [recommendationId]: action }));
    } catch (e) {
      setError(messageFromError(e, "Could not record decision."));
    } finally {
      setBusyId(null);
    }
  };

  const scriptLabel = useMemo(() => {
    if (!script) return "No script selected — open from a workspace to analyze its code.";
    return `${script.script_id ?? `#${script.id}`} · ${script.framework}`;
  }, [script]);

  return (
    <Drawer open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DrawerContent size="xl">
        <DrawerHeader>
          <div>
            <DrawerTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-violet-600" />
              AI Intelligence Assistant
            </DrawerTitle>
            <DrawerDescription>
              {scriptLabel}. Every recommendation creates a draft change — nothing is applied
              to approved scripts silently.
            </DrawerDescription>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            aria-label="Close panel"
          >
            <X className="h-4 w-4" />
          </button>
        </DrawerHeader>

        <div className="border-b border-gray-100 px-3 pt-2 shrink-0">
          <div className="flex gap-1 overflow-x-auto">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.key;
              return (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setTab(t.key)}
                  className={cn(
                    "flex shrink-0 items-center gap-1.5 rounded-t-md px-3 py-2 text-[11px] font-semibold transition",
                    active
                      ? "border-b-2 border-violet-600 text-violet-700"
                      : "text-gray-500 hover:text-gray-800",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>

        <DrawerBody>
          {!script ? (
            <EmptyState message="Pick a test case in the inventory and use the workspace AI Assistant button to analyze its script." />
          ) : loading ? (
            <LoadingState />
          ) : error ? (
            <ErrorBanner message={error} onRetry={loadReport} />
          ) : !report ? (
            <EmptyState message="No analysis available yet." />
          ) : (
            <>
              {tab === "recommendations" && (
                <RecommendationsTab data={report.recommendations} states={actionStates} busyId={busyId} onAction={onAction} />
              )}
              {tab === "locators" && (
                <LocatorsTab data={report.locators} states={actionStates} busyId={busyId} onAction={onAction} />
              )}
              {tab === "assertions" && (
                <AssertionsTab data={report.assertions} states={actionStates} busyId={busyId} onAction={onAction} />
              )}
              {tab === "test_data" && (
                <TestDataTab data={report.data_issues} states={actionStates} busyId={busyId} onAction={onAction} />
              )}
              {tab === "api_db" && (
                <ApiDbTab data={report.checks} states={actionStates} busyId={busyId} onAction={onAction} />
              )}
              {tab === "health" && <HealthTab data={report.health} />}
            </>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex h-48 items-center justify-center p-6 text-center">
      <p className="max-w-sm text-xs text-gray-500">{message}</p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex h-48 items-center justify-center p-6 text-center text-xs text-gray-400">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      Analyzing script…
    </div>
  );
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div className="flex-1">
        <p className="font-semibold">{message}</p>
        <button type="button" onClick={onRetry} className="mt-1 text-red-700 underline">
          Retry
        </button>
      </div>
    </div>
  );
}

function severityClasses(s: RecommendationSeverity): string {
  if (s === "high") return "bg-red-50 text-red-700 border-red-200";
  if (s === "medium") return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-gray-50 text-gray-600 border-gray-200";
}

function ActionRow({
  id,
  state,
  busy,
  onAction,
  applyLabel = "Apply as draft change",
}: {
  id: string;
  state?: ActionState;
  busy: boolean;
  onAction: (id: string, state: ActionState) => void;
  applyLabel?: string;
}) {
  if (state === "applied") {
    return (
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-700">
          <ShieldCheck className="h-3.5 w-3.5" />
          Applied as draft change · logged for review
        </div>
        <button
          type="button"
          onClick={() => onAction(id, "open")}
          className="text-[11px] text-violet-600 hover:underline"
        >
          undo locally
        </button>
      </div>
    );
  }
  if (state === "dismissed") {
    return (
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] text-gray-500">Dismissed · logged for audit</div>
        <button
          type="button"
          onClick={() => onAction(id, "open")}
          className="text-[11px] text-violet-600 hover:underline"
        >
          undo locally
        </button>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <Button size="sm" disabled={busy} onClick={() => onAction(id, "applied")} className="gap-1.5">
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
        {applyLabel}
      </Button>
      <Button variant="outline" size="sm" disabled={busy} onClick={() => onAction(id, "dismissed")}>
        Dismiss
      </Button>
    </div>
  );
}

function RecommendationsTab({
  data,
  states,
  busyId,
  onAction,
}: {
  data: IntelligenceRecommendation[];
  states: Record<string, ActionState>;
  busyId: string | null;
  onAction: (id: string, s: ActionState) => void;
}) {
  if (data.length === 0) {
    return <EmptyState message="No recommendations — the script looks healthy on the heuristics we run." />;
  }
  return (
    <div className="space-y-3">
      <p className="text-[11px] text-gray-500">
        Combined view of the highest-impact suggestions. Each is explainable, scoped to a script
        location, and applied only as a draft change.
      </p>
      {data.map((r) => (
        <div key={r.id} className="rounded-lg border border-gray-200 p-3">
          <div className="mb-1.5 flex items-start justify-between gap-2">
            <p className="text-xs font-semibold text-gray-800">{r.title}</p>
            <div className="flex shrink-0 items-center gap-1.5">
              <span
                className={cn(
                  "rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                  severityClasses(r.severity),
                )}
              >
                {r.severity}
              </span>
              <span className="rounded-md bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700">
                {r.confidence}% conf.
              </span>
            </div>
          </div>
          <p className="text-[11px] leading-relaxed text-gray-600">{r.description}</p>
          <p className="mt-2 text-[11px] leading-relaxed text-gray-700">
            <span className="font-semibold">Proposal: </span>
            {r.proposal}
          </p>
          <p className="mt-1 text-[10px] font-mono text-gray-400">{r.related}</p>
          <div className="mt-2">
            <ActionRow id={r.id} state={states[r.id]} busy={busyId === r.id} onAction={onAction} />
          </div>
        </div>
      ))}
    </div>
  );
}

function LocatorsTab({
  data,
  states,
  busyId,
  onAction,
}: {
  data: IntelligenceLocator[];
  states: Record<string, ActionState>;
  busyId: string | null;
  onAction: (id: string, s: ActionState) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-violet-100 bg-violet-50/50 p-3 text-[11px] text-violet-800">
        <p className="font-semibold">Locator recommendation priority</p>
        <ol className="mt-1 ml-4 list-decimal space-y-0.5">
          <li>data-testid</li>
          <li>Semantic role + accessible name</li>
          <li>Stable label</li>
          <li>Stable attribute</li>
          <li>CSS or XPath only as fallback</li>
        </ol>
      </div>
      {data.length === 0 ? (
        <EmptyState message="No fragile locators detected. Either the script uses stable selectors, or our analyzers missed something — check the script tab and let us know." />
      ) : (
        data.map((l) => (
          <div key={l.id} className="rounded-lg border border-gray-200 p-3">
            <div className="grid grid-cols-2 gap-3 text-[11px]">
              <div>
                <p className="font-semibold text-gray-500">Current locator</p>
                <p className="mt-0.5 font-mono text-gray-800 break-all">{l.current}</p>
                <Badge
                  variant={l.current_confidence < 50 ? "destructive" : "warning"}
                  className="mt-1 text-[10px]"
                >
                  {l.current_confidence}% stability
                </Badge>
              </div>
              <div>
                <p className="font-semibold text-emerald-700">Suggested locator</p>
                <p className="mt-0.5 font-mono text-emerald-900 break-all">{l.suggested}</p>
                <Badge variant="success" className="mt-1 text-[10px]">
                  {l.suggested_confidence}% confidence
                </Badge>
              </div>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-gray-600">
              <span className="font-semibold">Why: </span>
              {l.rationale}
            </p>
            <div className="mt-2">
              <ActionRow id={l.id} state={states[l.id]} busy={busyId === l.id} onAction={onAction} />
            </div>
          </div>
        ))
      )}
    </div>
  );
}

function AssertionsTab({
  data,
  states,
  busyId,
  onAction,
}: {
  data: IntelligenceAssertion[];
  states: Record<string, ActionState>;
  busyId: string | null;
  onAction: (id: string, s: ActionState) => void;
}) {
  if (data.length === 0) {
    return <EmptyState message="No assertion gaps detected." />;
  }
  return (
    <div className="space-y-3">
      <p className="text-[11px] text-gray-500">
        Business actions found in the script without a corresponding verification. Adding these
        is additive — existing assertions stay.
      </p>
      {data.map((a) => (
        <div key={a.id} className="rounded-lg border border-gray-200 p-3 space-y-2">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
            <div>
              <p className="text-xs font-semibold text-gray-800">{a.scenario}</p>
              <p className="text-[11px] text-gray-600">{a.missing}</p>
            </div>
          </div>
          <p className="text-[11px] leading-relaxed text-gray-700">
            <span className="font-semibold">Suggestion: </span>
            {a.suggestion}
          </p>
          <ActionRow
            id={a.id}
            state={states[a.id]}
            busy={busyId === a.id}
            onAction={onAction}
            applyLabel="Add validation draft"
          />
        </div>
      ))}
    </div>
  );
}

function TestDataTab({
  data,
  states,
  busyId,
  onAction,
}: {
  data: IntelligenceDataIssue[];
  states: Record<string, ActionState>;
  busyId: string | null;
  onAction: (id: string, s: ActionState) => void;
}) {
  const iconFor = (kind: IntelligenceDataIssue["kind"]) => {
    if (kind === "hardcoded") return Code2;
    if (kind === "unmasked") return Lock;
    if (kind === "expired") return Clock;
    return DatabaseIcon;
  };
  const labelFor = (kind: IntelligenceDataIssue["kind"]) => {
    if (kind === "hardcoded") return "Hardcoded data";
    if (kind === "unmasked") return "Unmasked credentials";
    if (kind === "expired") return "Expired data";
    return "Environment leak";
  };
  if (data.length === 0) {
    return <EmptyState message="No data-hygiene issues detected." />;
  }
  return (
    <div className="space-y-3">
      <p className="text-[11px] text-gray-500">
        Data-hygiene issues found in the script and its fixtures.
      </p>
      {data.map((d) => {
        const Icon = iconFor(d.kind);
        return (
          <div key={d.id} className="rounded-lg border border-gray-200 p-3 space-y-2">
            <div className="flex items-center gap-2">
              <Icon className="h-3.5 w-3.5 text-amber-600" />
              <span className="text-xs font-semibold text-gray-800">{labelFor(d.kind)}</span>
            </div>
            <p className="text-[11px] text-gray-600">{d.description}</p>
            <p className="text-[11px] leading-relaxed text-gray-700">
              <span className="font-semibold">Proposal: </span>
              {d.proposal}
            </p>
            <ActionRow id={d.id} state={states[d.id]} busy={busyId === d.id} onAction={onAction} />
          </div>
        );
      })}
    </div>
  );
}

function ApiDbTab({
  data,
  states,
  busyId,
  onAction,
}: {
  data: IntelligenceCheck[];
  states: Record<string, ActionState>;
  busyId: string | null;
  onAction: (id: string, s: ActionState) => void;
}) {
  if (data.length === 0) {
    return <EmptyState message="No additive backend checks suggested for this script." />;
  }
  return (
    <div className="space-y-3">
      <p className="text-[11px] text-gray-500">
        Additive backend checks the AI thinks would strengthen this test. Nothing here removes
        an existing assertion.
      </p>
      {data.map((c) => (
        <div key={c.id} className="rounded-lg border border-gray-200 p-3 space-y-2">
          <div className="flex items-center gap-2">
            <Badge variant="info" className="text-[10px]">{c.layer}</Badge>
            <span className="text-xs font-semibold text-gray-800">{c.title}</span>
          </div>
          <p className="text-[11px] leading-relaxed text-gray-600">{c.details}</p>
          <ActionRow
            id={c.id}
            state={states[c.id]}
            busy={busyId === c.id}
            onAction={onAction}
            applyLabel="Add check as draft"
          />
        </div>
      ))}
    </div>
  );
}

function HealthTab({ data }: { data: IntelligenceHealth }) {
  const tone = data.overall >= 85 ? "text-emerald-600" : data.overall >= 70 ? "text-amber-600" : "text-red-600";
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-gray-200 p-4">
        <div className="flex items-baseline justify-between">
          <p className="text-xs font-semibold text-gray-700">Script health</p>
          <p className={cn("text-3xl font-bold tabular-nums", tone)}>
            {data.overall}
            <span className="ml-1 text-sm font-normal text-gray-400">/ 100</span>
          </p>
        </div>
        <p className="mt-1 text-[11px] text-gray-500">
          Composite score with every contributing dimension explained below.
        </p>
      </div>
      <div className="space-y-2">
        {data.parts.map((p) => (
          <div key={p.label} className="rounded-lg border border-gray-200 p-3">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-gray-800">{p.label}</span>
              <span className="tabular-nums text-gray-700">{p.value}</span>
            </div>
            <div className="mt-1.5 h-1.5 w-full rounded-full bg-gray-100">
              <div
                className={cn(
                  "h-full rounded-full",
                  p.value >= 85 ? "bg-emerald-500" : p.value >= 70 ? "bg-amber-500" : "bg-red-500",
                )}
                style={{ width: `${p.value}%` }}
              />
            </div>
            <p className="mt-1.5 text-[11px] text-gray-500">{p.note}</p>
          </div>
        ))}
      </div>
      <p className="flex items-start gap-1.5 text-[11px] text-gray-400">
        <ChevronRight className="mt-0.5 h-3 w-3 shrink-0" />
        Score is recomputed each time you reopen the assistant after editing the script.
      </p>
    </div>
  );
}
