"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Activity,
  Bell,
  Bot,
  Database,
  FileSliders,
  Globe2,
  Loader2,
  Network,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  Webhook,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { LLMProvidersTab } from "@/components/settings/LLMProvidersTab";
import { ApplicationsTab } from "@/components/settings/ApplicationsTab";

const settingsNav = [
  { label: "General", icon: Settings },
  { label: "Team & Access", icon: Users },
  { label: "Integrations", icon: Network },
  { label: "LLM Providers", icon: Bot },
  { label: "Applications & Environments", icon: Globe2 },
  { label: "AI Preferences", icon: SlidersHorizontal },
  { label: "Webhooks", icon: Webhook },
  { label: "Custom Fields", icon: FileSliders },
  { label: "Notifications", icon: Bell },
  { label: "Data & Storage", icon: Database },
  { label: "Audit Logs", icon: Activity },
] as const;

// Only these tabs have real content today; the rest are placeholders.
const IMPLEMENTED_TABS = new Set(["LLM Providers", "Applications & Environments"]);

function SettingsContent() {
  const searchParams = useSearchParams();
  const projectId = Number(searchParams.get("project") || 8);
  const [activeTab, setActiveTab] = useState<string>("LLM Providers");

  return (
    <div className="mx-auto flex max-w-7xl gap-6 pb-8">
      <aside className="hidden w-80 shrink-0 lg:block">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="px-1 pb-4">
            <h1 className="text-lg font-bold text-slate-900">Project Settings</h1>
            <p className="mt-2 text-sm leading-6 text-slate-500">Manage all configurations and integrations for this project.</p>
          </div>
          <nav className="space-y-1">
            {settingsNav.map((item) => {
              const active = item.label === activeTab;
              return (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => setActiveTab(item.label)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-semibold transition-colors",
                    active ? "bg-blue-50 text-[#1b59f8]" : "text-slate-600 hover:bg-slate-50"
                  )}
                >
                  <item.icon className={cn("h-4 w-4", active ? "text-[#1b59f8]" : "text-slate-400")} />
                  <span className="flex-1">{item.label}</span>
                  {active && <Badge variant="info" className="text-[10px]">Active</Badge>}
                </button>
              );
            })}
          </nav>
          <div className="mt-6 rounded-lg border border-emerald-100 bg-emerald-50/60 p-3">
            <div className="flex gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 text-emerald-600" />
              <div>
                <p className="text-xs font-bold text-slate-800">Changes are saved per project</p>
                <p className="mt-1 text-xs leading-5 text-slate-600">These settings apply only to the current project.</p>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        {activeTab === "LLM Providers" && <LLMProvidersTab projectId={projectId} />}
        {activeTab === "Applications & Environments" && <ApplicationsTab projectId={projectId} />}
        {!IMPLEMENTED_TABS.has(activeTab) && (
          <div className="rounded-xl border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-400">
            {activeTab} settings are not available yet.
          </div>
        )}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-sm font-semibold text-slate-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#1b59f8]" />
        Loading settings...
      </div>
    }>
      <SettingsContent />
    </Suspense>
  );
}
