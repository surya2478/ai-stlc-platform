from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator


# Domain constants — keep in sync with models/project.py:DOMAIN_CHOICES
DOMAIN_QA = "qa_domain"
DOMAIN_TELECOM = "telecom_domain"
ProjectDomain = Literal["qa_domain", "telecom_domain"]

# Human-readable labels shown in the UI
DOMAIN_LABELS: dict[str, str] = {
    DOMAIN_QA: "QA Domain",
    DOMAIN_TELECOM: "Telecom Domain",
}


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    # HP PPM & Governance fields
    ppm_id: str                          # required — numeric HP PPM project ID
    project_manager_name: str            # required — IT/Delivery PM full name
    business_pm_name: str | None = None  # optional — Business-side PM
    domain: ProjectDomain | None = None  # optional — project domain enum
    metadata_: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Project name must not be blank")
        if len(v) > 255:
            raise ValueError("Project name must be 255 characters or fewer")
        return v

    @field_validator("description")
    @classmethod
    def description_max_length(cls, v: str | None) -> str | None:
        if v and len(v) > 2000:
            raise ValueError("Description must be 2000 characters or fewer")
        return v

    @field_validator("ppm_id")
    @classmethod
    def ppm_id_must_be_numeric(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("PPM ID must not be blank")
        if not v.isdigit():
            raise ValueError("PPM ID must contain digits only (e.g. 10234)")
        if len(v) > 50:
            raise ValueError("PPM ID must be 50 characters or fewer")
        return v

    @field_validator("project_manager_name")
    @classmethod
    def pm_name_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Project Manager Name must not be blank")
        if len(v) > 255:
            raise ValueError("Project Manager Name must be 255 characters or fewer")
        return v

    @field_validator("business_pm_name")
    @classmethod
    def business_pm_name_max_length(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip() or None
            if v and len(v) > 255:
                raise ValueError("Business PM Name must be 255 characters or fewer")
        return v


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: Literal["active", "archived", "completed"] | None = None
    ppm_id: str | None = None
    project_manager_name: str | None = None
    business_pm_name: str | None = None
    domain: ProjectDomain | None = None
    metadata_: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Project name must not be blank")
        return v

    @field_validator("ppm_id")
    @classmethod
    def ppm_id_numeric_if_provided(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v.isdigit():
                raise ValueError("PPM ID must contain digits only (e.g. 10234)")
        return v

    @field_validator("project_manager_name")
    @classmethod
    def pm_not_blank_if_provided(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Project Manager Name must not be blank")
        return v


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    status: str
    ppm_id: str | None = None
    project_manager_name: str | None = None
    business_pm_name: str | None = None
    domain: str | None = None
    owner_id: int
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Alias used by projects.py endpoint and project_service
ProjectRead = ProjectOut


class ProjectStats(BaseModel):
    project_id: int
    total_requirements: int = 0
    total_test_cases: int = 0
    open_defects: int = 0
