"""Pydantic schemas for Test Data Management."""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


TestDataSourceType = Literal[
    "ai_generated",
    "manual",
    "imported",
    "synthetic",
    "masked_production_like",
    "external_system",
    "jira",
    "automation_runtime",
    "external_tool",
]
TestDataStatus = Literal[
    "draft",
    "pending_approval",
    "approved",
    "rejected",
    "active",
    "reserved",
    "consumed",
    "expired",
    "archived",
    "invalid",
]
ApprovalStatus = Literal["draft", "pending_approval", "approved", "rejected"]
ReservationStatus = Literal["available", "reserved", "consumed", "released", "expired"]
PrivacyLevel = Literal["public", "internal", "confidential", "restricted"]
MaskingStatus = Literal["not_required", "pending", "masked", "failed"]
SyntheticGenerationStatus = Literal["not_required", "pending", "generated", "failed"]
QualityStatus = Literal["valid", "warning", "invalid", "not_checked"]
GenerationStatus = Literal["not_requested", "requested", "pending_external_generation", "generated", "failed", "cancelled"]
ValidationStatus = Literal["not_validated", "valid", "warning", "invalid"]
ImportMode = Literal["create_new_dataset", "append_to_existing_dataset"]
ExternalTool = Literal["Mock", "Faker", "Katalon", "Playwright", "Pytest", "GenRocket", "Delphix", "Broadcom TDM", "Informatica TDM", "Other"]


class TestDataTemplateBase(BaseModel):
    name: str
    description: str | None = None
    telecom_domain: str | None = None
    test_phase: str | None = None
    data_type: str = "Generic"
    schema_json: dict[str, Any] | None = None
    default_generation_rules_json: dict[str, Any] | None = None
    validation_rules_json: dict[str, Any] | None = None
    masking_rules_json: dict[str, Any] | None = None
    is_active: bool = True


class TestDataTemplateCreate(TestDataTemplateBase):
    pass


class TestDataTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    telecom_domain: str | None = None
    test_phase: str | None = None
    data_type: str | None = None
    schema_json: dict[str, Any] | None = None
    default_generation_rules_json: dict[str, Any] | None = None
    validation_rules_json: dict[str, Any] | None = None
    masking_rules_json: dict[str, Any] | None = None
    is_active: bool | None = None


class TestDataTemplateOut(TestDataTemplateBase):
    id: int
    project_id: int
    template_id: str
    created_by: int
    updated_by: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestDataBase(BaseModel):
    name: str
    description: str | None = None
    data_type: str = "Generic"
    source_type: TestDataSourceType = "manual"
    telecom_domain: str | None = None
    test_phase: str | None = None
    product_group: str | None = None
    product: str | None = None
    sub_request_type: str | None = None
    environment: str | None = None
    version: int = 1
    tags: list[str] = Field(default_factory=list)
    template_id: int | None = None
    test_case_id: int | None = None
    requirement_id: int | None = None
    execution_run_id: int | None = None
    linked_requirement_key: str | None = None
    linked_jira_issue_key: str | None = None
    linked_jira_url: str | None = None
    linked_defect_id: int | None = None
    data_payload_json: dict[str, Any] = Field(default_factory=dict)
    schema_json: dict[str, Any] | None = None
    sample_preview_json: dict[str, Any] | None = None
    sensitive_fields_json: list[str] = Field(default_factory=list)
    masking_rules_json: dict[str, Any] | None = None
    validation_rules_json: dict[str, Any] | None = None
    privacy_level: PrivacyLevel = "internal"
    contains_pii: bool = False
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("name is required")
        return trimmed


class TestDataCreate(TestDataBase):
    submit_for_approval: bool = False


class TestDataUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    data_type: str | None = None
    telecom_domain: str | None = None
    test_phase: str | None = None
    product_group: str | None = None
    product: str | None = None
    sub_request_type: str | None = None
    environment: str | None = None
    tags: list[str] | None = None
    template_id: int | None = None
    test_case_id: int | None = None
    requirement_id: int | None = None
    execution_run_id: int | None = None
    linked_requirement_key: str | None = None
    linked_jira_issue_key: str | None = None
    linked_jira_url: str | None = None
    linked_defect_id: int | None = None
    data_payload_json: dict[str, Any] | None = None
    schema_json: dict[str, Any] | None = None
    sample_preview_json: dict[str, Any] | None = None
    sensitive_fields_json: list[str] | None = None
    masking_rules_json: dict[str, Any] | None = None
    validation_rules_json: dict[str, Any] | None = None
    privacy_level: PrivacyLevel | None = None
    contains_pii: bool | None = None
    notes: str | None = None
    status: TestDataStatus | None = None


class TestDataGenerateRequest(BaseModel):
    name: str
    linked_requirement_id: int | None = None
    linked_test_case_id: int | None = None
    telecom_domain: str
    test_phase: str
    environment: str
    product_group: str | None = None
    product: str | None = None
    sub_request_type: str | None = None
    data_type: str
    number_of_records: int = 1
    generation_mode: Literal["positive", "negative", "boundary", "invalid", "mixed"] = "positive"
    external_tool: ExternalTool
    external_suite_id: str | None = None
    external_dataset_id: str | None = None
    external_url: HttpUrl | None = None
    request_notes: str | None = None
    priority: str | None = None
    expected_by_date: date | None = None
    # Schema consumed by the LocalFakerToolClient. Shape (see
    # app/services/test_data_generation/faker_engine.py docstring):
    #   { "locale": "en_US", "fields": [{ "name": "...", "provider": "...", "params": {...} }, ...] }
    # Ignored for other tools.
    schema_json: dict[str, Any] | None = None

    @field_validator("name", "data_type", "telecom_domain", "test_phase", "environment")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("field is required")
        return trimmed

    @field_validator("number_of_records")
    @classmethod
    def validate_record_count(cls, value: int) -> int:
        if value < 1 or value > 10000:
            raise ValueError("number_of_records must be between 1 and 10000")
        return value

    @field_validator("expected_by_date")
    @classmethod
    def validate_expected_date(cls, value: date | None) -> date | None:
        if value and value < date.today():
            raise ValueError("expected_by_date cannot be in the past")
        return value


class TestDataGenerateResponse(BaseModel):
    data_set_id: int
    data_id: str
    generation_status: GenerationStatus
    status: str
    external_tool: str | None = None
    message: str


class TestDataImportPreviewResponse(BaseModel):
    preview_token: str
    filename: str
    file_type: str
    detected_columns: list[str]
    row_count: int
    preview_rows: list[dict[str, Any]]
    validation_errors: list[dict[str, Any]]
    validation_warnings: list[dict[str, Any]]
    can_import: bool


class TestDataImportConfirmRequest(BaseModel):
    preview_token: str


class TestDataImportConfirmResponse(BaseModel):
    data_set_id: int
    data_id: str
    imported_record_count: int
    skipped_record_count: int
    validation_summary: dict[str, Any]


class TestDataImportMetadata(BaseModel):
    name: str | None = None
    data_type: str
    telecom_domain: str
    test_phase: str
    environment: str
    product_group: str | None = None
    product: str | None = None
    sub_request_type: str | None = None
    contains_pii: bool = False
    privacy_level: PrivacyLevel = "internal"
    linked_requirement_id: int | None = None
    linked_test_case_id: int | None = None
    import_mode: ImportMode = "create_new_dataset"
    existing_data_set_id: int | None = None
    validate_before_import: bool = True

    @field_validator("data_type", "telecom_domain", "test_phase", "environment")
    @classmethod
    def validate_metadata_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("field is required")
        return trimmed

    @model_validator(mode="after")
    def validate_privacy_and_mode(self):
        if self.contains_pii and self.privacy_level == "public":
            raise ValueError("privacy_level cannot be public when contains_pii is true")
        if self.import_mode == "append_to_existing_dataset" and not self.existing_data_set_id:
            raise ValueError("existing_data_set_id is required when appending to a data set")
        return self


class TestDataValidateOut(BaseModel):
    data_id: int
    quality_score: float
    quality_status: QualityStatus
    quality_issues_json: list[dict[str, Any]]


class TestDataMaskRequest(BaseModel):
    fields: list[str] = Field(default_factory=list)
    keep_last: int = 3


class TestDataReservationRequest(BaseModel):
    reserved_for_execution_id: int | None = None
    duration_minutes: int = 60


class TestDataApprovalRequest(BaseModel):
    notes: str | None = None


class TestDataHistoryOut(BaseModel):
    id: int
    action_type: str
    decision: str
    notes: str | None = None
    user_id: int
    actor_role: str | None = None
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TestDataOut(BaseModel):
    id: int
    project_id: int
    data_id: str
    name: str
    description: str | None = None
    data_type: str
    source_type: str
    status: str
    approval_status: str
    telecom_domain: str | None = None
    test_phase: str | None = None
    product_group: str | None = None
    product: str | None = None
    sub_request_type: str | None = None
    environment: str | None = None
    version: int
    tags: list[str] | None = None
    template_id: int | None = None
    linked_requirement_id: int | None = None
    linked_requirement_key: str | None = None
    linked_test_case_id: int | None = None
    linked_execution_run_id: int | None = None
    linked_jira_issue_key: str | None = None
    linked_jira_url: str | None = None
    linked_defect_id: int | None = None
    data_payload_json: dict[str, Any] | None = None
    sample_preview_json: dict[str, Any] | None = None
    sensitive_fields_json: list[str] | None = None
    privacy_level: str
    contains_pii: bool
    masking_status: str
    synthetic_generation_status: str
    generation_status: str
    generation_mode: str | None = None
    requested_record_count: int | None = None
    actual_record_count: int = 0
    external_tool: str | None = None
    external_suite_id: str | None = None
    external_dataset_id: str | None = None
    external_url: str | None = None
    request_notes: str | None = None
    priority: str | None = None
    expected_by_date: datetime | None = None
    validation_status: str
    validation_summary_json: dict[str, Any] | None = None
    import_filename: str | None = None
    reservation_status: str
    reserved_by: int | None = None
    reserved_for_execution_id: int | None = None
    reservation_expires_at: datetime | None = None
    consumed_at: datetime | None = None
    quality_score: float | None = None
    quality_status: str
    quality_issues_json: list[dict[str, Any]] | None = None
    jira_sync_status: str
    last_synced_at: datetime | None = None
    sync_error: str | None = None
    created_by: int
    updated_by: int | None = None
    approved_by: int | None = None
    approved_at: datetime | None = None
    last_used_at: datetime | None = None
    usage_count: int
    agent_run_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestDataSummaryOut(BaseModel):
    total_data_sets: int
    approved: int
    pending_approval: int
    synthetic: int
    masked: int
    reserved: int
    expired: int
    linked_test_cases: int
    data_quality_issues: int
    by_status: dict[str, int]
    by_source_type: dict[str, int]
    by_reservation_status: dict[str, int]
    by_quality_status: dict[str, int]
