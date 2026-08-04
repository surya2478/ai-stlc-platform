"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  FolderPlus,
  Loader2,
  Hash,
  User,
  Users,
  Globe2,
  FileText,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";

const DOMAIN_OPTIONS = [
  { value: "", label: "— Select Project Domain —" },
  { value: "digital_consumer", label: "Digital-Consumer" },
  { value: "digital_business", label: "Digital-Business" },
  { value: "non_digital", label: "Non-Digital" },
  { value: "billing", label: "Billing" },
  { value: "sales", label: "Sales" },
  { value: "marketing", label: "Marketing" },
  { value: "ccc", label: "CCC" },
  { value: "special_track", label: "Special Track" },
  { value: "production_testing", label: "Production Testing" },
];

type FormState = {
  name: string;
  ppm_id: string;
  project_manager_name: string;
  business_pm_name: string;
  domain: string;
  description: string;
};

type FieldError = Partial<Record<keyof FormState, string>>;

function FieldWrapper({
  label,
  required,
  error,
  children,
  icon,
}: {
  label: string;
  required?: boolean;
  error?: string;
  children: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
        {icon && <span className="text-slate-400">{icon}</span>}
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
      {error && (
        <p className="flex items-center gap-1 text-xs text-red-600 font-medium">
          <AlertCircle className="h-3 w-3 shrink-0" />
          {error}
        </p>
      )}
    </div>
  );
}

const inputClass =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 outline-none transition-all focus:border-blue-400 focus:ring-2 focus:ring-blue-100 disabled:opacity-50";
const inputErrorClass =
  "w-full rounded-lg border border-red-300 bg-red-50/40 px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 outline-none transition-all focus:border-red-400 focus:ring-2 focus:ring-red-100 disabled:opacity-50";

export default function NewProjectPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [form, setForm] = useState<FormState>({
    name: "",
    ppm_id: "",
    project_manager_name: "",
    business_pm_name: "",
    domain: "",
    description: "",
  });
  const [fieldErrors, setFieldErrors] = useState<FieldError>({});

  function update(field: keyof FormState, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
    if (fieldErrors[field]) setFieldErrors((e) => ({ ...e, [field]: undefined }));
  }

  function validate(): boolean {
    const errors: FieldError = {};
    if (!form.name.trim()) errors.name = "Project name is required";
    if (!form.ppm_id.trim()) {
      errors.ppm_id = "PPM ID is required";
    } else if (!/^\d+$/.test(form.ppm_id.trim())) {
      errors.ppm_id = "PPM ID must contain digits only (e.g. 10234)";
    }
    if (!form.project_manager_name.trim())
      errors.project_manager_name = "Project Manager Name is required";
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    setLoading(true);
    setSubmitError(null);
    try {
      const payload: Record<string, string | null> = {
        name: form.name.trim(),
        ppm_id: form.ppm_id.trim(),
        project_manager_name: form.project_manager_name.trim(),
        business_pm_name: form.business_pm_name.trim() || null,
        domain: form.domain || null,
        description: form.description.trim() || null,
      };
      await api.post("/projects/", payload);
      setSuccess(true);
      setTimeout(() => router.push("/projects"), 1200);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const status = err?.response?.status;
      setSubmitError(
        detail
          ? String(detail)
          : status
          ? `Server error ${status} — check backend logs`
          : "Cannot reach backend. Is it running? (docker compose up)"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-6">
      {/* Back navigation */}
      <Link
        href="/projects"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors font-medium"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to Projects
      </Link>

      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Create Project</h1>
        <p className="text-sm text-slate-500 mt-1 leading-6">
          A project groups all requirements, test cases, and executions for a product or release.
          HP PPM integration fields are required for portfolio tracking.
        </p>
      </div>

      {/* Success flash */}
      {success && (
        <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          Project created successfully! Redirecting…
        </div>
      )}

      <form onSubmit={handleSubmit} className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        {/* Form header */}
        <div className="px-6 pt-6 pb-4 border-b border-slate-100">
          <h2 className="text-base font-bold text-slate-800">Project Details</h2>
          <p className="text-xs text-slate-500 mt-0.5">Fields marked <span className="text-red-500 font-semibold">*</span> are required</p>
        </div>

        <div className="p-6 space-y-6">
          {/* Row 1 — Project Name + PPM ID */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FieldWrapper
              label="Project Name"
              required
              error={fieldErrors.name}
              icon={<FolderPlus className="h-3.5 w-3.5" />}
            >
              <input
                id="name"
                type="text"
                className={fieldErrors.name ? inputErrorClass : inputClass}
                placeholder="e.g. Customer Portal v2.4"
                value={form.name}
                onChange={(e) => update("name", e.target.value)}
                disabled={loading}
              />
            </FieldWrapper>

            <FieldWrapper
              label="HP PPM ID"
              required
              error={fieldErrors.ppm_id}
              icon={<Hash className="h-3.5 w-3.5" />}
            >
              <input
                id="ppm_id"
                type="text"
                inputMode="numeric"
                className={fieldErrors.ppm_id ? inputErrorClass : inputClass}
                placeholder="e.g. 10234"
                value={form.ppm_id}
                onChange={(e) => update("ppm_id", e.target.value.replace(/\D/g, ""))}
                disabled={loading}
                maxLength={50}
              />
            </FieldWrapper>
          </div>

          {/* Row 2 — PM Name + Business PM Name */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FieldWrapper
              label="Project Manager Name"
              required
              error={fieldErrors.project_manager_name}
              icon={<User className="h-3.5 w-3.5" />}
            >
              <input
                id="project_manager_name"
                type="text"
                className={fieldErrors.project_manager_name ? inputErrorClass : inputClass}
                placeholder="e.g. Alice Johnson"
                value={form.project_manager_name}
                onChange={(e) => update("project_manager_name", e.target.value)}
                disabled={loading}
              />
            </FieldWrapper>

            <FieldWrapper
              label="Business PM Name"
              error={fieldErrors.business_pm_name}
              icon={<Users className="h-3.5 w-3.5" />}
            >
              <input
                id="business_pm_name"
                type="text"
                className={inputClass}
                placeholder="e.g. Bob Smith (optional)"
                value={form.business_pm_name}
                onChange={(e) => update("business_pm_name", e.target.value)}
                disabled={loading}
              />
            </FieldWrapper>
          </div>

          {/* Row 3 — Domain */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FieldWrapper
              label="Project Domain"
              error={fieldErrors.domain}
              icon={<Globe2 className="h-3.5 w-3.5" />}
            >
              <select
                id="domain"
                className={inputClass}
                value={form.domain}
                onChange={(e) => update("domain", e.target.value)}
                disabled={loading}
              >
                {DOMAIN_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </FieldWrapper>
          </div>

          {/* Divider */}
          <hr className="border-slate-100" />

          {/* Description — full width */}
          <FieldWrapper
            label="Description"
            icon={<FileText className="h-3.5 w-3.5" />}
          >
            <textarea
              id="description"
              rows={3}
              className={`${inputClass} resize-none`}
              placeholder="Brief description of what will be tested (optional)…"
              value={form.description}
              onChange={(e) => update("description", e.target.value)}
              disabled={loading}
            />
          </FieldWrapper>

          {/* Submit error */}
          {submitError && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-700 font-medium">
              <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              {submitError}
            </div>
          )}
        </div>

        {/* Form footer */}
        <div className="flex items-center gap-3 px-6 py-4 border-t border-slate-100 bg-slate-50/60 rounded-b-2xl">
          <button
            type="submit"
            disabled={loading || success}
            className="flex items-center gap-2 rounded-lg bg-[#1b59f8] px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FolderPlus className="h-4 w-4" />
            )}
            {loading ? "Creating…" : "Create Project"}
          </button>
          <Link
            href="/projects"
            className="rounded-lg px-4 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-200 transition-colors"
          >
            Cancel
          </Link>
        </div>
      </form>

      {/* Info box */}
      <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-1.5">
        <p className="text-sm font-semibold text-slate-800">What happens next?</p>
        <p className="text-xs text-slate-500 leading-5">1. Upload requirement documents (PDF, DOCX, TXT, Markdown, CSV)</p>
        <p className="text-xs text-slate-500 leading-5">2. Or connect Jira and fetch Epics / Stories</p>
        <p className="text-xs text-slate-500 leading-5">3. AI agents analyze requirements and generate the full STLC pipeline</p>
      </div>
    </div>
  );
}
