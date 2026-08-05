"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  AppWindow,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  Download,
  ExternalLink,
  FileCheck2,
  FileText,
  Filter,
  GitBranch,
  Layers3,
  Link2,
  Loader2,
  Maximize2,
  MoreVertical,
  Network,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  TestTube2,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import {
  applicationsApi,
  automationApi,
  automationClassificationApi,
  isClassificationDisabled,
  requirementsApi,
  reviewsApi,
  scenariosApi,
  testCasesApi,
  testPlansApi,
  traceabilityApi,
  type ApprovalAction,
  type ArtifactReview,
  type ProjectApplication,
  type Requirement,
  type TestCase,
  type TestCaseAutomationClassification,
  type TestScenario,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerBody } from "@/components/ui/drawer";
import { cn } from "@/lib/utils";
import { useAIAction } from "@/hooks/useAIAction";
import { AI_PROCESSING_STAGES } from "@/lib/ai-processing-stages";

type ScenarioKind = "positive" | "negative" | "boundary" | "recovery" | "regression" | "other";
type InspectorTab = "overview" | "coverage" | "applications" | "evidence" | "automation" | "activity";
type NodeType = "requirement" | "journey" | "scenario" | "test_case" | "application" | "evidence" | "gap";
type Severity = "high" | "medium" | "low" | "info";

type GraphGap = {
  id: string;
  label: string;
  detail: string;
  severity: Severity;
  kind: string;
};

type JourneyRecord = {
  id: string;
  name: string;
  requirements: Requirement[];
  scenarios: TestScenario[];
  testCases: TestCase[];
  applications: ProjectApplication[];
  gaps: GraphGap[];
  coverage: number;
  evidenceCoverage: number;
  applicationCoverage: number;
  approvalReadiness: number;
  ownerId?: number;
  updatedAt?: string;
};

type SelectedNode = {
  type: NodeType;
  id: string;
  label: string;
  raw?: Requirement | TestScenario | TestCase | ProjectApplication | GraphGap | JourneyRecord;
};

type Props = { projectId: number | null };

const REQUIRED_SCENARIO_KINDS: ScenarioKind[] = ["positive", "negative", "boundary", "recovery"];
const GRAPH_SCENARIO_KINDS: ScenarioKind[] = [...REQUIRED_SCENARIO_KINDS, "regression", "other"];

const NODE_TONES: Record<NodeType, string> = {
  requirement: "border-slate-200 bg-white text-slate-800",
  journey: "border-blue-400 bg-blue-50 text-blue-900 shadow-sm shadow-blue-100",
  scenario: "border-emerald-200 bg-emerald-50/50 text-slate-800",
  test_case: "border-emerald-200 bg-white text-slate-800",
  application: "border-cyan-200 bg-cyan-50/40 text-slate-800",
  evidence: "border-violet-200 bg-violet-50/40 text-slate-800",
  gap: "border-red-300 bg-red-50/70 text-red-800",
};

function normal(value?: string | null) {
  return (value || "").trim().toLowerCase().replace(/[_-]+/g, " ");
}

function percent(part: number, total: number) {
  return total > 0 ? Math.round((part / total) * 100) : 0;
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
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string" && Boolean(item.trim()));
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

function ppmId(requirement?: Requirement) {
  return metadataString(requirement?.metadata_, "ppm_id", "ppmId") || "Not assigned";
}

function scenarioKind(scenario: TestScenario): ScenarioKind {
  const value = normal(scenario.scenario_type || scenario.title);
  if (value.includes("positive") || value.includes("happy")) return "positive";
  if (value.includes("negative") || value.includes("error") || value.includes("failure")) return "negative";
  if (value.includes("boundary") || value.includes("edge")) return "boundary";
  if (value.includes("recovery") || value.includes("recover")) return "recovery";
  if (value.includes("regression")) return "regression";
  return "other";
}

function evidenceRequirements(testCase: TestCase) {
  return metadataStrings(testCase.metadata_, "evidence_requirements");
}

function hasDiscoveryCheck(testCase: TestCase) {
  const status = normal(metadataString(testCase.metadata_, "discovery_status", "discovery_eligibility"));
  return ["complete", "completed", "eligible", "passed", "ready", "ineligible", "blocked"].includes(status);
}

function displayDate(value?: string | null) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function errorMessage(error: unknown, fallback: string) {
  const candidate = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = candidate.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return candidate.message || fallback;
}

function journeySource(requirement: Requirement) {
  const journeyId = metadataString(requirement.metadata_, "journey_id", "journeyId");
  const journeyName = metadataString(requirement.metadata_, "journey_name", "journeyName", "business_journey");
  const name = journeyName || requirement.business_process || requirement.title;
  return { journeyId, name, key: journeyId || normal(name) || requirement.requirement_id };
}

function deriveJourneys(
  requirements: Requirement[],
  scenarios: TestScenario[],
  testCases: TestCase[],
  applications: ProjectApplication[],
) {
  const groups = new Map<string, { name: string; explicitId: string; requirements: Requirement[] }>();
  for (const requirement of [...requirements].sort((a, b) => a.requirement_id.localeCompare(b.requirement_id))) {
    const source = journeySource(requirement);
    const group = groups.get(source.key) || { name: source.name, explicitId: source.journeyId, requirements: [] };
    group.requirements.push(requirement);
    groups.set(source.key, group);
  }
  const applicationById = new Map(applications.filter((app) => app.id != null).map((app) => [Number(app.id), app]));
  return Array.from(groups.values()).map((group, index): JourneyRecord => {
    const requirementIds = new Set(group.requirements.map((item) => item.id));
    const journeyScenarios = scenarios.filter((item) => item.requirement_id != null && requirementIds.has(item.requirement_id));
    const scenarioIds = new Set(journeyScenarios.map((item) => item.id));
    const journeyCases = testCases.filter((item) =>
      (item.requirement_id != null && requirementIds.has(item.requirement_id)) ||
      (item.linked_requirement_id != null && requirementIds.has(item.linked_requirement_id)) ||
      (item.scenario_id != null && scenarioIds.has(item.scenario_id)) ||
      (item.linked_scenario_id != null && scenarioIds.has(item.linked_scenario_id)),
    );
    const mappedApps = Array.from(new Set(journeyCases.map((item) => item.application_id).filter((id): id is number => typeof id === "number")))
      .map((id) => applicationById.get(id))
      .filter((item): item is ProjectApplication => Boolean(item));
    const presentKinds = new Set(journeyScenarios.map(scenarioKind));
    const gaps: GraphGap[] = [];
    for (const kind of REQUIRED_SCENARIO_KINDS) {
      if (!presentKinds.has(kind)) {
        gaps.push({
          id: `missing-${kind}`,
          kind: `missing_${kind}_scenario`,
          label: `Missing ${kind[0].toUpperCase()}${kind.slice(1)} Scenario`,
          detail: `No ${kind} scenario is linked to this journey.`,
          severity: kind === "boundary" ? "medium" : "high",
        });
      }
    }
    if (journeyCases.length === 0) {
      gaps.push({ id: "missing-test-cases", kind: "missing_test_case", label: "Missing Test Cases", detail: "No test case is linked to the journey scenarios.", severity: "high" });
    }
    const mappedCaseCount = journeyCases.filter((item) => item.application_id != null && applicationById.has(item.application_id)).length;
    if (journeyCases.length > 0 && mappedCaseCount < journeyCases.length) {
      gaps.push({ id: "missing-application", kind: "missing_application_mapping", label: "Ambiguous Application Mapping", detail: `${journeyCases.length - mappedCaseCount} test case(s) do not have an active project application mapping.`, severity: "medium" });
    }
    const evidenceCaseCount = journeyCases.filter((item) => evidenceRequirements(item).length > 0).length;
    if (journeyCases.length > 0 && evidenceCaseCount < journeyCases.length) {
      gaps.push({ id: "missing-evidence", kind: "missing_evidence_requirement", label: "Missing Evidence Requirement", detail: `${journeyCases.length - evidenceCaseCount} test case(s) have no saved evidence requirement.`, severity: "medium" });
    }
    const automationCandidates = journeyCases.filter((item) => item.automation_candidate || item.automation_eligible === "yes");
    const discoveryChecked = automationCandidates.filter(hasDiscoveryCheck).length;
    if (automationCandidates.length > 0 && discoveryChecked < automationCandidates.length) {
      gaps.push({ id: "discovery-unchecked", kind: "discovery_not_checked", label: "Discovery Eligibility Pending", detail: `${automationCandidates.length - discoveryChecked} automation candidate(s) have not completed discovery eligibility review.`, severity: "medium" });
    }
    const scenarioCoverage = percent(REQUIRED_SCENARIO_KINDS.filter((kind) => presentKinds.has(kind)).length, REQUIRED_SCENARIO_KINDS.length);
    const evidenceCoverage = percent(evidenceCaseCount, journeyCases.length);
    const applicationCoverage = percent(mappedCaseCount, journeyCases.length);
    const validatedCases = journeyCases.filter((item) => !["draft", "generated"].includes(normal(item.status))).length;
    const validationCoverage = percent(validatedCases, journeyCases.length);
    const approvalReadiness = Math.round((scenarioCoverage + evidenceCoverage + applicationCoverage + validationCoverage) / 4);
    const updatedAt = [...group.requirements.map((item) => item.updated_at), ...journeyScenarios.map((item) => item.updated_at || item.created_at), ...journeyCases.map((item) => item.updated_at)]
      .filter(Boolean)
      .sort()
      .at(-1);
    return {
      id: group.explicitId || `JRN-${String(index + 1).padStart(3, "0")}`,
      name: group.name,
      requirements: group.requirements,
      scenarios: journeyScenarios,
      testCases: journeyCases,
      applications: mappedApps,
      gaps,
      coverage: scenarioCoverage,
      evidenceCoverage,
      applicationCoverage,
      approvalReadiness,
      ownerId: group.requirements[0]?.updated_by || group.requirements[0]?.created_by,
      updatedAt,
    };
  });
}

export function JourneyGraphView({ projectId }: Props) {
  const { runAIAction } = useAIAction();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [scenarios, setScenarios] = useState<TestScenario[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [applications, setApplications] = useState<ProjectApplication[]>([]);
  const [availableEnvironments, setAvailableEnvironments] = useState<string[]>([]);
  const [reviews, setReviews] = useState<ArtifactReview[]>([]);
  const [approvals, setApprovals] = useState<ApprovalAction[]>([]);
  const [classifications, setClassifications] = useState<TestCaseAutomationClassification[]>([]);
  const [classificationsEnabled, setClassificationsEnabled] = useState(true);
  const [selectedJourneyId, setSelectedJourneyId] = useState("");
  const [selectedNode, setSelectedNode] = useState<SelectedNode | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("overview");
  const [query, setQuery] = useState("");
  const [graphQuery, setGraphQuery] = useState("");
  const [domainFilter, setDomainFilter] = useState("all");
  const [journeyFilter, setJourneyFilter] = useState("all");
  const [scenarioFilter, setScenarioFilter] = useState("all");
  const [applicationFilter, setApplicationFilter] = useState("all");
  const [coverageFilter, setCoverageFilter] = useState("all");
  const [approvalFilter, setApprovalFilter] = useState("all");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [graphOptionsOpen, setGraphOptionsOpen] = useState(false);
  const [showGapsOnly, setShowGapsOnly] = useState(false);
  const [showEvidenceLinks, setShowEvidenceLinks] = useState(true);
  const [showApplicationLinks, setShowApplicationLinks] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [evidenceFormOpen, setEvidenceFormOpen] = useState(false);
  const [evidenceText, setEvidenceText] = useState("");
  const [mappingFormOpen, setMappingFormOpen] = useState(false);
  const [applicationId, setApplicationId] = useState("");
  const [environment, setEnvironment] = useState("QA");
  const [linkFormOpen, setLinkFormOpen] = useState(false);
  const [linkCaseId, setLinkCaseId] = useState("");
  const [linkScenarioId, setLinkScenarioId] = useState("");

  const loadData = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const [requirementResult, scenarioResult, caseResult, applicationResult, reviewResult, approvalResult] = await Promise.all([
        requirementsApi.list(projectId, { status: "approved", limit: 200 }),
        scenariosApi.list(projectId),
        testCasesApi.list(projectId),
        applicationsApi.getForProject(projectId),
        reviewsApi.listForProject(projectId),
        traceabilityApi.approvals(projectId, { page_size: 200 }),
      ]);
      setRequirements(requirementResult.data);
      setScenarios(scenarioResult.data);
      setTestCases(caseResult.data);
      setApplications(applicationResult.data.applications.filter((item) => item.is_active));
      setAvailableEnvironments(applicationResult.data.available_environments);
      setReviews(reviewResult.data);
      setApprovals(approvalResult.data);
      const environments = applicationResult.data.available_environments;
      if (environments.length && !environments.includes(environment)) setEnvironment(environments[0]);
      setLastRefreshed(new Date());
    } catch (loadError) {
      setError(errorMessage(loadError, "Could not load the journey graph from the project records."));
    } finally {
      setLoading(false);
    }

    // Loaded separately so classification failures do not hide the journey
    // is off and must not break the rest of the (already working) graph.
    try {
      const clsRes = await automationClassificationApi.listForProject(projectId);
      setClassifications(clsRes.data);
      setClassificationsEnabled(true);
    } catch (clsError) {
      setClassifications([]);
      setClassificationsEnabled(!isClassificationDisabled(clsError));
    }
  }, [environment, projectId]);

  useEffect(() => { void loadData(); }, [loadData]);

  const classificationByTestCaseId = useMemo(
    () => new Map(classifications.map((item) => [item.test_case_id, item])),
    [classifications],
  );

  const journeys = useMemo(() => deriveJourneys(requirements, scenarios, testCases, applications), [applications, requirements, scenarios, testCases]);

  useEffect(() => {
    if (!journeys.length) {
      setSelectedJourneyId("");
      setSelectedNode(null);
      return;
    }
    const requestedJourney = searchParams.get("journey");
    if (requestedJourney && journeys.some((item) => item.id === requestedJourney)) {
      if (selectedJourneyId !== requestedJourney) setSelectedJourneyId(requestedJourney);
      return;
    }
    if (!journeys.some((item) => item.id === selectedJourneyId)) setSelectedJourneyId(journeys[0].id);
  }, [journeys, searchParams, selectedJourneyId]);

  const selectedJourney = journeys.find((item) => item.id === selectedJourneyId) || journeys[0];

  useEffect(() => {
    if (!selectedJourney) return;
    setSelectedNode((current) => current && current.type !== "journey" ? current : { type: "journey", id: selectedJourney.id, label: selectedJourney.name, raw: selectedJourney });
    setApplicationId(selectedJourney.applications[0]?.id != null ? String(selectedJourney.applications[0].id) : applications[0]?.id != null ? String(applications[0].id) : "");
    setLinkScenarioId(selectedJourney.scenarios[0] ? String(selectedJourney.scenarios[0].id) : "");
  }, [applications, selectedJourney]);

  const domains = useMemo(() => Array.from(new Set(requirements.map((item) => item.telecom_domain || item.qa_domain).filter((item): item is string => Boolean(item)))).sort(), [requirements]);
  const filteredJourneys = useMemo(() => journeys.filter((journey) => {
    const searchable = [journey.id, journey.name, ...journey.requirements.flatMap((item) => [item.requirement_id, ppmId(item), item.title]), ...journey.scenarios.map((item) => item.title), ...journey.testCases.flatMap((item) => [item.test_case_id, item.title]), ...journey.applications.map((item) => item.name)].join(" ").toLowerCase();
    const domainOk = domainFilter === "all" || journey.requirements.some((item) => (item.telecom_domain || item.qa_domain) === domainFilter);
    const journeyOk = journeyFilter === "all" || journey.id === journeyFilter;
    const scenarioOk = scenarioFilter === "all" || journey.scenarios.some((item) => scenarioKind(item) === scenarioFilter);
    const appOk = applicationFilter === "all" || journey.applications.some((item) => String(item.id) === applicationFilter);
    const coverageOk = coverageFilter === "all" || (coverageFilter === "complete" ? journey.gaps.length === 0 : journey.gaps.length > 0);
    const approvalOk = approvalFilter === "all" || (approvalFilter === "ready" ? journey.gaps.length === 0 : journey.gaps.length > 0);
    return (!query.trim() || searchable.includes(query.trim().toLowerCase())) && domainOk && journeyOk && scenarioOk && appOk && coverageOk && approvalOk;
  }), [applicationFilter, approvalFilter, coverageFilter, domainFilter, journeyFilter, journeys, query, scenarioFilter]);

  const pageSize = 6;
  const pages = Math.max(1, Math.ceil(filteredJourneys.length / pageSize));
  const visibleJourneys = filteredJourneys.slice((page - 1) * pageSize, page * pageSize);
  useEffect(() => { if (page > pages) setPage(pages); }, [page, pages]);

  const mappedRequirementIds = new Set(scenarios.map((item) => item.requirement_id).filter((id): id is number => typeof id === "number"));
  const mappedRequirementCount = requirements.filter((item) => mappedRequirementIds.has(item.id) || testCases.some((tc) => tc.requirement_id === item.id || tc.linked_requirement_id === item.id)).length;
  const uniqueApplicationIds = new Set(testCases.map((item) => item.application_id).filter((id): id is number => typeof id === "number"));
  const totalGaps = journeys.reduce((sum, item) => sum + item.gaps.length, 0);
  const readyJourneys = journeys.filter((item) => item.gaps.length === 0).length;
  const editedCases = testCases.filter((item) => !["draft", "generated"].includes(normal(item.status))).length;
  const taxonomyMapped = scenarios.filter((item) => Boolean(item.scenario_type)).length;
  const applicationMappedCases = testCases.filter((item) => item.application_id != null && applications.some((app) => app.id === item.application_id)).length;
  const evidenceCases = testCases.filter((item) => evidenceRequirements(item).length > 0).length;
  const automationCandidates = testCases.filter((item) => item.automation_candidate || item.automation_eligible === "yes");
  const discoveryChecked = automationCandidates.filter(hasDiscoveryCheck).length;
  const reviewedCases = new Set(reviews.filter((item) => item.artifact_type === "test_case").map((item) => item.artifact_id)).size;

  const graphNeedle = graphQuery.trim().toLowerCase();
  const matchesGraph = (value: string) => !graphNeedle || value.toLowerCase().includes(graphNeedle);
  const scenarioBuckets = selectedJourney ? GRAPH_SCENARIO_KINDS.map((kind) => ({ kind, items: selectedJourney.scenarios.filter((item) => scenarioKind(item) === kind) })).filter((item) => item.items.length > 0 || REQUIRED_SCENARIO_KINDS.includes(item.kind) && selectedJourney.gaps.some((gap) => gap.kind === `missing_${item.kind}_scenario`)) : [];
  const unlinkedCases = testCases.filter((item) => !item.requirement_id && !item.linked_requirement_id && !item.scenario_id && !item.linked_scenario_id);

  function selectNode(type: NodeType, id: string, label: string, raw?: SelectedNode["raw"]) {
    setSelectedNode({ type, id, label, raw });
    setInspectorTab("overview");
    setInspectorOpen(true);
  }

  function selectJourney(journey: JourneyRecord) {
    setSelectedJourneyId(journey.id);
    selectNode("journey", journey.id, journey.name, journey);
  }

  function exportGraph() {
    const header = ["Journey ID", "Journey Name", "Requirement Count", "Scenario Count", "Test Case Count", "Application Mappings", "Evidence Coverage", "Gaps", "Approval Readiness", "Owner", "Updated At"];
    const rows = filteredJourneys.map((journey) => [journey.id, journey.name, journey.requirements.length, journey.scenarios.length, journey.testCases.length, `${journey.applications.length}/${new Set(journey.testCases.map((item) => item.application_id).filter(Boolean)).size || journey.testCases.length}`, `${journey.evidenceCoverage}%`, journey.gaps.length, `${journey.approvalReadiness}%`, journey.ownerId ? `User #${journey.ownerId}` : "Unassigned", journey.updatedAt || ""]);
    const csv = [header, ...rows].map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `journey-graph-project-${projectId}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
    setNotice(`Exported ${filteredJourneys.length} journey record(s).`);
  }

  async function addMissingScenarios() {
    if (!projectId || !selectedJourney?.requirements.length) return;
    setBusy("scenario"); setError(""); setNotice("");
    try {
      const result = await runAIAction({
        actionName: "generate_missing_journey_scenarios",
        title: "Building Journey Coverage",
        module: "Journey Graph",
        artifactType: "Test Scenarios",
        projectId,
        stages: AI_PROCESSING_STAGES.testCaseGeneration,
        successMessage: "Missing journey scenarios are being generated.",
        execute: () => testPlansApi.generateScenarios(projectId, selectedJourney.requirements.map((item) => item.id)),
      });
      const data = result.data as Record<string, unknown>;
      setNotice(String(data.message || "Scenario generation was queued for this journey."));
    } catch (actionError) { setError(errorMessage(actionError, "Could not start scenario generation.")); }
    finally { setBusy(""); }
  }

  async function saveEvidenceRequirement() {
    if (!selectedJourney?.testCases.length || !evidenceText.trim()) return;
    setBusy("evidence"); setError(""); setNotice("");
    try {
      await Promise.all(selectedJourney.testCases.map((testCase) => {
        const current = evidenceRequirements(testCase);
        const next = Array.from(new Set([...current, evidenceText.trim()]));
        return testCasesApi.update(testCase.id, { metadata_: { ...(testCase.metadata_ || {}), evidence_requirements: next }, comment: `Journey graph evidence requirement: ${evidenceText.trim()}` });
      }));
      setEvidenceFormOpen(false); setEvidenceText(""); setNotice("Evidence requirement saved to the linked test cases.");
      await loadData();
    } catch (actionError) { setError(errorMessage(actionError, "Could not save the evidence requirement.")); }
    finally { setBusy(""); }
  }

  async function resolveMapping() {
    const selectedApplication = applications.find((item) => String(item.id) === applicationId);
    if (!selectedJourney?.testCases.length || !selectedApplication?.id) return;
    setBusy("mapping"); setError(""); setNotice("");
    try {
      await Promise.all(selectedJourney.testCases.map((testCase) => testCasesApi.update(testCase.id, { application_id: selectedApplication.id, comment: `Journey graph mapping resolved to ${selectedApplication.name}` })));
      setMappingFormOpen(false); setNotice(`Mapped ${selectedJourney.testCases.length} test case(s) to ${selectedApplication.name}.`);
      await loadData();
    } catch (actionError) { setError(errorMessage(actionError, "Could not resolve the application mapping.")); }
    finally { setBusy(""); }
  }

  async function linkExistingCase() {
    const testCase = unlinkedCases.find((item) => String(item.id) === linkCaseId);
    const scenario = selectedJourney?.scenarios.find((item) => String(item.id) === linkScenarioId);
    if (!testCase || !scenario || !scenario.requirement_id) return;
    setBusy("link"); setError(""); setNotice("");
    try {
      await testCasesApi.update(testCase.id, { requirement_id: scenario.requirement_id, scenario_id: scenario.id, comment: `Linked from Journey Graph ${selectedJourney?.id}` });
      setLinkFormOpen(false); setLinkCaseId(""); setNotice(`${testCase.test_case_id} linked to ${scenario.scenario_id}.`);
      await loadData();
    } catch (actionError) { setError(errorMessage(actionError, "Could not link the selected test case.")); }
    finally { setBusy(""); }
  }

  async function sendToDiscovery() {
    if (!projectId || !selectedJourney) return;
    const candidates = selectedJourney.testCases.filter((item) => item.automation_candidate || item.automation_eligible === "yes");
    if (!candidates.length) { setError("This journey has no automation candidates to send to discovery."); return; }
    setBusy("discovery"); setError(""); setNotice("");
    try {
      const result = await runAIAction({
        actionName: "prepare_application_discovery",
        title: "Preparing Application Discovery",
        module: "Journey Graph",
        artifactType: "Discovery Session",
        projectId,
        environmentId: environment,
        stages: AI_PROCESSING_STAGES.applicationDiscovery,
        successMessage: "Application discovery was queued successfully.",
        execute: () => automationApi.discoverUi(projectId, candidates.map((item) => item.id), environment),
      });
      setNotice(result.data.message || "Discovery review was queued.");
    } catch (actionError) { setError(errorMessage(actionError, "Could not send this journey to discovery review.")); }
    finally { setBusy(""); }
  }

  async function sendToApproval() {
    if (!selectedJourney || selectedJourney.gaps.length > 0) return;
    setBusy("approval"); setError(""); setNotice("");
    try {
      await Promise.all(selectedJourney.testCases.filter((item) => item.status !== "approved").map((item) => testCasesApi.update(item.id, { status: "pending_approval", comment: `Submitted from Journey Graph ${selectedJourney.id}` })));
      setNotice("Journey test cases were sent to independent Test Case Approval.");
      await loadData();
      router.push(`/test-cases?project=${projectId}&view=approval`);
    } catch (actionError) { setError(errorMessage(actionError, "Could not send the journey to Test Case Approval.")); }
    finally { setBusy(""); }
  }

  async function markGapReviewed(gap: GraphGap) {
    const target = selectedJourney?.testCases[0];
    if (!target) { setError("A linked test case is required before this gap can be reviewed and audited."); return; }
    setBusy("gap"); setError(""); setNotice("");
    try {
      const current = Array.isArray(target.metadata_?.journey_reviewed_gaps) ? target.metadata_?.journey_reviewed_gaps : [];
      const entry = { gap_id: gap.id, journey_id: selectedJourney?.id, reviewed_at: new Date().toISOString() };
      await testCasesApi.update(target.id, { metadata_: { ...(target.metadata_ || {}), journey_reviewed_gaps: [...current, entry] }, comment: `Reviewed journey gap: ${gap.label}` });
      setNotice(`${gap.label} was marked reviewed. The blocker remains until its source data is resolved.`);
      await loadData();
    } catch (actionError) { setError(errorMessage(actionError, "Could not record the gap review.")); }
    finally { setBusy(""); }
  }

  if (!projectId) return <div className="flex h-64 items-center justify-center text-sm font-semibold text-slate-500">Select a project to load its journey graph.</div>;

  return (
    <div className="min-h-full">
      <section className="space-y-2 pb-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
          <span>QAI Command Center</span><ChevronRight className="h-3 w-3 text-slate-300" /><span className="text-[#1b59f8]">Test Planning</span><ChevronRight className="h-3 w-3 text-slate-300" /><span className="text-slate-800">Journey Graph</span>
        </div>

        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2"><h1 className="text-2xl font-extrabold tracking-tight text-slate-950">Journey Graph</h1><span className="rounded-md border border-purple-100 bg-purple-50 px-2 py-0.5 text-[10px] font-bold text-purple-700">P1-S3 UI-012</span></div>
            <p className="mt-1 text-xs font-semibold text-slate-500">Visualize scenario coverage, journey paths, application touchpoints and approval readiness.</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden text-[10px] font-semibold text-slate-500 xl:inline">Last refreshed: {lastRefreshed ? displayDate(lastRefreshed.toISOString()) : "Loading"}</span>
            <Button aria-label="Refresh journey graph" variant="outline" size="sm" onClick={() => void loadData()} disabled={loading} className="h-9 gap-2 border-slate-200 text-xs font-bold"><RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />Refresh</Button>
            <Button aria-label="Rebuild journey graph" size="sm" onClick={() => void loadData()} disabled={loading} className="h-9 gap-2 bg-[#1b59f8] text-xs font-bold text-white hover:bg-[#1546c2]"><Network className="h-4 w-4" />Rebuild Graph</Button>
            <Button aria-label="Export journey graph" variant="outline" size="sm" onClick={exportGraph} disabled={!journeys.length} className="h-9 gap-2 border-slate-200 text-xs font-bold"><Download className="h-4 w-4" />Export Graph<ChevronDown className="h-3 w-3" /></Button>
          </div>
        </div>

        {(error || notice) && <div role="alert" className={cn("flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold", error ? "border-red-200 bg-red-50 text-red-700" : "border-blue-200 bg-blue-50 text-blue-700")}><AlertTriangle className="h-4 w-4 shrink-0" /><span className="flex-1">{error || notice}</span><button aria-label="Dismiss message" onClick={() => { setError(""); setNotice(""); }}><X className="h-4 w-4" /></button></div>}

        <div className="grid grid-cols-2 gap-2 xl:grid-cols-6">
          <Kpi title="Requirements Mapped" value={mappedRequirementCount} subtitle={`of ${requirements.length} approved`} icon={FileCheck2} tone="emerald" />
          <Kpi title="Journeys Identified" value={journeys.length} subtitle="Active journeys" icon={Network} tone="blue" />
          <Kpi title="Scenario Nodes" value={scenarios.length} subtitle="Across all journeys" icon={GitBranch} tone="purple" />
          <Kpi title="Application Touchpoints" value={uniqueApplicationIds.size} subtitle="Mapped systems" icon={Layers3} tone="cyan" />
          <Kpi title="Coverage Gaps" value={totalGaps} subtitle="Need attention" icon={AlertTriangle} tone="amber" />
          <Kpi title="Approval Ready" value={`${percent(readyJourneys, journeys.length)}%`} subtitle={`${readyJourneys} of ${journeys.length} journeys`} icon={ShieldCheck} tone="green" progress={percent(readyJourneys, journeys.length)} />
        </div>

        <div className="grid grid-cols-4 gap-x-4 gap-y-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm xl:grid-cols-8">
          <Readiness label="Requirements approved" value={`${requirements.length}/${requirements.length}`} good={requirements.length > 0} />
          <Readiness label="Test cases generated" value={`${testCases.length}/${scenarios.length}`} good={testCases.length >= scenarios.length && scenarios.length > 0} />
          <Readiness label="Test cases edited / validated" value={`${editedCases}/${testCases.length}`} good={editedCases === testCases.length && testCases.length > 0} />
          <Readiness label="Taxonomy mapped" value={`${percent(taxonomyMapped, scenarios.length)}%`} good={taxonomyMapped === scenarios.length && scenarios.length > 0} />
          <Readiness label="Application mapping complete" value={`${applicationMappedCases}/${testCases.length}`} good={applicationMappedCases === testCases.length && testCases.length > 0} />
          <Readiness label="Evidence requirements attached" value={`${percent(evidenceCases, testCases.length)}%`} good={evidenceCases === testCases.length && testCases.length > 0} />
          <Readiness label="Discovery eligibility checked" value={`${discoveryChecked}/${automationCandidates.length}`} good={discoveryChecked === automationCandidates.length && automationCandidates.length > 0} />
          <Readiness label="Independent review required" value={`${reviewedCases}/${testCases.length}`} good={reviewedCases === testCases.length && testCases.length > 0} blocker />
        </div>

        <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center gap-1.5 overflow-hidden border-b border-slate-100 p-2">
            <label className="relative w-[250px] shrink-0"><Search className="absolute left-3 top-2 h-3.5 w-3.5 text-slate-400" /><input aria-label="Search journeys" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="Search requirement, journey, scenario, test case, PPM ID or app..." className="h-8 w-full rounded-md border border-slate-200 pl-9 pr-3 text-[10px] font-semibold outline-none focus:border-blue-300" /></label>
            <FilterSelect label="Domain" value={domainFilter} onChange={setDomainFilter} options={domains.map((value) => ({ value, label: value }))} />
            <FilterSelect label="Journey" value={journeyFilter} onChange={setJourneyFilter} options={journeys.map((item) => ({ value: item.id, label: item.name }))} />
            <FilterSelect label="Scenario Type" value={scenarioFilter} onChange={setScenarioFilter} options={REQUIRED_SCENARIO_KINDS.map((value) => ({ value, label: value[0].toUpperCase() + value.slice(1) }))} />
            <FilterSelect label="Application" value={applicationFilter} onChange={setApplicationFilter} options={applications.filter((item) => item.id != null).map((item) => ({ value: String(item.id), label: item.name }))} />
            <FilterSelect label="Coverage Status" value={coverageFilter} onChange={setCoverageFilter} options={[{ value: "complete", label: "Complete" }, { value: "gaps", label: "Has Gaps" }]} />
            <FilterSelect label="Approval Readiness" value={approvalFilter} onChange={setApprovalFilter} options={[{ value: "ready", label: "Ready" }, { value: "blocked", label: "Blocked" }]} />
            <Button variant="outline" size="sm" onClick={() => setAdvancedOpen((value) => !value)} className="h-8 shrink-0 gap-1.5 border-slate-200 px-2 text-[9px] font-bold text-[#1b59f8]"><Filter className="h-3 w-3" />More Filters<ChevronDown className={cn("h-3 w-3 transition", advancedOpen && "rotate-180")} /></Button>
          </div>
          {advancedOpen && <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/60 px-3 py-2 text-[11px] font-semibold text-slate-600"><span>Filters use live requirement, scenario, test-case and application fields.</span><button onClick={() => { setQuery(""); setDomainFilter("all"); setJourneyFilter("all"); setScenarioFilter("all"); setApplicationFilter("all"); setCoverageFilter("all"); setApprovalFilter("all"); }} className="font-bold text-[#1b59f8]">Clear all filters</button></div>}

          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <div className="flex items-center gap-1.5"><span className="text-xs font-extrabold text-slate-900">Journey Graph Canvas</span><CircleDot className="h-3.5 w-3.5 text-slate-400" /></div>
            <div className="flex items-center gap-2">
              <label className="relative"><Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" /><input aria-label="Search graph" value={graphQuery} onChange={(event) => setGraphQuery(event.target.value)} placeholder="Search graph..." className="h-8 w-28 rounded-md border border-slate-200 pl-8 pr-2 text-[10px] outline-none focus:border-blue-300" /></label>
              <GraphButton label="Fit to Screen" icon={Maximize2} onClick={() => setZoom(1)} />
              <GraphButton label="Zoom In" icon={ZoomIn} onClick={() => setZoom((value) => Math.min(1.25, Number((value + 0.1).toFixed(2))))} />
              <GraphButton label="Zoom Out" icon={ZoomOut} onClick={() => setZoom((value) => Math.max(0.7, Number((value - 0.1).toFixed(2))))} />
              <Toggle label="Show Gaps Only" value={showGapsOnly} onChange={setShowGapsOnly} />
              <Toggle label="Show Evidence Links" value={showEvidenceLinks} onChange={setShowEvidenceLinks} />
              <Toggle label="Show Application Links" value={showApplicationLinks} onChange={setShowApplicationLinks} />
              <div className="relative"><button aria-label="Graph options" onClick={() => setGraphOptionsOpen((value) => !value)} className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50"><MoreVertical className="h-4 w-4" /></button>{graphOptionsOpen && <div className="absolute right-0 top-9 z-20 w-40 rounded-md border border-slate-200 bg-white p-1 shadow-lg"><button onClick={() => { setZoom(1); setGraphQuery(""); setShowGapsOnly(false); setShowEvidenceLinks(true); setShowApplicationLinks(true); setGraphOptionsOpen(false); }} className="w-full rounded px-2 py-2 text-left text-[9px] font-bold text-slate-700 hover:bg-slate-50">Reset graph controls</button><button onClick={() => router.push(`/test-cases?project=${projectId}&view=editor`)} className="w-full rounded px-2 py-2 text-left text-[9px] font-bold text-[#1b59f8] hover:bg-blue-50">Open Test Case Editor</button></div>}</div>
            </div>
          </div>

          <div className="h-[248px] overflow-hidden bg-slate-50/20 p-3">
            {loading ? <div className="flex h-full items-center justify-center gap-2 text-xs font-semibold text-slate-500"><Loader2 className="h-4 w-4 animate-spin text-[#1b59f8]" />Loading project graph...</div> : !selectedJourney ? <div className="flex h-full items-center justify-center text-xs font-semibold text-slate-500">No approved requirements are available to build a journey graph.</div> : (
              <div className="origin-top-left transition-transform" style={{ transform: `scale(${zoom})`, width: `${100 / zoom}%` }}>
                <div className="grid grid-cols-[1fr_20px_1fr_20px_1fr_20px_1fr_20px_1fr_20px_1fr_20px_1fr] gap-1 text-[9px]">
                  <GraphColumn title="Requirements" hidden={showGapsOnly}>{selectedJourney.requirements.filter((item) => matchesGraph(`${item.requirement_id} ${item.title}`)).slice(0, 3).map((item) => <GraphNode key={item.id} type="requirement" title={item.requirement_id} detail={`${ppmId(item)}\n${item.title}`} onClick={() => selectNode("requirement", item.requirement_id, item.title, item)} />)}<MoreCount count={selectedJourney.requirements.length - 3} /></GraphColumn>
                  <Connector label="maps to" hidden={showGapsOnly} />
                  <GraphColumn title="Journeys" hidden={showGapsOnly}><GraphNode type="journey" title={selectedJourney.id} detail={selectedJourney.name} selected onClick={() => selectJourney(selectedJourney)} /></GraphColumn>
                  <Connector label="has" hidden={showGapsOnly} />
                  <GraphColumn title="Scenarios" hidden={showGapsOnly}>{scenarioBuckets.filter((bucket) => matchesGraph(bucket.kind)).slice(0, 6).map((bucket) => <GraphNode key={bucket.kind} type="scenario" title={bucket.kind[0].toUpperCase() + bucket.kind.slice(1)} detail={`${bucket.items.length} scenario${bucket.items.length === 1 ? "" : "s"}`} scenario={bucket.kind} onClick={() => { const scenario = bucket.items[0]; const gap = selectedJourney.gaps.find((item) => item.kind === `missing_${bucket.kind}_scenario`); if (scenario) selectNode("scenario", scenario.scenario_id, scenario.title, scenario); else if (gap) selectNode("gap", gap.id, gap.label, gap); }} />)}</GraphColumn>
                  <Connector label="validates" hidden={showGapsOnly} />
                  <GraphColumn title="Test Cases" hidden={showGapsOnly}>{selectedJourney.testCases.filter((item) => matchesGraph(`${item.test_case_id} ${item.title}`)).slice(0, 5).map((item) => <GraphNode key={item.id} type="test_case" title={item.test_case_id} detail={item.title} classificationStatus={classificationsEnabled ? classificationByTestCaseId.get(item.id)?.candidate_status : undefined} onClick={() => selectNode("test_case", item.test_case_id, item.title, item)} />)}<MoreCount count={selectedJourney.testCases.length - 5} /></GraphColumn>
                  <Connector label="covers" hidden={showGapsOnly || !showApplicationLinks} />
                  <GraphColumn title="Applications" hidden={showGapsOnly || !showApplicationLinks}>{selectedJourney.applications.filter((item) => matchesGraph(`${item.key} ${item.name}`)).slice(0, 4).map((item) => <GraphNode key={item.key} type="application" title={item.name} detail={item.description || item.key} onClick={() => selectNode("application", item.key, item.name, item)} />)}{!selectedJourney.applications.length && <EmptyNode label="No mapped application" />}</GraphColumn>
                  <Connector label="requires evidence" hidden={showGapsOnly || !showEvidenceLinks} />
                  <GraphColumn title="Evidence" hidden={showGapsOnly || !showEvidenceLinks}>{Array.from(new Set(selectedJourney.testCases.flatMap(evidenceRequirements))).filter(matchesGraph).slice(0, 4).map((item) => <GraphNode key={item} type="evidence" title={item} detail="Required" onClick={() => selectNode("evidence", item, item)} />)}{!selectedJourney.testCases.some((item) => evidenceRequirements(item).length) && <EmptyNode label="No evidence requirement" tone="red" />}</GraphColumn>
                  <Connector label="gap / blocker" />
                  <GraphColumn title="Gaps / Blockers">{selectedJourney.gaps.filter((item) => matchesGraph(`${item.label} ${item.detail}`)).slice(0, 4).map((item) => <GraphNode key={item.id} type="gap" title={item.label} detail={`${item.severity.toUpperCase()} impact`} onClick={() => selectNode("gap", item.id, item.label, item)} />)}{!selectedJourney.gaps.length && <div className="rounded-md border border-emerald-200 bg-emerald-50 p-2 font-bold text-emerald-700">No unresolved blockers</div>}</GraphColumn>
                </div>
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-4 border-t border-slate-100 px-3 py-2 text-[9px] font-semibold text-slate-600"><span className="font-extrabold text-slate-800">Legend:</span><Legend color="bg-emerald-500" label="Positive" /><Legend color="bg-red-500" label="Negative" /><Legend color="bg-amber-500" label="Boundary" /><Legend color="bg-purple-500" label="Recovery" /><Legend color="bg-blue-500" label="Regression" /><Legend color="bg-yellow-400" label="Automation Candidate" /><Legend line="border-slate-400" label="maps to" /><Legend line="border-emerald-400" label="validates" /><Legend line="border-blue-400" label="covers" /><Legend line="border-purple-400" label="requires evidence" /><Legend line="border-red-400" label="gap / blocker" /></div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2"><span className="text-xs font-extrabold text-slate-900">Journey Coverage List</span><CircleDot className="h-3.5 w-3.5 text-slate-400" /><span className="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-bold text-slate-600">{filteredJourneys.length} of {journeys.length}</span></div>
          <div className="grid grid-cols-[76px_minmax(150px,1.2fr)_82px_82px_82px_110px_112px_52px_120px_98px_130px] border-b border-slate-100 bg-slate-50/70 px-3 py-1.5 text-[8px] font-extrabold uppercase text-slate-500"><span>Journey ID</span><span>Journey Name</span><span>Requirement Count</span><span>Scenario Count</span><span>Test Case Count</span><span>Application Mappings</span><span>Evidence Coverage</span><span>Gaps</span><span>Approval Readiness</span><span>Owner</span><span>Updated At</span></div>
          {visibleJourneys.map((journey) => <button key={journey.id} onClick={() => selectJourney(journey)} className={cn("grid w-full grid-cols-[76px_minmax(150px,1.2fr)_82px_82px_82px_110px_112px_52px_120px_98px_130px] items-center border-b border-slate-100 px-3 py-1.5 text-left text-[9px] font-semibold text-slate-700 transition hover:bg-blue-50/50", selectedJourney?.id === journey.id && "border-l-4 border-l-[#1b59f8] bg-blue-50/70 pl-2")}><span className="font-bold text-[#1b59f8]">{journey.id}</span><span className="truncate font-bold text-slate-900">{journey.name}</span><span>{journey.requirements.length}</span><span>{journey.scenarios.length}</span><span>{journey.testCases.length}</span><span className="font-bold text-[#1b59f8]">{journey.applications.length}/{Math.max(journey.applications.length, new Set(journey.testCases.map((item) => item.application_id).filter(Boolean)).size)}</span><ProgressCell value={journey.evidenceCoverage} /><span><span className={cn("rounded-full px-2 py-0.5 font-bold", journey.gaps.length ? "bg-red-50 text-red-600" : "bg-emerald-50 text-emerald-600")}>{journey.gaps.length}</span></span><ProgressCell value={journey.approvalReadiness} /><span>{journey.ownerId ? `User #${journey.ownerId}` : "Unassigned"}</span><span className="text-slate-500">{displayDate(journey.updatedAt)}</span></button>)}
          {!visibleJourneys.length && <div className="p-8 text-center text-xs font-semibold text-slate-500">No journeys match the selected filters.</div>}
          <div className="flex items-center justify-between px-3 py-2 text-[10px] font-semibold text-slate-500"><span>Showing {visibleJourneys.length ? (page - 1) * pageSize + 1 : 0} to {Math.min(page * pageSize, filteredJourneys.length)} of {filteredJourneys.length} journeys</span><div className="flex items-center gap-1"><button aria-label="Previous journey page" disabled={page === 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="flex h-7 w-7 items-center justify-center rounded border border-slate-200 disabled:opacity-40"><ChevronLeft className="h-3.5 w-3.5" /></button><span className="flex h-7 min-w-7 items-center justify-center rounded border border-blue-400 bg-blue-50 px-2 font-bold text-[#1b59f8]">{page}</span><button aria-label="Next journey page" disabled={page === pages} onClick={() => setPage((value) => Math.min(pages, value + 1))} className="flex h-7 w-7 items-center justify-center rounded border border-slate-200 disabled:opacity-40"><ChevronRight className="h-3.5 w-3.5" /></button><span className="ml-2 rounded border border-slate-200 px-3 py-1.5">{pageSize} / page</span></div></div>
        </div>
      </section>

      <Drawer open={inspectorOpen} onOpenChange={setInspectorOpen}>
      <DrawerContent size="lg">
        <DrawerHeader>
          <div>
            <div className="flex items-center gap-2"><DrawerTitle>{selectedNode?.id || selectedJourney?.id || "Journey"}</DrawerTitle><span className={cn("rounded-md border px-2 py-0.5 text-[9px] font-bold", selectedJourney?.gaps.length ? "border-amber-200 bg-amber-50 text-amber-700" : "border-emerald-200 bg-emerald-50 text-emerald-700")}>{selectedJourney?.gaps.length ? "Needs Review" : "Ready"}</span></div>
            <p className="mt-2 text-xs font-bold text-slate-800">{selectedNode?.label || selectedJourney?.name || "No journey selected"}</p>
          </div>
          <button aria-label="Close inspector" onClick={() => setInspectorOpen(false)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-50"><X className="h-4 w-4" /></button>
        </DrawerHeader>
        <div className="grid grid-cols-6 border-b border-slate-100 px-2 shrink-0">{(["overview", "coverage", "applications", "evidence", "automation", "activity"] as InspectorTab[]).map((tab) => <button key={tab} onClick={() => setInspectorTab(tab)} className={cn("border-b-2 px-1 py-3 text-[9px] font-bold capitalize", inspectorTab === tab ? "border-[#1b59f8] text-[#1b59f8]" : "border-transparent text-slate-500")}>{tab}</button>)}</div>
        <DrawerBody className="space-y-3">
          {selectedJourney && inspectorTab === "overview" && <OverviewInspector journey={selectedJourney} selectedNode={selectedNode} reviews={reviews} />}
          {selectedJourney && inspectorTab === "coverage" && <CoverageInspector journey={selectedJourney} unlinkedCases={unlinkedCases} linkFormOpen={linkFormOpen} setLinkFormOpen={setLinkFormOpen} linkCaseId={linkCaseId} setLinkCaseId={setLinkCaseId} linkScenarioId={linkScenarioId} setLinkScenarioId={setLinkScenarioId} onLink={linkExistingCase} busy={busy} />}
          {selectedJourney && inspectorTab === "applications" && <ApplicationsInspector projectId={projectId} journey={selectedJourney} applications={applications} availableEnvironments={availableEnvironments} environment={environment} setEnvironment={setEnvironment} mappingFormOpen={mappingFormOpen} setMappingFormOpen={setMappingFormOpen} applicationId={applicationId} setApplicationId={setApplicationId} onResolve={resolveMapping} busy={busy} />}
          {selectedJourney && inspectorTab === "evidence" && <EvidenceInspector journey={selectedJourney} evidenceFormOpen={evidenceFormOpen} setEvidenceFormOpen={setEvidenceFormOpen} evidenceText={evidenceText} setEvidenceText={setEvidenceText} onSave={saveEvidenceRequirement} busy={busy} />}
          {selectedJourney && inspectorTab === "automation" && <AutomationInspector journey={selectedJourney} selectedNode={selectedNode} classifications={classificationByTestCaseId} enabled={classificationsEnabled} />}
          {selectedJourney && inspectorTab === "activity" && <ActivityInspector journey={selectedJourney} reviews={reviews} approvals={approvals} />}

          {selectedJourney && <>
            <Panel title="Top Blockers for this Journey" tone="red"><div className="space-y-2">{selectedJourney.gaps.slice(0, 5).map((gap) => <button key={gap.id} onClick={() => selectNode("gap", gap.id, gap.label, gap)} className="flex w-full items-start justify-between gap-3 text-left text-[10px] font-semibold"><span className="text-red-700">• {gap.label}</span><span className="capitalize text-amber-600">{gap.severity}</span></button>)}{!selectedJourney.gaps.length && <p className="text-[10px] font-semibold text-emerald-700">No unresolved blockers.</p>}</div></Panel>
            {selectedNode?.type === "gap" && <Button variant="outline" onClick={() => void markGapReviewed(selectedNode.raw as GraphGap)} disabled={busy === "gap"} className="h-9 w-full border-slate-300 text-[10px] font-bold">Mark Gap Reviewed</Button>}
            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" onClick={() => void addMissingScenarios()} disabled={busy === "scenario" || !selectedJourney.requirements.length} className="h-9 gap-1 border-blue-300 text-[10px] font-bold text-[#1b59f8]"><Plus className="h-3.5 w-3.5" />Add Missing Scenario</Button>
              <Button aria-label="Add evidence requirement action" variant="outline" onClick={() => { setInspectorTab("evidence"); setEvidenceFormOpen(true); }} disabled={!selectedJourney.testCases.length} className="h-9 gap-1 border-purple-300 text-[10px] font-bold text-purple-700"><Plus className="h-3.5 w-3.5" />Add Evidence Requirement</Button>
              <Button aria-label="Resolve application mapping action" variant="outline" onClick={() => { setInspectorTab("applications"); setMappingFormOpen(true); }} disabled={!selectedJourney.testCases.length || !applications.length} className="h-9 gap-1 border-cyan-300 text-[10px] font-bold text-cyan-700"><Link2 className="h-3.5 w-3.5" />Resolve Mapping</Button>
              <Button variant="outline" onClick={() => void sendToDiscovery()} disabled={busy === "discovery"} className="h-9 gap-1 border-amber-300 text-[10px] font-bold text-amber-700"><ShieldCheck className="h-3.5 w-3.5" />Send to Discovery Review</Button>
            </div>
            <Button onClick={() => void sendToApproval()} disabled={selectedJourney.gaps.length > 0 || busy === "approval" || !selectedJourney.testCases.length} className="h-10 w-full bg-[#1b59f8] text-[11px] font-bold text-white hover:bg-[#1546c2]"><ShieldCheck className="mr-2 h-4 w-4" />Send to Test Case Approval</Button>
            {selectedJourney.gaps.length > 0 && <p className="-mt-2 text-center text-[9px] font-semibold text-red-600">Cannot proceed until blockers are resolved</p>}
          </>}
          <Panel title="Gap Summary (All Journeys)" action="View all" onAction={() => { setCoverageFilter("gaps"); setQuery(""); }}><div className="grid grid-cols-4 gap-2"><GapCount label="High" value={journeys.flatMap((item) => item.gaps).filter((gap) => gap.severity === "high").length} tone="red" /><GapCount label="Medium" value={journeys.flatMap((item) => item.gaps).filter((gap) => gap.severity === "medium").length} tone="amber" /><GapCount label="Low" value={journeys.flatMap((item) => item.gaps).filter((gap) => gap.severity === "low").length} tone="yellow" /><GapCount label="Info" value={journeys.flatMap((item) => item.gaps).filter((gap) => gap.severity === "info").length} tone="blue" /></div></Panel>
        </DrawerBody>
      </DrawerContent>
      </Drawer>
    </div>
  );
}

function Kpi({ title, value, subtitle, icon: Icon, tone, progress }: { title: string; value: string | number; subtitle: string; icon: typeof FileText; tone: "emerald" | "blue" | "purple" | "cyan" | "amber" | "green"; progress?: number }) {
  const tones = { emerald: "border-emerald-200 bg-emerald-50 text-emerald-600", blue: "border-blue-200 bg-blue-50 text-blue-600", purple: "border-purple-200 bg-purple-50 text-purple-600", cyan: "border-cyan-200 bg-cyan-50 text-cyan-600", amber: "border-amber-200 bg-amber-50 text-amber-600", green: "border-green-200 bg-green-50 text-green-600" };
  return <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm"><div className="flex items-center gap-2"><span className={cn("flex h-7 w-7 items-center justify-center rounded-lg border", tones[tone])}><Icon className="h-3.5 w-3.5" /></span><p className="truncate text-[9px] font-extrabold text-slate-800">{title}</p></div><div className="mt-2 flex items-end gap-2"><div><p className="text-lg font-extrabold text-slate-950">{value}</p><p className="mt-0.5 text-[8px] font-semibold text-slate-500">{subtitle}</p></div>{progress != null && <div className="ml-auto h-8 w-8 rounded-full p-1" style={{ background: `conic-gradient(#55a630 ${progress * 3.6}deg, #e5e7eb 0deg)` }}><div className="h-full w-full rounded-full bg-white" /></div>}</div></div>;
}

function Readiness({ label, value, good, blocker }: { label: string; value: string; good: boolean; blocker?: boolean }) {
  return <div className="flex min-w-0 items-center gap-2"><span className={cn("flex h-5 w-5 shrink-0 items-center justify-center rounded-full border", good ? "border-emerald-200 bg-emerald-50 text-emerald-600" : blocker ? "border-red-200 bg-red-50 text-red-600" : "border-amber-200 bg-amber-50 text-amber-600")}>{good ? <CheckCircle2 className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}</span><div className="min-w-0"><p className="truncate text-[8px] font-bold text-slate-600">{label}</p><p className="text-[9px] font-extrabold text-slate-900">{value}</p></div></div>;
}

function FilterSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: Array<{ value: string; label: string }> }) {
  return <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} className="h-8 min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-1.5 text-[9px] font-semibold text-slate-700 outline-none focus:border-blue-300"><option value="all">{label}: All</option>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>;
}

function GraphButton({ label, icon: Icon, onClick }: { label: string; icon: typeof Search; onClick: () => void }) { return <button onClick={onClick} className="flex h-8 items-center gap-1 rounded-md border border-slate-200 px-2 text-[9px] font-bold text-slate-600 hover:bg-slate-50"><Icon className="h-3.5 w-3.5" />{label}</button>; }

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (value: boolean) => void }) { return <label className="flex h-8 cursor-pointer items-center gap-1.5 text-[9px] font-bold text-slate-600"><button type="button" role="switch" aria-label={label} aria-checked={value} onClick={() => onChange(!value)} className={cn("relative h-4 w-7 rounded-full transition", value ? "bg-[#1b59f8]" : "bg-slate-200")}><span className={cn("absolute top-0.5 h-3 w-3 rounded-full bg-white transition", value ? "left-3.5" : "left-0.5")} /></button>{label}</label>; }

function GraphColumn({ title, children, hidden }: { title: string; children: React.ReactNode; hidden?: boolean }) { return <div className={cn("min-w-0", hidden && "opacity-15")}><p className="mb-1.5 text-center text-[8px] font-extrabold text-slate-900">{title}</p><div className="space-y-1.5">{children}</div></div>; }

function Connector({ label, hidden }: { label: string; hidden?: boolean }) { return <div className={cn("pt-12 text-center", hidden && "opacity-15")}><p className="-ml-5 mb-1 w-16 text-[7px] font-semibold text-slate-500">{label}</p><div className="border-t border-dashed border-slate-400" /></div>; }

const CLASSIFICATION_DOT_TONE: Record<string, string> = {
  RECOMMENDED: "bg-emerald-500",
  APPROVED: "bg-emerald-500",
  CONDITIONAL: "bg-amber-500",
  DEFERRED: "bg-amber-500",
  POLICY_STALE: "bg-amber-500",
  RECLASSIFICATION_REQUIRED: "bg-amber-500",
  NOT_RECOMMENDED: "bg-red-500",
  BLOCKED: "bg-red-500",
  NOT_EVALUATED: "bg-slate-300",
};

function GraphNode({ type, title, detail, selected, scenario, classificationStatus, onClick }: { type: NodeType; title: string; detail: string; selected?: boolean; scenario?: ScenarioKind; classificationStatus?: string; onClick: () => void }) {
  const scenarioTone = scenario === "negative" ? "border-red-300 bg-red-50" : scenario === "boundary" ? "border-amber-300 bg-amber-50" : scenario === "recovery" ? "border-purple-300 bg-purple-50" : scenario === "regression" ? "border-blue-300 bg-blue-50" : "";
  return <button onClick={onClick} className={cn("relative w-full rounded-md border p-1.5 text-left transition hover:ring-2 hover:ring-blue-100", NODE_TONES[type], scenarioTone, selected && "ring-2 ring-blue-200")}>
    {classificationStatus && <span title={`Automation classification: ${classificationStatus.replace(/_/g, " ")}`} className={cn("absolute right-1 top-1 h-1.5 w-1.5 rounded-full", CLASSIFICATION_DOT_TONE[classificationStatus] || "bg-slate-300")} />}
    <p className="truncate pr-2 text-[8px] font-extrabold">{title}</p>{detail.split("\n").map((line, index) => <p key={`${line}-${index}`} className="line-clamp-1 text-[7px] font-semibold opacity-75">{line}</p>)}
  </button>;
}

function EmptyNode({ label, tone = "slate" }: { label: string; tone?: "slate" | "red" }) { return <div className={cn("rounded-md border border-dashed p-2 text-center text-[8px] font-bold", tone === "red" ? "border-red-300 bg-red-50 text-red-600" : "border-slate-300 text-slate-400")}>{label}</div>; }
function MoreCount({ count }: { count: number }) { return count > 0 ? <div className="mx-auto w-fit rounded-full bg-slate-100 px-3 py-1 text-[8px] font-bold text-slate-600">+{count} more</div> : null; }
function Legend({ color, line, label }: { color?: string; line?: string; label: string }) { return <span className="flex items-center gap-1.5">{color && <span className={cn("h-2 w-2 rounded-full", color)} />}{line && <span className={cn("w-5 border-t border-dashed", line)} />}{label}</span>; }

function ProgressCell({ value }: { value: number }) { const tone = value >= 80 ? "bg-emerald-500" : value >= 50 ? "bg-amber-500" : "bg-red-500"; return <span className="flex items-center gap-2"><span className="h-1.5 w-14 rounded-full bg-slate-100"><span className={cn("block h-full rounded-full", tone)} style={{ width: `${value}%` }} /></span><span>{value}%</span></span>; }

function Panel({ title, action, onAction, tone, children }: { title: string; action?: string; onAction?: () => void; tone?: "red"; children: React.ReactNode }) { return <section className={cn("rounded-lg border p-3", tone === "red" ? "border-red-200 bg-red-50/50" : "border-slate-200 bg-white")}><div className="mb-3 flex items-center justify-between"><h3 className="text-[10px] font-extrabold text-slate-800">{title}</h3>{action && <button onClick={onAction} className="text-[9px] font-bold text-[#1b59f8]">{action}</button>}</div>{children}</section>; }

function InfoPair({ label, value, link }: { label: string; value: string; link?: boolean }) { return <div><p className="text-[8px] font-bold text-slate-400">{label}</p><p className={cn("mt-1 break-words text-[10px] font-bold", link ? "text-[#1b59f8]" : "text-slate-700")}>{value}</p></div>; }

function OverviewInspector({ journey, selectedNode, reviews }: { journey: JourneyRecord; selectedNode: SelectedNode | null; reviews: ArtifactReview[] }) {
  const requirement = journey.requirements[0];
  const scoreReviews = reviews.filter(
    (item) =>
      journey.scenarios.some((scenario) => scenario.id === item.artifact_id) &&
      item.artifact_type === "scenario_test_case_coverage" &&
      item.overall_score != null,
  );
  const aiScore = scoreReviews.length
    ? scoreReviews.reduce((sum, item) => sum + Number(item.overall_score), 0) / scoreReviews.length
    : null;
  const aiScorePercent = aiScore == null ? null : Math.round(Math.max(0, Math.min(5, aiScore)) * 20);
  return <>
    <Panel title="Selected Node"><div className="grid grid-cols-2 gap-3"><InfoPair label="Node Type" value={(selectedNode?.type || "journey").replace("_", " ")} /><InfoPair label="Status" value={journey.gaps.length ? "Needs Review" : "Ready"} /><InfoPair label="Journey ID" value={journey.id} link /><InfoPair label="Journey Name" value={journey.name} /><InfoPair label="Linked Requirement" value={requirement?.requirement_id || "Not linked"} link /><InfoPair label="PPM ID" value={ppmId(requirement)} link /><InfoPair label="Domain" value={requirement?.telecom_domain || requirement?.qa_domain || "Not classified"} /><InfoPair label="Owner" value={journey.ownerId ? `User #${journey.ownerId}` : "Unassigned"} /></div></Panel>
    <Panel title="AI Summary"><p className="text-[10px] font-semibold leading-5 text-slate-600">This graph is derived from the project&apos;s approved requirements, linked scenarios, test cases, applications, evidence requirements and review records.</p><p className="mt-2 text-[9px] font-bold text-purple-700">{aiScore == null ? "No persisted scenario test-case set review is available." : `Scenario test-case set review: ${aiScore.toFixed(1)}/5 (${aiScorePercent}%)`}</p></Panel>
    <Panel title="Readiness Snapshot"><div className="grid grid-cols-4 gap-2"><Ring label="Coverage" value={journey.coverage} /><Ring label="Evidence" value={journey.evidenceCoverage} /><Ring label="Applications" value={journey.applicationCoverage} /><Ring label="Approval" value={journey.approvalReadiness} locked={journey.gaps.length > 0} /></div></Panel>
  </>;
}

function Ring({ label, value, locked }: { label: string; value: number; locked?: boolean }) { return <div className="text-center"><div className="mx-auto h-8 w-8 rounded-full p-1" style={{ background: locked ? "#fee2e2" : `conic-gradient(${value >= 75 ? "#10b981" : "#f59e0b"} ${value * 3.6}deg, #e5e7eb 0deg)` }}><div className="flex h-full w-full items-center justify-center rounded-full bg-white text-[7px] font-extrabold text-slate-700">{locked ? "Gated" : `${value}%`}</div></div><p className="mt-1 text-[8px] font-bold text-slate-500">{label}</p></div>; }

function CoverageInspector({ journey, unlinkedCases, linkFormOpen, setLinkFormOpen, linkCaseId, setLinkCaseId, linkScenarioId, setLinkScenarioId, onLink, busy }: { journey: JourneyRecord; unlinkedCases: TestCase[]; linkFormOpen: boolean; setLinkFormOpen: (value: boolean) => void; linkCaseId: string; setLinkCaseId: (value: string) => void; linkScenarioId: string; setLinkScenarioId: (value: string) => void; onLink: () => void; busy: string }) {
  return <>
    <Panel title="Scenario Coverage"><div className="space-y-3">{REQUIRED_SCENARIO_KINDS.map((kind) => { const count = journey.scenarios.filter((item) => scenarioKind(item) === kind).length; return <div key={kind} className="flex items-center justify-between text-[10px] font-semibold"><span className="capitalize text-slate-600">{kind}</span><span className={cn("rounded-md px-2 py-0.5 font-bold", count ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600")}>{count}</span></div>; })}</div></Panel>
    <Panel title="Traceability"><div className="space-y-2 text-[10px] font-semibold text-slate-600"><p>{journey.requirements.length} requirement(s)</p><p>{journey.scenarios.length} scenario(s)</p><p>{journey.testCases.length} linked test case(s)</p></div><button onClick={() => setLinkFormOpen(!linkFormOpen)} className="mt-3 flex items-center gap-1 text-[10px] font-bold text-[#1b59f8]"><Link2 className="h-3.5 w-3.5" />Link Existing Test Case</button></Panel>
    {linkFormOpen && <Panel title="Link Existing Test Case"><div className="space-y-2"><select aria-label="Unlinked test case" value={linkCaseId} onChange={(event) => setLinkCaseId(event.target.value)} className="h-9 w-full rounded-md border border-slate-200 px-2 text-[10px]"><option value="">Select unlinked test case</option>{unlinkedCases.map((item) => <option key={item.id} value={item.id}>{item.test_case_id} — {item.title}</option>)}</select><select aria-label="Target scenario" value={linkScenarioId} onChange={(event) => setLinkScenarioId(event.target.value)} className="h-9 w-full rounded-md border border-slate-200 px-2 text-[10px]"><option value="">Select target scenario</option>{journey.scenarios.map((item) => <option key={item.id} value={item.id}>{item.scenario_id} — {item.title}</option>)}</select><Button onClick={onLink} disabled={!linkCaseId || !linkScenarioId || busy === "link"} className="h-9 w-full bg-[#1b59f8] text-[10px] font-bold text-white">Save Link</Button></div></Panel>}
  </>;
}

function ApplicationsInspector({ projectId, journey, applications, availableEnvironments, environment, setEnvironment, mappingFormOpen, setMappingFormOpen, applicationId, setApplicationId, onResolve, busy }: { projectId: number; journey: JourneyRecord; applications: ProjectApplication[]; availableEnvironments: string[]; environment: string; setEnvironment: (value: string) => void; mappingFormOpen: boolean; setMappingFormOpen: (value: boolean) => void; applicationId: string; setApplicationId: (value: string) => void; onResolve: () => void; busy: string }) {
  return <>
    <Panel title="Mapped Applications"><div className="space-y-2">{journey.applications.map((item) => <div key={item.key} className="rounded-md border border-cyan-100 bg-cyan-50/50 p-2"><p className="text-[10px] font-extrabold text-slate-800">{item.name}</p><p className="mt-1 text-[9px] font-semibold text-slate-500">Registry key: {item.key}</p><p className="mt-1 text-[9px] font-semibold text-slate-500">{Object.keys(item.environment_urls).length} environment URL(s)</p></div>)}{!journey.applications.length && <p className="text-[10px] font-semibold text-red-600">No active application is mapped.</p>}</div></Panel>
    <Panel title="Discovery Environment"><select aria-label="Discovery environment" value={environment} onChange={(event) => setEnvironment(event.target.value)} className="h-9 w-full rounded-md border border-slate-200 px-2 text-[10px]"><option value="QA">QA</option>{availableEnvironments.filter((item) => item !== "QA").map((item) => <option key={item} value={item}>{item}</option>)}</select></Panel>
    <button aria-label="Open application mapping form" onClick={() => setMappingFormOpen(!mappingFormOpen)} className="flex items-center gap-1 text-[10px] font-bold text-[#1b59f8]"><Link2 className="h-3.5 w-3.5" />Resolve Application Mapping</button>
    {mappingFormOpen && <Panel title="Resolve Mapping"><select aria-label="Application mapping" value={applicationId} onChange={(event) => setApplicationId(event.target.value)} className="h-9 w-full rounded-md border border-slate-200 px-2 text-[10px]"><option value="">Select application</option>{applications.filter((item) => item.id != null).map((item) => <option key={item.key} value={String(item.id)}>{item.name}</option>)}</select><Button onClick={onResolve} disabled={!applicationId || busy === "mapping"} className="mt-2 h-9 w-full bg-[#1b59f8] text-[10px] font-bold text-white">Apply Mapping</Button></Panel>}
    <Button variant="outline" onClick={() => window.open(`/settings?project=${projectId}`, "_self")} className="h-9 w-full gap-2 text-[10px] font-bold"><ExternalLink className="h-3.5 w-3.5" />Open Application Registry</Button>
  </>;
}

function EvidenceInspector({ journey, evidenceFormOpen, setEvidenceFormOpen, evidenceText, setEvidenceText, onSave, busy }: { journey: JourneyRecord; evidenceFormOpen: boolean; setEvidenceFormOpen: (value: boolean) => void; evidenceText: string; setEvidenceText: (value: string) => void; onSave: () => void; busy: string }) {
  const evidence = Array.from(new Set(journey.testCases.flatMap(evidenceRequirements)));
  return <><Panel title="Evidence Requirements"><div className="space-y-2">{evidence.map((item) => <div key={item} className="flex items-start gap-2 rounded-md border border-purple-100 bg-purple-50/50 p-2 text-[10px] font-semibold text-slate-700"><FileCheck2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-purple-600" />{item}</div>)}{!evidence.length && <p className="text-[10px] font-semibold text-red-600">No evidence requirements are attached.</p>}</div></Panel><button aria-label="Open evidence requirement form" onClick={() => setEvidenceFormOpen(!evidenceFormOpen)} className="flex items-center gap-1 text-[10px] font-bold text-[#1b59f8]"><Plus className="h-3.5 w-3.5" />Add Evidence Requirement</button>{evidenceFormOpen && <Panel title="New Evidence Requirement"><textarea aria-label="Evidence requirement" value={evidenceText} onChange={(event) => setEvidenceText(event.target.value)} placeholder="Describe the required screenshot, log, trace or audit evidence." className="min-h-20 w-full rounded-md border border-slate-200 p-2 text-[10px] outline-none focus:border-blue-300" /><Button onClick={onSave} disabled={!evidenceText.trim() || busy === "evidence"} className="mt-2 h-9 w-full bg-[#1b59f8] text-[10px] font-bold text-white">Save Evidence Requirement</Button></Panel>}</>;
}

function AutomationInspector({ journey, selectedNode, classifications, enabled }: { journey: JourneyRecord; selectedNode: SelectedNode | null; classifications: Map<number, TestCaseAutomationClassification>; enabled: boolean }) {
  if (!enabled) return <Panel title="Automation Classification"><p className="text-[10px] font-semibold text-slate-400">Automation classification is not enabled for this project.</p></Panel>;

  const focusedCase = selectedNode?.type === "test_case" ? journey.testCases.find((item) => item.test_case_id === selectedNode.id) : undefined;
  const focusedClassification = focusedCase ? classifications.get(focusedCase.id) : undefined;

  if (focusedCase) {
    if (!focusedClassification) {
      return <Panel title={`Automation Classification — ${focusedCase.test_case_id}`}><p className="text-[10px] font-semibold text-slate-400">Not yet classified. Classify from Generated Test Cases.</p></Panel>;
    }
    return <>
      <Panel title={`Automation Classification — ${focusedCase.test_case_id}`}>
        <div className="grid grid-cols-2 gap-3"><InfoPair label="Candidate status" value={focusedClassification.candidate_status.replace(/_/g, " ")} /><InfoPair label="Primary adapter" value={focusedClassification.primary_adapter || "Not resolved"} /><InfoPair label="Discovery" value={focusedClassification.discovery_required ? (focusedClassification.recommended_discovery_mode || "Required") : "Not required"} /><InfoPair label="Policy version" value={focusedClassification.policy_version ? `v${focusedClassification.policy_version}` : "—"} /></div>
      </Panel>
      <Panel title="Mandatory / Optional Validators"><div className="flex flex-wrap gap-1.5">{focusedClassification.mandatory_validators.map((item) => <span key={`m-${item}`} className="rounded-md border border-red-200 bg-red-50 px-2 py-0.5 text-[9px] font-bold text-red-700">{item}</span>)}{focusedClassification.optional_validators.map((item) => <span key={`o-${item}`} className="rounded-md border border-blue-200 bg-blue-50 px-2 py-0.5 text-[9px] font-bold text-blue-700">{item}</span>)}{!focusedClassification.mandatory_validators.length && !focusedClassification.optional_validators.length && <span className="text-[9px] font-semibold text-slate-400">None declared</span>}</div></Panel>
      {focusedClassification.deterministic_blockers.length > 0 && <Panel title="Missing Capabilities / Blockers" tone="red"><ul className="list-disc space-y-1 pl-4 text-[9px] font-semibold text-red-700">{focusedClassification.deterministic_blockers.map((item, index) => <li key={`${item.code}-${index}`}>{item.label}: {item.detail} — remediate before discovery.</li>)}</ul></Panel>}
      {focusedClassification.required_evidence.length > 0 && <Panel title="Required Evidence"><div className="flex flex-wrap gap-1.5">{focusedClassification.required_evidence.map((item) => <span key={item} className="rounded-md border border-purple-200 bg-purple-50 px-2 py-0.5 text-[9px] font-bold text-purple-700">{item}</span>)}</div></Panel>}
    </>;
  }

  return <Panel title="Automation Classification — Journey Summary">
    <div className="space-y-2">
      {journey.testCases.filter((item) => item.automation_candidate).map((item) => {
        const cls = classifications.get(item.id);
        return <div key={item.id} className="flex items-center justify-between text-[10px] font-semibold">
          <span className="text-slate-700">{item.test_case_id}</span>
          <span className={cn("rounded-md px-2 py-0.5 font-bold", classificationBadgeTone(cls?.candidate_status))}>{cls ? cls.candidate_status.replace(/_/g, " ") : "Not evaluated"}</span>
        </div>;
      })}
      {!journey.testCases.some((item) => item.automation_candidate) && <p className="text-[10px] font-semibold text-slate-400">No automation candidates in this journey.</p>}
    </div>
  </Panel>;
}

function classificationBadgeTone(status: string | undefined): string {
  if (status === "RECOMMENDED" || status === "APPROVED") return "bg-emerald-50 text-emerald-700";
  if (status === "CONDITIONAL" || status === "DEFERRED" || status === "POLICY_STALE" || status === "RECLASSIFICATION_REQUIRED") return "bg-amber-50 text-amber-700";
  if (status === "NOT_RECOMMENDED" || status === "BLOCKED") return "bg-red-50 text-red-700";
  return "bg-slate-100 text-slate-500";
}

function ActivityInspector({ journey, reviews, approvals }: { journey: JourneyRecord; reviews: ArtifactReview[]; approvals: ApprovalAction[] }) {
  const caseIds = new Set(journey.testCases.map((item) => item.id));
  const scenarioIds = new Set(journey.scenarios.map((item) => item.id));
  const entries = [
    ...reviews
      .filter((item) => item.artifact_type === "scenario_test_case_coverage" && scenarioIds.has(item.artifact_id))
      .map((item) => ({
        time: item.created_at,
        actor: item.reviewer_agent,
        text: `Scenario test-case set review ${item.verdict.replace("_", " ")}${typeof item.overall_score === "number" ? ` · ${item.overall_score.toFixed(1)}/5` : ""}`,
      })),
    ...approvals.filter((item) => item.entity_type === "test_case" && caseIds.has(item.entity_id)).map((item) => ({ time: item.created_at, actor: item.actor_role || `User #${item.user_id}`, text: `Approval ${item.decision}` })),
  ].sort((a, b) => b.time.localeCompare(a.time));
  return <Panel title="Audit Activity"><div className="space-y-3">{entries.slice(0, 12).map((entry, index) => <div key={`${entry.time}-${index}`} className="relative pl-4 text-[10px]"><span className="absolute left-0 top-1 h-2 w-2 rounded-full bg-[#1b59f8]" /><p className="font-bold text-slate-500">{displayDate(entry.time)}</p><p className="mt-0.5 font-extrabold text-slate-800">{entry.actor}</p><p className="font-semibold text-slate-600">{entry.text}</p></div>)}{!entries.length && <p className="text-[10px] font-semibold text-slate-500">No persisted review or approval activity is available for these test cases.</p>}</div></Panel>;
}

function GapCount({ label, value, tone }: { label: string; value: number; tone: "red" | "amber" | "yellow" | "blue" }) { const tones = { red: "border-red-200 bg-red-50 text-red-700", amber: "border-orange-200 bg-orange-50 text-orange-700", yellow: "border-amber-200 bg-amber-50 text-amber-700", blue: "border-blue-200 bg-blue-50 text-blue-700" }; return <div className={cn("rounded-md border p-2 text-center", tones[tone])}><p className="text-[8px] font-bold">{label}</p><p className="mt-1 text-base font-extrabold">{value}</p></div>; }
