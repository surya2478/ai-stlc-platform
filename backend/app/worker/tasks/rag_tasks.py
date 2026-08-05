"""
Celery tasks for RAG indexing operations.

These tasks run asynchronously in the background worker, keeping embedding
work out of the API request path.
"""
from __future__ import annotations

import asyncio
import logging

from app.database import AsyncSessionLocal
from app.services.rag_indexing_service import index_document, index_requirement, reindex_project
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="rag_tasks.index_document", max_retries=2, default_retry_delay=30)
def task_index_document(self, doc_id: int) -> dict:
    """Index an uploaded document into knowledge_chunks after text extraction."""
    async def _run():
        async with AsyncSessionLocal() as db:
            return await index_document(db, doc_id)

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("RAG document indexing failed: doc_id=%s", doc_id)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="rag_tasks.index_requirement", max_retries=2, default_retry_delay=30)
def task_index_requirement(self, requirement_id: int) -> dict:
    """Index or reindex a structured requirement into knowledge_chunks."""
    async def _run():
        async with AsyncSessionLocal() as db:
            return await index_requirement(db, requirement_id)

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("RAG requirement indexing failed: requirement_id=%s", requirement_id)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="rag_tasks.reindex_project", max_retries=1, default_retry_delay=60)
def task_reindex_project(self, project_id: int) -> dict:
    """Reindex all documents and requirements for a project."""
    async def _run():
        async with AsyncSessionLocal() as db:
            return await reindex_project(db, project_id)

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("RAG project reindex failed: project_id=%s", project_id)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="rag_tasks.reindex_stale_chunks", max_retries=1)
def task_reindex_stale_chunks(self, project_id: int | None = None) -> dict:
    """
    Find and reindex chunks that have no embedding (e.g. after embedding model change).
    Scoped to a project if project_id is provided, otherwise all projects.
    """
    from sqlalchemy import select
    from app.models.rag import KnowledgeChunk
    from app.services.embedding_service import EmbeddingService
    import json

    async def _run():
        async with AsyncSessionLocal() as db:
            query = select(KnowledgeChunk).where(
                KnowledgeChunk.is_active == True,  # noqa: E712
                KnowledgeChunk.embedding.is_(None),
            )
            if project_id is not None:
                query = query.where(KnowledgeChunk.project_id == project_id)

            result = await db.execute(query.limit(500))
            stale = result.scalars().all()

            if not stale:
                return {"reindexed": 0}

            svc = EmbeddingService()
            texts = [c.chunk_text for c in stale]
            embedding_result = svc.embed(texts)

            for chunk, vec in zip(stale, embedding_result.vectors):
                chunk.embedding = vec
                chunk.embedding_model = embedding_result.model
                chunk.embedding_dimension = embedding_result.dimension

            await db.commit()
            return {"reindexed": len(stale)}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("RAG stale chunk reindex failed")
        raise self.retry(exc=exc)
