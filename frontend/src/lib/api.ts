/**
 * Centralised API client.
 * All backend calls go through here so the base URL is set in one place.
 */
import axios from "axios";
import type { InternalAxiosRequestConfig } from "axios";

const SERVER_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const BROWSER_BASE_URL = "";
const TOKEN_STORAGE_KEY = "stlc_access_token";
const DEV_AUTH_EMAIL = "";
const DEV_AUTH_PASSWORD = "";

type RetriableRequestConfig = InternalAxiosRequestConfig & {
  _retryDevAuth?: boolean;
  _retry?: boolean;
};


function getNetworkErrorMessage() {
  return `Could not reach the backend API at ${SERVER_BASE_URL}. Please make sure the backend is running and accessible.`;
}

function normalizeAxiosError(error: unknown) {
  if (!axios.isAxiosError(error)) return error;
  if (error.message === "Network Error") {
    error.message = getNetworkErrorMessage();
  }
  return error;
}

export const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
  withCredentials: true,
});

let devAuthPromise: Promise<string | null> | null = null;

function isLocalBrowser() {
  return false;
}

function isDevAuthEnabled() {
  return false;
}

async function requestDevToken() {
  return null;
}

api.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  config.withCredentials = true;
  return config;
});

// Global response interceptor — automatically attempts cookie refresh on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    normalizeAxiosError(error);
    const originalConfig = error.config as RetriableRequestConfig | undefined;
    if (error?.response?.status === 401 && originalConfig && !originalConfig._retry && !originalConfig.url?.includes("/users/token")) {
      originalConfig._retry = true;
      try {
        await axios.post("/api/v1/users/refresh", {}, { withCredentials: true });
        return api(originalConfig);
      } catch (refreshError) {
        console.warn("[API] Session refresh failed, logging out:", refreshError);
        clearAccessToken();
        if (typeof window !== "undefined" && window.location.pathname !== "/login") {
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(normalizeAxiosError(error));
  }
);

// ── Types ──────────────────────────────────────────────────────────────────────

export interface TokenProjectMembership {
  project_id: number;
  role: string;
  permissions: string[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  global_role?: string;
  project_memberships?: TokenProjectMembership[];
}

export function getAccessToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("stlc_auth_profile") ? "cookie-auth" : null;
}

export function clearAccessToken() {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    window.localStorage.removeItem("stlc_auth_profile");
  }
}

export function getAuthProfile() {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem("stlc_auth_profile");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as TokenResponse;
  } catch {
    return null;
  }
}

export const authApi = {
  login: async (email: string, password: string) => {
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    const response = await axios.post<TokenResponse>(
      `${BROWSER_BASE_URL}/api/v1/users/token`,
      form,
      { headers: { "Content-Type": "application/x-www-form-urlencoded" }, withCredentials: true }
    );
    if (typeof window !== "undefined") {
      window.localStorage.setItem("stlc_auth_profile", JSON.stringify(response.data));
    }
    return response;
  },
  logout: async () => {
    try {
      await api.post("/users/logout");
    } catch {}
    clearAccessToken();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  },
};

export interface Project {
  id: number;
  name: string;
  description?: string;
  status: string;
  ppm_id?: string;
  project_manager_name?: string;
  business_pm_name?: string;
  domain?: string;
  owner_id?: number;
  created_at: string;
  updated_at?: string;
}

export interface UserAccount {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  is_superuser: boolean;
}

export interface ProjectRole {
  role: string;
  permissions: string[];
}

export interface ProjectMembership {
  id: number;
  project_id: number;
  user_id: number;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
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
  jira_issue_type?: string;
  jira_priority?: string;
  acceptance_criteria?: string[];
  business_rules?: string[];
  user_roles?: string[];
  systems_impacted?: string[];
  impacted_interfaces?: string[];
  impacted_products?: string[];
  impacted_channels?: string[];
  ui_pages?: string[];
  apis?: string[];
  dependencies?: string[];
  risks?: string[];
  missing_information?: string[];
  upstream_systems?: string[];
  downstream_systems?: string[];
  api_interface_refs?: string[];
  dependency_systems?: string[];
  telecom_domain?: string;
  qa_domain?: string;
  product_group?: string;
  product?: string;
  sub_request_type?: string;
  risk_level?: string;
  test_phase?: string;
  release_version?: string;
  release_train?: string;
  customer_segment?: string;
  business_process?: string;
  regulatory_impact?: boolean;
  revenue_impact?: boolean;
  customer_impact?: boolean;
  environment_needs?: string;
  test_data_needs?: string;
  nfr_requirements?: string;
  quality_score?: number;
  quality_feedback?: string;
  quality_verdict?: string;
  readiness_status?: string;
  jira_issue_id?: string;
  jira_status?: string;
  jira_assignee?: string;
  jira_reporter?: string;
  jira_labels?: string[];
  jira_components?: string[];
  jira_fix_versions?: string[];
  jira_sprint?: string;
  jira_epic_key?: string;
  jira_last_synced_at?: string;
  sync_status?: string;
  sync_error?: string;
  metadata_?: Record<string, unknown>;
  source_document_id?: number;
  created_by?: number;
  updated_by?: number;
  created_at: string;
  updated_at: string;
}

// GAP-4d: coverage & prioritization analytics
export interface RequirementCoverage {
  requirement_id: number;
  requirement_key: string;
  title: string;
  quality_score?: number | null;
  quality_verdict?: string | null;
  risk_level?: string | null;
  regulatory_impact: boolean;
  revenue_impact: boolean;
  customer_impact: boolean;
  scenario_count: number;
  test_case_count: number;
  automation_candidates: number;
  acceptance_criteria_count: number;
  cases_by_type: Record<string, number>;
  covered_categories: string[];
  missing_categories: string[];
  coverage_score: number;
  gaps: string[];
  priority_score: number;
  priority_band: string;
}

export interface ProjectCoverageSummary {
  project_id: number;
  requirements: Array<Omit<RequirementCoverage, "gaps" | "automation_candidates" | "acceptance_criteria_count" | "cases_by_type" | "regulatory_impact" | "revenue_impact" | "customer_impact"> & { status: string }>;
  summary: {
    total_requirements: number;
    fully_covered: number;
    partially_covered: number;
    uncovered: number;
    avg_coverage_score: number;
  };
}

export interface RequirementStats {
  total: number;
  approved: number;
  needs_clarification: number;
  ready_for_test_planning: number;
  jira_synced: number;
  quality_issues: number;
  high_risk: number;
  missing_ac: number;
}

export interface JiraConnection {
  id: number;
  project_id: number;
  created_by: number;
  jira_base_url: string;
  jira_email: string;
  jira_project_key: string;
  is_active: boolean;
  last_sync_at?: string | null;
  status: string;
  metadata_?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface JiraIssueFilters {
  issue_types?: string[];
  statuses?: string[];
  priorities?: string[];
  labels?: string[];
  assignee?: string;
  text?: string;
  updated_since?: string;
  jql?: string;
}

export interface JiraIssue {
  key: string;
  summary: string;
  description?: string | null;
  issue_type?: string | null;
  status?: string | null;
  priority?: string | null;
  labels: string[];
  updated?: string | null;
  raw: Record<string, unknown>;
}

export interface JiraIssuePage {
  items: JiraIssue[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  jql: string;
}

export interface JiraImportRequirementsResult {
  imported: number;
  created: number;
  updated: number;
  requirement_ids: number[];
}

export interface JiraConnectionTestResult {
  success: boolean;
  message: string;
  account_id?: string | null;
  display_name?: string | null;
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
  created_by?: number;
  created_at: string;
  updated_at: string;
  metadata_?: Record<string, any>;
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
  created_by?: number;
  metadata_?: Record<string, any>;
  created_at: string;
  updated_at?: string;
}

export interface TestCase {
  id: number;
  project_id?: number;
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
  mode: "manual" | "automated" | "hybrid" | "ai";
  execution_mode: "manual" | "automated" | "hybrid" | "ai";
  automation_eligible: "yes" | "no";
  automation_status: "not_required" | "mapping_required" | "ready_for_automation" | "automated" | "automation_failed" | "maintenance_required";
  automation_ready: boolean;
  test_phase?: string | null;
  telecom_domain?: string | null;
  product_group?: string | null;
  product?: string | null;
  sub_request_type?: string | null;
  external_tool?: string | null;
  suite_id?: string | null;
  external_tc_id?: string | null;
  external_tc_url?: string | null;
  automation_script_id?: number | null;
  last_automation_status?: "pending" | "passed" | "failed" | "skipped" | "blocked" | "not_run" | null;
  last_automation_run_at?: string | null;
  last_execution_run_id?: number | null;
  latest_evidence_available: boolean;
  evidence_url?: string | null;
  jira_issue_key?: string;
  jira_issue_id?: string | null;
  jira_url?: string | null;
  jira_final_status?: string | null;
  jira_sync_status: "synced" | "pending" | "failed" | "conflict" | "not_synced";
  jira_last_synced_at?: string | null;
  jira_sync_error?: string | null;
  jira_test_key?: string;
  approval_status: string;
  linked_requirement_id?: number | null;
  linked_requirement_key?: string | null;
  linked_scenario_id?: number | null;
  linked_project_id?: number | null;
  linked_release_version?: string | null;
  linked_test_plan_id?: number | null;
  created_by?: number;
  updated_by?: number | null;
  last_status_updated_by?: number | null;
  last_status_updated_at?: string | null;
  status: string;
  scenario_id?: number;
  requirement_id?: number;
  created_at: string;
  updated_at: string;
}

export interface TestCaseSummary {
  total: number;
  by_status: Record<string, number>;
  by_approval_status: Record<string, number>;
  by_automation_status: Record<string, number>;
  by_mode: Record<string, number>;
  by_jira_sync_status: Record<string, number>;
  by_priority: Record<string, number>;
  by_telecom_domain: Record<string, number>;
}

export interface TestCaseHistory {
  id: number;
  project_id: number;
  test_case_id: number;
  changed_by?: number | null;
  field_name: string;
  old_value?: string | null;
  new_value?: string | null;
  source: string;
  comment?: string | null;
  created_at: string;
}

export interface TestDataItem {
  id: number;
  project_id: number;
  data_id: string;
  name: string;
  description?: string | null;
  data_type: string;
  source_type: string;
  status: string;
  approval_status: string;
  telecom_domain?: string | null;
  test_phase?: string | null;
  product_group?: string | null;
  product?: string | null;
  sub_request_type?: string | null;
  environment?: string | null;
  version: number;
  tags?: string[] | null;
  template_id?: number | null;
  linked_requirement_id?: number | null;
  linked_requirement_key?: string | null;
  linked_test_case_id?: number | null;
  linked_execution_run_id?: number | null;
  linked_jira_issue_key?: string | null;
  linked_jira_url?: string | null;
  linked_defect_id?: number | null;
  data_payload_json?: Record<string, unknown> | null;
  sample_preview_json?: Record<string, unknown> | null;
  sensitive_fields_json?: string[] | null;
  privacy_level: string;
  contains_pii: boolean;
  masking_status: string;
  synthetic_generation_status: string;
  generation_status: string;
  generation_mode?: string | null;
  requested_record_count?: number | null;
  actual_record_count: number;
  external_tool?: string | null;
  external_suite_id?: string | null;
  external_dataset_id?: string | null;
  external_url?: string | null;
  request_notes?: string | null;
  priority?: string | null;
  expected_by_date?: string | null;
  validation_status: string;
  validation_summary_json?: Record<string, unknown> | null;
  import_filename?: string | null;
  reservation_status: string;
  reserved_by?: number | null;
  reserved_for_execution_id?: number | null;
  reservation_expires_at?: string | null;
  consumed_at?: string | null;
  quality_score?: number | null;
  quality_status: string;
  quality_issues_json?: Array<Record<string, unknown>> | null;
  jira_sync_status: string;
  last_synced_at?: string | null;
  sync_error?: string | null;
  created_by: number;
  updated_by?: number | null;
  approved_by?: number | null;
  approved_at?: string | null;
  last_used_at?: string | null;
  usage_count: number;
  agent_run_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface TestDataSummary {
  total_data_sets: number;
  approved: number;
  pending_approval: number;
  synthetic: number;
  masked: number;
  reserved: number;
  expired: number;
  linked_test_cases: number;
  data_quality_issues: number;
  by_status: Record<string, number>;
  by_source_type: Record<string, number>;
  by_reservation_status: Record<string, number>;
  by_quality_status: Record<string, number>;
}

export interface TestDataTemplate {
  id: number;
  project_id: number;
  template_id: string;
  name: string;
  description?: string | null;
  telecom_domain?: string | null;
  test_phase?: string | null;
  data_type: string;
  schema_json?: Record<string, unknown> | null;
  default_generation_rules_json?: Record<string, unknown> | null;
  validation_rules_json?: Record<string, unknown> | null;
  masking_rules_json?: Record<string, unknown> | null;
  is_active: boolean;
  created_by: number;
  updated_by?: number | null;
  created_at: string;
  updated_at: string;
}

export interface TestDataGenerateResponse {
  data_set_id: number;
  data_id: string;
  generation_status: string;
  status: string;
  external_tool?: string | null;
  message: string;
}

export interface TestDataImportPreviewResponse {
  preview_token: string;
  filename: string;
  file_type: string;
  detected_columns: string[];
  row_count: number;
  preview_rows: Array<Record<string, unknown>>;
  validation_errors: Array<Record<string, unknown>>;
  validation_warnings: Array<Record<string, unknown>>;
  can_import: boolean;
}

export interface TestDataImportConfirmResponse {
  data_set_id: number;
  data_id: string;
  imported_record_count: number;
  skipped_record_count: number;
  validation_summary: Record<string, unknown>;
}

export interface RequirementMetrics {
  total: number;
  approved: number;
  pending: number;
  rejected: number;
  completionPercentage: number;
}

export interface TestPlanMetrics {
  total: number;
  approved: number;
  completionPercentage: number;
}

export interface TestCaseMetrics {
  total: number;
  automated: number;
  manual: number;
  automationCoveragePercentage: number;
  testCaseCoveragePercentage: number;
}

export interface TestDataMetrics {
  total: number;
  approved: number;
  pending: number;
  readinessPercentage: number;
}

export interface ExecutionMetrics {
  totalRuns: number;
  completedRuns: number;
  failedRuns: number;
  runningRuns: number;
  passed: number;
  failed: number;
  blocked: number;
  notRun: number;
  completionPercentage: number;
  passRatePercentage: number;
}

export interface DefectMetrics {
  total: number;
  open: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  closurePercentage: number;
}

export interface ReportMetrics {
  total: number;
  published: number;
  completionPercentage: number;
}

export interface ReleaseReadinessMetrics {
  score: number;
  status: string;
  target: number;
  reasons: string[];
}

export interface JiraSyncMetrics {
  syncedCount: number;
  failureCount: number;
  conflictCount: number;
  isHealthy: boolean;
}

export interface DomainQualityMetrics {
  domain: string;
  passRate: number;
  total: number;
  hasData: boolean;
}

export interface PipelineStepMetrics {
  label: string;
  current: number;
  total: number;
  rate: number;
  color: string;
  isDefects?: boolean;
}

export interface DefectChartItem {
  name: string;
  value: number;
  color: string;
}

export interface ExecutionTrendItem {
  name: string;
  Passed: number;
  Failed: number;
  InProgress: number;
}

export interface PendingApprovalItem {
  title: string;
  subtitle: string;
  count: number;
  priority: string;
  priorityColor: string;
}

export interface RecentActivityItem {
  user: string;
  action: string;
  subject: string;
  time: string;
}

export interface DashboardMetrics {
  requirements: RequirementMetrics;
  testPlans: TestPlanMetrics;
  testCases: TestCaseMetrics;
  testData: TestDataMetrics;
  execution: ExecutionMetrics;
  defects: DefectMetrics;
  reports: ReportMetrics;
  releaseReadiness: ReleaseReadinessMetrics;
  jiraSync: JiraSyncMetrics;
  domainQuality: DomainQualityMetrics[];
  pipelineOverview: PipelineStepMetrics[];
  defectChartData: DefectChartItem[];
  executionTrend: ExecutionTrendItem[];
  pendingApprovals: PendingApprovalItem[];
  recentActivities: RecentActivityItem[];
}

// ── Projects ──────────────────────────────────────────────────────────────────

export const projectsApi = {
  list: () => api.get<Project[]>("/projects/"),
  get: (id: number) => api.get<Project>(`/projects/${id}`),
  dashboardMetrics: (projectId: number, releaseVersion?: string) =>
    api.get<DashboardMetrics>(`/projects/${projectId}/dashboard-metrics`, {
      params: releaseVersion ? { release_version: releaseVersion } : undefined,
    }),
  create: (data: { name: string; description?: string }) =>
    api.post<Project>("/projects/", data),
  update: (id: number, data: Partial<Project>) =>
    api.patch<Project>(`/projects/${id}`, data),
  delete: (id: number) => api.delete(`/projects/${id}`),
  roles: () => api.get<ProjectRole[]>("/projects/roles"),
  memberships: (projectId: number) =>
    api.get<ProjectMembership[]>(`/projects/${projectId}/memberships`),
  addMembership: (projectId: number, data: { user_id: number; role: string }) =>
    api.post<ProjectMembership>(`/projects/${projectId}/memberships`, data),
  updateMembership: (projectId: number, membershipId: number, data: { role?: string; is_active?: boolean }) =>
    api.patch<ProjectMembership>(`/projects/${projectId}/memberships/${membershipId}`, data),
  removeMembership: (projectId: number, membershipId: number) =>
    api.delete(`/projects/${projectId}/memberships/${membershipId}`),
};

export const usersApi = {
  list: (params?: { search?: string; skip?: number; limit?: number; project_id?: number }) =>
    api.get<UserAccount[]>("/users/", { params }),
  create: (data: {
    email: string;
    full_name: string;
    password: string;
    role: string;
    is_superuser?: boolean;
  }) => api.post<UserAccount>("/users/", data),
  update: (id: number, data: Partial<Pick<UserAccount, "full_name" | "role" | "is_active" | "is_superuser">>) =>
    api.patch<UserAccount>(`/users/${id}`, data),
  me: () => api.get<UserAccount>("/users/me"),
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
  list: (projectId: number, params?: string | {
    status?: string;
    search?: string;
    telecom_domain?: string;
    risk_level?: string;
    test_phase?: string;
    readiness_status?: string;
    sync_status?: string;
    has_quality_review?: boolean;
    source?: string;
    skip?: number;
    limit?: number;
  }) => {
    const queryParams = typeof params === "string" ? { status: params } : params;
    return api.get<Requirement[]>(`/requirements/project/${projectId}`, {
      params: queryParams,
    });
  },
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
  // GAP-1: vision analysis of an uploaded UI screenshot
  triggerUiAnalysis: (projectId: number, documentId: number, contextNote?: string) =>
    api.post("/requirements/agent/ui-analysis", {
      project_id: projectId,
      document_id: documentId,
      context_note: contextNote,
    }),
  // GAP-2: Playwright + vision analysis of a live portal URL
  triggerUrlAnalysis: (projectId: number, url: string, crawlDepth = 0, contextNote?: string) =>
    api.post("/requirements/agent/url-analysis", {
      project_id: projectId,
      url,
      crawl_depth: crawlDepth,
      context_note: contextNote,
    }),
  // GAP-3: GitHub / local repository code analysis
  triggerCodeAnalysis: (
    projectId: number,
    payload: {
      source: "github" | "local";
      github_url?: string;
      github_branch?: string;
      github_token?: string;
      local_path?: string;
      languages?: string[];
    }
  ) =>
    api.post("/requirements/agent/code-analysis", {
      project_id: projectId,
      ...payload,
    }),
  triggerQuality: (projectId: number, requirementIds?: number[]) =>
    api.post("/requirements/agent/quality", {
      project_id: projectId,
      requirement_ids: requirementIds,
    }),
  stats: (projectId: number) =>
    api.get<RequirementStats>(`/requirements/project/${projectId}/stats`),
  qualityReviews: (reqId: number) =>
    api.get<any[]>(`/requirements/${reqId}/quality-reviews`),
  // GAP-4d: coverage & prioritization analytics
  coverage: (reqId: number) =>
    api.get<RequirementCoverage>(`/requirements/${reqId}/coverage`),
  coverageSummary: (projectId: number) =>
    api.get<ProjectCoverageSummary>(`/requirements/project/${projectId}/coverage-summary`),
};

// ── Test Plans ────────────────────────────────────────────────────────────────

export const jiraApi = {
  listConnections: (projectId: number) =>
    api.get<JiraConnection[]>(`/jira/project/${projectId}/connections`),
  createConnection: (data: {
    project_id: number;
    jira_base_url: string;
    jira_email: string;
    jira_api_token: string;
    jira_project_key: string;
    is_active?: boolean;
  }) => api.post<JiraConnection>("/jira/connections", data),
  updateConnection: (
    id: number,
    data: Partial<Pick<JiraConnection, "jira_base_url" | "jira_email" | "jira_project_key" | "is_active" | "status">> & {
      jira_api_token?: string;
    }
  ) => api.patch<JiraConnection>(`/jira/connections/${id}`, data),
  deleteConnection: (id: number) => api.delete(`/jira/connections/${id}`),
  testConnection: (id: number) =>
    api.post<JiraConnectionTestResult>(`/jira/connections/${id}/test`),
  fetchIssues: (id: number, filters: JiraIssueFilters & { page?: number; page_size?: number }) =>
    api.post<JiraIssuePage>(`/jira/connections/${id}/fetch-issues`, filters),
  importRequirements: (
    id: number,
    filters: JiraIssueFilters & { batch_size?: number; max_issues?: number }
  ) => api.post<JiraImportRequirementsResult>(`/jira/connections/${id}/import-requirements`, filters),
  syncJiraExecutionStatus: (data: {
    test_case_id: number;
    jira_execution_status: string;
    jira_issue_key?: string;
    jira_test_key?: string;
  }) => api.post<JiraExecutionStatus>("/jira/sync-execution-status", data),
  getJiraExecutionStatus: (testCaseId: number) =>
    api.get<JiraExecutionStatus>(`/jira/test-cases/${testCaseId}/execution-status`),
};

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
  generateScenarios: (projectId: number, requirementIds: number[], overrideQualityGate = false) =>
    api.post("/test-plans/agent/generate-scenarios", {
      project_id: projectId,
      requirement_ids: requirementIds,
      override_quality_gate: overrideQualityGate,
    }),
  exportDocx: (id: number) =>
    api.get(`/test-plans/${id}/export/docx`, { responseType: "blob" }),
};

// ── Test Scenarios ────────────────────────────────────────────────────────────

export const scenariosApi = {
  list: (projectId: number, requirementId?: number) =>
    api.get<TestScenario[]>(`/test-plans/scenarios/project/${projectId}`, {
      params: requirementId ? { requirement_id: requirementId } : undefined,
    }),
  approve: (scenarioId: number, action: "approve" | "reject", notes?: string) =>
    api.post<TestScenario>(`/test-plans/scenarios/${scenarioId}/approve`, { action, notes }),
};

// ── Test Cases ────────────────────────────────────────────────────────────────

export const testCasesApi = {
  list: (projectId: number, params?: { scenario_id?: number; requirement_id?: number; status?: string; automation_only?: boolean }) =>
    api.get<TestCase[]>(`/test-cases/projects/${projectId}`, { params }),
  summary: (projectId: number) =>
    api.get<TestCaseSummary>(`/test-cases/projects/${projectId}/summary`),
  get: (id: number) => api.get<TestCase>(`/test-cases/${id}`),
  update: (id: number, data: Partial<TestCase>) =>
    api.patch<TestCase>(`/test-cases/${id}`, data),
  approve: (id: number, action: "approve" | "reject", notes?: string) =>
    api.post<TestCase>(`/test-plans/cases/${id}/approve`, { action, notes }),
  history: (id: number) => api.get<TestCaseHistory[]>(`/test-cases/${id}/history`),
  syncJira: (id: number) => api.post<{ test_case_id: number; status: string; sync_job_id?: number; task_id?: string }>(`/test-cases/${id}/sync-jira`),
  generateCases: (projectId: number, scenarioIds?: number[], requirementIds?: number[], overrideQualityGate = false) =>
    api.post("/test-plans/agent/generate-cases", {
      project_id: projectId,
      scenario_ids: scenarioIds,
      requirement_ids: requirementIds,
      override_quality_gate: overrideQualityGate,
    }),
};

export const testDataApi = {
  list: (projectId: number, params?: { status?: string; source_type?: string; reservation_status?: string }) =>
    api.get<TestDataItem[]>(`/test-data/projects/${projectId}`, { params }),
  summary: (projectId: number) =>
    api.get<TestDataSummary>(`/test-data/projects/${projectId}/summary`),
  get: (id: number) => api.get<TestDataItem>(`/test-data/${id}`),
  create: (projectId: number, data: {
    name: string;
    description?: string;
    data_type: string;
    source_type?: string;
    telecom_domain?: string;
    test_phase?: string;
    product_group?: string;
    product?: string;
    sub_request_type?: string;
    environment?: string;
    privacy_level?: string;
    contains_pii?: boolean;
    test_case_id?: number;
    requirement_id?: number;
    template_id?: number;
    tags?: string[];
    data_payload_json?: Record<string, unknown>;
    sensitive_fields_json?: string[];
    validation_rules_json?: Record<string, unknown>;
    masking_rules_json?: Record<string, unknown>;
    submit_for_approval?: boolean;
    notes?: string;
  }) => api.post<TestDataItem>(`/test-data/projects/${projectId}`, data),
  generate: (projectId: number, data: {
    name: string;
    linked_requirement_id?: number;
    linked_test_case_id?: number;
    telecom_domain: string;
    test_phase: string;
    product_group?: string;
    product?: string;
    sub_request_type?: string;
    environment: string;
    data_type: string;
    number_of_records: number;
    generation_mode: "positive" | "negative" | "boundary" | "invalid" | "mixed";
    external_tool: string;
    external_suite_id?: string;
    external_dataset_id?: string;
    external_url?: string;
    request_notes?: string;
    priority?: string;
    expected_by_date?: string;
  }) => api.post<TestDataGenerateResponse>(`/test-data/projects/${projectId}/generate`, data),
  importPreview: (projectId: number, data: {
    file: File;
    name?: string;
    data_type: string;
    telecom_domain: string;
    test_phase: string;
    product_group?: string;
    product?: string;
    sub_request_type?: string;
    environment: string;
    contains_pii: boolean;
    privacy_level: string;
    linked_requirement_id?: number;
    linked_test_case_id?: number;
    import_mode: "create_new_dataset" | "append_to_existing_dataset";
    existing_data_set_id?: number;
    validate_before_import?: boolean;
  }) => {
    const form = new FormData();
    form.append("file", data.file);
    if (data.name) form.append("name", data.name);
    form.append("data_type", data.data_type);
    form.append("telecom_domain", data.telecom_domain);
    form.append("test_phase", data.test_phase);
    if (data.product_group) form.append("product_group", data.product_group);
    if (data.product) form.append("product", data.product);
    if (data.sub_request_type) form.append("sub_request_type", data.sub_request_type);
    form.append("environment", data.environment);
    form.append("contains_pii", String(data.contains_pii));
    form.append("privacy_level", data.privacy_level);
    if (data.linked_requirement_id) form.append("linked_requirement_id", String(data.linked_requirement_id));
    if (data.linked_test_case_id) form.append("linked_test_case_id", String(data.linked_test_case_id));
    form.append("import_mode", data.import_mode);
    if (data.existing_data_set_id) form.append("existing_data_set_id", String(data.existing_data_set_id));
    form.append("validate_before_import", String(data.validate_before_import ?? true));
    return api.post<TestDataImportPreviewResponse>(`/test-data/projects/${projectId}/import/preview`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  importConfirm: (projectId: number, preview_token: string) =>
    api.post<TestDataImportConfirmResponse>(`/test-data/projects/${projectId}/import/confirm`, { preview_token }),
  update: (id: number, data: Partial<TestDataItem>) =>
    api.patch<TestDataItem>(`/test-data/${id}`, data),
  validate: (id: number) =>
    api.post<{ data_id: number; quality_score: number; quality_status: string; quality_issues_json: Array<Record<string, unknown>> }>(`/test-data/${id}/validate`),
  mask: (id: number, data?: { fields?: string[]; keep_last?: number }) =>
    api.post<TestDataItem>(`/test-data/${id}/mask`, data ?? {}),
  reserve: (id: number, data?: { reserved_for_execution_id?: number; duration_minutes?: number }) =>
    api.post<TestDataItem>(`/test-data/${id}/reserve`, data ?? {}),
  release: (id: number) =>
    api.post<TestDataItem>(`/test-data/${id}/release`),
  consume: (id: number) =>
    api.post<TestDataItem>(`/test-data/${id}/consume`),
  submit: (id: number, notes?: string) =>
    api.post<TestDataItem>(`/test-data/${id}/submit`, { notes }),
  approve: (id: number, notes?: string) =>
    api.post<TestDataItem>(`/test-data/${id}/approve`, { notes }),
  reject: (id: number, notes?: string) =>
    api.post<TestDataItem>(`/test-data/${id}/reject`, { notes }),
  history: (id: number) =>
    api.get<Array<{ id: number; action_type: string; decision: string; notes?: string | null; user_id: number; actor_role?: string | null; old_value?: Record<string, unknown> | null; new_value?: Record<string, unknown> | null; created_at: string }>>(`/test-data/${id}/history`),
  listTemplates: (projectId: number) =>
    api.get<TestDataTemplate[]>(`/test-data/templates/projects/${projectId}`),
  createTemplate: (projectId: number, data: {
    name: string;
    description?: string;
    telecom_domain?: string;
    test_phase?: string;
    data_type?: string;
    schema_json?: Record<string, unknown>;
    default_generation_rules_json?: Record<string, unknown>;
    validation_rules_json?: Record<string, unknown>;
    masking_rules_json?: Record<string, unknown>;
    is_active?: boolean;
  }) => api.post<TestDataTemplate>(`/test-data/templates/projects/${projectId}`, data),
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

export interface AutomationTestMapping {
  id: number;
  project_id: number;
  test_case_id: number;
  external_tool_name: string;
  external_project_id?: string | null;
  external_suite_id?: string | null;
  external_test_case_id: string;
  external_script_id?: string | null;
  automation_status: string;
  is_active: boolean;
  last_synced_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExternalAutomationRunResult {
  execution_run_id: number;
  external_run_id: string;
  status: string;
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  skipped_tests: number;
  message: string;
}

export interface JiraExecutionStatus {
  test_case_id: number;
  jira_issue_key?: string | null;
  jira_test_key?: string | null;
  jira_execution_status?: string | null;
  final_qa_status: string;
  source: string;
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
  createAutomationMapping: (data: {
    project_id: number;
    test_case_id: number;
    external_tool_name: string;
    external_project_id?: string;
    external_suite_id?: string;
    external_test_case_id: string;
    external_script_id?: string;
    automation_status?: string;
    is_active?: boolean;
  }) => api.post<AutomationTestMapping>("/automation/mappings", data),
  getAutomationMappings: (projectId: number, params?: { test_case_id?: number; active_only?: boolean }) =>
    api.get<AutomationTestMapping[]>("/automation/mappings", { params: { project_id: projectId, ...params } }),
  updateAutomationMapping: (mappingId: number, data: Partial<AutomationTestMapping>) =>
    api.put<AutomationTestMapping>(`/automation/mappings/${mappingId}`, data),
  deleteAutomationMapping: (mappingId: number) =>
    api.delete<AutomationTestMapping>(`/automation/mappings/${mappingId}`),
  runExternalAutomation: (projectId: number, testCaseIds: number[], environment: string = "staging") =>
    api.post<ExternalAutomationRunResult>("/automation/external/run", {
      project_id: projectId,
      test_case_ids: testCaseIds,
      environment,
    }),
  syncExternalAutomationResult: (mappingId: number, environment: string = "staging") =>
    api.post<ExternalAutomationRunResult>("/automation/external/sync-result", {
      mapping_id: mappingId,
      environment,
    }),
  getExecutionHistory: (testCaseId: number) =>
    api.get<ExecutionResult[]>(`/automation/test-cases/${testCaseId}/execution-history`),
  syncJiraExecutionStatus: (data: {
    test_case_id: number;
    jira_execution_status: string;
    jira_issue_key?: string;
    jira_test_key?: string;
  }) => api.post<JiraExecutionStatus>("/automation/jira/sync-execution-status", data),
  getJiraExecutionStatus: (testCaseId: number) =>
    api.get<JiraExecutionStatus>(`/automation/jira/test-cases/${testCaseId}/execution-status`),
};

// ── Execution ─────────────────────────────────────────────────────────────────

export interface ExecutionResult {
  id: number;
  execution_run_id: number;
  test_case_id?: number;
  automation_mapping_id?: number;
  test_name: string;
  status: string;
  duration_ms?: number;
  execution_mode?: string;
  external_tool_name?: string;
  external_test_case_id?: string;
  automation_execution_status?: string;
  manual_execution_status?: string;
  jira_execution_status?: string;
  duration_seconds?: number;
  error_message?: string;
  stack_trace?: string;
  screenshot_url?: string;
  video_url?: string;
  log_url?: string;
  external_result_url?: string;
  jira_issue_key?: string;
  jira_test_key?: string;
  raw_result_json?: Record<string, unknown>;
  logs?: string[];
  created_at: string;
  updated_at: string;
}

export interface ExecutionRun {
  id: number;
  project_id: number;
  execution_id: string;
  test_cycle_id?: string | null;
  source_type?: string | null;
  external_tool_name?: string | null;
  external_run_id?: string | null;
  suite_name?: string;
  environment?: string;
  status: string;
  triggered_by?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
  total_tests: number;
  passed: number;
  failed: number;
  skipped: number;
  execution_logs?: unknown[];
  allure_report_path?: string | null;
  agent_run_id?: number | null;
  metadata_?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export const executionApi = {
  listRuns: (projectId: number, params?: { status?: string }) =>
    api.get<ExecutionRun[]>(`/execution/project/${projectId}`, { params }),
  getRun: (id: number) => api.get<ExecutionRun>(`/execution/${id}`),
  getResults: (runId: number) => api.get<ExecutionResult[]>(`/execution/${runId}/results`),
  runTests: (projectId: number, testCaseIds: number[], environment: string = "staging", suiteName?: string, sourceType?: string) =>
    api.post("/execution/agent/run-tests", {
      project_id: projectId,
      test_case_ids: testCaseIds,
      environment,
      suite_name: suiteName,
      source_type: sourceType,
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
  agent_run_id?: number | null;
  metadata_?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface JiraDefect {
  id: number;
  defect_draft_id: number;
  project_id: number;
  jira_issue_key: string;
  jira_url?: string | null;
  jira_status: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export const defectsApi = {
  list: (projectId: number, params?: { status?: string }) =>
    api.get<DefectDraft[]>(`/defects/project/${projectId}`, { params }),
  get: (id: number) => api.get<DefectDraft>(`/defects/${id}`),
  create: (data: Omit<Partial<DefectDraft>, "id" | "defect_id" | "status" | "created_at" | "updated_at"> & { project_id: number; summary: string }) =>
    api.post<DefectDraft>("/defects/", data),
  update: (id: number, data: Partial<DefectDraft>) =>
    api.patch<DefectDraft>(`/defects/${id}`, data),
  approve: (id: number, action: "approve" | "reject", notes?: string) =>
    api.post<DefectDraft>(`/defects/${id}/approve`, { action, notes }),
  pushToJira: (id: number) => api.post<JiraDefect>(`/defects/${id}/push-to-jira`),
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
  progress_percent?: number;
  progress_message?: string;
  output_data?: Record<string, unknown>;
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

// ── GAP-5: Traceability + Export ─────────────────────────────────────────────

export interface TraceabilityChainItem {
  id: number;
  ref?: string | null;
  title: string;
  status?: string | null;
}

export interface TraceabilityMatrixRow {
  requirement: TraceabilityChainItem;
  test_cases: TraceabilityChainItem[];
  execution_results: TraceabilityChainItem[];
  defects: TraceabilityChainItem[];
  gaps: string[];
}

export interface TraceabilityMatrixOut {
  items: TraceabilityMatrixRow[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  include_drafts: boolean;
}

export interface CoverageGapsOut {
  project_id: number;
  include_drafts: boolean;
  no_test_cases: number[];
  no_execution: number[];
  undecided_failures: number[];
}

export interface RequirementTraceabilityScenario {
  id: number;
  scenario_id: string;
  title: string;
  scenario_type: string;
  priority: string;
  status: string;
}

export interface RequirementTraceabilityTestCase {
  id: number;
  test_case_id: string;
  title: string;
  test_type?: string | null;
  priority: string;
  status: string;
  automation_candidate: boolean;
  scenario_id?: number | null;
  jira_issue_key?: string | null;
}

export interface RequirementTraceabilityExecution {
  id: number;
  test_case_id?: number | null;
  test_name: string;
  status: string;
  execution_mode?: string | null;
  created_at?: string | null;
}

export interface RequirementTraceabilityDefect {
  id: number;
  defect_id: string;
  summary: string;
  severity: string;
  priority: string;
  status: string;
  jira_ready: boolean;
}

export interface RequirementTraceabilityChain {
  requirement: {
    id: number;
    requirement_id: string;
    title: string;
    status: string;
    risk_level?: string | null;
    telecom_domain?: string | null;
    quality_score?: number | null;
    quality_verdict?: string | null;
  };
  scenarios: RequirementTraceabilityScenario[];
  test_cases: RequirementTraceabilityTestCase[];
  execution_results: RequirementTraceabilityExecution[];
  defects: RequirementTraceabilityDefect[];
  summary: {
    scenario_count: number;
    test_case_count: number;
    execution_count: number;
    defect_count: number;
    gaps: string[];
  };
}

export interface ApprovalAction {
  id: number;
  project_id: number;
  user_id: number;
  action_type: string;
  entity_type: string;
  entity_id: number;
  decision: string;
  notes?: string;
  changes_requested?: Record<string, any>;
  source: string;
  actor_role?: string;
  old_value?: Record<string, any>;
  new_value?: Record<string, any>;
  jira_issue_key?: string;
  correlation_id?: string;
  request_id?: string;
  agent_run_id?: number;
  metadata_?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export const traceabilityApi = {
  /** Full paginated matrix for a project. */
  matrix: (
    projectId: number,
    params?: { page?: number; page_size?: number; domain?: string; phase?: string; release?: string; include_drafts?: boolean }
  ) =>
    api.get<TraceabilityMatrixOut>(`/traceability/projects/${projectId}/matrix`, { params }),

  /** Coverage gap IDs for a project. */
  gaps: (projectId: number, include_drafts = false) =>
    api.get<CoverageGapsOut>(`/traceability/projects/${projectId}/gaps`, { params: { include_drafts } }),

  /** Full traceability chain for a single requirement. */
  requirementChain: (requirementId: number) =>
    api.get<RequirementTraceabilityChain>(`/traceability/requirements/${requirementId}/chain`),

  /** Approval actions list for a project. */
  approvals: (projectId: number, params?: { entity_type?: string; entity_id?: number; page?: number; page_size?: number }) =>
    api.get<ApprovalAction[]>(`/traceability/projects/${projectId}/approvals`, { params }),
};

/** Trigger a file download from a Blob URL. */
function _triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const exportApi = {
  /**
   * Download test cases export.
   * format: "excel" | "csv" | "xray"
   * Edge cases: empty project → valid empty file; null fields → blank cells.
   */
  downloadTestCases: async (
    projectId: number,
    format: "excel" | "csv" | "xray" = "excel",
    include_drafts = false,
  ) => {
    const response = await api.get(
      `/traceability/projects/${projectId}/export/test-cases`,
      { params: { format, include_drafts }, responseType: "blob" }
    );
    const ext = format === "excel" ? "xlsx" : "csv";
    const suffix = format === "xray" ? "_xray" : "";
    _triggerDownload(response.data as Blob, `test_cases_project_${projectId}${suffix}.${ext}`);
  },

  /**
   * Download the traceability matrix export.
   * format: "excel" | "csv"
   * Excel includes Matrix + Summary sheets.
   */
  downloadTraceabilityMatrix: async (
    projectId: number,
    format: "excel" | "csv" = "excel",
    include_drafts = false,
  ) => {
    const response = await api.get(
      `/traceability/projects/${projectId}/export/traceability-matrix`,
      { params: { format, include_drafts }, responseType: "blob" }
    );
    const ext = format === "excel" ? "xlsx" : "csv";
    _triggerDownload(response.data as Blob, `traceability_matrix_project_${projectId}.${ext}`);
  },
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
