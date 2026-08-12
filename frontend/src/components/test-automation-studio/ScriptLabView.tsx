"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCheck,
  Download,
  FileCode2,
  Link2,
  Loader2,
  PlayCircle,
  Radar,
  Save,
  Sparkles,
  Trash2,
  Undo2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import {
  TAS_FRAMEWORKS,
  TAS_FRAMEWORK_LABELS,
  testAutomationStudioApi,
  waitForTasJob,
  type TasAuthMode,
  type TasDiscoveryRun,
  type TasFramework,
  type TasIntakeBatch,
  type TasRefinedTestCase,
  type TasScriptAsset,
} from "@/lib/api";
import { DiscoveryDrawer } from "./DiscoveryDrawer";
import { DryRunDrawer } from "./DryRunDrawer";
import {
  ConfirmDeleteDialog,
  DryRunBadge,
  EmptyState,
  GenerationModeBadge,
  JobProgress,
  SectionCard,
  StatTile,
  describeDeletion,
  skippedEntries,
} from "./shared";

function errorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return (error as Error)?.message ?? fallback;
}

export function ScriptLabView({
  projectId,
  onChanged,
}: {
  projectId: number;
  onChanged: () => void;
}) {
  const { toast } = useToast();

  const [testCases, setTestCases] = useState<TasRefinedTestCase[]>([]);
  const [scripts, setScripts] = useState<TasScriptAsset[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [framework, setFramework] = useState<TasFramework>("playwright");
  const [regenerate, setRegenerate] = useState(false);
  const [openScript, setOpenScript] = useState<TasScriptAsset | null>(null);
  const [draftCode, setDraftCode] = useState("");

  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState<{ percent: number; message: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // The script ids the confirmation dialog is about to delete.
  const [pendingDelete, setPendingDelete] = useState<number[] | null>(null);
  const [dryRunning, setDryRunning] = useState(false);
  // The script whose verification evidence is open in the drawer.
  const [verifying, setVerifying] = useState<TasScriptAsset | null>(null);

  // ── Grounding the lab in the real application ──────────────────────────────
  // Discovery and grounding live here rather than on Screens 1 and 2 because
  // they are engineering activities against a running system, not analysis of
  // documents. Both are optional: a script can still be generated without
  // them, it is simply ungrounded, and the badges say so.
  //
  // Both are scoped to an intake batch, not to the grid's selection. The grid
  // only lists approved, automation-classified test cases, but grounding is
  // most useful BEFORE approval — running it over the whole batch lets an
  // analyst see on Screen 2 that their steps do not match the real
  // application while the wording can still be fixed cheaply.
  const [batches, setBatches] = useState<TasIntakeBatch[]>([]);
  const [batchId, setBatchId] = useState<number | null>(null);
  const [discovery, setDiscovery] = useState<TasDiscoveryRun | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [grounding, setGrounding] = useState(false);
  const [showDiscovery, setShowDiscovery] = useState(false);
  const [showTargetSettings, setShowTargetSettings] = useState(false);

  // The URL and environment are also editable on the intake screen. Both
  // write the same batch columns through the same endpoint, and each view
  // re-fetches its batches on mount, so the two cannot drift — an edit here
  // is visible there the moment the tab is opened, and vice versa.
  const [applicationUrl, setApplicationUrl] = useState("");
  const [environment, setEnvironment] = useState("qa");
  const [authMode, setAuthMode] = useState<TasAuthMode>("none");
  const [loginUrl, setLoginUrl] = useState("");
  const [usernameLabel, setUsernameLabel] = useState("");
  const [passwordLabel, setPasswordLabel] = useState("");
  const [submitLabel, setSubmitLabel] = useState("");
  const [authUsername, setAuthUsername] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [savingAuth, setSavingAuth] = useState(false);

  const batch = useMemo(
    () => batches.find((entry) => entry.id === batchId) ?? null,
    [batches, batchId],
  );

  /** Reload the screen. Returns the fresh scripts so a caller that is holding
   *  one open (the code viewer, the verification drawer) can re-point at the
   *  updated row instead of showing the copy it captured before the run. */
  const load = useCallback(async (): Promise<TasScriptAsset[] | null> => {
    setLoading(true);
    try {
      const [testCaseResponse, scriptResponse] = await Promise.all([
        // Screen 3's input set: approved AND classified for automation. A
        // manual test case has no script to generate.
        testAutomationStudioApi.listTestCases(projectId, {
          status: ["approved"],
          classification: ["automation"],
        }),
        testAutomationStudioApi.listScripts(projectId),
      ]);
      setTestCases(testCaseResponse.data);
      setScripts(scriptResponse.data);
      return scriptResponse.data;
    } catch (error) {
      toast({
        title: "Could not load the script lab",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
      return null;
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const loadBatches = useCallback(async () => {
    try {
      const response = await testAutomationStudioApi.listBatches(projectId);
      setBatches(response.data);
      setBatchId((current) => {
        if (current && response.data.some((entry) => entry.id === current)) return current;
        return response.data[0]?.id ?? null;
      });
    } catch {
      // Discovery is optional, so a batch list that will not load must not
      // take the rest of the lab down with it.
      setBatches([]);
    }
  }, [projectId]);

  useEffect(() => {
    void loadBatches();
  }, [loadBatches]);

  const loadDiscovery = useCallback(async (id: number) => {
    try {
      const response = await testAutomationStudioApi.getDiscovery(id);
      setDiscovery(response.data ?? null);
    } catch {
      setDiscovery(null);
    }
  }, []);

  useEffect(() => {
    if (batchId == null) {
      setDiscovery(null);
      return;
    }
    void loadDiscovery(batchId);
  }, [batchId, loadDiscovery]);

  useEffect(() => {
    if (!batch) return;
    setApplicationUrl(batch.application_url ?? "");
    setEnvironment(batch.application_environment || "qa");
    setAuthMode(batch.auth_mode);
    setLoginUrl(batch.auth_config?.login_url ?? "");
    setUsernameLabel(batch.auth_config?.username_label ?? "");
    setPasswordLabel(batch.auth_config?.password_label ?? "");
    setSubmitLabel(batch.auth_config?.submit_label ?? "");
    // Never pre-filled: the server does not send credentials back, and a
    // masked placeholder would misrepresent what is about to be submitted.
    setAuthUsername("");
    setAuthPassword("");
  }, [batch]);

  const scriptsByTestCase = useMemo(() => {
    const map = new Map<number, TasScriptAsset[]>();
    for (const script of scripts) {
      const list = map.get(script.refined_test_case_id) ?? [];
      list.push(script);
      map.set(script.refined_test_case_id, list);
    }
    return map;
  }, [scripts]);

  const countsByFramework = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const script of scripts) {
      counts[script.framework] = (counts[script.framework] ?? 0) + 1;
    }
    return counts;
  }, [scripts]);

  const handleGenerate = async () => {
    if (!selectedIds.size) return;
    setGenerating(true);
    setProgress({ percent: 0, message: "Queueing..." });

    // The whole selection goes to the worker as one job. Each script is an LLM
    // call, so the work runs for minutes — far longer than any HTTP hop
    // between the browser and the API will stay open. The request returns 202
    // immediately and this polls the agent run for real progress.
    try {
      const { data: job } = await testAutomationStudioApi.generateScripts(projectId, {
        test_case_ids: Array.from(selectedIds),
        framework,
        regenerate,
      });
      const run = await waitForTasJob(job.agent_run_id, (update) =>
        setProgress({ percent: update.percent, message: update.message }),
      );

      await load();
      onChanged();

      if (run.status !== "completed") {
        toast({
          title: "Script generation failed",
          description: run.error_message ?? "The job stopped before finishing.",
          variant: "error",
        });
        return;
      }

      const generated = Number(run.output_data?.generated ?? 0);
      const skipped = skippedEntries(run.output_data);
      toast({
        title: `${generated} ${TAS_FRAMEWORK_LABELS[framework]} script(s) generated`,
        description: skipped.length
          ? skipped
              .map((entry) => `${entry.tc_display_id ?? ""} ${entry.reason ?? ""}`.trim())
              .slice(0, 3)
              .join(" | ")
          : undefined,
        variant: generated ? "success" : "warning",
      });
    } catch (error) {
      // The job may still be running server-side, so reload rather than
      // leaving the grid showing a state the database has already left.
      await load();
      toast({
        title: "Script generation failed",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setGenerating(false);
      setProgress(null);
    }
  };

  /** Persist everything discovery needs to reach the application: the URL,
   *  the environment and the sign-in settings.
   *
   *  All of it lives here, with Discover, rather than only on the intake
   *  screen: an engineer who can start a crawl but cannot correct its target
   *  or supply its credentials cannot actually use the button.
   *
   *  The intake screen still edits the same two fields, and that is fine —
   *  they are one row in one table behind one endpoint. The backend also
   *  mirrors the URL into the linked application's environment_urls exactly
   *  as it does for an intake edit, so saving from either place has the same
   *  effect on the rest of the platform. */
  const handleSaveTarget = async () => {
    if (!batch) return;
    setSavingAuth(true);
    try {
      const response = await testAutomationStudioApi.updateBatch(batch.id, {
        application_url: applicationUrl.trim() || null,
        application_environment: environment.trim() || undefined,
        auth_mode: authMode,
        auth_config: {
          login_url: loginUrl.trim() || null,
          username_label: usernameLabel.trim() || null,
          password_label: passwordLabel.trim() || null,
          submit_label: submitLabel.trim() || null,
        },
        // Sent only when both were typed. Omitting them keeps what is already
        // encrypted, so editing a label does not silently wipe the password.
        ...(authUsername && authPassword
          ? { auth_username: authUsername, auth_password: authPassword }
          : {}),
      });
      setBatches((current) =>
        current.map((entry) => (entry.id === response.data.id ? response.data : entry)),
      );
      setAuthPassword("");
      toast({ title: "Application settings saved", variant: "success" });
    } catch (error) {
      toast({
        title: "Could not save the application settings",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setSavingAuth(false);
    }
  };

  /** Open the batch's application in a real browser and catalogue what is on
   *  the page. Optional, and never automatic: it hits a live environment and
   *  may sign in with stored credentials. */
  const handleDiscover = async () => {
    if (batchId == null) return;
    const id = batchId;
    setDiscovering(true);
    setProgress({ percent: 0, message: "Queueing..." });
    try {
      const { data: job } = await testAutomationStudioApi.discoverApplication(id);
      const run = await waitForTasJob(job.agent_run_id, (update) =>
        setProgress({ percent: update.percent, message: update.message }),
      );
      await loadDiscovery(id);

      if (run.status !== "completed") {
        toast({
          title: "Discovery failed",
          description: run.error_message ?? "The job stopped before finishing.",
          variant: "error",
        });
        return;
      }

      const output = (run.output_data ?? {}) as {
        elements?: number;
        pages?: number;
        auth_status?: string;
      };
      // A crawl that could not sign in still "completes" and still returns a
      // count — all of it from the login page. The toast has to say which
      // happened rather than reporting a number that reads like success.
      const signInFailed = output.auth_status === "failed";
      toast({
        title: signInFailed
          ? "Discovery finished, but sign-in failed"
          : `Discovered ${output.elements ?? 0} element(s) across ${output.pages ?? 0} page(s)`,
        description: signInFailed
          ? "The catalog is most likely the login page. Open the discovery panel to see what was found."
          : "Run Check Grounding next to bind the test case steps to them.",
        variant: signInFailed ? "warning" : "success",
      });
    } catch (error) {
      await loadDiscovery(id);
      toast({
        title: "Discovery failed",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setDiscovering(false);
      setProgress(null);
    }
  };

  /** Match every refined test case in the batch against the discovered
   *  catalog — including ones not yet approved, which is the point.
   *
   *  This grid only shows approved, automation-classified test cases, but
   *  grounding is most useful before approval: the badge on the Test Case
   *  Workbench is how an analyst learns their step names a control the
   *  application does not have, while the wording is still cheap to change.
   *
   *  Synchronous — string matching over stored rows, no LLM, no browser — so
   *  there is no job to poll. */
  const handleGround = async () => {
    if (batchId == null) return;
    setGrounding(true);
    try {
      const response = await testAutomationStudioApi.groundTestCases(projectId, {
        batch_id: batchId,
      });
      await load();
      const updated = response.data.updated ?? [];
      const skipped = response.data.skipped ?? [];
      const fully = updated.filter((row) => row.grounding_status === "grounded").length;
      const partial = updated.filter(
        (row) => row.grounding_status === "partially_grounded",
      ).length;
      toast({
        title: `${updated.length} test case(s) checked in this batch`,
        description: skipped.length
          ? String(skipped[0]?.reason ?? "Some test cases could not be checked.")
          : `${fully} fully grounded, ${partial} partly. The grounding badges on the Test Case Workbench show which steps did not match.`,
        variant: skipped.length && !updated.length ? "warning" : "success",
      });
    } catch (error) {
      toast({
        title: "Grounding check failed",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setGrounding(false);
    }
  };

  /** Execute the selected test cases' current scripts, for real.
   *
   *  Takes script ids, not test case ids: a test case may have a Playwright
   *  and an Appium script, and only one of them can run here. Selecting a test
   *  case row therefore queues every current script it has, and the ones with
   *  no runner come back `blocked` with a reason rather than failing. */
  const handleDryRun = async (scriptIds?: number[]) => {
    const target =
      scriptIds ??
      testCases
        .filter((testCase) => selectedIds.has(testCase.id))
        .flatMap((testCase) => scriptsByTestCase.get(testCase.id) ?? [])
        .map((script) => script.id);

    if (!target.length) {
      toast({
        title: "Nothing to run",
        description: "Select a test case that already has a generated script.",
        variant: "warning",
      });
      return;
    }

    setDryRunning(true);
    setProgress({ percent: 0, message: "Queueing..." });
    try {
      const { data: job } = await testAutomationStudioApi.dryRunScripts(projectId, target);
      const run = await waitForTasJob(job.agent_run_id, (update) =>
        setProgress({ percent: update.percent, message: update.message }),
      );
      const refreshed = await load();
      // Keep the drawer on the same script, now showing the result it was
      // opened to wait for.
      setVerifying((current) =>
        current ? ((refreshed ?? []).find((row) => row.id === current.id) ?? current) : current,
      );

      if (run.status !== "completed") {
        toast({
          title: "Dry run failed",
          description: run.error_message ?? "The job stopped before finishing.",
          variant: "error",
        });
        return;
      }

      const executed = Number(run.output_data?.executed ?? 0);
      const passed = Number(run.output_data?.passed ?? 0);
      const blocked = Array.isArray(run.output_data?.blocked)
        ? (run.output_data?.blocked as unknown[]).length
        : 0;
      toast({
        title: `${passed} of ${executed} script(s) passed`,
        description: blocked
          ? `${blocked} could not run here - open a script's badge for the reason.`
          : "Open a script's dry-run badge to see the per-test evidence.",
        variant: executed && passed === executed ? "success" : "warning",
      });
    } catch (error) {
      await load();
      toast({
        title: "Dry run failed",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setDryRunning(false);
      setProgress(null);
    }
  };

  const handleSave = async () => {
    if (!openScript) return;
    setSaving(true);
    try {
      const response = await testAutomationStudioApi.updateScript(openScript.id, {
        code: draftCode,
      });
      setOpenScript(response.data);
      await load();
      toast({ title: "Script saved", variant: "success" });
    } catch (error) {
      toast({
        title: "Could not save the script",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDecide = async (decision: "approve" | "reopen") => {
    if (!openScript) return;
    try {
      const response = await testAutomationStudioApi.decideScript(openScript.id, { decision });
      setOpenScript(response.data);
      await load();
      onChanged();
    } catch (error) {
      toast({
        title: "Could not update the script",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    }
  };

  const handleDelete = async () => {
    if (!pendingDelete?.length) return;
    setDeleting(true);
    try {
      const response = await testAutomationStudioApi.deleteScripts(projectId, pendingDelete);
      setPendingDelete(null);
      // The open script may be one of the deleted ones, and there is nothing
      // left behind it to show.
      if (openScript && pendingDelete.includes(openScript.id)) setOpenScript(null);
      await load();
      onChanged();
      toast({
        title: `${response.data.deleted.length} script(s) deleted`,
        description: describeDeletion(response.data),
        variant: "success",
      });
    } catch (error) {
      toast({
        title: "Could not delete the scripts",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setDeleting(false);
    }
  };

  const toggle = (id: number) =>
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  /** Every script generated for the currently selected test cases. */
  const selectedScriptIds = useMemo(
    () => scripts.filter((script) => selectedIds.has(script.refined_test_case_id)).map((s) => s.id),
    [scripts, selectedIds],
  );

  const deleteDialog = useMemo(() => {
    if (!pendingDelete?.length) return null;
    const ids = new Set(pendingDelete);
    const rows = scripts.filter((script) => ids.has(script.id));
    const approved = rows.filter((script) => script.status === "approved").length;
    const edited = rows.filter((script) => script.edited_by_user).length;
    return {
      target:
        rows.length === 1
          ? `${rows[0].test_case_display_id} - ${TAS_FRAMEWORK_LABELS[rows[0].framework]} v${rows[0].version}`
          : `${ids.size} script(s)`,
      confirmLabel: `Delete ${ids.size} script(s)`,
      consequences: [
        "Every version of each script goes, not only the current one.",
        ...(approved ? [`${approved} of them are approved.`] : []),
        ...(edited ? [`${edited} were edited by hand - those edits are not recoverable.`] : []),
        "The test cases stay, so the scripts can be generated again.",
      ],
    };
  }, [pendingDelete, scripts]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-16 text-sm text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading the script lab...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Approved automation TCs" value={testCases.length} />
        {TAS_FRAMEWORKS.map((name) => (
          <StatTile
            key={name}
            label={`${TAS_FRAMEWORK_LABELS[name]} scripts`}
            value={countsByFramework[name] ?? 0}
          />
        ))}
      </div>

      {/* Optional, and deliberately first: everything below generates better
          output once the application has been discovered, but nothing here
          blocks generation. An engineer who cannot reach the environment can
          skip this entirely and get ungrounded scripts, clearly badged. */}
      <SectionCard
        title="Target application (optional)"
        description="Discover the running application so generated locators come from real elements instead of the model's guesses. Skip it and scripts are still produced - just ungrounded."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={batchId != null ? String(batchId) : ""}
              onChange={(event) => setBatchId(event.target.value ? Number(event.target.value) : null)}
              className="h-8 min-w-[12rem] rounded-lg border border-gray-200 bg-white px-2 text-xs"
              aria-label="Intake batch"
            >
              {batches.length === 0 && <option value="">No intake batches</option>}
              {batches.map((entry) => (
                <option key={entry.id} value={String(entry.id)}>
                  {entry.name}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              variant="outline"
              onClick={handleDiscover}
              disabled={discovering || !batch?.application_url}
              title={
                batch?.application_url
                  ? "Open the application in a real browser and catalogue its elements"
                  : "This batch has no application URL - open Application settings to set one"
              }
            >
              {discovering ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Radar className="h-3.5 w-3.5" />
              )}
              Discover Application
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleGround}
              disabled={grounding || batchId == null || !discovery}
              title={
                discovery
                  ? "Match every test case in this batch against the discovered elements, approved or not"
                  : "Run Discover Application first - there is nothing to match against yet"
              }
            >
              {grounding ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Link2 className="h-3.5 w-3.5" />
              )}
              Check Grounding
            </Button>
          </div>
        }
      >
        {batches.length === 0 ? (
          <p className="text-xs text-gray-500">
            No intake batches in this project yet. Create one on the Requirement Coverage Assessment
            screen to point the studio at an application.
          </p>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-gray-500">Application URL</span>
              {batch?.application_url ? (
                <code className="rounded bg-gray-50 px-1.5 py-0.5 font-mono text-[11px] text-gray-700">
                  {batch.application_url}
                </code>
              ) : (
                <span className="text-amber-700">
                  Not set - open Application settings below
                </span>
              )}
              {batch?.has_credentials && <Badge variant="success">Credentials stored</Badge>}
              {discovery && (
                <button
                  type="button"
                  onClick={() => setShowDiscovery(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-2 py-1 text-[11px] text-gray-700 hover:bg-gray-50"
                >
                  {discovery.status === "failed" ? (
                    <Badge variant="destructive">Discovery failed</Badge>
                  ) : discovery.auth_status === "failed" ? (
                    <Badge variant="warning">Sign-in failed</Badge>
                  ) : (
                    <Badge variant="success">{discovery.elements_discovered} element(s)</Badge>
                  )}
                  View details
                </button>
              )}
              <button
                type="button"
                onClick={() => setShowTargetSettings((open) => !open)}
                className="text-[11px] font-medium text-gray-600 underline underline-offset-2 hover:text-gray-900"
              >
                {showTargetSettings ? "Hide application settings" : "Application settings"}
              </button>
            </div>

            {/* Collapsed by default: most of the time the engineer wants the
                two buttons, not the form behind them. */}
            {showTargetSettings && (
              <div className="space-y-2.5 rounded-lg border border-gray-200 bg-gray-50/50 p-3">
                <div className="grid gap-2 sm:grid-cols-3">
                  <label className="text-xs sm:col-span-2">
                    <span className="mb-1 block font-medium text-gray-600">Application URL</span>
                    <input
                      value={applicationUrl}
                      onChange={(event) => setApplicationUrl(event.target.value)}
                      className="h-8 w-full rounded-lg border border-gray-200 px-2 text-xs"
                      placeholder="https://app.example.internal"
                    />
                  </label>
                  <label className="text-xs">
                    <span className="mb-1 block font-medium text-gray-600">Environment</span>
                    <input
                      value={environment}
                      onChange={(event) => setEnvironment(event.target.value)}
                      className="h-8 w-full rounded-lg border border-gray-200 px-2 text-xs"
                      placeholder="qa"
                    />
                  </label>
                  <p className="text-[11px] text-gray-500 sm:col-span-3">
                    The same URL the Requirement Coverage Assessment screen holds for this batch -
                    editing it in either place changes the one value. It is written into the linked
                    application&apos;s environment settings when that environment has none, so the
                    rest of the platform resolves the same target.
                  </p>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-200 pt-2.5">
                  <p className="text-[11px] text-gray-600">
                    Credentials are encrypted at rest and never sent back to this screen. They are
                    used only to open the application before crawling it.
                  </p>
                  <select
                    value={authMode}
                    onChange={(event) => setAuthMode(event.target.value as TasAuthMode)}
                    className="h-8 rounded-lg border border-gray-200 bg-white px-2 text-xs"
                    aria-label="Sign-in mode"
                  >
                    <option value="none">No sign-in</option>
                    <option value="form">Sign in with a form</option>
                  </select>
                </div>

                {authMode === "form" && (
                  <div className="grid gap-2 sm:grid-cols-3">
                    <label className="text-xs sm:col-span-3">
                      <span className="mb-1 block font-medium text-gray-600">
                        Login page URL (optional)
                      </span>
                      <input
                        value={loginUrl}
                        onChange={(event) => setLoginUrl(event.target.value)}
                        className="h-8 w-full rounded-lg border border-gray-200 px-2 text-xs"
                        placeholder="Leave blank to sign in on the application URL itself"
                      />
                    </label>
                    <label className="text-xs">
                      <span className="mb-1 block font-medium text-gray-600">Username</span>
                      <input
                        value={authUsername}
                        onChange={(event) => setAuthUsername(event.target.value)}
                        autoComplete="off"
                        className="h-8 w-full rounded-lg border border-gray-200 px-2 text-xs"
                        placeholder={batch?.has_credentials ? "Stored - type to replace" : "Username"}
                      />
                    </label>
                    <label className="text-xs">
                      <span className="mb-1 block font-medium text-gray-600">Password</span>
                      <input
                        type="password"
                        value={authPassword}
                        onChange={(event) => setAuthPassword(event.target.value)}
                        autoComplete="new-password"
                        className="h-8 w-full rounded-lg border border-gray-200 px-2 text-xs"
                        placeholder={batch?.has_credentials ? "Stored - type to replace" : "Password"}
                      />
                    </label>
                    {/* Labels, not selectors: discovery matches these against
                        the live accessibility tree, which is what a person
                        reads off the screen. */}
                    <label className="text-xs">
                      <span className="mb-1 block font-medium text-gray-600">
                        Username field label
                      </span>
                      <input
                        value={usernameLabel}
                        onChange={(event) => setUsernameLabel(event.target.value)}
                        className="h-8 w-full rounded-lg border border-gray-200 px-2 text-xs"
                        placeholder="Auto-detect"
                      />
                    </label>
                    <label className="text-xs">
                      <span className="mb-1 block font-medium text-gray-600">
                        Password field label
                      </span>
                      <input
                        value={passwordLabel}
                        onChange={(event) => setPasswordLabel(event.target.value)}
                        className="h-8 w-full rounded-lg border border-gray-200 px-2 text-xs"
                        placeholder="Auto-detect"
                      />
                    </label>
                    <label className="text-xs">
                      <span className="mb-1 block font-medium text-gray-600">
                        Submit button label
                      </span>
                      <input
                        value={submitLabel}
                        onChange={(event) => setSubmitLabel(event.target.value)}
                        className="h-8 w-full rounded-lg border border-gray-200 px-2 text-xs"
                        placeholder="Auto-detect"
                      />
                    </label>
                    <p className="text-[11px] text-gray-500 sm:col-span-3">
                      Leave the labels blank to auto-detect. Set them when auto-detection picks the
                      wrong field - the discovery panel lists the labels the page really uses.
                    </p>
                  </div>
                )}

                <Button size="sm" variant="outline" onClick={handleSaveTarget} disabled={savingAuth}>
                  {savingAuth ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <CheckCheck className="h-3.5 w-3.5" />
                  )}
                  Save application settings
                </Button>
              </div>
            )}
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Approved automation test cases"
        description="Every approved test case classified for automation lands here. Pick a framework and generate."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={framework}
              onChange={(event) => setFramework(event.target.value as TasFramework)}
              className="h-8 rounded-lg border border-gray-200 bg-white px-2 text-xs"
            >
              {TAS_FRAMEWORKS.map((name) => (
                <option key={name} value={name}>
                  {TAS_FRAMEWORK_LABELS[name]}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1.5 text-[11px] text-gray-600">
              <input
                type="checkbox"
                checked={regenerate}
                onChange={(event) => setRegenerate(event.target.checked)}
                className="h-3.5 w-3.5"
              />
              New version if one exists
            </label>
            <Button
              size="sm"
              variant="ai"
              onClick={handleGenerate}
              disabled={!selectedIds.size || generating}
            >
              {generating ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
              {generating ? "Generating..." : "Generate scripts"}
            </Button>
            {/* The step that turns "should run" into "did run". Each script
                starts a real browser, so it stays an explicit action. */}
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleDryRun()}
              disabled={!selectedScriptIds.length || dryRunning || generating}
              title={
                selectedScriptIds.length
                  ? "Execute the selected test cases' scripts once, against the real application"
                  : "Select a test case that has generated scripts"
              }
            >
              {dryRunning ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <PlayCircle className="h-3.5 w-3.5" />
              )}
              Dry run
              {selectedScriptIds.length ? ` (${selectedScriptIds.length})` : ""}
            </Button>
            <Button size="sm" variant="outline" asChild>
              <a href={testAutomationStudioApi.downloadScriptsUrl(projectId)}>
                <Download className="h-3.5 w-3.5" />
                Download all
              </a>
            </Button>
            <Button size="sm" variant="outline" asChild>
              <a href={testAutomationStudioApi.downloadScriptsUrl(projectId, framework)}>
                <Download className="h-3.5 w-3.5" />
                {TAS_FRAMEWORK_LABELS[framework]} only
              </a>
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPendingDelete(selectedScriptIds)}
              disabled={!selectedScriptIds.length || deleting}
              className="text-red-600 hover:bg-red-50 hover:text-red-700"
              title={
                selectedScriptIds.length
                  ? "Delete every script generated for the selected test cases"
                  : "Select a test case that has generated scripts"
              }
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete scripts
              {selectedScriptIds.length ? ` (${selectedScriptIds.length})` : ""}
            </Button>
          </div>
        }
      >
        {progress && (
          <div className="mb-3">
            <JobProgress percent={progress.percent} message={progress.message} />
          </div>
        )}

        {testCases.length === 0 ? (
          <EmptyState
            title="No approved automation test cases"
            description="Approve test cases classified as Automation on the Automation TC Coverage screen and they will appear here."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-xs">
              <thead>
                <tr className="border-b border-gray-200 text-left text-[11px] uppercase tracking-wide text-gray-500">
                  <th className="py-2 pr-3">
                    <input
                      type="checkbox"
                      checked={
                        testCases.length > 0 && testCases.every((tc) => selectedIds.has(tc.id))
                      }
                      onChange={(event) =>
                        setSelectedIds(
                          event.target.checked ? new Set(testCases.map((tc) => tc.id)) : new Set(),
                        )
                      }
                      className="h-3.5 w-3.5"
                      aria-label="Select all test cases"
                    />
                  </th>
                  <th className="py-2 pr-3 font-semibold">TC ID</th>
                  <th className="py-2 pr-3 font-semibold">Title</th>
                  <th className="py-2 pr-3 font-semibold">Steps</th>
                  <th className="py-2 pr-3 font-semibold">Generated scripts</th>
                </tr>
              </thead>
              <tbody>
                {testCases.map((testCase) => {
                  const generated = scriptsByTestCase.get(testCase.id) ?? [];
                  return (
                    <tr key={testCase.id} className="border-b border-gray-100 align-top">
                      <td className="py-2 pr-3">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(testCase.id)}
                          onChange={() => toggle(testCase.id)}
                          className="mt-1 h-3.5 w-3.5"
                          aria-label={`Select ${testCase.tc_display_id}`}
                        />
                      </td>
                      <td className="py-2 pr-3 font-mono text-[11px] text-gray-700">
                        {testCase.tc_display_id}
                      </td>
                      <td className="max-w-sm py-2 pr-3 font-medium text-gray-900">
                        {testCase.title}
                      </td>
                      <td className="py-2 pr-3 text-gray-600">{testCase.steps.length}</td>
                      <td className="py-2 pr-3">
                        {generated.length === 0 ? (
                          <span className="text-gray-400">None yet</span>
                        ) : (
                          <div className="space-y-1.5">
                            {generated.map((script) => (
                              <div key={script.id} className="flex flex-wrap items-center gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => {
                                    setOpenScript(script);
                                    setDraftCode(script.code);
                                  }}
                                  className="inline-flex items-center gap-1 rounded-full border border-gray-200 px-2 py-0.5 text-[11px] font-medium text-gray-700 hover:border-[#B71920] hover:text-[#B71920]"
                                >
                                  <FileCode2 className="h-3 w-3" />
                                  {TAS_FRAMEWORK_LABELS[script.framework]}
                                  <span className="text-gray-400">v{script.version}</span>
                                </button>
                                <GenerationModeBadge mode={script.generation_mode} />
                                {/* The badge is the button: it says whether
                                    the script ran, and one click says what
                                    happened when it did. */}
                                <button
                                  type="button"
                                  onClick={() => setVerifying(script)}
                                  className="rounded focus:outline-none focus:ring-2 focus:ring-gray-300"
                                  title="Grounding, static gate and dry-run evidence"
                                >
                                  <DryRunBadge status={script.dry_run_status} />
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {openScript && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-6">
          <div className="w-full max-w-5xl rounded-xl bg-white shadow-xl">
            <header className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 px-5 py-3">
              <div className="min-w-0">
                <h3 className="truncate text-sm font-semibold text-gray-900">
                  {openScript.test_case_display_id} - {TAS_FRAMEWORK_LABELS[openScript.framework]}
                </h3>
                <p className="truncate text-[11px] text-gray-500">
                  {openScript.script_key} - v{openScript.version} - {openScript.language}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={openScript.status === "approved" ? "success" : "secondary"}>
                  {openScript.status}
                </Badge>
                <Button size="sm" variant="outline" asChild>
                  <a href={testAutomationStudioApi.downloadScriptUrl(openScript.id)}>
                    <Download className="h-3.5 w-3.5" />
                    Download
                  </a>
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setPendingDelete([openScript.id])}
                  className="text-red-600 hover:bg-red-50 hover:text-red-700"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </Button>
                {openScript.status === "approved" ? (
                  <Button size="sm" variant="outline" onClick={() => handleDecide("reopen")}>
                    <Undo2 className="h-3.5 w-3.5" />
                    Reopen
                  </Button>
                ) : (
                  <>
                    <Button size="sm" variant="outline" onClick={handleSave} disabled={saving}>
                      {saving ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Save className="h-3.5 w-3.5" />
                      )}
                      Save
                    </Button>
                    <Button size="sm" onClick={() => handleDecide("approve")}>
                      <CheckCheck className="h-3.5 w-3.5" />
                      Approve
                    </Button>
                  </>
                )}
                <button
                  type="button"
                  onClick={() => setOpenScript(null)}
                  className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
                  aria-label="Close"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </header>

            <div className="max-h-[70vh] space-y-3 overflow-y-auto px-5 py-4">
              {openScript.setup_notes.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-[11px] text-amber-900">
                  <p className="mb-1 font-semibold">Setup required before this will run</p>
                  <ul className="list-disc space-y-0.5 pl-4">
                    {openScript.setup_notes.map((note, index) => (
                      <li key={index}>{note}</li>
                    ))}
                  </ul>
                </div>
              )}
              {openScript.execution_command && (
                <p className="rounded-lg bg-gray-900 px-3 py-2 font-mono text-[11px] text-gray-100">
                  {openScript.execution_command}
                </p>
              )}
              <textarea
                value={draftCode}
                onChange={(event) => setDraftCode(event.target.value)}
                disabled={openScript.status === "approved"}
                spellCheck={false}
                rows={26}
                className="w-full rounded-lg border border-gray-200 bg-gray-50 p-3 font-mono text-[11px] leading-relaxed text-gray-800 disabled:opacity-70"
              />
              {Object.keys(openScript.files ?? {}).length > 0 && (
                <div>
                  <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                    Additional files (included in the download)
                  </p>
                  <ul className="space-y-0.5">
                    {Object.keys(openScript.files).map((path) => (
                      <li key={path} className="font-mono text-[11px] text-gray-600">
                        {path}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {deleteDialog && (
        <ConfirmDeleteDialog
          title="Delete generated scripts?"
          target={deleteDialog.target}
          consequences={deleteDialog.consequences}
          confirmLabel={deleteDialog.confirmLabel}
          busy={deleting}
          onCancel={() => setPendingDelete(null)}
          onConfirm={handleDelete}
        />
      )}

      {verifying && (
        <DryRunDrawer
          script={verifying}
          onClose={() => setVerifying(null)}
          onRerun={() => handleDryRun([verifying.id])}
          rerunning={dryRunning}
        />
      )}

      {showDiscovery && discovery && batchId != null && (
        <DiscoveryDrawer
          batchId={batchId}
          run={discovery}
          onClose={() => setShowDiscovery(false)}
        />
      )}
    </div>
  );
}
