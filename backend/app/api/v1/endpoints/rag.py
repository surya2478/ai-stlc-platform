"""
RAG endpoints — citations, project search, and reindex.

All endpoints are scoped to a project and enforce membership checks.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, require_permission
from app.config import get_settings
from app.models.rag import ArtifactCitation, KnowledgeChunk
from app.services.rbac_service import VIEW_PROJECT, MANAGE_PROJECT

router = APIRouter()
settings = get_settings()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChunkOut(BaseModel):
    chunk_id: int
    chunk_text: str
    source_type: str
    source_id: int | None
    section: str | None
    hybrid_score: float
    semantic_score: float | None
    keyword_score: float | None

    model_config = {"from_attributes": True}


class CitationOut(BaseModel):
    id: int
    artifact_type: str
    artifact_id: int
    chunk_id: int
    retrieval_score: float | None
    rerank_score: float | None
    citation_reason: str | None
    created_at: datetime
    chunk_text: str | None = None
    section: str | None = None
    source_type: str | None = None

    model_config = {"from_attributes": True}


class SearchRequest(BaseModel):
    query: str
    source_types: list[str] | None = None
    top_k: int = 10


class SearchResponse(BaseModel):
    chunks: list[ChunkOut]
    query: str
    total_candidates: int
    elapsed_ms: float
    grounded: bool


class ReindexResponse(BaseModel):
    task_id: str | None
    message: str
    documents_queued: int
    requirements_queued: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/artifacts/{artifact_type}/{artifact_id}/citations", response_model=list[CitationOut])
async def get_artifact_citations(
    project_id: int,
    artifact_type: str,
    artifact_id: int,
    db: DBSession,
    current_user: CurrentUser,
    include_text: bool = Query(True),
):
    """
    Return the source citations for a generated artifact.
    Allows users to trace why a scenario, test case, or report was generated.
    """
    await require_permission(VIEW_PROJECT, project_id, current_user, db)

    result = await db.execute(
        select(ArtifactCitation).where(
            ArtifactCitation.project_id == project_id,
            ArtifactCitation.artifact_type == artifact_type,
            ArtifactCitation.artifact_id == artifact_id,
        ).order_by(ArtifactCitation.retrieval_score.desc().nullslast())
    )
    citations = result.scalars().all()

    out: list[CitationOut] = []
    for c in citations:
        chunk_text = None
        section = None
        source_type = None

        if include_text:
            chunk_result = await db.execute(
                select(KnowledgeChunk).where(KnowledgeChunk.id == c.chunk_id)
            )
            chunk = chunk_result.scalar_one_or_none()
            if chunk:
                chunk_text = chunk.chunk_text[:500]  # truncate for API response
                section = (chunk.metadata_ or {}).get("section")
                source_type = chunk.source_type

        out.append(CitationOut(
            id=c.id,
            artifact_type=c.artifact_type,
            artifact_id=c.artifact_id,
            chunk_id=c.chunk_id,
            retrieval_score=c.retrieval_score,
            rerank_score=c.rerank_score,
            citation_reason=c.citation_reason,
            created_at=c.created_at,
            chunk_text=chunk_text,
            section=section,
            source_type=source_type,
        ))

    return out


@router.post("/projects/{project_id}/search", response_model=SearchResponse)
async def search_project_knowledge(
    project_id: int,
    body: SearchRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Hybrid semantic + keyword search over a project's knowledge chunks.
    Useful for exploring what indexed context is available.
    """
    await require_permission(VIEW_PROJECT, project_id, current_user, db)

    if not settings.rag_enabled:
        raise HTTPException(status_code=400, detail="RAG is not enabled on this instance (RAG_ENABLED=false)")

    if not body.query or not body.query.strip():
        raise HTTPException(status_code=422, detail="Query must not be empty")

    from app.services.rag_retrieval_service import RAGRetrievalService
    svc = RAGRetrievalService()
    result = await svc.retrieve(
        db=db,
        project_id=project_id,
        query=body.query,
        query_type="manual_search",
        source_types=body.source_types,
        top_k_context=min(body.top_k, 20),
    )

    chunks_out = [
        ChunkOut(
            chunk_id=c.chunk_id,
            chunk_text=c.chunk_text,
            source_type=c.source_type,
            source_id=c.source_id,
            section=c.section,
            hybrid_score=c.hybrid_score,
            semantic_score=c.semantic_score,
            keyword_score=c.keyword_score,
        )
        for c in result.chunks
    ]

    return SearchResponse(
        chunks=chunks_out,
        query=result.query_text,
        total_candidates=result.total_candidates,
        elapsed_ms=result.elapsed_ms,
        grounded=len(result.chunks) > 0,
    )


@router.post("/projects/{project_id}/reindex", response_model=ReindexResponse)
async def reindex_project(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Queue a full reindex of all documents and requirements for the project.
    Requires MANAGE_PROJECT permission. Idempotent — safe to run repeatedly.
    """
    await require_permission(MANAGE_PROJECT, project_id, current_user, db)

    if not settings.rag_enabled:
        raise HTTPException(status_code=400, detail="RAG is not enabled on this instance (RAG_ENABLED=false)")

    from app.models.document import UploadedDocument
    from app.models.requirement import Requirement

    doc_result = await db.execute(
        select(UploadedDocument.id).where(UploadedDocument.project_id == project_id)
    )
    doc_ids = [row[0] for row in doc_result]

    req_result = await db.execute(
        select(Requirement.id).where(
            Requirement.project_id == project_id,
            Requirement.is_deleted == False,  # noqa: E712
        )
    )
    req_ids = [row[0] for row in req_result]

    from app.worker.tasks.rag_tasks import task_index_document, task_index_requirement

    for doc_id in doc_ids:
        task_index_document.delay(doc_id)

    for req_id in req_ids:
        task_index_requirement.delay(req_id)

    return ReindexResponse(
        task_id=None,
        message=f"Queued {len(doc_ids)} document(s) and {len(req_ids)} requirement(s) for RAG indexing",
        documents_queued=len(doc_ids),
        requirements_queued=len(req_ids),
    )


@router.get("/projects/{project_id}/status")
async def get_rag_status(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Return a summary of RAG indexing status for a project."""
    await require_permission(VIEW_PROJECT, project_id, current_user, db)

    from sqlalchemy import func
    from app.models.rag import KnowledgeChunk

    total_result = await db.execute(
        select(func.count(KnowledgeChunk.id)).where(
            KnowledgeChunk.project_id == project_id,
            KnowledgeChunk.is_active == True,  # noqa: E712
        )
    )
    total_chunks = total_result.scalar() or 0

    embedded_result = await db.execute(
        select(func.count(KnowledgeChunk.id)).where(
            KnowledgeChunk.project_id == project_id,
            KnowledgeChunk.is_active == True,  # noqa: E712
            KnowledgeChunk.embedding.isnot(None),
        )
    )
    embedded_chunks = embedded_result.scalar() or 0

    async def indexed_source_count(source_type: str) -> int:
        result = await db.execute(
            select(func.count(func.distinct(KnowledgeChunk.source_id))).where(
                KnowledgeChunk.project_id == project_id,
                KnowledgeChunk.is_active == True,  # noqa: E712
                KnowledgeChunk.source_type == source_type,
            )
        )
        return result.scalar() or 0

    return {
        "rag_enabled": settings.rag_enabled,
        "embedding_model": settings.embedding_model,
        "project_id": project_id,
        "indexed_documents": await indexed_source_count("uploaded_document"),
        "indexed_jira_stories": await indexed_source_count("jira"),
        "total_active_chunks": total_chunks,
        "embedded_chunks": embedded_chunks,
        "unembedded_chunks": total_chunks - embedded_chunks,
        "index_coverage_pct": round(embedded_chunks / total_chunks * 100, 1) if total_chunks else 0,
    }
