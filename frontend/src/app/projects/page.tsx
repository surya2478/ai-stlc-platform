"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Plus,
  FolderOpen,
  ArrowRight,
  Loader2,
  FolderKanban,
  Trash2,
  AlertTriangle,
  X,
  Pencil,
  Hash,
  User,
  Users,
  Globe2,
  CheckCircle2,
  AlertCircle,
  Save,
} from "lucide-react";
import { projectsApi, type Project } from "@/lib/api";
import { api } from "@/lib/api";
import { AuditStamp } from "@/components/ui/AuditStamp";
import { useUserDirectory } from "@/hooks/useUserDirectory";

// ── Constants ────────────────────────────────────────────────────────────────

const DOMAIN_OPTIONS = [
  { value: "", label: "— Select Project Domain —" },
  { value: "qa_domain", label: "QA Domain" },
  { value: "telecom_domain", label: "Telecom Domain" },
];

const DOMAIN_LABEL: Record<string, string> = {
  qa_domain: "QA Domain",
  telecom_domain: "Telecom Domain",
};

const DOMAIN_COLOR: Record<string, string> = {
  qa_domain: "bg-blue-50 text-blue-700 border-blue-200",
  telecom_domain: "bg-violet-50 text-violet-700 border-violet-200",
};

// ── Input style helpers ──────────────────────────────────────────────────────

const inputClass =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 outline-none transition-all focus:border-blue-400 focus:ring-2 focus:ring-blue-100 disabled:opacity-50";
const inputErrClass =
  "w-full rounded-lg border border-red-300 bg-red-50/40 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 outline-none focus:border-red-400 focus:ring-2 focus:ring-red-100 disabled:opacity-50";

// ── Delete Modal ─────────────────────────────────────────────────────────────

function DeleteProjectModal({
  project,
  onConfirm,
  onCancel,
}: {
  project: Project;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    setDeleting(true);
    setError(null);
    try {
      await onConfirm();
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Delete failed. Please try again.");
      setDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-sm rounded-2xl border bg-card shadow-2xl p-6 space-y-4">
        <div className="flex items-start gap-3">
          <div className="rounded-full bg-red-100 dark:bg-red-900/30 p-2 shrink-0">
            <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="font-semibold text-base">Delete project?</h2>
            <p className="text-sm text-muted-foreground mt-1">
              <span className="font-medium text-foreground">&ldquo;{project.name}&rdquo;</span> and all
              its requirements, test plans, test cases, scripts, executions, and defects will be
              permanently deleted. This cannot be undone.
            </p>
          </div>
          <button onClick={onCancel} className="rounded-md p-1 hover:bg-muted text-muted-foreground shrink-0">
            <X className="h-4 w-4" />
          </button>
        </div>

        {error && (
          <div className="rounded-lg bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-400">
            {error}
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <button
            onClick={onCancel}
            disabled={deleting}
            className="flex-1 rounded-lg border px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={deleting}
            className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
          >
            {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            {deleting ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Edit Modal ───────────────────────────────────────────────────────────────

type EditForm = {
  name: string;
  ppm_id: string;
  project_manager_name: string;
  business_pm_name: string;
  domain: string;
  description: string;
};
type EditErrors = Partial<Record<keyof EditForm, string>>;

function EditProjectModal({
  project,
  onSaved,
  onCancel,
}: {
  project: Project;
  onSaved: (updated: Project) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<EditForm>({
    name: project.name ?? "",
    ppm_id: project.ppm_id ?? "",
    project_manager_name: project.project_manager_name ?? "",
    business_pm_name: project.business_pm_name ?? "",
    domain: project.domain ?? "",
    description: project.description ?? "",
  });
  const [errors, setErrors] = useState<EditErrors>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  function upd(field: keyof EditForm, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
    if (errors[field]) setErrors((e) => ({ ...e, [field]: undefined }));
  }

  function validate(): boolean {
    const errs: EditErrors = {};
    if (!form.name.trim()) errs.name = "Project name is required";
    if (!form.ppm_id.trim()) {
      errs.ppm_id = "PPM ID is required";
    } else if (!/^\d+$/.test(form.ppm_id.trim())) {
      errs.ppm_id = "PPM ID must contain digits only";
    }
    if (!form.project_manager_name.trim())
      errs.project_manager_name = "Project Manager Name is required";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function handleSave() {
    if (!validate()) return;
    setSaving(true);
    setSaveError(null);
    try {
      const payload: Record<string, string | null> = {
        name: form.name.trim(),
        ppm_id: form.ppm_id.trim(),
        project_manager_name: form.project_manager_name.trim(),
        business_pm_name: form.business_pm_name.trim() || null,
        domain: form.domain || null,
        description: form.description.trim() || null,
      };
      const res = await api.patch<Project>(`/projects/${project.id}`, payload);
      setSaved(true);
      setTimeout(() => onSaved(res.data), 800);
    } catch (err: any) {
      setSaveError(err?.response?.data?.detail || "Save failed. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-xl rounded-2xl border bg-white shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="font-bold text-slate-900 text-base">Edit Project</h2>
            <p className="text-xs text-slate-500 mt-0.5">Update project details and governance fields</p>
          </div>
          <button
            onClick={onCancel}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Fields */}
        <div className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">
          {/* Row 1 */}
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-700 flex items-center gap-1">
                <FolderOpen className="h-3 w-3 text-slate-400" />
                Project Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                className={errors.name ? inputErrClass : inputClass}
                value={form.name}
                onChange={(e) => upd("name", e.target.value)}
                disabled={saving}
              />
              {errors.name && <p className="text-xs text-red-600 font-medium">{errors.name}</p>}
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-700 flex items-center gap-1">
                <Hash className="h-3 w-3 text-slate-400" />
                HP PPM ID <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                inputMode="numeric"
                className={errors.ppm_id ? inputErrClass : inputClass}
                placeholder="e.g. 10234"
                value={form.ppm_id}
                onChange={(e) => upd("ppm_id", e.target.value.replace(/\D/g, ""))}
                disabled={saving}
              />
              {errors.ppm_id && <p className="text-xs text-red-600 font-medium">{errors.ppm_id}</p>}
            </div>
          </div>

          {/* Row 2 */}
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-700 flex items-center gap-1">
                <User className="h-3 w-3 text-slate-400" />
                Project Manager <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                className={errors.project_manager_name ? inputErrClass : inputClass}
                value={form.project_manager_name}
                onChange={(e) => upd("project_manager_name", e.target.value)}
                disabled={saving}
              />
              {errors.project_manager_name && (
                <p className="text-xs text-red-600 font-medium">{errors.project_manager_name}</p>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-700 flex items-center gap-1">
                <Users className="h-3 w-3 text-slate-400" />
                Business PM Name
              </label>
              <input
                type="text"
                className={inputClass}
                placeholder="Optional"
                value={form.business_pm_name}
                onChange={(e) => upd("business_pm_name", e.target.value)}
                disabled={saving}
              />
            </div>
          </div>

          {/* Row 3 — Domain */}
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-700 flex items-center gap-1">
                <Globe2 className="h-3 w-3 text-slate-400" />
                Project Domain
              </label>
              <select
                className={inputClass}
                value={form.domain}
                onChange={(e) => upd("domain", e.target.value)}
                disabled={saving}
              >
                {DOMAIN_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Description */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-slate-700">Description</label>
            <textarea
              rows={3}
              className={`${inputClass} resize-none`}
              placeholder="Brief description (optional)…"
              value={form.description}
              onChange={(e) => upd("description", e.target.value)}
              disabled={saving}
            />
          </div>

          {/* Save error */}
          {saveError && (
            <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 font-medium">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
              {saveError}
            </div>
          )}

          {/* Saved confirmation */}
          {saved && (
            <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 font-semibold">
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
              Saved successfully!
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-slate-100 bg-slate-50/60">
          <button
            onClick={onCancel}
            disabled={saving}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || saved}
            className="flex items-center gap-2 rounded-lg bg-[#1b59f8] px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {saving ? "Saving…" : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Project Card ─────────────────────────────────────────────────────────────

function ProjectCard({
  project,
  onEdit,
  onDelete,
  resolveUser,
}: {
  project: Project;
  onEdit: () => void;
  onDelete: () => void;
  resolveUser: (id?: number) => string;
}) {
  const domainKey = project.domain ?? "";
  const domainLabel = DOMAIN_LABEL[domainKey];
  const domainColor = DOMAIN_COLOR[domainKey] ?? "bg-slate-50 text-slate-600 border-slate-200";

  return (
    <div className="relative group rounded-2xl border border-slate-200 bg-white hover:shadow-lg hover:border-slate-300 transition-all duration-200">
      {/* Action buttons — shown on hover */}
      <div className="absolute top-3 right-3 z-10 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={(e) => { e.preventDefault(); onEdit(); }}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-blue-50 hover:text-blue-600 transition-colors"
          title="Edit project"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={(e) => { e.preventDefault(); onDelete(); }}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors"
          title="Delete project"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      <Link href={`/requirements?project=${project.id}`} className="block p-5">
        {/* Card header — name + PPM badge */}
        <div className="flex items-start gap-3 mb-3 pr-14">
          <div className="rounded-xl bg-blue-50 p-2.5 shrink-0 border border-blue-100">
            <FolderOpen className="h-5 w-5 text-[#1b59f8]" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="font-bold text-slate-900 truncate text-sm leading-5">{project.name}</h2>
            {project.ppm_id && (
              <span className="inline-flex items-center gap-1 mt-0.5 text-[10px] font-mono font-semibold text-slate-500 bg-slate-100 border border-slate-200 rounded-full px-2 py-0.5">
                <Hash className="h-2.5 w-2.5" />
                {project.ppm_id}
              </span>
            )}
          </div>
        </div>

        {/* PM info */}
        {(project.project_manager_name || project.business_pm_name) && (
          <div className="space-y-0.5 mb-3">
            {project.project_manager_name && (
              <div className="flex items-center gap-1.5 text-xs text-slate-600">
                <User className="h-3 w-3 text-slate-400 shrink-0" />
                <span className="font-medium truncate">{project.project_manager_name}</span>
                <span className="text-slate-400 text-[10px] shrink-0">PM</span>
              </div>
            )}
            {project.business_pm_name && (
              <div className="flex items-center gap-1.5 text-xs text-slate-500">
                <Users className="h-3 w-3 text-slate-400 shrink-0" />
                <span className="truncate">{project.business_pm_name}</span>
                <span className="text-slate-400 text-[10px] shrink-0">Business PM</span>
              </div>
            )}
          </div>
        )}

        {/* Description */}
        {project.description && (
          <p className="text-xs text-slate-500 line-clamp-2 mb-3 leading-5">{project.description}</p>
        )}

        {/* Footer — domain pill + status + date + open arrow */}
        <div className="flex items-center gap-2 flex-wrap">
          {domainLabel && (
            <span className={`inline-flex items-center gap-1 text-[10px] font-semibold rounded-full border px-2 py-0.5 ${domainColor}`}>
              <Globe2 className="h-2.5 w-2.5" />
              {domainLabel}
            </span>
          )}
          <span className="text-[10px] font-semibold text-slate-400 capitalize bg-slate-50 border border-slate-200 rounded-full px-2 py-0.5">
            {project.status}
          </span>
          <span className="ml-auto flex items-center gap-1 text-[11px] text-[#1b59f8] font-semibold">
            Open <ArrowRight className="h-3 w-3" />
          </span>
        </div>

        {/* Audit trail */}
        <AuditStamp
          createdAt={project.created_at}
          updatedAt={project.updated_at}
          createdByName={resolveUser(project.owner_id ?? undefined)}
          compact
          className="mt-3 pt-2.5 border-t border-slate-100/60"
        />
      </Link>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function ProjectsPage() {
  const { resolveUser } = useUserDirectory();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingProject, setDeletingProject] = useState<Project | null>(null);
  const [editingProject, setEditingProject] = useState<Project | null>(null);

  useEffect(() => {
    projectsApi
      .list()
      .then((r) => setProjects(r.data))
      .catch((e) => setError(e?.response?.data?.detail || "Failed to load projects"))
      .finally(() => setLoading(false));
  }, []);

  const handleDelete = async () => {
    if (!deletingProject) return;
    await projectsApi.delete(deletingProject.id);
    setProjects((prev) => prev.filter((p) => p.id !== deletingProject.id));
    setDeletingProject(null);
  };

  const handleSaved = (updated: Project) => {
    setProjects((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
    setEditingProject(null);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage your STLC automation projects and HP PPM integrations.
          </p>
        </div>
        <Link
          href="/projects/new"
          className="flex items-center gap-2 rounded-lg bg-[#1b59f8] px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors shadow-sm"
        >
          <Plus className="h-4 w-4" />
          New Project
        </Link>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading projects…
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && projects.length === 0 && (
        <div className="rounded-2xl border border-dashed p-12 text-center text-muted-foreground">
          <FolderKanban className="mx-auto h-10 w-10 mb-3 opacity-40" />
          <p className="font-semibold">No projects yet</p>
          <p className="text-sm mt-1">Create your first project to get started</p>
          <Link
            href="/projects/new"
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[#1b59f8] px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
          >
            <Plus className="h-4 w-4" />New Project
          </Link>
        </div>
      )}

      {/* Project grid */}
      {!loading && projects.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onEdit={() => setEditingProject(project)}
              onDelete={() => setDeletingProject(project)}
              resolveUser={resolveUser}
            />
          ))}
        </div>
      )}

      {/* Delete confirmation modal */}
      {deletingProject && (
        <DeleteProjectModal
          project={deletingProject}
          onConfirm={handleDelete}
          onCancel={() => setDeletingProject(null)}
        />
      )}

      {/* Edit project modal */}
      {editingProject && (
        <EditProjectModal
          project={editingProject}
          onSaved={handleSaved}
          onCancel={() => setEditingProject(null)}
        />
      )}
    </div>
  );
}
