from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class TestData(TimestampMixin, Base):
    """Reusable test datasets from Test Data Agent (Agent 6)."""
    __tablename__ = "test_data"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    test_case_id: Mapped[int | None] = mapped_column(ForeignKey("test_cases.id"), nullable=True, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    data_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    valid_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    invalid_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    boundary_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    requirement_id: Mapped[int | None] = mapped_column(ForeignKey("requirements.id"), nullable=True, index=True)
    execution_run_id: Mapped[int | None] = mapped_column(ForeignKey("execution_runs.id"), nullable=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("test_data_templates.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reserved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    data_payload_json: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    schema_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sample_preview_json: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    sensitive_fields_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    masking_rules_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validation_rules_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # The `default=` values from here down mirror the column defaults the
    # database already declares. They are NOT decorative: these columns are
    # NOT NULL in the schema, and SQLAlchemy sends an explicit NULL for any
    # attribute left unset — which means the server default never applies and
    # the INSERT fails. Creating test data through the API raised
    # NotNullViolation on `usage_count` until these were added.
    approval_status: Mapped[str | None] = mapped_column(String(50), nullable=True, default="draft")
    telecom_domain: Mapped[str | None] = mapped_column(String(80), nullable=True)
    test_phase: Mapped[str | None] = mapped_column(String(80), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(80), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    linked_requirement_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linked_jira_issue_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linked_jira_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_defect_id: Mapped[int | None] = mapped_column(ForeignKey("defect_drafts.id"), nullable=True)
    privacy_level: Mapped[str | None] = mapped_column(String(50), nullable=True, default="internal")
    contains_pii: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    masking_status: Mapped[str | None] = mapped_column(String(50), nullable=True, default="not_required")
    synthetic_generation_status: Mapped[str | None] = mapped_column(String(50), nullable=True, default="not_required")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reservation_status: Mapped[str | None] = mapped_column(String(50), nullable=True, default="available")
    reserved_for_execution_id: Mapped[int | None] = mapped_column(ForeignKey("execution_runs.id"), nullable=True)
    reserved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reservation_expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_status: Mapped[str | None] = mapped_column(String(50), nullable=True, default="not_checked")
    quality_issues_json: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    jira_sync_status: Mapped[str | None] = mapped_column(String(50), nullable=True, default="not_synced")
    last_synced_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_status: Mapped[str | None] = mapped_column(String(50), nullable=True, default="not_requested")
    generation_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    requested_record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_record_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    external_tool: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_suite_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_dataset_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    expected_by_date: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_status: Mapped[str | None] = mapped_column(String(50), nullable=True, default="not_validated")
    validation_summary_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    import_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_group: Mapped[str | None] = mapped_column(String(200), nullable=True)
    product: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sub_request_type: Mapped[str | None] = mapped_column(String(200), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="active")
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    test_case: Mapped["TestCase | None"] = relationship("TestCase", back_populates="test_data_sets")
    records: Mapped[list["TestDataRecord"]] = relationship("TestDataRecord", back_populates="data_set")


class TestDataRecord(TimestampMixin, Base):
    """Individual row belonging to a generated or imported test data set."""
    __tablename__ = "test_data_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    data_set_id: Mapped[int] = mapped_column(ForeignKey("test_data.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    record_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_json: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    masked_payload_json: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    validation_status: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    validation_errors_json: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)

    data_set: Mapped["TestData"] = relationship("TestData", back_populates="records")


class TestDataTemplate(TimestampMixin, Base):
    """Reusable schema and generation template for test data."""
    __tablename__ = "test_data_templates"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    template_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    telecom_domain: Mapped[str | None] = mapped_column(String(80), nullable=True)
    test_phase: Mapped[str | None] = mapped_column(String(80), nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    schema_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    default_generation_rules_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validation_rules_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    masking_rules_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)


class TestDataImportPreview(TimestampMixin, Base):
    """Temporary parsed import payload awaiting user confirmation."""
    __tablename__ = "test_data_import_previews"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    preview_token: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    detected_columns_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    parsed_rows_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    validation_errors_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    validation_warnings_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    can_import: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consumed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
