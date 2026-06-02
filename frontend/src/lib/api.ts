/**
 * Centralised API client.
 * All backend calls go through here so the base URL is set in one place.
 */
import axios from "axios";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

// Global response interceptor — turns unhandled errors into console warnings
// instead of crashing the page. Components are expected to handle errors via
// Promise.allSettled() or try/catch, but this is a safety net.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      console.warn(
        "[API] 401 Unauthorized — backend returned auth required. " +
        "In local dev mode the backend auto-logs in as dev@stlc.local. " +
        "Check that the backend is running and APP_ENV=local is set."
      );
    }
    return Promise.reject(error);
  }
);

// ── Types ──────────────────────────────────────────────────────────────────────

export interface Project {
  id: number;
  name: string;
  description?: string;
  status: string;
  created_at: string;
}

export interface Document {
  id: number;
  project_id: number;
  original_filename: string;
  file_type: string;
  file_size_bytes: number;
  status: string;
  page_count?: number;
  created_at: string;
}

export interface Requirement {
  id: number;
  requirement_id: string;
  title: string;
  summary?: string;
  source: string;
  status: string;
  jira_issue_key?: string;
  acceptance_criteria?: string[];
  business_rules?: string[];
  user_roles?: string[];
  systems_impacted?: string[];
  ui_pages?: string[];
  apis?: string[];
  dependencies?: string[];
  risks?: string[];
  missing_information?: string[];
  metadata_?: Record<string, unknown>;
  source_document_id?: number;
  created_at: string;
  updated_at: string;
}

export interface TestPlan {
  id: number;
  test_plan_id: string;
  title: string;
  scope?: string[];
  out_of_scope?: string[];
  test_types?: string[];
  entry_criteria?: string[];
  exit_criteria?: string[];
  risks?: string[];
  mitigations?: string[];
  automation_candidates?: string[];
  estimated_effort?: string;
  resource_recommendation?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface TestScenario {
  id: number;
  scenario_id: string;
  title: string;
  description?: string;
  scenario_type?: string;
  priority: string;
  coverage_mapping?: string[];
  status: string;
  requirement_id?: number;
  created_at: string;
}

export interface TestCase {
  id: number;
  test_case_id: string;
  title: string;
  preconditions?: string[];
  test_data?: Record<string, unknown>;
  steps?: Array<{ step_number: number; action: string; expected_result: string }>;
  expected_result?: string;
  bdd_scenario?: string;
  priority: string;
  severity: string;
  test_type?: string;
  automation_candidate: boolean;
  status: string;
  scenario_id?: number;
  requirement_id?: number;
  created_at: string;
  updated_at: string;
}

// ── Projects ──────────────────────────────────────────────────────────────────

export const projectsApi = {
  list: () => api.get<Project[]>("/projects/"),
  get: (id: number) => api.get<Project>(`/projects/${id}`),
  create: (data: { name: string; description?: string }) =>
    api.post<Project>("/projects/", data),
  update: (id: number, data: Partial<Project>) =>
    api.patch<Project>(`/projects/${id}`, data),
  delete: (id: number) => api.delete(`/projects/${id}`),
};

// ── Documents ─────────────────────────────────────────────────────────────────

export const documentsApi = {
  upload: (projectId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<Document>(`/documents/upload?project_id=${projectId}`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  list: (projectId: number) =>
    api.get<Document[]>(`/documents/project/${projectId}`),
  get: (id: number) => api.get<Document>(`/documents/${id}`),
  delete: (id: number) => api.delete(`/documents/${id}`),
};

// ── Requirements ──────────────────────────────────────────────────────────────

export const requirementsApi = {
  list: (projectId: number, status?: string) =>
    api.get<Requirement[]>(`/requirements/project/${projectId}`, {
      params: status ? { status } : undefined,
    }),
  get: (id: number) => api.get<Requirement>(`/requirements/${id}`),
  create: (data: { project_id: number; title: string; summary?: string; source?: string }) =>
    api.post<Requirement>("/requirements/", data),
  update: (id: number, data: Partial<Requirement>) =>
    api.patch<Requirement>(`/requirements/${id}`, data),
  approve: (id: number, action: "approve" | "reject", notes?: string) =>
    api.post<Requirement>(`/requirements/${id}/approve`, { action, notes }),
  delete: (id: number) => api.delete(`/requirements/${id}`),
  triggerIntake: (projectId: number, documentId: number) =>
    api.post("/requirements/agent/intake", { project_id: projectId, document_id: documentId }),
  triggerQuality: (projectId: number, requirementIds?: number[]) =>
    api.post("/requirements/agent/quality", {
      project_id: projectId,
      requirement_ids: requirementIds,
    }),
};

// ── Test Plans ────────────────────────────────────────────────────────────────

export const testPlansApi = {
  list: (projectId: number) =>
    api.get<TestPlan[]>(`/test-plans/project/${projectId}`),
  get: (id: number) => api.get<TestPlan>(`/test-plans/${id}`),
  update: (id: number, data: Partial<TestPlan>) =>
    api.patch<TestPlan>(`/test-plans/${id}`, data),
  approve: (id: number, action: "approve" | "reject", notes?: string) =>
    api.post<TestPlan>(`/test-plans/${id}/approve`, { action, notes }),
  generatePlan: (projectId: number, requirementIds: number[]) =>
    api.post("/test-plans/agent/generate-plan", {
      project_id: projectId,
      requirement_ids: requirementIds,
    }),
  generateScenarios: (projectId: number, requirementIds: number[]) =>
    api.post("/test-plans/agent/generate-scenarios", {
      project_id: projectId,
      requirement_ids: requirementIds,
    }),
};

// ── Test Scenarios ────────────────────────────────────────────────────────────

export const scenariosApi = {
  list: (projectId: number, requirementId?: number) =>
    api.get<TestScenario[]>(`/test-plans/scenarios/project/${projectId}`, {
      params: requirementId ? { requirement_id: requirementId } : undefined,
    }),
};

// ── Test Cases ────────────────────────────────────────────────────────────────

export const testCasesApi = {
  list: (projectId: number, params?: { scenario_id?: number; requirement_id?: number; status?: string }) =>
    api.get<TestCase[]>(`/test-plans/cases/project/${projectId}`, { params }),
  get: (id: number) => api.get<TestCase>(`/test-plans/cases/${id}`),
  update: (id: number, data: Partial<TestCase>) =>
    api.patch<TestCase>(`/test-plans/cases/${id}`, data),
  approve: (id: number, action: "approve" | "reject", notes?: string) =>
    api.post<TestCase>(`/test-plans/cases/${id}/approve`, { action, notes }),
  generateCases: (projectId: number, scenarioIds?: number[], requirementIds?: number[]) =>
    api.post("/test-plans/agent/generate-cases", {
      project_id: projectId,
      scenario_ids: scenarioIds,
      requirement_ids: requirementIds,
    }),
};

// ── Automation ────────────────────────────────────────────────────────────────

export interface AutomationScript {
  id: number;
  project_id: number;
  test_case_id?: number;
  script_id: string;
  framework: string;
  file_path?: string;
  code: string;
  setup_required?: string[];
  execution_command?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export const automationApi = {
  list: (projectId: number, params?: { test_case_id?: number; status?: string }) =>
    api.get<AutomationScript[]>(`/automation/project/${projectId}`, { params }),
  get: (id: number) => api.get<AutomationScript>(`/automation/${id}`),
  update: (id: number, data: Partial<AutomationScript>) =>
    api.patch<AutomationScript>(`/automation/${id}`, data),
  approve: (id: number, action: "approve" | "reject", notes?: string) =>
    api.post<AutomationScript>(`/automation/${id}/approve`, { action, notes }),
  generateScripts: (projectId: number, testCaseIds: number[], framework: string = "playwright") =>
    api.post("/automation/agent/generate-scripts", {
      project_id: projectId,
      test_case_ids: testCaseIds,
      framework,
    }),
};

// ── Execution ─────────────────────────────────────────────────────────────────

export interface ExecutionResult {
  id: number;
  execution_run_id: number;
  test_case_id?: number;
  test_name: string;
  status: string;
  duration_ms?: number;
  error_message?: string;
  stack_trace?: string;
  logs?: string[];
  created_at: string;
  updated_at: string;
}

export interface ExecutionRun {
  id: number;
  project_id: number;
  execution_id: string;
  suite_name?: string;
  environment?: string;
  status: string;
  total_tests: number;
  passed: number;
  failed: number;
  skipped: number;
  execution_logs?: unknown[];
  created_at: string;
  updated_at: string;
}

export const executionApi = {
  listRuns: (projectId: number, params?: { status?: string }) =>
    api.get<ExecutionRun[]>(`/execution/project/${projectId}`, { params }),
  getRun: (id: number) => api.get<ExecutionRun>(`/execution/${id}`),
  getResults: (runId: number) => api.get<ExecutionResult[]>(`/execution/${runId}/results`),
  runTests: (projectId: number, testCaseIds: number[], environment: string = "staging", suiteName?: string) =>
    api.post("/execution/agent/run-tests", {
      project_id: projectId,
      test_case_ids: testCaseIds,
      environment,
      suite_name: suiteName,
    }),
};

// ── Defects ───────────────────────────────────────────────────────────────────

export interface DefectDraft {
  id: number;
  project_id: number;
  test_case_id?: number;
  execution_result_id?: number;
  defect_id: string;
  summary: string;
  description?: string;
  steps_to_reproduce?: string[];
  expected_result?: string;
  actual_result?: string;
  severity: string;
  priority: string;
  root_cause_hypothesis?: string;
  classification: string;
  jira_ready: boolean;
  status: string;
  created_at: string;
  updated_at: string;
}

export const defectsApi = {
  list: (projectId: number, params?: { status?: string }) =>
    api.get<DefectDraft[]>(`/defects/project/${projectId}`, { params }),
  get: (id: number) => api.get<DefectDraft>(`/defects/${id}`),
  update: (id: number, data: Partial<DefectDraft>) =>
    api.patch<DefectDraft>(`/defects/${id}`, data),
  approve: (id: number, action: "approve" | "reject", notes?: string) =>
    api.post<DefectDraft>(`/defects/${id}/approve`, { action, notes }),
  pushToJira: (id: number) => api.post(`/defects/${id}/push-to-jira`),
  analyseDefects: (projectId: number, executionResultIds?: number[], testCaseIds?: number[]) =>
    api.post("/defects/agent/analyse-defects", {
      project_id: projectId,
      execution_result_ids: executionResultIds,
      test_case_ids: testCaseIds,
    }),
};

// ── Agent Runs ────────────────────────────────────────────────────────────────

export interface AgentRun {
  id: number;
  project_id: number;
  agent_name: string;
  status: string;
  duration_seconds?: number;
  llm_provider?: string;
  llm_model?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface AgentLog {
  id: number;
  agent_run_id: number;
  level: string;
  step?: string;
  message: string;
  data?: Record<string, unknown>;
  created_at: string;
}

export const agentRunsApi = {
  list: (projectId: number, params?: { agent_name?: string; status?: string; limit?: number }) =>
    api.get<AgentRun[]>(`/agent-runs/project/${projectId}`, { params }),
  get: (id: number) => api.get<AgentRun>(`/agent-runs/${id}`),
  getLogs: (runId: number) => api.get<AgentLog[]>(`/agent-runs/${runId}/logs`),
};

// ── Reports ───────────────────────────────────────────────────────────────────

export interface Report {
  id: number;
  report_id: string;
  report_type: string;
  title: string;
  summary?: string;
  coverage?: Record<string, number>;
  execution_metrics?: Record<string, number | string>;
  defect_metrics?: Record<string, number | string>;
  risks?: string[];
  recommendations?: string[];
  status: string;
  created_at: string;
}

export const reportsApi = {
  list: (projectId: number) => api.get<Report[]>(`/reports/project/${projectId}`),
  get: (id: number) => api.get<Report>(`/reports/${id}`),
  generate: (projectId: number, reportType: string = "sprint") =>
    api.post("/reports/agent/generate-report", { project_id: projectId, report_type: reportType }),
};
