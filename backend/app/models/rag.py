"""
RAG data models: KnowledgeChunk, ArtifactCitation, RagRetrievalEvent.

KnowledgeChunk stores embedded text chunks from any source (uploaded documents,
requirements, test cases, defects, etc.) with a pgvector column for similarity search.

ArtifactCitation links generated artifacts back to the retrieved chunks that
grounded their generation.

RagRetrievalEvent is the audit log for each retrieval operation.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    cast,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from app.database import Base
from app.models.base import TimestampMixin

try:
    from pgvector.sqlalchemy import Vector
    _PGVECTOR_AVAILABLE = True
except ImportError:
    _PGVECTOR_AVAILABLE = False
    Vector = None


class _PgVector(UserDefinedType):
    """Renders as the bare `vector` type, purely as a cast target."""

    cache_ok = True

    def get_col_spec(self, **_kw: object) -> str:
        return "vector"


class VectorText(TypeDecorator):
    """Text in Python, `vector` in Postgres.

    Migration 018 creates `embedding` as vector(384) through raw DDL, and
    retrieval reads it through raw SQL that casts explicitly (`:vec::vector`).
    The ORM write path had no such cast: it mapped the column as Text and sent
    a JSON string, which Postgres refused with

        column "embedding" is of type vector but expression is of type
        character varying

    so every attempt to index a document failed at the insert while search —
    never reaching a row — looked healthy. That is why a project with a
    processed document still reported zero chunks.

    Casting the bind parameter restores the symmetry, and keeps the stored
    value a JSON string as the rest of this module expects, so it works
    whether or not pgvector's own SQLAlchemy type is installed.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, _dialect):
        """Accept the list callers now pass, as pgvector's own type does, so
        the two paths take the same input."""
        if value is None or isinstance(value, str):
            return value
        return "[" + ",".join(repr(float(v)) for v in value) + "]"

    def bind_expression(self, bindvalue):
        return cast(bindvalue, _PgVector())


def _vector_column(dim: int):
    """Return a pgvector column if the extension is installed, else a Text
    column that still casts to `vector` on write."""
    if _PGVECTOR_AVAILABLE and Vector is not None:
        return mapped_column(Vector(dim), nullable=True)
    return mapped_column(VectorText, nullable=True)


# Valid source types for KnowledgeChunk
SOURCE_TYPES = (
    "uploaded_document",
    "requirement",
    "test_case",
    "defect",
    "execution",
    "jira",
    "knowledge_base",
)

# Valid artifact types for ArtifactCitation
ARTIFACT_TYPES = (
    "test_scenario",
    "test_case",
    "test_plan",
    "defect",
    "report",
    "requirement",
)


class KnowledgeChunk(TimestampMixin, Base):
    """
    A single semantic chunk from any indexable source, with its embedding vector.

    The `embedding` column uses pgvector when available. Dimension is fixed at
    creation time by EMBEDDING_DIMENSION in settings (default 384 for bge-small).
    """
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # pgvector column — dimension set to 384 matching bge-small-en-v1.5.
    # Migration creates the actual vector(384) column via raw DDL, so this goes
    # through _vector_column rather than a plain Text mapping: the plain
    # mapping sent an uncast string and Postgres rejected every insert.
    embedding: Mapped[list[float] | None] = _vector_column(384)

    metadata_: Mapped[dict | None] = mapped_column("chunk_metadata", JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # Relationships
    citations: Mapped[list["ArtifactCitation"]] = relationship(
        "ArtifactCitation", back_populates="chunk", cascade="all, delete-orphan"
    )


class ArtifactCitation(TimestampMixin, Base):
    """
    Links a generated artifact to the KnowledgeChunk(s) that grounded it.
    Provides full provenance: which chunks, which agent run, what scores.
    """
    __tablename__ = "artifact_citations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    artifact_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    chunk_id: Mapped[int] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True)

    retrieval_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rerank_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    citation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    chunk: Mapped["KnowledgeChunk"] = relationship("KnowledgeChunk", back_populates="citations")


class RagRetrievalEvent(TimestampMixin, Base):
    """
    Audit log for every retrieval operation — query, filters, scores, latency.
    Enables reproducibility and quality measurement.
    """
    __tablename__ = "rag_retrieval_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True)

    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    retrieval_method: Mapped[str | None] = mapped_column(String(50), nullable=True)

    filters_applied: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    candidate_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_chunk_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
