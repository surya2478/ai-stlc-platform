"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  AlertTriangle,
  Bot,
  CheckCircle,
  Clock,
  ExternalLink,
  FileText,
  History,
  Link2,
  Loader2,
  PlayCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  Wrench,
  ChevronRight,
  X,
  Info,
  Terminal,
  Settings
} from "lucide-react";
import {
  automationApi,
  projectsApi,
  testCasesApi,
  type AutomationScript,
  type AutomationTestMapping,
  type ExecutionResult,
  type Project,
  type TestCase,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerDescription,
  DrawerBody,
  DrawerFooter
} from "@/components/ui/drawer";

// Status Chip Variant Mapping
function getStatusVariant(status: string | null | undefined): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" {
  if (!status) return "outline";
  const s = status.toLowerCase();
  if (["passed", "success", "completed", "synced", "yes"].includes(s)) return "success";
  if (["failed", "error", "rejected", "no"].includes(s)) return "destructive";
  if (["blocked", "in_progress", "running", "queued", "pending", "requested"].includes(s)) return "warning";
  if (["skipped", "deferred", "manual", "kept for later"].includes(s)) return "secondary";
  if (["automated", "hybrid", "active", "visible"].includes(s)) return "purple";
  return "outline";
}

function messageFromError(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => item?.msg ?? String(item)).join("; ");
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

type MappingForm = {
  external_tool_name: string;
  external_project_id: string;
  external_suite_id: string;
  external_test_case_id: string;
  external_script_id: string;
};

const emptyMappingForm: MappingForm = {
  external_tool_name: "Mock",
  external_project_id: "",
  external_suite_id: "",
  external_test_case_id: "",
  external_script_id: "",
};

function AutomationContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProject = Number(searchParams.get("project")) || null;

  const [projects, setProjects] = useState<Project[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [mappings, setMappings] = useState<AutomationTestMapping[]>([]);
  const [scripts, setScripts] = useState<AutomationScript[]>([]);
  const [latestResults, setLatestResults] = useState<Record<number, ExecutionResult | undefined>>({});
  
  // States
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [environment, setEnvironment] = useState("staging");
  const [showAiScripts, setShowAiScripts] = useState(false);

  // Drawer States
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedTestCase, setSelectedTestCase] = useState<TestCase | null>(null);
  const [drawerTab, setDrawerTab] = useState<"mapping" | "history">("mapping");
  const [mappingForm, setMappingForm] = useState<MappingForm>(emptyMappingForm);
  const [historyRows, setHistoryRows] = useState<ExecutionResult[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Load Projects on mount
  useEffect(() => {
    projectsApi.list().then((res) => {
      setProjects(res.data);
      if (res.data.length > 0 && !searchParams.get("project")) {
        const params = new URLSearchParams(searchParams.toString());
        params.set("project", String(res.data[0].id));
        router.push(`${pathname}?${params.toString()}`);
      }
    }).catch(() => setError("Could not load projects."));
  }, [searchParams]);

  // Load Data
  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    setError("");
    try {
      const [casesRes, mappingsRes, scriptsRes] = await Promise.all([
        testCasesApi.list(selectedProject, { status: "approved", automation_only: true }),
        automationApi.getAutomationMappings(selectedProject),
        automationApi.list(selectedProject),
      ]);
      setTestCases(casesRes.data);
      setMappings(mappingsRes.data);
      setScripts(scriptsRes.data);

      const candidateIds = casesRes.data
        .filter(isAutomationVisible)
        .map((tc) => tc.id);
      
      const historyPairs = await Promise.all(
        candidateIds.map(async (id) => {
          try {
            const history = await automationApi.getExecutionHistory(id);
            return [id, history.data[0]] as const;
          } catch {
            return [id, undefined] as const;
          }
        })
      );
      setLatestResults(Object.fromEntries(historyPairs));
    } catch (loadError) {
      setError(messageFromError(loadError, "Could not load automation control data."));
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Reset states on project change
  useEffect(() => {
    setDrawerOpen(false);
    setSelectedTestCase(null);
    setHistoryRows([]);
    setNotice("");
    setError("");
  }, [selectedProject]);

  // Load History when Drawer active tab is history
  useEffect(() => {
    if (selectedTestCase && drawerTab === "history" && drawerOpen) {
      setHistoryLoading(true);
      automationApi.getExecutionHistory(selectedTestCase.id)
        .then((res) => setHistoryRows(res.data))
        .catch(() => setError("Could not load execution history."))
        .finally(() => setHistoryLoading(false));
    }
  }, [selectedTestCase, drawerTab, drawerOpen]);

  const mappingByTestCase = useMemo(() => {
    const result = new Map<number, AutomationTestMapping>();
    mappings.forEach((mapping) => {
      if (mapping.is_active && !result.has(mapping.test_case_id)) {
        result.set(mapping.test_case_id, mapping);
      }
    });
    return result;
  }, [mappings]);

  const rows = useMemo(
    () =>
      testCases
        .filter(isAutomationVisible)
        .filter((tc) => {
          const q = search.trim().toLowerCase();
          return !q || tc.test_case_id.toLowerCase().includes(q) || tc.title.toLowerCase().includes(q);
        }),
    [testCases, search]
  );

  function handleRowClick(tc: TestCase) {
    const mapping = mappingByTestCase.get(tc.id);
    setSelectedTestCase(tc);
    setDrawerTab(mapping ? "history" : "mapping");
    setMappingForm(
      mapping
        ? {
            external_tool_name: mapping.external_tool_name,
            external_project_id: mapping.external_project_id ?? "",
            external_suite_id: mapping.external_suite_id ?? "",
            external_test_case_id: mapping.external_test_case_id,
            external_script_id: mapping.external_script_id ?? "",
          }
        : {
            ...emptyMappingForm,
            external_project_id: selectedProject ? `PROJECT-${selectedProject}` : "",
            external_suite_id: "REGRESSION",
            external_test_case_id: tc.test_case_id,
          }
    );
    setDrawerOpen(true);
  }

  async function handleSaveMapping(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProject || !selectedTestCase) return;
    if (!mappingForm.external_tool_name.trim() || !mappingForm.external_test_case_id.trim()) {
      setError("External tool and external automated test case ID are required.");
      return;
    }
    setBusyId(selectedTestCase.id);
    setError("");
    setNotice("");
    try {
      const existing = mappingByTestCase.get(selectedTestCase.id);
      const payload = {
        project_id: selectedProject,
        test_case_id: selectedTestCase.id,
        external_tool_name: mappingForm.external_tool_name.trim(),
        external_project_id: mappingForm.external_project_id.trim() || undefined,
        external_suite_id: mappingForm.external_suite_id.trim() || undefined,
        external_test_case_id: mappingForm.external_test_case_id.trim(),
        external_script_id: mappingForm.external_script_id.trim() || undefined,
        automation_status: "automated",
        is_active: true,
      };
      if (existing) {
        await automationApi.updateAutomationMapping(existing.id, payload);
      } else {
        await automationApi.createAutomationMapping(payload);
      }
      setNotice("Automation mapping saved.");
      setDrawerOpen(false);
      await loadData();
    } catch (saveError) {
      setError(messageFromError(saveError, "Could not save automation mapping."));
    } finally {
      setBusyId(null);
    }
  }

  async function handleRunAutomation(tc: TestCase) {
    if (!selectedProject) return;
    setBusyId(tc.id);
    setError("");
    setNotice("");
    try {
      const response = await automationApi.runExternalAutomation(selectedProject, [tc.id], environment);
      setNotice(`${response.data.message} Run ${response.data.external_run_id}`);
      await loadData();
      // If drawer is open, switch to history tab to see new runs
      if (drawerOpen && selectedTestCase?.id === tc.id) {
        setDrawerTab("history");
        // Reload history manually
        setHistoryLoading(true);
        automationApi.getExecutionHistory(tc.id)
          .then((res) => setHistoryRows(res.data))
          .catch(() => setError("Could not load execution history."))
          .finally(() => setHistoryLoading(false));
      }
    } catch (runError) {
      setError(messageFromError(runError, "Could not run external automation."));
    } finally {
      setBusyId(null);
    }
  }

  async function handleSyncAutomation(mapping: AutomationTestMapping) {
    setBusyId(mapping.test_case_id);
    setError("");
    setNotice("");
    try {
      const response = await automationApi.syncExternalAutomationResult(mapping.id, environment);
      setNotice(`${response.data.message} Run ${response.data.external_run_id}`);
      await loadData();
      if (drawerOpen && selectedTestCase?.id === mapping.test_case_id) {
        setDrawerTab("history");
        setHistoryLoading(true);
        automationApi.getExecutionHistory(mapping.test_case_id)
          .then((res) => setHistoryRows(res.data))
          .catch(() => setError("Could not load execution history."))
          .finally(() => setHistoryLoading(false));
      }
    } catch (syncError) {
      setError(messageFromError(syncError, "Could not sync automation result."));
    } finally {
      setBusyId(null);
    }
  }

  async function handleSyncJira(tc: TestCase) {
    const status = window.prompt("Enter Jira final execution status", latestResults[tc.id]?.jira_execution_status || "passed");
    if (!status) return;
    setBusyId(tc.id);
    setError("");
    setNotice("");
    try {
      await automationApi.syncJiraExecutionStatus({
        test_case_id: tc.id,
        jira_execution_status: status,
        jira_issue_key: tc.jira_issue_key,
        jira_test_key: tc.jira_test_key,
      });
      setNotice("Jira final execution status synced.");
      await loadData();
      if (drawerOpen && selectedTestCase?.id === tc.id) {
        setDrawerTab("history");
        setHistoryLoading(true);
        automationApi.getExecutionHistory(tc.id)
          .then((res) => setHistoryRows(res.data))
          .catch(() => setError("Could not load execution history."))
          .finally(() => setHistoryLoading(false));
      }
    } catch (jiraError) {
      setError(messageFromError(jiraError, "Could not sync Jira execution status."));
    } finally {
      setBusyId(null);
    }
  }

  const total = rows.length;
  const mapped = rows.filter((tc) => mappingByTestCase.has(tc.id)).length;
  const pendingJira = rows.filter((tc) => !latestResults[tc.id]?.jira_execution_status).length;
  const aiScripts = scripts.length;

  const mappedPct = total > 0 ? ((mapped / total) * 100).toFixed(1) : "0.0";
  const pendingJiraPct = total > 0 ? ((pendingJira / total) * 100).toFixed(1) : "0.0";

  const metrics = [
    {
      title: "Automation Rows",
      icon: Wrench,
      iconBg: "bg-blue-50 border-blue-100",
      iconColor: "text-blue-500",
      value: total.toLocaleString(),
      sublabel: "Eligible",
      footer: "100% of automated eligible cases",
    },
    {
      title: "Mapped Tests",
      icon: Link2,
      iconBg: "bg-emerald-50 border-emerald-100",
      iconColor: "text-emerald-500",
      value: mapped.toLocaleString(),
      sublabel: "Mapped",
      footer: `${mappedPct}% of eligible mapped to tool`,
    },
    {
      title: "Pending Jira Sync",
      icon: Clock,
      iconBg: "bg-amber-50 border-amber-100",
      iconColor: "text-amber-500",
      value: pendingJira.toLocaleString(),
      sublabel: "Unsynced",
      footer: `${pendingJiraPct}% sync remaining`,
    },
    {
      title: "AI Scripts Kept",
      icon: Bot,
      iconBg: "bg-purple-50 border-purple-100",
      iconColor: "text-purple-500",
      value: aiScripts.toLocaleString(),
      sublabel: "Scripts",
      footer: "AI generated helper scripts",
    },
  ];

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Global Controls ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-blue-50 border border-blue-100 p-2.5">
            <Wrench className="h-6 w-6 text-[#1b59f8]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Automation Control Center</h1>
            <p className="text-xs text-slate-500 mt-1">Map internal test cases to external automation tools and view live runs and Jira QA compliance status</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedProject ?? ""}
            onChange={(e) => {
              const val = e.target.value;
              const params = new URLSearchParams(searchParams.toString());
              params.set("project", val);
              router.push(`${pathname}?${params.toString()}`);
            }}
            className="appearance-none bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 rounded-lg text-xs font-semibold px-3 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-[#1b59f8] transition-colors cursor-pointer"
            style={{
              backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
              backgroundPosition: 'right 0.5rem center',
              backgroundSize: '1.25rem 1.25rem',
              backgroundRepeat: 'no-repeat',
            }}
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>

          <select
            value={environment}
            onChange={(e) => setEnvironment(e.target.value)}
            className="appearance-none bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 rounded-lg text-xs font-semibold px-3 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-[#1b59f8] transition-colors cursor-pointer"
            style={{
              backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
              backgroundPosition: 'right 0.5rem center',
              backgroundSize: '1.25rem 1.25rem',
              backgroundRepeat: 'no-repeat',
            }}
          >
            {["development", "staging", "production", "ci"].map((env) => (
              <option key={env} value={env}>
                {env.toUpperCase()}
              </option>
            ))}
          </select>

          <Button variant="outline" size="sm" onClick={loadData} className="h-8 w-8 p-0 border-slate-200">
            <RefreshCw className={cn("h-3.5 w-3.5 text-slate-500", loading && "animate-spin")} />
          </Button>
        </div>
      </div>

      {/* ── Metric Cards ───────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {metrics.map((card) => {
          const Icon = card.icon;
          return (
            <Card key={card.title} className="border-slate-200 hover:-translate-y-0.5 transition-all">
              <CardContent className="p-4 flex flex-col justify-between h-full space-y-3">
                <div className="flex items-center gap-2">
                  <div className={cn("rounded-lg p-1.5 flex items-center justify-center shrink-0 border", card.iconBg)}>
                    <Icon className={cn("h-4 w-4", card.iconColor)} />
                  </div>
                  <span className="text-xs font-bold text-slate-700 truncate">{card.title}</span>
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-slate-900">{card.value}</span>
                  {card.sublabel && (
                    <span className="text-[10px] font-bold text-slate-400">{card.sublabel}</span>
                  )}
                </div>
                <div className="text-[10px] text-slate-400 font-semibold border-t border-slate-50 pt-2">
                  {card.footer}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="flex-1 font-semibold">{error}</span>
          <button onClick={() => setError("")}><X className="h-4 w-4 text-red-400 hover:text-red-700" /></button>
        </div>
      )}
      {notice && (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-700">
          <CheckCircle className="h-4 w-4 shrink-0" />
          <span className="flex-1 font-semibold">{notice}</span>
          <button onClick={() => setNotice("")}><X className="h-4 w-4 text-emerald-400 hover:text-emerald-700" /></button>
        </div>
      )}

      {/* ── Search Input ───────────────────────────────────────────────────────── */}
      <div className="relative">
        <Search className="absolute left-3 top-2.5 h-4.5 w-4.5 text-slate-400" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-white hover:bg-slate-50/50 border border-slate-200 rounded-lg text-xs font-semibold pl-10 pr-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-[#1b59f8] transition-colors"
          placeholder="Search test cases by ID or title..."
        />
      </div>

      {/* ── Automation Table ───────────────────────────────────────────────────── */}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-full text-left border-collapse text-xs select-none">
          <thead className="bg-slate-50/70 border-b border-slate-200 text-[10px] font-bold uppercase tracking-wider text-slate-400">
            <tr>
              <th className="px-4 py-2.5">TC ID</th>
              <th className="px-4 py-2.5">Name</th>
              <th className="px-4 py-2.5">Mode</th>
              <th className="px-4 py-2.5">Eligible</th>
              <th className="px-4 py-2.5">Mapping Status</th>
              <th className="px-4 py-2.5">Tool</th>
              <th className="px-4 py-2.5">Suite ID</th>
              <th className="px-4 py-2.5">Ext ID</th>
              <th className="px-4 py-2.5">Last Run</th>
              <th className="px-4 py-2.5">Jira Final</th>
              <th className="px-4 py-2.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-600 font-medium">
            {loading ? (
              <tr>
                <td colSpan={11} className="px-4 py-16 text-center text-slate-400 font-semibold">
                  <Loader2 className="inline mr-2 h-4 w-4 animate-spin text-[#1b59f8]" />
                  Loading automated test case registry...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={11} className="px-4 py-16 text-center text-slate-400 font-semibold">
                  No automation-eligible test cases found.
                </td>
              </tr>
            ) : (
              rows.map((tc) => {
                const mapping = mappingByTestCase.get(tc.id);
                const latest = latestResults[tc.id];
                const isSelected = selectedTestCase?.id === tc.id;
                return (
                  <tr
                    key={tc.id}
                    onClick={() => handleRowClick(tc)}
                    className={cn(
                      "hover:bg-slate-50/50 cursor-pointer transition-colors",
                      isSelected && "bg-[#1b59f8]/5"
                    )}
                  >
                    <td className="px-4 py-2.5 font-mono text-[11px] font-bold text-[#1b59f8]">{tc.test_case_id}</td>
                    <td className="px-4 py-2.5 max-w-[200px] truncate">
                      <p className="font-bold text-slate-800 text-xs">{tc.title}</p>
                      <p className="text-[10px] text-slate-400 truncate mt-0.5">{tc.jira_issue_key || "No Jira key"}</p>
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge variant={getStatusVariant(tc.execution_mode)}>
                        {tc.execution_mode}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge variant={getStatusVariant(tc.automation_eligible)}>
                        {tc.automation_eligible}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge variant={mapping ? "purple" : "warning"}>
                        {mapping ? "Mapped" : "Required"}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5 text-slate-700">{mapping?.external_tool_name ?? "-"}</td>
                    <td className="px-4 py-2.5 text-slate-700">{mapping?.external_suite_id ?? "-"}</td>
                    <td className="px-4 py-2.5 font-mono text-[10px] text-slate-500">{mapping?.external_test_case_id ?? "-"}</td>
                    <td className="px-4 py-2.5">
                      <Badge variant={getStatusVariant(latest?.automation_execution_status)}>
                        {latest?.automation_execution_status ?? "Pending"}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge variant={getStatusVariant(latest?.jira_execution_status)}>
                        {latest?.jira_execution_status ?? "Unsynced"}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleRowClick(tc)}
                        className="h-7 px-3 text-xs border-slate-200"
                      >
                        Actions
                        <ChevronRight className="h-3 w-3 text-slate-400" />
                      </Button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* ── Details & Control Drawer ───────────────────────────────────────────── */}
      <Drawer open={drawerOpen} onOpenChange={setDrawerOpen}>
        <DrawerContent size="lg">
          {selectedTestCase && (
            <>
              <DrawerHeader>
                <div className="flex items-center gap-2">
                  <Terminal className="h-5 w-5 text-[#1b59f8]" />
                  <div className="min-w-0">
                    <DrawerTitle className="truncate">Automated Case: {selectedTestCase.test_case_id}</DrawerTitle>
                    <DrawerDescription className="truncate">{selectedTestCase.title}</DrawerDescription>
                  </div>
                </div>
                <button onClick={() => setDrawerOpen(false)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-50"><X className="h-4 w-4" /></button>
              </DrawerHeader>

              {/* Action Buttons Hub inside Drawer */}
              <div className="bg-slate-50 border-b border-slate-100 p-4 flex flex-wrap gap-2">
                <Button
                  variant="default"
                  size="sm"
                  disabled={busyId === selectedTestCase.id || !mappingByTestCase.has(selectedTestCase.id)}
                  onClick={() => handleRunAutomation(selectedTestCase)}
                  className="text-xs font-semibold h-8"
                >
                  <PlayCircle className="h-3.5 w-3.5 mr-1" />
                  Run Test
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busyId === selectedTestCase.id || !mappingByTestCase.has(selectedTestCase.id)}
                  onClick={() => {
                    const m = mappingByTestCase.get(selectedTestCase.id);
                    if (m) handleSyncAutomation(m);
                  }}
                  className="text-xs font-semibold h-8 border-slate-200 text-slate-600 bg-white"
                >
                  <RefreshCw className={cn("h-3.5 w-3.5 mr-1", busyId === selectedTestCase.id && "animate-spin")} />
                  Sync Agent Result
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busyId === selectedTestCase.id}
                  onClick={() => handleSyncJira(selectedTestCase)}
                  className="text-xs font-semibold h-8 border-slate-200 text-slate-600 bg-white"
                >
                  <ShieldCheck className="h-3.5 w-3.5 mr-1" />
                  Sync Jira QA Status
                </Button>
              </div>

              {/* Tab Selector */}
              <div className="flex border-b border-slate-100 px-4 bg-white shrink-0">
                <button
                  onClick={() => setDrawerTab("mapping")}
                  className={cn(
                    "px-4 py-2.5 text-xs font-bold border-b-2 transition-colors",
                    drawerTab === "mapping" ? "border-[#1b59f8] text-[#1b59f8]" : "border-transparent text-slate-500 hover:text-slate-900"
                  )}
                >
                  Mapping Configuration
                </button>
                <button
                  onClick={() => setDrawerTab("history")}
                  className={cn(
                    "px-4 py-2.5 text-xs font-bold border-b-2 transition-colors",
                    drawerTab === "history" ? "border-[#1b59f8] text-[#1b59f8]" : "border-transparent text-slate-500 hover:text-slate-900"
                  )}
                >
                  Execution History
                </button>
              </div>

              <DrawerBody className="space-y-5">
                {drawerTab === "mapping" && (
                  <form onSubmit={handleSaveMapping} className="space-y-4">
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External Tool Name</label>
                      <input
                        value={mappingForm.external_tool_name}
                        onChange={(e) => setMappingForm((f) => ({ ...f, external_tool_name: e.target.value }))}
                        className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50"
                        placeholder="e.g. Playwright, Katalon, Pytest, Mock"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External Project ID</label>
                      <input
                        value={mappingForm.external_project_id}
                        onChange={(e) => setMappingForm((f) => ({ ...f, external_project_id: e.target.value }))}
                        className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50"
                        placeholder="e.g. BSS-ACTIVATIONS"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External Suite ID</label>
                      <input
                        value={mappingForm.external_suite_id}
                        onChange={(e) => setMappingForm((f) => ({ ...f, external_suite_id: e.target.value }))}
                        className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50"
                        placeholder="e.g. REGRESSION-SIT"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External automated test case ID</label>
                      <input
                        value={mappingForm.external_test_case_id}
                        onChange={(e) => setMappingForm((f) => ({ ...f, external_test_case_id: e.target.value }))}
                        className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50 font-mono"
                        placeholder="e.g. tc_activate_esim_01"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External Script ID (Optional)</label>
                      <input
                        value={mappingForm.external_script_id}
                        onChange={(e) => setMappingForm((f) => ({ ...f, external_script_id: e.target.value }))}
                        className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50 font-mono"
                        placeholder="e.g. scripts/activate_esim.py"
                      />
                    </div>

                    <div className="pt-2">
                      <Button
                        type="submit"
                        variant="default"
                        size="sm"
                        disabled={busyId === selectedTestCase.id}
                        className="w-full text-xs font-bold"
                      >
                        {busyId === selectedTestCase.id ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Link2 className="h-3.5 w-3.5 mr-1" />}
                        Save Mapping Config
                      </Button>
                    </div>
                  </form>
                )}

                {drawerTab === "history" && (
                  <div className="space-y-4">
                    {historyLoading ? (
                      <div className="flex flex-col items-center justify-center py-12 text-slate-400 text-xs font-semibold">
                        <Loader2 className="h-5 w-5 animate-spin text-[#1b59f8] mb-2" />
                        Loading execution history logs...
                      </div>
                    ) : historyRows.length === 0 ? (
                      <div className="text-center py-12 text-slate-400 font-semibold text-xs">
                        No automated runs recorded for this case.
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {historyRows.map((row) => (
                          <div key={row.id} className="rounded-lg border border-slate-150 p-3 bg-slate-50/50 space-y-2.5">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="text-[10px] font-mono text-slate-400">{new Date(row.created_at).toLocaleString()}</span>
                              <div className="flex gap-1.5">
                                <Badge variant={getStatusVariant(row.automation_execution_status ?? row.status)}>
                                  {row.automation_execution_status ?? row.status}
                                </Badge>
                                <Badge variant={getStatusVariant(row.jira_execution_status)}>
                                  Jira: {row.jira_execution_status ?? "Unsynced"}
                                </Badge>
                              </div>
                            </div>

                            {row.error_message && (
                              <div className="text-[11px] bg-red-50 border border-red-100 rounded p-2 text-red-700 font-semibold">
                                {row.error_message}
                              </div>
                            )}

                            {/* Evidence files */}
                            <div className="flex flex-wrap gap-1.5 pt-1">
                              {row.external_result_url && (
                                <a
                                  href={row.external_result_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="inline-flex items-center gap-1 bg-white hover:bg-slate-50 border border-slate-200 text-slate-600 rounded px-2 py-1 text-[10px] font-bold"
                                >
                                  <ExternalLink className="h-3 w-3" />
                                  External Report
                                </a>
                              )}
                              {row.log_url && (
                                <a
                                  href={row.log_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="inline-flex items-center gap-1 bg-white hover:bg-slate-50 border border-slate-200 text-slate-600 rounded px-2 py-1 text-[10px] font-bold"
                                >
                                  <FileText className="h-3 w-3" />
                                  Evidence logs
                                </a>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </DrawerBody>
              <DrawerFooter>
                <Button variant="outline" size="sm" onClick={() => setDrawerOpen(false)} className="w-full h-9 border-slate-200 bg-white">Close Detail</Button>
              </DrawerFooter>
            </>
          )}
        </DrawerContent>
      </Drawer>

      {/* ── AI Generated Scripts Section ────────────────────────────────────────── */}
      <section className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <button
          onClick={() => setShowAiScripts(!showAiScripts)}
          className="flex w-full items-center justify-between px-5 py-4 text-left hover:bg-slate-50/50 transition-colors"
        >
          <span className="inline-flex items-center gap-2 text-xs font-bold text-slate-800">
            <Bot className="h-4.5 w-4.5 text-violet-600" />
            AI-Generated Automation Scripts Repository
          </span>
          <Badge variant={showAiScripts ? "purple" : "secondary"}>
            {showAiScripts ? "Hide List" : `${scripts.length} Scripts`}
          </Badge>
        </button>
        {showAiScripts && (
          <div className="border-t border-slate-200 p-5 bg-slate-50/30">
            <p className="mb-4 text-xs text-slate-500 leading-relaxed font-semibold">
              Existing AI script generation capability is preserved. In this environment, run triggers route to mapped automation files.
            </p>
            <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
              {scripts.map((script) => (
                <div key={script.id} className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-xs">
                  <span className="font-mono text-[10px] font-bold text-[#1b59f8]">{script.script_id}</span>
                  <span className="truncate px-3 font-semibold text-slate-700">{script.file_path || "Generated Script"}</span>
                  <Badge variant={getStatusVariant(script.status)}>
                    {script.status}
                  </Badge>
                </div>
              ))}
              {scripts.length === 0 && (
                <p className="text-xs text-slate-400 font-semibold text-center py-6">No AI-generated scripts found.</p>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function isAutomationVisible(tc: TestCase) {
  return (tc.execution_mode || "").toLowerCase() === "automated" && (tc.automation_eligible || "").toLowerCase() === "yes";
}

export default function AutomationPage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-slate-400 text-xs font-semibold">
        <Loader2 className="h-6 w-6 animate-spin text-[#1b59f8] mr-2" />
        Loading Automation Center...
      </div>
    }>
      <AutomationContent />
    </Suspense>
  );
}
