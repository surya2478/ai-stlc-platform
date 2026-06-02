"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, FolderPlus, Loader2 } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function NewProjectPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", description: "" });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await api.post("/projects/", form);
      router.push("/projects");
    } catch (err: any) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      setError(
        detail
          ? `${detail}`
          : status
          ? `Server error ${status} — check backend logs`
          : "Cannot reach backend. Is it running? (docker compose up)"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-lg space-y-6">
      {/* Back */}
      <Link
        href="/projects"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to Projects
      </Link>

      <div>
        <h1 className="text-2xl font-bold tracking-tight">Create Project</h1>
        <p className="text-sm text-muted-foreground mt-1">
          A project groups all requirements, test cases, and executions for a product or release.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="rounded-xl border bg-card p-6 space-y-5">
        <div className="space-y-1.5">
          <label className="text-sm font-medium" htmlFor="name">
            Project Name <span className="text-red-500">*</span>
          </label>
          <input
            id="name"
            type="text"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none ring-offset-background focus:ring-2 focus:ring-ring focus:ring-offset-2"
            placeholder="e.g. Customer Portal v2.4"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            required
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-sm font-medium" htmlFor="description">
            Description
          </label>
          <textarea
            id="description"
            rows={3}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none ring-offset-background focus:ring-2 focus:ring-ring focus:ring-offset-2 resize-none"
            placeholder="Brief description of what will be tested…"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          />
        </div>

        {error && (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        )}

        <div className="flex items-center gap-3 pt-1">
          <button
            type="submit"
            disabled={loading || !form.name.trim()}
            className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
            className="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-accent transition-colors"
          >
            Cancel
          </Link>
        </div>
      </form>

      {/* Info box */}
      <div className="rounded-xl border bg-muted/40 p-4 text-xs text-muted-foreground space-y-1">
        <p className="font-medium text-foreground">What happens next?</p>
        <p>1. Upload requirement documents (PDF, DOCX, TXT, Markdown, CSV)</p>
        <p>2. Or connect Jira and fetch Epics / Stories</p>
        <p>3. AI agents analyze requirements and generate the full STLC pipeline</p>
      </div>
    </div>
  );
}
