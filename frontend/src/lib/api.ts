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

// The backend rotates the refresh token on every use and rejects reuse of an
// already-rotated token. Several requests can 401 at once (e.g. multiple
// components fetching on mount after the access token expires), so all of
// them must share a single in-flight refresh call — otherwise the 2nd+
// caller presents an already-rotated refresh token and gets treated as a
// replay attack, wiping both cookies and forcing a spurious logout.
let refreshPromise: Promise<unknown> | null = null;

// Global response interceptor — automatically attempts cookie refresh on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    normalizeAxiosError(error);
    const originalConfig = error.config as RetriableRequestConfig | undefined;
    if (error?.response?.status === 401 && originalConfig && !originalConfig._retry && !originalConfig.url?.includes("/users/token")) {
      originalConfig._retry = true;
      try {
        if (!refreshPromise) {
          refreshPromise = axios
            .post("/api/v1/users/refresh", {}, { withCredentials: true })
            .finally(() => {
              refreshPromise = null;
            });
        }
        await refreshPromise;
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

export interface RegisterPayload {
  email: string;
  full_name: string;
  password: string;
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
  ldapLogin: async (username: string, password: string, domain: string) => {
    const response = await api.post<TokenResponse>(
      "/resource-operations/ldap-login",
      { username, password, domain }
    );
    if (typeof window !== "undefined") {
      window.localStorage.setItem("stlc_auth_profile", JSON.stringify(response.data));
    }
    return response;
  },
  register: async (payload: RegisterPayload) =>
    api.post("/users/register", payload),
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
  generation_notes?: string;
  quality_score?: number;
  quality_feedback?: string;
  quality_verdict?: string;
  readiness_status?: string;
  review_notes?: string;
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
  // Current canonical values are: "manual" | "automation" | "ai". Legacy values
  // ("automated", "hybrid") are kept in the union so existing records read from
  // the backend continue to typecheck while the UI migrates.
  execution_mode: "manual" | "automation" | "ai" | "automated" | "hybrid";
  automation_eligible: "yes" | "no";
  // Current canonical values: planned_for_automation | ready_for_automation |
  // automated | awaiting_qa_approval. Legacy values retained for existing rows.
  automation_status:
    | "planned_for_automation"
    | "ready_for_automation"
    | "automated"
    | "awaiting_qa_approval"
    | "not_required"
    | "mapping_required"
    | "automation_failed"
    | "maintenance_required";
  automation_ready: boolean;
  // Phase 5: per-TC AI assistance state.
  ai_assistance_status?:
    | "disabled"
    | "enabled"
    | "recommendation_pending"
    | "approved"
    | "rejected";
  test_phase?: string | null;
  telecom_domain?: string | null;
  product_group?: string | null;
  product?: string | null;
  sub_request_type?: string | null;
  // Which application/channel under test this test case targets. Null falls
  // back to the project's default ProjectApplication at script-generation/
  // execution time — see /projects/{id}/applications.
  application_id?: number | null;
  external_tool?: string | null;
  // Free-text suite/test-set ID from an *external* tool (Xray/Zephyr) synced
  // via automation mappings — distinct from the internal Test Suite below.
  suite_id?: string | null;
  test_suite_id?: number | null;
  test_suite_name?: string | null;
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
  version: number;
  metadata_?: Record<string, unknown>;
  agent_run_id?: number | null;
  scenario_id?: number;
  requirement_id?: number;
  created_at: string;
  updated_at: string;
}

export type ApplicationLifecycleStatus = "draft" | "active" | "deprecated" | "retired";

export interface ProjectApplication {
  id?: number | null;
  project_id: number;
  key: string;
  name: string;
  description?: string | null;
  is_default: boolean;
  environment_urls: Record<string, string>;
  is_active: boolean;
  application_type?: string | null;
  aliases: string[];
  lifecycle_status: ApplicationLifecycleStatus;
  business_owner_id?: number | null;
  technical_owner_id?: number | null;
  domain?: string | null;
  product_group?: string | null;
  product?: string | null;
  channel?: string | null;
  created_by?: number | null;
  updated_by?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProjectApplicationUpdatePayload {
  key: string;
  name: string;
  description?: string | null;
  is_default?: boolean;
  environment_urls?: Record<string, string>;
  is_active?: boolean;
  application_type?: string | null;
  aliases?: string[];
  lifecycle_status?: ApplicationLifecycleStatus;
  business_owner_id?: number | null;
  technical_owner_id?: number | null;
  domain?: string | null;
  product_group?: string | null;
  product?: string | null;
  channel?: string | null;
}

export interface ProjectExternalDependency {
  id?: number | null;
  project_id: number;
  application_id?: number | null;
  service_name: string;
  note?: string | null;
  sandbox_url?: string | null;
  mock_strategy: "intercept" | "sandbox" | "ignore";
  is_active: boolean;
  created_by?: number | null;
  updated_by?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProjectExternalDependencyUpdatePayload {
  id?: number | null;
  application_id?: number | null;
  service_name: string;
  note?: string | null;
  sandbox_url?: string | null;
  mock_strategy?: "intercept" | "sandbox" | "ignore";
  is_active?: boolean;
}

export interface ProjectApplicationsResponse {
  project_id: number;
  applications: ProjectApplication[];
  external_dependencies: ProjectExternalDependency[];
  available_environments: string[];
  last_updated?: string | null;
  updated_by?: number | null;
}

export interface ApplicationMappingConflict {
  product_group?: string | null;
  product?: string | null;
  channel?: string | null;
  application_ids: number[];
}

export interface ProjectApplicationsSummary {
  project_id: number;
  total_applications: number;
  active_applications: number;
  discovery_ready: number;
  discovery_ready_is_proxy: boolean;
  environment_gaps: number;
  mapping_conflicts: ApplicationMappingConflict[];
  health_tracked: boolean;
  mapping_usage: Record<number, number>;
}

export interface ProjectSettingAuditLogEntry {
  id: number;
  project_id: number;
  setting_type: string;
  old_value: Record<string, any> | null;
  new_value: Record<string, any> | null;
  changed_by: number | null;
  changed_at: string;
  source: string;
  change_reason: string | null;
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

export const applicationsApi = {
  getForProject: (projectId: number) =>
    api.get<ProjectApplicationsResponse>(`/projects/${projectId}/applications`),
  summary: (projectId: number) =>
    api.get<ProjectApplicationsSummary>(`/projects/${projectId}/applications/summary`),
  update: (projectId: number, applications: ProjectApplicationUpdatePayload[], changeReason?: string) =>
    api.put<ProjectApplicationsResponse>(`/projects/${projectId}/applications`, {
      applications,
      change_reason: changeReason,
    }),
  updateDependencies: (
    projectId: number,
    dependencies: ProjectExternalDependencyUpdatePayload[],
    changeReason?: string
  ) =>
    api.put<ProjectApplicationsResponse>(`/projects/${projectId}/external-dependencies`, {
      dependencies,
      change_reason: changeReason,
    }),
  seedCanonical: (projectId: number) =>
    api.post<ProjectApplicationsResponse>(`/projects/${projectId}/applications/seed-canonical`, {}),
  auditLog: (projectId: number) =>
    api.get<ProjectSettingAuditLogEntry[]>(`/projects/${projectId}/applications/audit-log`),
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
  transition: (id: number, action: "send_to_analysis" | "send_to_traceability" | "send_to_review" | "send_back_to_analysis" | "send_back_to_traceability" | "request_clarification" | "resolve_clarification", notes?: string) =>
    api.post<Requirement>(`/requirements/${id}/transition`, { action, notes }),
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
  delete: (id: number) => api.delete(`/test-plans/${id}`),
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
  approve: (scenarioId: number, action: "approve" | "reject", notes?: string, overrideReviewGate = false) =>
    api.post<TestScenario>(`/test-plans/scenarios/${scenarioId}/approve`, {
      action,
      notes,
      override_review_gate: overrideReviewGate,
    }),
};

// ── Test Cases ────────────────────────────────────────────────────────────────

export const testCasesApi = {
  list: (projectId: number, params?: { scenario_id?: number; requirement_id?: number; status?: string; automation_only?: boolean }) =>
    api.get<TestCase[]>(`/test-cases/projects/${projectId}`, { params }),
  summary: (projectId: number) =>
    api.get<TestCaseSummary>(`/test-cases/projects/${projectId}/summary`),
  get: (id: number) => api.get<TestCase>(`/test-cases/${id}`),
  update: (id: number, data: Partial<TestCase> & { comment?: string }) =>
    api.patch<TestCase>(`/test-cases/${id}`, data),
  approve: (id: number, action: "approve" | "reject", notes?: string, overrideReviewGate = false) =>
    api.post<TestCase>(`/test-plans/cases/${id}/approve`, {
      action,
      notes,
      override_review_gate: overrideReviewGate,
    }),
  history: (id: number) => api.get<TestCaseHistory[]>(`/test-cases/${id}/history`),
  syncJira: (id: number) => api.post<{ test_case_id: number; status: string; sync_job_id?: number; task_id?: string }>(`/test-cases/${id}/sync-jira`),
  generateCases: (projectId: number, scenarioIds?: number[], requirementIds?: number[], overrideQualityGate = false) =>
    api.post("/test-plans/agent/generate-cases", {
      project_id: projectId,
      scenario_ids: scenarioIds,
      requirement_ids: requirementIds,
      override_quality_gate: overrideQualityGate,
    }),
  /**
   * Apply the same field patch to many test cases in one transaction.
   * Always call once with `dry_run: true` to preview diffs + conflicts, then
   * call again with `dry_run: false` (and the same `reason`) to commit.
   */
  bulkUpdate: (
    projectId: number,
    payload: {
      test_case_ids: number[];
      patch: {
        execution_mode?: string;
        automation_status?: string;
        automation_ready?: boolean;
        external_tool?: string;
        suite_id?: string;
        external_tc_id?: string;
      };
      reason: string;
      dry_run: boolean;
    },
  ) => api.post<TestCaseBulkUpdateResult>(`/test-cases/projects/${projectId}/bulk-update`, payload),
};

// ── Test Automation Classification & Routing (P1-S3 extension) ──────────────
// Governed, policy-driven automation-candidate classification. Every field
// here is either persisted from the deterministic rules engine, the
// governed classification agent, or a human reviewer/approver — never a
// static frontend list. See docs/test-automation-classification-routing-
// implementation-prompt.md. Disabled server-side unless
// AUTOMATION_CLASSIFICATION_ENABLED=true (every route 404s).

export type AutomationCandidateStatus =
  | "NOT_EVALUATED"
  | "RECOMMENDED"
  | "CONDITIONAL"
  | "NOT_RECOMMENDED"
  | "BLOCKED"
  | "DEFERRED"
  | "APPROVED"
  | "POLICY_STALE"
  | "RECLASSIFICATION_REQUIRED";

export type ClassificationReviewStatus =
  | "PENDING_REVIEW"
  | "CHANGES_REQUESTED"
  | "REVIEWED"
  | "APPROVED"
  | "REJECTED";

export interface ClassificationRuleFinding {
  code: string;
  label: string;
  detail: string;
}

export interface ScoreFactor {
  factor: string;
  weight: number;
  score: number;
  category?: string | null;
}

export interface AutomationClassificationPolicy {
  id: number;
  project_id: number | null;
  application_id: number | null;
  code: string;
  name: string;
  version: number;
  parent_policy_id: number | null;
  status: "draft" | "published" | "archived";
  rules: Record<string, unknown>;
  created_by?: number | null;
  published_by?: number | null;
  published_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TestCaseAutomationClassification {
  id: number;
  project_id: number;
  test_case_id: number;
  test_case_version: number;
  version: number;
  parent_classification_id: number | null;
  is_current: boolean;
  candidate_status: AutomationCandidateStatus;
  primary_adapter: string | null;
  supporting_adapters: string[];
  mandatory_validators: string[];
  optional_validators: string[];
  discovery_required: boolean;
  recommended_discovery_mode: "GUIDED_USER" | "FREE_USER_ACTION" | "SUPERVISED_AGENT" | null;
  complexity_score: number | null;
  automation_value_score: number | null;
  score_factors: ScoreFactor[];
  required_evidence: string[];
  required_capabilities: string[];
  deterministic_blockers: ClassificationRuleFinding[];
  advisory_warnings: unknown[];
  matched_rules: unknown[];
  policy_id: number | null;
  policy_version: number | null;
  agent_run_id: number | null;
  review_status: ClassificationReviewStatus;
  reviewed_by: number | null;
  reviewed_at: string | null;
  approved_by: number | null;
  approved_at: string | null;
  decision_reason: string | null;
  created_at: string;
  updated_at: string;
  is_stale: boolean;
}

export interface ClassificationPolicySimulateResponse {
  policy: AutomationClassificationPolicy;
  deterministic_blockers: ClassificationRuleFinding[];
  deterministic_warnings: ClassificationRuleFinding[];
  routing_default_adapter: string | null;
  routing_default_mandatory_validators: string[];
  routing_default_optional_validators: string[];
}

export interface ClassificationEvaluateResponseItem {
  test_case_id: number;
  agent_run_id: number;
  status: string;
}

export const automationClassificationApi = {
  // Every route 404s when AUTOMATION_CLASSIFICATION_ENABLED is off — callers
  // should treat a 404 from listForProject as "feature disabled, show
  // Not Evaluated" rather than a hard load error (see isClassificationDisabled).
  listForProject: (projectId: number) =>
    api.get<TestCaseAutomationClassification[]>(`/automation-classifications/projects/${projectId}`),
  effectivePolicy: (projectId: number, applicationId?: number) =>
    api.get<AutomationClassificationPolicy>(`/automation-classifications/projects/${projectId}/policies/effective`, {
      params: applicationId ? { application_id: applicationId } : undefined,
    }),
  simulatePolicy: (projectId: number, testCaseId: number) =>
    api.post<ClassificationPolicySimulateResponse>(`/automation-classifications/projects/${projectId}/policies/simulate`, {
      test_case_id: testCaseId,
    }),
  evaluate: (projectId: number, testCaseIds: number[]) =>
    api.post<{ project_id: number; results: ClassificationEvaluateResponseItem[] }>(
      `/automation-classifications/projects/${projectId}/evaluate`,
      { test_case_ids: testCaseIds },
    ),
  getForTestCase: (testCaseId: number) =>
    api.get<TestCaseAutomationClassification>(`/automation-classifications/test-cases/${testCaseId}`),
  get: (classificationId: number) =>
    api.get<TestCaseAutomationClassification>(`/automation-classifications/${classificationId}`),
  review: (classificationId: number, corrections: Record<string, unknown>, reason?: string) =>
    api.post<TestCaseAutomationClassification>(`/automation-classifications/${classificationId}/review`, {
      corrections,
      reason,
    }),
  reclassify: (classificationId: number) =>
    api.post<ClassificationEvaluateResponseItem>(`/automation-classifications/${classificationId}/reclassify`),
  approve: (classificationId: number, reason?: string) =>
    api.post<TestCaseAutomationClassification>(`/automation-classifications/${classificationId}/approve`, { reason }),
  approveConditional: (classificationId: number, reason: string) =>
    api.post<TestCaseAutomationClassification>(`/automation-classifications/${classificationId}/approve-conditional`, { reason }),
  reject: (classificationId: number, reason: string) =>
    api.post<TestCaseAutomationClassification>(`/automation-classifications/${classificationId}/reject`, { reason }),
  defer: (classificationId: number, reason: string) =>
    api.post<TestCaseAutomationClassification>(`/automation-classifications/${classificationId}/defer`, { reason }),
  requestChanges: (classificationId: number, reason: string) =>
    api.post<TestCaseAutomationClassification>(`/automation-classifications/${classificationId}/request-changes`, { reason }),
};

// True when an automation-classification call 404'd because the feature
// flag is off (isolated-namespace pattern, same as grounded_automation) —
// distinct from a real load failure the UI should surface as an error.
export function isClassificationDisabled(error: unknown): boolean {
  return (error as { response?: { status?: number } } | undefined)?.response?.status === 404;
}

// ── Test Suites ─────────────────────────────────────────────────────────────────
// A named tag test cases are assigned to via `TestCase.test_suite_id` — one
// suite per test case, edited the same way as Test Environment/Telecom Domain.

export interface TestSuite {
  id: number;
  project_id: number;
  name: string;
  description?: string;
  environment?: string;
  status: string;
  case_count: number;
  created_by?: number;
  updated_by?: number;
  created_at: string;
  updated_at: string;
}

export const testSuitesApi = {
  list: (projectId: number) => api.get<TestSuite[]>(`/test-suites/project/${projectId}`),
  get: (id: number) => api.get<TestSuite>(`/test-suites/${id}`),
  create: (data: { project_id: number; name: string; description?: string; environment?: string }) =>
    api.post<TestSuite>("/test-suites", data),
  update: (id: number, data: { name?: string; description?: string; environment?: string; status?: "active" | "archived" }) =>
    api.patch<TestSuite>(`/test-suites/${id}`, data),
  delete: (id: number) => api.delete(`/test-suites/${id}`),
};

export interface TestCaseBulkRowOutcome {
  test_case_id: number;
  test_case_key?: string | null;
  title?: string | null;
  outcome: "updated" | "skipped" | "conflict" | "not_found" | "forbidden" | string;
  changes: Record<string, { old: unknown; new: unknown }>;
  conflict_reason?: string | null;
}

export interface TestCaseBulkUpdateResult {
  requested: number;
  updated: number;
  skipped: number;
  conflicts: number;
  not_found: number;
  forbidden: number;
  dry_run: boolean;
  rows: TestCaseBulkRowOutcome[];
}

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
    // Only consumed when external_tool === "Faker". Shape:
    //   { locale: "en_US", fields: [{ name, provider, params? }, ...] }
    schema_json?: Record<string, unknown>;
  }) => api.post<TestDataGenerateResponse>(`/test-data/projects/${projectId}/generate`, data),
  listBindableRecords: (projectId: number, params?: { test_case_id?: number; limit?: number }) =>
    api.get<Array<{
      record_id: number;
      record_key: string;
      data_set_id: number;
      data_set_name: string;
      data_set_data_id: string;
      test_case_id: number | null;
      preview_keys: string[];
      approval_status: string;
    }>>(`/test-data/projects/${projectId}/records`, { params }),
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

export interface StaticGateViolation {
  code: string;
  message: string;
  severity: "block" | "warn";
}

export interface StaticGateResult {
  passed: boolean;
  violations: StaticGateViolation[];
  warnings: StaticGateViolation[];
  syntax_check: "passed" | "failed" | "skipped";
  syntax_check_detail?: string | null;
}

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
  agent_run_id?: number | null;
  metadata_?: Record<string, unknown> | null;
  static_gate_result?: StaticGateResult | null;
  created_at: string;
  updated_at: string;
}

export interface ScriptQualitySignals {
  /** null = unknown (no grounding metadata yet), not "known ungrounded". */
  grounded: boolean | null;
  ungroundedElements: string[];
  /** null = never dry-run, distinct from a known failure. */
  lastDryRunPassed: boolean | null;
  needsRegeneration: boolean;
}

/** Reads the same grounding/dry-run signals the backend's
 * execution_blocked_reason() gates on, so the UI can show *why* a script
 * isn't trustworthy instead of just "approved" masking a known-bad script. */
export function getScriptQualitySignals(script: Pick<AutomationScript, "status" | "metadata_"> | null | undefined): ScriptQualitySignals {
  const metadata = script?.metadata_ ?? {};
  const grounding = (metadata as { grounding?: { grounded?: boolean; ungrounded_elements?: string[] } }).grounding;
  const lastDryRun = (metadata as { last_dry_run?: { passed?: boolean } }).last_dry_run;
  return {
    grounded: grounding?.grounded ?? null,
    ungroundedElements: grounding?.ungrounded_elements ?? [],
    lastDryRunPassed: lastDryRun?.passed ?? null,
    needsRegeneration: script?.status === "needs_regeneration",
  };
}

export interface GenerationAttempt {
  attempt: number;
  outcome: "compiled" | "validation_failed" | "parse_failed" | "llm_error";
  detail?: string | null;
  ungrounded_count?: number;
}

/** Reads metadata_.generation_attempts — every retry the feedback loop
 * made (validation/parse failures it corrected, or grounding it kept
 * narrowing) on the way to this script's final result. Empty for scripts
 * that predate the feedback loop, or that succeeded on the first attempt
 * with nothing to retry. */
export function getGenerationAttempts(script: Pick<AutomationScript, "metadata_"> | null | undefined): GenerationAttempt[] {
  const attempts = (script?.metadata_ as { generation_attempts?: GenerationAttempt[] } | undefined)?.generation_attempts;
  return attempts ?? [];
}

// Phase 4.6: staged post-generation approval chain — dry_run_passed ->
// reviewer_approved -> lead_approved -> [environment_approve, required for
// PROD_SANITY] -> ci_ready. Distinct from the legacy approve/reject flow
// above (AutomationScript.status ai_draft/draft/in_review/approved/rejected),
// which still governs manually-authored scripts.
export type LifecycleApprovalAction =
  | "reviewer_approve"
  | "reviewer_reject"
  | "lead_approve"
  | "lead_reject"
  | "environment_approve"
  | "mark_ci_ready";

export interface AutomationConfidenceScore {
  overall: number;
  locator_confidence: number;
  assertion_confidence: number;
  data_readiness: number;
  environment_readiness: number;
  dry_run_stability: number;
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

export interface AutomationFrameworkOption {
  key: "playwright" | "pytest";
  label: string;
  language: string;
  runner_family: string;
  primary_use_cases: string[];
}

export interface AutomationPlanningCandidate {
  test_case_id: number;
  test_case_key: string;
  title: string;
  test_type?: string | null;
  automation_status: string;
  automation_ready: boolean;
  mapping_status: string;
  execution_handoff: "draft_generation" | "human_review" | "repository_ready" | "ready_for_execution";
  recommended_framework: "playwright" | "pytest";
  secondary_framework: "playwright" | "pytest";
  hybrid_ready: boolean;
  recommended_language: string;
  assessment_score: number;
  assessment_band: "high" | "medium" | "low";
  assessment_reasons: string[];
  framework_reasons: string[];
  framework_scores: Record<string, number>;
  script_id?: number | null;
  linked_script_ids: number[];
  script_status?: string | null;
  /** null = unknown (no grounding metadata yet) — see getScriptQualitySignals. */
  grounded?: boolean | null;
  ungrounded_element_count?: number;
  last_dry_run_passed?: boolean | null;
  /** null = eligible to execute; otherwise the specific reason it's blocked
   * (mirrors the backend's execution_blocked_reason gate — the same check
   * the execute/execute-batch endpoints enforce server-side). */
  execution_blocked_reason?: string | null;
  consecutive_failure_count?: number;
  last_failure_error?: string | null;
  repository?: string | null;
  branch?: string | null;
  script_path?: string | null;
  last_execution_status?: string | null;
  last_execution_at?: string | null;
  inferred_suite?: string | null;
  coverage_hint?: string | null;
  updated_at?: string | null;
  framework_options: AutomationFrameworkOption[];
  test_suite_id?: number | null;
  test_suite_name?: string | null;
}

export interface AutomationPlanningSummary {
  total_candidates: number;
  ready_for_generation: number;
  pending_review: number;
  repository_ready: number;
  ready_for_execution: number;
  by_framework: Record<string, number>;
  by_handoff: Record<string, number>;
  supported_frameworks: AutomationFrameworkOption[];
  available_environments: string[];
  available_browsers: string[];
}

export interface AutomationPlanning {
  project_id: number;
  summary: AutomationPlanningSummary;
  candidates: AutomationPlanningCandidate[];
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

// ── AI Intelligence Assistant (Phase 2D) ──────────────────────────────────────

export type RecommendationSeverity = "low" | "medium" | "high";

export interface IntelligenceRecommendation {
  id: string;
  kind: string;
  title: string;
  severity: RecommendationSeverity;
  confidence: number;
  description: string;
  proposal: string;
  related: string;
}

export interface IntelligenceLocator {
  id: string;
  current: string;
  current_confidence: number;
  suggested: string;
  suggested_confidence: number;
  rationale: string;
}

export interface IntelligenceAssertion {
  id: string;
  scenario: string;
  missing: string;
  suggestion: string;
}

export interface IntelligenceDataIssue {
  id: string;
  kind: "hardcoded" | "unmasked" | "expired" | "env_leak";
  description: string;
  proposal: string;
}

export interface IntelligenceCheck {
  id: string;
  layer: "API" | "DB" | "Event";
  title: string;
  details: string;
}

export interface IntelligenceHealth {
  overall: number;
  parts: { label: string; value: number; note: string }[];
}

export interface IntelligenceDecision {
  recommendation_id: string;
  action: "apply" | "dismiss";
  user_id: number;
  ts: string;
  notes?: string;
}

export interface IntelligenceReport {
  script_id: number;
  framework: string;
  recommendations: IntelligenceRecommendation[];
  locators: IntelligenceLocator[];
  assertions: IntelligenceAssertion[];
  data_issues: IntelligenceDataIssue[];
  checks: IntelligenceCheck[];
  health: IntelligenceHealth;
  decisions: IntelligenceDecision[];
}

export const automationApi = {
  list: (projectId: number, params?: { test_case_id?: number; status?: string }) =>
    api.get<AutomationScript[]>(`/automation/project/${projectId}`, { params }),
  getPlanning: (projectId: number) =>
    api.get<AutomationPlanning>(`/automation/planning/project/${projectId}`),
  get: (id: number) => api.get<AutomationScript>(`/automation/${id}`),
  update: (id: number, data: Partial<AutomationScript>) =>
    api.patch<AutomationScript>(`/automation/${id}`, data),
  approve: (id: number, action: "approve" | "reject", notes?: string) =>
    api.post<AutomationScript>(`/automation/${id}/approve`, { action, notes }),
  bulkApprove: (scriptIds: number[], action: "approve" | "reject", notes?: string) =>
    api.post<{
      results: Array<{ script_id: number; ok: boolean; error?: string | null }>;
      approved_count: number;
      failed_count: number;
    }>("/automation/scripts/bulk-approve", { script_ids: scriptIds, action, notes }),
  transition: (
    id: number,
    action: "submit_for_review" | "request_changes" | "restore_draft",
    notes?: string,
  ) => api.post<AutomationScript>(`/automation/${id}/transition`, { action, notes }),
  lifecycleApprove: (id: number, action: LifecycleApprovalAction, notes?: string) =>
    api.post<AutomationScript>(`/automation/${id}/lifecycle-approval`, { action, notes }),
  getConfidenceScore: (id: number) =>
    api.get<AutomationConfidenceScore>(`/automation/${id}/confidence-score`),
  getIntelligence: (scriptId: number) =>
    api.get<IntelligenceReport>(`/automation/${scriptId}/intelligence`),
  recommendationDecision: (
    scriptId: number,
    recommendationId: string,
    action: "apply" | "dismiss",
    notes?: string,
  ) =>
    api.post<AutomationScript>(
      `/automation/${scriptId}/recommendations/${recommendationId}/decision`,
      { action, notes },
    ),
  generateScripts: (
    projectId: number,
    testCaseIds: number[],
    framework: string = "playwright",
    source: "approved_test_case" | "manual_conversion" = "approved_test_case",
  ) =>
    api.post("/automation/agent/generate-scripts", {
      project_id: projectId,
      test_case_ids: testCaseIds,
      framework,
      source,
    }),
  discoverUi: (projectId: number, testCaseIds: number[], environment: string = "QA") =>
    api.post<{ message: string; agent_run_id: number; task_id: string }>("/automation/agent/discover-ui", {
      project_id: projectId,
      test_case_ids: testCaseIds,
      environment,
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

  // Local subprocess runner — executes generated scripts on the backend host.
  // See backend/AUTOMATION_RUNNER.md for runtime requirements.
  getRunnerStatus: () =>
    api.get<{ frameworks: Array<{ framework: string; available: boolean; detail: string }> }>(
      "/automation/runner/status",
    ),
  executeScript: (scriptId: number, payload?: { environment?: string; timeout_seconds?: number }) =>
    api.post<{ execution_run_id: number; task_id?: string; status: string; message: string }>(
      `/automation/scripts/${scriptId}/execute`,
      { environment: payload?.environment ?? "staging", timeout_seconds: payload?.timeout_seconds ?? 600 },
    ),
  // "Run All Eligible" — runs several approved scripts as one batch ExecutionRun.
  executeBatch: (
    projectId: number,
    scriptIds: number[],
    payload?: { environment?: string; timeout_seconds?: number; run_name?: string; parent_run_id?: number },
  ) =>
    api.post<{ execution_run_id: number; task_id?: string; status: string; script_count: number; message: string }>(
      `/automation/project/${projectId}/execute-batch`,
      {
        script_ids: scriptIds,
        environment: payload?.environment ?? "staging",
        timeout_seconds: payload?.timeout_seconds ?? 600,
        run_name: payload?.run_name,
        parent_run_id: payload?.parent_run_id,
      },
    ),
  // Best-effort cancel for a local-runner run (single script or batch).
  cancelRun: (runId: number) =>
    api.post<{ execution_run_id: number; status: string; message: string }>(`/automation/runs/${runId}/cancel`),
  // Re-runs generation for this script using current application/URL context
  // and resets it to draft for re-review. Fixes scripts generated before a
  // real application URL was configured (e.g. ones hardcoding example.com).
  regenerateScript: (scriptId: number) =>
    api.post<AutomationScript>(`/automation/${scriptId}/regenerate`),
  // On-demand repair for a real (non-dry-run) execution failure — the
  // manual counterpart to the automatic dry-run chain, which never runs
  // for real Command Center executions. Classifies the failure first if
  // it hasn't been already, and only attempts a targeted contract patch
  // when the classification is repairable (locator_issue/timeout).
  repairFromResult: (executionResultId: number) =>
    api.post<RepairOutcome>(`/automation/results/${executionResultId}/repair`),
  // The real timeline behind a script's status — replaces the abstract,
  // status-only lifecycle stepper with what actually happened and when.
  getPipeline: (scriptId: number) =>
    api.get<PipelineStage[]>(`/automation/${scriptId}/pipeline`),
  runnerArtifactUrl: (resultId: number, kind: "log" | "screenshot" | "video" | "trace") =>
    `/api/v1/automation/runner/results/${resultId}/artifact/${kind}`,
};

// ── Playwright AI Studio ──────────────────────────────────────────────────────

export interface StudioRunConfig {
  application_id: number;
  application_name?: string;
  environment: string;
  target_url: string;
  objective?: string;
  coverage_types?: string[];
  excluded_paths?: string[];
  browser?: string;
  max_pages?: number;
  max_minutes?: number;
  target_test_case_count?: number | null;
  framework?: string;
  runner_mode?: "local" | "docker";
  parallelism?: number;
  timeout_seconds?: number;
}

export interface StudioRun {
  id: number;
  project_id: number;
  created_by: number;
  name: string;
  status: string;
  config: StudioRunConfig;
  error?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface StudioPlannedStep {
  action: string;
  element?: string | null;
  value?: string | null;
  description: string;
}

export interface StudioProposal {
  key: string;
  title: string;
  page_url: string;
  module?: string;
  priority: string;
  coverage_type: string;
  preconditions: string[];
  steps: StudioPlannedStep[];
  expected_result: string;
  blocked_reasons: string[];
  ungrounded_elements: string[];
}

export interface StudioPlan {
  explored_page_count: number;
  pages: Array<{ url: string; title?: string | null; element_count: number; blockers: string[] }>;
  proposed_test_cases: StudioProposal[];
  approved_keys?: string[];
  // Present when a target_test_case_count was set and the plan was
  // trimmed to it — total_proposed_before_cap is what every page proposed
  // independently before the deterministic cap was applied.
  total_proposed_before_cap?: number | null;
  target_test_case_count?: number | null;
}

export interface StudioAgentRunSummary {
  id: number;
  status: string;
  progress_percent: number;
  progress_message?: string | null;
  error_message?: string | null;
}

export interface StudioScriptSummary {
  id: number;
  script_id: string;
  test_case_id?: number | null;
  status: string;
  version: number;
  framework?: string | null;
  grounding?: { grounded?: boolean; grounded_element_count?: number; ungrounded_elements?: string[] } | null;
  static_gate_passed?: boolean | null;
  last_dry_run?: Record<string, unknown> | null;
}

export interface StudioAutoHealSummary {
  attempted: number;
  repaired: number;
  not_repairable: number;
  errors: number;
  new_script_ids: number[];
  capped: boolean;
}

export interface StudioExecutionSummary {
  id: number;
  execution_id: string;
  status: string;
  total_tests: number;
  passed: number;
  failed: number;
  skipped: number;
  auto_heal?: StudioAutoHealSummary | null;
}

export interface StudioFailureInsight {
  kind: string;
  severity: "error" | "warning" | "info";
  message: string;
  action: string;
  count: number;
  examples: string[];
}

export interface StudioRunDetail extends StudioRun {
  plan?: StudioPlan | null;
  test_case_ids?: number[] | null;
  agent_runs: { planner?: StudioAgentRunSummary | null; generation: StudioAgentRunSummary[] };
  scripts: StudioScriptSummary[];
  script_counts: Record<string, number>;
  executions: StudioExecutionSummary[];
  failure_insights: StudioFailureInsight[];
}

export interface StudioRunCreatePayload {
  project_id: number;
  name: string;
  application_id: number;
  environment: string;
  objective?: string;
  coverage_types?: string[];
  excluded_paths?: string[];
  browser?: string;
  max_pages?: number;
  max_minutes?: number;
  target_test_case_count?: number;
  framework?: string;
  runner_mode?: "local" | "docker";
  parallelism?: number;
  timeout_seconds?: number;
}

export const playwrightStudioApi = {
  listRuns: (projectId: number) =>
    api.get<StudioRun[]>("/playwright-studio/runs", { params: { project_id: projectId } }),
  getRun: (runId: number) => api.get<StudioRunDetail>(`/playwright-studio/runs/${runId}`),
  createRun: (payload: StudioRunCreatePayload) =>
    api.post<StudioRun>("/playwright-studio/runs", payload),
  startRun: (runId: number) =>
    api.post<{ studio_run_id: number; agent_run_id: number; task_id?: string; status: string; message: string }>(
      `/playwright-studio/runs/${runId}/start`,
    ),
  approvePlan: (runId: number, payload: { included_keys?: string[] | null; notes?: string }) =>
    api.post<{ studio_run_id: number; status: string; test_case_count: number; wave_count: number; message: string }>(
      `/playwright-studio/runs/${runId}/approve-plan`,
      payload,
    ),
  approveScripts: (runId: number, payload: { notes?: string }) =>
    api.post<{
      studio_run_id: number;
      status: string;
      approved_script_count: number;
      execution_run_ids: number[];
      message: string;
    }>(`/playwright-studio/runs/${runId}/approve-scripts`, payload),
  cancelRun: (runId: number) =>
    api.post<{ studio_run_id: number; status: string; message: string }>(
      `/playwright-studio/runs/${runId}/cancel`,
    ),
};

// ── MCP Connections (Playwright AI Studio) ────────────────────────────────────

export interface McpConnection {
  id: number;
  project_id: number;
  name: string;
  connection_type: string;
  transport: string;
  target?: string | null;
  command?: string | null;
  args?: string[] | null;
  url?: string | null;
  access_mode: string;
  available_to?: string[] | null;
  status: string;
  tool_count?: number | null;
  last_checked_at?: string | null;
  last_error?: string | null;
  is_builtin: boolean;
  has_credentials: boolean;
}

export interface McpConnectionCreatePayload {
  project_id: number;
  name: string;
  connection_type?: string;
  transport?: string;
  target?: string;
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
  access_mode?: string;
  available_to?: string[];
}

export const mcpConnectionsApi = {
  list: (projectId: number) =>
    api.get<McpConnection[]>("/mcp-connections", { params: { project_id: projectId } }),
  create: (payload: McpConnectionCreatePayload) =>
    api.post<McpConnection>("/mcp-connections", payload),
  update: (id: number, payload: Partial<McpConnectionCreatePayload>) =>
    api.patch<McpConnection>(`/mcp-connections/${id}`, payload),
  remove: (id: number) => api.delete(`/mcp-connections/${id}`),
  test: (id: number) => api.post<McpConnection>(`/mcp-connections/${id}/test`),
  testAll: (projectId: number) =>
    api.post<{
      results: Array<{ id: number; name: string; status: string; tool_count?: number | null; last_error?: string | null }>;
      connected_count: number;
      error_count: number;
    }>("/mcp-connections/test-all", undefined, { params: { project_id: projectId } }),
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
  // Local-runner artifact paths (served via automationApi.runnerArtifactUrl);
  // presence signals which artifact kinds exist for this result.
  screenshot_path?: string | null;
  video_path?: string | null;
  trace_path?: string | null;
  external_result_url?: string;
  jira_issue_key?: string;
  jira_test_key?: string;
  raw_result_json?: Record<string, unknown>;
  logs?: string[];
  metadata_?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export type FailureClassificationType =
  | "app_defect" | "locator_issue" | "data_issue" | "environment_issue" | "api_issue" | "timeout";

export interface FailureClassification {
  classification: FailureClassificationType;
  reason: string;
  source: "rules" | "llm";
  repairable: boolean;
}

/** Reads the same classification the backend writes onto
 * ExecutionResult.metadata_.failure_classification — via the automatic
 * hook after every real execution (automation_service.classify_failed_results)
 * or the on-demand repair endpoint. null means not yet classified. */
export function getFailureClassification(result: Pick<ExecutionResult, "metadata_"> | null | undefined): FailureClassification | null {
  const info = (result?.metadata_ as { failure_classification?: FailureClassification } | undefined)?.failure_classification;
  return info ?? null;
}

export interface RepairAttempt {
  attempt: number;
  outcome: string;
  detail?: string | null;
  static_gate_passed?: boolean | null;
  dry_run_passed?: boolean | null;
}

export interface RepairOutcome {
  classification: FailureClassificationType | null;
  classification_reason: string | null;
  repairable: boolean;
  repaired: boolean;
  new_script_id: number | null;
  attempts: RepairAttempt[];
  error: string | null;
}

export type PipelineStageName = "discover" | "generate" | "static" | "dry_run" | "review" | "ci_ready";
export type PipelineStageState = "done" | "failed" | "pending";

export interface PipelineStage {
  stage: PipelineStageName;
  state: PipelineStageState;
  at: string | null;
  detail: string | null;
}

export interface ExecutionRun {
  id: number;
  project_id: number;
  execution_id: string;
  execution_type?: "manual" | "automation" | "ai" | "hybrid" | string;
  test_cycle_id?: string | null;
  source_type?: string | null;
  external_tool_name?: string | null;
  external_run_id?: string | null;
  suite_name?: string;
  environment?: string;
  status: string;
  triggered_by?: number | null;
  triggered_by_name?: string | null;
  // Resolved live from the Test Cases module: test_suite_name via
  // TestCase.test_suite_id -> TestSuite.name, test_environment via
  // TestCase.test_phase. Distinct from `suite_name` above, which is just
  // this run's own free-text title.
  test_suite_name?: string | null;
  test_environment?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
  total_tests: number;
  passed: number;
  failed: number;
  skipped: number;
  confidence_score?: number | null;
  execution_logs?: unknown[];
  allure_report_path?: string | null;
  agent_run_id?: number | null;
  metadata_?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ExecutionDashboardPayload {
  kpis: {
    total_executions: number;
    total_test_cases: number;
    passed: number;
    failed: number;
    skipped: number;
    blocked: number;
    in_progress: number;
    review_required: number;
    avg_execution_seconds: number;
    total_execution_seconds: number;
    overall_pass_rate: number;
  };
  by_type: Array<{
    execution_type: string;
    run_count: number;
    total_tests: number;
    passed: number;
    failed: number;
    skipped: number;
    blocked: number;
    in_progress: number;
    pass_rate: number;
  }>;
  by_environment: Array<{ environment: string; run_count: number }>;
  by_module: Array<{ module: string; executions: number; failures: number }>;
  trend: Array<{ date: string; manual: number; automation: number; ai: number; hybrid: number }>;
  recent_runs: Array<{
    id: number;
    execution_id: string;
    execution_type: string;
    status: string;
    environment: string | null;
    suite_name: string | null;
    total_tests: number;
    passed: number;
    failed: number;
    started_at: string | null;
    duration_seconds: number | null;
    triggered_by_name: string | null;
    confidence_score: number | null;
  }>;
  defects: { total: number; by_type: Record<string, number> };
  insights: Array<{ kind: string; title: string; body: string }>;
  filters_applied: {
    project_id: number;
    environment: string | null;
    execution_type: string | null;
    date_from: string | null;
    date_to: string | null;
  };
}

export interface ExecutionTriggerResponse {
  message: string;
  agent_run_id?: number;
  task_id?: string;
  run_id?: number;
  result_ids?: number[];
}

export type ManualStepStatus = "not_run" | "in_progress" | "passed" | "failed" | "blocked" | "skipped";

export interface ManualEvidence {
  id: string;
  filename: string;
  size: number;
  content_type?: string | null;
  uploaded_at: string;
  download_url: string;
}

export interface ManualStepResult {
  id: number;
  execution_result_id: number;
  step_number: number;
  action_text?: string | null;
  expected_text?: string | null;
  status: ManualStepStatus;
  actual_result?: string | null;
  comments?: string | null;
  evidence: ManualEvidence[];
  started_at?: string | null;
  completed_at?: string | null;
  updated_by?: number | null;
  updated_at: string;
}

export interface ManualResultDetail {
  result: ExecutionResult;
  steps: ManualStepResult[];
}

export interface ManualRunDetail {
  run: ExecutionRun;
  results: ManualResultDetail[];
}

export const executionApi = {
  listRuns: (projectId: number, params?: { status?: string }) =>
    api.get<ExecutionRun[]>(`/execution/project/${projectId}`, { params }),
  getRun: (id: number) => api.get<ExecutionRun>(`/execution/${id}`),
  getResults: (runId: number) => api.get<ExecutionResult[]>(`/execution/${runId}/results`),

  // Unified Execution Dashboard — Manual + Automation + AI in a single payload.
  // Backed by GET /execution/dashboard (see execution_dashboard_service.py).
  getDashboard: (params: {
    project_id: number;
    environment?: string | null;
    execution_type?: "manual" | "automation" | "ai" | null;
    date_from?: string | null;
    date_to?: string | null;
  }) =>
    api.get<ExecutionDashboardPayload>("/execution/dashboard", {
      params: {
        project_id: params.project_id,
        environment: params.environment || undefined,
        execution_type: params.execution_type || undefined,
        date_from: params.date_from || undefined,
        date_to: params.date_to || undefined,
      },
    }),
  runTests: (projectId: number, testCaseIds: number[], environment: string = "staging", suiteName?: string, sourceType?: string) =>
    api.post<ExecutionTriggerResponse>("/execution/agent/run-tests", {
      project_id: projectId,
      test_case_ids: testCaseIds,
      environment,
      suite_name: suiteName,
      source_type: sourceType,
    }),

  // Manual Execution — server-persisted per-step results + evidence
  startManualRun: (
    projectId: number,
    testCaseIds: number[],
    environment: string = "staging",
    suiteName?: string,
    // Optional: map test_case_id -> TestDataRecord.id. When provided, the
    // server substitutes ${field} placeholders in step text against the bound
    // record at run-start, then snapshots the resolved text onto the step row.
    boundDataRecords?: Record<number, number>,
  ) =>
    api.post<ManualRunDetail>("/execution/manual/runs", {
      project_id: projectId,
      test_case_ids: testCaseIds,
      environment,
      suite_name: suiteName,
      bound_data_records: boundDataRecords ?? {},
    }),
  getManualRun: (runId: number) =>
    api.get<ManualRunDetail>(`/execution/manual/runs/${runId}/details`),
  updateManualStep: (stepId: number, patch: { status?: ManualStepStatus; actual_result?: string; comments?: string }) =>
    api.patch<ManualStepResult>(`/execution/manual/steps/${stepId}`, patch),
  uploadManualEvidence: (stepId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<ManualStepResult>(`/execution/manual/steps/${stepId}/evidence`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  deleteManualEvidence: (evidenceId: string) =>
    api.delete<ManualStepResult>(`/execution/manual/evidence/${evidenceId}`),
  completeManualRun: (runId: number) =>
    api.post<ManualRunDetail>(`/execution/manual/runs/${runId}/complete`),

  // Ask the configured LLM for a pass/fail/blocked suggestion on a step.
  // Tester drives invocation (no auto-suggest) so cost is predictable.
  aiAssistStep: (stepId: number, payload?: { actualResult?: string; comments?: string; screenshot?: File }) => {
    const form = new FormData();
    if (payload?.actualResult !== undefined) form.append("actual_result", payload.actualResult);
    if (payload?.comments !== undefined) form.append("comments", payload.comments);
    if (payload?.screenshot) form.append("file", payload.screenshot);
    return api.post<{
      suggested_status: "pass" | "fail" | "blocked";
      confidence: number;
      reasoning: string;
      observations: string[];
      inputs_used: { mode: "vision" | "text_only"; vision_blocker: string | null };
      raw_response: string | null;
    }>(`/execution/manual/steps/${stepId}/ai-assist`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
};

// ── AI Execution ──────────────────────────────────────────────────────────────

export interface AiRunGovernance {
  ai_confidence_threshold: number;
  ai_autonomous_environments: string[];
  ai_require_evidence_for_pass: boolean;
  ai_run_max_seconds: number;
}

export interface AiRunReviewLogEntry {
  ts: string;
  by_user_id: number;
  decision: "approve" | "override" | "request_rerun" | "reject";
  reason: string;
  previous_status: string;
  override_status?: string | null;
}

export interface AiRunDetail {
  run: ExecutionRun;
  results: ExecutionResult[];
  governance: AiRunGovernance;
  review_log: AiRunReviewLogEntry[];
}

export const aiExecutionApi = {
  governance: () => api.get<AiRunGovernance>("/execution/ai/governance"),
  startRun: (payload: {
    project_id: number;
    test_case_ids: number[];
    environment?: string;
    agent_name?: string;
    model?: string;
    suite_name?: string;
    confidence_threshold?: number;
    mode?: "autonomous" | "supervised";
  }) =>
    api.post<ExecutionRun>("/execution/ai/runs", {
      project_id: payload.project_id,
      test_case_ids: payload.test_case_ids,
      environment: payload.environment ?? "staging",
      agent_name: payload.agent_name ?? "nxtQA AI Agent v2.1",
      model: payload.model ?? null,
      suite_name: payload.suite_name ?? null,
      confidence_threshold: payload.confidence_threshold ?? null,
      mode: payload.mode ?? "autonomous",
    }),
  getRun: (runId: number) => api.get<AiRunDetail>(`/execution/ai/runs/${runId}`),
  submitReview: (runId: number, payload: {
    decision: "approve" | "override" | "request_rerun" | "reject";
    reason: string;
    override_status?: "completed" | "failed" | "auto_completed" | "cancelled";
  }) => api.post<ExecutionRun>(`/execution/ai/runs/${runId}/review`, payload),
  finalize: (runId: number) => api.post<ExecutionRun>(`/execution/ai/runs/${runId}/finalize`),
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

// ── Traceability ─────────────────────────────────────────────────────────────

export type LineageEntityType =
  | "requirement" | "test_plan" | "test_scenario" | "test_case" | "test_data"
  | "automation_script" | "execution_run" | "execution_result" | "defect_draft" | "report";

export interface LineageNode {
  entity_type: LineageEntityType | string;
  entity_id: number;
  ref?: string | null;
  title?: string | null;
  status?: string | null;
  relationship_type?: string | null;
  depth: number;
}

export interface LineageChain {
  entity_type: string;
  entity_id: number;
  project_id: number;
  upstream: LineageNode[];
  downstream: LineageNode[];
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

  /** Record an audited governance decision for a supported artifact. */
  decide: (
    entityType: string,
    entityId: number,
    action: "approve" | "reject" | "request_changes",
    notes?: string,
    changesRequested?: Record<string, unknown>,
  ) =>
    api.post<ApprovalAction>(`/traceability/approvals/${entityType}/${entityId}`, {
      action,
      notes,
      changes_requested: changesRequested,
    }),

  /** Entity-centric lineage walk over artifact_lineage (both directions). */
  getLineage: (entityType: LineageEntityType | string, entityId: number) =>
    api.get<LineageChain>(`/traceability/lineage/${entityType}/${entityId}`),
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

// ── Reviews & Coverage Matrix (Phase 1 stage reviewer agents) ─────────────────

export type ReviewVerdict = "pass" | "needs_revision" | "fail";

export interface ReviewFinding {
  dimension: string;
  issue: string;
  suggestion?: string | null;
}

export interface CoverageGap {
  source_ref: string;
  description: string;
  severity: "high" | "medium" | "low";
}

export interface ArtifactReview {
  id: number;
  project_id: number;
  agent_run_id?: number;
  artifact_type: string;
  artifact_id: number;
  reviewer_agent: string;
  scores?: Record<string, number>;
  overall_score?: number;
  verdict: ReviewVerdict;
  findings?: ReviewFinding[];
  coverage_gaps?: CoverageGap[];
  review_mode: string;
  created_at: string;
  updated_at: string;
}

export interface CoverageMatrixEntry {
  id: number;
  project_id: number;
  requirement_id?: number;
  scenario_id?: number;
  test_case_id?: number;
  script_id?: number;
  execution_result_id?: number;
  defect_id?: number;
  test_type?: string;
  risk_level?: string;
  case_class?: string;
  automation_eligible?: string;
  automation_reason?: string;
  execution_status?: string;
  defect_linked: boolean;
  created_at: string;
  updated_at: string;
}

export const reviewsApi = {
  /** Most recent review per reviewed artifact — for table badge overlays. */
  listForProject: (projectId: number, artifactType?: string) =>
    api.get<ArtifactReview[]>(`/reviews/project/${projectId}`, {
      params: artifactType ? { artifact_type: artifactType } : undefined,
    }),
  /** Full review history for one artifact, newest first — for a findings drawer. */
  history: (artifactType: string, artifactId: number, projectId: number) =>
    api.get<ArtifactReview[]>(`/reviews/artifact/${artifactType}/${artifactId}`, {
      params: { project_id: projectId },
    }),
  coverageMatrix: (projectId: number, params?: { requirement_id?: number; scenario_id?: number }) =>
    api.get<CoverageMatrixEntry[]>(`/reviews/coverage-matrix/project/${projectId}`, { params }),
};

// ── Grounded Automation PoC ───────────────────────────────────────────────────
// Evidence-first script generation (feature-flagged; /api/v1/poc namespace).

export interface PocRoute {
  type: string;
  adapter: string;
  implemented: boolean;
  target_phase: string;
  tools?: string;
  matched_indicators?: string[];
}

export interface PocStepRoute {
  index: number;
  action_text: string;
  expected_text: string;
  action_route: PocRoute;
  action_confidence: number;
  assertion_route: PocRoute;
  assertion_confidence: number;
  mutating: boolean;
  requires_cleanup: boolean;
}

export interface PocRouting {
  overall: PocRoute;
  overall_confidence: number;
  is_hybrid: boolean;
  type_counts: Record<string, number>;
  steps: PocStepRoute[];
  unimplemented_adapters: string[];
  manual_review_recommended: boolean;
}

export interface PocCoverageStep {
  step: number;
  action_text: string;
  action_evidence: Record<string, unknown> | null;
  data_evidence: Record<string, unknown> | null;
  assertion_evidence: Record<string, unknown> | null;
  cleanup_evidence: Record<string, unknown> | null;
  gaps: string[];
  status: "covered" | "gap";
}

export interface PocCoverage {
  testCaseId?: string;
  overallCoverage: number;
  coveredSteps: number;
  totalSteps: number;
  steps: PocCoverageStep[];
  unsupportedReferences: string[];
  liveBlockers: string[];
  warnings: string[];
  evidencePackageCount: number;
  generationAllowed: boolean;
}

export interface PocEvidenceSummary {
  id: number;
  sequence: number;
  state_fingerprint: string;
  url?: string | null;
  title?: string | null;
  element_count: number;
  blockers: string[];
  produced_by_step?: number | null;
  has_screenshot: boolean;
}

export interface PocEvidenceDetail extends PocEvidenceSummary {
  environment?: string | null;
  elements: Array<Record<string, unknown>>;
  snapshot_text?: string | null;
  console_evidence: string[];
  prev_evidence_id?: number | null;
}

export interface PocAgentRunSummary {
  id: number;
  status: string;
  progress_percent: number;
  progress_message?: string | null;
  error_message?: string | null;
}

export interface PocGroundingRun {
  id: number;
  project_id: number;
  created_by: number;
  test_case_id: number;
  application_id?: number | null;
  status: string;
  capture_mode: "automated" | "assisted" | "manual_guided";
  config: {
    environment?: string;
    target_url?: string;
    application_name?: string | null;
    test_case_display_id?: string;
    test_case_title?: string;
    confirmed_actions?: Record<string, string>;
  };
  error?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface PocGroundingRunDetail extends PocGroundingRun {
  routing?: PocRouting | null;
  coverage?: PocCoverage | null;
  pending_confirmation?: {
    step_index: number;
    action_text: string;
    candidates: Array<{ element_name: string; role: string; accessible_name?: string | null; match_score: number }>;
    reason?: string;
  } | null;
  script_ids?: number[] | null;
  evidence: PocEvidenceSummary[];
  agent_runs: { capture?: PocAgentRunSummary | null; generation?: PocAgentRunSummary | null };
  scripts: Array<{ id: number; script_id: string; status: string; version: number; framework?: string | null }>;
  step_trace: Array<Record<string, unknown>>;
}

export interface PocActionResponse {
  grounding_run_id: number;
  status: string;
  agent_run_id?: number | null;
  task_id?: string | null;
  message: string;
}

export const groundedPocApi = {
  status: () => api.get<{ enabled: boolean; message: string }>("/poc/grounded-automation/status"),
  listRuns: (projectId: number) =>
    api.get<PocGroundingRun[]>("/poc/grounded-automation/runs", { params: { project_id: projectId } }),
  getRun: (runId: number) =>
    api.get<PocGroundingRunDetail>(`/poc/grounded-automation/runs/${runId}`),
  createRun: (payload: { project_id: number; test_case_id: number; environment: string; capture_mode?: string }) =>
    api.post<PocGroundingRun>("/poc/grounded-automation/runs", payload),
  getEvidence: (runId: number, evidenceId: number) =>
    api.get<PocEvidenceDetail>(`/poc/grounded-automation/runs/${runId}/evidence/${evidenceId}`),
  startCapture: (runId: number) =>
    api.post<PocActionResponse>(`/poc/grounded-automation/runs/${runId}/start-capture`),
  confirmStep: (runId: number, payload: { step_index: number; element_name: string }) =>
    api.post<PocActionResponse>(`/poc/grounded-automation/runs/${runId}/confirm-step`, payload),
  generate: (runId: number) =>
    api.post<PocActionResponse>(`/poc/grounded-automation/runs/${runId}/generate`),
  cancelRun: (runId: number) =>
    api.post<PocActionResponse>(`/poc/grounded-automation/runs/${runId}/cancel`),
};
