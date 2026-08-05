"use client";

// UI-019 Live Recorder — Section 12's right/bottom activity panel.
//
// Network reuses UI-017's parsed network events rather than re-parsing the
// capture files: a recording *is* a discovery session, so the API that
// already owns that parsing works on it unchanged.

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Camera,
  Check,
  FileText,
  Loader2,
  MessageSquare,
  Network,
  Target,
  Terminal,
  Trash2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  networkExplorerApi,
  recorderApi,
  type NetworkEvent,
  type RecordedAction,
  type RecorderCapture,
  type RecorderCheckpoint,
  type RecorderStep,
  type RecorderStepMapping,
} from "@/lib/api";
import {
  useCheckpointMutations,
  useMappingMutations,
  useNoteMutations,
  useRecorderNotes,
} from "@/lib/queries/recorder";
import { cn } from "@/lib/utils";
import { EmptyRow, formatDateTime, messageFromError } from "@/components/automation/suite-shared";
import { ConfidenceChip, actionFamilyLabel } from "@/components/automation/recorder-shared";

export type ActivityTab = "actions" | "network" | "console" | "locators" | "evidence" | "notes";

export const ACTIVITY_TABS: { id: ActivityTab; label: string; icon: typeof Target }[] = [
  { id: "actions", label: "Actions", icon: Target },
  { id: "network", label: "Network", icon: Network },
  { id: "console", label: "Console", icon: Terminal },
  { id: "locators", label: "Locators", icon: Target },
  { id: "evidence", label: "Evidence", icon: Camera },
  { id: "notes", label: "Notes", icon: MessageSquare },
];

const TH = "px-2 py-1.5 text-[9px] font-extrabold uppercase tracking-wide text-gray-500";
const TD = "px-2 py-1.5 text-[10px] font-semibold text-gray-600";

interface ActivityProps {
  projectId: number;
  sessionId: number;
  actions: RecordedAction[];
  mappings: RecorderStepMapping[];
  steps: RecorderStep[];
  checkpoints: RecorderCheckpoint[];
  captures: RecorderCapture[];
  selectedActionId: number | null;
  onSelectAction: (actionId: number) => void;
  editable: boolean;
}

export function RecorderActivityTabs(props: ActivityProps & { tab: ActivityTab }) {
  switch (props.tab) {
    case "actions":
      return <ActionsTab {...props} />;
    case "network":
      return <NetworkTab sessionId={props.sessionId} actions={props.actions} />;
    case "console":
      return <ConsoleTab sessionId={props.sessionId} captures={props.captures} />;
    case "locators":
      return <LocatorsTab actions={props.actions} onSelectAction={props.onSelectAction} />;
    case "evidence":
      return <EvidenceTab sessionId={props.sessionId} captures={props.captures} />;
    case "notes":
      return <NotesTab projectId={props.projectId} sessionId={props.sessionId} editable={props.editable} />;
    default:
      return null;
  }
}

// ── Actions (Section 12.1) ───────────────────────────────────────────────────

function ActionsTab({
  projectId,
  sessionId,
  actions,
  mappings,
  steps,
  selectedActionId,
  onSelectAction,
  editable,
}: ActivityProps) {
  const { map, update } = useMappingMutations(projectId, sessionId);
  const [error, setError] = useState<string | null>(null);
  const mappingByAction = useMemo(
    () => new Map(mappings.map((mapping) => [mapping.action_id, mapping])),
    [mappings],
  );

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(messageFromError(err));
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {error && (
        <p className="border-b border-red-100 bg-red-50 px-3 py-1.5 text-[10px] font-bold text-red-700">
          {error}
        </p>
      )}
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full text-left">
          <thead className="sticky top-0 bg-white">
            <tr className="border-b border-gray-200">
              {["#", "Time", "Action", "Element", "Step", "Locator", "Evidence", "IR"].map((heading) => (
                <th key={heading} className={TH}>
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {actions.length === 0 ? (
              <EmptyRow colSpan={8} message="No actions recorded yet." />
            ) : (
              actions.map((action) => {
                const mapping = mappingByAction.get(action.id);
                const isSensitive =
                  (action.input_binding as { text?: string } | null)?.text ===
                  "[REDACTED - sensitive field]";
                return (
                  <tr
                    key={action.id}
                    onClick={() => onSelectAction(action.id)}
                    className={cn(
                      "cursor-pointer border-b border-gray-100 last:border-0 hover:bg-gray-50",
                      selectedActionId === action.id && "bg-app-brand-75/60",
                      action.inclusion_state !== "included" && "opacity-50",
                    )}
                  >
                    <td className={cn(TD, "font-extrabold text-gray-800")}>{action.sequence}</td>
                    <td className={TD}>
                      {new Date(action.occurred_at).toLocaleTimeString(undefined, {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </td>
                    <td className={TD}>
                      <Badge variant="secondary" className="text-[9px]">
                        {actionFamilyLabel(action.action_family)}
                      </Badge>
                    </td>
                    <td className={cn(TD, "max-w-[220px] truncate")} title={action.target_semantic ?? ""}>
                      {action.target_semantic ?? "—"}
                      {isSensitive && (
                        <Badge variant="warning" className="ml-1 text-[8px]" title="Value was not persisted.">
                          redacted
                        </Badge>
                      )}
                    </td>
                    <td className={TD} onClick={(event) => event.stopPropagation()}>
                      {editable ? (
                        <select
                          value={mapping?.step_key ?? ""}
                          onChange={(event) =>
                            run(() =>
                              map.mutateAsync({
                                actionId: action.id,
                                stepKey: event.target.value || null,
                              }),
                            )
                          }
                          className="rounded border border-gray-200 bg-white px-1 py-0.5 text-[10px] font-bold text-gray-700"
                        >
                          <option value="">Unmapped</option>
                          {steps.map((step) => (
                            <option key={step.step_key} value={step.step_key}>
                              {step.step_key}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span>{mapping?.step_key ?? "—"}</span>
                      )}
                    </td>
                    <td className={TD}>
                      {action.action_family === "click" || action.action_family === "input" ? (
                        <ConfidenceChip confidence={action.locator_confidence} />
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className={TD}>{action.evidence_refs?.length ?? 0}</td>
                    <td className={TD} onClick={(event) => event.stopPropagation()}>
                      {mapping ? (
                        <button
                          type="button"
                          disabled={!editable}
                          title={
                            mapping.excluded_from_ir
                              ? mapping.exclusion_reason ?? "Excluded from the Automation IR."
                              : "Included in the Automation IR. Click to exclude."
                          }
                          onClick={() =>
                            run(() =>
                              update.mutateAsync({
                                actionId: action.id,
                                excluded_from_ir: !mapping.excluded_from_ir,
                                exclusion_reason: mapping.excluded_from_ir
                                  ? null
                                  : "Excluded by reviewer during recording.",
                              }),
                            )
                          }
                          className="text-[10px] font-bold"
                        >
                          {mapping.excluded_from_ir ? (
                            <span className="text-gray-400">excluded</span>
                          ) : (
                            <span className="text-emerald-600">included</span>
                          )}
                        </button>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Network (Section 12.2) — UI-017's parsed events ──────────────────────────

function NetworkTab({ sessionId, actions }: { sessionId: number; actions: RecordedAction[] }) {
  const [events, setEvents] = useState<NetworkEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [failedOnly, setFailedOnly] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    networkExplorerApi
      .events(sessionId)
      .then((response) => !cancelled && setEvents(response.data))
      .catch((err) => !cancelled && setError(messageFromError(err)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [sessionId, actions.length]);

  const rows = useMemo(() => {
    const all = events ?? [];
    return failedOnly ? all.filter((e) => (e.status_code ?? 0) >= 400) : all;
  }, [events, failedOnly]);

  if (loading && events === null) {
    return <PanelMessage>Loading network activity…</PanelMessage>;
  }
  if (error) {
    return <PanelMessage tone="error">{error}</PanelMessage>;
  }
  if ((events ?? []).length === 0) {
    return (
      <PanelMessage>
        No network activity has been parsed for this recording yet. It is parsed when the recording is
        stopped.
      </PanelMessage>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 border-b border-gray-100 px-3 py-1.5">
        <label className="flex items-center gap-1.5 text-[10px] font-bold text-gray-600">
          <input
            type="checkbox"
            checked={failedOnly}
            onChange={(event) => setFailedOnly(event.target.checked)}
          />
          Failed only
        </label>
        <span className="text-[10px] font-semibold text-gray-400">
          {rows.length} of {events?.length} request(s)
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full text-left">
          <thead className="sticky top-0 bg-white">
            <tr className="border-b border-gray-200">
              {["Method", "Host", "Path", "Status", "External"].map((heading) => (
                <th key={heading} className={TH}>
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <EmptyRow colSpan={5} message="No requests match this filter." />
            ) : (
              rows.map((event) => (
                <tr key={event.id} className="border-b border-gray-100 last:border-0">
                  <td className={cn(TD, "font-extrabold text-gray-800")}>{event.method ?? "—"}</td>
                  <td className={cn(TD, "max-w-[180px] truncate")} title={event.host ?? ""}>
                    {event.host ?? "—"}
                  </td>
                  <td className={cn(TD, "max-w-[260px] truncate")} title={event.path ?? event.raw_line}>
                    {event.parse_state === "parsed" ? event.path ?? "—" : event.raw_line}
                  </td>
                  <td className={TD}>
                    {event.status_code === null ? (
                      <span className="text-gray-300">—</span>
                    ) : (
                      <Badge
                        variant={event.status_code >= 400 ? "destructive" : "success"}
                        className="text-[9px]"
                      >
                        {event.status_code}
                      </Badge>
                    )}
                  </td>
                  <td className={TD}>{event.is_external ? "yes" : "no"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Console (Section 12.3) ───────────────────────────────────────────────────

function ConsoleTab({ sessionId, captures }: { sessionId: number; captures: RecorderCapture[] }) {
  const consoleCaptures = useMemo(
    () => captures.filter((capture) => capture.capture_type === "console_log"),
    [captures],
  );
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const latest = consoleCaptures[consoleCaptures.length - 1];

  useEffect(() => {
    if (!latest) {
      setText(null);
      return;
    }
    let cancelled = false;
    // The recorder writes console captures per action; the discovery capture
    // content endpoint already serves them masked.
    recorderApi
      .captures(sessionId, latest.action_id ?? undefined)
      .then(() =>
        fetch(`/api/v1/discovery/sessions/${sessionId}/captures/${latest.id}/content`, {
          credentials: "include",
        }),
      )
      .then((response) => (response.ok ? response.text() : Promise.reject(new Error("Not available"))))
      .then((body) => !cancelled && setText(body))
      .catch((err) => !cancelled && setError(messageFromError(err)));
    return () => {
      cancelled = true;
    };
  }, [latest, sessionId]);

  if (consoleCaptures.length === 0) {
    return <PanelMessage>No console output has been captured for this recording.</PanelMessage>;
  }
  if (error) {
    return <PanelMessage tone="error">{error}</PanelMessage>;
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto p-3">
      <p className="mb-2 text-[10px] font-bold text-gray-500">
        {consoleCaptures.length} console capture(s) — showing the most recent. Secrets are masked before
        the capture is written to disk.
      </p>
      <pre className="whitespace-pre-wrap break-words rounded-lg border border-gray-200 bg-gray-50 p-2 font-mono text-[10px] leading-relaxed text-gray-700">
        {text ?? "Loading…"}
      </pre>
    </div>
  );
}

// ── Locators (Section 12.4) ──────────────────────────────────────────────────

function LocatorsTab({
  actions,
  onSelectAction,
}: {
  actions: RecordedAction[];
  onSelectAction: (actionId: number) => void;
}) {
  const rows = useMemo(
    () => actions.filter((action) => (action.locator_evidence?.candidates?.length ?? 0) > 0),
    [actions],
  );

  if (rows.length === 0) {
    return (
      <PanelMessage>
        No locator candidates yet. They are captured for click and type actions against real elements.
      </PanelMessage>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <table className="w-full text-left">
        <thead className="sticky top-0 bg-white">
          <tr className="border-b border-gray-200">
            {["#", "Element", "Strategy", "Locator", "Confidence", "Unique", "Validated"].map((heading) => (
              <th key={heading} className={TH}>
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.flatMap((action) =>
            (action.locator_evidence?.candidates ?? []).map((candidate, index) => (
              <tr
                key={`${action.id}-${candidate.strategy}-${index}`}
                onClick={() => onSelectAction(action.id)}
                className="cursor-pointer border-b border-gray-100 last:border-0 hover:bg-gray-50"
              >
                <td className={cn(TD, "font-extrabold text-gray-800")}>
                  {index === 0 ? action.sequence : ""}
                </td>
                <td className={cn(TD, "max-w-[160px] truncate")}>
                  {index === 0 ? action.locator_evidence?.element_name ?? "—" : ""}
                </td>
                <td className={TD}>
                  <Badge variant={index === 0 ? "success" : "outline"} className="text-[9px]">
                    {candidate.strategy}
                  </Badge>
                </td>
                <td
                  className={cn(TD, "max-w-[300px] truncate font-mono")}
                  title={candidate.locator}
                >
                  {candidate.locator}
                </td>
                <td className={TD}>
                  <ConfidenceChip confidence={candidate.confidence} />
                </td>
                <td className={TD}>{candidate.unique ? "yes" : "no"}</td>
                <td className={TD}>
                  {candidate.validated ? (
                    "live-checked"
                  ) : (
                    <span title="Could not be counted on the live page — scored lower as a result.">
                      unverified
                    </span>
                  )}
                </td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── Evidence (Section 12.5) ──────────────────────────────────────────────────

function EvidenceTab({ sessionId, captures }: { sessionId: number; captures: RecorderCapture[] }) {
  if (captures.length === 0) {
    return <PanelMessage>No evidence has been captured yet.</PanelMessage>;
  }
  const byType = captures.reduce<Record<string, RecorderCapture[]>>((acc, capture) => {
    (acc[capture.capture_type] ??= []).push(capture);
    return acc;
  }, {});

  return (
    <div className="min-h-0 flex-1 overflow-auto p-3">
      <div className="mb-3 flex flex-wrap gap-1.5">
        {Object.entries(byType).map(([type, rows]) => (
          <Badge key={type} variant="secondary" className="text-[9px]">
            {type.replace("_", " ")} · {rows.length}
          </Badge>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 lg:grid-cols-6">
        {(byType.screenshot ?? []).map((capture) => (
          <a
            key={capture.id}
            href={recorderApi.captureImageUrl(sessionId, capture.id)}
            target="_blank"
            rel="noreferrer"
            className="group overflow-hidden rounded-lg border border-gray-200 bg-white"
            title={`Captured ${formatDateTime(capture.captured_at)}`}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={recorderApi.captureImageUrl(sessionId, capture.id)}
              alt={`Screenshot for action ${capture.action_id ?? "—"}`}
              className="h-20 w-full object-cover object-top transition-transform group-hover:scale-105"
            />
            <p className="px-1.5 py-1 text-[9px] font-bold text-gray-500">
              action {capture.action_id ?? "—"}
            </p>
          </a>
        ))}
      </div>
      {(byType.video || byType.trace) === undefined && (
        <p className="mt-3 text-[10px] font-semibold text-gray-400">
          Video and trace capture are not available — the Playwright MCP transport this recorder uses does
          not expose them.
        </p>
      )}
    </div>
  );
}

// ── Notes (Section 12.6) ─────────────────────────────────────────────────────

function NotesTab({
  projectId,
  sessionId,
  editable,
}: {
  projectId: number;
  sessionId: number;
  editable: boolean;
}) {
  const notesQuery = useRecorderNotes(sessionId);
  const { create, remove } = useNoteMutations(projectId, sessionId);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!body.trim()) return;
    setError(null);
    try {
      await create.mutateAsync({ body, scope: "session" });
      setBody("");
    } catch (err) {
      setError(messageFromError(err));
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {error && <p className="mb-2 text-[10px] font-bold text-red-600">{error}</p>}
        {(notesQuery.data ?? []).length === 0 ? (
          <p className="text-[10px] font-semibold text-gray-400">No notes on this recording.</p>
        ) : (
          <ul className="space-y-1.5">
            {(notesQuery.data ?? []).map((note) => (
              <li
                key={note.id}
                className="flex items-start gap-2 rounded-lg border border-gray-200 bg-white px-2.5 py-2"
              >
                <FileText className="mt-0.5 h-3 w-3 shrink-0 text-gray-400" />
                <span className="min-w-0 flex-1">
                  <span className="block text-[11px] font-semibold text-gray-700">{note.body}</span>
                  <span className="block text-[9px] font-bold text-gray-400">
                    {note.scope}
                    {note.step_key ? ` · step ${note.step_key}` : ""} ·{" "}
                    {formatDateTime(note.created_at)}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => remove.mutate(note.id)}
                  className="shrink-0 text-gray-300 hover:text-red-500"
                  title="Delete note"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex items-center gap-2 border-t border-gray-100 p-2">
        <input
          value={body}
          onChange={(event) => setBody(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && submit()}
          placeholder="Add a note about this recording…"
          disabled={!editable}
          className="min-w-0 flex-1 rounded-lg border border-gray-200 px-2.5 py-1.5 text-[11px] font-semibold focus:outline-none focus:ring-2 focus:ring-[#B71920]"
        />
        <Button size="sm" onClick={submit} disabled={!editable || !body.trim() || create.isPending}>
          {create.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Add"}
        </Button>
      </div>
    </div>
  );
}

// ── Checkpoint review strip (Section 16) ─────────────────────────────────────

export function CheckpointReviewList({
  projectId,
  sessionId,
  checkpoints,
  editable,
}: {
  projectId: number;
  sessionId: number;
  checkpoints: RecorderCheckpoint[];
  editable: boolean;
}) {
  const { review, remove } = useCheckpointMutations(projectId, sessionId);
  const [error, setError] = useState<string | null>(null);

  if (checkpoints.length === 0) {
    return (
      <p className="px-1 text-[10px] font-semibold text-gray-400">
        No validation checkpoints yet. They are proposed when the recording is stopped, and you can add
        your own against any step.
      </p>
    );
  }

  return (
    <div className="space-y-1.5">
      {error && <p className="text-[10px] font-bold text-red-600">{error}</p>}
      {checkpoints.map((checkpoint) => (
        <div
          key={checkpoint.id}
          className={cn(
            "rounded-lg border px-2.5 py-2",
            checkpoint.review_state === "needs_review"
              ? "border-amber-200 bg-amber-50/60"
              : checkpoint.review_state === "rejected"
                ? "border-gray-200 bg-gray-50/60 opacity-60"
                : "border-emerald-200 bg-emerald-50/40",
          )}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-[11px] font-bold text-gray-800">
                {checkpoint.checkpoint_type.replace(/_/g, " ")}
                {checkpoint.step_key && (
                  <span className="ml-1 text-[9px] font-bold text-gray-400">
                    step {checkpoint.step_key}
                  </span>
                )}
              </p>
              {checkpoint.expected_value && (
                <p className="truncate text-[10px] font-semibold text-gray-500" title={checkpoint.expected_value}>
                  expects {checkpoint.expected_value}
                </p>
              )}
              {checkpoint.source === "recommended" && checkpoint.recommendation_reason && (
                <p className="mt-1 flex items-start gap-1 text-[9px] font-semibold text-amber-700">
                  <AlertTriangle className="mt-0.5 h-2.5 w-2.5 shrink-0" />
                  {checkpoint.recommendation_reason}
                </p>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {checkpoint.review_state === "needs_review" && editable && (
                <>
                  <button
                    type="button"
                    title="Accept — this becomes an assertion in the Automation IR."
                    onClick={() =>
                      review
                        .mutateAsync({ checkpointId: checkpoint.id, review_state: "accepted" })
                        .catch((err) => setError(messageFromError(err)))
                    }
                    className="rounded border border-emerald-200 bg-white p-1 text-emerald-600 hover:bg-emerald-50"
                  >
                    <Check className="h-3 w-3" />
                  </button>
                  <button
                    type="button"
                    title="Reject — kept on the recording but never asserted."
                    onClick={() =>
                      review
                        .mutateAsync({ checkpointId: checkpoint.id, review_state: "rejected" })
                        .catch((err) => setError(messageFromError(err)))
                    }
                    className="rounded border border-gray-200 bg-white p-1 text-gray-500 hover:bg-gray-50"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </>
              )}
              {checkpoint.source === "user" && editable && (
                <button
                  type="button"
                  title="Delete checkpoint"
                  onClick={() => remove.mutate(checkpoint.id)}
                  className="rounded border border-gray-200 bg-white p-1 text-gray-400 hover:text-red-500"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
              <Badge
                variant={
                  checkpoint.review_state === "accepted"
                    ? "success"
                    : checkpoint.review_state === "rejected"
                      ? "outline"
                      : "warning"
                }
                className="text-[9px]"
              >
                {checkpoint.review_state.replace("_", " ")}
              </Badge>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function PanelMessage({
  children,
  tone = "muted",
}: {
  children: React.ReactNode;
  tone?: "muted" | "error";
}) {
  return (
    <p
      className={cn(
        "p-4 text-[11px] font-semibold",
        tone === "error" ? "text-red-600" : "text-gray-400",
      )}
    >
      {children}
    </p>
  );
}
