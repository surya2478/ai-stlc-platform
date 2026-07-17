"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  Bot,
  Braces,
  CheckCircle2,
  ChevronDown,
  Database,
  Globe2,
  Info,
  KeyRound,
  Loader2,
  LockKeyhole,
  Route,
  Save,
  Settings,
  ShieldCheck,
  Sparkles,
  TestTube2,
  Users,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const MODULE_SCOPES = [
  "Requirement Analysis",
  "Test Plan Generation",
  "Test Scenario Generation",
  "Test Case Generation",
  "Test Execution Assistance",
  "Defect Triage",
  "Test Reporting",
];

type ProviderMeta = {
  provider_name: string;
  provider_key: string;
  description: string;
  logo_icon: string;
  available_models: string[];
  api_key_required: boolean;
  api_key_configured: boolean;
  supports_local_execution: boolean;
  supports_fallback_usage: boolean;
  enabled_for_selection: boolean;
  default_model: string;
};

type LLMRole = "coding" | "vision" | "reasoning";
const LLM_ROLES: LLMRole[] = ["coding", "vision", "reasoning"];
const ROLE_LABELS: Record<LLMRole, string> = { coding: "Coding", vision: "Vision", reasoning: "Reasoning" };

type ProjectLLMSetting = {
  id?: number | null;
  project_id: number;
  provider_name: string;
  provider_key: string;
  model_name: string;
  is_enabled: boolean;
  is_primary: boolean;
  is_fallback: boolean;
  fallback_priority: number | null;
  temperature: number;
  max_tokens: number;
  timeout_seconds: number;
  module_scope: string[];
  llm_role: LLMRole | null;
  config_status: string;
  created_by?: number | null;
  updated_by?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type RoleRoute = { provider_key: string; provider_name?: string; model_name: string; source?: string };

type ProjectLLMSettingsResponse = {
  project_id: number;
  providers: ProviderMeta[];
  settings: ProjectLLMSetting[];
  active_provider: ProjectLLMSetting | null;
  active_model: string | null;
  fallback_order: ProjectLLMSetting[];
  system_default_provider: string;
  system_default_model: string;
  uses_system_default: boolean;
  role_defaults: Record<LLMRole, RoleRoute>;
  active_by_role: Record<LLMRole, RoleRoute>;
  last_updated: string | null;
  updated_by: number | null;
  security_status: "Secure";
};

type ToastState = {
  title: string;
  message: string;
  kind: "success" | "error" | "info";
} | null;

function providerIcon(icon: string) {
  const className = "h-6 w-6";
  if (icon === "zap") return <Zap className={cn(className, "text-emerald-600")} />;
  if (icon === "sparkles") return <Sparkles className={cn(className, "text-blue-600")} />;
  if (icon === "server") return <Database className={cn(className, "text-slate-700")} />;
  if (icon === "route") return <Route className={cn(className, "text-violet-600")} />;
  if (icon === "braces") return <Braces className={cn(className, "text-amber-600")} />;
  return <Bot className={cn(className, "text-[#1b59f8]")} />;
}

function emptySetting(projectId: number, provider: ProviderMeta, llmRole: LLMRole | null = null): ProjectLLMSetting {
  return {
    id: null,
    project_id: projectId,
    provider_name: provider.provider_name,
    provider_key: provider.provider_key,
    model_name: provider.default_model === "configurable" ? provider.available_models[0] : provider.default_model,
    is_enabled: false,
    is_primary: false,
    is_fallback: false,
    fallback_priority: null,
    temperature: 0.2,
    max_tokens: 4000,
    timeout_seconds: 120,
    module_scope: [],
    llm_role: llmRole,
    config_status: "disabled",
  };
}

function statusFor(provider: ProviderMeta, setting: ProjectLLMSetting) {
  if (provider.api_key_required && !provider.api_key_configured) return "Missing API Key";
  if (setting.is_enabled && setting.is_primary) return "Active";
  if (setting.is_enabled && setting.is_fallback) return "Fallback";
  if (setting.is_enabled) return "Enabled";
  return "Disabled";
}

function statusVariant(status: string): "success" | "warning" | "secondary" | "info" {
  if (status === "Active" || status === "Enabled") return "success";
  if (status === "Missing API Key" || status === "Fallback") return "warning";
  if (status === "Disabled") return "secondary";
  return "info";
}

function Toggle({ checked, disabled, onChange }: { checked: boolean; disabled?: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onChange}
      className={cn(
        "relative h-7 w-12 rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "border-emerald-500 bg-emerald-500" : "border-slate-300 bg-slate-200"
      )}
      aria-pressed={checked}
    >
      <span
        className={cn(
          "absolute top-0.5 h-6 w-6 rounded-full bg-white shadow-sm transition-transform",
          checked ? "translate-x-5" : "translate-x-0.5"
        )}
      />
    </button>
  );
}

export function LLMProvidersTab({ projectId }: { projectId: number }) {
  const [data, setData] = useState<ProjectLLMSettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedRowKey, setSelectedRowKey] = useState<string | null>(null);
  const [configuring, setConfiguring] = useState<ProjectLLMSetting | null>(null);
  const [toast, setToast] = useState<ToastState>(null);
  const [confirmActive, setConfirmActive] = useState<ProjectLLMSetting | null>(null);

  function rowKey(providerKey: string, llmRole: LLMRole | null) {
    return `${providerKey}::${llmRole ?? ""}`;
  }

  useEffect(() => {
    setLoading(true);
    api.get<ProjectLLMSettingsResponse>(`/projects/${projectId}/llm-settings`)
      .then((response) => {
        setData(response.data);
        const active = response.data.active_provider?.provider_key;
        const key = active || response.data.settings[0]?.provider_key || response.data.providers[0]?.provider_key || null;
        setSelectedRowKey(key ? rowKey(key, null) : null);
      })
      .catch(() => setError("Could not load project LLM settings."))
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), 4200);
    return () => window.clearTimeout(id);
  }, [toast]);

  // One row per provider (generic, llm_role=null) plus one extra row for
  // each role that provider has an explicit override configured for — so a
  // project with no role routing still sees exactly the original 1-row-per-
  // provider list, and role-specific rows only appear once someone adds one.
  const rows = useMemo(() => {
    if (!data) return [];
    const byKey = new Map(data.settings.map((setting) => [rowKey(setting.provider_key, setting.llm_role), setting]));
    const result: { provider: ProviderMeta; setting: ProjectLLMSetting }[] = [];
    for (const provider of data.providers) {
      result.push({
        provider,
        setting: byKey.get(rowKey(provider.provider_key, null)) || emptySetting(data.project_id, provider),
      });
      for (const role of LLM_ROLES) {
        const existing = byKey.get(rowKey(provider.provider_key, role));
        if (existing) result.push({ provider, setting: existing });
      }
    }
    return result;
  }, [data]);

  const activeCount = rows.filter(({ setting }) => setting.is_enabled && setting.is_primary).length;
  const enabledCount = rows.filter(({ setting }) => setting.is_enabled && !setting.is_primary).length;
  const selectedRow = rows.find(({ provider, setting }) => rowKey(provider.provider_key, setting.llm_role) === selectedRowKey);

  function showToast(next: ToastState) {
    setToast(next);
  }

  function allSettingsWith(original: ProjectLLMSetting, updated: ProjectLLMSetting) {
    return rows.map(({ setting }) => {
      if (setting === original) return updated;
      if (updated.is_primary && (setting.llm_role ?? null) === (updated.llm_role ?? null)) {
        return { ...setting, is_primary: false, config_status: setting.is_enabled ? "enabled" : "disabled" };
      }
      return setting;
    });
  }

  async function persist(original: ProjectLLMSetting, updated: ProjectLLMSetting, reason: string) {
    if (!data) return;
    setSaving(true);
    try {
      const response = await api.put<ProjectLLMSettingsResponse>(`/projects/${projectId}/llm-settings`, {
        settings: allSettingsWith(original, updated).map((setting) => ({
          provider_key: setting.provider_key,
          model_name: setting.model_name,
          is_enabled: setting.is_enabled,
          is_primary: setting.is_primary,
          is_fallback: setting.is_fallback,
          fallback_priority: setting.fallback_priority,
          temperature: setting.temperature,
          max_tokens: setting.max_tokens,
          timeout_seconds: setting.timeout_seconds,
          module_scope: setting.module_scope,
          llm_role: setting.llm_role,
        })),
        change_reason: reason,
      });
      setData(response.data);
      setConfiguring(null);
      showToast({ kind: "success", title: "Settings saved successfully", message: "LLM provider configuration updated." });
    } catch (err: any) {
      const message = err?.response?.data?.detail || "LLM provider configuration could not be saved.";
      showToast({ kind: "error", title: "Configuration not saved", message });
    } finally {
      setSaving(false);
    }
  }

  function toggleProvider(provider: ProviderMeta, setting: ProjectLLMSetting) {
    if (!setting.is_enabled && provider.api_key_required && !provider.api_key_configured) {
      showToast({ kind: "error", title: "Missing API key", message: "Missing API key for selected provider." });
      return;
    }
    if (setting.is_enabled && setting.is_primary) {
      const confirmed = window.confirm("The active provider will be disabled and this project will fall back to the system default until another active provider is selected. Do you want to continue?");
      if (!confirmed) return;
    }
    const next = {
      ...setting,
      is_enabled: !setting.is_enabled,
      is_primary: setting.is_enabled ? false : setting.is_primary,
      is_fallback: setting.is_enabled ? false : setting.is_fallback,
      fallback_priority: setting.is_enabled ? null : setting.fallback_priority,
    };
    persist(setting, next, next.is_enabled ? "Provider enabled from settings UI" : "Provider disabled from settings UI");
  }

  async function testConnection(setting: ProjectLLMSetting) {
    try {
      const response = await api.post(`/projects/${projectId}/llm-settings/test`, {
        provider_key: setting.provider_key,
        model_name: setting.model_name,
      });
      showToast({
        kind: response.data.success ? "success" : "error",
        title: response.data.success ? "Connection successful" : "Connection failed",
        message: response.data.message,
      });
    } catch (err: any) {
      const message = err?.response?.data?.detail || "Provider connection test failed.";
      showToast({ kind: "error", title: "Connection failed", message });
    }
  }

  function setActiveProvider(setting: ProjectLLMSetting) {
    const provider = rows.find((row) => row.setting.provider_key === setting.provider_key)?.provider;
    if (provider?.api_key_required && !provider.api_key_configured) {
      showToast({ kind: "error", title: "Missing API key", message: "Missing API key for selected provider." });
      return;
    }
    if (!setting.is_enabled) {
      showToast({ kind: "error", title: "Enable provider first", message: "Enable the provider before making it active." });
      return;
    }
    setConfirmActive(setting);
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-slate-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#1b59f8]" />
        <span className="text-sm font-semibold">Loading project settings...</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-sm font-semibold text-rose-700">
        {error || "Project settings are unavailable."}
      </div>
    );
  }

  const fallbackText = data.fallback_order.length
    ? data.fallback_order.map((item, index) => `${index + 1}. ${item.provider_name}`).join(" -> ")
    : "System default only";

  return (
    <>
      <section className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-4 border-b border-slate-100 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-blue-100 bg-blue-50">
              <Bot className="h-5 w-5 text-[#1b59f8]" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900">LLM Providers</h2>
              <p className="mt-1 text-sm text-slate-500">Configure and manage which LLM providers are available for this project.</p>
            </div>
          </div>
          <Button variant="outline" size="sm" className="self-start">
            <Activity className="h-4 w-4" />
            LLM Usage & Analytics
          </Button>
        </div>

        <div className="p-5">
          <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50/70 px-4 py-3 text-sm text-blue-800">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-[#1b59f8]" />
            <p className="leading-6">
              Enable one or more LLM providers for this project. The selected primary provider will be used by AI features across requirements, test planning, test case generation, execution, defect triage, and reporting.
            </p>
          </div>

          <div className="mt-5 overflow-hidden rounded-xl border border-slate-200">
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/60 px-4 py-3">
              <h3 className="text-sm font-bold text-slate-900">Available Providers</h3>
              <p className="text-xs font-bold text-slate-600">
                <span className="text-emerald-600">{activeCount} Active</span> &bull; {enabledCount} Enabled
              </p>
            </div>

            <div className="divide-y divide-slate-100">
              {rows.map(({ provider, setting }) => {
                const status = statusFor(provider, setting);
                const key = rowKey(provider.provider_key, setting.llm_role);
                const selected = selectedRowKey === key;
                return (
                  <div
                    key={key}
                    onClick={() => setSelectedRowKey(key)}
                    className={cn(
                      "grid cursor-pointer grid-cols-1 gap-4 px-4 py-4 transition-colors xl:grid-cols-[64px_minmax(0,1fr)_auto]",
                      selected ? "bg-blue-50/35" : "bg-white hover:bg-slate-50/60"
                    )}
                  >
                    <div className="flex h-14 w-14 items-center justify-center rounded-xl border border-slate-200 bg-white shadow-sm">
                      {providerIcon(provider.logo_icon)}
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="font-bold text-slate-900">{provider.provider_name}</h4>
                        {setting.llm_role && <Badge variant="info" className="text-[10px]">{ROLE_LABELS[setting.llm_role]}</Badge>}
                        {setting.is_primary && <Badge variant="success" className="text-[10px]">Active</Badge>}
                      </div>
                      <p className="mt-1 text-sm leading-6 text-slate-500">{provider.description}</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {provider.available_models.map((model) => (
                          <span key={model} className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-slate-600">
                            {model}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-3 xl:justify-end">
                      <Toggle
                        checked={setting.is_enabled}
                        disabled={!provider.enabled_for_selection}
                        onChange={() => toggleProvider(provider, setting)}
                      />
                      <Badge variant={statusVariant(status)} className="min-w-[86px] justify-center text-[11px]">
                        {status}
                      </Badge>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={!setting.is_enabled}
                        onClick={(event) => {
                          event.stopPropagation();
                          setConfiguring(setting);
                        }}
                      >
                        <Settings className="h-3.5 w-3.5" />
                        Configure
                      </Button>
                      <button className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-white" type="button">
                        <ChevronDown className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mt-4 flex flex-col gap-3 rounded-lg border border-blue-100 bg-blue-50/40 px-4 py-3 text-sm text-slate-700 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-2">
              <Info className="mt-0.5 h-4 w-4 text-[#1b59f8]" />
              <p>Tip: You can enable multiple providers. The active provider is used by default, and enabled providers can be used as fallbacks.</p>
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={!selectedRow?.setting.is_enabled}
              onClick={() => selectedRow && setActiveProvider(selectedRow.setting)}
            >
              <TestTube2 className="h-4 w-4" />
              Set Active Provider
            </Button>
          </div>

          <div className="mt-5 rounded-xl border border-slate-200">
            <div className="border-b border-slate-100 px-4 py-3">
              <h3 className="font-bold text-slate-900">Role Routing</h3>
              <p className="mt-1 text-xs text-slate-500">Which provider and model each AI role uses for this project.</p>
            </div>
            <div className="grid gap-3 p-4 sm:grid-cols-3">
              {LLM_ROLES.map((role) => {
                const route = data.active_by_role?.[role] ?? data.role_defaults?.[role];
                const isOverride = route?.source === "project" || route?.source === "project_fallback";
                return (
                  <div key={role} className="rounded-lg border border-slate-200 p-3">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-bold uppercase tracking-wide text-slate-400">{ROLE_LABELS[role]}</p>
                      <Badge variant={isOverride ? "success" : "secondary"} className="text-[10px]">
                        {isOverride ? "Project override" : "System default"}
                      </Badge>
                    </div>
                    <p className="mt-2 text-sm font-semibold text-slate-800">{route?.provider_name || route?.provider_key || "—"}</p>
                    <p className="font-mono text-xs text-slate-500">{route?.model_name || "—"}</p>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mt-5 rounded-xl border border-slate-200">
            <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
              <h3 className="font-bold text-slate-900">Project LLM Settings Summary</h3>
              <Badge variant="success" className="text-[10px]">{data.security_status}</Badge>
            </div>
            <div className="grid gap-4 p-4 md:grid-cols-3">
              <SummaryItem icon={<Sparkles className="h-4 w-4 text-amber-500" />} label="Active Provider" value={data.active_provider?.provider_name || `System default (${data.system_default_provider})`} />
              <SummaryItem icon={<Bot className="h-4 w-4 text-[#1b59f8]" />} label="Active Model" value={data.active_model || data.system_default_model} />
              <SummaryItem icon={<Route className="h-4 w-4 text-violet-600" />} label="Fallback Order" value={fallbackText} />
              <SummaryItem icon={<Activity className="h-4 w-4 text-slate-500" />} label="Last Updated" value={data.last_updated ? new Date(data.last_updated).toLocaleString() : "Not configured"} />
              <SummaryItem icon={<Users className="h-4 w-4 text-slate-500" />} label="Updated By" value={data.updated_by ? `User #${data.updated_by}` : "System default"} />
              <SummaryItem icon={<ShieldCheck className="h-4 w-4 text-emerald-600" />} label="Security" value="Secure" />
            </div>
            <div className="mx-4 mb-4 flex items-start gap-3 rounded-lg border border-violet-200 bg-violet-50 px-4 py-3 text-sm text-violet-800">
              <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0" />
              <p>Project-specific settings are stored securely in the database and not in .env files. API keys remain server-side and are never exposed to the browser.</p>
            </div>
          </div>
        </div>
      </section>

      {configuring && (
        <ConfigureModal
          setting={configuring}
          provider={rows.find((row) => row.setting.provider_key === configuring.provider_key)?.provider}
          saving={saving}
          onClose={() => setConfiguring(null)}
          onTest={testConnection}
          onSave={(next) => persist(configuring, next, "Provider configured from settings UI")}
        />
      )}

      {confirmActive && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
            <h3 className="text-lg font-bold text-slate-900">Change active LLM provider?</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Changing the active LLM provider will affect AI generation for this project. Do you want to continue?
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setConfirmActive(null)}>Cancel</Button>
              <Button
                size="sm"
                onClick={() => {
                  const next = { ...confirmActive, is_enabled: true, is_primary: true, is_fallback: false, fallback_priority: null };
                  setConfirmActive(null);
                  persist(confirmActive, next, "Active provider changed from settings UI");
                }}
              >
                Continue
              </Button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-5 right-5 z-50 w-[360px] max-w-[calc(100vw-2rem)] rounded-xl border border-slate-200 bg-white p-4 shadow-xl">
          <div className="flex gap-3">
            {toast.kind === "success" ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : toast.kind === "error" ? <XCircle className="h-5 w-5 text-rose-600" /> : <Info className="h-5 w-5 text-[#1b59f8]" />}
            <div className="min-w-0 flex-1">
              <p className="font-bold text-slate-900">{toast.title}</p>
              <p className="mt-1 text-sm text-slate-600">{toast.message}</p>
            </div>
            <button type="button" onClick={() => setToast(null)} className="text-slate-400 hover:text-slate-700">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function SummaryItem({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <div className="mt-0.5">{icon}</div>
      <div className="min-w-0">
        <p className="text-xs font-bold uppercase tracking-wide text-slate-400">{label}</p>
        <p className="mt-1 text-sm font-semibold leading-6 text-slate-800">{value}</p>
      </div>
    </div>
  );
}

function ConfigureModal({
  setting,
  provider,
  saving,
  onClose,
  onSave,
  onTest,
}: {
  setting: ProjectLLMSetting;
  provider?: ProviderMeta;
  saving: boolean;
  onClose: () => void;
  onSave: (setting: ProjectLLMSetting) => void;
  onTest: (setting: ProjectLLMSetting) => void;
}) {
  const [draft, setDraft] = useState<ProjectLLMSetting>(setting);
  const models = provider?.available_models || [draft.model_name];
  const configurable = models.includes("configurable");

  function updateScope(scope: string) {
    const exists = draft.module_scope.includes(scope);
    setDraft({
      ...draft,
      module_scope: exists ? draft.module_scope.filter((item) => item !== scope) : [...draft.module_scope, scope],
    });
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4">
      <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white shadow-xl">
        <div className="flex items-start justify-between border-b border-slate-100 p-5">
          <div>
            <h3 className="text-lg font-bold text-slate-900">Configure {draft.provider_name}</h3>
            <p className="mt-1 text-sm text-slate-500">Tune model parameters, fallback priority, and module scope.</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-slate-50 hover:text-slate-700">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-5 p-5">
          <label className="block space-y-2 text-sm font-semibold text-slate-700">
            Applies To Role
            <select
              value={draft.llm_role ?? ""}
              onChange={(event) => setDraft({ ...draft, llm_role: (event.target.value || null) as LLMRole | null })}
              className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:ring-2 focus:ring-blue-100"
            >
              <option value="">All roles (default)</option>
              <option value="coding">Coding — test case & automation script generation</option>
              <option value="vision">Vision — screenshots, OCR, PDFs, UI analysis</option>
              <option value="reasoning">Reasoning — planning, agents, review, chat, reporting</option>
            </select>
          </label>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2 text-sm font-semibold text-slate-700">
              Model
              {configurable ? (
                <input
                  value={draft.model_name}
                  onChange={(event) => setDraft({ ...draft, model_name: event.target.value })}
                  className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:ring-2 focus:ring-blue-100"
                  placeholder="provider/model-name"
                />
              ) : (
                <select
                  value={draft.model_name}
                  onChange={(event) => setDraft({ ...draft, model_name: event.target.value })}
                  className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:ring-2 focus:ring-blue-100"
                >
                  {models.map((model) => <option key={model} value={model}>{model}</option>)}
                </select>
              )}
            </label>
            <label className="space-y-2 text-sm font-semibold text-slate-700">
              Fallback Priority
              <input
                type="number"
                min={1}
                value={draft.fallback_priority ?? ""}
                onChange={(event) => setDraft({ ...draft, fallback_priority: event.target.value ? Number(event.target.value) : null, is_fallback: Boolean(event.target.value) })}
                className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:ring-2 focus:ring-blue-100"
                placeholder="1"
              />
            </label>
            <label className="space-y-2 text-sm font-semibold text-slate-700">
              Temperature
              <input
                type="number"
                step="0.1"
                min={0}
                max={2}
                value={draft.temperature}
                onChange={(event) => setDraft({ ...draft, temperature: Number(event.target.value) })}
                className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:ring-2 focus:ring-blue-100"
              />
            </label>
            <label className="space-y-2 text-sm font-semibold text-slate-700">
              Max Tokens
              <input
                type="number"
                min={128}
                value={draft.max_tokens}
                onChange={(event) => setDraft({ ...draft, max_tokens: Number(event.target.value) })}
                className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:ring-2 focus:ring-blue-100"
              />
            </label>
            <label className="space-y-2 text-sm font-semibold text-slate-700">
              Timeout Seconds
              <input
                type="number"
                min={5}
                value={draft.timeout_seconds}
                onChange={(event) => setDraft({ ...draft, timeout_seconds: Number(event.target.value) })}
                className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:ring-2 focus:ring-blue-100"
              />
            </label>
            <label className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700">
              <input
                type="checkbox"
                checked={draft.is_fallback}
                onChange={(event) => setDraft({ ...draft, is_fallback: event.target.checked, fallback_priority: event.target.checked ? draft.fallback_priority || 1 : null })}
              />
              Use as fallback provider
            </label>
          </div>

          <div>
            <p className="text-sm font-bold text-slate-800">Module Scope</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {MODULE_SCOPES.map((scope) => (
                <label key={scope} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700">
                  <input type="checkbox" checked={draft.module_scope.includes(scope)} onChange={() => updateScope(scope)} />
                  {scope}
                </label>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-blue-100 bg-blue-50/60 p-3 text-sm text-blue-800">
            <div className="flex gap-2">
              <KeyRound className="mt-0.5 h-4 w-4" />
              <p>No API keys are shown or edited here. Key presence is validated server-side only.</p>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-2 border-t border-slate-100 p-5 sm:flex-row sm:justify-between">
          <Button variant="outline" size="sm" onClick={() => onTest(draft)}>
            <Globe2 className="h-4 w-4" />
            Test Connection
          </Button>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
            <Button size="sm" disabled={saving} onClick={() => onSave({ ...draft, is_enabled: true })}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Save Configuration
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
