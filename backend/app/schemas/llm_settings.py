from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MODULE_SCOPES = (
    "Requirement Analysis",
    "Test Plan Generation",
    "Test Scenario Generation",
    "Test Case Generation",
    "Test Execution Assistance",
    "Defect Triage",
    "Test Reporting",
)


class LLMProviderMetadataOut(BaseModel):
    provider_name: str
    provider_key: str
    description: str
    logo_icon: str
    available_models: list[str]
    api_key_required: bool
    api_key_configured: bool
    supports_local_execution: bool
    supports_fallback_usage: bool
    enabled_for_selection: bool
    default_model: str


class ProjectLLMSettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int | None = None
    project_id: int
    provider_name: str
    provider_key: str
    model_name: str
    is_enabled: bool
    is_primary: bool
    is_fallback: bool
    fallback_priority: int | None
    temperature: float
    max_tokens: int
    timeout_seconds: int
    module_scope: list[str]
    llm_role: Literal["coding", "vision", "reasoning"] | None = None
    config_status: str
    created_by: int | None = None
    updated_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectLLMSettingUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider_key: str
    model_name: str
    is_enabled: bool = False
    is_primary: bool = False
    is_fallback: bool = False
    fallback_priority: int | None = Field(default=None, ge=1)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=4000, ge=128, le=32000)
    timeout_seconds: int = Field(default=120, ge=5, le=600)
    module_scope: list[str] = Field(default_factory=list)
    llm_role: Literal["coding", "vision", "reasoning"] | None = None

    @field_validator("module_scope")
    @classmethod
    def validate_module_scope(cls, value: list[str]) -> list[str]:
        invalid = sorted(set(value) - set(MODULE_SCOPES))
        if invalid:
            raise ValueError(f"Unsupported module scope: {', '.join(invalid)}")
        return value


class ProjectLLMSettingsUpdateRequest(BaseModel):
    settings: list[ProjectLLMSettingUpdate]
    change_reason: str | None = None


class ProjectLLMSettingsOut(BaseModel):
    project_id: int
    providers: list[LLMProviderMetadataOut]
    settings: list[ProjectLLMSettingOut]
    active_provider: ProjectLLMSettingOut | None
    active_model: str | None
    fallback_order: list[ProjectLLMSettingOut]
    system_default_provider: str
    system_default_model: str
    uses_system_default: bool
    role_defaults: dict[str, dict[str, str]]
    active_by_role: dict[str, dict[str, str]]
    last_updated: datetime | None
    updated_by: int | None
    security_status: Literal["Secure"] = "Secure"


class LLMConnectionTestRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider_key: str
    model_name: str | None = None


class LLMConnectionTestOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    success: bool
    message: str
    provider_key: str
    model_name: str | None = None
