from sqlalchemy import ForeignKey, String, Text, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Requirement(TimestampMixin, Base):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    requirement_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # e.g. REQ-001 — auto-generated or from Jira
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    # source: jira | doc_upload | manual
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured output from Requirement Intake Agent (Agent 1)
    acceptance_criteria: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    business_rules: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    user_roles: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    systems_impacted: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    ui_pages: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    apis: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    dependencies: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    risks: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    missing_information: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Optional Jira fields
    jira_issue_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jira_issue_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jira_priority: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Linked document (if from upload)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_documents.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="draft")
    # status: draft | pending_review | approved | rejected

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="requirements")
    source_document: Mapped["UploadedDocument | None"] = relationship("UploadedDocument", back_populates="requirements")
    chunks: Mapped[list["RequirementChunk"]] = relationship("RequirementChunk", back_populates="requirement", cascade="all, delete-orphan")
    quality_reviews: Mapped[list["RequirementQualityReview"]] = relationship("RequirementQualityReview", back_populates="requirement")
    test_scenarios: Mapped[list["TestScenario"]] = relationship("TestScenario", back_populates="requirement")
    test_cases: Mapped[list["TestCase"]] = relationship("TestCase", back_populates="requirement")


class RequirementChunk(TimestampMixin, Base):
    """Chunked text embeddings for RAG / vector search over requirements."""
    __tablename__ = "requirement_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)

    chunk_index: Mapped[int] = mapped_column(nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(nullable=True)
    # embedding stored in pgvector column (added via migration after pgvector extension)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    requirement: Mapped["Requirement"] = relationship("Requirement", back_populates="chunks")
