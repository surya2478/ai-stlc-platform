"use client";

/**
 * Knowledge Base — the RAG workspace: what the project has indexed, what is
 * still being ingested, what a query retrieves, and what a generated artifact
 * was actually grounded on.
 *
 * Built on the same chrome as the other governed workspaces — Breadcrumb,
 * WorkspaceHeader, StatCard, GuidanceCard, ListShell, EmptyState from
 * components/applications/workspace — so this reads as part of the app rather
 * than a page with its own conventions.
 *
 * Every number and row comes from a real endpoint: /rag/.../status,
 * /rag/.../search, /rag/.../artifacts/{type}/{id}/citations, and /documents.
 * Where the screen design asks for something the backend does not hold, the
 * tab says so instead of rendering a control that would discard its input.
 */

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  CheckCircle2,
  Database,
  FileStack,
  FileText,
  Layers,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";
import {
  documentsApi,
  ragApi,
  type Document as UploadedDocument,
  type RagCitation,
  type RagProjectStatus,
  type RagSearchResponse,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import {
  Breadcrumb,
  EmptyState,
  GuidanceCard,
  ListShell,
  StatCard,
  WorkspaceHeader,
} from "@/components/applications/workspace";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "summary", label: "Summary" },
  { key: "sources", label: "Sources" },
  { key: "ingestion", label: "Ingestion status" },
  { key: "search", label: "Knowledge search" },
  { key: "trace", label: "Retrieval trace" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

/** The document lifecycle the backend actually writes, in order.
 *
 *  "indexed" is deliberately absent: indexing writes rows into
 *  knowledge_chunks and never touches UploadedDocument.status, so a document
 *  stays "processed" for good. Counting an "indexed" status made that box read
 *  0 while the corpus held chunks for the very same file. The indexed figure
 *  now comes from the chunks themselves. */
const PIPELINE = ["uploaded", "processing", "processed"] as const;

const ARTIFACT_TYPES = [
  { value: "requirement", label: "Requirement" },
  { value: "test_case", label: "Test case" },
  { value: "test_scenario", label: "Test scenario" },
  { value: "automation_script", label: "Automation script" },
];

const SOURCES_GRID = "minmax(260px,3fr) 90px 90px 80px 120px 140px 60px";

function statusTone(status: string): "success" | "warning" | "destructive" | "outline" {
  const s = status.toLowerCase();
  if (s === "indexed" || s === "processed") return "success";
  if (s === "failed" || s === "error") return "destructive";
  if (s === "processing" || s === "uploaded" || s === "extracting") return "warning";
  return "outline";
}

function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function KnowledgeBaseContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { toast } = useToast();
  const projectId = Number(searchParams.get("project")) || null;

  // The active section lives in `?view=`, not in component state: the sidebar
  // links straight to each one, and isActiveHref discriminates on that exact
  // parameter — the same contract Test Cases and Applications use. It also
  // makes a section linkable.
  const requestedView = searchParams.get("view");
  const tab: TabKey = TABS.some((t) => t.key === requestedView)
    ? (requestedView as TabKey)
    : "summary";

  const setTab = useCallback(
    (next: TabKey) => {
      const params = new URLSearchParams(searchParams.toString());
      // "summary" is the fallback, so it is expressed by the absence of the
      // parameter rather than by spelling it out.
      if (next === "summary") params.delete("view");
      else params.set("view", next);
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );
  const [status, setStatus] = useState<RagProjectStatus | null>(null);
  const [documents, setDocuments] = useState<UploadedDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");

  const [uploading, setUploading] = useState(false);
  const [reindexing, setReindexing] = useState(false);

  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<RagSearchResponse | null>(null);

  const [artifactType, setArtifactType] = useState(ARTIFACT_TYPES[0].value);
  const [artifactId, setArtifactId] = useState("");
  const [citations, setCitations] = useState<RagCitation[] | null>(null);
  const [tracing, setTracing] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setLoadError("");
    try {
      const [statusRes, docsRes] = await Promise.all([
        ragApi.status(projectId),
        documentsApi.list(projectId),
      ]);
      setStatus(statusRes.data);
      setDocuments(docsRes.data);
    } catch {
      setLoadError("Could not load the knowledge base for this project.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const sourceTypes = useMemo(() => {
    const counts = new Map<string, number>();
    for (const doc of documents) {
      const key = (doc.file_type || "unknown").toUpperCase();
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [documents]);

  const failedDocs = useMemo(
    () => documents.filter((d) => ["failed", "error"].includes((d.status || "").toLowerCase())),
    [documents],
  );

  const lastIngestion = useMemo(() => {
    if (documents.length === 0) return "—";
    const newest = documents
      .map((d) => new Date(d.created_at).getTime())
      .filter((t) => !Number.isNaN(t))
      .sort((a, b) => b - a)[0];
    return newest ? new Date(newest).toLocaleDateString() : "—";
  }, [documents]);

  async function handleUpload(files: FileList | null) {
    if (!projectId || !files || files.length === 0) return;
    setUploading(true);
    let uploaded = 0;
    const failures: string[] = [];
    for (const file of Array.from(files)) {
      try {
        await documentsApi.upload(projectId, file);
        uploaded += 1;
      } catch (err: unknown) {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        failures.push(`${file.name}: ${detail ?? "upload failed"}`);
      }
    }
    setUploading(false);
    await load();
    if (uploaded > 0) {
      toast({
        title: `${uploaded} file(s) uploaded`,
        description: "Text extraction runs in the background; the Ingestion status tab tracks it.",
      });
    }
    if (failures.length > 0) {
      toast({ title: "Some files were rejected", description: failures.join(" · "), variant: "error" });
    }
  }

  async function handleReindex() {
    if (!projectId) return;
    setReindexing(true);
    try {
      const res = await ragApi.reindex(projectId);
      toast({
        title: "Reindex queued",
        description: `${res.data.documents_queued} document(s) and ${res.data.requirements_queued} requirement(s). ${res.data.message}`,
      });
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast({ title: "Could not reindex", description: detail ?? "Unknown error", variant: "error" });
    } finally {
      setReindexing(false);
    }
  }

  async function handleDelete(doc: UploadedDocument) {
    if (!confirm(`Remove "${doc.original_filename}" from the knowledge base?`)) return;
    try {
      await documentsApi.delete(doc.id);
      toast({ title: "Source removed" });
      await load();
    } catch {
      toast({ title: "Could not remove the source", variant: "error" });
    }
  }

  async function handleSearch() {
    if (!projectId || !query.trim()) return;
    setSearching(true);
    setResults(null);
    try {
      const res = await ragApi.search(projectId, { query: query.trim(), top_k: 10 });
      setResults(res.data);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast({ title: "Search failed", description: detail ?? "Unknown error", variant: "error" });
    } finally {
      setSearching(false);
    }
  }

  async function handleTrace() {
    if (!projectId || !artifactId.trim()) return;
    setTracing(true);
    setCitations(null);
    try {
      const res = await ragApi.citations(projectId, artifactType, Number(artifactId));
      setCitations(res.data);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast({ title: "Could not load the trace", description: detail ?? "Unknown error", variant: "error" });
    } finally {
      setTracing(false);
    }
  }

  if (!projectId) {
    return (
      <div className="space-y-4 pb-8">
        <Breadcrumb trail={["QAI Command Center", "Operations", "Knowledge Base"]} />
        <div className="rounded-lg border border-gray-200 bg-white px-6 py-16 shadow-sm">
          <EmptyState
            title="No project selected"
            detail="The knowledge base is project-scoped — every source, chunk and citation belongs to one project. Pick a project from the header to open its corpus."
          />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 pb-8">
      <Breadcrumb trail={["QAI Command Center", "Operations", "Knowledge Base"]} />

      <WorkspaceHeader
        icon={Database}
        tone="blue"
        title="Knowledge Base"
        badge="RAG"
        description="Traceable, project-scoped knowledge for requirement analysis and test generation."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
              <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} /> Refresh
            </Button>
            <Button size="sm" onClick={() => void handleReindex()} disabled={reindexing}>
              {reindexing ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Database className="mr-2 h-4 w-4" />
              )}
              Reprocess index
            </Button>
          </>
        }
      />

      {status && !status.rag_enabled && (
        <GuidanceCard
          tone="amber"
          title="Retrieval is switched off for this deployment"
          detail="RAG_ENABLED is false, so nothing new is embedded and no query is answered from this corpus. Chunks already indexed are still listed below."
        />
      )}

      {loadError && <GuidanceCard tone="red" title="Could not load the knowledge base" detail={loadError} />}

      {/* Section tabs. Same shape as QueueTabs, without its count badge — these
          are sections rather than queues, and a "0" beside Search would be a
          number that means nothing. */}
      <div className="flex flex-wrap items-center gap-1 rounded-lg bg-gray-50 p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "inline-flex h-8 items-center rounded-md px-3 text-xs font-bold transition",
              tab === t.key ? "bg-[#4D0507] text-white" : "text-gray-600 hover:bg-white",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* A — Knowledge summary */}
      {tab === "summary" && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard title="Total sources" value={documents.length} subtitle="Uploaded documents" icon={FileStack} tone="blue" />
            <StatCard
              title="Indexed sources"
              value={status?.indexed_documents ?? 0}
              subtitle={`+ ${status?.indexed_jira_stories ?? 0} Jira stories`}
              icon={CheckCircle2}
              tone="emerald"
            />
            <StatCard
              title="Failed sources"
              value={failedDocs.length}
              subtitle={failedDocs.length ? "See Ingestion status" : "None"}
              icon={XCircle}
              tone={failedDocs.length ? "red" : "slate"}
            />
            <StatCard title="Last ingestion" value={lastIngestion} subtitle="Most recent upload" icon={Upload} tone="slate" />
            <StatCard title="Chunks" value={status?.total_active_chunks ?? 0} subtitle="Active in pgvector" icon={Layers} tone="purple" />
            <StatCard
              title="Embedded"
              value={status?.embedded_chunks ?? 0}
              subtitle={`${status?.unembedded_chunks ?? 0} awaiting embedding`}
              icon={Sparkles}
              tone="purple"
            />
            <StatCard
              title="Index coverage"
              value={`${status?.index_coverage_pct ?? 0}%`}
              subtitle="Chunks carrying an embedding"
              icon={Database}
              tone="blue"
            />
            <StatCard
              title="Retrieval"
              value={status?.rag_enabled ? "Online" : "Disabled"}
              subtitle={status?.embedding_model ?? "—"}
              icon={Search}
              tone={status?.rag_enabled ? "emerald" : "amber"}
            />
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-extrabold text-gray-700">Source types</p>
            {sourceTypes.length === 0 ? (
              <p className="mt-2 text-[11px] font-semibold text-gray-500">
                No sources uploaded for this project yet.
              </p>
            ) : (
              <div className="mt-2.5 flex flex-wrap gap-2">
                {sourceTypes.map(([type, count]) => (
                  <Badge key={type} variant="secondary">
                    {type} · {count}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* B — Source ingestion */}
      {tab === "sources" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <label
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-gray-200 px-6 py-10 text-center transition hover:border-app-brand-300",
                uploading && "pointer-events-none opacity-60",
              )}
            >
              <Upload className="h-7 w-7 text-[#B71920]" />
              <span className="text-xs font-extrabold text-gray-700">
                {uploading ? "Uploading…" : "Drop requirement files here or browse"}
              </span>
              <span className="text-[11px] font-semibold text-gray-500">
                PDF, DOCX, TXT, MD, CSV · bulk upload supported
              </span>
              <input
                type="file"
                multiple
                className="hidden"
                disabled={uploading}
                onChange={(e) => void handleUpload(e.target.files)}
              />
            </label>
          </div>

          {/* Stated rather than mocked: these are the screen-design fields the
              upload endpoint does not accept, so no input for them is drawn. */}
          <GuidanceCard
            tone="amber"
            title="Source metadata is not stored yet"
            detail="Domain, channel, product, version, effective date, tags, access classification and processing profile have no column today, and neither does duplicate detection or version handling. A file uploaded here is scoped to its project and nothing else — those fields need a knowledge-source model and migration before this form can collect them without dropping them."
          />

          <ListShell
            columns={["File", "Type", "Size", "Pages", "Status", "Uploaded", ""]}
            gridTemplate={SOURCES_GRID}
            minWidth={900}
            loading={loading}
            empty={
              documents.length === 0 ? (
                <EmptyState
                  title="No sources yet"
                  detail="Upload requirement documents, business rules or process documentation above. Text is extracted, chunked and embedded so agents can ground their output on it."
                />
              ) : undefined
            }
          >
            {documents.map((doc) => (
              <div
                key={doc.id}
                style={{ gridTemplateColumns: SOURCES_GRID }}
                className="grid w-full items-center gap-2 px-3 py-2.5 text-[11px] transition hover:bg-gray-50"
              >
                <span className="flex min-w-0 items-center gap-2 font-bold text-gray-800">
                  <FileText className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                  <span className="truncate">{doc.original_filename}</span>
                </span>
                <span className="font-semibold uppercase text-gray-500">{doc.file_type}</span>
                <span className="tabular-nums font-semibold text-gray-500">{fileSize(doc.file_size_bytes)}</span>
                <span className="tabular-nums font-semibold text-gray-500">{doc.page_count ?? "—"}</span>
                <span>
                  <Badge variant={statusTone(doc.status)}>{doc.status}</Badge>
                </span>
                <span className="font-semibold text-gray-500">
                  {new Date(doc.created_at).toLocaleDateString()}
                </span>
                <span className="text-right">
                  <button
                    onClick={() => void handleDelete(doc)}
                    className="rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-red-600"
                    title="Remove from knowledge base"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </span>
              </div>
            ))}
          </ListShell>
        </div>
      )}

      {/* C — Ingestion status */}
      {tab === "ingestion" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-extrabold text-gray-700">Pipeline</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {PIPELINE.map((stage) => {
                const count = documents.filter((d) => (d.status || "").toLowerCase() === stage).length;
                return (
                  <span key={stage} className="flex items-center gap-2">
                    <span className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5">
                      <span className="text-[11px] font-extrabold capitalize text-gray-700">{stage}</span>
                      <span className="ml-2 text-[11px] font-bold tabular-nums text-gray-500">{count}</span>
                    </span>
                    <span className="text-gray-300">→</span>
                  </span>
                );
              })}
              {/* Counted from knowledge_chunks, not from a document status —
                  see the note on PIPELINE. */}
              <span className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5">
                <span className="text-[11px] font-extrabold text-emerald-800">Indexed</span>
                <span className="ml-2 text-[11px] font-bold tabular-nums text-emerald-700">
                  {status?.indexed_documents ?? 0}
                </span>
              </span>
            </div>
            <p className="mt-3 text-[11px] font-semibold leading-5 text-gray-500">
              The first three are the states the ingestion pipeline writes on the document itself. Indexing never
              changes that status — it writes chunks — so <span className="font-extrabold">Indexed</span> counts
              documents that actually have active chunks in pgvector
              ({status?.embedded_chunks ?? 0} of {status?.total_active_chunks ?? 0} chunks embedded across this
              project). A document can therefore sit at &ldquo;processed&rdquo; and be fully indexed at the same time.
            </p>
          </div>

          {failedDocs.length > 0 ? (
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <p className="text-xs font-extrabold text-gray-700">Failures</p>
              <div className="mt-3 space-y-2">
                {failedDocs.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50/60 px-3 py-2"
                  >
                    <span className="text-[11px] font-extrabold text-red-900">{doc.original_filename}</span>
                    {/* The failing stage is all the list endpoint returns — the
                        reason lives in the document's metadata, which
                        DocumentListOut does not carry. */}
                    <span className="text-[11px] font-semibold text-red-700">Failed at: {doc.status}</span>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-[11px] font-semibold text-gray-500">
                Reprocess index re-queues every document and requirement in the project; there is no per-source retry
                endpoint yet.
              </p>
            </div>
          ) : (
            <GuidanceCard
              tone="emerald"
              title="No failed sources"
              detail="Every source in this project came through extraction without error."
            />
          )}
        </div>
      )}

      {/* D — Knowledge search */}
      {tab === "search" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleSearch();
              }}
              placeholder="Ask in natural language, e.g. how is a postpaid order fallout handled?"
              className="h-9 flex-1 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 outline-none focus:border-app-brand-300 focus:ring-2 focus:ring-app-brand-100"
            />
            <Button size="sm" onClick={() => void handleSearch()} disabled={searching || !query.trim()}>
              {searching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}
              Search
            </Button>
          </div>

          {results && (
            <>
              <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold text-gray-500">
                <span>
                  {results.chunks.length} of {results.total_candidates} candidate chunk(s)
                </span>
                <span className="text-gray-300">·</span>
                <span className="tabular-nums">{results.elapsed_ms.toFixed(0)} ms</span>
                {!results.grounded && (
                  <Badge variant="warning">Not grounded — nothing in this project matched</Badge>
                )}
              </div>

              {results.chunks.map((chunk) => (
                <div key={chunk.chunk_id} className="space-y-2 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                    <Badge variant="secondary">{chunk.source_type}</Badge>
                    {chunk.section && <span className="font-semibold text-gray-500">{chunk.section}</span>}
                    <span className="ml-auto font-semibold tabular-nums text-gray-500">
                      relevance {chunk.hybrid_score.toFixed(3)}
                      {chunk.semantic_score !== null && ` · semantic ${chunk.semantic_score.toFixed(3)}`}
                      {chunk.keyword_score !== null && ` · keyword ${chunk.keyword_score.toFixed(3)}`}
                    </span>
                  </div>
                  <p className="whitespace-pre-wrap text-xs leading-6 text-gray-700">{chunk.chunk_text}</p>
                </div>
              ))}

              {results.chunks.length === 0 && (
                <div className="rounded-lg border border-gray-200 bg-white px-6 py-16 shadow-sm">
                  <EmptyState
                    title="No chunk matched that query"
                    detail="Try different wording, or check on the Summary tab that this project has sources indexed at all."
                  />
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* E — Retrieval trace */}
      {tab === "trace" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div>
              <label className="mb-1 block text-[10px] font-extrabold uppercase tracking-wide text-gray-500">
                Artifact
              </label>
              <select
                value={artifactType}
                onChange={(e) => setArtifactType(e.target.value)}
                className="h-9 rounded-lg border border-gray-200 bg-white px-3 text-xs font-bold text-gray-600 outline-none focus:border-app-brand-300 focus:ring-2 focus:ring-app-brand-100"
              >
                {ARTIFACT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-extrabold uppercase tracking-wide text-gray-500">ID</label>
              <input
                value={artifactId}
                onChange={(e) => setArtifactId(e.target.value.replace(/[^0-9]/g, ""))}
                placeholder="e.g. 42"
                className="h-9 w-28 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 outline-none focus:border-app-brand-300 focus:ring-2 focus:ring-app-brand-100"
              />
            </div>
            <Button size="sm" onClick={() => void handleTrace()} disabled={tracing || !artifactId.trim()}>
              {tracing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Show trace
            </Button>
          </div>

          {citations && citations.length === 0 && (
            <div className="rounded-lg border border-gray-200 bg-white px-6 py-16 shadow-sm">
              <EmptyState
                title="No citation recorded"
                detail="That artifact was generated without retrieved knowledge, or it predates citation capture. Nothing is inferred here — an empty trace means the corpus did not influence it."
              />
            </div>
          )}

          {citations?.map((c) => (
            <div key={c.id} className="space-y-2 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <Badge variant="secondary">{c.source_type ?? "unknown source"}</Badge>
                {c.section && <span className="font-semibold text-gray-500">{c.section}</span>}
                <span className="ml-auto font-semibold tabular-nums text-gray-500">
                  {c.retrieval_score !== null && `retrieval ${c.retrieval_score.toFixed(3)}`}
                  {c.rerank_score !== null && ` · rerank ${c.rerank_score.toFixed(3)}`}
                </span>
              </div>
              {c.chunk_text && (
                <p className="whitespace-pre-wrap text-xs leading-6 text-gray-700">{c.chunk_text}</p>
              )}
              {c.citation_reason && (
                <p className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-[11px] font-semibold leading-5 text-gray-600">
                  <span className="font-extrabold text-gray-800">How it was used: </span>
                  {c.citation_reason}
                </p>
              )}
              <p className="text-[10px] font-semibold text-gray-400">
                Chunk #{c.chunk_id} · cited {new Date(c.created_at).toLocaleString()}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function KnowledgeBasePage() {
  return (
    <Suspense
      fallback={<div className="p-6 text-xs font-semibold text-gray-500">Loading knowledge base…</div>}
    >
      <KnowledgeBaseContent />
    </Suspense>
  );
}
