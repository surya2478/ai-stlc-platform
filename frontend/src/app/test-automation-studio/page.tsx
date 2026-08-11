"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, Cpu, FileText, Loader2, TerminalSquare, TestTube2 } from "lucide-react";
import {
  applicationsApi,
  navigationApi,
  projectsApi,
  testAutomationStudioApi,
  type Project,
  type ProjectApplication,
  type TasStudioSummary,
} from "@/lib/api";
import { CoverageAssessmentView } from "@/components/test-automation-studio/CoverageAssessmentView";
import { ScriptLabView } from "@/components/test-automation-studio/ScriptLabView";
import { TestCaseWorkbenchView } from "@/components/test-automation-studio/TestCaseWorkbenchView";
import { cn } from "@/lib/utils";

type StudioView = "coverage" | "test-cases" | "script-lab";

const VIEWS: Array<{ id: StudioView; label: string; icon: typeof FileText; blurb: string }> = [
  {
    id: "coverage",
    label: "Requirement Coverage Assessment",
    icon: FileText,
    blurb: "Upload BRD, SRD and existing test case documents, then assess automation coverage.",
  },
  {
    id: "test-cases",
    label: "Automation TC Coverage Assessment",
    icon: TestTube2,
    blurb: "Refine approved requirements into automation-ready test cases, classify and approve.",
  },
  {
    id: "script-lab",
    label: "Automation Script Lab",
    icon: Cpu,
    blurb: "Generate, edit and download Playwright, Katalon and Appium scripts.",
  },
];

function isStudioView(value: string | null): value is StudioView {
  return value === "coverage" || value === "test-cases" || value === "script-lab";
}

function StudioWorkspace() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const projectParam = searchParams.get("project");
  const viewParam = searchParams.get("view");
  const view: StudioView = isStudioView(viewParam) ? viewParam : "coverage";

  const [projects, setProjects] = useState<Project[]>([]);
  const [applications, setApplications] = useState<ProjectApplication[]>([]);
  const [summary, setSummary] = useState<TasStudioSummary | null>(null);
  const [accessible, setAccessible] = useState<boolean | null>(null);
  const [loadingProjects, setLoadingProjects] = useState(true);

  const projectId = useMemo(() => {
    const parsed = projectParam ? Number(projectParam) : NaN;
    if (Number.isFinite(parsed)) return parsed;
    return projects[0]?.id ?? null;
  }, [projectParam, projects]);

  useEffect(() => {
    navigationApi
      .get()
      .then((response) => setAccessible(response.data.can_access_test_automation_studio))
      // Treating an unreachable check as "no access" would lock out the whole
      // module on a transient error; the routes enforce it regardless, so the
      // page renders and any real refusal surfaces as a 404 from the API.
      .catch(() => setAccessible(true));
  }, []);

  useEffect(() => {
    projectsApi
      .list()
      .then((response) => setProjects(response.data))
      .catch(() => setProjects([]))
      .finally(() => setLoadingProjects(false));
  }, []);

  useEffect(() => {
    if (projectId == null) return;
    applicationsApi
      .getForProject(projectId)
      .then((response) => setApplications(response.data.applications ?? []))
      .catch(() => setApplications([]));
  }, [projectId]);

  const refreshSummary = useCallback(() => {
    if (projectId == null) return;
    testAutomationStudioApi
      .summary(projectId)
      .then((response) => setSummary(response.data))
      .catch(() => setSummary(null));
  }, [projectId]);

  useEffect(() => refreshSummary(), [refreshSummary]);

  const setParam = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set(key, value);
    router.replace(`${pathname}?${params.toString()}`);
  };

  if (accessible === false) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-amber-200 bg-amber-50 px-6 py-8 text-center">
        <AlertTriangle className="mx-auto h-6 w-6 text-amber-600" />
        <p className="mt-2 text-sm font-semibold text-amber-900">
          The Test Automation Studio is not available for your account
        </p>
        <p className="mt-1 text-xs text-amber-800">
          It is reserved for the Test_Automation_Users role and platform administrators, and it must
          be enabled for this deployment. Ask an administrator if you need access.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#B71920]/10 text-[#B71920]">
            <TerminalSquare className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-lg font-bold text-gray-900">Test Automation Studio</h1>
            <p className="text-xs text-gray-500">
              {VIEWS.find((entry) => entry.id === view)?.blurb}
            </p>
          </div>
        </div>
        <label className="text-xs">
          <span className="mb-1 block font-medium text-gray-600">Project</span>
          <select
            value={projectId != null ? String(projectId) : ""}
            onChange={(event) => setParam("project", event.target.value)}
            className="h-8 min-w-[14rem] rounded-lg border border-gray-200 bg-white px-2 text-xs"
            disabled={loadingProjects}
          >
            {projects.length === 0 && <option value="">No projects available</option>}
            {projects.map((project) => (
              <option key={project.id} value={String(project.id)}>
                {project.name}
              </option>
            ))}
          </select>
        </label>
      </header>

      <nav className="flex flex-wrap gap-2 border-b border-gray-200 pb-2">
        {VIEWS.map((entry) => {
          const Icon = entry.icon;
          const active = entry.id === view;
          return (
            <button
              key={entry.id}
              type="button"
              onClick={() => setParam("view", entry.id)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition",
                active
                  ? "bg-[#B71920] text-white shadow-sm"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900",
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {entry.label}
            </button>
          );
        })}
      </nav>

      {summary && (
        <p className="text-[11px] text-gray-500">
          {summary.requirements_approved} approved requirement(s) &middot; {summary.test_cases_total}{" "}
          refined test case(s) &middot; {summary.test_cases_automation} automation /{" "}
          {summary.test_cases_manual} manual &middot; {summary.scripts_total} script(s)
          {summary.test_cases_needing_test_data > 0 && (
            <span className="ml-1 font-semibold text-amber-700">
              &middot; {summary.test_cases_needing_test_data} awaiting test data
            </span>
          )}
        </p>
      )}

      {loadingProjects ? (
        <div className="flex items-center gap-2 py-16 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading projects...
        </div>
      ) : projectId == null ? (
        <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50/60 px-6 py-10 text-center">
          <p className="text-sm font-semibold text-gray-700">No project selected</p>
          <p className="mt-1 text-xs text-gray-500">
            Create or join a project before using the studio.
          </p>
        </div>
      ) : view === "coverage" ? (
        <CoverageAssessmentView
          projectId={projectId}
          applications={applications}
          onChanged={refreshSummary}
        />
      ) : view === "test-cases" ? (
        <TestCaseWorkbenchView
          projectId={projectId}
          applications={applications}
          onChanged={refreshSummary}
        />
      ) : (
        <ScriptLabView projectId={projectId} onChanged={refreshSummary} />
      )}
    </div>
  );
}

export default function TestAutomationStudioPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 py-16 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading the studio...
        </div>
      }
    >
      <StudioWorkspace />
    </Suspense>
  );
}
