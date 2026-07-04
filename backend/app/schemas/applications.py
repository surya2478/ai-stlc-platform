import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator

_KEY_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MOCK_STRATEGIES = ("intercept", "sandbox", "ignore")


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
