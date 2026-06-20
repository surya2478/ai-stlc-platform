"""
RAGIndexingService — converts documents and requirements into searchable KnowledgeChunks.

Responsibilities:
- Split extracted document text into section-aware semantic chunks
- Split structured requirements into per-field chunks
- Generate chunk hashes for dedup
- Deactivate stale chunks when source content changes
- Call EmbeddingService and store vectors in pgvector
- Mark index status on the source entity's metadata

All database operations use async SQLAlchemy sessions.
All embedding work is designed to run in Celery workers, never in request paths.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.document import UploadedDocument
from app.models.rag import KnowledgeChunk
from app.models.requirement import Requirement
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)
settings = get_settings()

# Chunk size targets (in characters — token estimate is chars / 4)
CHUNK_TARGET_CHARS = 2000   # ~500 tokens
CHUNK_MAX_CHARS = 3600      # ~900 tokens hard cap
CHUNK_OVERLAP_CHARS = 200   # carry-forward context

# Heading patterns to use as chunk boundaries
_HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+.+|[A-Z][A-Z0-9 /:()-]{3,80})\s*$",
    re.MULTILINE,
)

# Acceptance criteria / business rule markers
_CRITERIA_MARKERS = re.compile(
    r"(?:acceptance criteria|business rules?|given|when|then|shall|must|should)\b",
    re.IGNORECASE,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# ── Document chunking ────────────────────────────────────────────────────────

def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """
    Split document text at heading boundaries.
    Returns list of (heading, section_body) pairs.
    """
    positions = [m.start() for m in _HEADING_RE.finditer(text)]
    if not positions:
        return [("", text)]

    sections: list[tuple[str, str]] = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        block = text[pos:end]
        lines = block.split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if body:
            sections.append((heading, body))
    return sections if sections else [("", text)]


def _sliding_window_chunks(text: str, heading: str = "") -> list[dict[str, Any]]:
    """
    Split a text block into overlapping chunks respecting paragraph boundaries.
    Returns list of chunk dicts with text and metadata.
    """
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[dict[str, Any]] = []
    buffer = ""
    para_idx = 0

    for para in paragraphs:
        if len(buffer) + len(para) + 1 > CHUNK_MAX_CHARS and buffer:
            chunks.append({
                "text": buffer.strip(),
                "section": heading,
                "has_criteria": bool(_CRITERIA_MARKERS.search(buffer)),
            })
            # overlap: keep last paragraph for continuity
            buffer = para
        else:
            buffer = (buffer + "\n\n" + para).strip() if buffer else para

    if buffer:
        chunks.append({
            "text": buffer.strip(),
            "section": heading,
            "has_criteria": bool(_CRITERIA_MARKERS.search(buffer)),
        })

    return chunks


def chunk_document_text(
    text: str,
    source_metadata: dict | None = None,
) -> list[dict[str, Any]]:
    """
    Convert extracted document text into semantic chunk dicts.

    Returns a list of dicts with keys:
      chunk_text, section, token_count, has_criteria, chunk_hash
    """
    if not text or not text.strip():
        return []

    source_metadata = source_metadata or {}
    sections = _split_by_headings(text)
    result: list[dict[str, Any]] = []

    for heading, body in sections:
        for chunk_dict in _sliding_window_chunks(body, heading):
            chunk_text = chunk_dict["text"]
            if len(chunk_text) < 50:
                continue
            result.append({
                "chunk_text": chunk_text,
                "section": chunk_dict["section"],
                "token_count": _estimate_tokens(chunk_text),
                "has_criteria": chunk_dict["has_criteria"],
                "chunk_hash": _sha256(chunk_text),
                "metadata": {
                    **source_metadata,
                    "section": chunk_dict["section"],
                    "has_criteria": chunk_dict["has_criteria"],
                },
            })

    return result


# ── Requirement chunking ─────────────────────────────────────────────────────

def chunk_requirement(req: Requirement) -> list[dict[str, Any]]:
    """
    Split a structured Requirement into per-field semantic chunks.
    Creates one chunk per logical section so retrieval can find precise sections.
    """
    chunks: list[dict[str, Any]] = []

    def _add(section: str, text: str, extra: dict | None = None) -> None:
        if not text or not text.strip():
            return
        text = text.strip()
        chunks.append({
            "chunk_text": text,
            "section": section,
            "token_count": _estimate_tokens(text),
            "has_criteria": bool(_CRITERIA_MARKERS.search(text)),
            "chunk_hash": _sha256(text),
            "metadata": {
                "requirement_id": req.requirement_id,
                "section": section,
                **(extra or {}),
            },
        })

    # Title + summary
    title_block = f"{req.title}\n{req.summary or ''}".strip()
    _add("title_summary", title_block)

    # Acceptance criteria
    if req.acceptance_criteria:
        ac_text = "\n".join(
            f"- {c}" if isinstance(c, str) else f"- {json.dumps(c)}"
            for c in req.acceptance_criteria
        )
        _add("acceptance_criteria", ac_text)

    # Business rules
    if req.business_rules:
        br_text = "\n".join(
            f"- {r}" if isinstance(r, str) else f"- {json.dumps(r)}"
            for r in req.business_rules
        )
        _add("business_rules", br_text)

    # APIs
    if req.apis:
        api_text = "\n".join(
            f"- {a}" if isinstance(a, str) else f"- {json.dumps(a)}"
            for a in req.apis
        )
        _add("apis", api_text)

    # Impacted systems and interfaces
    systems = list(req.impacted_systems or []) + list(req.systems_impacted or [])
    interfaces = list(req.impacted_interfaces or [])
    if systems or interfaces:
        sys_text = "Systems: " + ", ".join(systems) if systems else ""
        iface_text = "Interfaces: " + ", ".join(interfaces) if interfaces else ""
        _add("systems_interfaces", "\n".join(filter(None, [sys_text, iface_text])))

    # Dependencies
    if req.dependencies:
        dep_text = "\n".join(
            f"- {d}" if isinstance(d, str) else f"- {json.dumps(d)}"
            for d in req.dependencies
        )
        _add("dependencies", dep_text)

    # Risks and missing info
    if req.risks or req.missing_information:
        risk_parts = []
        if req.risks:
            risk_parts.append("Risks:\n" + "\n".join(
                f"- {r}" if isinstance(r, str) else f"- {json.dumps(r)}"
                for r in req.risks
            ))
        if req.missing_information:
            risk_parts.append("Missing info:\n" + "\n".join(
                f"- {m}" if isinstance(m, str) else f"- {json.dumps(m)}"
                for m in req.missing_information
            ))
        _add("risks_gaps", "\n".join(risk_parts))

    return chunks


# ── Database persistence ─────────────────────────────────────────────────────

async def _deactivate_stale_chunks(
    db: AsyncSession,
    project_id: int,
    source_type: str,
    source_id: int,
    active_hashes: set[str],
) -> int:
    """Soft-deactivate chunks whose hash is no longer in the active set."""
    result = await db.execute(
        select(KnowledgeChunk).where(
            KnowledgeChunk.project_id == project_id,
            KnowledgeChunk.source_type == source_type,
            KnowledgeChunk.source_id == source_id,
            KnowledgeChunk.is_active == True,  # noqa: E712
        )
    )
    existing = result.scalars().all()
    deactivated = 0
    for chunk in existing:
        if chunk.chunk_hash not in active_hashes:
            chunk.is_active = False
            deactivated += 1
    return deactivated


async def _upsert_chunks(
    db: AsyncSession,
    project_id: int,
    source_type: str,
    source_id: int,
    source_version: int,
    chunk_dicts: list[dict[str, Any]],
    embedding_svc: EmbeddingService,
) -> int:
    """
    Insert new chunks and embed them; skip chunks whose hash already exists and is active.
    Returns the count of newly embedded chunks.
    """
    if not chunk_dicts:
        return 0

    # Find which hashes already have active embeddings
    all_hashes = {c["chunk_hash"] for c in chunk_dicts}
    existing_result = await db.execute(
        select(KnowledgeChunk.chunk_hash).where(
            KnowledgeChunk.project_id == project_id,
            KnowledgeChunk.source_type == source_type,
            KnowledgeChunk.source_id == source_id,
            KnowledgeChunk.is_active == True,  # noqa: E712
            KnowledgeChunk.chunk_hash.in_(all_hashes),
            KnowledgeChunk.embedding.isnot(None),
        )
    )
    already_embedded = {row[0] for row in existing_result}

    new_chunks = [c for c in chunk_dicts if c["chunk_hash"] not in already_embedded]
    if not new_chunks:
        logger.debug("All %d chunks already indexed for source %s/%d", len(chunk_dicts), source_type, source_id)
        return 0

    texts = [c["chunk_text"] for c in new_chunks]
    embedding_result = embedding_svc.embed(texts)

    for i, chunk_dict in enumerate(new_chunks):
        vector = embedding_result.vectors[i]
        chunk = KnowledgeChunk(
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            source_version=source_version,
            chunk_index=i,
            chunk_text=chunk_dict["chunk_text"],
            chunk_hash=chunk_dict["chunk_hash"],
            token_count=chunk_dict.get("token_count"),
            embedding_model=embedding_result.model,
            embedding_dimension=embedding_result.dimension,
            embedding=json.dumps(vector),
            metadata_=chunk_dict.get("metadata"),
            is_active=True,
        )
        db.add(chunk)

    await db.flush()
    return len(new_chunks)


# ── High-level index functions ───────────────────────────────────────────────

async def index_document(
    db: AsyncSession,
    doc_id: int,
    embedding_svc: EmbeddingService | None = None,
) -> dict:
    """
    Index an UploadedDocument into knowledge_chunks.
    Called from Celery after text extraction completes.
    """
    if not settings.rag_enabled:
        return {"skipped": True, "reason": "RAG_ENABLED=false"}

    result = await db.execute(select(UploadedDocument).where(UploadedDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc or not doc.extracted_text:
        return {"skipped": True, "reason": "document not found or no extracted text"}

    t0 = time.monotonic()
    svc = embedding_svc or EmbeddingService()

    chunk_dicts = chunk_document_text(
        doc.extracted_text,
        source_metadata={
            "filename": doc.original_filename,
            "file_type": doc.file_type,
        },
    )

    active_hashes = {c["chunk_hash"] for c in chunk_dicts}
    deactivated = await _deactivate_stale_chunks(db, doc.project_id, "uploaded_document", doc_id, active_hashes)
    new_count = await _upsert_chunks(db, doc.project_id, "uploaded_document", doc_id, 1, chunk_dicts, svc)

    # Mark RAG index status on document metadata
    doc.metadata_ = {**(doc.metadata_ or {}), "rag_index_status": "indexed", "rag_chunk_count": len(chunk_dicts)}
    await db.commit()

    elapsed_ms = round((time.monotonic() - t0) * 1000)
    logger.info(
        "Indexed document %d: %d chunks, %d new, %d deactivated in %dms",
        doc_id, len(chunk_dicts), new_count, deactivated, elapsed_ms,
    )
    return {
        "document_id": doc_id,
        "total_chunks": len(chunk_dicts),
        "new_chunks": new_count,
        "deactivated_chunks": deactivated,
        "elapsed_ms": elapsed_ms,
    }


async def index_requirement(
    db: AsyncSession,
    requirement_id: int,
    embedding_svc: EmbeddingService | None = None,
) -> dict:
    """Index a structured Requirement into knowledge_chunks."""
    if not settings.rag_enabled:
        return {"skipped": True, "reason": "RAG_ENABLED=false"}

    result = await db.execute(select(Requirement).where(Requirement.id == requirement_id))
    req = result.scalar_one_or_none()
    if not req:
        return {"skipped": True, "reason": "requirement not found"}

    t0 = time.monotonic()
    svc = embedding_svc or EmbeddingService()

    chunk_dicts = chunk_requirement(req)
    active_hashes = {c["chunk_hash"] for c in chunk_dicts}
    deactivated = await _deactivate_stale_chunks(db, req.project_id, "requirement", requirement_id, active_hashes)
    new_count = await _upsert_chunks(db, req.project_id, "requirement", requirement_id, req.version, chunk_dicts, svc)

    await db.commit()
    elapsed_ms = round((time.monotonic() - t0) * 1000)
    logger.info("Indexed requirement %d: %d chunks, %d new in %dms", requirement_id, len(chunk_dicts), new_count, elapsed_ms)
    return {
        "requirement_id": requirement_id,
        "total_chunks": len(chunk_dicts),
        "new_chunks": new_count,
        "deactivated_chunks": deactivated,
        "elapsed_ms": elapsed_ms,
    }


async def reindex_project(
    db: AsyncSession,
    project_id: int,
    embedding_svc: EmbeddingService | None = None,
) -> dict:
    """Reindex all documents and requirements in a project."""
    if not settings.rag_enabled:
        return {"skipped": True, "reason": "RAG_ENABLED=false"}

    svc = embedding_svc or EmbeddingService()

    doc_results = await db.execute(
        select(UploadedDocument).where(UploadedDocument.project_id == project_id)
    )
    docs = doc_results.scalars().all()

    req_results = await db.execute(
        select(Requirement).where(Requirement.project_id == project_id, Requirement.is_deleted == False)  # noqa: E712
    )
    reqs = req_results.scalars().all()

    total_new = 0
    for doc in docs:
        r = await index_document(db, doc.id, svc)
        total_new += r.get("new_chunks", 0)

    for req in reqs:
        r = await index_requirement(db, req.id, svc)
        total_new += r.get("new_chunks", 0)

    return {
        "project_id": project_id,
        "documents_indexed": len(docs),
        "requirements_indexed": len(reqs),
        "total_new_chunks": total_new,
    }
