"use client";

/**
 * UI-015 Live Discovery Session.
 *
 * Rebuilt on the Test Case module's list-and-drawer pattern. The screen used
 * to render one session inline as a three-column workspace with a session
 * history table bolted underneath, so "which sessions exist and what state
 * are they in" was the last thing on the page rather than the first, and
 * every control for the open session competed for the same screen.
 *
 * Now: the session list is the screen. Each row opens a drawer whose first
 * tab answers "what do I do next with this session?" — readiness, the one
 * available transition, and why the others are not — with evidence, live
 * control, checkpoints and audit history on their own tabs.
 */

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import {
  Activity, AlertTriangle, CheckCircle2, Clock, ExternalLink, Flag, Layers3, Loader2,
  Pause, Play, Plus, Radar, RefreshCw, Search, ShieldCheck, Square, StopCircle, Target, X, XCircle,
} from "lucide-react";
import {
  applicationsApi, type DiscoveryLocatorEvidence,
  type DiscoverySession, type EligibleTestCase, type ProjectApplication,
} from "@/lib/api";
import {
  useCaptureContent, useCorrectDiscoveryAction, useCreateDiscoverySession, useCurrentStep, useDiscoveryActions,
  useDiscoveryActivity, useDiscoveryCaptures, useDiscoveryCheckpoints, useDiscoveryReadiness, useDiscoverySession,
  useDiscoverySessions, useEligibleTestCases, useIssueDiscoveryCommand, useRecordFreeAction,
} from "@/lib/queries/discovery";
import { useToast } from "@/components/ui/toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerBody, DrawerFooter } from "@/components/ui/drawer";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import {
  Breadcrumb, ChecklistRow, DrawerCard, DrawerTabBar, EmptyState, FilterSelect, GuidanceCard,
  InfoPair, ListRow, ListShell, Notices, QueueTabs, StatCard, WorkspaceHeader,
  type DrawerTabSpec,
} from "@/components/applications/workspace";

const MODES = [
  { value: "GUIDED_USER", label: "Guided User Recording", hint: "The agent walks an approved test case end to end and captures evidence at every step. No intervention needed." },
  { value: "FREE_USER_ACTION", label: "Free User-Action Recording", hint: "You drive. Every action you record is captured with locator evidence. Use this to reverse-engineer an undocumented flow." },
  { value: "SUPERVISED_AGENT_DRIVEN", label: "Supervised Agent-Driven Recording", hint: "The agent proposes each step from an approved test case and waits for you to approve, modify or skip it." },
] as const;

const STATE_BADGE: Record<string, "success" | "warning" | "destructive" | "info" | "secondary" | "outline"> = {
  NOT_STARTED: "outline", INITIALISING: "warning", RECORDING: "success", PAUSE_REQUESTED: "warning",
  PAUSED: "warning", RESUMING: "warning", STOP_REQUESTED: "warning", STOPPED: "info",
  COMPLETED: "success", CANCELLED: "secondary", FAILED: "destructive", EMERGENCY_STOPPED: "destructive",
};

/**
 * The twelve persisted states, as the four a user actually decides between.
 *
 * PAUSE_REQUESTED, RESUMING and STOP_REQUESTED are transitional bookkeeping —
 * the session is between two places and the user has no decision to make until
 * it arrives. Showing them made the session look like it had twelve modes when
 * it has four, and made a request-then-settle transition read as an error.
 *
 * Failure and cancellation stay distinct rather than folding into "Finished":
 * a session that failed did not finish, and saying otherwise would hide the
 * one outcome most worth noticing. The exact state is always still shown
 * beside this, so nothing is concealed from someone debugging.
 */
const SESSION_PHASE: Record<string, { label: string; hint: string }> = {
  NOT_STARTED: { label: "Not started", hint: "Evaluate readiness, then start." },
  INITIALISING: { label: "Recording", hint: "Opening the browser session." },
  RECORDING: { label: "Recording", hint: "Performing and capturing each step." },
  RESUMING: { label: "Recording", hint: "Picking up from the last checkpoint." },
  PAUSE_REQUESTED: { label: "Paused", hint: "Finishing the current step first." },
  PAUSED: { label: "Paused", hint: "Resume, or stop to finish the session." },
  STOP_REQUESTED: { label: "Paused", hint: "Finishing the current step first." },
  STOPPED: { label: "Paused", hint: "Complete the session to build a model from it." },
  COMPLETED: { label: "Finished", hint: "Ready to build an Application Model." },
  CANCELLED: { label: "Cancelled", hint: "Ended without producing evidence." },
  FAILED: { label: "Failed", hint: "See the failure detail below." },
  EMERGENCY_STOPPED: { label: "Failed", hint: "Stopped immediately on request." },
};

const TERMINAL_STATES = ["COMPLETED", "CANCELLED", "FAILED", "EMERGENCY_STOPPED"];
const LIVE_STATES = ["INITIALISING", "RECORDING", "RESUMING", "PAUSE_REQUESTED", "STOP_REQUESTED"];

function sessionPhase(status: string) {
  return SESSION_PHASE[status] ?? { label: status, hint: "" };
}

type DrawerTab = "next" | "findings" | "control" | "checkpoints" | "activity";
type QueueKey = "all" | "live" | "paused" | "finished" | "failed";

const QUEUE_TABS: { key: QueueKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "live", label: "Recording" },
  { key: "paused", label: "Paused" },
  { key: "finished", label: "Finished" },
  { key: "failed", label: "Failed" },
];

const SESSION_GRID = "80px 200px 130px minmax(200px,1fr) 100px 90px 150px";

const FREE_ACTION_FAMILIES = [
  { value: "navigate", label: "Navigate" },
  { value: "click", label: "Click" },
  { value: "input", label: "Type" },
  { value: "read", label: "Observe" },
] as const;

function messageFromError(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in (detail as Record<string, unknown>)) {
      return String((detail as Record<string, unknown>).message);
    }
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function queueOf(session: DiscoverySession): QueueKey {
  if (LIVE_STATES.includes(session.status)) return "live";
  if (["PAUSED", "STOPPED", "NOT_STARTED"].includes(session.status)) return "paused";
  if (session.status === "COMPLETED") return "finished";
  return "failed";
}

/* ── evidence sub-panels ─────────────────────────────────────────────── */

function ActionLocators({ locatorEvidence }: { locatorEvidence: DiscoveryLocatorEvidence | null }) {
  const [open, setOpen] = useState(false);
  if (!locatorEvidence?.candidates?.length) return null;
  return (
    <div className="mt-2">
      <button onClick={() => setOpen((v) => !v)} className="text-[11px] font-bold text-[#1b59f8]">
        {open ? "Hide" : "Show"} locators ({locatorEvidence.candidates.length})
      </button>
      {open && (
        <div className="mt-2 space-y-1.5 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
          {locatorEvidence.candidates.map((candidate, index) => (
            <div key={index} className="flex flex-wrap items-center gap-1.5 text-[11px]">
              <Badge variant="outline">{candidate.strategy}</Badge>
              <code className="rounded bg-white px-1.5 py-0.5 font-mono text-slate-600">{candidate.locator}</code>
              <span className="font-semibold text-slate-400">confidence {candidate.confidence}</span>
              <Badge variant={candidate.unique ? "success" : "warning"}>{candidate.unique ? "Unique" : "Ambiguous"}</Badge>
              {!candidate.validated && <Badge variant="outline">Unvalidated</Badge>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ActionEvidence({ sessionId, actionId }: { sessionId: number; actionId: number }) {
  const [open, setOpen] = useState(false);
  const [viewingCaptureId, setViewingCaptureId] = useState<number | null>(null);
  const capturesQuery = useDiscoveryCaptures(sessionId, actionId, open);
  const contentQuery = useCaptureContent(sessionId, viewingCaptureId, viewingCaptureId !== null);

  const labelFor = (captureType: string) =>
    captureType === "console_log" ? "Console" : captureType === "network_log" ? "Network" : "Screenshot";

  return (
    <div className="mt-2">
      <button onClick={() => setOpen((v) => !v)} className="text-[11px] font-bold text-[#1b59f8]">
        {open ? "Hide" : "Show"} captured evidence
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {capturesQuery.isLoading && <p className="text-[11px] font-semibold text-slate-400">Loading…</p>}
          <div className="flex flex-wrap gap-1.5">
            {(capturesQuery.data ?? []).map((capture) => (
              <Button
                key={capture.id}
                size="sm"
                variant="outline"
                className="h-7"
                disabled={capture.capture_type === "screenshot"}
                title={capture.capture_type === "screenshot" ? "Screenshot viewing is not available yet — the file is still written to the evidence workspace." : undefined}
                onClick={() => setViewingCaptureId(capture.id)}
              >
                {labelFor(capture.capture_type)}
              </Button>
            ))}
            {capturesQuery.data?.length === 0 && (
              <p className="text-[11px] font-semibold text-slate-400">No evidence was captured for this step.</p>
            )}
          </div>
          {viewingCaptureId !== null && (
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-[11px] leading-5 text-slate-600">
              {contentQuery.isLoading ? "Loading…" : contentQuery.data || "No content."}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

/* ── new session drawer ──────────────────────────────────────────────── */

function NewSessionDrawer({
  open, projectId, applicationId, environment, environmentOptions, applicationName,
  onClose, onCreated,
}: {
  open: boolean;
  projectId: number;
  applicationId: number | null;
  environment: string;
  environmentOptions: string[];
  applicationName: string;
  onClose: () => void;
  onCreated: (sessionId: number) => void;
}) {
  const { toast } = useToast();
  const [mode, setMode] = useState<string>("GUIDED_USER");
  const [testCaseId, setTestCaseId] = useState<number | null>(null);
  const [purpose, setPurpose] = useState("");
  const [testCaseSearch, setTestCaseSearch] = useState("");

  const createSession = useCreateDiscoverySession(projectId);
  const eligibleQuery = useEligibleTestCases(projectId, applicationId, mode);

  useEffect(() => {
    if (open) { setMode("GUIDED_USER"); setTestCaseId(null); setPurpose(""); setTestCaseSearch(""); }
  }, [open]);

  useEffect(() => { setTestCaseId(null); }, [mode, applicationId]);

  const needsTestCase = mode !== "FREE_USER_ACTION";
  const modeSpec = MODES.find((m) => m.value === mode)!;
  const eligible = useMemo(() => eligibleQuery.data ?? [], [eligibleQuery.data]);
  const filteredCases = useMemo(() => {
    const q = testCaseSearch.trim().toLowerCase();
    if (!q) return eligible;
    return eligible.filter((tc) => `${tc.display_id} ${tc.title}`.toLowerCase().includes(q));
  }, [eligible, testCaseSearch]);
  const eligibleCount = eligible.filter((tc) => tc.eligible).length;

  // Client-side gates; the backend stays authoritative. Listed rather than
  // surfaced one at a time so nothing is a surprise on submit.
  const problems: string[] = [];
  if (!applicationId) problems.push("Select an application first — a session is always scoped to one registered application.");
  if (!environment) problems.push("Select an environment. Only environments with a URL configured in the registry can be recorded against.");
  if (needsTestCase && !testCaseId) problems.push("Select an approved, application-mapped test case to record against.");
  if (!needsTestCase && !purpose.trim()) problems.push("Free User-Action Recording needs a written purpose — it is the only record of what the session was for.");
  if (!needsTestCase && purpose.trim() && purpose.trim().length < 10) problems.push("Give the purpose at least 10 characters so it means something to the next reviewer.");

  async function submit() {
    if (problems.length > 0 || !applicationId) return;
    try {
      const created = await createSession.mutateAsync({
        application_id: applicationId, environment, mode,
        test_case_id: testCaseId, purpose: purpose.trim() || null,
      });
      toast({ title: `Session #${created.id} created — evaluate readiness, then start it.` });
      onCreated(created.id);
    } catch (error) {
      toast({ title: messageFromError(error, "Could not create the session"), variant: "error" });
    }
  }

  return (
    <Drawer open={open} onOpenChange={(next) => !next && !createSession.isPending && onClose()}>
      <DrawerContent size="2xl">
        <DrawerHeader>
          <div>
            <DrawerTitle>New Discovery Session</DrawerTitle>
            <DrawerDescription>
              Record governed evidence against {applicationName || "an application"}{environment ? ` in ${environment}` : ""}.
            </DrawerDescription>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={problems.length ? "warning" : "success"}>{problems.length ? "Incomplete" : "Ready to create"}</Badge>
            <button aria-label="Close" onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-50">
              <X className="h-4 w-4" />
            </button>
          </div>
        </DrawerHeader>

        <DrawerBody>
          <section className="space-y-3">
            <h4 className="text-xs font-extrabold uppercase tracking-wide text-slate-500">Step 1 · Recording mode</h4>
            <div className="space-y-2">
              {MODES.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setMode(option.value)}
                  className={cn(
                    "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition",
                    mode === option.value ? "border-[#1b59f8] bg-blue-50/50" : "border-slate-200 hover:bg-slate-50",
                  )}
                >
                  <span className={cn(
                    "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2",
                    mode === option.value ? "border-[#1b59f8]" : "border-slate-300",
                  )}>
                    {mode === option.value && <span className="h-2 w-2 rounded-full bg-[#1b59f8]" />}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-xs font-extrabold text-slate-900">{option.label}</span>
                    <span className="mt-0.5 block text-[11px] font-semibold leading-4 text-slate-500">{option.hint}</span>
                  </span>
                </button>
              ))}
            </div>
          </section>

          <section className="space-y-3 border-t border-slate-100 pt-4">
            <h4 className="text-xs font-extrabold uppercase tracking-wide text-slate-500">
              Step 2 · {needsTestCase ? "Test context" : "Session purpose"}
            </h4>

            {needsTestCase ? (
              <>
                <p className="text-[11px] font-semibold leading-4 text-slate-500">
                  {modeSpec.label} replays an approved test case. Only cases that are approved <em>and</em> mapped to this
                  application can be recorded — every other case is listed with the exact reason it is blocked.
                </p>
                {!applicationId ? (
                  <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs font-semibold text-amber-800">
                    Select an application to see which test cases are eligible.
                  </p>
                ) : eligibleQuery.isLoading ? (
                  <p className="text-xs font-semibold text-slate-400">Loading eligible test cases…</p>
                ) : eligible.length === 0 ? (
                  <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs font-semibold text-amber-800">
                    This project has no test cases yet. Generate and approve one in Test Design first.
                  </p>
                ) : (
                  <>
                    <div className="flex items-center justify-between gap-2">
                      <div className="relative flex-1">
                        <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
                        <input
                          value={testCaseSearch}
                          onChange={(e) => setTestCaseSearch(e.target.value)}
                          placeholder="Search test cases…"
                          className="h-9 w-full rounded-lg border border-slate-200 pl-9 pr-3 text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-100"
                        />
                      </div>
                      <span className="shrink-0 text-[11px] font-bold text-slate-500">
                        {eligibleCount} of {eligible.length} eligible
                      </span>
                    </div>
                    <div className="max-h-64 space-y-1.5 overflow-y-auto">
                      {filteredCases.map((tc: EligibleTestCase) => (
                        <button
                          key={tc.test_case_id}
                          disabled={!tc.eligible}
                          onClick={() => setTestCaseId(tc.test_case_id)}
                          title={tc.blocking_reason ?? undefined}
                          className={cn(
                            "flex w-full items-start justify-between gap-3 rounded-lg border p-2.5 text-left transition",
                            !tc.eligible && "cursor-not-allowed border-slate-100 bg-slate-50",
                            tc.eligible && testCaseId === tc.test_case_id && "border-[#1b59f8] bg-blue-50/50",
                            tc.eligible && testCaseId !== tc.test_case_id && "border-slate-200 hover:bg-slate-50",
                          )}
                        >
                          <span className="min-w-0">
                            <span className="block font-mono text-[11px] font-extrabold text-[#1b59f8]">{tc.display_id}</span>
                            <span className={cn("mt-0.5 block truncate text-xs font-bold", tc.eligible ? "text-slate-800" : "text-slate-400")}>
                              {tc.title}
                            </span>
                            {!tc.eligible && tc.blocking_reason && (
                              <span className="mt-1 block text-[11px] font-semibold leading-4 text-amber-700">{tc.blocking_reason}</span>
                            )}
                          </span>
                          <span className="shrink-0">
                            {tc.eligible ? <Badge variant="success">Eligible</Badge> : <Badge variant="secondary">Blocked</Badge>}
                          </span>
                        </button>
                      ))}
                      {filteredCases.length === 0 && (
                        <p className="py-4 text-center text-xs font-semibold text-slate-400">No test cases match that search.</p>
                      )}
                    </div>
                  </>
                )}
              </>
            ) : (
              <label className="block">
                <span className="mb-1 block text-[10px] font-extrabold uppercase tracking-wide text-slate-500">
                  What is this session for? *
                </span>
                <textarea
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value)}
                  rows={4}
                  placeholder="e.g. Reverse-engineer the promo-code path through checkout so we can write cases against it."
                  className="w-full rounded-lg border border-slate-200 p-3 text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-100"
                />
                <span className="mt-1 block text-[11px] font-semibold text-slate-400">
                  Free recording has no test case behind it, so this text is the only record of intent. It appears on the
                  session everywhere it is referenced.
                </span>
              </label>
            )}
          </section>

          <section className="space-y-2 border-t border-slate-100 pt-4">
            <h4 className="text-xs font-extrabold uppercase tracking-wide text-slate-500">Step 3 · Review</h4>
            <div className="rounded-lg border border-slate-200 p-3">
              <div className="grid grid-cols-2 gap-4">
                <InfoPair label="Application" value={applicationName || "Not selected"} />
                <InfoPair label="Environment" value={environment || "Not selected"} />
                <InfoPair label="Mode" value={modeSpec.label} />
                <InfoPair
                  label={needsTestCase ? "Test case" : "Purpose"}
                  value={needsTestCase
                    ? (eligible.find((tc) => tc.test_case_id === testCaseId)?.display_id ?? "Not selected")
                    : (purpose.trim() ? `${purpose.trim().slice(0, 40)}${purpose.trim().length > 40 ? "…" : ""}` : "Not written")}
                />
              </div>
              {problems.length > 0 ? (
                <div className="mt-3 space-y-1.5 border-t border-slate-100 pt-3">
                  {problems.map((problem) => (
                    <p key={problem} className="flex items-start gap-1.5 text-[11px] font-semibold text-amber-800">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{problem}
                    </p>
                  ))}
                </div>
              ) : (
                <p className="mt-3 flex items-center gap-1.5 border-t border-slate-100 pt-3 text-[11px] font-bold text-emerald-700">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  Creating the session does not start it. You will get a readiness check first.
                </p>
              )}
            </div>
          </section>
        </DrawerBody>

        <DrawerFooter>
          <Button variant="outline" size="sm" disabled={createSession.isPending} onClick={onClose}>Cancel</Button>
          <Button
            size="sm"
            disabled={createSession.isPending || problems.length > 0}
            title={problems.length > 0 ? problems[0] : undefined}
            onClick={submit}
          >
            {createSession.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            Create Session
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

/* ── main view ───────────────────────────────────────────────────────── */

export function DiscoverySessionView({ projectId }: { projectId: number }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { toast } = useToast();

  const applicationId = Number(searchParams.get("application")) || null;
  const environment = searchParams.get("environment") || "";
  const sessionIdParam = Number(searchParams.get("session")) || null;

  const [drawerTab, setDrawerTab] = useState<DrawerTab>("next");
  const [queueTab, setQueueTab] = useState<QueueKey>("all");
  const [search, setSearch] = useState("");
  const [modeFilter, setModeFilter] = useState("");
  const [newSessionOpen, setNewSessionOpen] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const applicationsQuery = useQuery({
    queryKey: ["applications-for-project", projectId],
    queryFn: async () => (await applicationsApi.getForProject(projectId)).data,
    enabled: projectId > 0,
  });
  const applications: ProjectApplication[] = applicationsQuery.data?.applications ?? [];
  const application = applications.find((a) => a.id === applicationId) ?? null;
  const environmentOptions = application ? Object.keys(application.environment_urls || {}) : [];

  const sessionsQuery = useDiscoverySessions(projectId, applicationId);
  const sessionQuery = useDiscoverySession(sessionIdParam);
  const readinessQuery = useDiscoveryReadiness(sessionIdParam);
  const actionsQuery = useDiscoveryActions(sessionIdParam);
  const checkpointsQuery = useDiscoveryCheckpoints(sessionIdParam);
  const activityQuery = useDiscoveryActivity(sessionIdParam);

  const issueCommand = useIssueDiscoveryCommand(projectId, sessionIdParam);
  const correctAction = useCorrectDiscoveryAction(projectId, sessionIdParam);
  const recordAction = useRecordFreeAction(projectId, sessionIdParam);

  const session = sessionQuery.data;
  const sessions = useMemo(() => sessionsQuery.data ?? [], [sessionsQuery.data]);

  const [freeActionFamily, setFreeActionFamily] = useState<string>("navigate");
  const [freeActionUrl, setFreeActionUrl] = useState("");
  const [freeActionTargetRef, setFreeActionTargetRef] = useState("");
  const [freeActionTargetSemantic, setFreeActionTargetSemantic] = useState("");
  const [freeActionInputText, setFreeActionInputText] = useState("");
  const [skipReason, setSkipReason] = useState("");
  const [rollbackCheckpointId, setRollbackCheckpointId] = useState("");
  const [rollbackReason, setRollbackReason] = useState("");
  const [showModifyForm, setShowModifyForm] = useState(false);

  const isAgentDriven = session?.mode === "SUPERVISED_AGENT_DRIVEN";
  const isStepDriven = session?.mode === "GUIDED_USER" || isAgentDriven;
  const manualControl = Boolean(session?.metadata_?.manual_control);

  /**
   * The step plan is worth knowing about outside RECORDING too.
   *
   * A step-driven session that runs out of approved steps self-pauses rather
   * than auto-completing, so the "no more steps" message only ever rendered
   * in a state the session had already left — the user landed on PAUSED with
   * Complete greyed out and no indication that Stop was the way forward.
   */
  const currentStepQuery = useCurrentStep(
    sessionIdParam,
    Boolean(isStepDriven && session && !TERMINAL_STATES.includes(session.status)),
  );

  const eligibleQuery = useEligibleTestCases(projectId, applicationId, session?.mode ?? "GUIDED_USER");

  /**
   * Applies every change in one push. Two `setParam` calls in a row both read
   * the same render's `searchParams`, so the second silently discarded the
   * first — changing application while a session was open kept the old
   * application in the URL.
   */
  function setParams(changes: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(changes).forEach(([key, value]) => {
      if (value) params.set(key, value);
      else params.delete(key);
    });
    router.push(`${pathname}?${params.toString()}`);
  }

  function setParam(key: string, value: string | null) {
    setParams({ [key]: value });
  }

  async function runCommand(
    command: string,
    options?: { params?: Record<string, unknown>; reason?: string; successMessage?: string },
  ) {
    setError("");
    try {
      await issueCommand.mutateAsync({ command, params: options?.params, reason: options?.reason });
      if (options?.successMessage) setNotice(options.successMessage);
    } catch (commandError) {
      setError(messageFromError(commandError, `Could not ${command.replace(/_/g, " ")} this session.`));
    }
  }

  const readiness = readinessQuery.data;
  const canStart = session?.status === "NOT_STARTED";
  const canPause = session?.status === "RECORDING";
  const canResume = session?.status === "PAUSED" || session?.status === "STOPPED";
  const canStop = session?.status === "RECORDING" || session?.status === "PAUSED";
  const canComplete = session?.status === "STOPPED";
  const canCancel = ["NOT_STARTED", "PAUSED", "STOPPED"].includes(session?.status ?? "");
  const canEmergencyStop = !TERMINAL_STATES.includes(session?.status ?? "");

  const testCase = useMemo(
    () => eligibleQuery.data?.find((tc) => tc.test_case_id === session?.test_case_id),
    [eligibleQuery.data, session?.test_case_id],
  );

  const actions = useMemo(() => actionsQuery.data ?? [], [actionsQuery.data]);
  const latestAction = actions.length ? actions[actions.length - 1] : undefined;
  const latestSnapshotExcerpt = latestAction?.post_state?.accessibility_snapshot_excerpt as string | undefined;
  const canRecordFreeAction =
    (session?.mode === "FREE_USER_ACTION" || (isAgentDriven && manualControl)) && session?.status === "RECORDING";

  // Every approved step captured, approved, modified or skipped: the session
  // has done all the work it was configured to do. Resuming would re-dispatch
  // a task that finds the same empty queue and pauses again within a second.
  const stepPlanExhausted = Boolean(
    isStepDriven && session?.started_at && currentStepQuery.isSuccess && !currentStepQuery.data?.text,
  );
  const resumeIsPointless = stepPlanExhausted && !manualControl;

  const included = useMemo(() => actions.filter((a) => a.inclusion_state !== "excluded"), [actions]);
  const screens = useMemo(
    () => Array.from(new Set(included.map((a) => a.target_screen_ref).filter((s): s is string => Boolean(s)))),
    [included],
  );
  const performed = included.filter((a) => a.action_family !== "read");
  const grounded = included.filter((a) => a.locator_confidence != null);
  const withIssues = included.filter((a) => a.issue_note);

  /* ── list ───────────────────────────────────────────────────────── */
  const queueCounts = useMemo(() => {
    const counts: Record<QueueKey, number> = { all: sessions.length, live: 0, paused: 0, finished: 0, failed: 0 };
    sessions.forEach((s) => { counts[queueOf(s)] += 1; });
    return counts;
  }, [sessions]);

  const filteredSessions = useMemo(() => {
    const q = search.trim().toLowerCase();
    return sessions.filter((s) => {
      if (queueTab !== "all" && queueOf(s) !== queueTab) return false;
      if (modeFilter && s.mode !== modeFilter) return false;
      if (!q) return true;
      return [`#${s.id}`, s.mode, s.status, s.environment, s.purpose, s.terminal_reason]
        .filter(Boolean).join(" ").toLowerCase().includes(q);
    });
  }, [sessions, queueTab, modeFilter, search]);

  /* ── guidance ───────────────────────────────────────────────────── */
  const guidance = (() => {
    if (!applicationId) {
      return { tone: "blue" as const, title: "Choose an application to record against", detail: "A discovery session is always scoped to one registered application and one of its configured environments." };
    }
    if (environmentOptions.length === 0) {
      return {
        tone: "amber" as const,
        title: "This application has no environment URLs configured",
        detail: "A session cannot open a browser without a target URL. Add at least one environment to this application in the registry.",
        action: <Button size="sm" variant="outline" onClick={() => { window.location.href = `/applications?project=${projectId}`; }}>Open Application Registry</Button>,
      };
    }
    if (!environment) {
      return { tone: "blue" as const, title: "Choose an environment", detail: `${application?.name ?? "This application"} has ${environmentOptions.length} configured: ${environmentOptions.join(", ")}.` };
    }
    const live = sessions.filter((s) => LIVE_STATES.includes(s.status));
    if (live.length > 0) {
      return {
        tone: "emerald" as const,
        title: `${live.length} session${live.length === 1 ? " is" : "s are"} recording now`,
        detail: "Open it to watch each step land, pause it, or take manual control.",
        action: <Button size="sm" variant="outline" onClick={() => setQueueTab("live")}>Show recording</Button>,
      };
    }
    const needsFinishing = sessions.filter((s) => ["PAUSED", "STOPPED"].includes(s.status));
    if (needsFinishing.length > 0) {
      return {
        tone: "amber" as const,
        title: `${needsFinishing.length} session${needsFinishing.length === 1 ? "" : "s"} started but never finished`,
        detail: "A discovery session never completes on its own — it has to be stopped and then completed before a model can be built from it.",
        action: <Button size="sm" variant="outline" onClick={() => setQueueTab("paused")}>Show unfinished</Button>,
      };
    }
    if (sessions.length === 0) {
      return {
        tone: "blue" as const,
        title: "No sessions recorded for this application yet",
        detail: "A session captures real evidence — screens, locators, network logs — which everything downstream is grounded in.",
        action: <Button size="sm" onClick={() => setNewSessionOpen(true)}><Plus className="h-3.5 w-3.5" /> New Session</Button>,
      };
    }
    return {
      tone: "emerald" as const,
      title: `${queueCounts.finished} completed session${queueCounts.finished === 1 ? "" : "s"} ready to build from`,
      detail: "Build an Application Model from a completed session to turn its evidence into reviewed structure.",
      action: (
        <Button size="sm" variant="outline" onClick={() => { window.location.href = `/applications?view=model&project=${projectId}&application=${applicationId}`; }}>
          <Layers3 className="h-3.5 w-3.5" /> Open Application Model
        </Button>
      ),
    };
  })();

  /* ── the one next move for the open session ─────────────────────── */
  const nextMove = (() => {
    if (!session) return null;
    if (session.status === "NOT_STARTED") {
      return readiness?.ready
        ? { tone: "blue" as const, title: "Ready to start", detail: "Every readiness check passed. Starting opens a browser session and begins capturing.", action: <Button size="sm" disabled={issueCommand.isPending} onClick={() => runCommand("start", { successMessage: "Session started." })}><Play className="h-3.5 w-3.5" /> Start Recording</Button> }
        : { tone: "amber" as const, title: "Not ready to start", detail: "One or more readiness checks are failing. Each is listed below with what it needs." };
    }
    if (LIVE_STATES.includes(session.status)) {
      return { tone: "emerald" as const, title: "Recording", detail: sessionPhase(session.status).hint, action: <Button size="sm" variant="outline" disabled={!canPause || issueCommand.isPending} onClick={() => runCommand("pause")}><Pause className="h-3.5 w-3.5" /> Pause</Button> };
    }
    if (stepPlanExhausted && !TERMINAL_STATES.includes(session.status)) {
      return session.status === "STOPPED"
        ? { tone: "blue" as const, title: "Every approved step has been captured", detail: "Complete the session to make its evidence available for an Application Model.", action: <Button size="sm" disabled={issueCommand.isPending} onClick={() => runCommand("complete", { successMessage: "Session completed." })}><CheckCircle2 className="h-3.5 w-3.5" /> Complete</Button> }
        : { tone: "blue" as const, title: "Every approved step has been captured", detail: "This session will not record anything further. Stop it, then complete it — a discovery session never finishes on its own.", action: <Button size="sm" disabled={!canStop || issueCommand.isPending} onClick={() => runCommand("stop", { successMessage: "Session stopped." })}><Square className="h-3.5 w-3.5" /> Stop</Button> };
    }
    if (session.status === "PAUSED") {
      return { tone: "amber" as const, title: "Paused", detail: "Resume to keep recording from the last checkpoint, or stop to finish the session.", action: <Button size="sm" variant="outline" disabled={!readiness?.ready || issueCommand.isPending} title={readiness?.ready ? undefined : "Readiness checks must pass before resuming."} onClick={() => runCommand("resume", { params: { recovery_option: "continue" } })}><Play className="h-3.5 w-3.5" /> Resume</Button> };
    }
    if (session.status === "STOPPED") {
      return { tone: "blue" as const, title: "Stopped — one step left", detail: "Complete the session to make its evidence available for an Application Model.", action: <Button size="sm" disabled={issueCommand.isPending} onClick={() => runCommand("complete", { successMessage: "Session completed." })}><CheckCircle2 className="h-3.5 w-3.5" /> Complete</Button> };
    }
    if (session.status === "COMPLETED") {
      return screens.length === 0
        ? { tone: "red" as const, title: "Completed, but nothing was grounded", detail: "No action recorded which screen it acted on, so an Application Model built from this session would be empty and is refused. Re-record it so each step names a screen." }
        : { tone: "emerald" as const, title: "Completed", detail: `${screens.length} screen${screens.length === 1 ? "" : "s"} captured with evidence. Build an Application Model from it.`, action: <Button size="sm" variant="outline" onClick={() => { window.location.href = `/applications?view=model&project=${projectId}&application=${session.application_id}`; }}><Layers3 className="h-3.5 w-3.5" /> Build Application Model</Button> };
    }
    return { tone: "red" as const, title: sessionPhase(session.status).label, detail: session.failure_detail || session.terminal_reason || sessionPhase(session.status).hint };
  })();

  const drawerTabs: DrawerTabSpec<DrawerTab>[] = [
    { key: "next", label: "What's next" },
    { key: "findings", label: `Evidence (${actions.length})` },
    {
      key: "control", label: "Live control",
      available: Boolean(session && !TERMINAL_STATES.includes(session.status)),
      reason: "This session has ended — there is nothing left to control.",
    },
    { key: "checkpoints", label: `Checkpoints (${checkpointsQuery.data?.length ?? 0})` },
    { key: "activity", label: "Audit trail" },
  ];

  async function submitFreeAction() {
    if (freeActionFamily === "navigate" && !freeActionUrl.trim()) {
      toast({ title: "Enter a URL to navigate to", variant: "error" });
      return;
    }
    if ((freeActionFamily === "click" || freeActionFamily === "input") && !freeActionTargetRef.trim()) {
      toast({ title: "Enter a target ref from the latest snapshot", variant: "error" });
      return;
    }
    if (freeActionFamily === "input" && !freeActionInputText) {
      toast({ title: "Enter the text to type", variant: "error" });
      return;
    }
    try {
      await recordAction.mutateAsync({
        action_family: freeActionFamily,
        url: freeActionFamily === "navigate" ? freeActionUrl.trim() : undefined,
        target_ref: freeActionTargetRef.trim() || undefined,
        target_semantic: freeActionTargetSemantic.trim() || undefined,
        input_text: freeActionFamily === "input" ? freeActionInputText : undefined,
      });
      setNotice("Action queued — it appears in Evidence once the recorder performs it.");
      setFreeActionUrl(""); setFreeActionTargetRef(""); setFreeActionTargetSemantic(""); setFreeActionInputText("");
    } catch (actionError) {
      setError(messageFromError(actionError, "Could not record that action."));
    }
  }

  async function modifyNextAction() {
    if (freeActionFamily === "navigate" && !freeActionUrl.trim()) {
      toast({ title: "Enter a URL to navigate to", variant: "error" });
      return;
    }
    if ((freeActionFamily === "click" || freeActionFamily === "input") && !freeActionTargetRef.trim()) {
      toast({ title: "Enter a target ref from the latest snapshot", variant: "error" });
      return;
    }
    await runCommand("modify_next_action", {
      params: {
        action_family: freeActionFamily,
        url: freeActionFamily === "navigate" ? freeActionUrl.trim() : undefined,
        target_ref: freeActionTargetRef.trim() || undefined,
        target_semantic: freeActionTargetSemantic.trim() || undefined,
        input_text: freeActionFamily === "input" ? freeActionInputText : undefined,
      },
      successMessage: "Modified action queued for execution.",
    });
    setFreeActionUrl(""); setFreeActionTargetRef(""); setFreeActionTargetSemantic(""); setFreeActionInputText("");
    setShowModifyForm(false);
  }

  return (
    <div className="space-y-4 pb-8">
      <Breadcrumb trail={["QAI Command Center","Applications", "Live Discovery Session"]} />

      <WorkspaceHeader
        icon={Radar}
        tone="blue"
        title="Live Discovery Session"
        badge="P1-S4 UI-015"
        description="Observe, record and ground application behaviour with governed evidence."
        actions={
          <>
            <Button variant="outline" size="sm" className="h-9" disabled={sessionsQuery.isFetching} onClick={() => sessionsQuery.refetch()}>
              <RefreshCw className={cn("h-4 w-4", sessionsQuery.isFetching && "animate-spin")} /> Refresh
            </Button>
            <Button
              size="sm" className="h-9"
              disabled={!applicationId || !environment}
              title={!applicationId ? "Select an application first." : !environment ? "Select an environment first." : undefined}
              onClick={() => setNewSessionOpen(true)}
            >
              <Plus className="h-4 w-4" /> New Session
            </Button>
          </>
        }
      />

      <Notices error={error} notice={notice} onDismiss={() => { setError(""); setNotice(""); }} />

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-extrabold uppercase tracking-wide text-slate-500">Application</span>
          <select
            value={applicationId ?? ""}
            onChange={(e) => setParams({ application: e.target.value || null, session: null, environment: null })}
            className="h-9 w-60 rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
          >
            <option value="">Select application…</option>
            {applications.map((a) => <option key={a.id ?? a.key} value={a.id ?? ""}>{a.name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-extrabold uppercase tracking-wide text-slate-500">Environment</span>
          <select
            value={environment}
            disabled={!application}
            onChange={(e) => setParam("environment", e.target.value || null)}
            className="h-9 w-44 rounded-lg border border-slate-200 px-3 text-xs font-bold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100 disabled:bg-slate-50 disabled:text-slate-400"
          >
            <option value="">{environmentOptions.length === 0 && application ? "None configured" : "Select environment…"}</option>
            {environmentOptions.map((env) => <option key={env} value={env}>{env}</option>)}
          </select>
        </label>
        {application && (
          <div className="ml-auto flex items-center gap-2 text-[11px] font-semibold text-slate-500">
            <span className="font-mono font-bold text-[#1b59f8]">APP-{application.id}</span>
            <span>{application.key}</span>
            <a href={`/applications?view=model&project=${projectId}&application=${application.id}`} className="ml-2 inline-flex items-center gap-1 font-bold text-[#1b59f8]">
              <Layers3 className="h-3.5 w-3.5" /> Application Model <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        )}
      </div>

      <GuidanceCard {...guidance} />

      {applicationId && (
        <>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
            <StatCard title="Sessions" value={sessions.length} subtitle="Recorded for this application" icon={Radar} tone="blue" />
            <StatCard title="Recording Now" value={queueCounts.live} subtitle="Holding a live browser" icon={Activity} tone={queueCounts.live > 0 ? "emerald" : "slate"} />
            <StatCard title="Unfinished" value={queueCounts.paused} subtitle="Started but never completed" icon={Pause} tone={queueCounts.paused > 0 ? "amber" : "slate"} />
            <StatCard title="Completed" value={queueCounts.finished} subtitle="Eligible to build a model from" icon={CheckCircle2} tone="emerald" />
            <StatCard title="Failed" value={queueCounts.failed} subtitle="Cancelled, failed or emergency-stopped" icon={XCircle} tone={queueCounts.failed > 0 ? "red" : "slate"} />
          </div>

          <QueueTabs tabs={QUEUE_TABS} active={queueTab} counts={queueCounts} onChange={setQueueTab} />

          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-64 flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by session number, state, environment or purpose…"
                className="h-9 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-xs font-semibold text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
              />
            </div>
            <FilterSelect
              label="Mode" value={modeFilter} onChange={setModeFilter}
              options={[{ value: "", label: "Mode: All" }, ...MODES.map((m) => ({ value: m.value, label: m.label }))]}
            />
            {(search || modeFilter || queueTab !== "all") && (
              <button onClick={() => { setSearch(""); setModeFilter(""); setQueueTab("all"); }} className="text-xs font-bold text-[#1b59f8]">
                Clear Filters
              </button>
            )}
          </div>

          <ListShell
            gridTemplate={SESSION_GRID}
            minWidth={1050}
            columns={["Session", "Mode", "State", "Recording against", "Steps", "Screens", "Started"]}
            loading={sessionsQuery.isLoading}
            empty={filteredSessions.length === 0 ? (
              <EmptyState
                title={sessions.length === 0 ? "No discovery sessions yet" : "No sessions match these filters"}
                detail={sessions.length === 0
                  ? "Recording a session is the first step in grounding tests against the real application. Nothing downstream — models, locators, automation — can be built without one."
                  : "Try clearing the search box or switching back to the All queue."}
                action={sessions.length === 0
                  ? <Button size="sm" disabled={!applicationId || !environment} title={!environment ? "Select an environment first." : undefined} onClick={() => setNewSessionOpen(true)}><Plus className="h-3.5 w-3.5" /> New Session</Button>
                  : <Button size="sm" variant="outline" onClick={() => { setSearch(""); setModeFilter(""); setQueueTab("all"); }}>Clear Filters</Button>}
              />
            ) : undefined}
            footer={<span className="text-xs font-semibold text-slate-500">Showing {filteredSessions.length} of {sessions.length} sessions</span>}
          >
            {filteredSessions.map((row) => {
              const phase = sessionPhase(row.status);
              const modeLabel = MODES.find((m) => m.value === row.mode)?.label ?? row.mode;
              return (
                <ListRow
                  key={row.id}
                  gridTemplate={SESSION_GRID}
                  selected={sessionIdParam === row.id}
                  onClick={() => { setParam("session", String(row.id)); setDrawerTab("next"); }}
                >
                  <span className="font-mono font-extrabold text-[#1b59f8]">#{row.id}</span>
                  <span className="truncate font-semibold text-slate-600">{modeLabel}</span>
                  <span className="flex items-center gap-1.5">
                    <Badge variant={STATE_BADGE[row.status] ?? "outline"} title={row.status}>{phase.label}</Badge>
                  </span>
                  <span className="truncate font-semibold text-slate-600" title={row.purpose ?? undefined}>
                    {row.purpose || (row.test_case_id ? `Test case #${row.test_case_id}` : "—")}
                  </span>
                  <span className="font-bold text-slate-700">{row.current_step_index}</span>
                  <span className="font-semibold text-slate-500">{row.environment}</span>
                  <span className="truncate font-semibold text-slate-500">
                    {row.started_at ? new Date(row.started_at).toLocaleString() : "Not started"}
                  </span>
                </ListRow>
              );
            })}
          </ListShell>
        </>
      )}

      <NewSessionDrawer
        open={newSessionOpen}
        projectId={projectId}
        applicationId={applicationId}
        environment={environment}
        environmentOptions={environmentOptions}
        applicationName={application?.name ?? ""}
        onClose={() => setNewSessionOpen(false)}
        onCreated={(id) => { setNewSessionOpen(false); setParam("session", String(id)); setDrawerTab("next"); }}
      />

      {/* ── session drawer ──────────────────────────────────────────── */}
      <Drawer open={!!sessionIdParam} onOpenChange={(open) => !open && setParam("session", null)}>
        <DrawerContent size="xl">
          {session ? (
            <div className="flex h-full flex-col">
              <div className="border-b border-slate-100 p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-lg font-extrabold text-slate-950">Session #{session.id}</span>
                    <Badge variant={STATE_BADGE[session.status] ?? "outline"} title={session.status}>
                      {sessionPhase(session.status).label}
                    </Badge>
                    {manualControl && <Badge variant="info">Manual control</Badge>}
                  </div>
                  <button onClick={() => setParam("session", null)} aria-label="Close" className="rounded-md p-1 text-slate-500 hover:bg-slate-50">
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <h2 className="mt-4 text-base font-extrabold text-slate-950">
                  {MODES.find((m) => m.value === session.mode)?.label ?? session.mode}
                </h2>
                <p className="mt-2 text-xs font-semibold text-slate-500">
                  {session.environment}
                  {session.purpose
                    ? <> · {session.purpose}</>
                    : testCase
                      ? <> · <span className="text-[#1b59f8]">{testCase.display_id}</span> {testCase.title}</>
                      : session.test_case_id ? <> · test case #{session.test_case_id}</> : null}
                  {" · "}exact state <span className="font-mono">{session.status}</span>
                </p>
              </div>

              <DrawerTabBar tabs={drawerTabs} active={drawerTab} onChange={setDrawerTab} />

              <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50/50 p-4">
                {/* ── what's next ─────────────────────────────────── */}
                {drawerTab === "next" && (
                  <>
                    {nextMove && <GuidanceCard {...nextMove} />}

                    <DrawerCard
                      title="Readiness"
                      icon={ShieldCheck}
                      action={
                        <Button size="sm" variant="outline" className="h-7" onClick={() => readinessQuery.refetch()}>
                          <RefreshCw className={cn("h-3 w-3", readinessQuery.isFetching && "animate-spin")} /> Re-evaluate
                        </Button>
                      }
                    >
                      {readinessQuery.isLoading ? (
                        <p className="text-xs font-semibold text-slate-400">Evaluating…</p>
                      ) : (readiness?.checks ?? []).length === 0 ? (
                        <p className="text-xs font-semibold text-slate-400">No readiness checks returned for this session.</p>
                      ) : (
                        <div className="grid grid-cols-1 gap-x-8 md:grid-cols-2">
                          {(readiness?.checks ?? []).map((check) => (
                            <ChecklistRow
                              key={check.name}
                              label={check.name.replace(/_/g, " ")}
                              state={check.passed ? "pass" : "blocked"}
                              detail={check.detail}
                            />
                          ))}
                        </div>
                      )}
                    </DrawerCard>

                    <DrawerCard title="All session controls" icon={Target}>
                      <p className="mb-3 text-[11px] font-semibold leading-4 text-slate-500">
                        Only the transitions your session&apos;s current state allows are enabled. Hover a disabled one to
                        see why.
                      </p>
                      <div className="flex flex-wrap gap-2">
                        <Button size="sm" disabled={!canStart || !readiness?.ready || issueCommand.isPending}
                          title={!canStart ? "Only a session that has not started can be started." : !readiness?.ready ? "Readiness checks must pass first." : undefined}
                          onClick={() => runCommand("start", { successMessage: "Session started." })}>
                          <Play className="h-3.5 w-3.5" /> Start
                        </Button>
                        <Button size="sm" variant="outline" disabled={!canPause || issueCommand.isPending}
                          title={canPause ? undefined : "Only a recording session can be paused."}
                          onClick={() => runCommand("pause")}>
                          <Pause className="h-3.5 w-3.5" /> Pause
                        </Button>
                        <Button size="sm" variant="outline" disabled={!canResume || !readiness?.ready || resumeIsPointless || issueCommand.isPending}
                          title={resumeIsPointless
                            ? "Every approved step is already captured — resuming would immediately pause again. Stop the session instead."
                            : !canResume ? "Only a paused or stopped session can be resumed."
                            : !readiness?.ready ? "Readiness checks must pass first." : undefined}
                          onClick={() => runCommand("resume", { params: { recovery_option: "continue" } })}>
                          <Play className="h-3.5 w-3.5" /> Resume
                        </Button>
                        <Button size="sm" variant="outline"
                          disabled={(session.status !== "RECORDING" && session.status !== "PAUSED") || issueCommand.isPending}
                          title="Persist a resumable point you can roll back to."
                          onClick={() => runCommand("checkpoint", { successMessage: "Checkpoint saved." })}>
                          <Flag className="h-3.5 w-3.5" /> Save Checkpoint
                        </Button>
                        <Button size="sm" variant="outline" disabled={!canStop || issueCommand.isPending}
                          title={canStop ? "Close the browser and make the session completable." : "Only a recording or paused session can be stopped."}
                          onClick={() => runCommand("stop", { successMessage: "Session stopped." })}>
                          <Square className="h-3.5 w-3.5" /> Stop
                        </Button>
                        <Button size="sm" variant="outline" disabled={!canComplete || issueCommand.isPending}
                          title={canComplete ? "Finalize the session so a model can be built from it." : "A session must be stopped before it can be completed."}
                          onClick={() => runCommand("complete", { successMessage: "Session completed." })}>
                          <CheckCircle2 className="h-3.5 w-3.5" /> Complete
                        </Button>
                        <Button size="sm" variant="outline" disabled={!canCancel || issueCommand.isPending}
                          title={canCancel ? "End without producing usable evidence." : "A recording or finished session cannot be cancelled."}
                          onClick={() => runCommand("cancel", { successMessage: "Session cancelled." })}>
                          <XCircle className="h-3.5 w-3.5" /> Cancel
                        </Button>
                        <Button size="sm" variant="destructive" disabled={!canEmergencyStop || issueCommand.isPending}
                          title={canEmergencyStop ? "Terminate immediately without graceful teardown. This is terminal." : "This session has already ended."}
                          onClick={() => runCommand("emergency_stop", { successMessage: "Emergency stop issued." })}>
                          <StopCircle className="h-3.5 w-3.5" /> Emergency Stop
                        </Button>
                      </div>
                    </DrawerCard>

                    <DrawerCard title="Session detail" icon={Clock}>
                      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                        <InfoPair label="Environment" value={session.environment} />
                        <InfoPair label="Steps captured" value={session.current_step_index} />
                        <InfoPair label="Started" value={session.started_at ? new Date(session.started_at).toLocaleString() : "Not started"} />
                        <InfoPair label="Resume classification" value={session.resume_state_classification ?? "—"} />
                        <InfoPair label="Ended" value={session.terminal_at ? new Date(session.terminal_at).toLocaleString() : "—"} />
                        <InfoPair label="Framework" value={session.framework} />
                      </div>
                      {(session.terminal_reason || session.failure_detail) && (
                        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3">
                          {session.terminal_reason && <p className="text-[11px] font-bold text-red-800">{session.terminal_reason}</p>}
                          {session.failure_detail && <p className="mt-1 break-words text-[11px] font-semibold text-red-700">{session.failure_detail}</p>}
                        </div>
                      )}
                    </DrawerCard>
                  </>
                )}

                {/* ── evidence ────────────────────────────────────── */}
                {drawerTab === "findings" && (
                  <>
                    <DrawerCard title="What this session found" icon={Layers3}>
                      {actions.length === 0 ? (
                        <p className="text-xs font-semibold text-slate-500">
                          Nothing has been captured yet. Actions appear here as the recorder performs each step.
                        </p>
                      ) : (
                        <>
                          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                            <InfoPair label="Screens" value={screens.length} />
                            <InfoPair label="Actions performed" value={performed.length} />
                            <InfoPair label="With locator evidence" value={grounded.length} />
                            <InfoPair label="Could not be performed" value={withIssues.length} />
                          </div>
                          {screens.length === 0 ? (
                            <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-[11px] font-semibold leading-5 text-amber-800">
                              No action recorded which screen it acted on, so there is nothing to ground tests against.
                              An Application Model built from this session would be empty and is refused. Re-record it so
                              each step names a screen.
                            </p>
                          ) : (
                            <div className="mt-3 flex flex-wrap gap-1.5">
                              {screens.map((screen) => (
                                <span key={screen} className="rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-[11px] font-bold text-slate-600">
                                  {screen}
                                </span>
                              ))}
                            </div>
                          )}
                        </>
                      )}
                    </DrawerCard>

                    {actions.map((action) => (
                      <DrawerCard key={action.id} title={`Step ${action.sequence} · ${action.action_family}`} icon={Target}>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="min-w-0 flex-1 text-xs font-semibold text-slate-700">
                            {action.target_semantic || "No description recorded."}
                          </p>
                          <Badge variant={action.inclusion_state === "included" ? "success" : "secondary"}>
                            {action.inclusion_state}
                          </Badge>
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-4">
                          <InfoPair label="Screen" value={action.target_screen_ref || "Not recorded"} mono />
                          <InfoPair label="Locator confidence" value={action.locator_confidence != null ? `${action.locator_confidence}%` : "None"} />
                        </div>
                        {action.issue_note && (
                          <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-[11px] font-semibold text-amber-800">
                            {action.issue_note}
                          </p>
                        )}

                        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
                          {["included", "excluded"].map((state) => (
                            <Button
                              key={state}
                              size="sm" variant="outline" className="h-7"
                              disabled={action.inclusion_state === state || correctAction.isPending}
                              title={state === "excluded"
                                ? "Exclude this step from everything built on this session's evidence."
                                : "Include this step in everything built on this session's evidence."}
                              onClick={() => correctAction.mutate({ actionId: action.id, inclusion_state: state })}
                            >
                              Mark {state}
                            </Button>
                          ))}
                          {session.mode === "FREE_USER_ACTION" && (
                            <input
                              defaultValue={action.test_step_ref ?? ""}
                              placeholder="Map to a test case (e.g. TC-0042)"
                              onBlur={(e) => {
                                const value = e.target.value.trim();
                                if (value !== (action.test_step_ref ?? "")) {
                                  correctAction.mutate({
                                    actionId: action.id, inclusion_state: action.inclusion_state,
                                    mapped_test_step_ref: value,
                                  });
                                }
                              }}
                              className="h-7 flex-1 rounded-lg border border-slate-200 px-2 text-[11px] font-semibold outline-none focus:ring-2 focus:ring-blue-100"
                            />
                          )}
                        </div>

                        <ActionLocators locatorEvidence={action.locator_evidence} />
                        <ActionEvidence sessionId={session.id} actionId={action.id} />
                      </DrawerCard>
                    ))}
                  </>
                )}

                {/* ── live control ────────────────────────────────── */}
                {drawerTab === "control" && (
                  <>
                    {isAgentDriven && session.status === "RECORDING" && !manualControl && (
                      <DrawerCard
                        title="Proposed next step"
                        icon={Play}
                        action={
                          <Button size="sm" variant="outline" className="h-7" disabled={issueCommand.isPending} onClick={() => runCommand("take_manual_control", { successMessage: "You have manual control." })}>
                            Take manual control
                          </Button>
                        }
                      >
                        {currentStepQuery.data?.text ? (
                          <>
                            <p className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-xs font-semibold text-slate-800">
                              {currentStepQuery.data.text}
                            </p>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <Button size="sm" disabled={issueCommand.isPending} onClick={() => runCommand("approve_next_action", { successMessage: "Approved — executing the step." })}>
                                Approve &amp; execute
                              </Button>
                              <Button size="sm" variant="outline" onClick={() => setShowModifyForm((v) => !v)}>
                                {showModifyForm ? "Cancel modify" : "Modify"}
                              </Button>
                            </div>

                            {showModifyForm && (
                              <div className="mt-3 space-y-2 rounded-lg border border-violet-200 bg-white p-3">
                                <p className="text-[11px] font-semibold text-slate-500">
                                  Replace the proposed step with the action you specify. The original stays in the audit trail.
                                </p>
                                <select
                                  value={freeActionFamily}
                                  onChange={(e) => setFreeActionFamily(e.target.value)}
                                  className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-bold outline-none"
                                >
                                  {FREE_ACTION_FAMILIES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
                                </select>
                                {freeActionFamily === "navigate" && (
                                  <input value={freeActionUrl} onChange={(e) => setFreeActionUrl(e.target.value)} placeholder="https://…"
                                    className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none" />
                                )}
                                {(freeActionFamily === "click" || freeActionFamily === "input") && (
                                  <>
                                    <input value={freeActionTargetRef} onChange={(e) => setFreeActionTargetRef(e.target.value)} placeholder="Target ref from the snapshot below"
                                      className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none" />
                                    <input value={freeActionTargetSemantic} onChange={(e) => setFreeActionTargetSemantic(e.target.value)} placeholder="Description (e.g. Login button)"
                                      className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none" />
                                  </>
                                )}
                                {freeActionFamily === "input" && (
                                  <input value={freeActionInputText} onChange={(e) => setFreeActionInputText(e.target.value)} placeholder="Text to type"
                                    className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none" />
                                )}
                                <Button size="sm" className="w-full" disabled={issueCommand.isPending} onClick={modifyNextAction}>
                                  Execute modified action
                                </Button>
                              </div>
                            )}

                            <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
                              <input
                                value={skipReason}
                                onChange={(e) => setSkipReason(e.target.value)}
                                placeholder="Reason for skipping this step"
                                className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-100"
                              />
                              <Button
                                size="sm" variant="outline" className="w-full"
                                disabled={!skipReason.trim() || issueCommand.isPending}
                                title={skipReason.trim() ? undefined : "A reason is required — skipping is recorded against the test case."}
                                onClick={async () => { await runCommand("skip_action", { reason: skipReason.trim(), successMessage: "Step skipped." }); setSkipReason(""); }}
                              >
                                Skip this step
                              </Button>
                            </div>
                          </>
                        ) : (
                          <p className="text-xs font-semibold text-slate-500">
                            No approved steps remain. Stop the session, then complete it.
                          </p>
                        )}
                      </DrawerCard>
                    )}

                    {isAgentDriven && session.status === "RECORDING" && manualControl && (
                      <GuidanceCard
                        tone="blue"
                        title="You have manual control"
                        detail="The agent has stopped proposing steps. Record actions yourself below, or hand control back."
                        action={
                          <Button size="sm" variant="outline" disabled={issueCommand.isPending} onClick={() => runCommand("return_control_to_agent", { successMessage: "Control returned to the agent." })}>
                            Return control to agent
                          </Button>
                        }
                      />
                    )}

                    {canRecordFreeAction ? (
                      <>
                        <DrawerCard title="Perform an action" icon={Target}>
                          <div className="space-y-2">
                            <select
                              value={freeActionFamily}
                              onChange={(e) => setFreeActionFamily(e.target.value)}
                              className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-bold outline-none focus:ring-2 focus:ring-blue-100"
                            >
                              {FREE_ACTION_FAMILIES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
                            </select>
                            {freeActionFamily === "navigate" && (
                              <input value={freeActionUrl} onChange={(e) => setFreeActionUrl(e.target.value)} placeholder="https://…"
                                className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-100" />
                            )}
                            {(freeActionFamily === "click" || freeActionFamily === "input") && (
                              <>
                                <input value={freeActionTargetRef} onChange={(e) => setFreeActionTargetRef(e.target.value)} placeholder="Target ref — copy one from the snapshot below"
                                  className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-100" />
                                <input value={freeActionTargetSemantic} onChange={(e) => setFreeActionTargetSemantic(e.target.value)} placeholder="Description (e.g. Login button)"
                                  className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-100" />
                              </>
                            )}
                            {freeActionFamily === "read" && (
                              <input value={freeActionTargetSemantic} onChange={(e) => setFreeActionTargetSemantic(e.target.value)} placeholder="What did you observe? (optional)"
                                className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-100" />
                            )}
                            {freeActionFamily === "input" && (
                              <input value={freeActionInputText} onChange={(e) => setFreeActionInputText(e.target.value)} placeholder="Text to type"
                                className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-100" />
                            )}
                            <Button size="sm" className="w-full" disabled={recordAction.isPending} onClick={submitFreeAction}>
                              {recordAction.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                              Record action
                            </Button>
                          </div>
                          <p className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-[11px] font-semibold leading-4 text-slate-500">
                            Naming a field &quot;password&quot;, &quot;OTP&quot;, &quot;card&quot; and similar redacts the typed
                            value before it is ever stored. The real action still executes against the application.
                          </p>
                        </DrawerCard>

                        <DrawerCard title="Latest accessibility snapshot" icon={Search}>
                          <p className="mb-2 text-[11px] font-semibold text-slate-500">
                            Copy a ref from here into the target field above to act on that element.
                          </p>
                          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-3 text-[11px] leading-5 text-slate-600">
                            {latestSnapshotExcerpt || "No snapshot captured yet — perform an action to capture one."}
                          </pre>
                        </DrawerCard>
                      </>
                    ) : !isAgentDriven && (
                      <DrawerCard title="Live control" icon={Play}>
                        <p className="text-xs font-semibold leading-5 text-slate-500">
                          {session.mode === "GUIDED_USER"
                            ? "Guided recording walks the approved test case on its own — there is nothing to drive by hand. Watch progress on the Evidence tab."
                            : session.status === "RECORDING"
                              ? "This session is recording."
                              : "Actions can only be recorded while the session is recording. Start or resume it from the What's next tab."}
                        </p>
                      </DrawerCard>
                    )}

                    {session.status === "PAUSED" && (checkpointsQuery.data?.length ?? 0) > 0 && (
                      <DrawerCard title="Roll back to a checkpoint" icon={Flag}>
                        <p className="mb-2 text-[11px] font-semibold leading-4 text-slate-500">
                          Rolling back marks every action after the chosen checkpoint as rolled back and resets the step
                          index. Nothing is deleted — the audit trail keeps both.
                        </p>
                        <div className="space-y-2">
                          <select
                            value={rollbackCheckpointId}
                            onChange={(e) => setRollbackCheckpointId(e.target.value)}
                            className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-bold outline-none"
                          >
                            <option value="">Select a checkpoint…</option>
                            {(checkpointsQuery.data ?? []).filter((cp) => cp.resumable).map((cp) => (
                              <option key={cp.id} value={cp.id}>#{cp.sequence} · {cp.state_at_checkpoint} · {new Date(cp.created_at).toLocaleString()}</option>
                            ))}
                          </select>
                          <input
                            value={rollbackReason}
                            onChange={(e) => setRollbackReason(e.target.value)}
                            placeholder="Reason for rolling back"
                            className="h-9 w-full rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-100"
                          />
                          <Button
                            size="sm" variant="outline" className="w-full"
                            disabled={!rollbackCheckpointId || !rollbackReason.trim() || issueCommand.isPending}
                            title={!rollbackCheckpointId ? "Select a checkpoint." : !rollbackReason.trim() ? "A reason is required." : undefined}
                            onClick={async () => {
                              await runCommand("rollback", { params: { checkpoint_id: Number(rollbackCheckpointId) }, reason: rollbackReason.trim(), successMessage: "Rolled back to checkpoint." });
                              setRollbackReason("");
                            }}
                          >
                            Confirm roll back
                          </Button>
                        </div>
                      </DrawerCard>
                    )}
                  </>
                )}

                {/* ── checkpoints ─────────────────────────────────── */}
                {drawerTab === "checkpoints" && (
                  <DrawerCard title="Checkpoints" icon={Flag}>
                    <p className="mb-3 text-[11px] font-semibold leading-4 text-slate-500">
                      A checkpoint is a resumable point recorded automatically when the session pauses or stops, and
                      manually whenever you save one.
                    </p>
                    {(checkpointsQuery.data ?? []).length === 0 ? (
                      <p className="text-xs font-semibold text-slate-400">No checkpoints recorded yet.</p>
                    ) : (
                      <div className="space-y-2">
                        {(checkpointsQuery.data ?? []).map((cp) => (
                          <div key={cp.id} className="rounded-lg border border-slate-200 p-3">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="text-xs font-extrabold text-slate-800">#{cp.sequence} · {cp.state_at_checkpoint}</span>
                              <Badge variant={cp.resumable ? "success" : "secondary"}>{cp.resumable ? "Resumable" : "Not resumable"}</Badge>
                            </div>
                            <p className="mt-1 break-all font-mono text-[11px] font-semibold text-slate-500">{cp.sanitized_url ?? "—"}</p>
                            <p className="mt-1 text-[11px] font-semibold text-slate-400">{new Date(cp.created_at).toLocaleString()}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </DrawerCard>
                )}

                {/* ── audit trail ─────────────────────────────────── */}
                {drawerTab === "activity" && (
                  <DrawerCard title="Audit trail" icon={Activity}>
                    <p className="mb-3 text-[11px] font-semibold leading-4 text-slate-500">
                      Every state change on this session, in order, with who or what caused it.
                    </p>
                    {(activityQuery.data ?? []).length === 0 ? (
                      <p className="text-xs font-semibold text-slate-400">No activity recorded yet.</p>
                    ) : (
                      <div className="space-y-2">
                        {(activityQuery.data ?? []).map((event) => (
                          <div key={event.id} className="rounded-lg border border-slate-200 p-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-mono text-[11px] font-bold text-slate-700">
                                {event.previous_state ?? "—"} → {event.new_state}
                              </span>
                              <Badge variant="outline">{event.actor_type}</Badge>
                              {event.command && <Badge variant="secondary">{event.command}</Badge>}
                            </div>
                            <p className="mt-1 text-[11px] font-semibold text-slate-400">{new Date(event.occurred_at).toLocaleString()}</p>
                            {event.reason && <p className="mt-1 text-[11px] font-semibold text-slate-600">{event.reason}</p>}
                          </div>
                        ))}
                      </div>
                    )}
                  </DrawerCard>
                )}
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-xs font-bold text-slate-500">
              <Loader2 className="mr-2 h-4 w-4 animate-spin text-[#1b59f8]" /> Loading session…
            </div>
          )}
        </DrawerContent>
      </Drawer>
    </div>
  );
}
