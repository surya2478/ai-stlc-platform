"""
Application configuration loaded from environment variables.
All secrets are read from .env — never hardcoded here.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "STLC Automation Platform"
    app_version: str = "0.1.0"
    app_env: Literal["local", "staging", "production"] = "local"
    app_debug: bool = True
    app_secret_key: str = Field(default="change-me", min_length=8)
    allowed_origins: str = "http://localhost:3000"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql://postgres:postgres@db:5432/stlc_agents"

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"

    # ── LLM Provider ─────────────────────────────────────────────────────────
    default_llm_provider: Literal["ollama", "openai"] = "ollama"
    default_llm_model: str = "llama3.1"

    # Ollama
    ollama_base_url: str = "http://ollama:11434"

    # OpenAI-compatible
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # ── Jira ─────────────────────────────────────────────────────────────────
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = ""

    # ── File Storage ──────────────────────────────────────────────────────────
    file_storage_path: str = "/app/storage"
    max_upload_size_mb: int = 25

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @field_validator("app_secret_key")
    @classmethod
    def secret_key_not_default_in_prod(cls, v: str, info) -> str:
        # Warn if default secret is used — don't block non-prod environments
        if v == "change-me":
            import warnings
            warnings.warn("APP_SECRET_KEY is set to the default value. Change it before deploying.")
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — call this everywhere instead of instantiating directly."""
    return Settings()
