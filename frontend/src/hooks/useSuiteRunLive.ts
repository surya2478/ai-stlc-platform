"use client";

/**
 * UI-046 live data. Polling, not a socket — this platform has no SSE or
 * WebSocket transport, and the two existing live screens poll a database state
 * machine for the same reason (contract Section 2.1.7).
 *
 * The correctness properties Section 14.8 asks for come from the cursor, not from
 * the transport:
 *
 * - `after` is the highest sequence number already seen, so a poll returns
 *   exactly the events that happened since. A dropped poll widens the gap; it
 *   cannot lose or duplicate an event.
 * - A failed poll never clears state (Section 10, "Reconnecting"). Counts are
 *   kept and the connection badge degrades instead, because zeroing a suite's
 *   progress because one request timed out would be actively misleading.
 * - Polling stops on a terminal run. There is nothing further to learn, and a
 *   command center left open overnight should not keep hitting the backend.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import {
  suiteExecutionApi,
  type SuiteRunEvent,
  type SuiteRunIdentity,
  type SuiteRunSummary,
  type SuiteTreeNode,
} from "@/lib/api";
import type { ConnectionState } from "@/components/execution/suite-execution-shared";

const POLL_INTERVAL_MS = 2500;
// Beyond this, the newest backend event is old enough that calling the view
// "live" would overstate it.
const STALE_EVENT_SECONDS = 20;
const MAX_RETAINED_EVENTS = 200;

export interface SuiteRunLive {
  identity: SuiteRunIdentity | null;
  summary: SuiteRunSummary | null;
  tree: SuiteTreeNode[];
  events: SuiteRunEvent[];
  connection: ConnectionState;
  /** Measured poll round-trip, which is what the operations bar reports. There is
   *  no socket latency to show. */
  pollLatencyMs: number | null;
  lastSuccessfulPoll: Date | null;
  loading: boolean;
  error: string | null;
  /** Bumped on every successful poll so dependent panels can refetch. */
  revision: number;
  refresh: () => void;
}

export function useSuiteRunLive(runId: number | null): SuiteRunLive {
  const [identity, setIdentity] = useState<SuiteRunIdentity | null>(null);
  const [summary, setSummary] = useState<SuiteRunSummary | null>(null);
  const [tree, setTree] = useState<SuiteTreeNode[]>([]);
  const [events, setEvents] = useState<SuiteRunEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("RECONNECTING");
  const [pollLatencyMs, setPollLatencyMs] = useState<number | null>(null);
  const [lastSuccessfulPoll, setLastSuccessfulPoll] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  // Cursor lives in a ref, not state: a re-render must not rewind it and
  // re-deliver events the UI has already shown.
  const cursorRef = useRef(0);
  const inFlightRef = useRef(false);
  const consecutiveFailuresRef = useRef(0);

  const poll = useCallback(async () => {
    if (runId == null || inFlightRef.current) return;
    inFlightRef.current = true;
    const startedAt = performance.now();
    try {
      const [identityRes, summaryRes, treeRes, eventsRes] = await Promise.all([
        suiteExecutionApi.get(runId),
        suiteExecutionApi.summary(runId),
        suiteExecutionApi.tree(runId),
        suiteExecutionApi.events(runId, cursorRef.current),
      ]);

      setPollLatencyMs(Math.round(performance.now() - startedAt));
      setIdentity(identityRes.data);
      setSummary(summaryRes.data);
      setTree(treeRes.data);

      const page = eventsRes.data;
      if (page.events.length > 0) {
        cursorRef.current = page.events[page.events.length - 1].sequence;
        setEvents((previous) =>
          // Newest first for the timeline (Section 7.5), capped so a long run
          // does not grow this list without bound.
          [...page.events].reverse().concat(previous).slice(0, MAX_RETAINED_EVENTS),
        );
      }

      const age = page.newest_event_age_seconds;
      const terminal = identityRes.data.is_terminal;
      setConnection(
        terminal
          ? "OFFLINE_SNAPSHOT"
          : age != null && age > STALE_EVENT_SECONDS
            ? "DELAYED"
            : "LIVE",
      );
      consecutiveFailuresRef.current = 0;
      setLastSuccessfulPoll(new Date());
      setError(null);
      setRevision((r) => r + 1);
    } catch (caught) {
      // Deliberately does not clear identity/summary/events: Section 10 requires
      // the last known data to stay on screen with a visible stale marker.
      consecutiveFailuresRef.current += 1;
      setConnection(
        consecutiveFailuresRef.current >= 4 ? "OFFLINE_SNAPSHOT" : "RECONNECTING",
      );
      const message =
        caught instanceof Error ? caught.message : "Could not reach the execution API.";
      // Only surface an error once the run has never loaded; a transient failure
      // mid-run is communicated by the connection badge instead of an alarm.
      setError((previous) => (identity == null ? message : previous));
    } finally {
      inFlightRef.current = false;
      setLoading(false);
    }
  }, [runId, identity]);

  useEffect(() => {
    if (runId == null) return;
    // Reset when the run changes so one run's cursor cannot suppress another's
    // events.
    cursorRef.current = 0;
    consecutiveFailuresRef.current = 0;
    setEvents([]);
    setIdentity(null);
    setLoading(true);
    void poll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  useEffect(() => {
    if (runId == null) return;
    // A terminal run has nothing left to report.
    if (identity?.is_terminal) return;
    const timer = window.setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [runId, identity?.is_terminal, poll]);

  return {
    identity,
    summary,
    tree,
    events,
    connection,
    pollLatencyMs,
    lastSuccessfulPoll,
    loading,
    error,
    revision,
    refresh: () => void poll(),
  };
}
