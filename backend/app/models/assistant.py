from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class AssistantConversation(TimestampMixin, Base):
    """Stores conversation threads initiated by authenticated users."""
    __tablename__ = "assistant_conversations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    messages: Mapped[list["AssistantMessage"]] = relationship(
        "AssistantMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AssistantMessage.created_at",
    )
    feedback: Mapped[list["AssistantFeedback"]] = relationship(
        "AssistantFeedback", back_populates="conversation", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list["AssistantAuditEvent"]] = relationship(
        "AssistantAuditEvent", back_populates="conversation", cascade="all, delete-orphan"
    )
    retrieval_events: Mapped[list["AssistantRetrievalEvent"]] = relationship(
        "AssistantRetrievalEvent", back_populates="conversation", cascade="all, delete-orphan"
    )


class AssistantMessage(TimestampMixin, Base):
    """Stores individual message turns in a conversation."""
    __tablename__ = "assistant_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    scope_classification: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(50), nullable=True)
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    conversation: Mapped["AssistantConversation"] = relationship(
        "AssistantConversation", back_populates="messages"
    )
    feedback: Mapped[list["AssistantFeedback"]] = relationship(
        "AssistantFeedback", back_populates="message", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list["AssistantAuditEvent"]] = relationship(
        "AssistantAuditEvent", back_populates="message", cascade="all, delete-orphan"
    )
    retrieval_events: Mapped[list["AssistantRetrievalEvent"]] = relationship(
        "AssistantRetrievalEvent", back_populates="message", cascade="all, delete-orphan"
    )


class AssistantAuditEvent(TimestampMixin, Base):
    """Audit log of assistant usage, scope guards, and security validation."""
    __tablename__ = "assistant_audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("assistant_messages.id", ondelete="SET NULL"), nullable=True, index=True
    )

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    scope_classification: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_names: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    retrieved_source_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    authorization_result: Mapped[str] = mapped_column(String(50), nullable=False)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    conversation: Mapped["AssistantConversation"] = relationship(
        "AssistantConversation", back_populates="audit_events"
    )
    message: Mapped["AssistantMessage"] = relationship(
        "AssistantMessage", back_populates="audit_events"
    )


class AssistantFeedback(TimestampMixin, Base):
    """User feedback helpful/unhelpful rating on individual assistant answers."""
    __tablename__ = "assistant_feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[int] = mapped_column(
        ForeignKey("assistant_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=False)  # helpful | unhelpful
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    conversation: Mapped["AssistantConversation"] = relationship(
        "AssistantConversation", back_populates="feedback"
    )
    message: Mapped["AssistantMessage"] = relationship(
        "AssistantMessage", back_populates="feedback"
    )


class AssistantKnowledgeSource(TimestampMixin, Base):
    """Global documentation chunks describing platform guidance & workflows."""
    __tablename__ = "assistant_knowledge_sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class AssistantRetrievalEvent(TimestampMixin, Base):
    """Linkage map between assistant messages and retrieved knowledge sources."""
    __tablename__ = "assistant_retrieval_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[int] = mapped_column(
        ForeignKey("assistant_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    selected_source_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    conversation: Mapped["AssistantConversation"] = relationship(
        "AssistantConversation", back_populates="retrieval_events"
    )
    message: Mapped["AssistantMessage"] = relationship(
        "AssistantMessage", back_populates="retrieval_events"
    )
