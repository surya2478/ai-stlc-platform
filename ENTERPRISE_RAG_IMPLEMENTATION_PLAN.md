# Enterprise RAG Implementation Plan

Date: 2026-06-15

Scope: implement enterprise-grade retrieval-augmented generation for the STLC platform, starting with requirement documents and expanding to test plans, test cases, defects, execution evidence, Jira artifacts, and domain knowledge.

## 1. Target Outcome

The platform should generate test artifacts from grounded, traceable project context rather than only from prompt text. When a user uploads a requirement document and later asks for test scenarios, test cases, automation, defect analysis, or reports, the system should retrieve the most relevant approved context, pass it to the LLM, and store citations so every generated artifact can be audited.

Target flow:

```text
Upload document
  -> extract text
  -> normalize and classify sections
  -> split into semantic chunks
  -> generate embeddings
  -> store chunks, metadata, and vectors
  -> retrieve relevant chunks for an agent task
  -> rerank and permission-filter context
  -> send grounded context to Groq or fallback LLM
  -> validate output
  -> store generated artifact with citations and audit trail
```

## 2. Recommended Enterprise Architecture

Use the existing FastAPI, PostgreSQL, Redis, Celery, and LangGraph foundation. Add retrieval as a first-class backend capability rather than replacing the current agent framework.

Recommended initial stack:

| Layer | Recommended Choice | Reason |
|---|---|---|
| LLM generation | Groq OpenAI-compatible provider | Already supported in `app.llm.provider`; fast and low-cost for generation |
| Fallback LLMs | OpenRouter, Gemini, Ollama, or existing project-level routing | The repo already has provider routing/fallback patterns |
| Embeddings | `BAAI/bge-small-en-v1.5` for MVP, `bge-base` or `bge-large` later | Good local/open embedding path with stronger retrieval quality than many tiny models |
| Vector store | PostgreSQL + pgvector for first enterprise release | Repo already runs PostgreSQL with pgvector image; avoids a second datastore early |
| Future vector store | Qdrant | Add when vector volume, multi-tenant filtering, or operational needs outgrow pgvector |
| Agent orchestration | Keep LangGraph | Existing agents already use it |
| Retrieval framework | Custom service first | Better fit for RBAC, audit, project scoping, citations, and existing SQLAlchemy models |
| Async processing | Celery | Existing background worker already handles document extraction and agents |
| Object storage | Existing local storage now, S3-compatible storage for production | Original files should remain immutable and retrievable |

## 3. Current State Summary

The platform is ready for RAG infrastructure work but is not currently RAG-enabled.

Current strengths:

- `UploadedDocument` stores extracted text.
- `RequirementChunk` exists as a RAG-oriented table stub.
- PostgreSQL uses the `pgvector/pgvector:pg16` Docker image.
- Agents already use a common LLM provider abstraction.
- Groq is supported as an OpenAI-compatible provider.
- Celery is available for asynchronous extraction and agent jobs.
- Project membership and RBAC exist and should be enforced during retrieval.

Current gaps:

- No embedding model configuration.
- No embedding service.
- No vector column on chunks.
- No chunk indexing job.
- No similarity search or hybrid retrieval service.
- No reranking.
- No prompt context injection layer.
- No source citations on generated artifacts.
- No RAG evaluation or quality monitoring.
- No prompt-injection controls around uploaded text.

## 4. Implementation Principles

1. Preserve project isolation. Every retrieval query must filter by `project_id` and the caller's access.
2. Prefer governed context over maximal context. Small, precise, cited chunks are better than large noisy excerpts.
3. Store provenance. Generated artifacts must know which chunks, document versions, prompts, and models influenced them.
4. Support reindexing. Embeddings must be refreshable when content, chunking strategy, or embedding model changes.
5. Make retrieval measurable. Track relevance, coverage, faithfulness, latency, and empty-result rates.
6. Keep the MVP deployable. Start with pgvector and local embeddings, then add Qdrant only when needed.

## 5. Phase 0 - Decisions And Baseline

Goal: lock choices before code changes.

Tasks:

1. Select initial embedding model.
2. Confirm initial vector store.
3. Define chunking strategy for requirements.
4. Define source citation requirements.
5. Decide which agents get RAG first.
6. Define evaluation dataset with representative telecom requirement documents.

Recommended decisions:

- Embedding model: `BAAI/bge-small-en-v1.5`
- Vector store: PostgreSQL + pgvector
- First RAG scope: requirement intake, scenario generation, test case generation
- Chunk size: 500-900 tokens with section-aware boundaries
- Retrieval default: top 12 semantic candidates, rerank to top 5 context chunks
- Context format: XML-like blocks with citation IDs

Example context format:

```xml
<retrieved_context>
  <chunk id="REQDOC-12#chunk-004" source="BRD_Mobile_Billing.pdf" section="Acceptance Criteria" score="0.84">
    Customer must receive a prorated invoice when plan upgrade occurs mid-cycle.
  </chunk>
</retrieved_context>
```

Exit criteria:

- Architecture decisions are documented.
- RAG success metrics are agreed.
- Initial test corpus is identified.

## 6. Phase 1 - Data Model And Migrations

Goal: add durable storage for chunks, embeddings, versions, and citations.

### 6.1 Add Chunk Embeddings

Update `RequirementChunk` or replace it with a more general `KnowledgeChunk` model.

Recommended enterprise direction:

- Keep `RequirementChunk` only if the first release is requirement-only.
- Prefer a new `KnowledgeChunk` table if the platform will retrieve from requirements, test cases, defects, execution results, documents, Jira, and telecom knowledge.

Recommended `knowledge_chunks` columns:

| Column | Purpose |
|---|---|
| `id` | Internal row ID |
| `project_id` | Project isolation |
| `source_type` | `uploaded_document`, `requirement`, `test_case`, `defect`, `execution`, `jira`, `knowledge_base` |
| `source_id` | Source entity row ID |
| `source_version` | Version of source content when chunked |
| `chunk_index` | Stable ordering within source |
| `chunk_text` | Text sent to embedding model |
| `chunk_hash` | Detect unchanged chunks |
| `token_count` | Retrieval/context budgeting |
| `embedding_model` | Model used to create vector |
| `embedding_dimension` | Vector dimension |
| `embedding` | pgvector column |
| `metadata` | Section, page, heading, filename, domain, tags |
| `is_active` | Soft deactivation for stale chunks |
| `created_at`, `updated_at` | Audit timestamps |

Recommended vector dimensions:

- `BAAI/bge-small-en-v1.5`: 384
- `BAAI/bge-base-en-v1.5`: 768
- OpenAI `text-embedding-3-small`: commonly 1536 unless configured otherwise

Important: choose the dimension before creating the pgvector column. If multiple embedding models are expected, either standardize on one model per deployment or create separate vector columns/tables per dimension.

### 6.2 Add Citations

Add a table such as `artifact_citations`.

Recommended columns:

| Column | Purpose |
|---|---|
| `id` | Internal row ID |
| `project_id` | Project isolation |
| `artifact_type` | `test_scenario`, `test_case`, `test_plan`, `defect`, `report` |
| `artifact_id` | Generated artifact row ID |
| `chunk_id` | Retrieved chunk row ID |
| `agent_run_id` | Agent run provenance |
| `retrieval_score` | Similarity score |
| `rerank_score` | Reranker score if available |
| `citation_reason` | Optional reason or mapped field |
| `created_at` | Audit timestamp |

### 6.3 Add Retrieval Audit

Extend agent run metadata or add `rag_retrieval_events`.

Recommended fields:

- query text
- query type
- embedding model
- retrieval method
- filters applied
- candidate count
- selected chunk IDs
- scores
- latency
- prompt version
- model provider and model

Exit criteria:

- Alembic migration creates vector extension, chunk table, vector index, citations, and retrieval audit storage.
- Models are available in SQLAlchemy.
- Tests confirm migrations create expected columns and indexes.

## 7. Phase 2 - Embedding Service

Goal: generate deterministic embeddings for chunks and queries.

Create `backend/app/services/embedding_service.py`.

Responsibilities:

- Load the configured embedding provider.
- Generate embeddings for text batches.
- Normalize text for embedding.
- Enforce max input length.
- Return model name, dimension, and vectors.
- Cache or skip embeddings when `chunk_hash` is unchanged.

Configuration to add:

```env
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSION=384
EMBEDDING_BATCH_SIZE=32
RAG_ENABLED=true
```

Provider options:

| Provider | Use Case |
|---|---|
| `sentence_transformers` | Local/private embeddings; recommended first |
| `openai` | Managed embedding API if external calls are allowed |
| `huggingface` | Hosted fallback if local model size is an issue |

Implementation notes:

- Add `sentence-transformers` to backend dependencies only when ready to install model runtime.
- Keep embedding generation out of request paths; use Celery for document indexing.
- For local Docker, consider model cache volume to avoid repeated downloads.

Exit criteria:

- Unit tests mock the embedding provider.
- Service returns consistent vector dimensions.
- Invalid dimensions fail early with clear errors.

## 8. Phase 3 - Chunking And Indexing Pipeline

Goal: convert extracted documents and structured artifacts into searchable chunks.

Create `backend/app/services/rag_indexing_service.py`.

Responsibilities:

- Build chunks from uploaded documents.
- Build chunks from structured requirements.
- Preserve section metadata.
- Generate chunk hashes.
- Deactivate stale chunks when sources change.
- Call `EmbeddingService`.
- Store embeddings in pgvector.

### 8.1 Requirement Document Chunking

Chunk boundaries should prefer:

- headings
- acceptance criteria lists
- business rules
- API/interface sections
- dependencies
- tables converted to text
- page numbers or source offsets

Avoid splitting:

- one acceptance criterion across chunks
- API contract name from its behavior
- condition from expected outcome
- telecom interface name from protocol details

### 8.2 Structured Requirement Chunking

Create separate chunks for:

- title and summary
- acceptance criteria
- business rules
- impacted systems/interfaces
- APIs
- dependencies
- risks and missing information

This lets retrieval find precise sections instead of only whole requirements.

### 8.3 Celery Integration

Update document extraction flow:

```text
extract_document_text
  -> save extracted_text
  -> enqueue index_document_for_rag
  -> chunk
  -> embed
  -> store vectors
  -> mark document metadata.rag_index_status = indexed
```

Add tasks:

- `rag_tasks.index_document`
- `rag_tasks.index_requirement`
- `rag_tasks.reindex_project`
- `rag_tasks.reindex_stale_chunks`

Exit criteria:

- Uploading a document creates active chunks with embeddings.
- Updating a requirement refreshes related chunks.
- Reindexing is idempotent.
- Index status is visible through document metadata or a backend endpoint.

## 9. Phase 4 - Retrieval Service

Goal: retrieve relevant, permission-safe, task-specific context.

Create `backend/app/services/rag_retrieval_service.py`.

Responsibilities:

- Convert user/task query to query embedding.
- Apply project and RBAC filters.
- Search semantic vectors.
- Search keyword/full-text.
- Merge results.
- Rerank.
- Trim context to token budget.
- Return chunks with citation metadata.
- Persist retrieval event audit.

### 9.1 Semantic Search

Use pgvector cosine distance for initial candidate retrieval.

Example behavior:

```text
query: "Generate SIT test scenarios for mid-cycle mobile plan upgrade billing"
filters:
  project_id = 12
  source_type in ["uploaded_document", "requirement", "jira"]
  is_active = true
top_k = 20
```

### 9.2 Keyword Search

Use PostgreSQL full-text search for exact telecom terms:

- system names
- interface names
- API paths
- product codes
- Jira keys
- regulatory terms

This matters because vector search can miss exact identifiers.

### 9.3 Hybrid Merge

Combine semantic and keyword candidates using weighted reciprocal rank fusion.

Recommended initial weights:

- semantic: 0.65
- keyword: 0.35

### 9.4 Reranking

Start without a reranker if dependency size is a concern. Add reranking as soon as retrieval quality becomes a bottleneck.

Recommended rerankers:

- `BAAI/bge-reranker-base`
- `cross-encoder/ms-marco-MiniLM-L-6-v2`

Rerank top 20 candidates down to 5-8 chunks for the final prompt.

Exit criteria:

- Retrieval returns useful chunks for known test queries.
- Exact terms like API names and Jira keys are found.
- Queries never return chunks from unauthorized projects.
- Retrieval audit records selected chunks and scores.

## 10. Phase 5 - Agent Context Injection

Goal: make agents use retrieved context consistently.

Create a shared context helper, for example `backend/app/agents/rag_context.py`.

Responsibilities:

- Decide whether RAG is enabled for the agent.
- Build retrieval query from agent input.
- Call `RAGRetrievalService`.
- Format chunks into a compact context block.
- Add grounding instructions to system prompts.
- Return citations for persistence.

### 10.1 First Agents To Integrate

Priority order:

1. Requirement quality agent
2. Test scenario agent
3. Test case agent
4. Test planning agent
5. Automation agent
6. Defect agent
7. Reporting agent

### 10.2 Prompt Pattern

Each RAG-enabled agent should include:

```text
Use the retrieved context as the primary source of truth.
If the context does not contain enough information, explicitly mark missing information.
Do not invent system names, APIs, rules, or dependencies that are not present in the requirement or retrieved context.
Return source_chunk_ids for each generated item when possible.
```

### 10.3 Scenario Generation Context

For "Generate test scenarios", retrieve using:

- requirement title
- requirement summary
- acceptance criteria
- impacted systems
- APIs
- test phase
- user instruction

Context should include:

- linked requirement chunks
- source document acceptance criteria
- relevant business rules
- similar approved scenarios from the same project
- relevant prior defects, if available

Exit criteria:

- Scenario generation receives retrieved context.
- Test scenarios include source chunk IDs or citation metadata.
- Agents degrade gracefully when no RAG context exists.

## 11. Phase 6 - Citation Persistence And UI

Goal: users can see why an artifact was generated.

Backend:

- Persist citations after generated artifacts are saved.
- Add citation read endpoints for generated artifacts.
- Include citation IDs in API responses where useful.

Frontend:

- Show "Sources" or "Grounding" in artifact drawers.
- Display source filename, section, snippet, and score.
- Allow user to open the original uploaded document where possible.
- Flag artifacts generated without retrieval context.

Recommended endpoints:

- `GET /api/v1/rag/artifacts/{artifact_type}/{artifact_id}/citations`
- `GET /api/v1/rag/projects/{project_id}/search`
- `POST /api/v1/rag/projects/{project_id}/reindex`

Exit criteria:

- A generated scenario can be traced back to source document chunks.
- Users can distinguish grounded and ungrounded AI output.

## 12. Phase 7 - Governance, Security, And Compliance

Goal: make RAG enterprise-safe.

### 12.1 Permission-Aware Retrieval

Every retrieval call must enforce:

- authenticated user
- project membership
- source visibility
- soft-delete filters
- artifact approval/status filters where required

### 12.2 Prompt-Injection Controls

Uploaded documents may contain instructions like "ignore previous instructions". Treat documents as data, not instructions.

Add:

- prompt-injection scan during indexing
- metadata flag for suspicious chunks
- retrieval-time filtering or warning
- prompt instruction that retrieved context is untrusted source material

### 12.3 Audit And Reproducibility

Store:

- prompt version
- LLM provider/model
- embedding provider/model
- chunk IDs and versions
- retrieval scores
- generated output
- validation result
- user ID
- project ID

### 12.4 Data Retention

Define retention for:

- original documents
- extracted text
- chunks
- embeddings
- retrieval events
- generated artifacts

Exit criteria:

- Security tests prove project isolation.
- Prompt-injection test corpus does not override system behavior.
- Agent runs are reproducible from stored retrieval metadata.

## 13. Phase 8 - Evaluation And Quality Gates

Goal: measure whether RAG improves output quality.

Create a small RAG evaluation set with:

- 10-20 telecom requirement documents
- expected relevant sections
- expected scenario categories
- known tricky APIs/interfaces
- known negative/boundary conditions

Metrics:

| Metric | Target |
|---|---|
| Retrieval precision@5 | 80%+ for curated queries |
| Citation coverage | 90%+ generated scenarios have citations |
| Empty retrieval rate | Under 5% for indexed projects |
| Hallucinated system/API names | Under 2% in reviewed outputs |
| Scenario acceptance criteria coverage | 85%+ |
| P95 retrieval latency | Under 1.5 seconds for normal projects |

Quality gates:

- If retrieval returns no context, agent output must mark itself as ungrounded.
- If source context conflicts, agent output must flag conflict.
- If acceptance criteria are not covered, coverage service should report gaps.

Exit criteria:

- Regression tests compare prompt-only vs RAG output.
- Evaluation report is available before enabling RAG by default.

## 14. Phase 9 - Production Scaling Path

Start with pgvector. Move to Qdrant when one or more of these become true:

- Millions of chunks per environment.
- Heavy concurrent vector search.
- Need advanced vector payload filtering at scale.
- Need separate vector operations team or observability.
- Need better multi-tenant vector isolation.

Qdrant migration strategy:

1. Keep PostgreSQL as metadata source of truth.
2. Add `vector_store_provider=qdrant`.
3. Mirror chunk vectors to Qdrant.
4. Compare retrieval results between pgvector and Qdrant.
5. Switch reads to Qdrant behind feature flag.
6. Keep chunk metadata and citations in PostgreSQL.

## 15. Suggested Delivery Plan

### Sprint 1 - Foundation

- Add RAG configuration.
- Add `knowledge_chunks` and `artifact_citations` migrations.
- Add SQLAlchemy models.
- Add embedding service interface with mocked tests.
- Add local sentence-transformer provider.

Deliverable: chunks can be embedded and stored in pgvector in tests.

### Sprint 2 - Indexing

- Add document chunking service.
- Add requirement chunking service.
- Add Celery indexing tasks.
- Hook indexing after document extraction.
- Add reindex endpoint/admin task.

Deliverable: uploaded documents become searchable indexed chunks.

### Sprint 3 - Retrieval

- Add semantic retrieval.
- Add keyword retrieval.
- Add hybrid merge.
- Add retrieval audit.
- Add tests for project isolation and exact-term search.

Deliverable: backend can retrieve top relevant chunks for a project query.

### Sprint 4 - Agent Integration

- Add shared RAG context helper.
- Integrate scenario agent.
- Integrate test case agent.
- Persist citations.
- Add fallback behavior when no context exists.

Deliverable: generated scenarios and test cases are grounded with source citations.

### Sprint 5 - Governance And UI

- Add citation endpoints.
- Add source display in frontend drawers.
- Add prompt-injection flags.
- Add RAG status indicators.
- Add admin reindex controls.

Deliverable: users can see sources and indexing status.

### Sprint 6 - Evaluation And Hardening

- Add curated RAG evaluation fixtures.
- Add retrieval quality tests.
- Add latency logging.
- Add coverage/hallucination review workflow.
- Tune chunking, top-K, and context formatting.

Deliverable: RAG can be enabled by default for scenario/test case generation.

## 16. Testing Strategy

Backend unit tests:

- chunker preserves section metadata
- embedding service validates dimensions
- unchanged chunks are skipped
- stale chunks are deactivated
- retrieval filters by `project_id`
- keyword retrieval finds exact API/interface names
- hybrid merge preserves high keyword matches
- citations are saved for generated artifacts

Backend integration tests:

- upload document -> extraction -> indexing -> retrieval
- requirement update -> reindex -> new retrieval results
- unauthorized project retrieval returns no data
- scenario generation includes retrieved context

Security tests:

- prompt-injection text does not override agent system instructions
- deleted documents are not retrieved
- unapproved/private artifacts are filtered where required

Performance tests:

- batch embedding throughput
- P95 retrieval latency
- reindex project runtime
- Celery indexing queue behavior

## 17. Operational Checklist

Before enabling in production:

- `RAG_ENABLED=false` by default until evaluation passes.
- Embedding model cache volume configured.
- Database vector indexes created.
- Reindex task tested on realistic document size.
- Retrieval audit retention policy defined.
- Prompt versions tracked.
- Provider keys configured for Groq and fallbacks.
- Backup policy covers original documents, extracted text, chunks, citations, and agent runs.
- Monitoring includes indexing failures, retrieval latency, empty retrieval rate, and LLM failures.

## 18. Acceptance Criteria

The enterprise RAG implementation is complete when:

1. Uploaded requirement documents are parsed, chunked, embedded, and searchable.
2. Scenario and test case generation retrieve project-specific context before calling the LLM.
3. Generated artifacts store citations to source chunks.
4. Retrieval enforces project permissions.
5. Exact identifiers such as API paths, system names, Jira keys, and telecom interfaces are retrievable.
6. RAG behavior is auditable through agent runs and retrieval events.
7. Users can view source grounding in the UI.
8. Evaluation shows reduced hallucination and improved acceptance criteria coverage.
9. RAG can be toggled per environment or project.
10. Reindexing works safely after document or embedding model changes.

## 19. Final Recommendation

Build enterprise RAG in this order:

```text
pgvector schema
  -> embedding service
  -> document and requirement indexing
  -> hybrid retrieval
  -> scenario/test case agent grounding
  -> citations
  -> UI source display
  -> prompt-injection controls
  -> evaluation and rollout
```

Use pgvector first because it fits the current platform and reduces operational complexity. Add Qdrant later only when scale or vector operations justify the extra service.
