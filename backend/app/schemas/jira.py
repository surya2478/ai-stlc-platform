"""Pydantic schemas for Jira connections and imports."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class JiraConnectionCreate(BaseModel):
    project_id: int
    jira_base_url: str = Field(max_length=500)
    jira_email: str = Field(max_length=255)
    jira_api_token: str = Field(min_length=1)
    jira_project_key: str = Field(max_length=50)
    is_active: bool = True
    metadata_: dict[str, Any] | None = None

    @field_validator("jira_base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("jira_base_url must start with http:// or https://")
        return value

    @field_validator("jira_email", "jira_api_token", "jira_project_key")
    @classmethod
    def required_string(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("jira_project_key")
    @classmethod
    def normalize_project_key(cls, value: str) -> str:
        return value.strip().upper()


class JiraConnectionUpdate(BaseModel):
    jira_base_url: str | None = Field(default=None, max_length=500)
    jira_email: str | None = Field(default=None, max_length=255)
    jira_api_token: str | None = Field(default=None, min_length=1)
    jira_project_key: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None
    status: Literal["connected", "error", "disconnected"] | None = None
    metadata_: dict[str, Any] | None = None

    @field_validator("jira_base_url")
    @classmethod
    def normalize_optional_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("jira_base_url must start with http:// or https://")
        return value

    @field_validator("jira_email", "jira_api_token", "jira_project_key")
    @classmethod
    def optional_required_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("jira_project_key")
    @classmethod
    def normalize_optional_project_key(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class JiraConnectionOut(BaseModel):
    id: int
    project_id: int
    created_by: int
    jira_base_url: str
    jira_email: str
    jira_project_key: str
    is_active: bool
    last_sync_at: str | None = None
    status: str
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JiraConnectionTestOut(BaseModel):
    success: bool
    message: str
    account_id: str | None = None
    display_name: str | None = None


class JiraIssueFilters(BaseModel):
    issue_types: list[str] | None = None
    statuses: list[str] | None = None
    priorities: list[str] | None = None
    labels: list[str] | None = None
    # An explicit pick, for when the caller has already seen the matches and
    # wants only some of them. Narrows the same query the other filters build
    # rather than replacing it, so it composes with them and stays project
    # scoped. Omitted (the default) means "everything the filters match" —
    # exactly the behaviour every existing caller relies on.
    issue_keys: list[str] | None = None
    assignee: str | None = None
    text: str | None = None
    updated_since: str | None = None
    jql: str | None = None

    @field_validator("issue_types", "statuses", "priorities", "labels", "issue_keys")
    @classmethod
    def clean_filter_list(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item and item.strip()]
        return cleaned or None

    @field_validator("assignee", "text", "updated_since", "jql")
    @classmethod
    def clean_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class JiraFetchIssuesRequest(JiraIssueFilters):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


class JiraIssueOut(BaseModel):
    key: str
    summary: str
    description: str | None = None
    issue_type: str | None = None
    status: str | None = None
    priority: str | None = None
    labels: list[str] = []
    updated: str | None = None
    raw: dict[str, Any]


class JiraIssuePageOut(BaseModel):
    items: list[JiraIssueOut]
    total: int
    page: int
    page_size: int
    pages: int
    jql: str


class JiraImportRequirementsRequest(JiraIssueFilters):
    batch_size: int = Field(default=50, ge=1, le=100)
    max_issues: int = Field(default=500, ge=1, le=5000)


class JiraImportRequirementsOut(BaseModel):
    imported: int
    created: int
    updated: int
    requirement_ids: list[int]
    # GAP-4b: agent run id of the post-import structured-field enrichment (if queued)
    enrichment_agent_run_id: int | None = None


class JiraSyncTriggerRequest(JiraIssueFilters):
    direction: Literal["inbound", "outbound", "both"] = "inbound"
    batch_size: int = Field(default=50, ge=1, le=100)
    max_issues: int = Field(default=500, ge=1, le=5000)


class JiraSyncTriggerOut(BaseModel):
    sync_job_id: int
    task_id: str
    status: str


class JiraWebhookReceiveOut(BaseModel):
    webhook_event_id: int
    event_key: str
    queued: bool
    task_id: str | None = None
