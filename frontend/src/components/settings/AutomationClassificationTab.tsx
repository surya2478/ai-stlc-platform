"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Plus, Save, ShieldCheck, Trash2 } from "lucide-react";
import {
  automationClassificationApi,
  type AutomationClassificationPolicy,
} from "@/lib/api";
import { Button } from "@/components/ui/button";

const CHECKS = [
  ["unresolved_requirement", "Requirement and scenario approval", "Require approved traceability before automation."],
  ["missing_expected_result", "Complete test instructions", "Require test steps and a deterministic expected result."],
  ["production_only", "Production-only or destructive tests", "Prevent unsafe unattended automation."],
  ["unsupported_application", "Application mapping", "Check that an active application is mapped."],
  ["test_data_not_ready", "Test data readiness", "Check that reusable test data is available."],
  ["unstable_ui", "UI stability", "Check whether the target interface is marked unstable."],
  ["scenario_not_approved", "Scenario approval", "Require the linked scenario to be approved."],
  ["optional_validator_unavailable", "Optional validators", "Warn when an optional validator is unavailable."],
] as const;

const AUTOMATION_WEIGHTS = [
  ["expected_result_determinism", "Expected-result determinism"],
  ["regression_value", "Regression value"],
  ["reusability", "Reusability"],
  ["manual_effort", "Manual effort saved"],
  ["business_criticality", "Business criticality"],
] as const;

const COMPLEXITY_WEIGHTS = [
  ["step_count", "Step count"],
  ["external_dependency_count", "External dependencies"],
  ["test_data_volume", "Test-data volume"],
  ["precondition_count", "Preconditions"],
] as const;

type RuleMode = "block" | "conditional" | "ignore";
type PolicyRules = {
  manual_only_conditions: Array<{
    code: string;
    label: string;
    keywords: string[];
    metadata_flags?: string[];
    reason: string;
  }>;
  candidate_rules: {
    block_if: string[];
    conditional_if: string[];
    minimum_automation_value_score: number;
  };
  routing_rules: Array<{ when: Record<string, unknown>; primary_adapter: string; supporting_adapters: string[] }>;
  external_validation_rules: Array<{ required: string[]; optional: string[] }>;
  evidence_rules: { web_e2e: { mandatory: string[] } };
  scoring_weights: {
    automation_value: Record<string, number>;
    complexity: Record<string, number>;
  };
};

const FALLBACK_RULES: PolicyRules = {
  manual_only_conditions: [
    { code: "captcha", label: "CAPTCHA challenge", keywords: ["captcha", "recaptcha", "hcaptcha"], metadata_flags: ["captcha_dependency"], reason: "CAPTCHA requires human verification and cannot be completed by unattended automation." },
    { code: "otp", label: "OTP verification", keywords: ["otp", "one-time password", "one time password", "sms code"], metadata_flags: ["otp_dependency"], reason: "OTP depends on a secure out-of-band code and requires controlled human handling." },
    { code: "biometrics", label: "Biometric verification", keywords: ["biometric", "fingerprint", "face id", "facial recognition", "iris scan"], metadata_flags: ["biometric_dependency"], reason: "Biometric identity checks require a physical person or approved specialist hardware." },
    { code: "kiosk", label: "Physical kiosk", keywords: ["kiosk", "self-service terminal"], metadata_flags: ["kiosk_dependency"], reason: "This test depends on physical kiosk hardware that is unavailable to unattended automation." },
    { code: "atm", label: "ATM machine", keywords: ["atm", "cash machine", "automated teller"], metadata_flags: ["atm_dependency"], reason: "This test depends on physical ATM hardware and must follow a controlled manual process." },
  ],
  candidate_rules: {
    block_if: ["unresolved_requirement", "missing_expected_result", "production_only"],
    conditional_if: ["unsupported_application", "test_data_not_ready", "unstable_ui", "optional_validator_unavailable"],
    minimum_automation_value_score: 60,
  },
  routing_rules: [{ when: {}, primary_adapter: "PLAYWRIGHT_MCP", supporting_adapters: [] }],
  external_validation_rules: [{ required: [], optional: [] }],
  evidence_rules: { web_e2e: { mandatory: ["SCREENSHOT", "DOM_SNAPSHOT", "NETWORK_TRACE", "STEP_RESULT", "BUSINESS_ASSERTION"] } },
  scoring_weights: {
    automation_value: {
      expected_result_determinism: 25,
      regression_value: 20,
      reusability: 15,
      manual_effort: 20,
      business_criticality: 20,
    },
    complexity: {
      step_count: 30,
      external_dependency_count: 30,
      test_data_volume: 20,
      precondition_count: 20,
    },
  },
};

function copyRules(value: unknown): PolicyRules {
  const source = (value && typeof value === "object" ? value : {}) as Partial<PolicyRules>;
  return {
    manual_only_conditions: source.manual_only_conditions || FALLBACK_RULES.manual_only_conditions,
    candidate_rules: { ...FALLBACK_RULES.candidate_rules, ...(source.candidate_rules || {}) },
    routing_rules: source.routing_rules?.length ? source.routing_rules : FALLBACK_RULES.routing_rules,
    external_validation_rules: source.external_validation_rules?.length
      ? source.external_validation_rules
      : FALLBACK_RULES.external_validation_rules,
    evidence_rules: {
      web_e2e: {
        mandatory: source.evidence_rules?.web_e2e?.mandatory || FALLBACK_RULES.evidence_rules.web_e2e.mandatory,
      },
    },
    scoring_weights: {
      automation_value: {
        ...FALLBACK_RULES.scoring_weights.automation_value,
        ...(source.scoring_weights?.automation_value || {}),
      },
      complexity: {
        ...FALLBACK_RULES.scoring_weights.complexity,
        ...(source.scoring_weights?.complexity || {}),
      },
    },
  };
}

function list(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function FieldLabel({ children }: { children: ReactNode }) {
  return <label className="mb-1 block text-xs font-bold text-gray-700">{children}</label>;
}

export function AutomationClassificationTab({ projectId }: { projectId: number }) {
  const [policy, setPolicy] = useState<AutomationClassificationPolicy | null>(null);
  const [name, setName] = useState("Project Automation Classification");
  const [rules, setRules] = useState<PolicyRules>(FALLBACK_RULES);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    setLoading(true);
    setMessage(null);
    automationClassificationApi.effectivePolicy(projectId)
      .then(({ data }) => {
        setPolicy(data);
        setName(data.project_id === projectId ? data.name : "Project Automation Classification");
        setRules(copyRules(data.rules));
      })
      .catch(() => setMessage({ kind: "error", text: "Could not load the automation-classification policy." }))
      .finally(() => setLoading(false));
  }, [projectId]);

  const scope = policy?.project_id === projectId ? "Project override" : "Platform default";
  const automationWeightTotal = useMemo(
    () => Object.values(rules.scoring_weights.automation_value).reduce((sum, value) => sum + Number(value || 0), 0),
    [rules.scoring_weights.automation_value],
  );
  const complexityWeightTotal = useMemo(
    () => Object.values(rules.scoring_weights.complexity).reduce((sum, value) => sum + Number(value || 0), 0),
    [rules.scoring_weights.complexity],
  );

  function modeFor(key: string): RuleMode {
    if (rules.candidate_rules.block_if.includes(key)) return "block";
    if (rules.candidate_rules.conditional_if.includes(key)) return "conditional";
    return "ignore";
  }

  function setMode(key: string, mode: RuleMode) {
    setRules((current) => ({
      ...current,
      candidate_rules: {
        ...current.candidate_rules,
        block_if: current.candidate_rules.block_if.filter((item) => item !== key).concat(mode === "block" ? [key] : []),
        conditional_if: current.candidate_rules.conditional_if.filter((item) => item !== key).concat(mode === "conditional" ? [key] : []),
      },
    }));
  }

  function setWeight(group: "automation_value" | "complexity", key: string, value: number) {
    setRules((current) => ({
      ...current,
      scoring_weights: {
        ...current.scoring_weights,
        [group]: { ...current.scoring_weights[group], [key]: Math.max(0, Math.min(100, value || 0)) },
      },
    }));
  }

  function updateManualCondition(index: number, patch: Partial<PolicyRules["manual_only_conditions"][number]>) {
    setRules((current) => ({
      ...current,
      manual_only_conditions: current.manual_only_conditions.map((condition, itemIndex) =>
        itemIndex === index ? { ...condition, ...patch } : condition
      ),
    }));
  }

  function addManualCondition() {
    setRules((current) => ({
      ...current,
      manual_only_conditions: [
        ...current.manual_only_conditions,
        {
          code: `custom_${Date.now()}`,
          label: "New manual-only condition",
          keywords: [],
          reason: "This condition requires controlled manual execution.",
        },
      ],
    }));
  }

  function removeManualCondition(index: number) {
    setRules((current) => ({
      ...current,
      manual_only_conditions: current.manual_only_conditions.filter((_, itemIndex) => itemIndex !== index),
    }));
  }

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      const { data } = await automationClassificationApi.updateProjectPolicy(projectId, {
        name,
        rules: rules as unknown as Record<string, unknown>,
      });
      setPolicy(data);
      setRules(copyRules(data.rules));
      setMessage({
        kind: "success",
        text: `Policy v${data.version} is published. Existing classifications must be rerun before approval.`,
      });
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: { message?: string } | string } } })?.response?.data?.detail;
      setMessage({
        kind: "error",
        text: typeof detail === "string" ? detail : detail?.message || "Could not publish the project policy.",
      });
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="flex h-64 items-center justify-center text-sm font-semibold text-gray-500"><Loader2 className="mr-2 h-5 w-5 animate-spin text-[#B71920]" />Loading classification policy...</div>;
  }

  const route = rules.routing_rules[0] || FALLBACK_RULES.routing_rules[0];
  const validators = rules.external_validation_rules[0] || FALLBACK_RULES.external_validation_rules[0];

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-app-brand-75 text-[#B71920]"><ShieldCheck className="h-5 w-5" /></span>
            <div>
              <h2 className="text-lg font-black text-gray-900">Automation Classification Policy</h2>
              <p className="mt-1 text-sm text-gray-500">Mandatory for every project. No environment feature flags are required.</p>
            </div>
          </div>
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700">
            Enabled · {scope}{policy ? ` · v${policy.version}` : ""}
          </div>
        </div>
        {message && (
          <div className={`mt-4 flex items-start gap-2 rounded-lg border p-3 text-xs font-semibold ${message.kind === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"}`}>
            {message.kind === "success" ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <AlertTriangle className="h-4 w-4 shrink-0" />}
            {message.text}
          </div>
        )}
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-black text-gray-900">Decision threshold</h3>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <FieldLabel>Policy name</FieldLabel>
            <input value={name} onChange={(event) => setName(event.target.value)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" />
          </div>
          <div>
            <FieldLabel>Minimum automation-value score (0–100)</FieldLabel>
            <input
              type="number"
              min={0}
              max={100}
              value={rules.candidate_rules.minimum_automation_value_score}
              onChange={(event) => setRules((current) => ({
                ...current,
                candidate_rules: { ...current.candidate_rules, minimum_automation_value_score: Number(event.target.value) },
              }))}
              className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm"
            />
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-black text-gray-900">Automation not possible</h3>
            <p className="mt-1 text-xs text-gray-500">Any matching condition becomes a clear deterministic blocker. Matching checks the test-case title, objective, steps, expected result, preconditions, BDD, and test data.</p>
          </div>
          <Button type="button" variant="outline" onClick={addManualCondition} className="h-9 gap-2 text-xs font-bold">
            <Plus className="h-4 w-4" />Add Condition
          </Button>
        </div>
        <div className="mt-4 space-y-3">
          {rules.manual_only_conditions.map((condition, index) => (
            <div key={condition.code} className="rounded-lg border border-gray-200 bg-gray-50/60 p-4">
              <div className="grid gap-3 md:grid-cols-[220px_1fr_auto]">
                <div>
                  <FieldLabel>Condition name</FieldLabel>
                  <input value={condition.label} onChange={(event) => updateManualCondition(index, { label: event.target.value })} className="h-9 w-full rounded-lg border border-gray-200 bg-white px-3 text-xs" />
                </div>
                <div>
                  <FieldLabel>Matching words or phrases</FieldLabel>
                  <input value={condition.keywords.join(", ")} onChange={(event) => updateManualCondition(index, { keywords: list(event.target.value) })} placeholder="Example: captcha, recaptcha" className="h-9 w-full rounded-lg border border-gray-200 bg-white px-3 text-xs" />
                </div>
                <button type="button" aria-label={`Remove ${condition.label}`} onClick={() => removeManualCondition(index)} className="mt-5 flex h-9 w-9 items-center justify-center rounded-lg border border-red-200 bg-white text-red-600 hover:bg-red-50">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
              <div className="mt-3">
                <FieldLabel>Message shown to the user</FieldLabel>
                <input value={condition.reason} onChange={(event) => updateManualCondition(index, { reason: event.target.value })} className="h-9 w-full rounded-lg border border-gray-200 bg-white px-3 text-xs" />
              </div>
            </div>
          ))}
          {!rules.manual_only_conditions.length && (
            <div className="rounded-lg border border-dashed border-gray-200 p-6 text-center text-xs font-semibold text-gray-400">No manual-only conditions configured.</div>
          )}
        </div>
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-black text-gray-900">Classification criteria</h3>
        <p className="mt-1 text-xs text-gray-500">Choose whether each finding blocks automation, makes it conditional, or is ignored.</p>
        <div className="mt-4 divide-y divide-gray-100">
          {CHECKS.map(([key, label, help]) => (
            <div key={key} className="grid gap-3 py-3 md:grid-cols-[1fr_180px] md:items-center">
              <div><p className="text-xs font-bold text-gray-800">{label}</p><p className="mt-1 text-[11px] text-gray-500">{help}</p></div>
              <select value={modeFor(key)} onChange={(event) => setMode(key, event.target.value as RuleMode)} className="h-9 rounded-lg border border-gray-200 px-2 text-xs font-semibold">
                <option value="block">Block automation</option>
                <option value="conditional">Conditional / warning</option>
                <option value="ignore">Ignore</option>
              </select>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-black text-gray-900">Routing, validators and evidence</h3>
        <p className="mt-1 text-xs text-gray-500">Use registered capability keys. Separate multiple values with commas.</p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div><FieldLabel>Primary adapter</FieldLabel><input value={route.primary_adapter || ""} onChange={(event) => setRules((current) => ({ ...current, routing_rules: [{ ...route, primary_adapter: event.target.value }] }))} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" /></div>
          <div><FieldLabel>Supporting adapters</FieldLabel><input value={(route.supporting_adapters || []).join(", ")} onChange={(event) => setRules((current) => ({ ...current, routing_rules: [{ ...route, supporting_adapters: list(event.target.value) }] }))} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" /></div>
          <div><FieldLabel>Mandatory validators</FieldLabel><input value={(validators.required || []).join(", ")} onChange={(event) => setRules((current) => ({ ...current, external_validation_rules: [{ ...validators, required: list(event.target.value) }] }))} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" /></div>
          <div><FieldLabel>Optional validators</FieldLabel><input value={(validators.optional || []).join(", ")} onChange={(event) => setRules((current) => ({ ...current, external_validation_rules: [{ ...validators, optional: list(event.target.value) }] }))} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" /></div>
          <div className="md:col-span-2"><FieldLabel>Required evidence</FieldLabel><input value={rules.evidence_rules.web_e2e.mandatory.join(", ")} onChange={(event) => setRules((current) => ({ ...current, evidence_rules: { web_e2e: { mandatory: list(event.target.value) } } }))} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" /></div>
        </div>
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-black text-gray-900">Scoring weights</h3>
        <p className="mt-1 text-xs text-gray-500">Weights are normalized automatically; totals do not need to equal 100.</p>
        <div className="mt-4 grid gap-6 lg:grid-cols-2">
          <div>
            <p className="mb-3 text-xs font-extrabold text-gray-700">Automation value · total {automationWeightTotal}</p>
            <div className="space-y-2">{AUTOMATION_WEIGHTS.map(([key, label]) => <div key={key} className="flex items-center justify-between gap-3"><label className="text-xs text-gray-600">{label}</label><input type="number" min={0} max={100} value={rules.scoring_weights.automation_value[key]} onChange={(event) => setWeight("automation_value", key, Number(event.target.value))} className="h-8 w-20 rounded border border-gray-200 px-2 text-xs" /></div>)}</div>
          </div>
          <div>
            <p className="mb-3 text-xs font-extrabold text-gray-700">Complexity · total {complexityWeightTotal}</p>
            <div className="space-y-2">{COMPLEXITY_WEIGHTS.map(([key, label]) => <div key={key} className="flex items-center justify-between gap-3"><label className="text-xs text-gray-600">{label}</label><input type="number" min={0} max={100} value={rules.scoring_weights.complexity[key]} onChange={(event) => setWeight("complexity", key, Number(event.target.value))} className="h-8 w-20 rounded border border-gray-200 px-2 text-xs" /></div>)}</div>
          </div>
        </div>
      </section>

      <div className="flex justify-end">
        <Button onClick={() => void save()} disabled={saving || !name.trim()} className="gap-2 bg-[#B71920] text-white">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Save &amp; Publish New Version
        </Button>
      </div>
    </div>
  );
}
