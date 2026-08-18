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
  ConfirmDeleteDialog,
  CoverageBadge,
  EmptyState,
  JobProgress,
  OriginBadge,
  SectionCard,
  StatTile,
  StatusBadge,
  describeDeletion,
  tasButtonTone,
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
  const [refreshing, setRefreshing] = useState(false);
  const [assessing, setAssessing] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [progress, setProgress] = useState<{ percent: number; message: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // The requirement ids the confirmation dialog is about to delete.
  const [pendingDelete, setPendingDelete] = useState<number[] | null>(null);

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

  // A quiet re-fetch for the documents table. Text extraction runs on the
  // worker after upload, so the "Extracting..." badges have to be able to catch
  // up on their own - loadBatches() cannot do it here because it raises the
  // full-view loading spinner and takes the table off screen mid-read.
  const refreshDocuments = useCallback(
    async ({ silent = false }: { silent?: boolean } = {}) => {
      if (!silent) setRefreshing(true);
      try {
        const response = await testAutomationStudioApi.listBatches(projectId);
        setBatches(response.data);
      } catch (error) {
        // A failed background poll is not worth a toast - the next tick retries.
        if (!silent) {
          toast({
            title: "Could not refresh the documents",
            description: errorMessage(error, "Please try again."),
            variant: "error",
          });
        }
      } finally {
        if (!silent) setRefreshing(false);
      }
    },
    [projectId, toast],
  );

  const hasExtractingDocument = useMemo(
    () =>
      (selectedBatch?.documents ?? []).some(
        (doc) => !doc.text_available && doc.document_status !== "failed",
      ),
    [selectedBatch],
  );

  // There is no push channel for the extraction job, so poll while one is
  // outstanding. The interval stops as soon as every row reads Ready or failed.
  useEffect(() => {
    if (!hasExtractingDocument) return;
    const timer = window.setInterval(() => void refreshDocuments({ silent: true }), 5000);
    return () => window.clearInterval(timer);
  }, [hasExtractingDocument, refreshDocuments]);

  useEffect(() => {
    if (!selectedBatch) return;
    setApplicationId(selectedBatch.application_id ? String(selectedBatch.application_id) : "");
    setApplicationUrl(selectedBatch.application_url ?? "");
    setEnvironment(selectedBatch.application_environment || "qa");
  }, [selectedBatch]);

  const selectedApplication = useMemo(
    () => applications.find((application) => String(application.id) === applicationId) ?? null,
    [applications, applicationId],
  );

  // The URL the linked application already holds for this environment. Matched
  // without regard to case, the same way the backend resolves it — an
  // application configured for "SIT" answers to "sit" there, and a screen that
  // disagreed about that would show "not configured" for a URL generation then
  // used anyway.
  const inheritedUrl = useMemo(() => {
    if (!selectedApplication) return null;
    const wanted = environment.trim().toLowerCase();
    if (!wanted) return null;
    const match = Object.entries(selectedApplication.environment_urls ?? {}).find(
      ([name, url]) => name.trim().toLowerCase() === wanted && url?.trim(),
    );
    return match ? match[1].trim() : null;
  }, [selectedApplication, environment]);

  // Environments this application does have a URL for. Named on screen when
  // the typed one has none: the batch defaults to "qa" while applications are
  // routinely configured only for "SIT", so the field sat empty and refined
  // test cases came out with "Application URL not configured" as their first
  // precondition, with nothing on the screen saying a URL existed at all.
  const configuredEnvironments = useMemo(
    () =>
      Object.entries(selectedApplication?.environment_urls ?? {})
        .filter(([, url]) => url?.trim())
        .map(([name]) => name)
        .sort(),
    [selectedApplication],
  );

  // These three look like a form and have no submit button, so they save when
  // they change. Until they did, the only thing that persisted them was Assess
  // Coverage — the one action a batch holding just a test case sheet cannot
  // run — and a value typed here survived only until the next reload.
  //
  // Local state is deliberately left alone on success: it already holds what
  // was typed, and replacing the batch row with the response would rebuild the
  // documents table under the user for no visible gain.
  const persistSettings = useCallback(
    async (overrides?: { applicationId?: string; environment?: string; applicationUrl?: string }) => {
      if (!selectedBatch) return;
      const nextApplicationId = (overrides?.applicationId ?? applicationId).trim();
      const nextEnvironment = (overrides?.environment ?? environment).trim();
      const nextUrl = (overrides?.applicationUrl ?? applicationUrl).trim();
      const applicationIdValue = nextApplicationId ? Number(nextApplicationId) : null;
      const environmentValue = nextEnvironment || selectedBatch.application_environment;

      if (
        applicationIdValue === (selectedBatch.application_id ?? null) &&
        (nextUrl || null) === (selectedBatch.application_url || null) &&
        environmentValue === selectedBatch.application_environment
      ) {
        return;
      }

      try {
        await testAutomationStudioApi.updateBatch(selectedBatch.id, {
          application_id: applicationIdValue,
          application_url: nextUrl || null,
          application_environment: environmentValue,
        });
      } catch (error) {
        toast({
          title: "Could not save the application settings",
          description: errorMessage(error, "Please try again."),
          variant: "error",
        });
      }
    },
    [selectedBatch, applicationId, environment, applicationUrl, toast],
  );

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
      // The application, environment and URL above are a form with no submit
      // button: they were persisted only as a side effect of Assess Coverage,
      // which is exactly the button a batch holding just a test case sheet
      // cannot press. Typing "SIT" and pressing this one discarded it — the
      // reload below put the stored "qa" back — and the refined test cases were
      // then grounded in no URL at all. Saved first, so extraction and
      // everything downstream see what is on screen.
      await testAutomationStudioApi.updateBatch(batchId, {
        application_id: applicationId ? Number(applicationId) : null,
        application_url: applicationUrl.trim() || null,
        application_environment: environment.trim() || selectedBatch.application_environment,
      });

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

  const handleDelete = async () => {
    if (!pendingDelete?.length) return;
    setDeleting(true);
    try {
      const response = await testAutomationStudioApi.deleteRequirements(projectId, pendingDelete);
      setPendingDelete(null);
      setSelectedIds(new Set());
      if (selectedBatchId != null) await loadBatchDetail(selectedBatchId);
      onChanged();
      toast({
        title: `${response.data.deleted.length} requirement(s) deleted`,
        description: describeDeletion(response.data),
        variant: "success",
      });
    } catch (error) {
      toast({
        title: "Could not delete the requirements",
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

  // What deleting the pending selection actually costs, read off the rows.
  const deleteDialog = useMemo(() => {
    if (!pendingDelete?.length) return null;
    const ids = new Set(pendingDelete);
    const rows = requirements.filter((requirement) => ids.has(requirement.id));
    const approved = rows.filter((requirement) => requirement.status === "approved").length;
    const extracted = rows.filter((requirement) => requirement.origin === "extracted").length;
    return {
      target:
        rows.length === 1
          ? `${rows[0].requirement_key} - ${rows[0].title}`
          : `${ids.size} requirement(s)`,
      confirmLabel: `Delete ${ids.size} requirement(s)`,
      consequences: [
        ...(approved ? [`${approved} of them are approved.`] : []),
        ...(extracted
          ? [
              `${extracted} were read out of an attached document - assessing this batch again re-derives them.`,
            ]
          : []),
        "Test cases already generated from them are kept, but lose the link back to the requirement.",
        "The coverage assessment's own figures are not recalculated.",
      ],
    };
  }, [pendingDelete, requirements]);

  // Every row, not only the pending ones. Approve/Reject skip or re-apply
  // harmlessly on a row already in that state, and Delete has to be able to
  // reach an approved requirement — a select-all that quietly excluded them
  // left no way to clear an approved row in bulk.
  const allSelected =
    requirements.length > 0 &&
    requirements.every((requirement) => selectedIds.has(requirement.id));
  const someSelected = selectedIds.size > 0;

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
                    className={tasButtonTone.brandSoft}
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

                <div className="space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                      Attached documents
                    </span>
                    <div className="flex items-center gap-2">
                      {hasExtractingDocument && (
                        <span className="inline-flex items-center gap-1 text-[11px] text-amber-700">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          Text extraction still running
                        </span>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        className={tasButtonTone.neutral}
                        onClick={() => void refreshDocuments()}
                        disabled={refreshing}
                        title="Re-check the extraction status of the attached documents"
                      >
                        {refreshing ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <RefreshCw className="h-3.5 w-3.5" />
                        )}
                        Refresh
                      </Button>
                    </div>
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
                </div>

                <div className="grid gap-3 border-t border-gray-200 pt-3 sm:grid-cols-3">
                  <label className="text-xs">
                    <span className="mb-1 block font-medium text-gray-600">Application</span>
                    <select
                      value={applicationId}
                      onChange={(event) => {
                        setApplicationId(event.target.value);
                        // The new value explicitly: state has not settled yet
                        // when this fires, so reading it back would save the
                        // application that was selected before this change.
                        void persistSettings({ applicationId: event.target.value });
                      }}
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
                      onBlur={() => void persistSettings()}
                      className="h-8 w-full rounded-lg border border-gray-200 px-2 text-xs"
                      placeholder="qa"
                      // Free text still, because a batch may name an
                      // environment the application has not been configured
                      // for yet — but the ones it has are offered, so the
                      // common case is picked rather than guessed at.
                      list="tas-configured-environments"
                    />
                    <datalist id="tas-configured-environments">
                      {configuredEnvironments.map((name) => (
                        <option key={name} value={name} />
                      ))}
                    </datalist>
                  </label>
                  <label className="text-xs">
                    <span className="mb-1 block font-medium text-gray-600">Application URL</span>
                    {/* Read-only while the application supplies one, because
                        that is exactly when generation ignores anything typed
                        here: the application's own setting wins, and an
                        editable box that silently has no effect is worse than
                        no box. It becomes editable — and is written back to the
                        application — only when this environment has none. */}
                    <input
                      value={inheritedUrl ?? applicationUrl}
                      onChange={(event) => setApplicationUrl(event.target.value)}
                      onBlur={() => void persistSettings()}
                      readOnly={Boolean(inheritedUrl)}
                      className={`h-8 w-full rounded-lg border border-gray-200 px-2 text-xs ${
                        inheritedUrl ? "bg-gray-50 text-gray-600" : ""
                      }`}
                      placeholder="https://app.example.internal"
                    />
                  </label>
                  <p className="text-[11px] text-gray-500 sm:col-span-3">
                    {inheritedUrl ? (
                      <>
                        From <span className="font-medium">{selectedApplication?.name}</span> ·{" "}
                        {environment.trim()}. Change it in Project Settings so every module resolves
                        the same value.
                      </>
                    ) : selectedApplication && configuredEnvironments.length > 0 ? (
                      <span className="text-amber-700">
                        <span className="font-medium">{selectedApplication.name}</span> has no URL for
                        &quot;{environment.trim() || "\u2014"}&quot;. It is configured for{" "}
                        {configuredEnvironments.map((name) => `"${name}"`).join(", ")} — use one of
                        those, or enter a URL here to configure this environment.
                      </span>
                    ) : (
                      <>
                        The URL is written into the linked application&apos;s environment settings when
                        that environment has none, so the rest of the platform resolves the same
                        value.
                      </>
                    )}
                  </p>
                </div>

                {/* Discovery and its sign-in credentials deliberately live on
                    the Automation Script Lab, not here: crawling a running
                    application is engineering work, and this screen is about
                    the documents.

                    The URL and environment above are editable in both places
                    on purpose — an engineer correcting a crawl target should
                    not have to come back here. They are one row in one table
                    behind one endpoint, and each view re-fetches its batches
                    on mount, so the two cannot show different values. */}

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
                    className={tasButtonTone.agentSoft}
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
          <StatTile
            label="Coverage"
            value={`${assessment.coverage_percent}%`}
            tone="success"
            // The percentage is a share of acceptance criteria, not of
            // requirements, so the counts behind it are shown: a document that
            // extracts as one requirement would otherwise only ever read 0,
            // 50 or 100 with nothing to explain why.
            hint={
              assessment.total_criteria > 0
                ? `${assessment.covered_criteria} of ${assessment.total_criteria} acceptance criteria`
                : "Scored by requirement - assessed before criterion-level scoring"
            }
          />
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
              className={tasButtonTone.reject}
              onClick={() => handleDecide("reject")}
              disabled={!selectedIds.size || deciding}
            >
              <X className="h-3.5 w-3.5" />
              Reject
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPendingDelete(Array.from(selectedIds))}
              disabled={!selectedIds.size || deleting}
              className={tasButtonTone.danger}
              title="Delete the selected requirements"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </Button>
            <Button
              size="sm"
              className={tasButtonTone.approve}
              onClick={() => handleDecide("approve")}
              disabled={!selectedIds.size || deciding}
            >
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
                      checked={allSelected}
                      ref={(node) => {
                        // Some-but-not-all reads as "clicking this clears the
                        // selection", which an unticked box does not convey.
                        if (node) node.indeterminate = someSelected && !allSelected;
                      }}
                      onChange={(event) =>
                        setSelectedIds(
                          event.target.checked
                            ? new Set(requirements.map((requirement) => requirement.id))
                            : new Set(),
                        )
                      }
                      className="h-3.5 w-3.5"
                      aria-label="Select all requirements"
                    />
                  </th>
                  <th className="py-2 pr-3 font-semibold">Key</th>
                  <th className="py-2 pr-3 font-semibold">Requirement</th>
                  <th className="py-2 pr-3 font-semibold">Origin</th>
                  <th className="py-2 pr-3 font-semibold">Coverage</th>
                  <th className="py-2 pr-3 font-semibold">Automation fit</th>
                  <th className="py-2 pr-3 font-semibold">Status</th>
                  <th className="py-2 pr-3 font-semibold" />
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
                      {requirement.total_criteria > 0 && (
                        <p className="mt-1 text-[11px] text-gray-500">
                          {requirement.covered_criteria} of {requirement.total_criteria} acceptance
                          criteria exercised
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
                    <td className="py-2 pr-3 text-right">
                      <button
                        type="button"
                        onClick={() => setPendingDelete([requirement.id])}
                        className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600"
                        title={`Delete ${requirement.requirement_key}`}
                        aria-label={`Delete ${requirement.requirement_key}`}
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
      </SectionCard>

      {deleteDialog && (
        <ConfirmDeleteDialog
          title="Delete requirements?"
          target={deleteDialog.target}
          consequences={deleteDialog.consequences}
          confirmLabel={deleteDialog.confirmLabel}
          busy={deleting}
          onCancel={() => setPendingDelete(null)}
          onConfirm={handleDelete}
        />
      )}

    </div>
  );
}
