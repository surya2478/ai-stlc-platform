"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Globe2, Info, Loader2, Plus, Save, Shield, Trash2, X, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type ProjectApplication = {
  id?: number | null;
  key: string;
  name: string;
  description?: string | null;
  is_default: boolean;
  environment_urls: Record<string, string>;
  is_active: boolean;
};

type ProjectExternalDependency = {
  id?: number | null;
  application_id?: number | null;
  service_name: string;
  note?: string | null;
  sandbox_url?: string | null;
  mock_strategy: "intercept" | "sandbox" | "ignore";
  is_active: boolean;
};

type ProjectApplicationsResponse = {
  project_id: number;
  applications: ProjectApplication[];
  external_dependencies: ProjectExternalDependency[];
  available_environments: string[];
  last_updated: string | null;
  updated_by: number | null;
};

type ToastState = { title: string; message: string; kind: "success" | "error" } | null;

function slugify(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function emptyApplication(): ProjectApplication {
  return { key: "", name: "", description: "", is_default: false, environment_urls: {}, is_active: true };
}

function emptyDependency(): ProjectExternalDependency {
  return { service_name: "", note: "", sandbox_url: "", mock_strategy: "intercept", is_active: true };
}

export function ApplicationsTab({ projectId }: { projectId: number }) {
  const [data, setData] = useState<ProjectApplicationsResponse | null>(null);
  const [apps, setApps] = useState<ProjectApplication[]>([]);
  const [deps, setDeps] = useState<ProjectExternalDependency[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingApps, setSavingApps] = useState(false);
  const [savingDeps, setSavingDeps] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState>(null);

  function load() {
    setLoading(true);
    api.get<ProjectApplicationsResponse>(`/projects/${projectId}/applications`)
      .then((response) => {
        setData(response.data);
        setApps(response.data.applications);
        setDeps(response.data.external_dependencies);
      })
      .catch(() => setError("Could not load applications for this project."))
      .finally(() => setLoading(false));
  }

  useEffect(load, [projectId]);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), 4200);
    return () => window.clearTimeout(id);
  }, [toast]);

  function updateApp(index: number, patch: Partial<ProjectApplication>) {
    setApps((prev) => prev.map((app, i) => (i === index ? { ...app, ...patch } : app)));
  }

  function addApp() {
    setApps((prev) => [...prev, emptyApplication()]);
  }

  function removeApp(index: number) {
    setApps((prev) => prev.filter((_, i) => i !== index));
  }

  function setEnvUrl(index: number, env: string, url: string) {
    setApps((prev) =>
      prev.map((app, i) => (i === index ? { ...app, environment_urls: { ...app.environment_urls, [env]: url } } : app))
    );
  }

  function removeEnv(index: number, env: string) {
    setApps((prev) =>
      prev.map((app, i) => {
        if (i !== index) return app;
        const next = { ...app.environment_urls };
        delete next[env];
        return { ...app, environment_urls: next };
      })
    );
  }

  function addEnvRow(index: number) {
    const env = window.prompt("Environment name (e.g. SIT, QA-Staging):");
    if (!env || !env.trim()) return;
    setEnvUrl(index, env.trim(), "");
  }

  async function saveApplications() {
    setSavingApps(true);
    try {
      const payload = {
        applications: apps.map((app) => ({
          key: app.key || slugify(app.name),
          name: app.name,
          description: app.description || null,
          is_default: app.is_default,
          environment_urls: app.environment_urls,
          is_active: app.is_active,
        })),
        change_reason: "Updated from Project Settings > Applications",
      };
      const response = await api.put<ProjectApplicationsResponse>(`/projects/${projectId}/applications`, payload);
      setData(response.data);
      setApps(response.data.applications);
      setToast({ kind: "success", title: "Applications saved", message: "Application URLs are now available to script generation." });
    } catch (err: any) {
      const message = err?.response?.data?.detail || "Could not save applications.";
      setToast({ kind: "error", title: "Save failed", message: typeof message === "string" ? message : "Could not save applications." });
    } finally {
      setSavingApps(false);
    }
  }

  function updateDep(index: number, patch: Partial<ProjectExternalDependency>) {
    setDeps((prev) => prev.map((dep, i) => (i === index ? { ...dep, ...patch } : dep)));
  }

  function addDep() {
    setDeps((prev) => [...prev, emptyDependency()]);
  }

  function removeDep(index: number) {
    setDeps((prev) => prev.filter((_, i) => i !== index));
  }

  async function saveDependencies() {
    setSavingDeps(true);
    try {
      const payload = {
        dependencies: deps.map((dep) => ({
          id: dep.id ?? null,
          application_id: dep.application_id ?? null,
          service_name: dep.service_name,
          note: dep.note || null,
          sandbox_url: dep.sandbox_url || null,
          mock_strategy: dep.mock_strategy,
          is_active: dep.is_active,
        })),
        change_reason: "Updated from Project Settings > Applications",
      };
      const response = await api.put<ProjectApplicationsResponse>(`/projects/${projectId}/external-dependencies`, payload);
      setData(response.data);
      setDeps(response.data.external_dependencies);
      setToast({ kind: "success", title: "External dependencies saved", message: "Generated scripts will mock these services instead of calling them live." });
    } catch (err: any) {
      const message = err?.response?.data?.detail || "Could not save external dependencies.";
      setToast({ kind: "error", title: "Save failed", message: typeof message === "string" ? message : "Could not save external dependencies." });
    } finally {
      setSavingDeps(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-gray-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#B71920]" />
        <span className="text-sm font-semibold">Loading applications...</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-sm font-semibold text-rose-700">
        {error || "Applications are unavailable."}
      </div>
    );
  }

  return (
    <>
      <section className="min-w-0 flex-1 rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="flex flex-col gap-4 border-b border-gray-100 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-app-brand-100 bg-app-brand-75">
              <Globe2 className="h-5 w-5 text-[#B71920]" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900">Applications & Environments</h2>
              <p className="mt-1 text-sm text-gray-500">
                Real URLs per application/channel, so AI-generated automation scripts use your app instead of a placeholder domain.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <a
              href={`/applications?project=${projectId}`}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 text-xs font-bold text-[#B71920] hover:bg-gray-50"
            >
              Open full Application Registry →
            </a>
            <Button size="sm" disabled={savingApps} onClick={saveApplications}>
              {savingApps ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Save Applications
            </Button>
          </div>
        </div>

        <div className="p-5 space-y-4">
          <div className="flex items-start gap-3 rounded-lg border border-app-brand-200 bg-app-brand-75/70 px-4 py-3 text-sm text-app-brand-800">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-[#B71920]" />
            <p className="leading-6">
              Define each application/channel under test (e.g. Web App, Mobile API, Admin Portal) with its base URL per environment. Mark exactly one as default — untagged test cases resolve to it.
            </p>
          </div>

          {apps.length === 0 && (
            <p className="rounded-lg border border-dashed border-gray-200 px-4 py-6 text-center text-sm text-gray-400">
              No applications configured yet.
            </p>
          )}

          <div className="space-y-3">
            {apps.map((app, index) => (
              <div key={app.id ?? `new-${index}`} className="rounded-xl border border-gray-200 p-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <label className="space-y-1 text-xs font-semibold text-gray-600">
                    Name
                    <input
                      value={app.name}
                      onChange={(e) => updateApp(index, { name: e.target.value, key: app.key || slugify(e.target.value) })}
                      placeholder="Web App"
                      className="h-9 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:ring-2 focus:ring-app-brand-100"
                    />
                  </label>
                  <label className="space-y-1 text-xs font-semibold text-gray-600">
                    Key (slug)
                    <input
                      value={app.key}
                      onChange={(e) => updateApp(index, { key: slugify(e.target.value) })}
                      placeholder="web-app"
                      className="h-9 w-full rounded-lg border border-gray-200 px-3 text-sm font-mono outline-none focus:ring-2 focus:ring-app-brand-100"
                    />
                  </label>
                </div>

                <label className="mt-3 block space-y-1 text-xs font-semibold text-gray-600">
                  Description
                  <input
                    value={app.description ?? ""}
                    onChange={(e) => updateApp(index, { description: e.target.value })}
                    placeholder="Optional"
                    className="h-9 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:ring-2 focus:ring-app-brand-100"
                  />
                </label>

                <div className="mt-3">
                  <p className="text-xs font-semibold text-gray-600">Environment URLs</p>
                  <div className="mt-1.5 space-y-1.5">
                    {Object.entries(app.environment_urls).map(([env, url]) => (
                      <div key={env} className="flex items-center gap-2">
                        <span className="w-28 shrink-0 rounded-md bg-gray-100 px-2 py-1.5 text-center text-xs font-bold text-gray-600">{env}</span>
                        <input
                          value={url}
                          onChange={(e) => setEnvUrl(index, env, e.target.value)}
                          placeholder="https://..."
                          className="h-8 flex-1 rounded-lg border border-gray-200 px-3 text-xs font-mono outline-none focus:ring-2 focus:ring-app-brand-100"
                        />
                        <button type="button" onClick={() => removeEnv(index, env)} className="text-gray-400 hover:text-rose-600">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                  <Button variant="outline" size="sm" className="mt-2" onClick={() => addEnvRow(index)}>
                    <Plus className="h-3.5 w-3.5" /> Add environment
                  </Button>
                </div>

                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-3">
                  <div className="flex items-center gap-4">
                    <label className="flex items-center gap-1.5 text-xs font-semibold text-gray-600">
                      <input
                        type="checkbox"
                        checked={app.is_default}
                        onChange={(e) => updateApp(index, { is_default: e.target.checked })}
                      />
                      Default application
                    </label>
                    <label className="flex items-center gap-1.5 text-xs font-semibold text-gray-600">
                      <input
                        type="checkbox"
                        checked={app.is_active}
                        onChange={(e) => updateApp(index, { is_active: e.target.checked })}
                      />
                      Active
                    </label>
                    {app.is_default && <Badge variant="success" className="text-[10px]">Default</Badge>}
                  </div>
                  <button type="button" onClick={() => removeApp(index)} className="text-xs font-semibold text-rose-600 hover:underline">
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>

          <Button variant="outline" size="sm" onClick={addApp}>
            <Plus className="h-4 w-4" /> Add Application
          </Button>
        </div>
      </section>

      <section className="mt-4 min-w-0 flex-1 rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="flex flex-col gap-4 border-b border-gray-100 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-amber-100 bg-amber-50">
              <Shield className="h-5 w-5 text-amber-600" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900">External Dependencies</h2>
              <p className="mt-1 text-sm text-gray-500">
                Third-party services your application calls out to. Generated scripts mock/intercept these instead of calling them live.
              </p>
            </div>
          </div>
          <Button size="sm" disabled={savingDeps} onClick={saveDependencies}>
            {savingDeps ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save Dependencies
          </Button>
        </div>

        <div className="p-5 space-y-3">
          {deps.length === 0 && (
            <p className="rounded-lg border border-dashed border-gray-200 px-4 py-6 text-center text-sm text-gray-400">
              No external dependencies registered.
            </p>
          )}

          {deps.map((dep, index) => (
            <div key={dep.id ?? `new-${index}`} className="grid gap-3 rounded-xl border border-gray-200 p-4 md:grid-cols-[1fr_1fr_1fr_auto]">
              <label className="space-y-1 text-xs font-semibold text-gray-600">
                Service name
                <input
                  value={dep.service_name}
                  onChange={(e) => updateDep(index, { service_name: e.target.value })}
                  placeholder="Payment Gateway"
                  className="h-9 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:ring-2 focus:ring-app-brand-100"
                />
              </label>
              <label className="space-y-1 text-xs font-semibold text-gray-600">
                Mock strategy
                <select
                  value={dep.mock_strategy}
                  onChange={(e) => updateDep(index, { mock_strategy: e.target.value as ProjectExternalDependency["mock_strategy"] })}
                  className="h-9 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:ring-2 focus:ring-app-brand-100"
                >
                  <option value="intercept">Intercept (mock in-script)</option>
                  <option value="sandbox">Sandbox URL</option>
                  <option value="ignore">Ignore</option>
                </select>
              </label>
              <label className="space-y-1 text-xs font-semibold text-gray-600">
                Sandbox URL
                <input
                  value={dep.sandbox_url ?? ""}
                  onChange={(e) => updateDep(index, { sandbox_url: e.target.value })}
                  placeholder="Optional"
                  className="h-9 w-full rounded-lg border border-gray-200 px-3 text-sm font-mono outline-none focus:ring-2 focus:ring-app-brand-100"
                />
              </label>
              <div className="flex items-end justify-end">
                <button type="button" onClick={() => removeDep(index)} className="text-xs font-semibold text-rose-600 hover:underline">
                  Remove
                </button>
              </div>
            </div>
          ))}

          <Button variant="outline" size="sm" onClick={addDep}>
            <Plus className="h-4 w-4" /> Add External Dependency
          </Button>
        </div>
      </section>

      {toast && (
        <div className="fixed bottom-5 right-5 z-50 w-[360px] max-w-[calc(100vw-2rem)] rounded-xl border border-gray-200 bg-white p-4 shadow-xl">
          <div className="flex gap-3">
            {toast.kind === "success" ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : <XCircle className="h-5 w-5 text-rose-600" />}
            <div className="min-w-0 flex-1">
              <p className="font-bold text-gray-900">{toast.title}</p>
              <p className="mt-1 text-sm text-gray-600">{toast.message}</p>
            </div>
            <button type="button" onClick={() => setToast(null)} className={cn("text-gray-400 hover:text-gray-700")}>
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
