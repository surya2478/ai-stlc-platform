"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCheck,
  Database,
  Download,
  Loader2,
  Pencil,
  Sparkles,
  Trash2,
  Undo2,
  Wand2,
  X,
} from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import {
  testAutomationStudioApi,
  waitForTasJob,
  type ProjectApplication,
  type TasClassification,
  type TasDerivedRequirement,
  type TasRefinedStep,
  type TasRefinedTestCase,
  type TasSourceTestCase,
} from "@/lib/api";
import { GroundingDrawer } from "./GroundingDrawer";
import {
  ClassificationBadge,
  GroundingBadge,
  ConfirmDeleteDialog,
  EmptyState,
  JobProgress,
  OriginBadge,
  SectionCard,
  StatTile,
  StatusBadge,
  TestDataBadge,
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

export function TestCaseWorkbenchView({
  projectId,
  applications,
  onChanged,
}: {
  projectId: number;
  applications: ProjectApplication[];
  onChanged: () => void;
}) {
  const { toast } = useToast();

  const [requirements, setRequirements] = useState<TasDerivedRequirement[]>([]);
  const [sourceTestCases, setSourceTestCases] = useState<TasSourceTestCase[]>([]);
  const [testCases, setTestCases] = useState<TasRefinedTestCase[]>([]);
  const [selectedSourceIds, setSelectedSourceIds] = useState<Set<number>>(new Set());
  const [selectedRequirementIds, setSelectedRequirementIds] = useState<Set<number>>(new Set());
  const [selectedTestCaseIds, setSelectedTestCaseIds] = useState<Set<number>>(new Set());
  const [editing, setEditing] = useState<TasRefinedTestCase | null>(null);
  // What the confirmation dialog is about to delete. Held as ids rather than
  // rows so a reload between opening the dialog and confirming cannot leave it
  // acting on a stale copy.
  const [pendingDelete, setPendingDelete] = useState<
    { kind: "refined" | "source"; ids: number[] } | null
  >(null);

  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState<{ percent: number; message: string } | null>(null);
  const [classifying, setClassifying] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [saving, setSaving] = useState(false);
  // The test case whose grounding evidence is open in the drawer. Read-only
  // here: the check itself is run from the Automation Script Lab, since
  // crawling and matching against a live application is engineering work.
  // The badge stays on this screen because an author who can see that their
  // step names a control the application does not have can fix the wording,
  // which is exactly this screen's job.
  const [groundingDetail, setGroundingDetail] = useState<TasRefinedTestCase | null>(null);

  const [applicationId, setApplicationId] = useState<string>("");
  const [regenerate, setRegenerate] = useState(false);
  const [classificationFilter, setClassificationFilter] = useState<"all" | TasClassification>("all");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [requirementsResponse, sourcesResponse, testCasesResponse] = await Promise.all([
        testAutomationStudioApi.listRequirements(projectId, { status: ["approved"] }),
        testAutomationStudioApi.listSourceTestCases(projectId),
        testAutomationStudioApi.listTestCases(projectId),
      ]);
      setRequirements(requirementsResponse.data);
      setSourceTestCases(sourcesResponse.data);
      setTestCases(testCasesResponse.data);
    } catch (error) {
      toast({
        title: "Could not load the workbench",
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

  const visibleTestCases = useMemo(
    () =>
      classificationFilter === "all"
        ? testCases
        : testCases.filter((testCase) => testCase.classification === classificationFilter),
    [testCases, classificationFilter],
  );

  const counts = useMemo(
    () => ({
      total: testCases.length,
      automation: testCases.filter((tc) => tc.classification === "automation").length,
      manual: testCases.filter((tc) => tc.classification === "manual").length,
      approved: testCases.filter((tc) => tc.status === "approved").length,
      needsData: testCases.filter(
        (tc) => tc.test_data_required && tc.test_data_status === "needs_user_action",
      ).length,
    }),
    [testCases],
  );

  const handleGenerate = async () => {
    if (!selectedRequirementIds.size && !selectedSourceIds.size) return;
    setGenerating(true);
    setProgress({ percent: 0, message: "Queueing..." });

    // Refinement runs on the worker: it is one LLM call per batch of test
    // cases plus test data materialisation, which takes minutes. The request
    // returns 202 and this polls the agent run for progress.
    try {
      const { data: job } = await testAutomationStudioApi.generateTestCases(projectId, {
        requirement_ids: Array.from(selectedRequirementIds),
        source_test_case_ids: Array.from(selectedSourceIds),
        application_id: applicationId ? Number(applicationId) : null,
        include_existing_test_cases: true,
        regenerate,
      });
      const run = await waitForTasJob(job.agent_run_id, (update) =>
        setProgress({ percent: update.percent, message: update.message }),
      );

      await load();
      onChanged();

      if (run.status !== "completed") {
        toast({
          title: "Test case generation failed",
          description: run.error_message ?? "The job stopped before finishing.",
          variant: "error",
        });
        return;
      }

      const generated = Number(run.output_data?.generated ?? 0);
      const skipped = skippedEntries(run.output_data);
      toast({
        title: `${generated} test case(s) generated`,
        description: skipped.length
          ? skipped
              .map((entry) => `${entry.requirement_key ?? ""} ${entry.reason ?? ""}`.trim())
              .slice(0, 3)
              .join(" | ")
          : undefined,
        variant: generated ? "success" : "warning",
      });
    } catch (error) {
      await load();
      toast({
        title: "Test case generation failed",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setGenerating(false);
      setProgress(null);
    }
  };

  const handleClassify = async (classification?: TasClassification) => {
    if (!selectedTestCaseIds.size) return;
    setClassifying(true);
    try {
      const response = await testAutomationStudioApi.bulkClassify(projectId, {
        test_case_ids: Array.from(selectedTestCaseIds),
        classification,
      });
      await load();
      onChanged();
      const unresolved = response.data.unresolved ?? [];
      toast({
        title: `${response.data.updated.length} test case(s) classified`,
        description: unresolved.length
          ? unresolved.map((entry) => String(entry.message ?? "")).slice(0, 2).join(" | ")
          : classification
            ? undefined
            : `Applied the project's automation classification policy${
                response.data.policy_version ? ` v${response.data.policy_version}` : ""
              }.`,
        variant: unresolved.length ? "warning" : "success",
      });
    } catch (error) {
      toast({
        title: "Classification failed",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setClassifying(false);
    }
  };

  const handleDecide = async (decision: "approve" | "reject") => {
    if (!selectedTestCaseIds.size) return;
    setDeciding(true);
    try {
      const response = await testAutomationStudioApi.decideTestCases(projectId, {
        test_case_ids: Array.from(selectedTestCaseIds),
        decision,
      });
      await load();
      setSelectedTestCaseIds(new Set());
      onChanged();
      const blocked = response.data.blocked ?? [];
      toast({
        title: `${response.data.updated.length} test case(s) ${
          decision === "approve" ? "approved" : "rejected"
        }`,
        description: blocked.length
          ? `${blocked.length} blocked: ${blocked
              .map((entry) => `${entry.tc_display_id} - ${entry.message}`)
              .slice(0, 3)
              .join(" | ")}`
          : undefined,
        variant: blocked.length ? "warning" : "success",
      });
    } catch (error) {
      toast({
        title: `Could not ${decision} the selected test cases`,
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setDeciding(false);
    }
  };

  const handleDelete = async () => {
    if (!pendingDelete) return;
    const { kind, ids } = pendingDelete;
    setDeleting(true);
    try {
      const response =
        kind === "refined"
          ? await testAutomationStudioApi.deleteTestCases(projectId, ids)
          : await testAutomationStudioApi.deleteSourceTestCases(projectId, ids);
      setPendingDelete(null);
      if (kind === "refined") setSelectedTestCaseIds(new Set());
      else setSelectedSourceIds(new Set());
      await load();
      onChanged();
      toast({
        title: `${response.data.deleted.length} ${
          kind === "refined" ? "refined" : "uploaded"
        } test case(s) deleted`,
        description: describeDeletion(response.data),
        variant: "success",
      });
    } catch (error) {
      toast({
        title: "Could not delete",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setDeleting(false);
    }
  };

  const handleReopen = async (testCase: TasRefinedTestCase) => {
    try {
      await testAutomationStudioApi.reopenTestCase(testCase.id);
      await load();
      onChanged();
    } catch (error) {
      toast({
        title: "Could not reopen the test case",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    }
  };

  const handleSaveEdit = async (draft: TasRefinedTestCase) => {
    setSaving(true);
    try {
      await testAutomationStudioApi.updateTestCase(draft.id, {
        title: draft.title,
        objective: draft.objective,
        preconditions: draft.preconditions,
        steps: draft.steps,
        expected_result: draft.expected_result,
        application_url: draft.application_url,
        priority: draft.priority,
        test_type: draft.test_type,
        test_data_required: draft.test_data_required,
        test_data_status: draft.test_data_status,
        test_data_notes: draft.test_data_notes,
      });
      setEditing(null);
      await load();
      onChanged();
      toast({ title: "Test case updated", variant: "success" });
    } catch (error) {
      toast({
        title: "Could not save the test case",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  const toggleRequirement = (id: number) =>
    setSelectedRequirementIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const toggleSource = (id: number) =>
    setSelectedSourceIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const allSourcesSelected =
    sourceTestCases.length > 0 &&
    sourceTestCases.every((source) => selectedSourceIds.has(source.id));
  const someSourcesSelected = selectedSourceIds.size > 0;
  const allRequirementsSelected =
    requirements.length > 0 &&
    requirements.every((requirement) => selectedRequirementIds.has(requirement.id));
  const someRequirementsSelected = selectedRequirementIds.size > 0;

  const toggleAllSources = (checked: boolean) =>
    setSelectedSourceIds(checked ? new Set(sourceTestCases.map((source) => source.id)) : new Set());

  const toggleAllRequirements = (checked: boolean) =>
    setSelectedRequirementIds(
      checked ? new Set(requirements.map((requirement) => requirement.id)) : new Set(),
    );

  const selectedForGeneration = selectedSourceIds.size + selectedRequirementIds.size;

  // Everything the confirmation needs to say, read off the rows the ids point
  // at. What goes with a delete differs per artefact, so the dialog states it
  // rather than asking a generic "are you sure?".
  const deleteDialog = useMemo(() => {
    if (!pendingDelete) return null;
    const ids = new Set(pendingDelete.ids);

    if (pendingDelete.kind === "refined") {
      const rows = testCases.filter((testCase) => ids.has(testCase.id));
      const approved = rows.filter((testCase) => testCase.status === "approved").length;
      const fromUpload = rows.filter((testCase) => testCase.origin !== "derived").length;
      return {
        title: "Delete refined test cases?",
        target:
          rows.length === 1
            ? `${rows[0].tc_display_id} - ${rows[0].title}`
            : `${ids.size} refined test case(s)`,
        confirmLabel: `Delete ${ids.size} test case(s)`,
        consequences: [
          "Every version is removed, not only the one listed here.",
          "Any Playwright, Katalon or Appium script generated from them goes too.",
          ...(approved ? [`${approved} of them are approved.`] : []),
          ...(fromUpload
            ? ["The uploaded test cases they were refined from stay, so they can be refined again."]
            : []),
          "Test data held in the Test Data module is left in place.",
        ],
      };
    }

    const rows = sourceTestCases.filter((source) => ids.has(source.id));
    const refined = rows.filter((source) => source.refined_test_case_id).length;
    return {
      title: "Delete uploaded test cases?",
      target:
        rows.length === 1
          ? `${rows[0].tc_display_id} - ${rows[0].title}`
          : `${ids.size} uploaded test case(s)`,
      confirmLabel: `Delete ${ids.size} test case(s)`,
      consequences: [
        "These are the rows read off the uploaded document, not the document itself.",
        "Running Extract Test Cases on that document again brings them back.",
        ...(refined
          ? [
              `${refined} have already been refined. The refined test case stays, flagged "Source deleted" — refining that ID again needs "Regenerate existing", or it builds a second one.`,
            ]
          : []),
      ],
    };
  }, [pendingDelete, testCases, sourceTestCases]);

  const toggleTestCase = (id: number) =>
    setSelectedTestCaseIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-16 text-sm text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading test cases...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatTile label="Test cases" value={counts.total} />
        <StatTile label="Automation" value={counts.automation} />
        <StatTile label="Manual" value={counts.manual} />
        <StatTile label="Approved" value={counts.approved} tone="success" />
        <StatTile
          label="Awaiting test data"
          value={counts.needsData}
          tone={counts.needsData ? "warning" : "default"}
          hint={counts.needsData ? "Blocks approval" : undefined}
        />
      </div>

      <SectionCard
        title="What to refine"
        description="Uploaded test cases are refined in place and keep their ID and name — the documents are read for context only. Coverage gaps have no test case to keep, so they produce new ones."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={applicationId}
              onChange={(event) => setApplicationId(event.target.value)}
              className="h-8 rounded-lg border border-gray-200 bg-white px-2 text-xs"
            >
              <option value="">Application from intake</option>
              {applications.map((application) => (
                <option key={application.id} value={String(application.id)}>
                  {application.name}
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
              Regenerate existing
            </label>
            <Button
              size="sm"
              variant="ai"
              onClick={handleGenerate}
              disabled={!selectedForGeneration || generating}
            >
              {generating ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
              {generating
                ? "Generating..."
                : selectedForGeneration
                  ? `Generate ${selectedForGeneration} test case(s)`
                  : "Generate refined test cases"}
            </Button>
          </div>
        }
      >
        {progress && (
          <div className="mb-3">
            <JobProgress percent={progress.percent} message={progress.message} />
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="min-w-0">
            <div className="mb-2 flex items-center justify-between gap-2">
              <label className="flex min-w-0 cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={allSourcesSelected}
                  ref={(node) => {
                    // Some-but-not-all reads as "clicking this clears the
                    // selection", which an unticked box does not convey.
                    if (node) node.indeterminate = someSourcesSelected && !allSourcesSelected;
                  }}
                  onChange={(event) => toggleAllSources(event.target.checked)}
                  disabled={sourceTestCases.length === 0}
                  className="h-3.5 w-3.5"
                  aria-label="Select all uploaded test cases"
                />
                <h4 className="truncate text-xs font-semibold text-gray-900">
                  Uploaded test cases
                  <span className="ml-1.5 font-normal text-gray-500">
                    ({sourceTestCases.length})
                  </span>
                </h4>
              </label>
              {selectedSourceIds.size > 0 ? (
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-[11px] text-gray-500">
                    {selectedSourceIds.size} selected
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      setPendingDelete({ kind: "source", ids: Array.from(selectedSourceIds) })
                    }
                    className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-gray-500 hover:bg-red-50 hover:text-red-600"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Delete
                  </button>
                </div>
              ) : (
                <span className="shrink-0 text-[11px] text-gray-500">ID and name preserved</span>
              )}
            </div>
            {sourceTestCases.length === 0 ? (
              <EmptyState
                title="No uploaded test cases"
                description="Attach a test case document to an intake batch and assess it; the test cases it contains appear here."
              />
            ) : (
              <div className="max-h-64 space-y-1 overflow-y-auto">
                {sourceTestCases.map((source) => (
                  <div
                    key={source.id}
                    className="group flex items-start gap-2 rounded-lg border border-transparent px-2 py-1.5 text-xs hover:border-gray-200 hover:bg-gray-50"
                  >
                    <label className="flex min-w-0 flex-1 cursor-pointer items-start gap-2">
                      <input
                        type="checkbox"
                        checked={selectedSourceIds.has(source.id)}
                        onChange={() => toggleSource(source.id)}
                        className="mt-0.5 h-3.5 w-3.5"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="font-mono text-[11px] text-gray-500">
                          {source.tc_display_id}
                        </span>
                        <span className="ml-2 font-medium text-gray-900">{source.title}</span>
                        {source.covers_requirement_ids.length > 0 && (
                          <span className="ml-2 text-[11px] text-gray-500">
                            covers {source.covers_requirement_ids.length} requirement(s)
                          </span>
                        )}
                      </span>
                    </label>
                    {source.refined_test_case_id ? (
                      <Badge variant="outline">Refined</Badge>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => setPendingDelete({ kind: "source", ids: [source.id] })}
                      className="rounded p-0.5 text-gray-300 hover:bg-red-50 hover:text-red-600 group-hover:text-gray-400"
                      title={`Delete ${source.tc_display_id}`}
                      aria-label={`Delete ${source.tc_display_id}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="min-w-0">
            <div className="mb-2 flex items-center justify-between gap-2">
              <label className="flex min-w-0 cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={allRequirementsSelected}
                  ref={(node) => {
                    if (node) {
                      node.indeterminate = someRequirementsSelected && !allRequirementsSelected;
                    }
                  }}
                  onChange={(event) => toggleAllRequirements(event.target.checked)}
                  disabled={requirements.length === 0}
                  className="h-3.5 w-3.5"
                  aria-label="Select all approved requirements"
                />
                <h4 className="truncate text-xs font-semibold text-gray-900">
                  Approved requirements
                  <span className="ml-1.5 font-normal text-gray-500">({requirements.length})</span>
                </h4>
              </label>
              {selectedRequirementIds.size > 0 ? (
                <span className="shrink-0 text-[11px] text-gray-500">
                  {selectedRequirementIds.size} selected
                </span>
              ) : (
                <span className="shrink-0 text-[11px] text-gray-500">creates new test cases</span>
              )}
            </div>
            {requirements.length === 0 ? (
              <EmptyState
                title="No approved requirements"
                description="Approve requirements on the Requirement Coverage Assessment screen and they will appear here for refinement."
              />
            ) : (
              <div className="max-h-64 space-y-1 overflow-y-auto">
                {requirements.map((requirement) => (
                  <label
                    key={requirement.id}
                    className="flex cursor-pointer items-start gap-2 rounded-lg border border-transparent px-2 py-1.5 text-xs hover:border-gray-200 hover:bg-gray-50"
                  >
                    <input
                      type="checkbox"
                      checked={selectedRequirementIds.has(requirement.id)}
                      onChange={() => toggleRequirement(requirement.id)}
                      className="mt-0.5 h-3.5 w-3.5"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="font-mono text-[11px] text-gray-500">
                        {requirement.requirement_key}
                      </span>
                      <span className="ml-2 font-medium text-gray-900">{requirement.title}</span>
                    </span>
                    <OriginBadge origin={requirement.origin} />
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Refined test cases"
        description="Bulk classify against the project's automation classification policy, edit, approve, and download Manual and Automation separately."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={classificationFilter}
              onChange={(event) =>
                setClassificationFilter(event.target.value as "all" | TasClassification)
              }
              className="h-8 rounded-lg border border-gray-200 bg-white px-2 text-xs"
            >
              <option value="all">All</option>
              <option value="automation">Automation</option>
              <option value="manual">Manual</option>
              <option value="undecided">Unclassified</option>
            </select>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleClassify()}
              disabled={!selectedTestCaseIds.size || classifying}
              title="Classify using the project's published automation classification policy"
            >
              {classifying ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Wand2 className="h-3.5 w-3.5" />
              )}
              Bulk classify by policy
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleClassify("automation")}
              disabled={!selectedTestCaseIds.size || classifying}
            >
              Set Automation
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleClassify("manual")}
              disabled={!selectedTestCaseIds.size || classifying}
            >
              Set Manual
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleDecide("reject")}
              disabled={!selectedTestCaseIds.size || deciding}
            >
              <X className="h-3.5 w-3.5" />
              Reject
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                setPendingDelete({ kind: "refined", ids: Array.from(selectedTestCaseIds) })
              }
              disabled={!selectedTestCaseIds.size || deleting}
              className="text-red-600 hover:bg-red-50 hover:text-red-700"
              title="Delete the selected test cases and any scripts generated from them"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </Button>
            <Button
              size="sm"
              onClick={() => handleDecide("approve")}
              disabled={!selectedTestCaseIds.size || deciding}
            >
              {deciding ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <CheckCheck className="h-3.5 w-3.5" />
              )}
              Approve
            </Button>
          </div>
        }
      >
        <div className="mb-3 flex flex-wrap items-center gap-2 border-b border-gray-100 pb-3">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
            Download
          </span>
          <Button size="sm" variant="outline" asChild>
            <a
              href={testAutomationStudioApi.exportTestCasesUrl(projectId, {
                format: "xlsx",
                classification: "all",
              })}
            >
              <Download className="h-3.5 w-3.5" />
              Workbook (both sheets)
            </a>
          </Button>
          <Button size="sm" variant="outline" asChild>
            <a
              href={testAutomationStudioApi.exportTestCasesUrl(projectId, {
                format: "csv",
                classification: "automation",
              })}
            >
              <Download className="h-3.5 w-3.5" />
              Automation CSV
            </a>
          </Button>
          <Button size="sm" variant="outline" asChild>
            <a
              href={testAutomationStudioApi.exportTestCasesUrl(projectId, {
                format: "csv",
                classification: "manual",
              })}
            >
              <Download className="h-3.5 w-3.5" />
              Manual CSV
            </a>
          </Button>
          <Link
            href={`/test-data?project=${projectId}`}
            className="ml-auto inline-flex items-center gap-1.5 text-[11px] font-medium text-[#B71920] hover:underline"
          >
            <Database className="h-3.5 w-3.5" />
            Manage test data
          </Link>
        </div>

        {visibleTestCases.length === 0 ? (
          <EmptyState
            title="No refined test cases"
            description="Select approved requirements above and generate refined test cases to populate this grid."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1100px] text-xs">
              <thead>
                <tr className="border-b border-gray-200 text-left text-[11px] uppercase tracking-wide text-gray-500">
                  <th className="py-2 pr-3">
                    <input
                      type="checkbox"
                      checked={
                        visibleTestCases.length > 0 &&
                        visibleTestCases.every((tc) => selectedTestCaseIds.has(tc.id))
                      }
                      onChange={(event) =>
                        setSelectedTestCaseIds(
                          event.target.checked
                            ? new Set(visibleTestCases.map((tc) => tc.id))
                            : new Set(),
                        )
                      }
                      className="h-3.5 w-3.5"
                      aria-label="Select all test cases"
                    />
                  </th>
                  <th className="py-2 pr-3 font-semibold">TC ID</th>
                  <th className="py-2 pr-3 font-semibold">Title</th>
                  <th className="py-2 pr-3 font-semibold">Origin</th>
                  <th className="py-2 pr-3 font-semibold">Steps</th>
                  <th className="py-2 pr-3 font-semibold">Classification</th>
                  <th className="py-2 pr-3 font-semibold">Grounding</th>
                  <th className="py-2 pr-3 font-semibold">Test Data Required</th>
                  <th className="py-2 pr-3 font-semibold">Status</th>
                  <th className="py-2 pr-3 font-semibold" />
                </tr>
              </thead>
              <tbody>
                {visibleTestCases.map((testCase) => (
                  <tr key={testCase.id} className="border-b border-gray-100 align-top">
                    <td className="py-2 pr-3">
                      <input
                        type="checkbox"
                        checked={selectedTestCaseIds.has(testCase.id)}
                        onChange={() => toggleTestCase(testCase.id)}
                        className="mt-1 h-3.5 w-3.5"
                        aria-label={`Select ${testCase.tc_display_id}`}
                      />
                    </td>
                    <td className="py-2 pr-3 font-mono text-[11px] text-gray-700">
                      {testCase.tc_display_id}
                      {testCase.version > 1 && (
                        <span className="ml-1 text-gray-400">v{testCase.version}</span>
                      )}
                    </td>
                    <td className="max-w-sm py-2 pr-3">
                      <p className="font-medium text-gray-900">{testCase.title}</p>
                      {testCase.objective && (
                        <p className="mt-0.5 line-clamp-2 text-[11px] text-gray-500">
                          {testCase.objective}
                        </p>
                      )}
                      {testCase.application_url && (
                        <p className="mt-0.5 truncate text-[11px] text-gray-400">
                          {testCase.application_url}
                        </p>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      <OriginBadge origin={testCase.origin} />
                      {testCase.source_missing && (
                        <p
                          className="mt-0.5 max-w-[160px] text-[10px] text-amber-700"
                          title="Generating again would build a second test case alongside this one unless you tick Regenerate existing."
                        >
                          Source deleted
                        </p>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-gray-600">{testCase.steps.length}</td>
                    <td className="py-2 pr-3">
                      <ClassificationBadge classification={testCase.classification} />
                      {testCase.classification_reason && (
                        <p className="mt-0.5 line-clamp-2 max-w-[220px] text-[10px] text-gray-500">
                          {testCase.classification_reason}
                        </p>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      {/* The badge is the button: its whole value is the
                          per-step evidence one click behind it. */}
                      <button
                        type="button"
                        onClick={() => setGroundingDetail(testCase)}
                        className="rounded focus:outline-none focus:ring-2 focus:ring-gray-300"
                        title="See which steps resolved to a real element"
                      >
                        <GroundingBadge status={testCase.grounding_status} />
                      </button>
                      {testCase.grounding_status === "partially_grounded" && (
                        <p className="mt-0.5 text-[10px] text-amber-700">
                          {testCase.grounding_summary?.unresolved?.length ?? 0} step(s) unmatched
                        </p>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      <TestDataBadge
                        required={testCase.test_data_required}
                        status={testCase.test_data_status}
                      />
                      {testCase.test_data_notes && (
                        <p className="mt-0.5 line-clamp-2 max-w-[220px] text-[10px] text-amber-700">
                          {testCase.test_data_notes}
                        </p>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      <StatusBadge status={testCase.status} />
                    </td>
                    <td className="py-2 pr-3">
                      <div className="flex items-center justify-end gap-0.5">
                        {testCase.status === "approved" ? (
                          <button
                            type="button"
                            onClick={() => handleReopen(testCase)}
                            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
                            title="Reopen for editing"
                          >
                            <Undo2 className="h-3.5 w-3.5" />
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setEditing(testCase)}
                            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
                            title="Edit"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() =>
                            setPendingDelete({ kind: "refined", ids: [testCase.id] })
                          }
                          className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600"
                          title={`Delete ${testCase.tc_display_id}`}
                          aria-label={`Delete ${testCase.tc_display_id}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {editing && (
        <TestCaseEditor
          testCase={editing}
          saving={saving}
          onCancel={() => setEditing(null)}
          onSave={handleSaveEdit}
        />
      )}

      {deleteDialog && (
        <ConfirmDeleteDialog
          title={deleteDialog.title}
          target={deleteDialog.target}
          consequences={deleteDialog.consequences}
          confirmLabel={deleteDialog.confirmLabel}
          busy={deleting}
          onCancel={() => setPendingDelete(null)}
          onConfirm={handleDelete}
        />
      )}

      {/* No re-check action: grounding is triggered from the Automation
          Script Lab, so there is exactly one place it happens. */}
      {groundingDetail && (
        <GroundingDrawer
          testCase={groundingDetail}
          onClose={() => setGroundingDetail(null)}
        />
      )}
    </div>
  );
}

function TestCaseEditor({
  testCase,
  saving,
  onCancel,
  onSave,
}: {
  testCase: TasRefinedTestCase;
  saving: boolean;
  onCancel: () => void;
  onSave: (draft: TasRefinedTestCase) => void;
}) {
  const [draft, setDraft] = useState<TasRefinedTestCase>(testCase);

  useEffect(() => setDraft(testCase), [testCase]);

  const updateStep = (index: number, patch: Partial<TasRefinedStep>) =>
    setDraft((current) => ({
      ...current,
      steps: current.steps.map((step, position) =>
        position === index ? { ...step, ...patch } : step,
      ),
    }));

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-6">
      <div className="w-full max-w-3xl rounded-xl bg-white shadow-xl">
        <header className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-900">
              Edit {draft.tc_display_id}
            </h3>
            <p className="text-[11px] text-gray-500">
              {draft.origin === "existing"
                ? "This test case keeps its existing ID and name - only the detail below is editable."
                : "Derived from a requirement gap."}
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto px-5 py-4 text-xs">
          <label className="block">
            <span className="mb-1 block font-medium text-gray-600">Title</span>
            <input
              value={draft.title}
              onChange={(event) => setDraft({ ...draft, title: event.target.value })}
              disabled={draft.origin === "existing"}
              className="h-8 w-full rounded-lg border border-gray-200 px-2 disabled:bg-gray-50 disabled:text-gray-500"
            />
            {draft.origin === "existing" && (
              <span className="mt-1 block text-[11px] text-gray-500">
                Locked: the platform and any linked script still know this test case by this name.
              </span>
            )}
          </label>

          <label className="block">
            <span className="mb-1 block font-medium text-gray-600">Objective</span>
            <textarea
              value={draft.objective ?? ""}
              onChange={(event) => setDraft({ ...draft, objective: event.target.value })}
              rows={2}
              className="w-full rounded-lg border border-gray-200 p-2"
            />
          </label>

          <label className="block">
            <span className="mb-1 block font-medium text-gray-600">
              Preconditions (one per line)
            </span>
            <textarea
              value={(draft.preconditions ?? []).join("\n")}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  preconditions: event.target.value.split("\n").filter((line) => line.trim()),
                })
              }
              rows={3}
              className="w-full rounded-lg border border-gray-200 p-2"
            />
          </label>

          <div>
            <span className="mb-1 block font-medium text-gray-600">Steps</span>
            <div className="space-y-2">
              {draft.steps.map((step, index) => (
                <div key={index} className="rounded-lg border border-gray-200 p-2">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-mono text-[11px] text-gray-500">
                      Step {step.step_number}
                    </span>
                    {step.test_data_ref && (
                      <Badge variant="warning">data: {step.test_data_ref}</Badge>
                    )}
                  </div>
                  <input
                    value={step.action}
                    onChange={(event) => updateStep(index, { action: event.target.value })}
                    placeholder="Action"
                    className="mb-1 h-8 w-full rounded border border-gray-200 px-2"
                  />
                  <div className="grid gap-1 sm:grid-cols-2">
                    <input
                      value={step.target ?? ""}
                      onChange={(event) => updateStep(index, { target: event.target.value })}
                      placeholder="Target element / endpoint"
                      className="h-8 w-full rounded border border-gray-200 px-2"
                    />
                    <input
                      value={step.expected_result ?? ""}
                      onChange={(event) =>
                        updateStep(index, { expected_result: event.target.value })
                      }
                      placeholder="Expected result"
                      className="h-8 w-full rounded border border-gray-200 px-2"
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <label className="block">
            <span className="mb-1 block font-medium text-gray-600">Expected result</span>
            <textarea
              value={draft.expected_result ?? ""}
              onChange={(event) => setDraft({ ...draft, expected_result: event.target.value })}
              rows={2}
              className="w-full rounded-lg border border-gray-200 p-2"
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block font-medium text-gray-600">Application URL</span>
              <input
                value={draft.application_url ?? ""}
                onChange={(event) => setDraft({ ...draft, application_url: event.target.value })}
                className="h-8 w-full rounded-lg border border-gray-200 px-2"
              />
            </label>
            <label className="block">
              <span className="mb-1 block font-medium text-gray-600">Priority</span>
              <select
                value={draft.priority}
                onChange={(event) => setDraft({ ...draft, priority: event.target.value })}
                className="h-8 w-full rounded-lg border border-gray-200 bg-white px-2"
              >
                <option>High</option>
                <option>Medium</option>
                <option>Low</option>
              </select>
            </label>
          </div>

          <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3">
            <p className="mb-2 font-semibold text-amber-900">Test data</p>
            {(draft.test_data_requirements ?? []).length > 0 ? (
              <ul className="mb-2 space-y-1">
                {draft.test_data_requirements.map((requirement) => (
                  <li key={requirement.key} className="text-[11px] text-amber-900">
                    <span className="font-mono">{requirement.key}</span>
                    {requirement.description ? ` - ${requirement.description}` : ""}
                    <Badge className="ml-1.5" variant="secondary">
                      {requirement.resolution}
                    </Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mb-2 text-[11px] text-amber-900">
                The agent identified no test data needs for this test case.
              </p>
            )}
            <label className="flex items-center gap-1.5 text-[11px] text-amber-900">
              <input
                type="checkbox"
                checked={draft.test_data_required}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    test_data_required: event.target.checked,
                    test_data_status: event.target.checked ? "needs_user_action" : "user_provided",
                  })
                }
                className="h-3.5 w-3.5"
              />
              Test Data Required - approval stays blocked while this is ticked
            </label>
            <textarea
              value={draft.test_data_notes ?? ""}
              onChange={(event) => setDraft({ ...draft, test_data_notes: event.target.value })}
              rows={2}
              placeholder="What must be provided, and where"
              className="mt-2 w-full rounded-lg border border-amber-200 bg-white p-2"
            />
          </div>
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-gray-100 px-5 py-3">
          <Button size="sm" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button size="sm" onClick={() => onSave(draft)} disabled={saving}>
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Save changes
          </Button>
        </footer>
      </div>
    </div>
  );
}
