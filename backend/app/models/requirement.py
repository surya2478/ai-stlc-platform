from sqlalchemy import ARRAY, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Requirement(TimestampMixin, Base):
    __tablename__ = "requirements"
    __table_args__ = (UniqueConstraint("project_id", "requirement_id", name="uq_requirements_project_requirement_id"),)

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

    # Telecom domain and classification fields.
    qa_domain: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    telecom_domain: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    product_group: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    product: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    sub_request_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    test_phase: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    impacted_systems: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    impacted_interfaces: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    impacted_products: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    impacted_channels: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    customer_segment: Mapped[str | None] = mapped_column(String(200), nullable=True)
    business_process: Mapped[str | None] = mapped_column(String(200), nullable=True)
    release_train: Mapped[str | None] = mapped_column(String(100), nullable=True)
    release_version: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    regulatory_impact: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    revenue_impact: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    customer_impact: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    dependency_systems: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    upstream_systems: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    downstream_systems: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    api_interface_refs: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    environment_needs: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_data_needs: Mapped[str | None] = mapped_column(Text, nullable=True)
    nfr_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)

    readiness_status: Mapped[str | None] = mapped_column(String(50), nullable=True, default="draft", index=True)

    # Optional Jira fields and sync state.
    jira_issue_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jira_issue_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jira_priority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    jira_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    jira_updated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    jira_last_synced_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    jira_issue_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    jira_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jira_assignee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jira_reporter: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jira_labels: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    jira_components: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    jira_fix_versions: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    jira_sprint: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jira_epic_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="draft")
    # status: draft | pending_review | approved | rejected

    # Quality denormalization for fast list queries.
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_verdict: Mapped[str | None] = mapped_column(String(30), nullable=True)

    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    deleted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Linked document (if from upload)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_documents.id"), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="requirements")
    source_document: Mapped["UploadedDocument | None"] = relationship("UploadedDocument", back_populates="requirements")
    chunks: Mapped[list["RequirementChunk"]] = relationship("RequirementChunk", back_populates="requirement", cascade="all, delete-orphan")
    quality_reviews: Mapped[list["RequirementQualityReview"]] = relationship("RequirementQualityReview", back_populates="requirement")
    test_scenarios: Mapped[list["TestScenario"]] = relationship("TestScenario", back_populates="requirement")
    test_cases: Mapped[list["TestCase"]] = relationship("TestCase", back_populates="requirement")

    @property
    def effective_domain(self) -> str | None:
        """Return the canonical domain, falling back to the legacy column."""
        return self.telecom_domain or self.qa_domain


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
