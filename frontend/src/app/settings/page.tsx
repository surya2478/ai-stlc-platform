"use client";
import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import {
  Settings, CheckCircle, XCircle, Cpu, ExternalLink,
  Database, Key, Globe, Upload, Bot, Info,
} from "lucide-react";

interface AppSettings {
  app_name: string;
  app_version: string;
  app_env: string;
  llm_provider: string;
  llm_model: string;
  ollama_base_url: string;
  openai_base_url: string;
  openai_model: string;
  openai_key_configured: boolean;
  jira_base_url: string;
  jira_email: string;
  jira_project_key: string;
  jira_configured: boolean;
  max_upload_size_mb: number;
  file_storage_path: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
      ok ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"
    }`}>
      {ok ? <CheckCircle size={12} /> : <XCircle size={12} />}
      {label}
    </span>
  );
}

function ConfigRow({ label, value, sensitive = false, mono = false }: {
  label: string; value: string; sensitive?: boolean; mono?: boolean;
}) {
  const display = sensitive && value ? "••••••••" : (value || "Not configured");
  const isEmpty = !value;
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-gray-50 last:border-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span className={`text-sm ${mono ? "font-mono" : ""} ${isEmpty ? "text-gray-300 italic" : "text-gray-800"}`}>
        {display}
      </span>
    </div>
  );
}

function SectionCard({ title, icon: Icon, iconClass, children, badge }: {
  title: string;
  icon: React.ElementType;
  iconClass: string;
  children: React.ReactNode;
  badge?: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-100">
        <div className={`p-1.5 rounded-lg ${iconClass.includes("indigo") ? "bg-indigo-50" : iconClass.includes("violet") ? "bg-violet-50" : iconClass.includes("blue") ? "bg-blue-50" : iconClass.includes("orange") ? "bg-orange-50" : "bg-gray-50"}`}>
          <Icon size={16} className={iconClass} />
        </div>
        <h2 className="font-semibold text-gray-800 text-sm">{title}</h2>
        {badge && <div className="ml-auto">{badge}</div>}
      </div>
      <div className="px-5 py-1">{children}</div>
    </div>
  );
}

function EnvBadge({ env }: { env: string }) {
  const map: Record<string, string> = {
    local: "bg-blue-100 text-blue-700",
    staging: "bg-yellow-100 text-yellow-700",
    production: "bg-red-100 text-red-700",
  };
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${map[env] ?? "bg-gray-100 text-gray-600"}`}>
      {env}
    </span>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const [config, setConfig] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<AppSettings>("/settings/")
      .then(r => setConfig(r.data))
      .catch(() => setError("Could not load settings — backend may be offline"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <span className="animate-spin w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error || !config) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <div className="bg-red-50 border border-red-200 rounded-xl p-5 flex items-start gap-3">
          <XCircle size={20} className="text-red-500 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-red-700">Settings unavailable</p>
            <p className="text-sm text-red-600 mt-1">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-2 bg-gray-100 rounded-lg">
          <Settings size={22} className="text-gray-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
          <p className="text-sm text-gray-500">Platform configuration — edit via <code className="bg-gray-100 px-1 rounded">.env</code> file and restart services</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <EnvBadge env={config.app_env} />
          <span className="text-xs text-gray-400">v{config.app_version}</span>
        </div>
      </div>

      {/* Info banner */}
      <div className="flex items-start gap-3 bg-blue-50 border border-blue-100 rounded-xl px-4 py-3">
        <Info size={16} className="text-blue-500 shrink-0 mt-0.5" />
        <p className="text-sm text-blue-700">
          Settings are read from the <strong>.env</strong> file in the project root.
          After editing, run <code className="bg-blue-100 px-1 rounded text-xs">docker compose restart backend worker</code> to apply changes.
        </p>
      </div>

      {/* LLM Provider */}
      <SectionCard
        title="LLM Provider"
        icon={Cpu}
        iconClass="text-indigo-600"
        badge={
          <StatusPill
            ok={config.llm_provider === "ollama" || config.openai_key_configured}
            label={config.llm_provider === "ollama" ? "Ollama (local)" : config.openai_key_configured ? "OpenAI connected" : "OpenAI key missing"}
          />
        }
      >
        <ConfigRow label="Active provider" value={config.llm_provider} mono />
        <ConfigRow label="Active model" value={config.llm_model} mono />
        {config.llm_provider === "ollama" ? (
          <ConfigRow label="Ollama base URL" value={config.ollama_base_url} mono />
        ) : (
          <>
            <ConfigRow label="OpenAI base URL" value={config.openai_base_url} mono />
            <ConfigRow label="OpenAI model" value={config.openai_model} mono />
            <ConfigRow label="OpenAI API key" value={config.openai_key_configured ? "configured" : ""} sensitive />
          </>
        )}
        <div className="py-3">
          <p className="text-xs text-gray-400 mb-2">Switch provider in <code className="bg-gray-100 px-1 rounded">.env</code>:</p>
          <div className="grid grid-cols-2 gap-2">
            <div className={`rounded-lg border p-3 text-xs ${config.llm_provider === "ollama" ? "border-indigo-300 bg-indigo-50" : "border-gray-200"}`}>
              <p className="font-semibold text-gray-700 mb-1">🦙 Ollama (local)</p>
              <code className="text-gray-500 block">DEFAULT_LLM_PROVIDER=ollama</code>
              <code className="text-gray-500 block">DEFAULT_LLM_MODEL=llama3.1</code>
            </div>
            <div className={`rounded-lg border p-3 text-xs ${config.llm_provider === "openai" ? "border-indigo-300 bg-indigo-50" : "border-gray-200"}`}>
              <p className="font-semibold text-gray-700 mb-1">🤖 OpenAI</p>
              <code className="text-gray-500 block">DEFAULT_LLM_PROVIDER=openai</code>
              <code className="text-gray-500 block">OPENAI_API_KEY=sk-...</code>
            </div>
          </div>
        </div>
      </SectionCard>

      {/* Jira Integration */}
      <SectionCard
        title="Jira Integration"
        icon={ExternalLink}
        iconClass="text-blue-600"
        badge={<StatusPill ok={config.jira_configured} label={config.jira_configured ? "Connected" : "Not configured"} />}
      >
        <ConfigRow label="Jira base URL" value={config.jira_base_url} />
        <ConfigRow label="Email" value={config.jira_email} />
        <ConfigRow label="Project key" value={config.jira_project_key} mono />
        <ConfigRow label="API token" value={config.jira_configured ? "configured" : ""} sensitive />
        {!config.jira_configured && (
          <div className="py-3">
            <p className="text-xs text-gray-400 mb-1">Add to <code className="bg-gray-100 px-1 rounded">.env</code> to enable Jira push:</p>
            <div className="bg-gray-900 rounded-lg p-3 font-mono text-xs text-green-300 space-y-0.5">
              <p>JIRA_BASE_URL=https://yourorg.atlassian.net</p>
              <p>JIRA_EMAIL=you@yourorg.com</p>
              <p>JIRA_API_TOKEN=your-api-token</p>
              <p>JIRA_PROJECT_KEY=QA</p>
            </div>
          </div>
        )}
      </SectionCard>

      {/* File Storage */}
      <SectionCard title="File Storage" icon={Upload} iconClass="text-violet-600">
        <ConfigRow label="Storage path" value={config.file_storage_path} mono />
        <ConfigRow label="Max upload size" value={`${config.max_upload_size_mb} MB`} />
      </SectionCard>

      {/* Agent Pipeline */}
      <SectionCard title="Agent Pipeline" icon={Bot} iconClass="text-orange-600">
        <div className="py-2 space-y-2">
          {[
            { num: 1,  name: "Requirement Intake",   status: "active" },
            { num: 2,  name: "Quality Analysis",     status: "active" },
            { num: 3,  name: "Test Planning",        status: "active" },
            { num: 4,  name: "Test Scenarios",       status: "active" },
            { num: 5,  name: "Test Cases",           status: "active" },
            { num: 6,  name: "Test Data",            status: "planned" },
            { num: 7,  name: "Automation Scripts",   status: "active" },
            { num: 8,  name: "Test Execution",       status: "active" },
            { num: 9,  name: "Defect Analysis",      status: "active" },
            { num: 10, name: "Jira Defect Push",     status: config.jira_configured ? "active" : "needs_config" },
            { num: 11, name: "QA Reporting",         status: "active" },
          ].map(a => (
            <div key={a.num} className="flex items-center gap-3 py-1">
              <span className="text-xs font-mono text-gray-400 w-6">#{a.num}</span>
              <span className="text-sm text-gray-700 flex-1">{a.name}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                a.status === "active" ? "bg-green-100 text-green-600" :
                a.status === "needs_config" ? "bg-yellow-100 text-yellow-600" :
                "bg-gray-100 text-gray-400"
              }`}>
                {a.status === "active" ? "Active" : a.status === "needs_config" ? "Needs config" : "Planned"}
              </span>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
