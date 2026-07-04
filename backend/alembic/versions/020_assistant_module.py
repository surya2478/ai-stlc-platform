"""020 - nxtQA Platform Assistant Tables

Revision ID: 020
Revises: 019
Create Date: 2026-06-26

Fully idempotent migration — safe to re-run after partial failures.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


# ── helpers ──────────────────────────────────────────────────────────────────

def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    r = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=:t"
    ), {"t": table})
    return r.fetchone() is not None


# ========================== UPGRADE ==========================

def upgrade() -> None:
    # 1. assistant_conversations
    if not _table_exists("assistant_conversations"):
        op.create_table(
            "assistant_conversations",
            sa.Column("id", sa.BigInteger, primary_key=True, index=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True),
            sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("title", sa.String(255), nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # 2. assistant_messages
    if not _table_exists("assistant_messages"):
        op.create_table(
            "assistant_messages",
            sa.Column("id", sa.BigInteger, primary_key=True, index=True),
            sa.Column("conversation_id", sa.BigInteger, sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("role", sa.String(50), nullable=False),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("scope_classification", sa.String(100), nullable=True),
            sa.Column("confidence", sa.String(50), nullable=True),
            sa.Column("token_usage", sa.Integer, nullable=True),
            sa.Column("latency_ms", sa.Float, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # 3. assistant_audit_events
    if not _table_exists("assistant_audit_events"):
        op.create_table(
            "assistant_audit_events",
            sa.Column("id", sa.BigInteger, primary_key=True, index=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("conversation_id", sa.BigInteger, sa.ForeignKey("assistant_conversations.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("message_id", sa.BigInteger, sa.ForeignKey("assistant_messages.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("event_type", sa.String(100), nullable=False),
            sa.Column("scope_classification", sa.String(100), nullable=True),
            sa.Column("tool_names", JSONB, nullable=True),
            sa.Column("retrieved_source_ids", JSONB, nullable=True),
            sa.Column("authorization_result", sa.String(50), nullable=False),
            sa.Column("blocked_reason", sa.Text, nullable=True),
            sa.Column("model_provider", sa.String(100), nullable=True),
            sa.Column("model_name", sa.String(200), nullable=True),
            sa.Column("latency_ms", sa.Float, nullable=True),
            sa.Column("token_usage", sa.Integer, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # 4. assistant_feedback
    if not _table_exists("assistant_feedback"):
        op.create_table(
            "assistant_feedback",
            sa.Column("id", sa.BigInteger, primary_key=True, index=True),
            sa.Column("conversation_id", sa.BigInteger, sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("message_id", sa.BigInteger, sa.ForeignKey("assistant_messages.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("feedback_type", sa.String(50), nullable=False),
            sa.Column("comment", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # 5. assistant_knowledge_sources
    if not _table_exists("assistant_knowledge_sources"):
        op.create_table(
            "assistant_knowledge_sources",
            sa.Column("id", sa.BigInteger, primary_key=True, index=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("module", sa.String(100), nullable=True, index=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true", index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # 6. assistant_retrieval_events
    if not _table_exists("assistant_retrieval_events"):
        op.create_table(
            "assistant_retrieval_events",
            sa.Column("id", sa.BigInteger, primary_key=True, index=True),
            sa.Column("conversation_id", sa.BigInteger, sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("message_id", sa.BigInteger, sa.ForeignKey("assistant_messages.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("query_text", sa.Text, nullable=False),
            sa.Column("selected_source_ids", JSONB, nullable=True),
            sa.Column("scores", JSONB, nullable=True),
            sa.Column("latency_ms", sa.Float, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


# ========================== DOWNGRADE ==========================

def downgrade() -> None:
    op.drop_table("assistant_retrieval_events")
    op.drop_table("assistant_feedback")
    op.drop_table("assistant_audit_events")
    op.drop_table("assistant_knowledge_sources")
    op.drop_table("assistant_messages")
    op.drop_table("assistant_conversations")
