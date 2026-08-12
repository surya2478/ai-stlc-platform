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
  /** Mixed by design: historical rows are plain strings, the agent now emits
   *  `{item, severity}`. Normalize with `missingInfoItems` before reading. */
  missing_information?: Array<string | MissingInfoItem>;
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

export interface RequirementQualityReview {
  id: number;
  quality_score?: number | null;
  verdict?: string | null;
  completeness_score?: number | null;
  clarity_score?: number | null;
  testability_score?: number | null;
  ambiguity_score?: number | null;
  acceptance_criteria_score?: number | null;
  interface_readiness_score?: number | null;
  telecom_domain_completeness?: number | null;
  scenario_generation_readiness?: number | null;
  ambiguities?: unknown[] | null;
  missing_details?: unknown[] | null;
  recommendations?: unknown[] | null;
  clarification_questions?: unknown[] | null;
  created_at?: string | null;
  agent_run_id?: number | null;
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

/** One pair similar enough to need a reviewer's decision. Candidates, not
 *  conclusions — the backend never merges or deletes on this basis. */
export interface RequirementDuplicatePair {
  left_id: number;
  right_id: number;
  left_display_id: string;
  right_display_id: string;
  score: number;
  title_similarity: number;
  criteria_similarity: number;
  description_similarity: number;
  shared_terms: string[];
  /** Which signal fired, in reviewer's terms — shown instead of a bare score. */
  reason: string;
}

export interface RequirementDuplicateReport {
  threshold: number;
  pairs: RequirementDuplicatePair[];
  /** Connected components: one subject to settle, not N pairwise decisions. */
  groups: number[][];
  duplicate_requirement_ids: number[];
  evaluated_count: number;
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
  /** Import only these issues. Narrows the other filters rather than replacing
   *  them; omit to take everything they match. */
  issue_keys?: string[];
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
  project_id: number;
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

  // UAT template fields (migration 042). `*_id` are the taxonomy-governed
  // source of truth; `*_name` is the resolved display value (falls back to
  // the legacy free-text column above when no taxonomy FK is set).
  channel_id?: number | null;
  channel_name?: string | null;
  domain_id?: number | null;
  domain_name?: string | null;
  area_of_test_id?: number | null;
  area_of_test_name?: string | null;
  product_id?: number | null;
  product_name?: string | null;
  sub_request_type_id?: number | null;
  sub_request_type_name?: string | null;
  test_case_type_id?: number | null;
  test_case_type_name?: string | null;
  test_case_complexity_id?: number | null;
  test_case_complexity_name?: string | null;
  test_case_objective?: string | null;
  atc_test_case?: string | null;
  is_critical: boolean;
  ppm_id?: string | null;
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
  is_agent: boolean;
}

export interface RagProjectStatus {
  rag_enabled: boolean;
  embedding_model: string;
  project_id: number;
  indexed_documents: number;
  indexed_jira_stories: number;
  total_active_chunks: number;
  embedded_chunks: number;
  unembedded_chunks: number;
  index_coverage_pct: number;
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

/** One retrieved chunk, as /rag/projects/{id}/search returns it. */
export interface RagChunk {
  chunk_id: number;
  chunk_text: string;
  source_type: string;
  source_id: number | null;
  section: string | null;
  hybrid_score: number;
  semantic_score: number | null;
  keyword_score: number | null;
}

export interface RagSearchResponse {
  chunks: RagChunk[];
  query: string;
  total_candidates: number;
  elapsed_ms: number;
  /** False when the query matched nothing the project owns — the answer would
   *  not have been grounded, and the UI has to say so rather than show zero
   *  results as if the corpus were simply empty. */
  grounded: boolean;
}

/** A chunk that actually influenced a generated artifact. */
export interface RagCitation {
  id: number;
  artifact_type: string;
  artifact_id: number;
  chunk_id: number;
  retrieval_score: number | null;
  rerank_score: number | null;
  citation_reason: string | null;
  created_at: string;
  chunk_text: string | null;
  section: string | null;
  source_type: string | null;
}

export interface RagReindexResponse {
  task_id: string | null;
  message: string;
  documents_queued: number;
  requirements_queued: number;
}

export const ragApi = {
  status: (projectId: number) =>
    api.get<RagProjectStatus>(`/rag/projects/${projectId}/status`),
  search: (projectId: number, payload: { query: string; source_types?: string[]; top_k?: number }) =>
    api.post<RagSearchResponse>(`/rag/projects/${projectId}/search`, payload),
  citations: (projectId: number, artifactType: string, artifactId: number) =>
    api.get<RagCitation[]>(
      `/rag/projects/${projectId}/artifacts/${artifactType}/${artifactId}/citations`,
    ),
  reindex: (projectId: number) =>
    api.post<RagReindexResponse>(`/rag/projects/${projectId}/reindex`, {}),
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

/** How a blocker is actually cleared. The old panel implied "Re-run Analysis"
 *  for all of them, including two that no re-run could ever fix. */
export type BlockerResolution = "rerun_analysis" | "human_input" | "clarification";

export interface RequirementBlocker {
  code: string;
  message: string;
  resolution: BlockerResolution;
  resolution_label: string;
}

export interface MissingInfoItem {
  item: string;
  severity: "blocking" | "advisory";
}

export interface RequirementBlockerSummary {
  blockers: RequirementBlocker[];
  total: number;
  by_resolution: Record<BlockerResolution, RequirementBlocker[]>;
  /** True when nothing remaining can be cleared by re-running the agent. */
  rerun_cannot_help: boolean;
  traceability: RequirementBlocker[];
  /** Declared gaps the agent judged non-blocking — shown, never gating. */
  advisory_missing_information: MissingInfoItem[];
  taxonomy_not_applicable: {
    reason: string;
    by_user_id: number | null;
    at: string;
  } | null;
}

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
  /** What is blocking this requirement, and how each blocker is actually cleared.
   *  Served by the backend so the screen no longer recomputes the gate itself —
   *  the two copies could and did disagree. */
  blockers: (id: number) => api.get<RequirementBlockerSummary>(`/requirements/${id}/blockers`),
  /** Record (or withdraw) a human decision that taxonomy does not apply. Never
   *  inferred — the telecom vocabulary genuinely does not fit every source, but
   *  deciding that is a person's call. */
  setTaxonomyApplicability: (id: number, applicable: boolean, reason?: string) =>
    api.post<Requirement>(`/requirements/${id}/taxonomy-not-applicable`, {
      applicable,
      reason,
    }),
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
    api.get<RequirementQualityReview[]>(`/requirements/${reqId}/quality-reviews`),
  // GAP-4d: coverage & prioritization analytics
  coverage: (reqId: number) =>
    api.get<RequirementCoverage>(`/requirements/${reqId}/coverage`),
  coverageSummary: (projectId: number) =>
    api.get<ProjectCoverageSummary>(`/requirements/project/${projectId}/coverage-summary`),
  // Scored server-side over every requirement in the project, not just the page
  // the client happens to have loaded.
  duplicates: (projectId: number, threshold?: number) =>
    api.get<RequirementDuplicateReport>(
      `/requirements/project/${projectId}/duplicates`
        + (threshold === undefined ? "" : `?threshold=${threshold}`)
    ),
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

/** UNKNOWN is deliberate: a step whose subsystem could not be read is never
 *  reported as DONE, so a green path means something. */
export type ExecutionPathState = "DONE" | "BLOCKED" | "WAITING" | "UNKNOWN";

export interface ExecutionPathStep {
  key: string;
  label: string;
  state: ExecutionPathState;
  detail: string;
  /** Present only on the one actionable step — consequences carry no link. */
  fix_label: string | null;
  fix_href: string | null;
}

export interface ExecutionPath {
  test_case_id: number;
  test_case_key: string | null;
  steps: ExecutionPathStep[];
  steps_total: number;
  steps_done: number;
  ready_to_execute: boolean;
  next_action: string | null;
  next_action_href: string | null;
  errors: string[];
}

export const testCasesApi = {
  list: (projectId: number, params?: { scenario_id?: number; requirement_id?: number; status?: string; automation_only?: boolean }) =>
    api.get<TestCase[]>(`/test-cases/projects/${projectId}`, { params }),
  summary: (projectId: number) =>
    api.get<TestCaseSummary>(`/test-cases/projects/${projectId}/summary`),
  /** Everything standing between this test case and a governed execution.
   *  Read-only — derived from state other services already own. */
  executionPath: (projectId: number, testCaseId: number) =>
    api.get<ExecutionPath>(`/test-cases/projects/${projectId}/execution-path/${testCaseId}`),
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

// ── Taxonomy (centrally governed telecom QA master data) ────────────────────
// Backs the Domain / Channel / Product / Area of Test / Sub Request Type /
// Test Case Type / Test Case Complexity / Environment dropdowns across
// Requirements, Test Cases, Test Planning and Execution. Real backend-driven
// reference data — replaces any hardcoded option arrays.

export interface TaxonomyEntry {
  id: number;
  organization_id?: number | null;
  name: string;
  code: string;
  description?: string | null;
  status: "active" | "draft" | "retired";
  is_active: boolean;
  sort_order: number;
}

export interface TaxonomyTree {
  qa_domains: Array<{ id: number; name: string; code: string; is_active: boolean; product_groups: Array<{ id: number; name: string; code: string; is_active: boolean; products: Array<{ id: number; name: string; code: string; is_active: boolean }> }> }>;
  systems: TaxonomyEntry[];
  sub_request_types: TaxonomyEntry[];
  business_processes: TaxonomyEntry[];
  test_case_types: TaxonomyEntry[];
  test_case_complexities: TaxonomyEntry[];
  environments: TaxonomyEntry[];
}

/** A Product Group. `parent_id` (a QA Domain) is optional since migration 059
 *  — Domain is a label, not a precondition. */
export interface TaxonomyGroupEntry extends TaxonomyEntry {
  parent_id: number | null;
}

/** A Product. `parent_id` (a Product Group) is NOT NULL — this is the
 *  dependency the classification chain actually enforces. */
export interface TaxonomyChildEntry extends TaxonomyEntry {
  parent_id: number;
}

/** Write shape shared by every master table. `code` is uppercased and
 *  restricted to [A-Z0-9_-] by the backend validator. */
export interface TaxonomyEntryInput {
  name: string;
  code: string;
  description?: string | null;
  status?: "active" | "draft" | "retired";
  owner?: string | null;
  is_active?: boolean;
  sort_order?: number;
}

/** Sub Request Type reaches Product through this edge table rather than a
 *  parent column, so one type can serve several products. */
export type TaxonomyRelationType =
  | "system_supports_product"
  | "subrequest_for_product"
  | "subrequest_for_system";

export interface TaxonomyRelationship {
  id: number;
  organization_id?: number | null;
  relation_type: TaxonomyRelationType;
  from_entity: string;
  from_id: number;
  to_entity: string;
  to_id: number;
  is_active: boolean;
}

/** DELETE deactivates (is_active=false) rather than removing the row — the
 *  ids are referenced by test cases and must stay resolvable. */
export const taxonomyApi = {
  tree: (activeOnly = true) => api.get<TaxonomyTree>("/taxonomy/tree", { params: { active_only: activeOnly } }),

  qaDomains: (activeOnly = false) => api.get<TaxonomyEntry[]>("/taxonomy/qa-domains", { params: { active_only: activeOnly } }),
  createQaDomain: (data: TaxonomyEntryInput) => api.post<TaxonomyEntry>("/taxonomy/qa-domains", data),
  updateQaDomain: (id: number, data: Partial<TaxonomyEntryInput>) => api.patch<TaxonomyEntry>(`/taxonomy/qa-domains/${id}`, data),
  deactivateQaDomain: (id: number) => api.delete(`/taxonomy/qa-domains/${id}`),

  productGroups: (params?: { parent_id?: number; active_only?: boolean }) =>
    api.get<TaxonomyGroupEntry[]>("/taxonomy/product-groups", { params }),
  createProductGroup: (data: TaxonomyEntryInput & { parent_id?: number | null }) =>
    api.post<TaxonomyGroupEntry>("/taxonomy/product-groups", data),
  updateProductGroup: (id: number, data: Partial<TaxonomyEntryInput & { parent_id: number | null }>) =>
    api.patch<TaxonomyGroupEntry>(`/taxonomy/product-groups/${id}`, data),
  deactivateProductGroup: (id: number) => api.delete(`/taxonomy/product-groups/${id}`),

  products: (params?: { parent_id?: number; active_only?: boolean }) =>
    api.get<TaxonomyChildEntry[]>("/taxonomy/products", { params }),
  createProduct: (data: TaxonomyEntryInput & { parent_id: number }) =>
    api.post<TaxonomyChildEntry>("/taxonomy/products", data),
  updateProduct: (id: number, data: Partial<TaxonomyEntryInput & { parent_id: number }>) =>
    api.patch<TaxonomyChildEntry>(`/taxonomy/products/${id}`, data),
  deactivateProduct: (id: number) => api.delete(`/taxonomy/products/${id}`),

  systems: (activeOnly = false) => api.get<TaxonomyEntry[]>("/taxonomy/systems", { params: { active_only: activeOnly } }),
  createSystem: (data: TaxonomyEntryInput) => api.post<TaxonomyEntry>("/taxonomy/systems", data),
  updateSystem: (id: number, data: Partial<TaxonomyEntryInput>) => api.patch<TaxonomyEntry>(`/taxonomy/systems/${id}`, data),
  deactivateSystem: (id: number) => api.delete(`/taxonomy/systems/${id}`),

  subRequestTypes: (activeOnly = false) => api.get<TaxonomyEntry[]>("/taxonomy/sub-request-types", { params: { active_only: activeOnly } }),
  createSubRequestType: (data: TaxonomyEntryInput) => api.post<TaxonomyEntry>("/taxonomy/sub-request-types", data),
  updateSubRequestType: (id: number, data: Partial<TaxonomyEntryInput>) => api.patch<TaxonomyEntry>(`/taxonomy/sub-request-types/${id}`, data),
  deactivateSubRequestType: (id: number) => api.delete(`/taxonomy/sub-request-types/${id}`),

  businessProcesses: (activeOnly = false) => api.get<TaxonomyEntry[]>("/taxonomy/business-processes", { params: { active_only: activeOnly } }),
  createBusinessProcess: (data: TaxonomyEntryInput) => api.post<TaxonomyEntry>("/taxonomy/business-processes", data),
  updateBusinessProcess: (id: number, data: Partial<TaxonomyEntryInput>) => api.patch<TaxonomyEntry>(`/taxonomy/business-processes/${id}`, data),
  deactivateBusinessProcess: (id: number) => api.delete(`/taxonomy/business-processes/${id}`),

  testCaseTypes: (activeOnly = false) => api.get<TaxonomyEntry[]>("/taxonomy/test-case-types", { params: { active_only: activeOnly } }),
  createTestCaseType: (data: TaxonomyEntryInput) => api.post<TaxonomyEntry>("/taxonomy/test-case-types", data),
  updateTestCaseType: (id: number, data: Partial<TaxonomyEntryInput>) => api.patch<TaxonomyEntry>(`/taxonomy/test-case-types/${id}`, data),
  deactivateTestCaseType: (id: number) => api.delete(`/taxonomy/test-case-types/${id}`),

  testCaseComplexities: (activeOnly = false) => api.get<TaxonomyEntry[]>("/taxonomy/test-case-complexities", { params: { active_only: activeOnly } }),
  createTestCaseComplexity: (data: TaxonomyEntryInput) => api.post<TaxonomyEntry>("/taxonomy/test-case-complexities", data),
  updateTestCaseComplexity: (id: number, data: Partial<TaxonomyEntryInput>) => api.patch<TaxonomyEntry>(`/taxonomy/test-case-complexities/${id}`, data),
  deactivateTestCaseComplexity: (id: number) => api.delete(`/taxonomy/test-case-complexities/${id}`),

  environments: (activeOnly = false) => api.get<TaxonomyEntry[]>("/taxonomy/environments", { params: { active_only: activeOnly } }),
  createEnvironment: (data: TaxonomyEntryInput) => api.post<TaxonomyEntry>("/taxonomy/environments", data),
  updateEnvironment: (id: number, data: Partial<TaxonomyEntryInput>) => api.patch<TaxonomyEntry>(`/taxonomy/environments/${id}`, data),
  deactivateEnvironment: (id: number) => api.delete(`/taxonomy/environments/${id}`),

  relationships: (params?: { relation_type?: TaxonomyRelationType; from_id?: number; to_id?: number }) =>
    api.get<TaxonomyRelationship[]>("/taxonomy/relationships", { params }),
  createRelationship: (data: { relation_type: TaxonomyRelationType; from_id: number; to_id: number }) =>
    api.post<TaxonomyRelationship>("/taxonomy/relationships", data),
  deleteRelationship: (id: number) => api.delete(`/taxonomy/relationships/${id}`),
};

// ── Plan Test Case Enrollment (UAT template: Environment / Tester / ────────
// Planned Execution Sequence, per test plan cycle) ───────────────────────────

export interface PlanTestCaseEnrollment {
  id: number;
  test_plan_id: number;
  test_case_id: number;
  test_case_display_id?: string | null;
  test_case_title?: string | null;
  environment_id?: number | null;
  environment_name?: string | null;
  tester_user_id?: number | null;
  planned_execution_sequence?: string | null;
  order_index: number;
  created_by?: number | null;
  created_at: string;
  updated_at: string;
}

export const planTestCasesApi = {
  list: (planId: number) => api.get<PlanTestCaseEnrollment[]>(`/test-plans/${planId}/cases`),
  enroll: (
    planId: number,
    data: { test_case_id: number; environment_id?: number | null; tester_user_id?: number | null; planned_execution_sequence?: string | null },
  ) => api.post<PlanTestCaseEnrollment>(`/test-plans/${planId}/cases`, data),
  update: (
    planId: number,
    enrollmentId: number,
    data: { environment_id?: number | null; tester_user_id?: number | null; planned_execution_sequence?: string | null; order_index?: number },
  ) => api.patch<PlanTestCaseEnrollment>(`/test-plans/${planId}/cases/${enrollmentId}`, data),
  reorder: (planId: number, orderedEnrollmentIds: number[]) =>
    api.post<PlanTestCaseEnrollment[]>(`/test-plans/${planId}/cases/reorder`, { ordered_enrollment_ids: orderedEnrollmentIds }),
  remove: (planId: number, enrollmentId: number) =>
    api.delete<{ message: string }>(`/test-plans/${planId}/cases/${enrollmentId}`),
};

// ── Test Automation Classification & Routing (P1-S3 extension) ──────────────
// Governed, policy-driven automation-candidate classification. Every field
// here is either persisted from the deterministic rules engine, the
// governed classification agent, or a human reviewer/approver — never a
// static frontend list. See docs/test-automation-classification-routing-
// implementation-prompt.md. Available for every project.

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
  // Project classification state is loaded separately from test-case content.
  listForProject: (projectId: number) =>
    api.get<TestCaseAutomationClassification[]>(`/automation-classifications/projects/${projectId}`),
  effectivePolicy: (projectId: number, applicationId?: number) =>
    api.get<AutomationClassificationPolicy>(`/automation-classifications/projects/${projectId}/policies/effective`, {
      params: applicationId ? { application_id: applicationId } : undefined,
    }),
  updateProjectPolicy: (projectId: number, data: { name: string; rules: Record<string, unknown> }) =>
    api.put<AutomationClassificationPolicy>(`/automation-classifications/projects/${projectId}/policies`, data),
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

/** Mirrors the server's runner policy (`VALID_MODES`). "executor" brokers the
 *  containers through the runner-executor service, which is the only one that
 *  mounts the Docker socket; "docker" drives the daemon from the calling
 *  service and is therefore refused wherever that socket is absent. */
export type StudioRunnerMode = "local" | "docker" | "executor";

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
  runner_mode?: StudioRunnerMode;
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
  created_at?: string | null;
  updated_at?: string | null;
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
  /** Whether a retry is available — true for a failed run AND for one that
   *  finished with failed executions, which still reports status "completed". */
  can_retry?: boolean;
  /** Test cases whose latest script failed — what "regenerate only the failed
   *  ones" acts on. */
  failed_test_case_ids?: number[];
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
  runner_mode?: StudioRunnerMode;
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
  /** Resumes a failed run from the stage that failed, keeping the approved
   *  plan and test cases — never re-crawls unless nothing approvable exists. */
  retryRun: (runId: number, runnerMode?: string, onlyFailed?: boolean) =>
    api.post<{
      studio_run_id: number;
      status: string;
      stage: "generation" | "exploration" | "execution";
      agent_run_ids: number[];
      execution_run_ids: number[];
      test_case_count: number;
      message: string;
    }>(`/playwright-studio/runs/${runId}/retry`, {
      ...(runnerMode ? { runner_mode: runnerMode } : {}),
      ...(onlyFailed ? { only_failed: true } : {}),
    }),
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
  // UAT template fields (migration 042).
  tested_by_id?: number | null;
  tested_by_name?: string | null;
  sit_status?: "not_started" | "passed" | "failed" | "n_a" | null;
  blocking_defect_id?: number | null;
  blocking_defect_display_id?: string | null;
  other_reason?: string | null;
  created_at: string;
  updated_at: string;
}

// UAT template's "Overall Status" execution outcome vocabulary.
export type OverallStatus = "pending" | "pass" | "fail" | "skip" | "error" | "blocked" | "not_run" | "running" | "passed_with_snag";

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
  // UAT template tracking for a single result: Overall Status outcome (incl.
  // "Passed with Snag"), Tested By, SIT status, Blocking Snag ID / Other Reason.
  updateManualResultUat: (
    resultId: number,
    patch: {
      status?: OverallStatus;
      tested_by_id?: number | null;
      sit_status?: "not_started" | "passed" | "failed" | "n_a";
      blocking_defect_id?: number | null;
      other_reason?: string;
    },
  ) => api.patch<ExecutionResult>(`/execution/manual/results/${resultId}/uat`, patch),

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

// ── Test Case Import (CSV/XLSX, canonical 35-column format) ────────────────

export interface TestCaseImportPreview {
  preview_token: string;
  filename: string;
  file_type: string;
  detected_columns: string[];
  row_count: number;
  preview_rows: Array<Record<string, unknown>>;
  validation_errors: Array<{ row_number?: number; test_case_id?: string; message: string }>;
  validation_warnings: Array<{ row_number?: number; message: string }>;
  can_import: boolean;
}

export interface TestCaseImportConfirmResult {
  imported_count: number;
  skipped_count: number;
  created_test_case_ids: number[];
  validation_summary: Record<string, unknown>;
}

export const testCaseImportApi = {
  preview: (projectId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<TestCaseImportPreview>(`/test-cases/projects/${projectId}/import/preview`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  confirm: (projectId: number, previewToken: string) =>
    api.post<TestCaseImportConfirmResult>(`/test-cases/projects/${projectId}/import/confirm`, {
      preview_token: previewToken,
    }),
};

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
    testCaseIds?: number[],
    filename?: string,
  ) => {
    const response = await api.get(
      `/traceability/projects/${projectId}/export/test-cases`,
      {
        params: {
          format,
          include_drafts,
          test_case_ids: testCaseIds?.length ? testCaseIds.join(",") : undefined,
        },
        responseType: "blob",
      }
    );
    const ext = format === "excel" ? "xlsx" : "csv";
    const suffix = format === "xray" ? "_xray" : "";
    _triggerDownload(response.data as Blob, filename || `test_cases_project_${projectId}${suffix}.${ext}`);
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

// ── UI-015 Live Discovery Session (P1-S4, Phase 1: Guided User Recording) ──

export interface EligibleTestCase {
  test_case_id: number;
  display_id: string;
  title: string;
  requirement_ref: string | null;
  scenario_ref: string | null;
  approval_status: string;
  eligible: boolean;
  blocking_reason: string | null;
}

export interface DiscoverySession {
  id: number;
  project_id: number;
  application_id: number;
  environment: string;
  mode: "GUIDED_USER" | "FREE_USER_ACTION" | "SUPERVISED_AGENT_DRIVEN";
  status: string;
  browser_target: string | null;
  framework: string;
  auth_profile_reference: string | null;
  test_case_id: number | null;
  test_case_version: number | null;
  requirement_ref: string | null;
  ppm_ref: string | null;
  journey_ref: string | null;
  scenario_ref: string | null;
  purpose: string | null;
  evidence_policy: Record<string, unknown>;
  capture_options: Record<string, unknown>;
  allowed_hosts: string[];
  owner_id: number | null;
  created_by: number | null;
  started_at: string | null;
  terminal_at: string | null;
  terminal_reason: string | null;
  failure_detail: string | null;
  latest_checkpoint_id: number | null;
  draft_model_version_id: number | null;
  correlation_id: string | null;
  current_step_index: number;
  resume_state_classification: string | null;
  metadata_: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ReadinessCheckResult {
  name: string;
  passed: boolean;
  detail: string;
}

export interface ReadinessResult {
  ready: boolean;
  checks: ReadinessCheckResult[];
}

export interface DiscoveryLocatorCandidate {
  strategy: string;
  value: string;
  locator: string;
  confidence: number;
  unique: boolean;
  validated: boolean;
}

export interface DiscoveryLocatorEvidence {
  element_name: string;
  role: string | null;
  page_url: string | null;
  candidates: DiscoveryLocatorCandidate[];
}

export interface DiscoveryAction {
  id: number;
  session_id: number;
  sequence: number;
  actor: string;
  test_step_ref: string | null;
  action_family: string;
  target_semantic: string | null;
  target_screen_ref: string | null;
  occurred_at: string;
  duration_ms: number | null;
  evidence_refs: number[];
  locator_confidence: number | null;
  locator_evidence: DiscoveryLocatorEvidence | null;
  inclusion_state: string;
  issue_note: string | null;
  reviewer_note: string | null;
  input_binding: Record<string, unknown> | null;
  post_state: { accessibility_snapshot_excerpt?: string } & Record<string, unknown> | null;
}

export interface DiscoveryCapture {
  id: number;
  session_id: number;
  capture_type: "screenshot" | "dom_snapshot" | "accessibility_tree" | "network_log" | "console_log" | "trace" | "video";
  checksum: string | null;
  source: string | null;
  captured_at: string;
  redaction_state: string;
  retention_state: string;
}

export interface DiscoveryCheckpoint {
  id: number;
  session_id: number;
  sequence: number;
  state_at_checkpoint: string;
  action_position: number | null;
  sanitized_url: string | null;
  sanitized_screen: string | null;
  resumable: boolean;
  expires_at: string | null;
  created_by_actor: string;
  created_at: string;
}

export interface DiscoverySessionEvent {
  id: number;
  session_id: number;
  actor_id: number | null;
  actor_type: string;
  previous_state: string | null;
  new_state: string;
  command: string | null;
  reason: string | null;
  idempotency_key: string | null;
  correlation_id: string | null;
  occurred_at: string;
}

const ACTIVE_DISCOVERY_STATUSES = new Set([
  "INITIALISING", "RECORDING", "PAUSE_REQUESTED", "RESUMING", "STOP_REQUESTED",
]);

export function isActiveDiscoverySession(session: Pick<DiscoverySession, "status"> | undefined | null): boolean {
  return Boolean(session && ACTIVE_DISCOVERY_STATUSES.has(session.status));
}

export const discoveryApi = {
  eligibleTestCases: (projectId: number, applicationId: number, mode: string) =>
    api.get<EligibleTestCase[]>(`/discovery/projects/${projectId}/eligible-test-cases`, {
      params: { application_id: applicationId, mode },
    }),
  createSession: (projectId: number, payload: {
    application_id: number; environment: string; mode: string; test_case_id?: number | null;
    purpose?: string | null; browser_target?: string | null; framework?: string;
    auth_profile_reference?: string | null; correlation_id?: string | null;
  }) => api.post<DiscoverySession>(`/discovery/projects/${projectId}/sessions`, payload),
  listSessions: (projectId: number, params?: { application_id?: number; status?: string }) =>
    api.get<DiscoverySession[]>(`/discovery/projects/${projectId}/sessions`, { params }),
  getSession: (sessionId: number) => api.get<DiscoverySession>(`/discovery/sessions/${sessionId}`),
  evaluateReadiness: (sessionId: number) =>
    api.post<ReadinessResult>(`/discovery/sessions/${sessionId}/readiness`),
  getCurrentStep: (sessionId: number) =>
    api.get<{ text: string | null; step_ref: string | null }>(`/discovery/sessions/${sessionId}/current-step`),
  issueCommand: (sessionId: number, payload: {
    command: string; idempotency_key: string; reason?: string | null; params?: Record<string, unknown>;
  }) => api.post<DiscoverySession>(`/discovery/sessions/${sessionId}/commands`, payload),
  listActions: (sessionId: number) => api.get<DiscoveryAction[]>(`/discovery/sessions/${sessionId}/actions`),
  recordAction: (sessionId: number, payload: {
    idempotency_key: string; action_family: string; target_ref?: string | null;
    target_semantic?: string | null; input_text?: string | null; url?: string | null;
  }) => api.post<DiscoverySession>(`/discovery/sessions/${sessionId}/actions`, payload),
  correctAction: (sessionId: number, actionId: number, payload: {
    inclusion_state: string; reviewer_note?: string | null; reason?: string | null; mapped_test_step_ref?: string | null;
  }) => api.post<DiscoveryAction>(`/discovery/sessions/${sessionId}/actions/${actionId}/correct`, payload),
  listCheckpoints: (sessionId: number) =>
    api.get<DiscoveryCheckpoint[]>(`/discovery/sessions/${sessionId}/checkpoints`),
  getActivity: (sessionId: number) =>
    api.get<DiscoverySessionEvent[]>(`/discovery/sessions/${sessionId}/activity`),
  listCaptures: (sessionId: number, actionId: number) =>
    api.get<DiscoveryCapture[]>(`/discovery/sessions/${sessionId}/captures`, { params: { action_id: actionId } }),
  getCaptureContent: (sessionId: number, captureId: number) =>
    api.get<string>(`/discovery/sessions/${sessionId}/captures/${captureId}/content`),
};

// ─── UI-016 Application Model (Phase 1) ─────────────────────────────────────

export type ApplicationModelStatus =
  | "draft" | "pending_review" | "changes_requested" | "approved" | "published"
  | "superseded" | "rejected" | "stale" | "archived";

/**
 * What script generation would ground one application on right now.
 *
 * Distinct from "does a published model exist": a model can be published and
 * still contribute nothing — no element carrying a usable locator, or every
 * element marked unstable by a reviewer — in which case generation grounds on
 * the raw locator_map alone. The common case is BOTH: the model supplies the
 * elements it has reviewed locators for and locator_map fills the rest, which
 * is what "application_model+locator_map" reports. `source` is the resolved
 * answer, so the studio can report what a script will actually be built from
 * rather than inferring it.
 */
export interface GroundingSource {
  application_id: number;
  source: "application_model" | "application_model+locator_map" | "locator_map" | "none";
  element_count: number;
  model_id: number | null;
  model_version: number | null;
}

export interface ApplicationModel {
  id: number;
  project_id: number;
  application_id: number;
  source_session_id: number | null;
  version: number;
  parent_model_id: number | null;
  is_current: boolean;
  status: ApplicationModelStatus;
  built_by: number | null;
  built_at: string | null;
  reviewed_by: number | null;
  reviewed_at: string | null;
  approved_by: number | null;
  approved_at: string | null;
  published_by: number | null;
  published_at: string | null;
  decision_reason: string | null;
  built_from_action_count: number;
  created_at: string;
  updated_at: string;
}

export interface ApplicationModelKpis {
  screens: number;
  components: number;
  elements: number;
  journeys: number;
  apis: number;
  gaps_open: number;
  gaps_critical_open: number;
  gaps_total: number;
}

export interface ApplicationModelDetail extends ApplicationModel {
  kpis: ApplicationModelKpis;
  stale: boolean;
  /** Whether this deployment requires a different person to approve than the
   *  one who built. The server enforces it regardless; this only lets the UI
   *  state the rule actually in force instead of assuming it. */
  requires_separate_approver: boolean;
}

export type ApplicationModelNodeType =
  | "application" | "environment" | "journey" | "scenario" | "test_case" | "screen"
  | "view" | "dialog" | "component" | "element" | "api" | "external_system" | "validator"
  | "evidence" | "gap";

export interface ApplicationModelNode {
  id: number;
  model_id: number;
  node_type: ApplicationModelNodeType;
  parent_node_id: number | null;
  external_ref: string;
  display_name: string;
  description: string | null;
  state: string;
  attributes: Record<string, unknown>;
}

export interface ApplicationModelEdge {
  id: number;
  model_id: number;
  edge_type: "CONTAINS" | "NAVIGATES_TO";
  from_node_id: number;
  to_node_id: number;
}

export interface ApplicationModelGap {
  id: number;
  model_id: number;
  gap_type: string;
  severity: "critical" | "warning";
  node_id: number | null;
  evidence: Record<string, unknown>;
  remediation: string | null;
  owner_id: number | null;
  status: "open" | "resolved";
  reviewer_notes: string | null;
  resolved_by: number | null;
  resolved_at: string | null;
}

export interface LocatorEvidenceEntry {
  id: number;
  node_id: number;
  locator_value: string | null;
  locator_type: string | null;
  confidence: number | null;
  status: "candidate" | "confirmed" | "unstable" | "fallback";
  source_action_id: number | null;
  reason: string | null;
  created_by: number | null;
  created_at: string;
}

export interface ApplicationModelActivityEntry {
  id: string;
  at: string;
  actor_id: number | null;
  event_type: string;
  node_id: number | null;
  reason: string | null;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
}

export const applicationModelsApi = {
  list: (projectId: number, applicationId: number) =>
    api.get<ApplicationModel[]>(`/lab/application-models/projects/${projectId}/applications/${applicationId}/models`),
  grounding: (projectId: number, applicationId: number) =>
    api.get<GroundingSource>(
      `/lab/application-models/projects/${projectId}/applications/${applicationId}/grounding`,
    ),
  get: (modelId: number) => api.get<ApplicationModelDetail>(`/lab/application-models/${modelId}`),
  build: (payload: { project_id: number; application_id: number; session_id: number }) =>
    api.post<ApplicationModelDetail>(`/lab/application-models/build`, payload),
  nodes: (modelId: number, nodeType?: ApplicationModelNodeType) =>
    api.get<ApplicationModelNode[]>(`/lab/application-models/${modelId}/nodes`, {
      params: nodeType ? { node_type: nodeType } : undefined,
    }),
  edges: (modelId: number) => api.get<ApplicationModelEdge[]>(`/lab/application-models/${modelId}/edges`),
  gaps: (modelId: number, status?: "open" | "resolved") =>
    api.get<ApplicationModelGap[]>(`/lab/application-models/${modelId}/gaps`, { params: status ? { status } : undefined }),
  locatorHistory: (modelId: number, nodeId: number) =>
    api.get<LocatorEvidenceEntry[]>(`/lab/application-models/${modelId}/nodes/${nodeId}/locator-history`),
  submitReview: (modelId: number) => api.post<ApplicationModelDetail>(`/lab/application-models/${modelId}/submit-review`),
  requestChanges: (modelId: number, reason: string) =>
    api.post<ApplicationModelDetail>(`/lab/application-models/${modelId}/request-changes`, { reason }),
  reject: (modelId: number, reason: string) =>
    api.post<ApplicationModelDetail>(`/lab/application-models/${modelId}/reject`, { reason }),
  approve: (modelId: number, reason?: string | null) =>
    api.post<ApplicationModelDetail>(`/lab/application-models/${modelId}/approve`, { reason: reason ?? null }),
  publish: (modelId: number) => api.post<ApplicationModelDetail>(`/lab/application-models/${modelId}/publish`),
  newDraft: (modelId: number) => api.post<ApplicationModelDetail>(`/lab/application-models/${modelId}/new-draft`),
  renameNode: (modelId: number, nodeId: number, displayName: string) =>
    api.patch<ApplicationModelNode>(`/lab/application-models/${modelId}/nodes/${nodeId}`, { display_name: displayName }),
  confirmLocator: (modelId: number, nodeId: number) =>
    api.post<LocatorEvidenceEntry>(`/lab/application-models/${modelId}/nodes/${nodeId}/locator/confirm`, {}),
  markLocatorUnstable: (modelId: number, nodeId: number, reason: string) =>
    api.post<LocatorEvidenceEntry>(`/lab/application-models/${modelId}/nodes/${nodeId}/locator/mark-unstable`, { reason }),
  addFallbackLocator: (modelId: number, nodeId: number, locatorValue: string, locatorType?: string | null) =>
    api.post<LocatorEvidenceEntry>(`/lab/application-models/${modelId}/nodes/${nodeId}/locator/fallback`, {
      locator_value: locatorValue, locator_type: locatorType ?? null,
    }),
  resolveGap: (modelId: number, gapId: number, reviewerNotes?: string | null) =>
    api.post<ApplicationModelGap>(`/lab/application-models/${modelId}/gaps/${gapId}/resolve`, { reviewer_notes: reviewerNotes ?? null }),
  activity: (modelId: number) => api.get<ApplicationModelActivityEntry[]>(`/lab/application-models/${modelId}/activity`),
  exportUrl: (modelId: number) => `/api/v1/lab/application-models/${modelId}/export`,
};

// ─── UI-017 API and Network Explorer (Phase 1) ──────────────────────────────

export type NetworkEventParseState = "parsed" | "unparsed";
export type NetworkEventReviewState = "unreviewed" | "reviewed" | "ignored";

export interface NetworkEvent {
  id: number;
  project_id: number;
  session_id: number;
  capture_id: number;
  action_id: number | null;
  sequence: number;
  parse_state: NetworkEventParseState;
  method: string | null;
  url: string | null;
  host: string | null;
  path: string | null;
  is_external: boolean | null;
  status_code: number | null;
  status_text: string | null;
  raw_line: string;
  review_state: NetworkEventReviewState;
  review_reason: string | null;
  reviewed_by: number | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface NetworkEventKpis {
  requests_captured: number;
  requests_parsed: number;
  requests_unparsed: number;
  apis_identified: number;
  external_systems: number;
  mapping_readiness_pct: number;
  ignored: number;
  validation_available: boolean;
}

export interface NetworkEventActivityEntry {
  id: number;
  session_id: number;
  event_id: number | null;
  event_type: string;
  actor_id: number | null;
  reason: string | null;
  correlation_id: string | null;
  created_at: string;
}

export const networkExplorerApi = {
  build: (payload: { project_id: number; session_id: number }) =>
    api.post<NetworkEventKpis>(`/lab/network-explorer/build`, payload),
  kpis: (sessionId: number) => api.get<NetworkEventKpis>(`/lab/network-explorer/sessions/${sessionId}/kpis`),
  events: (sessionId: number, params?: {
    method?: string; status_bucket?: "2xx" | "3xx" | "4xx" | "5xx"; external_only?: boolean;
    unmapped_only?: boolean; review_state?: NetworkEventReviewState; search?: string;
  }) => api.get<NetworkEvent[]>(`/lab/network-explorer/sessions/${sessionId}/events`, { params }),
  event: (eventId: number) => api.get<NetworkEvent>(`/lab/network-explorer/events/${eventId}`),
  ignore: (eventId: number, reason: string) =>
    api.post<NetworkEvent>(`/lab/network-explorer/events/${eventId}/ignore`, { reason }),
  review: (eventId: number, note?: string | null) =>
    api.post<NetworkEvent>(`/lab/network-explorer/events/${eventId}/review`, { note: note ?? null }),
  activity: (sessionId: number) => api.get<NetworkEventActivityEntry[]>(`/lab/network-explorer/sessions/${sessionId}/activity`),
  exportUrl: (sessionId: number) => `/api/v1/lab/network-explorer/sessions/${sessionId}/export`,
};

// ─── UI-018 Automation Workspace — Automation Test Suite (Phase A) ───────────

export type AutomationSuiteStatus =
  | "DRAFT" | "SCOPE_SELECTED" | "INHERITANCE_REVIEW_REQUIRED" | "MAPPING_INCOMPLETE"
  | "CONFLICT_REVIEW_REQUIRED" | "READY_FOR_VALIDATION" | "VALIDATION_PENDING"
  | "VALIDATION_FAILED" | "READY_FOR_REVIEW" | "APPROVED" | "PUBLISHED" | "DEPRECATED"
  | "ARCHIVED";

export type SuiteMemberStatus = "NOT_EVALUATED" | "READY" | "WARNING" | "BLOCKED";
export type SuiteInclusionStatus = "included" | "excluded" | "manual_only";
export type SuiteGapStatus = "open" | "resolved" | "exception_approved" | "excluded";

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface AutomationSuite {
  id: number;
  project_id: number;
  name: string;
  description: string | null;
  tags: string[];
  status: AutomationSuiteStatus;
  version: number;
  parent_suite_id: number | null;
  is_current: boolean;
  default_environment: string | null;
  owner_id: number | null;
  created_by: number | null;
  archived_by: number | null;
  archived_at: string | null;
  last_evaluated_at: string | null;
  last_inheritance_sync_at: string | null;
  members_total: number;
  members_included: number;
  members_ready: number;
  members_blocked: number;
  members_manual_only: number;
  members_drifted: number;
  gaps_critical_open: number;
  gaps_warning_open: number;
  conflicts_open: number;
  created_at: string;
  updated_at: string;
}

export interface AutomationSuiteListItem {
  id: number;
  name: string;
  description: string | null;
  tags: string[];
  status: AutomationSuiteStatus;
  version: number;
  is_current: boolean;
  default_environment: string | null;
  members_total: number;
  members_included: number;
  members_ready: number;
  members_blocked: number;
  members_manual_only: number;
  members_drifted: number;
  gaps_critical_open: number;
  gaps_warning_open: number;
  conflicts_open: number;
  frameworks: string[];
  application_count: number;
  owner_id: number | null;
  last_evaluated_at: string | null;
  updated_at: string;
  created_at: string;
}

export interface AutomationSuiteOverview {
  suite_id: number;
  name: string;
  description: string | null;
  tags: string[];
  status: AutomationSuiteStatus;
  default_environment: string | null;
  members_total: number;
  members_included: number;
  members_ready: number;
  members_blocked: number;
  members_manual_only: number;
  members_drifted: number;
  gaps_critical_open: number;
  gaps_warning_open: number;
  conflicts_open: number;
  automated_members: number;
  automation_coverage_pct: number;
  inherited_application_count: number;
  inherited_frameworks: string[];
  linked_script_count: number;
  last_evaluated_at: string | null;
  last_inheritance_sync_at: string | null;
  execution_group_count: number | null;
  validation_summary: string | null;
  unavailable: Record<string, string>;
}

export interface AutomationSuiteMember {
  id: number;
  test_case_id: number;
  test_case_reference: string | null;
  title: string | null;
  test_case_status: string | null;
  execution_mode: string | null;
  priority: string | null;
  automation_status: string | null;
  inclusion_status: SuiteInclusionStatus;
  planned_sequence: number | null;
  source_system: string;
  source_reference: string | null;
  member_status: SuiteMemberStatus;
  readiness_checks_passed: number;
  readiness_checks_total: number;
  last_evaluated_at: string | null;
  resolved_application_id: number | null;
  resolved_framework: string | null;
  resolved_environment: string | null;
  resolved_script_id: number | null;
  exclusion_reason: string | null;
}

export interface AutomationSuiteGap {
  id: number;
  suite_id: number;
  suite_test_case_id: number | null;
  test_case_id: number | null;
  gap_type: string;
  scope: "member" | "suite";
  category: "gap" | "conflict";
  severity: "critical" | "warning";
  stage: string;
  reason: string;
  remediation: string | null;
  evidence: Record<string, unknown>;
  status: SuiteGapStatus;
  resolution_action: string | null;
  reviewer_notes: string | null;
  resolved_by: number | null;
  resolved_at: string | null;
  auto_closed: boolean;
  first_detected_at: string;
  last_detected_at: string;
}

export interface AutomationSuiteActivityEntry {
  id: number;
  suite_id: number;
  suite_test_case_id: number | null;
  event_type: string;
  actor_id: number | null;
  reason: string | null;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  created_at: string;
}

export interface SelectableTestCase {
  id: number;
  test_case_reference: string | null;
  title: string | null;
  objective: string | null;
  status: string | null;
  test_type: string | null;
  priority: string | null;
  is_critical: boolean | null;
  execution_mode: string | null;
  automation_status: string | null;
  automation_candidate: boolean | null;
  application_id: number | null;
  requirement_id: number | null;
  test_suite_id: number | null;
  linked_release_version: string | null;
  linked_script_count: number;
  frameworks: string[];
  mapping_status: string;
}

export interface GroundingRow {
  step_number: number | null;
  action: string | null;
  screen: string | null;
  element: string | null;
  locator_status: string | null;
  apis: string[];
  external_validation: string;
  evidence_count: number;
  status: "Complete" | "Partial" | "Missing" | "Ambiguous" | "Stale" | "Blocked";
}

export interface InheritedScopeItem {
  source: string;
  source_entity: string;
  source_id: number | null;
  [key: string]: unknown;
}

export interface AutomationSuiteInheritedScope {
  business_traceability: InheritedScopeItem[];
  applications: InheritedScopeItem[];
  frameworks: InheritedScopeItem[];
  scripts: InheritedScopeItem[];
  environments: InheritedScopeItem[];
  test_data: InheritedScopeItem[];
  owners: InheritedScopeItem[];
  last_synchronized_at: string | null;
  unavailable: Record<string, string>;
}

export interface AutomationSuiteDashboard {
  suites: {
    total: number;
    draft: number;
    active: number;
    archived: number;
    in_review: number;
    published: number;
    created_last_7d: number;
    created_prev_7d: number;
    validation_pending: number | null;
  };
  test_cases: {
    linked_total: number;
    automation_candidates: number;
    automated: number;
    coverage_pct: number;
  };
  automation_assets: {
    scripts: number;
    recordings: number;
    automation_ir: number | null;
    page_objects: number | null;
    reusable_components: number | null;
    api_collections: number | null;
    object_repositories: number | null;
    git_repositories: number | null;
  };
  active_executions: {
    running: number;
    queued: number;
    review_required: number;
    blocked: number | null;
    inconclusive: number | null;
  };
  success_rate: {
    pass_rate_7d: number | null;
    pass_rate_prev_7d: number | null;
    trend: { date: string; pass_rate: number | null }[];
    scope: string;
  };
  unavailable: Record<string, string>;
}

export interface ActiveExecutionRow {
  id: number;
  execution_id: string;
  automation_test_suite: string | null;
  suite_link_available: boolean;
  environment: string | null;
  execution_type: string | null;
  status: string;
  started_at: string | null;
  total_tests: number;
  progress_pct: number | null;
  framework: string | null;
  execution_group: string | null;
}

export interface AutomationSuiteFooterStatus {
  agents: { total: number; connected: number; error: number; not_configured: number };
  qa_environment: string | null;
  storage_usage: string | null;
  server_time: string;
  unavailable: Record<string, string>;
}

export interface SuiteInheritancePreview {
  selected_test_cases: number;
  applications: number;
  frameworks: string[];
  existing_scripts: number;
  recordings: number;
  environments: string[];
  test_data_sources: number;
  requirements: number;
  missing_mappings: number;
  warnings: number;
  conflicts: number;
  blocking_conflicts: number;
  findings: {
    gap_type: string;
    scope: string;
    category: string;
    severity: string;
    stage: string;
    reason: string;
    remediation: string | null;
    test_case_id: number | null;
  }[];
  automation_ir_definitions: number | null;
  defects: number | null;
  change_requests: number | null;
  execution_groups: number | null;
  business_projects: number;
  unavailable: Record<string, string>;
}

export interface CreateSuitePayload {
  name: string;
  description?: string | null;
  tags?: string[];
  test_case_ids?: number[];
  test_suite_ids?: number[];
  default_environment?: string | null;
  idempotency_key?: string | null;
}

export const automationSuiteApi = {
  dashboard: (projectId: number) =>
    api.get<AutomationSuiteDashboard>(`/lab/automation-suites/projects/${projectId}/dashboard`),
  activeExecutions: (projectId: number, limit = 20) =>
    api.get<{ items: ActiveExecutionRow[]; unavailable: Record<string, string> }>(
      `/lab/automation-suites/projects/${projectId}/active-executions`,
      { params: { limit } },
    ),
  footerStatus: (projectId: number) =>
    api.get<AutomationSuiteFooterStatus>(`/lab/automation-suites/projects/${projectId}/footer-status`),

  listSuites: (
    projectId: number,
    params?: { search?: string; status?: string; page?: number; page_size?: number; sort?: string },
  ) =>
    api.get<Paginated<AutomationSuiteListItem>>(
      `/lab/automation-suites/projects/${projectId}/suites`,
      { params },
    ),
  createSuite: (projectId: number, payload: CreateSuitePayload) =>
    api.post<AutomationSuite>(`/lab/automation-suites/projects/${projectId}/suites`, payload),

  selectableTestCases: (
    projectId: number,
    params?: {
      search?: string;
      status?: string;
      automation_status?: string;
      execution_mode?: string;
      automation_candidate?: boolean;
      test_type?: string;
      priority?: string;
      is_critical?: boolean;
      application_id?: number;
      requirement_id?: number;
      test_suite_id?: number;
      framework?: string;
      has_script?: boolean;
      exclude_suite_id?: number;
      page?: number;
      page_size?: number;
    },
  ) =>
    api.get<Paginated<SelectableTestCase>>(
      `/lab/automation-suites/projects/${projectId}/selectable-test-cases`,
      { params },
    ),
  previewInheritance: (
    projectId: number,
    payload: { test_case_ids: number[]; default_environment?: string | null },
  ) =>
    api.post<SuiteInheritancePreview>(
      `/lab/automation-suites/projects/${projectId}/suites/preview-inheritance`,
      payload,
    ),

  getSuite: (suiteId: number) =>
    api.get<AutomationSuiteOverview>(`/lab/automation-suites/suites/${suiteId}`),
  updateSuite: (
    suiteId: number,
    payload: { name?: string; description?: string | null; tags?: string[] },
  ) => api.patch<AutomationSuite>(`/lab/automation-suites/suites/${suiteId}`, payload),
  setDefaultEnvironment: (suiteId: number, environment: string | null) =>
    api.patch<AutomationSuite>(`/lab/automation-suites/suites/${suiteId}/default-environment`, {
      environment,
    }),
  evaluate: (suiteId: number) =>
    api.post<AutomationSuite>(`/lab/automation-suites/suites/${suiteId}/evaluate`),
  archive: (suiteId: number) =>
    api.post<AutomationSuite>(`/lab/automation-suites/suites/${suiteId}/archive`),
  inheritedScope: (suiteId: number) =>
    api.get<AutomationSuiteInheritedScope>(
      `/lab/automation-suites/suites/${suiteId}/inherited-scope`,
    ),

  members: (
    suiteId: number,
    params?: {
      inclusion_status?: string;
      member_status?: string;
      page?: number;
      page_size?: number;
    },
  ) =>
    api.get<Paginated<AutomationSuiteMember>>(`/lab/automation-suites/suites/${suiteId}/members`, {
      params,
    }),
  addMembers: (suiteId: number, payload: { test_case_ids?: number[]; test_suite_ids?: number[] }) =>
    api.post<{
      added: number;
      skipped_duplicate: number;
      rejected: { test_case_id: number; reason: string }[];
    }>(`/lab/automation-suites/suites/${suiteId}/members`, payload),
  updateMember: (
    suiteId: number,
    memberId: number,
    payload: {
      inclusion_status?: SuiteInclusionStatus;
      planned_sequence?: number;
      exclusion_reason?: string;
    },
  ) => api.patch(`/lab/automation-suites/suites/${suiteId}/members/${memberId}`, payload),
  removeMember: (suiteId: number, memberId: number) =>
    api.delete(`/lab/automation-suites/suites/${suiteId}/members/${memberId}`),
  memberGrounding: (suiteId: number, memberId: number) =>
    api.get<GroundingRow[]>(
      `/lab/automation-suites/suites/${suiteId}/members/${memberId}/grounding`,
    ),

  gaps: (
    suiteId: number,
    params?: {
      category?: string;
      severity?: string;
      status?: string;
      member_id?: number;
      page?: number;
      page_size?: number;
    },
  ) =>
    api.get<Paginated<AutomationSuiteGap>>(`/lab/automation-suites/suites/${suiteId}/gaps`, {
      params,
    }),
  resolveGap: (
    suiteId: number,
    gapId: number,
    payload: { resolution_action: string; reviewer_notes?: string | null },
  ) =>
    api.post<AutomationSuiteGap>(
      `/lab/automation-suites/suites/${suiteId}/gaps/${gapId}/resolve`,
      payload,
    ),
  approveException: (suiteId: number, gapId: number, reason: string) =>
    api.post<AutomationSuiteGap>(
      `/lab/automation-suites/suites/${suiteId}/gaps/${gapId}/approve-exception`,
      { reason },
    ),

  activity: (suiteId: number, params?: { page?: number; page_size?: number }) =>
    api.get<Paginated<AutomationSuiteActivityEntry>>(
      `/lab/automation-suites/suites/${suiteId}/activity`,
      { params },
    ),
  exportUrl: (suiteId: number) => `/api/v1/lab/automation-suites/suites/${suiteId}/export`,

  // ── Phase B ──
  executionGroups: (suiteId: number) =>
    api.get<{
      items: AutomationSuiteExecutionGroup[];
      split_dimensions: string[];
      unavailable: Record<string, string>;
    }>(`/lab/automation-suites/suites/${suiteId}/execution-groups`),
  createExecutionGroup: (
    suiteId: number,
    payload: { name: string; framework?: string | null; environment?: string | null; notes?: string | null },
  ) => api.post(`/lab/automation-suites/suites/${suiteId}/execution-groups`, payload),
  splitExecutionGroups: (suiteId: number, dimension: string) =>
    api.post<{ groups_created: number; dimension: string }>(
      `/lab/automation-suites/suites/${suiteId}/execution-groups/split`,
      { dimension },
    ),
  deleteExecutionGroup: (suiteId: number, groupId: number) =>
    api.delete(`/lab/automation-suites/suites/${suiteId}/execution-groups/${groupId}`),
  assignExecutionGroup: (suiteId: number, memberId: number, executionGroupId: number | null) =>
    api.patch(`/lab/automation-suites/suites/${suiteId}/members/${memberId}/execution-group`, {
      execution_group_id: executionGroupId,
    }),

  submitForReview: (suiteId: number) =>
    api.post<AutomationSuite>(`/lab/automation-suites/suites/${suiteId}/submit-for-review`),
  requestChanges: (suiteId: number, reason: string) =>
    api.post<AutomationSuite>(`/lab/automation-suites/suites/${suiteId}/request-changes`, { reason }),
  rejectSuite: (suiteId: number, reason: string) =>
    api.post<AutomationSuite>(`/lab/automation-suites/suites/${suiteId}/reject`, { reason }),
  approveSuite: (suiteId: number, reason?: string | null) =>
    api.post<AutomationSuite>(`/lab/automation-suites/suites/${suiteId}/approve`, {
      reason: reason ?? null,
    }),
  publishSuite: (suiteId: number) =>
    api.post<AutomationSuite>(`/lab/automation-suites/suites/${suiteId}/publish`),

  versions: (suiteId: number) =>
    api.get<{ items: AutomationSuiteVersion[] }>(`/lab/automation-suites/suites/${suiteId}/versions`),
  newVersion: (suiteId: number) =>
    api.post<AutomationSuite>(`/lab/automation-suites/suites/${suiteId}/new-version`),
  snapshot: (suiteId: number) =>
    api.get<AutomationSuiteSnapshot | null>(`/lab/automation-suites/suites/${suiteId}/snapshot`),
  impactReview: (suiteId: number) =>
    api.get<AutomationSuiteImpactReview>(`/lab/automation-suites/suites/${suiteId}/impact-review`),
};

export interface AutomationSuiteExecutionGroup {
  id: number | null;
  name: string;
  sequence: number;
  status: string;
  framework: string | null;
  environment: string | null;
  application_id: number | null;
  notes: string | null;
  member_count: number;
  created_at: string | null;
}

export interface AutomationSuiteVersion {
  suite_id: number;
  version: number;
  status: AutomationSuiteStatus;
  is_current: boolean;
  submitted_by: number | null;
  approved_by: number | null;
  published_by: number | null;
  published_at: string | null;
  decision_reason: string | null;
  members_included: number;
  snapshot_checksum: string | null;
  created_at: string;
}

export interface AutomationSuiteSnapshot {
  id: number;
  suite_id: number;
  suite_version: number;
  members: Record<string, unknown>[];
  execution_groups: Record<string, unknown>[];
  summary: Record<string, unknown>;
  checksum: string;
  created_by: number | null;
  created_at: string;
}

export interface AutomationSuiteImpactReview {
  snapshot:
    | {
        suite_version: number;
        checksum: string;
        member_count: number;
        created_at: string;
      }
    | null;
  reason?: string;
  changed_members?: { member_id: number; test_case_id: number; reasons: string[] }[];
  impact_review_required?: boolean;
}

// ─── UI-019 Live Recorder (P1-S5 Automation Studio Core) ────────────────────

export type RecordingMode = "GUIDED_TEST_CASE" | "EXPLORATORY";

export type RecorderStepStatus =
  | "PENDING" | "ACTIVE" | "RECORDED" | "PARTIALLY_RECORDED"
  | "SKIPPED" | "MISMATCH" | "NEEDS_REVIEW" | "COMPLETED";

/**
 * A Live Recorder recording is a DiscoverySession with the recorder columns
 * set — the same capture engine, state machine and evidence contract as
 * UI-015. `status` therefore uses the discovery session states.
 */
export interface Recording {
  id: number;
  project_id: number;
  suite_id: number | null;
  suite_member_id: number | null;
  test_case_id: number | null;
  test_case_version: number | null;
  application_id: number;
  environment: string;
  framework: string;
  status: string;
  recording_mode: RecordingMode | null;
  recording_origin: string;
  recording_version: number;
  parent_recording_id: number | null;
  ir_status: string;
  current_step_index: number;
  purpose: string | null;
  requirement_ref: string | null;
  scenario_ref: string | null;
  started_at: string | null;
  terminal_at: string | null;
  terminal_reason: string | null;
  failure_detail: string | null;
  resume_state_classification: string | null;
  latest_checkpoint_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface RecorderInheritedContext {
  suite: { id: number; name: string; version: number; status: string } | null;
  test_case: {
    id: number;
    display_id: string;
    title: string;
    objective: string | null;
    test_type: string | null;
    priority: string;
    is_critical: boolean;
    status: string;
    version: number;
    automation_status: string;
    preconditions: string[] | null;
  } | null;
  application: { id: number; name: string; type: string | null } | null;
  environment: string;
  framework: string;
  recording_mode: RecordingMode | null;
  requirement_ref: string | null;
  scenario_ref: string | null;
  test_data: { id: number; name: string | null; status: string }[];
  existing_script: { id: number; framework: string; status: string; version: number } | null;
  application_model: { id: number; version: number; is_stale: boolean } | null;
}

export interface RecorderPrecondition {
  name: string;
  passed: boolean;
  blocking: boolean;
  detail: string;
  remediation_href: string | null;
}

export interface RecorderPreconditionResult {
  ready: boolean;
  checks: RecorderPrecondition[];
  blockers: RecorderPrecondition[];
  advisories: RecorderPrecondition[];
}

export interface RecorderStep {
  step_key: string;
  source_step_index: number | null;
  action_text: string | null;
  expected_result: string | null;
  status: RecorderStepStatus;
  recorded_action_count: number;
  checkpoint_count: number;
  accepted_checkpoint_count: number;
  skip_reason: string | null;
  is_discovered_substep: boolean;
  parent_step_key: string | null;
  status_reason: string;
}

export interface RecorderLocatorCandidate {
  strategy: string;
  value: string;
  locator: string;
  confidence: number;
  unique: boolean;
  validated: boolean;
}

export interface RecorderLocatorEvidence {
  element_name: string;
  role: string | null;
  page_url: string | null;
  candidates: RecorderLocatorCandidate[];
}

export interface RecordedAction {
  id: number;
  sequence: number;
  actor: string;
  action_family: string;
  target_semantic: string | null;
  test_step_ref: string | null;
  input_binding: Record<string, unknown> | null;
  occurred_at: string;
  duration_ms: number | null;
  evidence_refs: number[];
  locator_evidence: RecorderLocatorEvidence | null;
  locator_confidence: number | null;
  inclusion_state: string;
  issue_note: string | null;
  reviewer_note: string | null;
}

export interface RecorderStepMapping {
  id: number;
  action_id: number;
  step_key: string;
  mapping_source: string;
  confidence: number | null;
  review_state: string;
  lifecycle_phase: string | null;
  excluded_from_ir: boolean;
  exclusion_reason: string | null;
}

export interface RecorderCheckpoint {
  id: number;
  action_id: number | null;
  step_key: string | null;
  checkpoint_type: string;
  target: string | null;
  expected_value: string | null;
  source: string;
  review_state: string;
  recommendation_reason: string | null;
  expected_result_ref: string | null;
  evidence_capture_id: number | null;
  reviewed_by: number | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface RecorderSegment {
  id: number;
  sequence: number;
  application_id: number;
  environment: string;
  framework: string | null;
  adapter: string | null;
  started_at: string;
  ended_at: string | null;
  start_action_sequence: number | null;
  end_action_sequence: number | null;
  transition_reason: string | null;
}

export interface RecorderDataBinding {
  id: number;
  action_id: number | null;
  name: string;
  placeholder: string;
  classification: string;
  test_data_id: number | null;
  secret_reference: string | null;
  source_action_id: number | null;
  environment_key: string | null;
  sample_value: string | null;
}

export interface RecorderNote {
  id: number;
  scope: string;
  step_key: string | null;
  action_id: number | null;
  checkpoint_id: number | null;
  segment_id: number | null;
  body: string;
  created_by: number | null;
  created_at: string;
}

export interface RecorderCapture {
  id: number;
  action_id: number | null;
  capture_type: string;
  captured_at: string;
  source: string | null;
  redaction_state: string;
  retention_state: string;
}

export interface RecorderLatestView {
  action_id: number | null;
  sequence: number | null;
  screenshot_capture_id: number | null;
  accessibility_snapshot: string | null;
  page_url: string | null;
  captured_at: string | null;
}

/** A figure that reports why it has no value rather than defaulting to zero. */
export interface RecorderMeasure {
  value: number | null;
  reason: string | null;
}

export interface RecordingSummary {
  session_id: number;
  status: string;
  recording_mode: RecordingMode | null;
  recording_version: number;
  ir_status: string;
  duration_seconds: number | null;
  recorded_actions: number;
  excluded_actions: number;
  test_case_coverage: {
    total_steps: number;
    recorded_steps: number;
    skipped_steps: number;
    steps_without_actions: number;
    percent: number | null;
    percent_basis: string;
  };
  unmapped_actions: {
    action_id: number; sequence: number; action_family: string; target_semantic: string | null;
  }[];
  missing_steps: { step_key: string; action_text: string | null }[];
  expected_results_without_checkpoints: { step_key: string; expected_result: string | null }[];
  checkpoints: { total: number; accepted: number; needs_review: number; rejected: number };
  applications_visited: {
    segment: number; application_id: number; environment: string; transition_reason: string | null;
  }[];
  network_requests: RecorderMeasure;
  network_failures: RecorderMeasure;
  console_errors: RecorderMeasure;
  console_warnings: RecorderMeasure;
  locator_warnings: { action_id: number; sequence: number; confidence: number | null; detail: string }[];
  evidence_generated: Record<string, number>;
  redactions: { inputs: number; captures: number };
  unsupported_actions: { occurred_at: string | null; detail: string | null }[];
  unbound_inputs: {
    action_id: number; sequence: number; target_semantic: string | null;
    sample_value: string | null; requires_secret_reference: boolean;
  }[];
  data_bindings: number;
  notes: number;
}

export interface AutomationIrDraft {
  id: number;
  session_id: number;
  suite_id: number | null;
  test_case_id: number;
  version: number;
  is_current: boolean;
  status: string;
  contract: Record<string, unknown>;
  contract_version: string;
  source_action_ids: number[];
  readiness: {
    unresolved: {
      kind: string; detail: string; action_id?: number; sequence?: number; checkpoint_id?: number;
    }[];
    unresolved_count: number;
    step_count: number;
    assertion_count: number;
    custom_step_count: number;
    ready_for_script_generation: boolean;
  };
  generated_by: number | null;
  created_at: string;
}

/** States in which a live capture task is attached and polling for commands. */
const LIVE_RECORDING_STATUSES = new Set([
  "INITIALISING", "RECORDING", "PAUSE_REQUESTED", "RESUMING", "STOP_REQUESTED",
]);

export function isLiveRecording(recording: Pick<Recording, "status"> | undefined | null): boolean {
  return Boolean(recording && LIVE_RECORDING_STATUSES.has(recording.status));
}

/** A recording that has produced its final action set — summary and IR apply. */
export function isCapturedRecording(recording: Pick<Recording, "status"> | undefined | null): boolean {
  return Boolean(recording && ["STOPPED", "PAUSED", "COMPLETED"].includes(recording.status));
}

const RECORDER_BASE = "/lab/recorder";

export const recorderApi = {
  create: (projectId: number, payload: {
    suite_id: number; test_case_id: number; recording_mode: RecordingMode;
    environment?: string | null; correlation_id?: string | null;
  }) => api.post<Recording>(`${RECORDER_BASE}/projects/${projectId}/recordings`, payload),
  list: (projectId: number, params?: { suite_id?: number; test_case_id?: number; status?: string }) =>
    api.get<Recording[]>(`${RECORDER_BASE}/projects/${projectId}/recordings`, { params }),
  get: (sessionId: number) => api.get<Recording>(`${RECORDER_BASE}/recordings/${sessionId}`),
  inheritedContext: (sessionId: number) =>
    api.get<RecorderInheritedContext>(`${RECORDER_BASE}/recordings/${sessionId}/inherited-context`),
  preconditions: (sessionId: number) =>
    api.get<RecorderPreconditionResult>(`${RECORDER_BASE}/recordings/${sessionId}/preconditions`),
  command: (sessionId: number, payload: {
    command: string; idempotency_key: string; reason?: string | null; params?: Record<string, unknown>;
  }) => api.post<Recording>(`${RECORDER_BASE}/recordings/${sessionId}/commands`, payload),
  discard: (sessionId: number, reason: string) =>
    api.post<Recording>(`${RECORDER_BASE}/recordings/${sessionId}/discard`, { reason }),
  newVersion: (sessionId: number, reason: string) =>
    api.post<Recording>(`${RECORDER_BASE}/recordings/${sessionId}/new-version`, { reason }),

  steps: (sessionId: number) => api.get<RecorderStep[]>(`${RECORDER_BASE}/recordings/${sessionId}/steps`),
  activeStep: (sessionId: number) =>
    api.get<{ step_key: string | null }>(`${RECORDER_BASE}/recordings/${sessionId}/active-step`),
  activateStep: (sessionId: number, stepKey: string) =>
    api.post<RecorderStep[]>(
      `${RECORDER_BASE}/recordings/${sessionId}/steps/${encodeURIComponent(stepKey)}/activate`,
    ),
  setStepStatus: (sessionId: number, stepKey: string, payload: { status: string; reason?: string | null }) =>
    api.post<RecorderStep[]>(
      `${RECORDER_BASE}/recordings/${sessionId}/steps/${encodeURIComponent(stepKey)}/status`,
      payload,
    ),
  addDiscoveredSubstep: (sessionId: number, payload: { parent_step_key: string; label: string }) =>
    api.post<RecorderStep[]>(`${RECORDER_BASE}/recordings/${sessionId}/steps/discovered`, payload),

  actions: (sessionId: number) => api.get<RecordedAction[]>(`${RECORDER_BASE}/recordings/${sessionId}/actions`),
  recordAction: (sessionId: number, payload: {
    idempotency_key: string; action_family: string; target_ref?: string | null;
    target_semantic?: string | null; input_text?: string | null; url?: string | null;
    active_step_key?: string | null;
  }) => api.post<Recording>(`${RECORDER_BASE}/recordings/${sessionId}/actions`, payload),
  mappings: (sessionId: number) =>
    api.get<RecorderStepMapping[]>(`${RECORDER_BASE}/recordings/${sessionId}/mappings`),
  mapAction: (sessionId: number, actionId: number, stepKey: string | null) =>
    api.post<RecorderStepMapping | null>(
      `${RECORDER_BASE}/recordings/${sessionId}/actions/${actionId}/map`,
      { step_key: stepKey },
    ),
  updateMapping: (sessionId: number, actionId: number, payload: {
    lifecycle_phase?: string | null; excluded_from_ir?: boolean;
    exclusion_reason?: string | null; review_state?: string;
  }) => api.patch<RecorderStepMapping>(
    `${RECORDER_BASE}/recordings/${sessionId}/actions/${actionId}/mapping`,
    payload,
  ),

  checkpoints: (sessionId: number) =>
    api.get<RecorderCheckpoint[]>(`${RECORDER_BASE}/recordings/${sessionId}/checkpoints`),
  createCheckpoint: (sessionId: number, payload: {
    checkpoint_type: string; step_key?: string | null; action_id?: number | null;
    target?: string | null; expected_value?: string | null; expected_result_ref?: string | null;
  }) => api.post<RecorderCheckpoint>(`${RECORDER_BASE}/recordings/${sessionId}/checkpoints`, payload),
  reviewCheckpoint: (sessionId: number, checkpointId: number, payload: {
    review_state: string; expected_value?: string | null;
  }) => api.post<RecorderCheckpoint>(
    `${RECORDER_BASE}/recordings/${sessionId}/checkpoints/${checkpointId}/review`,
    payload,
  ),
  deleteCheckpoint: (sessionId: number, checkpointId: number) =>
    api.delete<void>(`${RECORDER_BASE}/recordings/${sessionId}/checkpoints/${checkpointId}`),

  segments: (sessionId: number) => api.get<RecorderSegment[]>(`${RECORDER_BASE}/recordings/${sessionId}/segments`),
  transitionSegment: (sessionId: number, payload: {
    application_id: number; environment: string; transition_reason: string;
  }) => api.post<RecorderSegment>(`${RECORDER_BASE}/recordings/${sessionId}/segments/transition`, payload),

  dataBindings: (sessionId: number) =>
    api.get<RecorderDataBinding[]>(`${RECORDER_BASE}/recordings/${sessionId}/data-bindings`),
  upsertDataBinding: (sessionId: number, payload: {
    name: string; classification: string; action_id?: number | null; test_data_id?: number | null;
    secret_reference?: string | null; source_action_id?: number | null;
    environment_key?: string | null; sample_value?: string | null;
  }) => api.put<RecorderDataBinding>(`${RECORDER_BASE}/recordings/${sessionId}/data-bindings`, payload),
  deleteDataBinding: (sessionId: number, bindingId: number) =>
    api.delete<void>(`${RECORDER_BASE}/recordings/${sessionId}/data-bindings/${bindingId}`),

  notes: (sessionId: number) => api.get<RecorderNote[]>(`${RECORDER_BASE}/recordings/${sessionId}/notes`),
  createNote: (sessionId: number, payload: {
    body: string; scope?: string; step_key?: string | null; action_id?: number | null;
    checkpoint_id?: number | null; segment_id?: number | null;
  }) => api.post<RecorderNote>(`${RECORDER_BASE}/recordings/${sessionId}/notes`, payload),
  deleteNote: (sessionId: number, noteId: number) =>
    api.delete<void>(`${RECORDER_BASE}/recordings/${sessionId}/notes/${noteId}`),

  captures: (sessionId: number, actionId?: number) =>
    api.get<RecorderCapture[]>(`${RECORDER_BASE}/recordings/${sessionId}/captures`, {
      params: actionId != null ? { action_id: actionId } : undefined,
    }),
  /** Screenshot URL for an <img src>, served through the same auth as every other call. */
  captureImageUrl: (sessionId: number, captureId: number) =>
    `/api/v1${RECORDER_BASE}/recordings/${sessionId}/captures/${captureId}/image`,
  latestView: (sessionId: number) =>
    api.get<RecorderLatestView>(`${RECORDER_BASE}/recordings/${sessionId}/latest-view`),

  summary: (sessionId: number) => api.get<RecordingSummary>(`${RECORDER_BASE}/recordings/${sessionId}/summary`),
  finalize: (sessionId: number) => api.post<RecordingSummary>(`${RECORDER_BASE}/recordings/${sessionId}/finalize`),
  irDraft: (sessionId: number) =>
    api.get<AutomationIrDraft | null>(`${RECORDER_BASE}/recordings/${sessionId}/ir-draft`),
  emitIrDraft: (sessionId: number) =>
    api.post<AutomationIrDraft>(`${RECORDER_BASE}/recordings/${sessionId}/ir-draft`),
  activity: (sessionId: number) =>
    api.get<DiscoverySessionEvent[]>(`${RECORDER_BASE}/recordings/${sessionId}/activity`),
};

// ─── UI-020/021/023 Automation Asset Workspace ────────────────────────────────
// One workspace, three tabs, over one Automation Suite member.

const AUTOMATION_ASSET_BASE = "/lab/automation-assets";

/** A value resolved from an authoritative source, rendered read-only with that
 *  source named. Contract Section 5 rule 4 — inherited context is never re-entered. */
export interface InheritedField {
  value: string | null;
  source: string | null;
  available: boolean;
  reason: string | null;
}

export interface AssetHeader {
  member_id: number;
  suite_id: number;
  suite_name: string;
  suite_version: number;
  suite_status: AutomationSuiteStatus;
  test_case_id: number;
  test_case_display_id: string | null;
  test_case_title: string | null;
  requirement_id: number | null;
  requirement_display_id: string | null;
  application: InheritedField;
  framework: InheritedField;
  environment: InheritedField;
  member_status: SuiteMemberStatus;
}

/** Section 10 — plain-English state and exactly one primary action. */
export interface AssetReadinessStrip {
  state: string;
  message: string;
  primary_action: string | null;
  primary_action_target: string | null;
}

export interface AssetTabState {
  enabled: boolean;
  reason: string | null;
}

export interface IrValidationError {
  field: string;
  message: string;
  type: string;
}

export interface IrValidationSummary {
  step_count: number;
  custom_step_count: number;
  custom_step_indexes: number[];
  locator_count: number;
  assertion_count: number;
  page_object_count: number;
  binding_count: number;
  ready_for_compile: boolean;
}

export interface IrValidationResult {
  valid: boolean;
  errors: IrValidationError[];
  summary: IrValidationSummary | null;
}

/** One entry from the emitter's readiness map. `kind` is one of ten values;
 *  the UI must render an unknown kind rather than dropping the row. */
export interface IrReadinessItem {
  kind: string;
  detail: string;
  action_id?: number | null;
  checkpoint_id?: number | null;
  sequence?: number | null;
}

export interface IrReadiness {
  unresolved?: IrReadinessItem[];
  unresolved_count?: number;
  step_count?: number;
  assertion_count?: number;
  custom_step_count?: number;
  ready_for_script_generation?: boolean;
}

export interface AssetIr {
  id: number | null;
  version: number;
  is_current: boolean;
  status: string;
  contract: Record<string, unknown>;
  contract_version: string;
  readiness: IrReadiness;
  source_action_ids: number[];
  generated_by: number | null;
  updated_at?: string | null;
  /** "ir_draft" is editable; "compiled_script" is a read-only reconstruction. */
  source: "ir_draft" | "compiled_script";
  editable: boolean;
}

export interface AssetPrecondition {
  code: string;
  label: string;
  met: boolean;
  detail: string;
}

/** The machine axis. Deliberately separate from `approval_state`, the human axis. */
export interface AssetAutonomy {
  autonomy_state: "AI_PENDING" | "AI_HELD" | "AI_APPROVED";
  approval_state: "PENDING_FINAL" | "FINAL_APPROVED" | "REJECTED";
  verdict_state: string;
  score: number | null;
  threshold: number;
  rubric_id: string;
  held_reason: string | null;
  would_approve: boolean;
  enabled: boolean;
  dimensions: Record<string, number>;
  preconditions: AssetPrecondition[];
}

export interface AssetScript {
  id: number;
  script_id: string;
  framework: string;
  version: number;
  status: string;
  entry_path: string | null;
  file_count: number;
  static_gate_result: Record<string, unknown> | null;
}

export interface AutomationAsset {
  header: AssetHeader;
  readiness_strip: AssetReadinessStrip;
  tabs: Record<string, AssetTabState>;
  ir: AssetIr | null;
  ir_validation: IrValidationResult | null;
  autonomy: AssetAutonomy;
  script: AssetScript | null;
  unavailable: Record<string, string>;
}

export interface DeclaredElement {
  page_object: string;
  name: string;
  locator_strategy: string | null;
  locator_value: string | null;
  role_hint: string | null;
  nth: number | null;
  business_meaning: string | null;
  in_model: boolean;
}

export interface AvailableElement {
  name: string;
  source: "application_model" | "locator_map";
  in_model: boolean;
  locator_value: string | null;
  locator_strategy: string | null;
  confidence: number | null;
  business_meaning: string | null;
}

export interface ElementCatalogue {
  declared: DeclaredElement[];
  available: AvailableElement[];
  element_required_actions: string[];
}

export interface IrVersionRow {
  id: number;
  version: number;
  is_current: boolean;
  status: string;
  /** `is_current` is scoped to one recording session's chain, not the member. */
  session_id: number;
  step_count: number;
  custom_step_count: number;
  unresolved_count: number;
  generated_by: number | null;
  created_at: string | null;
}

export interface ProvenanceAction {
  id: number;
  sequence: number | null;
  actor: string | null;
  /** DiscoveryAction's real field. There is no `action_type`/`description`. */
  action_family: string | null;
  target_semantic: string | null;
  target_element_ref: string | null;
  target_screen_ref: string | null;
  test_step_ref: string | null;
  created_at: string | null;
}

export const automationAssetApi = {
  get: (memberId: number) =>
    api.get<AutomationAsset>(`${AUTOMATION_ASSET_BASE}/members/${memberId}`),
  getIr: (memberId: number) =>
    api.get<{ ir: AssetIr | null; validation: IrValidationResult | null }>(
      `${AUTOMATION_ASSET_BASE}/members/${memberId}/ir`,
    ),
  /** Validate without saving. Returns 200 with valid:false while mid-edit —
   *  an invalid draft is a normal state, not an error. */
  validateIr: (memberId: number, contract: Record<string, unknown>) =>
    api.post<IrValidationResult>(`${AUTOMATION_ASSET_BASE}/members/${memberId}/ir/validate`, {
      contract,
    }),
  saveIr: (
    memberId: number,
    contract: Record<string, unknown>,
    resolvedReadinessKinds: string[] = [],
  ) =>
    api.put<{ ir: AssetIr; validation: IrValidationResult }>(
      `${AUTOMATION_ASSET_BASE}/members/${memberId}/ir`,
      { contract, resolved_readiness_kinds: resolvedReadinessKinds },
    ),
  irVersions: (memberId: number) =>
    api.get<{ versions: IrVersionRow[]; other_session_draft_count: number }>(
      `${AUTOMATION_ASSET_BASE}/members/${memberId}/ir/versions`,
    ),
  elements: (memberId: number) =>
    api.get<ElementCatalogue>(`${AUTOMATION_ASSET_BASE}/members/${memberId}/elements`),
  provenance: (memberId: number) =>
    api.get<{ actions: ProvenanceAction[]; unavailable: string | null }>(
      `${AUTOMATION_ASSET_BASE}/members/${memberId}/provenance`,
    ),
  evaluate: (memberId: number) =>
    api.post<AssetAutonomy & { decision_id: number | null }>(
      `${AUTOMATION_ASSET_BASE}/members/${memberId}/evaluate`,
    ),
};

// ─── UI-021 Script Editor ─────────────────────────────────────────────────────

export interface CompiledScript {
  id: number;
  script_id: string;
  framework: string;
  version: number;
  parent_script_id: number | null;
  status: string;
  entry_path: string | null;
  /** The full multi-file bundle: relative path -> source. Read-only. */
  compiled_files: Record<string, string>;
  execution_command: string | null;
  setup_required: string[];
  static_gate_result: StaticGateResult | null;
  compiler_version: string | null;
  created_by: number | null;
  updated_at: string | null;
}

// StaticGateResult / StaticGateViolation are already declared above and reused
// here — the gate has one shape across the whole client.

export interface DryRunTestResult {
  id: number | null;
  test_name: string;
  status: string;
  duration_ms: number | null;
  error_message: string | null;
  screenshot_url?: string | null;
  video_url?: string | null;
  trace_path?: string | null;
  created_at?: string | null;
}

export interface DryRunOutcome {
  execution_run_id: number;
  /** "completed" on a successful run — NOT "passed". The verdict is per-test. */
  run_status: string;
  all_passed: boolean;
  duration_seconds: number | null;
  error_message: string | null;
  log_path: string | null;
  runner: string | null;
  exit_code: number | null;
  results: DryRunTestResult[];
  static_gate_result: StaticGateResult;
}

export interface RunnerFrameworkStatus {
  framework: string;
  available: boolean;
  detail: string;
}

export const automationScriptApi = {
  get: (memberId: number) =>
    api.get<{
      script: CompiledScript | null;
      unavailable: string | null;
      dry_runs: DryRunTestResult[];
    }>(`${AUTOMATION_ASSET_BASE}/members/${memberId}/script`),
  compile: (memberId: number) =>
    api.post<{
      id: number;
      script_id: string;
      version: number;
      framework: string;
      entry_path: string | null;
      file_count: number;
      status: string;
      static_gate_result: StaticGateResult | null;
    }>(`${AUTOMATION_ASSET_BASE}/members/${memberId}/compile`),
  dryRun: (memberId: number) =>
    api.post<DryRunOutcome>(`${AUTOMATION_ASSET_BASE}/members/${memberId}/dry-run`),
  runnerStatus: () =>
    api.get<{ frameworks: RunnerFrameworkStatus[] }>(
      `${AUTOMATION_ASSET_BASE}/runner-status`,
    ),
};

// ─── UI-023 Validation and Review ─────────────────────────────────────────────

export interface ValidationCard {
  label: string;
  status: "pass" | "fail" | "partial" | "below" | "unknown";
  detail: string;
  available: boolean;
  reason: string | null;
}

export interface ValidationFinding {
  code: string;
  message: string;
  severity: "block" | "warn";
  /** Blocking violations are never waivable from this screen. */
  waivable: boolean;
  accepted: boolean;
}

export interface GatingDecision extends AssetAutonomy {
  state: string;
}

export interface ValidationPayload {
  cards: {
    static_quality: ValidationCard;
    real_execution: ValidationCard;
    readiness: ValidationCard;
    confidence_score: ValidationCard;
  };
  gating: GatingDecision;
  findings: ValidationFinding[];
  /** Three states. "skipped" is rendered as skipped, never as a pass. */
  syntax_check: { status: "passed" | "failed" | "skipped"; detail: string | null };
  readiness_items: IrReadinessItem[];
  dry_runs: DryRunTestResult[];
  accepted_exceptions: string[];
  script_id: string | null;
  unavailable: Record<string, string>;
}

export interface FinalApprovalOutcome {
  decision_id: number;
  decision: string;
  approval_state: string;
  autonomy_state: string;
  decided_by: number | null;
  threshold: number;
  score: number | null;
}

export interface AssetDecisionRow {
  id: number;
  decision: string;
  decided_by: number | null;
  rubric_id: string;
  threshold: number;
  score: number | null;
  dimensions: Record<string, number>;
  preconditions: AssetPrecondition[];
  model_versions: Record<string, string>;
  reason: string | null;
  created_at: string | null;
}

export const automationValidationApi = {
  get: (memberId: number) =>
    api.get<ValidationPayload>(`${AUTOMATION_ASSET_BASE}/members/${memberId}/validation`),
  acceptException: (memberId: number, code: string, reason: string) =>
    api.post<StaticGateResult>(
      `${AUTOMATION_ASSET_BASE}/members/${memberId}/validation/exceptions`,
      { code, reason },
    ),
  finalApproval: (memberId: number, approve: boolean, reason?: string) =>
    api.post<FinalApprovalOutcome>(
      `${AUTOMATION_ASSET_BASE}/members/${memberId}/final-approval`,
      { approve, reason: reason ?? null },
    ),
  decisions: (memberId: number) =>
    api.get<AssetDecisionRow[]>(`${AUTOMATION_ASSET_BASE}/members/${memberId}/decisions`),
  pendingFinalApproval: (suiteId: number) =>
    api.get<{
      pending_final_approval: Array<{
        member_id: number;
        test_case_id: number;
        autonomy_state: string;
        approval_state: string;
        last_evaluated_at: string | null;
      }>;
      blocking_publish: Array<{
        member_id: number;
        test_case_id: number;
        approval_state: string;
      }>;
    }>(`${AUTOMATION_ASSET_BASE}/suites/${suiteId}/pending-final-approval`),
};

export interface AutomationAssetRow {
  member_id: number;
  suite_id: number;
  suite_name: string;
  suite_status: AutomationSuiteStatus;
  test_case_id: number;
  test_case_display_id: string | null;
  test_case_title: string | null;
  member_status: SuiteMemberStatus;
  inclusion_status: string;
  autonomy_state: "AI_PENDING" | "AI_HELD" | "AI_APPROVED";
  approval_state: "PENDING_FINAL" | "FINAL_APPROVED" | "REJECTED";
  has_script: boolean;
  framework: string | null;
  last_evaluated_at: string | null;
}

export interface AutomationAssetListing {
  assets: AutomationAssetRow[];
  counts: {
    total: number;
    ai_approved: number;
    ai_held: number;
    pending_final_approval: number;
    final_approved: number;
  };
}

export const automationAssetListApi = {
  list: (projectId: number) =>
    api.get<AutomationAssetListing>(`${AUTOMATION_ASSET_BASE}/projects/${projectId}/assets`),
};

// ─── UI-046 Suite Execution Command Center (P1-S7) ────────────────────────────
// The live transport is polling `events?after={sequence}`, not a socket: this
// platform has no SSE/WebSocket infrastructure, and a dense sequence cursor is
// what makes reconnection lossless (contract Sections 2.1.7 and 14.8).

const SUITE_EXECUTION_BASE = "/lab/suite-executions";

export interface ExecutionReadinessCheck {
  axis: string;
  name: string;
  passed: boolean;
  detail: string;
  blocking: boolean;
}

export interface ExecutionReadiness {
  ready: boolean;
  axes: Record<string, boolean>;
  checks: ExecutionReadinessCheck[];
  blockers: ExecutionReadinessCheck[];
}

/** Section 3.1 — the server owns which action is primary, so the UI cannot drift
 *  from the run state machine. */
export type ExecutionPrimaryAction =
  | "VIEW_READINESS"
  | "REVIEW_BLOCKER"
  | "VIEW_QUEUE_POSITION"
  | "PAUSE_AFTER_CURRENT"
  | "VIEW_PAUSE_PROGRESS"
  | "RESUME"
  | "VIEW_STOP_PROGRESS"
  | "OPEN_REPORT";

export type ExecutionLifecycleState =
  | "READINESS_PENDING"
  | "BLOCKED_BEFORE_START"
  | "QUEUED"
  | "RUNNING"
  | "PAUSE_REQUESTED"
  | "PAUSED"
  | "STOP_REQUESTED"
  | "STOPPED"
  | "CANCELLED"
  | "COMPLETED";

/** The eight deterministic outcomes. */
export type ExecutionOutcome =
  | "PASS"
  | "FAIL"
  | "INCONCLUSIVE"
  | "BLOCKED"
  | "ENVIRONMENT_FAILURE"
  | "DATA_FAILURE"
  | "AUTOMATION_FAILURE"
  | "POLICY_BLOCKED";

/** Plus the two item states that are not a verdict on the application. */
export type ExecutionItemResult = ExecutionOutcome | "PENDING" | "SKIPPED";

export interface SuiteRunIdentity {
  id: number;
  execution_id: string;
  project_id: number;
  suite_id: number | null;
  suite_name: string | null;
  suite_snapshot_id: number | null;
  suite_version: number | null;
  snapshot_checksum: string | null;
  environment: string | null;
  execution_purpose: string | null;
  frameworks: string[];
  trigger_source: string | null;
  triggered_by: number | null;
  triggered_by_name: string | null;
  lifecycle_state: ExecutionLifecycleState | null;
  outcome: ExecutionOutcome | null;
  run_version: number;
  pending_command: string | null;
  correlation_id: string | null;
  parallel_limit: number;
  started_at: string | null;
  completed_at: string | null;
  readiness: ExecutionReadiness | null;
  primary_action: ExecutionPrimaryAction;
  is_terminal: boolean;
  latest_sequence: number;
  can_control: boolean;
  can_cancel: boolean;
}

export interface SuiteRunCounts {
  passed: number;
  failed: number;
  inconclusive: number;
  blocked: number;
  environment_failure: number;
  data_failure: number;
  automation_failure: number;
  policy_blocked: number;
  skipped: number;
  running: number;
  queued: number;
}

export interface SuiteRunSummary {
  total: number;
  completed: number;
  completion_percent: number;
  counts: SuiteRunCounts;
  /** Section 4.3 — false means render "Status data delayed" rather than a total
   *  the backend cannot justify. */
  reconciled: boolean;
  reconciliation_detail: string | null;
  parallel_in_use: number;
  parallel_allowed: number;
  queue_depth: number;
  evidence_captured: number;
  evidence_required: number;
  environment_ready: boolean;
  operational_message: string;
}

export interface SuiteRunItem {
  id: number;
  order_index: number;
  test_case_id: number | null;
  test_case_key: string | null;
  title: string | null;
  journey: string | null;
  application_id: number | null;
  priority: string | null;
  framework: string | null;
  runner_name: string | null;
  lifecycle_state: "QUEUED" | "STARTING" | "RUNNING" | "PAUSED" | "COMPLETED";
  result: ExecutionItemResult;
  attempt: number;
  attempts_allowed: number;
  /** Steps declared by the Automation IR. There is deliberately no
   *  `steps_completed`: no runner reports per-step progress, so the server
   *  stopped publishing a completion count it could not substantiate. It
   *  returns once adapter step telemetry exists. */
  steps_total: number;
  /** The mandatory pair the evidence quorum is judged on. */
  evidence_captured: number;
  evidence_required: number;
  /** Every artifact retained, mandatory or not. A test with no declared evidence
   *  requirement can still have produced a trace and a screenshot. */
  evidence_total_captured: number;
  assertions_passed: number;
  assertions_total: number;
  duration_ms: number | null;
  attention_reason: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface SuiteRunItemPage {
  items: SuiteRunItem[];
  next_cursor: number | null;
  total_matching: number;
}

export interface SuiteTreeChild {
  framework: string;
  total: number;
  complete: number;
}

export interface SuiteTreeNode {
  journey: string;
  total: number;
  complete: number;
  worst_result: ExecutionItemResult | null;
  children: SuiteTreeChild[];
}

export interface SuiteRunStep {
  id: number;
  step_number: number;
  action_text: string | null;
  expected_text: string | null;
  actual_text: string | null;
  status: "pending" | "running" | "passed" | "failed" | "skipped";
  application_context: string | null;
  elapsed_ms: number | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface SuiteRunAssertion {
  id: number;
  source: string;
  description: string;
  expected_value: string | null;
  actual_value: string | null;
  mandatory: boolean;
  /** null means never evaluated — shown as pending, not as a failure. */
  passed: boolean | null;
  /** How the verdict was reached. "runner_verdict" is inferred from the
   *  test-level result — Playwright fails the whole test when any web-first
   *  assertion fails, so a green test does mean every assertion held, but that
   *  is not a per-assertion evaluation. "reported" means the adapter evaluated
   *  this assertion individually. null whenever `passed` is null. */
  evaluation_source: "runner_verdict" | "reported" | "manual" | null;
  evaluated_at: string | null;
}

/** Metadata only. Content is served by a separate authenticated, masked download
 *  because a captured network payload can contain request headers. */
export interface SuiteRunEvidence {
  id: number;
  evidence_type: string;
  status: "pending" | "captured" | "unavailable";
  mandatory: boolean;
  summary: string | null;
  payload_entry_count: number | null;
  size_bytes: number | null;
  has_artifact: boolean;
  sanitized: boolean;
  /** Why `sanitized` reads as it does. "masked" means the pass rewrote the
   *  content; "not_maskable" means no text pass applies (screenshot, video,
   *  trace) and serving it is a deployment policy decision. */
  redaction_state: "pending" | "masked" | "not_maskable";
  /** SHA-256 of the bytes as captured, so a download can be checked against
   *  what the run actually produced. */
  checksum_sha256: string | null;
  content_type: string | null;
  /** False when the row records no artifact and no payload — the viewer must
   *  not offer a link to nothing. */
  downloadable: boolean;
  unavailable_reason: string | null;
  captured_at: string | null;
}

export interface SuiteRunItemDetail {
  item: SuiteRunItem;
  script_id: number | null;
  test_case_version: number | null;
  environment: string | null;
  session_id: string | null;
  retry_reason: string | null;
  error_message: string | null;
  snapshot_member: Record<string, unknown>;
  current_step: SuiteRunStep | null;
  steps: SuiteRunStep[];
  assertions: SuiteRunAssertion[];
  evidence: SuiteRunEvidence[];
  quorum_met: boolean;
  quorum_missing: string[];
  latest_screenshot_evidence_id: number | null;
  latest_screenshot_captured_at: string | null;
}

export interface SuiteRunEvent {
  sequence: number;
  event_type: string;
  message: string;
  item_id: number | null;
  payload: Record<string, unknown> | null;
  occurred_at: string;
}

export interface SuiteRunEventPage {
  events: SuiteRunEvent[];
  latest_sequence: number;
  newest_event_age_seconds: number | null;
  has_more: boolean;
}

export type SuiteRunControlAction =
  | "PAUSE_AFTER_CURRENT"
  | "RESUME"
  | "STOP_GRACEFULLY"
  | "CANCEL_NOW"
  | "EMERGENCY_STOP";

export interface SuiteRunControlResponse {
  commandId: string;
  accepted: boolean;
  currentState: string;
  runVersion: number;
  message: string;
}

export interface SuiteRunItemQuery {
  cursor?: number;
  limit?: number;
  result?: string[];
  lifecycle_state?: string[];
  search?: string;
  journey?: string;
  framework?: string;
  priority?: string;
}

/** Thin projection for the suite's Executions tab list. */
export interface SuiteRunListRow {
  id: number;
  execution_id: string;
  lifecycle_state: ExecutionLifecycleState | null;
  outcome: ExecutionOutcome | null;
  environment: string | null;
  execution_purpose: string | null;
  total_tests: number;
  passed: number;
  failed: number;
  started_at: string | null;
  completed_at: string | null;
  is_terminal: boolean;
}

export const suiteExecutionApi = {
  start: (suiteId: number, body: { environment?: string; execution_purpose?: string }) =>
    api.post<SuiteRunIdentity>(`${SUITE_EXECUTION_BASE}/suites/${suiteId}/runs`, body),
  listForSuite: (suiteId: number, limit = 20) =>
    api.get<SuiteRunListRow[]>(`${SUITE_EXECUTION_BASE}/suites/${suiteId}/runs`, {
      params: { limit },
    }),
  get: (runId: number) => api.get<SuiteRunIdentity>(`${SUITE_EXECUTION_BASE}/runs/${runId}`),
  summary: (runId: number) =>
    api.get<SuiteRunSummary>(`${SUITE_EXECUTION_BASE}/runs/${runId}/summary`),
  tree: (runId: number) =>
    api.get<SuiteTreeNode[]>(`${SUITE_EXECUTION_BASE}/runs/${runId}/tree`),
  items: (runId: number, query: SuiteRunItemQuery = {}) =>
    api.get<SuiteRunItemPage>(`${SUITE_EXECUTION_BASE}/runs/${runId}/items`, {
      params: query,
      // `result` and `lifecycle_state` are repeatable query parameters. Axios
      // defaults to `result[]=A&result[]=B`, which FastAPI's `list[str] = Query()`
      // does not parse — it silently sees no filter and returns everything. This
      // emits `result=A&result=B` instead.
      paramsSerializer: { indexes: null },
    }),
  item: (runId: number, itemId: number) =>
    api.get<SuiteRunItemDetail>(`${SUITE_EXECUTION_BASE}/runs/${runId}/items/${itemId}`),
  /** Poll with the cursor last received, so a gap replays exactly once. */
  events: (runId: number, after: number, limit = 200) =>
    api.get<SuiteRunEventPage>(`${SUITE_EXECUTION_BASE}/runs/${runId}/events`, {
      params: { after, limit },
    }),
  control: (
    runId: number,
    body: {
      action: SuiteRunControlAction;
      reason?: string;
      expectedRunVersion?: number;
    },
  ) =>
    api.post<SuiteRunControlResponse>(
      `${SUITE_EXECUTION_BASE}/runs/${runId}/controls`,
      body,
    ),
  /** Fetch one evidence artifact. Text and JSON come back masked; binary
   *  artifacts cannot be masked and the server refuses them where policy says
   *  so, which surfaces here as a normal request error with the reason. */
  evidence: (runId: number, evidenceId: number) =>
    api.get<Blob>(`${SUITE_EXECUTION_BASE}/runs/${runId}/evidence/${evidenceId}`, {
      responseType: "blob",
    }),
};

// â”€â”€ Test Automation Studio â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// A separate module: its own /lab/test-automation-studio namespace, its own
// tas_* tables, and no overlap with the Requirements / Test Cases / Automation
// clients above. Every route 404s when the module is disabled or when the
// caller's global role is outside admin / Test_Automation_Users.

const TAS_BASE = "/lab/test-automation-studio";

export type TasDocRole = "brd" | "srd" | "test_cases" | "other";
export type TasApprovalStatus = "draft" | "pending_approval" | "approved" | "rejected";
export type TasCoverageState = "covered" | "partially_covered" | "uncovered";
export type TasClassification = "automation" | "manual" | "undecided";
export type TasTestDataStatus =
  | "not_required"
  | "agent_provided"
  | "needs_user_action"
  | "user_provided";
export type TasFramework = "playwright" | "katalon" | "appium";

export const TAS_FRAMEWORKS: TasFramework[] = ["playwright", "katalon", "appium"];

export const TAS_FRAMEWORK_LABELS: Record<TasFramework, string> = {
  playwright: "Playwright",
  katalon: "Katalon",
  appium: "Appium",
};

export interface TasIntakeDocument {
  id: number;
  batch_id: number;
  document_id: number;
  doc_role: TasDocRole;
  extraction_status: string;
  extraction_error?: string | null;
  /** The uploaded document's own status. Extraction is a background job, so a
   *  just-uploaded document is attached but not yet assessable. */
  document_status: string;
  text_available: boolean;
  ready_for_assessment: boolean;
  extracted_requirement_count: number;
  extracted_test_case_count: number;
  original_filename?: string | null;
  file_type?: string | null;
  file_size_bytes?: number | null;
  created_at: string;
}

export type TasAuthMode = "none" | "form";

/** The non-secret shape of the application's login form. Field *labels*, not
 *  selectors: discovery matches these against the live accessibility tree,
 *  which is what a person reads off the screen. */
export interface TasBatchAuthConfig {
  login_url?: string | null;
  username_label?: string | null;
  password_label?: string | null;
  submit_label?: string | null;
}

export interface TasIntakeBatch {
  id: number;
  project_id: number;
  name: string;
  description?: string | null;
  application_id?: number | null;
  application_url?: string | null;
  application_environment: string;
  status: string;
  status_error?: string | null;
  auth_mode: TasAuthMode;
  auth_config: TasBatchAuthConfig;
  /** Whether credentials are stored. The password itself is never sent to the
   *  client in any direction but up. */
  has_credentials: boolean;
  created_by: number;
  created_at: string;
  updated_at: string;
  documents: TasIntakeDocument[];
}

export type TasDiscoveryStatus = "running" | "completed" | "failed";
export type TasAuthStatus = "not_required" | "succeeded" | "failed" | "skipped";

/** One live crawl of the batch's application — the evidence every locator
 *  downstream is grounded against. */
export interface TasDiscoveryRun {
  id: number;
  project_id: number;
  batch_id: number;
  version: number;
  is_current: boolean;
  status: TasDiscoveryStatus;
  application_url?: string | null;
  application_environment?: string | null;
  auth_mode: TasAuthMode;
  /** Tracked separately from `status`: a crawl that never got past the login
   *  page still completed, it just catalogued the wrong page. */
  auth_status: TasAuthStatus;
  auth_detail?: string | null;
  pages_discovered: number;
  elements_discovered: number;
  explored_pages: Array<{ url?: string; title?: string | null; element_count?: number }>;
  blockers: Array<{ name?: string; detail?: string }>;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TasDiscoveredElement {
  id: number;
  page_url: string;
  page_title?: string | null;
  element_name: string;
  role?: string | null;
  accessible_name?: string | null;
  business_meaning?: string | null;
  recommended_locator: string;
  recommended_strategy: string;
  confidence_score: number;
  href?: string | null;
}

export interface TasCoverageAssessment {
  id: number;
  project_id: number;
  batch_id: number;
  version: number;
  is_current: boolean;
  status: string;
  error?: string | null;
  total_requirements: number;
  covered_requirements: number;
  partially_covered_requirements: number;
  uncovered_requirements: number;
  existing_test_case_count: number;
  derived_requirement_count: number;
  coverage_percent: number;
  coverage_rows: Array<Record<string, unknown>>;
  extracted_test_cases: Array<Record<string, unknown>>;
  gap_summary: Record<string, unknown>;
  agent_run_id?: number | null;
  created_at: string;
}

export interface TasDerivedRequirement {
  id: number;
  project_id: number;
  batch_id: number;
  assessment_id?: number | null;
  requirement_key: string;
  title: string;
  summary?: string | null;
  acceptance_criteria: string[];
  business_rules: string[];
  ui_pages: string[];
  apis: string[];
  test_data_needs: string[];
  origin: "extracted" | "derived";
  coverage_state: TasCoverageState;
  gap_reason?: string | null;
  source_refs: string[];
  covering_test_case_refs: string[];
  automation_relevance?: string | null;
  priority: string;
  status: TasApprovalStatus;
  decision_reason?: string | null;
  approved_by?: number | null;
  approved_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TasRefinedStep {
  step_number: number;
  action: string;
  target?: string | null;
  test_data_ref?: string | null;
  expected_result?: string | null;
}

export interface TasTestDataRequirement {
  key: string;
  description?: string | null;
  example_value?: string | null;
  sensitive?: boolean;
  resolution: "agent_generated" | "existing_record" | "user_required";
  test_data_id?: number | null;
}

/** A test case read off an uploaded test case document, ID and name verbatim. */
export interface TasSourceTestCase {
  id: number;
  project_id: number;
  batch_id: number;
  assessment_id?: number | null;
  tc_display_id: string;
  title: string;
  summary?: string | null;
  steps: string[];
  source_document_id?: number | null;
  source_ref?: string | null;
  matched_platform_test_case_id?: number | null;
  covers_requirement_ids: number[];
  refined_test_case_id?: number | null;
  refined_status?: string | null;
  created_at: string;
  updated_at: string;
}

export type TasGroundingStatus =
  | "not_checked"
  | "grounded"
  | "partially_grounded"
  | "ungrounded";

export interface TasGroundingMatch {
  step_number?: number;
  target?: string | null;
  element_name?: string;
  locator?: string;
  page?: string;
  confidence?: number;
}

export interface TasGroundingGap {
  step_number?: number;
  action?: string | null;
  target?: string | null;
  /** Always actionable — "no element matches X", or "matches more than one".
   *  This is what the grounding drawer shows per unresolved step. */
  reason?: string;
}

export interface TasGroundingSummary {
  total_steps?: number;
  groundable_steps?: number;
  matched_steps?: number;
  skipped_steps?: number;
  matched?: TasGroundingMatch[];
  unresolved?: TasGroundingGap[];
  note?: string | null;
  discovery_run_id?: number | null;
}

export interface TasRefinedTestCase {
  id: number;
  project_id: number;
  batch_id?: number | null;
  derived_requirement_id?: number | null;
  source_test_case_id?: number | null;
  source_uploaded_test_case_id?: number | null;
  origin: "existing" | "imported" | "derived";
  tc_display_id: string;
  title: string;
  objective?: string | null;
  preconditions: string[];
  steps: TasRefinedStep[];
  expected_result?: string | null;
  bdd_scenario?: string | null;
  application_id?: number | null;
  application_url?: string | null;
  priority: string;
  test_type?: string | null;
  classification: TasClassification;
  classification_source?: string | null;
  classification_reason?: string | null;
  manual_only_reasons: Array<Record<string, unknown>>;
  test_data_required: boolean;
  test_data_status: TasTestDataStatus;
  test_data_notes?: string | null;
  test_data_requirements: TasTestDataRequirement[];
  test_data_ids: number[];
  /** Whether each step resolved to an element discovery actually found.
   *  `not_checked` (grounding never ran) is a different statement from
   *  `ungrounded` (it ran and nothing matched). */
  grounding_status: TasGroundingStatus;
  grounding_summary?: TasGroundingSummary | null;
  grounded_at?: string | null;
  discovery_run_id?: number | null;
  status: TasApprovalStatus;
  decision_reason?: string | null;
  approved_by?: number | null;
  approved_at?: string | null;
  version: number;
  is_current: boolean;
  edited_by_user: boolean;
  agent_run_id?: number | null;
  created_at: string;
  updated_at: string;
  /** Server-derived: the uploaded or platform test case this was refined from
   *  has since been deleted. The refined test case is still valid work - it
   *  keeps the ID and title it inherited - but its provenance is gone and
   *  re-running generation would build a second one alongside it. */
  source_missing: boolean;
}

export type TasDryRunStatus =
  | "not_run"
  | "queued"
  | "running"
  | "passed"
  | "failed"
  | "blocked";

/** One test's outcome inside a dry run, straight from the Playwright JSON
 *  reporter. `error_message` is what makes a failure actionable — it names the
 *  locator that did not resolve. */
export interface TasDryRunResult {
  name?: string;
  status?: string;
  duration_ms?: number | null;
  error_message?: string | null;
  stack_trace?: string | null;
  screenshot_path?: string | null;
  video_path?: string | null;
  trace_path?: string | null;
}

export interface TasDryRunSummary {
  run_status?: string | null;
  passed?: boolean;
  results?: TasDryRunResult[];
  log_path?: string | null;
  error_message?: string | null;
  /** Set only for `blocked` — the framework has no runner here, which is not
   *  a failure of the script. */
  reason?: string | null;
}

export interface TasScriptGrounding {
  catalog_size?: number;
  grounded_elements?: number;
  ungrounded_elements?: string[];
  discovery_run_id?: number | null;
  /** False for free-form frameworks: the catalog was offered to the model,
   *  not substituted into the output. */
  enforced?: boolean;
}

export interface TasStaticGateResult {
  passed?: boolean;
  violations?: Array<{ code?: string; message?: string; severity?: string }>;
  warnings?: Array<{ code?: string; message?: string; severity?: string }>;
  syntax_check?: string;
  type_check?: string;
}

export interface TasScriptAsset {
  id: number;
  project_id: number;
  refined_test_case_id: number;
  framework: TasFramework;
  language: string;
  script_key: string;
  code: string;
  files: Record<string, string>;
  execution_command?: string | null;
  setup_notes: string[];
  /** `compiled` went through the Script Compiler with its locators
   *  substituted from the discovered catalog; `freeform` is LLM-authored code
   *  that was merely shown the catalog. Very different guarantees. */
  generation_mode: "compiled" | "freeform";
  entry_path?: string | null;
  static_gate_result?: TasStaticGateResult | null;
  grounding?: TasScriptGrounding | null;
  dry_run_status: TasDryRunStatus;
  dry_run_summary?: TasDryRunSummary | null;
  dry_run_at?: string | null;
  contract_present: boolean;
  status: string;
  version: number;
  is_current: boolean;
  edited_by_user: boolean;
  generation_error?: string | null;
  agent_run_id?: number | null;
  created_at: string;
  updated_at: string;
  test_case_display_id?: string | null;
  test_case_title?: string | null;
}

export interface TasStudioSummary {
  batches: number;
  requirements_pending: number;
  requirements_approved: number;
  test_cases_total: number;
  test_cases_pending: number;
  test_cases_approved: number;
  test_cases_automation: number;
  test_cases_manual: number;
  test_cases_needing_test_data: number;
  scripts_total: number;
  scripts_by_framework: Record<string, number>;
}

export interface TasSkipped {
  requirement_key?: string | null;
  test_case_id?: number | string | null;
  tc_display_id?: string | null;
  reason?: string | null;
}

export interface TasBlocked {
  test_case_id: number;
  tc_display_id: string;
  code: string;
  message: string;
}

/** What a delete actually removed.
 *
 *  Deleting a studio artefact is never only the row that was clicked:
 *  superseded versions go with it and scripts cascade off a refined test case.
 *  The screens report these counts so the user is told what left with it. */
export interface TasDeletionSummary {
  deleted: number[];
  /** Requested ids the project no longer has - a stale grid, usually. */
  not_found: number[];
  versions_deleted: number;
  scripts_deleted: number;
  /** Artefacts kept, but no longer linked to what produced them. */
  test_cases_unlinked: number;
  approved_deleted: number;
}

/** Acknowledgement for a queued studio job.
 *
 *  The three heavy studio operations return this instead of their results:
 *  each runs one or more LLM calls over minutes, which no HTTP hop will hold
 *  open. Poll the agent run, then re-read the screen's own list endpoint. */
export interface TasJob {
  agent_run_id: number;
  task_id?: string | null;
  status: string;
  message: string;
}

/** Progress of a queued studio job. */
export interface TasJobStatus {
  agent_run_id: number;
  agent_name: string;
  status: string;
  progress_percent: number;
  progress_message?: string | null;
  error_message?: string | null;
  output_data?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  /** Server-decided: true once the run has stopped, whatever the outcome.
   *  Polling stops on this rather than on a status list held here, so a status
   *  the client has never heard of ends the poll instead of spinning. */
  finished: boolean;
}

export interface TasJobProgress {
  status: string;
  percent: number;
  message: string;
}

/** Poll a queued studio job until it stops, reporting progress as it goes.
 *
 *  Resolves with the finished job rather than throwing when it failed: a job
 *  that died after generating three of ten scripts still changed the project,
 *  so the caller must refresh and then report, not just report. */
export async function waitForTasJob(
  agentRunId: number,
  onProgress?: (progress: TasJobProgress) => void,
  options?: { intervalMs?: number; timeoutMs?: number },
): Promise<TasJobStatus> {
  const intervalMs = options?.intervalMs ?? 2000;
  // Generous: a full wave is one LLM call per item. The server-side per-run
  // limit bounds this well below the ceiling.
  const timeoutMs = options?.timeoutMs ?? 30 * 60 * 1000;
  const deadline = Date.now() + timeoutMs;
  // A dropped poll is a blip; repeated failures mean the job is unreachable
  // and pretending otherwise spins the UI forever.
  const maxConsecutiveErrors = 5;
  let consecutiveErrors = 0;
  let last: TasJobStatus | null = null;

  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
    try {
      const job = (await testAutomationStudioApi.jobStatus(agentRunId)).data;
      consecutiveErrors = 0;
      last = job;
      onProgress?.({
        status: job.status,
        percent: job.progress_percent ?? 0,
        message: job.progress_message ?? "",
      });
      if (job.finished) return job;
    } catch {
      consecutiveErrors += 1;
      if (consecutiveErrors >= maxConsecutiveErrors) {
        throw new Error(
          `Lost contact with job ${agentRunId}. It may still be running - refresh in a moment.`,
        );
      }
    }
  }

  throw new Error(
    `Job ${agentRunId} did not finish within ${Math.round(timeoutMs / 60000)} minutes. ` +
      `Last status: ${last?.progress_message ?? last?.status ?? "unknown"}.`,
  );
}

export interface TasNavigation {
  global_role: string;
  is_platform_admin: boolean;
  nav_groups: string[];
  all_nav_groups: string[];
  test_automation_studio_enabled: boolean;
  can_access_test_automation_studio: boolean;
}

/** Server-decided sidebar visibility. The sidebar renders from this rather
 *  than inferring from a locally cached role, so a stale login profile cannot
 *  reveal a module the server would refuse anyway. */
export const navigationApi = {
  get: () => api.get<TasNavigation>("/users/me/navigation"),
};

export const testAutomationStudioApi = {
  summary: (projectId: number) =>
    api.get<TasStudioSummary>(`${TAS_BASE}/projects/${projectId}/summary`),
  frameworks: () => api.get<{ frameworks: TasFramework[] }>(`${TAS_BASE}/frameworks`),
  /** Progress of a queued job. Not the platform's /agent-runs/{id}: that is
   *  gated on VIEW_AUDIT_LOGS, which the studio role does not hold. */
  jobStatus: (agentRunId: number) =>
    api.get<TasJobStatus>(`${TAS_BASE}/jobs/${agentRunId}`),

  // Screen 1 â€” Requirement Coverage Assessment
  listBatches: (projectId: number) =>
    api.get<TasIntakeBatch[]>(`${TAS_BASE}/projects/${projectId}/batches`),
  createBatch: (
    projectId: number,
    body: {
      name: string;
      description?: string;
      application_id?: number | null;
      application_url?: string | null;
      application_environment?: string;
      auth_mode?: TasAuthMode;
      auth_config?: TasBatchAuthConfig;
      auth_username?: string | null;
      auth_password?: string | null;
    },
  ) => api.post<TasIntakeBatch>(`${TAS_BASE}/projects/${projectId}/batches`, body),
  getBatch: (batchId: number) => api.get<TasIntakeBatch>(`${TAS_BASE}/batches/${batchId}`),
  updateBatch: (
    batchId: number,
    body: {
      name?: string;
      description?: string;
      application_id?: number | null;
      application_url?: string | null;
      application_environment?: string;
      auth_mode?: TasAuthMode;
      auth_config?: TasBatchAuthConfig;
      /** Omit to keep the stored credentials. Send both to replace them.
       *  Setting auth_mode to "none" clears them outright. */
      auth_username?: string | null;
      auth_password?: string | null;
    },
  ) => api.patch<TasIntakeBatch>(`${TAS_BASE}/batches/${batchId}`, body),

  /** Open the batch's application in a real browser and catalogue what is on
   *  the page. Never automatic: it hits a live environment and may sign in. */
  discoverApplication: (batchId: number) =>
    api.post<TasJob>(`${TAS_BASE}/batches/${batchId}/discover`),
  getDiscovery: (batchId: number) =>
    api.get<TasDiscoveryRun | null>(`${TAS_BASE}/batches/${batchId}/discovery`),
  listDiscoveredElements: (batchId: number, params?: { page_url?: string }) => {
    const query = new URLSearchParams();
    if (params?.page_url) query.set("page_url", params.page_url);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api.get<TasDiscoveredElement[]>(
      `${TAS_BASE}/batches/${batchId}/discovery/elements${suffix}`,
    );
  },
  /** Discard every discovery run for a batch. Grounded test cases keep their
   *  summaries but lose the link to the evidence behind them. */
  deleteDiscovery: (batchId: number) =>
    api.delete<TasDeletionSummary>(`${TAS_BASE}/batches/${batchId}/discovery`),
  deleteBatch: (batchId: number) => api.delete(`${TAS_BASE}/batches/${batchId}`),
  /** Upload one document straight into a batch.
   *
   *  Deliberately not documentsApi.upload: that route is gated on
   *  MANAGE_PROJECT, which Test_Automation_Users does not hold. This one is
   *  gated on tas.intake and runs the same storage and extraction pipeline. */
  uploadDocument: (batchId: number, file: File, docRole: TasDocRole) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<TasIntakeBatch>(
      `${TAS_BASE}/batches/${batchId}/upload?doc_role=${docRole}`,
      form,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
  },
  /** Attach documents already uploaded elsewhere in the platform. */
  attachDocuments: (
    batchId: number,
    documents: Array<{ document_id: number; doc_role: TasDocRole }>,
  ) => api.post<TasIntakeBatch>(`${TAS_BASE}/batches/${batchId}/documents`, { documents }),
  setDocumentRole: (batchId: number, linkId: number, docRole: TasDocRole) =>
    api.patch<TasIntakeBatch>(
      `${TAS_BASE}/batches/${batchId}/documents/${linkId}?doc_role=${docRole}`,
    ),
  detachDocument: (batchId: number, linkId: number) =>
    api.delete<TasIntakeBatch>(`${TAS_BASE}/batches/${batchId}/documents/${linkId}`),
  assessCoverage: (
    batchId: number,
    body: {
      application_id?: number | null;
      application_url?: string | null;
      application_environment?: string | null;
      derive_gap_requirements?: boolean;
    },
  ) => api.post<TasJob>(`${TAS_BASE}/batches/${batchId}/assess`, body),
  /**
   * Reads the uploaded test cases into refinable rows without assessing
   * coverage. Needs only a `test_cases` document — no BRD or SRD.
   */
  extractTestCases: (batchId: number) =>
    api.post<TasJob>(`${TAS_BASE}/batches/${batchId}/extract-test-cases`),
  getAssessment: (batchId: number) =>
    api.get<TasCoverageAssessment | null>(`${TAS_BASE}/batches/${batchId}/assessment`),
  listRequirements: (projectId: number, params?: { batch_id?: number; status?: string[] }) => {
    const query = new URLSearchParams();
    if (params?.batch_id != null) query.set("batch_id", String(params.batch_id));
    for (const value of params?.status ?? []) query.append("status", value);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api.get<TasDerivedRequirement[]>(
      `${TAS_BASE}/projects/${projectId}/requirements${suffix}`,
    );
  },
  updateRequirement: (
    requirementId: number,
    body: {
      title?: string;
      summary?: string;
      acceptance_criteria?: string[];
      priority?: string;
      automation_relevance?: string;
    },
  ) => api.patch<TasDerivedRequirement>(`${TAS_BASE}/requirements/${requirementId}`, body),
  decideRequirements: (
    projectId: number,
    body: { requirement_ids: number[]; decision: "approve" | "reject"; reason?: string },
  ) =>
    api.post<TasDerivedRequirement[]>(
      `${TAS_BASE}/projects/${projectId}/requirements/decide`,
      body,
    ),
  /** Delete derived requirements. Any test case already generated from one
   *  survives but loses the link back to it - the count is in the summary. */
  deleteRequirements: (projectId: number, ids: number[]) =>
    api.post<TasDeletionSummary>(`${TAS_BASE}/projects/${projectId}/requirements/delete`, {
      ids,
    }),

  // Screen 2 â€” Automation TC Coverage Assessment
  listSourceTestCases: (projectId: number, params?: { batch_id?: number }) => {
    const query = new URLSearchParams();
    if (params?.batch_id != null) query.set("batch_id", String(params.batch_id));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api.get<TasSourceTestCase[]>(
      `${TAS_BASE}/projects/${projectId}/source-test-cases${suffix}`,
    );
  },
  /** Delete test cases read off an uploaded document. The refined version of
   *  one, if it exists, stays - re-extracting the document brings the source
   *  row back. */
  deleteSourceTestCases: (projectId: number, ids: number[]) =>
    api.post<TasDeletionSummary>(`${TAS_BASE}/projects/${projectId}/source-test-cases/delete`, {
      ids,
    }),
  /**
   * Two entry points, at least one required. `source_test_case_ids` refines
   * uploaded test cases in place, keeping their ID and name;
   * `requirement_ids` creates new test cases for coverage gaps.
   */
  generateTestCases: (
    projectId: number,
    body: {
      requirement_ids?: number[];
      source_test_case_ids?: number[];
      application_id?: number | null;
      application_environment?: string | null;
      include_existing_test_cases?: boolean;
      regenerate?: boolean;
    },
  ) => api.post<TasJob>(`${TAS_BASE}/projects/${projectId}/test-cases/generate`, body),
  listTestCases: (
    projectId: number,
    params?: { batch_id?: number; status?: string[]; classification?: string[] },
  ) => {
    const query = new URLSearchParams();
    if (params?.batch_id != null) query.set("batch_id", String(params.batch_id));
    for (const value of params?.status ?? []) query.append("status", value);
    for (const value of params?.classification ?? []) query.append("classification", value);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api.get<TasRefinedTestCase[]>(
      `${TAS_BASE}/projects/${projectId}/test-cases${suffix}`,
    );
  },
  getTestCase: (testCaseId: number) =>
    api.get<TasRefinedTestCase>(`${TAS_BASE}/test-cases/${testCaseId}`),
  updateTestCase: (testCaseId: number, body: Partial<TasRefinedTestCase>) =>
    api.patch<TasRefinedTestCase>(`${TAS_BASE}/test-cases/${testCaseId}`, body),
  bulkClassify: (
    projectId: number,
    body: { test_case_ids: number[]; classification?: TasClassification; reason?: string },
  ) =>
    api.post<{
      updated: TasRefinedTestCase[];
      policy_id?: number | null;
      policy_version?: number | null;
      unresolved: Array<Record<string, unknown>>;
    }>(`${TAS_BASE}/projects/${projectId}/test-cases/classify`, body),
  decideTestCases: (
    projectId: number,
    body: { test_case_ids: number[]; decision: "approve" | "reject"; reason?: string },
  ) =>
    api.post<{ updated: TasRefinedTestCase[]; blocked: TasBlocked[] }>(
      `${TAS_BASE}/projects/${projectId}/test-cases/decide`,
      body,
    ),
  /** Match each step's target against the discovered element catalog.
   *
   *  Synchronous, unlike the other studio actions: it is string matching over
   *  rows already stored, with no LLM and no browser. Advisory — an
   *  ungrounded test case can still be approved and generated. */
  groundTestCases: (
    projectId: number,
    body: { test_case_ids?: number[]; batch_id?: number },
  ) =>
    api.post<{ updated: TasRefinedTestCase[]; skipped: TasSkipped[] }>(
      `${TAS_BASE}/projects/${projectId}/test-cases/ground`,
      body,
    ),
  reopenTestCase: (testCaseId: number) =>
    api.post<TasRefinedTestCase>(`${TAS_BASE}/test-cases/${testCaseId}/reopen`),
  /** Delete refined test cases. Every version of each goes, and the database
   *  cascades away any script generated from them. */
  deleteTestCases: (projectId: number, ids: number[]) =>
    api.post<TasDeletionSummary>(`${TAS_BASE}/projects/${projectId}/test-cases/delete`, { ids }),
  /** Manual and Automation downloads are separate by design â€” xlsx returns a
   *  sheet per classification, csv must name one. */
  exportTestCasesUrl: (
    projectId: number,
    params: {
      format: "xlsx" | "csv";
      classification: "all" | "automation" | "manual";
      batch_id?: number;
    },
  ) => {
    const query = new URLSearchParams({
      format: params.format,
      classification: params.classification,
    });
    if (params.batch_id != null) query.set("batch_id", String(params.batch_id));
    return `/api/v1${TAS_BASE}/projects/${projectId}/test-cases/export?${query.toString()}`;
  },

  // Screen 3 â€” Automation Script Lab
  generateScripts: (
    projectId: number,
    body: {
      test_case_ids: number[];
      framework: TasFramework;
      regenerate?: boolean;
      /** Force the old LLM-writes-the-code path for Playwright instead of
       *  contract + Script Compiler. An escape hatch, not a routine option. */
      freeform?: boolean;
      environment_profile?: string;
    },
  ) => api.post<TasJob>(`${TAS_BASE}/projects/${projectId}/scripts/generate`, body),
  /** Execute the selected scripts once, for real. The only step that turns
   *  "should run" into "did run". */
  dryRunScripts: (projectId: number, scriptIds: number[]) =>
    api.post<TasJob>(`${TAS_BASE}/projects/${projectId}/scripts/dry-run`, {
      script_ids: scriptIds,
    }),
  listScripts: (
    projectId: number,
    params?: { framework?: TasFramework; test_case_id?: number },
  ) => {
    const query = new URLSearchParams();
    if (params?.framework) query.set("framework", params.framework);
    if (params?.test_case_id != null) query.set("test_case_id", String(params.test_case_id));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api.get<TasScriptAsset[]>(`${TAS_BASE}/projects/${projectId}/scripts${suffix}`);
  },
  getScript: (scriptId: number) => api.get<TasScriptAsset>(`${TAS_BASE}/scripts/${scriptId}`),
  updateScript: (
    scriptId: number,
    body: {
      code?: string;
      files?: Record<string, string>;
      execution_command?: string;
      setup_notes?: string[];
    },
  ) => api.patch<TasScriptAsset>(`${TAS_BASE}/scripts/${scriptId}`, body),
  decideScript: (scriptId: number, body: { decision: "approve" | "reopen"; reason?: string }) =>
    api.post<TasScriptAsset>(`${TAS_BASE}/scripts/${scriptId}/decide`, body),
  /** Delete generated scripts, version history included. The test case is
   *  untouched, so the script can be generated again. */
  deleteScripts: (projectId: number, ids: number[]) =>
    api.post<TasDeletionSummary>(`${TAS_BASE}/projects/${projectId}/scripts/delete`, { ids }),
  downloadScriptUrl: (scriptId: number) => `/api/v1${TAS_BASE}/scripts/${scriptId}/download`,
  downloadScriptsUrl: (projectId: number, framework?: TasFramework) =>
    `/api/v1${TAS_BASE}/projects/${projectId}/scripts/download${
      framework ? `?framework=${framework}` : ""
    }`,
};

