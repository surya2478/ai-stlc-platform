"use client";

// UI-019 Live Recorder — Section 5 entry point.
//
// A recording always belongs to an Automation Test Suite member, so when no
// recording is open this screen asks for exactly two things: which suite and
// which of its test cases. Everything else — application, framework,
// environment, traceability — is inherited and is never asked for here.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { CircleDot, Loader2, Radio, Video } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import {
  automationSuiteApi,
  type AutomationSuiteListItem,
  type AutomationSuiteMember,
  type RecordingMode,
} from "@/lib/api";
import { useCreateRecording, useRecordings } from "@/lib/queries/recorder";
import { cn } from "@/lib/utils";
import {
  Banner,
  EmptyRow,
  MemberStatusBadge,
  Panel,
  SuiteStatusBadge,
  formatDateTime,
  messageFromError,
} from "@/components/automation/suite-shared";
import { RecordingStatusBadge } from "@/components/automation/recorder-shared";

const RECORDING_MODES: { value: RecordingMode; label: string; description: string }[] = [
  {
    value: "GUIDED_TEST_CASE",
    label: "Guided Test Case Recording",
    description:
      "Walk the test case step by step. Actions are mapped to the step you have active, and gaps are reported against the steps.",
  },
  {
    value: "EXPLORATORY",
    label: "Exploratory Recording",
    description:
      "Record without following the step list. Still linked to the suite, test case, application and environment — but every action needs review before it reaches the IR.",
  },
];

export function LiveRecorderLauncher({ projectId }: { projectId: number }) {
  const router = useRouter();
  const { toast } = useToast();

  const [suites, setSuites] = useState<AutomationSuiteListItem[]>([]);
  const [suitesLoading, setSuitesLoading] = useState(true);
  const [suiteId, setSuiteId] = useState<number | null>(null);

  const [members, setMembers] = useState<AutomationSuiteMember[] | null>(null);
  const [membersLoading, setMembersLoading] = useState(false);
  const [membersError, setMembersError] = useState<string | null>(null);
  const [testCaseId, setTestCaseId] = useState<number | null>(null);

  const [mode, setMode] = useState<RecordingMode>("GUIDED_TEST_CASE");
  const [error, setError] = useState<string | null>(null);

  const recordingsQuery = useRecordings(projectId, suiteId);
  const createRecording = useCreateRecording(projectId);

  useEffect(() => {
    let cancelled = false;
    setSuitesLoading(true);
    automationSuiteApi
      .listSuites(projectId, { page_size: 100 })
      .then((response) => {
        if (cancelled) return;
        // Only the current version of each suite chain is recordable — a
        // superseded version is a historical record, and recording into one
        // would produce an IR against scope that has already moved on.
        setSuites((response.data.items ?? []).filter((suite) => suite.is_current));
      })
      .catch((err) => !cancelled && setError(messageFromError(err)))
      .finally(() => !cancelled && setSuitesLoading(false));
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    if (!suiteId) {
      setMembers(null);
      setTestCaseId(null);
      return;
    }
    let cancelled = false;
    setMembersLoading(true);
    setMembersError(null);
    setTestCaseId(null);
    automationSuiteApi
      // 100 is the API's maximum page size; asking for more is rejected
      // outright, which previously surfaced as a false "no members" state.
      .members(suiteId, { inclusion_status: "included", page_size: 100 })
      .then((response) => {
        if (cancelled) return;
        setMembers(response.data.items ?? []);
      })
      .catch((err) => {
        if (cancelled) return;
        setMembers(null);
        setMembersError(messageFromError(err));
      })
      .finally(() => !cancelled && setMembersLoading(false));
    return () => {
      cancelled = true;
    };
  }, [suiteId]);

  const selectedMember = useMemo(
    () => (members ?? []).find((member) => member.test_case_id === testCaseId) ?? null,
    [members, testCaseId],
  );

  const openRecording = useCallback(
    (recordingId: number) => {
      router.push(`/automation?view=recorder&project=${projectId}&recording=${recordingId}`);
    },
    [projectId, router],
  );

  const handleStart = useCallback(async () => {
    if (!suiteId || !testCaseId) return;
    setError(null);
    try {
      const recording = await createRecording.mutateAsync({
        suite_id: suiteId,
        test_case_id: testCaseId,
        recording_mode: mode,
      });
      toast({ title: `Recording v${recording.recording_version} created` });
      openRecording(recording.id);
    } catch (err) {
      setError(messageFromError(err));
    }
  }, [createRecording, mode, openRecording, suiteId, testCaseId, toast]);

  const recordings = recordingsQuery.data ?? [];

  return (
    <div className="space-y-4 pb-8">
      {error && <Banner kind="error" message={error} onDismiss={() => setError(null)} />}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Panel title="1 — Automation Test Suite">
          {suitesLoading ? (
            <p className="p-3 text-[11px] font-semibold text-gray-400">Loading suites…</p>
          ) : suites.length === 0 ? (
            <p className="p-3 text-[11px] font-semibold text-gray-400">
              No Automation Test Suites in this project yet. Create one in the Automation Workspace first —
              a recording always belongs to a suite member.
            </p>
          ) : (
            <div className="max-h-64 space-y-1 overflow-y-auto">
              {suites.map((suite) => (
                <button
                  key={suite.id}
                  type="button"
                  onClick={() => setSuiteId(suite.id)}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left transition-colors",
                    suiteId === suite.id
                      ? "border-[#B71920] bg-app-brand-75/60"
                      : "border-gray-200 bg-white hover:bg-gray-50",
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-bold text-gray-800">{suite.name}</span>
                    <span className="block text-[10px] font-semibold text-gray-500">
                      v{suite.version} · {suite.members_included} included ·{" "}
                      {suite.members_blocked} blocked
                    </span>
                  </span>
                  <SuiteStatusBadge status={suite.status} />
                </button>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="2 — Test Case">
          {!suiteId ? (
            <p className="p-3 text-[11px] font-semibold text-gray-400">
              Select a suite to see its test cases.
            </p>
          ) : membersLoading ? (
            <p className="p-3 text-[11px] font-semibold text-gray-400">Loading members…</p>
          ) : membersError ? (
            // Never render "no members" for a request that failed — an empty
            // suite and an unreachable API are different situations.
            <p className="p-3 text-[11px] font-semibold text-red-600">
              Could not load this suite&apos;s members: {membersError}
            </p>
          ) : (members?.length ?? 0) === 0 ? (
            <p className="p-3 text-[11px] font-semibold text-gray-400">
              This suite has no included members. Add test cases to it in the Automation Workspace.
            </p>
          ) : (
            <div className="max-h-64 space-y-1 overflow-y-auto">
              {(members ?? []).map((member) => (
                <button
                  key={member.id}
                  type="button"
                  onClick={() => setTestCaseId(member.test_case_id)}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left transition-colors",
                    testCaseId === member.test_case_id
                      ? "border-[#B71920] bg-app-brand-75/60"
                      : "border-gray-200 bg-white hover:bg-gray-50",
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-bold text-gray-800">
                      {member.test_case_reference} — {member.title}
                    </span>
                    <span className="block truncate text-[10px] font-semibold text-gray-500">
                      {member.resolved_environment ?? "no environment"} ·{" "}
                      {member.resolved_framework ?? "no framework"}
                      {member.resolved_script_id ? " · has script" : ""}
                    </span>
                  </span>
                  <MemberStatusBadge status={member.member_status} />
                </button>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Panel title="3 — Recording Mode">
        <div className="grid gap-2 md:grid-cols-2">
          {RECORDING_MODES.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setMode(option.value)}
              className={cn(
                "rounded-lg border px-3 py-2.5 text-left transition-colors",
                mode === option.value
                  ? "border-[#B71920] bg-app-brand-75/60"
                  : "border-gray-200 bg-white hover:bg-gray-50",
              )}
            >
              <span className="flex items-center gap-1.5 text-xs font-bold text-gray-800">
                <CircleDot
                  className={cn("h-3 w-3", mode === option.value ? "text-[#B71920]" : "text-gray-300")}
                />
                {option.label}
              </span>
              <span className="mt-1 block text-[10px] font-semibold leading-relaxed text-gray-500">
                {option.description}
              </span>
            </button>
          ))}
        </div>

        {selectedMember && (
          <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50/60 px-3 py-2.5">
            <p className="text-[9px] font-bold uppercase tracking-wide text-gray-400">
              Inherited for this member — read-only
            </p>
            <p className="mt-1 text-[11px] font-semibold text-gray-600">
              Environment {selectedMember.resolved_environment ?? "—"} · Framework{" "}
              {selectedMember.resolved_framework ?? "—"} · Readiness{" "}
              {selectedMember.readiness_checks_passed}/{selectedMember.readiness_checks_total}
            </p>
          </div>
        )}

        <div className="mt-3 flex justify-end">
          <Button
            onClick={handleStart}
            disabled={!suiteId || !testCaseId || createRecording.isPending}
            className="gap-1.5"
          >
            {createRecording.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Video className="h-3.5 w-3.5" />
            )}
            Create Recording
          </Button>
        </div>
      </Panel>

      <Panel
        title={suiteId ? "Recordings in this suite" : "Recordings in this project"}
        action={
          recordingsQuery.isFetching ? (
            <span className="text-[9px] font-bold text-gray-400">Refreshing…</span>
          ) : null
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-200">
                {["Recording", "Test Case", "Mode", "Status", "IR", "Created", ""].map((heading) => (
                  <th
                    key={heading}
                    className="px-2 py-1.5 text-[9px] font-extrabold uppercase tracking-wide text-gray-500"
                  >
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recordings.length === 0 ? (
                <EmptyRow colSpan={7} message="No recordings yet." />
              ) : (
                recordings.map((recording) => (
                  <tr key={recording.id} className="border-b border-gray-100 last:border-0">
                    <td className="px-2 py-2 text-[11px] font-bold text-gray-800">
                      #{recording.id}
                      <span className="ml-1 text-[10px] font-semibold text-gray-400">
                        v{recording.recording_version}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-[11px] font-semibold text-gray-600">
                      {recording.test_case_id ?? "—"}
                    </td>
                    <td className="px-2 py-2 text-[10px] font-semibold text-gray-500">
                      {recording.recording_mode === "EXPLORATORY" ? "Exploratory" : "Guided"}
                    </td>
                    <td className="px-2 py-2">
                      <RecordingStatusBadge status={recording.status} />
                    </td>
                    <td className="px-2 py-2">
                      {recording.ir_status === "DRAFT" ? (
                        <Badge variant="purple" className="text-[9px]">
                          Draft
                        </Badge>
                      ) : (
                        <span className="text-[10px] font-semibold text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-2 py-2 text-[10px] font-semibold text-gray-500">
                      {formatDateTime(recording.created_at)}
                    </td>
                    <td className="px-2 py-2 text-right">
                      <Button size="sm" variant="outline" onClick={() => openRecording(recording.id)}>
                        <Radio className="mr-1 h-3 w-3" />
                        Open
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
