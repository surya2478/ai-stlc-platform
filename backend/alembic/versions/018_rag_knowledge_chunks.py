"""018 - RAG knowledge chunks, citations, and retrieval audit

Revision ID: 018
Revises: 017
Create Date: 2026-06-19

Fully idempotent migration — safe to re-run after partial failures.

1. Enables pgvector extension (if not already present)
2. Creates knowledge_chunks table with vector(384) embedding column + HNSW index
3. Creates artifact_citations table for provenance tracking
4. Creates rag_retrieval_events table for retrieval audit
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


# ── helpers ──────────────────────────────────────────────────────────────────

def _col_exists(table, column):
    conn = op.get_bind()
    r = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
    ), {"t": table, "c": column})
    return r.fetchone() is not None


def _table_exists(table):
    conn = op.get_bind()
    r = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=:t"
    ), {"t": table})
    return r.fetchone() is not None


def _index_exists(index_name):
    conn = op.get_bind()
    r = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"
    ), {"n": index_name})
    return r.fetchone() is not None


def _extension_exists(ext_name):
    conn = op.get_bind()
    r = conn.execute(sa.text(
        "SELECT 1 FROM pg_extension WHERE extname=:n"
    ), {"n": ext_name})
    return r.fetchone() is not None


# ========================== UPGRADE ==========================

def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Enable pgvector extension
    # ------------------------------------------------------------------
    if not _extension_exists("vector"):
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    # ------------------------------------------------------------------
    # 2. knowledge_chunks table
    # ------------------------------------------------------------------
    if not _table_exists("knowledge_chunks"):
        op.create_table(
            "knowledge_chunks",
            sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_type", sa.String(50), nullable=False),
            sa.Column("source_id", sa.BigInteger, nullable=True),
            sa.Column("source_version", sa.Integer, nullable=False, server_default="1"),
            sa.Column("chunk_index", sa.Integer, nullable=False),
            sa.Column("chunk_text", sa.Text, nullable=False),
            sa.Column("chunk_hash", sa.String(64), nullable=False),
            sa.Column("token_count", sa.Integer, nullable=True),
            sa.Column("embedding_model", sa.String(200), nullable=True),
            sa.Column("embedding_dimension", sa.Integer, nullable=True),
            sa.Column("chunk_metadata", JSONB, nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # Add vector column separately (requires pgvector DDL syntax)
    if not _col_exists("knowledge_chunks", "embedding"):
        op.execute(sa.text(
            "ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(384)"
        ))

    # Standard B-tree indexes
    if not _index_exists("ix_knowledge_chunks_project_id"):
        op.create_index("ix_knowledge_chunks_project_id", "knowledge_chunks", ["project_id"])
    if not _index_exists("ix_knowledge_chunks_source_type"):
        op.create_index("ix_knowledge_chunks_source_type", "knowledge_chunks", ["source_type"])
    if not _index_exists("ix_knowledge_chunks_source_id"):
        op.create_index("ix_knowledge_chunks_source_id", "knowledge_chunks", ["source_id"])
    if not _index_exists("ix_knowledge_chunks_chunk_hash"):
        op.create_index("ix_knowledge_chunks_chunk_hash", "knowledge_chunks", ["chunk_hash"])
    if not _index_exists("ix_knowledge_chunks_is_active"):
        op.create_index("ix_knowledge_chunks_is_active", "knowledge_chunks", ["is_active"])

    # Composite index for the most common retrieval filter
    if not _index_exists("ix_knowledge_chunks_project_source_active"):
        op.create_index(
            "ix_knowledge_chunks_project_source_active",
            "knowledge_chunks",
            ["project_id", "source_type", "is_active"],
        )

    # HNSW vector index for fast approximate nearest-neighbour search
    if not _index_exists("ix_knowledge_chunks_embedding_hnsw"):
        op.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_hnsw "
            "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        ))

    # Full-text search index for keyword retrieval
    if not _index_exists("ix_knowledge_chunks_chunk_text_fts"):
        op.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_chunk_text_fts "
            "ON knowledge_chunks USING gin (to_tsvector('english', chunk_text))"
        ))

    # ------------------------------------------------------------------
    # 3. artifact_citations table
    # ------------------------------------------------------------------
    if not _table_exists("artifact_citations"):
        op.create_table(
            "artifact_citations",
            sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("artifact_type", sa.String(50), nullable=False),
            sa.Column("artifact_id", sa.BigInteger, nullable=False),
            sa.Column("chunk_id", sa.BigInteger, sa.ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("agent_run_id", sa.Integer, sa.ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("retrieval_score", sa.Float, nullable=True),
            sa.Column("rerank_score", sa.Float, nullable=True),
            sa.Column("citation_reason", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if not _index_exists("ix_artifact_citations_project_id"):
        op.create_index("ix_artifact_citations_project_id", "artifact_citations", ["project_id"])
    if not _index_exists("ix_artifact_citations_artifact"):
        op.create_index("ix_artifact_citations_artifact", "artifact_citations", ["artifact_type", "artifact_id"])
    if not _index_exists("ix_artifact_citations_chunk_id"):
        op.create_index("ix_artifact_citations_chunk_id", "artifact_citations", ["chunk_id"])

    # ------------------------------------------------------------------
    # 4. rag_retrieval_events table
    # ------------------------------------------------------------------
    if not _table_exists("rag_retrieval_events"):
        op.create_table(
            "rag_retrieval_events",
            sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("agent_run_id", sa.Integer, sa.ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("query_text", sa.Text, nullable=False),
            sa.Column("query_type", sa.String(100), nullable=True),
            sa.Column("embedding_model", sa.String(200), nullable=True),
            sa.Column("retrieval_method", sa.String(50), nullable=True),
            sa.Column("filters_applied", JSONB, nullable=True),
            sa.Column("candidate_count", sa.Integer, nullable=True),
            sa.Column("selected_chunk_ids", JSONB, nullable=True),
            sa.Column("scores", JSONB, nullable=True),
            sa.Column("latency_ms", sa.Float, nullable=True),
            sa.Column("prompt_version", sa.String(100), nullable=True),
            sa.Column("llm_provider", sa.String(100), nullable=True),
            sa.Column("llm_model", sa.String(200), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if not _index_exists("ix_rag_retrieval_events_project_id"):
        op.create_index("ix_rag_retrieval_events_project_id", "rag_retrieval_events", ["project_id"])
    if not _index_exists("ix_rag_retrieval_events_agent_run_id"):
        op.create_index("ix_rag_retrieval_events_agent_run_id", "rag_retrieval_events", ["agent_run_id"])


# ========================== DOWNGRADE ==========================

def downgrade() -> None:
    # Drop in reverse dependency order
    op.execute(sa.text("DROP INDEX IF EXISTS ix_rag_retrieval_events_agent_run_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_rag_retrieval_events_project_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS rag_retrieval_events"))

    op.execute(sa.text("DROP INDEX IF EXISTS ix_artifact_citations_chunk_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_artifact_citations_artifact"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_artifact_citations_project_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS artifact_citations"))

    op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_chunks_chunk_text_fts"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_chunks_project_source_active"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_chunks_is_active"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_chunks_chunk_hash"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_chunks_source_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_chunks_source_type"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_chunks_project_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS knowledge_chunks"))
