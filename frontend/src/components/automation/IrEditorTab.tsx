// UI-020 Automation IR Editor — Tab A.
//
// The tab does not open on a JSON tree. It opens on the work: the Unresolved
// section, driven by the emitter's real readiness map.
//
// The defining constraint (contract Section 11.4) is that
// `_targets_resolve_to_real_elements` rejects any step whose target is not a
// declared `<PageObject>.<element>`. So a target is NEVER a text input — it is
// a picker over declared elements — and the action is a select over the closed
// StepAction vocabulary. Validation runs on every edit against the real
// pydantic model, so an invalid contract can be seen but never saved.

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  Code2,
  History,
  Info,
  Loader2,
  Save,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import {
  automationAssetApi,
  type AutomationAsset,
  type DeclaredElement,
  type ElementCatalogue,
  type IrReadinessItem,
  type IrValidationResult,
  type IrVersionRow,
  type ProvenanceAction,
} from "@/lib/api";

import { messageFromError, Panel } from "./suite-shared";

// The closed StepAction vocabulary from generation_contract.py. Free text is
// impossible by construction — a value outside this list cannot be produced.
const STEP_ACTIONS = [
  "navigate",
  "fill",
  "click",
  "check",
  "uncheck",
  "select",
  "hover",
  "wait_for_visible",
  "wait_for_url",
  "custom",
] as const;

const STEP_PHASES = ["arrange", "act", "assert"] as const;

// PageObject.name / PageElement.name become TypeScript class names and
// filesystem path segments. Mirrors _SAFE_IDENTIFIER_RE exactly.
const SAFE_IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;

/** Plain-English label per readiness `kind`. An unknown kind still renders. */
const READINESS_LABELS: Record<string, string> = {
  unmapped_action: "Recorded action not attached to any step",
  no_locator: "Action has no usable locator",
  navigate_without_url: "Navigation has no resolved URL",
  unbound_input: "Typed value is not bound to test data",
  unreviewed_recommendation: "Recommended checkpoint not reviewed",
  unrenderable_checkpoint: "Checkpoint cannot be represented",
  checkpoint_without_element: "Checkpoint is missing its element",
  secret_reference: "Value identified as a secret",
  environment_profile: "Environment could not be resolved",
  script_type: "Script type could not be resolved",
};

interface ContractStep {
  phase?: string;
  action?: string;
  target?: string | null;
  value?: string | null;
  dataBinding?: string | null;
  description?: string | null;
  expectedResult?: string | null;
}

type Contract = Record<string, unknown> & { steps?: ContractStep[] };

function CollapsibleSection({
  title,
  count,
  defaultOpen = false,
  forceOpen = false,
  children,
}: {
  title: string;
  count?: number;
  defaultOpen?: boolean;
  forceOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const isOpen = forceOpen || open;
  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        onClick={() => !forceOpen && setOpen((v) => !v)}
        disabled={forceOpen}
      >
        <span className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-wide text-gray-800">
          {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          {title}
          {count !== undefined ? (
            <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-semibold text-gray-600">
              {count}
            </span>
          ) : null}
        </span>
      </button>
      {isOpen ? <div className="border-t border-gray-100 px-3 py-2">{children}</div> : null}
    </div>
  );
}

export function IrEditorTab({
  memberId,
  asset,
  onReload,
  onBusyChange,
}: {
  memberId: number;
  asset: AutomationAsset;
  onReload: () => Promise<void> | void;
  onBusyChange: (label: string | null) => void;
}) {
  const { toast } = useToast();

  const [contract, setContract] = useState<Contract>((asset.ir?.contract as Contract) ?? {});
  const [validation, setValidation] = useState<IrValidationResult | null>(asset.ir_validation);
  const [validating, setValidating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);

  const [catalogue, setCatalogue] = useState<ElementCatalogue | null>(null);
  const [versions, setVersions] = useState<IrVersionRow[]>([]);
  const [otherDrafts, setOtherDrafts] = useState(0);
  const [provenance, setProvenance] = useState<ProvenanceAction[]>([]);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const editable = asset.ir?.editable ?? false;
  const readiness = asset.ir?.readiness ?? {};
  const unresolved: IrReadinessItem[] = readiness.unresolved ?? [];

  useEffect(() => {
    setContract((asset.ir?.contract as Contract) ?? {});
    setValidation(asset.ir_validation);
    setDirty(false);
  }, [asset.ir?.id, asset.ir?.version, asset.ir?.contract, asset.ir_validation]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [cat, vers, prov] = await Promise.all([
          automationAssetApi.elements(memberId),
          automationAssetApi.irVersions(memberId),
          automationAssetApi.provenance(memberId),
        ]);
        if (cancelled) return;
        setCatalogue(cat.data);
        setVersions(vers.data.versions);
        setOtherDrafts(vers.data.other_session_draft_count);
        setProvenance(prov.data.actions);
      } catch {
        // Side panels are supporting context; the editor stays usable without
        // them rather than failing the whole tab.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [memberId]);

  /** Validate on every edit, not on save (Section 11.4 rule 4). Debounced. */
  const scheduleValidation = useCallback(
    (next: Contract) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        setValidating(true);
        automationAssetApi
          .validateIr(memberId, next)
          .then((res) => setValidation(res.data))
          .catch(() => {
            /* transport failure leaves the last verdict rather than clearing it */
          })
          .finally(() => setValidating(false));
      }, 400);
    },
    [memberId],
  );

  const updateContract = useCallback(
    (next: Contract) => {
      setContract(next);
      setDirty(true);
      scheduleValidation(next);
    },
    [scheduleValidation],
  );

  const steps = useMemo(() => (contract.steps ?? []) as ContractStep[], [contract.steps]);

  const updateStep = useCallback(
    (index: number, patch: Partial<ContractStep>) => {
      const nextSteps = steps.map((s, i) => (i === index ? { ...s, ...patch } : s));
      updateContract({ ...contract, steps: nextSteps });
    },
    [contract, steps, updateContract],
  );

  const errorsByField = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const err of validation?.errors ?? []) {
      const list = map.get(err.field) ?? [];
      list.push(err.message);
      map.set(err.field, list);
    }
    return map;
  }, [validation]);

  const pageLevelErrors = (validation?.errors ?? []).filter((e) => !e.field);

  const elementRequiredActions = new Set(
    catalogue?.element_required_actions ?? [
      "fill",
      "click",
      "check",
      "uncheck",
      "select",
      "hover",
      "wait_for_visible",
    ],
  );

  const declared: DeclaredElement[] = catalogue?.declared ?? [];

  const handleSave = useCallback(async () => {
    if (!validation?.valid) return;
    setSaving(true);
    onBusyChange("Saving behaviour…");
    try {
      await automationAssetApi.saveIr(memberId, contract);
      toast({ title: "Behaviour saved" });
      setDirty(false);
      await onReload();
    } catch (err) {
      toast({
        title: "Could not save the behaviour",
        description: messageFromError(err),
        variant: "error",
      });
    } finally {
      setSaving(false);
      onBusyChange(null);
    }
  }, [contract, memberId, onReload, onBusyChange, toast, validation?.valid]);

  const openAdvanced = useCallback(() => {
    setJsonText(JSON.stringify(contract, null, 2));
    setJsonError(null);
    setAdvanced(true);
  }, [contract]);

  const applyJson = useCallback(
    (text: string) => {
      setJsonText(text);
      try {
        const parsed = JSON.parse(text) as Contract;
        setJsonError(null);
        updateContract(parsed);
      } catch (err) {
        setJsonError((err as Error).message);
      }
    },
    [updateContract],
  );

  if (!asset.ir) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-6 text-center">
        <p className="text-[12px] font-semibold text-gray-700">No Automation IR yet</p>
        <p className="mx-auto mt-1 max-w-lg text-[11px] text-gray-500">
          {asset.unavailable.ir ??
            "Record this test case in the Live Recorder to produce an Automation IR."}
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
      {/* ── Main column ─────────────────────────────────────────────────── */}
      <div className="space-y-3">
        {!editable ? (
          <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-[11px] text-amber-900">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{asset.unavailable.ir_draft ?? "This behaviour is read-only."}</span>
          </div>
        ) : null}

        {/* Behaviour — read from the test case at render time, never copied. */}
        <Panel title="Behaviour (from Test Case)">
          {(asset as unknown as { behaviour?: { steps?: unknown[]; preconditions?: unknown[] } })
            .behaviour?.steps?.length ? (
            <ol className="space-y-1">
              {(
                (asset as unknown as { behaviour: { steps: Array<Record<string, unknown>> } })
                  .behaviour.steps
              ).map((step, i) => (
                <li key={i} className="flex gap-2 text-[11px] text-gray-700">
                  <span className="shrink-0 font-semibold text-gray-400">{i + 1}.</span>
                  <span>
                    {String(
                      step.description ?? step.action ?? step.step ?? JSON.stringify(step),
                    )}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-[11px] text-gray-400">
              {asset.unavailable.behaviour ?? "This test case records no steps."}
            </p>
          )}
        </Panel>

        {/* UNRESOLVED — first, and it cannot be collapsed while non-empty. */}
        {unresolved.length > 0 ? (
          <div className="rounded-lg border border-amber-300 bg-amber-50">
            <div className="flex items-center gap-1.5 border-b border-amber-200 px-3 py-2">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
              <span className="text-[10px] font-extrabold uppercase tracking-wide text-amber-900">
                Unresolved
              </span>
              <span className="rounded bg-amber-200 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900">
                {unresolved.length}
              </span>
            </div>
            <ul className="divide-y divide-amber-200">
              {unresolved.map((item, i) => (
                <li key={i} className="flex items-start justify-between gap-3 px-3 py-2">
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold text-amber-900">
                      {/* An unknown kind is rendered, never dropped. */}
                      {READINESS_LABELS[item.kind] ?? item.kind}
                    </p>
                    <p className="mt-0.5 text-[11px] text-amber-800">{item.detail}</p>
                  </div>
                  {item.action_id ? (
                    <Badge variant="outline" className="shrink-0 text-[10px]">
                      action #{item.action_id}
                    </Badge>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* Page-level validation errors that could not be anchored to a row. */}
        {pageLevelErrors.length > 0 ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-2.5">
            <p className="text-[10px] font-extrabold uppercase tracking-wide text-red-800">
              Validation
            </p>
            <ul className="mt-1 space-y-0.5">
              {pageLevelErrors.map((e, i) => (
                <li key={i} className="text-[11px] text-red-800">
                  {e.message}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* IR CONTRACT */}
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 px-3 py-2">
            <div className="flex items-center gap-2">
              <h3 className="text-[10px] font-extrabold uppercase tracking-wide text-gray-800">
                IR Contract
              </h3>
              <span className="text-[10px] text-gray-400">AutomationGenerationContract</span>
            </div>
            <div className="flex items-center gap-1.5">
              {validating ? (
                <span className="flex items-center gap-1 text-[10px] text-gray-500">
                  <Loader2 className="h-3 w-3 animate-spin" /> Validating…
                </span>
              ) : validation ? (
                <span
                  className={cn(
                    "flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold",
                    validation.valid
                      ? "bg-emerald-50 text-emerald-700"
                      : "bg-red-50 text-red-700",
                  )}
                >
                  {validation.valid ? <Check className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
                  {validation.valid ? "Valid" : `${validation.errors.length} error(s)`}
                </span>
              ) : null}
              <Button
                variant="outline"
                size="sm"
                className="h-6 text-[10px]"
                onClick={() => (advanced ? setAdvanced(false) : openAdvanced())}
              >
                <Code2 className="mr-1 h-3 w-3" />
                {advanced ? "Form" : "Advanced"}
              </Button>
            </div>
          </div>

          <div className="space-y-2 p-3">
            {advanced ? (
              <>
                {/* The Advanced surface bypasses the pickers, never the validator:
                    it posts to the same endpoint and shows the same errors. */}
                <textarea
                  className="h-[420px] w-full rounded border border-gray-200 bg-gray-50 p-2 font-mono text-[11px] text-gray-800"
                  value={jsonText}
                  spellCheck={false}
                  readOnly={!editable}
                  onChange={(e) => applyJson(e.target.value)}
                />
                {jsonError ? (
                  <p className="text-[11px] text-red-700">Malformed JSON: {jsonError}</p>
                ) : null}
              </>
            ) : (
              <>
                <CollapsibleSection title="Steps" count={steps.length} defaultOpen forceOpen={false}>
                  {steps.length === 0 ? (
                    <p className="text-[11px] text-gray-400">This contract has no steps.</p>
                  ) : (
                    <div className="space-y-1.5">
                      {steps.map((step, index) => {
                        const fieldErrors = errorsByField.get(`steps.${index}.target`) ?? [];
                        const needsElement = elementRequiredActions.has(step.action ?? "");
                        const isCustom = step.action === "custom";
                        return (
                          <div
                            key={index}
                            className={cn(
                              "rounded border p-2",
                              isCustom
                                ? "border-amber-300 bg-amber-50"
                                : fieldErrors.length
                                  ? "border-red-300 bg-red-50"
                                  : "border-gray-200 bg-white",
                            )}
                          >
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="w-5 text-[10px] font-bold text-gray-400">
                                {index + 1}
                              </span>

                              <select
                                className="h-6 rounded border border-gray-200 bg-white px-1 text-[11px]"
                                value={step.phase ?? "act"}
                                disabled={!editable}
                                onChange={(e) => updateStep(index, { phase: e.target.value })}
                              >
                                {STEP_PHASES.map((p) => (
                                  <option key={p} value={p}>
                                    {p}
                                  </option>
                                ))}
                              </select>

                              {/* Closed vocabulary — free text is impossible. */}
                              <select
                                className="h-6 rounded border border-gray-200 bg-white px-1 text-[11px] font-medium"
                                value={step.action ?? "click"}
                                disabled={!editable}
                                onChange={(e) => {
                                  const action = e.target.value;
                                  // Switching away from an element action clears a
                                  // target that would no longer be valid, so the
                                  // form can never hold an unsaveable shape.
                                  const patch: Partial<ContractStep> = { action };
                                  if (!elementRequiredActions.has(action)) patch.target = null;
                                  updateStep(index, patch);
                                }}
                              >
                                {STEP_ACTIONS.map((a) => (
                                  <option key={a} value={a}>
                                    {a}
                                  </option>
                                ))}
                              </select>

                              {/* Target is a PICKER over declared elements. Never a text input. */}
                              {needsElement ? (
                                <select
                                  className={cn(
                                    "h-6 min-w-[190px] rounded border bg-white px-1 text-[11px]",
                                    fieldErrors.length ? "border-red-400" : "border-gray-200",
                                  )}
                                  value={step.target ?? ""}
                                  disabled={!editable}
                                  onChange={(e) =>
                                    updateStep(index, { target: e.target.value || null })
                                  }
                                >
                                  <option value="">— pick an element —</option>
                                  {declared.map((d) => (
                                    <option
                                      key={`${d.page_object}.${d.name}`}
                                      value={`${d.page_object}.${d.name}`}
                                    >
                                      {d.page_object}.{d.name}
                                      {d.in_model ? "" : "  (recorded, not in model)"}
                                    </option>
                                  ))}
                                </select>
                              ) : step.action === "navigate" ? (
                                <input
                                  className="h-6 min-w-[190px] rounded border border-gray-200 px-1 text-[11px]"
                                  placeholder="/path"
                                  value={step.value ?? step.target ?? ""}
                                  disabled={!editable}
                                  onChange={(e) => updateStep(index, { value: e.target.value })}
                                />
                              ) : step.action === "wait_for_url" ? (
                                <input
                                  className="h-6 min-w-[190px] rounded border border-gray-200 px-1 text-[11px]"
                                  placeholder="url fragment"
                                  value={step.value ?? ""}
                                  disabled={!editable}
                                  onChange={(e) => updateStep(index, { value: e.target.value })}
                                />
                              ) : null}

                              {isCustom ? (
                                <input
                                  className="h-6 flex-1 rounded border border-amber-300 px-1 text-[11px]"
                                  placeholder="Describe what this step should do (renders as a TODO)"
                                  value={step.description ?? ""}
                                  disabled={!editable}
                                  onChange={(e) =>
                                    updateStep(index, { description: e.target.value })
                                  }
                                />
                              ) : null}
                            </div>

                            {fieldErrors.map((msg, i) => (
                              <p key={i} className="mt-1 pl-6 text-[10px] font-medium text-red-700">
                                {msg}
                              </p>
                            ))}

                            {isCustom ? (
                              <p className="mt-1 pl-6 text-[10px] text-amber-800">
                                Unresolved — this compiles to a TODO comment, not a real action.
                              </p>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CollapsibleSection>

                <CollapsibleSection
                  title="Page objects and elements"
                  count={declared.length}
                >
                  {declared.length === 0 ? (
                    <p className="text-[11px] text-gray-400">
                      This contract declares no page objects.
                    </p>
                  ) : (
                    <table className="w-full text-[11px]">
                      <thead>
                        <tr className="text-left text-[10px] uppercase text-gray-400">
                          <th className="py-1">Page object</th>
                          <th>Element</th>
                          <th>Strategy</th>
                          <th>Locator</th>
                          <th>Grounded</th>
                        </tr>
                      </thead>
                      <tbody>
                        {declared.map((d) => (
                          <tr key={`${d.page_object}.${d.name}`} className="border-t border-gray-100">
                            <td className="py-1 text-gray-600">{d.page_object}</td>
                            <td className="font-medium text-gray-800">
                              {d.name}
                              {!SAFE_IDENTIFIER.test(d.name) ? (
                                <span className="ml-1 text-red-600" title="Not a safe identifier">
                                  !
                                </span>
                              ) : null}
                            </td>
                            <td className="text-gray-600">{d.locator_strategy ?? "—"}</td>
                            <td className="max-w-[180px] truncate text-gray-500">
                              {d.locator_value ?? "—"}
                            </td>
                            <td>
                              {d.in_model ? (
                                <Badge variant="success" className="text-[9px]">
                                  In model
                                </Badge>
                              ) : (
                                <Badge
                                  variant="outline"
                                  className="text-[9px]"
                                  title="Observed during recording but not present in the approved Application Model."
                                >
                                  Recorded only
                                </Badge>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </CollapsibleSection>

                <CollapsibleSection
                  title="Assertions"
                  count={(contract.assertions as unknown[] | undefined)?.length ?? 0}
                >
                  <pre className="max-h-48 overflow-auto text-[10px] text-gray-600">
                    {JSON.stringify(contract.assertions ?? [], null, 2)}
                  </pre>
                </CollapsibleSection>

                <CollapsibleSection
                  title="Test data bindings"
                  count={(contract.testDataBindings as unknown[] | undefined)?.length ?? 0}
                >
                  <pre className="max-h-48 overflow-auto text-[10px] text-gray-600">
                    {JSON.stringify(contract.testDataBindings ?? [], null, 2)}
                  </pre>
                </CollapsibleSection>
              </>
            )}
          </div>

          <div className="flex items-center justify-between gap-2 border-t border-gray-100 px-3 py-2">
            <span className="text-[10px] text-gray-400">
              Schema: AutomationGenerationContract v{asset.ir.contract_version}
            </span>
            <div className="flex items-center gap-2">
              {dirty ? (
                <span className="text-[10px] font-medium text-amber-700">Unsaved changes</span>
              ) : null}
              <Button
                size="sm"
                className="h-7 text-[11px]"
                disabled={!editable || !dirty || saving || !validation?.valid}
                title={
                  !editable
                    ? asset.unavailable.ir_draft ?? "This behaviour is read-only."
                    : !validation?.valid
                      ? "Fix the validation errors before saving."
                      : !dirty
                        ? "No changes to save."
                        : undefined
                }
                onClick={() => void handleSave()}
              >
                {saving ? (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                ) : (
                  <Save className="mr-1 h-3 w-3" />
                )}
                Save IR
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Right rail ──────────────────────────────────────────────────── */}
      <div className="space-y-3">
        <Panel title="IR Source">
          <div className="space-y-1 text-[11px]">
            <div className="flex items-center justify-between">
              <span className="text-gray-500">Draft</span>
              <span className="font-medium text-gray-800">
                {asset.ir.id ? `IRD-${asset.ir.id}` : "From compiled script"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-500">Version</span>
              <span className="font-medium text-gray-800">v{asset.ir.version}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-500">Status</span>
              <Badge variant={asset.ir.editable ? "info" : "outline"} className="text-[9px]">
                {asset.ir.status}
              </Badge>
            </div>
            {validation?.summary ? (
              <div className="mt-2 border-t border-gray-100 pt-2 text-[10px] text-gray-500">
                {validation.summary.step_count} steps · {validation.summary.locator_count} locators ·{" "}
                {validation.summary.assertion_count} assertions
                {validation.summary.custom_step_count > 0 ? (
                  <span className="ml-1 font-semibold text-amber-700">
                    · {validation.summary.custom_step_count} unresolved
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
        </Panel>

        <Panel title="Readiness" action={<span className="text-[10px] text-gray-400">{unresolved.length} items</span>}>
          {unresolved.length === 0 ? (
            <p className="text-[11px] text-emerald-700">Nothing unresolved.</p>
          ) : (
            <ul className="space-y-2">
              {unresolved.map((item, i) => (
                <li key={i} className="rounded border border-amber-200 bg-amber-50 p-2">
                  <p className="flex items-center gap-1 text-[11px] font-semibold text-amber-900">
                    <Wrench className="h-3 w-3" />
                    {READINESS_LABELS[item.kind] ?? item.kind}
                  </p>
                  <p className="mt-0.5 text-[10px] text-amber-800">{item.detail}</p>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title="Provenance"
          action={<span className="text-[10px] text-gray-400">{provenance.length} actions</span>}
        >
          {provenance.length === 0 ? (
            <p className="text-[11px] text-gray-400">
              This IR records no source actions — its steps are authored, not recorded.
            </p>
          ) : (
            <ul className="space-y-1">
              {provenance.map((a) => (
                <li key={a.id} className="flex items-start gap-1.5 text-[11px] text-gray-700">
                  <Check className="mt-0.5 h-3 w-3 shrink-0 text-emerald-600" />
                  <span
                    className="truncate"
                    title={a.target_element_ref ?? a.target_semantic ?? undefined}
                  >
                    {a.action_family ?? "action"}
                    {a.target_semantic ? ` — ${a.target_semantic}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {versions.length > 1 || otherDrafts > 0 ? (
          <Panel title="Versions" action={<History className="h-3 w-3 text-gray-400" />}>
            <ul className="space-y-1">
              {versions.map((v) => (
                <li
                  key={v.id}
                  className={cn(
                    "flex items-center justify-between rounded px-1.5 py-1 text-[11px]",
                    v.is_current ? "bg-app-brand-75 font-medium text-app-brand-800" : "text-gray-600",
                  )}
                >
                  <span>v{v.version}</span>
                  <span className="text-[10px] text-gray-400">
                    {v.step_count} steps · {v.unresolved_count} unresolved
                  </span>
                </li>
              ))}
            </ul>
            {otherDrafts > 0 ? (
              // Drafts from other recording sessions are counted, never merged
              // into this chain — they are separate chains, not older versions.
              <p className="mt-2 border-t border-gray-100 pt-2 text-[10px] text-gray-500">
                {otherDrafts} draft{otherDrafts === 1 ? "" : "s"} from other recording
                sessions of this test case are not shown here.
              </p>
            ) : null}
          </Panel>
        ) : null}
      </div>
    </div>
  );
}
