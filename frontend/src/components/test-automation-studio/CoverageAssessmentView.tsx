"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCheck,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import {
  testAutomationStudioApi,
  waitForTasJob,
  type ProjectApplication,
  type TasCoverageAssessment,
  type TasDerivedRequirement,
  type TasDocRole,
  type TasIntakeBatch,
} from "@/lib/api";
import {
  CoverageBadge,
  EmptyState,
  JobProgress,
  OriginBadge,
  SectionCard,
  StatTile,
  StatusBadge,
} from "./shared";

const DOC_ROLE_OPTIONS: Array<{ value: TasDocRole; label: string }> = [
  { value: "brd", label: "BRD" },
  { value: "srd", label: "SRD" },
  { value: "test_cases", label: "Test Cases" },
  { value: "other", label: "Other" },
];

const DOC_ROLE_LABELS: Record<TasDocRole, string> = {
  brd: "BRD",
  srd: "SRD",
  test_cases: "Test Cases",
  other: "Other",
};

function errorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return (error as Error)?.message ?? fallback;
}

export function CoverageAssessmentView({
  projectId,
  applications,
  onChanged,
}: {
  projectId: number;
  applications: ProjectApplication[];
  onChanged: () => void;
}) {
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [batches, setBatches] = useState<TasIntakeBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null);
  const [assessment, setAssessment] = useState<TasCoverageAssessment | null>(null);
  const [requirements, setRequirements] = useState<TasDerivedRequirement[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  const [loading, setLoading] = useState(true);
  const [assessing, setAssessing] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [progress, setProgress] = useState<{ percent: number; message: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deciding, setDeciding] = useState(false);

  const [creating, setCreating] = useState(false);
  const [newBatchName, setNewBatchName] = useState("");
  const [uploadRole, setUploadRole] = useState<TasDocRole>("brd");
  const [applicationId, setApplicationId] = useState<string>("");
  const [applicationUrl, setApplicationUrl] = useState("");
  const [environment, setEnvironment] = useState("qa");
  const [deriveGaps, setDeriveGaps] = useState(true);

  const selectedBatch = useMemo(
    () => batches.find((batch) => batch.id === selectedBatchId) ?? null,
    [batches, selectedBatchId],
  );

  const loadBatches = useCallback(
    async (preferredId?: number) => {
      setLoading(true);
      try {
        const response = await testAutomationStudioApi.listBatches(projectId);
        setBatches(response.data);
        setSelectedBatchId((current) => {
          const target = preferredId ?? current;
          if (target && response.data.some((batch) => batch.id === target)) return target;
          return response.data[0]?.id ?? null;
        });
      } catch (error) {
        toast({
          title: "Could not load intake batches",
          description: errorMessage(error, "Please try again."),
          variant: "error",
        });
      } finally {
        setLoading(false);
      }
    },
    [projectId, toast],
  );

  useEffect(() => {
    void loadBatches();
  }, [loadBatches]);

  const loadBatchDetail = useCallback(
    async (batchId: number) => {
      try {
        const [assessmentResponse, requirementsResponse] = await Promise.all([
          testAutomationStudioApi.getAssessment(batchId),
          testAutomationStudioApi.listRequirements(projectId, { batch_id: batchId }),
        ]);
        setAssessment(assessmentResponse.data ?? null);
        setRequirements(requirementsResponse.data);
        setSelectedIds(new Set());
      } catch (error) {
        toast({
          title: "Could not load the assessment",
          description: errorMessage(error, "Please try again."),
          variant: "error",
        });
      }
    },
    [projectId, toast],
  );

  useEffect(() => {
    if (selectedBatchId == null) {
      setAssessment(null);
      setRequirements([]);
      return;
    }
    void loadBatchDetail(selectedBatchId);
  }, [selectedBatchId, loadBatchDetail]);

  useEffect(() => {
    if (!selectedBatch) return;
    setApplicationId(selectedBatch.application_id ? String(selectedBatch.application_id) : "");
    setApplicationUrl(selectedBatch.application_url ?? "");
    setEnvironment(selectedBatch.application_environment || "qa");
  }, [selectedBatch]);

  const handleCreateBatch = async () => {
    const name = newBatchName.trim();
    if (!name) {
      toast({ title: "Give the intake a name", variant: "warning" });
      return;
    }
    setCreating(true);
    try {
      const response = await testAutomationStudioApi.createBatch(projectId, { name });
      setNewBatchName("");
      await loadBatches(response.data.id);
      toast({ title: `Created "${name}"`, variant: "success" });
    } catch (error) {
      toast({
        title: "Could not create the intake",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setCreating(false);
    }
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length || !selectedBatch) return;
    setUploading(true);
    const failures: string[] = [];
    let uploaded = 0;
    try {
      // Uploaded one at a time so a single rejected file (wrong type, too
      // large) does not discard the ones that would have succeeded.
      for (const file of Array.from(files)) {
        try {
          await testAutomationStudioApi.uploadDocument(selectedBatch.id, file, uploadRole);
          uploaded += 1;
        } catch (error) {
          failures.push(`${file.name}: ${errorMessage(error, "upload failed")}`);
        }
      }
      if (uploaded) await loadBatches(selectedBatch.id);
      if (failures.length) {
        toast({
          title: `${failures.length} file(s) could not be uploaded`,
          description: failures.join(" | "),
          variant: "error",
        });
      } else if (uploaded) {
        toast({
          title: `Attached ${uploaded} document(s) as ${DOC_ROLE_LABELS[uploadRole]}`,
          description: "Text extraction runs in the background - assess once it finishes.",
          variant: "success",
        });
      }
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleRoleChange = async (linkId: number, role: TasDocRole) => {
    if (!selectedBatch) return;
    try {
      const response = await testAutomationStudioApi.setDocumentRole(selectedBatch.id, linkId, role);
      setBatches((current) =>
        current.map((batch) => (batch.id === response.data.id ? response.data : batch)),
      );
    } catch (error) {
      toast({
        title: "Could not change the document type",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    }
  };

  const handleDetach = async (linkId: number) => {
    if (!selectedBatch) return;
    try {
      const response = await testAutomationStudioApi.detachDocument(selectedBatch.id, linkId);
      setBatches((current) =>
        current.map((batch) => (batch.id === response.data.id ? response.data : batch)),
      );
    } catch (error) {
      toast({
        title: "Could not remove the document",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    }
  };

  const handleExtractTestCases = async () => {
    if (!selectedBatch) return;
    const batchId = selectedBatch.id;
    setExtracting(true);
    setProgress({ percent: 0, message: "Queueing..." });

    // One LLM pass per test case document, so the same 202-and-poll contract
    // the assessment uses.
    try {
      const { data: job } = await testAutomationStudioApi.extractTestCases(batchId);
      const run = await waitForTasJob(job.agent_run_id, (update) =>
        setProgress({ percent: update.percent, message: update.message }),
      );

      await loadBatches(batchId);
      await loadBatchDetail(batchId);
      onChanged();

      if (run.status !== "completed") {
        toast({
          title: "Test case extraction failed",
          description: run.error_message ?? "The job stopped before finishing.",
          variant: "error",
        });
        return;
      }

      const extracted = Number((run.output_data ?? {}).test_cases ?? 0);
      toast({
        title: `${extracted} test case(s) ready to refine`,
        description: "Open the Test Case Workbench to refine them - they keep their ID and name.",
        variant: extracted ? "success" : "warning",
      });
    } catch (error) {
      await loadBatches(batchId);
      await loadBatchDetail(batchId);
      toast({
        title: "Test case extraction failed",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setExtracting(false);
      setProgress(null);
    }
  };

  const handleAssess = async () => {
    if (!selectedBatch) return;
    const batchId = selectedBatch.id;
    setAssessing(true);
    setProgress({ percent: 0, message: "Queueing..." });

    // The assessment reads every attached document through an LLM and takes
    // minutes. It runs on the worker; this polls the agent run.
    try {
      const { data: job } = await testAutomationStudioApi.assessCoverage(batchId, {
        application_id: applicationId ? Number(applicationId) : null,
        application_url: applicationUrl.trim() || null,
        application_environment: environment || null,
        derive_gap_requirements: deriveGaps,
      });
      const run = await waitForTasJob(job.agent_run_id, (update) =>
        setProgress({ percent: update.percent, message: update.message }),
      );

      await loadBatches(batchId);
      await loadBatchDetail(batchId);
      onChanged();

      if (run.status !== "completed") {
        toast({
          title: "Coverage assessment failed",
          description: run.error_message ?? "The job stopped before finishing.",
          variant: "error",
        });
        return;
      }

      const output = (run.output_data ?? {}) as {
        coverage_percent?: number;
        derived?: number;
      };
      toast({
        title: `Coverage assessed - ${output.coverage_percent ?? 0}% covered`,
        description: `${output.derived ?? 0} requirement(s) derived to close gaps.`,
        variant: "success",
      });
    } catch (error) {
      await loadBatches(batchId);
      await loadBatchDetail(batchId);
      toast({
        title: "Coverage assessment failed",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setAssessing(false);
      setProgress(null);
    }
  };

  const handleDecide = async (decision: "approve" | "reject") => {
    if (!selectedIds.size) return;
    setDeciding(true);
    try {
      await testAutomationStudioApi.decideRequirements(projectId, {
        requirement_ids: Array.from(selectedIds),
        decision,
      });
      if (selectedBatchId != null) await loadBatchDetail(selectedBatchId);
      onChanged();
      toast({
        title: `${selectedIds.size} requirement(s) ${decision === "approve" ? "approved" : "rejected"}`,
        variant: "success",
      });
    } catch (error) {
      toast({
        title: `Could not ${decision} the selected requirements`,
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    } finally {
      setDeciding(false);
    }
  };

  const toggle = (id: number) =>
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const pendingIds = requirements
    .filter((requirement) => requirement.status === "pending_approval")
    .map((requirement) => requirement.id);
  const allPendingSelected = pendingIds.length > 0 && pendingIds.every((id) => selectedIds.has(id));

  const requirementDocs =
    selectedBatch?.documents.filter((doc) => doc.doc_role === "brd" || doc.doc_role === "srd") ?? [];
  const hasRequirementDoc = requirementDocs.length > 0;
  // Extraction is a background job. Offering Assess before any requirement
  // document has text produces a failure that reads like a bad document.
  const requirementTextReady = requirementDocs.some((doc) => doc.text_available);
  const canAssess = hasRequirementDoc && requirementTextReady;
  const assessBlockedReason = !hasRequirementDoc
    ? "Attach a BRD or SRD document to enable the assessment."
    : !requirementTextReady
      ? "Text extraction is still running. Refresh in a moment."
      : null;

  // Reading the test cases off a sheet is gated only on the sheet. Coverage is
  // measured against requirements and rightly needs a BRD or SRD, but a team
  // whose only input is their existing test cases still has to be able to get
  // them into the studio and refine them.
  const testCaseDocs =
    selectedBatch?.documents.filter((doc) => doc.doc_role === "test_cases") ?? [];
  const canExtractTestCases = testCaseDocs.some((doc) => doc.text_available);
  const extractBlockedReason = testCaseDocs.length === 0
    ? "Attach a test case document to extract test cases."
    : !canExtractTestCases
      ? "Text extraction is still running. Refresh in a moment."
      : null;

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-16 text-sm text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading intake batches...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SectionCard
        title="Document intake"
        description="Upload the BRD, SRD and existing test case documents that describe one scope of work."
        actions={
          <div className="flex items-center gap-2">
            <input
              value={newBatchName}
              onChange={(event) => setNewBatchName(event.target.value)}
              placeholder="New intake name"
              className="h-8 w-52 rounded-lg border border-gray-200 px-2.5 text-xs focus:border-[#B71920] focus:outline-none"
            />
            <Button size="sm" onClick={handleCreateBatch} disabled={creating}>
              {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              Create intake
            </Button>
          </div>
        }
      >
        {batches.length === 0 ? (
          <EmptyState
            title="No intake batches yet"
            description="Create an intake, then upload the BRD, SRD and existing test case documents for the scope you want to automate."
          />
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {batches.map((batch) => (
                <button
                  key={batch.id}
                  type="button"
                  onClick={() => setSelectedBatchId(batch.id)}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                    batch.id === selectedBatchId
                      ? "border-[#B71920] bg-[#B71920]/5 text-[#B71920]"
                      : "border-gray-200 text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  {batch.name}
                  <span className="ml-2 text-[10px] uppercase tracking-wide text-gray-400">
                    {batch.status}
                  </span>
                </button>
              ))}
            </div>

            {selectedBatch && (
              <div className="space-y-4 rounded-lg border border-gray-100 bg-gray-50/50 p-3">
                <div className="flex flex-wrap items-end gap-2">
                  <label className="text-xs">
                    <span className="mb-1 block font-medium text-gray-600">Upload as</span>
                    <select
                      value={uploadRole}
                      onChange={(event) => setUploadRole(event.target.value as TasDocRole)}
                      className="h-8 rounded-lg border border-gray-200 bg-white px-2 text-xs"
                    >
                      {DOC_ROLE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    className="hidden"
                    onChange={(event) => handleUpload(event.target.files)}
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                  >
                    {uploading ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Upload className="h-3.5 w-3.5" />
                    )}
                    Upload documents
                  </Button>
                  <p className="text-[11px] text-gray-500">
                    PDF, DOCX, XLSX, CSV, TXT or MD. Multiple files at once.
                  </p>
                </div>

                {selectedBatch.documents.length === 0 ? (
                  <p className="text-xs text-gray-500">No documents attached yet.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[640px] text-xs">
                      <thead>
                        <tr className="border-b border-gray-200 text-left text-[11px] uppercase tracking-wide text-gray-500">
                          <th className="py-2 pr-3 font-semibold">Document</th>
                          <th className="py-2 pr-3 font-semibold">Type</th>
                          {/* "Text" is the upload-time docx/pdf -> text job.
                              "Requirements found" is the LLM pass that only
                              runs on assessment. Two different steps, so two
                              differently-named columns. */}
                          <th className="py-2 pr-3 font-semibold">Text</th>
                          <th className="py-2 pr-3 font-semibold">Requirements found</th>
                          <th className="py-2 pr-3 font-semibold" />
                        </tr>
                      </thead>
                      <tbody>
                        {selectedBatch.documents.map((doc) => (
                          <tr key={doc.id} className="border-b border-gray-100">
                            <td className="py-2 pr-3">
                              <span className="inline-flex items-center gap-1.5 text-gray-800">
                                <FileText className="h-3.5 w-3.5 text-gray-400" />
                                {doc.original_filename ?? `Document ${doc.document_id}`}
                              </span>
                            </td>
                            <td className="py-2 pr-3">
                              <select
                                value={doc.doc_role}
                                onChange={(event) =>
                                  handleRoleChange(doc.id, event.target.value as TasDocRole)
                                }
                                className="h-7 rounded border border-gray-200 bg-white px-1.5 text-xs"
                              >
                                {DOC_ROLE_OPTIONS.map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td className="py-2 pr-3">
                              {doc.text_available ? (
                                <Badge variant="success">Ready</Badge>
                              ) : doc.document_status === "failed" ? (
                                <Badge variant="destructive">Extraction failed</Badge>
                              ) : (
                                <Badge variant="warning">Extracting...</Badge>
                              )}
                            </td>
                            <td className="py-2 pr-3 text-gray-600">
                              {/* Requirement extraction happens during the
                                  assessment, not on upload. Showing a bare "0"
                                  beforehand reads as "the document yielded
                                  nothing" when nothing has run yet. */}
                              {doc.extraction_status === "pending" ? (
                                <span className="text-gray-400">Not assessed yet</span>
                              ) : doc.doc_role === "test_cases" ? (
                                `${doc.extracted_test_case_count} test case(s)`
                              ) : (
                                `${doc.extracted_requirement_count} requirement(s)`
                              )}
                            </td>
                            <td className="py-2 pr-3 text-right">
                              <button
                                type="button"
                                onClick={() => handleDetach(doc.id)}
                                className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600"
                                aria-label="Remove document"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="grid gap-3 border-t border-gray-200 pt-3 sm:grid-cols-3">
                  <label className="text-xs">
                    <span className="mb-1 block font-medium text-gray-600">Application</span>
                    <select
                      value={applicationId}
                      onChange={(event) => setApplicationId(event.target.value)}
                      className="h-8 w-full rounded-lg border border-gray-200 bg-white px-2 text-xs"
                    >
                      <option value="">Not linked</option>
                      {applications.map((application) => (
                        <option key={application.id} value={String(application.id)}>
                          {application.name}
                        </option>
                      ))}
                    </select>
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
                  <label className="text-xs">
                    <span className="mb-1 block font-medium text-gray-600">Application URL</span>
                    <input
                      value={applicationUrl}
                      onChange={(event) => setApplicationUrl(event.target.value)}
                      className="h-8 w-full rounded-lg border border-gray-200 px-2 text-xs"
                      placeholder="https://app.example.internal"
                    />
                  </label>
                  <p className="text-[11px] text-gray-500 sm:col-span-3">
                    The URL is written into the linked application&apos;s environment settings when that
                    environment has none, so the rest of the platform resolves the same value.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-3 border-t border-gray-200 pt-3">
                  <label className="flex items-center gap-1.5 text-xs text-gray-600">
                    <input
                      type="checkbox"
                      checked={deriveGaps}
                      onChange={(event) => setDeriveGaps(event.target.checked)}
                      className="h-3.5 w-3.5"
                    />
                    Derive additional requirements for coverage gaps
                  </label>
                  <Button
                    variant="ai"
                    size="sm"
                    onClick={handleAssess}
                    disabled={assessing || extracting || !canAssess}
                    title={assessBlockedReason ?? undefined}
                  >
                    {assessing ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5" />
                    )}
                    Assess Coverage for Automation
                  </Button>
                  {/* Available on its own: a batch holding only a test case
                      sheet has nothing to assess coverage against, but its test
                      cases can still be refined for automation. */}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleExtractTestCases}
                    disabled={assessing || extracting || !canExtractTestCases}
                    title={
                      extractBlockedReason ??
                      "Read the uploaded test cases into the workbench, keeping their ID and name."
                    }
                  >
                    {extracting ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <FileText className="h-3.5 w-3.5" />
                    )}
                    Extract Test Cases
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => loadBatches(selectedBatch.id)}
                    title="Refresh extraction status"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    Refresh
                  </Button>
                  {assessBlockedReason && canExtractTestCases && (
                    <span className="inline-flex items-center gap-1 text-[11px] text-gray-600">
                      <FileText className="h-3.5 w-3.5" />
                      No BRD/SRD in this batch — extract the test cases and refine them directly.
                    </span>
                  )}
                  {assessBlockedReason && !canExtractTestCases && (
                    <span className="inline-flex items-center gap-1 text-[11px] text-amber-700">
                      <AlertTriangle className="h-3.5 w-3.5" />
                      {assessBlockedReason}
                    </span>
                  )}
                </div>
                {progress && (
                  <JobProgress percent={progress.percent} message={progress.message} />
                )}
                {selectedBatch.status_error && (
                  <p className="text-[11px] text-red-600">{selectedBatch.status_error}</p>
                )}
              </div>
            )}
          </div>
        )}
      </SectionCard>

      {assessment && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <StatTile label="Coverage" value={`${assessment.coverage_percent}%`} tone="success" />
          <StatTile label="Requirements" value={assessment.total_requirements} />
          <StatTile label="Covered" value={assessment.covered_requirements} />
          <StatTile label="Partial" value={assessment.partially_covered_requirements} tone="warning" />
          <StatTile label="Not covered" value={assessment.uncovered_requirements} tone="warning" />
          <StatTile
            label="Existing TCs read"
            value={assessment.existing_test_case_count}
            hint={`${assessment.derived_requirement_count} derived`}
          />
        </div>
      )}

      <SectionCard
        title="Requirements"
        description="Approve the requirements that should drive automation test case generation on the next screen."
        actions={
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-gray-500">{selectedIds.size} selected</span>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleDecide("reject")}
              disabled={!selectedIds.size || deciding}
            >
              <X className="h-3.5 w-3.5" />
              Reject
            </Button>
            <Button size="sm" onClick={() => handleDecide("approve")} disabled={!selectedIds.size || deciding}>
              {deciding ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <CheckCheck className="h-3.5 w-3.5" />
              )}
              Bulk Approve
            </Button>
          </div>
        }
      >
        {requirements.length === 0 ? (
          <EmptyState
            title="No requirements yet"
            description="Run Assess Coverage for Automation to extract requirements from the attached documents and derive the ones needed to close coverage gaps."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-xs">
              <thead>
                <tr className="border-b border-gray-200 text-left text-[11px] uppercase tracking-wide text-gray-500">
                  <th className="py-2 pr-3">
                    <input
                      type="checkbox"
                      checked={allPendingSelected}
                      onChange={(event) =>
                        setSelectedIds(event.target.checked ? new Set(pendingIds) : new Set())
                      }
                      className="h-3.5 w-3.5"
                      aria-label="Select all pending requirements"
                    />
                  </th>
                  <th className="py-2 pr-3 font-semibold">Key</th>
                  <th className="py-2 pr-3 font-semibold">Requirement</th>
                  <th className="py-2 pr-3 font-semibold">Origin</th>
                  <th className="py-2 pr-3 font-semibold">Coverage</th>
                  <th className="py-2 pr-3 font-semibold">Automation fit</th>
                  <th className="py-2 pr-3 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {requirements.map((requirement) => (
                  <tr key={requirement.id} className="border-b border-gray-100 align-top">
                    <td className="py-2 pr-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(requirement.id)}
                        onChange={() => toggle(requirement.id)}
                        className="mt-1 h-3.5 w-3.5"
                        aria-label={`Select ${requirement.requirement_key}`}
                      />
                    </td>
                    <td className="py-2 pr-3 font-mono text-[11px] text-gray-600">
                      {requirement.requirement_key}
                    </td>
                    <td className="max-w-md py-2 pr-3">
                      <p className="font-medium text-gray-900">{requirement.title}</p>
                      {requirement.summary && (
                        <p className="mt-0.5 line-clamp-2 text-[11px] text-gray-500">
                          {requirement.summary}
                        </p>
                      )}
                      {requirement.gap_reason && (
                        <p className="mt-1 text-[11px] text-amber-700">{requirement.gap_reason}</p>
                      )}
                      {requirement.covering_test_case_refs.length > 0 && (
                        <p className="mt-1 text-[11px] text-gray-500">
                          Covered by: {requirement.covering_test_case_refs.join(", ")}
                        </p>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      <OriginBadge origin={requirement.origin} />
                    </td>
                    <td className="py-2 pr-3">
                      <CoverageBadge state={requirement.coverage_state} />
                    </td>
                    <td className="py-2 pr-3">
                      {requirement.automation_relevance ? (
                        <Badge variant="secondary">{requirement.automation_relevance}</Badge>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      <StatusBadge status={requirement.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
}
