"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCheck,
  Download,
  FileCode2,
  Loader2,
  Save,
  Sparkles,
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
  type TasFramework,
  type TasRefinedTestCase,
  type TasScriptAsset,
} from "@/lib/api";
import { EmptyState, JobProgress, SectionCard, StatTile, skippedEntries } from "./shared";

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

  const load = useCallback(async () => {
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
    } catch (error) {
      toast({
        title: "Could not load the script lab",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    void load();
  }, [load]);

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

  const toggle = (id: number) =>
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

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
                          <div className="flex flex-wrap gap-1.5">
                            {generated.map((script) => (
                              <button
                                key={script.id}
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
    </div>
  );
}
