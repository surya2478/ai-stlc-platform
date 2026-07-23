import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator

_KEY_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MOCK_STRATEGIES = ("intercept", "sandbox", "ignore")
LIFECYCLE_STATUSES = ("draft", "active", "deprecated", "retired")


def _validate_absolute_url(value: str, field: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"{field} must be an absolute http(s) URL, got: {value!r}")
    return value


class ProjectApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    key: str
    name: str
    description: str | None = None
    is_default: bool
    environment_urls: dict[str, str]
    is_active: bool
    application_type: str | None = None
    aliases: list[str] = []
    lifecycle_status: str = "active"
    business_owner_id: int | None = None
    technical_owner_id: int | None = None
    domain: str | None = None
    product_group: str | None = None
    product: str | None = None
    channel: str | None = None
    created_by: int | None = None
    updated_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectApplicationUpdate(BaseModel):
    key: str
    name: str
    description: str | None = None
    is_default: bool = False
    environment_urls: dict[str, str] = {}
    is_active: bool = True
    application_type: str | None = None
    aliases: list[str] = []
    lifecycle_status: str = "active"
    business_owner_id: int | None = None
    technical_owner_id: int | None = None
    domain: str | None = None
    product_group: str | None = None
    product: str | None = None
    channel: str | None = None

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        value = value.strip().lower()
        if not _KEY_RE.match(value):
            raise ValueError(
                f"key must be a lowercase slug (letters, digits, hyphens): {value!r}"
            )
        return value

    @field_validator("environment_urls")
    @classmethod
    def validate_environment_urls(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for env, url in value.items():
            env = env.strip()
            if not env:
                raise ValueError("environment name cannot be blank")
            cleaned[env] = _validate_absolute_url(url, f"environment_urls[{env}]")
        return cleaned

    @field_validator("lifecycle_status")
    @classmethod
    def validate_lifecycle_status(cls, value: str) -> str:
        value = (value or "active").strip().lower()
        if value not in LIFECYCLE_STATUSES:
            raise ValueError(f"lifecycle_status must be one of {LIFECYCLE_STATUSES}, got: {value!r}")
        return value

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, value: list[str]) -> list[str]:
        cleaned = [alias.strip() for alias in value if alias and alias.strip()]
        # Preserve order while dropping duplicates.
        seen: set[str] = set()
        deduped = []
        for alias in cleaned:
            if alias not in seen:
                seen.add(alias)
                deduped.append(alias)
        return deduped


class ProjectApplicationsUpdateRequest(BaseModel):
    applications: list[ProjectApplicationUpdate]
    change_reason: str | None = None


class ProjectExternalDependencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    application_id: int | None = None
    service_name: str
    note: str | None = None
    sandbox_url: str | None = None
    mock_strategy: str
    is_active: bool
    created_by: int | None = None
    updated_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectExternalDependencyUpdate(BaseModel):
    id: int | None = None
    application_id: int | None = None
    service_name: str
    note: str | None = None
    sandbox_url: str | None = None
    mock_strategy: Literal["intercept", "sandbox", "ignore"] = "intercept"
    is_active: bool = True

    @field_validator("sandbox_url")
    @classmethod
    def validate_sandbox_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return _validate_absolute_url(value, "sandbox_url")


class ProjectExternalDependenciesUpdateRequest(BaseModel):
    dependencies: list[ProjectExternalDependencyUpdate]
    change_reason: str | None = None


class ProjectApplicationsResponse(BaseModel):
    project_id: int
    applications: list[ProjectApplicationOut]
    external_dependencies: list[ProjectExternalDependencyOut]
    available_environments: list[str]
    last_updated: datetime | None
    updated_by: int | None


class ApplicationMappingConflict(BaseModel):
    product_group: str | None = None
    product: str | None = None
    channel: str | None = None
    application_ids: list[int]


class ProjectSettingAuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    setting_type: str
    old_value: dict | None = None
    new_value: dict | None = None
    changed_by: int | None = None
    changed_at: datetime
    source: str
    change_reason: str | None = None


class ProjectApplicationsSummary(BaseModel):
    """Registry KPI aggregates. Every count here is computed from persisted
    data — `discovery_ready` is an explicitly disclosed proxy (the contract's
    own gate: at least one active environment with a valid URL), not real
    discovery telemetry, since no discovery-session subsystem exists yet.
    `health_tracked` is always False today; the frontend must render an
    honest "Not tracked" state rather than inventing a health number.
    """

    project_id: int
    total_applications: int
    active_applications: int
    discovery_ready: int
    discovery_ready_is_proxy: bool = True
    environment_gaps: int
    mapping_conflicts: list[ApplicationMappingConflict]
    health_tracked: bool = False
    mapping_usage: dict[int, int]
