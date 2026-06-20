"""
RAGRetrievalService — retrieve relevant, permission-safe context for agent tasks.

Pipeline per query:
  1. Embed the query text
  2. Semantic search via pgvector cosine distance (top_k_candidates)
  3. Keyword search via PostgreSQL full-text (to_tsvector)
  4. Merge with weighted Reciprocal Rank Fusion
  5. Return top_k_context chunks with citation metadata
  6. Persist a RagRetrievalEvent audit record

Every query is scoped to project_id and filters out inactive chunks.
Cross-project retrieval is never possible.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.rag import KnowledgeChunk, RagRetrievalEvent
from app.services.embedding_service import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class RetrievedChunk:
    chunk_id: int
    chunk_text: str
    source_type: str
    source_id: int | None
    section: str | None
    semantic_score: float | None
    keyword_score: float | None
    hybrid_score: float
    metadata: dict | None = None


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    query_text: str
    query_type: str
    total_candidates: int
    elapsed_ms: float
    embedding_model: str
    retrieval_method: str = "hybrid"


def _rrf_merge(
    semantic_ids: list[int],
    keyword_ids: list[int],
    semantic_weight: float,
    keyword_weight: float,
    k: int = 60,
) -> list[tuple[int, float]]:
    """
    Weighted Reciprocal Rank Fusion.
    Returns (chunk_id, score) list sorted by score descending.
    """
    scores: dict[int, float] = {}

    for rank, chunk_id in enumerate(semantic_ids):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + semantic_weight / (k + rank + 1)

    for rank, chunk_id in enumerate(keyword_ids):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + keyword_weight / (k + rank + 1)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class RAGRetrievalService:
    """
    Retrieves relevant KnowledgeChunks for a given query within a project.

    Instantiate once per request or share as a singleton.
    The embedding service is lazy-loaded.
    """

    def __init__(self, embedding_svc: EmbeddingService | None = None) -> None:
        self._embedding_svc = embedding_svc or get_embedding_service()

    async def retrieve(
        self,
        db: AsyncSession,
        project_id: int,
        query: str,
        query_type: str = "general",
        source_types: list[str] | None = None,
        top_k_candidates: int | None = None,
        top_k_context: int | None = None,
        agent_run_id: int | None = None,
        prompt_version: str | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> RetrievalResult:
        """
        Main entry point. Returns the top context chunks for the query.

        Args:
            db: async database session
            project_id: all results are scoped to this project
            query: natural-language query or structured context string
            query_type: label for audit (e.g. "scenario_generation", "test_case_generation")
            source_types: restrict to these source types (default: all)
            top_k_candidates: how many candidates to fetch per search method
            top_k_context: how many final chunks to return after merge
            agent_run_id: for audit linkage
        """
        if not settings.rag_enabled:
            return RetrievalResult(
                chunks=[],
                query_text=query,
                query_type=query_type,
                total_candidates=0,
                elapsed_ms=0.0,
                embedding_model=settings.embedding_model,
                retrieval_method="disabled",
            )

        top_k = top_k_candidates or settings.rag_top_k_candidates
        top_ctx = top_k_context or settings.rag_top_k_context

        t0 = time.monotonic()

        # 1. Embed query
        query_vec = self._embedding_svc.embed_query(query)

        # 2. Semantic search
        semantic_rows = await self._semantic_search(db, project_id, query_vec, source_types, top_k)

        # 3. Keyword search
        keyword_rows = await self._keyword_search(db, project_id, query, source_types, top_k)

        # 4. RRF merge
        semantic_ids = [r["id"] for r in semantic_rows]
        keyword_ids = [r["id"] for r in keyword_rows]
        merged = _rrf_merge(
            semantic_ids,
            keyword_ids,
            settings.rag_semantic_weight,
            settings.rag_keyword_weight,
        )

        # Build score lookups
        sem_scores = {r["id"]: r["score"] for r in semantic_rows}
        kw_scores = {r["id"]: r["rank"] for r in keyword_rows}
        all_ids = [chunk_id for chunk_id, _ in merged[:top_ctx]]

        # 5. Fetch selected chunks
        chunks_result = await db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.id.in_(all_ids))
        )
        chunk_map: dict[int, KnowledgeChunk] = {c.id: c for c in chunks_result.scalars().all()}

        retrieved: list[RetrievedChunk] = []
        for chunk_id, hybrid_score in merged[:top_ctx]:
            chunk = chunk_map.get(chunk_id)
            if not chunk:
                continue
            meta = chunk.metadata_ or {}
            retrieved.append(RetrievedChunk(
                chunk_id=chunk_id,
                chunk_text=chunk.chunk_text,
                source_type=chunk.source_type,
                source_id=chunk.source_id,
                section=meta.get("section"),
                semantic_score=sem_scores.get(chunk_id),
                keyword_score=kw_scores.get(chunk_id),
                hybrid_score=hybrid_score,
                metadata=meta,
            ))

        elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
        total_candidates = len(set(semantic_ids) | set(keyword_ids))

        # 6. Persist audit event (fire-and-forget; don't let errors block callers)
        try:
            await self._save_audit(
                db=db,
                project_id=project_id,
                agent_run_id=agent_run_id,
                query_text=query,
                query_type=query_type,
                filters={"source_types": source_types},
                candidate_count=total_candidates,
                selected_chunk_ids=[r.chunk_id for r in retrieved],
                scores={str(r.chunk_id): r.hybrid_score for r in retrieved},
                latency_ms=elapsed_ms,
                prompt_version=prompt_version,
                llm_provider=llm_provider,
                llm_model=llm_model,
            )
        except Exception:
            logger.warning("Failed to save retrieval audit event", exc_info=True)

        return RetrievalResult(
            chunks=retrieved,
            query_text=query,
            query_type=query_type,
            total_candidates=total_candidates,
            elapsed_ms=elapsed_ms,
            embedding_model=settings.embedding_model,
        )

    # ── search methods ────────────────────────────────────────────────────────

    async def _semantic_search(
        self,
        db: AsyncSession,
        project_id: int,
        query_vec: list[float],
        source_types: list[str] | None,
        top_k: int,
    ) -> list[dict]:
        """pgvector cosine distance search."""
        vec_str = "[" + ",".join(str(v) for v in query_vec) + "]"

        source_filter = ""
        params: dict[str, Any] = {
            "project_id": project_id,
            "vec": vec_str,
            "top_k": top_k,
        }

        if source_types:
            source_filter = "AND source_type = ANY(:source_types)"
            params["source_types"] = source_types

        sql = text(f"""
            SELECT id, 1 - (embedding <=> :vec::vector) AS score
            FROM knowledge_chunks
            WHERE project_id = :project_id
              AND is_active = true
              AND embedding IS NOT NULL
              {source_filter}
            ORDER BY embedding <=> :vec::vector
            LIMIT :top_k
        """)

        result = await db.execute(sql, params)
        return [{"id": row[0], "score": float(row[1])} for row in result]

    async def _keyword_search(
        self,
        db: AsyncSession,
        project_id: int,
        query: str,
        source_types: list[str] | None,
        top_k: int,
    ) -> list[dict]:
        """PostgreSQL full-text search using to_tsvector / plainto_tsquery."""
        source_filter = ""
        params: dict[str, Any] = {
            "project_id": project_id,
            "query": query,
            "top_k": top_k,
        }

        if source_types:
            source_filter = "AND source_type = ANY(:source_types)"
            params["source_types"] = source_types

        sql = text(f"""
            SELECT id,
                   ts_rank(to_tsvector('english', chunk_text),
                           plainto_tsquery('english', :query)) AS rank
            FROM knowledge_chunks
            WHERE project_id = :project_id
              AND is_active = true
              AND to_tsvector('english', chunk_text) @@ plainto_tsquery('english', :query)
              {source_filter}
            ORDER BY rank DESC
            LIMIT :top_k
        """)

        result = await db.execute(sql, params)
        return [{"id": row[0], "rank": float(row[1])} for row in result]

    # ── audit ─────────────────────────────────────────────────────────────────

    async def _save_audit(
        self,
        db: AsyncSession,
        project_id: int,
        agent_run_id: int | None,
        query_text: str,
        query_type: str,
        filters: dict,
        candidate_count: int,
        selected_chunk_ids: list[int],
        scores: dict,
        latency_ms: float,
        prompt_version: str | None,
        llm_provider: str | None,
        llm_model: str | None,
    ) -> None:
        event = RagRetrievalEvent(
            project_id=project_id,
            agent_run_id=agent_run_id,
            query_text=query_text,
            query_type=query_type,
            embedding_model=settings.embedding_model,
            retrieval_method="hybrid",
            filters_applied=filters,
            candidate_count=candidate_count,
            selected_chunk_ids=selected_chunk_ids,
            scores=scores,
            latency_ms=latency_ms,
            prompt_version=prompt_version,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
        db.add(event)
        await db.flush()

    # ── context formatting ────────────────────────────────────────────────────

    @staticmethod
    def format_context_block(chunks: list[RetrievedChunk], source_label: str = "") -> str:
        """
        Format retrieved chunks into an XML-like context block for prompt injection.

        Example output:
          <retrieved_context>
            <chunk id="12#3" source_type="requirement" section="acceptance_criteria" score="0.84">
              Customer must receive a prorated invoice when plan upgrade occurs mid-cycle.
            </chunk>
          </retrieved_context>
        """
        if not chunks:
            return ""

        lines = ["<retrieved_context>"]
        for c in chunks:
            score_str = f"{c.hybrid_score:.3f}"
            section_str = f' section="{c.section}"' if c.section else ""
            source_id_str = f"{c.source_id}" if c.source_id else "?"
            chunk_id_label = f"{c.source_type}-{source_id_str}#chunk-{c.chunk_id}"
            lines.append(
                f'  <chunk id="{chunk_id_label}" source_type="{c.source_type}"'
                f'{section_str} score="{score_str}">'
            )
            lines.append(f"    {c.chunk_text.strip()}")
            lines.append("  </chunk>")
        lines.append("</retrieved_context>")
        return "\n".join(lines)
