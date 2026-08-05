"use client";

// UI-018 — New Automation Test Suite wizard.
//
// Test case selection comes first because test cases are the primary source of
// a suite's scope. Steps 3 and 4 show what the selection *inherits* and what
// conflicts it creates, all computed by the backend's preview endpoint — the
// user is never asked to re-enter an inherited value.
//
// The idempotency key is minted once per wizard session and kept in state, so a
// double-submit or a slow network cannot create two suites.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Search,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  automationSuiteApi,
  type SelectableTestCase,
  type SuiteInheritancePreview,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Banner,
  Panel,
  SeverityBadge,
  humanizeCode,
  messageFromError,
} from "@/components/automation/suite-shared";

const STEPS = [
  { index: 1, title: "Select Test Cases", subtitle: "Choose test cases to include" },
  { index: 2, title: "Suite Identification", subtitle: "Provide basic suite details" },
  { index: 3, title: "Review Inherited Details", subtitle: "Preview inherited information" },
  { index: 4, title: "Resolve Conflicts and Scope", subtitle: "Review findings before creating" },
  { index: 5, title: "Execution and Schedule", subtitle: "Suite-level orchestration" },
  { index: 6, title: "Review and Create", subtitle: "Confirm and create the suite" },
] as const;

const PAGE_SIZE = 10;

function makeIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `suite-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function SummaryRow({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number | null;
  hint?: string;
}) {
  const missing = value === null;
  return (
    <div className="flex items-start justify-between gap-2 border-b border-gray-50 py-1.5 last:border-0">
      <span className="min-w-0">
        <span className="block text-[10px] font-bold text-gray-600">{label}</span>
        {(hint || missing) && (
          <span className="block text-[9px] font-semibold text-gray-400">{hint}</span>
        )}
      </span>
      <span
        className={cn(
          "shrink-0 text-xs font-extrabold",
          missing ? "text-gray-300" : "text-gray-900",
        )}
      >
        {missing ? "—" : value}
      </span>
    </div>
  );
}

export function NewAutomationSuiteWizard({ projectId }: { projectId: number }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const idempotencyKey = useRef(makeIdempotencyKey());

  const [step, setStep] = useState(1);
  const [selected, setSelected] = useState<Map<number, SelectableTestCase>>(new Map());
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [environment, setEnvironment] = useState("");

  const [candidates, setCandidates] = useState<SelectableTestCase[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("approved");
  const [onlyCandidates, setOnlyCandidates] = useState(false);

  const [preview, setPreview] = useState<SuiteInheritancePreview | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedIds = useMemo(() => Array.from(selected.keys()), [selected]);

  const loadCandidates = useCallback(async () => {
    setLoadingList(true);
    try {
      const res = await automationSuiteApi.selectableTestCases(projectId, {
        search: search.trim() || undefined,
        status: statusFilter || undefined,
        automation_candidate: onlyCandidates ? true : undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setCandidates(res.data.items);
      setTotal(res.data.total);
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setLoadingList(false);
    }
  }, [projectId, search, statusFilter, onlyCandidates, page]);

  useEffect(() => {
    loadCandidates();
  }, [loadCandidates]);

  // The summary panel reflects the real inherited scope of the current
  // selection, so it refreshes whenever the selection or environment changes.
  const loadPreview = useCallback(async () => {
    if (selectedIds.length === 0) {
      setPreview(null);
      return;
    }
    setLoadingPreview(true);
    try {
      const res = await automationSuiteApi.previewInheritance(projectId, {
        test_case_ids: selectedIds,
        default_environment: environment || null,
      });
      setPreview(res.data);
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setLoadingPreview(false);
    }
  }, [projectId, selectedIds, environment]);

  useEffect(() => {
    const timer = setTimeout(loadPreview, 250);
    return () => clearTimeout(timer);
  }, [loadPreview]);

  const toggle = (testCase: SelectableTestCase) => {
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(testCase.id)) next.delete(testCase.id);
      else next.set(testCase.id, testCase);
      return next;
    });
  };

  const close = () => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("view", "workspace");
    params.delete("suite");
    router.push(`/automation?${params.toString()}`);
  };

  const create = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await automationSuiteApi.createSuite(projectId, {
        name: name.trim(),
        description: description.trim() || null,
        tags: tagsText
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        test_case_ids: selectedIds,
        default_environment: environment || null,
        idempotency_key: idempotencyKey.current,
      });
      const params = new URLSearchParams(searchParams.toString());
      params.set("view", "workspace");
      params.set("suite", String(res.data.id));
      router.push(`/automation?${params.toString()}`);
    } catch (err) {
      setError(messageFromError(err));
      setSubmitting(false);
    }
  };

  const canLeaveStep1 = selected.size > 0;
  const canLeaveStep2 = name.trim().length > 0;
  const canContinue = step === 1 ? canLeaveStep1 : step === 2 ? canLeaveStep2 : true;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex items-start justify-between gap-3 border-b border-gray-200 pb-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">New Automation Test Suite</h1>
          <p className="mt-1 text-xs font-semibold text-gray-500">
            Select test cases to create your suite. Applications, frameworks, scripts, environments
            and traceability are inherited automatically.
          </p>
        </div>
        <button
          type="button"
          onClick={close}
          className="rounded-md p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700"
          aria-label="Cancel"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      {error && (
        <div className="pt-3">
          <Banner kind="error" message={error} onDismiss={() => setError(null)} />
        </div>
      )}

      <div className="grid flex-1 grid-cols-1 gap-3 py-3 xl:grid-cols-[220px_1fr_290px]">
        {/* ── Left vertical stepper ── */}
        <ol className="space-y-1">
          {STEPS.map((s) => {
            const done = s.index < step;
            const active = s.index === step;
            return (
              <li key={s.index}>
                <button
                  type="button"
                  onClick={() => s.index < step && setStep(s.index)}
                  disabled={s.index > step}
                  className={cn(
                    "flex w-full items-start gap-2.5 rounded-lg border px-3 py-2 text-left transition",
                    active
                      ? "border-[#B71920] bg-app-brand-75/60"
                      : done
                        ? "border-gray-200 bg-white hover:bg-gray-50"
                        : "border-transparent bg-transparent",
                  )}
                >
                  <span
                    className={cn(
                      "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
                      done
                        ? "bg-emerald-500 text-white"
                        : active
                          ? "bg-[#B71920] text-white"
                          : "bg-gray-100 text-gray-400",
                    )}
                  >
                    {done ? <Check className="h-3 w-3" /> : s.index}
                  </span>
                  <span className="min-w-0">
                    <span
                      className={cn(
                        "block text-[11px] font-bold",
                        active ? "text-[#B71920]" : done ? "text-gray-800" : "text-gray-400",
                      )}
                    >
                      {s.title}
                    </span>
                    <span className="block text-[9px] font-semibold text-gray-400">
                      {s.subtitle}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>

        {/* ── Main workspace ── */}
        <div className="min-w-0 space-y-3">
          {step === 1 && (
            <Panel
              title="Select Test Cases (Primary Source)"
              action={
                <span className="text-[10px] font-bold text-gray-500">
                  Selected: {selected.size}
                  {selected.size > 0 && (
                    <button
                      type="button"
                      onClick={() => setSelected(new Map())}
                      className="ml-2 font-bold text-[#B71920]"
                    >
                      Clear all
                    </button>
                  )}
                </span>
              }
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-gray-400" />
                  <input
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setPage(1);
                    }}
                    placeholder="Search by ID, title or objective..."
                    className="h-8 w-56 rounded-md border border-gray-200 pl-7 pr-2 text-xs font-semibold"
                  />
                </div>
                <select
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                    setPage(1);
                  }}
                  className="h-8 rounded-md border border-gray-200 px-2 text-xs font-semibold"
                >
                  <option value="">Any approval status</option>
                  <option value="approved">Approved</option>
                  <option value="pending_approval">Pending approval</option>
                  <option value="draft">Draft</option>
                </select>
                <label className="flex items-center gap-1.5 text-[10px] font-bold text-gray-600">
                  <input
                    type="checkbox"
                    checked={onlyCandidates}
                    onChange={(e) => {
                      setOnlyCandidates(e.target.checked);
                      setPage(1);
                    }}
                  />
                  Automation candidates only
                </label>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-[10px]">
                  <thead>
                    <tr className="border-b border-gray-100 text-[9px] font-extrabold uppercase text-gray-400">
                      <th className="w-8 py-1.5" />
                      <th>Test Case</th>
                      <th>Title / Objective</th>
                      <th>Type</th>
                      <th>Priority</th>
                      <th>Automation</th>
                      <th>Assets</th>
                      <th>Mapping</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loadingList && (
                      <tr>
                        <td colSpan={8} className="py-8 text-center">
                          <Loader2 className="mx-auto h-4 w-4 animate-spin text-[#B71920]" />
                        </td>
                      </tr>
                    )}
                    {!loadingList &&
                      candidates.map((tc) => {
                        const checked = selected.has(tc.id);
                        return (
                          <tr
                            key={tc.id}
                            onClick={() => toggle(tc)}
                            className={cn(
                              "cursor-pointer border-b border-gray-50 hover:bg-gray-50",
                              checked && "bg-app-brand-75/40",
                            )}
                          >
                            <td className="py-1.5">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggle(tc)}
                                // Without this the row's own onClick also
                                // fires, toggling twice and appearing to do
                                // nothing when the checkbox itself is clicked.
                                onClick={(e) => e.stopPropagation()}
                                aria-label={`Select ${tc.test_case_reference ?? tc.id}`}
                              />
                            </td>
                            <td className="font-bold text-gray-800">
                              {tc.test_case_reference ?? `TC-${tc.id}`}
                            </td>
                            <td className="max-w-[240px] truncate font-semibold text-gray-600">
                              {tc.title ?? "—"}
                            </td>
                            <td className="font-semibold text-gray-600">{tc.test_type ?? "—"}</td>
                            <td className="font-semibold text-gray-600">{tc.priority ?? "—"}</td>
                            <td className="font-semibold text-gray-600">
                              {tc.automation_status ?? "—"}
                            </td>
                            <td className="font-semibold text-gray-600">
                              {tc.linked_script_count > 0 ? (
                                <span className="flex flex-wrap gap-1">
                                  {tc.frameworks.map((f) => (
                                    <Badge key={f} variant="outline" className="text-[8px]">
                                      {f}
                                    </Badge>
                                  ))}
                                </span>
                              ) : (
                                <span className="text-gray-300">None</span>
                              )}
                            </td>
                            <td>
                              <Badge
                                variant={tc.mapping_status === "MAPPED" ? "success" : "warning"}
                                className="text-[8px]"
                              >
                                {tc.mapping_status === "MAPPED" ? "Mapped" : "No application"}
                              </Badge>
                            </td>
                          </tr>
                        );
                      })}
                    {!loadingList && candidates.length === 0 && (
                      <tr>
                        <td colSpan={8} className="py-10 text-center text-xs font-semibold text-gray-400">
                          {search || onlyCandidates || statusFilter
                            ? "No test cases match these filters."
                            : "No test cases are available for selection. Create or import test cases in Test Management first."}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between border-t border-gray-100 pt-2 text-[10px] font-semibold text-gray-500">
                <span>
                  Showing {candidates.length} of {total} test cases
                </span>
                <span className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className="font-bold disabled:text-gray-300"
                  >
                    Previous
                  </button>
                  <span>
                    Page {page} of {pages}
                  </span>
                  <button
                    type="button"
                    disabled={page >= pages}
                    onClick={() => setPage((p) => Math.min(pages, p + 1))}
                    className="font-bold disabled:text-gray-300"
                  >
                    Next
                  </button>
                </span>
              </div>

              <p className="mt-2 rounded-md border border-app-brand-100 bg-app-brand-75/60 px-3 py-2 text-[10px] font-semibold text-app-brand-700">
                All application, framework, script, environment, data and traceability information
                is inherited from the selected test cases and their linked assets.
              </p>
            </Panel>
          )}

          {step === 2 && (
            <Panel title="Suite Identification">
              <div className="space-y-3">
                <label className="block">
                  <span className="mb-1 block text-[10px] font-extrabold uppercase text-gray-600">
                    Suite Name *
                  </span>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Postpaid Order Provisioning E2E"
                    className="h-9 w-full rounded-lg border border-gray-200 px-3 text-xs font-semibold"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-[10px] font-extrabold uppercase text-gray-600">
                    Description
                  </span>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-xs font-semibold"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-[10px] font-extrabold uppercase text-gray-600">
                    Tags
                  </span>
                  <input
                    value={tagsText}
                    onChange={(e) => setTagsText(e.target.value)}
                    placeholder="Comma separated, e.g. regression, postpaid"
                    className="h-9 w-full rounded-lg border border-gray-200 px-3 text-xs font-semibold"
                  />
                </label>
                <p className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-[10px] font-semibold text-gray-500">
                  Domain, product, channel, application, framework, priority, criticality and owner
                  are not captured here — they are inherited from the selected test cases. Suite
                  ownership is derived from you as the creator.
                </p>
              </div>
            </Panel>
          )}

          {step === 3 && (
            <Panel title="Review Inherited Details">
              {!preview ? (
                <p className="py-8 text-center text-xs font-semibold text-gray-400">
                  Select test cases to see what this suite inherits.
                </p>
              ) : (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {[
                    ["Applications", preview.applications, "Resolved from the selected test cases"],
                    [
                      "Framework Profiles",
                      preview.frameworks.length,
                      preview.frameworks.join(", ") || "No active scripts in scope",
                    ],
                    ["Existing Scripts", preview.existing_scripts, "From linked automation assets"],
                    ["Recordings", preview.recordings, "Discovery sessions for these test cases"],
                    [
                      "Environments",
                      preview.environments.length,
                      preview.environments.join(", ") || "Set a suite default in step 5",
                    ],
                    ["Test Data Sources", preview.test_data_sources, "Linked test data sets"],
                    ["Requirements", preview.requirements, "Traced through the test cases"],
                    ["Business Project", 1, preview.unavailable.business_projects],
                  ].map(([label, value, hint]) => (
                    <SummaryRow
                      key={String(label)}
                      label={String(label)}
                      value={value as number}
                      hint={String(hint)}
                    />
                  ))}
                  <SummaryRow
                    label="Automation IR definitions"
                    value={null}
                    hint={preview.unavailable.automation_ir_definitions}
                  />
                  <SummaryRow
                    label="Change Requests"
                    value={null}
                    hint={preview.unavailable.change_requests}
                  />
                </div>
              )}
              <p className="mt-2 text-[9px] font-semibold text-gray-400">
                All values above are read-only. Correct them at their source, not here.
              </p>
            </Panel>
          )}

          {step === 4 && (
            <Panel title="Resolve Conflicts and Define Scope">
              {!preview || preview.findings.length === 0 ? (
                <p className="py-8 text-center text-xs font-semibold text-gray-400">
                  No conflicts or missing mappings detected for this selection.
                </p>
              ) : (
                <>
                  <div className="mb-2 flex flex-wrap gap-2 text-[10px] font-bold">
                    <span className="rounded-md bg-red-50 px-2 py-1 text-red-700">
                      {preview.missing_mappings} blocking gap(s)
                    </span>
                    <span className="rounded-md bg-amber-50 px-2 py-1 text-amber-700">
                      {preview.warnings} warning(s)
                    </span>
                    <span className="rounded-md bg-purple-50 px-2 py-1 text-purple-700">
                      {preview.conflicts} conflict(s)
                    </span>
                  </div>
                  <div className="max-h-[340px] overflow-y-auto">
                    <table className="w-full text-left text-[10px]">
                      <thead>
                        <tr className="border-b border-gray-100 text-[9px] font-extrabold uppercase text-gray-400">
                          <th className="py-1.5">Finding</th>
                          <th>Severity</th>
                          <th>Scope</th>
                          <th>Detail</th>
                        </tr>
                      </thead>
                      <tbody>
                        {preview.findings.map((f, i) => (
                          <tr key={i} className="border-b border-gray-50 align-top">
                            <td className="py-1.5 font-bold text-gray-800">
                              {humanizeCode(f.gap_type)}
                            </td>
                            <td>
                              <SeverityBadge severity={f.severity as "critical" | "warning"} />
                            </td>
                            <td className="font-semibold text-gray-500">
                              {f.scope === "suite" ? "Suite" : `TC-${f.test_case_id ?? "?"}`}
                            </td>
                            <td className="max-w-[320px] font-semibold text-gray-600">
                              {f.reason}
                              {f.remediation && (
                                <span className="mt-0.5 block text-[9px] text-gray-400">
                                  {f.remediation}
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-2 flex items-start gap-1.5 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] font-semibold text-amber-800">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span>
                      A suite can be created with unresolved findings — it will open as a draft with
                      these listed under Conflicts and Gaps, where each one can be resolved,
                      excluded or waived with a recorded reason. Nothing at the source is changed.
                    </span>
                  </p>
                </>
              )}
            </Panel>
          )}

          {step === 5 && (
            <Panel title="Execution and Schedule">
              <label className="block max-w-xs">
                <span className="mb-1 block text-[10px] font-extrabold uppercase text-gray-600">
                  Default Environment
                </span>
                <input
                  value={environment}
                  onChange={(e) => setEnvironment(e.target.value)}
                  placeholder="e.g. SIT"
                  className="h-9 w-full rounded-lg border border-gray-200 px-3 text-xs font-semibold"
                />
                <span className="mt-1 block text-[9px] font-semibold text-gray-400">
                  Applied only where a test case has no environment of its own. It is matched
                  against the environment URLs configured in the Application Registry.
                </span>
              </label>
              <div className="mt-3 space-y-1.5 rounded-md border border-gray-200 bg-gray-50 px-3 py-2.5">
                <p className="text-[10px] font-extrabold uppercase text-gray-600">
                  Configured elsewhere, or not available
                </p>
                {[
                  [
                    "Execution groups and planned sequence",
                    "configured on the suite's Execution Groups tab once it exists",
                  ],
                  [
                    "Approval workflow",
                    "submit, approve and publish from the suite once it exists",
                  ],
                  ["Schedule", "no scheduler dispatches suite executions yet (P1-S7)"],
                  [
                    "Parallelism, retry and timeout policy",
                    "no suite-to-execution path exists yet (P1-S7)",
                  ],
                  ["Evidence policy", "no evidence entity exists yet"],
                  ["Agent pool preference", "no agent-pool entity exists"],
                  ["Notification rules", "no notification-rule entity exists"],
                ].map(([item, reason]) => (
                  <p key={item} className="text-[10px] font-semibold text-gray-400">
                    · <span className="text-gray-500">{item}</span> — {reason}
                  </p>
                ))}
              </div>
            </Panel>
          )}

          {step === 6 && (
            <Panel title="Review and Create">
              <div className="space-y-1">
                <SummaryRow label="Suite Name" value={name.trim() || null} hint="Required" />
                <SummaryRow label="Description" value={description.trim() || null} />
                <SummaryRow
                  label="Tags"
                  value={
                    tagsText
                      .split(",")
                      .map((t) => t.trim())
                      .filter(Boolean)
                      .join(", ") || null
                  }
                />
                <SummaryRow label="Selected Test Cases" value={selected.size} />
                <SummaryRow
                  label="Default Environment"
                  value={environment || null}
                  hint={environment ? undefined : "Environment readiness cannot be assessed without one"}
                />
                <SummaryRow label="Inherited Applications" value={preview?.applications ?? null} />
                <SummaryRow
                  label="Inherited Frameworks"
                  value={preview?.frameworks.join(", ") || null}
                />
                <SummaryRow label="Linked Scripts" value={preview?.existing_scripts ?? null} />
                <SummaryRow label="Blocking Gaps" value={preview?.missing_mappings ?? 0} />
                <SummaryRow label="Blocking Conflicts" value={preview?.blocking_conflicts ?? 0} />
              </div>
              {!canLeaveStep2 && (
                <p className="mt-2 text-[10px] font-bold text-red-600">
                  A suite name is required before the suite can be created.
                </p>
              )}
              <p className="mt-2 text-[10px] font-semibold text-gray-500">
                The suite will be created and immediately evaluated. Its status is derived from the
                result — it is not chosen here.
              </p>
            </Panel>
          )}
        </div>

        {/* ── Right summary panel ── */}
        <aside className="space-y-3">
          <Panel
            title="Selection Summary"
            action={
              loadingPreview ? (
                <Loader2 className="h-3 w-3 animate-spin text-[#B71920]" />
              ) : (
                <Badge variant="info" className="text-[8px]">
                  {selected.size} selected
                </Badge>
              )
            }
          >
            {selected.size === 0 ? (
              <p className="py-6 text-center text-[10px] font-semibold text-gray-400">
                Select test cases to see the inherited scope.
              </p>
            ) : (
              <div className="space-y-0">
                <SummaryRow label="Test Cases" value={preview?.selected_test_cases ?? selected.size} />
                <SummaryRow label="Applications" value={preview?.applications ?? null} />
                <SummaryRow
                  label="Frameworks"
                  value={preview ? preview.frameworks.length : null}
                  hint={preview?.frameworks.join(", ")}
                />
                <SummaryRow label="Existing Scripts" value={preview?.existing_scripts ?? null} />
                <SummaryRow
                  label="Environments"
                  value={preview ? preview.environments.length : null}
                  hint={preview?.environments.join(", ")}
                />
                <SummaryRow label="Test Data Sources" value={preview?.test_data_sources ?? null} />
                <SummaryRow label="Requirements" value={preview?.requirements ?? null} />
                <SummaryRow label="Missing Mappings" value={preview?.missing_mappings ?? null} />
                <SummaryRow label="Conflicts" value={preview?.conflicts ?? null} />
                <SummaryRow
                  label="Execution Groups"
                  value={null}
                  hint={preview?.unavailable.execution_groups}
                />
              </div>
            )}
          </Panel>

          {selected.size > 0 && (
            <Panel title={`Selected (${selected.size})`}>
              <ul className="max-h-52 space-y-1 overflow-y-auto">
                {Array.from(selected.values()).map((tc) => (
                  <li
                    key={tc.id}
                    className="flex items-center justify-between gap-2 border-b border-gray-50 py-1 last:border-0"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-[10px] font-bold text-gray-700">
                        {tc.test_case_reference ?? `TC-${tc.id}`}
                      </span>
                      <span className="block truncate text-[9px] font-semibold text-gray-400">
                        {tc.title ?? ""}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => toggle(tc)}
                      className="shrink-0 text-gray-300 hover:text-red-500"
                      aria-label={`Remove ${tc.test_case_reference ?? tc.id}`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </aside>
      </div>

      {/* ── Sticky footer ── */}
      {/* The platform's floating assistant widget sits bottom-right, so the
          primary action needs clearance or it ends up underneath it. */}
      <footer className="sticky bottom-0 flex flex-wrap items-center justify-between gap-2 border-t border-gray-200 bg-white/95 py-3 pr-[230px] backdrop-blur">
        <Button variant="outline" size="sm" onClick={close} disabled={submitting}>
          Cancel
        </Button>
        <div className="flex items-center gap-2">
          {step > 1 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setStep((s) => Math.max(1, s - 1))}
              disabled={submitting}
            >
              <ChevronLeft className="mr-1 h-3.5 w-3.5" />
              Back
            </Button>
          )}
          {step < 6 ? (
            <Button
              size="sm"
              onClick={() => setStep((s) => Math.min(6, s + 1))}
              disabled={!canContinue}
              title={
                canContinue
                  ? undefined
                  : step === 1
                    ? "Select at least one test case"
                    : "A suite name is required"
              }
            >
              Continue
              <ChevronRight className="ml-1 h-3.5 w-3.5" />
            </Button>
          ) : (
            <Button size="sm" onClick={create} disabled={submitting || !canLeaveStep2 || selected.size === 0}>
              {submitting && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              Create Suite
            </Button>
          )}
        </div>
      </footer>
    </div>
  );
}
