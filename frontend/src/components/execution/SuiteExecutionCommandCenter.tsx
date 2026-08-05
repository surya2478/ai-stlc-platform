"use client";

/**
 * UI-046 Suite Execution Command Center.
 *
 * Layout follows the approved reference image's content region — status strip,
 * three panels, operations bar — inside the existing application shell. The
 * image's own sidebar and header are a design mock and are not reproduced;
 * delivery rule 4 and contract Section 2.1.1 both point the other way.
 *
 * Three things this screen must never do, each enforced below rather than left to
 * good intentions:
 *
 * 1. Show a total it cannot justify. When the backend reports
 *    `reconciled: false`, the strip says "Status data delayed" instead of
 *    displaying counts that do not add up (Section 4.3).
 * 2. Claim a control took effect before the backend acknowledged it. Controls
 *    disable while a request is in flight and the lifecycle badge only changes
 *    when a poll returns the new state (Section 14.9).
 * 3. Imply captured evidence that does not exist. The inspector's application
 *    view is labelled as the last captured frame with its timestamp, never as a
 *    live feed (Section 2.1.6), and deferred evidence types state why they are
 *    unavailable.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  AlertTriangle,
  Ban,
  Check,
  ChevronRight,
  Copy,
  FileText,
  Pause,
  Play,
  Square,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { useSuiteRunLive } from "@/hooks/useSuiteRunLive";
import {
  suiteExecutionApi,
  type ExecutionItemResult,
  type SuiteRunControlAction,
  type SuiteRunIdentity,
  type SuiteRunItem,
  type SuiteRunEvidence,
  type SuiteRunItemDetail,
  type SuiteRunSummary,
} from "@/lib/api";
import {
  AXIS_LABEL,
  ConnectionBadge,
  ItemLifecyclePill,
  LifecycleBadge,
  RESULT_TONE,
  ResultPill,
  formatClock,
  formatDuration,
  formatElapsed,
  priorityClass,
} from "@/components/execution/suite-execution-shared";

const PAGE_SIZE = 100;

/** Section 4.1's interactive status cards, in the reference image's order. */
const STATUS_CARDS: {
  key: keyof SuiteRunSummary["counts"];
  result: ExecutionItemResult | null;
  label: string;
  /** Section 4.1: Skipped shows only when non-zero. */
  onlyWhenNonZero?: boolean;
}[] = [
  { key: "passed", result: "PASS", label: "Passed" },
  { key: "failed", result: "FAIL", label: "Failed" },
  { key: "inconclusive", result: "INCONCLUSIVE", label: "Inconclusive" },
  { key: "blocked", result: "BLOCKED", label: "Blocked" },
  {
    key: "environment_failure",
    result: "ENVIRONMENT_FAILURE",
    label: "Environment",
    onlyWhenNonZero: true,
  },
  { key: "data_failure", result: "DATA_FAILURE", label: "Data", onlyWhenNonZero: true },
  {
    key: "automation_failure",
    result: "AUTOMATION_FAILURE",
    label: "Harness",
    onlyWhenNonZero: true,
  },
  {
    key: "policy_blocked",
    result: "POLICY_BLOCKED",
    label: "Policy",
    onlyWhenNonZero: true,
  },
  { key: "skipped", result: "SKIPPED", label: "Skipped", onlyWhenNonZero: true },
  { key: "running", result: null, label: "Running" },
  { key: "queued", result: null, label: "Queued" },
];

/** Section 5.1's saved views, expressed as the filters they actually apply. */
const SAVED_VIEWS: {
  id: string;
  label: string;
  results?: ExecutionItemResult[];
  lifecycle?: string[];
}[] = [
  { id: "all", label: "All tests" },
  {
    id: "attention",
    label: "Needs attention",
    results: [
      "FAIL",
      "INCONCLUSIVE",
      "BLOCKED",
      "ENVIRONMENT_FAILURE",
      "DATA_FAILURE",
      "AUTOMATION_FAILURE",
      "POLICY_BLOCKED",
    ],
  },
  { id: "running", label: "Running now", lifecycle: ["RUNNING", "STARTING"] },
  { id: "failed", label: "Failed or inconclusive", results: ["FAIL", "INCONCLUSIVE"] },
  { id: "blocked", label: "Blocked by dependency", results: ["BLOCKED", "POLICY_BLOCKED"] },
];

export function SuiteExecutionCommandCenter({ runId }: { runId: number }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast } = useToast();
  const live = useSuiteRunLive(runId);

  // ── URL-reflected state (Section 12) ─────────────────────────────────────
  const selectedItemId = searchParams.get("item")
    ? Number(searchParams.get("item"))
    : null;
  const activeView = searchParams.get("view") ?? "all";
  const statusFilters = useMemo(
    () => (searchParams.get("status") ?? "").split(",").filter(Boolean),
    [searchParams],
  );
  const journeyFilter = searchParams.get("journey");
  const frameworkFilter = searchParams.get("framework");
  const priorityFilter = searchParams.get("priority");
  const search = searchParams.get("q") ?? "";

  const setParams = useCallback(
    (updates: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value == null || value === "") next.delete(key);
        else next.set(key, value);
      }
      // replace, not push: filtering is not navigation, and stacking history
      // entries would make Back feel broken.
      router.replace(`?${next.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  const [searchDraft, setSearchDraft] = useState(search);
  useEffect(() => setSearchDraft(search), [search]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (searchDraft !== search) setParams({ q: searchDraft || null });
    }, 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft]);

  const savedView = SAVED_VIEWS.find((v) => v.id === activeView) ?? SAVED_VIEWS[0];
  // An explicit status-card selection overrides the saved view's own result set.
  const effectiveResults = useMemo(
    () => (statusFilters.length > 0 ? statusFilters : savedView.results),
    [statusFilters, savedView.results],
  );
  // A fresh array literal every render would give `loadItems` a new identity on
  // every render and refire its effect in a loop. These string keys are the
  // stable dependency.
  const resultsKey = (effectiveResults ?? []).join(",");
  const lifecycleKey = (savedView.lifecycle ?? []).join(",");

  // ── Matrix rows ──────────────────────────────────────────────────────────
  const [items, setItems] = useState<SuiteRunItem[]>([]);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const [totalMatching, setTotalMatching] = useState(0);
  const [itemsError, setItemsError] = useState<string | null>(null);

  const loadItems = useCallback(
    async (cursor: number, append: boolean) => {
      try {
        const { data } = await suiteExecutionApi.items(runId, {
          cursor,
          limit: PAGE_SIZE,
          result: effectiveResults,
          lifecycle_state: savedView.lifecycle,
          search: search || undefined,
          journey: journeyFilter ?? undefined,
          framework: frameworkFilter ?? undefined,
          priority: priorityFilter ?? undefined,
        });
        setItems((previous) => (append ? [...previous, ...data.items] : data.items));
        setNextCursor(data.next_cursor);
        setTotalMatching(data.total_matching);
        setItemsError(null);
      } catch (caught) {
        setItemsError(
          caught instanceof Error ? caught.message : "Could not load the test matrix.",
        );
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [runId, resultsKey, lifecycleKey, search, journeyFilter, frameworkFilter, priorityFilter],
  );

  // Refetch when filters change, and on each successful poll so in-flight rows
  // advance. `revision` is the poll heartbeat.
  useEffect(() => {
    void loadItems(0, false);
  }, [loadItems, live.revision]);

  // ── Inspector ────────────────────────────────────────────────────────────
  const [detail, setDetail] = useState<SuiteRunItemDetail | null>(null);
  useEffect(() => {
    if (selectedItemId == null) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    void suiteExecutionApi
      .item(runId, selectedItemId)
      .then(({ data }) => {
        if (!cancelled) setDetail(data);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, selectedItemId, live.revision]);

  // ── Controls ─────────────────────────────────────────────────────────────
  const [controlInFlight, setControlInFlight] = useState<SuiteRunControlAction | null>(null);

  const runControl = useCallback(
    async (action: SuiteRunControlAction, reason?: string) => {
      if (!live.identity) return;
      setControlInFlight(action);
      try {
        const { data } = await suiteExecutionApi.control(runId, {
          action,
          reason,
          // Optimistic concurrency: if the run moved on since this screen last
          // polled, the backend refuses rather than applying a stale decision.
          expectedRunVersion: live.identity.run_version,
        });
        toast({ title: `Accepted (${data.commandId})`, description: data.message });
        live.refresh();
      } catch (caught) {
        const detailPayload = (
          caught as { response?: { data?: { detail?: { code?: string; message?: string } } } }
        )?.response?.data?.detail;
        toast({
          variant: "error",
          title: detailPayload?.code ?? "Control refused",
          description:
            detailPayload?.message ??
            (caught instanceof Error ? caught.message : "The control request failed."),
        });
        // A refusal usually means our view is stale; re-read immediately.
        live.refresh();
      } finally {
        setControlInFlight(null);
      }
    },
    [runId, live, toast],
  );

  const downloadEvidence = useCallback(
    async (evidence: SuiteRunEvidence) => {
      try {
        const { data } = await suiteExecutionApi.evidence(runId, evidence.id);
        const url = URL.createObjectURL(data);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${evidence.evidence_type}-${evidence.id}`;
        link.click();
        URL.revokeObjectURL(url);
      } catch (error) {
        // The server refuses unmaskable artifacts where policy says so, and
        // refuses any artifact whose bytes no longer match its capture
        // checksum. Both are answers the operator needs, not noise to swallow.
        const detail = await readBlobErrorDetail(error);
        toast({
          variant: "error",
          title: "Evidence not available",
          description: detail ?? "The evidence could not be downloaded.",
        });
      }
    },
    [runId, toast],
  );

  const requestWithReason = useCallback(
    (action: SuiteRunControlAction, prompt: string) => {
      const reason = window.prompt(prompt);
      // Cancelling the dialog is not a reason, and the backend would refuse it.
      if (reason == null || !reason.trim()) return;
      void runControl(action, reason.trim());
    },
    [runControl],
  );

  // ── Keyboard behaviour (Section 13) ──────────────────────────────────────
  // Bound at the window rather than to the table, so j/k work as soon as the
  // screen is open instead of requiring the operator to click into the grid
  // first.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      // Never hijack typing.
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;

      if (event.key === "Escape") {
        setParams({ item: null });
        return;
      }
      if (!["j", "k", "ArrowDown", "ArrowUp"].includes(event.key)) return;
      if (items.length === 0) return;
      event.preventDefault();
      const currentIndex = items.findIndex((i) => i.id === selectedItemId);
      const delta = event.key === "j" || event.key === "ArrowDown" ? 1 : -1;
      const nextIndex =
        currentIndex === -1
          ? 0
          : Math.min(items.length - 1, Math.max(0, currentIndex + delta));
      setParams({ item: String(items[nextIndex].id) });
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [items, selectedItemId, setParams]);

  const identity = live.identity;
  const summary = live.summary;

  if (live.loading && !identity) {
    return (
      <div className="flex h-64 items-center justify-center text-xs text-gray-500">
        Loading execution run…
      </div>
    );
  }

  if (!identity) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-xs text-red-700">
        {live.error ?? "This execution run could not be loaded."}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-3">
      <RunHeader
        identity={identity}
        connection={live.connection}
        controlInFlight={controlInFlight}
        onControl={runControl}
        onControlWithReason={requestWithReason}
      />

      {identity.lifecycle_state === "BLOCKED_BEFORE_START" && (
        <ReadinessBlockerPanel identity={identity} />
      )}

      {summary && <StatusStrip
        summary={summary}
        statusFilters={statusFilters}
        onToggleStatus={(result) => {
          const next = statusFilters.includes(result)
            ? statusFilters.filter((r) => r !== result)
            : [...statusFilters, result];
          setParams({ status: next.join(",") || null });
        }}
        onClear={() => setParams({ status: null, view: null })}
      />}

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(240px,280px)_minmax(0,1fr)_minmax(340px,400px)] gap-3">
        <SuiteStructurePanel
          searchDraft={searchDraft}
          onSearchChange={setSearchDraft}
          activeView={activeView}
          onViewChange={(id) => setParams({ view: id === "all" ? null : id, status: null })}
          tree={live.tree}
          journeyFilter={journeyFilter}
          onJourneyChange={(journey) => setParams({ journey })}
          frameworks={identity.frameworks}
          frameworkFilter={frameworkFilter}
          onFrameworkChange={(framework) => setParams({ framework })}
          priorityFilter={priorityFilter}
          onPriorityChange={(priority) => setParams({ priority })}
        />

        <ExecutionMatrix
          items={items}
          totalMatching={totalMatching}
          selectedItemId={selectedItemId}
          error={itemsError}
          hasMore={nextCursor != null}
          onSelect={(id) => setParams({ item: String(id) })}
          onLoadMore={() => nextCursor != null && void loadItems(nextCursor, true)}
        />

        <InspectorPanel
          detail={detail}
          selectedItemId={selectedItemId}
          events={live.events}
          onDownloadEvidence={downloadEvidence}
        />
      </div>

      <OperationsBar
        identity={identity}
        summary={summary}
        connection={live.connection}
        pollLatencyMs={live.pollLatencyMs}
        lastSuccessfulPoll={live.lastSuccessfulPoll}
        newestEvent={live.events[0]?.occurred_at ?? null}
      />
    </div>
  );
}

// ─── Header ──────────────────────────────────────────────────────────────────

function RunHeader({
  identity,
  connection,
  controlInFlight,
  onControl,
  onControlWithReason,
}: {
  identity: SuiteRunIdentity;
  connection: React.ComponentProps<typeof ConnectionBadge>["state"];
  controlInFlight: SuiteRunControlAction | null;
  onControl: (action: SuiteRunControlAction) => void;
  onControlWithReason: (action: SuiteRunControlAction, prompt: string) => void;
}) {
  const { toast } = useToast();
  const [showDetails, setShowDetails] = useState(false);
  const [elapsed, setElapsed] = useState(() =>
    formatElapsed(identity.started_at, identity.completed_at),
  );

  // A ticking clock only while the run is live; a finished run's elapsed time is
  // fixed and re-rendering it every second would be pointless work.
  useEffect(() => {
    if (identity.is_terminal) {
      setElapsed(formatElapsed(identity.started_at, identity.completed_at));
      return;
    }
    const timer = window.setInterval(
      () => setElapsed(formatElapsed(identity.started_at, identity.completed_at)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [identity.started_at, identity.completed_at, identity.is_terminal]);

  const busy = controlInFlight != null;
  const canPause = identity.lifecycle_state === "RUNNING" && identity.can_control;
  const canResume = identity.lifecycle_state === "PAUSED" && identity.can_control;

  return (
    <header className="rounded-lg border border-gray-200 bg-white p-4">
      <nav className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">
        <Link href="/automation?view=workspace" className="hover:text-gray-600">
          Automation
        </Link>
        <ChevronRight className="h-3 w-3" />
        <Link href="/execution" className="hover:text-gray-600">
          Execution
        </Link>
        <ChevronRight className="h-3 w-3" />
        <span className="text-gray-600">Live</span>
      </nav>

      <div className="mt-1.5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {/* The suite name, not the screen name: an operator needs to know
                which run they are looking at (contract Section 2.1.2). */}
            <h1 className="truncate text-lg font-bold text-gray-900">
              {identity.suite_name ?? `Run ${identity.execution_id}`}
            </h1>
            <LifecycleBadge state={identity.lifecycle_state} />
            <ConnectionBadge state={connection} />
            {identity.outcome && (
              <Badge
                variant={identity.outcome === "PASS" ? "success" : "warning"}
                className="text-[9px]"
              >
                {RESULT_TONE[identity.outcome]?.label ?? identity.outcome}
              </Badge>
            )}
          </div>

          <dl className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-[11px] text-gray-600">
            <MetaField label="Suite snapshot">
              {identity.suite_version != null ? `v${identity.suite_version}` : "—"}
            </MetaField>
            <MetaField label="Run">
              <button
                type="button"
                className="inline-flex items-center gap-1 font-semibold hover:text-[#B71920]"
                onClick={() => {
                  void navigator.clipboard.writeText(identity.execution_id);
                  toast({ title: "Run ID copied", description: identity.execution_id });
                }}
              >
                {identity.execution_id}
                <Copy className="h-3 w-3" />
              </button>
            </MetaField>
            <MetaField label="Environment">{identity.environment ?? "—"}</MetaField>
            <MetaField label="Frameworks">
              {identity.frameworks.length === 0
                ? "—"
                : identity.frameworks.length === 1
                  ? identity.frameworks[0]
                  : `Mixed (${identity.frameworks.length})`}
            </MetaField>
            <MetaField label="Elapsed">
              <span className="font-mono">{elapsed}</span>
            </MetaField>
          </dl>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {canPause && (
            <Button
              size="sm"
              disabled={busy}
              onClick={() => onControl("PAUSE_AFTER_CURRENT")}
              title="No further test cases are dispatched. The test in flight finishes first."
            >
              <Pause className="mr-1.5 h-3.5 w-3.5" />
              {controlInFlight === "PAUSE_AFTER_CURRENT"
                ? "Requesting…"
                : "Pause after current test"}
            </Button>
          )}
          {canResume && (
            <Button size="sm" disabled={busy} onClick={() => onControl("RESUME")}>
              <Play className="mr-1.5 h-3.5 w-3.5" />
              {controlInFlight === "RESUME" ? "Requesting…" : "Resume execution"}
            </Button>
          )}
          {identity.is_terminal && (
            <Button size="sm" variant="outline" disabled title="UI-052 is not implemented yet.">
              <FileText className="mr-1.5 h-3.5 w-3.5" />
              Open execution report
            </Button>
          )}

          {!identity.is_terminal && identity.can_control && (
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() =>
                onControlWithReason(
                  "STOP_GRACEFULLY",
                  "Why are you stopping this run? The current test completes and results are finalized.",
                )
              }
            >
              <Square className="mr-1.5 h-3 w-3" />
              Stop gracefully
            </Button>
          )}
          {!identity.is_terminal && identity.can_cancel && (
            <Button
              size="sm"
              variant="destructive"
              disabled={busy}
              onClick={() =>
                onControlWithReason(
                  "CANCEL_NOW",
                  "Why are you cancelling? Runners and queued work are terminated; captured evidence is kept.",
                )
              }
            >
              <X className="mr-1.5 h-3.5 w-3.5" />
              Cancel now
            </Button>
          )}
          {/* Section 9.5. Disabled with the reason rather than hidden, so the
              capability is discoverable and its absence is explained. */}
          <Button
            size="sm"
            variant="ghost"
            disabled
            title="Emergency stop requires the project-wide kill path delivered with P2-S1 Operational Command Centre. Use 'Cancel now'."
          >
            <Ban className="mr-1.5 h-3.5 w-3.5" />
            Emergency stop
          </Button>

          <Button
            size="sm"
            variant="ghost"
            onClick={() => setShowDetails((open) => !open)}
            title="Run provenance and contract details"
          >
            ⋮
          </Button>
        </div>
      </div>

      {showDetails && (
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-md border border-gray-200 bg-gray-50 p-3 text-[11px] text-gray-600 md:grid-cols-3">
          <MetaField label="Purpose">{identity.execution_purpose ?? "Not stated"}</MetaField>
          <MetaField label="Trigger">{identity.trigger_source ?? "—"}</MetaField>
          <MetaField label="Triggered by">
            {identity.triggered_by_name ?? (identity.triggered_by ? `User ${identity.triggered_by}` : "—")}
          </MetaField>
          <MetaField label="Started">
            {identity.started_at ? formatClock(identity.started_at) : "Not started"}
          </MetaField>
          <MetaField label="Parallel runners">
            {identity.parallel_limit} allowed
          </MetaField>
          <MetaField label="Correlation">
            <span className="font-mono text-[10px]">{identity.correlation_id ?? "—"}</span>
          </MetaField>
          <MetaField label="Snapshot checksum">
            {/* Truncated for width; the full value is in the title so the
                integrity check stays verifiable. */}
            <span className="font-mono text-[10px]" title={identity.snapshot_checksum ?? ""}>
              {identity.snapshot_checksum
                ? `${identity.snapshot_checksum.slice(0, 16)}…`
                : "—"}
            </span>
          </MetaField>
          <MetaField label="Run version">{identity.run_version}</MetaField>
          {identity.pending_command && (
            <MetaField label="Pending command">{identity.pending_command}</MetaField>
          )}
        </dl>
      )}
    </header>
  );
}

function MetaField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="text-[9px] font-bold uppercase tracking-wide text-gray-400">{label}</dt>
      <dd className="font-semibold text-gray-700">{children}</dd>
    </div>
  );
}

function ReadinessBlockerPanel({ identity }: { identity: SuiteRunIdentity }) {
  const readiness = identity.readiness;
  if (!readiness) return null;
  return (
    <section className="rounded-lg border border-red-200 bg-red-50 p-3">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-red-600" />
        <h2 className="text-xs font-bold text-red-800">
          This run cannot start — {readiness.blockers.length} readiness blocker
          {readiness.blockers.length === 1 ? "" : "s"}
        </h2>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {Object.entries(readiness.axes).map(([axis, ready]) => (
          <Badge key={axis} variant={ready ? "success" : "destructive"} className="text-[9px]">
            {AXIS_LABEL[axis] ?? axis}
          </Badge>
        ))}
      </div>
      <ul className="mt-2 space-y-1">
        {readiness.blockers.map((blocker) => (
          <li key={blocker.name} className="text-[11px] text-red-700">
            <span className="font-semibold">{AXIS_LABEL[blocker.axis] ?? blocker.axis}:</span>{" "}
            {blocker.detail}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10px] text-red-600">
        No test case was dispatched. Nothing has been marked failed — a readiness
        blocker is not a test result.
      </p>
    </section>
  );
}

// ─── Status strip ────────────────────────────────────────────────────────────

function StatusStrip({
  summary,
  statusFilters,
  onToggleStatus,
  onClear,
}: {
  summary: SuiteRunSummary;
  statusFilters: string[];
  onToggleStatus: (result: string) => void;
  onClear: () => void;
}) {
  const visibleCards = STATUS_CARDS.filter(
    (card) => !card.onlyWhenNonZero || summary.counts[card.key] > 0,
  );

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-4">
        <div className="min-w-[180px]">
          <p className="text-[9px] font-bold uppercase tracking-wide text-gray-400">
            Suite completion
          </p>
          {summary.reconciled ? (
            <>
              <p className="text-lg font-bold leading-tight text-gray-900">
                {summary.completed} of {summary.total}
                <span className="ml-2 text-xs font-semibold text-[#B71920]">
                  {summary.completion_percent}%
                </span>
              </p>
              <SegmentedRail summary={summary} />
            </>
          ) : (
            // Section 4.3 — never render a total the backend cannot justify.
            <p
              className="mt-1 text-xs font-bold text-amber-700"
              title={summary.reconciliation_detail ?? undefined}
            >
              Status data delayed
            </p>
          )}
        </div>

        <div className="flex flex-1 flex-wrap gap-1.5">
          {visibleCards.map((card) => {
            const count = summary.counts[card.key];
            const filterable = card.result != null;
            const active = card.result != null && statusFilters.includes(card.result);
            const tone = card.result ? RESULT_TONE[card.result] : null;
            return (
              <button
                key={card.key}
                type="button"
                disabled={!filterable}
                aria-pressed={active}
                aria-label={`${card.label}: ${count}`}
                onClick={() => card.result && onToggleStatus(card.result)}
                title={
                  filterable
                    ? `Filter the matrix to ${card.label.toLowerCase()}`
                    : `${card.label} is a lifecycle state, not a result — filter it from the saved views`
                }
                className={cn(
                  "min-w-[74px] rounded-md border px-2.5 py-1.5 text-left transition",
                  active
                    ? "border-[#B71920] bg-app-brand-75 ring-1 ring-[#B71920]"
                    : "border-gray-200 bg-white",
                  filterable ? "hover:border-gray-300" : "cursor-default opacity-90",
                )}
              >
                <span className="block text-base font-bold leading-none text-gray-900">
                  {count}
                </span>
                <span
                  className={cn(
                    "mt-0.5 block text-[9px] font-bold uppercase tracking-wide",
                    tone?.text ?? "text-gray-500",
                  )}
                >
                  {card.label}
                </span>
              </button>
            );
          })}
          {statusFilters.length > 0 && (
            <button
              type="button"
              onClick={onClear}
              className="self-center text-[10px] font-semibold text-[#B71920] underline"
            >
              Clear filters
            </button>
          )}
        </div>

        <div className="flex gap-4 border-l border-gray-200 pl-4">
          <Metric
            label="Parallel runners"
            value={`${summary.parallel_in_use} / ${summary.parallel_allowed}`}
          />
          <Metric
            label="Evidence quorum"
            value={`${summary.evidence_captured} / ${summary.evidence_required}`}
            tone={
              summary.evidence_required > 0 &&
              summary.evidence_captured < summary.evidence_required
                ? "text-amber-600"
                : undefined
            }
          />
          <div>
            <p className="text-[9px] font-bold uppercase tracking-wide text-gray-400">
              Environment
            </p>
            <p
              className={cn(
                "flex items-center gap-1 text-xs font-bold",
                summary.environment_ready ? "text-emerald-600" : "text-amber-600",
              )}
            >
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  summary.environment_ready ? "bg-emerald-500" : "bg-amber-500",
                )}
              />
              {summary.environment_ready ? "Ready" : "Not confirmed"}
            </p>
          </div>
        </div>
      </div>

      <p className="mt-2 text-[11px] text-gray-600">{summary.operational_message}</p>
    </section>
  );
}

/** Section 4.1 — segmented by final result, not one flat bar. */
function SegmentedRail({ summary }: { summary: SuiteRunSummary }) {
  const segments = STATUS_CARDS.filter((c) => c.result != null && c.result !== "PENDING").map(
    (card) => ({
      key: card.key,
      count: summary.counts[card.key],
      bar: RESULT_TONE[card.result as ExecutionItemResult].bar,
    }),
  );
  return (
    <div className="mt-1.5 flex h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
      {segments.map((segment) =>
        segment.count === 0 ? null : (
          <div
            key={segment.key}
            className={segment.bar}
            style={{ width: `${(segment.count / Math.max(1, summary.total)) * 100}%` }}
          />
        ),
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div>
      <p className="text-[9px] font-bold uppercase tracking-wide text-gray-400">{label}</p>
      <p className={cn("text-xs font-bold text-gray-800", tone)}>{value}</p>
    </div>
  );
}

// ─── Left panel ──────────────────────────────────────────────────────────────

function SuiteStructurePanel({
  searchDraft,
  onSearchChange,
  activeView,
  onViewChange,
  tree,
  journeyFilter,
  onJourneyChange,
  frameworks,
  frameworkFilter,
  onFrameworkChange,
  priorityFilter,
  onPriorityChange,
}: {
  searchDraft: string;
  onSearchChange: (value: string) => void;
  activeView: string;
  onViewChange: (id: string) => void;
  tree: React.ComponentProps<typeof JourneyNode>["node"][];
  journeyFilter: string | null;
  onJourneyChange: (journey: string | null) => void;
  frameworks: string[];
  frameworkFilter: string | null;
  onFrameworkChange: (framework: string | null) => void;
  priorityFilter: string | null;
  onPriorityChange: (priority: string | null) => void;
}) {
  return (
    <aside className="flex min-h-0 flex-col gap-3 overflow-y-auto rounded-lg border border-gray-200 bg-white p-3">
      <div>
        <label htmlFor="matrix-search" className="sr-only">
          Search test cases or errors
        </label>
        <input
          id="matrix-search"
          value={searchDraft}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Search ID, objective or error…"
          className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-[11px] outline-none focus:border-[#B71920]"
        />
      </div>

      <nav>
        <p className="mb-1 text-[9px] font-bold uppercase tracking-wide text-gray-400">
          Saved views
        </p>
        <ul className="space-y-0.5">
          {SAVED_VIEWS.map((view) => (
            <li key={view.id}>
              <button
                type="button"
                onClick={() => onViewChange(view.id)}
                aria-current={activeView === view.id}
                className={cn(
                  "w-full rounded px-2 py-1 text-left text-[11px] font-semibold transition",
                  activeView === view.id
                    ? "bg-app-brand-75 text-[#B71920]"
                    : "text-gray-600 hover:bg-gray-50",
                )}
              >
                {view.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <div>
        <p className="mb-1 text-[9px] font-bold uppercase tracking-wide text-gray-400">
          Business journeys
        </p>
        {tree.length === 0 ? (
          <p className="text-[10px] text-gray-400">
            No journey grouping — these test cases are not linked to scenarios.
          </p>
        ) : (
          <ul className="space-y-0.5">
            <li>
              <button
                type="button"
                onClick={() => onJourneyChange(null)}
                className={cn(
                  "w-full rounded px-2 py-1 text-left text-[11px] font-semibold",
                  journeyFilter == null ? "bg-app-brand-75 text-[#B71920]" : "text-gray-600",
                )}
              >
                Complete suite
              </button>
            </li>
            {tree.map((node) => (
              <JourneyNode
                key={node.journey}
                node={node}
                active={journeyFilter === node.journey}
                onSelect={() => onJourneyChange(node.journey)}
              />
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-2 border-t border-gray-100 pt-2">
        <p className="text-[9px] font-bold uppercase tracking-wide text-gray-400">
          Quick filters
        </p>
        <FilterSelect
          label="Framework"
          value={frameworkFilter}
          options={frameworks}
          onChange={onFrameworkChange}
        />
        <FilterSelect
          label="Priority"
          value={priorityFilter}
          options={["Very Critical", "Critical", "High", "Medium", "Low"]}
          onChange={onPriorityChange}
        />
      </div>
    </aside>
  );
}

function JourneyNode({
  node,
  active,
  onSelect,
}: {
  node: {
    journey: string;
    total: number;
    complete: number;
    worst_result: ExecutionItemResult | null;
    children: { framework: string; total: number; complete: number }[];
  };
  active: boolean;
  onSelect: () => void;
}) {
  const percent = node.total === 0 ? 0 : (node.complete / node.total) * 100;
  const tone = node.worst_result ? RESULT_TONE[node.worst_result] : null;
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "w-full rounded px-2 py-1 text-left transition hover:bg-gray-50",
          active && "bg-app-brand-75",
        )}
      >
        <span className="flex items-center justify-between gap-2">
          <span
            className={cn(
              "truncate text-[11px] font-semibold",
              active ? "text-[#B71920]" : "text-gray-700",
            )}
          >
            {node.journey}
          </span>
          {tone && <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", tone.dot)} />}
        </span>
        <span className="mt-0.5 flex items-center gap-2">
          <span className="text-[9px] text-gray-400">
            {node.complete} / {node.total} complete
          </span>
          <span className="h-1 flex-1 overflow-hidden rounded-full bg-gray-200">
            <span className="block h-full bg-[#B71920]" style={{ width: `${percent}%` }} />
          </span>
        </span>
      </button>
      {node.children.length > 1 && (
        <ul className="ml-3 mt-0.5 space-y-0.5">
          {node.children.map((child) => (
            <li
              key={child.framework}
              className="flex items-center justify-between text-[9px] text-gray-400"
            >
              <span className="truncate">{child.framework}</span>
              <span>
                {child.complete} / {child.total}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string | null;
  options: string[];
  onChange: (value: string | null) => void;
}) {
  return (
    <label className="block">
      <span className="text-[9px] font-semibold text-gray-500">{label}</span>
      <select
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value || null)}
        className="mt-0.5 w-full rounded-md border border-gray-200 px-2 py-1 text-[11px] outline-none focus:border-[#B71920]"
      >
        <option value="">All</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

// ─── Centre matrix ───────────────────────────────────────────────────────────

function ExecutionMatrix({
  items,
  totalMatching,
  selectedItemId,
  error,
  hasMore,
  onSelect,
  onLoadMore,
}: {
  items: SuiteRunItem[];
  totalMatching: number;
  selectedItemId: number | null;
  error: string | null;
  hasMore: boolean;
  onSelect: (id: number) => void;
  onLoadMore: () => void;
}) {
  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="flex items-center justify-between border-b border-gray-200 px-3 py-2">
        <h2 className="text-[10px] font-bold uppercase tracking-wide text-gray-500">
          Test execution matrix
        </h2>
        <span className="text-[10px] text-gray-400">
          Showing {items.length} of {totalMatching}
        </span>
      </div>

      {error && (
        <p className="border-b border-amber-200 bg-amber-50 px-3 py-1.5 text-[10px] text-amber-700">
          {error}
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse text-[11px]">
          <thead className="sticky top-0 z-10 bg-gray-50">
            <tr className="text-left text-[9px] font-bold uppercase tracking-wide text-gray-500">
              <th className="w-10 px-2 py-1.5">#</th>
              <th className="px-2 py-1.5">Test case</th>
              <th className="px-2 py-1.5">Journey</th>
              <th className="px-2 py-1.5">Priority</th>
              <th className="px-2 py-1.5">Framework</th>
              <th className="px-2 py-1.5">Runner</th>
              <th className="px-2 py-1.5">Lifecycle</th>
              <th className="px-2 py-1.5">Result</th>
              <th className="px-2 py-1.5">Steps</th>
              <th className="px-2 py-1.5">Try</th>
              <th className="px-2 py-1.5">Evidence</th>
              <th className="px-2 py-1.5">Duration</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={12} className="px-3 py-6 text-center text-[11px] text-gray-400">
                  No test case matches the current filters.
                </td>
              </tr>
            ) : (
              items.map((item) => {
                const selected = item.id === selectedItemId;
                const running =
                  item.lifecycle_state === "RUNNING" || item.lifecycle_state === "STARTING";
                return (
                  <tr
                    key={item.id}
                    onClick={() => onSelect(item.id)}
                    aria-selected={selected}
                    className={cn(
                      "cursor-pointer border-b border-gray-100 transition",
                      selected
                        ? "bg-app-brand-75"
                        : running
                          ? "bg-app-brand-75/40 hover:bg-app-brand-75/70"
                          : "hover:bg-gray-50",
                    )}
                  >
                    <td className="px-2 py-1.5 text-gray-400">{item.order_index}</td>
                    <td className="px-2 py-1.5">
                      <span className="block font-bold text-gray-800">
                        {item.test_case_key ?? `#${item.test_case_id ?? "—"}`}
                      </span>
                      <span className="block max-w-[26rem] truncate text-[10px] text-gray-500">
                        {item.title ?? "No title in the published snapshot"}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-gray-600">{item.journey ?? "—"}</td>
                    <td className={cn("px-2 py-1.5 font-bold", priorityClass(item.priority))}>
                      {item.priority ?? "—"}
                    </td>
                    <td className="px-2 py-1.5 text-gray-600">{item.framework ?? "—"}</td>
                    <td className="px-2 py-1.5 text-[10px] text-gray-500">
                      {item.runner_name ?? "—"}
                    </td>
                    <td className="px-2 py-1.5">
                      <ItemLifecyclePill item={item} />
                    </td>
                    <td className="px-2 py-1.5">
                      <ResultPill result={item.result} reason={item.attention_reason} />
                    </td>
                    <td className="px-2 py-1.5 text-gray-600">
                      {/* No runner reports per-step progress, so there is no
                          completion count to show against the declared total.
                          "0 / 9" would read as "failed on step one", which is a
                          different and wrong claim. */}
                      {item.steps_total === 0 ? (
                        "—"
                      ) : (
                        <span
                          className="text-gray-400"
                          title={`${item.steps_total} steps declared by the Automation IR. No runner reports per-step progress, so per-step completion is not tracked yet.`}
                        >
                          {item.steps_total} declared
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-gray-500">
                      {item.attempt} / {item.attempts_allowed}
                    </td>
                    <td
                      className={cn(
                        "px-2 py-1.5",
                        item.evidence_required > 0 &&
                          item.evidence_captured < item.evidence_required
                          ? "font-bold text-amber-600"
                          : "text-gray-600",
                      )}
                      title={
                        item.evidence_required > 0
                          ? `${item.evidence_captured} of ${item.evidence_required} mandatory artifacts captured; ${item.evidence_total_captured} retained in total.`
                          : `No mandatory evidence was declared by the Automation IR. ${item.evidence_total_captured} artifact(s) were captured and retained.`
                      }
                    >
                      {/* Mandatory shortfall drives the quorum, but a test with
                          no declared requirement can still have real artifacts —
                          hiding them behind a dash would understate the evidence. */}
                      {item.evidence_required > 0
                        ? `${item.evidence_captured} / ${item.evidence_required}`
                        : item.evidence_total_captured > 0
                          ? `${item.evidence_total_captured} kept`
                          : "—"}
                    </td>
                    <td className="px-2 py-1.5 font-mono text-[10px] text-gray-500">
                      {formatDuration(item.duration_ms)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {hasMore && (
          <div className="p-2 text-center">
            <Button size="sm" variant="outline" onClick={onLoadMore}>
              Load next {PAGE_SIZE}
            </Button>
          </div>
        )}
      </div>
    </section>
  );
};

/** Pull the FastAPI `detail` out of a failed blob request.
 *
 *  With `responseType: "blob"` the error body arrives as a Blob too, so the
 *  usual `response.data.detail` read yields nothing and the operator sees a
 *  generic failure instead of the actual reason — which for evidence is always
 *  the useful part (policy refusal, checksum mismatch, artifact gone). */
async function readBlobErrorDetail(error: unknown): Promise<string | null> {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  try {
    if (data instanceof Blob) {
      const parsed = JSON.parse(await data.text());
      return typeof parsed?.detail === "string" ? parsed.detail : null;
    }
    if (data && typeof (data as { detail?: unknown }).detail === "string") {
      return (data as { detail: string }).detail;
    }
  } catch {
    return null;
  }
  return null;
}

// ─── Inspector ───────────────────────────────────────────────────────────────

function InspectorPanel({
  detail,
  selectedItemId,
  events,
  onDownloadEvidence,
}: {
  detail: SuiteRunItemDetail | null;
  selectedItemId: number | null;
  events: { sequence: number; event_type: string; message: string; occurred_at: string }[];
  onDownloadEvidence: (evidence: SuiteRunEvidence) => void;
}) {
  if (selectedItemId == null) {
    return (
      <aside className="flex min-h-0 flex-col overflow-y-auto rounded-lg border border-gray-200 bg-white p-3">
        <p className="text-[11px] text-gray-400">
          Select a test case to inspect its steps, assertions and evidence.
        </p>
        <EventTimeline events={events} />
      </aside>
    );
  }

  if (!detail) {
    return (
      <aside className="rounded-lg border border-gray-200 bg-white p-3 text-[11px] text-gray-400">
        Loading test details…
      </aside>
    );
  }

  const { item } = detail;
  const pendingAssertions = detail.assertions.filter((a) => a.passed == null).length;
  const failedAssertions = detail.assertions.filter((a) => a.passed === false);
  // Every evaluated assertion came from the test-level verdict rather than from
  // a per-assertion report. Sound, but the reader should not take the count as
  // evidence each expectation was checked individually.
  const evaluated = detail.assertions.filter((a) => a.passed != null);
  const allInferred =
    evaluated.length > 0 &&
    evaluated.every((a) => a.evaluation_source === "runner_verdict");

  return (
    <aside className="flex min-h-0 flex-col gap-3 overflow-y-auto rounded-lg border border-gray-200 bg-white p-3">
      <div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-bold text-[#B71920]">
            {item.test_case_key ?? `#${item.test_case_id}`}
          </span>
          <ItemLifecyclePill item={item} />
          <ResultPill result={item.result} reason={item.attention_reason} />
        </div>
        <h3 className="mt-0.5 text-sm font-bold text-gray-900">
          {item.title ?? "No title in the published snapshot"}
        </h3>
        <div className="mt-1.5 flex flex-wrap gap-1">
          {item.framework && (
            <Badge variant="secondary" className="text-[9px]">
              {item.framework}
            </Badge>
          )}
          {detail.script_id != null && (
            <Badge variant="outline" className="text-[9px]">
              Script #{detail.script_id}
            </Badge>
          )}
          {detail.test_case_version != null && (
            <Badge variant="outline" className="text-[9px]">
              TC v{detail.test_case_version}
            </Badge>
          )}
          <Badge variant="outline" className="text-[9px]">
            Attempt {item.attempt} of {item.attempts_allowed}
          </Badge>
        </div>
        {item.attention_reason && (
          <p className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-[10px] text-amber-800">
            {item.attention_reason}
          </p>
        )}
        {detail.error_message && (
          <pre className="mt-1.5 max-h-24 overflow-auto rounded border border-gray-200 bg-gray-50 p-2 text-[9px] text-gray-700">
            {detail.error_message}
          </pre>
        )}
      </div>

      <Section
        title={`Steps${item.steps_total ? ` — ${item.steps_total} declared` : ""}`}
      >
        {detail.current_step ? (
          <div className="rounded border border-gray-200 bg-gray-50 p-2">
            <p className="text-[11px] font-bold text-gray-800">
              {detail.current_step.action_text ?? `Step ${detail.current_step.step_number}`}
            </p>
            {detail.current_step.expected_text && (
              <p className="mt-0.5 text-[10px] text-gray-600">
                Expected: {detail.current_step.expected_text}
              </p>
            )}
            <p className="mt-1 text-[9px] text-gray-400">
              {detail.current_step.application_context ?? "No application context recorded"}
              {detail.current_step.elapsed_ms != null &&
                ` · ${formatDuration(detail.current_step.elapsed_ms)}`}
            </p>
          </div>
        ) : (
          <p className="text-[10px] text-gray-400">
            {item.steps_total === 0
              ? "No steps were declared by the Automation IR for this test."
              : // Not "no step has started yet" — that implies one will be
                // reported shortly. Nothing reports step state at all, so the
                // absence is structural rather than a matter of timing.
                `${item.steps_total} steps are declared for this test. Per-step execution state is not reported by the runner, so no step detail is available.`}
          </p>
        )}
      </Section>

      <Section title="Last captured application view">
        {/* Section 2.1.6 — a last-captured frame, never presented as live. */}
        {detail.latest_screenshot_evidence_id != null ? (
          <div className="rounded border border-gray-200 bg-gray-50 p-2 text-[10px] text-gray-600">
            Screenshot captured
            {detail.latest_screenshot_captured_at
              ? ` at ${formatClock(detail.latest_screenshot_captured_at)}`
              : ""}
            . Artifacts are served through the authenticated, masked download once
            UI-052 Execution Report and Evidence is implemented.
          </div>
        ) : (
          <p className="text-[10px] text-gray-400">
            No screenshot has been captured for this test yet. This pane shows the
            most recent captured frame — the platform has no live browser feed.
          </p>
        )}
      </Section>

      <Section title="Assertions and evidence">
        <div className="grid grid-cols-2 gap-2 text-[10px]">
          <Stat
            label="Assertions passed"
            value={`${item.assertions_passed} / ${item.assertions_total}`}
          />
          <Stat
            // Mirrors the matrix column: with no mandatory evidence declared,
            // "0 / 0" beside a list of five artifacts reads as a contradiction.
            label={item.evidence_required > 0 ? "Mandatory evidence" : "Evidence captured"}
            value={
              item.evidence_required > 0
                ? `${item.evidence_captured} / ${item.evidence_required}`
                : `${item.evidence_total_captured} kept`
            }
            tone={detail.quorum_met ? undefined : "text-amber-600"}
          />
          <Stat
            label="Pending assertions"
            value={String(pendingAssertions)}
            tone={pendingAssertions > 0 ? "text-amber-600" : undefined}
          />
          <Stat
            label="Evidence quorum"
            value={detail.quorum_met ? "Met" : "Not met"}
            tone={detail.quorum_met ? "text-emerald-600" : "text-amber-600"}
          />
        </div>

        {detail.quorum_missing.length > 0 && (
          <p className="mt-1.5 text-[10px] text-amber-700">
            Missing mandatory evidence: {detail.quorum_missing.join(", ")}.
          </p>
        )}

        {item.assertions_total === 0 && (
          <p className="mt-1.5 rounded border border-gray-200 bg-gray-50 p-2 text-[10px] text-gray-600">
            This test declares no mandatory assertion, so a green runner cannot
            produce a pass. Accepted checkpoints in the Automation IR are what
            become assertions.
          </p>
        )}

        {allInferred && (
          <p className="mt-1.5 text-[10px] text-gray-500">
            Assertion verdicts are inferred from the test-level result: the
            runner fails the whole test when any assertion fails, but does not
            report which one. Per-assertion attribution arrives with adapter
            step telemetry.
          </p>
        )}

        {failedAssertions.length > 0 && (
          <ul className="mt-1.5 space-y-1">
            {failedAssertions.map((assertion) => (
              <li
                key={assertion.id}
                className="rounded border border-red-200 bg-red-50 p-1.5 text-[10px] text-red-700"
              >
                <span className="font-bold">{assertion.description}</span>
                <span className="block">
                  Expected {assertion.expected_value ?? "—"} · actual{" "}
                  {assertion.actual_value ?? "not captured"}
                </span>
              </li>
            ))}
          </ul>
        )}

        <ul className="mt-1.5 space-y-1">
          {detail.evidence.map((evidence) => (
            <li key={evidence.id} className="flex items-start gap-1.5 text-[10px]">
              {evidence.status === "captured" ? (
                <Check className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />
              ) : (
                <AlertTriangle
                  className={cn(
                    "mt-0.5 h-3 w-3 shrink-0",
                    evidence.mandatory ? "text-amber-500" : "text-gray-300",
                  )}
                />
              )}
              <span className="min-w-0">
                <span className="font-semibold text-gray-700">
                  {evidence.evidence_type}
                  {evidence.mandatory ? " (mandatory)" : ""}
                </span>
                {evidence.payload_entry_count != null && (
                  <span className="text-gray-400"> · {evidence.payload_entry_count} entries</span>
                )}
                {evidence.downloadable && (
                  <button
                    type="button"
                    className="ml-1.5 font-semibold text-[#B71920] hover:underline"
                    onClick={() => onDownloadEvidence(evidence)}
                    title={
                      evidence.redaction_state === "not_maskable"
                        ? "A screenshot, video or trace cannot be masked. The server refuses this download where deployment policy says so."
                        : "Downloaded through the masking pass."
                    }
                  >
                    Download
                  </button>
                )}
                {/* Stating this on the row rather than only in the tooltip: an
                    artifact that could not be masked is the one a reader most
                    needs to be told about before opening it. */}
                {evidence.redaction_state === "not_maskable" && (
                  <span className="ml-1 text-amber-600">not masked</span>
                )}
                {evidence.unavailable_reason && (
                  <span className="block text-gray-500">{evidence.unavailable_reason}</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <EventTimeline events={events} />
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-gray-100 pt-2">
      <h4 className="mb-1 text-[9px] font-bold uppercase tracking-wide text-gray-400">
        {title}
      </h4>
      {children}
    </section>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <p className="text-[9px] text-gray-400">{label}</p>
      <p className={cn("text-[11px] font-bold text-gray-800", tone)}>{value}</p>
    </div>
  );
}

function EventTimeline({
  events,
}: {
  events: { sequence: number; event_type: string; message: string; occurred_at: string }[];
}) {
  return (
    <Section title="Latest events">
      {events.length === 0 ? (
        <p className="text-[10px] text-gray-400">
          The run is ready. Waiting for the first runner event.
        </p>
      ) : (
        <ol className="space-y-1.5">
          {events.slice(0, 20).map((event) => (
            <li key={event.sequence} className="flex gap-2 text-[10px]">
              <span className="shrink-0 font-mono text-gray-400">
                {formatClock(event.occurred_at)}
              </span>
              <span className="min-w-0">
                <span className="block font-semibold text-gray-700">
                  {event.event_type.replace(/_/g, " ")}
                </span>
                <span className="block text-gray-500">{event.message}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </Section>
  );
}

// ─── Operations bar ──────────────────────────────────────────────────────────

function OperationsBar({
  identity,
  summary,
  connection,
  pollLatencyMs,
  lastSuccessfulPoll,
  newestEvent,
}: {
  identity: SuiteRunIdentity;
  summary: SuiteRunSummary | null;
  connection: React.ComponentProps<typeof ConnectionBadge>["state"];
  pollLatencyMs: number | null;
  lastSuccessfulPoll: Date | null;
  newestEvent: string | null;
}) {
  return (
    <footer className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-[10px] text-gray-500">
      <span className="flex items-center gap-1.5">
        <ConnectionBadge state={connection} />
        {/* Measured poll round-trip. There is no socket, so reporting "stream
            latency" would be inventing a number. */}
        <span title="Measured poll round-trip time">
          Poll {pollLatencyMs != null ? `${pollLatencyMs}ms` : "—"}
        </span>
      </span>
      <span>
        Runners{" "}
        <strong className="text-gray-700">
          {summary ? `${summary.parallel_in_use} of ${summary.parallel_allowed}` : "—"}
        </strong>
      </span>
      <span>
        Queued <strong className="text-gray-700">{summary?.queue_depth ?? "—"}</strong>
      </span>
      <span>
        Evidence{" "}
        <strong className="text-gray-700">
          {summary ? `${summary.evidence_captured} / ${summary.evidence_required}` : "—"}
        </strong>
      </span>
      <span title="Derived from the persisted readiness verdict for this run">
        Environment{" "}
        <strong className={summary?.environment_ready ? "text-emerald-600" : "text-amber-600"}>
          {summary?.environment_ready ? "Ready" : "Not confirmed"}
        </strong>
      </span>
      <span className="ml-auto">
        {newestEvent ? `Last backend event ${formatClock(newestEvent)}` : "No events yet"}
        {lastSuccessfulPoll && ` · read ${formatClock(lastSuccessfulPoll.toISOString())}`}
        {identity.is_terminal && " · run finished, polling stopped"}
      </span>
    </footer>
  );
}
