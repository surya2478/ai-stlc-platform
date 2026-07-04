"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  Users, BarChart3, Calendar, ClipboardList, Activity, Clock, ShieldCheck,
  Cpu, FileSpreadsheet, AlertTriangle, Settings, RefreshCw, Plus, CheckCircle, XCircle, Search, Bot,
  Info, Database, Lock, Eye, Check, ChevronRight, HelpCircle
} from "lucide-react";
import axios from "axios";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";

// Standard global design token card styles
const cardClass = "rounded-xl border border-border bg-card p-6 shadow-sm transition-all duration-200 hover:shadow-md";

const SUBMENUS = [
  { id: "exec", label: "Executive Dashboard", icon: BarChart3 },
  { id: "directory", label: "Resource Directory", icon: Users },
  { id: "planning", label: "Daily Work Planning", icon: Calendar },
  { id: "capacity", label: "Team Capacity & Allocation", icon: Clock },
  { id: "taskboard", label: "Task Board", icon: ClipboardList },
  { id: "timeline", label: "Daily Activity Timeline", icon: Activity },
  { id: "utilization", label: "Effort & Delivery Evidence", icon: FileSpreadsheet },
  { id: "rtc", label: "RTC Defects & Changes", icon: Settings },
  { id: "rqm", label: "RQM Test Contribution", icon: Cpu },
  { id: "integrations", label: "Integration Hub", icon: Database },
  { id: "ai_estimate", label: "AI Estimate Intelligence", icon: Bot },
  { id: "reports", label: "Reports & Exports", icon: FileSpreadsheet },
  { id: "exceptions", label: "Exceptions & Data Quality", icon: AlertTriangle },
  { id: "governance", label: "Governance, Privacy & Audit", icon: ShieldCheck }
];

function ResourceIntelligenceContent() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project") || "1";

  const [activeTab, setActiveTab] = useState("exec");
  const [resources, setResources] = useState<any[]>([]);
  const [selectedResource, setSelectedResource] = useState<any>(null);
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [connections, setConnections] = useState<any[]>([]);
  const [timelineData, setTimelineData] = useState<any>({ events: [] });
  const [workPlans, setWorkPlans] = useState<any[]>([]);
  const [mappings, setMappings] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // AI Estimation states
  const [activityType, setActivityType] = useState("Manual Test Execution");
  const [complexity, setComplexity] = useState("Medium");
  const [numTestCases, setNumTestCases] = useState(10);
  const [scopeDetails, setScopeDetails] = useState("");
  const [aiResult, setAiResult] = useState<any>(null);
  const [aiLoading, setAiLoading] = useState(false);

  // New Daily Plan state
  const [newPlanTitle, setNewPlanTitle] = useState("");
  const [newPlanEst, setNewPlanEst] = useState(4);
  const [newPlanType, setNewPlanType] = useState("Manual Test Execution");

  // New Connection state
  const [newConnName, setNewConnName] = useState("");
  const [newConnUrl, setNewConnUrl] = useState("");
  const [newConnType, setNewConnType] = useState("Jira");
  const [newConnUser, setNewConnUser] = useState("");
  const [newConnPass, setNewConnPass] = useState("");

  useEffect(() => {
    fetchDashboard();
    fetchResources();
    fetchConnections();
    fetchMappings();
  }, [projectId]);

  const fetchDashboard = async () => {
    try {
      const res = await axios.get(`/api/v1/resource-operations/dashboard?project_id=${projectId}`);
      setDashboardData(res.data);
    } catch (err) {
      console.error("Failed to load dashboard data", err);
    }
  };

  const fetchResources = async () => {
    try {
      const res = await axios.get("/api/v1/resource-operations/resources");
      setResources(res.data);
      if (res.data.length > 0 && !selectedResource) {
        setSelectedResource(res.data[0]);
        fetchResourceTimeline(res.data[0].person_id);
      }
    } catch (err) {
      console.error("Failed to load resources", err);
    }
  };

  const fetchConnections = async () => {
    try {
      const res = await axios.get(`/api/v1/resource-operations/connections?project_id=${projectId}`);
      setConnections(res.data);
    } catch (err) {
      console.error("Failed to load connections", err);
    }
  };

  const fetchMappings = async () => {
    try {
      const res = await axios.get("/api/v1/resource-operations/mappings");
      setMappings(res.data);
    } catch (err) {
      console.error("Failed to load mappings", err);
    }
  };

  const fetchResourceTimeline = async (resId: string) => {
    try {
      const todayStr = new Date().toISOString().split("T")[0];
      const res = await axios.get(`/api/v1/resource-operations/timeline?resource_id=${resId}&date_val=${todayStr}`);
      setTimelineData(res.data);
      const plansRes = await axios.get(`/api/v1/resource-operations/work-plans?resource_id=${resId}&date_val=${todayStr}`);
      setWorkPlans(plansRes.data);
    } catch (err) {
      console.error("Failed to load timeline", err);
    }
  };

  const handleSelectResource = (res: any) => {
    setSelectedResource(res);
    fetchResourceTimeline(res.person_id);
  };

  const handleAddWorkPlan = async (e: any) => {
    e.preventDefault();
    if (!selectedResource || !newPlanTitle) return;
    try {
      const todayStr = new Date().toISOString().split("T")[0];
      await axios.post("/api/v1/resource-operations/work-plans", {
        date: todayStr,
        resource_id: selectedResource.person_id,
        project_id: Number(projectId),
        task_title: newPlanTitle,
        task_type: newPlanType,
        estimated_effort: Number(newPlanEst),
        status: "Planned"
      });
      setNewPlanTitle("");
      fetchResourceTimeline(selectedResource.person_id);
      fetchDashboard();
    } catch (err) {
      console.error("Failed to add work plan", err);
    }
  };

  const handleCreateConnection = async (e: any) => {
    e.preventDefault();
    try {
      await axios.post("/api/v1/resource-operations/connections", {
        project_id: Number(projectId),
        system_type: newConnType,
        name: newConnName,
        base_url: newConnUrl,
        username: newConnUser,
        password: newConnPass,
        is_active: true
      });
      setNewConnName("");
      setNewConnUrl("");
      setNewConnUser("");
      setNewConnPass("");
      fetchConnections();
    } catch (err) {
      console.error("Failed to create connection", err);
    }
  };

  const triggerSync = async (connId: number) => {
    try {
      await axios.post(`/api/v1/resource-operations/connections/${connId}/sync`);
      alert("Background synchronization job scheduled.");
      setTimeout(() => {
        fetchConnections();
        if (selectedResource) fetchResourceTimeline(selectedResource.person_id);
        fetchDashboard();
      }, 2000);
    } catch (err) {
      console.error("Failed to trigger sync", err);
    }
  };

  const approveMapping = async (mapId: number) => {
    try {
      await axios.put(`/api/v1/resource-operations/mappings/${mapId}/approve`);
      fetchMappings();
    } catch (err) {
      console.error("Failed to approve mapping", err);
    }
  };

  const requestAiEstimate = async (e: any) => {
    e.preventDefault();
    setAiLoading(true);
    try {
      const res = await axios.post("/api/v1/resource-operations/estimate", {
        project_id: Number(projectId),
        activity_type: activityType,
        complexity: complexity,
        inputs: {
          num_test_cases: Number(numTestCases),
          functional_scope: scopeDetails
        }
      });
      setAiResult(res.data);
    } catch (err) {
      console.error("AI Estimate request failed", err);
    } finally {
      setAiLoading(false);
    }
  };

  // Recharts metric calculations
  const dashboardChartData = dashboardData ? [
    { name: "Planned", Hours: dashboardData.planned_hours },
    { name: "Achieved", Hours: dashboardData.achieved_hours },
    { name: "Blocked", Hours: dashboardData.blocked_hours },
    { name: "Unplanned", Hours: dashboardData.unplanned_hours },
  ] : [];

  return (
    <div className="space-y-6">
      
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-border pb-4 space-y-2 md:space-y-0">
        <div>
          <h1 className="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-indigo-400">
            Resource Intelligence & Utilization Hub
          </h1>
          <p className="text-xs text-muted-foreground font-semibold tracking-wide">
            Corporate Audits, Timesheets, Active Directory Integration, and AI QA Estimations
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs font-semibold bg-secondary px-3 py-1.5 rounded-lg border border-border">
          <Database className="h-3.5 w-3.5 text-cyan-400" />
          <span>Active Directory Server: </span>
          <span className="text-emerald-400 font-mono font-bold">Ready</span>
        </div>
      </div>

      {/* Primary Layout grid: Navigation Sidebar + Tab Container */}
      <div className="grid lg:grid-cols-[280px_1fr] gap-6">
        
        {/* Submenu navigation list */}
        <aside className="space-y-1">
          <p className="px-3 text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">OPERATIONS MENU</p>
          <nav className="flex flex-col space-y-1">
            {SUBMENUS.map((menu) => {
              const Icon = menu.icon;
              const active = activeTab === menu.id;
              return (
                <button
                  key={menu.id}
                  onClick={() => setActiveTab(menu.id)}
                  className={`flex items-center gap-3 px-4 py-2.5 rounded-xl text-left text-xs font-semibold tracking-wide transition-all duration-150 ${
                    active
                      ? "bg-primary text-primary-foreground shadow-lg shadow-indigo-650/30"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
                >
                  <Icon className="h-4.5 w-4.5 shrink-0" />
                  <span>{menu.label}</span>
                </button>
              );
            })}
          </nav>
        </aside>

        {/* Tab contents window */}
        <main className="space-y-6">

          {/* TAB 1: EXECUTIVE DASHBOARD */}
          {activeTab === "exec" && (
            <div className="space-y-6">
              {/* Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className={cardClass}>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Active Resources</p>
                  <p className="text-3xl font-black text-foreground mt-2">{dashboardData?.active_resources ?? 0}</p>
                </div>
                <div className={cardClass}>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Today Capacity</p>
                  <p className="text-3xl font-black text-foreground mt-2">{dashboardData?.available_capacity_hours ?? 0} hrs</p>
                </div>
                <div className={cardClass}>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Progress Rate</p>
                  <p className="text-3xl font-black text-emerald-450 mt-2">
                    {dashboardData?.progress_percentage?.toFixed(1) ?? "0.0"}%
                  </p>
                </div>
                <div className={cardClass}>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Blocked Hours</p>
                  <p className="text-3xl font-black text-rose-500 mt-2">{dashboardData?.blocked_hours ?? 0} hrs</p>
                </div>
              </div>

              {/* Chart Visuals */}
              <div className="grid md:grid-cols-2 gap-6">
                <div className={cardClass}>
                  <h3 className="text-sm font-black text-foreground mb-4">Effort Allocation (Today)</h3>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={dashboardChartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="name" stroke="#64748b" fontSize={11} />
                        <YAxis stroke="#64748b" fontSize={11} />
                        <Tooltip contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)" }} />
                        <Bar dataKey="Hours" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className={cardClass}>
                  <h3 className="text-sm font-black text-foreground mb-4">Delivery Evidence Sources</h3>
                  <div className="space-y-4">
                    {dashboardData?.evidence_contributions && Object.keys(dashboardData.evidence_contributions).length > 0 ? (
                      Object.entries(dashboardData.evidence_contributions).map(([source, val]: any) => (
                        <div key={source} className="flex items-center justify-between border-b border-border/50 pb-2">
                          <span className="text-xs font-semibold text-muted-foreground">{source} API Integration</span>
                          <span className="text-xs font-mono font-bold text-indigo-400 bg-secondary px-2 py-0.5 rounded border border-border">
                            {val} events synced
                          </span>
                        </div>
                      ))
                    ) : (
                      <p className="text-xs text-muted-foreground/75 font-semibold">No integration sync logs logged today.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: RESOURCE DIRECTORY */}
          {activeTab === "directory" && (
            <div className={cardClass}>
              <h3 className="text-sm font-black text-foreground mb-4">Corporate Resource Directory</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="py-2.5">Name</th>
                      <th>LDAP Account</th>
                      <th>Corporate Email</th>
                      <th>Department</th>
                      <th>Work Hours</th>
                      <th>Telemetry Status</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resources.map((res) => (
                      <tr key={res.person_id} className="border-b border-border/30 hover:bg-muted/40 cursor-pointer" onClick={() => handleSelectResource(res)}>
                        <td className="py-3 font-bold text-foreground">{res.display_name}</td>
                        <td className="font-mono text-cyan-400">{res.ldap_username}</td>
                        <td className="text-muted-foreground/80">{res.corporate_email}</td>
                        <td>{res.department || "N/A"}</td>
                        <td>{res.standard_work_hours} hrs/day</td>
                        <td>
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                            res.device_telemetry_status === "active" ? "bg-emerald-950/50 text-emerald-400 border-emerald-900" : "bg-muted text-muted-foreground border-border"
                          }`}>
                            {res.device_telemetry_status}
                          </span>
                        </td>
                        <td>
                          <span className="text-emerald-400 font-semibold">{res.status}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 3: DAILY WORK PLANNING */}
          {activeTab === "planning" && (
            <div className="grid md:grid-cols-[300px_1fr] gap-6">
              <div className={cardClass}>
                <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-4">Target Resource</h3>
                <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                  {resources.map((res) => (
                    <button
                      key={res.person_id}
                      onClick={() => handleSelectResource(res)}
                      className={`w-full flex items-center justify-between p-3 rounded-xl border text-xs text-left ${
                        selectedResource?.person_id === res.person_id
                          ? "bg-secondary border-cyan-500 text-foreground"
                          : "bg-muted/30 border-border text-muted-foreground"
                      }`}
                    >
                      <span>{res.display_name}</span>
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-6">
                <div className={cardClass}>
                  <h3 className="text-sm font-black text-foreground mb-4">Plan Daily Task for {selectedResource?.display_name}</h3>
                  <form onSubmit={handleAddWorkPlan} className="grid md:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-[10px] font-bold text-muted-foreground uppercase mb-1.5">Task Title</label>
                      <input
                        type="text"
                        value={newPlanTitle}
                        onChange={(e) => setNewPlanTitle(e.target.value)}
                        className="w-full bg-background border border-border rounded-lg p-2.5 text-xs text-foreground outline-none focus:border-cyan-500"
                        placeholder="Manual test execution for Billing"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] font-bold text-muted-foreground uppercase mb-1.5">Est Effort (hours)</label>
                      <input
                        type="number"
                        step="0.5"
                        value={newPlanEst}
                        onChange={(e) => setNewPlanEst(Number(e.target.value))}
                        className="w-full bg-background border border-border rounded-lg p-2.5 text-xs text-foreground outline-none focus:border-cyan-500"
                        required
                      />
                    </div>
                    <div className="flex items-end">
                      <button
                        type="submit"
                        className="w-full bg-cyan-600 hover:bg-cyan-700 text-white text-xs font-bold py-2.5 rounded-lg flex items-center justify-center gap-1 transition-colors"
                      >
                        <Plus className="h-4 w-4" /> Schedule Plan
                      </button>
                    </div>
                  </form>
                </div>

                <div className={cardClass}>
                  <h3 className="text-sm font-black text-foreground mb-4">Scheduled Tasks</h3>
                  <div className="space-y-2">
                    {workPlans.map((plan) => (
                      <div key={plan.id} className="flex items-center justify-between p-3 rounded-xl border border-border bg-muted/20">
                        <div>
                          <p className="text-xs font-bold text-foreground">{plan.task_title}</p>
                          <p className="text-[10px] text-muted-foreground font-semibold mt-1">Status: {plan.status} | Validation: Lead ({plan.lead_validation})</p>
                        </div>
                        <div className="text-right">
                          <span className="text-xs font-mono font-bold text-cyan-400">{plan.estimated_effort} hrs est</span>
                        </div>
                      </div>
                    ))}
                    {workPlans.length === 0 && (
                      <p className="text-xs text-muted-foreground/75 font-semibold">No planned tasks found for this resource today.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: TEAM CAPACITY */}
          {activeTab === "capacity" && (
            <div className={cardClass}>
              <h3 className="text-sm font-black text-foreground mb-4">Team capacity allocations</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div className="bg-muted/30 p-4 rounded-xl border border-border">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase">Available Capacity</p>
                  <p className="text-2xl font-black text-foreground mt-1">192.0 hrs</p>
                </div>
                <div className="bg-muted/30 p-4 rounded-xl border border-border">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase">Allocated Effort</p>
                  <p className="text-2xl font-black text-foreground mt-1">168.0 hrs</p>
                </div>
                <div className="bg-muted/30 p-4 rounded-xl border border-border">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase">Remaining Buffer</p>
                  <p className="text-2xl font-black text-emerald-450 mt-1">24.0 hrs</p>
                </div>
                <div className="bg-muted/30 p-4 rounded-xl border border-border">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase">Buffer Percentage</p>
                  <p className="text-2xl font-black text-foreground mt-1">12.5%</p>
                </div>
              </div>

              <div className="bg-muted/50 p-4 rounded-xl border border-border">
                <h4 className="text-xs font-bold text-muted-foreground uppercase mb-3">Timezone Distribution Heatmap</h4>
                <div className="flex items-center gap-2">
                  <div className="px-3 py-1 bg-cyan-950 text-cyan-400 border border-cyan-900 rounded text-xs font-mono font-bold">CST: 8 Resources</div>
                  <div className="px-3 py-1 bg-indigo-950 text-indigo-400 border border-indigo-900 rounded text-xs font-mono font-bold">EST: 12 Resources</div>
                  <div className="px-3 py-1 bg-blue-950 text-blue-400 border border-blue-900 rounded text-xs font-mono font-bold">UTC: 4 Resources</div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: TASK BOARD */}
          {activeTab === "taskboard" && (
            <div className="grid md:grid-cols-4 gap-4">
              {["Planned", "In Progress", "Blocked", "Done"].map((col) => (
                <div key={col} className="bg-muted/50 p-4 rounded-xl border border-border">
                  <h4 className="text-xs font-black text-foreground border-b border-border pb-2 mb-3">{col}</h4>
                  <div className="space-y-2">
                    {workPlans
                      .filter((p) => p.status === col)
                      .map((plan) => (
                        <div key={plan.id} className="bg-card border border-border p-3 rounded-lg text-xs space-y-2">
                          <p className="font-bold text-foreground">{plan.task_title}</p>
                          <div className="flex justify-between items-center text-[10px] text-muted-foreground">
                            <span>{plan.estimated_effort} hrs</span>
                            <span className="font-mono text-cyan-400">{selectedResource?.ldap_username}</span>
                          </div>
                        </div>
                      ))}
                    {workPlans.filter((p) => p.status === col).length === 0 && (
                      <p className="text-[10px] text-muted-foreground/50 font-semibold py-4 text-center">No tasks.</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* TAB 6: DAILY ACTIVITY TIMELINE */}
          {activeTab === "timeline" && (
            <div className="space-y-6">
              <div className="flex justify-between items-center">
                <h3 className="text-sm font-black text-foreground">Daily Evidence Timeline ({selectedResource?.display_name})</h3>
                <span className="text-xs text-muted-foreground font-semibold bg-secondary px-2.5 py-1 rounded border border-border">
                  Evidence Confidence Score: <span className="text-emerald-450 font-bold">94%</span>
                </span>
              </div>

              <div className="relative border-l border-border ml-4 pl-6 space-y-6">
                {timelineData?.events.map((ev: any) => (
                  <div key={ev.id} className="relative">
                    {/* Circle timeline dot */}
                    <div className="absolute -left-[31px] top-1.5 h-3 w-3 rounded-full bg-cyan-400 border-2 border-background" />
                    <div className="bg-muted/20 border border-border p-4 rounded-xl space-y-2">
                      <div className="flex justify-between items-start">
                        <div>
                          <span className="text-xs font-mono font-bold text-cyan-400 bg-cyan-950 px-2 py-0.5 rounded border border-cyan-900 mr-2">
                            {ev.source_system}
                          </span>
                          <span className="text-xs font-bold text-foreground">{ev.event_category}</span>
                        </div>
                        <span className="text-[10px] text-muted-foreground font-mono">{new Date(ev.timestamp).toLocaleTimeString()}</span>
                      </div>
                      <p className="text-xs text-muted-foreground">{ev.event_type.replace(/_/g, " ").toUpperCase()}</p>
                      <div className="flex justify-between items-center text-[10px] text-muted-foreground font-semibold pt-1 border-t border-border/30">
                        <span>External ID: {ev.source_event_id}</span>
                        <span className="text-indigo-400">{ev.actual_effort_hours} hrs logged</span>
                      </div>
                    </div>
                  </div>
                ))}

                {timelineData?.events.length === 0 && (
                  <p className="text-xs text-muted-foreground/75 font-semibold">No sync events ingested for this resource today. Run a mock sync inside Integration Hub to import sample logs.</p>
                )}
              </div>
            </div>
          )}

          {/* TAB 7: EFFORT & EVIDENCE */}
          {activeTab === "utilization" && (
            <div className={cardClass}>
              <h3 className="text-sm font-black text-foreground mb-4">Deduplicated timesheet verification</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="py-2.5">Scheduled Activity</th>
                      <th>Estimated Hours</th>
                      <th>Achieved Hours (Dedupled)</th>
                      <th>Variance</th>
                      <th>Freshness Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workPlans.map((plan) => (
                      <tr key={plan.id} className="border-b border-border/30 hover:bg-muted/30">
                        <td className="py-3 font-bold text-foreground">{plan.task_title}</td>
                        <td>{plan.estimated_effort} hrs</td>
                        <td className="text-cyan-400 font-bold">{plan.achieved_effort} hrs</td>
                        <td className={`font-bold ${plan.achieved_effort - plan.estimated_effort >= 0 ? "text-emerald-450" : "text-amber-500"}`}>
                          {(plan.achieved_effort - plan.estimated_effort).toFixed(1)} hrs
                        </td>
                        <td>
                          <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950/40 text-emerald-400 border border-emerald-900 font-bold">
                            Live Sync
                          </span>
                        </td>
                      </tr>
                    ))}
                    {workPlans.length === 0 && (
                      <tr>
                        <td colSpan={5} className="py-6 text-center text-muted-foreground/50 font-semibold">No planned tasks logs today.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 8: RTC DEFECTS & CHANGES */}
          {activeTab === "rtc" && (
            <div className="grid md:grid-cols-2 gap-6">
              <div className={cardClass}>
                <h3 className="text-sm font-black text-foreground mb-4">IBM RTC Defect Contributions</h3>
                <div className="space-y-4 text-xs">
                  <div className="flex justify-between border-b border-border/40 pb-2">
                    <span className="text-muted-foreground">Defects Triage / Retested</span>
                    <span className="font-bold text-foreground font-mono">14 Completed</span>
                  </div>
                  <div className="flex justify-between border-b border-border/40 pb-2">
                    <span className="text-muted-foreground">Average Defect Retesting Effort</span>
                    <span className="font-bold text-foreground font-mono">1.8 hrs / Defect</span>
                  </div>
                  <div className="flex justify-between border-b border-border/40 pb-2">
                    <span className="text-muted-foreground">Leakage indicators</span>
                    <span className="font-bold text-emerald-450 font-mono">0% reported leakage</span>
                  </div>
                </div>
              </div>

              <div className={cardClass}>
                <h3 className="text-sm font-black text-foreground mb-4">Change Requests validations</h3>
                <div className="space-y-4 text-xs">
                  <div className="flex justify-between border-b border-border/40 pb-2">
                    <span className="text-muted-foreground">Emergency Validation Runs</span>
                    <span className="font-bold text-rose-500 font-mono">2 Major Validation Checks</span>
                  </div>
                  <div className="flex justify-between border-b border-border/40 pb-2">
                    <span className="text-muted-foreground">Post-deployment Validation Checks</span>
                    <span className="font-bold text-foreground font-mono">8 Approved Sign-offs</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 9: RQM TEST CONTRIBUTION */}
          {activeTab === "rqm" && (
            <div className={cardClass}>
              <h3 className="text-sm font-black text-foreground mb-4">RQM Execution metrics</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div className="bg-muted/30 p-4 rounded-xl border border-border">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase">Test Runs Executed</p>
                  <p className="text-2xl font-black text-foreground mt-1">42 runs</p>
                </div>
                <div className="bg-muted/30 p-4 rounded-xl border border-border">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase">Passed runs</p>
                  <p className="text-2xl font-black text-emerald-450 mt-1">38 runs</p>
                </div>
                <div className="bg-muted/30 p-4 rounded-xl border border-border">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase">Failed / Blocked</p>
                  <p className="text-2xl font-black text-rose-500 mt-1">4 runs</p>
                </div>
                <div className="bg-muted/30 p-4 rounded-xl border border-border">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase">Average Duration</p>
                  <p className="text-2xl font-black text-foreground mt-1">12 mins / run</p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 10: INTEGRATION HUB */}
          {activeTab === "integrations" && (
            <div className="space-y-6">
              <div className={cardClass}>
                <h3 className="text-sm font-black text-foreground mb-4">Add Connection</h3>
                <form onSubmit={handleCreateConnection} className="grid md:grid-cols-5 gap-4">
                  <div>
                    <label className="block text-[10px] font-bold text-muted-foreground uppercase mb-1.5">System Type</label>
                    <select
                      value={newConnType}
                      onChange={(e) => setNewConnType(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg p-2.5 text-xs text-foreground outline-none"
                    >
                      <option value="Jira">Jira</option>
                      <option value="RTC">IBM RTC / EWM</option>
                      <option value="RQM">IBM RQM / ETM</option>
                      <option value="LDAP">Corporate LDAP</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-muted-foreground uppercase mb-1.5">Connection Name</label>
                    <input
                      type="text"
                      value={newConnName}
                      onChange={(e) => setNewConnName(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg p-2.5 text-xs text-foreground outline-none focus:border-cyan-500"
                      placeholder="My Jira Endpoint"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-muted-foreground uppercase mb-1.5">Endpoint URL</label>
                    <input
                      type="url"
                      value={newConnUrl}
                      onChange={(e) => setNewConnUrl(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg p-2.5 text-xs text-foreground outline-none focus:border-cyan-500"
                      placeholder="https://jira.company.com"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-muted-foreground uppercase mb-1.5">Username</label>
                    <input
                      type="text"
                      value={newConnUser}
                      onChange={(e) => setNewConnUser(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg p-2.5 text-xs text-foreground outline-none focus:border-cyan-500"
                      placeholder="ad.username"
                    />
                  </div>
                  <div className="flex items-end">
                    <button
                      type="submit"
                      className="w-full bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold py-2.5 rounded-lg transition-colors"
                    >
                      Save Configuration
                    </button>
                  </div>
                </form>
              </div>

              <div className={cardClass}>
                <h3 className="text-sm font-black text-foreground mb-4">Configured connections</h3>
                <div className="space-y-3">
                  {connections.map((conn) => (
                    <div key={conn.id} className="flex items-center justify-between p-4 rounded-xl border border-border bg-muted/20">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
                          <h4 className="text-xs font-bold text-foreground">{conn.name}</h4>
                          <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-900">
                            {conn.system_type}
                          </span>
                        </div>
                        <p className="text-[10px] text-muted-foreground font-semibold mt-1">Endpoint: {conn.base_url}</p>
                      </div>
                      <div>
                        <button
                          onClick={() => triggerSync(conn.id)}
                          className="bg-cyan-600 hover:bg-cyan-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg flex items-center gap-1 transition-colors"
                        >
                          <RefreshCw className="h-3.5 w-3.5" /> Trigger Ingestion Sync
                        </button>
                      </div>
                    </div>
                  ))}
                  {connections.length === 0 && (
                    <p className="text-xs text-muted-foreground/75 font-semibold">No external integration connections configured yet.</p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 11: AI ESTIMATE INTELLIGENCE */}
          {activeTab === "ai_estimate" && (
            <div className="grid md:grid-cols-2 gap-6">
              <div className={cardClass}>
                <h3 className="text-sm font-black text-foreground mb-4">Request AI Effort Recommendation</h3>
                <form onSubmit={requestAiEstimate} className="space-y-4">
                  <div>
                    <label className="block text-[10px] font-bold text-muted-foreground uppercase mb-1.5">Activity Type</label>
                    <select
                      value={activityType}
                      onChange={(e) => setActivityType(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg p-2.5 text-xs text-foreground outline-none focus:border-cyan-500"
                    >
                      <option value="Manual Test Execution">Manual Test Execution</option>
                      <option value="Test Case Design">Test Case Design</option>
                      <option value="Automation Development">Automation Development</option>
                      <option value="Requirement Analysis">Requirement Analysis</option>
                      <option value="Database Validation">Database Validation</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-muted-foreground uppercase mb-1.5">Complexity Level</label>
                    <select
                      value={complexity}
                      onChange={(e) => setComplexity(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg p-2.5 text-xs text-foreground outline-none focus:border-cyan-500"
                    >
                      <option value="Low">Low</option>
                      <option value="Medium">Medium</option>
                      <option value="High">High</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-muted-foreground uppercase mb-1.5">Scope Metrics (e.g. Test Cases Count)</label>
                    <input
                      type="number"
                      value={numTestCases}
                      onChange={(e) => setNumTestCases(Number(e.target.value))}
                      className="w-full bg-background border border-border rounded-lg p-2.5 text-xs text-foreground outline-none focus:border-cyan-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-muted-foreground uppercase mb-1.5">Scope / Requirements Detail</label>
                    <textarea
                      value={scopeDetails}
                      onChange={(e) => setScopeDetails(e.target.value)}
                      rows={3}
                      className="w-full bg-background border border-border rounded-lg p-2.5 text-xs text-foreground outline-none focus:border-cyan-500"
                      placeholder="Validate wholesale billing rating engine across 4 main API segments..."
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={aiLoading}
                    className="w-full bg-cyan-600 hover:bg-cyan-700 disabled:opacity-50 text-white text-xs font-bold py-2.5 rounded-lg flex items-center justify-center gap-1 transition-colors"
                  >
                    {aiLoading ? "Consulting AI Engine..." : <><Bot className="h-4.5 w-4.5" /> Estimate with AI</>}
                  </button>
                </form>
              </div>

              <div className="space-y-6">
                {aiResult ? (
                  <div className={cardClass}>
                    <h3 className="text-sm font-black text-foreground mb-4">AI Recommended Estimates</h3>
                    
                    <div className="grid grid-cols-3 gap-2 mb-4 text-center">
                      <div className="bg-muted/30 p-2.5 rounded-lg border border-border">
                        <p className="text-[9px] font-bold text-muted-foreground uppercase">Optimistic</p>
                        <p className="text-sm font-black text-foreground">{aiResult.optimistic_hours} hrs</p>
                      </div>
                      <div className="bg-muted/30 p-2.5 rounded-lg border border-border ring-1 ring-cyan-500/50">
                        <p className="text-[9px] font-bold text-cyan-400 uppercase">PERT Estimate</p>
                        <p className="text-sm font-black text-cyan-400">{aiResult.pert_hours} hrs</p>
                      </div>
                      <div className="bg-muted/30 p-2.5 rounded-lg border border-border">
                        <p className="text-[9px] font-bold text-muted-foreground uppercase">Pessimistic</p>
                        <p className="text-sm font-black text-foreground">{aiResult.pessimistic_hours} hrs</p>
                      </div>
                    </div>

                    <div className="space-y-3.5 text-xs">
                      <div>
                        <p className="font-bold text-muted-foreground uppercase text-[9px]">Confidence Index</p>
                        <p className="font-semibold text-foreground mt-0.5">{aiResult.confidence_score * 100}% Confidence</p>
                      </div>
                      <div>
                        <p className="font-bold text-muted-foreground uppercase text-[9px]">Identified Assumptions</p>
                        <p className="font-semibold text-foreground mt-0.5">{aiResult.assumptions}</p>
                      </div>
                      <div>
                        <p className="font-bold text-muted-foreground uppercase text-[9px]">Potential Risks</p>
                        <p className="font-semibold text-rose-450 mt-0.5">{aiResult.risk_factors}</p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className={`${cardClass} flex flex-col items-center justify-center text-center h-full min-h-[300px]`}>
                    <Bot className="h-10 w-10 text-muted-foreground/60 mb-3" />
                    <p className="text-xs text-muted-foreground/75 font-semibold">AI Estimate recommendation results will appear here after request.</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 12: REPORTS & EXPORTS */}
          {activeTab === "reports" && (
            <div className={cardClass}>
              <h3 className="text-sm font-black text-foreground mb-4">Operational Reports</h3>
              <div className="grid md:grid-cols-2 gap-4">
                {[
                  "Daily Resource Timesheet Audits",
                  "Sprint QA Delivery & Utilization Report",
                  "IBM RTC Defect Contribution Audits",
                  "RQM Execution Evidence Traceability Matrix"
                ].map((rep, idx) => (
                  <div key={idx} className="flex items-center justify-between p-4 rounded-xl border border-border bg-muted/20">
                    <div>
                      <h4 className="text-xs font-bold text-foreground">{rep}</h4>
                      <p className="text-[10px] text-muted-foreground/70 mt-1">Available formats: Excel (.xlsx), PDF, CSV</p>
                    </div>
                    <div className="flex gap-2">
                      <button className="bg-slate-800 hover:bg-slate-700 text-white text-[10px] font-bold px-3 py-1.5 rounded-lg border border-border transition-all">
                        PDF
                      </button>
                      <button className="bg-cyan-600 hover:bg-cyan-700 text-white text-[10px] font-bold px-3 py-1.5 rounded-lg transition-all">
                        Excel
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 13: EXCEPTIONS & RECONCILIATION */}
          {activeTab === "exceptions" && (
            <div className={cardClass}>
              <h3 className="text-sm font-black text-foreground mb-4">Identity mapping reconciliation queue</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="py-2.5">System</th>
                      <th>External Account Name</th>
                      <th>External Email</th>
                      <th>Confidence Match</th>
                      <th>Mapping Status</th>
                      <th className="text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mappings.map((map) => (
                      <tr key={map.id} className="border-b border-border/30 hover:bg-muted/30">
                        <td className="py-3">
                          <span className="font-mono text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-900">
                            {map.source_system}
                          </span>
                        </td>
                        <td className="font-bold text-foreground">{map.external_display_name || map.external_username}</td>
                        <td>{map.external_email || "N/A"}</td>
                        <td>{(map.mapping_confidence * 100).toFixed(0)}%</td>
                        <td>
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            map.status === "approved" ? "bg-emerald-950 text-emerald-450 border border-emerald-900" : "bg-amber-950 text-amber-500 border border-amber-900"
                          }`}>
                            {map.status}
                          </span>
                        </td>
                        <td className="text-right">
                          {map.status !== "approved" && (
                            <button
                              onClick={() => approveMapping(map.id)}
                              className="bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] font-bold px-2.5 py-1.5 rounded transition-all"
                            >
                              Approve Map
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {mappings.length === 0 && (
                      <tr>
                        <td colSpan={6} className="py-6 text-center text-muted-foreground/50 font-semibold">No identity mappings registered.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 14: GOVERNANCE & PRIVACY */}
          {activeTab === "governance" && (
            <div className="grid md:grid-cols-2 gap-6">
              <div className={cardClass}>
                <h3 className="text-sm font-black text-foreground mb-4">Device Telemetry Privacy Controls</h3>
                <div className="bg-secondary border border-border p-4 rounded-xl space-y-3">
                  <div className="flex items-center justify-between border-b border-border/50 pb-2">
                    <span className="text-xs font-semibold text-muted-foreground/80">Keystrokes / Screen Capture</span>
                    <span className="text-xs font-bold text-rose-500 uppercase">Disabled (Spyware Filter)</span>
                  </div>
                  <div className="flex items-center justify-between border-b border-border/50 pb-2">
                    <span className="text-xs font-semibold text-muted-foreground/80">Work Category Adherence</span>
                    <span className="text-xs font-bold text-emerald-450 uppercase">Active (Classified Categories Only)</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground/60 font-semibold leading-relaxed mt-1">
                    “Supporting activity context only. It is not a productivity, attendance, disciplinary, or performance score.”
                  </p>
                </div>
              </div>

              <div className={cardClass}>
                <h3 className="text-sm font-black text-foreground mb-4">Privacy Consent Acknowledgement</h3>
                <div className="space-y-4 text-xs font-semibold text-muted-foreground/80">
                  <p>In adherence to GDPR, CCPA, and corporate employment policies, telemetry data collection requires active consent.</p>
                  <div className="flex items-center gap-2">
                    <CheckCircle className="h-4.5 w-4.5 text-emerald-400 shrink-0" />
                    <span className="text-foreground">Active consent records synced with Active Directory</span>
                  </div>
                </div>
              </div>
            </div>
          )}

        </main>
      </div>

    </div>
  );
}

export default function ResourceIntelligencePage() {
  return (
    <Suspense fallback={
      <div className="flex h-64 items-center justify-center text-muted-foreground text-xs font-semibold">
        Loading Resource Intelligence & Utilization Hub...
      </div>
    }>
      <ResourceIntelligenceContent />
    </Suspense>
  );
}
