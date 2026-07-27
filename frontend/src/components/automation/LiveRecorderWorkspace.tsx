"use client";

// UI-019 Live Recorder — the recording workspace (contract Sections 8-13).
//
// The centre panel is a *proxied* viewport, not an embedded browser. The
// application runs in a headless Playwright session on the backend host, so
// what is shown here is the real screenshot the browser just took, alongside
// the real accessibility tree it just read. The user picks an element from
// that tree and names an action; the backend performs it against the live
// application and records what actually happened. Every recorded action is
// one the platform genuinely executed — nothing here infers a click.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  Clock,
  ExternalLink,
  FileCheck2,
  Globe,
  Loader2,
  MousePointerClick,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  SkipForward,
  Square,
  Type as TypeIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import {
  isCapturedRecording,
  isLiveRecording,
  recorderApi,
  type RecorderStep,
} from "@/lib/api";
import {
  useDiscardRecording,
  useEmitIrDraft,
  useFinalizeRecording,
  useIrDraft,
  useRecordAction,
  useRecordedActions,
  useRecorderCaptures,
  useRecorderCheckpoints,
  useRecorderCommand,
  useRecorderContext,
  useRecorderLatestView,
  useRecorderMappings,
  useRecorderPreconditions,
  useRecorderSteps,
  useRecording,
  useRecordingSummary,
  useResolvedActiveStep,
  useStepMutations,
} from "@/lib/queries/recorder";
import { cn } from "@/lib/utils";
import { Banner, Panel, messageFromError } from "@/components/automation/suite-shared";
import {
  ConfidenceChip,
  InheritedField,
  RecordingStatusBadge,
  StepStatusPill,
  formatDuration,
} from "@/components/automation/recorder-shared";
import {
  ACTIVITY_TABS,
  CheckpointReviewList,
  RecorderActivityTabs,
  type ActivityTab,
} from "@/components/automation/RecorderActivityTabs";
import { RecordingSummaryDrawer } from "@/components/automation/RecordingSummaryDrawer";

/** One element read out of the live accessibility snapshot. */
interface SnapshotElement {
  ref: string;
  role: string;
  name: string | null;
  depth: number;
}

/**
 * Parses the accessibility tree the browser just produced. Lines look like
 *   - combobox "Search" [ref=f1e40] [cursor=pointer]
 * Only lines carrying a `ref` are actionable, because a ref is what the
 * backend needs to target the real element.
 */
function parseSnapshotElements(snapshot: string | null | undefined): SnapshotElement[] {
  if (!snapshot) return [];
  const elements: SnapshotElement[] = [];
  for (const line of snapshot.split("\n")) {
    const refMatch = line.match(/\[ref=([^\]]+)\]/);
    if (!refMatch) continue;
    const body = line.slice(0, refMatch.index).replace(/^[\s-]*/, "");
    const roleMatch = body.match(/^([A-Za-z][A-Za-z0-9_-]*)/);
    if (!roleMatch) continue;
    const nameMatch = body.match(/"([^"]*)"/);
    elements.push({
      ref: refMatch[1],
      role: roleMatch[1],
      name: nameMatch ? nameMatch[1] : null,
      depth: (line.match(/^\s*/)?.[0].length ?? 0) / 2,
    });
  }
  return elements;
}

/** Roles a person can meaningfully type into. */
const TYPEABLE_ROLES = new Set(["textbox", "combobox", "searchbox", "textarea", "spinbutton"]);

export function LiveRecorderWorkspace({
  projectId,
  recordingId,
}: {
  projectId: number;
  recordingId: number;
}) {
  const router = useRouter();
  const { toast } = useToast();

  const recordingQuery = useRecording(recordingId);
  const recording = recordingQuery.data;
  const live = isLiveRecording(recording);
  const captured = isCapturedRecording(recording);
  const editable = Boolean(recording && !["CANCELLED", "COMPLETED", "EMERGENCY_STOPPED"].includes(recording.status));

  const contextQuery = useRecorderContext(recordingId);
  const preconditionsQuery = useRecorderPreconditions(recordingId);
  const stepsQuery = useRecorderSteps(recordingId, live);
  const actionsQuery = useRecordedActions(recordingId, live);
  const mappingsQuery = useRecorderMappings(recordingId, live);
  const checkpointsQuery = useRecorderCheckpoints(recordingId);
  const capturesQuery = useRecorderCaptures(recordingId, live);
  const latestViewQuery = useRecorderLatestView(recordingId, live);
  const activeStepQuery = useResolvedActiveStep(recordingId, live);

  const [summaryOpen, setSummaryOpen] = useState(false);
  const summaryQuery = useRecordingSummary(recordingId, summaryOpen);
  const irDraftQuery = useIrDraft(recordingId);

  const command = useRecorderCommand(projectId, recordingId);
  const recordAction = useRecordAction(projectId, recordingId);
  const stepMutations = useStepMutations(projectId, recordingId);
  const finalize = useFinalizeRecording(projectId, recordingId);
  const emitIr = useEmitIrDraft(projectId, recordingId);
  const discard = useDiscardRecording(projectId, recordingId);

  const [error, setError] = useState<string | null>(null);
  const [activityTab, setActivityTab] = useState<ActivityTab>("actions");
  const [selectedActionId, setSelectedActionId] = useState<number | null>(null);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [elementFilter, setElementFilter] = useState("");
  const [selectedRef, setSelectedRef] = useState<string | null>(null);
  const [typeValue, setTypeValue] = useState("");
  const [navUrl, setNavUrl] = useState("");
  const [substepFor, setSubstepFor] = useState<string | null>(null);
  const [substepLabel, setSubstepLabel] = useState("");

  const steps = useMemo(() => stepsQuery.data ?? [], [stepsQuery.data]);
  const actions = useMemo(() => actionsQuery.data ?? [], [actionsQuery.data]);
  const checkpoints = useMemo(() => checkpointsQuery.data ?? [], [checkpointsQuery.data]);
  const explicitActiveStep = useMemo(
    () => steps.find((step) => step.status === "ACTIVE") ?? null,
    [steps],
  );
  // What the backend will actually map the next action to — see
  // `useResolvedActiveStep`. Falling back to the explicit one keeps the badge
  // correct on the first render before the query resolves.
  const resolvedActiveStepKey = activeStepQuery.data?.step_key ?? explicitActiveStep?.step_key ?? null;
  const activeStep = useMemo(
    () => steps.find((step) => step.step_key === resolvedActiveStepKey) ?? null,
    [resolvedActiveStepKey, steps],
  );
  const snapshotElements = useMemo(
    () => parseSnapshotElements(latestViewQuery.data?.accessibility_snapshot),
    [latestViewQuery.data?.accessibility_snapshot],
  );
  const filteredElements = useMemo(() => {
    const needle = elementFilter.trim().toLowerCase();
    if (!needle) return snapshotElements;
    return snapshotElements.filter(
      (element) =>
        element.role.toLowerCase().includes(needle) ||
        (element.name ?? "").toLowerCase().includes(needle),
    );
  }, [elementFilter, snapshotElements]);
  const selectedElement = useMemo(
    () => snapshotElements.find((element) => element.ref === selectedRef) ?? null,
    [selectedRef, snapshotElements],
  );

  // Session timer — derived from the recording's own started_at so a page
  // refresh never restarts it.
  const [elapsed, setElapsed] = useState<number | null>(null);
  useEffect(() => {
    if (!recording?.started_at) {
      setElapsed(null);
      return;
    }
    const started = new Date(recording.started_at).getTime();
    const end = recording.terminal_at ? new Date(recording.terminal_at).getTime() : null;
    const tick = () => setElapsed(Math.max(Math.floor(((end ?? Date.now()) - started) / 1000), 0));
    tick();
    if (end) return;
    const handle = window.setInterval(tick, 1000);
    return () => window.clearInterval(handle);
  }, [recording?.started_at, recording?.terminal_at]);

  // Stop finalization runs once per transition into STOPPED: it closes the
  // open segment, parses network activity and proposes checkpoints.
  const finalizedFor = useRef<number | null>(null);
  useEffect(() => {
    if (recording?.status !== "STOPPED") return;
    if (finalizedFor.current === recording.id) return;
    finalizedFor.current = recording.id;
    finalize
      .mutateAsync()
      .then(() => setSummaryOpen(true))
      .catch((err) => setError(messageFromError(err)));
  }, [finalize, recording?.id, recording?.status]);

  const runCommand = useCallback(
    async (name: string, params?: Record<string, unknown>) => {
      setError(null);
      try {
        await command.mutateAsync({ command: name, params });
      } catch (err) {
        setError(messageFromError(err));
      }
    },
    [command],
  );

  const perform = useCallback(
    async (payload: Parameters<typeof recordAction.mutateAsync>[0]) => {
      setError(null);
      try {
        await recordAction.mutateAsync(payload);
      } catch (err) {
        setError(messageFromError(err));
      }
    },
    [recordAction],
  );

  if (recordingQuery.isLoading) {
    return <p className="p-8 text-sm font-semibold text-slate-400">Loading recording…</p>;
  }
  if (!recording) {
    return <p className="p-8 text-sm font-semibold text-slate-400">Recording not found.</p>;
  }

  const context = contextQuery.data;
  const preconditions = preconditionsQuery.data;
  const blockers = preconditions?.blockers ?? [];
  const advisories = preconditions?.advisories ?? [];

  return (
    <div className="flex h-[calc(100vh-8rem)] min-h-0 flex-col gap-2">
      {/* ── Header (Section 9) ────────────────────────────────────────────── */}
      <div className="shrink-0 rounded-lg border border-slate-200 bg-white px-3 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <button
              type="button"
              onClick={() => router.push(`/automation?view=recorder&project=${projectId}`)}
              className="rounded-lg border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-50"
              title="Back to Live Recorder"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
            </button>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="truncate text-sm font-extrabold text-slate-900">
                  {context?.test_case
                    ? `${context.test_case.display_id}: ${context.test_case.title}`
                    : `Recording #${recording.id}`}
                </h2>
                <RecordingStatusBadge status={recording.status} />
                <Badge variant="outline" className="text-[9px]">
                  v{recording.recording_version}
                </Badge>
              </div>
              <p className="mt-0.5 truncate text-[10px] font-semibold text-slate-500">
                Suite: {context?.suite?.name ?? "—"} · App: {context?.application?.name ?? "—"} ·
                Framework: {context?.framework ?? "—"} · Environment: {context?.environment ?? "—"} ·
                Mode: {recording.recording_mode === "EXPLORATORY" ? "Exploratory" : "Guided Recording"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <span
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-extrabold text-slate-800"
              title="Session duration"
            >
              {live && <CircleDot className="h-3 w-3 animate-pulse text-red-500" />}
              <Clock className="h-3 w-3 text-slate-400" />
              {formatDuration(elapsed)}
            </span>

            {recording.status === "NOT_STARTED" && (
              <Button size="sm" onClick={() => runCommand("start")} disabled={command.isPending}>
                {command.isPending ? (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                ) : (
                  <Play className="mr-1 h-3 w-3" />
                )}
                Launch & Start
              </Button>
            )}
            {recording.status === "RECORDING" && (
              <>
                <Button size="sm" variant="outline" onClick={() => runCommand("pause")}>
                  <Pause className="mr-1 h-3 w-3" />
                  Pause
                </Button>
                <Button size="sm" variant="destructive" onClick={() => runCommand("stop")}>
                  <Square className="mr-1 h-3 w-3" />
                  Stop
                </Button>
              </>
            )}
            {recording.status === "PAUSED" && (
              <>
                <Button
                  size="sm"
                  onClick={() => runCommand("resume", { recovery_option: "resume_from_checkpoint" })}
                >
                  <Play className="mr-1 h-3 w-3" />
                  Resume
                </Button>
                <Button size="sm" variant="destructive" onClick={() => runCommand("stop")}>
                  <Square className="mr-1 h-3 w-3" />
                  Stop
                </Button>
              </>
            )}
            {captured && (
              <Button size="sm" onClick={() => setSummaryOpen(true)}>
                <Save className="mr-1 h-3 w-3" />
                Review & Save
              </Button>
            )}
          </div>
        </div>
      </div>

      {error && <Banner kind="error" message={error} onDismiss={() => setError(null)} />}

      {blockers.length > 0 && recording.status === "NOT_STARTED" && (
        <div className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5">
          <p className="text-[11px] font-extrabold text-red-800">
            Recording is blocked until these are resolved (Section 6):
          </p>
          <ul className="mt-1 space-y-1">
            {blockers.map((check) => (
              <li key={check.name} className="text-[11px] font-semibold text-red-700">
                {check.detail}
                {check.remediation_href && (
                  <a href={check.remediation_href} className="ml-1.5 underline">
                    Open source
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Main workspace ────────────────────────────────────────────────── */}
      <div className="flex min-h-0 flex-1 gap-2">
        {/* Left — test case steps (Section 10) */}
        {leftOpen ? (
          <div className="flex w-[300px] shrink-0 flex-col gap-2 overflow-hidden">
            <Panel
              title="Test Case Steps"
              className="flex min-h-0 flex-1 flex-col"
              action={
                <button
                  type="button"
                  onClick={() => setLeftOpen(false)}
                  className="text-slate-400 hover:text-slate-700"
                  title="Collapse panel"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </button>
              }
            >
              <StepProgress steps={steps} />
              <div className="mt-2 min-h-0 flex-1 space-y-1 overflow-y-auto">
                {steps.length === 0 ? (
                  <p className="p-2 text-[10px] font-semibold text-slate-400">
                    This test case has no steps.
                  </p>
                ) : (
                  steps.map((step) => (
                    <StepRow
                      key={step.step_key}
                      step={step}
                      editable={editable}
                      busy={stepMutations.activate.isPending || stepMutations.setStatus.isPending}
                      onActivate={() =>
                        stepMutations.activate
                          .mutateAsync(step.step_key)
                          .catch((err) => setError(messageFromError(err)))
                      }
                      onComplete={() =>
                        stepMutations.setStatus
                          .mutateAsync({ stepKey: step.step_key, status: "COMPLETED" })
                          .catch((err) => setError(messageFromError(err)))
                      }
                      onSkip={() => {
                        const reason = window.prompt(`Why is step ${step.step_key} being skipped?`);
                        if (!reason?.trim()) return;
                        stepMutations.setStatus
                          .mutateAsync({ stepKey: step.step_key, status: "SKIPPED", reason })
                          .catch((err) => setError(messageFromError(err)));
                      }}
                      onAddSubstep={() => {
                        setSubstepFor(step.step_key);
                        setSubstepLabel("");
                      }}
                    />
                  ))
                )}
              </div>

              {substepFor && (
                <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-2">
                  <p className="text-[9px] font-bold uppercase tracking-wide text-slate-500">
                    Discovered sub-step under {substepFor}
                  </p>
                  <input
                    value={substepLabel}
                    onChange={(event) => setSubstepLabel(event.target.value)}
                    placeholder="What did the application actually require?"
                    className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-[10px] font-semibold"
                  />
                  <div className="mt-1.5 flex gap-1.5">
                    <Button
                      size="sm"
                      disabled={!substepLabel.trim()}
                      onClick={() =>
                        stepMutations.addSubstep
                          .mutateAsync({ parent_step_key: substepFor, label: substepLabel })
                          .then(() => setSubstepFor(null))
                          .catch((err) => setError(messageFromError(err)))
                      }
                    >
                      Add
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setSubstepFor(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </Panel>
          </div>
        ) : (
          <CollapsedRail label="Steps" onExpand={() => setLeftOpen(true)} side="left" />
        )}

        {/* Centre — proxied live application viewport (Section 11) */}
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white">
            <div className="flex shrink-0 items-center gap-2 border-b border-slate-200 px-2.5 py-1.5">
              <Globe className="h-3.5 w-3.5 shrink-0 text-slate-400" />
              <span
                className="min-w-0 flex-1 truncate rounded bg-slate-50 px-2 py-1 text-[10px] font-semibold text-slate-600"
                title={latestViewQuery.data?.page_url ?? ""}
              >
                {latestViewQuery.data?.page_url ?? "No page loaded yet"}
              </span>
              {latestViewQuery.data?.page_url && (
                <a
                  href={latestViewQuery.data.page_url}
                  target="_blank"
                  rel="noreferrer"
                  className="shrink-0 rounded border border-slate-200 p-1 text-slate-500 hover:bg-slate-50"
                  title="Open this URL in your own browser (does not record)"
                >
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
              <button
                type="button"
                onClick={() => latestViewQuery.refetch()}
                className="shrink-0 rounded border border-slate-200 p-1 text-slate-500 hover:bg-slate-50"
                title="Refresh the captured view"
              >
                <RefreshCw className={cn("h-3 w-3", latestViewQuery.isFetching && "animate-spin")} />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-auto bg-slate-100 p-2">
              {latestViewQuery.data?.screenshot_capture_id ? (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={recorderApi.captureImageUrl(
                      recordingId,
                      latestViewQuery.data.screenshot_capture_id,
                    )}
                    alt="Latest captured view of the application under test"
                    className="mx-auto max-w-full rounded border border-slate-200 bg-white shadow-sm"
                  />
                  <p className="mt-1.5 text-center text-[9px] font-bold text-slate-400">
                    Captured after action #{latestViewQuery.data.sequence} — this is a screenshot of the
                    real application, not a live embed.
                  </p>
                </>
              ) : (
                <div className="flex h-full flex-col items-center justify-center gap-1.5 text-center">
                  <p className="text-xs font-bold text-slate-500">
                    {recording.status === "NOT_STARTED"
                      ? "Start the recording to launch the application."
                      : "No view captured yet — perform an action to capture one."}
                  </p>
                  <p className="max-w-md text-[10px] font-semibold text-slate-400">
                    The application runs in a browser on the backend host. You drive it by choosing a real
                    element and an action below; every recorded step is one the platform actually performed.
                  </p>
                </div>
              )}
            </div>

            {/* Action composer — the proxied interaction surface */}
            <div className="shrink-0 border-t border-slate-200 bg-white p-2">
              {!live ? (
                <p className="px-1 text-[10px] font-semibold text-slate-400">
                  {recording.status === "PAUSED"
                    ? "Paused — no user action or locator capture is happening. Resume to continue recording."
                    : "The recording is not live, so no actions can be performed."}
                </p>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[9px] font-bold uppercase tracking-wide text-slate-400">
                      Recording into
                    </span>
                    {activeStep ? (
                      <Badge
                        variant="info"
                        className="text-[9px]"
                        title={
                          explicitActiveStep
                            ? "You set this step active."
                            : "No step is explicitly active, so actions attach to the first step with nothing recorded."
                        }
                      >
                        Step {activeStep.step_key}
                        {!explicitActiveStep && <span className="ml-1 opacity-70">(auto)</span>}
                      </Badge>
                    ) : (
                      <Badge
                        variant="outline"
                        className="text-[9px]"
                        title="Every step already has recorded actions, so new ones will be unmapped until you set a step active."
                      >
                        No active step — actions will be unmapped
                      </Badge>
                    )}
                  </div>

                  <div className="flex gap-1.5">
                    <input
                      value={navUrl}
                      onChange={(event) => setNavUrl(event.target.value)}
                      placeholder="https://… navigate to a URL"
                      className="min-w-0 flex-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-semibold focus:outline-none focus:ring-2 focus:ring-[#1b59f8]"
                    />
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!navUrl.trim() || recordAction.isPending}
                      onClick={() =>
                        perform({
                          action_family: "navigate",
                          url: navUrl,
                          target_semantic: `Navigate to ${navUrl}`,
                        }).then(() => setNavUrl(""))
                      }
                    >
                      <Globe className="mr-1 h-3 w-3" />
                      Go
                    </Button>
                  </div>

                  <div className="grid gap-1.5 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                    <div className="rounded-lg border border-slate-200">
                      <input
                        value={elementFilter}
                        onChange={(event) => setElementFilter(event.target.value)}
                        placeholder={`Filter ${snapshotElements.length} element(s) on the page…`}
                        className="w-full rounded-t-lg border-b border-slate-200 px-2.5 py-1.5 text-[10px] font-semibold focus:outline-none"
                      />
                      <div className="max-h-28 overflow-y-auto">
                        {filteredElements.length === 0 ? (
                          <p className="p-2 text-[10px] font-semibold text-slate-400">
                            No elements available — perform an action to capture the page.
                          </p>
                        ) : (
                          filteredElements.slice(0, 200).map((element) => (
                            <button
                              key={element.ref}
                              type="button"
                              onClick={() => setSelectedRef(element.ref)}
                              className={cn(
                                "flex w-full items-center gap-1.5 px-2 py-1 text-left text-[10px] font-semibold hover:bg-slate-50",
                                selectedRef === element.ref && "bg-blue-50 text-[#1b59f8]",
                              )}
                            >
                              <Badge variant="outline" className="shrink-0 text-[8px]">
                                {element.role}
                              </Badge>
                              <span className="min-w-0 truncate">{element.name ?? element.ref}</span>
                            </button>
                          ))
                        )}
                      </div>
                    </div>

                    <div className="flex flex-col gap-1.5">
                      <p className="truncate text-[10px] font-bold text-slate-600">
                        {selectedElement
                          ? `${selectedElement.role} — ${selectedElement.name ?? selectedElement.ref}`
                          : "Select an element to act on"}
                      </p>
                      <div className="flex gap-1.5">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={!selectedElement || recordAction.isPending}
                          onClick={() =>
                            perform({
                              action_family: "click",
                              target_ref: selectedElement!.ref,
                              target_semantic: selectedElement!.name ?? selectedElement!.role,
                            })
                          }
                        >
                          <MousePointerClick className="mr-1 h-3 w-3" />
                          Click
                        </Button>
                      </div>
                      <div className="flex gap-1.5">
                        <input
                          value={typeValue}
                          onChange={(event) => setTypeValue(event.target.value)}
                          placeholder="Text to type"
                          disabled={!selectedElement || !TYPEABLE_ROLES.has(selectedElement.role)}
                          className="min-w-0 flex-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-semibold disabled:bg-slate-50"
                        />
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={
                            !selectedElement ||
                            !TYPEABLE_ROLES.has(selectedElement.role) ||
                            !typeValue ||
                            recordAction.isPending
                          }
                          title={
                            selectedElement && !TYPEABLE_ROLES.has(selectedElement.role)
                              ? `A ${selectedElement.role} cannot be typed into.`
                              : undefined
                          }
                          onClick={() =>
                            perform({
                              action_family: "input",
                              target_ref: selectedElement!.ref,
                              target_semantic: selectedElement!.name ?? selectedElement!.role,
                              input_text: typeValue,
                            }).then(() => setTypeValue(""))
                          }
                        >
                          <TypeIcon className="mr-1 h-3 w-3" />
                          Type
                        </Button>
                      </div>
                    </div>
                  </div>
                  {recordAction.isPending && (
                    <p className="flex items-center gap-1.5 px-1 text-[10px] font-bold text-[#1b59f8]">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      Performing the action against the live application…
                    </p>
                  )}
                </div>
              )}
            </div>
          </section>

          {/* Bottom — recording activity (Section 12) */}
          <section className="flex h-[38%] min-h-0 shrink-0 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white">
            <div className="flex shrink-0 items-center gap-0.5 border-b border-slate-200 px-1.5">
              {ACTIVITY_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActivityTab(tab.id)}
                  className={cn(
                    "flex items-center gap-1 whitespace-nowrap border-b-2 px-2.5 py-2 text-[10px] font-bold transition-colors",
                    activityTab === tab.id
                      ? "border-[#1b59f8] text-[#1b59f8]"
                      : "border-transparent text-slate-500 hover:text-slate-800",
                  )}
                >
                  <tab.icon className="h-3 w-3" />
                  {tab.label}
                  {tab.id === "actions" && actions.length > 0 && (
                    <span className="text-slate-400">({actions.length})</span>
                  )}
                </button>
              ))}
            </div>
            <RecorderActivityTabs
              tab={activityTab}
              projectId={projectId}
              sessionId={recordingId}
              actions={actions}
              mappings={mappingsQuery.data ?? []}
              steps={steps}
              checkpoints={checkpoints}
              captures={capturesQuery.data ?? []}
              selectedActionId={selectedActionId}
              onSelectAction={setSelectedActionId}
              editable={editable}
            />
          </section>
        </div>

        {/* Right — inherited context and checkpoints (Sections 10.1, 16) */}
        {rightOpen ? (
          <div className="flex w-[280px] shrink-0 flex-col gap-2 overflow-y-auto">
            <Panel
              title="Recording Details"
              action={
                <button
                  type="button"
                  onClick={() => setRightOpen(false)}
                  className="text-slate-400 hover:text-slate-700"
                  title="Collapse panel"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              }
            >
              <p className="mb-2 rounded border border-slate-200 bg-slate-50 px-2 py-1 text-[9px] font-bold text-slate-500">
                Inherited and read-only — correct it in the source, not here.
              </p>
              <div className="space-y-2">
                <InheritedField
                  label="Test Case"
                  value={context?.test_case?.display_id ?? "—"}
                  hint={context?.test_case?.objective ?? undefined}
                  href={context?.test_case ? `/test-cases?view=editor` : undefined}
                />
                <InheritedField
                  label="Objective"
                  value={
                    <span className="line-clamp-2 whitespace-normal">
                      {context?.test_case?.objective ?? "—"}
                    </span>
                  }
                />
                <div className="grid grid-cols-2 gap-2">
                  <InheritedField label="Priority" value={context?.test_case?.priority ?? "—"} />
                  <InheritedField
                    label="Criticality"
                    value={context?.test_case?.is_critical ? "Critical" : "Standard"}
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <InheritedField label="Type" value={context?.test_case?.test_type ?? "—"} />
                  <InheritedField
                    label="Automation"
                    value={context?.test_case?.automation_status ?? "—"}
                  />
                </div>
                <InheritedField
                  label="Application Under Test"
                  value={context?.application?.name ?? "—"}
                  href="/applications"
                />
                <div className="grid grid-cols-2 gap-2">
                  <InheritedField label="Framework" value={context?.framework ?? "—"} />
                  <InheritedField label="Environment" value={context?.environment ?? "—"} />
                </div>
                <InheritedField
                  label="Traceability"
                  value={context?.requirement_ref ?? context?.scenario_ref ?? "—"}
                />
                <InheritedField
                  label="Test Data"
                  value={
                    context?.test_data.length
                      ? `${context.test_data.length} linked record(s)`
                      : "None linked"
                  }
                  href="/test-data"
                />
              </div>
            </Panel>

            {context?.existing_script && (
              <Panel title="Existing Automation Asset">
                <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-2.5 py-2">
                  <p className="text-[11px] font-bold text-amber-900">
                    {context.existing_script.framework} script v{context.existing_script.version} —{" "}
                    {context.existing_script.status}
                  </p>
                  <p className="mt-1 text-[10px] font-semibold text-amber-800">
                    This recording produces a new Automation IR draft. It never overwrites the published
                    script — that is a separate, reviewed step.
                  </p>
                </div>
              </Panel>
            )}

            <Panel title="Validation Checkpoints">
              <CheckpointReviewList
                projectId={projectId}
                sessionId={recordingId}
                checkpoints={checkpoints}
                editable={editable}
              />
              {editable && activeStep && (
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-2 w-full"
                  onClick={() => setActivityTab("actions")}
                  title="Checkpoints are proposed on Stop and can be added against any recorded action."
                >
                  <ShieldCheck className="mr-1 h-3 w-3" />
                  Review after stopping
                </Button>
              )}
            </Panel>

            {advisories.length > 0 && (
              <Panel title="Advisories">
                <ul className="space-y-1.5">
                  {advisories.map((check) => (
                    <li key={check.name} className="text-[10px] font-semibold text-slate-600">
                      {check.detail}
                      {check.remediation_href && (
                        <a href={check.remediation_href} className="ml-1 text-[#1b59f8] underline">
                          Open
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              </Panel>
            )}
          </div>
        ) : (
          <CollapsedRail label="Details" onExpand={() => setRightOpen(true)} side="right" />
        )}
      </div>

      {/* ── Bottom dock (Section 8) ───────────────────────────────────────── */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2">
        <div className="flex flex-wrap items-center gap-4">
          <DockStat
            label="Recording Status"
            value={
              <span className="flex items-center gap-1.5">
                {live && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />}
                {recording.status.replace(/_/g, " ").toLowerCase()}
              </span>
            }
          />
          <DockStat label="Actions" value={String(actions.length)} />
          <DockStat
            label="Steps recorded"
            value={`${steps.filter((s) => s.recorded_action_count > 0).length} / ${steps.length}`}
          />
          <DockStat label="Duration" value={formatDuration(elapsed)} />
          <DockStat
            label="IR"
            value={irDraftQuery.data ? `draft v${irDraftQuery.data.version}` : "not generated"}
          />
        </div>
        <div className="flex items-center gap-1.5">
          {captured && (
            <Button size="sm" variant="outline" onClick={() => setSummaryOpen(true)}>
              <FileCheck2 className="mr-1 h-3 w-3" />
              Recording Summary
            </Button>
          )}
          <Button
            size="sm"
            disabled={!captured}
            title={
              captured
                ? "Convert this recording into an Automation IR draft."
                : "Stop the recording first — an IR can only be emitted from a captured recording."
            }
            onClick={() => setSummaryOpen(true)}
          >
            <Save className="mr-1 h-3 w-3" />
            Save & Create IR
          </Button>
        </div>
      </div>

      <RecordingSummaryDrawer
        open={summaryOpen}
        onOpenChange={setSummaryOpen}
        summary={summaryQuery.data}
        irDraft={irDraftQuery.data}
        loading={summaryQuery.isLoading || finalize.isPending}
        canEmitIr={captured}
        onEmitIr={async () => {
          const draft = await emitIr.mutateAsync();
          toast({ title: `Automation IR draft v${draft.version} created` });
          return draft;
        }}
        onDiscard={async (reason) => {
          await discard.mutateAsync(reason);
          toast({ title: "Recording discarded" });
          router.push(`/automation?view=recorder&project=${projectId}`);
        }}
      />
    </div>
  );
}

function StepProgress({ steps }: { steps: RecorderStep[] }) {
  const recorded = steps.filter((step) => step.recorded_action_count > 0).length;
  const denominator = steps.filter((step) => step.status !== "SKIPPED").length;
  const percent = denominator ? Math.round((recorded / denominator) * 100) : 0;
  return (
    <div>
      <p className="text-[10px] font-bold text-slate-600">
        {recorded} / {denominator} steps recorded
        {steps.length !== denominator && (
          <span className="ml-1 font-semibold text-slate-400">
            ({steps.length - denominator} skipped)
          </span>
        )}
      </p>
      <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-[#1b59f8] transition-all" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

function StepRow({
  step,
  editable,
  busy,
  onActivate,
  onComplete,
  onSkip,
  onAddSubstep,
}: {
  step: RecorderStep;
  editable: boolean;
  busy: boolean;
  onActivate: () => void;
  onComplete: () => void;
  onSkip: () => void;
  onAddSubstep: () => void;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border px-2.5 py-2 transition-colors",
        step.status === "ACTIVE"
          ? "border-[#1b59f8] bg-blue-50/60"
          : "border-slate-200 bg-white hover:bg-slate-50",
        step.is_discovered_substep && "ml-3 border-dashed",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-[11px] font-extrabold text-slate-800">
            <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[9px]">
              {step.step_key}
            </span>
            <span className="truncate">{step.action_text ?? "(no step text)"}</span>
          </p>
          {step.expected_result && (
            <p className="mt-0.5 truncate text-[10px] font-semibold text-slate-500" title={step.expected_result}>
              Expects: {step.expected_result}
            </p>
          )}
          {step.skip_reason && (
            <p className="mt-0.5 text-[10px] font-semibold text-amber-700">Skipped: {step.skip_reason}</p>
          )}
        </div>
        <div className="shrink-0 text-right">
          <StepStatusPill status={step.status} reason={step.status_reason} />
          <p className="mt-0.5 text-[9px] font-bold text-slate-400">
            {step.recorded_action_count} action(s)
            {step.checkpoint_count > 0 && ` · ${step.accepted_checkpoint_count}/${step.checkpoint_count} ✓`}
          </p>
        </div>
      </div>

      {editable && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {step.status !== "ACTIVE" && (
            <StepAction icon={CircleDot} label="Set active" onClick={onActivate} disabled={busy} />
          )}
          <StepAction icon={ShieldCheck} label="Complete" onClick={onComplete} disabled={busy} />
          <StepAction icon={SkipForward} label="Skip" onClick={onSkip} disabled={busy} />
          {!step.is_discovered_substep && (
            <StepAction icon={Plus} label="Sub-step" onClick={onAddSubstep} disabled={busy} />
          )}
        </div>
      )}
    </div>
  );
}

function StepAction({
  icon: Icon,
  label,
  onClick,
  disabled,
}: {
  icon: typeof CircleDot;
  label: string;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex items-center gap-1 rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[9px] font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-40"
    >
      <Icon className="h-2.5 w-2.5" />
      {label}
    </button>
  );
}

function DockStat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-[9px] font-bold uppercase tracking-wide text-slate-400">{label}</p>
      <p className="text-[11px] font-extrabold capitalize text-slate-800">{value}</p>
    </div>
  );
}

function CollapsedRail({
  label,
  onExpand,
  side,
}: {
  label: string;
  onExpand: () => void;
  side: "left" | "right";
}) {
  return (
    <button
      type="button"
      onClick={onExpand}
      className="flex w-8 shrink-0 flex-col items-center gap-2 rounded-lg border border-slate-200 bg-white py-3 text-slate-400 hover:text-slate-700"
      title={`Expand ${label} panel`}
    >
      {side === "left" ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
      <span className="text-[9px] font-bold uppercase [writing-mode:vertical-rl]">{label}</span>
    </button>
  );
}
