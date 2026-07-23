"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import {
  AlertTriangle, CheckCircle2, ChevronRight, Clock, Loader2, Pause, Play,
  Radar, RefreshCw, Square, StopCircle, XCircle,
} from "lucide-react";
import { applicationsApi, type ProjectApplication } from "@/lib/api";
import {
  useCorrectDiscoveryAction, useCreateDiscoverySession, useCurrentStep, useDiscoveryActions, useDiscoveryActivity,
  useDiscoveryCheckpoints, useDiscoveryReadiness, useDiscoverySession, useDiscoverySessions,
  useEligibleTestCases, useIssueDiscoveryCommand, useRecordFreeAction,
} from "@/lib/queries/discovery";
import { useToast } from "@/components/ui/toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

const MODES = [
  { value: "GUIDED_USER", label: "Guided User Recording" },
  { value: "FREE_USER_ACTION", label: "Free User-Action Recording" },
  { value: "SUPERVISED_AGENT_DRIVEN", label: "Supervised Agent-Driven Recording" },
] as const;

const STATE_BADGE: Record<string, "success" | "warning" | "destructive" | "info" | "secondary" | "outline"> = {
  NOT_STARTED: "outline", INITIALISING: "warning", RECORDING: "success", PAUSE_REQUESTED: "warning",
  PAUSED: "warning", RESUMING: "warning", STOP_REQUESTED: "warning", STOPPED: "info",
  COMPLETED: "success", CANCELLED: "secondary", FAILED: "destructive", EMERGENCY_STOPPED: "destructive",
};

const INSPECTOR_TABS = ["Live State", "Actions", "Checkpoints", "Activity"] as const;
type InspectorTab = (typeof INSPECTOR_TABS)[number];

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

export function DiscoverySessionView({ projectId }: { projectId: number }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { toast } = useToast();

  const applicationId = Number(searchParams.get("application")) || null;
  const environment = searchParams.get("environment") || "";
  const sessionIdParam = Number(searchParams.get("session")) || null;
  const [mode, setMode] = useState<string>("GUIDED_USER");
  const [testCaseId, setTestCaseId] = useState<number | null>(null);
  const [purpose, setPurpose] = useState("");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("Live State");

  const applicationsQuery = useQuery({
    queryKey: ["applications-for-project", projectId],
    queryFn: async () => (await applicationsApi.getForProject(projectId)).data,
    enabled: projectId > 0,
  });
  const applications: ProjectApplication[] = applicationsQuery.data?.applications ?? [];
  const application = applications.find((a) => a.id === applicationId) ?? null;
  const environmentOptions = application ? Object.keys(application.environment_urls || {}) : [];

  const eligibleQuery = useEligibleTestCases(projectId, applicationId, mode);
  const sessionsQuery = useDiscoverySessions(projectId, applicationId);
  const sessionQuery = useDiscoverySession(sessionIdParam);
  const readinessQuery = useDiscoveryReadiness(sessionIdParam);
  const actionsQuery = useDiscoveryActions(sessionIdParam);
  const checkpointsQuery = useDiscoveryCheckpoints(sessionIdParam);
  const activityQuery = useDiscoveryActivity(sessionIdParam);

  const createSession = useCreateDiscoverySession(projectId);
  const issueCommand = useIssueDiscoveryCommand(projectId, sessionIdParam);
  const correctAction = useCorrectDiscoveryAction(projectId, sessionIdParam);
  const recordAction = useRecordFreeAction(projectId, sessionIdParam);

  const session = sessionQuery.data;

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
  const manualControl = Boolean(session?.metadata_?.manual_control);
  const currentStepQuery = useCurrentStep(sessionIdParam, Boolean(isAgentDriven && session?.status === "RECORDING" && !manualControl));

  function setParam(key: string, value: string | null) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) params.set(key, value);
    else params.delete(key);
    router.push(`${pathname}?${params.toString()}`);
  }

  useEffect(() => {
    setTestCaseId(null);
  }, [applicationId, mode]);

  async function handleCreateAndStart() {
    if (!applicationId || !environment) {
      toast({ title: "Select an application and environment first", variant: "error" });
      return;
    }
    if (mode === "FREE_USER_ACTION" && !purpose.trim()) {
      toast({ title: "Free User-Action Recording requires a session purpose", variant: "error" });
      return;
    }
    if (mode !== "FREE_USER_ACTION" && !testCaseId) {
      toast({ title: "Select an eligible test case first", variant: "error" });
      return;
    }
    try {
      const created = await createSession.mutateAsync({
        application_id: applicationId, environment, mode,
        test_case_id: testCaseId, purpose: purpose.trim() || null,
      });
      setParam("session", String(created.id));
      toast({ title: `Session ${created.id} created — evaluate readiness to start` });
    } catch (error) {
      toast({ title: messageFromError(error, "Could not create session"), variant: "error" });
    }
  }

  async function runCommand(command: string, params?: Record<string, unknown>) {
    try {
      await issueCommand.mutateAsync({ command, params });
    } catch (error) {
      toast({ title: messageFromError(error, `Could not ${command}`), variant: "error" });
    }
  }

  async function submitFreeAction() {
    if (freeActionFamily === "navigate" && !freeActionUrl.trim()) {
      toast({ title: "Enter a URL to navigate to", variant: "error" });
      return;
    }
    if ((freeActionFamily === "click" || freeActionFamily === "input") && !freeActionTargetRef.trim()) {
      toast({ title: "Enter a target ref from the latest snapshot below", variant: "error" });
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
      toast({ title: "Action queued — it will appear in the Actions tab shortly" });
      setFreeActionUrl("");
      setFreeActionTargetRef("");
      setFreeActionTargetSemantic("");
      setFreeActionInputText("");
    } catch (error) {
      toast({ title: messageFromError(error, "Could not record action"), variant: "error" });
    }
  }

  async function approveNextAction() {
    try {
      await issueCommand.mutateAsync({ command: "approve_next_action" });
      toast({ title: "Approved — executing the proposed step" });
    } catch (error) {
      toast({ title: messageFromError(error, "Could not approve the next action"), variant: "error" });
    }
  }

  async function skipNextAction() {
    if (!skipReason.trim()) {
      toast({ title: "A reason is required to skip a step", variant: "error" });
      return;
    }
    try {
      await issueCommand.mutateAsync({ command: "skip_action", reason: skipReason.trim() });
      toast({ title: "Step skipped" });
      setSkipReason("");
    } catch (error) {
      toast({ title: messageFromError(error, "Could not skip the next action"), variant: "error" });
    }
  }

  async function modifyNextAction() {
    if (freeActionFamily === "navigate" && !freeActionUrl.trim()) {
      toast({ title: "Enter a URL to navigate to", variant: "error" });
      return;
    }
    if ((freeActionFamily === "click" || freeActionFamily === "input") && !freeActionTargetRef.trim()) {
      toast({ title: "Enter a target ref from the latest snapshot below", variant: "error" });
      return;
    }
    try {
      await issueCommand.mutateAsync({
        command: "modify_next_action",
        params: {
          action_family: freeActionFamily,
          url: freeActionFamily === "navigate" ? freeActionUrl.trim() : undefined,
          target_ref: freeActionTargetRef.trim() || undefined,
          target_semantic: freeActionTargetSemantic.trim() || undefined,
          input_text: freeActionFamily === "input" ? freeActionInputText : undefined,
        },
      });
      toast({ title: "Modified action queued for execution" });
      setFreeActionUrl(""); setFreeActionTargetRef(""); setFreeActionTargetSemantic(""); setFreeActionInputText("");
      setShowModifyForm(false);
    } catch (error) {
      toast({ title: messageFromError(error, "Could not modify the next action"), variant: "error" });
    }
  }

  async function submitRollback() {
    if (!rollbackCheckpointId) {
      toast({ title: "Select a checkpoint to roll back to", variant: "error" });
      return;
    }
    if (!rollbackReason.trim()) {
      toast({ title: "A reason is required to roll back", variant: "error" });
      return;
    }
    try {
      await issueCommand.mutateAsync({
        command: "rollback", reason: rollbackReason.trim(),
        params: { checkpoint_id: Number(rollbackCheckpointId) },
      });
      toast({ title: "Rolled back to checkpoint" });
      setRollbackReason("");
    } catch (error) {
      toast({ title: messageFromError(error, "Could not roll back"), variant: "error" });
    }
  }

  const readiness = readinessQuery.data;
  const canStart = session?.status === "NOT_STARTED";
  const canPause = session?.status === "RECORDING";
  const canResume = session?.status === "PAUSED" || session?.status === "STOPPED";
  const canStop = session?.status === "RECORDING" || session?.status === "PAUSED";
  const canComplete = session?.status === "STOPPED";
  const canCancel = ["NOT_STARTED", "PAUSED", "STOPPED"].includes(session?.status ?? "");
  const canEmergencyStop = !["COMPLETED", "CANCELLED", "FAILED", "EMERGENCY_STOPPED"].includes(session?.status ?? "");

  const testCase = useMemo(
    () => eligibleQuery.data?.find((tc) => tc.test_case_id === session?.test_case_id),
    [eligibleQuery.data, session?.test_case_id],
  );

  const latestAction = actionsQuery.data?.length ? actionsQuery.data[actionsQuery.data.length - 1] : undefined;
  const latestSnapshotExcerpt = latestAction?.post_state?.accessibility_snapshot_excerpt as string | undefined;
  const canRecordFreeAction =
    (session?.mode === "FREE_USER_ACTION" || (isAgentDriven && manualControl)) && session?.status === "RECORDING";

  return (
    <div className="space-y-4">
      {/* Header context selectors */}
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 p-4">
          <div className="flex items-center gap-2">
            <Radar className="h-4 w-4 text-blue-600" />
            <span className="text-xs font-bold uppercase tracking-wide text-slate-500">P1-S4 UI-015 · Live Discovery Session</span>
          </div>
          <div className="ml-auto flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-xs font-bold text-slate-500">
              Application
              <select
                value={applicationId ?? ""}
                disabled={!!session && session.status !== "NOT_STARTED"}
                onChange={(e) => setParam("application", e.target.value || null)}
                className="h-9 w-44 rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-100"
              >
                <option value="">Select application</option>
                {applications.map((a) => <option key={a.id} value={a.id ?? ""}>{a.name}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs font-bold text-slate-500">
              Environment
              <select
                value={environment}
                disabled={!application || (!!session && session.status !== "NOT_STARTED")}
                onChange={(e) => setParam("environment", e.target.value || null)}
                className="h-9 w-36 rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-100"
              >
                <option value="">Select environment</option>
                {environmentOptions.map((env) => <option key={env} value={env}>{env}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs font-bold text-slate-500">
              Mode
              <select
                value={mode}
                disabled={!!session}
                onChange={(e) => setMode(e.target.value)}
                className="h-9 w-56 rounded-lg border border-slate-200 px-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-100"
              >
                {MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </label>
            {session && (
              <div className="flex flex-col gap-1 text-xs font-bold text-slate-500">
                Session
                <Badge variant={STATE_BADGE[session.status] ?? "outline"} className="h-9 justify-center px-3 text-xs">
                  #{session.id} · {session.status}
                </Badge>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {!session && (
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="text-sm font-bold text-slate-700">Session configuration</div>
            {mode !== "FREE_USER_ACTION" ? (
              <div>
                <div className="mb-1 text-xs font-bold text-slate-500">Test Context</div>
                {!applicationId ? (
                  <p className="text-xs font-semibold text-slate-400">Select an application to see eligible test cases.</p>
                ) : eligibleQuery.isLoading ? (
                  <p className="text-xs font-semibold text-slate-400">Loading eligible test cases…</p>
                ) : (
                  <div className="max-h-56 overflow-y-auto rounded-lg border border-slate-100">
                    {(eligibleQuery.data ?? []).map((tc) => (
                      <button
                        key={tc.test_case_id}
                        disabled={!tc.eligible}
                        onClick={() => setTestCaseId(tc.test_case_id)}
                        className={cn(
                          "flex w-full items-center justify-between gap-2 border-b border-slate-50 px-3 py-2 text-left text-xs last:border-0",
                          !tc.eligible && "cursor-not-allowed opacity-50",
                          testCaseId === tc.test_case_id && "bg-blue-50",
                        )}
                      >
                        <span className="font-semibold text-slate-700">{tc.display_id} · {tc.title}</span>
                        {tc.eligible ? (
                          <Badge variant="success" className="text-[10px]">Eligible</Badge>
                        ) : (
                          <span className="text-[10px] font-bold text-red-500" title={tc.blocking_reason ?? ""}>Blocked</span>
                        )}
                      </button>
                    ))}
                    {eligibleQuery.data?.length === 0 && (
                      <p className="p-3 text-xs font-semibold text-slate-400">No test cases in this project.</p>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <label className="flex flex-col gap-1 text-xs font-bold text-slate-500">
                Session purpose (required for Free User-Action Recording)
                <textarea
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value)}
                  className="min-h-[64px] w-full rounded-lg border border-slate-200 p-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-100"
                  placeholder="e.g. Reverse-engineer the promo-code checkout flow"
                />
              </label>
            )}
            <Button onClick={handleCreateAndStart} disabled={createSession.isPending} className="gap-2">
              {createSession.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Create Session
            </Button>
          </CardContent>
        </Card>
      )}

      {session && (
        <>
          {/* Readiness strip */}
          <Card>
            <CardContent className="p-4">
              <div className="mb-2 flex items-center justify-between">
                <div className="text-sm font-bold text-slate-700">Readiness</div>
                <Button size="sm" variant="outline" onClick={() => readinessQuery.refetch()} className="h-7 gap-1 text-[11px]">
                  <RefreshCw className="h-3 w-3" /> Re-evaluate
                </Button>
              </div>
              {readinessQuery.isLoading ? (
                <p className="text-xs font-semibold text-slate-400">Evaluating…</p>
              ) : (
                <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4">
                  {(readiness?.checks ?? []).map((check) => (
                    <div
                      key={check.name}
                      className={cn(
                        "rounded-lg border p-2 text-[11px]",
                        check.passed ? "border-emerald-100 bg-emerald-50" : "border-red-100 bg-red-50",
                      )}
                      title={check.detail}
                    >
                      <div className="flex items-center gap-1 font-bold">
                        {check.passed ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : <AlertTriangle className="h-3.5 w-3.5 text-red-600" />}
                        {check.name.replace(/_/g, " ")}
                      </div>
                      <p className="mt-0.5 truncate text-slate-500">{check.detail}</p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Primary controls */}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={!canStart || !readiness?.ready} onClick={() => runCommand("start")} className="gap-1">
              <Play className="h-3.5 w-3.5" /> Start
            </Button>
            <Button size="sm" variant="outline" disabled={!canPause} onClick={() => runCommand("pause")} className="gap-1">
              <Pause className="h-3.5 w-3.5" /> Pause
            </Button>
            <Button size="sm" variant="outline" disabled={!canResume || !readiness?.ready} onClick={() => runCommand("resume", { recovery_option: "continue" })} className="gap-1">
              <Play className="h-3.5 w-3.5" /> Resume
            </Button>
            <Button size="sm" variant="outline" disabled={session.status !== "RECORDING" && session.status !== "PAUSED"} onClick={() => runCommand("checkpoint")} className="gap-1">
              Save Checkpoint
            </Button>
            <Button size="sm" variant="outline" disabled={!canStop} onClick={() => runCommand("stop")} className="gap-1">
              <Square className="h-3.5 w-3.5" /> Stop
            </Button>
            <Button size="sm" variant="outline" disabled={!canComplete} onClick={() => runCommand("complete")} className="gap-1">
              <CheckCircle2 className="h-3.5 w-3.5" /> Complete
            </Button>
            <Button size="sm" variant="outline" disabled={!canCancel} onClick={() => runCommand("cancel")} className="gap-1">
              <XCircle className="h-3.5 w-3.5" /> Cancel
            </Button>
            <Button size="sm" variant="destructive" disabled={!canEmergencyStop} onClick={() => runCommand("emergency_stop")} className="gap-1">
              <StopCircle className="h-3.5 w-3.5" /> Emergency Stop
            </Button>
            {isAgentDriven && session.status === "RECORDING" && !manualControl && (
              <Button size="sm" variant="outline" onClick={() => runCommand("take_manual_control")} className="gap-1">
                Take Manual Control
              </Button>
            )}
            {isAgentDriven && session.status === "RECORDING" && manualControl && (
              <Button size="sm" variant="outline" onClick={() => runCommand("return_control_to_agent")} className="gap-1">
                Return Control to Agent
              </Button>
            )}
          </div>

          {/* Three-region workspace */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr_360px]">
            <Card>
              <CardContent className="space-y-2 p-3">
                <div className="text-xs font-bold text-slate-500">
                  {session.mode === "FREE_USER_ACTION" ? "Session Purpose" : "Step Plan"}
                </div>
                {session.mode === "FREE_USER_ACTION" ? (
                  <p className="text-xs font-semibold text-slate-600">{session.purpose}</p>
                ) : testCase ? (
                  <p className="text-xs font-semibold text-slate-600">{testCase.display_id} · {testCase.title}</p>
                ) : null}
                <div className="text-[11px] font-bold text-slate-400">
                  Step {session.current_step_index} captured
                </div>

                {isAgentDriven && session.status === "RECORDING" && !manualControl && (
                  <div className="space-y-2 rounded-lg border border-violet-100 bg-violet-50 p-2">
                    <div className="text-[11px] font-bold text-violet-700">Proposed Next Step</div>
                    {currentStepQuery.data?.text ? (
                      <>
                        <p className="text-xs font-semibold text-slate-700">{currentStepQuery.data.text}</p>
                        <div className="flex flex-wrap gap-1">
                          <Button size="sm" onClick={approveNextAction} disabled={issueCommand.isPending} className="h-7 gap-1 text-[10px]">
                            Approve
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => setShowModifyForm((v) => !v)} className="h-7 gap-1 text-[10px]">
                            Modify
                          </Button>
                        </div>

                        {showModifyForm && (
                          <div className="space-y-1 rounded border border-violet-200 bg-white p-1.5">
                            <select
                              value={freeActionFamily}
                              onChange={(e) => setFreeActionFamily(e.target.value)}
                              className="h-7 w-full rounded border border-slate-200 px-1.5 text-[10px] outline-none"
                            >
                              {FREE_ACTION_FAMILIES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
                            </select>
                            {freeActionFamily === "navigate" && (
                              <input value={freeActionUrl} onChange={(e) => setFreeActionUrl(e.target.value)} placeholder="https://…"
                                className="h-7 w-full rounded border border-slate-200 px-1.5 text-[10px] outline-none" />
                            )}
                            {(freeActionFamily === "click" || freeActionFamily === "input") && (
                              <>
                                <input value={freeActionTargetRef} onChange={(e) => setFreeActionTargetRef(e.target.value)} placeholder="Target ref"
                                  className="h-7 w-full rounded border border-slate-200 px-1.5 text-[10px] outline-none" />
                                <input value={freeActionTargetSemantic} onChange={(e) => setFreeActionTargetSemantic(e.target.value)} placeholder="Description"
                                  className="h-7 w-full rounded border border-slate-200 px-1.5 text-[10px] outline-none" />
                              </>
                            )}
                            {freeActionFamily === "input" && (
                              <input value={freeActionInputText} onChange={(e) => setFreeActionInputText(e.target.value)} placeholder="Text to type"
                                className="h-7 w-full rounded border border-slate-200 px-1.5 text-[10px] outline-none" />
                            )}
                            <Button size="sm" onClick={modifyNextAction} disabled={issueCommand.isPending} className="h-7 w-full text-[10px]">
                              Execute Modified Action
                            </Button>
                          </div>
                        )}

                        <input
                          value={skipReason}
                          onChange={(e) => setSkipReason(e.target.value)}
                          placeholder="Reason to skip this step"
                          className="h-7 w-full rounded border border-slate-200 px-1.5 text-[10px] outline-none"
                        />
                        <Button size="sm" variant="outline" onClick={skipNextAction} disabled={issueCommand.isPending} className="h-7 w-full text-[10px]">
                          Skip (reason required)
                        </Button>
                      </>
                    ) : (
                      <p className="text-[11px] font-semibold text-slate-500">No more approved steps — Stop or Complete the session.</p>
                    )}
                  </div>
                )}

                {isAgentDriven && session.status === "PAUSED" && (
                  <div className="space-y-2 rounded-lg border border-amber-100 bg-amber-50 p-2">
                    <div className="text-[11px] font-bold text-amber-700">Roll Back to Checkpoint</div>
                    <select
                      value={rollbackCheckpointId}
                      onChange={(e) => setRollbackCheckpointId(e.target.value)}
                      className="h-7 w-full rounded border border-slate-200 px-1.5 text-[10px] outline-none"
                    >
                      <option value="">Select checkpoint</option>
                      {(checkpointsQuery.data ?? []).map((cp) => (
                        <option key={cp.id} value={cp.id}>#{cp.sequence} · {cp.state_at_checkpoint}</option>
                      ))}
                    </select>
                    <input
                      value={rollbackReason}
                      onChange={(e) => setRollbackReason(e.target.value)}
                      placeholder="Reason (required)"
                      className="h-7 w-full rounded border border-slate-200 px-1.5 text-[10px] outline-none"
                    />
                    <Button size="sm" variant="outline" onClick={submitRollback} disabled={issueCommand.isPending} className="h-7 w-full text-[10px]">
                      Confirm Roll Back
                    </Button>
                  </div>
                )}

                {(session.mode === "FREE_USER_ACTION" || isAgentDriven) && (
                  <div className="space-y-1 border-t border-slate-100 pt-2">
                    <div className="text-[11px] font-bold text-slate-500">Action Timeline</div>
                    {(actionsQuery.data ?? []).map((action) => (
                      <div key={action.id} className="text-[11px]">
                        <span className="font-bold text-slate-600">#{action.sequence}</span>{" "}
                        <span className="text-slate-500">{action.action_family}</span>
                        {action.target_semantic && <span className="text-slate-400"> — {action.target_semantic}</span>}
                      </div>
                    ))}
                    {actionsQuery.data?.length === 0 && (
                      <p className="text-[11px] font-semibold text-slate-400">No actions recorded yet.</p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardContent className="space-y-2 p-3">
                <div className="flex items-center justify-between text-xs font-bold text-slate-500">
                  <span>Live Target View</span>
                  <Badge variant="outline" className="gap-1 text-[10px]">
                    <Clock className="h-3 w-3" /> Latest capture — not live
                  </Badge>
                </div>
                <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 text-center text-xs font-semibold text-slate-400">
                  {actionsQuery.data?.length
                    ? `Last captured evidence at step ${actionsQuery.data[actionsQuery.data.length - 1]?.sequence} — see Actions tab for the full evidence trail.`
                    : "No evidence captured yet."}
                </div>

                {canRecordFreeAction && (
                  <div className="space-y-2 rounded-lg border border-slate-100 p-2">
                    <div className="text-[11px] font-bold text-slate-500">Perform Action</div>
                    <div className="flex flex-wrap gap-2">
                      <select
                        value={freeActionFamily}
                        onChange={(e) => setFreeActionFamily(e.target.value)}
                        className="h-8 rounded-md border border-slate-200 px-2 text-[11px] font-semibold outline-none"
                      >
                        {FREE_ACTION_FAMILIES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
                      </select>
                      {freeActionFamily === "navigate" && (
                        <input
                          value={freeActionUrl}
                          onChange={(e) => setFreeActionUrl(e.target.value)}
                          placeholder="https://…"
                          className="h-8 flex-1 rounded-md border border-slate-200 px-2 text-[11px] outline-none"
                        />
                      )}
                      {(freeActionFamily === "click" || freeActionFamily === "input") && (
                        <>
                          <input
                            value={freeActionTargetRef}
                            onChange={(e) => setFreeActionTargetRef(e.target.value)}
                            placeholder="Target ref (from snapshot below)"
                            className="h-8 w-44 rounded-md border border-slate-200 px-2 text-[11px] outline-none"
                          />
                          <input
                            value={freeActionTargetSemantic}
                            onChange={(e) => setFreeActionTargetSemantic(e.target.value)}
                            placeholder="Description (e.g. Login button)"
                            className="h-8 flex-1 rounded-md border border-slate-200 px-2 text-[11px] outline-none"
                          />
                        </>
                      )}
                      {freeActionFamily === "read" && (
                        <input
                          value={freeActionTargetSemantic}
                          onChange={(e) => setFreeActionTargetSemantic(e.target.value)}
                          placeholder="What did you observe? (optional)"
                          className="h-8 flex-1 rounded-md border border-slate-200 px-2 text-[11px] outline-none"
                        />
                      )}
                      <Button size="sm" onClick={submitFreeAction} disabled={recordAction.isPending} className="h-8 gap-1 text-[11px]">
                        {recordAction.isPending && <Loader2 className="h-3 w-3 animate-spin" />}
                        Record
                      </Button>
                    </div>
                    {freeActionFamily === "input" && (
                      <input
                        value={freeActionInputText}
                        onChange={(e) => setFreeActionInputText(e.target.value)}
                        placeholder="Text to type"
                        className="h-8 w-full rounded-md border border-slate-200 px-2 text-[11px] outline-none"
                      />
                    )}
                    <div className="text-[10px] font-semibold text-slate-400">
                      Naming a field &quot;password&quot;/&quot;OTP&quot;/&quot;card&quot; etc. redacts the typed value before it&apos;s ever stored — the real action still executes.
                    </div>
                  </div>
                )}

                {canRecordFreeAction && (
                  <div>
                    <div className="mb-1 text-[11px] font-bold text-slate-500">Latest accessibility snapshot (read refs to target actions)</div>
                    <pre className="max-h-40 overflow-auto rounded-lg border border-slate-100 bg-slate-50 p-2 text-[10px] leading-relaxed text-slate-600">
                      {latestSnapshotExcerpt || "No snapshot captured yet — perform an action to capture one."}
                    </pre>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-0">
                <div className="flex border-b border-slate-100">
                  {INSPECTOR_TABS.map((tab) => (
                    <button
                      key={tab}
                      onClick={() => setInspectorTab(tab)}
                      className={cn(
                        "flex-1 px-2 py-2 text-[11px] font-bold",
                        inspectorTab === tab ? "border-b-2 border-blue-600 text-blue-600" : "text-slate-400",
                      )}
                    >
                      {tab}
                    </button>
                  ))}
                </div>
                <div className="max-h-96 overflow-y-auto p-3">
                  {inspectorTab === "Live State" && (
                    <div className="space-y-1 text-xs">
                      <div><span className="font-bold text-slate-500">Environment:</span> {session.environment}</div>
                      <div><span className="font-bold text-slate-500">Resume classification:</span> {session.resume_state_classification ?? "—"}</div>
                      <div><span className="font-bold text-slate-500">Started:</span> {session.started_at ?? "—"}</div>
                      <div><span className="font-bold text-slate-500">Terminal reason:</span> {session.terminal_reason ?? "—"}</div>
                      <div><span className="font-bold text-slate-500">Failure detail:</span> {session.failure_detail ?? "—"}</div>
                    </div>
                  )}
                  {inspectorTab === "Actions" && (
                    <div className="space-y-2">
                      {(actionsQuery.data ?? []).map((action) => (
                        <div key={action.id} className="rounded-lg border border-slate-100 p-2 text-[11px]">
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-slate-700">#{action.sequence} · {action.action_family}</span>
                            <Badge variant={action.inclusion_state === "included" ? "success" : "secondary"} className="text-[10px]">
                              {action.inclusion_state}
                            </Badge>
                          </div>
                          <p className="mt-1 text-slate-500">{action.target_semantic}</p>
                          <div className="mt-1 flex gap-1">
                            {["included", "excluded"].map((state) => (
                              <Button
                                key={state}
                                size="sm"
                                variant="outline"
                                className="h-6 px-2 text-[10px]"
                                disabled={action.inclusion_state === state}
                                onClick={() => correctAction.mutate({ actionId: action.id, inclusion_state: state })}
                              >
                                Mark {state}
                              </Button>
                            ))}
                          </div>
                          {session.mode === "FREE_USER_ACTION" && (
                            <input
                              defaultValue={action.test_step_ref ?? ""}
                              placeholder="Map to test case (e.g. TC-0042)"
                              onBlur={(e) => {
                                const value = e.target.value.trim();
                                if (value !== (action.test_step_ref ?? "")) {
                                  correctAction.mutate({
                                    actionId: action.id, inclusion_state: action.inclusion_state,
                                    mapped_test_step_ref: value,
                                  });
                                }
                              }}
                              className="mt-1 h-6 w-full rounded border border-slate-200 px-1.5 text-[10px] outline-none"
                            />
                          )}
                        </div>
                      ))}
                      {actionsQuery.data?.length === 0 && <p className="text-xs font-semibold text-slate-400">No actions captured yet.</p>}
                    </div>
                  )}
                  {inspectorTab === "Checkpoints" && (
                    <div className="space-y-2">
                      {(checkpointsQuery.data ?? []).map((cp) => (
                        <div key={cp.id} className="rounded-lg border border-slate-100 p-2 text-[11px]">
                          <div className="font-bold text-slate-700">#{cp.sequence} · {cp.state_at_checkpoint}</div>
                          <div className="text-slate-500">{cp.sanitized_url ?? "—"}</div>
                          <div className="text-slate-400">{cp.resumable ? "Resumable" : "Not resumable"} · {cp.created_at}</div>
                        </div>
                      ))}
                      {checkpointsQuery.data?.length === 0 && <p className="text-xs font-semibold text-slate-400">No checkpoints yet.</p>}
                    </div>
                  )}
                  {inspectorTab === "Activity" && (
                    <div className="space-y-2">
                      {(activityQuery.data ?? []).map((event) => (
                        <div key={event.id} className="rounded-lg border border-slate-100 p-2 text-[11px]">
                          <div className="font-bold text-slate-700">{event.previous_state ?? "—"} → {event.new_state}</div>
                          <div className="text-slate-500">{event.command ?? "—"} · {event.actor_type} · {event.occurred_at}</div>
                          {event.reason && <div className="text-slate-400">{event.reason}</div>}
                        </div>
                      ))}
                      {activityQuery.data?.length === 0 && <p className="text-xs font-semibold text-slate-400">No activity yet.</p>}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {/* Session history */}
      <Card>
        <CardContent className="p-4">
          <div className="mb-2 text-sm font-bold text-slate-700">Session History</div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-slate-400">
                  <th className="pb-2 font-bold">Session</th>
                  <th className="pb-2 font-bold">Mode</th>
                  <th className="pb-2 font-bold">State</th>
                  <th className="pb-2 font-bold">Started</th>
                  <th className="pb-2 font-bold" />
                </tr>
              </thead>
              <tbody>
                {(sessionsQuery.data ?? []).map((s) => (
                  <tr key={s.id} className="border-t border-slate-50">
                    <td className="py-2 font-semibold text-slate-700">#{s.id}</td>
                    <td className="py-2">{s.mode}</td>
                    <td className="py-2"><Badge variant={STATE_BADGE[s.status] ?? "outline"} className="text-[10px]">{s.status}</Badge></td>
                    <td className="py-2">{s.started_at ?? "—"}</td>
                    <td className="py-2">
                      <button
                        onClick={() => setParam("session", String(s.id))}
                        className="flex items-center gap-1 font-bold text-blue-600"
                      >
                        Open <ChevronRight className="h-3 w-3" />
                      </button>
                    </td>
                  </tr>
                ))}
                {sessionsQuery.data?.length === 0 && (
                  <tr><td colSpan={5} className="py-4 text-center text-slate-400">No discovery sessions yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
