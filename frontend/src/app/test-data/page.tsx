"use client";

import { useCallback, useEffect, useMemo, useState, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  AlertTriangle, CheckCircle, Database, Eye, ExternalLink, History, Loader2, PlayCircle, RefreshCw,
  Shield, ShieldCheck, Upload, Wand2, XCircle, ChevronRight, X, Info, Sparkles, Check, Trash,
  Plus, Save, Clock
} from "lucide-react";
import {
  getAuthProfile, projectsApi, requirementsApi, testCasesApi, testDataApi,
  type Project, type Requirement, type TestCase, type TestDataImportPreviewResponse, type TestDataItem, type TestDataSummary
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerBody, DrawerFooter, DrawerClose
} from "@/components/ui/drawer";

// ── Constants and Select Options ──────────────────────────────────────────────
const FILTERS = ["all", "draft", "pending_approval", "approved", "rejected", "synthetic", "manual", "masked", "reserved", "available", "expired"];
const DATA_TYPES = ["Customer", "Subscriber", "MSISDN", "IMSI", "ICCID", "SIM/eSIM Profile", "Device", "Plan", "Product", "Bundle", "Billing Account", "Charging Account", "Order", "Trouble Ticket", "Network Profile", "API Payload", "Payment", "Invoice", "Contract", "Address", "KYC Document Reference", "Generic"];
const ENVIRONMENT_OPTIONS = ["SIT", "UAT", "PreProd", "Production"];
const PHASE_OPTIONS = ["SIT", "UAT", "Regression", "NFT", "Production Validation"];
const DOMAIN_OPTIONS = ["Mobile", "Fixed", "Digital", "Billing", "Data", "CRM", "OSS", "BSS", "Middleware", "Integration", "Network"];
const PRIVACY_LEVELS = ["public", "internal", "confidential", "restricted"];
const GENERATION_MODES = ["positive", "negative", "boundary", "invalid", "mixed"] as const;
const EXTERNAL_TOOLS = ["Mock", "Katalon", "Playwright", "Pytest", "GenRocket", "Delphix", "Broadcom TDM", "Informatica TDM", "Other"];
const IMPORT_MODES = ["create_new_dataset", "append_to_existing_dataset"] as const;
const PRIORITIES = ["Low", "Medium", "High", "Critical"];

const PRODUCT_GROUP_OPTIONS = [
  "",
  "BusinessLite",
  "Figital Services",
  "MOBILE Products",
  "eLife Product Group",
  "Internet - Broad Band Services",
  "Data",
  "PSTN",
  "eCompany Application Based Services",
  "Cloud Communications",
  "Product Group Code for EES and FMS",
  "Multi Play"
];

const PRODUCT_OPTIONS = [
  "",
  "GSM Prepaid",
  "GSM Post Paid",
  "iShare",
  "Global IPVPN",
  "eLife TV",
  "Triple Play Products",
  "PABX Lines",
  "Dual Play Products",
  "Bit Stream"
];

const SUB_REQUEST_TYPE_OPTIONS = [
  "",
  "Add Service",
  "Delete Service",
  "New Account",
  "Number Change",
  "Reconnection",
  "Technician Visit",
  "Migration Request",
  "External Shift"
];

type DraftForm = {
  name: string;
  data_type: string;
  environment: string;
  telecom_domain: string;
  test_phase: string;
  product_group: string;
  product: string;
  sub_request_type: string;
  privacy_level: string;
  contains_pii: boolean;
  test_case_id: string;
  requirement_id: string;
  tags: string;
  payload: string;
  sensitive_fields: string;
  submit_for_approval: boolean;
};

type GenerateForm = {
  name: string;
  data_type: string;
  environment: string;
  telecom_domain: string;
  test_phase: string;
  product_group: string;
  product: string;
  sub_request_type: string;
  linked_test_case_id: string;
  linked_requirement_id: string;
  number_of_records: string;
  generation_mode: (typeof GENERATION_MODES)[number];
  external_tool: string;
  external_suite_id: string;
  external_dataset_id: string;
  external_url: string;
  request_notes: string;
  priority: string;
  expected_by_date: string;
};

type ImportForm = {
  file: File | null;
  name: string;
  data_type: string;
  environment: string;
  telecom_domain: string;
  test_phase: string;
  product_group: string;
  product: string;
  sub_request_type: string;
  contains_pii: boolean;
  privacy_level: string;
  linked_test_case_id: string;
  linked_requirement_id: string;
  import_mode: (typeof IMPORT_MODES)[number];
  existing_data_set_id: string;
  validate_before_import: boolean;
};

type HistoryRow = {
  id: number;
  action_type: string;
  decision: string;
  notes?: string | null;
  created_at: string;
};

const INITIAL_FORM: DraftForm = {
  name: "",
  data_type: "Generic",
  environment: "SIT",
  telecom_domain: "Mobile",
  test_phase: "SIT",
  product_group: "",
  product: "",
  sub_request_type: "",
  privacy_level: "internal",
  contains_pii: false,
  test_case_id: "",
  requirement_id: "",
  tags: "",
  payload: '{\n  "sample_key": "sample_value"\n}',
  sensitive_fields: "",
  submit_for_approval: false,
};

const INITIAL_GENERATE_FORM: GenerateForm = {
  name: "",
  data_type: "Generic",
  environment: "SIT",
  telecom_domain: "Mobile",
  test_phase: "SIT",
  product_group: "",
  product: "",
  sub_request_type: "",
  linked_test_case_id: "",
  linked_requirement_id: "",
  number_of_records: "10",
  generation_mode: "positive",
  external_tool: "Mock",
  external_suite_id: "",
  external_dataset_id: "",
  external_url: "",
  request_notes: "",
  priority: "Medium",
  expected_by_date: "",
};

const INITIAL_IMPORT_FORM: ImportForm = {
  file: null,
  name: "",
  data_type: "Generic",
  environment: "SIT",
  telecom_domain: "Mobile",
  test_phase: "SIT",
  product_group: "",
  product: "",
  sub_request_type: "",
  contains_pii: false,
  privacy_level: "internal",
  linked_test_case_id: "",
  linked_requirement_id: "",
  import_mode: "create_new_dataset",
  existing_data_set_id: "",
  validate_before_import: true,
};

function permissionSet(projectId: number | null) {
  const profile = getAuthProfile();
  if (!profile || projectId == null) return null;
  
  const globalRole = profile.global_role?.toLowerCase() || "";
  if (globalRole === "admin" || globalRole === "platform_admin" || globalRole === "platform admin") {
    return new Set([
      "create_test_data",
      "generate_test_data",
      "import_test_data",
      "approve_test_data",
      "reserve_test_data",
      "consume_test_data",
      "mask_test_data",
      "sync_test_data_jira",
      "view_sensitive_test_data"
    ]);
  }

  const membership = profile.project_memberships?.find((item) => item.project_id === projectId);
  return new Set(membership?.permissions ?? []);
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

// ── Content Component ─────────────────────────────────────────────────────────
function TestDataContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const selectedProject = Number(searchParams.get("project")) || null;

  const [projects, setProjects] = useState<Project[]>([]);
  const [items, setItems] = useState<TestDataItem[]>([]);
  const [summary, setSummary] = useState<TestDataSummary | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  
  // Drawer States
  const [selectedItem, setSelectedItem] = useState<TestDataItem | null>(null);
  const [drawerTab, setDrawerTab] = useState<"attributes" | "payload" | "history">("attributes");
  const [historyRows, setHistoryRows] = useState<HistoryRow[]>([]);

  // Form Drawers
  const [createOpen, setCreateOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const [form, setForm] = useState<DraftForm>(INITIAL_FORM);
  const [generateForm, setGenerateForm] = useState<GenerateForm>(INITIAL_GENERATE_FORM);
  const [importForm, setImportForm] = useState<ImportForm>(INITIAL_IMPORT_FORM);
  const [importPreview, setImportPreview] = useState<TestDataImportPreviewResponse | null>(null);

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [previewingImport, setPreviewingImport] = useState(false);
  const [confirmingImport, setConfirmingImport] = useState(false);
  const [busyItemId, setBusyItemId] = useState<number | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // Load Initial Projects
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

  // Reset page components when project changes
  useEffect(() => {
    setSelectedItem(null);
    setHistoryRows([]);
    setForm(INITIAL_FORM);
    setGenerateForm(INITIAL_GENERATE_FORM);
    setImportForm(INITIAL_IMPORT_FORM);
    setImportPreview(null);
    setNotice("");
  }, [selectedProject]);

  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    setError("");
    try {
      const [dataRes, summaryRes, reqRes, tcRes] = await Promise.allSettled([
        testDataApi.list(selectedProject),
        testDataApi.summary(selectedProject),
        requirementsApi.list(selectedProject),
        testCasesApi.list(selectedProject),
      ]);

      if (dataRes.status === "rejected") throw dataRes.reason;
      if (summaryRes.status === "rejected") throw summaryRes.reason;

      const nextItems = dataRes.value.data;
      setItems(nextItems);
      setSummary(summaryRes.value.data);
      setRequirements(reqRes.status === "fulfilled" ? reqRes.value.data : []);
      setTestCases(tcRes.status === "fulfilled" ? tcRes.value.data : []);
    } catch (loadError) {
      setError(messageFromError(loadError, "Could not load test data."));
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadData();
  }, [selectedProject]);

  // Keep selectedItem synced with the latest item from items list
  useEffect(() => {
    if (selectedItem) {
      const fresh = items.find((entry) => entry.id === selectedItem.id);
      if (!fresh) {
        setSelectedItem(null);
      } else if (fresh !== selectedItem) {
        setSelectedItem(fresh);
      }
    }
  }, [items, selectedItem]);

  // Load history whenever tab changes to history
  useEffect(() => {
    if (selectedItem && drawerTab === "history") {
      setHistoryLoading(true);
      testDataApi.history(selectedItem.id)
        .then(res => setHistoryRows(res.data))
        .catch(() => setError("Could not load test data history."))
        .finally(() => setHistoryLoading(false));
    }
  }, [selectedItem, drawerTab]);

  const permissions = useMemo(() => permissionSet(selectedProject), [selectedProject]);
  const canCreate = !permissions || permissions.has("create_test_data");
  const canGenerate = !permissions || permissions.has("generate_test_data");
  const canImport = !permissions || permissions.has("import_test_data");
  const canApprove = !permissions || permissions.has("approve_test_data");
  const canReserve = !permissions || permissions.has("reserve_test_data");
  const canMask = !permissions || permissions.has("mask_test_data");

  const filteredItems = useMemo(() => {
    if (filter === "all") return items;
    if (filter === "synthetic") return items.filter((item) => ["synthetic", "ai_generated", "external_tool"].includes(item.source_type));
    if (filter === "manual") return items.filter((item) => item.source_type === "manual");
    if (filter === "masked") return items.filter((item) => item.masking_status === "masked");
    if (filter === "reserved") return items.filter((item) => item.reservation_status === "reserved");
    if (filter === "available") return items.filter((item) => item.reservation_status === "available");
    return items.filter((item) => item.status === filter || item.approval_status === filter || item.reservation_status === filter || item.generation_status === filter);
  }, [filter, items]);

  async function handleCreate() {
    if (!selectedProject) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const trimmedName = form.name.trim();
      if (!trimmedName) {
        setError("Name is required.");
        return;
      }
      const payload = JSON.parse(form.payload);
      if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        setError("Payload JSON must be an object.");
        return;
      }
      const sensitiveFields = form.sensitive_fields.split(",").map((v) => v.trim()).filter(Boolean);
      if (form.contains_pii && sensitiveFields.length === 0) {
        setError("Sensitive Fields are required when Contains PII is enabled.");
        return;
      }
      await testDataApi.create(selectedProject, {
        name: trimmedName,
        data_type: form.data_type,
        environment: form.environment,
        telecom_domain: form.telecom_domain,
        test_phase: form.test_phase,
        product_group: form.product_group || undefined,
        product: form.product || undefined,
        sub_request_type: form.sub_request_type || undefined,
        privacy_level: form.privacy_level,
        contains_pii: form.contains_pii,
        test_case_id: form.test_case_id ? Number(form.test_case_id) : undefined,
        requirement_id: form.requirement_id ? Number(form.requirement_id) : undefined,
        tags: form.tags.split(",").map((v) => v.trim()).filter(Boolean),
        data_payload_json: payload,
        sensitive_fields_json: sensitiveFields,
        submit_for_approval: form.submit_for_approval,
      });
      setNotice("Test data created successfully.");
      setForm(INITIAL_FORM);
      setCreateOpen(false);
      await loadData();
    } catch (createError) {
      setError(messageFromError(createError, "Could not create test data."));
    } finally {
      setSaving(false);
    }
  }

  async function handleGenerate() {
    if (!selectedProject) return;
    setGenerating(true);
    setError("");
    setNotice("");
    try {
      if (!generateForm.name.trim()) {
        setError("Data Set Name is required.");
        return;
      }
      const recordCount = Number(generateForm.number_of_records);
      if (!Number.isFinite(recordCount) || recordCount < 1 || recordCount > 10000) {
        setError("Number of Records must be between 1 and 10000.");
        return;
      }
      await testDataApi.generate(selectedProject, {
        name: generateForm.name.trim(),
        data_type: generateForm.data_type,
        telecom_domain: generateForm.telecom_domain,
        test_phase: generateForm.test_phase,
        product_group: generateForm.product_group || undefined,
        product: generateForm.product || undefined,
        sub_request_type: generateForm.sub_request_type || undefined,
        environment: generateForm.environment,
        linked_requirement_id: generateForm.linked_requirement_id ? Number(generateForm.linked_requirement_id) : undefined,
        linked_test_case_id: generateForm.linked_test_case_id ? Number(generateForm.linked_test_case_id) : undefined,
        number_of_records: recordCount,
        generation_mode: generateForm.generation_mode,
        external_tool: generateForm.external_tool,
        external_suite_id: generateForm.external_suite_id.trim() || undefined,
        external_dataset_id: generateForm.external_dataset_id.trim() || undefined,
        external_url: generateForm.external_url.trim() || undefined,
        request_notes: generateForm.request_notes.trim() || undefined,
        priority: generateForm.priority,
        expected_by_date: generateForm.expected_by_date || undefined,
      });
      setNotice("External generation request created successfully.");
      setGenerateForm(INITIAL_GENERATE_FORM);
      setGenerateOpen(false);
      await loadData();
    } catch (generateError) {
      setError(messageFromError(generateError, "Could not create generation request."));
    } finally {
      setGenerating(false);
    }
  }

  async function handleImportPreview() {
    if (!selectedProject) return;
    setPreviewingImport(true);
    setError("");
    setNotice("");
    try {
      if (!importForm.file) {
        setError("Choose a CSV or Excel file to preview.");
        return;
      }
      if (importForm.contains_pii && importForm.privacy_level === "public") {
        setError("Privacy Level cannot be public when Contains PII is enabled.");
        return;
      }
      const res = await testDataApi.importPreview(selectedProject, {
        file: importForm.file,
        name: importForm.name.trim() || undefined,
        data_type: importForm.data_type,
        telecom_domain: importForm.telecom_domain,
        test_phase: importForm.test_phase,
        product_group: importForm.product_group || undefined,
        product: importForm.product || undefined,
        sub_request_type: importForm.sub_request_type || undefined,
        environment: importForm.environment,
        contains_pii: importForm.contains_pii,
        privacy_level: importForm.privacy_level,
        linked_requirement_id: importForm.linked_requirement_id ? Number(importForm.linked_requirement_id) : undefined,
        linked_test_case_id: importForm.linked_test_case_id ? Number(importForm.linked_test_case_id) : undefined,
        import_mode: importForm.import_mode,
        existing_data_set_id: importForm.existing_data_set_id ? Number(importForm.existing_data_set_id) : undefined,
        validate_before_import: importForm.validate_before_import,
      });
      setImportPreview(res.data);
    } catch (previewError) {
      setError(messageFromError(previewError, "Could not preview import file."));
    } finally {
      setPreviewingImport(false);
    }
  }

  async function handleImportConfirm() {
    if (!selectedProject || !importPreview?.preview_token) return;
    setConfirmingImport(true);
    setError("");
    setNotice("");
    try {
      const res = await testDataApi.importConfirm(selectedProject, importPreview.preview_token);
      setNotice(`Imported ${res.data.imported_record_count} records successfully.`);
      setImportPreview(null);
      setImportForm(INITIAL_IMPORT_FORM);
      setImportOpen(false);
      await loadData();
    } catch (confirmError) {
      setError(messageFromError(confirmError, "Could not confirm import."));
    } finally {
      setConfirmingImport(false);
    }
  }

  async function runAction(item: TestDataItem, action: "validate" | "mask" | "reserve" | "release" | "consume" | "submit" | "approve" | "reject") {
    setBusyItemId(item.id);
    setError("");
    setNotice("");
    try {
      if (action === "validate") {
        const res = await testDataApi.validate(item.id);
        setNotice(`Validation complete: ${res.data.quality_status.replace(/_/g, " ")} (${Math.round(res.data.quality_score)}).`);
      } else if (action === "mask") {
        await testDataApi.mask(item.id, { fields: item.sensitive_fields_json ?? [] });
        setNotice(`${item.data_id} masked.`);
      } else if (action === "reserve") {
        await testDataApi.reserve(item.id, { duration_minutes: 60 });
        setNotice(`${item.data_id} reserved for 60 minutes.`);
      } else if (action === "release") {
        await testDataApi.release(item.id);
        setNotice(`${item.data_id} released.`);
      } else if (action === "consume") {
        await testDataApi.consume(item.id);
        setNotice(`${item.data_id} marked consumed.`);
      } else if (action === "submit") {
        await testDataApi.submit(item.id, "Submitted from Test Data page");
        setNotice(`${item.data_id} submitted for approval.`);
      } else if (action === "approve") {
        await testDataApi.approve(item.id, "Approved from Test Data page");
        setNotice(`${item.data_id} approved.`);
      } else if (action === "reject") {
        await testDataApi.reject(item.id, "Rejected from Test Data page");
        setNotice(`${item.data_id} rejected.`);
      }
      await loadData();
    } catch (actionError) {
      setError(messageFromError(actionError, `Could not ${action} test data.`));
    } finally {
      setBusyItemId(null);
    }
  }

  const total = summary?.total_data_sets ?? items.length;
  const approved = summary?.approved ?? 0;
  const pending = summary?.pending_approval ?? 0;
  const synthetic = summary?.synthetic ?? 0;
  const masked = summary?.masked ?? 0;
  const reserved = summary?.reserved ?? 0;
  const expired = summary?.expired ?? 0;
  const linked = summary?.linked_test_cases ?? 0;
  const qualityIssues = summary?.data_quality_issues ?? 0;

  const approvedPct = total > 0 ? ((approved / total) * 100).toFixed(1) : "0.0";
  const pendingPct = total > 0 ? ((pending / total) * 100).toFixed(1) : "0.0";
  const syntheticPct = total > 0 ? ((synthetic / total) * 100).toFixed(1) : "0.0";
  const maskedPct = total > 0 ? ((masked / total) * 100).toFixed(1) : "0.0";
  const reservedPct = total > 0 ? ((reserved / total) * 100).toFixed(1) : "0.0";
  const expiredPct = total > 0 ? ((expired / total) * 100).toFixed(1) : "0.0";

  const cards = [
    {
      title: "Total Datasets",
      icon: Database,
      iconBg: "bg-blue-50 border-blue-100",
      iconColor: "text-blue-500",
      value: total.toLocaleString(),
      sublabel: "Total",
      footer: "100% of all datasets",
    },
    {
      title: "Approved",
      icon: ShieldCheck,
      iconBg: "bg-emerald-50 border-emerald-100",
      iconColor: "text-emerald-500",
      value: approved.toLocaleString(),
      sublabel: "Approved",
      footer: `${approvedPct}% of total datasets`,
    },
    {
      title: "Pending Approval",
      icon: Clock,
      iconBg: "bg-amber-50 border-amber-100",
      iconColor: "text-amber-500",
      value: pending.toLocaleString(),
      sublabel: "Pending",
      footer: `${pendingPct}% pending review`,
    },
    {
      title: "Synthetic",
      icon: Wand2,
      iconBg: "bg-purple-50 border-purple-100",
      iconColor: "text-purple-500",
      value: synthetic.toLocaleString(),
      sublabel: "Synthetic",
      footer: `${syntheticPct}% AI generated`,
    },
    {
      title: "Masked",
      icon: Shield,
      iconBg: "bg-cyan-50 border-cyan-100",
      iconColor: "text-cyan-500",
      value: masked.toLocaleString(),
      sublabel: "Masked",
      footer: `${maskedPct}% PII anonymized`,
    },
    {
      title: "Reserved",
      icon: Save,
      iconBg: "bg-orange-50 border-orange-100",
      iconColor: "text-orange-500",
      value: reserved.toLocaleString(),
      sublabel: "Reserved",
      footer: `${reservedPct}% reserved for runs`,
    },
    {
      title: "Expired",
      icon: XCircle,
      iconBg: "bg-red-50 border-red-100",
      iconColor: "text-red-500",
      value: expired.toLocaleString(),
      sublabel: "Expired",
      footer: `${expiredPct}% outdated data`,
    },
    {
      title: "Linked Test Cases",
      icon: CheckCircle,
      iconBg: "bg-slate-50 border-slate-100",
      iconColor: "text-slate-500",
      value: linked.toLocaleString(),
      sublabel: "Linked",
      footer: "Direct bindings to test cases",
    },
    {
      title: "Quality Issues",
      icon: AlertTriangle,
      iconBg: "bg-red-50 border-red-100",
      iconColor: "text-red-500",
      value: qualityIssues.toLocaleString(),
      sublabel: "Issues",
      footer: "Data validation error events",
    },
  ];

  return (
    <div className="space-y-6 select-none pb-8 animate-fade-in">
      {/* ── Title & Global Controls ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-blue-50 border border-blue-100 p-2.5">
            <Database className="h-6 w-6 text-[#1b59f8]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Test Data Set governs</h1>
            <p className="text-xs text-slate-500 mt-1">Manage synthetic profiles, PII masking rules, synthetic generations, validation runs, and test case bindings</p>
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
          <Button variant="outline" size="sm" onClick={loadData} className="h-8 w-8 p-0 border-slate-200">
            <RefreshCw className={cn("h-3.5 w-3.5 text-slate-500", loading && "animate-spin")} />
          </Button>
        </div>
      </div>

      {/* ── Status Counts Cards ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-9 gap-3">
        {cards.map((card) => {
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

      {/* ── Actions Card ───────────────────────────────────────────────────────── */}
      <Card className="border-slate-200 bg-white">
        <CardContent className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="h-9 w-9 shrink-0 flex items-center justify-center rounded-lg bg-blue-50 border border-blue-100">
              <Wand2 className="h-5 w-5 text-blue-500" />
            </div>
            <div>
              <h3 className="text-xs font-bold text-slate-800">Datasets Actions Hub</h3>
              <p className="text-[10px] text-slate-400 mt-1 leading-relaxed">Synthesise bulk rows, allocate manual mock values, or import external files to the active project</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 shrink-0">
            <Button
              variant="ai"
              size="sm"
              onClick={() => { setGenerateOpen(true); setError(""); }}
              disabled={!canGenerate}
              className="h-8 text-xs"
            >
              <Wand2 className="h-3.5 w-3.5" />
              Generate Data
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={() => { setCreateOpen(true); setError(""); }}
              disabled={!canCreate}
              className="h-8 text-xs font-semibold"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Manual Data
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => { setImportOpen(true); setError(""); }}
              disabled={!canImport}
              className="h-8 text-xs border-slate-200 font-semibold text-slate-600"
            >
              <Upload className="h-3.5 w-3.5" />
              Import CSV/Excel
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ── Filter Buttons ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-1.5 rounded-lg border border-slate-200 bg-white p-1 self-start w-fit">
        {FILTERS.map((value) => (
          <button
            key={value}
            onClick={() => setFilter(value)}
            className={cn(
              "rounded-md px-3 py-1 text-xs font-semibold capitalize transition-all",
              filter === value
                ? "bg-[#1b59f8] text-white shadow-sm"
                : "text-slate-500 hover:text-slate-900"
            )}
          >
            {value.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      {/* ── Datasets Table ────────────────────────────────────────────────────── */}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-full text-left border-collapse text-xs select-none">
          <thead className="bg-slate-50/70 border-b border-slate-200 text-[10px] font-bold uppercase tracking-wider text-slate-400">
            <tr>
              <th className="px-4 py-2.5">Data ID</th>
              <th className="px-4 py-2.5">Name</th>
              <th className="px-4 py-2.5">Type</th>
              <th className="px-4 py-2.5">Source</th>
              <th className="px-4 py-2.5">Env</th>
              <th className="px-4 py-2.5">Status</th>
              <th className="px-4 py-2.5">Generation</th>
              <th className="px-4 py-2.5">Records</th>
              <th className="px-4 py-2.5">Quality Score</th>
              <th className="px-4 py-2.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-600 font-medium">
            {loading ? (
              <tr>
                <td colSpan={10} className="px-4 py-16 text-center text-slate-400 font-semibold">
                  <Loader2 className="inline mr-2 h-4 w-4 animate-spin text-[#1b59f8]" />
                  Loading governed test data catalog...
                </td>
              </tr>
            ) : filteredItems.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-4 py-16 text-center text-slate-400 font-semibold">
                  No datasets found matching selection filter.
                </td>
              </tr>
            ) : (
              filteredItems.map((item) => {
                const isBusy = busyItemId === item.id;
                return (
                  <tr 
                    key={item.id} 
                    onClick={() => setSelectedItem(item)}
                    className={cn(
                      "hover:bg-slate-50/50 cursor-pointer transition-colors",
                      selectedItem?.id === item.id && "bg-[#1b59f8]/5"
                    )}
                  >
                    <td className="px-4 py-2.5 font-mono text-[11px] font-bold text-[#1b59f8]">{item.data_id}</td>
                    <td className="px-4 py-2.5 max-w-[200px] truncate">
                      <p className="font-bold text-slate-800 text-xs">{item.name}</p>
                      <p className="text-[10px] text-slate-400 truncate mt-0.5">{item.linked_requirement_key || "No spec link"}</p>
                    </td>
                    <td className="px-4 py-2.5 font-semibold text-slate-700">{item.data_type}</td>
                    <td className="px-4 py-2.5">
                      <Badge variant={item.source_type === "manual" ? "secondary" : "purple"} className="capitalize">
                        {item.source_type}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5 font-semibold text-slate-700">{item.environment}</td>
                    <td className="px-4 py-2.5">
                      <Badge variant={
                        item.approval_status === "approved" ? "success" :
                        item.approval_status === "rejected" ? "destructive" :
                        item.approval_status === "pending_approval" ? "warning" : "secondary"
                      } className="capitalize">
                        {item.approval_status}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge variant={
                        item.generation_status === "completed" || item.generation_status === "generated" ? "success" :
                        item.generation_status === "failed" ? "destructive" :
                        item.generation_status === "pending" || item.generation_status === "requested" ? "warning" : "secondary"
                      } className="capitalize">
                        {item.generation_status}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5 font-bold text-slate-800">{item.actual_record_count}</td>
                    <td className="px-4 py-2.5">
                      {item.quality_score != null ? (
                        <span className={cn(
                          "font-bold text-xs",
                          item.quality_score >= 80 ? "text-emerald-600" : item.quality_score >= 50 ? "text-amber-500" : "text-red-500"
                        )}>
                          {Math.round(item.quality_score)}/100
                        </span>
                      ) : <span className="text-slate-400 font-medium">-</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setSelectedItem(item)}
                        className="h-7 px-3 text-xs border-slate-200"
                      >
                        Details
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

      {/* ── Creation Manual Drawer ────────────────────────────────────────────── */}
      <Drawer open={createOpen} onOpenChange={setCreateOpen}>
        <DrawerContent size="xl">
          <DrawerHeader>
            <div className="flex items-center gap-2">
              <Database className="h-5 w-5 text-[#1b59f8]" />
              <div>
                <DrawerTitle>Add Manual Test Data Set</DrawerTitle>
                <DrawerDescription>Create a governed test data record with custom attributes and payload JSON</DrawerDescription>
              </div>
            </div>
            <button onClick={() => setCreateOpen(false)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-50"><X className="h-4 w-4" /></button>
          </DrawerHeader>
          <DrawerBody className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Dataset Name</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" placeholder="e.g. eSIM Activation Profiles" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Data Type</label>
              <select value={form.data_type} onChange={e => setForm(f => ({ ...f, data_type: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {DATA_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Environment</label>
              <select value={form.environment} onChange={e => setForm(f => ({ ...f, environment: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {ENVIRONMENT_OPTIONS.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Telecom Domain</label>
              <select value={form.telecom_domain} onChange={e => setForm(f => ({ ...f, telecom_domain: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {DOMAIN_OPTIONS.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Test Phase</label>
              <select value={form.test_phase} onChange={e => setForm(f => ({ ...f, test_phase: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {PHASE_OPTIONS.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Product Group</label>
              <select value={form.product_group} onChange={e => setForm(f => ({ ...f, product_group: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {PRODUCT_GROUP_OPTIONS.map(v => <option key={v} value={v}>{v || "None"}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Product</label>
              <select value={form.product} onChange={e => setForm(f => ({ ...f, product: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {PRODUCT_OPTIONS.map(v => <option key={v} value={v}>{v || "None"}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Sub Request Type</label>
              <select value={form.sub_request_type} onChange={e => setForm(f => ({ ...f, sub_request_type: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {SUB_REQUEST_TYPE_OPTIONS.map(v => <option key={v} value={v}>{v || "None"}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Privacy Level</label>
              <select value={form.privacy_level} onChange={e => setForm(f => ({ ...f, privacy_level: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {PRIVACY_LEVELS.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Tags</label>
              <input value={form.tags} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" placeholder="smoke, eSIM, activations" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Sensitive PII Fields</label>
              <input value={form.sensitive_fields} onChange={e => setForm(f => ({ ...f, sensitive_fields: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" placeholder="msisdn, email, imsi" />
            </div>
            <div className="flex items-center justify-between border rounded-lg p-2.5 bg-slate-50">
              <label className="text-xs font-bold text-slate-700">Contains PII</label>
              <input type="checkbox" checked={form.contains_pii} onChange={e => setForm(f => ({ ...f, contains_pii: e.target.checked }))} className="rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8] h-4.5 w-4.5" />
            </div>
            <div className="flex items-center justify-between border rounded-lg p-2.5 bg-slate-50">
              <label className="text-xs font-bold text-slate-700">Submit for Approval</label>
              <input type="checkbox" checked={form.submit_for_approval} onChange={e => setForm(f => ({ ...f, submit_for_approval: e.target.checked }))} className="rounded border-slate-300 text-[#1b59f8] focus:ring-[#1b59f8] h-4.5 w-4.5" />
            </div>
            <div className="flex flex-col gap-1 col-span-2">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Payload JSON</label>
              <textarea value={form.payload} onChange={e => setForm(f => ({ ...f, payload: e.target.value }))} rows={7} className="rounded-lg border border-slate-200 p-2 text-xs font-mono bg-slate-50" />
            </div>
          </DrawerBody>
          <DrawerFooter>
            <Button variant="outline" size="sm" onClick={() => setCreateOpen(false)} className="h-9 border-slate-200">Cancel</Button>
            <Button variant="default" size="sm" disabled={saving || !form.name.trim()} onClick={handleCreate} className="h-9 font-semibold">
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              Save Test Data
            </Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* ── AI / External Generation Drawer ───────────────────────────────────── */}
      <Drawer open={generateOpen} onOpenChange={setGenerateOpen}>
        <DrawerContent size="xl">
          <DrawerHeader>
            <div className="flex items-center gap-2">
              <Wand2 className="h-5 w-5 text-indigo-500" />
              <div>
                <DrawerTitle>Generate Synthetic Test Data</DrawerTitle>
                <DrawerDescription>Configure AI or external tools to generate synthetic datasets</DrawerDescription>
              </div>
            </div>
            <button onClick={() => setGenerateOpen(false)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-50"><X className="h-4 w-4" /></button>
          </DrawerHeader>
          <DrawerBody className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Data Set Name</label>
              <input value={generateForm.name} onChange={e => setGenerateForm(f => ({ ...f, name: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Data Type</label>
              <select value={generateForm.data_type} onChange={e => setGenerateForm(f => ({ ...f, data_type: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {DATA_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Environment</label>
              <select value={generateForm.environment} onChange={e => setGenerateForm(f => ({ ...f, environment: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {ENVIRONMENT_OPTIONS.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Telecom Domain</label>
              <select value={generateForm.telecom_domain} onChange={e => setGenerateForm(f => ({ ...f, telecom_domain: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {DOMAIN_OPTIONS.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Test Phase</label>
              <select value={generateForm.test_phase} onChange={e => setGenerateForm(f => ({ ...f, test_phase: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {PHASE_OPTIONS.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Product Group</label>
              <select value={generateForm.product_group} onChange={e => setGenerateForm(f => ({ ...f, product_group: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {PRODUCT_GROUP_OPTIONS.map(v => <option key={v} value={v}>{v || "None"}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Product</label>
              <select value={generateForm.product} onChange={e => setGenerateForm(f => ({ ...f, product: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {PRODUCT_OPTIONS.map(v => <option key={v} value={v}>{v || "None"}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Sub Request Type</label>
              <select value={generateForm.sub_request_type} onChange={e => setGenerateForm(f => ({ ...f, sub_request_type: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {SUB_REQUEST_TYPE_OPTIONS.map(v => <option key={v} value={v}>{v || "None"}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External Generation Tool</label>
              <select value={generateForm.external_tool} onChange={e => setGenerateForm(f => ({ ...f, external_tool: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {EXTERNAL_TOOLS.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Number of Records</label>
              <input type="number" min={1} max={10000} value={generateForm.number_of_records} onChange={e => setGenerateForm(f => ({ ...f, number_of_records: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Generation Mode</label>
              <select value={generateForm.generation_mode} onChange={e => setGenerateForm(f => ({ ...f, generation_mode: e.target.value as GenerateForm["generation_mode"] }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {GENERATION_MODES.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External Suite ID</label>
              <input value={generateForm.external_suite_id} onChange={e => setGenerateForm(f => ({ ...f, external_suite_id: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External Dataset ID</label>
              <input value={generateForm.external_dataset_id} onChange={e => setGenerateForm(f => ({ ...f, external_dataset_id: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">External URL</label>
              <input value={generateForm.external_url} onChange={e => setGenerateForm(f => ({ ...f, external_url: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" placeholder="https://..." />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Priority</label>
              <select value={generateForm.priority} onChange={e => setGenerateForm(f => ({ ...f, priority: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                {PRIORITIES.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1 col-span-2">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Generation Notes</label>
              <textarea value={generateForm.request_notes} onChange={e => setGenerateForm(f => ({ ...f, request_notes: e.target.value }))} rows={3} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" />
            </div>
          </DrawerBody>
          <DrawerFooter>
            <Button variant="outline" size="sm" onClick={() => setGenerateOpen(false)} className="h-9 border-slate-200">Cancel</Button>
            <Button variant="default" size="sm" disabled={generating || !generateForm.name.trim()} onClick={handleGenerate} className="h-9 font-semibold">
              {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
              Submit Generation Request
            </Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* ── CSV / Excel Import Drawer ─────────────────────────────────────────── */}
      <Drawer open={importOpen} onOpenChange={setImportOpen}>
        <DrawerContent size="xl">
          <DrawerHeader>
            <div className="flex items-center gap-2">
              <Upload className="h-5 w-5 text-indigo-500" />
              <div>
                <DrawerTitle>Import Test Data Set</DrawerTitle>
                <DrawerDescription>Upload a local CSV or Excel sheet to register rows in the project</DrawerDescription>
              </div>
            </div>
            <button onClick={() => setImportOpen(false)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-50"><X className="h-4 w-4" /></button>
          </DrawerHeader>
          <DrawerBody className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">File</label>
                <input type="file" accept=".csv,.xlsx,.xls" onChange={e => setImportForm(f => ({ ...f, file: e.target.files?.[0] ?? null }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-white" />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Dataset Name Override</label>
                <input value={importForm.name} onChange={e => setImportForm(f => ({ ...f, name: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50" />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Data Type</label>
                <select value={importForm.data_type} onChange={e => setImportForm(f => ({ ...f, data_type: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                  {DATA_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Telecom Domain</label>
                <select value={importForm.telecom_domain} onChange={e => setImportForm(f => ({ ...f, telecom_domain: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                  {DOMAIN_OPTIONS.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Test Phase</label>
                <select value={importForm.test_phase} onChange={e => setImportForm(f => ({ ...f, test_phase: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                  {PHASE_OPTIONS.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Product Group</label>
                <select value={importForm.product_group} onChange={e => setImportForm(f => ({ ...f, product_group: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                  {PRODUCT_GROUP_OPTIONS.map(v => <option key={v} value={v}>{v || "None"}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Product</label>
                <select value={importForm.product} onChange={e => setImportForm(f => ({ ...f, product: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                  {PRODUCT_OPTIONS.map(v => <option key={v} value={v}>{v || "None"}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Sub Request Type</label>
                <select value={importForm.sub_request_type} onChange={e => setImportForm(f => ({ ...f, sub_request_type: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                  {SUB_REQUEST_TYPE_OPTIONS.map(v => <option key={v} value={v}>{v || "None"}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Environment</label>
                <select value={importForm.environment} onChange={e => setImportForm(f => ({ ...f, environment: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                  {ENVIRONMENT_OPTIONS.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Privacy Level</label>
                <select value={importForm.privacy_level} onChange={e => setImportForm(f => ({ ...f, privacy_level: e.target.value }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                  {PRIVACY_LEVELS.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Import Mode</label>
                <select value={importForm.import_mode} onChange={e => setImportForm(f => ({ ...f, import_mode: e.target.value as ImportForm["import_mode"] }))} className="rounded-lg border border-slate-200 p-2 text-xs font-semibold bg-slate-50">
                  {IMPORT_MODES.map(v => <option key={v} value={v}>{v.replace(/_/g, " ")}</option>)}
                </select>
              </div>
            </div>

            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={handleImportPreview} disabled={previewingImport} className="h-8 text-xs">
                {previewingImport ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                Preview Import File
              </Button>
            </div>

            {/* Preview Section */}
            {importPreview && (
              <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                  <div>
                    <h4 className="font-bold text-slate-800 text-xs">Previewing Import Data</h4>
                    <p className="text-[10px] text-slate-400 mt-0.5">{importPreview.filename} • {importPreview.row_count} rows</p>
                  </div>
                  <Badge variant={importPreview.can_import ? "success" : "destructive"}>
                    {importPreview.can_import ? "Valid File" : "Invalid Layout"}
                  </Badge>
                </div>
                {importPreview.validation_errors.length > 0 && (
                  <div className="rounded-lg border border-red-200 bg-red-50 p-2.5 text-xs text-red-700">
                    {importPreview.validation_errors.map((item, idx) => <p key={idx}>{String(item.message ?? JSON.stringify(item))}</p>)}
                  </div>
                )}
                <div className="overflow-x-auto rounded-lg border max-h-40">
                  <table className="min-w-full text-left text-xs border-collapse">
                    <thead className="bg-slate-50 text-[10px] font-bold text-slate-500 border-b">
                      <tr>{importPreview.detected_columns.map(col => <th key={col} className="px-2.5 py-1.5">{col}</th>)}</tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {importPreview.preview_rows.slice(0, 5).map((row, rIdx) => (
                        <tr key={rIdx}>
                          {importPreview.detected_columns.map(col => <td key={col} className="px-2.5 py-1.5 truncate max-w-[120px]">{String(row[col] ?? "")}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="default"
                    size="sm"
                    disabled={!importPreview.can_import || confirmingImport}
                    onClick={handleImportConfirm}
                    className="h-8 bg-emerald-600 hover:bg-emerald-700 font-semibold"
                  >
                    {confirmingImport ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle className="h-3.5 w-3.5" />}
                    Confirm Import
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setImportPreview(null)} className="h-8 border-slate-200 text-xs">
                    Reset Preview
                  </Button>
                </div>
              </div>
            )}
          </DrawerBody>
          <DrawerFooter>
            <Button variant="outline" size="sm" onClick={() => setImportOpen(false)} className="h-9 border-slate-200">Cancel</Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* ── Right-Side Detail Drawer (Sliding dataset controls) ────────────────── */}
      <Drawer open={selectedItem !== null} onOpenChange={(open) => { if (!open) setSelectedItem(null); }}>
        <DrawerContent size="lg">
          {selectedItem && (
            <>
              <DrawerHeader>
                <div className="min-w-0">
                  <span className="font-mono text-xs font-bold text-[#1b59f8]">
                    {selectedItem.data_id}
                  </span>
                  <DrawerTitle className="mt-1.5 truncate text-slate-800" title={selectedItem.name}>
                    {selectedItem.name}
                  </DrawerTitle>
                  <DrawerDescription>
                    Governance parameters, synthetic preview payloads, and dataset validation gates
                  </DrawerDescription>
                </div>
                <DrawerClose asChild>
                  <button 
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-50 hover:text-slate-600 focus:outline-none"
                  >
                    <X className="h-4.5 w-4.5" />
                  </button>
                </DrawerClose>
              </DrawerHeader>

              {/* Tabs */}
              <div className="flex border-b border-slate-100 px-4 shrink-0 bg-slate-50/50">
                {(["attributes", "payload", "history"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setDrawerTab(tab)}
                    className={cn(
                      "px-4 py-2.5 text-xs font-semibold capitalize border-b-2 -mb-px transition-colors focus:outline-none",
                      drawerTab === tab
                        ? "border-[#1b59f8] text-[#1b59f8]"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    )}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              {/* Drawer Body */}
              <DrawerBody className="p-5">
                {/* TAB 1: ATTRIBUTES & ACTION BUTTONS */}
                {drawerTab === "attributes" && (
                  <div className="space-y-5">
                    {/* Attributes Grid */}
                    <div className="grid grid-cols-2 gap-3 text-xs bg-slate-50 p-4 rounded-xl border border-slate-100">
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Data Type</p>
                        <p className="font-bold text-slate-700 mt-1">{selectedItem.data_type}</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Environment</p>
                        <p className="font-bold text-slate-700 mt-1">{selectedItem.environment}</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Telecom Domain</p>
                        <p className="font-bold text-slate-700 mt-1">{selectedItem.telecom_domain || "Generic"}</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Privacy Level</p>
                        <p className="font-bold text-slate-700 mt-1 capitalize">{selectedItem.privacy_level}</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Contains PII</p>
                        <p className="font-bold text-slate-700 mt-1">{selectedItem.contains_pii ? "Yes" : "No"}</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Quality Score</p>
                        <p className="font-bold text-slate-700 mt-1">
                          {selectedItem.quality_score != null ? `${Math.round(selectedItem.quality_score)}/100` : "Not Evaluated"}
                        </p>
                      </div>
                    </div>

                    {/* Quality Gate Issues */}
                    {selectedItem.quality_issues_json && selectedItem.quality_issues_json.length > 0 && (
                      <div className="space-y-1.5">
                        <label className="text-[10px] font-bold uppercase tracking-wider text-red-500">Quality Issues Identified</label>
                        <div className="rounded-xl border border-red-200 bg-red-50/50 p-3 space-y-1 text-xs text-red-700">
                          {selectedItem.quality_issues_json.map((issue, idx) => (
                            <p key={idx} className="font-medium">• {String(issue.message ?? JSON.stringify(issue))}</p>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Operational controls */}
                    <div className="space-y-2">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">TDM Operations & Controls</label>
                      <div className="grid grid-cols-2 gap-2">
                        {/* 1. Validation */}
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => runAction(selectedItem, "validate")}
                          className="h-8 text-xs border-slate-200 justify-start"
                        >
                          <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
                          Validate Quality
                        </Button>

                        {/* 2. Masking */}
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={!canMask || !selectedItem.contains_pii}
                          onClick={() => runAction(selectedItem, "mask")}
                          className="h-8 text-xs border-slate-200 justify-start"
                        >
                          <Shield className="h-3.5 w-3.5 text-indigo-500" />
                          Mask PII Payload
                        </Button>

                        {/* 3. Reservation */}
                        {selectedItem.reservation_status !== "reserved" ? (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={!canReserve}
                            onClick={() => runAction(selectedItem, "reserve")}
                            className="h-8 text-xs border-slate-200 justify-start"
                          >
                            <Clock className="h-3.5 w-3.5 text-orange-500" />
                            Reserve dataset
                          </Button>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => runAction(selectedItem, "release")}
                            className="h-8 text-xs border-slate-200 justify-start bg-orange-50"
                          >
                            <XCircle className="h-3.5 w-3.5 text-orange-600" />
                            Release reservation
                          </Button>
                        )}

                        {/* 4. Consumed */}
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => runAction(selectedItem, "consume")}
                          className="h-8 text-xs border-slate-200 justify-start"
                        >
                          <PlayCircle className="h-3.5 w-3.5 text-blue-500" />
                          Mark as Consumed
                        </Button>
                      </div>
                    </div>

                    {/* Approval Quality Sign-off */}
                    {selectedItem.approval_status === "pending_approval" && (
                      <div className="space-y-2 border-t border-slate-100 pt-4">
                        <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Approval Quality Gate</label>
                        <div className="flex gap-2">
                          <Button
                            variant="default"
                            size="sm"
                            disabled={!canApprove}
                            onClick={() => runAction(selectedItem, "approve")}
                            className="bg-emerald-600 hover:bg-emerald-700 h-8 text-xs font-semibold flex-1"
                          >
                            <Check className="h-3.5 w-3.5" />
                            Approve Dataset
                          </Button>
                          <Button
                            variant="destructive"
                            size="sm"
                            disabled={!canApprove}
                            onClick={() => runAction(selectedItem, "reject")}
                            className="h-8 text-xs font-semibold flex-1"
                          >
                            <X className="h-3.5 w-3.5" />
                            Reject Dataset
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* TAB 2: PAYLOAD JSON PREVIEW */}
                {drawerTab === "payload" && (
                  <div className="space-y-2.5">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Sample Records Payload JSON</label>
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-xs overflow-auto max-h-96">
                      <pre>{JSON.stringify(selectedItem.data_payload_json || selectedItem.sample_preview_json || {}, null, 2)}</pre>
                    </div>
                  </div>
                )}

                {/* TAB 3: TIMELINE logs */}
                {drawerTab === "history" && (
                  <div className="space-y-3">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Dataset Activity History</label>
                    {historyLoading ? (
                      <div className="flex items-center justify-center py-8 text-xs text-slate-400">
                        <Loader2 className="mr-2 h-4 w-4 animate-spin text-[#1b59f8]" />
                        Fetching activity log...
                      </div>
                    ) : historyRows.length === 0 ? (
                      <p className="text-xs text-slate-400 font-medium italic p-2 bg-slate-50/50 rounded border">No history records mapped for this dataset.</p>
                    ) : (
                      <div className="space-y-2">
                        {historyRows.map((row) => (
                          <div key={row.id} className="rounded-lg border border-slate-200 p-3 text-xs bg-white space-y-1">
                            <div className="flex items-center justify-between">
                              <Badge variant="secondary" className="text-[10px] font-bold uppercase">{row.action_type}</Badge>
                              <span className="text-[10px] text-slate-400 font-semibold">{new Date(row.created_at).toLocaleString()}</span>
                            </div>
                            <p className="text-slate-800 font-semibold text-[11px] mt-1.5">Decision: {row.decision.replace(/_/g, " ")}</p>
                            {row.notes && <p className="text-[10px] text-slate-400 italic mt-0.5">Notes: {row.notes}</p>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </DrawerBody>

              <DrawerFooter>
                <DrawerClose asChild>
                  <Button variant="outline" size="sm" className="h-9 border-slate-200">Close</Button>
                </DrawerClose>
              </DrawerFooter>
            </>
          )}
        </DrawerContent>
      </Drawer>
    </div>
  );
}

// ── Root Wrapper with Suspense ────────────────────────────────────────────────
export default function TestDataPage() {
  return (
    <Suspense fallback={
      <div className="p-8 text-center text-xs text-slate-500 font-semibold flex items-center justify-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin text-[#1b59f8]" />
        Loading Test Data Governs Catalog...
      </div>
    }>
      <TestDataContent />
    </Suspense>
  );
}
