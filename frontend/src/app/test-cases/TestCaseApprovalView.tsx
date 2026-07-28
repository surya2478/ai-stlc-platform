"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  AppWindow,
  Bot,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Download,
  ExternalLink,
  FileCheck2,
  FileText,
  Filter,
  GitBranch,
  History,
  Link2,
  Loader2,
  MoreVertical,
  RefreshCw,
  Search,
  ShieldCheck,
  UserRound,
  X,
  XCircle,
} from "lucide-react";
import {
  applicationsApi,
  automationClassificationApi,
  exportApi,
  isClassificationDisabled,
  projectsApi,
  requirementsApi,
  reviewsApi,
  scenariosApi,
  testCasesApi,
  traceabilityApi,
  usersApi,
  type ApprovalAction,
  type ArtifactReview,
  type ProjectApplication,
  type ProjectMembership,
  type ProjectRole,
  type Requirement,
  type TestCase,
  type TestCaseAutomationClassification,
  type TestCaseHistory,
  type TestScenario,
  type UserAccount,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Drawer, DrawerContent, DrawerTitle } from "@/components/ui/drawer";
import { cn } from "@/lib/utils";
import { useAIAction } from "@/hooks/useAIAction";
import { AI_PROCESSING_STAGES } from "@/lib/ai-processing-stages";

type Tone = "blue" | "emerald" | "amber" | "red" | "purple" | "slate";
type InspectorTab = "review" | "traceability" | "test-case" | "evidence" | "history" | "activity" | "automation";
type QueueTab = "all" | "ready" | "pending" | "changes" | "approved" | "rejected" | "blocked";
type CheckState = "pass" | "warning" | "blocker";
type CheckScope = "approval" | "downstream";

type GovernanceCheck = {
  key: string;
  label: string;
  state: CheckState;
  scope: CheckScope;
  detail: string;
  guidance?: string;
  owner?: string;
};
type ApprovalRow = {
  testCase: TestCase;
  requirement?: Requirement;
  scenario?: TestScenario;
  application?: ProjectApplication;
  review?: ArtifactReview;
  approval?: ApprovalAction;
  classification?: TestCaseAutomationClassification;
  journeyId: string;
  journeyName: string;
  validationScore: number;
  validationFindings: string[];
  journeyCoverage: number;
  evidence: string[];
  discovery: string;
  reviewer?: UserAccount;
  checks: GovernanceCheck[];
  blockers: GovernanceCheck[];
  status: "Ready" | "Pending Review" | "Changes Requested" | "Approved" | "Rejected" | "Blocked";
};

function classificationCheckState(
  testCase: TestCase,
  classification: TestCaseAutomationClassification | undefined,
  enabled: boolean,
): GovernanceCheck {
  if (!enabled) {
    return { key: "automation_classification", label: "Automation classification", state: "pass", scope: "downstream", detail: "Not enabled for this project", owner: "Automation Classification" };
  }
  if (!testCase.automation_candidate) {
    return { key: "automation_classification", label: "Automation classification", state: "pass", scope: "downstream", detail: "Not required for a manual test case", owner: "Automation Classification" };
  }
  if (!classification) {
    return { key: "automation_classification", label: "Automation classification", state: "warning", scope: "downstream", detail: "Pending after test-case approval", guidance: "Classify the approved test case before automation design.", owner: "Automation Classification" };
  }
  if (classification.test_case_version !== testCase.version) {
    return { key: "automation_classification", label: "Automation classification", state: "warning", scope: "downstream", detail: "Reclassification required after approval", guidance: "Reclassify the approved version before automation design.", owner: "Automation Classification" };
  }
  if (classification.review_status !== "APPROVED") {
    return { key: "automation_classification", label: "Automation classification", state: "warning", scope: "downstream", detail: `${classification.candidate_status}: ${classification.review_status.replace("_", " ").toLowerCase()}`, guidance: "Complete classification review before automation design.", owner: "Automation Classification" };
  }
  return { key: "automation_classification", label: "Automation classification", state: "pass", scope: "downstream", detail: `${classification.candidate_status}: v${classification.version} approved`, owner: "Automation Classification" };
}

const GRID = "34px 72px 112px minmax(150px,1fr) 72px 92px 62px 88px 70px 78px 90px 102px 64px 90px 34px";
const PAGE_SIZE = 10;

function normal(value: unknown) {
  return String(value ?? "").trim().toLowerCase().replace(/[\s_-]+/g, " ");
}

function metadataString(metadata: Record<string, unknown> | undefined, ...keys: string[]) {
  for (const key of keys) {
    const value = metadata?.[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function metadataStrings(metadata: Record<string, unknown> | undefined, key: string) {
  const value = metadata?.[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())).map((item) => item.trim()) : [];
}

function errorMessage(error: unknown, fallback: string) {
  const candidate = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = candidate.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail && typeof (detail as { message?: unknown }).message === "string") {
    return String((detail as { message: string }).message);
  }
  return candidate.message || fallback;
}

function dateTime(value?: string | null) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function shortDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function ageLabel(value?: string | null) {
  if (!value) return "—";
  const hours = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 3_600_000));
  if (hours < 24) return `${Math.max(1, hours)}h`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}

function ppmId(requirement?: Requirement) {
  return metadataString(requirement?.metadata_, "ppm_id", "ppmId") || "Not assigned";
}

function scenarioClass(scenario?: TestScenario, testCase?: TestCase) {
  return scenario?.scenario_type || metadataString(testCase?.metadata_, "scenario_class") || testCase?.test_type || "Not classified";
}

function evidenceRequirements(testCase: TestCase) {
  const explicit = metadataStrings(testCase.metadata_, "evidence_requirements");
  if (explicit.length) return explicit;
  return metadataStrings(testCase.metadata_, "required_evidence_types");
}

function discoveryState(testCase: TestCase) {
  if (!(testCase.automation_candidate || testCase.automation_eligible === "yes")) return "Not required";
  return metadataString(testCase.metadata_, "discovery_eligibility", "discovery_status") || "Not evaluated";
}

function isDiscoveryEvaluated(value: string) {
  return ["complete", "completed", "eligible", "passed", "ready", "ineligible", "blocked"].includes(normal(value));
}

function journeyFor(requirement?: Requirement, testCase?: TestCase) {
  const id = metadataString(testCase?.metadata_, "journey_id", "journeyId") || metadataString(requirement?.metadata_, "journey_id", "journeyId");
  const name = metadataString(testCase?.metadata_, "journey_name", "journeyName") || metadataString(requirement?.metadata_, "journey_name", "journeyName", "business_journey") || requirement?.business_process || "Not mapped";
  return { id: id || "Not mapped", name };
}

function journeyReviewed(testCase: TestCase) {
  if (testCase.metadata_?.journey_reviewed === true) return true;
  const state = metadataString(testCase.metadata_, "journey_status", "journey_coverage_status");
  return ["reviewed", "complete", "completed", "approved", "ready"].includes(normal(state));
}

function contentValidation(testCase: TestCase) {
  const steps = testCase.steps || [];
  const checks: Array<[boolean, string]> = [
    [Boolean(testCase.title.trim()), "Add a clear test-case title."],
    [Boolean(testCase.preconditions?.length), "Add at least one precondition."],
    [Boolean(steps.length), "Add at least one ordered test step."],
    [Boolean(steps.length && steps.every((step) => Boolean(step.action?.trim()))), "Complete the action for every test step."],
    [Boolean(steps.length && steps.every((step) => Boolean(step.expected_result?.trim()))), "Add an expected result to every test step."],
    [Boolean(testCase.expected_result?.trim()), "Add the overall expected result."],
  ];
  return {
    score: Math.round((checks.filter(([passed]) => passed).length / checks.length) * 100),
    missing: checks.filter(([passed]) => !passed).map(([, message]) => message),
  };
}

function reviewScoreLabel(score: number | null | undefined) {
  return typeof score === "number"
    ? `${score.toFixed(1)}/5 (${Math.round(Math.max(0, Math.min(5, score)) * 20)}%)`
    : "No score";
}

function coverageFor(requirement: Requirement | undefined, allScenarios: TestScenario[]) {
  if (!requirement) return 0;
  const kinds = new Set(allScenarios.filter((item) => item.requirement_id === requirement.id && item.status === "approved").map((item) => normal(item.scenario_type)));
  const required = ["positive", "negative", "boundary", "recovery"];
  return Math.round((required.filter((kind) => Array.from(kinds).some((value) => value.includes(kind) || (kind === "boundary" && value.includes("edge")))).length / required.length) * 100);
}

function toneClass(tone: Tone) {
  return cn(
    "border",
    tone === "blue" && "border-blue-100 bg-blue-50 text-blue-700",
    tone === "emerald" && "border-emerald-100 bg-emerald-50 text-emerald-700",
    tone === "amber" && "border-amber-100 bg-amber-50 text-amber-700",
    tone === "red" && "border-red-100 bg-red-50 text-red-700",
    tone === "purple" && "border-purple-100 bg-purple-50 text-purple-700",
    tone === "slate" && "border-slate-200 bg-slate-50 text-slate-600",
  );
}

function statusTone(status: ApprovalRow["status"]): Tone {
  if (status === "Approved" || status === "Ready") return "emerald";
  if (status === "Pending Review" || status === "Changes Requested") return "amber";
  if (status === "Rejected" || status === "Blocked") return "red";
  return "slate";
}

function Badge({ children, tone = "slate" }: { children: React.ReactNode; tone?: Tone }) {
  const isLaterStage = children === "Missing" && tone === "red";
  return <span className={cn("inline-flex items-center rounded px-1.5 py-0.5 text-[9px] font-extrabold", toneClass(isLaterStage ? "amber" : tone))}>{isLaterStage ? "Later" : children}</span>;
}

function Progress({ value, tone = "emerald" }: { value: number; tone?: Tone }) {
  return <div className="h-1.5 w-full rounded-full bg-slate-100"><div className={cn("h-full rounded-full", tone === "emerald" ? "bg-emerald-500" : tone === "amber" ? "bg-amber-500" : tone === "red" ? "bg-red-500" : "bg-blue-500")} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>;
}

function Kpi({ label, value, detail, icon: Icon, tone }: { label: string; value: number; detail: string; icon: typeof FileText; tone: Tone }) {
  return <div className="rounded-lg border border-slate-200 bg-white px-3 py-3 shadow-sm">
    <div className="flex items-center gap-2"><span className={cn("flex h-7 w-7 items-center justify-center rounded-md", toneClass(tone))}><Icon className="h-3.5 w-3.5" /></span><p className="text-[10px] font-extrabold text-slate-800">{label}</p></div>
    <p className="mt-3 text-xl font-black leading-none text-slate-950">{value}</p><p className="mt-2 text-[9px] font-semibold text-slate-500">{detail}</p>
  </div>;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="rounded-md border border-dashed border-slate-200 p-3 text-[10px] font-semibold text-slate-500">{children}</div>;
}

function Panel({ title, action, children, className }: { title: string; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return <section className={cn("rounded-lg border border-slate-200 bg-white p-3", className)}><div className="mb-2 flex items-center justify-between"><h3 className="text-[10px] font-extrabold text-slate-800">{title}</h3>{action}</div>{children}</section>;
}

export function TestCaseApprovalView({ projectId, initialTestCaseId = null }: { projectId: number | null; initialTestCaseId?: number | null }) {
  const router = useRouter();
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [scenarios, setScenarios] = useState<TestScenario[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [applications, setApplications] = useState<ProjectApplication[]>([]);
  const [reviews, setReviews] = useState<ArtifactReview[]>([]);
  const [approvals, setApprovals] = useState<ApprovalAction[]>([]);
  const [classifications, setClassifications] = useState<TestCaseAutomationClassification[]>([]);
  const [classificationsEnabled, setClassificationsEnabled] = useState(true);
  const [memberships, setMemberships] = useState<ProjectMembership[]>([]);
  const [roles, setRoles] = useState<ProjectRole[]>([]);
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [me, setMe] = useState<UserAccount | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [history, setHistory] = useState<TestCaseHistory[]>([]);
  const [reviewHistory, setReviewHistory] = useState<ArtifactReview[]>([]);
  const [tab, setTab] = useState<QueueTab>("all");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("review");
  const [query, setQuery] = useState("");
  const [reviewFilter, setReviewFilter] = useState("all");
  const [domainFilter, setDomainFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [classFilter, setClassFilter] = useState("all");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [reviewerFilter, setReviewerFilter] = useState("all");
  const [journeyFilter, setJourneyFilter] = useState("all");
  const [evidenceFilter, setEvidenceFilter] = useState("all");
  const [applicationFilter, setApplicationFilter] = useState("all");
  const [showMoreFilters, setShowMoreFilters] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [decisionMode, setDecisionMode] = useState<"changes" | "reject" | null>(null);
  const [comment, setComment] = useState("");
  const [assigning, setAssigning] = useState(false);
  const [assigneeId, setAssigneeId] = useState("");
  const [actionMenu, setActionMenu] = useState<number | null>(null);

  const loadData = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const [reqRes, scenarioRes, caseRes, appRes, reviewRes, approvalRes, membershipRes, roleRes, userRes, meRes] = await Promise.all([
        requirementsApi.list(projectId, { limit: 200 }),
        scenariosApi.list(projectId),
        testCasesApi.list(projectId),
        applicationsApi.getForProject(projectId),
        reviewsApi.listForProject(projectId, "scenario_test_case_coverage"),
        traceabilityApi.approvals(projectId, { entity_type: "test_case", page_size: 200 }),
        projectsApi.memberships(projectId),
        projectsApi.roles(),
        usersApi.list({ project_id: projectId, limit: 200 }),
        usersApi.me(),
      ]);
      setRequirements(reqRes.data); setScenarios(scenarioRes.data); setTestCases(caseRes.data);
      setApplications(appRes.data.applications.filter((item) => item.is_active)); setReviews(reviewRes.data); setApprovals(approvalRes.data);
      setMemberships(membershipRes.data); setRoles(roleRes.data); setUsers(userRes.data); setMe(meRes.data);
      setSelectedId((current) => {
        if (current && caseRes.data.some((item) => item.id === current)) return current;
        if (initialTestCaseId && caseRes.data.some((item) => item.id === initialTestCaseId)) return initialTestCaseId;
        return caseRes.data[0]?.id ?? null;
      });
      setLastRefreshed(new Date());
    } catch (loadError) { setError(errorMessage(loadError, "Could not load the test-case approval queue.")); }
    finally { setLoading(false); }

    // Loaded separately from the Promise.all above: a 404 here just means
    // Classification failures must not break the rest
    // of the (already working) approval queue.
    try {
      const clsRes = await automationClassificationApi.listForProject(projectId);
      setClassifications(clsRes.data); setClassificationsEnabled(true);
    } catch (clsError) {
      setClassifications([]);
      setClassificationsEnabled(!isClassificationDisabled(clsError));
    }
  }, [initialTestCaseId, projectId]);

  useEffect(() => { void loadData(); }, [loadData]);

  useEffect(() => {
    if (!projectId || !selectedId) { setHistory([]); setReviewHistory([]); return; }
    const selectedCase = testCases.find((item) => item.id === selectedId);
    const scenarioId = selectedCase?.scenario_id ?? selectedCase?.linked_scenario_id;
    const reviewPromise = scenarioId
      ? reviewsApi.history("scenario_test_case_coverage", scenarioId, projectId)
      : Promise.resolve({ data: [] as ArtifactReview[] });
    Promise.all([testCasesApi.history(selectedId), reviewPromise])
      .then(([historyRes, reviewRes]) => { setHistory(historyRes.data); setReviewHistory(reviewRes.data); })
      .catch((loadError) => setError(errorMessage(loadError, "Could not load the selected test-case history.")));
  }, [projectId, selectedId, testCases]);

  const requirementById = useMemo(() => new Map(requirements.map((item) => [item.id, item])), [requirements]);
  const requirementByKey = useMemo(() => new Map(requirements.map((item) => [item.requirement_id, item])), [requirements]);
  const scenarioById = useMemo(() => new Map(scenarios.map((item) => [item.id, item])), [scenarios]);
  const appById = useMemo(() => new Map(applications.filter((item) => item.id != null).map((item) => [Number(item.id), item])), [applications]);
  const userById = useMemo(() => new Map(users.map((item) => [item.id, item])), [users]);
  const activeMembershipByUser = useMemo(() => new Map(memberships.filter((item) => item.is_active).map((item) => [item.user_id, item])), [memberships]);
  const roleByName = useMemo(() => new Map(roles.map((item) => [item.role, item])), [roles]);
  const myMembership = me ? activeMembershipByUser.get(me.id) : undefined;
  const myRole = myMembership ? roleByName.get(myMembership.role) : me ? roleByName.get(me.role) : undefined;
  const canApprove = Boolean(me?.is_superuser || myRole?.permissions.includes("approve_test_cases"));
  const canEvaluateClassification = Boolean(me?.is_superuser || myRole?.permissions.includes("automation_classification.evaluate"));
  const canReviewClassification = Boolean(me?.is_superuser || myRole?.permissions.includes("automation_classification.review"));
  const canApproveClassification = Boolean(me?.is_superuser || myRole?.permissions.includes("automation_classification.approve"));
  const classificationByTestCaseId = useMemo(() => new Map(classifications.map((item) => [item.test_case_id, item])), [classifications]);

  const rows = useMemo<ApprovalRow[]>(() => testCases.map((testCase) => {
    const requirement = (testCase.requirement_id ? requirementById.get(testCase.requirement_id) : undefined) || (testCase.linked_requirement_id ? requirementById.get(testCase.linked_requirement_id) : undefined) || (testCase.linked_requirement_key ? requirementByKey.get(testCase.linked_requirement_key) : undefined);
    const scenario = (testCase.scenario_id ? scenarioById.get(testCase.scenario_id) : undefined) || (testCase.linked_scenario_id ? scenarioById.get(testCase.linked_scenario_id) : undefined);
    const application = testCase.application_id ? appById.get(testCase.application_id) : undefined;
    const review = scenario
      ? reviews
        .filter((item) => item.artifact_id === scenario.id)
        .sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
      : undefined;
    const approval = approvals.filter((item) => item.entity_id === testCase.id).sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
    const reviewerId = Number(testCase.metadata_?.assigned_reviewer_id || 0);
    const reviewer = reviewerId ? userById.get(reviewerId) : undefined;
    const evidence = evidenceRequirements(testCase);
    const discovery = discoveryState(testCase);
    const journey = journeyFor(requirement, testCase);
    const validation = contentValidation(testCase);
    const validationScore = validation.score;
    const journeyCoverage = coverageFor(requirement, scenarios);
    const classification = classificationByTestCaseId.get(testCase.id);
    const checks: GovernanceCheck[] = [
      { key: "requirement", label: "Requirement approved", state: requirement?.status === "approved" ? "pass" : "blocker", scope: "approval", detail: requirement ? `${requirement.requirement_id}: ${requirement.status}` : "No linked requirement", guidance: requirement ? `Approve ${requirement.requirement_id} in Requirements > Review & Approval.` : "Link an approved requirement in the Test Case Editor.", owner: "Requirements" },
      { key: "scenario", label: "Scenario approved", state: scenario?.status === "approved" ? "pass" : "blocker", scope: "approval", detail: scenario ? `${scenario.scenario_id}: ${scenario.status}` : "No linked scenario", guidance: scenario ? `Approve ${scenario.scenario_id} in Test Planning.` : "Link an approved scenario in the Test Case Editor.", owner: "Test Planning" },
      { key: "validation", label: "Test case content complete", state: validationScore === 100 ? "pass" : "blocker", scope: "approval", detail: validationScore === 100 ? "100/100 required fields complete" : `${validationScore}/100: ${validation.missing[0]}`, guidance: `${validation.missing.join(" ")} Update the test case in Test Case Editor, then return to approval.`, owner: "Test Case Editor" },
      { key: "journey", label: "Journey coverage", state: journey.id !== "Not mapped" && journeyReviewed(testCase) ? "pass" : "warning", scope: "downstream", detail: journey.id === "Not mapped" ? "Later: map in Journey Graph" : journeyReviewed(testCase) ? `${journeyCoverage}% scenario coverage` : "Later: review in Journey Graph", guidance: "Complete journey mapping and coverage review before journey sign-off. This does not block test-case content approval.", owner: "Journey Graph" },
      { key: "application", label: "Application mapping", state: application ? "pass" : "warning", scope: "downstream", detail: application?.name || "Later: map before discovery", guidance: "Map the approved test case to an application before discovery or automation starts.", owner: "Application Registry" },
      { key: "evidence", label: "Evidence policy", state: evidence.length ? "pass" : "warning", scope: "downstream", detail: evidence.length ? `${evidence.length} required type${evidence.length === 1 ? "" : "s"}` : "Later: define before execution", guidance: "Declare screenshots, logs, traces, or audit evidence before execution. Evidence is not required to approve test-case content.", owner: "Execution Preparation" },
      { key: "discovery", label: "Discovery eligibility", state: discovery === "Not required" || isDiscoveryEvaluated(discovery) ? "pass" : "warning", scope: "downstream", detail: discovery === "Not evaluated" ? "Later: evaluate after approval" : discovery, guidance: "Evaluate discovery eligibility after the test case is approved and before a discovery session starts.", owner: "Application Discovery" },
      {
        key: "review",
        label: "Scenario test-case set review",
        state: review?.verdict === "pass" ? "pass" : review?.review_mode === "gating" ? "blocker" : "warning",
        scope: "approval",
        detail: review
          ? `${review.verdict.replace("_", " ")}: ${reviewScoreLabel(review.overall_score)}: ${review.review_mode}`
          : "No persisted set-level review",
        guidance: review?.review_mode === "gating" ? "Resolve the gating AI review findings and rerun the scenario test-case set review." : "Advisory findings may be improved but do not block approval.",
        owner: "AI Review",
      },
      { key: "policy", label: "Reviewer permission", state: canApprove ? "pass" : "blocker", scope: "approval", detail: canApprove ? "Approval permission confirmed" : "Current user cannot approve test cases", guidance: "Assign a project reviewer with the approve_test_cases permission.", owner: "Project Settings" },
      classificationCheckState(testCase, classification, classificationsEnabled),
    ];
    const blockers = checks.filter((item) => item.state === "blocker");
    const approvalDecision = normal(approval?.decision);
    const persisted = normal(testCase.status || testCase.approval_status);
    let status: ApprovalRow["status"];
    if (persisted === "approved" || approvalDecision === "approved") status = "Approved";
    else if (persisted === "rejected" || approvalDecision === "rejected") status = "Rejected";
    else if (approvalDecision === "requested changes" || approvalDecision === "requested_changes" || normal(testCase.metadata_?.review_status) === "changes requested") status = "Changes Requested";
    else if (persisted === "blocked" || blockers.length) status = "Blocked";
    else if (["pending approval", "pending", "pending review"].includes(persisted)) status = "Pending Review";
    else status = "Ready";
    return { testCase, requirement, scenario, application, review, approval, classification, journeyId: journey.id, journeyName: journey.name, validationScore, validationFindings: validation.missing, journeyCoverage, evidence, discovery, reviewer, checks, blockers, status };
  }), [appById, approvals, canApprove, classificationByTestCaseId, classificationsEnabled, requirementById, requirementByKey, reviews, scenarioById, scenarios, testCases, userById]);

  const selected = rows.find((item) => item.testCase.id === selectedId) || rows[0];

  useEffect(() => {
    setInspectorTab("review"); setDecisionMode(null); setComment(""); setAssigning(false);
    setAssigneeId(selected?.reviewer ? String(selected.reviewer.id) : "");
  }, [selected?.testCase.id, selected?.reviewer]);

  const counts = useMemo(() => ({
    all: rows.length,
    ready: rows.filter((item) => item.status === "Ready").length,
    pending: rows.filter((item) => item.status === "Pending Review").length,
    changes: rows.filter((item) => item.status === "Changes Requested").length,
    approved: rows.filter((item) => item.status === "Approved").length,
    rejected: rows.filter((item) => item.status === "Rejected").length,
    blocked: rows.filter((item) => item.status === "Blocked").length,
  }), [rows]);

  const filtered = useMemo(() => rows.filter((row) => {
    const text = [row.testCase.test_case_id, row.testCase.title, row.requirement?.requirement_id, ppmId(row.requirement), row.scenario?.scenario_id, row.scenario?.title, row.journeyId, row.journeyName].join(" ").toLowerCase();
    const tabMatch = tab === "all" || (tab === "ready" && row.status === "Ready") || (tab === "pending" && row.status === "Pending Review") || (tab === "changes" && row.status === "Changes Requested") || (tab === "approved" && row.status === "Approved") || (tab === "rejected" && row.status === "Rejected") || (tab === "blocked" && row.status === "Blocked");
    return tabMatch && (!query.trim() || text.includes(query.trim().toLowerCase()))
      && (reviewFilter === "all" || row.status === reviewFilter)
      && (domainFilter === "all" || (row.requirement?.telecom_domain || row.testCase.telecom_domain || "Unassigned") === domainFilter)
      && (typeFilter === "all" || (row.testCase.test_type || "Unassigned") === typeFilter)
      && (classFilter === "all" || scenarioClass(row.scenario, row.testCase) === classFilter)
      && (priorityFilter === "all" || row.testCase.priority === priorityFilter)
      && (reviewerFilter === "all" || (reviewerFilter === "unassigned" ? !row.reviewer : String(row.reviewer?.id) === reviewerFilter))
      && (journeyFilter === "all" || (journeyFilter === "ready" ? row.journeyId !== "Not mapped" && journeyReviewed(row.testCase) : row.journeyId === "Not mapped" || !journeyReviewed(row.testCase)))
      && (evidenceFilter === "all" || (evidenceFilter === "complete" ? row.evidence.length > 0 : row.evidence.length === 0))
      && (applicationFilter === "all" || (applicationFilter === "mapped" ? Boolean(row.application) : !row.application));
  }), [applicationFilter, classFilter, domainFilter, evidenceFilter, journeyFilter, priorityFilter, query, reviewFilter, reviewerFilter, rows, tab, typeFilter]);

  useEffect(() => { setPage(1); }, [query, tab, reviewFilter, domainFilter, typeFilter, classFilter, priorityFilter, reviewerFilter, journeyFilter, evidenceFilter, applicationFilter]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const allChecks = rows.flatMap((item) => item.checks);
  const readiness = (key: string) => {
    const relevant = allChecks.filter((item) => item.key === key);
    const passed = relevant.filter((item) => item.state === "pass").length;
    const warnings = relevant.filter((item) => item.state === "warning").length;
    return { passed, total: relevant.length, warnings, scope: relevant[0]?.scope || "approval", good: relevant.length > 0 && passed === relevant.length };
  };

  function clearFilters() {
    setQuery(""); setReviewFilter("all"); setDomainFilter("all"); setTypeFilter("all"); setClassFilter("all"); setPriorityFilter("all"); setReviewerFilter("all"); setJourneyFilter("all"); setEvidenceFilter("all"); setApplicationFilter("all");
  }

  async function approveRows(targets: ApprovalRow[]) {
    const eligible = targets.filter((row) => row.blockers.length === 0 && !["Approved", "Rejected"].includes(row.status));
    const skipped = targets.length - eligible.length;
    if (!eligible.length) { setError(`No selected test case is eligible for approval. ${skipped} blocked or finalised row${skipped === 1 ? " was" : "s were"} excluded.`); return; }
    setBusy("approve"); setError(""); setNotice("");
    const results = await Promise.allSettled(eligible.map((row) => testCasesApi.approve(row.testCase.id, "approve", "Approved from Test Case Approval workspace")));
    const failures = results.map((result, index) => result.status === "rejected" ? `${eligible[index].testCase.test_case_id}: ${errorMessage(result.reason, "Approval failed")}` : "").filter(Boolean);
    const succeeded = results.length - failures.length;
    if (failures.length) setError(failures.join(" · "));
    setNotice(`${succeeded} approved, ${failures.length} failed, ${skipped} ineligible.`);
    setSelectedIds(new Set()); setBusy(""); await loadData();
  }

  async function submitDecision() {
    if (!selected || !decisionMode || !comment.trim()) return;
    setBusy(decisionMode); setError(""); setNotice("");
    try {
      if (decisionMode === "reject") await testCasesApi.approve(selected.testCase.id, "reject", comment.trim());
      else await traceabilityApi.decide("test_case", selected.testCase.id, "request_changes", comment.trim(), { reviewer_comment: comment.trim() });
      setNotice(decisionMode === "reject" ? `${selected.testCase.test_case_id} was rejected.` : `Changes were requested for ${selected.testCase.test_case_id}.`);
      setDecisionMode(null); setComment(""); await loadData();
    } catch (decisionError) { setError(errorMessage(decisionError, "Could not record the review decision.")); }
    finally { setBusy(""); }
  }

  async function assignReviewer() {
    if (!selected || !assigneeId) return;
    setBusy("assign"); setError(""); setNotice("");
    try {
      const assignee = userById.get(Number(assigneeId));
      await testCasesApi.update(selected.testCase.id, { metadata_: { ...(selected.testCase.metadata_ || {}), assigned_reviewer_id: Number(assigneeId) }, comment: `Assigned reviewer: ${assignee?.full_name || assigneeId}` });
      setNotice(`${selected.testCase.test_case_id} assigned to ${assignee?.full_name || "the selected reviewer"}.`); setAssigning(false); await loadData();
    } catch (assignError) { setError(errorMessage(assignError, "Could not assign the reviewer.")); }
    finally { setBusy(""); }
  }

  async function exportQueue() {
    if (!projectId) return;
    try {
      await exportApi.downloadTestCases(
        projectId,
        "excel",
        true,
        filtered.map((row) => row.testCase.id),
        `test_cases_approval_project_${projectId}.xlsx`,
      );
      setNotice("Review queue exported in the canonical test-case import template.");
    } catch (exportError) {
      setError(errorMessage(exportError, "Could not export the review queue."));
    }
  }

  async function exportSelected() {
    if (!projectId || !selected) return;
    try {
      await exportApi.downloadTestCases(
        projectId,
        "excel",
        true,
        [selected.testCase.id],
        `${selected.testCase.test_case_id}.xlsx`,
      );
      setNotice(`${selected.testCase.test_case_id} exported in the canonical test-case import template.`);
    } catch (exportError) {
      setError(errorMessage(exportError, "Could not export the test case."));
    }
  }

  const domains = Array.from(new Set(rows.map((row) => row.requirement?.telecom_domain || row.testCase.telecom_domain).filter(Boolean))) as string[];
  const testTypes = Array.from(new Set(rows.map((row) => row.testCase.test_type || "Unassigned")));
  const classes = Array.from(new Set(rows.map((row) => scenarioClass(row.scenario, row.testCase))));
  const priorities = Array.from(new Set(rows.map((row) => row.testCase.priority)));
  const activeReviewerUsers = users.filter((user) => activeMembershipByUser.has(user.id));

  if (!projectId) return <Empty>Select a project to load Test Case Approval.</Empty>;

  return <div className="min-h-full pb-3">
    <main className="space-y-3">
      <div className="flex items-center gap-2 text-[10px] font-semibold text-slate-500"><span>e&amp; STLC</span><ChevronRight className="h-3 w-3 text-slate-300" /><span className="text-[#1b59f8]">Test Planning</span><ChevronRight className="h-3 w-3 text-slate-300" /><span className="text-slate-800">Test Case Approval</span></div>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-[270px] flex-1 items-start gap-3"><span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-purple-100 bg-purple-50 text-purple-600"><FileCheck2 className="h-4 w-4" /></span><div><div className="flex items-center gap-2"><h1 className="text-xl font-black text-slate-950">Test Case Approval</h1><Badge tone="purple">P1-S3 UI-013</Badge></div><p className="mt-1 text-sm font-normal leading-5 text-slate-500">Independently review and approve validated test cases before discovery and execution.</p></div></div>
        <div className="ml-auto flex shrink-0 flex-wrap items-center justify-end gap-2"><span className="text-[9px] font-semibold text-slate-500">Last refreshed: {lastRefreshed ? dateTime(lastRefreshed.toISOString()) : "Not yet refreshed"}</span><Button variant="outline" onClick={() => void loadData()} disabled={loading} className="h-8 gap-1.5 px-3 text-[10px] font-bold"><RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />Refresh</Button><Button variant="outline" onClick={() => void exportQueue()} disabled={!filtered.length} className="h-8 gap-1.5 px-3 text-[10px] font-bold"><Download className="h-3.5 w-3.5" />Export Review Queue (.xlsx)</Button><Button onClick={() => void approveRows(rows.filter((row) => selectedIds.has(row.testCase.id)))} disabled={!selectedIds.size || busy === "approve" || !canApprove} className="h-8 gap-1.5 bg-[#1b59f8] px-3 text-[10px] font-bold text-white"><Check className="h-3.5 w-3.5" />Approve Selected</Button></div>
      </header>

      {error && <div role="alert" className="flex items-center justify-between rounded-md border border-red-200 bg-red-50 px-3 py-2 text-[10px] font-bold text-red-700"><span className="flex items-center gap-2"><AlertTriangle className="h-3.5 w-3.5" />{error}</span><button aria-label="Dismiss error" onClick={() => setError("")}><X className="h-3.5 w-3.5" /></button></div>}
      {notice && <div role="status" className="flex items-center justify-between rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-[10px] font-bold text-emerald-700"><span className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5" />{notice}</span><button aria-label="Dismiss notice" onClick={() => setNotice("")}><X className="h-3.5 w-3.5" /></button></div>}

      <div className="grid grid-cols-3 gap-2 2xl:grid-cols-6">
        <Kpi label="Total for Review" value={counts.all} detail="All test cases in queue" icon={FileText} tone="blue" />
        <Kpi label="Ready for Approval" value={counts.ready} detail={`${counts.all ? Math.round(counts.ready / counts.all * 100) : 0}% ready`} icon={ShieldCheck} tone="emerald" />
        <Kpi label="Pending Review" value={counts.pending} detail="Awaiting reviewer decision" icon={Clock3} tone="red" />
        <Kpi label="Changes Requested" value={counts.changes} detail="Need updates" icon={History} tone="amber" />
        <Kpi label="Approved" value={counts.approved} detail={`${counts.all ? Math.round(counts.approved / counts.all * 100) : 0}% approved`} icon={CheckCircle2} tone="emerald" />
        <Kpi label="Rejected / Blocked" value={counts.rejected + counts.blocked} detail="Rejected or unresolved blockers" icon={XCircle} tone="red" />
      </div>

      <section className="rounded-lg border border-slate-200 bg-white px-3 py-3 shadow-sm"><div className="mb-3 flex items-center justify-between"><div><h2 className="text-[10px] font-extrabold uppercase tracking-wide text-slate-700">Approval & Downstream Readiness</h2><p className="mt-1 text-[9px] font-semibold text-slate-500">Only approval-stage checks block the reviewer decision. Blue clock items are completed later.</p></div><span className="text-[9px] font-bold text-[#1b59f8]">Persisted project records</span></div><div className="grid grid-cols-4 gap-2 2xl:grid-cols-9">
        {["requirement", "scenario", "validation", "journey", "application", "evidence", "discovery", "policy", "automation_classification"].map((key) => { const item = readiness(key); const label = rows[0]?.checks.find((check) => check.key === key)?.label || key; const later = item.scope === "downstream" && item.warnings > 0; return <div key={key} className="flex min-w-0 gap-2"><span className={cn("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full", item.good ? "bg-emerald-50 text-emerald-600" : later ? "bg-blue-50 text-blue-600" : "bg-red-50 text-red-600")}>{item.good ? <CheckCircle2 className="h-3.5 w-3.5" /> : later ? <Clock3 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}</span><div className="min-w-0"><p className="text-[8px] font-bold leading-3 text-slate-700">{label}</p><p className="mt-1 text-[9px] font-extrabold text-slate-900">{item.passed}/{item.total}{later ? " · Later stage" : ""}</p></div></div>; })}
      </div></section>

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center gap-1 border-b border-slate-100 px-3 py-2">{([
          ["all", "All"], ["ready", "Ready"], ["pending", "Pending"], ["changes", "Changes Requested"], ["approved", "Approved"], ["rejected", "Rejected"], ["blocked", "Blocked"],
        ] as Array<[QueueTab, string]>).map(([key, label]) => <button key={key} onClick={() => setTab(key)} className={cn("rounded-md px-3 py-1.5 text-[9px] font-extrabold", tab === key ? "bg-[#1b59f8] text-white" : "text-slate-600 hover:bg-slate-50")}>{label}<span className={cn("ml-1 rounded px-1 py-0.5", tab === key ? "bg-white/20" : "bg-slate-100")}>{counts[key]}</span></button>)}</div>
        <div className="space-y-2 border-b border-slate-100 p-3">
          <div className="grid grid-cols-[minmax(230px,1.6fr)_repeat(5,minmax(110px,1fr))_94px] gap-2"><label className="relative"><Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" /><input aria-label="Search approval queue" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by TC ID, requirement ID, PPM ID, title, scenario or journey" className="h-8 w-full rounded-md border border-slate-200 pl-9 pr-3 text-[9px] outline-none focus:border-blue-400" /></label><FilterSelect label="Review status" value={reviewFilter} setValue={setReviewFilter} options={Object.values({ ready: "Ready", pending: "Pending Review", changes: "Changes Requested", approved: "Approved", rejected: "Rejected", blocked: "Blocked" })} /><FilterSelect label="Domain" value={domainFilter} setValue={setDomainFilter} options={domains} /><FilterSelect label="Test type" value={typeFilter} setValue={setTypeFilter} options={testTypes} /><FilterSelect label="Scenario class" value={classFilter} setValue={setClassFilter} options={classes} /><FilterSelect label="Priority" value={priorityFilter} setValue={setPriorityFilter} options={priorities} /><Button variant="outline" onClick={() => setShowMoreFilters(!showMoreFilters)} className="h-8 gap-1 text-[9px] font-bold"><Filter className="h-3.5 w-3.5" />More Filters</Button></div>
          {showMoreFilters && <div className="grid grid-cols-[repeat(4,minmax(150px,1fr))_94px] gap-2"><FilterSelect label="Assigned reviewer" value={reviewerFilter} setValue={setReviewerFilter} options={activeReviewerUsers.map((user) => user.full_name)} optionValues={activeReviewerUsers.map((user) => String(user.id))} extra={[{ value: "unassigned", label: "Unassigned" }]} /><FilterSelect label="Journey readiness" value={journeyFilter} setValue={setJourneyFilter} options={["Ready", "Missing / Unreviewed"]} optionValues={["ready", "missing"]} /><FilterSelect label="Evidence status" value={evidenceFilter} setValue={setEvidenceFilter} options={["Complete", "Missing"]} optionValues={["complete", "missing"]} /><FilterSelect label="Application mapping" value={applicationFilter} setValue={setApplicationFilter} options={["Mapped", "Missing"]} optionValues={["mapped", "missing"]} /><button onClick={clearFilters} className="h-8 text-[9px] font-extrabold text-[#1b59f8]">Clear Filters</button></div>}
        </div>

        <div className="overflow-x-auto"><div className="min-w-[1250px]"><div className="grid items-center border-b border-slate-200 bg-slate-50 px-2 py-2 text-[8px] font-extrabold uppercase tracking-wide text-slate-500" style={{ gridTemplateColumns: GRID }}><span><input aria-label="Select visible test cases" type="checkbox" checked={pageRows.length > 0 && pageRows.every((row) => selectedIds.has(row.testCase.id))} onChange={(event) => setSelectedIds((current) => { const next = new Set(current); pageRows.forEach((row) => event.target.checked ? next.add(row.testCase.id) : next.delete(row.testCase.id)); return next; })} /></span><span>TC ID</span><span>Requirement<br />ID / PPM ID</span><span>Title</span><span>Test type</span><span>Scenario class</span><span>Priority</span><span>Journey coverage</span><span>Validation</span><span>Evidence</span><span>Review status</span><span>Reviewer</span><span>SLA / age</span><span>Updated</span><span /></div>
          {loading ? <div className="flex h-40 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-blue-600" /></div> : pageRows.length ? pageRows.map((row) => <div key={row.testCase.id} onClick={() => { setSelectedId(row.testCase.id); setInspectorOpen(true); }} className={cn("relative grid min-h-[54px] cursor-pointer items-center border-b border-slate-100 px-2 py-2 text-[9px] font-semibold text-slate-600 hover:bg-blue-50/40", selected?.testCase.id === row.testCase.id && "bg-blue-50/50 ring-1 ring-inset ring-blue-400")} style={{ gridTemplateColumns: GRID }}><span onClick={(event) => event.stopPropagation()}><input aria-label={`Select ${row.testCase.test_case_id}`} type="checkbox" checked={selectedIds.has(row.testCase.id)} onChange={(event) => setSelectedIds((current) => { const next = new Set(current); event.target.checked ? next.add(row.testCase.id) : next.delete(row.testCase.id); return next; })} /></span><button className="text-left font-extrabold text-[#1b59f8]">{row.testCase.test_case_id}</button><span><strong className="block text-slate-800">{row.requirement?.requirement_id || "Unlinked"}</strong><span className="text-[8px] text-slate-500">{ppmId(row.requirement)}</span></span><span className="pr-2 font-bold leading-3 text-slate-800">{row.testCase.title}</span><span className="text-blue-700">{row.testCase.test_type || "Unassigned"}</span><span className="truncate pr-1">{scenarioClass(row.scenario, row.testCase)}</span><span><Badge tone={normal(row.testCase.priority).includes("high") ? "red" : normal(row.testCase.priority).includes("medium") ? "amber" : "emerald"}>{row.testCase.priority}</Badge></span><span className="pr-2"><span className="mb-1 block font-bold text-slate-800">{row.journeyCoverage}%</span><Progress value={row.journeyCoverage} tone={row.journeyCoverage >= 80 ? "emerald" : "amber"} /></span><span><span className={cn("flex h-7 w-7 items-center justify-center rounded-full border text-[9px] font-black", row.validationScore === 100 ? "border-emerald-300 text-emerald-700" : "border-amber-300 text-amber-700")}>{row.validationScore}</span></span><span><Badge tone={row.evidence.length ? "emerald" : "red"}>{row.evidence.length ? "Complete" : "Missing"}</Badge></span><span><Badge tone={statusTone(row.status)}>{row.status}</Badge></span><span className="flex items-center gap-1"><span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[7px] font-black text-white">{row.reviewer ? row.reviewer.full_name.split(" ").map((part) => part[0]).join("").slice(0, 2) : "—"}</span><span className="truncate">{row.reviewer?.full_name || "Unassigned"}</span></span><span className={cn("font-bold", ageLabel(row.testCase.updated_at).startsWith("0") ? "text-emerald-600" : "text-red-600")}>{ageLabel(row.testCase.updated_at)}</span><span>{shortDate(row.testCase.updated_at)}</span><span className="relative" onClick={(event) => event.stopPropagation()}><button aria-label={`Actions for ${row.testCase.test_case_id}`} onClick={() => setActionMenu(actionMenu === row.testCase.id ? null : row.testCase.id)} className="flex h-7 w-7 items-center justify-center rounded border border-slate-200"><MoreVertical className="h-3.5 w-3.5" /></button>{actionMenu === row.testCase.id && <div className="absolute right-0 top-8 z-30 w-36 rounded-md border border-slate-200 bg-white p-1 shadow-xl"><button onClick={() => { setSelectedId(row.testCase.id); setInspectorOpen(true); setActionMenu(null); }} className="w-full rounded px-2 py-1.5 text-left text-[9px] font-bold hover:bg-slate-50">Open review</button><button onClick={() => router.push(`/test-cases?project=${projectId}&view=editor&case=${row.testCase.id}`)} className="w-full rounded px-2 py-1.5 text-left text-[9px] font-bold hover:bg-slate-50">Open editor</button></div>}</span></div>) : <div className="p-8 text-center text-[10px] font-semibold text-slate-500">No test cases match the selected filters.</div>}
        </div></div>
        <div className="flex items-center justify-between px-3 py-2 text-[9px] font-semibold text-slate-500"><span>Showing {filtered.length ? (page - 1) * PAGE_SIZE + 1 : 0} to {Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length} test cases</span><div className="flex items-center gap-1"><button aria-label="Previous page" disabled={page === 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="flex h-7 w-7 items-center justify-center rounded border disabled:opacity-40"><ChevronLeft className="h-3.5 w-3.5" /></button><span className="flex h-7 min-w-7 items-center justify-center rounded bg-[#1b59f8] px-2 font-bold text-white">{page}</span><span>of {pageCount}</span><button aria-label="Next page" disabled={page === pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))} className="flex h-7 w-7 items-center justify-center rounded border disabled:opacity-40"><ChevronRight className="h-3.5 w-3.5" /></button><span className="ml-2 rounded border px-2 py-1.5">{PAGE_SIZE} / page</span></div></div>
      </section>
    </main>

    <Drawer open={inspectorOpen && !!selected} onOpenChange={setInspectorOpen}>
    <DrawerContent size="lg" className="bg-slate-50/70">
      {selected && <div className="flex-1 overflow-y-auto">
        <div className="sticky top-0 z-20 border-b border-slate-200 bg-white px-3 pt-3"><div className="flex items-start justify-between gap-2"><div><div className="flex items-center gap-2"><DrawerTitle className="text-sm text-slate-900">{selected.testCase.test_case_id}</DrawerTitle><Badge tone={statusTone(selected.status)}>{selected.status}</Badge></div><p className="mt-2 text-[11px] font-extrabold text-slate-800">{selected.testCase.title}</p></div><button aria-label="Close inspector" onClick={() => setInspectorOpen(false)}><X className="h-4 w-4 text-slate-500" /></button></div><div className="mt-3 flex gap-3 overflow-x-auto">{(["review", "traceability", "test-case", "evidence", "automation", "history", "activity"] as InspectorTab[]).map((item) => <button key={item} onClick={() => setInspectorTab(item)} className={cn("border-b-2 px-0.5 pb-2 text-[9px] font-extrabold capitalize", inspectorTab === item ? "border-[#1b59f8] text-[#1b59f8]" : "border-transparent text-slate-500")}>{item.replace("-", " ")}</button>)}</div></div>
        <div className="space-y-2 p-3">
          {inspectorTab === "review" && <ReviewInspector row={selected} history={history} approvals={approvals.filter((item) => item.entity_id === selected.testCase.id)} onTrace={() => setInspectorTab("traceability")} />}
          {inspectorTab === "traceability" && <TraceabilityInspector row={selected} projectId={projectId} router={router} />}
          {inspectorTab === "test-case" && <TestCaseInspector row={selected} onEdit={() => router.push(`/test-cases?project=${projectId}&view=editor&case=${selected.testCase.id}`)} />}
          {inspectorTab === "evidence" && <EvidenceInspector row={selected} />}
          {inspectorTab === "automation" && <ClassificationInspector row={selected} enabled={classificationsEnabled} canEvaluate={canEvaluateClassification} canReview={canReviewClassification} canApprove={canApproveClassification} onChanged={() => void loadData()} />}
          {inspectorTab === "history" && <HistoryInspector history={history} approvals={approvals.filter((item) => item.entity_id === selected.testCase.id)} users={userById} />}
          {inspectorTab === "activity" && <ActivityInspector row={selected} history={history} reviews={reviewHistory} approvals={approvals.filter((item) => item.entity_id === selected.testCase.id)} users={userById} />}

          <Panel title="Review Actions" className="border-amber-200 bg-amber-50/40">
            {selected.blockers.length > 0 && <div className="mb-2 rounded-md border border-red-200 bg-red-50 p-2 text-[9px] text-red-800"><div className="flex items-start gap-2 font-bold"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>Approval is blocked only by the current-stage requirement{selected.blockers.length === 1 ? "" : "s"} below.</span></div><ul className="mt-2 space-y-1 pl-5">{selected.blockers.map((item) => <li key={item.key} className="list-disc font-semibold"><strong>{item.label}:</strong> {item.guidance || item.detail}</li>)}</ul></div>}
            {selected.blockers.length === 0 && selected.checks.some((check) => check.scope === "downstream" && check.state !== "pass") && <div className="mb-2 rounded-md border border-blue-200 bg-blue-50 p-2 text-[9px] font-semibold text-blue-800"><strong>Ready for approval.</strong> Remaining journey, evidence, discovery, application, or automation items are tracked for later stages and do not disable this action.</div>}
            {decisionMode && <div className="mb-2 rounded-md border border-slate-200 bg-white p-2"><label className="text-[9px] font-extrabold text-slate-700">Reviewer comment (required)</label><textarea aria-label="Reviewer comment" value={comment} onChange={(event) => setComment(event.target.value)} className="mt-1 h-16 w-full resize-none rounded border border-slate-200 p-2 text-[10px]" /><div className="mt-2 flex gap-2"><Button onClick={() => void submitDecision()} disabled={!comment.trim() || Boolean(busy)} className={cn("h-8 flex-1 text-[9px] font-bold text-white", decisionMode === "reject" ? "bg-red-600" : "bg-amber-500")}>Confirm {decisionMode === "reject" ? "Rejection" : "Changes"}</Button><Button variant="outline" onClick={() => { setDecisionMode(null); setComment(""); }} className="h-8 text-[9px] font-bold">Cancel</Button></div></div>}
            {assigning && <div className="mb-2 rounded-md border border-slate-200 bg-white p-2"><select aria-label="Assigned reviewer" value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)} className="h-8 w-full rounded border border-slate-200 px-2 text-[9px]"><option value="">Select reviewer</option>{activeReviewerUsers.map((user) => <option key={user.id} value={user.id}>{user.full_name} · {activeMembershipByUser.get(user.id)?.role}</option>)}</select><div className="mt-2 flex gap-2"><Button onClick={() => void assignReviewer()} disabled={!assigneeId || Boolean(busy)} className="h-8 flex-1 bg-[#1b59f8] text-[9px] font-bold text-white">Save Assignment</Button><Button variant="outline" onClick={() => setAssigning(false)} className="h-8 text-[9px] font-bold">Cancel</Button></div></div>}
            <div className="grid grid-cols-1 gap-2 2xl:grid-cols-3"><Button onClick={() => void approveRows([selected])} disabled={selected.blockers.length > 0 || Boolean(busy) || !canApprove || selected.status === "Approved"} className="h-9 bg-emerald-500 text-[9px] font-bold text-white disabled:bg-slate-200"><ShieldCheck className="mr-1 h-3.5 w-3.5" />Approve Test Case</Button><Button variant="outline" onClick={() => setDecisionMode("changes")} className="h-9 border-amber-300 text-[9px] font-bold text-amber-700">Request Changes</Button><Button variant="outline" onClick={() => setDecisionMode("reject")} className="h-9 border-red-300 text-[9px] font-bold text-red-700">Reject Test Case</Button></div>
            <div className="mt-2 grid grid-cols-1 gap-2 2xl:grid-cols-3"><Button variant="outline" onClick={() => router.push(`/test-cases?project=${projectId}&view=editor&case=${selected.testCase.id}`)} className="h-9 text-[9px] font-bold"><ChevronLeft className="mr-1 h-3.5 w-3.5" />Send Back to Editor</Button><Button variant="outline" onClick={() => router.push(`/test-cases?project=${projectId}&view=journey-graph&journey=${encodeURIComponent(selected.journeyId)}&case=${selected.testCase.id}`)} className="h-9 text-[9px] font-bold"><GitBranch className="mr-1 h-3.5 w-3.5" />Journey Graph</Button><Button variant="outline" onClick={() => setAssigning(true)} className="h-9 text-[9px] font-bold"><UserRound className="mr-1 h-3.5 w-3.5" />Assign Reviewer</Button></div>
            <div className="mt-2 grid grid-cols-1 gap-2 2xl:grid-cols-3"><Button variant="outline" onClick={() => setInspectorTab("traceability")} className="h-9 text-[9px] font-bold"><Link2 className="mr-1 h-3.5 w-3.5" />View Full Trace</Button><Button variant="outline" onClick={() => setInspectorTab("activity")} className="h-9 text-[9px] font-bold"><History className="mr-1 h-3.5 w-3.5" />View Audit Log</Button><Button variant="outline" onClick={() => void exportSelected()} className="h-9 text-[9px] font-bold"><Download className="mr-1 h-3.5 w-3.5" />Export Test Case (.xlsx)</Button></div>
          </Panel>
        </div>
      </div>}
    </DrawerContent>
    </Drawer>
  </div>;
}

function FilterSelect({ label, value, setValue, options, optionValues, extra = [] }: { label: string; value: string; setValue: (value: string) => void; options: string[]; optionValues?: string[]; extra?: Array<{ value: string; label: string }> }) {
  return <select aria-label={label} value={value} onChange={(event) => setValue(event.target.value)} className="h-8 min-w-0 rounded-md border border-slate-200 bg-white px-2 text-[9px] font-semibold text-slate-600"><option value="all">{label}: All</option>{extra.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}{options.map((item, index) => <option key={`${item}-${index}`} value={optionValues?.[index] ?? item}>{item}</option>)}</select>;
}

function CheckList({ checks }: { checks: GovernanceCheck[] }) {
  return <div className="space-y-1.5">{checks.map((check) => <div key={check.key} className="flex items-start justify-between gap-2"><span className="flex min-w-0 items-start gap-2 text-[9px] font-semibold text-slate-600">{check.state === "pass" ? <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" /> : check.scope === "downstream" ? <Clock3 className="h-3.5 w-3.5 shrink-0 text-blue-500" /> : <AlertTriangle className={cn("h-3.5 w-3.5 shrink-0", check.state === "blocker" ? "text-red-500" : "text-amber-500")} />}<span>{check.label}{check.scope === "downstream" && check.state !== "pass" && <span className="ml-1 rounded bg-blue-50 px-1 py-0.5 text-[7px] font-extrabold text-blue-700">LATER</span>}</span></span><span className="max-w-[48%] text-right text-[8px] font-bold text-slate-500">{check.detail}</span></div>)}</div>;
}

function ReviewInspector({ row, history, approvals, onTrace }: { row: ApprovalRow; history: TestCaseHistory[]; approvals: ApprovalAction[]; onTrace: () => void }) {
  const approvalChecks = row.checks.filter((check) => check.scope === "approval");
  const approvalPassed = approvalChecks.filter((check) => check.state !== "blocker").length;
  const downstreamItems = row.checks.filter((check) => check.scope === "downstream" && check.state !== "pass");
  return <>
    <div className="grid grid-cols-4 gap-2 rounded-lg border border-slate-200 bg-white p-3 text-[9px]"><LabelValue label="Test case ID" value={row.testCase.test_case_id} /><LabelValue label="Current status" value={row.status} /><LabelValue label="Test type" value={row.testCase.test_type || "Unassigned"} /><LabelValue label="Priority" value={row.testCase.priority} /></div>
    <Panel title="What is required to approve" className={row.blockers.length ? "border-red-200 bg-red-50/40" : "border-emerald-200 bg-emerald-50/40"}>
      <p className={cn("text-[10px] font-extrabold", row.blockers.length ? "text-red-800" : "text-emerald-800")}>{row.blockers.length ? `${row.blockers.length} approval requirement${row.blockers.length === 1 ? "" : "s"} must be resolved.` : "All approval-stage requirements are satisfied."}</p>
      <p className="mt-1 text-[9px] font-semibold leading-4 text-slate-600">Approval validates test-case content, approved requirement/scenario traceability, applicable gating review, and reviewer permission. Journey, application, evidence, discovery, and automation preparation happen afterward.</p>
      {row.blockers.length > 0 && <div className="mt-3 space-y-2">{row.blockers.map((item) => <div key={item.key} className="rounded-md border border-red-100 bg-white p-2"><p className="text-[9px] font-extrabold text-red-800">{item.label}: {item.detail}</p><p className="mt-1 text-[8px] font-semibold leading-4 text-slate-600"><strong>Update in {item.owner || "the owning workspace"}:</strong> {item.guidance}</p></div>)}</div>}
      {downstreamItems.length > 0 && <div className="mt-3 rounded-md border border-blue-100 bg-blue-50 p-2"><p className="text-[9px] font-extrabold text-blue-800">Later-stage preparation — does not block approval</p><ul className="mt-1.5 space-y-1">{downstreamItems.map((item) => <li key={item.key} className="text-[8px] font-semibold leading-4 text-blue-900"><strong>{item.owner}:</strong> {item.guidance}</li>)}</ul></div>}
    </Panel>
    <div className="grid grid-cols-1 gap-2 2xl:grid-cols-3">
      <Panel title="Readiness Summary">
        <p className="text-lg font-black text-slate-900">{approvalPassed} / {approvalChecks.length}</p>
        <p className="mb-2 text-[8px] font-semibold text-slate-500">approval-stage gates satisfied</p>
        <Progress value={Math.round(approvalPassed / Math.max(1, approvalChecks.length) * 100)} />
        <div className="mt-3"><CheckList checks={row.checks} /></div>
      </Panel>
      <Panel title="Deterministic Validation">
        <div className={cn("flex items-center gap-2 text-sm font-black", row.validationScore === 100 ? "text-emerald-600" : "text-amber-600")}>
          {row.validationScore === 100 ? <ShieldCheck className="h-5 w-5" /> : <AlertTriangle className="h-5 w-5" />}
          {row.validationScore === 100 ? "Pass" : "Needs work"}
        </div>
        <p className="mt-3 text-[8px] font-semibold text-slate-500">Required-field completeness</p>
        <p className="mt-1 text-xl font-black text-slate-900">{row.validationScore} / 100</p>
        <button onClick={onTrace} className="mt-4 text-[9px] font-bold text-[#1b59f8]">View details</button>
      </Panel>
      <Panel
        title={`AI Scenario Test-Case Set Review${row.review ? ` (${row.review.review_mode === "gating" ? "Gating" : "Advisory"})` : ""}`}
        className="border-purple-100 bg-purple-50/30"
      >
        {row.review ? (
          <>
            <p className="text-[10px] font-extrabold text-purple-700">
              {row.review.verdict === "pass" ? "Pass" : row.review.verdict === "needs_revision" ? "Needs revision" : "Fail"}
            </p>
            <p className="mt-2 text-[9px] leading-4 text-slate-600">
              {row.review.findings?.[0]?.issue || "Persisted set-level review has no narrative finding."}
            </p>
            <p className="mt-3 text-[8px] font-semibold text-slate-500">Set-level score</p>
            <p className="mt-1 text-lg font-black text-purple-700">{reviewScoreLabel(row.review.overall_score)}</p>
            <p className="mt-2 text-[8px] font-semibold leading-4 text-slate-500">
              {row.review.review_mode === "gating"
                ? "Unresolved review findings can block approval."
                : "Findings are advisory improvements and do not block approval."}
            </p>
          </>
        ) : (
          <Empty>No persisted scenario test-case set review.</Empty>
        )}
      </Panel>
    </div>
    <Panel title="Reviewer, SLA & Approval Findings"><div className="grid grid-cols-3 gap-3"><LabelValue label="Assigned reviewer" value={row.reviewer?.full_name || "Unassigned"} /><LabelValue label="Review SLA / age" value={ageLabel(row.testCase.updated_at)} /><LabelValue label="Approval blockers" value={`${row.blockers.length} blocker${row.blockers.length === 1 ? "" : "s"}`} /></div>{row.blockers.length > 0 ? <ul className="mt-3 space-y-2">{row.blockers.map((item) => <li key={item.key} className="rounded-md border border-red-100 bg-red-50 p-2 text-[9px] font-semibold text-red-700"><strong>{item.label}:</strong> {item.detail}<span className="mt-1 block text-[8px] text-slate-600">{item.guidance}</span></li>)}</ul> : <p className="mt-3 rounded-md border border-emerald-100 bg-emerald-50 p-2 text-[9px] font-semibold text-emerald-700">No approval blockers. The reviewer can approve this test case now; later-stage items remain visible for downstream teams.</p>}</Panel>
    <Panel title="Traceability Snapshot" action={<button onClick={onTrace} className="text-[8px] font-bold text-[#1b59f8]">View full trace</button>}><div className="grid grid-cols-2 gap-2 2xl:grid-cols-6"><LabelValue label="Requirement" value={row.requirement?.requirement_id || "Unlinked"} /><LabelValue label="PPM ID" value={ppmId(row.requirement)} /><LabelValue label="Scenario" value={row.scenario?.scenario_id || "Unlinked"} /><LabelValue label="Journey" value={row.journeyId} /><LabelValue label="Application" value={row.application?.name || "Missing"} /><LabelValue label="Discovery" value={row.discovery} /></div></Panel>
    <div className="grid grid-cols-1 gap-2 2xl:grid-cols-3"><Panel title="Test Case Preview"><p className="text-[8px] font-semibold text-slate-500">Preconditions</p><p className="mt-1 text-[9px] font-bold text-slate-800">{row.testCase.preconditions?.length || 0} recorded</p><p className="mt-2 text-[8px] font-semibold text-slate-500">Test steps</p><p className="mt-1 text-[9px] font-bold text-slate-800">{row.testCase.steps?.length || 0} ordered steps</p><p className="mt-2 text-[8px] font-semibold text-slate-500">Expected result</p><p className="mt-1 line-clamp-2 text-[9px] font-semibold text-slate-700">{row.testCase.expected_result || "Missing"}</p></Panel><Panel title="Evidence Summary"><p className="text-[8px] font-semibold text-slate-500">Required evidence</p><div className="mt-2 flex flex-wrap gap-1">{row.evidence.map((item) => <Badge key={item} tone="blue">{item}</Badge>)}{!row.evidence.length && <Badge tone="red">Missing</Badge>}</div><p className="mt-3 text-[8px] font-semibold text-slate-500">Latest execution evidence</p><p className="mt-1 text-[9px] font-bold text-slate-800">{row.testCase.latest_evidence_available ? "Available" : "Not available"}</p></Panel><Panel title="History / Activity"><p className="text-[9px] font-bold text-slate-800">{history.length} editor change{history.length === 1 ? "" : "s"}</p><p className="mt-2 text-[9px] font-bold text-slate-800">{approvals.length} approval action{approvals.length === 1 ? "" : "s"}</p><p className="mt-2 text-[8px] font-semibold text-slate-500">Latest activity</p><p className="mt-1 text-[9px] font-semibold text-slate-700">{shortDate(history[0]?.created_at || approvals[0]?.created_at || row.testCase.updated_at)}</p></Panel></div>
  </>;
}

function TraceabilityInspector({ row, projectId, router }: { row: ApprovalRow; projectId: number; router: ReturnType<typeof useRouter> }) {
  return <><Panel title="Requirement"><LabelValue label="Requirement ID" value={row.requirement?.requirement_id || "Unlinked"} /><div className="mt-2"><LabelValue label="PPM ID" value={ppmId(row.requirement)} /></div><p className="mt-2 text-[9px] font-semibold text-slate-700">{row.requirement?.title || "No linked requirement title"}</p></Panel><Panel title="Scenario"><LabelValue label="Scenario ID" value={row.scenario?.scenario_id || "Unlinked"} /><div className="mt-2"><LabelValue label="Scenario class" value={scenarioClass(row.scenario, row.testCase)} /></div><p className="mt-2 text-[9px] font-semibold text-slate-700">{row.scenario?.title || "No linked scenario title"}</p></Panel><Panel title="Journey"><div className="grid grid-cols-2 gap-2"><LabelValue label="Journey ID" value={row.journeyId} /><LabelValue label="Journey name" value={row.journeyName} /></div><div className="mt-3"><Progress value={row.journeyCoverage} tone={row.journeyCoverage >= 80 ? "emerald" : "amber"} /></div><p className="mt-1 text-[8px] font-semibold text-slate-500">{row.journeyCoverage}% required scenario-class coverage</p></Panel><Panel title="Application & Discovery"><div className="grid grid-cols-2 gap-2"><LabelValue label="Application mapping" value={row.application?.name || "Missing"} /><LabelValue label="Discovery eligibility" value={row.discovery} /></div></Panel><Button variant="outline" onClick={() => router.push(`/requirements?project=${projectId}&view=traceability&requirement=${row.requirement?.id || ""}`)} disabled={!row.requirement} className="h-9 w-full gap-2 text-[9px] font-bold"><ExternalLink className="h-3.5 w-3.5" />Open Requirement Traceability</Button></>;
}

function TestCaseInspector({ row, onEdit }: { row: ApprovalRow; onEdit: () => void }) {
  return <><Panel title="Preconditions">{row.testCase.preconditions?.length ? <ol className="list-decimal space-y-1 pl-4 text-[9px] font-semibold text-slate-700">{row.testCase.preconditions.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ol> : <Empty>No preconditions recorded.</Empty>}</Panel><Panel title="Ordered Test Steps">{row.testCase.steps?.length ? <div className="overflow-hidden rounded border border-slate-200"><div className="grid grid-cols-[28px_1fr_1fr] bg-slate-50 p-2 text-[8px] font-extrabold uppercase text-slate-500"><span>#</span><span>Action</span><span>Expected result</span></div>{row.testCase.steps.map((step, index) => <div key={`${step.step_number}-${index}`} className="grid grid-cols-[28px_1fr_1fr] border-t border-slate-100 p-2 text-[9px] font-semibold text-slate-700"><span>{step.step_number}</span><span>{step.action || "Missing"}</span><span>{step.expected_result || "Missing"}</span></div>)}</div> : <Empty>No test steps recorded.</Empty>}</Panel><Panel title="Test Data & Expected Result"><pre className="max-h-28 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-[8px] text-slate-700">{row.testCase.test_data && Object.keys(row.testCase.test_data).length ? JSON.stringify(row.testCase.test_data, null, 2) : "No test data reference recorded."}</pre><p className="mt-2 text-[9px] font-semibold text-slate-700">{row.testCase.expected_result || "No overall expected result recorded."}</p></Panel><Panel title="Classification"><div className="grid grid-cols-4 gap-2"><LabelValue label="Priority" value={row.testCase.priority} /><LabelValue label="Severity" value={row.testCase.severity} /><LabelValue label="Test type" value={row.testCase.test_type || "Unassigned"} /><LabelValue label="Automation" value={row.testCase.automation_candidate ? "Candidate" : "Manual"} /></div></Panel><Panel title="Validation Findings"><CheckList checks={row.checks.filter((item) => ["validation", "requirement", "scenario"].includes(item.key))} /></Panel><Button onClick={onEdit} className="h-9 w-full bg-[#1b59f8] text-[9px] font-bold text-white">Open Test Case Editor</Button></>;
}

function EvidenceInspector({ row }: { row: ApprovalRow }) {
  const dependencies = metadataStrings(row.testCase.metadata_, "evidence_dependencies");
  const owner = metadataString(row.testCase.metadata_, "evidence_owner");
  return <><Panel title="Required Evidence Types">{row.evidence.length ? <div className="flex flex-wrap gap-2">{row.evidence.map((item) => <Badge key={item} tone="purple">{item}</Badge>)}</div> : <Empty>No evidence policy is defined yet. This is tracked for execution preparation and does not block test-case approval.</Empty>}</Panel><Panel title="Evidence Policy Status"><CheckList checks={[row.checks.find((item) => item.key === "evidence")!]} /></Panel><Panel title="When to complete it">{row.evidence.length ? <p className="text-[9px] font-semibold text-emerald-700">Evidence types are already declared.</p> : <p className="text-[9px] font-semibold leading-4 text-blue-700">Before execution, define the required screenshots, logs, traces, or audit records in execution preparation. Actual evidence is captured during execution.</p>}</Panel><Panel title="Execution / Application Dependencies">{dependencies.length ? <ul className="list-disc space-y-1 pl-4 text-[9px] font-semibold text-slate-700">{dependencies.map((item) => <li key={item}>{item}</li>)}</ul> : <Empty>No persisted evidence dependency recorded.</Empty>}</Panel><Panel title="Evidence Owner"><LabelValue label="Owner" value={owner || "Execution preparation team"}/></Panel></>;
}

const CLASSIFICATION_DECISIONS: Array<{ key: "approve" | "approve_conditional" | "not_recommended" | "defer" | "request_changes"; label: string; reasonRequired: boolean; tone: string }> = [
  { key: "approve", label: "Approve Automation Classification", reasonRequired: false, tone: "bg-emerald-500 text-white" },
  { key: "approve_conditional", label: "Approve as Conditional", reasonRequired: true, tone: "border-amber-300 text-amber-700" },
  { key: "not_recommended", label: "Mark Not Recommended", reasonRequired: true, tone: "border-red-300 text-red-700" },
  { key: "defer", label: "Defer", reasonRequired: true, tone: "border-slate-300 text-slate-700" },
  { key: "request_changes", label: "Request Changes", reasonRequired: true, tone: "border-blue-300 text-blue-700" },
];

function ClassificationInspector({ row, enabled, canEvaluate, canApprove, onChanged }: { row: ApprovalRow; enabled: boolean; canEvaluate: boolean; canReview: boolean; canApprove: boolean; onChanged: () => void }) {
  const { runAIAction } = useAIAction();
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [decisionKey, setDecisionKey] = useState<typeof CLASSIFICATION_DECISIONS[number]["key"] | null>(null);
  const [reason, setReason] = useState("");
  const classification = row.classification;
  const projectId = row.testCase.project_id;

  async function runEvaluate() {
    if (!projectId) return;
    setBusy("evaluate"); setError("");
    try {
      await runAIAction({
        actionName: "classify_automation_eligibility",
        title: "Classifying Automation Eligibility",
        module: "Test Case Approval",
        artifactType: "Automation Classification",
        projectId,
        testCaseId: row.testCase.test_case_id,
        stages: AI_PROCESSING_STAGES.automationClassification,
        successMessage: "Automation classification was queued.",
        execute: () => automationClassificationApi.evaluate(projectId, [row.testCase.id]),
      });
      onChanged();
    } catch (evalError) { setError(errorMessage(evalError, "Could not queue classification.")); }
    finally { setBusy(""); }
  }

  async function runReclassify() {
    if (!classification) return;
    setBusy("reclassify"); setError("");
    try {
      await runAIAction({
        actionName: "reclassify_automation_eligibility",
        title: "Reclassifying Automation Eligibility",
        module: "Test Case Approval",
        artifactType: "Automation Classification",
        projectId,
        testCaseId: row.testCase.test_case_id,
        stages: AI_PROCESSING_STAGES.automationClassification,
        successMessage: "Automation reclassification was queued.",
        execute: () => automationClassificationApi.reclassify(classification.id),
      });
      onChanged();
    } catch (evalError) { setError(errorMessage(evalError, "Could not queue reclassification.")); }
    finally { setBusy(""); }
  }

  async function submitDecision(key: typeof CLASSIFICATION_DECISIONS[number]["key"]) {
    if (!classification) return;
    setBusy(key); setError("");
    try {
      if (key === "approve") await automationClassificationApi.approve(classification.id, reason.trim() || undefined);
      else if (key === "approve_conditional") await automationClassificationApi.approveConditional(classification.id, reason.trim());
      else if (key === "not_recommended") await automationClassificationApi.reject(classification.id, reason.trim());
      else if (key === "defer") await automationClassificationApi.defer(classification.id, reason.trim());
      else await automationClassificationApi.requestChanges(classification.id, reason.trim());
      setDecisionKey(null); setReason(""); onChanged();
    } catch (decisionError) { setError(errorMessage(decisionError, "Could not record the classification decision.")); }
    finally { setBusy(""); }
  }

  if (!enabled) return <Empty>Automation classification is not enabled for this project.</Empty>;
  if (!row.testCase.automation_candidate) return <Empty>This test case is not marked as an automation candidate — classification is not applicable.</Empty>;

  return <>
    {error && <div role="alert" className="flex items-center justify-between rounded-md border border-red-200 bg-red-50 px-3 py-2 text-[10px] font-bold text-red-700"><span className="flex items-center gap-2"><AlertTriangle className="h-3.5 w-3.5" />{error}</span><button aria-label="Dismiss error" onClick={() => setError("")}><X className="h-3.5 w-3.5" /></button></div>}

    {!classification ? <Panel title="Automation Classification"><Empty>This test case has not been classified yet.</Empty>{canEvaluate && <Button onClick={() => void runEvaluate()} disabled={Boolean(busy)} className="mt-2 h-9 w-full bg-[#1b59f8] text-[9px] font-bold text-white"><Bot className="mr-1 h-3.5 w-3.5" />Classify Now</Button>}</Panel> : <>
      <div className="grid grid-cols-4 gap-2 rounded-lg border border-slate-200 bg-white p-3 text-[9px]">
        <LabelValue label="Candidate status" value={classification.candidate_status} />
        <LabelValue label="Review status" value={classification.review_status.replace(/_/g, " ")} />
        <LabelValue label="Policy" value={`v${classification.policy_version ?? "—"}`} />
        <LabelValue label="Classification version" value={`v${classification.version}${classification.is_stale ? " (stale)" : ""}`} />
      </div>

      <div className="grid grid-cols-1 gap-2 2xl:grid-cols-2">
        <Panel title="Recommended Automation Route">
          <LabelValue label="Primary adapter" value={classification.primary_adapter || "Not resolved"} />
          <div className="mt-2"><LabelValue label="Supporting adapters" value={classification.supporting_adapters.length ? classification.supporting_adapters.join(", ") : "None"} /></div>
          <div className="mt-2"><LabelValue label="Discovery required" value={classification.discovery_required ? `Yes · ${classification.recommended_discovery_mode || "mode not set"}` : "No"} /></div>
        </Panel>
        <Panel title="Complexity & Automation Value">
          <div className="grid grid-cols-2 gap-3"><div><p className="text-[8px] font-semibold text-slate-500">Complexity</p><p className="mt-1 text-lg font-black text-slate-900">{classification.complexity_score ?? "—"}</p></div><div><p className="text-[8px] font-semibold text-slate-500">Automation value</p><p className="mt-1 text-lg font-black text-slate-900">{classification.automation_value_score ?? "—"}</p></div></div>
        </Panel>
      </div>

      <Panel title="Mandatory & Optional Validators">
        <div className="flex flex-wrap gap-1">{classification.mandatory_validators.map((item) => <Badge key={item} tone="red">{item}</Badge>)}{classification.optional_validators.map((item) => <Badge key={item} tone="blue">{item}</Badge>)}{!classification.mandatory_validators.length && !classification.optional_validators.length && <Badge tone="slate">None declared</Badge>}</div>
      </Panel>

      <Panel title="Deterministic Blockers">{classification.deterministic_blockers.length ? <ul className="list-disc space-y-1 pl-4 text-[9px] font-semibold text-red-600">{classification.deterministic_blockers.map((item, index) => <li key={`${item.code}-${index}`}>{item.label}: {item.detail}</li>)}</ul> : <p className="text-[9px] font-semibold text-emerald-700">No deterministic blockers.</p>}</Panel>

      <Panel title="Required Evidence">
        <div className="flex flex-wrap gap-1">{classification.required_evidence.length ? classification.required_evidence.map((item) => <Badge key={item} tone="purple">{item}</Badge>) : <Badge tone="slate">None declared</Badge>}</div>
      </Panel>

      {canEvaluate && <div><Button variant="outline" onClick={() => void runReclassify()} disabled={Boolean(busy)} className="h-8 gap-1.5 text-[9px] font-bold"><RefreshCw className={cn("h-3.5 w-3.5", busy === "reclassify" && "animate-spin")} />Reclassify</Button></div>}

      {canApprove && <Panel title="Classification Decision" className="border-amber-200 bg-amber-50/40">
        {decisionKey && <div className="mb-2 rounded-md border border-slate-200 bg-white p-2"><label className="text-[9px] font-extrabold text-slate-700">Reason {CLASSIFICATION_DECISIONS.find((item) => item.key === decisionKey)?.reasonRequired ? "(required)" : "(optional)"}</label><textarea aria-label="Classification decision reason" value={reason} onChange={(event) => setReason(event.target.value)} className="mt-1 h-16 w-full resize-none rounded border border-slate-200 p-2 text-[10px]" /><div className="mt-2 flex gap-2"><Button onClick={() => void submitDecision(decisionKey)} disabled={Boolean(busy) || (CLASSIFICATION_DECISIONS.find((item) => item.key === decisionKey)?.reasonRequired && !reason.trim())} className="h-8 flex-1 bg-[#1b59f8] text-[9px] font-bold text-white">Confirm</Button><Button variant="outline" onClick={() => { setDecisionKey(null); setReason(""); }} className="h-8 text-[9px] font-bold">Cancel</Button></div></div>}
        <div className="grid grid-cols-1 gap-2 2xl:grid-cols-3">{CLASSIFICATION_DECISIONS.map((item) => <Button key={item.key} variant={item.key === "approve" ? "default" : "outline"} onClick={() => setDecisionKey(item.key)} disabled={Boolean(busy) || classification.review_status === "APPROVED"} className={cn("h-9 text-[9px] font-bold", item.tone)}>{item.label}</Button>)}</div>
      </Panel>}
    </>}
  </>;
}

function HistoryInspector({ history, approvals, users }: { history: TestCaseHistory[]; approvals: ApprovalAction[]; users: Map<number, UserAccount> }) {
  const entries = [...history.map((item) => ({ id: `h-${item.id}`, at: item.created_at, actor: item.changed_by ? users.get(item.changed_by)?.full_name || `User ${item.changed_by}` : item.source, title: `${item.field_name} changed`, detail: `${item.old_value ?? "—"} → ${item.new_value ?? "—"}`, comment: item.comment })), ...approvals.map((item) => ({ id: `a-${item.id}`, at: item.created_at, actor: users.get(item.user_id)?.full_name || `User ${item.user_id}`, title: item.action_type.replace(/_/g, " "), detail: item.decision.replace(/_/g, " "), comment: item.notes }))].sort((a, b) => b.at.localeCompare(a.at));
  return <Panel title="Immutable Change & Review History">{entries.length ? <Timeline entries={entries} /> : <Empty>No change or approval history has been recorded.</Empty>}</Panel>;
}

function ActivityInspector({ row, history, reviews, approvals, users }: { row: ApprovalRow; history: TestCaseHistory[]; reviews: ArtifactReview[]; approvals: ApprovalAction[]; users: Map<number, UserAccount> }) {
  const entries = [{ id: "generated", at: row.testCase.created_at, actor: row.testCase.created_by ? users.get(row.testCase.created_by)?.full_name || `User ${row.testCase.created_by}` : "Generation service", title: "Test case generated", detail: row.testCase.test_case_id, comment: null }, ...history.map((item) => ({ id: `h-${item.id}`, at: item.created_at, actor: item.changed_by ? users.get(item.changed_by)?.full_name || `User ${item.changed_by}` : item.source, title: `${item.field_name} updated`, detail: item.source, comment: item.comment })), ...reviews.map((item) => ({ id: `r-${item.id}`, at: item.created_at, actor: item.reviewer_agent, title: "Scenario test-case set review", detail: `${item.verdict.replace("_", " ")} · ${reviewScoreLabel(item.overall_score)} · ${item.review_mode}`, comment: item.findings?.[0]?.issue || null })), ...approvals.map((item) => ({ id: `a-${item.id}`, at: item.created_at, actor: users.get(item.user_id)?.full_name || `User ${item.user_id}`, title: "Approval action", detail: item.decision, comment: item.notes }))].sort((a, b) => b.at.localeCompare(a.at));
  return <Panel title="Activity & Audit Log"><Timeline entries={entries} /></Panel>;
}

function Timeline({ entries }: { entries: Array<{ id: string; at: string; actor: string; title: string; detail: string; comment?: string | null }> }) {
  return <div className="space-y-3">{entries.map((entry) => <div key={entry.id} className="relative border-l-2 border-blue-100 pl-4 before:absolute before:-left-[5px] before:top-1 before:h-2 before:w-2 before:rounded-full before:bg-blue-600"><p className="text-[8px] font-bold text-slate-500">{dateTime(entry.at)}</p><p className="mt-1 text-[9px] font-extrabold text-slate-800">{entry.title} · {entry.actor}</p><p className="mt-0.5 text-[9px] font-semibold text-slate-600">{entry.detail}</p>{entry.comment && <p className="mt-1 rounded bg-slate-50 p-1.5 text-[8px] font-semibold text-slate-500">{entry.comment}</p>}</div>)}</div>;
}

function LabelValue({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="min-w-0"><p className="text-[8px] font-semibold text-slate-400">{label}</p><p className="mt-1 break-words text-[9px] font-extrabold text-slate-800">{value}</p></div>;
}
